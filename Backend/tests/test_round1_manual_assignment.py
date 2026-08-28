from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.websockets import manager
from app.core.database import Base
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, WalletTransaction
from app.services.round1_assignment import manually_assign_problem


def _round_case(db, *, status="no_bids", assigned=0, unassigned=3, coins=1000):
    problem = ProblemStatement(
        ps_number="R1-1",
        title="Manual control problem",
        description="Round 1 problem",
        round=1,
        status=status,
    )
    db.add(problem)
    db.flush()
    for index in range(assigned):
        db.add(Team(
            team_name=f"Existing {index}",
            coins=800,
            ps_id=problem.id,
            round1_problem_id=problem.id,
            round1_assignment_type="BID_WINNER",
            round1_assignment_cost=200,
            is_approved=True,
            is_system_team=False,
        ))
    waiting = [
        Team(
            team_name=f"Waiting {index}",
            coins=coins,
            is_approved=True,
            is_system_team=False,
        )
        for index in range(unassigned)
    ]
    db.add_all(waiting)
    control = RoundControl(round_type="ROUND1", status="READY")
    db.add(control)
    db.query(GameConfig).one().state = "ROUND1_RESULT"
    db.commit()
    return problem, control, waiting


def test_zero_bid_and_last_problem_remain_admin_controllable(client, admin_headers, db):
    problem, control, waiting = _round_case(db, status="current")
    control.current_problem_id = problem.id
    db.commit()

    response = client.post("/admin/rounds/round-1/assign-winners", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["winners"] == []
    assert response.json()["message"] == "No bids received. Problem moved to remaining allocation pool."
    db.expire_all()
    assert db.get(ProblemStatement, problem.id).status == "no_bids"
    assert all(db.get(Team, team.id).coins == 1000 for team in waiting)
    assert db.query(WalletTransaction).count() == 0
    control = db.get(RoundControl, control.id)
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (0, 0)
    assert control.ended is False

    row = response.json()["remaining_problems"]["problems"][0]
    assert row["assignment_status"] == "UNASSIGNED"
    assert row["assigned_team_count"] == 0 and row["capacity_remaining"] == 5
    assert row["can_rebid"] is True and row["can_assign"] is True


def test_three_real_bidders_leave_partial_capacity_and_update_actual_aggregate(
    client, admin_headers, db,
):
    problem, control, waiting = _round_case(db, status="current", unassigned=3)
    control.current_problem_id = problem.id
    for team, amount in zip(waiting, (200, 300, 400)):
        db.add(Bid(team_id=team.id, ps_id=problem.id, amount=amount, round=1))
    db.commit()

    response = client.post("/admin/rounds/round-1/assign-winners", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert len(response.json()["winners"]) == 3
    db.expire_all()
    control = db.get(RoundControl, control.id)
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (900, 3)
    row = response.json()["remaining_problems"]["problems"][0]
    assert row["assignment_status"] == "PARTIAL"
    assert row["assigned_team_count"] == 3 and row["capacity_remaining"] == 2


def test_manual_assignment_charges_selected_teams_once_without_changing_average(
    client, admin_headers, db, monkeypatch,
):
    problem, control, waiting = _round_case(db, unassigned=3)
    control.round1_winning_bid_sum = 1000
    control.round1_winning_bid_count = 4
    db.commit()
    events = []

    async def capture(event_type, payload):
        events.append((event_type, payload))

    monkeypatch.setattr(manager, "broadcast_event", capture)
    payload = {"team_ids": [waiting[0].id, waiting[1].id], "deduction": 300}
    first = client.post(
        f"/admin/rounds/round-1/problems/{problem.id}/assign",
        headers=admin_headers,
        json=payload,
    )
    second = client.post(
        f"/admin/rounds/round-1/problems/{problem.id}/assign",
        headers=admin_headers,
        json=payload,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200 and second.json()["idempotent"] is True
    db.expire_all()
    assert [(db.get(Team, team.id).coins, db.get(Team, team.id).round1_problem_id) for team in waiting] == [
        (700, problem.id),
        (700, problem.id),
        (1000, None),
    ]
    assert db.query(WalletTransaction).filter(
        WalletTransaction.transaction_type == "ROUND1_MANUAL_ASSIGN"
    ).count() == 2
    control = db.get(RoundControl, control.id)
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (1000, 4)
    row = second.json()["remaining_problems"]["problems"][0]
    assert row["assignment_status"] == "PARTIAL" and row["assigned_team_count"] == 2
    updates = [payload for event_type, payload in events if event_type == "round_updated"]
    assert len(updates) == 1 and updates[0]["action"] == "problem_manually_assigned"


def test_manual_assignment_rejects_owned_team_capacity_overflow_and_negative_balance(
    client, admin_headers, db,
):
    problem, _control, waiting = _round_case(db, assigned=4, unassigned=3)
    other = ProblemStatement(ps_number="R1-2", title="Other", round=1, status="completed")
    db.add(other)
    db.flush()
    waiting[0].round1_problem_id = other.id
    waiting[0].ps_id = other.id
    waiting[0].round1_assignment_type = "BID_WINNER"
    waiting[1].coins = 100
    db.commit()

    owned = client.post(
        f"/admin/rounds/round-1/problems/{problem.id}/assign",
        headers=admin_headers,
        json={"team_ids": [waiting[0].id], "deduction": 50},
    )
    overflow = client.post(
        f"/admin/rounds/round-1/problems/{problem.id}/assign",
        headers=admin_headers,
        json={"team_ids": [waiting[1].id, waiting[2].id], "deduction": 50},
    )
    balance = client.post(
        f"/admin/rounds/round-1/problems/{problem.id}/assign",
        headers=admin_headers,
        json={"team_ids": [waiting[1].id], "deduction": 300},
    )

    assert owned.status_code == 409 and "Only unassigned eligible" in owned.json()["detail"]
    assert overflow.status_code == 409 and "room for 1 more team" in overflow.json()["detail"]
    assert balance.status_code == 409 and "exceeds the available balance" in balance.json()["detail"]
    db.expire_all()
    assert db.get(Team, waiting[1].id).coins == 100
    assert db.query(WalletTransaction).filter(
        WalletTransaction.transaction_type == "ROUND1_MANUAL_ASSIGN"
    ).count() == 0


def test_rebid_reuses_normal_flow_resets_old_bid_slate_and_can_return_to_unassigned(
    client, admin_headers, db,
):
    problem, control, waiting = _round_case(db, unassigned=2)
    db.add(Bid(team_id=waiting[0].id, ps_id=problem.id, amount=300, round=1))
    db.commit()

    rebid = client.post(
        f"/admin/rounds/round-1/problems/{problem.id}/rebid",
        headers=admin_headers,
    )
    assert rebid.status_code == 200, rebid.text
    assert rebid.json()["current_problem"]["id"] == problem.id
    assert rebid.json()["status"] == "READY"
    assert db.query(Bid).filter(Bid.ps_id == problem.id, Bid.round == 1).count() == 0
    assert client.post("/admin/rounds/round-1/preview/start", headers=admin_headers).status_code == 200
    assert client.post("/admin/rounds/round-1/bidding/start", headers=admin_headers).status_code == 200
    assert client.post("/admin/rounds/round-1/bidding/close", headers=admin_headers).status_code == 200
    no_bids_again = client.post("/admin/rounds/round-1/assign-winners", headers=admin_headers)
    assert no_bids_again.status_code == 200, no_bids_again.text
    row = no_bids_again.json()["remaining_problems"]["problems"][0]
    assert row["assignment_status"] == "UNASSIGNED"
    assert row["can_rebid"] is True and row["can_assign"] is True
    db.expire_all()
    control = db.get(RoundControl, control.id)
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (0, 0)


def test_partial_problem_rebid_fills_only_remaining_capacity(client, admin_headers, db):
    problem, control, waiting = _round_case(db, status="current", assigned=4, unassigned=2)
    control.current_problem_id = problem.id
    for team, amount in zip(waiting, (300, 400)):
        db.add(Bid(team_id=team.id, ps_id=problem.id, amount=amount, round=1))
    db.commit()

    response = client.post("/admin/rounds/round-1/assign-winners", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert len(response.json()["winners"]) == 1
    assert response.json()["winners"][0]["team_id"] == waiting[1].id
    assert db.query(Team).filter(Team.round1_problem_id == problem.id).count() == 5
    assert db.get(Team, waiting[0].id).round1_problem_id is None


def test_zero_aggregate_uses_configured_base_deduction(client, admin_headers, db):
    db.query(EventConfig).one().round1_minimum_bid = 175
    problem, _control, _waiting = _round_case(db, unassigned=1)
    db.commit()

    response = client.get("/admin/rounds/round-1", headers=admin_headers)

    assert response.status_code == 200
    remaining = response.json()["remaining_problems"]
    assert remaining["round1_winning_bid_count"] == 0
    assert remaining["suggested_deduction"] == 175


def test_two_admin_sessions_cannot_apply_the_same_assignment_twice(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'round1-manual-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with factory() as db:
        db.add_all([EventConfig(), GameConfig(state="ROUND1_RESULT")])
        problem = ProblemStatement(ps_number="R1-RACE", title="Race", round=1, status="no_bids")
        control = RoundControl(round_type="ROUND1", status="READY")
        team = Team(team_name="Concurrent Team", coins=1000, is_approved=True, is_system_team=False)
        db.add_all([problem, control, team])
        db.commit()
        problem_id, control_id, team_id = problem.id, control.id, team.id

    def assign():
        with factory() as db:
            result = manually_assign_problem(
                db,
                db.get(RoundControl, control_id),
                problem_id,
                [team_id],
                250,
            )
            db.commit()
            return result["idempotent"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        idempotent_results = list(executor.map(lambda _: assign(), range(2)))

    with factory() as db:
        team = db.get(Team, team_id)
        assert team.round1_problem_id == problem_id and team.coins == 750
        assert db.query(WalletTransaction).filter(
            WalletTransaction.transaction_type == "ROUND1_MANUAL_ASSIGN"
        ).count() == 1
    assert sorted(idempotent_results) == [False, True]
    engine.dispose()
