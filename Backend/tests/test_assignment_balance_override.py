from app.core.security import get_password_hash
from app.models.models import ProblemStatement, RoundControl, Team, User


def _problem(db, number: int) -> ProblemStatement:
    problem = ProblemStatement(
        ps_number=f"R1-{number}",
        title=f"Problem {number}",
        description=f"Description {number}",
        round=1,
        status="completed",
    )
    db.add(problem)
    db.flush()
    return problem


def _team(db, name: str, *, coins: int, problem: ProblemStatement | None = None) -> Team:
    slug = name.lower().replace(" ", "-")
    leader = User(
        name=f"{name} Leader",
        email=f"{slug}@balance.test",
        password_hash=get_password_hash("temp-pass"),
        role="leader",
    )
    db.add(leader)
    db.flush()
    team = Team(
        team_name=name,
        leader_id=leader.id,
        coins=coins,
        ps_id=problem.id if problem else None,
        round1_problem_id=problem.id if problem else None,
        is_approved=True,
        is_system_team=False,
    )
    db.add(team)
    db.flush()
    leader.team_id = team.id
    return team


def _control(db) -> RoundControl:
    control = RoundControl(
        round_type="ROUND1",
        status="CLOSED",
        ended=True,
        round1_winning_bid_sum=1400,
        round1_winning_bid_count=4,
    )
    db.add(control)
    db.flush()
    return control


def _assign(client, admin_headers, team: Team, problem: ProblemStatement, balance: int):
    return client.put(
        f"/admin/rounds/round-1/assignments/{team.id}",
        headers=admin_headers,
        json={"target_problem_id": problem.id, "new_balance": balance},
    )


def test_assignment_with_unchanged_final_balance(client, admin_headers, db):
    problem = _problem(db, 3)
    team = _team(db, "Unchanged Balance", coins=5000)
    _control(db)
    db.commit()

    response = _assign(client, admin_headers, team, problem, 5000)

    assert response.status_code == 200, response.text
    db.expire_all()
    team = db.get(Team, team.id)
    assert team.round1_problem_id == problem.id and team.coins == 5000
    assert response.json()["change"]["balance_changed"] is False


def test_assignment_can_set_a_lower_final_balance(client, admin_headers, db):
    problem = _problem(db, 3)
    team = _team(db, "Lower Balance", coins=5000)
    _control(db)
    db.commit()

    response = _assign(client, admin_headers, team, problem, 4200)

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Team, team.id).coins == 4200
    assert response.json()["change"]["coins_before"] == 5000
    assert response.json()["change"]["coins"] == 4200


def test_assignment_can_set_a_higher_final_balance(client, admin_headers, db):
    problem = _problem(db, 3)
    team = _team(db, "Higher Balance", coins=3200)
    _control(db)
    db.commit()

    response = _assign(client, admin_headers, team, problem, 5000)

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Team, team.id).coins == 5000
    assert db.get(Team, team.id).round1_problem_id == problem.id


def test_negative_balance_is_rejected_without_assignment(client, admin_headers, db):
    problem = _problem(db, 3)
    team = _team(db, "Negative Balance", coins=5000)
    _control(db)
    db.commit()

    response = _assign(client, admin_headers, team, problem, -100)

    assert response.status_code == 422
    db.expire_all()
    team = db.get(Team, team.id)
    assert team.coins == 5000 and team.round1_problem_id is None and team.ps_id is None


def test_full_problem_rejection_rolls_back_balance_override(client, admin_headers, db):
    problem = _problem(db, 3)
    for index in range(5):
        _team(db, f"Occupied {index}", coins=5000, problem=problem)
    waiting = _team(db, "Atomic Failure", coins=5000)
    _control(db)
    db.commit()

    response = _assign(client, admin_headers, waiting, problem, 4500)

    assert response.status_code == 409
    db.expire_all()
    waiting = db.get(Team, waiting.id)
    assert waiting.coins == 5000 and waiting.round1_problem_id is None and waiting.ps_id is None


def test_balance_override_preserves_winning_bid_aggregate(client, admin_headers, db):
    problem = _problem(db, 3)
    team = _team(db, "Aggregate Balance", coins=5000)
    control = _control(db)
    db.commit()

    response = _assign(client, admin_headers, team, problem, 4000)

    assert response.status_code == 200, response.text
    db.expire_all()
    control = db.get(RoundControl, control.id)
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (1400, 4)


def test_admin_refresh_returns_persisted_problem_and_balance(client, admin_headers, db):
    problem = _problem(db, 3)
    team = _team(db, "Refresh Balance", coins=7250)
    _control(db)
    db.commit()

    assert _assign(client, admin_headers, team, problem, 6100).status_code == 200
    refreshed = client.get("/admin/rounds/round-1/assignments", headers=admin_headers)

    assert refreshed.status_code == 200, refreshed.text
    row = next(item for item in refreshed.json()["teams"] if item["team_id"] == team.id)
    assert row["coins"] == 6100
    assert row["current_problem"]["id"] == problem.id


def test_double_click_retry_is_idempotent_after_setting_balance(client, admin_headers, db):
    problem = _problem(db, 3)
    team = _team(db, "Balance Retry", coins=5000)
    _control(db)
    db.commit()

    first = _assign(client, admin_headers, team, problem, 4200)
    second = _assign(client, admin_headers, team, problem, 4200)

    assert first.status_code == 200 and first.json()["idempotent"] is False
    assert second.status_code == 200 and second.json()["idempotent"] is True
    db.expire_all()
    assert db.get(Team, team.id).coins == 4200
