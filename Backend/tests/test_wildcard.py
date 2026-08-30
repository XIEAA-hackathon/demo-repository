"""Wildcard slot auction, ranked selection, history, and deterministic ties."""

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import auth, participant, rounds, wildcard
from app.core.database import get_db

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
from app.services.wildcard_service import reconcile_wildcard_selection


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
    for team_headers in reversed(headers):
        response = client.post("/wildcard/bid", json={"increment": 5}, headers=team_headers)
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


def _prepare_active_selection(client, admin_headers, db, *, slots=3, problems=5):
    _prepare_round(db)
    config = db.query(EventConfig).first()
    config.wildcard_selection_seconds = 10
    db.commit()
    teams, headers = [], []
    for index in range(1, slots + 1):
        team, email, password = _team(db, index)
        teams.append(team)
        headers.append(_login(client, email, password))
    assert client.post("/admin/rounds/wildcard/applications/open", headers=admin_headers).status_code == 200
    for team_headers in headers:
        assert client.post("/wildcard/apply", headers=team_headers).status_code == 200
    assert client.post("/admin/rounds/wildcard/applications/close", headers=admin_headers).status_code == 200
    assert client.post(
        "/admin/rounds/wildcard/problems/import",
        headers=admin_headers,
        files={"file": ("wildcard.csv", _problem_csv(problems), "text/csv")},
    ).status_code == 200
    assert client.post("/admin/rounds/wildcard/slots", headers=admin_headers, json={"slots": slots}).status_code == 200
    assert client.post("/admin/rounds/wildcard/bidding/start", headers=admin_headers).status_code == 200
    for team_headers in reversed(headers):
        assert client.post("/wildcard/bid", json={"increment": 5}, headers=team_headers).status_code == 200
    closed = client.post("/admin/rounds/wildcard/bidding/close", headers=admin_headers)
    assert closed.status_code == 200, closed.text
    assert closed.json()["selection"]["duration_seconds"] == 10
    return teams, headers


def test_five_slot_ranked_selection_and_problem_history(client, admin_headers, db):
    teams, headers, choice_counts, round1_problem = _run_slot_flow(
        client, admin_headers, db, applicants=8, slots=5, problems=7, preserve_history=True,
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


def test_problem_display_snapshot_shrinks_with_wildcard_selection(
    client, admin_headers, display_headers, db,
):
    _teams, participant_headers = _prepare_active_selection(
        client, admin_headers, db, slots=4, problems=6,
    )

    previous_numbers = None
    for rank, expected_count in enumerate([4, 3, 2, 1]):
        snapshot = client.get("/public/leaderboard", headers=display_headers)
        assert snapshot.status_code == 200, snapshot.text
        payload = snapshot.json()
        assert payload["event_state"] == "WILDCARD_SELECTION"
        available = payload["available_wildcard_problems"]
        assert len(available) == expected_count
        assert all(set(problem) == {"problem_number", "number", "title", "description"} for problem in available)

        current_numbers = [problem["problem_number"] for problem in available]
        if previous_numbers is not None:
            assert set(current_numbers) < set(previous_numbers)
        previous_numbers = current_numbers

        if expected_count > 1:
            choices = client.get(
                "/participant/problems?round=2", headers=participant_headers[rank],
            ).json()
            selected = client.post(
                f"/wildcard/select/{choices[0]['id']}", headers=participant_headers[rank],
            )
            assert selected.status_code == 200, selected.text

    # A fresh request is the reconnect recovery path used by the display client.
    reconnected = client.get("/public/leaderboard", headers=display_headers).json()
    assert len(reconnected["available_wildcard_problems"]) == 1


def test_wildcard_selection_timer_configuration_range(client, admin_headers):
    configured = client.put("/admin/config", headers=admin_headers, json={"wildcard_selection_seconds": 10})
    assert configured.status_code == 200, configured.text
    assert configured.json()["wildcard_selection_seconds"] == 10
    assert client.put("/admin/config", headers=admin_headers, json={"wildcard_selection_seconds": 4}).status_code == 400
    assert client.put("/admin/config", headers=admin_headers, json={"wildcard_selection_seconds": 301}).status_code == 400


def test_selection_timeout_assigns_first_frozen_problem_and_starts_fresh_timer(client, admin_headers, db):
    teams, headers = _prepare_active_selection(client, admin_headers, db)
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    control.selection_ends_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    background_result = reconcile_wildcard_selection(db)
    assert background_result is not None
    assert background_result["method"] == "timeout"
    db.expire_all()
    first_application = db.query(Wildcard).filter(Wildcard.team_id == teams[0].id).one()
    first_pool_row = db.query(WildcardSelectionPool).order_by(WildcardSelectionPool.position.asc()).first()
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    assert first_application.problem_id == first_pool_row.problem_id
    assert first_application.selection_method == "timeout"
    assert first_pool_row.selected_by_team_id == teams[0].id
    assert control.current_selection_rank == 2
    assert control.selection_duration_seconds == 10
    assert round((control.selection_ends_at - control.selection_started_at).total_seconds()) == 10


def test_admin_end_turn_assigns_first_problem_and_advances(client, admin_headers, db):
    teams, _headers = _prepare_active_selection(client, admin_headers, db)
    state = client.get("/admin/rounds/wildcard", headers=admin_headers).json()
    response = client.post(
        "/admin/rounds/wildcard/selection/end-turn",
        headers=admin_headers,
        json={"expected_rank": state["selection"]["current_rank"], "expected_team_id": state["selection"]["current_team_id"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["assignment"]["method"] == "admin_end_turn"
    db.expire_all()
    first_application = db.query(Wildcard).filter(Wildcard.team_id == teams[0].id).one()
    first_pool_row = db.query(WildcardSelectionPool).order_by(WildcardSelectionPool.position.asc()).first()
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    assert first_application.problem_id == first_pool_row.problem_id
    assert control.current_selection_rank == 2
    assert control.selection_duration_seconds == 10


def test_manual_submit_at_expiry_has_exactly_one_assignment(client, admin_headers, db):
    teams, headers = _prepare_active_selection(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    requested_problem_id = choices[-1]["id"]
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    control.selection_ends_at = datetime.utcnow() - timedelta(milliseconds=1)
    db.commit()

    response = client.post(f"/wildcard/select/{requested_problem_id}", headers=headers[0])
    assert response.status_code == 200, response.text
    assert response.json()["selection_method"] == "timeout"
    db.expire_all()
    application = db.query(Wildcard).filter(Wildcard.team_id == teams[0].id).one()
    claims = db.query(WildcardSelectionPool).filter(WildcardSelectionPool.selected_by_team_id == teams[0].id).all()
    assert len(claims) == 1
    assert application.problem_id == claims[0].problem_id
    assert application.problem_id != requested_problem_id


def test_manual_selection_just_before_expiry_wins_once(client, admin_headers, db):
    teams, headers = _prepare_active_selection(client, admin_headers, db)
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    requested_problem_id = choices[-1]["id"]
    deadline_base = datetime.now(timezone.utc)
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    control.selection_ends_at = deadline_base + timedelta(seconds=1)
    db.commit()

    response = client.post(f"/wildcard/select/{requested_problem_id}", headers=headers[0])
    assert response.status_code == 200, response.text
    assert response.json()["selection_method"] == "manual"
    assert reconcile_wildcard_selection(db, now=deadline_base + timedelta(seconds=2)) is None
    db.expire_all()
    application = db.query(Wildcard).filter(Wildcard.team_id == teams[0].id).one()
    claims = db.query(WildcardSelectionPool).filter(WildcardSelectionPool.selected_by_team_id == teams[0].id).all()
    assert len(claims) == 1
    assert application.problem_id == requested_problem_id == claims[0].problem_id


@pytest.mark.parametrize("first_actor", ["participant", "admin"])
def test_admin_end_turn_and_participant_selection_cannot_both_win(client, admin_headers, db, first_actor):
    teams, headers = _prepare_active_selection(client, admin_headers, db, slots=2, problems=3)
    state = client.get("/admin/rounds/wildcard", headers=admin_headers).json()
    choices = client.get("/participant/problems?round=2", headers=headers[0]).json()
    participant_request = lambda: client.post(f"/wildcard/select/{choices[-1]['id']}", headers=headers[0])
    admin_request = lambda: client.post(
        "/admin/rounds/wildcard/selection/end-turn",
        headers=admin_headers,
        json={"expected_rank": state["selection"]["current_rank"], "expected_team_id": state["selection"]["current_team_id"]},
    )

    first = participant_request() if first_actor == "participant" else admin_request()
    second = admin_request() if first_actor == "participant" else participant_request()
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    db.expire_all()
    application = db.query(Wildcard).filter(Wildcard.team_id == teams[0].id).one()
    claims = db.query(WildcardSelectionPool).filter(WildcardSelectionPool.selected_by_team_id == teams[0].id).all()
    assert application.status == "selected"
    assert len(claims) == 1


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
    client.post("/wildcard/bid", json={"increment": 5}, headers=headers2)
    client.post("/wildcard/bid", json={"increment": 5}, headers=headers1)
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

    db.add_all([
        WildcardBid(team_id=team1.id, amount=500, timestamp=datetime.utcnow() - timedelta(seconds=1)),
        WildcardBid(team_id=team2.id, amount=500, timestamp=datetime.utcnow()),
    ])
    db.commit()
    result = client.post("/admin/rounds/wildcard/bidding/close", headers=admin_headers)
    assert result.status_code == 200
    assert result.json()["winners"][0]["team_id"] == team1.id
    assert db.query(WildcardBid).count() == 2


def test_simultaneous_wildcard_choices_allow_exactly_one_claim(session_factory):
    race_sessions = session_factory
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
    assert client.post("/wildcard/bid", json={"increment": 5}, headers=headers2).status_code == 200
    assert client.post("/wildcard/bid", json={"increment": 5}, headers=headers1).status_code == 200
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
