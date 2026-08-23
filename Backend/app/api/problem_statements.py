from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.models import ProblemStatement, Team
from app.schemas.schemas import PSCreate, PSUpdate, PSResponse, AdminPSResponse
from app.api.auth import get_current_user, get_current_active_admin
from app.api.websockets import manager

router = APIRouter()

@router.post("/problem-statement", response_model=PSResponse)
async def create_ps(ps: PSCreate, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    db_ps = db.query(ProblemStatement).filter(ProblemStatement.ps_number == ps.ps_number).first()
    if db_ps:
        raise HTTPException(status_code=400, detail="Problem Statement number already exists")
    
    new_ps = ProblemStatement(**ps.model_dump())
    db.add(new_ps)
    db.commit()
    db.refresh(new_ps)

    await manager.broadcast_event("ps_updated", {
        "action": "created",
        "ps_id": new_ps.id,
        "ps_number": new_ps.ps_number,
        "title": new_ps.title,
    })
    return new_ps

@router.get("/problem-statements", response_model=List[PSResponse])
def get_pss(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.role == "admin":
        pss = db.query(ProblemStatement).all()
    else:
        pss = db.query(ProblemStatement).filter(ProblemStatement.status == "visible").all()
    return pss

@router.get("/problem-statements/admin", response_model=List[AdminPSResponse])
def get_pss_admin(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    """Admin live view of all Problem Statements with team allotment information."""
    pss = db.query(ProblemStatement).all()
    teams = db.query(Team).all()
    team_by_ps = {t.ps_id: t for t in teams if t.ps_id}

    res = []
    for ps in pss:
        team = team_by_ps.get(ps.id)
        res.append(AdminPSResponse(
            id=ps.id,
            ps_number=ps.ps_number,
            title=ps.title,
            description=ps.description,
            round=ps.round,
            status=ps.status,
            allocated_team_id=team.id if team else None,
            allocated_team_name=team.team_name if team else None,
        ))
    return res

@router.put("/problem-statement/{ps_id}", response_model=PSResponse)
async def update_ps(ps_id: int, ps_in: PSUpdate, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    ps = db.query(ProblemStatement).filter(ProblemStatement.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Problem Statement not found")

    if ps_in.ps_number and ps_in.ps_number != ps.ps_number:
        dup = db.query(ProblemStatement).filter(ProblemStatement.ps_number == ps_in.ps_number).first()
        if dup:
            raise HTTPException(status_code=400, detail="Problem Statement number already in use")
        ps.ps_number = ps_in.ps_number

    if ps_in.title is not None:
        ps.title = ps_in.title
    if ps_in.description is not None:
        ps.description = ps_in.description
    if ps_in.round is not None:
        ps.round = ps_in.round
    if ps_in.status is not None:
        ps.status = ps_in.status

    db.commit()
    db.refresh(ps)

    await manager.broadcast_event("ps_updated", {
        "action": "updated",
        "ps_id": ps.id,
        "ps_number": ps.ps_number,
        "title": ps.title,
        "status": ps.status,
    })
    return ps

@router.put("/problem-statement/{ps_id}/visibility")
async def toggle_visibility(ps_id: int, status: str, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if status not in ["visible", "hidden", "allocated"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    ps = db.query(ProblemStatement).filter(ProblemStatement.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="PS not found")
    ps.status = status
    db.commit()
    await manager.broadcast_event("problem_visibility_updated", {"problem_id": ps.id, "status": status})
    await manager.broadcast_event("ps_updated", {"action": "status_changed", "ps_id": ps.id, "status": status})
    return {"message": f"PS {ps.ps_number} status updated to {status}"}

@router.delete("/problem-statement/{ps_id}")
async def delete_ps(ps_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    ps = db.query(ProblemStatement).filter(ProblemStatement.id == ps_id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Problem Statement not found")

    # Clear ps_id on any allocated team
    allocated_teams = db.query(Team).filter(Team.ps_id == ps.id).all()
    for t in allocated_teams:
        t.ps_id = None

    db.delete(ps)
    db.commit()

    await manager.broadcast_event("ps_updated", {
        "action": "deleted",
        "ps_id": ps_id,
    })
    return {"message": f"Problem Statement {ps.ps_number} deleted successfully"}
