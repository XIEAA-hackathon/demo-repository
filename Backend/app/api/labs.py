from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import get_current_active_admin, get_current_active_admin_or_lab_admin
from app.api.websockets import manager
from app.core.database import get_db
from app.models.models import Lab, LabAssignment, User
from app.services.activity_log import record_event
from app.services.lab_allocation import LabAllocationError, allocate_labs, lab_board, move_team, try_allocate_labs


router = APIRouter()


class LabCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    capacity: int = Field(ge=1, le=10_000)
    sort_order: int = Field(default=0, ge=0, le=10_000)
    active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Lab name is required.")
        return cleaned


class LabUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    capacity: int | None = Field(default=None, ge=1, le=10_000)
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Lab name is required.")
        return cleaned


class LabMoveRequest(BaseModel):
    target_lab_id: int = Field(ge=1)
    expected_version: int = Field(ge=0)
    allow_constraint_override: bool = False


class TeamLabMoveRequest(BaseModel):
    lab_id: int = Field(gt=0, strict=True)
    expected_version: int = Field(default=0, ge=0, strict=True)


def _lab_payload(lab: Lab) -> dict:
    return {
        "id": lab.id,
        "name": lab.name,
        "capacity": lab.capacity,
        "sort_order": lab.sort_order,
        "active": lab.active,
        "created_at": lab.created_at,
        "updated_at": lab.updated_at,
    }


def _raise_allocation_error(exc: LabAllocationError) -> None:
    code = status.HTTP_404_NOT_FOUND if exc.code == "assignment_not_found" else status.HTTP_409_CONFLICT
    raise HTTPException(status_code=code, detail=exc.detail()) from exc


@router.get("/admin/labs")
def list_labs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    labs = db.query(Lab).order_by(Lab.sort_order.asc(), Lab.id.asc()).all()
    return [_lab_payload(lab) for lab in labs]


@router.post("/admin/labs", status_code=status.HTTP_201_CREATED)
async def create_lab(
    payload: LabCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    duplicate = db.query(Lab.id).filter(func.lower(Lab.name) == payload.name.lower()).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="A lab with this name already exists.")
    lab = Lab(**payload.model_dump())
    db.add(lab)
    record_event(db, "lab.created", actor=current_user, entity_type="lab")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A lab with this name already exists.") from exc
    db.refresh(lab)
    result = _lab_payload(lab)
    allocation_team_count = try_allocate_labs(db)
    db.close()
    await manager.broadcast_event("lab_configuration_updated", {"action": "created", "lab_id": result["id"]}, roles={"admin", "lab_admin"})
    if allocation_team_count is not None:
        await manager.broadcast_event("lab_allocation_updated", {"action": "auto_allocated", "team_count": allocation_team_count, "assignments": db.info.pop("lab_assignment_changes", [])}, roles={"admin", "lab_admin"})
    return result


@router.put("/admin/labs/{lab_id}")
async def update_lab(
    lab_id: int,
    payload: LabUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    lab = db.query(Lab).filter(Lab.id == lab_id).with_for_update().one_or_none()
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found.")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        duplicate = db.query(Lab.id).filter(func.lower(Lab.name) == data["name"].lower(), Lab.id != lab.id).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="A lab with this name already exists.")
    occupancy = db.query(LabAssignment).filter(LabAssignment.current_lab_id == lab.id).count()
    if data.get("capacity", lab.capacity) < occupancy:
        raise HTTPException(status_code=409, detail=f"Capacity cannot be lower than the current occupancy of {occupancy}.")
    if data.get("active") is False and occupancy:
        raise HTTPException(status_code=409, detail="Move assigned teams before deactivating this lab.")
    for field, value in data.items():
        setattr(lab, field, value)
    record_event(db, "lab.updated", actor=current_user, entity_type="lab", entity_id=lab.id, metadata={"fields": sorted(data)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A lab with this name already exists.") from exc
    db.refresh(lab)
    result = _lab_payload(lab)
    allocation_team_count = try_allocate_labs(db)
    db.close()
    await manager.broadcast_event("lab_configuration_updated", {"action": "updated", "lab_id": lab_id}, roles={"admin", "lab_admin"})
    if allocation_team_count is not None:
        await manager.broadcast_event("lab_allocation_updated", {"action": "auto_allocated", "team_count": allocation_team_count, "assignments": db.info.pop("lab_assignment_changes", [])}, roles={"admin", "lab_admin"})
    return result


@router.delete("/admin/labs/{lab_id}")
async def delete_lab(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    lab = db.query(Lab).filter(Lab.id == lab_id).with_for_update().one_or_none()
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found.")
    referenced = db.query(LabAssignment.id).filter(
        (LabAssignment.current_lab_id == lab.id) | (LabAssignment.original_lab_id == lab.id)
    ).first()
    if referenced:
        raise HTTPException(status_code=409, detail="This lab is part of the saved allocation and cannot be deleted.")
    name = lab.name
    db.delete(lab)
    record_event(db, "lab.deleted", actor=current_user, entity_type="lab", entity_id=lab_id, metadata={"name": name})
    db.commit()
    db.close()
    await manager.broadcast_event("lab_configuration_updated", {"action": "deleted", "lab_id": lab_id}, roles={"admin", "lab_admin"})
    return {"message": f"{name} deleted."}


@router.get("/lab-allocation")
def get_lab_allocation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin_or_lab_admin),
):
    return lab_board(db)


@router.post("/admin/lab-allocation/allocate")
async def generate_lab_allocation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    try:
        changed, team_count = allocate_labs(db, actor=current_user, replace_manual=True)
    except LabAllocationError as exc:
        db.rollback()
        _raise_allocation_error(exc)
    board = lab_board(db)
    db.close()
    if changed:
        await manager.broadcast_event(
            "lab_allocation_updated",
            {"action": "auto_allocated", "team_count": team_count, "assignments": db.info.pop("lab_assignment_changes", [])},
            roles={"admin", "lab_admin"},
        )
    return board


@router.put("/lab-allocation/assignments/{assignment_id}/move")
async def move_lab_assignment(
    assignment_id: int,
    payload: LabMoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin_or_lab_admin),
    team_id: int | None = None,
):
    try:
        assignment = move_team(
            db,
            assignment_id=assignment_id,
            target_lab_id=payload.target_lab_id,
            expected_version=payload.expected_version,
            allow_constraint_override=payload.allow_constraint_override,
            actor=current_user,
            team_id=team_id,
        )
    except LabAllocationError as exc:
        db.rollback()
        _raise_allocation_error(exc)
    result = {
        "assignment_id": assignment.id,
        "team_id": assignment.team_id,
        "current_lab_id": assignment.current_lab_id,
        "original_lab_id": assignment.original_lab_id,
        "assignment_source": assignment.assignment_source,
        "constraint_override": assignment.constraint_override,
        "version": assignment.version,
        "moved_at": assignment.moved_at,
    }
    changes = db.info.pop("lab_assignment_changes", [])
    if changes:
        result.update(changes[0])
    db.close()
    if changes:
        await manager.broadcast_event("lab_assignment_changed", result, roles={"admin", "lab_admin", "leader", "member"})
    return result


@router.put("/lab-admin/teams/{team_id}/lab")
async def move_or_assign_team_lab(team_id: int, payload: TeamLabMoveRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin_or_lab_admin)):
    return await move_lab_assignment(0, LabMoveRequest(target_lab_id=payload.lab_id, expected_version=payload.expected_version), db, current_user, team_id=team_id)
