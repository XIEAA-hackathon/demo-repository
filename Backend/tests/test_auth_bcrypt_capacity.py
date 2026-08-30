import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from time import monotonic

import pytest

from app.api import auth
from app.core.security import get_password_hash
from app.models.models import EventConfig, GameConfig, Team, User
from app.services.auth_password_verifier import (
    AuthenticationCapacityUnavailable,
    BoundedPasswordVerifier,
)


def _create_participant(db, *, email: str, password: str = "Correct@123") -> User:
    user = User(
        name=email.split("@", 1)[0],
        email=email,
        password_hash=get_password_hash(password),
        role="leader",
    )
    db.add(user)
    db.flush()
    team = Team(team_name=f"Team {user.id}", leader_id=user.id, is_approved=True)
    db.add(team)
    db.flush()
    user.team_id = team.id
    if not db.query(EventConfig).first():
        db.add_all([EventConfig(), GameConfig(state="WAITING")])
    db.commit()
    return user


def _wait_for(event: Event, timeout: float = 2) -> None:
    assert event.wait(timeout), "password verification did not start"


def test_auth_bcrypt_concurrency_limit_is_respected():
    verifier = BoundedPasswordVerifier(
        concurrency=2,
        queue_limit=8,
        queue_timeout_seconds=2,
    )
    release = Event()
    two_started = Event()
    lock = Lock()
    started = 0

    def blocking_verify(_password: str, _password_hash: str) -> bool:
        nonlocal started
        with lock:
            started += 1
            if started >= 2:
                two_started.set()
        assert release.wait(2)
        return True

    async def exercise() -> None:
        tasks = [
            asyncio.create_task(verifier.verify("password", "hash", blocking_verify))
            for _ in range(8)
        ]
        deadline = monotonic() + 2
        while not two_started.is_set() and monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert two_started.is_set()
        assert verifier.peak_active == 2
        release.set()
        results = await asyncio.gather(*tasks)
        assert all(result.valid for result in results)

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        verifier.shutdown()


def test_auth_queue_full_is_rejected_without_unbounded_waiting():
    verifier = BoundedPasswordVerifier(
        concurrency=1,
        queue_limit=2,
        queue_timeout_seconds=1,
    )
    release = Event()
    started = Event()

    def blocking_verify(_password: str, _password_hash: str) -> bool:
        started.set()
        assert release.wait(2)
        return True

    async def exercise() -> None:
        running = asyncio.create_task(verifier.verify("password", "hash", blocking_verify))
        while not started.is_set():
            await asyncio.sleep(0.01)
        queued = asyncio.create_task(verifier.verify("password", "hash", blocking_verify))
        await asyncio.sleep(0.02)
        with pytest.raises(AuthenticationCapacityUnavailable) as caught:
            await verifier.verify("password", "hash", blocking_verify)
        assert caught.value.reason == "queue_full"
        release.set()
        await asyncio.gather(running, queued)

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        verifier.shutdown()


def test_auth_queue_wait_times_out_cleanly():
    verifier = BoundedPasswordVerifier(
        concurrency=1,
        queue_limit=2,
        queue_timeout_seconds=0.05,
    )
    release = Event()
    started = Event()

    def blocking_verify(_password: str, _password_hash: str) -> bool:
        started.set()
        assert release.wait(2)
        return True

    async def exercise() -> None:
        running = asyncio.create_task(verifier.verify("password", "hash", blocking_verify))
        while not started.is_set():
            await asyncio.sleep(0.005)
        with pytest.raises(AuthenticationCapacityUnavailable) as caught:
            await verifier.verify("password", "hash", blocking_verify)
        assert caught.value.reason == "queue_timeout"
        assert caught.value.queue_wait_ms >= 40
        release.set()
        await running

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        verifier.shutdown()


def test_queue_overflow_returns_503_and_does_not_corrupt_sessions(client, db, monkeypatch):
    first = _create_participant(db, email="first-capacity@example.com")
    second = _create_participant(db, email="second-capacity@example.com")
    verifier = BoundedPasswordVerifier(
        concurrency=1,
        queue_limit=1,
        queue_timeout_seconds=1,
    )
    release = Event()
    started = Event()

    def blocking_verify(_password: str, _password_hash: str) -> bool:
        started.set()
        assert release.wait(3)
        return True

    monkeypatch.setattr(auth, "password_verifier", verifier)
    monkeypatch.setattr(auth, "verify_password", blocking_verify)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            first_login = executor.submit(
                client.post,
                "/login",
                data={"username": first.email, "password": "Correct@123"},
            )
            _wait_for(started)
            overloaded = client.post(
                "/login",
                data={"username": second.email, "password": "Correct@123"},
            )
            assert overloaded.status_code == 503
            assert overloaded.headers["Retry-After"] == "2"
            assert overloaded.json()["detail"] == "Authentication service is busy. Please retry shortly."
            db.expire_all()
            assert db.query(User).filter(User.id == second.id).one().session_id is None
            release.set()
            assert first_login.result(timeout=3).status_code == 200
    finally:
        release.set()
        verifier.shutdown()


def test_queue_timeout_returns_503(client, db, monkeypatch):
    first = _create_participant(db, email="first-timeout@example.com")
    second = _create_participant(db, email="second-timeout@example.com")
    verifier = BoundedPasswordVerifier(
        concurrency=1,
        queue_limit=2,
        queue_timeout_seconds=0.05,
    )
    release = Event()
    started = Event()

    def blocking_verify(_password: str, _password_hash: str) -> bool:
        started.set()
        assert release.wait(3)
        return True

    monkeypatch.setattr(auth, "password_verifier", verifier)
    monkeypatch.setattr(auth, "verify_password", blocking_verify)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            first_login = executor.submit(
                client.post,
                "/login",
                data={"username": first.email, "password": "Correct@123"},
            )
            _wait_for(started)
            timed_out = client.post(
                "/login",
                data={"username": second.email, "password": "Correct@123"},
            )
            assert timed_out.status_code == 503
            assert timed_out.headers["Retry-After"] == "2"
            release.set()
            assert first_login.result(timeout=3).status_code == 200
    finally:
        release.set()
        verifier.shutdown()


def test_password_change_during_bcrypt_cannot_claim_session(client, db, monkeypatch):
    user = _create_participant(db, email="password-race@example.com", password="Old@123")
    verifier = BoundedPasswordVerifier(
        concurrency=1,
        queue_limit=2,
        queue_timeout_seconds=1,
    )
    release = Event()
    started = Event()

    def blocking_verify(_password: str, _password_hash: str) -> bool:
        started.set()
        assert release.wait(3)
        return True

    monkeypatch.setattr(auth, "password_verifier", verifier)
    monkeypatch.setattr(auth, "verify_password", blocking_verify)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            old_password_login = executor.submit(
                client.post,
                "/login",
                data={"username": user.email, "password": "Old@123"},
            )
            _wait_for(started)
            db.expire_all()
            current = db.query(User).filter(User.id == user.id).one()
            current.password_hash = get_password_hash("New@456")
            db.commit()
            release.set()
            rejected = old_password_login.result(timeout=3)
            assert rejected.status_code == 401
            db.expire_all()
            assert db.query(User).filter(User.id == user.id).one().session_id is None
    finally:
        release.set()
        verifier.shutdown()
