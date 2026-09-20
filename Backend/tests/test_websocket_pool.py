import asyncio
from contextlib import ExitStack, suppress
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from starlette.websockets import WebSocketState

from app.api import auth, participant, websockets
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.models import EventConfig, GameConfig, Team, User


class _Socket:
    def __init__(self, *, blocked: bool = False):
        self.application_state = WebSocketState.CONNECTING
        self.messages = []
        self.started = asyncio.Event()
        self.closed = asyncio.Event()
        self._gate = asyncio.Event()
        if not blocked:
            self._gate.set()

    async def accept(self):
        self.application_state = WebSocketState.CONNECTED

    async def send_json(self, message):
        self.started.set()
        await self._gate.wait()
        self.messages.append(message)

    async def close(self, *, code, reason):
        self.application_state = WebSocketState.DISCONNECTED
        self.close_code = code
        self.close_reason = reason
        self._gate.set()
        self.closed.set()


def test_broadcast_order_and_slow_client_isolation():
    async def scenario():
        manager = websockets.ConnectionManager(queue_size=4, send_timeout_seconds=0.2)
        slow, healthy = _Socket(blocked=True), _Socket()
        await manager.connect(slow, {"role": "leader", "team_id": 1})
        await manager.connect(healthy, {"role": "leader", "team_id": 2})

        started = asyncio.get_running_loop().time()
        await manager.broadcast_event("first", {"value": 1})
        await manager.broadcast_event("second", {"value": 2})
        dispatch_seconds = asyncio.get_running_loop().time() - started

        await manager.wait_for_pending()
        assert dispatch_seconds < 0.1
        assert [message["type"] for message in healthy.messages] == ["first", "second"]
        assert slow not in manager.active_connections
        assert manager.diagnostics()["slow_client_disconnects"] == 1

        await manager.stop()
        assert not manager._client_senders
        assert not manager._client_queues

    asyncio.run(scenario())


def test_client_queue_overflow_disconnects_and_settles_sender():
    async def scenario():
        manager = websockets.ConnectionManager(queue_size=1, send_timeout_seconds=10)
        slow = _Socket(blocked=True)
        await manager.connect(slow, {"role": "leader", "team_id": 1})
        sender = manager._client_senders[slow]

        direct_send = asyncio.create_task(manager.send_event(slow, "direct"))
        await asyncio.wait_for(slow.started.wait(), timeout=1)
        await manager.broadcast_event("queued")
        await manager.broadcast_event("overflow")

        assert await asyncio.wait_for(direct_send, timeout=1) is False
        with suppress(asyncio.CancelledError):
            await sender
        await asyncio.wait_for(slow.closed.wait(), timeout=1)
        diagnostics = manager.diagnostics()
        assert diagnostics["client_queue_overflows"] == 1
        assert diagnostics["slow_client_disconnects"] == 1
        assert slow not in manager.active_connections
        assert sender.done()
        assert slow not in manager._client_senders
        assert slow not in manager._client_queues
        await manager.stop()

    asyncio.run(scenario())


def test_heartbeat_validation_is_throttled_and_revocation_is_detected(db, session_factory, monkeypatch):
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    user = User(
        name="Heartbeat Leader",
        email="heartbeat@test.example",
        password_hash="unused",
        role="leader",
        credentials_active=True,
        session_id="active-session",
        session_last_seen_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    identity = {
        "user_id": user.id,
        "role": user.role,
        "session_id": user.session_id,
        "session_last_seen_at": now,
        "last_session_validation_at": now,
    }
    opened = 0

    def tracked_factory():
        nonlocal opened
        opened += 1
        return session_factory()

    monkeypatch.setattr(websockets, "utc_now", lambda: now + timedelta(seconds=1))
    assert websockets._touch_socket_identity(identity, tracked_factory) is True
    assert websockets._touch_socket_identity(identity, tracked_factory) is True
    assert opened == 0

    validation_time = now + timedelta(seconds=settings.SESSION_TOUCH_INTERVAL_SECONDS)
    monkeypatch.setattr(websockets, "utc_now", lambda: validation_time)
    assert websockets._touch_socket_identity(identity, tracked_factory) is True
    assert opened == 1
    assert identity["last_session_validation_at"] == validation_time

    db.query(User).filter(User.id == user.id).update({User.session_id: None})
    db.commit()
    revoked_check = validation_time + timedelta(seconds=settings.SESSION_TOUCH_INTERVAL_SECONDS)
    monkeypatch.setattr(websockets, "utc_now", lambda: revoked_check)
    assert websockets._touch_socket_identity(identity, tracked_factory) is False
    assert opened == 2


def test_idle_websockets_do_not_exhaust_the_database_pool(engine):
    """More sockets than pool slots must not block ordinary HTTP requests."""
    constrained_engine = create_engine(
        engine.url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=0,
        pool_timeout=0.2,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=constrained_engine)

    with session_factory() as db:
        user = User(
            name="Pool Test Leader",
            email="pool-test@example.com",
            password_hash=get_password_hash("pool-test-password"),
            role="leader",
        )
        db.add(user)
        db.flush()
        team = Team(team_name="Pool Test Team", leader_id=user.id, is_approved=True)
        db.add(team)
        db.flush()
        user.team_id = team.id
        db.add_all([EventConfig(), GameConfig(state="WAITING")])
        db.commit()

    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(participant.router)
    app.include_router(websockets.router)
    app.state.session_factory = session_factory

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            login = client.post(
                "/login",
                data={"username": "pool-test@example.com", "password": "pool-test-password"},
            )
            assert login.status_code == 200, login.text
            token = login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            with ExitStack() as sockets:
                for _ in range(20):
                    socket = sockets.enter_context(client.websocket_connect(f"/ws/auction?token={token}"))
                    assert socket.receive_json()["type"] == "event_snapshot"

                # Connection churn schedules one short presence query. Wait for
                # that work before measuring idle sockets, not an active query.
                async def finish_presence_refresh():
                    task = websockets.manager._presence_task
                    if task is not None:
                        await task

                client.portal.call(finish_presence_refresh)
                assert constrained_engine.pool.checkedout() == 0
                responses = [client.get("/participant/dashboard", headers=headers) for _ in range(25)]
                assert all(response.status_code == 200 for response in responses)
                assert constrained_engine.pool.checkedout() == 0
    finally:
        constrained_engine.dispose()
