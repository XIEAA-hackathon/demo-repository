from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.models import ProblemStatement
from app.schemas.schemas import PSCreate, PSResponse
from app.api.auth import get_current_user, get_current_active_admin
from app.api.websockets import manager

router = APIRouter()

@router.post("/problem-statement", response_model=PSResponse)
def create_ps(ps: PSCreate, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    db_ps = db.query(ProblemStatement).filter(ProblemStatement.ps_number == ps.ps_number).first()
    if db_ps:
        raise HTTPException(status_code=400, detail="Problem Statement number already exists")
    
    new_ps = ProblemStatement(**ps.model_dump())
    db.add(new_ps)
    db.commit()
    db.refresh(new_ps)
    return new_ps

@router.get("/problem-statements", response_model=List[PSResponse])
def get_pss(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.role == "admin":
        # Admin sees all
        pss = db.query(ProblemStatement).all()
    else:
        # User only sees visible ones, and we should ideally hide titles until they own it (based on requirements)
        # But for now, just return visible ones
        pss = db.query(ProblemStatement).filter(ProblemStatement.status == "visible").all()
        # Hide title and description if not allocated to this team, according to rules.
        # This can be handled in frontend or we can nullify them here.
        for ps in pss:
            ps.title = "Hidden"
            ps.description = "Hidden"
    return pss

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
    return {"message": f"PS {ps.ps_number} status updated to {status}"}
