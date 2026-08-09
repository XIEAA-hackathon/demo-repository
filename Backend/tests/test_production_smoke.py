from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.models import EventConfig, GameConfig, Member, Team, User
from app.core.security import get_password_hash


def test_health_and_version_endpoints():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/version").json() == {"commit": settings.DEPLOYED_COMMIT}


def test_participant_login_and_protected_dashboard(client, db):
    leader = User(
        name="Demo Leader",
        email="leader.integration@example.com",
        role="leader",
        password_hash=get_password_hash("IntegrationLeader@123"),
    )
    db.add(leader)
    db.flush()
    team = Team(team_name="Integration Team", leader_id=leader.id, coins=1000, is_approved=True)
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.add(Member(team_id=team.id, member_name="Member One", email="one.integration@example.com"))
    db.add(Member(team_id=team.id, member_name="Member Two", email="two.integration@example.com"))
    db.add(EventConfig())
    db.add(GameConfig(state="WAITING"))
    db.commit()

    login = client.post(
        "/login",
        data={"username": leader.email, "password": "IntegrationLeader@123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    dashboard = client.get("/participant/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["team"]["team_name"] == "Integration Team"
    assert dashboard.json()["isLeader"] is True


def test_admin_role_is_enforced(client, db):
    leader = User(
        name="Non Admin",
        email="not-admin@example.com",
        role="leader",
        password_hash=get_password_hash("NotAdmin@123"),
    )
    db.add(leader)
    db.flush()
    team = Team(team_name="Non Admin Team", leader_id=leader.id, is_approved=True)
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.commit()
    login = client.post("/login", data={"username": leader.email, "password": "NotAdmin@123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/admin/state", headers=headers).status_code == 403


def test_admin_login_rejects_invalid_password_and_requires_authentication(client, db):
    admin = User(
        name="Production Admin",
        email="production-admin@example.com",
        role="admin",
        password_hash=get_password_hash("Correct-Password-123"),
    )
    db.add(admin)
    db.commit()

    valid = client.post("/login", data={"username": admin.email, "password": "Correct-Password-123"})
    invalid = client.post("/login", data={"username": admin.email, "password": "wrong-password"})

    assert valid.status_code == 200
    assert valid.json()["access_token"]
    assert invalid.status_code == 401
    assert client.get("/admin/state").status_code == 401


def test_admin_cannot_enter_participant_panel(client, db):
    admin = User(
        name="Panel Admin",
        email="panel-admin@example.com",
        role="admin",
        password_hash=get_password_hash("Panel-Password-123"),
    )
    db.add(admin)
    db.commit()
    login = client.post("/login", data={"username": admin.email, "password": "Panel-Password-123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/participant/dashboard", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Participant access required"


def test_admin_can_read_event_state(client, admin_headers):
    response = client.get("/admin/state", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["event_state"] == "WAITING"
