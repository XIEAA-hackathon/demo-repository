from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import get_password_hash
from app.models.models import EventActivityLog, Team, User
from app.services.participant_session import participant_session_is_stale


PASSWORD = "ParticipantSession@123"


def test_session_staleness_uses_strict_ninety_second_boundary():
    now = datetime.now(timezone.utc)
    assert participant_session_is_stale(None, now=now) is True
    assert participant_session_is_stale(now - timedelta(seconds=90), now=now) is False
    assert participant_session_is_stale(
        now - timedelta(seconds=90, milliseconds=1),
        now=now,
    ) is True


def _participant(db, *, email: str, role: str = "leader") -> User:
    user = User(
        name=f"Session {role.title()}",
        email=email,
        password_hash=get_password_hash(PASSWORD),
        role=role,
    )
    db.add(user)
    db.flush()
    if role == "leader":
        team = Team(team_name=f"Team {email}", leader_id=user.id, is_approved=True)
        db.add(team)
        db.flush()
        user.team_id = team.id
    else:
        leader = User(
            name="Member Team Leader",
            email=f"leader-{email}",
            password_hash=get_password_hash("unused-password"),
            role="leader",
        )
        db.add(leader)
        db.flush()
        team = Team(team_name=f"Team {email}", leader_id=leader.id, is_approved=True)
        db.add(team)
        db.flush()
        leader.team_id = team.id
        user.team_id = team.id
    db.commit()
    db.refresh(user)
    return user


def _login(client, user: User, password: str = PASSWORD):
    return client.post("/login", data={"username": user.email, "password": password})


def _headers(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_first_login_invalid_credentials_active_rejection_and_reload(client, db):
    user = _participant(db, email="session-first@example.test")
    assert _login(client, user, "wrong-password").status_code == 401

    first = _login(client, user)
    assert first.status_code == 200, first.text
    first_headers = _headers(first)
    db.expire_all()
    stored = db.get(User, user.id)
    original_session_id = stored.session_id
    assert original_session_id
    assert stored.session_created_at is not None
    assert stored.session_last_seen_at is not None

    duplicate = _login(client, user)
    assert duplicate.status_code == 409
    assert client.get("/participant/dashboard", headers=first_headers).status_code == 200

    # A page reload restores and reuses the same local JWT; it does not login.
    # This also revives a matching pre-migration session whose timestamp is NULL.
    db.expire_all()
    db.get(User, user.id).session_last_seen_at = None
    db.commit()
    assert client.get("/participant/dashboard", headers=first_headers).status_code == 200
    db.expire_all()
    assert db.get(User, user.id).session_id == original_session_id
    assert db.get(User, user.id).session_last_seen_at is not None


def test_stale_session_is_replaced_and_old_token_cannot_logout_new_session(client, db):
    user = _participant(db, email="session-stale@example.test")
    first = _login(client, user)
    first_headers = _headers(first)
    db.expire_all()
    stored = db.get(User, user.id)
    first_session_id = stored.session_id
    stored.session_last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=91)
    db.commit()

    replacement = _login(client, user)
    assert replacement.status_code == 200, replacement.text
    replacement_headers = _headers(replacement)
    db.expire_all()
    current = db.get(User, user.id)
    assert current.session_id and current.session_id != first_session_id
    assert client.get("/participant/dashboard", headers=first_headers).status_code == 401
    assert client.post("/logout", headers=first_headers).status_code == 401
    assert client.get("/participant/dashboard", headers=replacement_headers).status_code == 200
    assert db.query(EventActivityLog).filter(
        EventActivityLog.action == "auth.session_replaced_stale"
    ).count() == 1


@pytest.mark.parametrize("role", ["leader", "member"])
def test_logout_clears_all_session_fields_and_allows_immediate_login(client, db, role):
    user = _participant(db, email=f"session-{role}@example.test", role=role)
    login = _login(client, user)
    assert login.status_code == 200, login.text
    assert _login(client, user).status_code == 409

    logout = client.post("/logout", headers=_headers(login))
    assert logout.status_code == 200
    db.expire_all()
    stored = db.get(User, user.id)
    assert stored.session_id is None
    assert stored.session_created_at is None
    assert stored.session_last_seen_at is None
    assert _login(client, user).status_code == 200


def test_websocket_reconnect_and_disconnect_preserve_same_session(client, db):
    user = _participant(db, email="session-websocket@example.test")
    login = _login(client, user)
    token = login.json()["access_token"]
    db.expire_all()
    session_id = db.get(User, user.id).session_id

    with client.websocket_connect(f"/ws/auction?token={token}") as socket:
        assert socket.receive_json()["type"] == "event_snapshot"
        db.expire_all()
        stored = db.get(User, user.id)
        heartbeat_baseline = datetime.now(timezone.utc) - timedelta(seconds=30)
        stored.session_last_seen_at = heartbeat_baseline
        db.commit()
        socket.send_text("heartbeat")
        assert socket.receive_json()["type"] == "session_heartbeat"
        db.expire_all()
        first_heartbeat_at = db.get(User, user.id).session_last_seen_at
        socket.send_text("heartbeat")
        assert socket.receive_json()["type"] == "session_heartbeat"
        db.expire_all()
        assert db.get(User, user.id).session_last_seen_at == first_heartbeat_at

    db.expire_all()
    disconnected = db.get(User, user.id)
    assert disconnected.session_id == session_id
    assert disconnected.session_last_seen_at is not None
    persisted_last_seen = disconnected.session_last_seen_at
    if persisted_last_seen.tzinfo is None:
        persisted_last_seen = persisted_last_seen.replace(tzinfo=timezone.utc)
    assert persisted_last_seen > heartbeat_baseline

    with client.websocket_connect(f"/ws/auction?token={token}") as socket:
        assert socket.receive_json()["type"] == "event_snapshot"
    db.expire_all()
    assert db.get(User, user.id).session_id == session_id


def test_admin_force_logout_revokes_session_and_allows_immediate_login(
    client, admin_headers, db,
):
    user = _participant(db, email="session-force@example.test")
    login = _login(client, user)
    old_headers = _headers(login)

    forced = client.post(
        f"/admin/participant-accounts/{user.id}/force-logout",
        headers=admin_headers,
    )
    assert forced.status_code == 200, forced.text
    assert forced.json()["status"] == "force_logged_out"
    assert client.get("/participant/dashboard", headers=old_headers).status_code == 401
    db.expire_all()
    stored = db.get(User, user.id)
    assert stored.session_id is None
    assert stored.session_created_at is None
    assert stored.session_last_seen_at is None
    assert _login(client, user).status_code == 200


def test_participant_cannot_force_logout_and_admin_login_still_replaces_admin_session(
    client, admin_headers, db,
):
    user = _participant(db, email="session-authz@example.test")
    participant_login = _login(client, user)
    assert client.post(
        f"/admin/participant-accounts/{user.id}/force-logout",
        headers=_headers(participant_login),
    ).status_code == 403

    second_admin = client.post(
        "/login",
        data={"username": "admin@test.com", "password": "admin123"},
    )
    assert second_admin.status_code == 200
    assert client.get("/admin/state", headers=admin_headers).status_code == 401
    assert client.get("/admin/state", headers=_headers(second_admin)).status_code == 200
