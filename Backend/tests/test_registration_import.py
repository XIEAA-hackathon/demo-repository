"""Registration import: teams/members/leaders, idempotency, credentials."""
import csv
import io
from datetime import datetime, timedelta, timezone
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.core.config import settings
from app.core.security import verify_password
from app.models.models import Bid, GameConfig, Member, ProblemStatement, RoundControl, Team, User, WalletTransaction
from app.services.demo_seed import provision_demo_accounts


def test_import_preview_detects_teams_and_leaders(client, admin_headers, csv_bytes):
    response = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["teams_detected"] == 3
    assert data["leaders_detected"] == 3
    assert data["members_detected"] == 4  # Aarav+Diya (alpha), Charlie+Rohan (beta)



def test_import_preview_does_not_persist_data(client, admin_headers, csv_bytes, db):
    response = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 200
    assert db.query(Team).count() == 0
    assert db.query(User).count() == 1  # only admin


def test_confirm_import_creates_teams_members_leader_and_wallets(client, admin_headers, csv_bytes, db):
    preview = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    ).json()
    import_id = preview["import_id"]

    response = client.post("/admin/registration/import/confirm", headers=admin_headers, json={"import_id": import_id})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["teams_created"] == 3
    assert data["accounts_created"] == 7  # 3 leaders + all 4 teammates

    team_alpha = db.query(Team).filter(Team.team_name == "Team Alpha").first()
    assert team_alpha is not None
    assert team_alpha.is_approved is True
    assert team_alpha.coins == 1000  # EventConfig.starting_coins

    leader_email = db.query(User).filter(User.email == "alice@test.com").first()
    assert leader_email is not None
    assert leader_email.role == "leader"
    assert team_alpha.leader_id == leader_email.id

    member = db.query(Member).filter(Member.team_id == team_alpha.id, Member.member_name == "Aarav").first()
    assert member is not None
    assert member.email == "aarav@test.com"

    # member account created for Aarav
    aarav_user = db.query(User).filter(User.email == "aarav@test.com").first()
    assert aarav_user is not None
    assert aarav_user.role == "member"
    assert aarav_user.team_id == team_alpha.id

    # teammates without email receive a stable readable participant ID
    diya_user = db.query(User).filter(User.email == f"BTB-T{team_alpha.id:03d}-M02").first()
    assert diya_user is not None
    assert diya_user.name == "Diya"
    assert diya_user.team_id == team_alpha.id

    # wallet ledger entry
    tx = db.query(WalletTransaction).filter(WalletTransaction.team_id == team_alpha.id).first()
    assert tx is not None
    assert tx.transaction_type == "INITIAL_ALLOCATION"
    assert tx.amount == 1000


def test_duplicate_import_does_not_create_duplicates(client, admin_headers, csv_bytes, db):
    preview = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    ).json()
    first = client.post("/admin/registration/import/confirm", headers=admin_headers, json={"import_id": preview["import_id"]})
    assert first.status_code == 200

    # second import: same file uploaded again
    preview2 = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    ).json()
    assert all(row["status"] in ("update", "duplicate") for row in preview2["rows"])

    second = client.post("/admin/registration/import/confirm", headers=admin_headers, json={"import_id": preview2["import_id"]})
    assert second.status_code == 200
    assert second.json()["teams_created"] == 0
    assert second.json()["accounts_created"] == 0

    assert db.query(Team).count() == 3
    assert db.query(User).filter(User.role == "leader").count() == 3


def test_import_rejects_unsupported_file(client, admin_headers):
    response = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("data.txt", b"not a spreadsheet", "text/plain")},
    )
    assert response.status_code == 400


def test_import_credential_export(client, admin_headers, csv_bytes):
    preview = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    ).json()
    confirm = client.post("/admin/registration/import/confirm", headers=admin_headers, json={"import_id": preview["import_id"]}).json()
    assert len(confirm["credentials"]) == 7  # 3 leaders + every teammate
    assert all(c["temporary_password"] for c in confirm["credentials"])
    assert all(c["participant_id"] == c["username"] for c in confirm["credentials"])
    assert all(c["username"] == c["email"] for c in confirm["credentials"] if c["email"])
    assert any(c["username"].startswith("BTB-T") for c in confirm["credentials"] if not c["email"])


def test_import_requires_admin(client, csv_bytes):
    response = client.post(
        "/admin/registration/import/preview",
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code in (401, 403)


def _registration_xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Registrations"
    sheet.append([
        "Team Name", "Leader Name", "Leader Email", "Member 1 Name",
        "Member 1 Email", "Member 2 Name", "Member 2 Email", "Organizer Notes",
    ])
    sheet.append(["Team Alpha", "Leader Alpha", "alpha@example.com", "A One", "a.one@example.com", "A Two", "a.two@example.com", "Keep alpha note"])
    sheet.append(["Team Beta", "Leader Beta", "beta@example.com", "B One", "b.one@example.com", "B Two", "b.two@example.com", "Keep beta note"])
    sheet["A1"].font = sheet["A1"].font.copy(bold=True)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_xlsx_import_returns_preserved_one_time_leader_credentials(client, admin_headers, db):
    source = _registration_xlsx()
    response = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.xlsx", source, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary == {
        **summary,
        "teams_processed": 2,
        "teams_created": 2,
        "teams_updated": 0,
        "leaders_created": 2,
        "existing_leaders": 0,
        "members_imported": 4,
        "rows_failed": 0,
        "errors": [],
    }

    download = client.get(
        f"/admin/registration/import/download/{summary['download_token']}",
        headers=admin_headers,
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    workbook = load_workbook(BytesIO(download.content), data_only=True)
    sheet = workbook.active
    headers = [cell.value for cell in sheet[1]]
    assert headers == [
        "Team Name", "Leader Name", "Leader Email", "Member 1 Name",
        "Member 1 Email", "Member 2 Name", "Member 2 Email", "Organizer Notes",
        "Leader Login Email", "Leader Password",
    ]
    assert sheet["H2"].value == "Keep alpha note"
    assert sheet["H3"].value == "Keep beta note"
    assert sheet["I2"].value == "alpha@example.com"
    assert sheet["I3"].value == "beta@example.com"
    assert sheet["J2"].value and sheet["J2"].value != "EXISTING ACCOUNT"
    assert sheet["J3"].value and sheet["J3"].value != "EXISTING ACCOUNT"
    alpha_password = sheet["J2"].value
    workbook.close()

    alpha = db.query(User).filter(User.email == "alpha@example.com").one()
    assert alpha.role == "leader"
    assert verify_password(alpha_password, alpha.password_hash)
    assert alpha.password_hash != alpha_password
    assert client.post("/login", data={"username": alpha.email, "password": alpha_password}).status_code == 200
    assert db.query(Member).count() == 4
    assert db.query(User).filter(User.role == "member").count() == 0
    assert client.get(
        f"/admin/registration/import/download/{summary['download_token']}",
        headers=admin_headers,
    ).status_code == 404

    original_hash = alpha.password_hash
    second = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.xlsx", source, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    assert second["teams_created"] == 0
    assert second["teams_updated"] == 2
    assert second["leaders_created"] == 0
    assert second["existing_leaders"] == 2
    assert db.query(Team).count() == 2
    assert db.query(User).filter(User.role == "leader").count() == 2
    assert db.query(User).filter(User.email == "alpha@example.com").one().password_hash == original_hash

    second_download = client.get(
        f"/admin/registration/import/download/{second['download_token']}",
        headers=admin_headers,
    )
    workbook = load_workbook(BytesIO(second_download.content), data_only=True)
    assert workbook.active["J2"].value == "EXISTING ACCOUNT"
    assert workbook.active["J3"].value == "EXISTING ACCOUNT"
    workbook.close()


def test_registration_import_reports_duplicate_rows_and_requires_admin(client, admin_headers):
    csv_content = (
        "Team Name,Leader Name,Leader Email,Member 1 Name,Member 1 Email\n"
        "Team Alpha,Alpha,alpha@example.com,Member A,member@example.com\n"
        "Team Alpha,Beta,beta@example.com,Member B,other@example.com\n"
        "Team Gamma,Gamma,gamma@example.com,Member C,member@example.com\n"
    ).encode()
    response = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 200
    summary = response.json()
    assert summary["teams_processed"] == 1
    assert summary["rows_failed"] == 2
    assert any("already appears" in error["message"] for error in summary["errors"])
    assert any("already used" in error["message"] for error in summary["errors"])

    unauthorized = client.post(
        "/admin/registration/import",
        files={"file": ("registrations.csv", csv_content, "text/csv")},
    )
    assert unauthorized.status_code == 401


def test_demo_csv_is_importer_compatible_and_returns_csv_credentials(client, admin_headers, db):
    demo = client.get("/admin/registration/demo.csv", headers=admin_headers)
    assert demo.status_code == 200
    source_rows = list(csv.reader(io.StringIO(demo.content.decode("utf-8-sig"))))
    assert source_rows[0] == [
        "Team Name", "Leader Name", "Leader Email", "Member 1 Name",
        "Member 1 Email", "Member 2 Name", "Member 2 Email",
    ]

    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("demo-registration.csv", demo.content, "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    summary = imported.json()
    assert summary["teams_created"] == 2
    assert summary["leaders_created"] == 2
    assert summary["download_filename"].endswith(".csv")

    downloaded = client.get(
        f"/admin/registration/import/download/{summary['download_token']}",
        headers=admin_headers,
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("text/csv")
    output_rows = list(csv.reader(io.StringIO(downloaded.content.decode("utf-8-sig"))))
    assert output_rows[0] == [*source_rows[0], "Leader Login Email", "Leader Password"]
    assert [row[:7] for row in output_rows[1:]] == source_rows[1:]
    assert output_rows[1][-2] == "alice@example.com"
    assert output_rows[1][-1] and output_rows[1][-1] != "EXISTING ACCOUNT"
    alice_password = output_rows[1][-1]
    alice = db.query(User).filter(User.email == "alice@example.com").one()
    assert verify_password(alice_password, alice.password_hash)
    original_hash = alice.password_hash

    repeated = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("demo-registration.csv", demo.content, "text/csv")},
    ).json()
    assert repeated["teams_created"] == 0
    assert repeated["leaders_created"] == 0
    assert db.query(User).filter(User.email == "alice@example.com").one().password_hash == original_hash
    repeated_download = client.get(
        f"/admin/registration/import/download/{repeated['download_token']}",
        headers=admin_headers,
    )
    repeated_rows = list(csv.reader(io.StringIO(repeated_download.content.decode("utf-8-sig"))))
    assert repeated_rows[1][-1] == "EXISTING ACCOUNT"


def test_registration_credential_reset_allows_fresh_passwords_and_preserves_system_accounts(client, admin_headers, db):
    provision_demo_accounts(db)
    db.commit()
    source = (
        "Team Name,Leader Name,Leader Email,Member 1 Name,Member 1 Email\n"
        "Team Alpha,Alpha Leader,alpha@example.com,Alpha Member,member.alpha@example.com\n"
        "Team Beta,Beta Leader,beta@example.com,Beta Member,member.beta@example.com\n"
    ).encode()

    def import_and_download():
        imported = client.post(
            "/admin/registration/import",
            headers=admin_headers,
            files={"file": ("registrations.csv", source, "text/csv")},
        )
        assert imported.status_code == 200, imported.text
        downloaded = client.get(
            f"/admin/registration/import/download/{imported.json()['download_token']}",
            headers=admin_headers,
        )
        assert downloaded.status_code == 200, downloaded.text
        rows = list(csv.DictReader(io.StringIO(downloaded.content.decode("utf-8-sig"))))
        return imported.json(), rows

    first, first_rows = import_and_download()
    assert first["leaders_created"] == 2
    first_passwords = {row["Leader Login Email"]: row["Leader Password"] for row in first_rows}
    assert all(password and password != "EXISTING ACCOUNT" for password in first_passwords.values())
    for email, password in first_passwords.items():
        account = db.query(User).filter(User.email == email).one()
        assert account.password_hash != password
        assert verify_password(password, account.password_hash)
        assert client.post("/login", data={"username": email, "password": password}).status_code == 200

    repeated, repeated_rows = import_and_download()
    assert repeated["leaders_created"] == 0
    assert repeated["existing_leaders"] == 2
    assert all(row["Leader Password"] == "EXISTING ACCOUNT" for row in repeated_rows)
    assert db.query(User).filter(User.email.in_(("alpha@example.com", "beta@example.com"))).count() == 2

    alpha_headers = {
        "Authorization": "Bearer " + client.post(
            "/login",
            data={"username": "alpha@example.com", "password": first_passwords["alpha@example.com"]},
        ).json()["access_token"]
    }
    assert client.post(
        "/admin/registration/credentials/reset",
        json={"confirmation": "RESET CREDENTIALS"},
    ).status_code == 401
    assert client.post(
        "/admin/registration/credentials/reset",
        headers=admin_headers,
        json={"confirmation": "wrong"},
    ).status_code == 422
    assert client.post(
        "/admin/registration/credentials/reset",
        headers=alpha_headers,
        json={"confirmation": "RESET CREDENTIALS"},
    ).status_code == 403

    reset = client.post(
        "/admin/registration/credentials/reset",
        headers=admin_headers,
        json={"confirmation": "RESET CREDENTIALS"},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["deleted"]["participant_accounts"] == 2
    assert reset.json()["deleted"]["teams"] == 2
    assert db.query(User).filter(User.email.in_(("alpha@example.com", "beta@example.com"))).count() == 0
    assert db.query(Team).filter(Team.team_name.in_(("Team Alpha", "Team Beta"))).count() == 0
    assert client.post("/login", data={"username": settings.DEMO_LEADER_EMAIL, "password": settings.DEMO_LEADER_PASSWORD}).status_code == 200
    assert client.post("/login", data={"username": settings.DEMO_ADMIN_EMAIL, "password": settings.DEMO_ADMIN_PASSWORD}).status_code == 200
    assert client.post(
        "/leaderboard/login",
        data={"username": settings.LEADERBOARD_DISPLAY_EMAIL, "password": settings.LEADERBOARD_DISPLAY_PASSWORD},
    ).status_code == 200

    after_reset, after_reset_rows = import_and_download()
    assert after_reset["leaders_created"] == 2
    new_passwords = {row["Leader Login Email"]: row["Leader Password"] for row in after_reset_rows}
    assert all(password and password != "EXISTING ACCOUNT" for password in new_passwords.values())
    assert new_passwords != first_passwords
    for email, password in new_passwords.items():
        assert client.post("/login", data={"username": email, "password": password}).status_code == 200


def test_assignment_export_preserves_xlsx_format_and_original_columns(client, admin_headers):
    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.xlsx", _registration_xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert imported.status_code == 200, imported.text
    exported = client.get("/admin/registration/assignments", headers=admin_headers)
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("application/vnd.openxmlformats")
    workbook = load_workbook(BytesIO(exported.content), data_only=True)
    sheet = workbook.active
    headers = [cell.value for cell in sheet[1]]
    row = {header: sheet.cell(row=2, column=index + 1).value for index, header in enumerate(headers)}
    workbook.close()
    assert row["Organizer Notes"] == "Keep alpha note"
    assert row["Leader Login Email"] == "alpha@example.com"
    assert "Round 1 Problem Number" in headers
    assert "Wildcard Problem Description" in headers
    assert "Final Problem Title" in headers


def test_updated_registration_export_reflects_three_team_round_and_wildcard_assignments(client, admin_headers, db):
    source = (
        "Team Name,Leader Name,Leader Email,Organizer Notes\n"
        "Team A,Leader A,leader.a@example.com,Keep A\n"
        "Team B,Leader B,leader.b@example.com,Keep B\n"
        "Team C,Leader C,leader.c@example.com,Keep C\n"
    ).encode()
    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.csv", source, "text/csv")},
    )
    assert imported.status_code == 200, imported.text

    round_problems = [
        ProblemStatement(ps_number=f"R1-{index}", title=f"Round title {index}", description=f"Round description {index}", round=1, status="allocated")
        for index in range(1, 4)
    ]
    wildcard_problem = ProblemStatement(
        ps_number="WC-5", title="Wildcard title 5", description="Wildcard description 5", round=2, status="allocated",
    )
    db.add_all([*round_problems, wildcard_problem])
    db.flush()
    teams = {team.team_name: team for team in db.query(Team).filter(Team.team_name.in_(("Team A", "Team B", "Team C"))).all()}
    for index, team_name in enumerate(("Team A", "Team B", "Team C")):
        teams[team_name].round1_problem_id = round_problems[index].id
        teams[team_name].ps_id = round_problems[index].id
    teams["Team B"].wildcard_problem_id = wildcard_problem.id
    teams["Team B"].ps_id = wildcard_problem.id
    db.commit()

    exported = client.get("/admin/registration/assignments", headers=admin_headers)
    assert exported.status_code == 200, exported.text
    reader = csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig")))
    rows = {row["Team Name"]: row for row in reader}
    assert reader.fieldnames[:4] == ["Team Name", "Leader Name", "Leader Email", "Organizer Notes"]
    assert [rows[name]["Organizer Notes"] for name in ("Team A", "Team B", "Team C")] == ["Keep A", "Keep B", "Keep C"]

    assert rows["Team A"]["Round 1 Problem Number"] == "R1-1"
    assert rows["Team A"]["Round 1 Problem Title"] == "Round title 1"
    assert rows["Team A"]["Round 1 Problem Description"] == "Round description 1"
    assert rows["Team A"]["Wildcard Problem Number"] == ""
    assert rows["Team A"]["Final Problem Number"] == "R1-1"

    assert rows["Team B"]["Round 1 Problem Number"] == "R1-2"
    assert rows["Team B"]["Round 1 Problem Title"] == "Round title 2"
    assert rows["Team B"]["Wildcard Problem Number"] == "WC-5"
    assert rows["Team B"]["Wildcard Problem Title"] == "Wildcard title 5"
    assert rows["Team B"]["Wildcard Problem Description"] == "Wildcard description 5"
    assert rows["Team B"]["Final Problem Number"] == "WC-5"

    assert rows["Team C"]["Round 1 Problem Number"] == "R1-3"
    assert rows["Team C"]["Round 1 Problem Title"] == "Round title 3"
    assert rows["Team C"]["Round 1 Problem Description"] == "Round description 3"
    assert rows["Team C"]["Wildcard Problem Number"] == ""
    assert rows["Team C"]["Final Problem Number"] == "R1-3"


def test_assignment_export_never_replays_uploaded_plaintext_password(client, admin_headers):
    source = (
        "Team Name,Leader Name,Leader Email,Leader Password\n"
        "Secure Team,Secure Leader,secure@example.com,DoNotReplay123!\n"
    ).encode()
    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.csv", source, "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    exported = client.get("/admin/registration/assignments", headers=admin_headers)
    row = next(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert row["Leader Password"] == "EXISTING ACCOUNT"
    assert "DoNotReplay123!" not in exported.text


def test_registration_credential_reset_clears_active_event_data(client, admin_headers, db):
    provision_demo_accounts(db)
    db.commit()
    source = (
        "Team Name,Leader Name,Leader Email,Member 1 Name,Member 1 Email\n"
        "Team Alpha,Alpha Leader,alpha@example.com,Alpha Member,member.alpha@example.com\n"
    ).encode()
    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.csv", source, "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    team = db.query(Team).filter(Team.team_name == "Team Alpha").one()
    problem = ProblemStatement(ps_number="RESET-PS", title="Active", description="Active", round=1)
    db.add(problem)
    db.flush()
    db.add(Bid(team_id=team.id, ps_id=problem.id, amount=100, round=1))
    game = db.query(GameConfig).first()
    game.state = "ROUND1_BIDDING"
    wildcard_control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").first()
    if wildcard_control is None:
        wildcard_control = RoundControl(round_type="WILDCARD")
        db.add(wildcard_control)
    wildcard_control.status = "PROBLEM_SELECTION"
    wildcard_control.current_selection_rank = 1
    wildcard_control.selection_started_at = datetime.now(timezone.utc)
    wildcard_control.selection_ends_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    wildcard_control.selection_duration_seconds = 30
    db.commit()

    reset = client.post(
        "/admin/registration/credentials/reset",
        headers=admin_headers,
        json={"confirmation": "RESET CREDENTIALS"},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["event_state"] == "WAITING"
    assert db.query(User).filter(User.email == "alpha@example.com").count() == 0
    assert db.query(Team).filter(Team.team_name == "Team Alpha").count() == 0
    assert db.query(Bid).count() == 0
    assert db.query(ProblemStatement).count() == 0
    db.expire_all()
    assert db.query(GameConfig).first().state == "WAITING"
    controls = {control.round_type: control for control in db.query(RoundControl).all()}
    assert controls["ROUND1"].status == "IDLE"
    assert controls["WILDCARD"].status == "NOT_STARTED"
    assert controls["WILDCARD"].current_selection_rank is None
    assert controls["WILDCARD"].selection_started_at is None
    assert controls["WILDCARD"].selection_ends_at is None
    assert client.post("/login", data={"username": settings.DEMO_LEADER_EMAIL, "password": settings.DEMO_LEADER_PASSWORD}).status_code == 200
    assert client.post("/login", data={"username": settings.DEMO_ADMIN_EMAIL, "password": settings.DEMO_ADMIN_PASSWORD}).status_code == 200

    imported_again = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.csv", source, "text/csv")},
    )
    assert imported_again.status_code == 200, imported_again.text
    assert imported_again.json()["leaders_created"] == 1
    credentials = client.get(
        f"/admin/registration/import/download/{imported_again.json()['download_token']}",
        headers=admin_headers,
    )
    row = next(csv.DictReader(io.StringIO(credentials.content.decode("utf-8-sig"))))
    assert row["Leader Password"] not in {"", "EXISTING ACCOUNT"}
    assert client.post(
        "/login",
        data={"username": row["Leader Login Email"], "password": row["Leader Password"]},
    ).status_code == 200
