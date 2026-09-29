import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import rounds
from app.api.auth import get_current_active_admin
from app.core.database import get_db
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, WalletTransaction, WildcardBid
from app.services.extra_assignment import automatic_assignment_price, automatically_assign_extra_problems, ExtraAssignmentError
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
        db.add(WalletTransaction(team_id=winner.id, transaction_type="ROUND1_WIN", amount=-amount,
                                 description=f"Round 1 win for problem {i + 1}"))
    extra = ProblemStatement(ps_number="EXT-1", title="Extra", round=0)
    team = Team(team_name="Unassigned", coins=5000)
    db.add_all([extra, team]); db.commit()
    return team, extra


@pytest.mark.parametrize("amounts, expected", [((), 77), ((100, 151), 126), ((100, 150, 200), 150),
    ((100, 150, 200, 250, 300, 350, 400), 300)])
def test_latest_five_actual_winners_and_rounding(db, amounts, expected):
    seed(db, amounts)
    assert automatic_assignment_price(db)["suggested_auto_deduction"] == expected
    assert automatic_assignment_price(db)["automatic_winning_bids"] == list(amounts[-5:])


def test_non_winning_sources_do_not_affect_price_or_r1_average(db):
    team, problem = seed(db, (100, 150, 200, 250, 300, 350, 400))
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    control.round1_winning_bid_sum = 1750; control.round1_winning_bid_count = 7
    manual = Team(team_name="Manual", ps_id=problem.id, round1_problem_id=problem.id,
                  round1_assignment_type="MANUAL_ASSIGNMENT", round1_assignment_cost=9000)
    db.add(manual); db.flush()
    db.add_all([Bid(team_id=team.id, ps_id=problem.id, round=1, amount=99999),
        WildcardBid(team_id=team.id, amount=88888),
        WalletTransaction(team_id=manual.id, transaction_type="ROUND1_MANUAL_ASSIGN", amount=-9000),
        WalletTransaction(team_id=team.id, transaction_type="WILDCARD_WIN", amount=-8000)])
    db.commit()
    assert automatic_assignment_price(db)["suggested_auto_deduction"] == 300
    result = automatically_assign_extra_problems(db)
    assert result["deduction"] == 300 and team.coins == 4700
    assert automatic_assignment_price(db)["suggested_auto_deduction"] == 300
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (1750, 7)
    assert team.round1_problem_id is team.round1_assignment_type is team.round1_assignment_cost is None
    board_team = next(row for row in lab_board(db)["teams"] if row["id"] == team.id)
    assert board_team["problem_assignment_status"] == "allocated"
    assert board_team["allocation_status"] == "lab_pending" and board_team["round1"] is None


@pytest.mark.parametrize("deduction", [0, 300])
def test_chosen_deduction_wallet_and_idempotency(db, deduction):
    team, _ = seed(db)
    first = automatically_assign_extra_problems(db, deduction)
    selected = team.ps_id
    assert first["assignments"][0]["coins"] == team.coins == 5000 - deduction
    ledger = db.query(WalletTransaction).filter_by(team_id=team.id, transaction_type="EXTRA_GRID_AUTO_ASSIGN").one()
    assert ledger.amount == -deduction and "Automatic Extra/Grid assignment for" in ledger.description
    assert automatically_assign_extra_problems(db, 999)["idempotent"] is True
    assert team.ps_id == selected and team.coins == 5000 - deduction
    assert db.query(WalletTransaction).filter_by(transaction_type="EXTRA_GRID_AUTO_ASSIGN").count() == 1


def test_insufficient_balance_skips_only_that_team(db):
    team, _ = seed(db)
    team.coins = 100
    funded = Team(team_name="Funded", coins=5000)
    db.add(funded); db.commit()
    result = automatically_assign_extra_problems(db, 300)
    assert result["failures"] == [{"team_id": team.id, "team_name": team.team_name,
        "reason": "Insufficient coins", "required": 300, "available": 100}]
    assert team.ps_id is None and team.coins == 100
    assert db.query(WalletTransaction).filter_by(team_id=team.id).count() == 0
    assert funded.ps_id is not None and funded.coins == 4700


def test_assignment_charge_and_ledger_roll_back_together(db, monkeypatch):
    team, _ = seed(db)
    def fail_commit(): raise RuntimeError("Simulated failed commit")
    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError): automatically_assign_extra_problems(db, 300)
    assert team.ps_id is None and team.coins == 5000
    assert db.query(WalletTransaction).count() == 0


@pytest.mark.parametrize("deduction", [-1, 1.5, True, "300"])
def test_service_rejects_invalid_deductions(db, deduction):
    team, _ = seed(db)
    with pytest.raises(ExtraAssignmentError): automatically_assign_extra_problems(db, deduction)
    assert team.ps_id is None and team.coins == 5000
    assert db.query(WalletTransaction).count() == 0


def test_endpoint_validates_and_publishes_committed_balances(db, monkeypatch):
    team, _ = seed(db)
    team_id = team.id
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
            assert client.post("/admin/extra-grid/auto-assign", json={"deduction": value}).status_code == 422
        response = client.post("/admin/extra-grid/auto-assign", json={"deduction": 300})
        assert response.status_code == 200 and response.json()["deduction"] == 300
        assert events[0][1]["assignments"][0]["coins"] == 4700
        assert client.post("/admin/extra-grid/auto-assign", json={"deduction": 300}).json()["idempotent"] is True
    assert len(events) == 1
    assert db.query(WalletTransaction).filter_by(team_id=team_id, transaction_type="EXTRA_GRID_AUTO_ASSIGN").count() == 1
