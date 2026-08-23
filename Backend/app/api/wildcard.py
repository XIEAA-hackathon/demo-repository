from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.api.auth import get_current_active_admin, get_current_user
from app.api.websockets import manager
from app.core.database import get_db
from app.models.models import ProblemStatement, Team, Wildcard, WildcardBid, WildcardSelectionPool
from app.schemas.schemas import WildcardSlotRequest
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
    available_wildcard_problems,
    current_selection,
    finalize_slot_bidding,
    problem_payload,
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
        "current_selection_rank": active[0].rank if active else None,
        "current_selection_team": active[1].team_name if active else None,
        "is_selection_turn": bool(active and team and active[1].id == team.id),
        "available_problem_count": len(available_wildcard_problems(db)),
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
    amount: int,
    ps_id: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    del ps_id  # Ignored compatibility parameter from the retired problem auction.
    team = ensure_leader(db, current_user)
    sync_expired_event_state(db)
    control = get_or_create_round_control(db, "WILDCARD")
    game = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)
    if control.status != "BIDDING_OPEN" or game.state != "WILDCARD_BIDDING" or _remaining_seconds(game) == 0:
        raise HTTPException(status_code=409, detail="Wildcard slot bidding is not open.")
    application = db.query(Wildcard).filter(Wildcard.team_id == team.id, Wildcard.status == "applied").first()
    if not application:
        raise HTTPException(status_code=403, detail="Only teams that applied may bid for a Wildcard slot.")
    if amount > team.coins:
        raise HTTPException(status_code=400, detail="Bid cannot exceed the team wallet balance.")
    if amount < event_config.wildcard_starting_bid:
        raise HTTPException(status_code=400, detail=f"Wildcard bid must be at least {event_config.wildcard_starting_bid} coins.")

    team = db.query(Team).filter(Team.id == team.id).with_for_update().first()
    bid = db.query(WildcardBid).filter(WildcardBid.team_id == team.id).with_for_update().first()
    if bid and amount < bid.amount + event_config.wildcard_bid_increment:
        raise HTTPException(
            status_code=400,
            detail=f"New wildcard bid must be at least {event_config.wildcard_bid_increment} coin(s) higher than {bid.amount}.",
        )

    cooldown = event_config.bid_cooldown_seconds or 0
    remaining = bid_cooldown_remaining(db, team.id, cooldown, round_type="WILDCARD")
    if remaining > 0:
        return bid_cooldown_rejection(remaining)

    now = datetime.now(timezone.utc)
    if bid:
        bid.amount = amount
        bid.timestamp = now
    else:
        db.add(WildcardBid(team_id=team.id, amount=amount, timestamp=now))
    record_event(db, "wildcard.bid_placed", actor=current_user, entity_type="team", entity_id=team.id, metadata={"amount": amount})
    db.commit()
    await manager.broadcast_event("wildcard_bid_updated", {
        "team_name": team.team_name,
        "team_id": team.id,
        "amount": amount,
        "round": "WILDCARD",
    })
    return {"message": "Wildcard slot bid placed. Coins are deducted only if the team qualifies.", "amount": amount}


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


@router.post("/wildcard/select/{ps_id}")
async def select_wildcard_problem(ps_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    team = ensure_leader(db, current_user)
    control = get_or_create_round_control(db, "WILDCARD")
    if control.status != "PROBLEM_SELECTION":
        raise HTTPException(status_code=409, detail=f"Wildcard problem selection is not open (state: {control.status}).")

    active = (
        db.query(Wildcard, Team)
        .join(Team, Team.id == Wildcard.team_id)
        .filter(Wildcard.status == "qualified", Wildcard.problem_id.is_(None))
        .order_by(Wildcard.rank.asc())
        .with_for_update()
        .first()
    )
    if not active or active[1].id != team.id:
        waiting_for = active[1].team_name if active else "the current winner"
        raise HTTPException(status_code=409, detail=f"Wait for {waiting_for} to select a problem.")

    problem = (
        db.query(ProblemStatement)
        .join(WildcardSelectionPool, WildcardSelectionPool.problem_id == ProblemStatement.id)
        .filter(
            ProblemStatement.id == ps_id,
            ProblemStatement.round == 2,
            ProblemStatement.status.in_(("available", "visible")),
            WildcardSelectionPool.selected_by_team_id.is_(None),
        )
        .with_for_update()
        .first()
    )
    if not problem:
        raise HTTPException(status_code=409, detail="That Wildcard problem is unavailable or was already selected.")

    record = active[0]
    try:
        claimed = (
            db.query(Wildcard)
            .filter(Wildcard.id == record.id, Wildcard.status == "qualified", Wildcard.problem_id.is_(None))
            .update({
                Wildcard.status: "selected",
                Wildcard.problem_id: problem.id,
                Wildcard.selected_at: datetime.utcnow(),
                Wildcard.used: True,
            }, synchronize_session=False)
        )
        reserved = (
            db.query(ProblemStatement)
            .filter(
                ProblemStatement.id == problem.id,
                ProblemStatement.round == 2,
                ProblemStatement.status.in_(("available", "visible")),
            )
            .update({ProblemStatement.status: "allocated"}, synchronize_session=False)
        )
        pool_reserved = (
            db.query(WildcardSelectionPool)
            .filter(
                WildcardSelectionPool.problem_id == problem.id,
                WildcardSelectionPool.selected_by_team_id.is_(None),
            )
            .update({
                WildcardSelectionPool.selected_by_team_id: team.id,
                WildcardSelectionPool.selected_at: datetime.utcnow(),
            }, synchronize_session=False)
        )
        if claimed != 1 or reserved != 1 or pool_reserved != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="The selection changed concurrently. Reload and try again.")

        if team.round1_problem_id is None and team.ps_id:
            previous = db.query(ProblemStatement).filter(ProblemStatement.id == team.ps_id).first()
            if previous and previous.round == 1:
                team.round1_problem_id = previous.id
        team.wildcard_problem_id = problem.id
        team.ps_id = problem.id

        remaining = db.query(Wildcard).filter(
            Wildcard.id != record.id,
            Wildcard.status == "qualified",
            Wildcard.problem_id.is_(None),
        ).count()
        if remaining == 0:
            control.status = "COMPLETE"
            control.ended = True
        record_event(
            db,
            "wildcard.problem_selected",
            actor=current_user,
            entity_type="problem",
            entity_id=problem.id,
            metadata={"team_id": team.id, "rank": record.rank},
        )
        db.commit()
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That Wildcard problem was selected concurrently.") from exc

    await manager.broadcast_event("wildcard_updated", {
        "team_name": team.team_name,
        "problem_id": problem.id,
        "action": "problem_selected",
    })
    if control.status == "COMPLETE":
        await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return {
        "message": f"Wildcard Problem {problem_payload(problem)['problem_number']} selected.",
        "problem": problem_payload(problem),
        "wildcard_status": control.status,
    }
