from datetime import datetime, timedelta, timezone

from sqlalchemy import event

from app.api.websockets import manager
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.models import (
    Bid,
    FinalResult,
    Lab,
    LabAssignment,
    ProblemStatement,
    RoundControl,
    Team,
    User,
    Wildcard,
)
from app.services.lab_admin import provision_lab_admin_account


def _lab_admin_headers(client, db):
    user = provision_lab_admin_account(db)
    db.commit()
    response = client.post(
        "/lab-admin/login",
        data={"username": user.email, "password": settings.LAB_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_team_details(db):
    round1 = ProblemStatement(ps_number="PS-04", title="Smart Campus", description="Hidden", round=1, status="allocated")
    manual_problem = ProblemStatement(ps_number="PS-05", title="Energy Grid", description="Hidden", round=1, status="allocated")
    wildcard_problem = ProblemStatement(ps_number="WC-02", title="Open Innovation", description="Hidden", round=2, status="allocated")
    db.add_all([round1, manual_problem, wildcard_problem])
    db.flush()

    teams = {}
    costs = {"Alpha": 480, "Beta": 455, "Gamma": 440, "Delta": 420, "Epsilon": 400}
    for name in ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"):
        leader = User(
            name=f"{name} Leader",
            email=f"{name.lower()}@details.test",
            password_hash=get_password_hash("temp-pass"),
            role="leader",
        )
        db.add(leader)
        db.flush()
        manual = name == "Zeta"
        team = Team(
            team_name=name,
            leader_id=leader.id,
            ps_id=wildcard_problem.id if name == "Alpha" else (manual_problem.id if manual else round1.id),
            round1_problem_id=manual_problem.id if manual else round1.id,
            wildcard_problem_id=wildcard_problem.id if name == "Alpha" else None,
            final_problem_choice="WILDCARD" if name == "Alpha" else "ROUND1",
            round1_assignment_type="MANUAL_ASSIGNMENT" if manual else "BID_WINNER",
            round1_assignment_cost=None if manual else costs[name],
            is_approved=True,
            is_system_team=False,
        )
        db.add(team)
        db.flush()
        leader.team_id = team.id
        teams[name] = team

    waiting = Team(team_name="Waiting", is_approved=True, is_system_team=False)
    db.add(waiting)
    db.flush()
    labs = [Lab(name=f"Lab {name}", capacity=2, sort_order=index) for index, name in enumerate(teams, start=1)]
    db.add_all(labs)
    db.flush()
    for team, lab in zip(teams.values(), labs):
        db.add(LabAssignment(
            team_id=team.id,
            original_lab_id=lab.id,
            current_lab_id=lab.id,
            effective_ps_id=team.ps_id,
        ))

    reached_at = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)
    db.add_all([
        Bid(team_id=teams["Alpha"].id, ps_id=round1.id, amount=500, round=1, timestamp=reached_at),
        Bid(team_id=teams["Beta"].id, ps_id=round1.id, amount=460, round=1, timestamp=reached_at + timedelta(minutes=1)),
        Bid(team_id=teams["Gamma"].id, ps_id=round1.id, amount=460, round=1, timestamp=reached_at + timedelta(minutes=1)),
        Bid(team_id=teams["Delta"].id, ps_id=round1.id, amount=460, round=1, timestamp=reached_at + timedelta(minutes=2)),
        Bid(team_id=teams["Epsilon"].id, ps_id=round1.id, amount=400, round=1, timestamp=reached_at),
        Wildcard(
            team_id=teams["Alpha"].id,
            status="selected",
            used=True,
            rank=5,
            winning_bid=300,
            coins_paid=300,
            problem_id=wildcard_problem.id,
            selection_method="manual",
        ),
        RoundControl(round_type="WILDCARD", status="COMPLETE", ended=True),
        # Conflicting judging data must never affect Lab Admin team details.
        FinalResult(first_place_team_id=teams["Zeta"].id, result_status="PUBLISHED"),
        Team(team_name="System Team", ps_id=round1.id, is_approved=True, is_system_team=True),
        Team(team_name="Unapproved Team", ps_id=round1.id, is_approved=False, is_system_team=False),
    ])
    db.commit()
    return {"round1": round1, "manual": manual_problem, "wildcard": wildcard_problem, "teams": teams, "waiting": waiting, "labs": labs}


def _team(board, name):
    return next(row for row in board["teams"] if row["team_name"] == name)


def test_lab_admin_team_details_require_operator_role(client, db):
    seeded = _seed_team_details(db)
    assert client.get("/lab-allocation").status_code == 401

    participant = client.post("/login", data={"username": "alpha@details.test", "password": "temp-pass"})
    denied = client.get(
        "/lab-allocation",
        headers={"Authorization": f"Bearer {participant.json()['access_token']}"},
    )
    assert denied.status_code == 403

    allowed = client.get("/lab-allocation", headers=_lab_admin_headers(client, db))
    assert allowed.status_code == 200
    assert _team(allowed.json(), "Alpha")["round1"]["problem_number"] == "PS-04"
    assert seeded["teams"]["Alpha"].id == _team(allowed.json(), "Alpha")["id"]


def test_lab_admin_team_details_are_bounded_read_only_and_authoritative(client, db, engine, monkeypatch):
    seeded = _seed_team_details(db)
    online_ids = {seeded["teams"]["Alpha"].id, seeded["teams"]["Gamma"].id}
    monkeypatch.setattr(manager, "participant_team_ids", lambda: online_ids)
    headers = _lab_admin_headers(client, db)
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.strip().upper())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/lab-allocation", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert response.status_code == 200, response.text
    assert not [statement for statement in statements if statement.startswith(("INSERT", "UPDATE", "DELETE"))]
    assert not [statement for statement in statements if "FOR UPDATE" in statement]
    selects = [statement for statement in statements if statement.startswith("SELECT")]
    assert len(selects) == 9  # auth + eight fixed board/detail reads
    assert not [statement for statement in selects if "FINAL_RESULTS" in statement]

    board = response.json()
    assert board["team_count"] == 7
    assert board["participant_logged_in_count"] == 2
    assert board["logged_in_team_ids"] == sorted(online_ids)
    assert sum(team["logged_in"] for team in board["teams"]) == board["participant_logged_in_count"]
    assert {team["team_name"] for team in board["teams"]} == {*seeded["teams"], "Waiting"}
    assert all(team["team_name"] not in {"System Team", "Unapproved Team"} for team in board["teams"])

    expected_places = {"Alpha": 1, "Beta": 2, "Gamma": 3, "Delta": 4, "Epsilon": 5}
    for name, place in expected_places.items():
        row = _team(board, name)
        assert row["round1"]["place"] == place
        assert row["round1"]["assignment_type"] == "BID_WINNER"

    alpha = _team(board, "Alpha")
    assert alpha["round1"] == {
        "id": seeded["round1"].id,
        "problem_number": "PS-04",
        "problem_title": "Smart Campus",
        "winning_bid": 480,
        "assignment_type": "BID_WINNER",
        "place": 1,
    }
    assert alpha["wildcard_history"] == {
        "selected": True,
        "id": seeded["wildcard"].id,
        "problem_number": "WC-02",
        "problem_title": "Open Innovation",
        "winning_bid": 300,
        "place": 5,
    }
    assert alpha["final_problem"]["id"] == seeded["wildcard"].id
    assert alpha["effective_problem"]["id"] == seeded["wildcard"].id
    assert "description" not in alpha["round1"] and "description" not in alpha["wildcard_history"]

    beta = _team(board, "Beta")
    assert beta["round1"]["winning_bid"] == 455  # stored assignment cost, not ranking Bid.amount
    assert beta["wildcard_history"] == {"selected": False, "winning_bid": None, "place": None}
    assert beta["final_problem"]["id"] == seeded["round1"].id

    zeta = _team(board, "Zeta")
    assert zeta["round1"]["assignment_type"] == "MANUAL_ASSIGNMENT"
    assert zeta["round1"]["place"] is None
    assert zeta["final_problem"]["id"] == seeded["manual"].id

    alpha_assignment = next(
        team
        for lab in board["labs"]
        for team in lab["teams"]
        if team["id"] == seeded["teams"]["Alpha"].id
    )
    assert alpha_assignment["current_lab_id"] == seeded["labs"][0].id
    assert alpha_assignment["round1"]["place"] == 1

    waiting = _team(board, "Waiting")
    assert waiting["round1"] is None
    assert waiting["wildcard_history"] == {"selected": False, "winning_bid": None, "place": None}
    assert waiting["final_problem"] is None
