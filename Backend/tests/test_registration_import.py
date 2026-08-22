"""Registration import: teams/members/leaders, idempotency, credentials."""
import csv
import io
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.core.security import verify_password
from app.models.models import Team, User, Member, WalletTransaction


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
