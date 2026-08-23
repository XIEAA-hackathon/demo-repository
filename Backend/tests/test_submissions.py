from app.core.security import get_password_hash
from app.models.models import GameConfig, ProblemStatement, RoundControl, Submission, Team, User


def _team(db, name, email, problem):
    leader = User(name=f"{name} Leader", email=email, password_hash=get_password_hash("temp-pass"), role="leader")
    db.add(leader)
    db.flush()
    team = Team(
        team_name=name,
        coins=1000,
        leader_id=leader.id,
        is_approved=True,
        ps_id=problem.id,
        round1_problem_id=problem.id,
    )
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.commit()
    return team


def test_submission_monitor_open_close_and_final_problem(client, admin_headers, db, login_headers_factory):
    problem = ProblemStatement(ps_number="R1-1", title="Final Challenge", description="Build it", round=1, status="completed")
    db.add(problem)
    db.flush()
    alpha = _team(db, "Team Alpha", "alpha@submit.test", problem)
    beta = _team(db, "Team Beta", "beta@submit.test", problem)
    db.add_all([
        RoundControl(round_type="ROUND1", status="CLOSED", ended=True),
        RoundControl(round_type="WILDCARD", status="COMPLETE", ended=True),
    ])
    db.commit()
    alpha_headers = login_headers_factory("alpha@submit.test")
    beta_headers = login_headers_factory("beta@submit.test")

    assert client.put(
        "/submissions/me", headers=alpha_headers,
        json={"repository_url": "https://github.com/team-alpha/project"},
    ).status_code == 409
    opened = client.post("/admin/submissions/open", headers=admin_headers)
    assert opened.status_code == 200, opened.text

    submitted = client.put(
        "/submissions/me", headers=alpha_headers,
        json={"repository_url": "https://github.com/team-alpha/project"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["problem_id"] == problem.id
    record = db.query(Submission).filter(Submission.team_id == alpha.id).one()
    assert record.submitted_by_user_id == alpha.leader_id

    monitor = client.get("/admin/submissions", headers=admin_headers)
    assert monitor.status_code == 200
    body = monitor.json()
    assert body["submitted"] == 1
    assert body["pending"] == 1
    rows = {row["team_name"]: row for row in body["rows"]}
    assert rows["Team Alpha"]["status"] == "SUBMITTED"
    assert rows["Team Alpha"]["final_problem"]["title"] == "Final Challenge"
    assert rows["Team Beta"]["status"] == "PENDING"

    assert client.post("/admin/submissions/close", headers=admin_headers).status_code == 200
    db.expire_all()
    assert db.query(GameConfig).first().state == "JUDGING_WAIT"
    assert client.put(
        "/submissions/me", headers=alpha_headers,
        json={"repository_url": "https://github.com/team-alpha/updated"},
    ).status_code == 409
    assert client.put(
        "/submissions/me", headers=beta_headers,
        json={"repository_url": "https://github.com/team-beta/project"},
    ).status_code == 409
