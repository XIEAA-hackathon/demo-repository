from sqlalchemy import event

from app.core.security import get_password_hash
from app.models.models import Bid, FinalResult, ProblemStatement, Team, User, Wildcard
from app.services.lab_admin import provision_lab_admin_account
from app.core.config import settings


def _lab_admin_headers(client, db):
    user = provision_lab_admin_account(db)
    db.commit()
    response = client.post(
        "/lab-admin/login",
        data={"username": user.email, "password": settings.LAB_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_results(db, *, published=True):
    round1 = ProblemStatement(ps_number="PS-04", title="Smart Campus", description="Round one", round=1, status="allocated")
    second_round1 = ProblemStatement(ps_number="PS-05", title="Energy Grid", round=1, status="allocated")
    wildcard_problem = ProblemStatement(ps_number="WC-02", title="Open Innovation", description="Wildcard", round=2, status="allocated")
    unassigned = ProblemStatement(ps_number="PS-06", title="Unused Problem", round=1, status="visible")
    db.add_all([round1, second_round1, wildcard_problem, unassigned])
    db.flush()

    teams = []
    for index, name in enumerate(("Alpha", "Beta", "Gamma", "Delta"), start=1):
        leader = User(
            name=f"{name} Leader",
            email=f"{name.lower()}@results.test",
            password_hash=get_password_hash("temp-pass"),
            role="leader",
        )
        db.add(leader)
        db.flush()
        original = round1 if index < 3 else second_round1
        team = Team(
            team_name=name,
            leader_id=leader.id,
            ps_id=wildcard_problem.id if name == "Alpha" else original.id,
            round1_problem_id=original.id,
            wildcard_problem_id=wildcard_problem.id if name == "Alpha" else None,
            final_problem_choice="WILDCARD" if name == "Alpha" else "ROUND1",
            final_problem_defaulted=name == "Delta",
            round1_assignment_type="BID_WINNER" if name != "Delta" else "MANUAL_ASSIGNMENT",
            round1_assignment_cost=420 - index * 20,
            is_approved=True,
        )
        db.add(team)
        db.flush()
        leader.team_id = team.id
        teams.append(team)

    db.add_all([
        Bid(team_id=teams[0].id, ps_id=round1.id, amount=420, round=1),
        Bid(team_id=teams[1].id, ps_id=round1.id, amount=300, round=1),
        Wildcard(
            team_id=teams[0].id,
            status="selected",
            used=True,
            rank=1,
            winning_bid=300,
            coins_paid=300,
            problem_id=wildcard_problem.id,
            selection_method="manual",
        ),
        FinalResult(
            first_place_team_id=teams[0].id,
            second_place_team_id=teams[1].id,
            third_place_team_id=teams[2].id,
            result_status="PUBLISHED" if published else "WAITING",
        ),
    ])
    db.commit()
    return {"round1": round1, "wildcard": wildcard_problem, "teams": teams}


def _problem(payload, problem_id):
    return next(row for row in payload["problems"] if row["id"] == problem_id)


def test_problem_results_requires_lab_admin(client, db):
    seeded = _seed_results(db)
    assert client.get("/lab-admin/problem-results").status_code == 401

    member = User(name="Alpha Member", email="member@results.test", password_hash=get_password_hash("temp-pass"), role="member", team_id=seeded["teams"][0].id)
    db.add(member)
    db.commit()
    for email in ("alpha@results.test", "member@results.test"):
        participant_login = client.post("/login", data={"username": email, "password": "temp-pass"})
        assert participant_login.status_code == 200, participant_login.text
        participant_headers = {"Authorization": f"Bearer {participant_login.json()['access_token']}"}
        denied = client.get("/lab-admin/problem-results", headers=participant_headers)
        assert denied.status_code == 403
        assert denied.json()["detail"] == "Lab Admin access required"

    allowed = client.get("/lab-admin/problem-results", headers=_lab_admin_headers(client, db))
    assert allowed.status_code == 200
    assert _problem(allowed.json(), seeded["round1"].id)["number"] == "PS-04"


def test_problem_results_preserves_history_values_placements_and_uses_bounded_read_queries(client, db, engine):
    seeded = _seed_results(db)
    headers = _lab_admin_headers(client, db)
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.strip().upper())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/lab-admin/problem-results", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert response.status_code == 200, response.text
    assert not [statement for statement in statements if statement.startswith(("INSERT", "UPDATE", "DELETE"))]
    assert len([statement for statement in statements if statement.startswith("SELECT")]) == 6  # auth + five fixed data reads

    payload = response.json()
    assert payload["summary"] == {"total_problems": 4, "round1_problems": 3, "wildcard_problems": 1, "assigned_teams": 4}
    round1 = _problem(payload, seeded["round1"].id)
    assert [row["team_name"] for row in round1["assignments"]] == ["Alpha", "Beta"]
    alpha_history = round1["assignments"][0]
    assert alpha_history["assignment_source"] == "BID_WINNER"
    assert alpha_history["assignment_cost"] == 400
    assert alpha_history["round1_bid_amount"] == 420
    assert alpha_history["changed_after_wildcard"] is True
    assert alpha_history["round1_problem"]["id"] == seeded["round1"].id
    assert "description" not in alpha_history["round1_problem"]
    assert alpha_history["final_problem"]["id"] == seeded["wildcard"].id
    assert alpha_history["placement"] == "1st Place"
    assert round1["assignments"][1]["placement"] == "2nd Place"

    wildcard = _problem(payload, seeded["wildcard"].id)
    assert len(wildcard["assignments"]) == 1
    selected = wildcard["assignments"][0]
    assert selected["team_name"] == "Alpha"
    assert selected["wildcard_rank"] == 1
    assert selected["wildcard_winning_bid"] == 300
    assert selected["coins_paid"] == 300
    assert selected["selection_method"] == "manual"
    assert selected["final_problem"]["id"] == seeded["wildcard"].id

    other_round1 = _problem(payload, seeded["teams"][2].round1_problem_id)
    assert {row["team_name"]: row["placement"] for row in other_round1["assignments"]} == {
        "Delta": "Not Placed",
        "Gamma": "3rd Place",
    }


def test_problem_results_keeps_placements_pending_until_published(client, db):
    _seed_results(db, published=False)
    response = client.get("/lab-admin/problem-results", headers=_lab_admin_headers(client, db))
    assert response.status_code == 200
    assignments = [assignment for problem in response.json()["problems"] for assignment in problem["assignments"]]
    assert assignments
    assert {assignment["placement"] for assignment in assignments} == {"Pending"}


def test_problem_results_handles_normal_incomplete_event_data(client, db):
    seeded = _seed_results(db)
    db.query(FinalResult).delete()
    db.query(Wildcard).delete()
    db.query(Bid).delete()
    alpha = seeded["teams"][0]
    alpha.leader_id = None
    alpha.round1_assignment_cost = None
    no_problem_leader = User(name="Waiting Leader", email="waiting@results.test", password_hash="unused", role="leader")
    db.add(no_problem_leader)
    db.flush()
    db.add(Team(team_name="Waiting Team", leader_id=no_problem_leader.id, is_approved=True))
    db.commit()

    response = client.get("/lab-admin/problem-results", headers=_lab_admin_headers(client, db))
    assert response.status_code == 200, response.text
    payload = response.json()
    alpha_row = next(row for problem in payload["problems"] for row in problem["assignments"] if row["team_name"] == "Alpha")
    assert payload["result_status"] == "WAITING"
    assert alpha_row["placement"] == "Pending"
    assert alpha_row["leader_name"] is None
    assert alpha_row["assignment_cost"] is None
    assert alpha_row["round1_bid_amount"] is None
    assert alpha_row["wildcard_rank"] is None
    assert all(row["team_name"] != "Waiting Team" for problem in payload["problems"] for row in problem["assignments"])
