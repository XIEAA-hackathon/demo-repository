import csv
import io

from app.models.models import Bid, GameConfig, ProblemStatement, Team, User


SOURCE = (
    "Team Name,Leader Name,Leader Email,Member 1 Name,Member 1 Email\n"
    "Password Team,Test Leader,leader.test@example.com,Test Member,member.test@example.com\n"
).encode()


def _login(client, login_id: str, password: str):
    return client.post("/login", data={"username": login_id, "password": password})


def _set_password(client, admin_headers, user_id: int, password: str):
    return client.put(
        f"/admin/registration/participant-accounts/{user_id}/password",
        headers=admin_headers,
        json={"new_password": password, "confirm_password": password},
    )


def test_manual_password_lifecycle_and_event_reset_preserves_hash(
    client, admin_headers, display_headers, db,
):
    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("participants.csv", SOURCE, "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    summary = imported.json()
    assert summary["leaders_created"] == 1
    assert summary["participant_accounts_created"] == 1

    account_sheet = client.get(
        f"/admin/registration/import/download/{summary['download_token']}",
        headers=admin_headers,
    )
    row = next(csv.DictReader(io.StringIO(account_sheet.content.decode("utf-8-sig"))))
    assert row["Leader Login Email"] == "leader.test@example.com"
    assert row["Credential Status"] == "PASSWORD NOT SET"
    assert "Leader Password" not in row
    assert "temporary_password" not in account_sheet.text.lower()

    accounts_response = client.get("/admin/registration/participant-accounts", headers=admin_headers)
    assert accounts_response.status_code == 200
    accounts = {account["login_id"]: account for account in accounts_response.json()["accounts"]}
    assert set(accounts) == {"leader.test@example.com", "member.test@example.com"}
    assert all(account["credential_status"] == "NOT_SET" for account in accounts.values())
    leader = accounts["leader.test@example.com"]
    member = accounts["member.test@example.com"]
    assert _login(client, leader["login_id"], "OldPassword@123").status_code == 401

    assert client.put(
        f"/admin/registration/participant-accounts/{leader['user_id']}/password",
        json={"new_password": "OldPassword@123", "confirm_password": "OldPassword@123"},
    ).status_code == 401
    assert _set_password(client, admin_headers, leader["user_id"], "OldPassword@123").status_code == 200
    old_login = _login(client, leader["login_id"], "OldPassword@123")
    assert old_login.status_code == 200
    participant_headers = {"Authorization": f"Bearer {old_login.json()['access_token']}"}
    assert client.put(
        f"/admin/registration/participant-accounts/{member['user_id']}/password",
        headers=participant_headers,
        json={"new_password": "MemberPassword@123", "confirm_password": "MemberPassword@123"},
    ).status_code == 403
    assert client.put(
        f"/admin/registration/participant-accounts/{member['user_id']}/password",
        headers=display_headers,
        json={"new_password": "MemberPassword@123", "confirm_password": "MemberPassword@123"},
    ).status_code == 403

    changed = _set_password(client, admin_headers, leader["user_id"], "NewPassword@456")
    assert changed.status_code == 200, changed.text
    assert client.get("/participant/dashboard", headers=participant_headers).status_code == 401
    assert _login(client, leader["login_id"], "OldPassword@123").status_code == 401
    new_login = _login(client, leader["login_id"], "NewPassword@456")
    assert new_login.status_code == 200
    current_headers = {"Authorization": f"Bearer {new_login.json()['access_token']}"}

    db.expire_all()
    user_before = db.query(User).filter(User.email == leader["login_id"]).one()
    team_before = db.query(Team).filter(Team.id == user_before.team_id).one()
    user_id = user_before.id
    team_id = team_before.id
    hash_before = user_before.password_hash
    problem = ProblemStatement(ps_number="RESET-R1", title="Reset", description="Reset", round=1, status="current")
    db.add(problem)
    db.flush()
    team_before.ps_id = problem.id
    team_before.round1_problem_id = problem.id
    db.add(Bid(team_id=team_id, ps_id=problem.id, amount=100, round=1))
    db.query(GameConfig).one().state = "ROUND1_BIDDING"
    db.commit()

    reset_event = client.post(
        "/admin/event-data/reset",
        headers=admin_headers,
        json={"confirmation": "RESET EVENT"},
    )
    assert reset_event.status_code == 200, reset_event.text
    assert reset_event.json()["deleted"]["participant_users"] == 0
    assert reset_event.json()["deleted"]["teams"] == 0
    db.expire_all()
    user_after = db.query(User).filter(User.id == user_id).one()
    team_after = db.query(Team).filter(Team.id == team_id).one()
    assert user_after.password_hash == hash_before
    assert user_after.credentials_active is True
    assert user_after.team_id == team_id and team_after.leader_id == user_id
    assert db.query(GameConfig).one().state == "WAITING"
    assert db.query(Bid).count() == 0
    assert client.get("/participant/dashboard", headers=current_headers).status_code == 200
    assert _login(client, leader["login_id"], "OldPassword@123").status_code == 401
    assert _login(client, leader["login_id"], "NewPassword@456").status_code == 200

    repeated = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("participants.csv", SOURCE, "text/csv")},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["teams_created"] == 0
    assert repeated.json()["leaders_created"] == 0
    db.expire_all()
    assert db.query(User).filter(User.email == leader["login_id"]).count() == 1
    assert db.query(User).filter(User.email == leader["login_id"]).one().password_hash == hash_before

    game = db.query(GameConfig).one()
    game.state = "SUBMISSION"
    db.commit()
    reset_credentials = client.post(
        "/admin/registration/credentials/reset",
        headers=admin_headers,
        json={"confirmation": "RESET CREDENTIALS"},
    )
    assert reset_credentials.status_code == 200, reset_credentials.text
    assert reset_credentials.json()["event_state"] == "SUBMISSION"
    assert reset_credentials.json()["reset"]["participant_accounts"] == 2
    assert _login(client, leader["login_id"], "OldPassword@123").status_code == 401
    assert _login(client, leader["login_id"], "NewPassword@456").status_code == 401
    account_after_reset = next(
        account for account in client.get(
            "/admin/registration/participant-accounts", headers=admin_headers,
        ).json()["accounts"] if account["user_id"] == user_id
    )
    assert account_after_reset["credential_status"] == "NOT_SET"

    assert _set_password(client, admin_headers, user_id, "ThirdPassword@789").status_code == 200
    assert _login(client, leader["login_id"], "ThirdPassword@789").status_code == 200
    assert db.query(GameConfig).one().state == "SUBMISSION"
