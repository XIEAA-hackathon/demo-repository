from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError
from typing import List

from app.core.database import get_db
from app.models.models import Bid, Team, ProblemStatement, GameConfig, WalletTransaction, EventConfig
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

router = APIRouter()

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

    if team.ps_id is not None:
        raise HTTPException(status_code=409, detail="Round 1 is complete for your team. Assigned teams cannot bid again.")

    ps = db.query(ProblemStatement).filter(ProblemStatement.id == bid.ps_id).first()
    control = get_or_create_round_control(db, "ROUND1")
    if not ps or ps.id != control.current_problem_id or ps.status != "current":
        raise HTTPException(status_code=400, detail="Invalid or unavailable Problem Statement")

    min_bid = event_config.round1_minimum_bid
    increment = event_config.round1_bid_increment

    if bid.amount > team.coins:
        raise HTTPException(status_code=400, detail="Bid cannot exceed the team wallet balance.")
    if bid.amount < min_bid:
        raise HTTPException(status_code=400, detail=f"Bid must be at least {min_bid} coins.")

    existing_bid = db.query(Bid).filter(
        Bid.team_id == team.id,
        Bid.ps_id == ps.id,
        Bid.round == config.current_round,
    ).first()
    if existing_bid and bid.amount < existing_bid.amount + increment:
        raise HTTPException(
            status_code=400,
            detail=f"New bid must be at least {increment} coin(s) higher than the current bid of {existing_bid.amount}.",
        )

    if existing_bid:
        existing_bid.amount = bid.amount
    else:
        db.add(Bid(team_id=team.id, ps_id=ps.id, amount=bid.amount, round=config.current_round))
    record_event(db, "round1.bid_placed", actor=current_user, entity_type="team", entity_id=team.id, metadata={"problem_id": ps.id, "amount": bid.amount})
    try:
        db.commit()
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The bid changed concurrently. Refresh and retry.") from exc

    await manager.broadcast_event("bid_updated", {
        "team_name": team.team_name,
        "team_id": team.id,
        "ps_id": ps.id,
        "amount": bid.amount,
    })
    return {"message": "Bid placed successfully. Coins are not deducted yet.", "amount": bid.amount}

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
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)
    winner_count = event_config.round1_winner_count

    ps = db.query(ProblemStatement).filter(ProblemStatement.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Problem Statement not found")
    if ps.status == "allocated":
        # idempotent: already finalized
        existing_winners = db.query(Team).filter(Team.ps_id == ps.id).all()
        return {
            "message": "Problem Statement already finalized.",
            "ps": ps.ps_number,
            "winners": [t.team_name for t in existing_winners],
        }

    top_bids = db.query(Bid).filter(
        Bid.ps_id == ps.id,
        Bid.round == config.current_round,
    ).order_by(Bid.amount.desc(), Bid.timestamp.asc()).limit(winner_count).all()

    winners = []
    for bid in top_bids:
        winner_team = db.query(Team).filter(Team.id == bid.team_id).first()
        if not winner_team or winner_team.ps_id is not None:
            continue  # team already has a problem; skip
        if winner_team.coins < bid.amount:
            continue

        # charge exactly once via explicit ledger entry
        winner_team.coins -= bid.amount
        db.add(WalletTransaction(
            team_id=winner_team.id,
            transaction_type="ROUND1_WIN",
            amount=-bid.amount,
            description=f"Round 1 auction win for {ps.ps_number}",
        ))
        winner_team.ps_id = ps.id
        winner_team.round1_problem_id = ps.id
        winners.append({"team": winner_team.team_name, "amount": bid.amount})

    if winners:
        ps.status = "allocated"
    record_event(db, "round1.auction_finalized", actor=current_user, entity_type="problem", entity_id=ps.id, metadata={"winner_count": len(winners)})
    db.commit()

    transition_event_state(db, "ROUND1_RESULT")

    await manager.broadcast_event("auction_finalized", {
        "ps_number": ps.ps_number,
        "winners": winners,
    })
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return {"message": "Round 1 finalized. Winners charged once.", "winners": winners}

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
    await manager.broadcast_event("event_state_changed", snapshot)
    return {"state": config.state, **snapshot}

@router.post("/admin/round/start-bidding")
async def start_bidding(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = transition_event_state(db, "ROUND1_BIDDING")
    snapshot = event_snapshot(db)
    await manager.broadcast_event("event_state_changed", snapshot)
    return {"state": config.state, "ends_at": config.auction_timer_end, **snapshot}

@router.post("/admin/round/pause")
async def pause_timer(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = pause_event_timer(db)
    await manager.broadcast_event("timer_sync", event_snapshot(db))
    return {"paused": True, "remaining_seconds": config.timer_paused_remaining_seconds}

@router.post("/admin/round/resume")
async def resume_timer(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = resume_event_timer(db)
    await manager.broadcast_event("timer_sync", event_snapshot(db))
    return {"paused": False, "ends_at": config.auction_timer_end}

@router.post("/admin/round/add-time")
async def add_time(seconds: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="seconds must be greater than zero")
    config = adjust_event_timer(db, seconds)
    await manager.broadcast_event("timer_sync", {**event_snapshot(db), "delta": seconds})
    return {"ends_at": config.auction_timer_end, "delta": seconds}

@router.post("/admin/round/remove-time")
async def remove_time(seconds: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="seconds must be greater than zero")
    config = adjust_event_timer(db, -seconds)
    await manager.broadcast_event("timer_sync", {**event_snapshot(db), "delta": -seconds})
    return {"ends_at": config.auction_timer_end, "delta": -seconds}

@router.post("/admin/round/end-bidding")
async def end_bidding(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = transition_event_state(db, "ROUND1_RESULT")
    snapshot = event_snapshot(db)
    await manager.broadcast_event("auction_closed", snapshot)
    await manager.broadcast_event("event_state_changed", snapshot)
    return {"state": config.state, **snapshot}

@router.post("/admin/round/next-problem")
async def next_problem(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    """Close Round 1 for teams that already won a problem; move on."""
    config = transition_event_state(db, "ROUND1_RESULT")
    await manager.broadcast_event("problem_revealed", event_snapshot(db))
    return {"state": config.state}
