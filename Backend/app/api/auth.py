import logging
import uuid
from dataclasses import dataclass
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from starlette.concurrency import run_in_threadpool
from app.core.database import SessionLocal, get_db
from app.models.models import User, Team, Member
from app.schemas.schemas import UserCreate, UserResponse, Token, TeamCreate
from app.core.security import (
    create_access_token,
    get_password_hash,
    is_sha256_password_hash,
    verify_password,
)
from jose import ExpiredSignatureError, JWTError, jwt
from app.core.config import settings
from app.services.participant_session import (
    PARTICIPANT_ROLES,
    acquire_participant_session,
    cleared_session_values,
    participant_session_is_stale,
    touch_participant_session,
    utc_now,
)
from app.api.websockets import manager

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
logger = logging.getLogger("uvicorn.error")

ALREADY_LOGGED_IN_MESSAGE = (
    "This leader account is already logged in on another device. "
    "Please log out from the existing session before logging in again."
)


@dataclass(frozen=True)
class BidAuthClaims:
    """Signed identity claims; bidding transactions revalidate them in PostgreSQL."""

    email: str
    session_id: str
    role: str


def decode_bid_auth_claims(token: str) -> BidAuthClaims:
    """Validate a bidding JWT without opening a database session."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        session_id = payload.get("session_id")
        role = payload.get("role")
        if (
            not isinstance(email, str)
            or not email.strip()
            or not isinstance(session_id, str)
            or not session_id
            or not isinstance(role, str)
            or not role
        ):
            raise credentials_exception
        return BidAuthClaims(email=email, session_id=session_id, role=role)
    except ExpiredSignatureError as exc:
        logger.info("Rejected invalid bid token logout_reason=JWT_EXPIRED")
        raise credentials_exception from exc
    except JWTError as exc:
        logger.info("Rejected invalid bid token logout_reason=JWT_INVALID")
        raise credentials_exception from exc


async def get_bid_auth_claims(token: str = Depends(oauth2_scheme)) -> BidAuthClaims:
    claims = decode_bid_auth_claims(token)
    if claims.role != "leader":
        raise HTTPException(status_code=403, detail="Only the imported team leader can perform this action.")
    return claims

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        session_id: str = payload.get("session_id")
        if email is None or not session_id:
            logger.info("Rejected invalid session token logout_reason=JWT_INVALID detail=missing_claims")
            raise credentials_exception
    except ExpiredSignatureError:
        logger.info("Rejected invalid session token logout_reason=JWT_EXPIRED")
        raise credentials_exception
    except JWTError:
        logger.info("Rejected invalid session token logout_reason=JWT_INVALID")
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        logger.info("Rejected invalid session token logout_reason=ACCOUNT_NOT_FOUND")
        raise credentials_exception
    if not user.credentials_active:
        logger.info(
            "Rejected invalid session token user_id=%s role=%s logout_reason=ACCOUNT_DISABLED",
            user.id,
            user.role,
        )
        raise credentials_exception
    
    # A token is valid only while both sides carry the same active session.
    # A null database session is an explicit revocation, not a skipped check.
    if not user.session_id or user.session_id != session_id:
        logout_reason = "SESSION_REVOKED" if not user.session_id else "SESSION_REPLACED"
        logger.info(
            "Rejected invalid session token user_id=%s role=%s logout_reason=%s",
            user.id,
            user.role,
            logout_reason,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or was revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.role in PARTICIPANT_ROLES and not touch_participant_session(
        db,
        user_id=user.id,
        session_id=session_id,
        last_seen_at=user.session_last_seen_at,
    ):
        logger.info(
            "Rejected invalid session token user_id=%s role=%s logout_reason=SESSION_MISMATCH",
            user.id,
            user.role,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or was revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return user

def get_current_active_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def get_current_active_lab_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "lab_admin":
        raise HTTPException(status_code=403, detail="Lab Admin access required")
    return current_user


def get_current_active_admin_or_lab_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in ("admin", "lab_admin"):
        raise HTTPException(status_code=403, detail="Event Admin or Lab Admin access required")
    return current_user


def get_current_active_participant(current_user: User = Depends(get_current_user)):
    if current_user.role not in ("leader", "member"):
        raise HTTPException(status_code=403, detail="Participant access required")
    return current_user


def get_current_active_display(current_user: User = Depends(get_current_user)):
    if current_user.role != "display":
        raise HTTPException(status_code=403, detail="Leaderboard display access required")
    return current_user


def _issue_session(user: User, db: Session) -> dict:
    new_session_id = uuid.uuid4().hex
    now = utc_now()

    # Capture primitive values BEFORE commit. SQLAlchemy normally expires ORM
    # objects on commit, and reading them afterwards can trigger another query
    # and checkout another DB connection.
    user_id = user.id
    user_email = user.email
    user_role = user.role

    user.session_id = new_session_id
    user.session_created_at = now
    user.session_last_seen_at = now
    db.commit()
    logger.info("Successful login user_id=%s role=%s", user_id, user_role)

    access_token = create_access_token(
        data={
            "sub": user_email,
            "role": user_role,
            "session_id": new_session_id,
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


def _acquire_participant_session(
    user: User,
    password_hash: str,
    db: Session,
) -> tuple[dict, bool]:
    """Atomically claim a free or stale participant credential."""
    new_session_id = uuid.uuid4().hex
    now = utc_now()
    user_id = user.id
    user_email = user.email
    user_role = user.role
    replaced_stale_session = bool(user.session_id) and participant_session_is_stale(
        user.session_last_seen_at,
        now=now,
    )
    acquired = acquire_participant_session(
        db,
        user_id=user_id,
        password_hash=password_hash,
        new_session_id=new_session_id,
        now=now,
    )
    if not acquired:
        db.rollback()
        current = db.query(User).filter(User.id == user_id).first()
        if not current or not current.credentials_active or current.password_hash != password_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        db.commit()
        logger.info("Rejected duplicate participant login user_id=%s role=%s", user_id, user_role)
        detail = ALREADY_LOGGED_IN_MESSAGE if user_role == "leader" else (
            "This participant account is already logged in on another device. "
            "Please log out from the existing session before logging in again."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    db.commit()
    if replaced_stale_session:
        logger.info("Replaced stale participant session user_id=%s role=%s", user_id, user_role)
    logger.info(
        "Successful login user_id=%s role=%s replaced_stale_session=%s",
        user_id,
        user_role,
        replaced_stale_session,
    )
    access_token = create_access_token(
        data={"sub": user_email, "role": user_role, "session_id": new_session_id}
    )
    return {"access_token": access_token, "token_type": "bearer"}, replaced_stale_session


def _lookup_login_candidate(session_factory, login_id: str) -> tuple[int, str, str] | None:
    with session_factory() as db:
        candidate = db.query(User).filter(func.lower(User.email) == login_id).first()
        if not candidate or not candidate.credentials_active:
            return None
        return candidate.id, candidate.role, candidate.password_hash


def _complete_login_claim(
    session_factory,
    *,
    candidate_id: int,
    password_hash: str,
) -> tuple[dict, bool, int, str]:
    """Complete a PARTICIPANT login only."""

    with session_factory() as db:
        user = (
            db.query(User)
            .filter(
                User.id == candidate_id,
                User.credentials_active.is_(True),
                User.password_hash == password_hash,
            )
            .with_for_update()
            .populate_existing()
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # /login is PARTICIPANT ONLY.
        if user.role not in PARTICIPANT_ROLES:
            role_messages = {
                "admin": "Use the dedicated Event Admin login.",
                "lab_admin": "Use the dedicated Lab Admin login.",
                "display": "Use the dedicated leaderboard display login.",
            }

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=role_messages.get(
                    user.role,
                    "Participant access requires a participant account.",
                ),
            )

        # From here onward the account is guaranteed to be leader/member.
        if user.team_id:
            team = (
                db.query(Team)
                .filter(Team.id == user.team_id)
                .first()
            )
        else:
            team = (
                db.query(Team)
                .filter(Team.leader_id == user.id)
                .first()
            )

        if not team or not team.is_approved:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Team is not approved by admin yet.",
            )

        user_id = user.id
        user_role = user.role

        token, replaced_stale_session = _acquire_participant_session(
            user,
            password_hash,
            db,
        )

        return (
            token,
            replaced_stale_session,
            user_id,
            user_role,
        )

@router.post("/register")
def register(user_data: UserCreate, team_data: TeamCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(User).filter(User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if team exists
    db_team = db.query(Team).filter(Team.team_name == team_data.team_name).first()
    if db_team:
        raise HTTPException(status_code=400, detail="Team name already taken")
    
    if len(team_data.members) < 2 or len(team_data.members) > 4:
        raise HTTPException(status_code=400, detail="Team must have between 2 and 4 members")

    hashed_password = get_password_hash(user_data.password)
    new_user = User(name=user_data.name, email=user_data.email, password_hash=hashed_password, role="leader")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    new_team = Team(team_name=team_data.team_name, leader_id=new_user.id)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    
    for member in team_data.members:
        new_member = Member(team_id=new_team.id, member_name=member.member_name)
        db.add(new_member)
    db.commit()
    
    return {"message": "Registration successful, pending admin approval."}

@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    total_started_at = perf_counter()
    lookup_ms = 0.0
    password_verify_ms = 0.0
    acquisition_ms = 0.0
    outcome = "internal_error"
    candidate_id: int | None = None
    candidate_role: str | None = None
    password_scheme = "unknown"

    try:
        login_id = form_data.username.strip().lower()
        bound_factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
        session_factory = getattr(request.app.state, "session_factory", bound_factory)
        db.close()
        lookup_started_at = perf_counter()
        candidate = await run_in_threadpool(_lookup_login_candidate, session_factory, login_id)
        lookup_ms = (perf_counter() - lookup_started_at) * 1000
        candidate_id = candidate[0] if candidate else None
        candidate_role = candidate[1] if candidate else None
        password_hash = candidate[2] if candidate else ""

        password_scheme = "sha256" if is_sha256_password_hash(password_hash) else "unknown"
        verification_valid = False
        if candidate_id:
            verify_started_at = perf_counter()
            verification_valid = verify_password(form_data.password, password_hash)
            password_verify_ms = (perf_counter() - verify_started_at) * 1000

        if not verification_valid:
            outcome = "invalid_credentials"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        acquisition_started_at = perf_counter()
        try:
            token, replaced_stale_session, user_id, candidate_role = await run_in_threadpool(
                _complete_login_claim,
                session_factory,
                candidate_id=candidate_id,
                password_hash=password_hash,
            )
        finally:
            acquisition_ms = (perf_counter() - acquisition_started_at) * 1000

        if replaced_stale_session:
            await manager.disconnect_users(
                {user_id},
                reason="Stale session replaced by a new login",
            )
            session_factory = getattr(request.app.state, "session_factory", SessionLocal)
            manager.schedule_presence_refresh(session_factory)
        outcome = "success"
        return token
    except HTTPException as exc:
        if outcome == "internal_error":
            outcome = f"http_{exc.status_code}"
        raise
    finally:
        db.close()
        logger.info(
            "Participant login timing outcome=%s user_id=%s role=%s "
            "password_scheme=%s lookup_ms=%.2f password_verify_ms=%.2f "
            "session_acquisition_ms=%.2f total_ms=%.2f",
            outcome,
            candidate_id,
            candidate_role,
            password_scheme,
            lookup_ms,
            password_verify_ms,
            acquisition_ms,
            (perf_counter() - total_started_at) * 1000,
        )


@router.post("/leaderboard/login", response_model=Token)
def leaderboard_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    login_id = form_data.username.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == login_id).first()
    if not user or user.role != "display" or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect leaderboard login ID or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_session(user, db)


@router.post("/admin/login", response_model=Token)
def admin_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    login_id = form_data.username.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == login_id).first()
    if (
        not user
        or user.role != "admin"
        or not user.credentials_active
        or not verify_password(form_data.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Admin ID or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_session(user, db)


@router.post("/lab-admin/login", response_model=Token)
def lab_admin_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    login_id = form_data.username.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == login_id).first()
    if (
        not user
        or user.role != "lab_admin"
        or not user.credentials_active
        or not verify_password(form_data.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Lab Admin ID or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_session(user, db)


@router.get("/participant/session")
def participant_session(current_user: User = Depends(get_current_active_participant)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email, "role": current_user.role}


@router.get("/lab-admin/session")
def lab_admin_session(current_user: User = Depends(get_current_active_lab_admin)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email, "role": current_user.role}

@router.post("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    participant_logout = current_user.role in ("leader", "member")
    user_id = current_user.id
    user_role = current_user.role
    active_session_id = current_user.session_id

    cleared = (
        db.query(User)
        .filter(User.id == user_id, User.session_id == active_session_id)
        .update(cleared_session_values(), synchronize_session=False)
    )
    if cleared != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer active.")
    db.commit()
    logger.info("Logout completed user_id=%s role=%s logout_reason=EXPLICIT_LOGOUT", user_id, user_role)

    # Release request DB connection before WebSocket/network I/O.
    db.close()

    await manager.disconnect_users({user_id})
    if participant_logout:
        session_factory = getattr(request.app.state, "session_factory", SessionLocal)
        manager.schedule_presence_refresh(session_factory)
    return {"message": "Successfully logged out"}
