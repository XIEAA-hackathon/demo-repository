from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from app.core.database import get_db
from app.models.models import Bid, Team, ProblemStatement, GameConfig
from app.schemas.schemas import BidCreate, BidResponse
from app.api.auth import get_current_user, get_current_active_admin
from app.api.websockets import manager

router = APIRouter()

@router.post("/bid")
async def place_bid(bid: BidCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.role != "leader":
        raise HTTPException(status_code=403, detail="Only team leaders can bid")
    
    team = db.query(Team).filter(Team.leader_id == current_user.id).first()
    config = db.query(GameConfig).first()
    
    if not team.is_approved:
        raise HTTPException(status_code=403, detail="Team not approved")
    
    ps = db.query(ProblemStatement).filter(ProblemStatement.id == bid.ps_id).first()
    if not ps or ps.status != "visible":
        raise HTTPException(status_code=400, detail="Invalid or unavailable Problem Statement")
        
    if bid.amount > team.coins:
        raise HTTPException(status_code=400, detail="Insufficient coins")
    if bid.amount < 25 or bid.amount > 75:
        raise HTTPException(status_code=400, detail="Bid amount must be between 25 and 75 coins")
        
    # Overwrite previous bid for this team and PS in this round, or just add a new one?
    # Usually we just add a new one, but to prevent spam, we can update if exists.
    existing_bid = db.query(Bid).filter(
        Bid.team_id == team.id, 
        Bid.ps_id == ps.id, 
        Bid.round == config.current_round
    ).first()
    
    if existing_bid:
        existing_bid.amount = bid.amount
    else:
        new_bid = Bid(team_id=team.id, ps_id=ps.id, amount=bid.amount, round=config.current_round)
        db.add(new_bid)
    
    db.commit()
    
    await manager.broadcast_json({
        "type": "new_bid",
        "team_name": team.team_name,
        "ps_number": ps.ps_number,
        "amount": bid.amount
    })
    return {"message": "Bid placed successfully. Coins are not deducted yet."}

@router.get("/bid-history")
def get_bid_history(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    bids = db.query(Bid).all()
    return bids

@router.post("/admin/start-round")
async def start_round(duration_minutes: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    from datetime import datetime, timedelta
    config = db.query(GameConfig).first()
    if not config:
        config = GameConfig(current_round=1)
        db.add(config)
    
    config.auction_timer_end = datetime.utcnow() + timedelta(minutes=duration_minutes)
    db.commit()
    
    await manager.broadcast_json({
        "type": "round_started",
        "round": config.current_round,
        "duration": duration_minutes
    })
    return {"message": f"Round {config.current_round} started for {duration_minutes} minutes."}

@router.post("/admin/end-round")
async def end_round(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = db.query(GameConfig).first()
    
    # 1. Get all PS that are visible
    visible_pss = db.query(ProblemStatement).filter(ProblemStatement.status == "visible").all()
    
    results = []
    for ps in visible_pss:
        # Find highest 5 bids for this PS in this round
        top_bids = db.query(Bid).filter(
            Bid.ps_id == ps.id,
            Bid.round == config.current_round
        ).order_by(Bid.amount.desc()).limit(5).all()
        
        winners = []
        for bid in top_bids:
            winner_team = db.query(Team).filter(Team.id == bid.team_id).first()
            if winner_team.coins >= bid.amount and winner_team.ps_id is None:
                # Deduct coins and assign PS
                winner_team.coins -= bid.amount
                winner_team.ps_id = ps.id
                winners.append({"team": winner_team.team_name, "amount": bid.amount})
                
        if winners:
            ps.status = "allocated"
            results.append({"ps": ps.ps_number, "winners": winners})
                
    config.current_round += 1
    db.commit()
    
    await manager.broadcast_json({
        "type": "round_ended",
        "results": results
    })
    return {"message": "Round ended. Winners allocated.", "results": results}

@router.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    teams = db.query(Team).order_by(Team.coins.desc()).all()
    result = []
    for t in teams:
        ps = db.query(ProblemStatement).filter(ProblemStatement.id == t.ps_id).first()
        result.append({
            "team_name": t.team_name,
            "coins": t.coins,
            "allocated_ps": ps.ps_number if ps else "Not Assigned"
        })
    return result
