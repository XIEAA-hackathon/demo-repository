from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Team, Wildcard, ExchangeRequest, GameConfig, ProblemStatement
from app.api.auth import get_current_user, get_current_active_admin
from pydantic import BaseModel

router = APIRouter()

class ExchangeRequestCreate(BaseModel):
    receiver_team_id: int

@router.put("/admin/wildcard-visibility")
def toggle_wildcard_visibility(visible: bool, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    config = db.query(GameConfig).first()
    if not config:
        config = GameConfig(wildcards_visible=visible)
        db.add(config)
    else:
        config.wildcards_visible = visible
    db.commit()
    return {"message": f"Wildcards visibility set to {visible}"}

@router.get("/wildcards/status")
def get_wildcard_status(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    config = db.query(GameConfig).first()
    if not config or not config.wildcards_visible:
        return {"visible": False, "message": "Wildcard round is not active yet."}
    
    # We can also return the list of teams who bought wildcards or total wildcards bought
    total_wildcards = db.query(Wildcard).count()
    return {"visible": True, "remaining": max(0, 5 - total_wildcards)}

@router.post("/buy-wildcard")
def buy_wildcard(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.role != "leader":
        raise HTTPException(status_code=403, detail="Only leaders can buy wildcards")
        
    config = db.query(GameConfig).first()
    if not config or not config.wildcards_visible:
        raise HTTPException(status_code=400, detail="Wildcard round is not active")

    total_wildcards = db.query(Wildcard).count()
    if total_wildcards >= 5:
        raise HTTPException(status_code=400, detail="No more wildcards available")
        
    team = db.query(Team).filter(Team.leader_id == current_user.id).first()
    
    if db.query(Wildcard).filter(Wildcard.team_id == team.id).first():
        raise HTTPException(status_code=400, detail="Your team already has a wildcard")
        
    wildcard_cost = 200 # example cost
    if team.coins < wildcard_cost:
        raise HTTPException(status_code=400, detail="Not enough coins to buy wildcard")
        
    team.coins -= wildcard_cost
    new_wc = Wildcard(team_id=team.id, coins_paid=wildcard_cost)
    db.add(new_wc)
    db.commit()
    
    return {"message": "Wildcard purchased successfully"}

@router.post("/request-exchange")
def request_exchange(req: ExchangeRequestCreate, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    team = db.query(Team).filter(Team.leader_id == current_user.id).first()
    wildcard = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()
    
    if not wildcard or wildcard.used:
        raise HTTPException(status_code=400, detail="You do not have a valid wildcard")
        
    receiver_team = db.query(Team).filter(Team.id == req.receiver_team_id).first()
    if not receiver_team:
        raise HTTPException(status_code=404, detail="Receiver team not found")
        
    if not team.ps_id or not receiver_team.ps_id:
        raise HTTPException(status_code=400, detail="Both teams must have an allocated PS to exchange")
        
    exchange = ExchangeRequest(
        requester_team_id=team.id,
        receiver_team_id=receiver_team.id,
        requester_ps_id=team.ps_id,
        receiver_ps_id=receiver_team.ps_id,
        status="pending"
    )
    db.add(exchange)
    db.commit()
    
    return {"message": "Exchange request sent"}

@router.post("/exchange/{request_id}/accept")
def accept_exchange(request_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    team = db.query(Team).filter(Team.leader_id == current_user.id).first()
    exchange = db.query(ExchangeRequest).filter(ExchangeRequest.id == request_id, ExchangeRequest.receiver_team_id == team.id).first()
    
    if not exchange or exchange.status != "pending":
        raise HTTPException(status_code=400, detail="Invalid or already processed request")
        
    requester_team = db.query(Team).filter(Team.id == exchange.requester_team_id).first()
    
    # Swap PS
    team.ps_id, requester_team.ps_id = requester_team.ps_id, team.ps_id
    
    exchange.status = "accepted"
    
    # Mark wildcard as used
    wildcard = db.query(Wildcard).filter(Wildcard.team_id == requester_team.id).first()
    if wildcard:
        wildcard.used = True
        
    db.commit()
    return {"message": "Exchange accepted successfully"}

@router.post("/exchange/{request_id}/reject")
def reject_exchange(request_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    team = db.query(Team).filter(Team.leader_id == current_user.id).first()
    exchange = db.query(ExchangeRequest).filter(ExchangeRequest.id == request_id, ExchangeRequest.receiver_team_id == team.id).first()
    
    if not exchange or exchange.status != "pending":
        raise HTTPException(status_code=400, detail="Invalid request")
        
    exchange.status = "rejected"
    db.commit()
    return {"message": "Exchange rejected"}
