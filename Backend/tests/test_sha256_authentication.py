from app.core.security import verify_password
from app.models.models import Team, User


def test_registration_import_creates_sha256_leader_and_member_credentials(
    client,
    admin_headers,
    db,
):
    registration = (
        "Team Name,Leader Name,Leader Email,Leader Password,"
        "Member 1 Name,Member 1 Email,Member 1 Password\n"
        "SHA Team,SHA Leader,sha.leader@example.com,Leader@123,"
        "SHA Member,sha.member@example.com,Member@123\n"
    ).encode()
    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("sha-registration.csv", registration, "text/csv")},
    )

    assert imported.status_code == 200, imported.text
    leader = db.query(User).filter(User.email == "sha.leader@example.com").one()
    member = db.query(User).filter(User.email == "sha.member@example.com").one()
    assert leader.password_hash.startswith("sha256$")
    assert member.password_hash.startswith("sha256$")
    assert verify_password("Leader@123", leader.password_hash)
    assert verify_password("Member@123", member.password_hash)

    leader_login = client.post(
        "/login",
        data={"username": leader.email, "password": "Leader@123"},
    )
    member_login = client.post(
        "/login",
        data={"username": member.email, "password": "Member@123"},
    )
    assert leader_login.status_code == 200, leader_login.text
    assert member_login.status_code == 200, member_login.text
    assert client.post(
        "/login",
        data={"username": "sha.leader@example.com", "password": "wrong"},
    ).status_code == 401


def test_single_active_session_protection_remains_enabled(client, admin_headers, db):
    registration = (
        "Team Name,Leader Name,Leader Email,Leader Password\n"
        "Session Team,Session Leader,session.leader@example.com,Session@123\n"
    ).encode()
    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("session-registration.csv", registration, "text/csv")},
    )
    assert imported.status_code == 200, imported.text

    first = client.post(
        "/login",
        data={"username": "session.leader@example.com", "password": "Session@123"},
    )
    second = client.post(
        "/login",
        data={"username": "session.leader@example.com", "password": "Session@123"},
    )
    assert first.status_code == 200
    assert second.status_code == 409


def test_bcrypt_hashes_are_not_accepted_by_login(client, db):
    user = User(
        name="Legacy Leader",
        email="legacy@example.com",
        password_hash="$2b$12$.....................................................",
        role="leader",
        credentials_active=True,
    )
    db.add(user)
    db.flush()
    team = Team(team_name="Legacy Team", leader_id=user.id, is_approved=True)
    db.add(team)
    db.flush()
    user.team_id = team.id
    db.commit()

    response = client.post(
        "/login",
        data={"username": user.email, "password": "Legacy@123"},
    )
    assert response.status_code == 401


def test_registration_import_rejects_bcrypt_hash_input(client, admin_headers, db):
    registration = (
        "Team Name,Leader Name,Leader Email,Leader Password Hash\n"
        "Legacy Import,Legacy,legacy.import@example.com,"
        "$2b$12$.....................................................\n"
    ).encode()
    response = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("legacy.csv", registration, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["teams_processed"] == 0
    assert "sha256$salt$digest" in response.text
    assert db.query(User).filter(User.email == "legacy.import@example.com").count() == 0
