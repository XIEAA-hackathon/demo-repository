from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.api.auth import get_current_active_admin, get_current_user
from app.api.websockets import manager
from app.core.database import get_db
from app.models.models import RoundControl, Team, Wildcard, WildcardBid
from app.schemas.schemas import BidIncrementRequest, WildcardEndTurnRequest, WildcardSlotRequest
from app.services.event_service import (
    _remaining_seconds,
    ensure_leader,
    event_snapshot,
    get_or_create_event_config,
    get_or_create_game_config,
    get_or_create_round_control,
    get_team_for_user,
    sync_expired_event_state,
    transition_event_state,
)
from app.services.activity_log import record_event
from app.services.bid_cooldown import bid_cooldown_rejection, bid_cooldown_remaining
from app.services.wildcard_service import (
    WildcardSelectionConflict,
    assign_wildcard_selection,
    available_wildcard_problems,
    current_selection,
    finalize_slot_bidding,
    reconcile_wildcard_selection,
    ranked_wildcard_bids,
    selection_remaining_seconds,
    sync_application_window,
    wildcard_payload,
)

router = APIRouter()


def _require_round_one_complete(db: Session) -> None:
    if not get_or_create_round_control(db, "ROUND1").ended:
        raise HTTPException(status_code=409, detail="End Round 1 before starting Wildcard.")


@router.post("/wildcard/apply")
async def apply_wildcard(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    team = ensure_leader(db, current_user)
    _require_round_one_complete(db)
    control = sync_application_window(db)
    game = get_or_create_game_config(db)
    if not get_or_create_event_config(db).wildcard_enabled:
        raise HTTPException(status_code=400, detail="Wildcard round is disabled.")
    if control.status != "APPLICATIONS_OPEN" or not control.applications_open or _remaining_seconds(game) == 0:
        raise HTTPException(status_code=409, detail="Wildcard applications are closed.")

    record = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()
    if record and record.status == "applied":
        return {"message": "Wildcard application already confirmed."}
    record = record or Wildcard(team_id=team.id, coins_paid=0)
    record.status = "applied"
    record.applied_at = datetime.utcnow()
    record.rank = None
    record.winning_bid = None
    record.problem_id = None
    record.selected_at = None
    record.used = False
    db.add(record)
    record_event(db, "wildcard.application_confirmed", actor=current_user, entity_type="team", entity_id=team.id)
    db.commit()
    await manager.broadcast_event("wildcard_updated", {"team_name": team.team_name, "action": "applied"})
    return {"message": "Wildcard application confirmed."}


@router.post("/wildcard/decline")
async def decline_wildcard(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    team = ensure_leader(db, current_user)
    _require_round_one_complete(db)
    control = sync_application_window(db)
    if control.status != "APPLICATIONS_OPEN" or not control.applications_open:
        raise HTTPException(status_code=409, detail="Wildcard applications are closed.")
    record = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()
    if record and record.status == "applied":
        raise HTTPException(status_code=409, detail="Your team already applied for Wildcard.")
    record = record or Wildcard(team_id=team.id, coins_paid=0)
    record.status = "declined"
    db.add(record)
    record_event(db, "wildcard.application_declined", actor=current_user, entity_type="team", entity_id=team.id)
    db.commit()
    await manager.broadcast_event("wildcard_updated", {"team_name": team.team_name, "action": "declined"})
    return {"message": "Wildcard participation declined."}


@router.get("/wildcard/status")
def get_wildcard_status(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    reconcile_wildcard_selection(db)
    control = sync_application_window(db)
    team = get_team_for_user(db, current_user)
    record = db.query(Wildcard).filter(Wildcard.team_id == team.id).first() if team else None
    active = current_selection(db)
    return {
        "visible": control.status != "NOT_STARTED",
        "enabled": get_or_create_event_config(db).wildcard_enabled,
        "state": control.status,
        "wildcard_slots": control.slot_count,
        "applied": bool(record and record.status in {"applied", "qualified", "selected", "eliminated"}),
        "status": record.status if record else None,
        "rank": record.rank if record else None,
        "winning_bid": record.winning_bid if record else None,
        "problem_id": record.problem_id if record else None,
        "selection_method": record.selection_method if record else None,
        "current_selection_rank": active[0].rank if active else None,
        "current_selection_team": active[1].team_name if active else None,
        "is_selection_turn": bool(active and team and active[1].id == team.id),
        "available_problem_count": len(available_wildcard_problems(db)),
        "selection_started_at": control.selection_started_at,
        "selection_ends_at": control.selection_ends_at,
        "selection_duration_seconds": control.selection_duration_seconds,
        "selection_remaining_seconds": selection_remaining_seconds(control),
    }


@router.post("/admin/rounds/wildcard/slots")
async def confirm_wildcard_slots(
    request: WildcardSlotRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_admin),
):
    control = sync_application_window(db)
    if control.status != "APPLICATIONS_CLOSED":
        raise HTTPException(status_code=409, detail="Close Wildcard applications before confirming slots.")
    if control.slot_count is not None:
        if control.slot_count == request.slots:
            return wildcard_payload(db)
        raise HTTPException(status_code=409, detail=f"Wildcard slots are already confirmed at {control.slot_count}.")
    applicants = db.query(Wildcard).filter(Wildcard.status == "applied").count()
    problem_count = len(available_wildcard_problems(db))
    maximum = min(applicants, problem_count)
    if request.slots > maximum:
        raise HTTPException(
            status_code=422,
            detail=f"Wildcard slots cannot exceed {maximum} (applicants: {applicants}, available problems: {problem_count}).",
        )
    control.slot_count = request.slots
    get_or_create_event_config(db).wildcard_slots = request.slots
    record_event(db, "wildcard.slots_confirmed", actor=current_user, metadata={"slot_count": request.slots})
    db.commit()
    await manager.broadcast_event("wildcard_updated", {"action": "slots_confirmed", "slots": request.slots})
    return wildcard_payload(db)


@router.post("/admin/rounds/wildcard/bidding/start")
async def start_wildcard_slot_bidding(db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    control = sync_application_window(db)
    if control.status == "BIDDING_OPEN":
        return wildcard_payload(db)
    if control.status != "APPLICATIONS_CLOSED" or not control.slot_count:
        raise HTTPException(status_code=409, detail="Confirm the number of Wildcard slots before bidding.")
    control.status = "BIDDING_OPEN"
    control.applications_open = False
    transition_event_state(db, "WILDCARD_BIDDING", validate=False, restart=True)
    record_event(db, "wildcard.bidding_started", actor=current_user, metadata={"slot_count": control.slot_count})
    db.commit()
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return wildcard_payload(db)


@router.post("/wildcard/bid")
async def place_wildcard_bid(
    request: BidIncrementRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    team = ensure_leader(db, current_user)
    sync_expired_event_state(db)
    get_or_create_round_control(db, "WILDCARD")
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").with_for_update().one()
    game = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)
    if control.status != "BIDDING_OPEN" or game.state != "WILDCARD_BIDDING" or _remaining_seconds(game) == 0:
        raise HTTPException(status_code=409, detail="Wildcard slot bidding is not open.")
    application = db.query(Wildcard).filter(Wildcard.team_id == team.id, Wildcard.status == "applied").first()
    if not application:
        raise HTTPException(status_code=403, detail="Only teams that applied may bid for a Wildcard slot.")
    team = db.query(Team).filter(Team.id == team.id).with_for_update().first()
    auction_bids = db.query(WildcardBid).with_for_update().all()
    current_price = max(
        [event_config.wildcard_starting_bid, *(row.amount for row in auction_bids)],
    )
    next_amount = current_price + request.increment
    if next_amount > team.coins:
        raise HTTPException(
            status_code=400,
            detail=f"A +{request.increment} bid would be {next_amount} coins and exceed the team wallet balance of {team.coins}.",
        )
    bid = next((row for row in auction_bids if row.team_id == team.id), None)

    cooldown = event_config.bid_cooldown_seconds or 0
    remaining = bid_cooldown_remaining(db, team.id, cooldown, round_type="WILDCARD")
    if remaining > 0:
        return bid_cooldown_rejection(remaining)

    now = datetime.now(timezone.utc)
    if bid:
        bid.amount = next_amount
        bid.timestamp = now
    else:
        db.add(WildcardBid(team_id=team.id, amount=next_amount, timestamp=now))
    record_event(db, "wildcard.bid_placed", actor=current_user, entity_type="team", entity_id=team.id, metadata={"increment": request.increment, "amount": next_amount})
    try:
        db.commit()
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The wildcard bid changed concurrently. Refresh and retry.") from exc

    leaderboard = [
        {"rank": rank, "team_id": ranked_team.id, "team_name": ranked_team.team_name, "amount": ranked_bid.amount}
        for rank, (ranked_bid, ranked_team, _application) in enumerate(ranked_wildcard_bids(db), start=1)
    ]
    payload = {
        "team_name": team.team_name,
        "team_id": team.id,
        "amount": next_amount,
        "round": "WILDCARD",
        "leaderboard": leaderboard,
    }
    db.close()
    await manager.broadcast_event("wildcard_bid_updated", payload)
    return {"message": "Wildcard slot bid placed. Coins are deducted only if the team qualifies.", "increment": request.increment, "amount": next_amount}


@router.post("/admin/rounds/wildcard/bidding/close")
async def close_wildcard_slot_bidding(db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    sync_expired_event_state(db)
    control = get_or_create_round_control(db, "WILDCARD")
    if control.status in {"PROBLEM_SELECTION", "COMPLETE"}:
        winners = finalize_slot_bidding(db, control)
        return {"winners": winners, **wildcard_payload(db)}
    if control.status not in {"BIDDING_OPEN", "BIDDING_CLOSED"}:
        raise HTTPException(status_code=409, detail="Wildcard slot bidding is not active.")
    control.status = "BIDDING_CLOSED"
    game = get_or_create_game_config(db)
    game.auction_timer_end = None
    game.timer_paused = False
    game.timer_paused_remaining_seconds = None
    try:
        winners = finalize_slot_bidding(db, control, commit=False)
        transition_event_state(db, "WILDCARD_SELECTION", validate=False, commit=False)
        record_event(db, "wildcard.bidding_finalized", actor=current_user, metadata={"winner_count": len(winners)})
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await manager.broadcast_event("wildcard_updated", {"action": "bidding_finalized", "winners": winners})
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return {"winners": winners, **wildcard_payload(db)}


@router.post("/admin/wildcard/finalize")
async def finalize_wildcard_alias(db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    return await close_wildcard_slot_bidding(db, current_user)


@router.post("/admin/rounds/wildcard/end")
async def end_wildcard(db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    control = get_or_create_round_control(db, "WILDCARD")
    if control.ended:
        return wildcard_payload(db)

    applications = db.query(Wildcard).filter(Wildcard.status.in_(("applied", "qualified", "selected", "eliminated"))).count()
    winners = db.query(Wildcard).filter(Wildcard.status.in_(("qualified", "selected"))).count()
    selections = db.query(Wildcard).filter(Wildcard.status == "selected", Wildcard.problem_id.is_not(None)).count()
    control.ended = True
    control.status = "COMPLETE"
    control.applications_open = False
    control.current_problem_id = None
    control.current_selection_rank = None
    control.selection_started_at = None
    control.selection_ends_at = None
    transition_event_state(db, "CODING", validate=False, commit=False)
    record_event(db, "wildcard.manually_ended", actor=current_user, metadata={
        "application_count": applications,
        "winner_count": winners,
        "completed_selection_count": selections,
    })
    db.commit()
    snapshot = event_snapshot(db)
    response = wildcard_payload(db)
    db.close()
    await manager.broadcast_event("wildcard_ended", {
        "manual": True,
        "application_count": applications,
        "winner_count": winners,
        "completed_selection_count": selections,
    })
    await manager.broadcast_event("event_state_changed", snapshot)
    return response


@router.post("/wildcard/select/{ps_id}")
async def select_wildcard_problem(ps_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    team = ensure_leader(db, current_user)
    try:
        result = assign_wildcard_selection(
            db,
            method="manual",
            team_id=team.id,
            problem_id=ps_id,
            actor=current_user,
        )
    except WildcardSelectionConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That Wildcard problem was selected concurrently.") from exc

    await manager.broadcast_event("wildcard_updated", {
        "team_name": team.team_name,
        "problem_id": result["problem"]["id"],
        "action": "problem_selected" if result["method"] == "manual" else "selection_timeout",
    })
    control = get_or_create_round_control(db, "WILDCARD")
    if control.status == "COMPLETE":
        await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return {
        "message": f"Wildcard Problem {result['problem']['problem_number']} selected.",
        "problem": result["problem"],
        "selection_method": result["method"],
        "wildcard_status": control.status,
    }


@router.post("/admin/rounds/wildcard/selection/end-turn")
async def end_wildcard_selection_turn(
    request: WildcardEndTurnRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_admin),
):
    try:
        result = assign_wildcard_selection(
            db,
            method="admin_end_turn",
            expected_rank=request.expected_rank,
            expected_team_id=request.expected_team_id,
            actor=current_user,
        )
    except WildcardSelectionConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The Wildcard turn changed concurrently.") from exc

    await manager.broadcast_event("wildcard_updated", {
        "team_name": result["team_name"],
        "problem_id": result["problem"]["id"],
        "action": result["method"],
    })
    control = get_or_create_round_control(db, "WILDCARD")
    if control.status == "COMPLETE":
        await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return {"assignment": result, **wildcard_payload(db)}
