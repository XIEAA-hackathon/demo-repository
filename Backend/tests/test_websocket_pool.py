from contextlib import ExitStack

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.api import auth, participant, websockets
from app.core.database import Base, get_db
from app.core.security import get_password_hash
from app.models.models import EventConfig, GameConfig, Team, User


def test_idle_websockets_do_not_exhaust_the_database_pool(tmp_path):
    """More sockets than pool slots must not block ordinary HTTP requests."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'websocket-pool.db'}",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=0,
        pool_timeout=0.2,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

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

                assert engine.pool.checkedout() == 0
                responses = [client.get("/participant/dashboard", headers=headers) for _ in range(25)]
                assert all(response.status_code == 200 for response in responses)
                assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
