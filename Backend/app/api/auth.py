from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.core.database import get_db
from app.models.models import User, Team, Member
from app.schemas.schemas import UserCreate, UserResponse, Token, TeamCreate
from app.core.security import get_password_hash, verify_password, create_access_token
from jose import JWTError, jwt
from app.core.config import settings
from app.services.activity_log import record_event
from app.services.participant_presence import participant_presence_payload
from app.api.websockets import manager

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

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
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.credentials_active:
        raise credentials_exception
    
    # A token is valid only while both sides carry the same active session.
    # A null database session is an explicit revocation, not a skipped check.
    if not user.session_id or user.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. You logged in from another device.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return user

def get_current_active_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
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
    import uuid
    new_session_id = uuid.uuid4().hex
    user.session_id = new_session_id
    record_event(db, "auth.login", actor=user)
    db.commit()
    access_token = create_access_token(data={"sub": user.email, "role": user.role, "session_id": new_session_id})
    return {"access_token": access_token, "token_type": "bearer"}

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
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    login_id = form_data.username.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == login_id).first()
    if not user or not user.credentials_active or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.role == "display":
        raise HTTPException(status_code=403, detail="Use the dedicated leaderboard display login.")
    
    if user.role in ("leader", "member"):
        if user.team_id:
            team = db.query(Team).filter(Team.id == user.team_id).first()
        else:
            team = db.query(Team).filter(Team.leader_id == user.id).first()
        if not team or not team.is_approved:
            raise HTTPException(status_code=403, detail="Team is not approved by admin yet.")
            
    if user.role in ("leader", "member"):
        await manager.disconnect_users({user.id}, reason="Signed in from another session")
    token = _issue_session(user, db)
    if user.role in ("leader", "member"):
        presence = participant_presence_payload(db, connected_team_ids=manager.participant_team_ids())
        await manager.broadcast_event("participant_presence_changed", presence)
    return token


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

@router.post("/logout")
async def logout(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    participant_logout = current_user.role in ("leader", "member")
    record_event(db, "auth.logout", actor=current_user)
    current_user.session_id = None
    db.commit()
    if participant_logout:
        await manager.disconnect_users({current_user.id})
        presence = participant_presence_payload(db, connected_team_ids=manager.participant_team_ids())
        await manager.broadcast_event("participant_presence_changed", presence)
    return {"message": "Successfully logged out"}
