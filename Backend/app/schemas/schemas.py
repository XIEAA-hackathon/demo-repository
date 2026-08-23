from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import List, Optional, Any
from datetime import datetime

EVENT_STATES = [
    "WAITING",
    "ROUND1_PREVIEW",
    "ROUND1_BIDDING",
    "ROUND1_RESULT",
    "WILDCARD_APPLICATION",
    "WILDCARD_PREVIEW",
    "WILDCARD_BIDDING",
    "WILDCARD_SELECTION",
    "CODING",
    "SUBMISSION",
    "JUDGING_WAIT",
    "RESULTS",
]

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

    model_config = ConfigDict(from_attributes=True)

# --- Team Schemas ---
class MemberCreate(BaseModel):
    member_name: str

class TeamCreate(BaseModel):
    team_name: str
    members: List[MemberCreate]

class MemberResponse(BaseModel):
    id: int
    member_name: str

    model_config = ConfigDict(from_attributes=True)

class TeamResponse(BaseModel):
    id: int
    team_name: str
    coins: int
    leader_id: int
    ps_id: Optional[int]
    is_approved: bool
    members: List[MemberResponse]

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)

# --- Bid Schemas ---
class BidCreate(BaseModel):
    ps_id: int
    amount: int = Field(..., gt=0, description="Bid amount must be strictly greater than 0")

class BidResponse(BaseModel):
    id: int
    team_id: int
    ps_id: int
    amount: int
    round: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Event Config Schemas ---
class EventConfigBase(BaseModel):
    starting_coins: int = 1000
    round1_preview_seconds: int = 120
    round1_bid_seconds: int = 300
    round1_winner_count: int = 5
    round1_minimum_bid: int = 25
    round1_bid_increment: int = 1
    wildcard_enabled: bool = True
    wildcard_slots: int = 3
    wildcard_problem_count: int = 3
    wildcard_preview_seconds: int = 120
    wildcard_bid_seconds: int = 180
    wildcard_starting_bid: int = 150
    wildcard_bid_increment: int = 1
    coding_duration_seconds: int = 10800
    bid_cooldown_seconds: int = 5
    royalty_coins_per_point: int = 10
    royalty_max_points: int = 100

class EventConfigUpdate(BaseModel):
    starting_coins: Optional[int] = None
    round1_preview_seconds: Optional[int] = None
    round1_bid_seconds: Optional[int] = None
    round1_winner_count: Optional[int] = None
    round1_minimum_bid: Optional[int] = None
    round1_bid_increment: Optional[int] = None
    wildcard_enabled: Optional[bool] = None
    wildcard_slots: Optional[int] = None
    wildcard_problem_count: Optional[int] = None
    wildcard_preview_seconds: Optional[int] = None
    wildcard_bid_seconds: Optional[int] = None
    wildcard_starting_bid: Optional[int] = None
    wildcard_bid_increment: Optional[int] = None
    coding_duration_seconds: Optional[int] = None
    bid_cooldown_seconds: Optional[int] = None
    royalty_coins_per_point: Optional[int] = None
    royalty_max_points: Optional[int] = None

class EventConfigResponse(EventConfigBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

# --- Participant Dashboard Schemas ---
class DashboardUser(BaseModel):
    id: int
    name: str
    email: str
    role: str

class DashboardMember(BaseModel):
    id: int
    member_name: str
    email: Optional[str]
    is_leader: bool

class DashboardLeader(BaseModel):
    id: int
    name: str
    email: str

class DashboardTeam(BaseModel):
    id: int
    team_name: str
    coins: int
    leader_id: int
    ps_id: Optional[int]
    is_approved: bool
    members: List[DashboardMember]

class DashboardProblem(BaseModel):
    id: int
    ps_number: str
    title: str
    description: Optional[str]
    round: int
    status: str

class DashboardBid(BaseModel):
    id: int
    team_id: int
    ps_id: int
    amount: int
    round: int
    timestamp: datetime

class DashboardWildcard(BaseModel):
    status: Optional[str] = None
    coins_paid: int = 0
    used: bool = False

class DashboardSubmission(BaseModel):
    id: int
    problem_id: Optional[int]
    repository_url: str
    submitted_at: datetime
    updated_at: Optional[datetime]

class DashboardGameConfig(BaseModel):
    starting_coins: int
    round1_winner_count: int
    round1_minimum_bid: int
    round1_preview_seconds: int
    round1_bid_seconds: int
    wildcard_slots: int
    wildcard_starting_bid: int
    wildcard_preview_seconds: int
    wildcard_bid_seconds: int
    coding_duration_seconds: int
    bid_cooldown_seconds: int = 5

class EventTiming(BaseModel):
    server_time: datetime
    started_at: Optional[datetime]
    ends_at: Optional[datetime]
    paused: bool
    paused_remaining_seconds: Optional[int]

class ParticipantDashboardResponse(BaseModel):
    user: DashboardUser
    team: DashboardTeam
    leader: DashboardLeader
    eventState: str
    wallet: dict
    currentProblem: Optional[DashboardProblem]
    currentBid: Optional[DashboardBid]
    wildcard: Optional[DashboardWildcard]
    submission: Optional[DashboardSubmission]
    isLeader: bool
    gameConfig: DashboardGameConfig
    timing: EventTiming

# --- Submission Schemas ---
class SubmissionCreate(BaseModel):
    repository_url: str

class SubmissionUpdate(BaseModel):
    repository_url: str

# --- Leaderboard Schemas ---
class LeaderboardEntry(BaseModel):
    rank: int
    team_id: int
    team_name: str
    coins: int
    ps_title: Optional[str] = None
    bid_amount: Optional[int] = None

# --- Admin Config / State Schemas ---
class EventStateUpdate(BaseModel):
    state: str

# --- Registration Import Schemas ---
class ImportRowPreview(BaseModel):
    row_number: int
    team_name: str
    leader_name: str
    leader_email: str
    members: List[dict]
    status: str = "new"  # new, update, duplicate, error
    warnings: List[str] = []

class ImportPreviewResponse(BaseModel):
    import_id: int
    filename: str
    teams_detected: int
    members_detected: int
    leaders_detected: int
    warnings: List[str]
    errors: List[str]
    rows: List[ImportRowPreview]

class CredentialRow(BaseModel):
    user_id: Optional[int] = None
    team_name: str
    name: str
    email: str
    username: str
    participant_id: Optional[str] = None
    temporary_password: str
    role: str

class ParticipantIdentityInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: Optional[EmailStr] = None

class ManualTeamCredentialsRequest(BaseModel):
    team_name: str = Field(min_length=1, max_length=120)
    leader: ParticipantIdentityInput
    members: List[ParticipantIdentityInput] = Field(min_length=1, max_length=3)

class ManualTeamCredentialsResponse(BaseModel):
    team_id: int
    team_name: str
    member_count: int
    credentials: List[CredentialRow]

class ImportConfirmRequest(BaseModel):
    import_id: int

class ImportConfirmResponse(BaseModel):
    import_id: int
    teams_created: int
    teams_updated: int
    accounts_created: int
    credentials: List[CredentialRow]

class ImportStatusResponse(BaseModel):
    import_id: int
    filename: str
    status: str
    created_at: datetime
    teams_created: Optional[int] = None
    teams_updated: Optional[int] = None
    accounts_created: Optional[int] = None
