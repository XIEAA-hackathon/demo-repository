import asyncio
from datetime import timedelta

from fastapi import Response
from sqlalchemy import event as sqlalchemy_event

from app.api import auction, participant, rounds, websockets
from app.api.websockets import ConnectionManager, _touch_socket_identity
from app.main import _process_expiry_database_cycle
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, User
from app.services.event_service import event_snapshot
from app.services.participant_session import utc_now


def _statement_counter(engine):
    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    sqlalchemy_event.listen(engine, "before_cursor_execute", record)
    return statements, record


def test_generic_leaderboard_uses_constant_query_count(db, engine):
    db.add(GameConfig(state="WAITING", current_round=1))
    problem = ProblemStatement(ps_number="R1-PERF", title="Performance", round=1, status="allocated")
    db.add(problem)
    db.flush()
    db.add_all([
        Team(team_name=f"Leaderboard Team {index}", coins=5000 - index, ps_id=problem.id)
        for index in range(12)
    ])
    db.commit()

    statements, listener = _statement_counter(engine)
    try:
        payload = auction.get_leaderboard(db, current_user=None)
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", listener)

    assert len(payload["teams"]) >= 12
    assert len(statements) == 2


def test_public_round_leaderboard_does_not_query_once_per_team(db, engine):
    problem = ProblemStatement(ps_number="R1-PUBLIC-PERF", title="Public performance", round=1, status="current")
    control = RoundControl(round_type="ROUND1", status="BIDDING")
    db.add_all([problem, control, EventConfig()])
    db.flush()
    control.current_problem_id = problem.id
    control.status = "BIDDING"
    for index in range(12):
        team = Team(team_name=f"Public Board Team {index}", coins=5000)
        db.add(team)
        db.flush()
        db.add(Bid(team_id=team.id, ps_id=problem.id, amount=100 + index, round=1))
    db.commit()

    statements, listener = _statement_counter(engine)
    try:
        payload = rounds.public_round_leaderboard(
            "round-1",
            Response(),
            db,
            current_user=None,
        )
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", listener)

    assert len(payload["rows"]) == 12
    assert len(statements) == 3


def test_normal_timer_cycle_is_one_database_query(db, engine, session_factory):
    game = GameConfig(state="WAITING", auction_timer_end=None)
    db.add(game)
    db.commit()

    statements, listener = _statement_counter(engine)
    try:
        actions, wildcard_assignment, snapshot, timer_sync = _process_expiry_database_cycle(session_factory)
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", listener)

    assert (actions, wildcard_assignment, snapshot, timer_sync) == ([], None, None, None)
    assert len(statements) == 1


def test_waiting_participant_dashboard_uses_five_queries(db, engine):
    user = User(
        name="Dashboard Leader",
        email="dashboard-performance@example.com",
        password_hash="unused",
        role="leader",
        credentials_active=True,
    )
    db.add(user)
    db.flush()
    team = Team(team_name="Dashboard Performance Team", leader_id=user.id, coins=5000)
    db.add(team)
    db.flush()
    user.team_id = team.id
    db.add_all([
        GameConfig(state="WAITING", current_round=1),
        EventConfig(),
        RoundControl(round_type="ROUND1", status="IDLE", ended=False),
        RoundControl(round_type="WILDCARD", status="NOT_STARTED", ended=False),
    ])
    db.commit()
    db.refresh(user)

    statements, listener = _statement_counter(engine)
    try:
        payload = participant.get_participant_dashboard(db, current_user=user)
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", listener)

    assert payload.team.id == team.id
    assert len(statements) == 5


def test_event_snapshot_is_read_only_and_reuses_preloaded_singletons(db, engine):
    game = GameConfig(state="WAITING", current_round=1)
    event_config = EventConfig()
    round1 = RoundControl(round_type="ROUND1", status="IDLE", ended=False)
    wildcard = RoundControl(round_type="WILDCARD", status="NOT_STARTED", ended=False)
    db.add_all([game, event_config, round1, wildcard])
    db.commit()
    for row in (game, event_config, round1, wildcard):
        db.refresh(row)

    statements, listener = _statement_counter(engine)
    try:
        snapshot = event_snapshot(
            db,
            config=game,
            event_config=event_config,
            round_controls={"ROUND1": round1, "WILDCARD": wildcard},
        )
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", listener)

    assert snapshot["event_state"] == "WAITING"
    assert statements == []


def test_fresh_socket_heartbeat_checks_revocation_without_update(db, engine, session_factory):
    user = User(
        name="Heartbeat User",
        email="heartbeat-performance@example.com",
        password_hash="unused",
        role="leader",
        credentials_active=True,
        session_id="heartbeat-session",
        session_last_seen_at=utc_now(),
    )
    db.add(user)
    db.commit()
    identity = {
        "user_id": user.id,
        "session_id": user.session_id,
        "session_last_seen_at": user.session_last_seen_at,
    }

    statements, listener = _statement_counter(engine)
    try:
        assert _touch_socket_identity(identity, session_factory) is True
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", listener)

    assert not any(statement.lstrip().upper().startswith("UPDATE") for statement in statements)
    assert sum(statement.lstrip().upper().startswith("SELECT") for statement in statements) == 1


def test_presence_refresh_coalesces_reconnect_burst(monkeypatch):
    async def scenario():
        manager = ConnectionManager()
        rebuilds = 0

        async def rebuild(_session_factory, **_kwargs):
            nonlocal rebuilds
            rebuilds += 1

        monkeypatch.setattr(websockets, "broadcast_presence_snapshot", rebuild)
        for _ in range(50):
            manager.schedule_presence_refresh(lambda: None, debounce_seconds=0.01)
        await asyncio.sleep(0.04)
        assert rebuilds == 1
        await manager.stop()

    asyncio.run(scenario())
