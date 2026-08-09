from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.models import Team, User
from app.schemas.schemas import TeamResponse
from app.api.auth import get_current_user, get_current_active_admin
from app.api.websockets import manager

router = APIRouter()

@router.get("/dashboard", response_model=TeamResponse)
def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "leader":
        raise HTTPException(status_code=403, detail="Only team leaders can view this dashboard")
    
    team = db.query(Team).filter(Team.leader_id == current_user.id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    return team

@router.get("/teams", response_model=List[TeamResponse])
def get_all_teams(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    teams = db.query(Team).all()
    return teams

@router.put("/team/{team_id}/approve")
async def approve_team(team_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team.is_approved = True
    db.commit()
    await manager.broadcast_event("team_updated", {"action": "approved", "team_id": team.id, "team_name": team.team_name})
    return {"message": f"Team {team.team_name} approved successfully"}

@router.delete("/team/{team_id}")
async def delete_team(team_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Due to cascade delete, this will remove members, bids, user, etc based on how it's configured.
    # Actually, we should probably delete the leader user as well, or just delete the team.
    leader = db.query(User).filter(User.id == team.leader_id).first()
    team_name = team.team_name
    db.delete(team)
    if leader:
        db.delete(leader)
    db.commit()
    await manager.broadcast_event("team_updated", {"action": "deleted", "team_id": team_id, "team_name": team_name})
    return {"message": "Team deleted successfully"}
