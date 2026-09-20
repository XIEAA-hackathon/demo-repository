from unittest.mock import AsyncMock
from app.api import participant
from app.core.security import get_password_hash
from app.models.models import EventConfig, GameConfig, ProblemStatement, RoundControl, Submission, Team, User
from app.schemas.schemas import EVENT_STATES
from app.services.event_service import get_or_create_game_config


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


def test_submission_monitor_open_close_and_final_problem(client, admin_headers, db, login_headers_factory, monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr(participant.manager, "broadcast_event", broadcast)
    problem = ProblemStatement(ps_number="R1-1", title="Final Challenge", description="Build it", round=1, status="completed")
    db.add(problem)
    db.flush()
    alpha = _team(db, "Team Alpha", "alpha@submit.test", problem)
    beta = _team(db, "Team Beta", "beta@submit.test", problem)
    member = User(name="Alpha Member", email="alpha-member@submit.test", password_hash=get_password_hash("temp-pass"), role="member", team_id=alpha.id)
    db.add_all([
        member,
        RoundControl(round_type="ROUND1", status="CLOSED", ended=True),
        RoundControl(round_type="WILDCARD", status="COMPLETE", ended=True),
    ])
    game = db.query(GameConfig).one()
    game.state = "WILDCARD_FINAL_CHOICE"
    event_config = db.query(EventConfig).one()
    event_config.coding_duration_seconds = 7200
    event_config.submissions_open = False
    db.commit()

    opened = client.post("/admin/submissions/open", headers=admin_headers)
    assert opened.status_code == 200, opened.text
    db.expire_all()
    game = db.query(GameConfig).one()
    first_timer_end = game.auction_timer_end
    assert game.state == "CODING"
    assert (game.auction_timer_end - game.phase_started_at).total_seconds() == 7200
    assert db.query(EventConfig).one().submissions_open is True
    assert [call.args[0] for call in broadcast.await_args_list] == ["submission_updated", "event_state_changed"]

    duplicate = client.post("/admin/submissions/open", headers=admin_headers)
    assert duplicate.status_code == 200, duplicate.text
    db.expire_all()
    assert db.query(GameConfig).one().auction_timer_end == first_timer_end
    alpha_headers = login_headers_factory("alpha@submit.test")
    beta_headers = login_headers_factory("beta@submit.test")
    member_headers = login_headers_factory("alpha-member@submit.test")

    assert client.put(
        "/submissions/me", headers=member_headers,
        json={"repository_url": "https://github.com/team-alpha/member"},
    ).status_code == 403
    broadcast.reset_mock()

    submitted = client.post(
        "/submissions/me", headers=alpha_headers,
        json={"repository_url": "https://github.com/team-alpha/project"},
    )
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["problem_id"] == problem.id
    broadcast.assert_awaited_once()
    event_type, payload = broadcast.await_args.args
    assert event_type == "submission_updated"
    assert payload["team_id"] == alpha.id
    assert payload["submission"]["git_url"] == "https://github.com/team-alpha/project"
    assert payload["submission"]["submitted_by"] == "Team Alpha Leader"
    assert payload["submission"]["status"] == "SUBMITTED"
    assert set(payload) == {"team_id", "submission"}
    broadcast.reset_mock()

    updated = client.put(
        "/submissions/me", headers=alpha_headers,
        json={"repository_url": "https://github.com/team-alpha/updated"},
    )
    assert updated.status_code == 200, updated.text
    broadcast.assert_awaited_once()
    assert broadcast.await_args.args[1]["submission"]["git_url"] == "https://github.com/team-alpha/updated"
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
    assert db.query(EventConfig).one().submissions_open is False
    assert client.put(
        "/submissions/me", headers=alpha_headers,
        json={"repository_url": "https://github.com/team-alpha/updated"},
    ).status_code == 409
    assert client.put(
        "/submissions/me", headers=beta_headers,
        json={"repository_url": "https://github.com/team-beta/project"},
    ).status_code == 409


def test_open_coding_requires_completed_wildcard(client, admin_headers, db):
    db.add(RoundControl(round_type="WILDCARD", status="FINAL_CHOICE", ended=False))
    db.commit()

    response = client.post("/admin/submissions/open", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Complete the Wildcard round before opening Coding."
    assert db.query(GameConfig).one().state == "WAITING"
    assert db.query(EventConfig).one().submissions_open is False


def test_legacy_submission_state_normalizes_safely(db):
    assert "SUBMISSION" not in EVENT_STATES
    event_config = EventConfig(submissions_open=True)
    game = GameConfig(state="SUBMISSION")
    db.add_all([event_config, game]); db.commit()

    assert get_or_create_game_config(db).state == "CODING"
    game.state = "SUBMISSION"; event_config.submissions_open = False; db.commit()
    assert get_or_create_game_config(db).state == "JUDGING_WAIT"
