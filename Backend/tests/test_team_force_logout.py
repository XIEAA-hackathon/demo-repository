from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api import admin, auth, websockets
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash
from app.models.models import Bid, Lab, LabAssignment, ProblemStatement, Team, User, Wildcard


class Socket:
    def __init__(self):
        self.closed = []

    async def close(self, **kwargs):
        self.closed.append(kwargs)


@pytest.fixture
def logout_app(session_factory, monkeypatch):
    app = FastAPI()
    app.include_router(admin.router)
    app.include_router(auth.router)
    app.state.session_factory = session_factory
    requests = []
    manager = websockets.ConnectionManager()
    events = []

    def request_db():
        with session_factory() as db:
            requests.append(db)
            yield db

    app.dependency_overrides[get_db] = request_db

    @app.get("/session-check")
    def session_check(user=Depends(auth.get_current_user)):
        return {"id": user.id}

    async def broadcast(event_type, payload, **kwargs):
        events.append((event_type, payload, kwargs))

    async def presence(factory):
        # Revocation must have committed and released its transaction before fanout.
        assert not requests[-1].in_transaction()
        await websockets.broadcast_presence_snapshot(factory, connection_manager=manager)

    monkeypatch.setattr(admin, "manager", manager)
    monkeypatch.setattr(manager, "broadcast_event", broadcast)
    monkeypatch.setattr(admin, "broadcast_presence_snapshot", presence)
    return app, manager, events


def seed_accounts(db, member_count=1, *, active=True):
    now = datetime.now(timezone.utc)
    target = Team(team_name="Team A", coins=4951, is_approved=True)
    other = Team(team_name="Team B", coins=4200, is_approved=True)
    db.add_all([target, other]); db.flush()

    def account(name, role, team_id=None):
        user = User(name=name, email=f"{name}@example.test", role=role,
                    team_id=team_id, password_hash=get_password_hash("SameCredentials123"),
                    credentials_active=True, session_id=f"session-{name}",
                    session_created_at=now, session_last_seen_at=now)
        db.add(user); db.flush()
        return user

    # Legacy leaders can have only Team.leader_id, with no User.team_id.
    leader = account("leader-a", "leader")
    target.leader_id = leader.id
    participants = [leader, *[account(f"member-a-{i}", "member", target.id) for i in range(member_count)]]
    untouched = [account("leader-b", "leader", other.id), account("member-b", "member", other.id),
                 account("event-admin", "admin", target.id), account("lab-admin", "lab_admin", target.id),
                 account("display", "display", target.id)]
    if not active:
        for user in participants:
            user.session_id = None
            user.session_created_at = None
            user.session_last_seen_at = None
    db.commit()
    return target.id, other.id, [user.id for user in participants], [user.id for user in untouched]


def headers(user):
    return {"Authorization": "Bearer " + create_access_token({
        "sub": user.email, "role": user.role, "session_id": user.session_id,
    })}


def account_snapshot(user):
    return (user.password_hash, user.credentials_active, user.role, user.team_id,
            user.session_id, user.session_created_at, user.session_last_seen_at)


@pytest.mark.parametrize("member_count", [1, 3])
def test_revokes_every_participant_atomically_without_changing_event_data(
    db, session_factory, logout_app, member_count, caplog,
):
    app, manager, events = logout_app
    team_id, other_id, participant_ids, untouched_ids = seed_accounts(db, member_count)
    problem = ProblemStatement(ps_number="PS-4", title="Final problem", round=1)
    lab = Lab(name="CC Lab", capacity=7)
    db.add_all([problem, lab]); db.flush()
    team = db.get(Team, team_id)
    team.ps_id = team.round1_problem_id = team.wildcard_problem_id = problem.id
    team.final_problem_choice = "WILDCARD"
    team.round1_assignment_type = "BID_WINNER"
    team.round1_assignment_cost = 100
    db.add_all([Bid(team_id=team_id, ps_id=problem.id, round=1, amount=100),
                Wildcard(team_id=team_id, status="selected", winning_bid=200),
                LabAssignment(team_id=team_id, original_lab_id=lab.id, current_lab_id=lab.id, effective_ps_id=problem.id)])
    db.commit()
    problem_id, lab_id = problem.id, lab.id
    before = {user.id: account_snapshot(user) for user in db.query(User).all()}
    participant_headers = {user_id: headers(db.get(User, user_id)) for user_id in participant_ids}
    admin_headers = headers(db.get(User, untouched_ids[2]))
    sockets = {}
    for user in db.query(User).all():
        socket = Socket(); sockets[user.id] = socket
        manager.active_connections[socket] = {"user_id": user.id, "role": user.role,
                                              "team_id": other_id if user.id in untouched_ids[:2] else team_id}
    db.close()
    commits = []
    record_commit = lambda session: commits.append(True)
    event.listen(session_factory.class_, "after_commit", record_commit)
    try:
        with TestClient(app) as client, caplog.at_level("INFO", logger="uvicorn.error"):
            response = client.post(f"/admin/teams/{team_id}/force-logout", headers=admin_headers)
            assert response.status_code == 200
            assert response.json() == {
                "status": "team_force_logged_out", "team_id": team_id, "team_name": "Team A",
                "participant_accounts_revoked": member_count + 1,
                "active_sessions_revoked": member_count + 1,
                "presence_connections_closed": member_count + 1,
            }
            assert len(commits) == 1
            with session_factory() as revoked_db:
                for user_id in participant_ids:
                    user = revoked_db.get(User, user_id)
                    assert (user.session_id, user.session_created_at, user.session_last_seen_at) == (None, None, None)
            for old_headers in participant_headers.values():
                assert client.get("/session-check", headers=old_headers).status_code == 401
            assert client.get("/session-check", headers=admin_headers).status_code == 200
            for user_id in untouched_ids[:2]:
                assert client.get("/session-check", headers=headers(db.get(User, user_id))).status_code == 200
            # Revocation is not a ban, and the normal duplicate-login policy still applies.
            login = client.post("/login", data={"username": "leader-a@example.test", "password": "SameCredentials123"})
            assert login.status_code == 200
            assert client.get("/session-check", headers={"Authorization": "Bearer " + login.json()["access_token"]}).status_code == 200
            assert client.post("/login", data={"username": "leader-a@example.test", "password": "SameCredentials123"}).status_code == 409
    finally:
        event.remove(session_factory.class_, "after_commit", record_commit)
    # Check the revocation snapshot before the later intentional re-login.
    event_type, presence, options = events[0]
    assert event_type == "participant_presence_changed"
    assert presence["logged_in_team_ids"] == presence["online_team_ids"] == [other_id]
    assert presence["participant_logged_in_count"] == presence["participant_online_count"] == 1
    assert options["roles"] == {"admin", "lab_admin"}
    for user_id in participant_ids:
        assert sockets[user_id].closed == [{"code": 4401, "reason": "Signed out by event admin"}]
        assert sockets[user_id] not in manager.active_connections
    for user_id in untouched_ids:
        assert not sockets[user_id].closed
    db.expire_all()
    for user_id in participant_ids[1:]:
        user = db.get(User, user_id)
        assert (user.session_id, user.session_created_at, user.session_last_seen_at) == (None, None, None)
        assert account_snapshot(user)[:4] == before[user_id][:4]
    assert account_snapshot(db.get(User, participant_ids[0]))[:4] == before[participant_ids[0]][:4]
    for user_id in untouched_ids:
        assert account_snapshot(db.get(User, user_id)) == before[user_id]
    team = db.get(Team, team_id)
    assert (team.coins, team.ps_id, team.round1_problem_id, team.wildcard_problem_id,
            team.final_problem_choice, team.round1_assignment_cost, team.is_approved) == (
                4951, problem_id, problem_id, problem_id, "WILDCARD", 100, True)
    assert db.query(Bid).one().amount == 100
    assert db.query(Wildcard).one().winning_bid == 200
    assert db.query(LabAssignment).one().current_lab_id == lab_id
    assert "admin.team_force_logout" in caplog.text
    assert "session-leader-a" not in caplog.text and "SameCredentials123" not in caplog.text


def test_offline_team_and_repeated_revocation_are_safe(db, logout_app):
    app, manager, events = logout_app
    team_id, _, participants, untouched = seed_accounts(db, active=False)
    admin_headers = headers(db.get(User, untouched[2]))
    before = {user_id: account_snapshot(db.get(User, user_id)) for user_id in participants}
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post(f"/admin/teams/{team_id}/force-logout", headers=admin_headers)
            assert response.status_code == 200
            assert response.json()["active_sessions_revoked"] == response.json()["presence_connections_closed"] == 0
    db.expire_all()
    assert all(account_snapshot(db.get(User, user_id)) == before[user_id] for user_id in participants)


@pytest.mark.parametrize("role", ["leader", "member", "lab_admin", "display", None])
def test_authorization_and_missing_team(db, logout_app, role):
    app, manager, events = logout_app
    team_id, _, participants, untouched = seed_accounts(db)
    users = db.query(User).all()
    request_headers = headers(next(user for user in users if user.role == role)) if role else {}
    with TestClient(app) as client:
        response = client.post(f"/admin/teams/{team_id}/force-logout", headers=request_headers)
        assert response.status_code == (403 if role else 401)
        admin_headers = headers(db.get(User, untouched[2]))
        assert client.post("/admin/teams/999999/force-logout", headers=admin_headers).status_code == 404
    db.expire_all()
    assert all(db.get(User, user_id).session_id for user_id in participants)
    assert not events
