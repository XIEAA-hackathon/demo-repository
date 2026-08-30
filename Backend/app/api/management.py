from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_active_admin
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.models import User
from app.services.activity_log import record_event
from app.services.participant_session import clear_user_session


router = APIRouter(prefix="/admin/management")
MANAGED_ROLES = {"admin", "display"}


class ManagedUserCreate(BaseModel):
    login_id: str
    password: str
    confirm_password: str


class ManagedPasswordReset(BaseModel):
    new_password: str
    confirm_password: str


class ManagedUsersReset(BaseModel):
    confirmation: str


def _validate_password(password: str, confirmation: str) -> None:
    if not password:
        raise HTTPException(status_code=422, detail="Password is required.")
    if password != confirmation:
        raise HTTPException(status_code=422, detail="Password confirmation does not match.")
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="Password must be 72 bytes or fewer.")


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "login_id": user.email,
        "role": user.role,
        "is_system_account": bool(user.is_system_account),
        "status": "SYSTEM" if user.is_system_account else "ACTIVE",
        "created_at": user.created_at,
    }


def _list_role(db: Session, role: str) -> list[dict]:
    users = (
        db.query(User)
        .filter(User.role == role)
        .order_by(User.is_system_account.desc(), func.lower(User.email).asc())
        .all()
    )
    return [_user_payload(user) for user in users]


def _create_user(payload: ManagedUserCreate, role: str, db: Session, actor: User) -> dict:
    login_id = payload.login_id.strip().lower()
    if not login_id:
        raise HTTPException(status_code=422, detail="Login ID is required.")
    _validate_password(payload.password, payload.confirm_password)
    if db.query(User).filter(func.lower(User.email) == login_id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Login ID already exists.")
    user = User(
        name="Managed Admin" if role == "admin" else "Managed Leaderboard Display",
        email=login_id,
        password_hash=get_password_hash(payload.password),
        role=role,
        is_system_account=False,
    )
    db.add(user)
    db.flush()
    record_event(
        db,
        "management.user_created",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        metadata={"login_id": login_id, "role": role},
    )
    db.commit()
    db.refresh(user)
    return _user_payload(user)


@router.get("/admin-users")
def list_admin_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    del current_user
    return {"users": _list_role(db, "admin")}


@router.post("/admin-users", status_code=status.HTTP_201_CREATED)
def create_admin_user(payload: ManagedUserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    return _create_user(payload, "admin", db, current_user)


@router.get("/leaderboard-users")
def list_leaderboard_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    del current_user
    return {"users": _list_role(db, "display")}


@router.post("/leaderboard-users", status_code=status.HTTP_201_CREATED)
def create_leaderboard_user(payload: ManagedUserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    return _create_user(payload, "display", db, current_user)


@router.put("/users/{user_id}/password")
def reset_managed_user_password(
    user_id: int,
    payload: ManagedPasswordReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    _validate_password(payload.new_password, payload.confirm_password)
    target = db.query(User).filter(User.id == user_id, User.role.in_(MANAGED_ROLES)).first()
    if not target:
        raise HTTPException(status_code=404, detail="Managed Admin or leaderboard user not found.")
    if target.role == "admin" and target.is_system_account:
        raise HTTPException(status_code=403, detail="The permanent system Admin password is managed through backend configuration.")
    target.password_hash = get_password_hash(payload.new_password)
    clear_user_session(target)
    record_event(
        db,
        "management.password_reset",
        actor=current_user,
        entity_type="user",
        entity_id=target.id,
        metadata={"login_id": target.email, "role": target.role},
    )
    db.commit()
    return {"status": "password_reset", "user": _user_payload(target)}


@router.post("/reset")
def reset_managed_users(
    payload: ManagedUsersReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    if payload.confirmation != "RESET USERS":
        raise HTTPException(status_code=422, detail="Enter RESET USERS to confirm managed-user reset.")
    managed_users = (
        db.query(User)
        .filter(User.role.in_(MANAGED_ROLES), User.is_system_account.is_(False))
        .all()
    )
    deleted = {
        "admin_users": sum(user.role == "admin" for user in managed_users),
        "leaderboard_users": sum(user.role == "display" for user in managed_users),
    }
    managed_ids = [user.id for user in managed_users]
    if managed_ids:
        db.query(User).filter(User.id.in_(managed_ids)).delete(synchronize_session=False)
    record_event(
        db,
        "management.users_reset",
        actor=current_user,
        metadata={**deleted, "total": len(managed_ids)},
    )
    db.commit()
    return {
        "status": "reset_complete",
        "deleted": {**deleted, "total": len(managed_ids)},
        "preserved": {
            "system_accounts": db.query(User).filter(User.is_system_account.is_(True)).count(),
            "participant_users": db.query(User).filter(User.role.in_(("leader", "member"))).count(),
        },
    }
