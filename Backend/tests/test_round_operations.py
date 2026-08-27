from app.core.security import get_password_hash
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, User, Wildcard, WildcardBid


def _team(db, name, email):
    leader = User(name=f"{name} Leader", email=email, password_hash=get_password_hash("temp-pass"), role="leader")
    db.add(leader)
    db.flush()
    team = Team(team_name=name, coins=1000, leader_id=leader.id, is_approved=True)
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.commit()
    db.refresh(team)
    return team


def _problem_csv(prefix="Problem"):
    return (
        "Problem Number,Title,Description\n"
        f"1,{prefix} one title,{prefix} one description\n"
        f"2,{prefix} two title,{prefix} two description\n"
        f"3,{prefix} three title,{prefix} three description\n"
    ).encode()


def test_round_one_import_arbitrary_selection_and_team_lockout(client, admin_headers, db, login_headers_factory):
    alpha = _team(db, "Team Alpha", "alpha@round.test")
    beta = _team(db, "Team Beta", "beta@round.test")
    alpha_headers = login_headers_factory("alpha@round.test")
    beta_headers = login_headers_factory("beta@round.test")

    imported = client.post(
        "/admin/rounds/round-1/problems/import", headers=admin_headers,
        files={"file": ("round1.csv", _problem_csv(), "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 3
    problem_two = next(row for row in imported.json()["problems"] if row["problem_number"] == "2")
    selected = client.post(f"/admin/rounds/round-1/problems/{problem_two['id']}/select", headers=admin_headers)
    assert selected.status_code == 200
    assert selected.json()["current_problem"]["problem_number"] == "2"

    assert client.post("/admin/rounds/round-1/preview/start", headers=admin_headers).status_code == 200
    assert client.post("/admin/rounds/round-1/bidding/start", headers=admin_headers).status_code == 200
    assert client.post("/bid", headers=alpha_headers, json={"ps_id": problem_two["id"], "increment": 25}).status_code == 200
    assert client.post("/admin/rounds/round-1/bidding/close", headers=admin_headers).status_code == 200
    assigned = client.post("/admin/rounds/round-1/assign-winners", headers=admin_headers)
    assert assigned.status_code == 200, assigned.text
    assert [winner["team_name"] for winner in assigned.json()["winners"]] == ["Team Alpha"]

    db.expire_all()
    assert db.query(Team).filter(Team.id == alpha.id).one().ps_id == problem_two["id"]
    assert db.query(Team).filter(Team.id == alpha.id).one().round1_problem_id == problem_two["id"]
    assert db.query(Team).filter(Team.id == beta.id).one().ps_id is None
    dashboard = client.get("/participant/dashboard", headers=alpha_headers).json()
    assert dashboard["round1Assigned"] is True
    assert dashboard["currentProblem"]["ps_number"].endswith("2")

    problem_one = next(row for row in assigned.json()["problems"] if row["problem_number"] == "1")
    assert client.post(f"/admin/rounds/round-1/problems/{problem_one['id']}/select", headers=admin_headers).status_code == 200
    client.post("/admin/rounds/round-1/preview/start", headers=admin_headers)
    client.post("/admin/rounds/round-1/bidding/start", headers=admin_headers)
    locked = client.post("/bid", headers=alpha_headers, json={"ps_id": problem_one["id"], "increment": 25})
    assert locked.status_code == 409
    assert "already has a Round 1 problem" in locked.json()["detail"]
    assert client.post("/bid", headers=beta_headers, json={"ps_id": problem_one["id"], "increment": 10}).status_code == 200


def test_wildcard_applications_and_separate_problem_pool(client, admin_headers, db, login_headers_factory):
    assigned = _team(db, "Assigned Team", "assigned@wild.test")
    eligible = _team(db, "Eligible Team", "eligible@wild.test")
    late = _team(db, "Late Team", "late@wild.test")
    assigned_problem = ProblemStatement(ps_number="R1-99", title="Assigned", description="Assigned", round=1, status="completed")
    db.add(assigned_problem)
    db.flush()
    assigned.ps_id = assigned_problem.id
    db.commit()
    eligible_headers = login_headers_factory("eligible@wild.test")
    late_headers = login_headers_factory("late@wild.test")

    assert client.post("/admin/rounds/round-1/end", headers=admin_headers).status_code == 200
    opened = client.post("/admin/rounds/wildcard/applications/open", headers=admin_headers)
    assert opened.status_code == 200
    assert opened.json()["settings"]["application_seconds"] == 60
    assert opened.json()["applications"]["open"] is True
    assert client.post("/wildcard/apply", headers=eligible_headers).status_code == 200
    status = client.get("/admin/rounds/wildcard", headers=admin_headers).json()
    assert status["applications"]["applied"] == 1
    assert client.get("/participant/dashboard", headers=eligible_headers).json()["wildcardApplicationsOpen"] is True

    assert client.post("/admin/rounds/wildcard/applications/close", headers=admin_headers).status_code == 200
    assert client.post("/wildcard/apply", headers=late_headers).status_code == 409

    round_one = client.post(
        "/admin/rounds/round-1/problems/import", headers=admin_headers,
        files={"file": ("round1.csv", _problem_csv("Round"), "text/csv")},
    )
    wildcard = client.post(
        "/admin/rounds/wildcard/problems/import", headers=admin_headers,
        files={"file": ("wildcard.csv", _problem_csv("Wildcard"), "text/csv")},
    )
    assert round_one.status_code == wildcard.status_code == 200
    assert len([row for row in round_one.json()["problems"] if row["title"].startswith("Round")]) == 3
    assert all(row["description"].startswith("Wildcard") for row in wildcard.json()["problems"])
    wildcard_two = next(row for row in wildcard.json()["problems"] if row["problem_number"] == "2")
    selected = client.post(f"/admin/rounds/wildcard/problems/{wildcard_two['id']}/select", headers=admin_headers)
    assert selected.status_code == 409


def test_round_leaderboards_do_not_mix_rounds(client, admin_headers, display_headers, db):
    alpha = _team(db, "Round Team", "round@board.test")
    beta = _team(db, "Wildcard Team", "wildcard@board.test")
    round_problem = ProblemStatement(ps_number="R1-1", title="R1", round=1)
    wildcard_problem = ProblemStatement(ps_number="WC-1", title="WC", round=2)
    db.add_all([round_problem, wildcard_problem])
    db.flush()
    db.add_all([
        Bid(team_id=alpha.id, ps_id=round_problem.id, amount=225, round=1),
        Wildcard(team_id=beta.id, status="applied"),
        WildcardBid(team_id=beta.id, amount=175),
    ])
    db.commit()

    round_board = client.get("/leaderboard/round-1", headers=display_headers).json()
    wildcard_board = client.get("/leaderboard/wildcard", headers=display_headers).json()
    assert [row["team_name"] for row in round_board["rows"]] == ["Round Team"]
    assert [row["team_name"] for row in wildcard_board["rows"]] == ["Wildcard Team"]


def test_problem_import_validation_and_admin_authorization(client, admin_headers):
    duplicate = b"Problem No,Problem Title,Problem Description\n1,First,First description\n1,Duplicate,Duplicate description\n2,,\n"
    response = client.post(
        "/admin/rounds/round-1/problems/import", headers=admin_headers,
        files={"file": ("invalid.csv", duplicate, "text/csv")},
    )
    assert response.status_code == 422
    assert any("duplicate problem number" in item for item in response.json()["detail"])
    assert any("problem title is required" in item for item in response.json()["detail"])
    assert any("problem description is required" in item for item in response.json()["detail"])
    assert client.post(
        "/admin/rounds/round-1/problems/import",
        files={"file": ("round.csv", _problem_csv(), "text/csv")},
    ).status_code == 401
    assert client.post(
        "/admin/rounds/round-1/problems/import", headers=admin_headers,
        files={"file": ("round.txt", b"not supported", "text/plain")},
    ).status_code == 400


def test_round_one_live_board_uses_current_problem_and_reflects_bid_updates(client, admin_headers, display_headers, db, login_headers_factory):
    team = _team(db, "Live Team", "live@board.test")
    headers = login_headers_factory("live@board.test")
    old_problem = ProblemStatement(ps_number="R1-10", title="Old", round=1, status="completed")
    current_problem = ProblemStatement(ps_number="R1-11", title="Current", round=1, status="current")
    final_problem = ProblemStatement(ps_number="R1-12", title="Final", round=1, status="available")
    db.add_all([old_problem, current_problem, final_problem])
    db.flush()
    db.add(Bid(team_id=team.id, ps_id=old_problem.id, amount=900, round=1))
    db.add(RoundControl(round_type="ROUND1", current_problem_id=current_problem.id, status="BIDDING"))
    game = db.query(GameConfig).first()
    game.state = "ROUND1_BIDDING"
    game.current_round = 1
    db.query(EventConfig).first().bid_cooldown_seconds = 0
    db.commit()

    first = client.post("/bid", headers=headers, json={"ps_id": current_problem.id, "increment": 5})
    assert first.status_code == 200, first.text
    board = client.get("/leaderboard/round-1", headers=display_headers)
    assert board.headers["cache-control"] == "no-store"
    assert board.json()["rows"][0]["value"] == 30

    updated = client.post("/bid", headers=headers, json={"ps_id": current_problem.id, "increment": 25})
    assert updated.status_code == 200, updated.text
    refreshed = client.get("/leaderboard/round-1", headers=display_headers).json()
    assert refreshed["rows"][0]["value"] == 55


def test_problem_samples_round_trip_with_title_and_description(client, admin_headers):
    for round_slug in ("round-1", "wildcard"):
        sample = client.get(f"/admin/rounds/{round_slug}/problems/sample.csv", headers=admin_headers)
        assert sample.status_code == 200
        assert sample.text.startswith("Problem Number,Title,Description")
        imported = client.post(
            f"/admin/rounds/{round_slug}/problems/import",
            headers=admin_headers,
            files={"file": (f"{round_slug}.csv", sample.content, "text/csv")},
        )
        assert imported.status_code == 200, imported.text
        first = next(row for row in imported.json()["problems"] if row["problem_number"] == "1")
        assert first["title"] == "Adaptive Noise Cancellation"
        assert first["description"].startswith("Develop an AI/ML-enabled")
