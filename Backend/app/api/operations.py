from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.api.auth import get_current_active_admin
from app.api.websockets import manager
from app.core.config import settings
from app.core.database import get_db
from app.models.models import (
    Bid,
    EventConfig,
    GameConfig,
    ProblemStatement,
    RoundControl,
    Submission,
    Team,
    User,
    WalletTransaction,
    Wildcard,
    WildcardBid,
    WildcardSelectionPool,
    LabAllocationState,
    LabAssignment,
)
from app.services.event_service import (
    event_snapshot,
    event_timing,
    get_or_create_event_config,
    get_or_create_game_config,
    get_or_create_round_control,
    resume_event_timer,
    sync_expired_event_state,
)
from app.services.reset_service import reset_event_and_imported_participants
from app.services.wildcard_service import current_selection

router = APIRouter()


class DevelopmentResetRequest(BaseModel):
    confirmation: str


class EventDataResetRequest(BaseModel):
    confirmation: str


def _check(name: str, status: str, detail: str, value=None) -> dict:
    return {"name": name, "status": status, "detail": detail, "value": value}


@router.get("/admin/health")
def admin_health(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    del current_user
    db.execute(text("SELECT 1"))
    return {
        "backend": "connected",
        "database": "healthy",
        "server_time": datetime.now(timezone.utc),
        "reset_enabled": bool(settings.ENABLE_EVENT_RESET and not settings.is_production),
    }


@router.get("/admin/preflight")
def preflight(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    del current_user
    event = get_or_create_event_config(db)
    team_count = db.query(Team).count()
    leader_count = db.query(User).filter(User.role == "leader").count()
    round1_count = db.query(ProblemStatement).filter(ProblemStatement.round == 1).count()
    wildcard_count = db.query(ProblemStatement).filter(ProblemStatement.round == 2).count()
    duplicate_numbers = (
        db.query(ProblemStatement.ps_number)
        .group_by(ProblemStatement.ps_number)
        .having(func.count(ProblemStatement.id) > 1)
        .count()
    )
    checks = [
        _check("Backend", "READY", "API request completed."),
        _check("Database", "READY", "Database query completed."),
        _check("Admin authentication", "READY", "Administrator session is valid."),
        _check("Registration", "READY" if team_count else "BLOCKED", f"{team_count} team(s) registered.", team_count),
        _check("Leader accounts", "READY" if leader_count else "BLOCKED", f"{leader_count} leader account(s) available.", leader_count),
        _check("Round 1 problems", "READY" if round1_count else "BLOCKED", f"{round1_count} problem(s) imported.", round1_count),
        _check("Wildcard problems", "READY" if wildcard_count or not event.wildcard_enabled else "BLOCKED", f"{wildcard_count} problem(s) imported.", wildcard_count),
        _check("Problem numbers", "READY" if not duplicate_numbers else "BLOCKED", f"{duplicate_numbers} duplicate number(s).", duplicate_numbers),
        _check("Round 1 timers", "READY" if event.round1_preview_seconds > 0 and event.round1_bid_seconds > 0 else "BLOCKED", "Preview and bidding durations are positive."),
        _check("Wildcard timers", "READY" if event.wildcard_application_seconds > 0 and event.wildcard_bid_seconds > 0 else "BLOCKED", "Application and bidding durations are positive."),
        _check(
            "Wildcard slots",
            "READY" if not event.wildcard_enabled or 0 < event.wildcard_slots <= wildcard_count else "WARNING",
            f"Configured for {event.wildcard_slots} slot(s) and {wildcard_count} imported problem(s).",
            event.wildcard_slots,
        ),
        _check("Submission API", "READY", "Submission persistence is available."),
        _check("Public Round 1 leaderboard", "READY", "Public endpoint is registered."),
        _check("Public Wildcard leaderboard", "READY", "Public endpoint is registered."),
    ]
    overall = "BLOCKED" if any(item["status"] == "BLOCKED" for item in checks) else "WARNING" if any(item["status"] == "WARNING" for item in checks) else "READY"
    return {"status": overall, "checked_at": datetime.now(timezone.utc), "checks": checks}


@router.get("/admin/recovery")
def recovery_snapshot(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    del current_user
    expiry_actions: list[str] = []
    event = event_snapshot(db)
    game = db.query(GameConfig).first() or GameConfig(state="SETUP")
    round1 = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").first() or RoundControl(round_type="ROUND1")
    wildcard = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").first() or RoundControl(round_type="WILDCARD")
    event_config = db.query(EventConfig).first() or EventConfig()
    active = current_selection(db)
    current_problem = db.query(ProblemStatement).filter(ProblemStatement.id == round1.current_problem_id).first() if round1.current_problem_id else None
    return {
        "current_phase": game.state,
        "current_sub_state": wildcard.status if game.current_round == 2 else round1.status,
        "current_problem": {"id": current_problem.id, "number": current_problem.ps_number, "title": current_problem.title} if current_problem else None,
        "timer": event_timing(game),
        "round1_complete": round1.ended,
        "wildcard_applications": {"open": wildcard.applications_open, "status": wildcard.status},
        "wildcard_auction_state": wildcard.status,
        "wildcard_selection_rank": active[0].rank if active else None,
        "submission_state": "OPEN" if event_config.submissions_open else "CLOSED",
        "last_state_update": game.last_state_update,
        "expiry_actions": expiry_actions,
        "reset_enabled": bool(settings.ENABLE_EVENT_RESET and not settings.is_production),
        "event_data_reset_allowed": True,
        "event_data_reset_block_reason": None,
        "event": event,
    }


@router.post("/admin/recovery/resume-timer")
async def recovery_resume_timer(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    game = get_or_create_game_config(db)
    if not game.timer_paused:
        return recovery_snapshot(db, current_user)
    resume_event_timer(db)
    db.commit()
    snapshot = event_snapshot(db)
    response = recovery_snapshot(db, current_user)
    db.close()
    await manager.broadcast_event("timer_sync", snapshot)
    return response


@router.post("/admin/recovery/reload-state")
def recovery_reload_state(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    db.commit()
    return recovery_snapshot(db, current_user)


@router.post("/admin/recovery/resync-clients")
async def recovery_resync_clients(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    db.commit()
    snapshot = event_snapshot(db)
    response = recovery_snapshot(db, current_user)
    db.close()
    await manager.broadcast_event("event_state_changed", snapshot)
    return response


@router.post("/admin/recovery/retry-transition")
def recovery_retry_transition(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    actions = sync_expired_event_state(db)
    db.commit()
    return recovery_snapshot(db, current_user)


@router.post("/admin/event-data/reset")
async def reset_event_data(
    payload: EventDataResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Transactionally reset event-scoped data while preserving every account."""
    if payload.confirmation != "RESET EVENT":
        raise HTTPException(status_code=422, detail="Enter RESET EVENT to confirm the event data reset.")

    try:
        deleted = reset_event_and_imported_participants(
            db,
            actor=current_user,
            action="event.data_reset",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    snapshot = event_snapshot(db)
    preserved = {
        "system_accounts": db.query(User).filter(User.is_system_account.is_(True)).count(),
        "system_teams": db.query(Team).filter(Team.is_system_team.is_(True)).count(),
        "admin_accounts": db.query(User).filter(User.role == "admin").count(),
        "participant_accounts": db.query(User).filter(User.role.in_(("leader", "member"))).count(),
        "teams": db.query(Team).count(),
    }
    db.close()
    await manager.broadcast_event("event_state_changed", snapshot)
    await manager.broadcast_event("round_updated", {"action": "event_reset", "event": snapshot})
    await manager.broadcast_event("wildcard_updated", {"action": "event_reset", "event": snapshot})
    await manager.broadcast_event("team_updated", {"action": "event_reset"})
    return {
        "status": "reset_complete",
        "deleted": deleted,
        "preserved": preserved,
        "event_state": "WAITING",
        "next_action": "round1_setup",
    }


@router.post("/admin/development/reset")
async def development_reset(
    payload: DevelopmentResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    if settings.is_production or not settings.ENABLE_EVENT_RESET:
        raise HTTPException(status_code=403, detail="Development event reset is disabled.")
    if payload.confirmation != "RESET DEVELOPMENT EVENT":
        raise HTTPException(status_code=422, detail="Enter RESET DEVELOPMENT EVENT to confirm the rehearsal reset.")

    event = get_or_create_event_config(db)
    for model in (Submission, WildcardSelectionPool, WildcardBid, Wildcard, Bid, WalletTransaction, LabAssignment):
        db.query(model).delete(synchronize_session=False)
    allocation_state = db.query(LabAllocationState).filter(LabAllocationState.id == 1).one_or_none()
    if allocation_state:
        allocation_state.status = "NOT_READY"
        allocation_state.allocated_at = None
        allocation_state.finalized_at = None
    for team in db.query(Team).all():
        team.coins = event.starting_coins
        team.ps_id = None
        team.round1_problem_id = None
        team.wildcard_problem_id = None
        team.final_problem_choice = None
        team.final_problem_confirmed_at = None
        team.final_problem_defaulted = False
        team.round1_assignment_type = None
        team.round1_assignment_cost = None
    db.query(ProblemStatement).update({ProblemStatement.status: "available"}, synchronize_session=False)
    db.query(RoundControl).delete(synchronize_session=False)
    game = get_or_create_game_config(db)
    game.state = "WAITING"
    game.current_round = 1
    game.phase_started_at = datetime.now(timezone.utc)
    game.auction_timer_end = None
    game.timer_paused = False
    game.timer_paused_remaining_seconds = None
    game.timer_bias_seconds = 0
    game.last_state_update = datetime.now(timezone.utc)
    event.submissions_open = False
    db.add_all([
        RoundControl(
            round_type="ROUND1",
            status="IDLE",
            ended=False,
            applications_open=False,
            round1_winning_bid_sum=0,
            round1_winning_bid_count=0,
        ),
        RoundControl(round_type="WILDCARD", status="NOT_STARTED", ended=False, applications_open=False),
    ])
    db.commit()
    snapshot = event_snapshot(db)
    db.close()
    await manager.broadcast_event("event_state_changed", snapshot)
    return {"message": "Development rehearsal state reset.", "event": snapshot}
