from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.models import Bid, Team, ProblemStatement, GameConfig, WalletTransaction, EventConfig
from app.schemas.schemas import BidCreate, EVENT_STATES
from app.api.auth import get_current_user, get_current_active_admin
from app.api.websockets import manager
from app.services.event_service import (
    event_snapshot, get_or_create_game_config, get_or_create_event_config,
    get_team_for_user, ensure_leader, transition_event_state,
)

router = APIRouter()

def _assert_state(state: str, config: GameConfig, allowed: List[str]):
    if state not in allowed:
        raise HTTPException(status_code=409, detail=f"Action not allowed in state '{state}'. Allowed: {allowed}")

# ---------------------------------------------------------------- Bidding

@router.post("/bid")
async def place_bid(bid: BidCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    team = ensure_leader(db, current_user)
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)

    _assert_state(config.state, config, ["ROUND1_BIDDING"])

    if config.auction_timer_end and not config.timer_paused:
        end_time = config.auction_timer_end if config.auction_timer_end.tzinfo else config.auction_timer_end.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > end_time:
            raise HTTPException(status_code=400, detail="Bidding time has expired for this round.")

    # Row-level pessimistic locking for concurrency safety
    team = db.query(Team).filter(Team.id == team.id).with_for_update().first()
    ps = db.query(ProblemStatement).filter(ProblemStatement.id == bid.ps_id).with_for_update().first()
    if not ps or ps.status != "visible":
        raise HTTPException(status_code=400, detail="Invalid or unavailable Problem Statement")

    min_bid = event_config.round1_minimum_bid
    increment = event_config.round1_bid_increment

    if bid.amount > team.coins:
        raise HTTPException(status_code=400, detail="Bid cannot exceed the team wallet balance.")
    if bid.amount < min_bid:
        raise HTTPException(status_code=400, detail=f"Bid must be at least {min_bid} coins.")

    # 1. Single Problem Statement Check
    other_ps_bid = db.query(Bid).filter(
        Bid.team_id == team.id,
        Bid.ps_id != ps.id,
        Bid.round == config.current_round,
    ).first()
    if other_ps_bid:
        raise HTTPException(status_code=400, detail="You can only bid on one Problem Statement per round.")

    # 2. Incremental Bid Check
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

    # 3. Cooldown Delay Enforcement (5s Default)
    cooldown = getattr(event_config, "bid_cooldown_seconds", 5) or 0
    if cooldown > 0:
        latest_team_bid = db.query(Bid).filter(
            Bid.team_id == team.id,
            Bid.round == config.current_round,
        ).order_by(Bid.timestamp.desc()).first()
        if latest_team_bid and latest_team_bid.timestamp:
            ts = latest_team_bid.timestamp if latest_team_bid.timestamp.tzinfo else latest_team_bid.timestamp.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            elapsed = (now - ts).total_seconds()
            if elapsed < cooldown:
                remaining = int(cooldown - elapsed) + 1
                raise HTTPException(
                    status_code=400,
                    detail=f"Please wait {remaining} second(s) before placing another bid.",
                )

    now = datetime.now(timezone.utc)
    if existing_bid:
        existing_bid.amount = bid.amount
        existing_bid.timestamp = now
    else:
        db.add(Bid(team_id=team.id, ps_id=ps.id, amount=bid.amount, round=config.current_round, timestamp=now))

    db.commit()

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
        winners.append({"team": winner_team.team_name, "amount": bid.amount})

    if winners:
        ps.status = "allocated"
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
    config = get_or_create_game_config(db)
    # This semantic command intentionally permits skipping preview when the
    # organizer needs to recover a live event.
    config = transition_event_state(db, "ROUND1_BIDDING", validate=False)
    snapshot = event_snapshot(db)
    await manager.broadcast_event("event_state_changed", snapshot)
    return {"state": config.state, "ends_at": config.auction_timer_end, **snapshot}

@router.post("/admin/round/pause")
async def pause_timer(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = get_or_create_game_config(db)
    if config.timer_paused:
        return {"message": "Timer already paused", "paused": True}
    if not config.auction_timer_end:
        raise HTTPException(status_code=400, detail="No active timer")
    end_time = config.auction_timer_end if config.auction_timer_end.tzinfo else config.auction_timer_end.replace(tzinfo=timezone.utc)
    remaining = (end_time - datetime.now(timezone.utc)).total_seconds()
    config.timer_paused = True
    config.timer_paused_remaining_seconds = int(max(0, remaining))
    db.commit()
    await manager.broadcast_event("timer_sync", event_snapshot(db))
    return {"paused": True, "remaining_seconds": config.timer_paused_remaining_seconds}

@router.post("/admin/round/resume")
async def resume_timer(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = get_or_create_game_config(db)
    if not config.timer_paused:
        return {"message": "Timer is not paused", "paused": False}
    remaining = config.timer_paused_remaining_seconds or 0
    config.auction_timer_end = datetime.now(timezone.utc) + timedelta(seconds=remaining)
    config.timer_paused = False
    config.timer_paused_remaining_seconds = None
    db.commit()
    await manager.broadcast_event("timer_sync", event_snapshot(db))
    return {"paused": False, "ends_at": config.auction_timer_end}

@router.post("/admin/round/add-time")
async def add_time(seconds: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="seconds must be greater than zero")
    config = get_or_create_game_config(db)
    if not config.auction_timer_end:
        raise HTTPException(status_code=400, detail="No active timer")
    config.auction_timer_end = config.auction_timer_end + timedelta(seconds=seconds)
    config.timer_bias_seconds += seconds
    db.commit()
    await manager.broadcast_event("timer_sync", {**event_snapshot(db), "delta": seconds})
    return {"ends_at": config.auction_timer_end, "delta": seconds}

@router.post("/admin/round/remove-time")
async def remove_time(seconds: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="seconds must be greater than zero")
    config = get_or_create_game_config(db)
    if not config.auction_timer_end:
        raise HTTPException(status_code=400, detail="No active timer")
    config.auction_timer_end = config.auction_timer_end - timedelta(seconds=seconds)
    config.timer_bias_seconds -= seconds
    db.commit()
    await manager.broadcast_event("timer_sync", {**event_snapshot(db), "delta": -seconds})
    return {"ends_at": config.auction_timer_end, "delta": -seconds}

@router.post("/admin/round/end-bidding")
async def end_bidding(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = transition_event_state(db, "ROUND1_RESULT", validate=False)
    snapshot = event_snapshot(db)
    await manager.broadcast_event("auction_closed", snapshot)
    await manager.broadcast_event("event_state_changed", snapshot)
    return {"state": config.state, **snapshot}

@router.post("/admin/round/next-problem")
async def next_problem(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    """Close Round 1 for teams that already won a problem; move on."""
    config = transition_event_state(db, "ROUND1_RESULT", validate=False)
    await manager.broadcast_event("problem_revealed", event_snapshot(db))
    return {"state": config.state}
