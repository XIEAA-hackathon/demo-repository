import asyncio
from time import perf_counter
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.auth import BidAuthClaims, get_bid_auth_claims, get_current_active_admin
from app.api import labs, rounds, wildcard
from app.api.websockets import ConnectionManager
from app.core.database import get_db
from app.models.models import Bid, EventConfig, GameConfig, Lab, LabAssignment, ProblemStatement, RoundControl, Team, User, WalletTransaction, Wildcard, WildcardBid, WildcardSelectionPool
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
    db.flush()
    db.add_all([Bid(team_id=team.id, ps_id=team.ps_id, round=1, amount=100) for team in teams[:30]])
    db.commit()
    return teams, problems


def test_33_resolved_allocate_and_two_awaiting_remain_visible(db):
    teams, _ = seed_35(db)
    assert allocate_labs(db) == (True, 33)
    board = lab_board(db)
    assert board["participant_team_count"] == len(board["teams"]) == 35
    assert board["allocation_eligible_count"] == board["allocated_count"] == 33
    assert board["awaiting_problem_count"] == 2 and board["unallocated_eligible_count"] == 0
    assert db.query(LabAssignment).filter(LabAssignment.team_id.in_([team.id for team in teams[-2:]])).count() == 0
    assert [row["id"] for row in board["awaiting_problem_teams"]] == [team.id for team in teams[-2:]]
    assert board["status"] == "ALLOCATED"
    assert allocate_labs(db) == (False, 33)


def test_allocation_endpoint_returns_clear_409(db):
    seed_35(db)
    for index, lab in enumerate(db.query(Lab).order_by(Lab.id).all()):
        lab.capacity = 6 if index < 4 else 7
    db.commit()
    app = FastAPI()
    app.include_router(labs.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_admin] = lambda: None
    with TestClient(app) as client:
        response = client.post("/admin/lab-allocation/allocate")
    assert response.status_code == 409
    assert response.json()["detail"]["expected_count"] == 33
    assert response.json()["detail"]["allocated_count"] == 31
    assert len(response.json()["detail"]["unassigned_teams"]) == 2


def test_incremental_resolution_preserves_33_and_manual_history(db):
    teams, problems = seed_35(db)
    allocate_labs(db)
    first = db.query(LabAssignment).order_by(LabAssignment.id).first()
    first.assignment_source = "MANUAL_OVERRIDE"
    before = [(r.id, r.team_id, r.current_lab_id, r.version, r.assignment_source) for r in db.query(LabAssignment).all()]
    teams[-2].ps_id = problems[-1].id
    db.commit()
    assert lab_board(db)["unallocated_eligible_count"] == 1
    assert allocate_labs(db) == (True, 34)
    assert [(r.id, r.team_id, r.current_lab_id, r.version, r.assignment_source) for r in db.query(LabAssignment).filter(LabAssignment.team_id.in_([t.id for t in teams[:33]])).all()] == before
    assert allocate_labs(db) == (False, 34)
    assert lab_board(db)["awaiting_problem_count"] == 1


def test_persistent_login_survives_disconnect_and_stale_activity_until_logout(db):
    from app.services.participant_presence import participant_presence_payload
    from app.services.participant_session import clear_user_session
    teams, _ = seed_35(db)
    user = User(name="Leader", email="session@test.example", password_hash="unused", role="leader", team_id=teams[0].id,
                credentials_active=True, session_id="active", session_last_seen_at=datetime.now(timezone.utc) - timedelta(days=10))
    db.add(user); db.commit()
    presence = participant_presence_payload(db, connected_team_ids=[])
    assert presence["logged_in_team_ids"] == [teams[0].id]
    assert presence["online_team_ids"] == []
    assert lab_board(db, logged_in_team_ids=set(presence["logged_in_team_ids"]))["teams"][0]["logged_in"] is True
    clear_user_session(user); db.commit()
    assert participant_presence_payload(db)["logged_in_team_ids"] == []


def test_login_projection_is_bulk_and_supports_legacy_leader_link(db):
    from app.services.participant_presence import participant_presence_payload
    teams, _ = seed_35(db)
    users = [User(name=f"Leader {i}", email=f"bulk-{i}@test.example", password_hash="unused", role="leader",
                  team_id=team.id if i else None, session_id=f"session-{i}", credentials_active=True) for i, team in enumerate(teams)]
    db.add_all(users); db.flush(); teams[0].leader_id = users[0].id; db.commit()
    expected_ids = [team.id for team in teams]
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany): statements.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", record)
    presence = participant_presence_payload(db, connected_team_ids=[])
    event.remove(db.get_bind(), "before_cursor_execute", record)
    assert presence["logged_in_team_ids"] == expected_ids
    assert len(statements) == 2  # One session/team join plus approved participant IDs.


def test_incremental_conflict_exposes_explicit_regeneration_without_reshuffling(db):
    a = ProblemStatement(ps_number="A", title="A", round=1)
    b = ProblemStatement(ps_number="B", title="B", round=1)
    left, right = Lab(name="Left", capacity=2), Lab(name="Right", capacity=1)
    db.add_all([a, b, left, right, RoundControl(round_type="WILDCARD", ended=True)]); db.flush()
    teams = [Team(team_name="Existing A", ps_id=a.id), Team(team_name="Existing B", ps_id=b.id), Team(team_name="New A", ps_id=a.id)]
    db.add_all(teams); db.flush()
    db.add_all([LabAssignment(team_id=teams[0].id, original_lab_id=left.id, current_lab_id=left.id, effective_ps_id=a.id, assignment_source="MANUAL_OVERRIDE"),
                LabAssignment(team_id=teams[1].id, original_lab_id=right.id, current_lab_id=right.id, effective_ps_id=b.id)])
    db.commit()
    with pytest.raises(LabAllocationError) as error:
        allocate_labs(db)
    assert error.value.code == "regeneration_required"
    assert error.value.context["regeneration_possible"] is True
    db.rollback()
    assert db.query(LabAssignment).count() == 2
    assert allocate_labs(db, replace_manual=True) == (True, 3)


def test_extra_grid_35_of_35_and_idempotent_with_r1_frozen(db):
    teams, problems = seed_35(db)
    before = [(t.id, t.round1_problem_id, t.round1_assignment_type, t.round1_assignment_cost, t.coins) for t in teams]
    result = automatically_assign_extra_problems(db, problems[-1].id)
    assert len(result["assignments"]) == 2 and result["failures"] == []
    assignments = [t.ps_id for t in teams]
    with pytest.raises(ExtraAssignmentError, match="no remaining capacity"):
        automatically_assign_extra_problems(db, problems[-1].id)
    assert [t.ps_id for t in teams] == assignments
    assert [(t.id, t.round1_problem_id, t.round1_assignment_type, t.round1_assignment_cost) for t in teams] == [row[:4] for row in before]
    assert [t.coins for t in teams] == [5000] * 33 + [4900, 4900]
    control = db.query(RoundControl).filter_by(round_type="ROUND1").one()
    assert (control.status, control.ended, control.round1_winning_bid_sum, control.round1_winning_bid_count) == ("CLOSED", True, 1234, 30)
    assert db.query(WalletTransaction).filter_by(transaction_type="EXTRA_GRID_AUTO_ASSIGN").count() == 2
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
        automatically_assign_extra_problems(db, problems[-1].id)
    assert teams[-1].ps_id is None
    control.ended = True
    problems[-1].round = 2  # Remove the last remaining R1 capacity.
    db.commit()
    with pytest.raises(ExtraAssignmentError, match="not eligible"):
        automatically_assign_extra_problems(db, problems[-1].id)
    assert teams[-1].coins == 5000


def test_mixed_35_graph_uses_wildcard_final_choice_and_overrides_extra(db):
    teams, problems = seed_35(db)
    automatically_assign_extra_problems(db, problems[-1].id)
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
    assert extra_team.coins == 4900
    assert db.query(WalletTransaction).filter_by(team_id=extra_team.id, transaction_type="EXTRA_GRID_AUTO_ASSIGN").one().amount == -100
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
    assert db.query(Bid).count() == 30  # Five Extra/Grid entrants have no R1 bid.


def test_infeasible_flow_preserves_existing_assignments(db):
    _, problems = seed_35(db)
    automatically_assign_extra_problems(db, problems[-1].id)
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
    sql_durations = []
    def before_sql(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)
        context._bid_test_started_at = perf_counter()
    def after_sql(conn, cursor, statement, parameters, context, executemany):
        sql_durations.append((perf_counter() - context._bid_test_started_at) * 1000)
    event.listen(session_factory.kw["bind"], "before_cursor_execute", before_sql)
    event.listen(session_factory.kw["bind"], "after_cursor_execute", after_sql)
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
            started = perf_counter()
            response = await asyncio.wait_for(client.post("/wildcard/bid", json={"increment": 1}), timeout=1)
            print(f"Isolated SQLite bid HTTP={(perf_counter() - started) * 1000:.2f}ms SQL={sum(sql_durations):.2f}ms queries={len(queries)} {response.headers.get('Server-Timing')}")
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
    _, problems = seed_35(db)
    automatically_assign_extra_problems(db, problems[-1].id)
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


def test_extra_endpoint_commits_then_notifies_and_connects_lab_allocation(db, monkeypatch):
    _, problems = seed_35(db)
    problem_id = problems[-1].id
    events = []
    def publish(name, payload, **kwargs):
        assert db.get_bind().pool.checkedout() == 0
        events.append((name, payload, kwargs))
        return True
    monkeypatch.setattr(rounds.manager, "publish_event", publish)
    app = FastAPI()
    app.include_router(rounds.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_admin] = lambda: None
    with TestClient(app) as client:
        first = client.post("/admin/extra-grid/auto-assign", json={"problem_id": problem_id, "deduction": 100})
        second = client.post("/admin/extra-grid/auto-assign", json={"problem_id": problem_id, "deduction": 100})
    assert first.status_code == 200 and second.status_code == 409
    assert len(first.json()["assignments"]) == 2
    assert "no remaining capacity" in second.json()["detail"]
    assert [row[0] for row in events] == ["round_updated", "lab_allocation_updated"]
    assert events[1][1]["team_count"] == 35
    assert "lab_admin" in events[1][2]["roles"]
    assert db.query(LabAssignment).count() == 35


def test_extra_grid_uses_external_pool_when_r1_capacity_is_full(db):
    teams, problems = seed_35(db)
    problems[-1].round = 2
    extra = ProblemStatement(ps_number="EXT-1", title="Extra problem", round=0)
    db.add(extra); db.commit()
    result = automatically_assign_extra_problems(db, extra.id)
    assert [row["problem_id"] for row in result["assignments"]] == [extra.id, extra.id]
    assert result["failures"] == []
    assert all(team.round1_problem_id is None for team in teams[-2:])
    assert automatically_assign_extra_problems(db, extra.id)["assignments"] == []
    assert allocate_labs(db)[1] == 35
