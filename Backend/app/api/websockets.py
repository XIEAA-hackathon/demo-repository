from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import User
from app.services.event_service import event_snapshot, get_team_for_user
from app.services.participant_presence import participant_presence_payload

router = APIRouter()


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
            except Exception:
                pass
        return len(matches)

    async def send_event(self, websocket: WebSocket, event_type: str, payload: dict[str, Any] | None = None):
        await websocket.send_json(make_event(event_type, payload, version=self._version))

    async def broadcast_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        exclude: set[WebSocket] | None = None,
    ):
        async with self._broadcast_lock:
            self._version += 1
            message = make_event(event_type, payload, version=self._version)
            connections = [
                connection
                for connection in self.active_connections
                if not exclude or connection not in exclude
            ]

            async def send(connection: WebSocket) -> WebSocket | None:
                try:
                    await asyncio.wait_for(connection.send_json(message), timeout=2.0)
                    return None
                except Exception:
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
        return None, None


async def _broadcast_presence_snapshot(
    session_factory: Callable[[], Session],
    *,
    exclude: set[WebSocket] | None = None,
) -> None:
    with session_factory() as db:
        presence = participant_presence_payload(
            db,
            connected_team_ids=manager.participant_team_ids(),
        )
    await manager.broadcast_event("participant_presence_changed", presence, exclude=exclude)


@router.websocket("/ws/auction")
async def websocket_auction(websocket: WebSocket):
    session_factory = getattr(websocket.app.state, "session_factory", SessionLocal)
    identity, snapshot = _authenticate_socket(websocket.query_params.get("token"), session_factory)
    if not identity or not snapshot:
        await websocket.close(code=4401, reason="Valid access token required")
        return

    await manager.connect(websocket, identity)
    if identity["role"] in ("leader", "member"):
        await _broadcast_presence_snapshot(session_factory, exclude={websocket})
    await manager.send_event(websocket, "event_snapshot", snapshot)
    try:
        while True:
            # Mutations are deliberately REST-only. Incoming frames are only
            # accepted as keep-alives and never rebroadcast.
            expires_at = identity.get("expires_at")
            if expires_at is None:
                await websocket.receive_text()
                continue
            seconds_until_expiry = expires_at - datetime.now(timezone.utc).timestamp()
            if seconds_until_expiry <= 0:
                await websocket.close(code=4401, reason="Session expired")
                break
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=seconds_until_expiry)
            except asyncio.TimeoutError:
                await websocket.close(code=4401, reason="Session expired")
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        disconnected_identity = manager.disconnect(websocket)
        if disconnected_identity and disconnected_identity.get("role") in ("leader", "member"):
            await _broadcast_presence_snapshot(session_factory)
