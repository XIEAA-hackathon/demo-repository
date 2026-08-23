"""Wildcard slot auction, ranked selection, history, and deterministic ties."""

from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import auth, participant, rounds, wildcard
from app.core.database import Base, get_db

from app.core.security import get_password_hash
from app.models.models import (
    EventConfig,
    GameConfig,
    ProblemStatement,
    RoundControl,
    Team,
    User,
    WalletTransaction,
    Wildcard,
    WildcardBid,
    WildcardSelectionPool,
)


def _team(db, index: int, *, round1_problem=None):
    password = "temp-pass"
    leader = User(
        name=f"Leader {index}",
        email=f"leader{index}@wild.test",
        password_hash=get_password_hash(password),
        role="leader",
    )
    db.add(leader)
    db.flush()
    team = Team(
        team_name=f"Team {index}",
        coins=1000,
        leader_id=leader.id,
        is_approved=True,
        ps_id=round1_problem.id if round1_problem else None,
        round1_problem_id=round1_problem.id if round1_problem else None,
    )
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.commit()
    return team, leader.email, password


def _login(client, email, password):
    response = client.post("/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _problem_csv(count: int) -> bytes:
    rows = ["Problem Number,Title,Description"]
    rows.extend(f"{index},Wildcard title {index},Wildcard description {index}" for index in range(1, count + 1))
    return ("\n".join(rows) + "\n").encode()


def _prepare_round(db):
    config = db.query(EventConfig).first()
    config.wildcard_starting_bid = 100
    config.wildcard_bid_increment = 1
    config.wildcard_bid_seconds = 60
    game = db.query(GameConfig).first()
    game.auction_timer_end = None
    db.add(RoundControl(round_type="ROUND1", status="CLOSED", ended=True))
    db.commit()


def _run_slot_flow(client, admin_headers, db, *, applicants: int, slots: int, problems: int, preserve_history=False):
    _prepare_round(db)
    round1_problem = None
    if preserve_history:
        round1_problem = ProblemStatement(
            ps_number="R1-4", title="Round 1 Problem 4", description="R4", round=1, status="completed",
        )
        db.add(round1_problem)
        db.commit()
        db.refresh(round1_problem)

    teams = []
    headers = []
    for index in range(1, applicants + 1):
        team, email, password = _team(db, index, round1_problem=round1_problem if index == 1 else None)
        teams.append(team)
        headers.append(_login(client, email, password))

    opened = client.post("/admin/rounds/wildcard/applications/open", headers=admin_headers)
    assert opened.status_code == 200, opened.text
    assert opened.json()["settings"]["application_seconds"] == 60
    for team_headers in headers:
        assert client.post("/wildcard/apply", headers=team_headers).status_code == 200
    assert client.post("/admin/rounds/wildcard/applications/close", headers=admin_headers).status_code == 200
    assert client.post("/wildcard/apply", headers=headers[0]).status_code == 409

    imported = client.post(
        "/admin/rounds/wildcard/problems/import",
        headers=admin_headers,
        files={"file": ("wildcard.csv", _problem_csv(problems), "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    configured = client.post(
        "/admin/rounds/wildcard/slots",
        headers=admin_headers,
        json={"slots": slots},
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["slots"]["count"] == slots

    started = client.post("/admin/rounds/wildcard/bidding/start", headers=admin_headers)
    assert started.status_code == 200, started.text
    for index, team_headers in enumerate(headers):
        amount = 900 - index * 50
        response = client.post("/wildcard/bid", params={"amount": amount}, headers=team_headers)
        assert response.status_code == 200, response.text

    closed = client.post("/admin/rounds/wildcard/bidding/close", headers=admin_headers)
    assert closed.status_code == 200, closed.text
    winners = closed.json()["winners"]
    assert len(winners) == slots
    assert [winner["rank"] for winner in winners] == list(range(1, slots + 1))
    assert [winner["team_name"] for winner in winners] == [f"Team {index}" for index in range(1, slots + 1)]
    assert closed.json()["selection"]["pool_frozen"] is True
    assert len(closed.json()["selection"]["pool"]) == slots

    # A later upload must not mutate the frozen selection snapshot.
    late_import = client.post(
        "/admin/rounds/wildcard/problems/import",
        headers=admin_headers,
        files={"file": ("late.csv", b"Problem Number,Title,Description\n999,Late title,Late description\n", "text/csv")},
    )
    assert late_import.status_code == 200, late_import.text
    assert len(late_import.json()["selection"]["pool"]) == slots

    selections = []
    choice_counts = []
    for rank in range(slots):
        problems_response = client.get("/participant/problems?round=2", headers=headers[rank])
        assert problems_response.status_code == 200, problems_response.text
        choices = problems_response.json()
        choice_counts.append(len(choices))
        assert choices
        selected_problem = choices[0]
        selected = client.post(f"/wildcard/select/{selected_problem['id']}", headers=headers[rank])
        assert selected.status_code == 200, selected.text
        selections.append(selected_problem["id"])

    assert len(set(selections)) == slots
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    assert control.status == "COMPLETE"
    assert db.query(WalletTransaction).filter(WalletTransaction.transaction_type == "WILDCARD_WIN").count() == slots
    return teams, headers, choice_counts, round1_problem


def test_five_slot_ranked_selection_and_problem_history(client, admin_headers, db):
    teams, headers, choice_counts, round1_problem = _run_slot_flow(
        client, admin_headers, db, applicants=8, slots=5, problems=5, preserve_history=True,
    )
    assert choice_counts == [5, 4, 3, 2, 1]
    db.expire_all()
    first = db.query(Team).filter(Team.id == teams[0].id).one()
    assert first.round1_problem_id == round1_problem.id
    assert first.wildcard_problem_id is not None
    assert first.ps_id == first.wildcard_problem_id
    assert first.ps_id != first.round1_problem_id


def test_three_slot_ranked_selection_is_not_hardcoded(client, admin_headers, db):
    _teams, _headers, choice_counts, _round1_problem = _run_slot_flow(
        client, admin_headers, db, applicants=3, slots=3, problems=5,
    )
    assert choice_counts == [3, 2, 1]


def test_only_current_rank_can_select_and_slots_are_validated(client, admin_headers, db):
    _prepare_round(db)
    team1, email1, password1 = _team(db, 1)
    _team2, email2, password2 = _team(db, 2)
    headers1 = _login(client, email1, password1)
    headers2 = _login(client, email2, password2)
    client.post("/admin/rounds/wildcard/applications/open", headers=admin_headers)
    client.post("/wildcard/apply", headers=headers1)
    client.post("/wildcard/apply", headers=headers2)
    client.post("/admin/rounds/wildcard/applications/close", headers=admin_headers)
    client.post(
        "/admin/rounds/wildcard/problems/import",
        headers=admin_headers,
        files={"file": ("wildcard.csv", _problem_csv(2), "text/csv")},
    )
    too_many = client.post("/admin/rounds/wildcard/slots", headers=admin_headers, json={"slots": 3})
    assert too_many.status_code == 422
    assert client.post("/admin/rounds/wildcard/slots", headers=admin_headers, json={"slots": 2}).status_code == 200
    client.post("/admin/rounds/wildcard/bidding/start", headers=admin_headers)
    client.post("/wildcard/bid", params={"amount": 500}, headers=headers1)
    client.post("/wildcard/bid", params={"amount": 400}, headers=headers2)
    client.post("/admin/rounds/wildcard/bidding/close", headers=admin_headers)

    available = client.get("/participant/problems?round=2", headers=headers1).json()
    blocked = client.post(f"/wildcard/select/{available[0]['id']}", headers=headers2)
    assert blocked.status_code == 409
    assert "Team 1" in blocked.json()["detail"]


def test_equal_slot_bids_use_earlier_final_bid_timestamp(client, admin_headers, db):
    _prepare_round(db)
    team1, email1, password1 = _team(db, 1)
    team2, email2, password2 = _team(db, 2)
    headers1 = _login(client, email1, password1)
    headers2 = _login(client, email2, password2)
    control = RoundControl(
        round_type="WILDCARD", status="BIDDING_OPEN", slot_count=1, applications_open=False,
    )
    db.add(control)
    db.add_all([
        Wildcard(team_id=team1.id, status="applied"),
        Wildcard(team_id=team2.id, status="applied"),
        ProblemStatement(ps_number="WC-1", title="Wildcard", description="W", round=2, status="available"),
    ])
    game = db.query(GameConfig).first()
    game.state = "WILDCARD_BIDDING"
    game.current_round = 2
    game.auction_timer_end = datetime.utcnow() + timedelta(seconds=60)
    db.commit()

    assert client.post("/wildcard/bid", params={"amount": 500}, headers=headers1).status_code == 200
    assert client.post("/wildcard/bid", params={"amount": 500}, headers=headers2).status_code == 200
    result = client.post("/admin/rounds/wildcard/bidding/close", headers=admin_headers)
    assert result.status_code == 200
    assert result.json()["winners"][0]["team_id"] == team1.id
    assert db.query(WildcardBid).count() == 2


def test_simultaneous_wildcard_choices_allow_exactly_one_claim(tmp_path):
    race_engine = create_engine(
        f"sqlite:///{tmp_path / 'wildcard-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(race_engine)
    race_sessions = sessionmaker(autocommit=False, autoflush=False, bind=race_engine)
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(wildcard.router)
    app.include_router(participant.router)
    app.include_router(rounds.router)

    def race_db():
        session = race_sessions()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = race_db
    client = TestClient(app)
    db = race_sessions()
    db.add_all([EventConfig(), GameConfig(state="WAITING")])
    admin = User(name="Race Admin", email="race-admin@test.com", password_hash=get_password_hash("admin123"), role="admin")
    db.add(admin)
    db.commit()
    admin_login = client.post("/login", data={"username": admin.email, "password": "admin123"})
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    _prepare_round(db)
    team1, email1, password1 = _team(db, 1)
    _team2, email2, password2 = _team(db, 2)
    headers1 = _login(client, email1, password1)
    headers2 = _login(client, email2, password2)
    assert client.post("/admin/rounds/wildcard/applications/open", headers=admin_headers).status_code == 200
    assert client.post("/wildcard/apply", headers=headers1).status_code == 200
    assert client.post("/wildcard/apply", headers=headers2).status_code == 200
    assert client.post("/admin/rounds/wildcard/applications/close", headers=admin_headers).status_code == 200
    assert client.post(
        "/admin/rounds/wildcard/problems/import",
        headers=admin_headers,
        files={"file": ("wildcard.csv", _problem_csv(2), "text/csv")},
    ).status_code == 200
    assert client.post("/admin/rounds/wildcard/slots", headers=admin_headers, json={"slots": 2}).status_code == 200
    started = client.post("/admin/rounds/wildcard/bidding/start", headers=admin_headers)
    assert started.status_code == 200, started.text
    assert client.post("/wildcard/bid", params={"amount": 500}, headers=headers1).status_code == 200
    assert client.post("/wildcard/bid", params={"amount": 400}, headers=headers2).status_code == 200
    assert client.post("/admin/rounds/wildcard/bidding/close", headers=admin_headers).status_code == 200

    choices = client.get("/participant/problems?round=2", headers=headers1).json()
    assert len(choices) == 2
    barrier = Barrier(3)

    def choose(problem_id):
        barrier.wait()
        return client.post(f"/wildcard/select/{problem_id}", headers=headers1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(choose, choice["id"]) for choice in choices]
        barrier.wait()
        responses = [future.result(timeout=10) for future in futures]

    assert sorted(response.status_code for response in responses) == [200, 409]
    db.expire_all()
    assert db.query(Wildcard).filter(Wildcard.team_id == team1.id, Wildcard.status == "selected").count() == 1
    assert db.query(WildcardSelectionPool).filter(WildcardSelectionPool.selected_by_team_id == team1.id).count() == 1
    assert db.query(ProblemStatement).filter(ProblemStatement.round == 2, ProblemStatement.status == "allocated").count() == 1
    db.close()
    race_engine.dispose()
