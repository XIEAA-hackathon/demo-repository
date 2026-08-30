import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.security import get_password_hash
from app.models.models import EventActivityLog, GameConfig, ProblemStatement, RoundControl, Team, User
from app.main import process_expiry_cycle
from app.services.event_service import _remaining_seconds


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


def test_duplicate_leader_login_is_rejected_without_revoking_original_session(client, db):
    user, _team = _leader(db, email="single-session@team.test")
    first_headers = _login(client, user.email, "temp-pass")
    db.expire_all()
    original_session_id = db.get(User, user.id).session_id

    duplicate = client.post(
        "/login",
        data={"username": user.email, "password": "temp-pass"},
    )

    assert duplicate.status_code == 409
    assert "already logged in on another device" in duplicate.json()["detail"]
    assert client.get("/participant/dashboard", headers=first_headers).status_code == 200
    db.expire_all()
    assert db.get(User, user.id).session_id == original_session_id


def test_backend_timer_keeps_fractional_final_second_open():
    now = datetime.utcnow()
    game = GameConfig(auction_timer_end=now + timedelta(milliseconds=100))
    assert _remaining_seconds(game, now=now) == 1
    game.auction_timer_end = now
    assert _remaining_seconds(game, now=now) == 0


def test_natural_expiry_broadcasts_committed_snapshot_once(db):
    problem = ProblemStatement(
        ps_number="R1-TIMER",
        title="Timer source of truth",
        description="Timer regression",
        round=1,
        status="current",
    )
    db.add(problem)
    db.flush()
    db.add(RoundControl(round_type="ROUND1", status="BIDDING", current_problem_id=problem.id))
    game = GameConfig(
        state="ROUND1_BIDDING",
        current_round=1,
        auction_timer_end=datetime.utcnow() - timedelta(milliseconds=1),
    )
    db.add(game)
    db.commit()

    class CapturingManager:
        def __init__(self):
            self.events = []

        async def broadcast_event(self, event_type, payload):
            self.events.append((event_type, payload))

    manager = CapturingManager()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    first_actions = asyncio.run(process_expiry_cycle(factory, manager))
    second_actions = asyncio.run(process_expiry_cycle(factory, manager))

    assert first_actions == ["round1.bidding_expired"]
    assert second_actions == []
    assert len(manager.events) == 1
    event_type, payload = manager.events[0]
    assert event_type == "event_state_changed"
    assert payload["event_state"] == "ROUND1_RESULT"
    assert payload["rounds"]["ROUND1"]["status"] == "READY"
    assert payload["timing"]["ends_at"] is None
    assert payload["expiry_actions"] == ["round1.bidding_expired"]
    db.expire_all()
    assert db.query(EventActivityLog).filter(
        EventActivityLog.action == "round1.bidding_expired"
    ).count() == 1


def test_repeated_manual_round_end_is_idempotent(client, admin_headers, db):
    control = RoundControl(round_type="ROUND1", status="BIDDING", ended=False)
    db.add(control)
    db.commit()

    first = client.post("/admin/rounds/round-1/end", headers=admin_headers)
    second = client.post("/admin/rounds/round-1/end", headers=admin_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one()
    assert control.ended is True and control.status == "CLOSED"
    assert db.query(EventActivityLog).filter(
        EventActivityLog.action == "round1.manually_ended"
    ).count() == 1


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
    response = client.post("/bid", headers=headers, json={"ps_id": problem.id, "increment": 5})
    assert response.status_code == 409
    db.expire_all()
    assert db.query(GameConfig).first().state == "ROUND1_RESULT"
    assert db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one().status == "READY"
    assert team.coins == 1000


def test_bid_in_fractional_final_second_is_accepted(client, db):
    user, _team = _leader(db, email="last-second@team.test")
    problem = ProblemStatement(ps_number="R1-LAST", title="Last second", description="Race", round=1, status="current")
    db.add(problem)
    db.flush()
    db.add(RoundControl(round_type="ROUND1", status="BIDDING", current_problem_id=problem.id))
    game = db.query(GameConfig).first() or GameConfig()
    db.add(game)
    game.state = "ROUND1_BIDDING"
    game.current_round = 1
    db.commit()
    headers = _login(client, user.email, "temp-pass")
    game.auction_timer_end = datetime.utcnow() + timedelta(milliseconds=900)
    db.commit()

    response = client.post("/bid", headers=headers, json={"ps_id": problem.id, "increment": 5})

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("remaining_ms", [2000, 900])
def test_manual_close_before_expiry_wins_without_auto_close_race(
    client, admin_headers, db, remaining_ms,
):
    problem = ProblemStatement(ps_number=f"R1-CLOSE-{remaining_ms}", title="Close race", round=1, status="current")
    db.add(problem)
    db.flush()
    db.add(RoundControl(round_type="ROUND1", status="BIDDING", current_problem_id=problem.id))
    game = db.query(GameConfig).one()
    game.state = "ROUND1_BIDDING"
    game.current_round = 1
    game.auction_timer_end = datetime.utcnow() + timedelta(milliseconds=remaining_ms)
    db.commit()

    response = client.post("/admin/rounds/round-1/bidding/close", headers=admin_headers)

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.query(EventActivityLog).filter(EventActivityLog.action == "round1.bidding_closed").count() == 1
    assert db.query(EventActivityLog).filter(EventActivityLog.action == "round1.bidding_expired").count() == 0


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
