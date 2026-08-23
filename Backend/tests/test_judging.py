from app.core.security import get_password_hash
from app.models.models import Bid, FinalResult, GameConfig, ProblemStatement, Team, User, Wildcard, WildcardBid
from app.services.event_service import get_or_create_round_control


def _team(db, name: str, email: str) -> tuple[User, Team]:
    leader = User(name=f"{name} Leader", email=email, password_hash=get_password_hash("temp-pass"), role="leader")
    db.add(leader)
    db.flush()
    team = Team(team_name=name, leader_id=leader.id, coins=1000, is_approved=True)
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.commit()
    return leader, team


def _login(client, email: str) -> dict:
    response = client.post("/login", data={"username": email, "password": "temp-pass"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_problem_display_payload_tracks_round_one_preview_selection(client, display_headers, db):
    first = ProblemStatement(
        ps_number="R1-1", title="Adaptive Noise Cancellation", description="First problem description", round=1, status="current",
    )
    second = ProblemStatement(
        ps_number="R1-2", title="Tropical Cyclone Prediction", description="Second problem description", round=1, status="available",
    )
    db.add_all([first, second])
    db.flush()
    control = get_or_create_round_control(db, "ROUND1")
    control.current_problem_id = first.id
    control.status = "PREVIEW"
    game = db.query(GameConfig).first()
    game.state = "ROUND1_PREVIEW"
    db.commit()

    preview = client.get("/public/leaderboard", headers=display_headers)
    assert preview.status_code == 200
    assert preview.json()["problem"] == {
        "problem_number": "1", "number": "1", "title": "Adaptive Noise Cancellation", "description": "First problem description",
    }

    control.current_problem_id = second.id
    db.commit()
    updated = client.get("/public/leaderboard", headers=display_headers).json()["problem"]
    assert updated["problem_number"] == "2"
    assert updated["title"] == "Tropical Cyclone Prediction"
    assert updated["description"] == "Second problem description"


def test_saved_winners_remain_private_until_published_and_reset_clears_them(client, admin_headers, display_headers, db):
    leader_a, team_a = _team(db, "Team Alpha", "alpha@judging.test")
    _leader_b, team_b = _team(db, "Team Beta", "beta@judging.test")
    _leader_c, team_c = _team(db, "Team Gamma", "gamma@judging.test")
    game = db.query(GameConfig).first()
    game.state = "JUDGING_WAIT"
    db.commit()

    assert client.get("/admin/judging").status_code == 401
    assert client.put("/admin/judging/winners", json={
        "first_place_team_id": team_a.id,
        "second_place_team_id": team_b.id,
        "third_place_team_id": team_c.id,
    }).status_code == 401

    duplicate = client.put("/admin/judging/winners", headers=admin_headers, json={
        "first_place_team_id": team_a.id,
        "second_place_team_id": team_a.id,
        "third_place_team_id": team_c.id,
    })
    assert duplicate.status_code == 400

    invalid = client.put("/admin/judging/winners", headers=admin_headers, json={
        "first_place_team_id": team_a.id,
        "second_place_team_id": team_b.id,
        "third_place_team_id": 999999,
    })
    assert invalid.status_code == 400

    saved = client.put("/admin/judging/winners", headers=admin_headers, json={
        "first_place_team_id": team_a.id,
        "second_place_team_id": team_b.id,
        "third_place_team_id": team_c.id,
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["result_status"] == "WAITING"
    assert saved.json()["saved_at"] is not None

    public_waiting = client.get("/public/leaderboard", headers=display_headers)
    assert public_waiting.status_code == 200
    assert public_waiting.json()["mode"] == "JUDGING_WAITING"
    assert public_waiting.json()["results"] is None
    assert "Team Alpha" not in public_waiting.text

    participant_headers = _login(client, leader_a.email)
    dashboard_waiting = client.get("/participant/dashboard", headers=participant_headers)
    assert dashboard_waiting.status_code == 200
    assert dashboard_waiting.json()["finalResults"] is None

    published = client.post("/admin/judging/publish", headers=admin_headers)
    assert published.status_code == 200, published.text
    assert published.json()["result_status"] == "PUBLISHED"
    assert published.json()["first_place"]["team_name"] == "Team Alpha"

    db.expire_all()
    stored = db.query(FinalResult).one()
    assert stored.first_place_team_id == team_a.id
    assert stored.second_place_team_id == team_b.id
    assert stored.third_place_team_id == team_c.id
    assert stored.saved_at is not None
    assert stored.published_at is not None
    assert stored.result_status == "PUBLISHED"
    assert db.query(GameConfig).first().state == "RESULTS"

    public_results = client.get("/public/leaderboard", headers=display_headers).json()
    assert public_results["mode"] == "RESULTS_PUBLISHED"
    assert public_results["results"]["third_place"]["team_name"] == "Team Gamma"
    participant_results = client.get("/participant/dashboard", headers=participant_headers).json()
    assert participant_results["finalResults"]["second_place"]["team_name"] == "Team Beta"

    reset = client.post("/admin/event-data/reset", headers=admin_headers, json={"confirmation": "RESET EVENT"})
    assert reset.status_code == 200, reset.text
    assert reset.json()["deleted"]["final_results"] == 1
    assert db.query(FinalResult).count() == 0
    reset_display = client.get("/public/leaderboard", headers=display_headers).json()
    assert reset_display["mode"] == "WAITING"
    assert reset_display["results"] is None


def test_unified_public_leaderboard_uses_live_round_rankings_and_hides_closed_rows(client, admin_headers, display_headers, db):
    del admin_headers
    _leader_a, team_a = _team(db, "Team Alpha", "alpha@board.test")
    _leader_b, team_b = _team(db, "Team Beta", "beta@board.test")
    problem = ProblemStatement(ps_number="R1-3", title="Build the bridge", description="Short statement", round=1, status="current")
    db.add(problem)
    db.flush()
    round_one = get_or_create_round_control(db, "ROUND1")
    round_one.current_problem_id = problem.id
    round_one.status = "BIDDING"
    game = db.query(GameConfig).first()
    game.state = "ROUND1_BIDDING"
    db.add_all([
        Bid(team_id=team_a.id, ps_id=problem.id, amount=650, round=1),
        Bid(team_id=team_b.id, ps_id=problem.id, amount=590, round=1),
    ])
    db.commit()

    round_one_live = client.get("/public/leaderboard", headers=display_headers).json()
    assert round_one_live["mode"] == "ROUND1_LIVE"
    assert round_one_live["problem"] == {
        "problem_number": "3", "number": "3", "title": "Build the bridge", "description": "Short statement",
    }
    assert [row["team_name"] for row in round_one_live["rows"]] == ["Team Alpha", "Team Beta"]

    game.state = "ROUND1_RESULT"
    round_one.status = "CLOSED"
    db.commit()
    between_rounds = client.get("/public/leaderboard", headers=display_headers).json()
    assert between_rounds["mode"] == "WAITING"
    assert between_rounds["rows"] == []

    game.state = "RESULTS"
    db.commit()
    assert client.get("/public/leaderboard", headers=display_headers).json()["mode"] == "RESULTS_WAITING"

    wildcard = get_or_create_round_control(db, "WILDCARD")
    wildcard.status = "BIDDING_OPEN"
    wildcard.slot_count = 1
    game.state = "WILDCARD_BIDDING"
    db.add_all([
        Wildcard(team_id=team_a.id, status="applied"),
        Wildcard(team_id=team_b.id, status="applied"),
        WildcardBid(team_id=team_a.id, amount=500),
        WildcardBid(team_id=team_b.id, amount=450),
    ])
    db.commit()

    wildcard_live = client.get("/public/leaderboard", headers=display_headers).json()
    assert wildcard_live["mode"] == "WILDCARD_LIVE"
    assert wildcard_live["slot_count"] == 1
    assert [row["value"] for row in wildcard_live["rows"]] == [500, 450]
