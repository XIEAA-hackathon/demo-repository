from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

# --- User Schemas ---
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "leader"

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str

    class Config:
        from_attributes = True

# --- Team Schemas ---
class MemberCreate(BaseModel):
    member_name: str

class TeamCreate(BaseModel):
    team_name: str
    members: List[MemberCreate]

class MemberResponse(BaseModel):
    id: int
    member_name: str
    
    class Config:
        from_attributes = True

class TeamResponse(BaseModel):
    id: int
    team_name: str
    coins: int
    leader_id: int
    ps_id: Optional[int]
    is_approved: bool
    members: List[MemberResponse]
    
    class Config:
        from_attributes = True

# --- Problem Statement Schemas ---
class PSCreate(BaseModel):
    ps_number: str
    title: str
    description: str
    round: int = 1
    status: str = "visible"

class PSResponse(BaseModel):
    id: int
    ps_number: str
    title: str
    description: Optional[str]
    round: int
    status: str
    
    class Config:
        from_attributes = True

# --- Bid Schemas ---
class BidCreate(BaseModel):
    ps_id: int
    amount: int

class BidResponse(BaseModel):
    id: int
    team_id: int
    ps_id: int
    amount: int
    round: int
    timestamp: datetime
    
    class Config:
        from_attributes = True

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
