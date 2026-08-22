from app.core.security import verify_password
from app.models.models import Bid, EventConfig, GameConfig, Member, ProblemStatement, RoundControl, Submission, Team, User, Wildcard, WildcardSelectionPool


def activate_round_one_problem(db, problem):
    problem.status = "current"
    db.add(RoundControl(round_type="ROUND1", current_problem_id=problem.id, status="BIDDING"))


def team_payload(name="Alpha", leader_email="alice@example.com"):
    return {
        "team_name": name,
        "leader": {"name": "Alice", "email": leader_email},
        "members": [
            {"name": "Bob", "email": "bob@example.com"},
            {"name": "Charlie", "email": None},
        ],
    }


def create_team(client, admin_headers, payload=None):
    response = client.post(
        "/admin/teams/credentials",
        headers=admin_headers,
        json=payload or team_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client, login_id, password):
    response = client.post("/login", data={"username": login_id, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def login_token(client, login_id, password):
    response = client.post("/login", data={"username": login_id, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def credentials_by_role(result):
    leader = next(item for item in result["credentials"] if item["role"] == "leader")
    members = [item for item in result["credentials"] if item["role"] == "member"]
    return leader, members


def test_admin_generates_individual_accounts_and_shared_team_wallet(client, admin_headers, db):
    result = create_team(client, admin_headers)
    assert result["team_name"] == "Alpha"
    assert result["member_count"] == 3
    assert len(result["credentials"]) == 3
    assert len({row["username"].lower() for row in result["credentials"]}) == 3

    db.expire_all()
    team = db.query(Team).filter(Team.team_name == "Alpha").one()
    assert db.query(Team).count() == 1
    assert db.query(Member).filter(Member.team_id == team.id).count() == 2
    accounts = db.query(User).filter(User.team_id == team.id).all()
    assert len(accounts) == 3
    assert len([account for account in accounts if account.role == "leader"]) == 1
    assert team.leader_id == next(account.id for account in accounts if account.role == "leader")

    dashboards = []
    for credential in result["credentials"]:
        account = db.query(User).filter(User.id == credential["user_id"]).one()
        assert account.password_hash != credential["temporary_password"]
        assert verify_password(credential["temporary_password"], account.password_hash)
        headers = login(client, credential["username"], credential["temporary_password"])
        dashboard = client.get("/participant/dashboard", headers=headers)
        assert dashboard.status_code == 200, dashboard.text
        dashboards.append(dashboard.json())

    assert len(dashboards[0]["team"]["members"]) == 3
    assert {dashboard["wallet"]["balance"] for dashboard in dashboards} == {1000}
    assert sum(bool(dashboard["isLeader"]) for dashboard in dashboards) == 1


def test_duplicate_team_and_account_are_rejected(client, admin_headers):
    create_team(client, admin_headers)
    duplicate_team = client.post("/admin/teams/credentials", headers=admin_headers, json=team_payload())
    assert duplicate_team.status_code == 409
    assert duplicate_team.json()["detail"] == "TEAM ALREADY EXISTS"

    duplicate_account = team_payload(name="Beta", leader_email="alice@example.com")
    response = client.post("/admin/teams/credentials", headers=admin_headers, json=duplicate_account)
    assert response.status_code == 409
    assert "ACCOUNT ALREADY EXISTS" in response.json()["detail"]


def test_admin_can_reset_password_once_without_storing_plaintext(client, admin_headers, db):
    result = create_team(client, admin_headers)
    _, members = credentials_by_role(result)
    member = members[0]
    assert client.post("/login", data={"username": member["username"], "password": member["temporary_password"]}).status_code == 200

    existing = client.get(f"/admin/teams/{result['team_id']}/credentials", headers=admin_headers)
    assert existing.status_code == 200, existing.text
    assert len(existing.json()["credentials"]) == 3
    assert all(item["temporary_password"] == "" for item in existing.json()["credentials"])

    reset = client.post(
        f"/admin/participant-accounts/{member['user_id']}/reset-password",
        headers=admin_headers,
    )
    assert reset.status_code == 200, reset.text
    updated = reset.json()
    assert updated["temporary_password"] != member["temporary_password"]
    assert client.post("/login", data={"username": member["username"], "password": member["temporary_password"]}).status_code == 401
    assert client.post("/login", data={"username": member["username"], "password": updated["temporary_password"]}).status_code == 200
    db.expire_all()
    account = db.query(User).filter(User.id == member["user_id"]).one()
    assert verify_password(updated["temporary_password"], account.password_hash)


def test_teammate_is_spectator_and_leader_controls_all_mutations(client, admin_headers, db):
    result = create_team(client, admin_headers)
    leader_credential, members = credentials_by_role(result)
    leader_headers = login(client, leader_credential["username"], leader_credential["temporary_password"])
    member_headers = login(client, members[0]["username"], members[0]["temporary_password"])

    db.expire_all()
    team = db.query(Team).filter(Team.id == result["team_id"]).one()
    round_one = ProblemStatement(ps_number="PS-01", title="Round one", description="desc", round=1, status="visible")
    bonus = ProblemStatement(ps_number="WC-01", title="Bonus", description="desc", round=2, status="visible")
    db.add_all([round_one, bonus])
    db.flush()
    activate_round_one_problem(db, round_one)
    config = db.query(GameConfig).first()
    config.state = "ROUND1_BIDDING"
    config.current_round = 1
    db.commit()

    assert client.get("/participant/dashboard", headers=member_headers).status_code == 200
    assert client.get("/participant/leaderboard", headers=member_headers).status_code == 200
    assert client.post("/bid", headers=member_headers, json={"ps_id": round_one.id, "amount": 100}).status_code == 403
    leader_bid = client.post("/bid", headers=leader_headers, json={"ps_id": round_one.id, "amount": 100})
    assert leader_bid.status_code == 200, leader_bid.text
    member_dashboard = client.get("/participant/dashboard", headers=member_headers).json()
    assert member_dashboard["currentBid"]["amount"] == 100
    assert member_dashboard["isLeader"] is False

    config.state = "WILDCARD_APPLICATION"
    from datetime import datetime, timedelta
    wildcard_control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    round_one_control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one()
    round_one_control.ended = True
    wildcard_control.status = "APPLICATIONS_OPEN"
    wildcard_control.applications_open = True
    config.auction_timer_end = datetime.utcnow() + timedelta(seconds=30)
    db.commit()
    assert client.post("/wildcard/apply", headers=member_headers).status_code == 403
    assert client.post("/wildcard/apply", headers=leader_headers).status_code == 200

    config.state = "WILDCARD_BIDDING"
    wildcard_control.status = "BIDDING_OPEN"
    wildcard_control.slot_count = 1
    wildcard_control.applications_open = False
    bonus.status = "current"
    db.commit()
    assert client.post("/wildcard/bid?amount=150", headers=member_headers).status_code == 403
    assert client.post("/wildcard/bid?amount=150", headers=leader_headers).status_code == 200

    team.ps_id = round_one.id
    team.round1_problem_id = round_one.id
    wildcard = db.query(Wildcard).filter(Wildcard.team_id == team.id).one()
    wildcard.status = "qualified"
    wildcard.rank = 1
    wildcard.winning_bid = 150
    wildcard_control.status = "PROBLEM_SELECTION"
    bonus.status = "visible"
    config.state = "WILDCARD_SELECTION"
    db.add(WildcardSelectionPool(position=1, problem_id=bonus.id))
    db.commit()
    assert client.post(f"/wildcard/select/{bonus.id}", headers=member_headers).status_code == 403
    assert client.post(f"/wildcard/select/{bonus.id}", headers=leader_headers).status_code == 200

    submission = {"repository_url": "https://github.com/example/alpha"}
    db.query(EventConfig).first().submissions_open = True
    db.commit()
    assert client.post("/submissions/me", headers=member_headers, json=submission).status_code == 403
    assert client.post("/submissions/me", headers=leader_headers, json=submission).status_code == 201
    assert db.query(Submission).filter(Submission.team_id == team.id).count() == 1


def test_cross_team_id_injection_cannot_redirect_a_leaders_bid(client, admin_headers, db):
    alpha = create_team(client, admin_headers)
    beta_payload = {
        "team_name": "Beta",
        "leader": {"name": "Bea", "email": "bea@example.com"},
        "members": [{"name": "Ben", "email": "ben@example.com"}],
    }
    beta = create_team(client, admin_headers, beta_payload)
    alpha_leader, _ = credentials_by_role(alpha)
    headers = login(client, alpha_leader["username"], alpha_leader["temporary_password"])

    problem = ProblemStatement(ps_number="PS-X", title="Cross-team", description="desc", round=1, status="visible")
    db.add(problem)
    db.flush()
    activate_round_one_problem(db, problem)
    config = db.query(GameConfig).first()
    config.state = "ROUND1_BIDDING"
    config.current_round = 1
    db.commit()
    db.refresh(problem)

    response = client.post(
        "/bid",
        headers=headers,
        json={"ps_id": problem.id, "amount": 100, "team_id": beta["team_id"]},
    )
    assert response.status_code == 200, response.text
    bid = db.query(Bid).one()
    assert bid.team_id == alpha["team_id"]
    assert bid.team_id != beta["team_id"]


def test_teammate_websocket_receives_leaders_live_bid(client, admin_headers, db):
    result = create_team(client, admin_headers)
    leader, members = credentials_by_role(result)
    leader_headers = login(client, leader["username"], leader["temporary_password"])
    member_token = login_token(client, members[0]["username"], members[0]["temporary_password"])

    problem = ProblemStatement(ps_number="PS-LIVE", title="Live bid", description="desc", round=1, status="visible")
    db.add(problem)
    db.flush()
    activate_round_one_problem(db, problem)
    config = db.query(GameConfig).first()
    config.state = "ROUND1_BIDDING"
    config.current_round = 1
    db.commit()
    db.refresh(problem)

    with client.websocket_connect(f"/ws/auction?token={member_token}") as socket:
        snapshot = socket.receive_json()
        assert snapshot["type"] == "event_snapshot"
        assert snapshot["payload"]["identity"]["role"] == "member"

        response = client.post("/bid", headers=leader_headers, json={"ps_id": problem.id, "amount": 420})
        assert response.status_code == 200, response.text
        update = socket.receive_json()
        assert update["type"] == "bid_updated"
        assert update["payload"]["team_id"] == result["team_id"]
        assert update["payload"]["amount"] == 420
