from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.models import EventConfig, GameConfig, RoundControl, Team, User, WalletTransaction
from app.core.event_constants import ROUND1_WINNER_COUNT
from app.schemas.schemas import EVENT_STATES
from app.services.activity_log import record_event

STATE_TRANSITIONS = {
    state: ({EVENT_STATES[index + 1]} if index + 1 < len(EVENT_STATES) else set())
    for index, state in enumerate(EVENT_STATES)
}

LEGACY_STARTING_COINS = 1000
STARTING_COINS = 5000


def upgrade_legacy_starting_coins(db: Session) -> int:
    """Upgrade wallets created with the former 1,000-coin allocation once."""
    legacy_team_ids = db.query(WalletTransaction.team_id).filter(
        WalletTransaction.transaction_type == "INITIAL_ALLOCATION",
        WalletTransaction.amount == LEGACY_STARTING_COINS,
    )
    team_count = db.query(Team).filter(Team.id.in_(legacy_team_ids)).update(
        {Team.coins: Team.coins + (STARTING_COINS - LEGACY_STARTING_COINS)},
        synchronize_session=False,
    )
    db.query(WalletTransaction).filter(
        WalletTransaction.transaction_type == "INITIAL_ALLOCATION",
        WalletTransaction.amount == LEGACY_STARTING_COINS,
    ).update({WalletTransaction.amount: STARTING_COINS}, synchronize_session=False)
    db.query(EventConfig).filter(EventConfig.starting_coins == LEGACY_STARTING_COINS).update(
        {EventConfig.starting_coins: STARTING_COINS},
        synchronize_session=False,
    )
    db.commit()
    return team_count

def get_or_create_event_config(db: Session) -> EventConfig:
    config = db.query(EventConfig).first()
    if not config:
        config = EventConfig(round1_winner_count=ROUND1_WINNER_COUNT)
        db.add(config)
        db.commit()
        db.refresh(config)
    elif config.round1_winner_count != ROUND1_WINNER_COUNT or config.starting_coins == LEGACY_STARTING_COINS:
        config.round1_winner_count = ROUND1_WINNER_COUNT
        if config.starting_coins == LEGACY_STARTING_COINS:
            config.starting_coins = STARTING_COINS
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
        "WILDCARD_APPLICATION": event_config.wildcard_application_seconds,
        "WILDCARD_BIDDING": event_config.wildcard_bid_seconds,
        "CODING": event_config.coding_duration_seconds,
    }.get(state)

def transition_event_state(
    db: Session,
    state: str,
    *,
    validate: bool = True,
    restart: bool = False,
    commit: bool = True,
) -> GameConfig:
    if state not in EVENT_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state. Must be one of {EVENT_STATES}")

    config = get_or_create_game_config(db)
    if state == config.state and not restart:
        return config
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
    config.last_state_update = now
    if commit:
        db.commit()
        db.refresh(config)
    else:
        db.flush()
    return config

def get_or_create_round_control(db: Session, round_type: str) -> RoundControl:
    if round_type not in ("ROUND1", "WILDCARD"):
        raise HTTPException(status_code=400, detail="round_type must be ROUND1 or WILDCARD")
    control = db.query(RoundControl).filter(RoundControl.round_type == round_type).first()
    if control and round_type == "WILDCARD" and control.status in {"IDLE", "READY"}:
        control.status = "NOT_STARTED"
        db.commit()
        db.refresh(control)
    if not control:
        control = RoundControl(round_type=round_type, status="NOT_STARTED" if round_type == "WILDCARD" else "IDLE")
        db.add(control)
        if round_type == "ROUND1":
            event_config = get_or_create_event_config(db)
            if event_config.round1_preview_seconds == 120 and event_config.round1_bid_seconds == 300:
                event_config.round1_preview_seconds = 60
                event_config.round1_bid_seconds = 60
        else:
            event_config = get_or_create_event_config(db)
            if event_config.wildcard_application_seconds == 30:
                event_config.wildcard_application_seconds = 60
        db.commit()
        db.refresh(control)
    return control


def _remaining_seconds(config: GameConfig, now: datetime | None = None) -> int | None:
    if config.timer_paused:
        return max(0, config.timer_paused_remaining_seconds or 0)
    if not config.auction_timer_end:
        return None
    current_time = now or datetime.utcnow()
    return max(0, int((config.auction_timer_end - current_time).total_seconds()))


def sync_expired_event_state(db: Session) -> list[str]:
    """Persist safe timer expiry outcomes from server time.

    This function is safe to call from requests and the background expiry worker.
    It closes mutation windows but never performs a rule-sensitive winner assignment.
    """
    config = get_or_create_game_config(db)
    if config.timer_paused or _remaining_seconds(config) != 0:
        return []

    now = datetime.utcnow()
    actions: list[str] = []
    if config.state == "ROUND1_PREVIEW":
        control = get_or_create_round_control(db, "ROUND1")
        if control.status == "PREVIEW":
            control.status = "PREVIEW_EXPIRED"
            actions.append("round1.preview_expired")
    elif config.state == "ROUND1_BIDDING":
        control = get_or_create_round_control(db, "ROUND1")
        if control.status == "BIDDING":
            control.status = "READY"
            config.state = "ROUND1_RESULT"
            actions.append("round1.bidding_expired")
    elif config.state == "WILDCARD_APPLICATION":
        control = get_or_create_round_control(db, "WILDCARD")
        if control.status == "APPLICATIONS_OPEN" or control.applications_open:
            control.applications_open = False
            control.status = "APPLICATIONS_CLOSED"
            actions.append("wildcard.applications_expired")
    elif config.state == "WILDCARD_BIDDING":
        control = get_or_create_round_control(db, "WILDCARD")
        if control.status == "BIDDING_OPEN":
            control.status = "BIDDING_CLOSED"
            actions.append("wildcard.bidding_expired")

    if not actions:
        return []
    config.auction_timer_end = None
    config.timer_paused = False
    config.timer_paused_remaining_seconds = None
    config.last_state_update = now
    for action in actions:
        record_event(db, action, actor_type="system", metadata={"reason": "timer_expired"})
    db.commit()
    db.refresh(config)
    return actions


def pause_event_timer(db: Session) -> GameConfig:
    config = get_or_create_game_config(db)
    if config.timer_paused:
        return config
    remaining = _remaining_seconds(config)
    if remaining is None:
        raise HTTPException(status_code=400, detail="The current stage has no active timer.")
    config.timer_paused = True
    config.timer_paused_remaining_seconds = remaining
    config.last_state_update = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return config


def resume_event_timer(db: Session) -> GameConfig:
    config = get_or_create_game_config(db)
    if not config.timer_paused:
        raise HTTPException(status_code=409, detail="The event timer is not paused.")
    remaining = max(0, config.timer_paused_remaining_seconds or 0)
    config.auction_timer_end = datetime.utcnow() + timedelta(seconds=remaining)
    config.timer_paused = False
    config.timer_paused_remaining_seconds = None
    config.last_state_update = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return config


def adjust_event_timer(db: Session, seconds: int) -> GameConfig:
    if seconds == 0:
        raise HTTPException(status_code=400, detail="Timer adjustment cannot be zero.")
    config = get_or_create_game_config(db)
    remaining = _remaining_seconds(config)
    if remaining is None:
        raise HTTPException(status_code=400, detail="The current stage has no active timer.")
    adjusted = max(0, remaining + seconds)
    applied_delta = adjusted - remaining
    if config.timer_paused:
        config.timer_paused_remaining_seconds = adjusted
    else:
        config.auction_timer_end = datetime.utcnow() + timedelta(seconds=adjusted)
    config.timer_bias_seconds += applied_delta
    config.last_state_update = datetime.utcnow()
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
        "remaining_seconds": _remaining_seconds(config),
    }

def event_snapshot(db: Session) -> dict:
    sync_expired_event_state(db)
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)
    round1 = get_or_create_round_control(db, "ROUND1")
    wildcard = get_or_create_round_control(db, "WILDCARD")
    return {
        "event_state": config.state,
        "current_round": config.current_round,
        "bid_cooldown_seconds": event_config.bid_cooldown_seconds,
        "last_state_update": config.last_state_update,
        "timing": event_timing(config),
        "allowed_transitions": sorted(STATE_TRANSITIONS.get(config.state, set())),
        "rounds": {
            "ROUND1": {"status": round1.status, "ended": round1.ended, "current_problem_id": round1.current_problem_id},
            "WILDCARD": {"status": wildcard.status, "ended": wildcard.ended, "current_problem_id": wildcard.current_problem_id, "applications_open": wildcard.applications_open},
        },
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
