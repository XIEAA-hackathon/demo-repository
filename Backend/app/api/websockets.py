from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketState

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import User
from app.services.event_service import event_snapshot, get_team_for_user
from app.services.participant_presence import participant_presence_payload
from app.services.participant_session import PARTICIPANT_ROLES, touch_participant_session

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def make_event(event_type: str, payload: dict[str, Any] | None = None, *, version: int = 0) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return jsonable_encoder({
        "type": event_type,
        "timestamp": timestamp,
        "server_time": timestamp,
        "version": version,
        "payload": payload or {},
    })


class ConnectionManager:
    """In-memory fan-out for the single-instance hackathon deployment."""

    def __init__(self):
        self.active_connections: dict[WebSocket, dict[str, Any]] = {}
        self._version = 0
        self._broadcast_lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, identity: dict[str, Any]):
        await websocket.accept()
        self.active_connections[websocket] = identity

    def disconnect(self, websocket: WebSocket) -> dict[str, Any] | None:
        return self.active_connections.pop(websocket, None)

    def participant_team_ids(self) -> set[int]:
        return {
            int(identity["team_id"])
            for identity in self.active_connections.values()
            if identity.get("role") in ("leader", "member") and identity.get("team_id") is not None
        }

    async def disconnect_users(self, user_ids: set[int], *, code: int = 4401, reason: str = "Session revoked") -> int:
        matches = [
            connection
            for connection, identity in self.active_connections.items()
            if identity.get("user_id") in user_ids
        ]
        for connection in matches:
            self.disconnect(connection)
        for connection in matches:
            try:
                await connection.close(code=code, reason=reason)
            except (WebSocketDisconnect, RuntimeError, OSError):
                pass
        return len(matches)

    async def send_event(self, websocket: WebSocket, event_type: str, payload: dict[str, Any] | None = None) -> bool:
        if websocket not in self.active_connections:
            return False
        if getattr(websocket, "application_state", WebSocketState.CONNECTED) != WebSocketState.CONNECTED:
            self.disconnect(websocket)
            return False
        try:
            await asyncio.wait_for(
                websocket.send_json(make_event(event_type, payload, version=self._version)),
                timeout=2.0,
            )
            return True
        except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
            self.disconnect(websocket)
            return False

    async def broadcast_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        exclude: set[WebSocket] | None = None,
        roles: set[str] | None = None,
    ):
        async with self._broadcast_lock:
            # The shared version tracks events every client is eligible to
            # receive. Admin-only presence messages must not create apparent
            # gaps that force all participant clients to reconcile.
            if roles is None:
                self._version += 1
            message = make_event(event_type, payload, version=self._version)
            connections = [
                connection
                for connection, identity in self.active_connections.items()
                if (not exclude or connection not in exclude)
                and (roles is None or identity.get("role") in roles)
            ]

            async def send(connection: WebSocket) -> WebSocket | None:
                try:
                    await asyncio.wait_for(connection.send_json(message), timeout=2.0)
                    return None
                except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
                    return connection

            dead = [connection for connection in await asyncio.gather(*(send(connection) for connection in connections)) if connection]
        for connection in dead:
            self.disconnect(connection)

    async def broadcast_json(self, data: dict):
        """Compatibility adapter for existing REST routes while keeping one envelope."""
        event_type = str(data.get("type", "event_updated"))
        payload = {key: value for key, value in data.items() if key != "type"}
        await self.broadcast_event(event_type, payload)


manager = ConnectionManager()


def _authenticate_socket(
    token: str | None,
    session_factory: Callable[[], Session],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not token:
        return None, None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        session_id = payload.get("session_id")
        expires_at = payload.get("exp")
        # Authentication and the initial snapshot are the only database work
        # needed by this socket. Close the session before accepting the
        # long-lived connection so an idle socket never occupies the pool.
        with session_factory() as db:
            user = db.query(User).filter(User.email == email).first()
            if not user or not user.credentials_active or not user.session_id or user.session_id != session_id:
                logger.info("Rejected WebSocket session reason=session_mismatch")
                return None, None
            if user.role in PARTICIPANT_ROLES and not touch_participant_session(
                db,
                user_id=user.id,
                session_id=session_id,
                last_seen_at=user.session_last_seen_at,
                force=True,
            ):
                logger.info(
                    "Rejected WebSocket session user_id=%s role=%s reason=concurrent_replacement",
                    user.id,
                    user.role,
                )
                return None, None
            team = get_team_for_user(db, user) if user.role != "admin" else None
            identity = {
                "user_id": user.id,
                "email": user.email,
                "role": user.role,
                "team_id": team.id if team else None,
                "session_id": user.session_id,
                "expires_at": int(expires_at) if expires_at is not None else None,
            }
            snapshot = event_snapshot(db)
            snapshot["identity"] = {"role": user.role, "team_id": team.id if team else None}
            return identity, snapshot
    except JWTError:
        logger.info("Rejected WebSocket session reason=jwt_validation")
        return None, None


async def broadcast_presence_snapshot(
    session_factory: Callable[[], Session],
    *,
    exclude: set[WebSocket] | None = None,
) -> None:
    connected_team_ids = manager.participant_team_ids()

    def build_presence() -> dict[str, Any]:
        with session_factory() as db:
            return participant_presence_payload(
                db,
                connected_team_ids=connected_team_ids,
            )

    presence = await run_in_threadpool(build_presence)
    await manager.broadcast_event(
        "participant_presence_changed",
        presence,
        exclude=exclude,
        roles={"admin"},
    )


def _touch_socket_identity(
    identity: dict[str, Any],
    session_factory: Callable[[], Session],
) -> bool:
    with session_factory() as db:
        return touch_participant_session(
            db,
            user_id=int(identity["user_id"]),
            session_id=str(identity["session_id"]),
        )


async def _safe_close(websocket: WebSocket, *, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass


@router.websocket("/ws/auction")
async def websocket_auction(websocket: WebSocket):
    session_factory = getattr(websocket.app.state, "session_factory", SessionLocal)
    try:
        identity, snapshot = await run_in_threadpool(
            _authenticate_socket,
            websocket.query_params.get("token"),
            session_factory,
        )
    except SQLAlchemyError:
        logger.exception("WebSocket authentication snapshot failed before handshake.")
        await _safe_close(websocket, code=1011, reason="Initial state temporarily unavailable")
        return
    if not identity or not snapshot:
        await _safe_close(websocket, code=4401, reason="Valid access token required")
        return

    connected = False
    try:
        await manager.connect(websocket, identity)
        connected = True
        if identity["role"] in ("leader", "member"):
            try:
                await broadcast_presence_snapshot(session_factory, exclude={websocket})
            except SQLAlchemyError:
                logger.warning("Participant presence snapshot was skipped after WebSocket connect.")
        # The first client-visible frame is sent only after all initial DB work
        # has closed its short-lived session, so an idle socket never overlaps
        # with a checked-out connection.
        if not await manager.send_event(websocket, "event_snapshot", snapshot):
            return

        while True:
            # Mutations are deliberately REST-only. Incoming frames are only
            # accepted as keep-alives and never rebroadcast.
            expires_at = identity.get("expires_at")
            if expires_at is None:
                message = await websocket.receive_text()
                if identity["role"] in PARTICIPANT_ROLES and message == "heartbeat":
                    session_alive = await run_in_threadpool(
                        _touch_socket_identity,
                        identity,
                        session_factory,
                    )
                    if not session_alive:
                        await websocket.close(code=4401, reason="Session revoked")
                        break
                    await manager.send_event(websocket, "session_heartbeat", {"status": "active"})
                continue
            seconds_until_expiry = expires_at - datetime.now(timezone.utc).timestamp()
            if seconds_until_expiry <= 0:
                await websocket.close(code=4401, reason="Session expired")
                break
            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=seconds_until_expiry,
                )
                if identity["role"] in PARTICIPANT_ROLES and message == "heartbeat":
                    session_alive = await run_in_threadpool(
                        _touch_socket_identity,
                        identity,
                        session_factory,
                    )
                    if not session_alive:
                        await websocket.close(code=4401, reason="Session revoked")
                        break
                    await manager.send_event(websocket, "session_heartbeat", {"status": "active"})
            except asyncio.TimeoutError:
                await websocket.close(code=4401, reason="Session expired")
                break
    except WebSocketDisconnect:
        pass
    except (RuntimeError, OSError):
        pass
    except Exception:
        logger.exception("Unexpected error in established WebSocket connection.")
        await _safe_close(websocket, code=1011, reason="WebSocket connection error")
    finally:
        disconnected_identity = manager.disconnect(websocket) if connected else None
        if disconnected_identity and disconnected_identity.get("role") in ("leader", "member"):
            try:
                await broadcast_presence_snapshot(session_factory)
            except SQLAlchemyError:
                logger.warning("Participant presence snapshot was skipped after WebSocket disconnect.")
