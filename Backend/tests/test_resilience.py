from datetime import datetime, timedelta

from app.core.security import get_password_hash
from app.models.models import EventActivityLog, GameConfig, ProblemStatement, RoundControl, Team, User


def _leader(db, email="resilient@team.test"):
    user = User(name="Resilient Leader", email=email, role="leader", password_hash=get_password_hash("temp-pass"))
    db.add(user)
    db.flush()
    team = Team(team_name=f"Team {user.id}", leader_id=user.id, coins=1000, is_approved=True)
    db.add(team)
    db.flush()
    user.team_id = team.id
    db.commit()
    return user, team


def _login(client, email, password):
    response = client.post("/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_logout_revokes_old_token_and_relogin_works(client, admin_headers):
    assert client.get("/admin/state", headers=admin_headers).status_code == 200
    assert client.post("/logout", headers=admin_headers).status_code == 200
    assert client.get("/admin/state", headers=admin_headers).status_code == 401

    new_login = client.post("/login", data={"username": "admin@test.com", "password": "admin123"})
    assert new_login.status_code == 200
    new_headers = {"Authorization": f"Bearer {new_login.json()['access_token']}"}
    assert client.get("/admin/state", headers=new_headers).status_code == 200


def test_leader_logout_revokes_old_token_and_relogin_works(client, db):
    user, _team = _leader(db)
    headers = _login(client, user.email, "temp-pass")
    assert client.get("/participant/dashboard", headers=headers).status_code == 200
    assert client.post("/logout", headers=headers).status_code == 200
    assert client.get("/participant/dashboard", headers=headers).status_code == 401
    new_headers = _login(client, user.email, "temp-pass")
    assert client.get("/participant/dashboard", headers=new_headers).status_code == 200


def test_expired_round_one_bidding_rejects_late_bid_and_marks_ready(client, db):
    user, team = _leader(db)
    problem = ProblemStatement(ps_number="R1-1", title="Expired", description="Expired", round=1, status="current")
    db.add(problem)
    db.flush()
    db.add(RoundControl(round_type="ROUND1", status="BIDDING", current_problem_id=problem.id))
    game = db.query(GameConfig).first()
    if not game:
        game = GameConfig()
        db.add(game)
    game.state = "ROUND1_BIDDING"
    game.current_round = 1
    game.auction_timer_end = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    headers = _login(client, user.email, "temp-pass")
    response = client.post("/bid", headers=headers, json={"ps_id": problem.id, "amount": 100})
    assert response.status_code == 409
    db.expire_all()
    assert db.query(GameConfig).first().state == "ROUND1_RESULT"
    assert db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one().status == "READY"
    assert team.coins == 1000


def test_recovery_preflight_log_and_disabled_reset(client, admin_headers, db):
    preflight = client.get("/admin/preflight", headers=admin_headers)
    assert preflight.status_code == 200
    assert preflight.json()["status"] == "BLOCKED"
    recovery = client.get("/admin/recovery", headers=admin_headers)
    assert recovery.status_code == 200
    assert recovery.json()["current_phase"] == "WAITING"
    assert recovery.json()["reset_enabled"] is False
    assert client.post(
        "/admin/development/reset",
        headers=admin_headers,
        json={"confirmation": "RESET DEVELOPMENT EVENT"},
    ).status_code == 403

    log = client.get("/admin/activity-log", headers=admin_headers)
    assert log.status_code == 200
    serialized = log.text.lower()
    assert "password" not in serialized
    assert "bearer" not in serialized
    assert db.query(EventActivityLog).count() >= 1
