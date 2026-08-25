"""Focused coverage for backend functionality synchronized from Pictures."""

from datetime import datetime, timedelta, timezone

from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, Wildcard


def _leader_headers(client, admin_headers, csv_bytes):
    preview = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    ).json()
    confirmed = client.post(
        "/admin/registration/import/confirm",
        headers=admin_headers,
        json={"import_id": preview["import_id"]},
    ).json()
    headers = {}
    for row in confirmed["credentials"]:
        login = client.post("/login", data={"username": row["username"], "password": row["temporary_password"]})
        assert login.status_code == 200, login.text
        headers[row["username"]] = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return headers


def test_admin_cooldown_controls_and_snapshot(client, admin_headers):
    too_high = client.put("/admin/config", headers=admin_headers, json={"bid_cooldown_seconds": 61})
    assert too_high.status_code == 400

    response = client.put("/admin/cooldown?seconds=9", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["bid_cooldown_seconds"] == 9

    response = client.post("/admin/cooldown/add?seconds=3", headers=admin_headers)
    assert response.json()["bid_cooldown_seconds"] == 12
    response = client.post("/admin/cooldown/reduce?seconds=20", headers=admin_headers)
    assert response.json()["bid_cooldown_seconds"] == 0

    snapshot = client.get("/admin/state", headers=admin_headers)
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["bid_cooldown_seconds"] == 0


def test_round_one_bid_cooldown_and_positive_validation(client, admin_headers, csv_bytes, db):
    leaders = _leader_headers(client, admin_headers, csv_bytes)
    alpha_headers = leaders["alice@test.com"]
    beta_headers = leaders["bob@test.com"]
    problem = ProblemStatement(ps_number="R1-COOLDOWN", title="Cooldown", description="desc", round=1, status="current")
    db.add(problem)
    db.commit()
    db.refresh(problem)

    game = db.query(GameConfig).first()
    game.state = "ROUND1_BIDDING"
    game.current_round = 1
    event = db.query(EventConfig).first()
    event.bid_cooldown_seconds = 5
    event.round1_minimum_bid = 100
    db.add(RoundControl(round_type="ROUND1", current_problem_id=problem.id, status="BIDDING"))
    db.commit()

    invalid = client.post("/bid", headers=alpha_headers, json={"ps_id": problem.id, "increment": 0})
    assert invalid.status_code == 422
    first = client.post("/bid", headers=alpha_headers, json={"ps_id": problem.id, "increment": 10})
    assert first.status_code == 200, first.text
    assert first.json()["amount"] == 110
    second = client.post("/bid", headers=alpha_headers, json={"ps_id": problem.id, "increment": 5})
    assert second.status_code == 429
    assert second.json()["detail"] == "Bid cooldown active."
    assert 0 < second.json()["retry_after_seconds"] <= 5
    assert int(second.headers["Retry-After"]) <= 5

    dashboard = client.get("/participant/dashboard", headers=alpha_headers)
    assert 0 < dashboard.json()["bidCooldownRemainingSeconds"] <= 5
    assert dashboard.json()["gameConfig"]["bid_cooldown_seconds"] == 5

    beta_bid = client.post("/bid", headers=beta_headers, json={"ps_id": problem.id, "increment": 25})
    assert beta_bid.status_code == 200, beta_bid.text
    assert beta_bid.json()["amount"] == 135

    alpha_bid = db.query(Bid).order_by(Bid.id.asc()).first()
    alpha_bid.timestamp = datetime.now(timezone.utc) - timedelta(seconds=5.1)
    db.commit()
    after_wait = client.post("/bid", headers=alpha_headers, json={"ps_id": problem.id, "increment": 10})
    assert after_wait.status_code == 200, after_wait.text
    assert after_wait.json()["amount"] == 145

    configured = client.put("/admin/config", headers=admin_headers, json={"bid_cooldown_seconds": 2})
    assert configured.status_code == 200, configured.text
    assert configured.json()["bid_cooldown_seconds"] == 2
    two_second_block = client.post("/bid", headers=alpha_headers, json={"ps_id": problem.id, "increment": 5})
    assert two_second_block.status_code == 429
    assert two_second_block.json()["retry_after_seconds"] <= 2

    alpha_bid.timestamp = datetime.now(timezone.utc) - timedelta(seconds=2.1)
    db.commit()
    assert client.post("/bid", headers=alpha_headers, json={"ps_id": problem.id, "increment": 5}).status_code == 200

    disabled = client.put("/admin/config", headers=admin_headers, json={"bid_cooldown_seconds": 0})
    assert disabled.status_code == 200, disabled.text
    assert client.post("/bid", headers=alpha_headers, json={"ps_id": problem.id, "increment": 5}).status_code == 200
    assert client.post("/bid", headers=alpha_headers, json={"ps_id": problem.id, "increment": 10}).status_code == 200
    leaderboard = client.get("/participant/leaderboard", headers=alpha_headers)
    assert leaderboard.status_code == 200
    assert any(row["bid_amount"] == 165 for row in leaderboard.json())
    db.query(Team).filter(Team.id == alpha_bid.team_id).update({Team.coins: 165})
    db.commit()
    insufficient = client.post("/bid", headers=alpha_headers, json={"ps_id": problem.id, "increment": 5})
    assert insufficient.status_code == 400
    assert "exceed the team wallet balance" in insufficient.json()["detail"]


def test_wildcard_bid_uses_same_team_cooldown(client, admin_headers, csv_bytes, db):
    alpha_headers = _leader_headers(client, admin_headers, csv_bytes)["alice@test.com"]
    team_id = client.get("/participant/dashboard", headers=alpha_headers).json()["team"]["id"]
    event = db.query(EventConfig).first()
    event.bid_cooldown_seconds = 5
    event.wildcard_starting_bid = 100
    event.wildcard_bid_increment = 1
    game = db.query(GameConfig).first()
    game.state = "WILDCARD_BIDDING"
    game.current_round = 2
    game.auction_timer_end = datetime.now(timezone.utc) + timedelta(seconds=60)
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    control.status = "BIDDING_OPEN"
    control.slot_count = 1
    db.add(Wildcard(team_id=team_id, status="applied"))
    db.commit()

    first = client.post("/wildcard/bid", json={"increment": 10}, headers=alpha_headers)
    assert first.status_code == 200, first.text
    assert first.json()["amount"] == 110
    second = client.post("/wildcard/bid", json={"increment": 5}, headers=alpha_headers)
    assert second.status_code == 429
    assert second.json()["detail"] == "Bid cooldown active."

    event.bid_cooldown_seconds = 0
    db.commit()
    allowed = client.post("/wildcard/bid", json={"increment": 25}, headers=alpha_headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["amount"] == 135
    db.query(Team).filter(Team.id == team_id).update({Team.coins: 135})
    db.commit()
    insufficient = client.post("/wildcard/bid", json={"increment": 5}, headers=alpha_headers)
    assert insufficient.status_code == 400


def test_admin_problem_management_and_upload_restriction(client, admin_headers):
    created = client.post(
        "/problem-statement",
        headers=admin_headers,
        json={"ps_number": "R1-EDIT", "title": "Before", "description": "desc", "round": 1, "status": "available"},
    )
    assert created.status_code == 200, created.text
    problem_id = created.json()["id"]

    updated = client.put(
        f"/problem-statement/{problem_id}",
        headers=admin_headers,
        json={"title": "After"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "After"

    admin_list = client.get("/problem-statements/admin", headers=admin_headers)
    assert admin_list.status_code == 200, admin_list.text
    assert any(row["id"] == problem_id for row in admin_list.json())

    deleted = client.delete(f"/problem-statement/{problem_id}", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text

    invalid_upload = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.exe", b"not a registration file", "application/octet-stream")},
    )
    assert invalid_upload.status_code == 400
    assert "Invalid file type" in invalid_upload.json()["detail"]
