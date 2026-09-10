"""Round 1 auction: leader-only bidding, EventConfig rules, finalization."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.models.models import Team, User, Bid, WalletTransaction, Member, RoundControl
from app.api.websockets import manager


def _activate_problem(db, ps):
    ps.status = "current"
    control = RoundControl(round_type="ROUND1", current_problem_id=ps.id, status="BIDDING")
    db.add(control)
    db.commit()


def _import_and_get_client_state(client, admin_headers, csv_bytes, db):
    """Import the 3-team CSV and return email/password for a leader and a member."""
    credentialed_csv = (
        "Team Name,Leader Name,Leader Email,Leader Password,Member 1,Member 1 Email,Member 1 Password,Member 2\n"
        "Team Alpha,Alice,alice@test.com,Alice@123,Aarav,aarav@test.com,Aarav@123,Diya\n"
        "Team Beta,Bob,bob@test.com,Bob@1234,Charlie,charlie@test.com,Charlie@123,Rohan\n"
        "Team Gamma,Carol,carol@test.com,Carol@123,,,\n"
    ).encode()
    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("registrations.csv", credentialed_csv, "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    return {
        "alice@test.com": "Alice@123",
        "aarav@test.com": "Aarav@123",
        "bob@test.com": "Bob@1234",
        "charlie@test.com": "Charlie@123",
        "carol@test.com": "Carol@123",
    }


def test_non_leader_cannot_bid(client, admin_headers, csv_bytes, db):
    creds = _import_and_get_client_state(client, admin_headers, csv_bytes, db)
    leader_login = client.post("/login", data={"username": "alice@test.com", "password": creds["alice@test.com"]})
    assert leader_login.status_code == 200
    member_login = client.post("/login", data={"username": "aarav@test.com", "password": creds["aarav@test.com"]})
    assert member_login.status_code == 200
    member_headers = {"Authorization": f"Bearer {member_login.json()['access_token']}"}

    from app.models.models import ProblemStatement
    ps = ProblemStatement(ps_number="PS-01", title="T1", description="d", round=1)
    db.add(ps)
    db.commit()
    db.refresh(ps)

    response = client.post("/bid", json={"ps_id": ps.id, "increment": 5}, headers=member_headers)
    assert response.status_code == 403


def test_imported_leader_can_bid(client, admin_headers, csv_bytes, db, monkeypatch):
    creds = _import_and_get_client_state(client, admin_headers, csv_bytes, db)
    leader_headers = {"Authorization": "Bearer " + client.post(
        "/login", data={"username": "alice@test.com", "password": creds["alice@test.com"]}
    ).json()["access_token"]}

    from app.models.models import ProblemStatement, GameConfig
    ps = ProblemStatement(ps_number="PS-01", title="T1", description="d", round=1)
    db.add(ps)
    db.commit()
    db.refresh(ps)

    # must be in ROUND1_BIDDING state
    response = client.post("/bid", json={"ps_id": ps.id, "increment": 5}, headers=leader_headers)
    assert response.status_code == 409

    config = db.query(GameConfig).first()
    config.state = "ROUND1_BIDDING"
    db.commit()
    _activate_problem(db, ps)

    published = []
    monkeypatch.setattr(manager, "publish_event", lambda event_type, payload: published.append((event_type, payload)) or True)
    response = client.post("/bid", json={"ps_id": ps.id, "increment": 5}, headers=leader_headers)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {
        "message", "bid_id", "increment", "amount", "cooldown_seconds", "timestamp", "server_time",
    }
    assert published[0][0] == "bid_updated"
    assert set(published[0][1]) == {
        "team_name", "team_id", "ps_id", "amount", "increment", "round", "bid_id", "timestamp", "cooldown_seconds",
    }
    assert "leaderboard" not in published[0][1]


def test_broadcast_queue_failure_after_commit_does_not_undo_bid(
    client, admin_headers, csv_bytes, db, monkeypatch,
):
    creds = _import_and_get_client_state(client, admin_headers, csv_bytes, db)
    leader_headers = {"Authorization": "Bearer " + client.post(
        "/login", data={"username": "alice@test.com", "password": creds["alice@test.com"]}
    ).json()["access_token"]}

    from app.models.models import ProblemStatement, GameConfig, EventConfig
    problem = ProblemStatement(ps_number="PS-BROADCAST", title="Broadcast", description="d", round=1)
    db.add(problem)
    db.commit()
    db.refresh(problem)
    game = db.query(GameConfig).one()
    game.state = "ROUND1_BIDDING"
    event = db.query(EventConfig).one()
    event.bid_cooldown_seconds = 0
    db.commit()
    _activate_problem(db, problem)

    monkeypatch.setattr(manager, "publish_event", lambda *_args, **_kwargs: False)
    response = client.post(
        "/bid",
        json={"ps_id": problem.id, "increment": 5},
        headers=leader_headers,
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.query(Bid).filter(Bid.ps_id == problem.id).count() == 1


def test_bid_does_not_deduct_coins_immediately(client, admin_headers, csv_bytes, db):
    creds = _import_and_get_client_state(client, admin_headers, csv_bytes, db)
    leader_headers = {"Authorization": "Bearer " + client.post(
        "/login", data={"username": "alice@test.com", "password": creds["alice@test.com"]}
    ).json()["access_token"]}

    from app.models.models import ProblemStatement, GameConfig
    ps = ProblemStatement(ps_number="PS-01", title="T1", description="d", round=1)
    db.add(ps)
    db.commit()
    db.refresh(ps)
    config = db.query(GameConfig).first()
    config.state = "ROUND1_BIDDING"
    db.commit()
    _activate_problem(db, ps)

    team_alpha = db.query(Team).filter(Team.team_name == "Team Alpha").first()
    assert team_alpha.coins == 5000

    client.post("/bid", json={"ps_id": ps.id, "increment": 25}, headers=leader_headers)
    db.refresh(team_alpha)
    assert team_alpha.coins == 5000  # not deducted on placement

    assert db.query(WalletTransaction).filter(WalletTransaction.transaction_type == "ROUND1_WIN").count() == 0


def test_bid_bounds_from_event_config(client, admin_headers, csv_bytes, db):
    creds = _import_and_get_client_state(client, admin_headers, csv_bytes, db)
    leader_headers = {"Authorization": "Bearer " + client.post(
        "/login", data={"username": "alice@test.com", "password": creds["alice@test.com"]}
    ).json()["access_token"]}

    from app.models.models import ProblemStatement, GameConfig, EventConfig
    ps = ProblemStatement(ps_number="PS-01", title="T1", description="d", round=1)
    db.add(ps)
    db.commit()
    db.refresh(ps)

    config = db.query(GameConfig).first()
    config.state = "ROUND1_BIDDING"
    config.current_round = 1
    db.commit()
    _activate_problem(db, ps)

    # update EventConfig: minimum bid 200
    event_config = db.query(EventConfig).first()
    event_config.round1_minimum_bid = 200
    event_config.round1_bid_increment = 25
    event_config.bid_cooldown_seconds = 0
    db.commit()

    dashboard = client.get("/participant/dashboard", headers=leader_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["gameConfig"]["round1_bid_increment"] == 25

    response = client.post("/bid", json={"ps_id": ps.id, "amount": 200}, headers=leader_headers)
    assert response.status_code == 422

    response = client.post("/bid", json={"ps_id": ps.id, "increment": 5}, headers=leader_headers)
    assert response.status_code == 200, response.text
    assert response.json()["amount"] == 205
    response = client.post("/bid", json={"ps_id": ps.id, "increment": 10}, headers=leader_headers)
    assert response.status_code == 200, response.text
    assert response.json()["amount"] == 215


def test_finalize_assigns_all_bidders_when_fewer_than_five_and_charges_once(client, admin_headers, csv_bytes, db):
    creds = _import_and_get_client_state(client, admin_headers, csv_bytes, db)

    from app.models.models import ProblemStatement, GameConfig, EventConfig
    ps = ProblemStatement(ps_number="PS-01", title="T1", description="d", round=1)
    db.add(ps)
    db.commit()
    db.refresh(ps)

    config = db.query(GameConfig).first()
    config.state = "ROUND1_BIDDING"
    config.current_round = 1
    db.commit()
    _activate_problem(db, ps)

    bids = (("carol@test.com", 5), ("bob@test.com", 10), ("alice@test.com", 25))
    for email, increment in bids:
        headers = {"Authorization": "Bearer " + client.post(
            "/login", data={"username": email, "password": creds[email]}
        ).json()["access_token"]}
        resp = client.post("/bid", json={"ps_id": ps.id, "increment": increment}, headers=headers)
        assert resp.status_code == 200, resp.text

    response = client.post(f"/admin/auction/{ps.id}/finalize", headers=admin_headers)
    assert response.status_code == 200, response.text
    winners = response.json()["winners"]
    assert len(winners) == 3
    assert [w["team"] for w in winners] == ["Team Alpha", "Team Beta", "Team Gamma"]

    alpha = db.query(Team).filter(Team.team_name == "Team Alpha").first()
    beta = db.query(Team).filter(Team.team_name == "Team Beta").first()
    gamma = db.query(Team).filter(Team.team_name == "Team Gamma").first()

    # winners charged exactly once, losers pay zero
    assert alpha.coins == 5000 - 65
    assert beta.coins == 5000 - 40
    assert gamma.coins == 5000 - 30

    round1_win_tx = db.query(WalletTransaction).filter(WalletTransaction.transaction_type == "ROUND1_WIN").all()
    assert len(round1_win_tx) == 3
    assert sum(tx.amount for tx in round1_win_tx) == -135

    # finalized is idempotent
    response2 = client.post(f"/admin/auction/{ps.id}/finalize", headers=admin_headers)
    assert response2.status_code == 200
    assert response2.json()["message"].startswith("Problem Statement already finalized")
    assert db.query(WalletTransaction).filter(WalletTransaction.transaction_type == "ROUND1_WIN").count() == 3


def test_simultaneous_bids_are_serialized_against_one_highest_price(
    client, admin_headers, csv_bytes, db,
):
    creds = _import_and_get_client_state(client, admin_headers, csv_bytes, db)
    from app.models.models import EventConfig, GameConfig, ProblemStatement

    problem = ProblemStatement(ps_number="PS-RACE", title="Race", description="d", round=1)
    db.add(problem)
    db.flush()
    game = db.query(GameConfig).one()
    game.state = "ROUND1_BIDDING"
    game.current_round = 1
    event = db.query(EventConfig).one()
    event.round1_minimum_bid = 25
    event.bid_cooldown_seconds = 0
    db.commit()
    _activate_problem(db, problem)
    problem_id = problem.id

    headers = []
    for email in ("alice@test.com", "bob@test.com"):
        login = client.post("/login", data={"username": email, "password": creds[email]})
        assert login.status_code == 200, login.text
        headers.append({"Authorization": f"Bearer {login.json()['access_token']}"})

    barrier = Barrier(3)

    def bid_once(request_headers):
        barrier.wait(timeout=10)
        return client.post(
                "/bid",
                json={"ps_id": problem_id, "increment": 5},
            headers=request_headers,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(bid_once, request_headers) for request_headers in headers]
        barrier.wait(timeout=10)
        responses = [future.result(timeout=15) for future in futures]

    assert [response.status_code for response in responses] == [200, 200]
    db.expire_all()
    amounts = sorted(row.amount for row in db.query(Bid).filter(Bid.ps_id == problem_id).all())
    assert amounts == [30, 35]
    assert all(team.coins == 5000 for team in db.query(Team).filter(Team.team_name.in_(("Team Alpha", "Team Beta"))))


def test_dashboard_shows_imported_leader(client, admin_headers, csv_bytes, db):
    creds = _import_and_get_client_state(client, admin_headers, csv_bytes, db)
    headers = {"Authorization": "Bearer " + client.post(
        "/login", data={"username": "alice@test.com", "password": creds["alice@test.com"]}
    ).json()["access_token"]}

    response = client.get("/participant/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["leader"]["name"] == "Alice"
    assert data["leader"]["email"] == "alice@test.com"
    assert data["isLeader"] is True
    assert data["team"]["team_name"] == "Team Alpha"

    member_headers = {"Authorization": "Bearer " + client.post(
        "/login", data={"username": "aarav@test.com", "password": creds["aarav@test.com"]}
    ).json()["access_token"]}
    data2 = client.get("/participant/dashboard", headers=member_headers).json()
    assert data2["leader"]["name"] == "Alice"
    assert data2["isLeader"] is False
