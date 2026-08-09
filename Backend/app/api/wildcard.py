from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.models import Team, Wildcard, GameConfig, ProblemStatement, Bid, WalletTransaction
from app.api.auth import get_current_user, get_current_active_admin
from app.api.websockets import manager
from app.services.event_service import (
    event_snapshot, get_or_create_game_config, get_or_create_event_config,
    ensure_leader, transition_event_state,
)

router = APIRouter()

# ---------------------------------------------------------------- Application

@router.post("/wildcard/apply")
async def apply_wildcard(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    team = ensure_leader(db, current_user)
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)

    if not event_config.wildcard_enabled:
        raise HTTPException(status_code=400, detail="Wildcard round is disabled.")
    if config.state not in ("WILDCARD_APPLICATION", "WILDCARD_PREVIEW", "WILDCARD_BIDDING"):
        raise HTTPException(status_code=409, detail=f"Wildcard application is not open (state: {config.state}).")

    # A team without a problem cannot apply; also teams that already have a wildcard record skip.
    existing = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()
    if existing and existing.status != "bid":
        raise HTTPException(status_code=400, detail="Your team already has a wildcard record.")

    record = existing or Wildcard(team_id=team.id, coins_paid=0, status="bid")
    if not existing:
        db.add(record)
    db.commit()

    await manager.broadcast_event("wildcard_updated", {
        "team_name": team.team_name,
        "action": "applied",
    })
    return {"message": "Wildcard application confirmed."}

@router.get("/wildcard/status")
def get_wildcard_status(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)
    team = None
    from app.services.event_service import get_team_for_user
    team = get_team_for_user(db, current_user)

    record = None
    if team:
        record = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()

    return {
        "visible": config.state in ("WILDCARD_APPLICATION", "WILDCARD_PREVIEW", "WILDCARD_BIDDING", "WILDCARD_SELECTION"),
        "enabled": event_config.wildcard_enabled,
        "state": config.state,
        "wildcard_slots": event_config.wildcard_slots,
        "applied": record is not None,
        "status": record.status if record else None,
        "used": record.used if record else False,
    }

# ---------------------------------------------------------------- Wildcard Bidding

@router.post("/wildcard/bid")
async def place_wildcard_bid(ps_id: int, amount: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    team = ensure_leader(db, current_user)
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)

    if not event_config.wildcard_enabled:
        raise HTTPException(status_code=400, detail="Wildcard round is disabled.")
    if config.state != "WILDCARD_BIDDING":
        raise HTTPException(status_code=409, detail=f"Wildcard bidding is not open (state: {config.state}).")

    ps = db.query(ProblemStatement).filter(ProblemStatement.id == ps_id).first()
    if not ps or ps.round != 2 or ps.status != "visible":
        raise HTTPException(status_code=400, detail="Invalid or unavailable Wildcard problem.")

    starting = event_config.wildcard_starting_bid
    increment = event_config.wildcard_bid_increment
    if amount > team.coins:
        raise HTTPException(status_code=400, detail="Bid cannot exceed the team wallet balance.")
    if amount < starting:
        raise HTTPException(status_code=400, detail=f"Wildcard bid must be at least {starting} coins.")

    existing_bid = db.query(Bid).filter(
        Bid.team_id == team.id, Bid.ps_id == ps.id, Bid.round == 2,
    ).first()
    if existing_bid and amount < existing_bid.amount + increment:
        raise HTTPException(
            status_code=400,
            detail=f"New wildcard bid must be at least {increment} coin(s) higher than {existing_bid.amount}.",
        )

    record = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()
    if record and record.status != "bid":
        raise HTTPException(status_code=400, detail="Your team already owns a wildcard outcome.")

    if existing_bid:
        existing_bid.amount = amount
    else:
        db.add(Bid(team_id=team.id, ps_id=ps.id, amount=amount, round=2))

    if not record:
        db.add(Wildcard(team_id=team.id, coins_paid=0, status="bid"))
    db.commit()

    await manager.broadcast_event("bid_updated", {
        "team_name": team.team_name,
        "team_id": team.id,
        "ps_id": ps.id,
        "amount": amount,
        "round": "WILDCARD",
    })
    return {"message": "Wildcard bid placed. Coins are not deducted yet.", "amount": amount}

@router.post("/admin/wildcard/finalize")
async def finalize_wildcard(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    """Top N bidders (N = EventConfig.wildcard_slots) win the wildcard auction."""
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)
    slots = event_config.wildcard_slots

    top_bids = db.query(Bid).filter(Bid.round == 2).order_by(Bid.amount.desc(), Bid.timestamp.asc()).limit(slots).all()

    winners = []
    for bid in top_bids:
        team = db.query(Team).filter(Team.id == bid.team_id).first()
        record = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()
        if record and record.status in ("won", "selected"):
            continue
        # winner must still switch from original problem at selection time; mark won now
        record = record or Wildcard(team_id=team.id)
        record.status = "won"
        record.coins_paid = bid.amount
        db.add(record)
        winners.append({"team": team.team_name, "amount": bid.amount})

    db.commit()
    transition_event_state(db, "WILDCARD_SELECTION", validate=False)

    await manager.broadcast_event("wildcard_updated", {
        "action": "finalized",
        "winners": winners,
    })
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return {"message": "Wildcard round finalized.", "winners": winners}

@router.post("/wildcard/select/{ps_id}")
async def select_wildcard_problem(ps_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Winner picks a Bonus Problem in ranking order. Must switch from original PS.
    Selected problem becomes unavailable to later winners."""
    team = ensure_leader(db, current_user)
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)

    if config.state != "WILDCARD_SELECTION":
        raise HTTPException(status_code=409, detail=f"Wildcard selection is not open (state: {config.state}).")

    record = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()
    if not record or record.status != "won":
        raise HTTPException(status_code=403, detail="Only wildcard winners can select a Bonus Problem.")
    if record.used or record.status == "selected":
        raise HTTPException(status_code=400, detail="Your team already selected a Bonus Problem.")
    if not team.ps_id:
        raise HTTPException(status_code=400, detail="Your team has no original problem to switch from.")

    ps = db.query(ProblemStatement).filter(ProblemStatement.id == ps_id).first()
    if not ps or ps.round != 2 or ps.status != "visible":
        raise HTTPException(status_code=400, detail="Invalid or already-selected Bonus Problem.")

    # rank check: process in descending bid order; a lower-ranked winner may not steal a problem
    winning_bids = db.query(Bid).filter(Bid.round == 2).order_by(Bid.amount.desc(), Bid.timestamp.asc()).all()
    rank_team_ids = []
    for bid in winning_bids:
        if bid.team_id not in rank_team_ids:
            rank_team_ids.append(bid.team_id)
    if team.id not in rank_team_ids:
        raise HTTPException(status_code=403, detail="Your team is not a wildcard winner.")

    # previous winners selecting this problem get priority (first come, first served in rank order)
    already_selected = db.query(Wildcard).filter(
        Wildcard.status == "selected", Wildcard.used.is_(True),
    ).all()
    for other in already_selected:
        other_team = db.query(Team).filter(Team.id == other.team_id).first()
        if other_team and other_team.ps_id == ps.id:
            raise HTTPException(status_code=400, detail="That Bonus Problem was already selected by another team.")

    # --- commit the switch in a single transaction; the allocated status
    # prevents other winners from selecting the same problem ---
    team.ps_id = ps.id
    ps.status = "allocated"
    record.status = "selected"
    record.used = True

    # deduct the wildcard bid exactly once
    wildcard_bid = db.query(Bid).filter(Bid.team_id == team.id, Bid.round == 2).first()
    if wildcard_bid:
        team.coins -= wildcard_bid.amount
        db.add(WalletTransaction(
            team_id=team.id,
            transaction_type="WILDCARD_WIN",
            amount=-wildcard_bid.amount,
            description="Wildcard auction win",
        ))
    db.commit()

    await manager.broadcast_event("wildcard_updated", {
        "team_name": team.team_name,
        "ps_number": ps.ps_number,
        "action": "selected",
    })
    return {"message": f"Bonus Problem {ps.ps_number} selected. Your team switched problems.", "ps": ps.ps_number}
