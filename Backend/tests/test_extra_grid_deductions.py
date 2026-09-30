import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import rounds
from app.api.auth import get_current_active_admin
from app.core.database import get_db
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, WalletTransaction, WildcardBid
from app.services.extra_assignment import automatic_assignment_price, automatically_assign_extra_problems, extra_assignment_payload, ExtraAssignmentError
from app.services.lab_allocation import lab_board
from app.services.round1_assignment import remaining_problems_payload


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
    next_funded = Team(team_name="Next funded", coins=5000)
    db.add_all([funded, next_funded] + [Team(team_name=f"Occupant {i}", ps_id=problem.id) for i in range(3)]); db.commit()
    result = automatically_assign_extra_problems(db, problem.id, 300)
    assert result["failures"] == [{"team_id": team.id, "team_name": team.team_name,
        "reason": "Insufficient coins", "required": 300, "available": 100}]
    assert team.ps_id is None and team.coins == 100
    assert db.query(WalletTransaction).filter_by(team_id=team.id).count() == 0
    assert funded.ps_id == next_funded.ps_id == problem.id
    assert funded.coins == next_funded.coins == 4700
    assert db.query(Team).filter_by(ps_id=problem.id).count() == 5
    assert db.query(WalletTransaction).count() == 2


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


@pytest.mark.parametrize("invalid_target", ["missing", "wildcard", "full"])
def test_invalid_target_rejected_without_charge(db, invalid_target):
    team, target = seed(db)
    target_id = target.id
    if invalid_target == "missing": target_id = 99999
    elif invalid_target == "wildcard": target.round = 2
    elif invalid_target == "full": db.add_all([Team(team_name=f"Assigned {i}", ps_id=target.id) for i in range(5)])
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
    payload = extra_assignment_payload(db)
    assert payload["remaining_team_count"] == 1
    assert [row["team_id"] for row in payload["unassigned_teams"]] == [eligible.id]
    assert next(row for row in payload["problems"] if row["id"] == target.id)["capacity_remaining"] == 5
    before = [(t.ps_id, t.round1_problem_id, t.wildcard_problem_id, t.coins) for t in excluded + previous_winners]
    result = automatically_assign_extra_problems(db, target.id, 300)
    assert [row["team_id"] for row in result["assignments"]] == [eligible.id]
    assert result["failures"] == []
    assert [(t.ps_id, t.round1_problem_id, t.wildcard_problem_id, t.coins) for t in excluded + previous_winners] == before
    assert db.query(WalletTransaction).count() == 1


def test_auto_panel_and_remaining_share_post_r1_capacity_and_refresh_counts(db):
    first, target = seed(db)
    target.round = 1
    occupants = [Team(team_name=f"R1 winner {i}", ps_id=target.id, round1_problem_id=target.id,
        round1_assignment_type="BID_WINNER", round1_assignment_cost=100) for i in range(3)]
    extra_candidates = [Team(team_name=f"Candidate {i}") for i in range(3)]
    db.add_all(occupants + extra_candidates); db.commit()
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    def views():
        auto = extra_assignment_payload(db)
        remaining = remaining_problems_payload(db, control)
        auto_problem = next(row for row in auto["problems"] if row["id"] == target.id)
        remaining_problem = next(row for row in remaining["problems"] if row["id"] == target.id)
        assert auto["remaining_team_count"] == remaining["unassigned_team_count"]
        assert (auto_problem["assigned_team_count"], auto_problem["capacity_remaining"]) == (remaining_problem["assigned_team_count"], remaining_problem["capacity_remaining"])
        assert remaining_problem["auction_capacity"] == 5
        assert remaining_problem["can_assign"] is remaining_problem["can_rebid"] is False
        return auto, remaining_problem
    before, problem_before = views()
    assert before["remaining_team_count"] == 4 and problem_before["capacity_remaining"] == 2
    result = automatically_assign_extra_problems(db, target.id, 167)
    assert [row["team_id"] for row in result["assignments"]] == [first.id, extra_candidates[0].id]
    after, problem_after = views()
    assert after["remaining_team_count"] == 2 and problem_after["capacity_remaining"] == 0
    assert problem_after["assignment_status"] == "ASSIGNED" and problem_after["auction_full"] is True
    assert [row["team_id"] for row in problem_after["assigned_teams"]] == sorted([t.id for t in occupants] + [first.id, extra_candidates[0].id])
    assert first.round1_problem_id is first.round1_assignment_type is first.round1_assignment_cost is None


def test_active_r1_remaining_uses_existing_history_and_controls(db):
    team, target = seed(db)
    target.round = 1
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    control.ended = False; control.status = "READY"
    history = Team(team_name="Historical R1", round1_problem_id=target.id, round1_assignment_type="BID_WINNER", round1_assignment_cost=100)
    current_only = Team(team_name="Current Extra", ps_id=target.id)
    db.add_all([history, current_only]); db.commit()
    before = remaining_problems_payload(db, control)
    problem = next(row for row in before["problems"] if row["id"] == target.id)
    assert [row["team_id"] for row in problem["assigned_teams"]] == [history.id]
    assert problem["assigned_team_count"] == 1 and problem["capacity_remaining"] == 4
    assert problem["assignment_status"] == "PARTIAL"
    assert problem["can_assign"] is problem["can_rebid"] is True
    assert extra_assignment_payload(db)["can_auto_assign"] is True
    automatically_assign_extra_problems(db, target.id, 167)
    assert team.ps_id == target.id and team.coins == 4833
    assert team.round1_problem_id is None
    assert (control.ended, control.status) == (False, "READY")
    after = remaining_problems_payload(db, control)
    row = next(row for row in after["problems"] if row["id"] == target.id)
    for key in ["assigned_teams", "assigned_team_count", "capacity_remaining", "assignment_status", "can_rebid"]:
        assert row[key] == problem[key]
    assert after["unassigned_team_count"] == 0


@pytest.mark.parametrize("ended", [False, True])
@pytest.mark.parametrize("availability", ["available", "full", "no_candidates", "wildcard_only"])
def test_availability_depends_only_on_candidates_and_eligible_capacity(db, ended, availability):
    team, target = seed(db)
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    control.ended = ended
    if availability == "full":
        db.add_all([Team(team_name=f"Occupant {i}", ps_id=target.id) for i in range(5)])
    elif availability == "no_candidates":
        team.is_approved = False
    elif availability == "wildcard_only":
        target.round = 2
    db.commit()
    assert extra_assignment_payload(db)["can_auto_assign"] is (availability == "available")


def test_active_r1_one_slot_two_teams_charged_once_in_id_order(db):
    first, target = seed(db)
    target.round = 1
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    control.ended = False; control.status = "BIDDING"
    second = Team(team_name="Second candidate")
    db.add_all([second] + [Team(team_name=f"Winner {i}", ps_id=target.id,
        round1_problem_id=target.id, round1_assignment_type="BID_WINNER", round1_assignment_cost=100) for i in range(4)])
    db.commit()
    result = automatically_assign_extra_problems(db, target.id, 167)
    assert [row["team_id"] for row in result["assignments"]] == [first.id]
    assert db.query(Team).filter_by(ps_id=target.id).count() == 5
    assert first.coins == 4833 and first.round1_problem_id is None
    assert second.ps_id is None and second.coins == 5000
    assert db.query(WalletTransaction).one().amount == -167
    assert (control.ended, control.status) == (False, "BIDDING")
    with pytest.raises(ExtraAssignmentError, match="no remaining capacity"):
        automatically_assign_extra_problems(db, target.id, 167)
    assert db.query(WalletTransaction).count() == 1


@pytest.mark.parametrize("endpoint", ["rounds", "auction"])
@pytest.mark.parametrize("order", ["auto_first", "r1_first", "concurrent"])
def test_r1_finalization_and_auto_share_locked_capacity(db, session_factory, monkeypatch, endpoint, order):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.api import auction

    first, target = seed(db)
    target.round = 1; target.ps_number = "R1-1"; target.status = "visible"
    second = Team(team_name="Higher bidder")
    db.add(second); db.flush()
    db.add_all([Team(team_name=f"Existing winner {i}", ps_id=target.id, round1_problem_id=target.id,
        round1_assignment_type="BID_WINNER", round1_assignment_cost=100) for i in range(4)])
    db.add_all([Bid(team_id=first.id, ps_id=target.id, round=1, amount=100),
                Bid(team_id=second.id, ps_id=target.id, round=1, amount=200)])
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    control.ended = False; control.status = "READY"; control.current_problem_id = target.id
    db.query(GameConfig).one().current_round = 1
    db.commit()
    target_id, first_id, second_id = target.id, first.id, second.id
    db.close()
    async def broadcast(*args, **kwargs): pass
    monkeypatch.setattr(rounds.manager, "broadcast_event", broadcast)
    monkeypatch.setattr(auction.manager, "broadcast_event", broadcast)
    barrier = Barrier(2) if order == "concurrent" else None
    def auto():
        with session_factory() as session:
            if barrier: barrier.wait(timeout=5)
            try:
                return automatically_assign_extra_problems(session, target_id, 167)
            except ExtraAssignmentError as error:
                assert "no remaining capacity" in str(error)
                return None
    def finalize():
        if barrier: barrier.wait(timeout=5)
        if endpoint == "auction":
            return auction._finalize_round_one_transaction(session_factory, ps_id=target_id)
        with session_factory() as session:
            return asyncio.run(rounds.assign_winners("round-1", session, None))
    if order == "concurrent":
        with ThreadPoolExecutor(max_workers=2) as pool:
            auto_future, r1_future = pool.submit(auto), pool.submit(finalize)
            auto_future.result(timeout=15); r1_future.result(timeout=15)
    elif order == "auto_first":
        auto(); finalize()
    else:
        finalize(); auto()
    with session_factory() as check:
        assert check.query(Team).filter_by(ps_id=target_id).count() == 5
        candidates = [check.get(Team, first_id), check.get(Team, second_id)]
        assert sum(team.ps_id == target_id for team in candidates) == 1
        ledger = check.query(WalletTransaction).one()
        assigned = next(team for team in candidates if team.ps_id == target_id)
        assert assigned.id == ledger.team_id and assigned.coins == 5000 + ledger.amount
        if assigned.round1_problem_id is None:
            assert assigned.id == first_id and ledger.amount == -167
            assert ledger.transaction_type == "EXTRA_GRID_AUTO_ASSIGN"
        else:
            assert assigned.id == second_id and ledger.amount == -200
            assert ledger.transaction_type == "ROUND1_WIN"
        assert all(team.coins == 5000 for team in candidates if team.ps_id is None)
        assert check.query(Team).filter_by(round1_assignment_type="BID_WINNER", round1_assignment_cost=100).count() == 4
