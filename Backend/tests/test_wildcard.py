"""Wildcard auction + selection, submissions leader-only, EventConfig controls."""
from app.models.models import Team, EventConfig, GameConfig, ProblemStatement, Bid


def _import_creds(client, admin_headers, csv_bytes):
    preview = client.post(
        "/admin/registration/import/preview",
        headers=admin_headers,
        files={"file": ("registrations.csv", csv_bytes, "text/csv")},
    ).json()
    confirm = client.post("/admin/registration/import/confirm", headers=admin_headers, json={"import_id": preview["import_id"]}).json()
    return {c["email"]: c["temporary_password"] for c in confirm["credentials"]}


def _headers(client, email, password):
    login = client.post("/login", data={"username": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _set_state(db, state, round_no=2):
    config = db.query(GameConfig).first()
    config.state = state
    config.current_round = round_no
    db.commit()


def _create_round1_problem(db, ps_number="PS-01"):
    ps = ProblemStatement(ps_number=ps_number, title=f"T-{ps_number}", description="d", round=1)
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return ps


def _create_bonus_problem(db, ps_number="BX-01", status="visible"):
    ps = ProblemStatement(ps_number=ps_number, title=f"B-{ps_number}", description="d", round=2, status=status)
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return ps


def test_wildcard_flow(client, admin_headers, csv_bytes, db):
    creds = _import_creds(client, admin_headers, csv_bytes)
    alpha = _headers(client, "alice@test.com", creds["alice@test.com"])

    # give every team a round-1 problem (required precondition)
    ps1 = _create_round1_problem(db)
    for team in db.query(Team).all():
        team.ps_id = ps1.id
        team.coins = 1000
    db.commit()

    bonus = _create_bonus_problem(db, "BX-01")

    _set_state(db, "WILDCARD_APPLICATION", round_no=2)
    resp = client.post("/wildcard/apply", headers=alpha)
    assert resp.status_code == 200, resp.text

    _set_state(db, "WILDCARD_BIDDING")
    resp = client.post("/wildcard/bid", params={"ps_id": bonus.id, "amount": 200}, headers=alpha)
    assert resp.status_code == 200, resp.text

    # finalize -> winner
    resp = client.post("/admin/wildcard/finalize", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    winners = resp.json()["winners"]
    assert len(winners) == 1
    assert winners[0]["team"] == "Team Alpha"

    # select bonus problem -> must switch problem
    _set_state(db, "WILDCARD_SELECTION")
    resp = client.post(f"/wildcard/select/{bonus.id}", headers=alpha)
    assert resp.status_code == 200, resp.text

    team = db.query(Team).filter(Team.team_name == "Team Alpha").first()
    assert team.ps_id == bonus.id
    assert team.coins == 800  # 1000 - 200 wildcard bid, charged once at selection

    # bonus problem now unavailable to others
    _set_state(db, "WILDCARD_SELECTION")
    beta = _headers(client, "bob@test.com", creds["bob@test.com"])
    # give beta a won wildcard record
    from app.models.models import Wildcard
    db.add(Wildcard(team_id=db.query(Team).filter(Team.team_name == "Team Beta").first().id, status="won"))
    db.commit()
    resp = client.post(f"/wildcard/select/{bonus.id}", headers=beta)
    assert resp.status_code == 400


def test_non_winner_cannot_select_bonus_problem(client, admin_headers, csv_bytes, db):
    creds = _import_creds(client, admin_headers, csv_bytes)
    alpha = _headers(client, "alice@test.com", creds["alice@test.com"])
    ps1 = _create_round1_problem(db)
    for team in db.query(Team).all():
        team.ps_id = ps1.id
        team.coins = 1000
    db.commit()
    bonus = _create_bonus_problem(db, "BX-02")
    _set_state(db, "WILDCARD_SELECTION")
    resp = client.post(f"/wildcard/select/{bonus.id}", headers=alpha)
    assert resp.status_code in (403, 400)


def test_only_leader_can_submit_repository(client, admin_headers, csv_bytes, db):
    creds = _import_creds(client, admin_headers, csv_bytes)
    leader_headers = _headers(client, "alice@test.com", creds["alice@test.com"])
    member_headers = _headers(client, "aarav@test.com", creds["aarav@test.com"])

    ps = _create_round1_problem(db)
    team = db.query(Team).filter(Team.team_name == "Team Alpha").first()
    team.ps_id = ps.id
    db.commit()

    # non-leader cannot submit
    resp = client.post("/submissions/me", json={"repository_url": "https://github.com/alpha/repo"}, headers=member_headers)
    assert resp.status_code == 403

    # leader can submit
    resp = client.post("/submissions/me", json={"repository_url": "https://github.com/alpha/repo"}, headers=leader_headers)
    assert resp.status_code == 201, resp.text

    # update by leader
    resp = client.put("/submissions/me", json={"repository_url": "https://github.com/alpha/repo2"}, headers=leader_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["repository_url"] == "https://github.com/alpha/repo2"

    # get by member (view allowed)
    resp = client.get("/submissions/me", headers=member_headers)
    assert resp.status_code == 200
    assert resp.json()["repository_url"] == "https://github.com/alpha/repo2"

    # non-GitHub URL rejected
    resp = client.put("/submissions/me", json={"repository_url": "https://gitlab.com/x/y"}, headers=leader_headers)
    assert resp.status_code == 400


def test_event_config_controls_winner_count_and_bid_limits(client, admin_headers, csv_bytes, db):
    config = db.query(EventConfig).first()
    config.wildcard_slots = 2
    config.wildcard_starting_bid = 300
    config.wildcard_bid_increment = 50
    db.commit()

    creds = _import_creds(client, admin_headers, csv_bytes)
    alpha = _headers(client, "alice@test.com", creds["alice@test.com"])
    beta = _headers(client, "bob@test.com", creds["bob@test.com"])
    gamma = _headers(client, "carol@test.com", creds["carol@test.com"])

    ps1 = _create_round1_problem(db)
    bonus1 = _create_bonus_problem(db, "BX-10")
    # use a second bonus problem so two winners are possible
    bonus2 = _create_bonus_problem(db, "BX-11")
    for team in db.query(Team).all():
        team.ps_id = ps1.id
    db.commit()

    _set_state(db, "WILDCARD_BIDDING")
    for h, amount in [(alpha, 400), (beta, 350), (gamma, 300)]:
        resp = client.post("/wildcard/bid", params={"ps_id": bonus1.id, "amount": amount}, headers=h)
        assert resp.status_code == 200, resp.text

    # starting bid is 300 now; a 250 bid should fail
    resp = client.post("/wildcard/bid", params={"ps_id": bonus1.id, "amount": 250}, headers=alpha)
    assert resp.status_code == 400

    resp = client.post("/admin/wildcard/finalize", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["winners"]) == 2  # EventConfig.wildcard_slots = 2