import pytest

from app.api import rounds as rounds_api
from app.models.models import (
    Bid,
    GameConfig,
    Lab,
    LabAssignment,
    ProblemStatement,
    RoundControl,
    Team,
    WalletTransaction,
)
from app.services.lab_allocation import lab_board
from app.services.round1_assignment import (
    ROUND1_MANUAL_TRANSACTION,
    Round1AssignmentError,
    change_round1_problem_assignment,
    manually_assign_problem,
    remaining_problems_payload,
)


def _problem(db, number="R1-1", *, round_no=1):
    problem = ProblemStatement(
        ps_number=number,
        title=f"Problem {number}",
        description="Shared challenge",
        round=round_no,
        status="available",
    )
    db.add(problem)
    db.flush()
    return problem


def _team(db, name, problem=None, *, coins=500, approved=True, system=False):
    team = Team(
        team_name=name,
        coins=coins,
        is_approved=approved,
        is_system_team=system,
        ps_id=problem.id if problem else None,
        round1_problem_id=problem.id if problem else None,
        round1_assignment_type="BID_WINNER" if problem else None,
        round1_assignment_cost=100 if problem else None,
    )
    db.add(team)
    db.flush()
    return team


def _control(db, *, problem=None, status="READY", ended=False):
    control = RoundControl(
        round_type="ROUND1",
        current_problem_id=problem.id if problem else None,
        status=status,
        ended=ended,
    )
    db.add(control)
    db.flush()
    return control


def _assigned(db, problem, count):
    return [_team(db, f"Assigned {index + 1}", problem) for index in range(count)]


def test_manual_request_assigns_sixth_and_seventh_atomically_and_broadcasts(
    client, db, admin_headers, monkeypatch
):
    problem = _problem(db)
    _assigned(db, problem, 5)
    candidates = [_team(db, "Sixth"), _team(db, "Seventh")]
    _control(db)
    db.commit()
    events = []

    async def capture(kind, payload, **_kwargs):
        events.append((kind, payload))

    monkeypatch.setattr(rounds_api.manager, "broadcast_event", capture)
    response = client.post(
        f"/admin/rounds/round-1/problems/{problem.id}/assign",
        headers=admin_headers,
        json={"team_ids": [team.id for team in candidates], "deduction": 75},
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.query(Team).filter(Team.round1_problem_id == problem.id).count() == 7
    for team in candidates:
        refreshed = db.query(Team).filter(Team.id == team.id).one()
        assert (refreshed.ps_id, refreshed.round1_problem_id, refreshed.coins) == (problem.id, problem.id, 425)
        assert db.query(WalletTransaction).filter_by(
            team_id=team.id, transaction_type=ROUND1_MANUAL_TRANSACTION
        ).count() == 1
    update = next(payload for kind, payload in events if kind == "round_updated")
    assert update["action"] == "problem_manually_assigned"
    assert len(update["assignments"]) == 2


def test_manual_assignment_allows_eighth_and_is_idempotent(db):
    problem = _problem(db)
    _assigned(db, problem, 7)
    candidate = _team(db, "Eighth")
    control = _control(db)
    db.commit()

    result = manually_assign_problem(db, control, problem.id, [candidate.id], 50)
    db.commit()
    assert result["idempotent"] is False
    assert db.query(Team).filter(Team.round1_problem_id == problem.id).count() == 8
    assert candidate.coins == 450

    repeated = manually_assign_problem(db, control, problem.id, [candidate.id], 50)
    db.commit()
    db.refresh(candidate)
    assert repeated["idempotent"] is True
    assert candidate.coins == 450
    assert db.query(WalletTransaction).filter_by(
        team_id=candidate.id, transaction_type=ROUND1_MANUAL_TRANSACTION
    ).count() == 1


def test_payload_separates_auction_capacity_from_manual_availability(db):
    problem = _problem(db)
    _assigned(db, problem, 7)
    _team(db, "Still eligible")
    control = _control(db)
    db.commit()

    row = remaining_problems_payload(db, control)["problems"][0]
    assert row["assigned_team_count"] == 7
    assert row["auction_capacity"] == 5
    assert row["auction_capacity_remaining"] == row["capacity_remaining"] == 0
    assert row["auction_full"] is True
    assert row["can_rebid"] is False
    assert row["can_assign"] is row["manual_assignment_allowed"] is True


@pytest.mark.parametrize("invalid_kind", ["assigned", "system", "unapproved", "insufficient"])
def test_manual_multi_team_validation_is_atomic(db, invalid_kind):
    problem = _problem(db)
    other = _problem(db, "R1-2")
    valid = _team(db, "Valid")
    invalid = _team(
        db,
        "Invalid",
        other if invalid_kind == "assigned" else None,
        coins=20 if invalid_kind == "insufficient" else 500,
        approved=invalid_kind != "unapproved",
        system=invalid_kind == "system",
    )
    control = _control(db)
    db.commit()

    with pytest.raises(Round1AssignmentError):
        manually_assign_problem(db, control, problem.id, [valid.id, invalid.id], 50)
    db.rollback()
    db.refresh(valid)
    assert valid.ps_id is None and valid.round1_problem_id is None and valid.coins == 500
    assert db.query(WalletTransaction).filter_by(team_id=valid.id).count() == 0


def test_manual_assignment_rejects_duplicate_team_ids_without_charging(db):
    problem = _problem(db)
    candidate = _team(db, "Duplicate")
    control = _control(db)
    db.commit()

    with pytest.raises(Round1AssignmentError, match="only once"):
        manually_assign_problem(db, control, problem.id, [candidate.id, candidate.id], 50)
    db.rollback()
    db.refresh(candidate)
    assert candidate.coins == 500 and candidate.round1_problem_id is None


def test_change_problem_can_target_auction_full_problem_without_overwriting_wildcard(db):
    target = _problem(db)
    previous = _problem(db, "R1-OLD")
    wildcard = _problem(db, "WC-1", round_no=2)
    _assigned(db, target, 6)
    team = _team(db, "Correction", previous)
    team.ps_id = wildcard.id
    team.wildcard_problem_id = wildcard.id
    _control(db)
    db.commit()

    result = change_round1_problem_assignment(db, team.id, target.id)
    db.expire_all()
    changed = db.query(Team).filter(Team.id == team.id).one()
    assert result["idempotent"] is False
    assert changed.round1_problem_id == target.id
    assert changed.ps_id == wildcard.id


def test_auction_assignment_and_rebid_remain_capped_at_five(client, db, admin_headers, monkeypatch):
    problem = _problem(db)
    _assigned(db, problem, 3)
    bidders = [_team(db, f"Bidder {index + 1}") for index in range(4)]
    for index, team in enumerate(bidders):
        db.add(Bid(team_id=team.id, ps_id=problem.id, amount=400 - index * 10, round=1))
    control = _control(db, problem=problem)
    db.query(GameConfig).one().state = "ROUND1_RESULT"
    db.commit()

    async def ignore(*_args, **_kwargs):
        return None

    monkeypatch.setattr(rounds_api.manager, "broadcast_event", ignore)
    response = client.post("/admin/rounds/round-1/assign-winners", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["winners"]) == 2
    db.expire_all()
    assert db.query(Team).filter(Team.round1_problem_id == problem.id).count() == 5

    control = db.query(RoundControl).filter_by(id=control.id).one()
    control.status = "READY"
    control.ended = False
    control.current_problem_id = None
    db.commit()
    rebid = client.post(f"/admin/rounds/round-1/problems/{problem.id}/rebid", headers=admin_headers)
    assert rebid.status_code == 409


def test_lab_board_returns_all_seven_same_problem_teams(db):
    problem = _problem(db)
    _assigned(db, problem, 7)
    db.add(GameConfig(state="WAITING"))
    db.commit()

    board = lab_board(db)
    assert board["team_count"] == board["eligible_team_count"] == 7
    assert len(board["teams"]) == 7
    assert {team["round1"]["id"] for team in board["teams"]} == {problem.id}
    assert {team["effective_problem"]["id"] for team in board["teams"]} == {problem.id}


@pytest.mark.parametrize("lab_count,expected_status", [(7, 200), (6, 409)])
def test_same_problem_lab_allocation_keeps_one_team_per_lab(
    client, db, admin_headers, lab_count, expected_status
):
    problem = _problem(db)
    teams = _assigned(db, problem, 7)
    db.add_all([Lab(name=f"Lab {index + 1}", capacity=7, sort_order=index) for index in range(lab_count)])
    db.add(RoundControl(round_type="WILDCARD", status="COMPLETE", ended=True))
    db.query(GameConfig).one().state = "CODING"
    db.commit()

    response = client.post("/admin/lab-allocation/allocate", headers=admin_headers)
    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        assignments = db.query(LabAssignment).filter(LabAssignment.team_id.in_([team.id for team in teams])).all()
        assert len(assignments) == 7
        assert len({assignment.current_lab_id for assignment in assignments}) == 7
    else:
        assert response.json()["detail"]["code"] == "constraints_unsatisfied"
        assert response.json()["detail"]["max_flow"] == 6
        assert db.query(LabAssignment).count() == 0
