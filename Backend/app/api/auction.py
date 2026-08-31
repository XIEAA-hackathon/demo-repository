from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.concurrency import run_in_threadpool
from typing import List

from app.core.database import SessionLocal, get_db
from app.models.models import Bid, Team, ProblemStatement, GameConfig, WalletTransaction, EventConfig, RoundControl, User
from app.schemas.schemas import BidCreate, EVENT_STATES
from app.api.auth import BidAuthClaims, get_bid_auth_claims, get_current_user, get_current_active_admin
from app.api.websockets import manager
from app.services.event_service import (
    event_snapshot, get_or_create_game_config, get_or_create_event_config,
    get_team_for_user, ensure_leader, transition_event_state,
    pause_event_timer, resume_event_timer, adjust_event_timer,
    get_or_create_round_control, _remaining_seconds,
)
from app.services.activity_log import record_event
from app.services.bid_cooldown import bid_cooldown_rejection
from app.services.participant_session import participant_session_needs_touch
from app.services.round1_assignment import (
    ROUND1_FINALIZATION_LOCK,
    ROUND1_PROBLEM_CAPACITY,
    update_round1_winning_bid_aggregate,
)

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class Round1BidResult:
    bid_id: int
    team_id: int
    team_name: str
    problem_id: int
    amount: int
    round_number: int
    timestamp: datetime
    cooldown_seconds: int
    auction_lock_wait_ms: float
    transaction_ms: float


class BidCooldownActive(RuntimeError):
    def __init__(self, remaining_seconds: float):
        super().__init__("Bid cooldown active")
        self.remaining_seconds = remaining_seconds


def _place_round1_bid_transaction(
    session_factory,
    *,
    email: str,
    session_id: str,
    problem_id: int,
    increment: int,
) -> Round1BidResult:
    """Commit one bid while holding only the auction row and bidding team row."""
    started_at = perf_counter()
    user_id: int | None = None
    with session_factory() as db:
        try:
            # This single row serializes price decisions for the active Round 1
            # auction. Finalization, rebids and assignments use the same first
            # lock, so MAX(amount) does not need to lock every Bid row.
            auction_lock_started_at = perf_counter()
            control = (
                db.query(RoundControl)
                .filter(RoundControl.round_type == "ROUND1")
                .with_for_update()
                .one_or_none()
            )
            auction_lock_wait_ms = (perf_counter() - auction_lock_started_at) * 1000
            if control is None:
                raise HTTPException(status_code=409, detail="Round 1 is not initialized.")

            # Validate the signed identity after any auction-lock wait so a
            # session revoked while queued cannot enter the price decision.
            user = (
                db.query(User)
                .filter(
                    User.email == email,
                    User.credentials_active.is_(True),
                    User.session_id == session_id,
                )
                .first()
            )
            if not user:
                raise HTTPException(status_code=401, detail="Session expired or was revoked. Please log in again.")
            if user.role != "leader":
                raise HTTPException(status_code=403, detail="Only the imported team leader can perform this action.")
            user_id = user.id
            team_id = user.team_id
            if team_id is None:
                team_id = db.query(Team.id).filter(Team.leader_id == user.id).scalar()
            if team_id is None:
                raise HTTPException(status_code=403, detail="No team is linked to your account.")

            config = db.query(GameConfig).order_by(GameConfig.id.asc()).first()
            event_config = db.query(EventConfig).order_by(EventConfig.id.asc()).first()
            if not config or not event_config:
                raise HTTPException(status_code=409, detail="Event configuration is unavailable.")
            if config.state != "ROUND1_BIDDING" or _remaining_seconds(config) == 0:
                raise HTTPException(status_code=409, detail="Round 1 bidding is not open.")

            problem = db.query(ProblemStatement).filter(ProblemStatement.id == problem_id).first()
            if (
                not problem
                or problem.id != control.current_problem_id
                or problem.status != "current"
                or control.status != "BIDDING"
            ):
                raise HTTPException(status_code=400, detail="Invalid or unavailable Problem Statement")

            # Team is the second and final row lock. It protects this team's
            # wallet, assignment state and cooldown against concurrent tabs.
            team = (
                db.query(Team)
                .filter(Team.id == team_id)
                .with_for_update()
                .populate_existing()
                .first()
            )
            if not team or team.leader_id != user.id:
                raise HTTPException(status_code=403, detail="Only the imported team leader can perform this action.")
            if team.round1_problem_id is not None or team.ps_id is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Your team already has a Round 1 problem and cannot participate in another Round 1 auction.",
                )

            round_number = config.current_round
            highest_amount = (
                db.query(func.max(Bid.amount))
                .filter(Bid.ps_id == problem.id, Bid.round == round_number)
                .scalar()
            )
            current_price = max(event_config.round1_minimum_bid, highest_amount or 0)
            next_amount = current_price + increment
            if next_amount > (team.coins or 0):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"A +{increment} bid would be {next_amount} coins and exceed "
                        f"the team wallet balance of {team.coins}."
                    ),
                )

            existing_bid = (
                db.query(Bid)
                .filter(
                    Bid.team_id == team.id,
                    Bid.ps_id == problem.id,
                    Bid.round == round_number,
                )
                .one_or_none()
            )
            cooldown = event_config.bid_cooldown_seconds or 0
            remaining = 0.0
            if existing_bid is not None:
                latest = existing_bid.timestamp
                if latest is not None:
                    latest_utc = latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc)
                    remaining = max(0.0, cooldown - (datetime.now(timezone.utc) - latest_utc).total_seconds())
            if remaining > 0:
                raise BidCooldownActive(remaining)

            now = datetime.now(timezone.utc)
            if existing_bid:
                bid_row = existing_bid
                bid_row.amount = next_amount
                bid_row.timestamp = now
            else:
                bid_row = Bid(
                    team_id=team.id,
                    ps_id=problem.id,
                    amount=next_amount,
                    round=round_number,
                    timestamp=now,
                )
                db.add(bid_row)
            record_event(
                db,
                "round1.bid_placed",
                actor=user,
                entity_type="team",
                entity_id=team.id,
                metadata={"problem_id": problem.id, "increment": increment, "amount": next_amount},
            )
            if participant_session_needs_touch(user.session_last_seen_at, now=now):
                user.session_last_seen_at = now
            db.flush()
            result_values = {
                "bid_id": bid_row.id,
                "team_id": team.id,
                "team_name": team.team_name,
                "problem_id": problem.id,
                "amount": next_amount,
                "round_number": round_number,
                "timestamp": now,
                "cooldown_seconds": cooldown,
                "auction_lock_wait_ms": auction_lock_wait_ms,
            }
            db.commit()
            return Round1BidResult(
                **result_values,
                transaction_ms=(perf_counter() - started_at) * 1000,
            )
        except (HTTPException, BidCooldownActive):
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            logger.info("Round 1 bid constraint conflict user_id=%s", user_id)
            raise HTTPException(status_code=409, detail="The bid changed concurrently. Refresh and retry.") from exc
        except OperationalError:
            db.rollback()
            logger.exception("Round 1 bid database operation failed user_id=%s", user_id)
            raise
        except Exception:
            db.rollback()
            raise

def _assert_state(state: str, config: GameConfig, allowed: List[str]):
    if state not in allowed:
        raise HTTPException(status_code=409, detail=f"Action not allowed in state '{state}'. Allowed: {allowed}")

# ---------------------------------------------------------------- Bidding

@router.post("/bid")
async def place_bid(
    request: Request,
    bid: BidCreate,
    response: Response,
    identity: BidAuthClaims = Depends(get_bid_auth_claims),
):
    request_started_at = perf_counter()
    session_factory = getattr(request.app.state, "session_factory", SessionLocal)

    try:
        result = await run_in_threadpool(
            _place_round1_bid_transaction,
            session_factory,
            email=identity.email,
            session_id=identity.session_id,
            problem_id=bid.ps_id,
            increment=bid.increment,
        )
    except BidCooldownActive as exc:
        return bid_cooldown_rejection(exc.remaining_seconds)

    payload = {
        "team_name": result.team_name,
        "team_id": result.team_id,
        "ps_id": result.problem_id,
        "amount": result.amount,
        "increment": bid.increment,
        "round": "ROUND1",
        "bid_id": result.bid_id,
        "timestamp": result.timestamp.isoformat(),
        "cooldown_seconds": result.cooldown_seconds,
    }
    queued = manager.publish_event("bid_updated", payload)
    response.headers["Server-Timing"] = (
        f"auction-lock;dur={result.auction_lock_wait_ms:.2f}, "
        f"db-transaction;dur={result.transaction_ms:.2f}"
    )
    logger.info(
        "Round 1 bid timing bid_id=%s team_id=%s auction_lock_wait_ms=%.2f "
        "transaction_ms=%.2f total_ms=%.2f broadcast_queued=%s",
        result.bid_id,
        result.team_id,
        result.auction_lock_wait_ms,
        result.transaction_ms,
        (perf_counter() - request_started_at) * 1000,
        queued,
    )
    return {
        "message": "Bid placed successfully. Coins are not deducted yet.",
        "bid_id": result.bid_id,
        "increment": bid.increment,
        "amount": result.amount,
        "cooldown_seconds": result.cooldown_seconds,
        "timestamp": result.timestamp.isoformat(),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }

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
        ).order_by(Bid.amount.desc(), Bid.timestamp.asc(), Bid.team_id.asc()).all()

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
