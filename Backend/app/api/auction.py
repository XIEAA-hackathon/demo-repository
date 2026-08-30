from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError
from typing import List

from app.core.database import get_db
from app.models.models import Bid, Team, ProblemStatement, GameConfig, WalletTransaction, EventConfig, RoundControl
from app.schemas.schemas import BidCreate, EVENT_STATES
from app.api.auth import get_current_user, get_current_active_admin
from app.api.websockets import manager
from app.services.event_service import (
    event_snapshot, get_or_create_game_config, get_or_create_event_config,
    get_team_for_user, ensure_leader, transition_event_state,
    pause_event_timer, resume_event_timer, adjust_event_timer,
    get_or_create_round_control,
    sync_expired_event_state,
)
from app.services.activity_log import record_event
from app.services.bid_cooldown import bid_cooldown_rejection, bid_cooldown_remaining
from app.services.round1_assignment import (
    ROUND1_FINALIZATION_LOCK,
    ROUND1_PROBLEM_CAPACITY,
    update_round1_winning_bid_aggregate,
)

router = APIRouter()


def _round1_bid_leaderboard(db: Session, ps_id: int, round_number: int) -> list[dict]:
    rows = (
        db.query(Bid, Team)
        .join(Team, Team.id == Bid.team_id)
        .filter(Bid.ps_id == ps_id, Bid.round == round_number)
        .order_by(Bid.amount.desc(), Bid.timestamp.asc(), Bid.team_id.asc())
        .all()
    )
    return [
        {
            "rank": rank,
            "team_id": team.id,
            "team_name": team.team_name,
            "amount": row.amount,
        }
        for rank, (row, team) in enumerate(rows, start=1)
    ]

def _assert_state(state: str, config: GameConfig, allowed: List[str]):
    if state not in allowed:
        raise HTTPException(status_code=409, detail=f"Action not allowed in state '{state}'. Allowed: {allowed}")

# ---------------------------------------------------------------- Bidding

@router.post("/bid")
async def place_bid(bid: BidCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # Leader-only: identity comes from imported registration data
    team = ensure_leader(db, current_user)
    sync_expired_event_state(db)
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)

    _assert_state(config.state, config, ["ROUND1_BIDDING"])

    if team.round1_problem_id is not None or team.ps_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Your team already has a Round 1 problem and cannot participate in another Round 1 auction.",
        )

    control = get_or_create_round_control(db, "ROUND1")
    # Use the same lock order as finalization: round control, problem, team,
    # then bids. Locking the singleton control serializes the price decision so
    # concurrent requests cannot calculate from the same stale highest bid.
    control = (
        db.query(RoundControl)
        .filter(RoundControl.id == control.id)
        .with_for_update()
        .one()
    )
    ps = db.query(ProblemStatement).filter(ProblemStatement.id == bid.ps_id).with_for_update().first()
    team = db.query(Team).filter(Team.id == team.id).with_for_update().first()
    if not ps or ps.id != control.current_problem_id or ps.status != "current":
        raise HTTPException(status_code=400, detail="Invalid or unavailable Problem Statement")
    auction_bids = db.query(Bid).filter(
        Bid.ps_id == ps.id,
        Bid.round == config.current_round,
    ).with_for_update().all()
    current_price = max(
        [event_config.round1_minimum_bid, *(row.amount for row in auction_bids)],
    )
    next_amount = current_price + bid.increment
    if next_amount > team.coins:
        raise HTTPException(
            status_code=400,
            detail=f"A +{bid.increment} bid would be {next_amount} coins and exceed the team wallet balance of {team.coins}.",
        )

    existing_bid = next((row for row in auction_bids if row.team_id == team.id), None)

    cooldown = event_config.bid_cooldown_seconds or 0
    remaining = bid_cooldown_remaining(
        db,
        team.id,
        cooldown,
        round_type="ROUND1",
        problem_id=ps.id,
        round_number=config.current_round,
    )
    if remaining > 0:
        return bid_cooldown_rejection(remaining)

    now = datetime.now(timezone.utc)
    if existing_bid:
        existing_bid.amount = next_amount
        existing_bid.timestamp = now
    else:
        db.add(Bid(team_id=team.id, ps_id=ps.id, amount=next_amount, round=config.current_round, timestamp=now))
    record_event(db, "round1.bid_placed", actor=current_user, entity_type="team", entity_id=team.id, metadata={"problem_id": ps.id, "increment": bid.increment, "amount": next_amount})
    try:
        db.commit()
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The bid changed concurrently. Refresh and retry.") from exc

    payload = {
        "team_name": team.team_name,
        "team_id": team.id,
        "ps_id": ps.id,
        "amount": next_amount,
        "round": "ROUND1",
        "bid": {
            "id": existing_bid.id if existing_bid else f"{ps.id}-{team.id}",
            "team_id": team.id,
            "ps_id": ps.id,
            "amount": next_amount,
            "round": config.current_round,
            "timestamp": now.isoformat(),
        },
        "leaderboard": _round1_bid_leaderboard(db, ps.id, config.current_round),
    }
    db.close()
    await manager.broadcast_event("bid_updated", {
        **payload,
    })
    return {"message": "Bid placed successfully. Coins are not deducted yet.", "increment": bid.increment, "amount": next_amount}

@router.get("/bid-history")
def get_bid_history(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    bids = db.query(Bid).all()
    return bids

@router.post("/admin/auction/{ps_id}/finalize")
async def finalize_round_one(
    ps_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_admin),
):
    """Top N winners (N = EventConfig.round1_winner_count) for ONE problem statement.

    Winning teams are charged exactly once. Transactional + idempotent.
    """
    with ROUND1_FINALIZATION_LOCK:
        config = get_or_create_game_config(db)
        get_or_create_event_config(db)
        control = get_or_create_round_control(db, "ROUND1")

        # The in-process lock protects one worker; these row locks also protect
        # against a second Uvicorn worker/admin request finalizing concurrently.
        control = db.query(RoundControl).filter(RoundControl.id == control.id).with_for_update().one()

        ps = db.query(ProblemStatement).filter(ProblemStatement.id == ps_id).with_for_update().first()
        if not ps:
            raise HTTPException(status_code=404, detail="Problem Statement not found")
        if ps.status in {"allocated", "completed", "no_bids"}:
            # Idempotent: the assignment and aggregate were already committed.
            existing_winners = db.query(Team).filter(Team.round1_problem_id == ps.id).all()
            return {
                "message": "Problem Statement already finalized.",
                "ps": ps.ps_number,
                "winners": [t.team_name for t in existing_winners],
            }

        ranked_bids = db.query(Bid).filter(
            Bid.ps_id == ps.id,
            Bid.round == config.current_round,
        ).order_by(Bid.amount.desc(), Bid.timestamp.asc(), Bid.team_id.asc()).with_for_update().all()

        existing_assignment_count = db.query(Team).filter(Team.round1_problem_id == ps.id).count()
        winner_count = max(0, ROUND1_PROBLEM_CAPACITY - existing_assignment_count)
        winners = []
        for bid in ranked_bids:
            if len(winners) >= winner_count:
                break
            winner_team = db.query(Team).filter(Team.id == bid.team_id).with_for_update().first()
            if not winner_team or winner_team.round1_problem_id is not None or winner_team.ps_id is not None:
                continue  # team already has a problem; skip
            if winner_team.coins < bid.amount:
                continue

            # Charge exactly once via explicit ledger entry.
            winner_team.coins -= bid.amount
            db.add(WalletTransaction(
                team_id=winner_team.id,
                transaction_type="ROUND1_WIN",
                amount=-bid.amount,
                description=f"Round 1 auction win for {ps.ps_number}",
            ))
            winner_team.ps_id = ps.id
            winner_team.round1_problem_id = ps.id
            winner_team.round1_assignment_type = "BID_WINNER"
            winner_team.round1_assignment_cost = bid.amount
            winners.append({"team": winner_team.team_name, "amount": bid.amount})

        if winners:
            update_round1_winning_bid_aggregate(
                control,
                ps,
                [winner["amount"] for winner in winners],
            )
            ps.status = "allocated"
        else:
            ps.status = "no_bids"
        if control.current_problem_id == ps.id:
            control.current_problem_id = None
        unassigned_count = db.query(Team).filter(
            Team.is_approved.is_(True),
            Team.is_system_team.is_(False),
            Team.round1_problem_id.is_(None),
        ).count()
        control.status = "COMPLETE" if unassigned_count == 0 else "READY"
        control.ended = unassigned_count == 0
        record_event(db, "round1.auction_finalized", actor=current_user, entity_type="problem", entity_id=ps.id, metadata={"winner_count": len(winners)})
        db.commit()

    transition_event_state(db, "ROUND1_RESULT")
    snapshot = event_snapshot(db)
    ps_number = ps.ps_number
    db.close()

    await manager.broadcast_event("auction_finalized", {
        "ps_number": ps_number,
        "winners": winners,
    })
    await manager.broadcast_event("event_state_changed", snapshot)
    message = (
        "Round 1 finalized. Actual winners charged once."
        if winners
        else "No bids received. Problem moved to remaining allocation pool."
    )
    return {"message": message, "winners": winners}

@router.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Visible to all authenticated participants; cutoff is a display concern handled
    by the frontend using EventConfig.round1_winner_count."""
    config = get_or_create_game_config(db)
    teams = db.query(Team).order_by(Team.coins.desc()).all()
    result = []
    for t in teams:
        ps = db.query(ProblemStatement).filter(ProblemStatement.id == t.ps_id).first()
        result.append({
            "team_id": t.id,
            "team_name": t.team_name,
            "coins": t.coins,
            "allocated_ps": ps.ps_number if ps else None,
        })
    return {"teams": result, "state": config.state, "round": config.current_round}

# ---------------------------------------------------------------- Admin Round Controls

@router.post("/admin/round/start-preview")
async def start_preview(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = transition_event_state(db, "ROUND1_PREVIEW")
    snapshot = event_snapshot(db)
    state = config.state
    db.close()
    await manager.broadcast_event("event_state_changed", snapshot)
    return {"state": state, **snapshot}

@router.post("/admin/round/start-bidding")
async def start_bidding(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = transition_event_state(db, "ROUND1_BIDDING")
    snapshot = event_snapshot(db)
    response = {"state": config.state, "ends_at": config.auction_timer_end, **snapshot}
    db.close()
    await manager.broadcast_event("event_state_changed", snapshot)
    return response

@router.post("/admin/round/pause")
async def pause_timer(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = pause_event_timer(db)
    snapshot = event_snapshot(db)
    remaining_seconds = config.timer_paused_remaining_seconds
    db.close()
    await manager.broadcast_event("timer_sync", snapshot)
    return {"paused": True, "remaining_seconds": remaining_seconds}

@router.post("/admin/round/resume")
async def resume_timer(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = resume_event_timer(db)
    snapshot = event_snapshot(db)
    ends_at = config.auction_timer_end
    db.close()
    await manager.broadcast_event("timer_sync", snapshot)
    return {"paused": False, "ends_at": ends_at}

@router.post("/admin/round/add-time")
async def add_time(seconds: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="seconds must be greater than zero")
    config = adjust_event_timer(db, seconds)
    snapshot = {**event_snapshot(db), "delta": seconds}
    ends_at = config.auction_timer_end
    db.close()
    await manager.broadcast_event("timer_sync", snapshot)
    return {"ends_at": ends_at, "delta": seconds}

@router.post("/admin/round/remove-time")
async def remove_time(seconds: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="seconds must be greater than zero")
    config = adjust_event_timer(db, -seconds)
    snapshot = {**event_snapshot(db), "delta": -seconds}
    ends_at = config.auction_timer_end
    db.close()
    await manager.broadcast_event("timer_sync", snapshot)
    return {"ends_at": ends_at, "delta": -seconds}

@router.post("/admin/round/end-bidding")
async def end_bidding(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = transition_event_state(db, "ROUND1_RESULT")
    snapshot = event_snapshot(db)
    state = config.state
    db.close()
    await manager.broadcast_event("auction_closed", snapshot)
    await manager.broadcast_event("event_state_changed", snapshot)
    return {"state": state, **snapshot}

@router.post("/admin/round/next-problem")
async def next_problem(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    """Close Round 1 for teams that already won a problem; move on."""
    config = transition_event_state(db, "ROUND1_RESULT")
    snapshot = event_snapshot(db)
    state = config.state
    db.close()
    await manager.broadcast_event("problem_revealed", snapshot)
    return {"state": state}
