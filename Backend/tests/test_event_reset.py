import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from app.api import operations
from app.core.security import get_password_hash
from app.core.config import settings
from app.models.models import (
    Bid,
    EventActivityLog,
    EventConfig,
    ExchangeRequest,
    FinalResult,
    GameConfig,
    Member,
    ProblemStatement,
    RoundControl,
    Submission,
    Team,
    User,
    Wildcard,
    WildcardBid,
    WildcardSelectionPool,
    WalletTransaction,
)
from app.services.demo_seed import provision_demo_accounts


def _team(db, name, email, *, system=False):
    leader = User(
        name=f"{name} Leader",
        email=email,
        role="leader",
        password_hash=get_password_hash("temp-pass"),
        is_system_account=system,
    )
    db.add(leader)
    db.flush()
    team = Team(
        team_name=name,
        leader_id=leader.id,
        coins=1000,
        is_approved=True,
        is_system_team=system,
    )
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.add(Member(team_id=team.id, member_name="Member", email=f"member-{team.id}@reset.test"))
    db.commit()
    return leader, team


def _login(client, email, password="temp-pass"):
    response = client.post("/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _display_login(client):
    response = client.post(
        "/leaderboard/login",
        data={"username": settings.LEADERBOARD_DISPLAY_EMAIL, "password": settings.LEADERBOARD_DISPLAY_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize(
    "active_state",
    [
        "WAITING",
        "ROUND1_PREVIEW",
        "ROUND1_BIDDING",
        "ROUND1_RESULT",
        "WILDCARD_APPLICATION",
        "WILDCARD_BIDDING",
        "WILDCARD_SELECTION",
        "SUBMISSION",
        "JUDGING_WAIT",
        "RESULTS",
    ],
)
def test_event_reset_is_allowed_from_every_active_stage(client, admin_headers, db, active_state):
    leader, team = _team(db, f"{active_state} Team", f"{active_state.lower()}@reset.test")
    participant_headers = _login(client, leader.email)
    problem = ProblemStatement(ps_number=f"{active_state}-PS", title="Active", description="Active", round=1, status="current")
    db.add(problem)
    db.flush()
    team.ps_id = problem.id
    team.round1_problem_id = problem.id
    db.add(Bid(team_id=team.id, ps_id=problem.id, amount=100, round=1))
    db.add(Submission(team_id=team.id, problem_id=problem.id, repository_url="https://github.com/example/active-reset"))
    db.add(FinalResult(
        first_place_team_id=team.id,
        result_status="PUBLISHED" if active_state == "RESULTS" else "WAITING",
        saved_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc) if active_state == "RESULTS" else None,
    ))

    game = db.query(GameConfig).first()
    game.state = active_state
    game.current_round = 2 if active_state == "WILDCARD_BIDDING" else 1
    game.phase_started_at = datetime.now(timezone.utc)
    game.auction_timer_end = datetime.now(timezone.utc) + timedelta(minutes=5)
    game.timer_paused = True
    game.timer_paused_remaining_seconds = 120
    event = db.query(EventConfig).first()
    event.submissions_open = active_state == "SUBMISSION"
    round1 = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").first()
    if round1 is None:
        round1 = RoundControl(round_type="ROUND1")
        db.add(round1)
    round1.status = "BIDDING" if active_state == "ROUND1_BIDDING" else "PREVIEW"
    round1.current_problem_id = problem.id
    wildcard = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").first()
    if wildcard is None:
        wildcard = RoundControl(round_type="WILDCARD")
        db.add(wildcard)
    wildcard.status = active_state
    wildcard.applications_open = active_state == "WILDCARD_APPLICATION"
    wildcard.current_selection_rank = 1
    wildcard.selection_started_at = datetime.now(timezone.utc)
    wildcard.selection_ends_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    wildcard.selection_duration_seconds = 30
    db.commit()

    recovery = client.get("/admin/recovery", headers=admin_headers)
    assert recovery.status_code == 200
    assert recovery.json()["event_data_reset_allowed"] is True
    assert recovery.json()["event_data_reset_block_reason"] is None

    reset = client.post("/admin/event-data/reset", headers=admin_headers, json={"confirmation": "RESET EVENT"})
    assert reset.status_code == 200, reset.text
    assert reset.json()["event_state"] == "WAITING"

    db.expire_all()
    game = db.query(GameConfig).first()
    assert game.state == "WAITING"
    assert game.phase_started_at is None
    assert game.auction_timer_end is None
    assert game.timer_paused is False
    assert game.timer_paused_remaining_seconds is None
    assert db.query(EventConfig).first().submissions_open is False
    assert db.query(Bid).count() == 0
    assert db.query(Submission).count() == 0
    assert db.query(FinalResult).count() == 0
    preserved_team = db.query(Team).filter(Team.id == team.id).one()
    preserved_leader = db.query(User).filter(User.id == leader.id).one()
    assert preserved_team.ps_id is None and preserved_team.round1_problem_id is None
    assert preserved_team.coins == db.query(EventConfig).first().starting_coins
    assert preserved_leader.team_id == preserved_team.id
    controls = {control.round_type: control for control in db.query(RoundControl).all()}
    assert controls["ROUND1"].status == "IDLE"
    assert controls["ROUND1"].current_problem_id is None
    assert controls["WILDCARD"].status == "NOT_STARTED"
    assert controls["WILDCARD"].current_problem_id is None
    assert controls["WILDCARD"].current_selection_rank is None
    assert controls["WILDCARD"].selection_started_at is None
    assert controls["WILDCARD"].selection_ends_at is None
    assert controls["WILDCARD"].selection_duration_seconds is None
    assert client.get("/participant/dashboard", headers=participant_headers).status_code == 200


def test_event_reset_rolls_back_if_any_step_fails(client, admin_headers, db, monkeypatch):
    _leader, team = _team(db, "Rollback Team", "rollback@reset.test")
    problem = ProblemStatement(ps_number="ROLLBACK-PS", title="Rollback", round=1, status="current")
    db.add(problem)
    db.flush()
    db.add(Bid(team_id=team.id, ps_id=problem.id, amount=100, round=1))
    game = db.query(GameConfig).first()
    game.state = "ROUND1_BIDDING"
    db.commit()

    def fail_mid_reset(transaction, **_kwargs):
        transaction.query(Bid).delete(synchronize_session=False)
        transaction.query(GameConfig).first().state = "WAITING"
        raise RuntimeError("forced reset failure")

    monkeypatch.setattr(operations, "reset_event_and_imported_participants", fail_mid_reset)
    with pytest.raises(RuntimeError, match="forced reset failure"):
        client.post("/admin/event-data/reset", headers=admin_headers, json={"confirmation": "RESET EVENT"})

    db.expire_all()
    assert db.query(GameConfig).first().state == "ROUND1_BIDDING"
    assert db.query(Bid).count() == 1
    assert db.query(Team).filter(Team.id == team.id).count() == 1


def test_event_data_reset_preserves_system_access_and_supports_fresh_import(client, admin_headers, db):
    del admin_headers  # Initializes the singleton event configuration used by this test.
    provisioned = provision_demo_accounts(db)
    db.commit()
    system_leader = db.query(User).filter(User.email == settings.DEMO_LEADER_EMAIL).one()
    system_team = db.query(Team).filter(Team.team_name == settings.DEMO_TEAM_NAME).one()
    demo_admin_headers = _login(client, settings.DEMO_ADMIN_EMAIL, settings.DEMO_ADMIN_PASSWORD)
    assert _login(client, settings.DEMO_LEADER_EMAIL, settings.DEMO_LEADER_PASSWORD)
    assert provisioned == {
        "team": "Demo Team",
        "leader": "leader@demo.example.com",
        "admin": "admin.demo@bidtobuild.example.com",
        "display": "leaderboard@bidtobuild.example.com",
    }
    display_headers = _display_login(client)
    assert client.get("/leaderboard/round-1").status_code == 401
    assert client.get("/leaderboard/wildcard").status_code == 401
    assert client.get("/leaderboard/round-1", headers=display_headers).status_code == 200
    assert client.get("/leaderboard/wildcard", headers=display_headers).status_code == 200
    imported_alpha, alpha_team = _team(db, "Imported Team Alpha", "alpha@reset.test")
    imported_alpha_email = imported_alpha.email
    _imported_beta, beta_team = _team(db, "Imported Team Beta", "beta@reset.test")
    alpha_headers = _login(client, imported_alpha.email)
    assert client.post("/admin/event-data/reset", headers=alpha_headers, json={"confirmation": "RESET EVENT"}).status_code == 403
    assert client.post("/admin/event-data/reset", json={"confirmation": "RESET EVENT"}).status_code == 401

    round1 = ProblemStatement(ps_number="R1-1", title="Round", description="Round", round=1, status="current")
    wildcard_problem = ProblemStatement(ps_number="WC-1", title="Wildcard", description="Wildcard", round=2, status="allocated")
    db.add_all([round1, wildcard_problem])
    db.flush()
    alpha_team.ps_id = round1.id
    alpha_team.round1_problem_id = round1.id
    beta_team.ps_id = wildcard_problem.id
    beta_team.wildcard_problem_id = wildcard_problem.id
    db.add_all([
        Bid(team_id=alpha_team.id, ps_id=round1.id, amount=200, round=1),
        Wildcard(team_id=beta_team.id, status="selected", rank=1, winning_bid=300, problem_id=wildcard_problem.id),
        WildcardBid(team_id=beta_team.id, amount=300),
        WildcardSelectionPool(position=1, problem_id=wildcard_problem.id, selected_by_team_id=beta_team.id),
        ExchangeRequest(
            requester_team_id=alpha_team.id,
            receiver_team_id=beta_team.id,
            requester_ps_id=round1.id,
            receiver_ps_id=wildcard_problem.id,
        ),
        WalletTransaction(team_id=alpha_team.id, transaction_type="TEST", amount=-10, description="Reset test"),
        Submission(team_id=alpha_team.id, problem_id=round1.id, submitted_by_user_id=imported_alpha.id, repository_url="https://github.com/example/reset"),
    ])
    round1_control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one()
    round1_control.status = "READY"
    round1_control.current_problem_id = round1.id
    wildcard_control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    wildcard_control.status = "COMPLETE"
    wildcard_control.ended = True
    wildcard_control.slot_count = 1
    wildcard_control.current_selection_rank = 1
    wildcard_control.selection_started_at = datetime.now(timezone.utc)
    wildcard_control.selection_ends_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    wildcard_control.selection_duration_seconds = 30
    game = db.query(GameConfig).first()
    game.state = "ROUND1_BIDDING"
    db.commit()

    reset = client.post("/admin/event-data/reset", headers=demo_admin_headers, json={"confirmation": "RESET EVENT"})
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["status"] == "reset_complete"
    assert body["deleted"]["teams"] == 0
    assert body["deleted"]["participant_users"] == 0
    assert body["deleted"]["round1_problems"] == 1
    assert body["deleted"]["wildcard_problems"] == 1
    assert body["event_state"] == "WAITING"

    db.expire_all()
    assert db.query(Team).filter(Team.is_system_team.is_(False)).count() == 2
    assert db.query(User).filter(User.role.in_(("leader", "member")), User.is_system_account.is_(False)).count() == 2
    assert db.query(ProblemStatement).count() == 0
    assert db.query(Bid).count() == 0
    assert db.query(Wildcard).count() == 0
    assert db.query(WildcardBid).count() == 0
    assert db.query(WildcardSelectionPool).count() == 0
    assert db.query(ExchangeRequest).count() == 0
    assert db.query(WalletTransaction).count() == 3
    assert all(row.transaction_type == "INITIAL_ALLOCATION" for row in db.query(WalletTransaction).all())
    assert db.query(Submission).count() == 0
    assert db.query(EventActivityLog).count() == 1
    controls = {row.round_type: row for row in db.query(RoundControl).all()}
    assert controls["ROUND1"].status == "IDLE" and controls["ROUND1"].current_problem_id is None
    assert controls["WILDCARD"].status == "NOT_STARTED" and controls["WILDCARD"].slot_count is None
    assert controls["WILDCARD"].current_selection_rank is None
    assert controls["WILDCARD"].selection_started_at is None
    assert controls["WILDCARD"].selection_ends_at is None
    assert db.query(GameConfig).first().auction_timer_end is None

    # Existing Admin bearer token and permanent demo leader credentials remain valid.
    assert client.get("/admin/state", headers=demo_admin_headers).status_code == 200
    assert _login(client, system_leader.email, settings.DEMO_LEADER_PASSWORD)
    assert _login(client, settings.DEMO_ADMIN_EMAIL, settings.DEMO_ADMIN_PASSWORD)
    assert client.post("/login", data={"username": imported_alpha_email, "password": "temp-pass"}).status_code == 200
    assert db.query(Team).filter(Team.id == system_team.id, Team.is_system_team.is_(True)).count() == 1
    assert db.query(User).filter(User.id == system_leader.id, User.is_system_account.is_(True)).count() == 1
    assert client.get("/leaderboard/round-1", headers=display_headers).status_code == 200
    assert client.get("/leaderboard/wildcard", headers=display_headers).status_code == 200
    assert _display_login(client)

    registration = (
        "Team Name,Leader Name,Leader Email,Member 1 Name,Member 1 Email,Member 2 Name,Member 2 Email\n"
        "Real Event Team,Real Leader,real.leader@event.test,Member One,one@event.test,Member Two,two@event.test\n"
    ).encode()
    imported = client.post(
        "/admin/registration/import",
        headers=_login(client, settings.DEMO_ADMIN_EMAIL, settings.DEMO_ADMIN_PASSWORD),
        files={"file": ("real-event.csv", registration, "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["teams_created"] == 1
    account = db.query(User).filter(User.email == "real.leader@event.test").one()
    assert account.credentials_active is False
    assert client.post(
        "/login",
        data={"username": account.email, "password": "NoGeneratedPassword@123"},
    ).status_code == 401
    assigned = client.put(
        f"/admin/registration/participant-accounts/{account.id}/password",
        headers=_login(client, settings.DEMO_ADMIN_EMAIL, settings.DEMO_ADMIN_PASSWORD),
        json={"new_password": "ManualPassword@123", "confirm_password": "ManualPassword@123"},
    )
    assert assigned.status_code == 200
    assert client.post(
        "/login",
        data={"username": account.email, "password": "ManualPassword@123"},
    ).status_code == 200
