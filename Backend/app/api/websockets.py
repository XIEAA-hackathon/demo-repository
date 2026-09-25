from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime, timezone
from time import monotonic, perf_counter
from typing import Any, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketState

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import User
from app.services.event_service import event_snapshot, get_team_for_user
from app.services.participant_presence import participant_presence_payload
from app.services.participant_session import (
    PARTICIPANT_ROLES,
    participant_session_needs_touch,
    touch_participant_session,
    utc_now,
)

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

    def __init__(self, *, queue_size: int = 256, send_timeout_seconds: float = 0.5):
        self.active_connections: dict[WebSocket, dict[str, Any]] = {}
        self._version = 0
        self._queue_size = queue_size
        self._send_timeout_seconds = send_timeout_seconds
        self._broadcast_queue: asyncio.Queue | None = None
        self._broadcast_worker: asyncio.Task | None = None
        self._worker_loop: asyncio.AbstractEventLoop | None = None
        self._client_queues: dict[WebSocket, asyncio.Queue] = {}
        self._client_senders: dict[WebSocket, asyncio.Task] = {}
        self._client_close_tasks: set[asyncio.Task] = set()
        self._slow_client_disconnects = 0
        self._client_queue_overflows = 0
        self._dropped_publish_events = 0
        self._drop_counter_started_at = monotonic()
        self._last_drop_log_at = 0.0
        self._presence_generation = 0
        self._presence_task: asyncio.Task | None = None
        self._presence_session_factory: Callable[[], Session] | None = None

    def start(self) -> None:
        """Start one bounded, ordered fan-out worker for the current event loop."""
        loop = asyncio.get_running_loop()
        if (
            self._broadcast_worker is not None
            and not self._broadcast_worker.done()
            and self._worker_loop is loop
        ):
            return
        self._broadcast_queue = asyncio.Queue(maxsize=self._queue_size)
        self._worker_loop = loop
        self._broadcast_worker = loop.create_task(
            self._run_broadcast_worker(),
            name="websocket-broadcast",
        )

    async def stop(self) -> None:
        presence_task = self._presence_task
        if presence_task is not None and not presence_task.done():
            presence_task.cancel()
            with suppress(asyncio.CancelledError):
                await presence_task
        self._presence_task = None
        self._presence_session_factory = None
        worker = self._broadcast_worker
        if worker is not None and not worker.done():
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        self._broadcast_worker = None
        self._broadcast_queue = None
        self._worker_loop = None
        senders = list(self._client_senders.values())
        for sender in senders:
            sender.cancel()
        for sender in senders:
            with suppress(asyncio.CancelledError):
                await sender
        self._client_senders.clear()
        self._client_queues.clear()
        self.active_connections.clear()
        close_tasks = list(self._client_close_tasks)
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        self._client_close_tasks.clear()

    async def wait_for_pending(self) -> None:
        """Test helper: wait until currently queued broadcasts reach client senders."""
        if self._broadcast_queue is not None:
            await self._broadcast_queue.join()
        await asyncio.gather(*(queue.join() for queue in list(self._client_queues.values())))

    async def _run_broadcast_worker(self) -> None:
        assert self._broadcast_queue is not None
        while True:
            event_type, payload, exclude, roles, completion = await self._broadcast_queue.get()
            try:
                await self._deliver_broadcast(event_type, payload, exclude=exclude, roles=roles)
                if completion is not None and not completion.done():
                    completion.set_result(None)
            except Exception as exc:
                logger.exception("WebSocket broadcast worker failed event_type=%s", event_type)
                if completion is not None and not completion.done():
                    completion.set_exception(exc)
            finally:
                self._broadcast_queue.task_done()

    def publish_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        exclude: set[WebSocket] | None = None,
        roles: set[str] | None = None,
    ) -> bool:
        """Queue a committed hot-path event without waiting on client sockets."""
        self.start()
        assert self._broadcast_queue is not None
        try:
            self._broadcast_queue.put_nowait((event_type, payload, exclude, roles, None))
            return True
        except asyncio.QueueFull:
            self._dropped_publish_events += 1
            now = monotonic()
            if self._dropped_publish_events == 1 or now - self._last_drop_log_at >= 5:
                elapsed = max(1.0, now - self._drop_counter_started_at)
                logger.error(
                    "WebSocket broadcast queue full event_type=%s queue_depth=%s "
                    "dropped_total=%s dropped_per_second=%.3f",
                    event_type,
                    self._broadcast_queue.qsize(),
                    self._dropped_publish_events,
                    self._dropped_publish_events / elapsed,
                )
                self._last_drop_log_at = now
            return False

    def diagnostics(self) -> dict[str, int | float | bool]:
        queue = self._broadcast_queue
        return {
            "active_connections": len(self.active_connections),
            "broadcast_queue_depth": queue.qsize() if queue is not None else 0,
            "broadcast_queue_capacity": self._queue_size,
            "broadcast_dropped_total": self._dropped_publish_events,
            "broadcast_worker_running": bool(self._broadcast_worker and not self._broadcast_worker.done()),
            "slow_client_disconnects": self._slow_client_disconnects,
            "client_queue_overflows": self._client_queue_overflows,
        }

    def schedule_presence_refresh(
        self,
        session_factory: Callable[[], Session],
        *,
        debounce_seconds: float = 0.35,
    ) -> None:
        """Coalesce participant connection churn into one authoritative refresh."""
        self._presence_generation += 1
        self._presence_session_factory = session_factory
        if self._presence_task is None or self._presence_task.done():
            self._presence_task = asyncio.get_running_loop().create_task(
                self._run_presence_refresh(debounce_seconds),
                name="websocket-presence-refresh",
            )

    async def _run_presence_refresh(self, debounce_seconds: float) -> None:
        try:
            while True:
                generation = self._presence_generation
                await asyncio.sleep(debounce_seconds)
                if generation != self._presence_generation:
                    continue
                session_factory = self._presence_session_factory
                if session_factory is None:
                    return
                try:
                    await broadcast_presence_snapshot(session_factory, connection_manager=self)
                except Exception:
                    logger.exception("Participant presence snapshot was skipped after connection change.")
                if generation == self._presence_generation:
                    return
        finally:
            self._presence_task = None

    async def connect(self, websocket: WebSocket, identity: dict[str, Any]):
        await websocket.accept()
        self.active_connections[websocket] = identity
        self._ensure_client_sender(websocket)

    def disconnect(self, websocket: WebSocket) -> dict[str, Any] | None:
        identity = self.active_connections.pop(websocket, None)
        self._client_queues.pop(websocket, None)
        sender = self._client_senders.pop(websocket, None)
        if sender is not None and sender is not asyncio.current_task():
            sender_loop = sender.get_loop()
            if sender_loop is asyncio.get_running_loop():
                sender.cancel()
            elif sender_loop.is_running():
                sender_loop.call_soon_threadsafe(sender.cancel)
            else:
                sender.cancel()
        return identity

    async def disconnect_and_wait(self, websocket: WebSocket) -> dict[str, Any] | None:
        sender = self._client_senders.get(websocket)
        identity = self.disconnect(websocket)
        if sender is not None and sender is not asyncio.current_task():
            sender_loop = sender.get_loop()
            if sender_loop is asyncio.get_running_loop():
                with suppress(asyncio.CancelledError):
                    await sender
            elif sender_loop.is_running():
                async def wait_for_sender() -> None:
                    with suppress(asyncio.CancelledError):
                        await sender

                await asyncio.wrap_future(
                    asyncio.run_coroutine_threadsafe(wait_for_sender(), sender_loop)
                )
        return identity

    def _ensure_client_sender(self, websocket: WebSocket) -> asyncio.Queue:
        queue = self._client_queues.get(websocket)
        if queue is not None:
            return queue
        queue = asyncio.Queue(maxsize=self._queue_size)
        self._client_queues[websocket] = queue
        self._client_senders[websocket] = asyncio.get_running_loop().create_task(
            self._run_client_sender(websocket, queue),
            name="websocket-client-sender",
        )
        return queue

    async def _run_client_sender(self, websocket: WebSocket, queue: asyncio.Queue) -> None:
        try:
            while True:
                message, completion = await queue.get()
                try:
                    await asyncio.wait_for(websocket.send_json(message), timeout=self._send_timeout_seconds)
                    if completion is not None and not completion.done():
                        completion.set_result(True)
                except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError) as exc:
                    if isinstance(exc, asyncio.TimeoutError):
                        self._slow_client_disconnects += 1
                    if completion is not None and not completion.done():
                        completion.set_result(False)
                    self.disconnect(websocket)
                    await _safe_close(websocket, code=1013, reason="Client send timed out")
                    return
                except asyncio.CancelledError:
                    if completion is not None and not completion.done():
                        completion.set_result(False)
                    raise
                except Exception as exc:
                    logger.warning("WebSocket client sender failed error=%s", exc.__class__.__name__)
                    if completion is not None and not completion.done():
                        completion.set_result(False)
                    self.disconnect(websocket)
                    await _safe_close(websocket, code=1011, reason="Client send failed")
                    return
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            raise
        finally:
            while not queue.empty():
                _message, completion = queue.get_nowait()
                if completion is not None and not completion.done():
                    completion.set_result(False)
                queue.task_done()
            if self._client_senders.get(websocket) is asyncio.current_task():
                self._client_senders.pop(websocket, None)
                self._client_queues.pop(websocket, None)

    def _enqueue_client_message(self, websocket: WebSocket, message: dict[str, Any], completion=None) -> bool:
        if websocket not in self.active_connections:
            return False
        if getattr(websocket, "application_state", WebSocketState.CONNECTED) != WebSocketState.CONNECTED:
            self.disconnect(websocket)
            return False
        queue = self._ensure_client_sender(websocket)
        try:
            queue.put_nowait((message, completion))
            return True
        except asyncio.QueueFull:
            self._client_queue_overflows += 1
            self._slow_client_disconnects += 1
            if completion is not None and not completion.done():
                completion.set_result(False)
            self.disconnect(websocket)
            close_task = asyncio.get_running_loop().create_task(
                _safe_close(websocket, code=1013, reason="Client outbound queue full"),
                name="websocket-slow-client-close",
            )
            self._client_close_tasks.add(close_task)
            close_task.add_done_callback(self._client_close_tasks.discard)
            return False

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
            await self.disconnect_and_wait(connection)
        for connection in matches:
            try:
                await connection.close(code=code, reason=reason)
            except (WebSocketDisconnect, RuntimeError, OSError):
                pass
        return len(matches)

    async def send_event(self, websocket: WebSocket, event_type: str, payload: dict[str, Any] | None = None) -> bool:
        completion = asyncio.get_running_loop().create_future()
        if not self._enqueue_client_message(
            websocket, make_event(event_type, payload, version=self._version), completion,
        ):
            return False
        return await completion

    async def broadcast_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        exclude: set[WebSocket] | None = None,
        roles: set[str] | None = None,
    ):
        self.start()
        assert self._broadcast_queue is not None
        completion = asyncio.get_running_loop().create_future()
        await self._broadcast_queue.put((event_type, payload, exclude, roles, completion))
        await completion

    async def _deliver_broadcast(
        self,
        event_type: str,
        payload: dict[str, Any] | None,
        *,
        exclude: set[WebSocket] | None,
        roles: set[str] | None,
    ) -> None:
        if event_type == "lab_allocation_updated":
            for change in (payload or {}).get("assignments", []):
                await self._deliver_broadcast("lab_assignment_changed", change, exclude=None, roles={"admin", "lab_admin", "leader", "member"})
            payload = {key: value for key, value in (payload or {}).items() if key != "assignments"}
        # The shared version tracks events every client is eligible to receive.
        # Operator-only presence messages must not create participant version gaps.
        if roles is None:
            self._version += 1
        message = make_event(event_type, payload, version=self._version)
        connections = [
            connection
            for connection, identity in self.active_connections.items()
            if (not exclude or connection not in exclude)
            and (roles is None or identity.get("role") in roles)
            and (event_type != "lab_assignment_changed" or identity.get("role") in {"admin", "lab_admin"}
                 or identity.get("team_id") == (payload or {}).get("team_id"))
        ]

        for connection in connections:
            self._enqueue_client_message(connection, message)

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
            if not user:
                logger.info("Rejected WebSocket session logout_reason=ACCOUNT_NOT_FOUND")
                return None, None
            if not user.credentials_active:
                logger.info("Rejected WebSocket session user_id=%s logout_reason=ACCOUNT_DISABLED", user.id)
                return None, None
            if not user.session_id:
                logger.info("Rejected WebSocket session user_id=%s logout_reason=SESSION_REVOKED", user.id)
                return None, None
            if user.session_id != session_id:
                logger.info("Rejected WebSocket session user_id=%s logout_reason=SESSION_REPLACED", user.id)
                return None, None
            authenticated_at = utc_now()
            session_needs_touch = participant_session_needs_touch(
                user.session_last_seen_at,
                now=authenticated_at,
            )
            if user.role in PARTICIPANT_ROLES and not touch_participant_session(
                db,
                user_id=user.id,
                session_id=session_id,
                last_seen_at=user.session_last_seen_at,
                now=authenticated_at,
            ):
                logger.info(
                    "Rejected WebSocket session user_id=%s role=%s logout_reason=SESSION_MISMATCH",
                    user.id,
                    user.role,
                )
                return None, None
            team = get_team_for_user(db, user) if user.role in PARTICIPANT_ROLES else None
            identity = {
                "user_id": user.id,
                "email": user.email,
                "role": user.role,
                "team_id": team.id if team else None,
                "session_id": user.session_id,
                "session_last_seen_at": (
                    authenticated_at if session_needs_touch else user.session_last_seen_at
                ),
                "last_session_validation_at": authenticated_at,
                "expires_at": int(expires_at) if expires_at is not None else None,
            }
            snapshot = event_snapshot(db)
            snapshot["identity"] = {"role": user.role, "team_id": team.id if team else None}
            return identity, snapshot
    except ExpiredSignatureError:
        logger.info("Rejected WebSocket session logout_reason=JWT_EXPIRED")
        return None, None
    except JWTError:
        logger.info("Rejected WebSocket session logout_reason=JWT_INVALID")
        return None, None


def _heartbeat_frame(message: str) -> tuple[bool, int | float | None]:
    if message == "heartbeat":
        return True, None
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return False, None
    if not isinstance(payload, dict) or payload.get("type") != "heartbeat":
        return False, None
    client_time = payload.get("client_time")
    return True, client_time if isinstance(client_time, (int, float)) else None


async def broadcast_presence_snapshot(
    session_factory: Callable[[], Session],
    *,
    exclude: set[WebSocket] | None = None,
    connection_manager: ConnectionManager = manager,
) -> None:
    started_at = perf_counter()
    connected_team_ids = connection_manager.participant_team_ids()

    def build_presence() -> dict[str, Any]:
        with session_factory() as db:
            return participant_presence_payload(
                db,
                connected_team_ids=connected_team_ids,
            )

    presence = await run_in_threadpool(build_presence)
    await connection_manager.broadcast_event(
        "participant_presence_changed",
        presence,
        exclude=exclude,
        roles={"admin", "lab_admin"},
    )
    logger.info(
        "Participant presence rebuilt connected_teams=%s duration_ms=%.2f",
        len(connected_team_ids),
        (perf_counter() - started_at) * 1000,
    )


def _touch_socket_identity(
    identity: dict[str, Any],
    session_factory: Callable[[], Session],
) -> bool:
    now = utc_now()
    if not participant_session_needs_touch(identity.get("last_session_validation_at"), now=now):
        return True
    last_seen_at = identity.get("session_last_seen_at")
    with session_factory() as db:
        role = identity.get("role")
        if role is not None and role not in PARTICIPANT_ROLES:
            alive = db.query(User.id).filter(
                User.id == int(identity["user_id"]),
                User.role == str(role),
                User.credentials_active.is_(True),
                User.session_id == str(identity["session_id"]),
            ).first() is not None
            if alive:
                identity["last_session_validation_at"] = now
            return alive
        if participant_session_needs_touch(last_seen_at, now=now):
            alive = touch_participant_session(
                db,
                user_id=int(identity["user_id"]),
                session_id=str(identity["session_id"]),
                last_seen_at=last_seen_at,
                now=now,
            )
            if alive:
                identity["session_last_seen_at"] = now
                identity["last_session_validation_at"] = now
            return alive
        persisted = db.query(User.session_last_seen_at).filter(
            User.id == int(identity["user_id"]),
            User.role.in_(PARTICIPANT_ROLES),
            User.credentials_active.is_(True),
            User.session_id == str(identity["session_id"]),
        ).first()
        if persisted is None:
            return False
        persisted_last_seen_at = persisted[0]
        if participant_session_needs_touch(persisted_last_seen_at, now=now):
            alive = touch_participant_session(
                db,
                user_id=int(identity["user_id"]),
                session_id=str(identity["session_id"]),
                last_seen_at=persisted_last_seen_at,
                now=now,
            )
            if alive:
                identity["session_last_seen_at"] = now
                identity["last_session_validation_at"] = now
            return alive
        identity["session_last_seen_at"] = persisted_last_seen_at
        identity["last_session_validation_at"] = now
        return True


async def _validate_socket_identity(
    identity: dict[str, Any],
    session_factory: Callable[[], Session],
) -> bool:
    if not participant_session_needs_touch(identity.get("last_session_validation_at")):
        return True
    return await run_in_threadpool(_touch_socket_identity, identity, session_factory)


async def _safe_close(websocket: WebSocket, *, code: int, reason: str) -> None:
    try:
        if websocket.application_state == WebSocketState.CONNECTING:
            await websocket.accept()
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
    except Exception:
        logger.exception("Unexpected WebSocket authentication failure before handshake.")
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
            manager.schedule_presence_refresh(session_factory)
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
                is_heartbeat, client_time = _heartbeat_frame(message)
                if is_heartbeat:
                    session_alive = await _validate_socket_identity(identity, session_factory)
                    if not session_alive:
                        await websocket.close(code=4401, reason="Session revoked")
                        break
                    await manager.send_event(
                        websocket,
                        "session_heartbeat",
                        {"status": "active", "client_time": client_time},
                    )
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
                is_heartbeat, client_time = _heartbeat_frame(message)
                if is_heartbeat:
                    session_alive = await _validate_socket_identity(identity, session_factory)
                    if not session_alive:
                        await websocket.close(code=4401, reason="Session revoked")
                        break
                    await manager.send_event(
                        websocket,
                        "session_heartbeat",
                        {"status": "active", "client_time": client_time},
                    )
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
        if connected:
            await manager.disconnect_and_wait(websocket)
        if connected and identity.get("role") in ("leader", "member"):
            manager.schedule_presence_refresh(session_factory)
