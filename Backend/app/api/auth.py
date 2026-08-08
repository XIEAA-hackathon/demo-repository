from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.core.database import get_db
from app.models.models import User, Team, Member
from app.schemas.schemas import UserCreate, UserResponse, Token, TeamCreate
from app.core.security import get_password_hash, verify_password, create_access_token
from jose import JWTError, jwt
from app.core.config import settings

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
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    
    # Invalidate if the session_id doesn't match the current one in the DB
    if user.session_id and user.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. You logged in from another device.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return user

def get_current_active_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=400, detail="Not enough permissions")
    return current_user

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
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.role == "leader":
        team = db.query(Team).filter(Team.leader_id == user.id).first()
        if not team or not team.is_approved:
            raise HTTPException(status_code=403, detail="Team is not approved by admin yet.")
            
    import uuid
    new_session_id = uuid.uuid4().hex
    user.session_id = new_session_id
    db.commit()
            
    access_token = create_access_token(data={"sub": user.email, "role": user.role, "session_id": new_session_id})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
def logout(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.session_id = None
    db.commit()
    return {"message": "Successfully logged out"}
