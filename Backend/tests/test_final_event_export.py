import csv
import io

from app.models.models import (
    EventConfig,
    GameConfig,
    ProblemStatement,
    RegistrationImportRow,
    Submission,
    Team,
    User,
)


def _import_teams(client, admin_headers):
    source = (
        "Team ID,Team Name,Leader Name,Leader Email,Leader Password,Member 1 Name,Organizer Notes\n"
        "T-001,Team Alpha,Alpha Leader,alpha@example.com,Alpha@123,Alpha Member,\"=SUM(1,1)\"\n"
        "T-002,Team Beta,Beta Leader,beta@example.com,Beta@123,Beta Member,Keep beta\n"
        "T-003,Team Gamma,Gamma Leader,gamma@example.com,Gamma@123,Gamma Member,Keep gamma\n"
        "T-004,Team Delta,Delta Leader,delta@example.com,Delta@123,Delta Member,Keep delta\n"
    ).encode()
    response = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.csv", source, "text/csv")},
    )
    assert response.status_code == 200, response.text


def _closed_final_event(db):
    db.query(EventConfig).one().submissions_open = False
    db.query(GameConfig).one().state = "JUDGING_WAIT"


def _rows(response):
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_final_export_combines_assignments_latest_submission_and_blanks(client, admin_headers, db):
    _import_teams(client, admin_headers)
    teams = {team.team_name: team for team in db.query(Team).all()}
    round1 = ProblemStatement(ps_number="P04", title="Smart Waste Management", round=1, status="allocated")
    wildcard = ProblemStatement(ps_number="P11", title="AI Traffic Management", round=2, status="allocated")
    db.add_all([round1, wildcard])
    db.flush()

    teams["Team Alpha"].round1_problem_id = round1.id
    teams["Team Alpha"].ps_id = round1.id
    teams["Team Beta"].round1_problem_id = round1.id
    teams["Team Beta"].wildcard_problem_id = wildcard.id
    teams["Team Beta"].ps_id = wildcard.id
    teams["Team Delta"].round1_problem_id = round1.id
    teams["Team Delta"].ps_id = round1.id
    alpha_leader = db.query(User).filter(User.email == "alpha@example.com").one()
    beta_leader = db.query(User).filter(User.email == "beta@example.com").one()
    alpha_submission = Submission(
        team_id=teams["Team Alpha"].id,
        problem_id=round1.id,
        submitted_by_user_id=alpha_leader.id,
        repository_url="https://github.com/example/alpha-old",
    )
    beta_submission = Submission(
        team_id=teams["Team Beta"].id,
        problem_id=wildcard.id,
        submitted_by_user_id=beta_leader.id,
        repository_url="https://github.com/example/beta-final",
    )
    db.add_all([alpha_submission, beta_submission])
    db.flush()
    alpha_submission.repository_url = "https://github.com/example/alpha-final"
    _closed_final_event(db)
    db.commit()

    counts_before = {
        "teams": db.query(Team).count(),
        "problems": db.query(ProblemStatement).count(),
        "submissions": db.query(Submission).count(),
    }
    response = client.get("/admin/submissions/export/final", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="Bid_to_Build_Final_Results.csv"'
    rows = _rows(response)
    assert [row["Team ID"] for row in rows] == ["T-001", "T-002", "T-003", "T-004"]
    by_team = {row["Team Name"]: row for row in rows}

    assert by_team["Team Alpha"]["Round 1 Assigned Problem"] == "P04 - Smart Waste Management"
    assert by_team["Team Alpha"]["Wildcard Assigned Problem"] == ""
    assert by_team["Team Alpha"]["GitHub Link"] == "https://github.com/example/alpha-final"
    assert by_team["Team Beta"]["Round 1 Assigned Problem"] == "P04 - Smart Waste Management"
    assert by_team["Team Beta"]["Wildcard Assigned Problem"] == "P11 - AI Traffic Management"
    assert by_team["Team Beta"]["GitHub Link"] == "https://github.com/example/beta-final"
    assert by_team["Team Gamma"]["Round 1 Assigned Problem"] == ""
    assert by_team["Team Gamma"]["Wildcard Assigned Problem"] == ""
    assert by_team["Team Gamma"]["GitHub Link"] == ""
    assert by_team["Team Delta"]["Round 1 Assigned Problem"] == "P04 - Smart Waste Management"
    assert by_team["Team Delta"]["GitHub Link"] == ""
    assert by_team["Team Alpha"]["Organizer Notes"] == "'=SUM(1,1)"
    assert counts_before == {
        "teams": db.query(Team).count(),
        "problems": db.query(ProblemStatement).count(),
        "submissions": db.query(Submission).count(),
    }


def test_final_export_uses_stored_team_id_not_mutable_display_fields(client, admin_headers, db):
    _import_teams(client, admin_headers)
    alpha = db.query(Team).filter(Team.team_name == "Team Alpha").one()
    beta = db.query(Team).filter(Team.team_name == "Team Beta").one()
    alpha_problem = ProblemStatement(ps_number="ID-A", title="Alpha assignment", round=1)
    beta_problem = ProblemStatement(ps_number="ID-B", title="Beta assignment", round=1)
    db.add_all([alpha_problem, beta_problem])
    db.flush()
    alpha.round1_problem_id = alpha_problem.id
    beta.round1_problem_id = beta_problem.id
    alpha_row = db.query(RegistrationImportRow).filter(RegistrationImportRow.team_name == "Team Alpha").one()
    alpha_row.team_name = "A stale display name"
    assert alpha_row.team_id == alpha.id
    _closed_final_event(db)
    db.commit()

    response = client.get("/admin/submissions/export/final", headers=admin_headers)
    assert response.status_code == 200, response.text
    alpha_export = next(row for row in _rows(response) if row["Team ID"] == "T-001")
    assert alpha_export["Round 1 Assigned Problem"] == "ID-A - Alpha assignment"


def test_final_export_requires_closed_submission_state_and_admin(client, admin_headers, db):
    _import_teams(client, admin_headers)
    config = db.query(EventConfig).one()
    game = db.query(GameConfig).one()

    game.state = "CODING"
    config.submissions_open = False
    db.commit()
    before_open = client.get("/admin/submissions/export/final", headers=admin_headers)
    assert before_open.status_code == 409

    game.state = "SUBMISSION"
    config.submissions_open = True
    db.commit()
    while_open = client.get("/admin/submissions/export/final", headers=admin_headers)
    assert while_open.status_code == 409
    submission_monitor = client.get("/admin/submissions", headers=admin_headers)
    assert submission_monitor.json()["export_available"] is False

    _closed_final_event(db)
    db.commit()
    submission_monitor = client.get("/admin/submissions", headers=admin_headers)
    assert submission_monitor.json()["export_available"] is True
    assert client.get("/admin/submissions/export/final").status_code == 401

    login = client.post("/login", data={"username": "alpha@example.com", "password": "Alpha@123"})
    assert login.status_code == 200, login.text
    participant_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/admin/submissions/export/final", headers=participant_headers).status_code == 403
