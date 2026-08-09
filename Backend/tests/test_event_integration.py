from app.api.websockets import make_event


def _participant_headers(client, admin_headers, csv_bytes):
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
    password = next(row["temporary_password"] for row in confirmed["credentials"] if row["email"] == "alice@test.com")
    token = client.post("/login", data={"username": "alice@test.com", "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_participant_cannot_use_admin_state(client, admin_headers, csv_bytes):
    headers = _participant_headers(client, admin_headers, csv_bytes)
    response = client.get("/admin/state", headers=headers)
    assert response.status_code == 403


def test_invalid_event_jump_is_rejected(client, admin_headers):
    response = client.put("/admin/event/state", headers=admin_headers, json={"state": "RESULTS"})
    assert response.status_code == 409
    assert "Cannot transition" in response.json()["detail"]


def test_event_snapshot_contains_server_timing(client, admin_headers):
    response = client.put("/admin/event/state", headers=admin_headers, json={"state": "ROUND1_PREVIEW"})
    assert response.status_code == 200
    timing = response.json()["timing"]
    assert timing["server_time"]
    assert timing["started_at"]
    assert timing["ends_at"]
    assert timing["paused"] is False


def test_websocket_event_envelope_is_structured():
    message = make_event("bid_updated", {"team_id": 4, "amount": 250})
    assert message["type"] == "bid_updated"
    assert message["timestamp"] == message["server_time"]
    assert message["payload"] == {"team_id": 4, "amount": 250}
