import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import get_password_hash
from app.models.models import User, EventConfig, GameConfig, ProblemStatement
from app.api import auth, team, problem_statements, auction, wildcard, participant, admin, websockets

# ---------------------------------------------------------------- helpers

def _create_admin(db):
    admin_user = User(
        name="Admin", email="admin@test.com",
        password_hash=get_password_hash("admin123"), role="admin",
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)
    return admin_user

def _create_event_defaults(db):
    if not db.query(EventConfig).first():
        db.add(EventConfig())
        db.add(GameConfig(state="WAITING"))
        db.commit()

def _create_problem(db, ps_number="PS-01", round_no=1):
    ps = ProblemStatement(ps_number=ps_number, title=f"Title {ps_number}", description="desc", round=round_no)
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return ps

# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine

@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def _clean_db(engine, session_factory):
    """Truncate all tables before each test so state never leaks between tests."""
    db = session_factory()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()
    yield

@pytest.fixture()
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture()
def client(engine, session_factory):
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(team.router)
    app.include_router(problem_statements.router)
    app.include_router(auction.router)
    app.include_router(wildcard.router)
    app.include_router(participant.router)
    app.include_router(admin.router)
    app.include_router(websockets.router)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)

@pytest.fixture()
def admin_headers(client, db):
    _create_event_defaults(db)
    admin_user = _create_admin(db)
    response = client.post("/login", data={"username": admin_user.email, "password": "admin123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

@pytest.fixture()
def csv_bytes():
    return (
        "Team Name,Leader Name,Leader Email,Member 1,Member 1 Email,Member 2\n"
        "Team Alpha,Alice,alice@test.com,Aarav,aarav@test.com,Diya\n"
        "Team Beta,Bob,bob@test.com,Charlie,charlie@test.com,Rohan\n"
        "Team Gamma,Carol,carol@test.com,,,\n"
    ).encode("utf-8")

@pytest.fixture()
def login_headers_factory(client):
    def _make(email, password="temp-pass"):
        response = client.post("/login", data={"username": email, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    return _make
