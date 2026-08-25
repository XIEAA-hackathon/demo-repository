from app.core.config import settings


def test_display_login_is_dedicated_and_least_privilege(client, admin_headers, display_headers):
    assert client.post(
        "/login",
        data={"username": settings.LEADERBOARD_DISPLAY_EMAIL, "password": settings.LEADERBOARD_DISPLAY_PASSWORD},
    ).status_code == 403

    assert client.get("/public/leaderboard").status_code == 401
    assert client.get("/leaderboard/round-1").status_code == 401
    assert client.get("/public/leaderboard", headers=display_headers).status_code == 200
    assert client.get("/leaderboard/round-1", headers=display_headers).status_code == 200

    assert client.get("/admin/state", headers=display_headers).status_code == 403
    assert client.post(
        "/admin/event-data/reset",
        headers=display_headers,
        json={"confirmation": "RESET EVENT"},
    ).status_code == 403
    assert client.post("/bid", headers=display_headers, json={"ps_id": 1, "increment": 5}).status_code == 403

    assert client.post("/logout", headers=display_headers).status_code == 200
    assert client.get("/public/leaderboard", headers=display_headers).status_code == 401
