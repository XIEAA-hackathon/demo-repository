from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.api import auth, participant
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.models import EventActivityLog, EventConfig, GameConfig, Team, User


def _concurrent_login_app(session_factory, leader_count: int):
    with session_factory() as db:
        for index in range(leader_count):
            user = User(
                name=f"Concurrent Leader {index}",
                email=f"leader-{index}@concurrency.test",
                password_hash=get_password_hash("correct-password"),
                role="leader",
            )
            db.add(user)
            db.flush()
            team = Team(team_name=f"Concurrent Team {index}", leader_id=user.id, is_approved=True)
            db.add(team)
            db.flush()
            user.team_id = team.id
        db.add_all([EventConfig(), GameConfig(state="WAITING")])
        db.commit()

    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(participant.router)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    return app


def test_login_releases_database_connection_before_password_verification(engine, monkeypatch):
    constrained_engine = create_engine(
        engine.url,
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=constrained_engine)
    with session_factory() as db:
        user = User(
            name="Concurrent Leader",
            email="concurrent@example.com",
            password_hash=get_password_hash("correct-password"),
            role="leader",
        )
        db.add(user)
        db.flush()
        team = Team(team_name="Concurrent Team", leader_id=user.id, is_approved=True)
        db.add(team)
        db.flush()
        user.team_id = team.id
        db.add_all([EventConfig(), GameConfig(state="WAITING")])
        db.commit()

    checked_out_during_verify = []

    def observe_verify(_plain_password, _password_hash):
        checked_out_during_verify.append(constrained_engine.pool.checkedout())
        return True

    monkeypatch.setattr(auth, "verify_password", observe_verify)
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(participant.router)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            login = client.post(
                "/login",
                data={"username": "concurrent@example.com", "password": "correct-password"},
            )
            assert login.status_code == 200, login.text
            dashboard = client.get(
                "/participant/dashboard",
                headers={"Authorization": f"Bearer {login.json()['access_token']}"},
            )
            assert dashboard.status_code == 200, dashboard.text

        assert checked_out_during_verify == [0]
        assert constrained_engine.pool.checkedout() == 0
    finally:
        constrained_engine.dispose()


def test_ten_simultaneous_logins_acquire_exactly_one_leader_session(session_factory):
    app = _concurrent_login_app(session_factory, 1)
    with TestClient(app) as client:
        def login_once(_index: int):
            return client.post(
                "/login",
                data={"username": "leader-0@concurrency.test", "password": "correct-password"},
            )

        with ThreadPoolExecutor(max_workers=10) as executor:
            responses = list(executor.map(login_once, range(10)))

        successes = [response for response in responses if response.status_code == 200]
        rejected = [response for response in responses if response.status_code == 409]
        assert len(successes) == 1
        assert len(rejected) == 9
        assert all("already logged in" in response.json()["detail"] for response in rejected)

        active_headers = {"Authorization": f"Bearer {successes[0].json()['access_token']}"}
        assert client.get("/participant/dashboard", headers=active_headers).status_code == 200

    with session_factory() as db:
        leader = db.query(User).filter(User.email == "leader-0@concurrency.test").one()
        assert leader.session_id
        assert leader.session_created_at is not None
        assert leader.session_last_seen_at is not None
        assert db.query(EventActivityLog).filter(EventActivityLog.action == "auth.login").count() == 1
        assert db.query(EventActivityLog).filter(
            EventActivityLog.action == "auth.login_rejected_duplicate"
        ).count() == 9


def test_fifty_distinct_leaders_can_login_concurrently(session_factory):
    app = _concurrent_login_app(session_factory, 50)
    with TestClient(app) as client:
        def login_leader(index: int):
            return client.post(
                "/login",
                data={"username": f"leader-{index}@concurrency.test", "password": "correct-password"},
            )

        with ThreadPoolExecutor(max_workers=25) as executor:
            responses = list(executor.map(login_leader, range(50)))

    assert [response.status_code for response in responses] == [200] * 50
    with session_factory() as db:
        assert db.query(User).filter(User.session_id.is_not(None)).count() == 50
        assert db.query(User).filter(User.session_last_seen_at.is_not(None)).count() == 50
