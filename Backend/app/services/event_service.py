from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.models import EventConfig, GameConfig, Team, User
from app.schemas.schemas import EVENT_STATES

STATE_TRANSITIONS = {
    state: ({EVENT_STATES[index + 1]} if index + 1 < len(EVENT_STATES) else set())
    for index, state in enumerate(EVENT_STATES)
}
# An organizer can reset a completed event for a new run.
STATE_TRANSITIONS["RESULTS"].add("WAITING")

def get_or_create_event_config(db: Session) -> EventConfig:
    config = db.query(EventConfig).first()
    if not config:
        config = EventConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

def get_or_create_game_config(db: Session) -> GameConfig:
    config = db.query(GameConfig).first()
    if not config:
        config = GameConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

def _duration_for_state(event_config: EventConfig, state: str) -> int | None:
    return {
        "ROUND1_PREVIEW": event_config.round1_preview_seconds,
        "ROUND1_BIDDING": event_config.round1_bid_seconds,
        "WILDCARD_PREVIEW": event_config.wildcard_preview_seconds,
        "WILDCARD_BIDDING": event_config.wildcard_bid_seconds,
        "CODING": event_config.coding_duration_seconds,
    }.get(state)

def transition_event_state(db: Session, state: str, *, validate: bool = True) -> GameConfig:
    if state not in EVENT_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state. Must be one of {EVENT_STATES}")

    config = get_or_create_game_config(db)
    if validate and state != config.state and state not in STATE_TRANSITIONS.get(config.state, set()):
        allowed = sorted(STATE_TRANSITIONS.get(config.state, set()))
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from {config.state} to {state}. Allowed next state(s): {allowed}",
        )

    now = datetime.utcnow()
    duration = _duration_for_state(get_or_create_event_config(db), state)
    config.state = state
    if state == "WAITING" or state.startswith("ROUND1"):
        config.current_round = 1
    elif state.startswith("WILDCARD"):
        config.current_round = 2
    config.phase_started_at = now
    config.auction_timer_end = now + timedelta(seconds=duration) if duration is not None else None
    config.timer_paused = False
    config.timer_paused_remaining_seconds = None
    config.timer_bias_seconds = 0
    db.commit()
    db.refresh(config)
    return config

def event_timing(config: GameConfig) -> dict:
    def as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    return {
        "server_time": datetime.now(timezone.utc),
        "started_at": as_utc(config.phase_started_at),
        "ends_at": as_utc(config.auction_timer_end),
        "paused": bool(config.timer_paused),
        "paused_remaining_seconds": config.timer_paused_remaining_seconds,
    }

def event_snapshot(db: Session) -> dict:
    config = get_or_create_game_config(db)
    return {
        "event_state": config.state,
        "current_round": config.current_round,
        "timing": event_timing(config),
    }

def get_team_for_user(db: Session, user: User) -> Team | None:
    """Return the team a user belongs to (leader via leader_id, member via team_id)."""
    if user.team_id:
        return db.query(Team).filter(Team.id == user.team_id).first()
    return db.query(Team).filter(Team.leader_id == user.id).first()

def current_user_is_team_leader(db: Session, user: User, team: Team) -> bool:
    return team is not None and team.leader_id == user.id

def ensure_leader(db: Session, user: User) -> Team:
    """Raise 403 unless the user is the imported team leader."""
    from fastapi import HTTPException, status as http_status
    team = get_team_for_user(db, user)
    if not team:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="No team is linked to your account.")
    if team.leader_id != user.id:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Only the imported team leader can perform this action.")
    return team
