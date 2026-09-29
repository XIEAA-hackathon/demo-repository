import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.auth import BidAuthClaims, get_bid_auth_claims, get_current_active_admin
from app.api import labs, wildcard
from app.api.websockets import ConnectionManager
from app.core.database import get_db
from app.models.models import EventConfig, GameConfig, Lab, LabAssignment, ProblemStatement, RoundControl, Team, User, WalletTransaction, Wildcard, WildcardBid, WildcardSelectionPool
from app.schemas.schemas import BidIncrementRequest
from app.services.extra_assignment import ExtraAssignmentError, automatically_assign_extra_problems
from app.services.lab_allocation import LabAllocationError, allocate_labs, lab_board
from app.services.wildcard_service import assign_wildcard_selection, confirm_final_problem


def seed_35(db):
    problems = [ProblemStatement(ps_number=f"R1-{i}", title=f"Problem {i}", round=1, status="completed") for i in range(1, 8)]
    db.add_all(problems)
    db.add_all([RoundControl(round_type="ROUND1", ended=True, status="CLOSED", round1_winning_bid_sum=1234, round1_winning_bid_count=30), RoundControl(round_type="WILDCARD", ended=True, status="COMPLETE")])
    db.add_all([Lab(name=f"Lab {i}", capacity=7, sort_order=i) for i in range(5)])
    db.flush()
    teams = [Team(team_name=f"Team {i:02}", coins=5000, is_approved=True, is_system_team=False,
                  ps_id=problems[i // 5].id if i < 33 else None,
                  round1_problem_id=problems[i // 5].id if i < 30 else None,
                  round1_assignment_type="BID_WINNER" if i < 30 else None,
                  round1_assignment_cost=100 if i < 30 else None) for i in range(35)]
    db.add_all(teams)
    db.commit()
    return teams, problems


def test_missing_two_are_diagnosed_and_no_partial_commit(db):
    teams, _ = seed_35(db)
    with pytest.raises(LabAllocationError) as error:
        allocate_labs(db)
    detail = error.value.detail()
    assert detail["expected_count"] == detail["eligible_team_count"] == 35
    assert detail["graph_team_count"] == detail["max_flow"] == detail["allocated_count"] == 33
    assert [(row["team_id"], row["team_name"]) for row in detail["unassigned_teams"]] == [(team.id, team.team_name) for team in teams[-2:]]
    db.rollback()
    assert db.query(LabAssignment).count() == 0
    assert lab_board(db)["eligible_team_count"] == 35


def test_allocation_endpoint_returns_clear_409(db):
    seed_35(db)
    app = FastAPI()
    app.include_router(labs.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_admin] = lambda: None
    with TestClient(app) as client:
        response = client.post("/admin/lab-allocation/allocate")
    assert response.status_code == 409
    assert response.json()["detail"]["expected_count"] == 35
    assert response.json()["detail"]["allocated_count"] == 33
    assert len(response.json()["detail"]["unassigned_teams"]) == 2


def test_extra_grid_35_of_35_and_idempotent_with_r1_frozen(db):
    teams, _ = seed_35(db)
    before = [(t.id, t.round1_problem_id, t.round1_assignment_type, t.round1_assignment_cost, t.coins) for t in teams]
    result = automatically_assign_extra_problems(db)
    assert len(result["assignments"]) == 2 and result["failures"] == []
    assignments = [t.ps_id for t in teams]
    assert automatically_assign_extra_problems(db)["idempotent"] is True
    assert [t.ps_id for t in teams] == assignments
    assert [(t.id, t.round1_problem_id, t.round1_assignment_type, t.round1_assignment_cost, t.coins) for t in teams] == before
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    assert (control.status, control.ended, control.round1_winning_bid_sum, control.round1_winning_bid_count) == ("CLOSED", True, 1234, 30)
    assert db.query(WalletTransaction).count() == 0
    assert allocate_labs(db) == (True, 35)
    assert db.info["lab_allocation_diagnostics"]["graph_team_count"] == 35
    assert db.query(LabAssignment).count() == 35
    assert allocate_labs(db) == (False, 35)


def test_extra_grid_cannot_run_during_r1_or_exceed_capacity(db):
    teams, problems = seed_35(db)
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    control.ended = False
    db.commit()
    with pytest.raises(ExtraAssignmentError):
        automatically_assign_extra_problems(db)
    assert teams[-1].ps_id is None
    control.ended = True
    problems[-1].round = 2  # Remove the last remaining R1 capacity.
    db.commit()
    result = automatically_assign_extra_problems(db)
    assert result["assignments"] == []
    assert len(result["failures"]) == 2
    assert teams[-1].coins == 5000


def test_mixed_35_graph_uses_wildcard_final_choice_and_overrides_extra(db):
    teams, problems = seed_35(db)
    automatically_assign_extra_problems(db)
    bonus = [ProblemStatement(ps_number=f"WC-{i}", title=f"Wildcard {i}", round=2, status="visible") for i in range(2)]
    db.add_all(bonus)
    db.add(EventConfig())
    db.add(GameConfig(state="WILDCARD_FINAL_CHOICE", current_round=2))
    db.flush()
    control = db.query(RoundControl).filter_by(round_type="WILDCARD").one()
    control.ended = False
    control.status = "PROBLEM_SELECTION"
    # This team has an Extra/Grid assignment but no normal R1 bid/assignment.
    extra_team = teams[-1]
    previous = extra_team.ps_id
    db.add(Wildcard(team_id=extra_team.id, status="qualified", rank=1))
    db.add(WildcardSelectionPool(problem_id=bonus[0].id, position=1))
    db.commit()
    assign_wildcard_selection(db, method="manual", team_id=extra_team.id, problem_id=bonus[0].id)
    assert extra_team.ps_id == bonus[0].id != previous
    assert extra_team.round1_problem_id is None
    assert extra_team.final_problem_choice == "WILDCARD"
    # A normal R1 winner then chooses Wildcard over its earlier problem.
    team = teams[0]
    team.wildcard_problem_id = bonus[1].id
    control.status = "FINAL_CHOICE"
    control.ended = False
    db.add(Wildcard(team_id=team.id, status="selected", rank=2, problem_id=bonus[1].id))
    db.commit()
    confirm_final_problem(db, team_id=team.id, choice="WILDCARD", actor=None)
    assert team.ps_id == bonus[1].id
    assert team.round1_problem_id == problems[0].id
    assert allocate_labs(db)[1] == 35
    rows = db.query(LabAssignment).all()
    assert {row.team_id for row in rows} == {team.id for team in teams}
    assert {row.team_id: row.effective_ps_id for row in rows} == {team.id: team.ps_id for team in teams}


def test_infeasible_flow_preserves_existing_assignments(db):
    seed_35(db)
    automatically_assign_extra_problems(db)
    allocate_labs(db)
    before = [(row.id, row.team_id, row.current_lab_id) for row in db.query(LabAssignment).all()]
    db.query(Lab).update({Lab.capacity: 1})
    db.commit()
    with pytest.raises(LabAllocationError) as error:
        allocate_labs(db, replace_manual=True)
    assert error.value.context["max_flow"] == 5
    assert error.value.context["expected_count"] == 35
    db.rollback()
    assert [(row.id, row.team_id, row.current_lab_id) for row in db.query(LabAssignment).all()] == before


def test_lab_admin_receives_allocation_and_manual_change_events():
    async def scenario():
        manager = ConnectionManager()
        received = {}
        class Socket:
            async def accept(self): pass
            async def send_json(self, payload): received[self].append(payload)
        admin, participant, other = Socket(), Socket(), Socket()
        for socket, role, team in [(admin, "lab_admin", None), (participant, "leader", 1), (other, "leader", 2)]:
            received[socket] = []
            await manager.connect(socket, {"role": role, "team_id": team})
        change = {"team_id": 1, "lab": {"id": 4}}
        await manager.broadcast_event("lab_allocation_updated", {"assignments": [change]}, roles={"admin", "lab_admin"})
        await manager.broadcast_event("lab_assignment_changed", change, roles={"admin", "lab_admin", "leader", "member"})
        await manager.wait_for_pending()
        assert [row["type"] for row in received[admin]] == ["lab_assignment_changed", "lab_allocation_updated", "lab_assignment_changed"]
        assert [row["type"] for row in received[participant]] == ["lab_assignment_changed", "lab_assignment_changed"]
        assert received[other] == []
        await manager.stop()
    asyncio.run(scenario())


def test_wildcard_http_finishes_with_slow_fanout_and_closed_db(db, session_factory, monkeypatch):
    now = datetime.now(timezone.utc)
    user = User(name="Leader", email="leader@test.example", password_hash="unused", role="leader", session_id="session", session_last_seen_at=now)
    db.add(user); db.flush()
    team = Team(team_name="Bidders", leader_id=user.id, coins=5000)
    db.add(team); db.flush(); user.team_id = team.id
    db.add_all([Wildcard(team_id=team.id, status="applied"), EventConfig(wildcard_starting_bid=100, bid_cooldown_seconds=0), RoundControl(round_type="WILDCARD", status="BIDDING_OPEN"), GameConfig(state="WILDCARD_BIDDING", current_round=2, auction_timer_end=now + timedelta(minutes=5))])
    db.commit()
    email = user.email
    queries = []
    event.listen(session_factory.kw["bind"], "before_cursor_execute", lambda conn, cursor, statement, parameters, context, executemany: queries.append(statement))
    async def scenario():
        manager = ConnectionManager()
        gate = asyncio.Event()
        async def slow_fanout(*args, **kwargs): await gate.wait()
        manager._deliver_broadcast = slow_fanout
        real_publish = manager.publish_event
        def publish(*args, **kwargs):
            # The transaction's context manager must have returned its connection.
            assert session_factory.kw["bind"].pool.checkedout() == 0
            assert args[1]["amount"] == 101
            assert "leaderboard" not in args[1]
            return real_publish(*args, **kwargs)
        manager.publish_event = publish
        monkeypatch.setattr(wildcard, "manager", manager)
        app = FastAPI()
        app.state.session_factory = session_factory
        app.include_router(wildcard.router)
        app.dependency_overrides[get_bid_auth_claims] = lambda: BidAuthClaims(email=email, session_id="session", role="leader")
        # ASGI transport exercises the HTTP endpoint without launching a server.
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await asyncio.wait_for(client.post("/wildcard/bid", json={"increment": 1}), timeout=1)
        assert response.status_code == 200 and response.json()["amount"] == 101
        assert not gate.is_set()
        gate.set()
        await manager.wait_for_pending()
        await manager.stop()
    # Detach auth values so no fixture DB session remains checked out.
    db.expunge_all(); db.close()
    asyncio.run(scenario())
    assert sum("max(wildcard_bids.amount)" in statement.lower() for statement in queries) == 1
    assert not any("join" in statement.lower() for statement in queries)
    with session_factory() as check:
        assert check.query(WildcardBid).one().amount == 101
        assert check.query(Team).one().coins == 5000


@pytest.mark.parametrize("count", [33, 34, 35, 38])
def test_dynamic_eligible_count_independent_of_presence(db, count):
    problem = ProblemStatement(ps_number="R1-1", title="Problem", round=1)
    db.add(problem); db.flush()
    db.add(RoundControl(round_type="WILDCARD", ended=True, status="COMPLETE"))
    db.add_all([Lab(name=f"Lab {i}", capacity=1, sort_order=i) for i in range(count)])
    db.add_all([Team(team_name=f"Eligible {i}", ps_id=problem.id) for i in range(count)])
    db.add_all([Team(team_name="System", is_system_team=True), Team(team_name="Unapproved", is_approved=False)])
    db.commit()
    assert allocate_labs(db) == (True, count)
    detail = db.info["lab_allocation_diagnostics"]
    assert detail["eligible_team_count"] == detail["allocated_count"] == count
    assert detail["total_team_count"] == count + 2
    assert detail["unresolved_final_problem_count"] == 0
    board = lab_board(db, logged_in_team_ids=set())
    assert board["assigned_count"] == board["eligible_team_count"] == count
    assert board["participant_logged_in_count"] == 0


def test_35_resolved_teams_impossible_33_flow_is_not_committed(db):
    seed_35(db)
    automatically_assign_extra_problems(db)
    # Total capacity is exactly 33, although all 35 final problems are resolved.
    for index, lab in enumerate(db.query(Lab).order_by(Lab.id).all()):
        lab.capacity = 6 if index < 2 else 7
    db.commit()
    with pytest.raises(LabAllocationError) as error:
        allocate_labs(db)
    detail = error.value.detail()
    assert detail["expected_count"] == detail["graph_team_count"] == 35
    assert detail["max_flow"] == detail["allocated_count"] == 33
    assert len(detail["unassigned_teams"]) == 2
    assert all(row["team_id"] and row["team_name"] for row in detail["unassigned_teams"])
    db.rollback()
    assert db.query(LabAssignment).count() == 0
