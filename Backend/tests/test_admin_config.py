"""Admin config API and event state transitions."""
from app.models.models import EventConfig, GameConfig


def test_admin_get_config(client, admin_headers, db):
    response = client.get("/admin/config", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["starting_coins"] == 5000
    assert data["round1_winner_count"] == 5


def test_admin_update_config_validates(client, admin_headers, db):
    response = client.put("/admin/config", headers=admin_headers, json={"round1_winner_count": -1})
    assert response.status_code == 400
    response = client.put("/admin/config", headers=admin_headers, json={"round1_winner_count": 3})
    assert response.status_code == 400

    response = client.put("/admin/config", headers=admin_headers, json={
        "starting_coins": 1500,
        "round1_winner_count": 5,
        "round1_minimum_bid": 50,
        "round1_bid_increment": 5,
        "wildcard_starting_bid": 300,
        "wildcard_bid_increment": 10,
        "wildcard_enabled": False,
        "wildcard_slots": 4,
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["starting_coins"] == 1500
    assert data["round1_winner_count"] == 5
    assert data["round1_minimum_bid"] == 50
    assert data["wildcard_starting_bid"] == 300
    assert data["wildcard_bid_increment"] == 10
    assert data["wildcard_enabled"] is False


def test_import_uses_event_config_starting_coins(client, admin_headers, csv_bytes, db):
    client.put("/admin/config", headers=admin_headers, json={"starting_coins": 777})
    preview = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    ).json()
    client.post("/admin/registration/import/confirm", headers=admin_headers, json={"import_id": preview["import_id"]})

    from app.models.models import Team
    team = db.query(Team).filter(Team.team_name == "Team Alpha").first()
    assert team.coins == 777


def test_event_state_transitions(client, admin_headers, db):
    response = client.post("/admin/state", headers=admin_headers, json={"state": "ROUND1_PREVIEW"})
    assert response.status_code == 200
    assert response.json()["state"] == "ROUND1_PREVIEW"

    config = db.query(GameConfig).first()
    assert config.state == "ROUND1_PREVIEW"

    # invalid state rejected
    response = client.post("/admin/state", headers=admin_headers, json={"state": "LEADER_SELECTION"})
    assert response.status_code == 400


def test_round_controls(client, admin_headers, db):
    from app.models.models import EventConfig
    config = db.query(EventConfig).first()
    config.round1_bid_seconds = 300
    db.commit()

    preview = client.post("/admin/round/start-preview", headers=admin_headers)
    assert preview.status_code == 200

    resp = client.post("/admin/round/start-bidding", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["state"] == "ROUND1_BIDDING"
    assert resp.json()["ends_at"] is not None

    resp = client.post("/admin/round/pause", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["paused"] is True

    resp = client.post("/admin/round/add-time", params={"seconds": 60}, headers=admin_headers)
    assert resp.status_code == 200

    resp = client.post("/admin/round/resume", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["paused"] is False

    resp = client.post("/admin/round/end-bidding", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["state"] == "ROUND1_RESULT"


def test_event_lifecycle_timer_floor_and_persistence(client, admin_headers):
    client.put("/admin/config", headers=admin_headers, json={"round1_preview_seconds": 120})

    preview = client.post(
        "/admin/event/transition",
        headers=admin_headers,
        json={"state": "ROUND1_PREVIEW"},
    )
    assert preview.status_code == 200
    assert preview.json()["timing"]["remaining_seconds"] <= 120

    paused = client.post("/admin/event/timer/pause", headers=admin_headers)
    assert paused.status_code == 200
    assert paused.json()["timing"]["paused"] is True

    floored = client.post(
        "/admin/event/timer/adjust",
        headers=admin_headers,
        json={"seconds": -10000},
    )
    assert floored.status_code == 200
    assert floored.json()["timing"]["remaining_seconds"] == 0

    resumed = client.post("/admin/event/timer/resume", headers=admin_headers)
    assert resumed.status_code == 200
    assert resumed.json()["timing"]["paused"] is False

    extended = client.post(
        "/admin/event/timer/adjust",
        headers=admin_headers,
        json={"seconds": 60},
    )
    assert extended.status_code == 200
    assert 58 <= extended.json()["timing"]["remaining_seconds"] <= 60

    persisted = client.get("/admin/state", headers=admin_headers).json()
    assert persisted["event_state"] == "ROUND1_PREVIEW"
    assert persisted["timing"]["ends_at"] == extended.json()["timing"]["ends_at"]

    lifecycle = [
        "ROUND1_BIDDING", "ROUND1_RESULT", "WILDCARD_APPLICATION",
        "WILDCARD_BIDDING", "WILDCARD_SELECTION",
        "CODING", "SUBMISSION", "JUDGING_WAIT", "RESULTS",
    ]
    for state in lifecycle:
        response = client.post(
            "/admin/event/transition",
            headers=admin_headers,
            json={"state": state},
        )
        assert response.status_code == 200, response.text
        assert response.json()["event_state"] == state

    reset = client.post(
        "/admin/event/transition",
        headers=admin_headers,
        json={"state": "WAITING"},
    )
    assert reset.status_code == 409
    assert "Cannot transition" in reset.json()["detail"]


def test_event_controls_require_admin(client):
    assert client.post("/admin/event/transition", json={"state": "ROUND1_PREVIEW"}).status_code == 401
    assert client.post("/admin/event/timer/pause").status_code == 401
    assert client.post("/admin/event/timer/adjust", json={"seconds": 60}).status_code == 401
