from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.api import auth, participant
from app.core.database import Base, get_db
from app.core.security import get_password_hash
from app.models.models import EventConfig, GameConfig, Team, User


def test_login_releases_database_connection_before_password_verification(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'login-connection.db'}",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
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
        checked_out_during_verify.append(engine.pool.checkedout())
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
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
