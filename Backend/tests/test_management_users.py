from app.core.config import settings
from app.core.security import get_password_hash
from app.models.models import EventConfig, GameConfig, ProblemStatement, Team, User
from app.services.demo_seed import provision_demo_accounts


def _login(client, email: str, password: str, route: str = "/login") -> dict:
    response = client.post(route, data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_managed_user_lifecycle_authorization_and_reset_isolation(client, db):
    db.add(EventConfig())
    db.add(GameConfig(state="WAITING"))
    db.commit()
    provision_demo_accounts(db)
    participant = User(
        name="Imported Leader",
        email="imported@example.com",
        password_hash=get_password_hash("Imported@123"),
        role="leader",
        is_system_account=False,
    )
    db.add(participant)
    db.flush()
    team = Team(team_name="Imported Team", leader_id=participant.id, is_approved=True, coins=1000)
    db.add(team)
    db.flush()
    participant.team_id = team.id
    problem = ProblemStatement(ps_number="R1-MANAGED", title="Keep me", description="Event data", round=1)
    db.add(problem)
    game = db.query(GameConfig).first()
    game.state = "ROUND1_PREVIEW"
    db.commit()

    demo_admin_headers = _login(client, settings.DEMO_ADMIN_EMAIL, settings.DEMO_ADMIN_PASSWORD)
    assert client.get("/admin/state", headers=demo_admin_headers).status_code == 200
    system_admin = db.query(User).filter(User.email == settings.DEMO_ADMIN_EMAIL).one()
    assert client.put(
        f"/admin/management/users/{system_admin.id}/password",
        headers=demo_admin_headers,
        json={"new_password": "ShouldNotChange@123", "confirm_password": "ShouldNotChange@123"},
    ).status_code == 403
    participant_headers = _login(client, participant.email, "Imported@123")
    display_headers = _login(
        client,
        settings.LEADERBOARD_DISPLAY_EMAIL,
        settings.LEADERBOARD_DISPLAY_PASSWORD,
        "/leaderboard/login",
    )

    assert client.get("/admin/management/admin-users").status_code == 401
    assert client.get("/admin/management/admin-users", headers=participant_headers).status_code == 403
    assert client.get("/admin/management/admin-users", headers=display_headers).status_code == 403

    mismatch = client.post(
        "/admin/management/admin-users",
        headers=demo_admin_headers,
        json={"login_id": "event.admin@example.com", "password": "TestAdmin@123", "confirm_password": "different"},
    )
    assert mismatch.status_code == 422

    created_admin = client.post(
        "/admin/management/admin-users",
        headers=demo_admin_headers,
        json={"login_id": "event.admin@example.com", "password": "TestAdmin@123", "confirm_password": "TestAdmin@123"},
    )
    assert created_admin.status_code == 201, created_admin.text
    assert created_admin.json()["role"] == "admin"
    assert created_admin.json()["is_system_account"] is False
    assert created_admin.json()["created_at"] is not None
    assert client.post(
        "/admin/management/admin-users",
        headers=demo_admin_headers,
        json={"login_id": "EVENT.ADMIN@example.com", "password": "TestAdmin@123", "confirm_password": "TestAdmin@123"},
    ).status_code == 409
    managed_admin_headers = _login(client, "event.admin@example.com", "TestAdmin@123")
    assert client.get("/admin/state", headers=managed_admin_headers).status_code == 200

    created_display = client.post(
        "/admin/management/leaderboard-users",
        headers=demo_admin_headers,
        json={"login_id": "hall-display@example.com", "password": "DisplayTest@123", "confirm_password": "DisplayTest@123"},
    )
    assert created_display.status_code == 201, created_display.text
    assert created_display.json()["role"] == "display"
    managed_display_headers = _login(client, "hall-display@example.com", "DisplayTest@123", "/leaderboard/login")
    assert client.get("/public/leaderboard", headers=managed_display_headers).status_code == 200
    assert client.post(
        "/admin/event-data/reset",
        headers=managed_display_headers,
        json={"confirmation": "RESET EVENT"},
    ).status_code == 403

    admin_password_reset = client.put(
        f"/admin/management/users/{created_admin.json()['id']}/password",
        headers=demo_admin_headers,
        json={"new_password": "NewAdmin@123", "confirm_password": "NewAdmin@123"},
    )
    assert admin_password_reset.status_code == 200
    assert client.post("/login", data={"username": "event.admin@example.com", "password": "TestAdmin@123"}).status_code == 401
    new_admin_headers = _login(client, "event.admin@example.com", "NewAdmin@123")
    assert client.get("/admin/state", headers=new_admin_headers).status_code == 200

    display_password_reset = client.put(
        f"/admin/management/users/{created_display.json()['id']}/password",
        headers=demo_admin_headers,
        json={"new_password": "NewDisplay@123", "confirm_password": "NewDisplay@123"},
    )
    assert display_password_reset.status_code == 200
    assert client.get("/public/leaderboard", headers=managed_display_headers).status_code == 401
    assert client.post(
        "/leaderboard/login",
        data={"username": "hall-display@example.com", "password": "DisplayTest@123"},
    ).status_code == 401
    _login(client, "hall-display@example.com", "NewDisplay@123", "/leaderboard/login")

    assert client.post(
        "/admin/management/reset",
        headers=demo_admin_headers,
        json={"confirmation": "wrong"},
    ).status_code == 422
    assert client.post(
        "/admin/management/reset",
        headers=display_headers,
        json={"confirmation": "RESET USERS"},
    ).status_code == 403

    before = {
        "teams": db.query(Team).count(),
        "problems": db.query(ProblemStatement).count(),
        "participants": db.query(User).filter(User.role.in_(("leader", "member"))).count(),
        "state": db.query(GameConfig).first().state,
    }
    reset = client.post(
        "/admin/management/reset",
        headers=demo_admin_headers,
        json={"confirmation": "RESET USERS"},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["deleted"] == {"admin_users": 1, "leaderboard_users": 1, "total": 2}
    db.expire_all()
    assert db.query(User).filter(User.email.in_(("event.admin@example.com", "hall-display@example.com"))).count() == 0
    assert before == {
        "teams": db.query(Team).count(),
        "problems": db.query(ProblemStatement).count(),
        "participants": db.query(User).filter(User.role.in_(("leader", "member"))).count(),
        "state": db.query(GameConfig).first().state,
    }
    demo_admin_headers = _login(client, settings.DEMO_ADMIN_EMAIL, settings.DEMO_ADMIN_PASSWORD)
    assert _login(client, settings.DEMO_LEADER_EMAIL, settings.DEMO_LEADER_PASSWORD)
    assert _login(
        client,
        settings.LEADERBOARD_DISPLAY_EMAIL,
        settings.LEADERBOARD_DISPLAY_PASSWORD,
        "/leaderboard/login",
    )

    admins = client.get("/admin/management/admin-users", headers=demo_admin_headers).json()["users"]
    displays = client.get("/admin/management/leaderboard-users", headers=demo_admin_headers).json()["users"]
    assert next(user for user in admins if user["login_id"] == settings.DEMO_ADMIN_EMAIL)["status"] == "SYSTEM"
    assert next(user for user in displays if user["login_id"] == settings.LEADERBOARD_DISPLAY_EMAIL)["status"] == "SYSTEM"
