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


def _team(payload, name):
    return next(row for row in payload["teams"] if row["team_name"] == name)


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
    assert _team(allowed.json(), "Alpha")["round1"]["problem_number"] == "PS-04"


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
    assert len([statement for statement in statements if statement.startswith("SELECT")]) == 5  # auth + four fixed data reads

    payload = response.json()
    assert payload["summary"] == {"total_teams": 4, "round1_assigned": 4, "wildcard_selected": 1, "top3_finalized": 3}
    assert [row["team_name"] for row in payload["teams"]] == ["Alpha", "Beta", "Delta", "Gamma"]
    assert len({row["team_id"] for row in payload["teams"]}) == 4

    alpha = _team(payload, "Alpha")
    assert alpha["round1"] == {
        "id": seeded["round1"].id,
        "problem_number": "PS-04",
        "problem_title": "Smart Campus",
        "winning_bid": 400,
    }
    assert alpha["wildcard"] == {
        "selected": True,
        "id": seeded["wildcard"].id,
        "problem_number": "WC-02",
        "problem_title": "Open Innovation",
        "winning_bid": 300,
    }
    assert alpha["final_problem"]["id"] == seeded["wildcard"].id
    assert alpha["final_choice"] == "WILDCARD"
    assert alpha["final_placement"] == "FIRST"
    assert "description" not in alpha["round1"]
    assert "description" not in alpha["wildcard"]

    assert _team(payload, "Beta")["final_placement"] == "SECOND"
    assert _team(payload, "Gamma")["final_placement"] == "THIRD"
    delta = _team(payload, "Delta")
    assert delta["wildcard"] == {"selected": False, "winning_bid": None}
    assert delta["final_placement"] == "NOT_PLACED"


def test_problem_results_keeps_placements_pending_until_published(client, db):
    _seed_results(db, published=False)
    response = client.get("/lab-admin/problem-results", headers=_lab_admin_headers(client, db))
    assert response.status_code == 200
    teams = response.json()["teams"]
    assert teams
    assert {team["final_placement"] for team in teams} == {"PENDING"}


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
    alpha_row = _team(payload, "Alpha")
    assert payload["result_status"] == "WAITING"
    assert alpha_row["final_placement"] == "PENDING"
    assert alpha_row["round1"]["winning_bid"] is None
    assert alpha_row["wildcard"] == {
        "selected": True,
        "id": seeded["wildcard"].id,
        "problem_number": "WC-02",
        "problem_title": "Open Innovation",
        "winning_bid": None,
    }
    assert all(row["team_name"] != "Waiting Team" for row in payload["teams"])
