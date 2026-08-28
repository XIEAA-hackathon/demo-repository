from app.core.security import get_password_hash
from app.api.websockets import manager
from app.models.models import GameConfig, ProblemStatement, RoundControl, Team, User, Wildcard
from app.services.participant_presence import participant_presence_payload
from app.services.round1_auto_assignment import is_final_auto_allotment_problem


def _participant(db, *, name: str, email: str, session_id: str | None = None):
    user = User(
        name=name,
        email=email,
        password_hash=get_password_hash("Participant@123"),
        role="leader",
        session_id=session_id,
    )
    db.add(user)
    db.flush()
    team = Team(team_name=f"{name} Team", leader_id=user.id, is_approved=True)
    db.add(team)
    db.commit()
    return user, team


def test_participant_presence_counts_unique_active_teams_and_excludes_other_roles(db):
    first, first_team = _participant(db, name="First", email="first@presence.test", session_id="leader-session")
    second, _second_team = _participant(db, name="Second", email="second@presence.test", session_id="second-session")
    db.add(User(name="First member", email="member@presence.test", password_hash="x", role="member", team_id=first_team.id, session_id="member-session"))
    db.add(User(name="Other admin", email="admin@presence.test", password_hash="x", role="admin", session_id="admin-session"))
    db.add(User(name="Display", email="display@presence.test", password_hash="x", role="display", session_id="display-session"))
    db.commit()

    assert participant_presence_payload(db) == {
        "logged_in_team_ids": [first_team.id, _second_team.id],
        "participant_logged_in_count": 2,
        "registered_participant_count": 2,
    }
    first.session_id = None
    db.commit()
    assert participant_presence_payload(db)["participant_logged_in_count"] == 2
    db.query(User).filter(User.team_id == first_team.id).update({User.session_id: None})
    db.commit()
    assert participant_presence_payload(db)["participant_logged_in_count"] == 1


def test_admin_team_list_uses_unique_authenticated_connection_presence(client, admin_headers, db):
    _first, first_team = _participant(db, name="Connected", email="connected@presence.test")
    _second, second_team = _participant(db, name="Offline", email="offline@presence.test")
    first_tab = object()
    duplicate_tab = object()
    manager.active_connections = {
        first_tab: {"user_id": 10, "role": "leader", "team_id": first_team.id},
        duplicate_tab: {"user_id": 10, "role": "leader", "team_id": first_team.id},
    }
    try:
        response = client.get("/teams", headers=admin_headers)
        assert response.status_code == 200, response.text
        rows = {row["id"]: row for row in response.json()}
        assert rows[first_team.id]["logged_in"] is True
        assert rows[second_team.id]["logged_in"] is False
    finally:
        manager.active_connections.clear()


def test_manual_round_one_end_stops_active_auction_without_assigning(client, admin_headers, db):
    problem = ProblemStatement(ps_number="R1-MANUAL", title="Active", round=1, status="current")
    db.add(problem)
    db.flush()
    team = Team(team_name="Unassigned", is_approved=True, coins=900)
    db.add(team)
    control = RoundControl(round_type="ROUND1", current_problem_id=problem.id, status="BIDDING")
    db.add(control)
    game = db.query(GameConfig).one()
    game.state = "ROUND1_BIDDING"
    db.commit()

    response = client.post("/admin/rounds/round-1/end", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["ended"] is True
    db.refresh(control)
    db.refresh(team)
    assert control.status == "CLOSED" and control.current_problem_id is None
    assert team.round1_problem_id is None and team.coins == 900
    assert client.post("/admin/rounds/round-1/end", headers=admin_headers).status_code == 200


def test_final_round_one_problem_rejects_every_normal_auction_api(client, admin_headers, db):
    participant, team = _participant(db, name="Final", email="final@round.test")
    login = client.post("/login", data={"username": participant.email, "password": "Participant@123"})
    participant_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    problem = ProblemStatement(ps_number="R1-LAST", title="Last", round=1, status="current")
    db.add(problem)
    db.flush()
    control = RoundControl(round_type="ROUND1", current_problem_id=problem.id, status="READY")
    db.add(control)
    db.commit()

    assert is_final_auto_allotment_problem(db, problem.id) is True
    summary = client.get("/admin/rounds/round-1", headers=admin_headers)
    assert summary.status_code == 200
    assert summary.json()["final_auto_assignment"]["status"] == "PENDING"
    assert client.post("/admin/rounds/round-1/preview/start", headers=admin_headers).status_code == 409
    assert client.post("/admin/rounds/round-1/bidding/start", headers=admin_headers).status_code == 409
    game = db.query(GameConfig).one()
    game.state = "ROUND1_BIDDING"
    control.status = "BIDDING"
    db.commit()
    assert client.post("/bid", headers=participant_headers, json={"ps_id": problem.id, "increment": 5}).status_code == 409
    assert client.post("/admin/rounds/round-1/bidding/close", headers=admin_headers).status_code == 409
    assert client.post("/admin/rounds/round-1/assign-winners", headers=admin_headers).status_code == 409
    assert client.post(f"/admin/auction/{problem.id}/finalize", headers=admin_headers).status_code == 409
    ended = client.post("/admin/rounds/round-1/end", headers=admin_headers)
    assert ended.status_code == 200 and ended.json()["unassigned_team_count"] == 1


def test_manual_wildcard_end_is_admin_only_and_preserves_incomplete_selection(client, admin_headers, display_headers, db):
    participant, team = _participant(db, name="Wildcard", email="wildcard@end.test")
    login = client.post("/login", data={"username": participant.email, "password": "Participant@123"})
    participant_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    control = RoundControl(round_type="WILDCARD", status="PROBLEM_SELECTION", applications_open=False, slot_count=1, current_selection_rank=1)
    db.add(control)
    db.add(Wildcard(team_id=team.id, status="qualified", rank=1, winning_bid=200, coins_paid=200))
    game = db.query(GameConfig).one()
    game.state = "WILDCARD_SELECTION"
    db.commit()

    assert client.post("/admin/rounds/wildcard/end").status_code == 401
    assert client.post("/admin/rounds/wildcard/end", headers=participant_headers).status_code == 403
    assert client.post("/admin/rounds/wildcard/end", headers=display_headers).status_code == 403
    response = client.post("/admin/rounds/wildcard/end", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["ended"] is True
    db.refresh(control)
    wildcard = db.query(Wildcard).filter(Wildcard.team_id == team.id).one()
    assert control.status == "COMPLETE" and control.ended is True
    assert wildcard.status == "qualified" and wildcard.problem_id is None
    assert client.post("/admin/rounds/wildcard/end", headers=admin_headers).status_code == 200
