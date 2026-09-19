import pytest

from app.core.security import get_password_hash
from app.models.models import Team, User


PASSWORD = "portal-test-password"


def _create_portal_users(db):
    leader = User(
        name="Leader",
        email="leader@portal.test",
        password_hash=get_password_hash(PASSWORD),
        role="leader",
        credentials_active=True,
    )
    db.add(leader)
    db.flush()

    team = Team(team_name="Portal Team", leader_id=leader.id, is_approved=True)
    db.add(team)
    db.flush()
    leader.team_id = team.id

    users = {
        "leader": leader,
        "member": User(
            name="Member",
            email="member@portal.test",
            password_hash=get_password_hash(PASSWORD),
            role="member",
            team_id=team.id,
            credentials_active=True,
        ),
        "admin": User(
            name="Admin",
            email="admin@portal.test",
            password_hash=get_password_hash(PASSWORD),
            role="admin",
            credentials_active=True,
        ),
        "lab_admin": User(
            name="Lab Admin",
            email="lab-admin@portal.test",
            password_hash=get_password_hash(PASSWORD),
            role="lab_admin",
            credentials_active=True,
        ),
        "display": User(
            name="Display",
            email="display@portal.test",
            password_hash=get_password_hash(PASSWORD),
            role="display",
            credentials_active=True,
        ),
    }
    db.add_all(user for role, user in users.items() if role != "leader")
    db.commit()
    return users


def _login(client, path, user):
    return client.post(path, data={"username": user.email.upper(), "password": PASSWORD})


@pytest.mark.parametrize(
    ("role", "expected_status", "expected_detail"),
    [
        ("leader", 200, None),
        ("member", 200, None),
        ("admin", 403, "Use the dedicated Event Admin login."),
        ("lab_admin", 403, "Use the dedicated Lab Admin login."),
        ("display", 403, "Use the dedicated leaderboard display login."),
    ],
)
def test_participant_login_role_matrix(client, db, role, expected_status, expected_detail):
    users = _create_portal_users(db)

    response = _login(client, "/login", users[role])

    assert response.status_code == expected_status
    if expected_detail:
        assert response.json()["detail"] == expected_detail


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("admin", 200), ("lab_admin", 401), ("leader", 401), ("member", 401), ("display", 401)],
)
def test_admin_login_role_matrix(client, db, role, expected_status):
    users = _create_portal_users(db)
    response = _login(client, "/admin/login", users[role])

    assert response.status_code == expected_status
    if expected_status == 401:
        assert response.json()["detail"] == "Incorrect Admin ID or password"


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("lab_admin", 200), ("admin", 401), ("leader", 401), ("member", 401), ("display", 401)],
)
def test_lab_admin_login_role_matrix(client, db, role, expected_status):
    users = _create_portal_users(db)

    response = _login(client, "/lab-admin/login", users[role])

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("display", 200), ("admin", 401), ("lab_admin", 401), ("leader", 401), ("member", 401)],
)
def test_leaderboard_login_role_matrix(client, db, role, expected_status):
    users = _create_portal_users(db)

    response = _login(client, "/leaderboard/login", users[role])

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "login_path", "expected_status"),
    [
        ("leader", "/login", 200),
        ("member", "/login", 200),
        ("lab_admin", "/lab-admin/login", 403),
        ("admin", "/admin/login", 403),
    ],
)
def test_participant_session_rejects_wrong_portal_tokens(client, db, role, login_path, expected_status):
    users = _create_portal_users(db)
    login_response = _login(client, login_path, users[role])
    assert login_response.status_code == 200

    response = client.get(
        "/participant/session",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )

    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json()["role"] == role


def test_participant_single_session_protection_remains_active(client, db):
    users = _create_portal_users(db)

    first = _login(client, "/login", users["leader"])
    second = _login(client, "/login", users["leader"])

    assert first.status_code == 200
    assert second.status_code == 409
