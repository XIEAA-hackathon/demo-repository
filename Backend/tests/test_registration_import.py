"""Registration import: teams/members/leaders, idempotency, credentials."""
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
    assert data["accounts_created"] == 5  # 3 leaders + 2 member emails (Aarav, Charlie)

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
    assert len(confirm["credentials"]) == 5  # 3 leaders + 2 members with emails
    assert all(c["temporary_password"] for c in confirm["credentials"])
    assert all(c["username"] == c["email"] for c in confirm["credentials"])


def test_import_requires_admin(client, csv_bytes):
    response = client.post(
        "/admin/registration/import/preview",
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code in (401, 403)