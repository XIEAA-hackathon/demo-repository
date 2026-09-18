"""Wildcard final problem choice: payment happens once at finalization, never after."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from app.core.security import get_password_hash
from app.models.models import (
    EventConfig,
    GameConfig,
    Lab,
    ProblemStatement,
    RoundControl,
    Team,
    User,
    WalletTransaction,
    Wildcard,
    WildcardBid,
)
from app.services.lab_allocation import LabAllocationError, allocate_labs


def _team(db, index: int, *, coins=1000, round1_problem=None):
    password = "temp-pass"
    leader = User(
        name=f"FC Leader {index}",
        email=f"fc-leader{index}@wild.test",
        password_hash=get_password_hash(password),
        role="leader",
    )
    db.add(leader)
    db.flush()
    team = Team(
        team_name=f"FC Team {index}",
        coins=coins,
        leader_id=leader.id,
        is_approved=True,
        ps_id=round1_problem.id if round1_problem else None,
        round1_problem_id=round1_problem.id if round1_problem else None,
    )
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.commit()
    return team, leader.email, password


def _login(client, email, password):
    response = client.post("/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _setup_final_choice(client, admin_headers, db, *, slots=1, applicants=2, bids=(250, 200)):
    """Finalize slot bidding with fixed winning bids, ready for problem selection."""
    config = db.query(EventConfig).first()
    config.wildcard_starting_bid = 100
    game = db.query(GameConfig).first()
    game.auction_timer_end = None
    db.add(RoundControl(round_type="ROUND1", status="CLOSED", ended=True))
    round1_problem = ProblemStatement(
        ps_number="R1-FC", title="Round 1 keeper", description="R1", round=1, status="completed",
    )
    db.add(round1_problem)
    db.commit()
    db.refresh(round1_problem)

    teams, headers = [], []
    for index in range(1, applicants + 1):
        team, email, password = _team(db, index, round1_problem=round1_problem)
        teams.append(team)
        headers.append(_login(client, email, password))

    assert client.post("/admin/rounds/wildcard/applications/open", headers=admin_headers).status_code == 200
    for team_headers in headers:
        assert client.post("/wildcard/apply", headers=team_headers).status_code == 200
    assert client.post("/admin/rounds/wildcard/applications/close", headers=admin_headers).status_code == 200
    problems = []
    for number in range(1, slots + 2):
        problem = ProblemStatement(
            ps_number=f"WC-FC-{number}", title=f"Wildcard {number}", description="W", round=2, status="available",
        )
        db.add(problem)
        problems.append(problem)
    db.commit()
    assert client.post("/admin/rounds/wildcard/slots", headers=admin_headers, json={"slots": slots}).status_code == 200
    assert client.post("/admin/rounds/wildcard/bidding/start", headers=admin_headers).status_code == 200
    for team, amount in zip(teams, bids):
        db.add(WildcardBid(team_id=team.id, amount=amount, timestamp=datetime.now(timezone.utc)))
    db.commit()
    assert client.post("/admin/rounds/wildcard/bidding/close", headers=admin_headers).status_code == 200
    finalized = client.post("/admin/wildcard/finalize", headers=admin_headers)
    assert finalized.status_code == 200, finalized.text
    return teams, headers, problems, round1_problem


def _winner_transactions(db, team_id):
    return (
        db.query(WalletTransaction)
        .filter(WalletTransaction.team_id == team_id, WalletTransaction.transaction_type == "WILDCARD_WIN")
        .all()
    )


def test_winner_charged_exactly_once_at_finalization(client, admin_headers, db):
    teams, _headers, _problems, _round1 = _setup_final_choice(client, admin_headers, db)
    db.expire_all()
    winner = db.query(Team).filter(Team.id == teams[0].id).one()
    application = db.query(Wildcard).filter(Wildcard.team_id == winner.id).one()
    assert application.status == "qualified"
    assert application.winning_bid == 250
    assert application.coins_paid == 250
    assert winner.coins == 750
    transactions = _winner_transactions(db, winner.id)
    assert len(transactions) == 1
    assert transactions[0].amount == -250


def test_refinalize_in_problem_selection_and_final_choice_does_not_recharge(client, admin_headers, db):
    teams, headers, problems, _round1 = _setup_final_choice(client, admin_headers, db)
    again = client.post("/admin/wildcard/finalize", headers=admin_headers)
    assert again.status_code == 200, again.text
    db.expire_all()
    assert db.query(Team).filter(Team.id == teams[0].id).one().coins == 750

    # Move into FINAL_CHOICE via the ranked selection, then finalize again.
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0]).status_code == 200
    db.expire_all()
    assert db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one().status == "FINAL_CHOICE"
    repeat = client.post("/admin/wildcard/finalize", headers=admin_headers)
    assert repeat.status_code == 200, repeat.text
    db.expire_all()
    assert db.query(Team).filter(Team.id == teams[0].id).one().coins == 750
    assert len(_winner_transactions(db, teams[0].id)) == 1


def test_selection_records_history_without_touching_coins(client, admin_headers, db):
    teams, headers, _problems, round1_problem = _setup_final_choice(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    selected = client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0])
    assert selected.status_code == 200, selected.text
    assert selected.json()["final_choice_opened"] is True
    db.expire_all()
    team = db.query(Team).filter(Team.id == teams[0].id).one()
    assert team.wildcard_problem_id == choices[0]["id"]
    assert team.round1_problem_id == round1_problem.id
    assert team.ps_id == round1_problem.id
    assert team.final_problem_choice is None
    assert team.coins == 750


def test_confirm_round1_does_not_refund(client, admin_headers, db):
    teams, headers, _problems, round1_problem = _setup_final_choice(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0]).status_code == 200
    response = client.post("/wildcard/final-choice", headers=headers[0], json={"choice": "ROUND1"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["choice"] == "ROUND1"
    assert body["winning_bid"] == 250
    assert body["coins_paid"] == 250
    db.expire_all()
    team = db.query(Team).filter(Team.id == teams[0].id).one()
    application = db.query(Wildcard).filter(Wildcard.team_id == team.id).one()
    assert team.ps_id == round1_problem.id
    assert team.final_problem_choice == "ROUND1"
    assert team.final_problem_confirmed_at is not None
    assert team.coins == 750
    assert application.coins_paid == 250
    assert len(_winner_transactions(db, team.id)) == 1


def test_confirm_wildcard_does_not_charge_again(client, admin_headers, db):
    teams, headers, _problems, _round1 = _setup_final_choice(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0]).status_code == 200
    response = client.post("/wildcard/final-choice", headers=headers[0], json={"choice": "WILDCARD"})
    assert response.status_code == 200, response.text
    db.expire_all()
    team = db.query(Team).filter(Team.id == teams[0].id).one()
    assert team.ps_id == choices[0]["id"]
    assert team.final_problem_choice == "WILDCARD"
    assert team.coins == 750
    assert len(_winner_transactions(db, team.id)) == 1


def test_duplicate_confirm_is_rejected_without_coin_change(client, admin_headers, db):
    teams, headers, _problems, _round1 = _setup_final_choice(client, admin_headers, db, slots=2, applicants=2, bids=(250, 200))
    for rank, team_headers in enumerate(headers):
        choices = client.get("/participant/problems?round=2", headers=team_headers).json()
        assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=team_headers).status_code == 200
    first = client.post("/wildcard/final-choice", headers=headers[0], json={"choice": "WILDCARD"})
    assert first.status_code == 200, first.text
    # Completion requires every winner; the second winner is still pending.
    db.expire_all()
    assert db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one().status == "FINAL_CHOICE"
    duplicate = client.post("/wildcard/final-choice", headers=headers[0], json={"choice": "ROUND1"})
    assert duplicate.status_code == 409, duplicate.text
    db.expire_all()
    team = db.query(Team).filter(Team.id == teams[0].id).one()
    assert team.final_problem_choice == "WILDCARD"
    assert team.coins == 750
    assert len(_winner_transactions(db, team.id)) == 1
    second = client.post("/wildcard/final-choice", headers=headers[1], json={"choice": "ROUND1"})
    assert second.status_code == 200, second.text
    db.expire_all()
    assert db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one().status == "COMPLETE"


def test_timeout_defaults_to_round1_without_refund(client, admin_headers, db):
    from app.services.wildcard_service import reconcile_final_choice

    teams, headers, _problems, round1_problem = _setup_final_choice(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0]).status_code == 200
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    control.final_choice_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    result = reconcile_final_choice(db)
    assert result is not None and result["reason"] == "timeout"
    db.expire_all()
    team = db.query(Team).filter(Team.id == teams[0].id).one()
    assert team.final_problem_choice == "ROUND1"
    assert team.final_problem_defaulted is True
    assert team.ps_id == round1_problem.id
    assert team.coins == 750
    assert len(_winner_transactions(db, team.id)) == 1
    assert db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one().status == "COMPLETE"


def test_admin_end_choice_defaults_without_refund(client, admin_headers, db):
    teams, headers, _problems, round1_problem = _setup_final_choice(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0]).status_code == 200
    ended = client.post("/admin/rounds/wildcard/final-choice/end", headers=admin_headers)
    assert ended.status_code == 200, ended.text
    db.expire_all()
    team = db.query(Team).filter(Team.id == teams[0].id).one()
    assert team.final_problem_choice == "ROUND1"
    assert team.ps_id == round1_problem.id
    assert team.coins == 750
    assert len(_winner_transactions(db, team.id)) == 1


def test_discarded_wildcard_problem_stays_reserved(client, admin_headers, db):
    from app.models.models import WildcardSelectionPool

    teams, headers, _problems, _round1 = _setup_final_choice(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0]).status_code == 200
    assert client.post("/wildcard/final-choice", headers=headers[0], json={"choice": "ROUND1"}).status_code == 200
    db.expire_all()
    team = db.query(Team).filter(Team.id == teams[0].id).one()
    assert team.wildcard_problem_id == choices[0]["id"]
    pool_row = db.query(WildcardSelectionPool).filter(WildcardSelectionPool.problem_id == choices[0]["id"]).one()
    assert pool_row.selected_by_team_id == team.id
    problem = db.query(ProblemStatement).filter(ProblemStatement.id == choices[0]["id"]).one()
    assert problem.status == "allocated"


def test_loser_pays_nothing(client, admin_headers, db):
    teams, _headers, _problems, _round1 = _setup_final_choice(client, admin_headers, db)
    db.expire_all()
    loser = db.query(Team).filter(Team.id == teams[1].id).one()
    application = db.query(Wildcard).filter(Wildcard.team_id == loser.id).one()
    assert application.status == "eliminated"
    assert loser.coins == 1000
    assert _winner_transactions(db, loser.id) == []
    rejected = client.post("/wildcard/final-choice", headers=_headers[1], json={"choice": "WILDCARD"})
    assert rejected.status_code == 409, rejected.text


def test_concurrent_duplicate_confirm_charges_nothing(client, admin_headers, db, session_factory):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import auth, participant, rounds, wildcard
    from app.core.database import get_db

    teams, headers, _problems, _round1 = _setup_final_choice(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0]).status_code == 200

    race_app = FastAPI()
    race_app.include_router(auth.router)
    race_app.include_router(wildcard.router)
    race_app.include_router(participant.router)
    race_app.include_router(rounds.router)

    def race_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    race_app.dependency_overrides[get_db] = race_db
    race_client = TestClient(race_app)
    barrier = Barrier(3)

    def confirm(choice):
        barrier.wait()
        return race_client.post("/wildcard/final-choice", headers=headers[0], json={"choice": choice})

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(confirm, "ROUND1"), executor.submit(confirm, "WILDCARD")]
        barrier.wait()
        statuses = sorted(future.result(timeout=15).status_code for future in futures)
    assert statuses == [200, 409]
    db.expire_all()
    team = db.query(Team).filter(Team.id == teams[0].id).one()
    assert team.coins == 750
    assert len(_winner_transactions(db, team.id)) == 1


def test_lab_allocation_waits_for_final_choice(client, admin_headers, db):
    db.add(Lab(name="Choice Lab", capacity=10, sort_order=0, active=True))
    db.commit()
    teams, headers, _problems, _round1 = _setup_final_choice(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0]).status_code == 200
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    assert control.status == "FINAL_CHOICE" and control.ended is False
    try:
        allocate_labs(db)
        allocated_early = True
    except LabAllocationError as exc:
        allocated_early = False
        assert exc.code == "not_ready"
    finally:
        db.rollback()
    assert allocated_early is False
    assert client.post("/wildcard/final-choice", headers=headers[0], json={"choice": "WILDCARD"}).status_code == 200
    db.expire_all()
    assert db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one().ended is True


def test_dashboard_and_event_state_expose_final_choice(client, admin_headers, db):
    teams, headers, _problems, _round1 = _setup_final_choice(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    assert client.post(f"/wildcard/select/{choices[0]['id']}", headers=headers[0]).status_code == 200
    db.expire_all()
    game = db.query(GameConfig).one()
    assert game.state == "WILDCARD_FINAL_CHOICE"
    dashboard = client.get("/participant/dashboard", headers=headers[0]).json()
    assert dashboard["eventState"] == "WILDCARD_FINAL_CHOICE"
    assert dashboard["wildcardWinningBid"] == 250
    assert dashboard["wildcardCoinsPaid"] == 250
    assert dashboard["finalProblemChoice"] is None
    assert dashboard["round1Problem"] is not None
    assert dashboard["wildcardProblem"] is not None
    assert client.post("/wildcard/final-choice", headers=headers[0], json={"choice": "WILDCARD"}).status_code == 200
    dashboard = client.get("/participant/dashboard", headers=headers[0]).json()
    assert dashboard["finalProblemChoice"] == "WILDCARD"
    assert dashboard["finalProblemConfirmedAt"] is not None
    assert dashboard["finalProblem"]["id"] == dashboard["wildcardProblem"]["id"]
    payload = client.get("/admin/rounds/wildcard", headers=admin_headers).json()
    assert payload["status"] == "COMPLETE"
    assert payload["final_choice"]["confirmed_count"] == 1
