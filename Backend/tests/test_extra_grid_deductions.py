import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import rounds
from app.api.auth import get_current_active_admin
from app.core.database import get_db
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, WalletTransaction, WildcardBid
from app.services.extra_assignment import automatic_assignment_price, automatically_assign_extra_problems, extra_assignment_payload, ExtraAssignmentError
from app.services.lab_allocation import lab_board


def seed(db, amounts=()):
    db.add_all([EventConfig(round1_minimum_bid=77), GameConfig(state="ROUND1_RESULT"),
                RoundControl(round_type="ROUND1", status="CLOSED", ended=True),
                RoundControl(round_type="WILDCARD", status="NOT_STARTED")])
    for i, amount in enumerate(amounts):
        problem = ProblemStatement(ps_number=f"R1-{i + 1}", title="Auction winner", round=1)
        db.add(problem); db.flush()
        winner = Team(team_name=f"Winner {i}", ps_id=problem.id, round1_problem_id=problem.id,
                      round1_assignment_type="BID_WINNER", round1_assignment_cost=amount, coins=5000 - amount)
        db.add(winner); db.flush()
        db.add(Bid(team_id=winner.id, ps_id=problem.id, round=1, amount=amount))
        db.add(WalletTransaction(team_id=winner.id, transaction_type="ROUND1_WIN", amount=-amount,
                                 description=f"Round 1 win for problem {i + 1}"))
    extra = ProblemStatement(ps_number="EXT-1", title="Extra", round=0)
    team = Team(team_name="Unassigned", coins=5000)
    db.add_all([extra, team]); db.commit()
    return team, extra


@pytest.mark.parametrize("amounts, expected", [((), 77), ((100, 151), 126), ((100, 150, 200), 150),
    ((100, 150, 200, 250, 300, 350, 400), 250), ((100, 120, 150, 180, 200, 250), 167)])
def test_all_persisted_r1_bids_and_rounding(db, amounts, expected):
    seed(db, amounts)
    assert automatic_assignment_price(db)["suggested_auto_deduction"] == expected
    assert automatic_assignment_price(db)["r1_bid_sum"] == sum(amounts)
    assert automatic_assignment_price(db)["r1_bid_count"] == len(amounts)
    assert automatic_assignment_price(db)["automatic_price_source"] == "Average of all Round 1 bids"


def test_losing_bids_count_but_wallet_charges_and_wildcard_do_not(db):
    team, problem = seed(db, (100, 150, 200, 250, 300, 350, 400))
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    control.round1_winning_bid_sum = 1750; control.round1_winning_bid_count = 7
    manual = Team(team_name="Manual", ps_id=problem.id, round1_problem_id=problem.id,
                  round1_assignment_type="MANUAL_ASSIGNMENT", round1_assignment_cost=9000)
    db.add(manual); db.flush()
    db.add_all([Bid(team_id=team.id, ps_id=problem.id, round=1, amount=450),
        Bid(team_id=team.id, ps_id=problem.id, round=2, amount=99999),
        WildcardBid(team_id=team.id, amount=88888),
        WalletTransaction(team_id=manual.id, transaction_type="ROUND1_MANUAL_ASSIGN", amount=-9000),
        WalletTransaction(team_id=manual.id, transaction_type="EXTRA_GRID_AUTO_ASSIGN", amount=-7000),
        WalletTransaction(team_id=manual.id, transaction_type="ROUND1_WIN", amount=-6000),
        WalletTransaction(team_id=team.id, transaction_type="WILDCARD_WIN", amount=-8000)])
    db.commit()
    assert automatic_assignment_price(db) == {"suggested_auto_deduction": 275, "r1_bid_sum": 2200,
        "r1_bid_count": 8, "automatic_price_source": "Average of all Round 1 bids"}
    result = automatically_assign_extra_problems(db, problem.id)
    assert result["deduction"] == 275 and team.coins == 4725
    assert automatic_assignment_price(db)["suggested_auto_deduction"] == 275
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (1750, 7)
    assert team.round1_problem_id is team.round1_assignment_type is team.round1_assignment_cost is None
    board_team = next(row for row in lab_board(db)["teams"] if row["id"] == team.id)
    assert board_team["problem_assignment_status"] == "allocated"
    assert board_team["allocation_status"] == "lab_pending" and board_team["round1"] is None


@pytest.mark.parametrize("deduction", [0, 300])
def test_chosen_deduction_wallet_and_idempotency(db, deduction):
    team, problem = seed(db)
    first = automatically_assign_extra_problems(db, problem.id, deduction)
    selected = team.ps_id
    assert first["assignments"][0]["coins"] == team.coins == 5000 - deduction
    ledger = db.query(WalletTransaction).filter_by(team_id=team.id, transaction_type="EXTRA_GRID_AUTO_ASSIGN").one()
    assert ledger.amount == -deduction and "Automatic Extra/Grid assignment for" in ledger.description
    assert automatically_assign_extra_problems(db, problem.id, 999)["idempotent"] is True
    assert team.ps_id == selected and team.coins == 5000 - deduction
    assert db.query(WalletTransaction).filter_by(transaction_type="EXTRA_GRID_AUTO_ASSIGN").count() == 1


def test_insufficient_balance_skips_only_that_team(db):
    team, problem = seed(db)
    team.coins = 100
    funded = Team(team_name="Funded", coins=5000)
    db.add(funded); db.commit()
    result = automatically_assign_extra_problems(db, problem.id, 300)
    assert result["failures"] == [{"team_id": team.id, "team_name": team.team_name,
        "reason": "Insufficient coins", "required": 300, "available": 100}]
    assert team.ps_id is None and team.coins == 100
    assert db.query(WalletTransaction).filter_by(team_id=team.id).count() == 0
    assert funded.ps_id is not None and funded.coins == 4700


def test_assignment_charge_and_ledger_roll_back_together(db, monkeypatch):
    team, problem = seed(db)
    def fail_commit(): raise RuntimeError("Simulated failed commit")
    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError): automatically_assign_extra_problems(db, problem.id, 300)
    assert team.ps_id is None and team.coins == 5000
    assert db.query(WalletTransaction).count() == 0


@pytest.mark.parametrize("deduction", [-1, 1.5, True, "300"])
def test_service_rejects_invalid_deductions(db, deduction):
    team, problem = seed(db)
    with pytest.raises(ExtraAssignmentError): automatically_assign_extra_problems(db, problem.id, deduction)
    assert team.ps_id is None and team.coins == 5000
    assert db.query(WalletTransaction).count() == 0


def test_endpoint_validates_and_publishes_committed_balances(db, monkeypatch):
    team, problem = seed(db)
    team_id = team.id
    problem_id = problem.id
    events = []
    def publish(name, payload, **kwargs):
        assert db.get_bind().pool.checkedout() == 0
        events.append((name, payload)); return True
    monkeypatch.setattr(rounds.manager, "publish_event", publish)
    app = FastAPI(); app.include_router(rounds.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_admin] = lambda: None
    with TestClient(app) as client:
        for value in [-1, 1.5, True, "300", None]:
            assert client.post("/admin/extra-grid/auto-assign", json={"problem_id": problem_id, "deduction": value}).status_code == 422
        for value in [-1, 0, 1.5, True, "1", None]:
            assert client.post("/admin/extra-grid/auto-assign", json={"problem_id": value, "deduction": 300}).status_code == 422
        assert client.post("/admin/extra-grid/auto-assign").status_code == 422
        assert client.post("/admin/extra-grid/auto-assign", json={"deduction": 300}).status_code == 422
        assert client.post("/admin/extra-grid/auto-assign", json={"problem_id": 99999, "deduction": 300}).status_code == 409
        response = client.post("/admin/extra-grid/auto-assign", json={"problem_id": problem_id, "deduction": 300})
        assert response.status_code == 200 and response.json()["deduction"] == 300
        assert events[0][1]["assignments"][0]["coins"] == 4700
        assert client.post("/admin/extra-grid/auto-assign", json={"problem_id": problem_id, "deduction": 300}).json()["idempotent"] is True
    assert len(events) == 1
    assert db.query(WalletTransaction).filter_by(team_id=team_id, transaction_type="EXTRA_GRID_AUTO_ASSIGN").count() == 1


def test_selected_problem_only_capacity_no_spill_and_deterministic_order(db):
    first, target = seed(db)
    other = ProblemStatement(ps_number="R1-OTHER", title="Other free capacity", round=1)
    db.add(other); db.flush()
    # Three current occupants leave exactly two slots; four eligible teams exist.
    db.add_all([Team(team_name=f"Occupant {i}", ps_id=target.id) for i in range(3)])
    remaining = [Team(team_name=f"Unassigned {i}") for i in range(3)]
    db.add_all(remaining); db.commit()
    result = automatically_assign_extra_problems(db, target.id, 167)
    assert [row["team_id"] for row in result["assignments"]] == [first.id, remaining[0].id]
    assert {row["problem_id"] for row in result["assignments"]} == {target.id}
    assert db.query(Team).filter_by(ps_id=target.id).count() == 5
    assert db.query(Team).filter_by(ps_id=other.id).count() == 0
    assert all(team.ps_id is None and team.coins == 5000 for team in remaining[1:])
    with pytest.raises(ExtraAssignmentError, match="no remaining capacity"):
        automatically_assign_extra_problems(db, target.id, 167)
    assert first.coins == remaining[0].coins == 4833
    assert db.query(WalletTransaction).count() == 2


@pytest.mark.parametrize("invalid_target", ["missing", "wildcard", "full", "r1_open"])
def test_invalid_target_or_active_r1_rejected_without_charge(db, invalid_target):
    team, target = seed(db)
    target_id = target.id
    if invalid_target == "missing": target_id = 99999
    elif invalid_target == "wildcard": target.round = 2
    elif invalid_target == "full": db.add_all([Team(team_name=f"Assigned {i}", ps_id=target.id) for i in range(5)])
    else: db.query(RoundControl).filter_by(round_type="ROUND1").one().ended = False
    db.commit()
    with pytest.raises(ExtraAssignmentError): automatically_assign_extra_problems(db, target_id, 300)
    assert team.ps_id is None and team.coins == 5000
    assert db.query(WalletTransaction).count() == 0


def test_only_eligible_teams_and_current_assignments_count_for_extra_capacity(db):
    eligible, target = seed(db)
    wildcard = ProblemStatement(ps_number="WC-1", title="Final", round=2)
    db.add(wildcard); db.flush()
    excluded = [Team(team_name="Unapproved", is_approved=False), Team(team_name="System", is_system_team=True),
        Team(team_name="R1 pending", round1_problem_id=target.id),
        Team(team_name="Wildcard pending", wildcard_problem_id=wildcard.id),
        Team(team_name="Final assigned", ps_id=wildcard.id)]
    # Earlier R1 history does not occupy a current Extra/Grid slot after WC.
    previous_winners = [Team(team_name=f"WC winner {i}", ps_id=wildcard.id, round1_problem_id=target.id,
        wildcard_problem_id=wildcard.id) for i in range(5)]
    db.add_all(excluded + previous_winners); db.commit()
    assert next(row for row in extra_assignment_payload(db)["problems"] if row["id"] == target.id)["capacity_remaining"] == 5
    before = [(t.ps_id, t.round1_problem_id, t.wildcard_problem_id, t.coins) for t in excluded + previous_winners]
    result = automatically_assign_extra_problems(db, target.id, 300)
    assert [row["team_id"] for row in result["assignments"]] == [eligible.id]
    assert result["failures"] == []
    assert [(t.ps_id, t.round1_problem_id, t.wildcard_problem_id, t.coins) for t in excluded + previous_winners] == before
    assert db.query(WalletTransaction).count() == 1
