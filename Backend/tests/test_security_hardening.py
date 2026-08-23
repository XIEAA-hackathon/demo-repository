import pytest
from app.models.models import EventConfig, GameConfig, ProblemStatement, Team, User, Wildcard, Bid
from app.core.security import get_password_hash

def _make_problem(db, ps_number="PS-01", round_no=1):
    ps = ProblemStatement(ps_number=ps_number, title=f"Title {ps_number}", description="desc", round=round_no)
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return ps

def _setup_imported_team(client, admin_headers, csv_bytes):
    # Import registration data to create approved team & leader
    resp = client.post(
        "/admin/registration/import/preview",
        files={"file": ("teams.csv", csv_bytes, "text/csv")},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    import_id = resp.json()["import_id"]

    confirm = client.post(
        "/admin/registration/import/confirm",
        json={"import_id": import_id},
        headers=admin_headers,
    )
    assert confirm.status_code == 200, confirm.text
    return confirm.json()["credentials"]

def test_negative_and_zero_bid_validation(client, admin_headers, csv_bytes, login_headers_factory, db):
    creds = _setup_imported_team(client, admin_headers, csv_bytes)
    leader_cred = next(c for c in creds if c["team_name"] == "Team Alpha" and c["role"] == "leader")
    leader_headers = login_headers_factory(leader_cred["username"], leader_cred["temporary_password"])

    # Advance state to ROUND1_BIDDING
    client.post("/admin/round/start-bidding", headers=admin_headers)

    # Create problem statement
    ps = _make_problem(db, ps_number="PS-101", round_no=1)

    # Zero bid test -> 422
    resp_zero = client.post("/bid", json={"ps_id": ps.id, "amount": 0}, headers=leader_headers)
    assert resp_zero.status_code == 422, resp_zero.text

    # Negative bid test -> 422
    resp_neg = client.post("/bid", json={"ps_id": ps.id, "amount": -50}, headers=leader_headers)
    assert resp_neg.status_code == 422, resp_neg.text

def test_bid_cooldown_enforcement(client, admin_headers, csv_bytes, login_headers_factory, db):
    creds = _setup_imported_team(client, admin_headers, csv_bytes)
    leader_cred = next(c for c in creds if c["team_name"] == "Team Alpha" and c["role"] == "leader")
    leader_headers = login_headers_factory(leader_cred["username"], leader_cred["temporary_password"])

    # Set 5s cooldown
    client.put("/admin/config", json={"bid_cooldown_seconds": 5}, headers=admin_headers)
    client.post("/admin/round/start-bidding", headers=admin_headers)

    ps = _make_problem(db, ps_number="PS-102", round_no=1)

    # First bid -> 200 OK
    b1 = client.post("/bid", json={"ps_id": ps.id, "amount": 100}, headers=leader_headers)
    assert b1.status_code == 200, b1.text

    # Immediate second bid -> 400 Cooldown
    b2 = client.post("/bid", json={"ps_id": ps.id, "amount": 105}, headers=leader_headers)
    assert b2.status_code == 400, b2.text
    assert "Please wait" in b2.json()["detail"]

def test_single_active_session_invalidation(client, db):
    # Setup user
    password = "secret-password"
    user = User(name="User", email="single@test.com", password_hash=get_password_hash(password), role="admin")
    db.add(user)
    db.commit()

    # Login 1 (Device 1)
    login1 = client.post("/login", data={"username": "single@test.com", "password": password})
    assert login1.status_code == 200
    token1 = login1.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    # Verify device 1 works
    me1 = client.get("/admin/config", headers=headers1)
    assert me1.status_code == 200

    # Login 2 (Device 2) -> should update session_id in DB
    login2 = client.post("/login", data={"username": "single@test.com", "password": password})
    assert login2.status_code == 200

    # Device 1 token should now be invalidated
    me1_after = client.get("/admin/config", headers=headers1)
    assert me1_after.status_code == 401
    assert "Session expired" in me1_after.json()["detail"]

def test_file_upload_type_restriction(client, admin_headers):
    # Invalid extension
    bad_file = ("script.exe", b"malicious binary content", "application/octet-stream")
    resp = client.post(
        "/admin/registration/import/preview",
        files={"file": bad_file},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "Invalid file type" in resp.json()["detail"]

def test_wildcard_rank_order_selection(client, admin_headers, csv_bytes, login_headers_factory, db):
    creds = _setup_imported_team(client, admin_headers, csv_bytes)
    alpha_leader = login_headers_factory(
        next(c for c in creds if c["team_name"] == "Team Alpha" and c["role"] == "leader")["username"],
        next(c for c in creds if c["team_name"] == "Team Alpha" and c["role"] == "leader")["temporary_password"],
    )
    beta_leader = login_headers_factory(
        next(c for c in creds if c["team_name"] == "Team Beta" and c["role"] == "leader")["username"],
        next(c for c in creds if c["team_name"] == "Team Beta" and c["role"] == "leader")["temporary_password"],
    )

    # Setup R1 problems & assign original problems to Alpha and Beta
    ps1 = _make_problem(db, ps_number="PS-R1-A", round_no=1)
    ps2 = _make_problem(db, ps_number="PS-R1-B", round_no=1)
    ps1.status = "allocated"
    ps2.status = "allocated"
    db.commit()

    team_alpha = db.query(Team).filter(Team.team_name == "Team Alpha").first()
    team_beta = db.query(Team).filter(Team.team_name == "Team Beta").first()
    team_alpha.ps_id = ps1.id
    team_beta.ps_id = ps2.id

    # Create Wildcard problem (round 2)
    w_ps1 = _make_problem(db, ps_number="PS-W1", round_no=2)
    w_ps2 = _make_problem(db, ps_number="PS-W2", round_no=2)

    # Move to WILDCARD_BIDDING
    config = db.query(GameConfig).first()
    config.state = "WILDCARD_BIDDING"
    config.current_round = 2
    db.commit()

    # Disable cooldown for wildcard test
    client.put("/admin/config", json={"bid_cooldown_seconds": 0}, headers=admin_headers)

    # Team Alpha bids 300 (Rank #1)
    b_alpha = client.post(f"/wildcard/bid?ps_id={w_ps1.id}&amount=300", headers=alpha_leader)
    assert b_alpha.status_code == 200, b_alpha.text
    # Team Beta bids 200 (Rank #2)
    b_beta = client.post(f"/wildcard/bid?ps_id={w_ps1.id}&amount=200", headers=beta_leader)
    assert b_beta.status_code == 200, b_beta.text

    # Admin finalizes wildcard round
    fin = client.post("/admin/wildcard/finalize", headers=admin_headers)
    assert fin.status_code == 200, fin.text

    # Team Beta (Rank #2) attempts to select problem before Team Alpha (Rank #1)
    beta_select = client.post(f"/wildcard/select/{w_ps1.id}", headers=beta_leader)
    assert beta_select.status_code == 400
    assert "higher-ranked wildcard winner must select" in beta_select.json()["detail"]

    # Team Alpha (Rank #1) selects -> 200 OK
    alpha_select = client.post(f"/wildcard/select/{w_ps1.id}", headers=alpha_leader)
    assert alpha_select.status_code == 200

    # Now Team Beta (Rank #2) selects remaining problem w_ps2 -> 200 OK
    beta_select2 = client.post(f"/wildcard/select/{w_ps2.id}", headers=beta_leader)
    assert beta_select2.status_code == 200
