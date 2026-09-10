from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from app.core.database import get_db
from app.models.models import Bid, ProblemStatement, RoundControl, Submission, Team, Wildcard, WildcardSelectionPool
from app.schemas.schemas import AdminPSResponse, PSCreate, PSResponse, PSUpdate
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


@router.get("/problem-statements/admin", response_model=List[AdminPSResponse])
def get_pss_admin(db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    problems = db.query(ProblemStatement).all()
    teams = db.query(Team).filter(
        or_(Team.ps_id.is_not(None), Team.round1_problem_id.is_not(None), Team.wildcard_problem_id.is_not(None))
    ).all()
    team_by_problem: dict[int, Team] = {}
    for team in teams:
        for problem_id in (team.ps_id, team.round1_problem_id, team.wildcard_problem_id):
            if problem_id is not None:
                team_by_problem.setdefault(problem_id, team)

    return [
        AdminPSResponse(
            id=problem.id,
            ps_number=problem.ps_number,
            title=problem.title,
            description=problem.description,
            round=problem.round,
            status=problem.status,
            allocated_team_id=team_by_problem[problem.id].id if problem.id in team_by_problem else None,
            allocated_team_name=team_by_problem[problem.id].team_name if problem.id in team_by_problem else None,
        )
        for problem in problems
    ]


@router.put("/problem-statement/{ps_id}", response_model=PSResponse)
async def update_ps(
    ps_id: int,
    updates: PSUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_admin),
):
    problem = db.query(ProblemStatement).filter(ProblemStatement.id == ps_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem Statement not found")

    data = updates.model_dump(exclude_unset=True)
    new_number = data.get("ps_number")
    if new_number and new_number != problem.ps_number:
        duplicate = db.query(ProblemStatement).filter(ProblemStatement.ps_number == new_number).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Problem Statement number already in use")
    for field, value in data.items():
        setattr(problem, field, value)

    db.commit()
    db.refresh(problem)
    await manager.broadcast_event("ps_updated", {
        "action": "updated",
        "ps_id": problem.id,
        "ps_number": problem.ps_number,
        "title": problem.title,
        "status": problem.status,
    })
    return problem

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
    problem = db.query(ProblemStatement).filter(ProblemStatement.id == ps_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem Statement not found")

    referenced = any((
        db.query(Team).filter(or_(Team.ps_id == ps_id, Team.round1_problem_id == ps_id, Team.wildcard_problem_id == ps_id)).first(),
        db.query(RoundControl).filter(RoundControl.current_problem_id == ps_id).first(),
        db.query(Bid).filter(Bid.ps_id == ps_id).first(),
        db.query(Wildcard).filter(Wildcard.problem_id == ps_id).first(),
        db.query(WildcardSelectionPool).filter(WildcardSelectionPool.problem_id == ps_id).first(),
        db.query(Submission).filter(Submission.problem_id == ps_id).first(),
    ))
    if referenced:
        raise HTTPException(status_code=409, detail="Problem Statement is in use and cannot be deleted.")

    problem_number = problem.ps_number
    db.delete(problem)
    db.commit()
    await manager.broadcast_event("ps_updated", {"action": "deleted", "ps_id": ps_id})
    return {"message": f"Problem Statement {problem_number} deleted successfully"}
