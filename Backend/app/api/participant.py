from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import User, Team, Member, Bid, Wildcard, Submission, GameConfig, ProblemStatement
from app.schemas.schemas import (
    ParticipantDashboardResponse, DashboardUser, DashboardTeam, DashboardMember,
    DashboardLeader, DashboardProblem, DashboardBid, DashboardWildcard,
    DashboardSubmission, DashboardGameConfig, SubmissionCreate, SubmissionUpdate,
    EventTiming, LeaderboardEntry,
)
from app.api.auth import get_current_user
from app.services.event_service import (
    get_team_for_user, get_or_create_game_config, get_or_create_event_config,
    current_user_is_team_leader,
    ensure_leader, event_snapshot, event_timing,
)
from app.api.websockets import manager

router = APIRouter()

@router.get("/participant/dashboard", response_model=ParticipantDashboardResponse)
def get_participant_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    team = get_team_for_user(db, current_user)
    if not team:
        raise HTTPException(status_code=404, detail="No team linked to this account")

    leader = db.query(User).filter(User.id == team.leader_id).first()
    config = get_or_create_game_config(db)
    event_config = get_or_create_event_config(db)

    # members with leader flags
    member_objs = db.query(Member).filter(Member.team_id == team.id).all()
    members = []
    if leader:
        members.append(DashboardMember(
            id=leader.id,
            member_name=leader.name,
            email=leader.email,
            is_leader=True,
        ))
    for m in member_objs:
        members.append(DashboardMember(
            id=m.id,
            member_name=m.member_name,
            email=m.email,
            is_leader=(team.leader_id and m.member_name == leader.name) if leader else False,
        ))

    current_problem = None
    if team.ps_id:
        ps = db.query(ProblemStatement).filter(ProblemStatement.id == team.ps_id).first()
        if ps:
            current_problem = DashboardProblem(
                id=ps.id, ps_number=ps.ps_number, title=ps.title,
                description=ps.description, round=ps.round, status=ps.status,
            )

    current_bid = None
    latest_bid = db.query(Bid).filter(Bid.team_id == team.id).order_by(Bid.timestamp.desc()).first()
    if latest_bid:
        current_bid = DashboardBid(
            id=latest_bid.id, team_id=latest_bid.team_id, ps_id=latest_bid.ps_id,
            amount=latest_bid.amount, round=latest_bid.round, timestamp=latest_bid.timestamp,
        )

    wildcard = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()
    wildcard_out = None
    if wildcard:
        wildcard_out = DashboardWildcard(status=wildcard.status, coins_paid=wildcard.coins_paid, used=wildcard.used)

    submission = db.query(Submission).filter(Submission.team_id == team.id).first()
    submission_out = None
    if submission:
        submission_out = DashboardSubmission(
            id=submission.id, problem_id=submission.problem_id,
            repository_url=submission.repository_url,
            submitted_at=submission.submitted_at, updated_at=submission.updated_at,
        )

    is_leader = current_user_is_team_leader(db, current_user, team)

    return ParticipantDashboardResponse(
        user=DashboardUser(id=current_user.id, name=current_user.name, email=current_user.email, role=current_user.role),
        team=DashboardTeam(
            id=team.id, team_name=team.team_name, coins=team.coins,
            leader_id=team.leader_id, ps_id=team.ps_id, is_approved=team.is_approved,
            members=members,
        ),
        leader=DashboardLeader(id=leader.id, name=leader.name, email=leader.email) if leader else None,
        eventState=config.state,
        wallet={"team_id": team.id, "balance": team.coins, "currency": "coins"},
        currentProblem=current_problem,
        currentBid=current_bid,
        wildcard=wildcard_out,
        submission=submission_out,
        isLeader=is_leader,
        gameConfig=DashboardGameConfig(
            starting_coins=event_config.starting_coins,
            round1_winner_count=event_config.round1_winner_count,
            round1_minimum_bid=event_config.round1_minimum_bid,
            round1_preview_seconds=event_config.round1_preview_seconds,
            round1_bid_seconds=event_config.round1_bid_seconds,
            wildcard_slots=event_config.wildcard_slots,
            wildcard_starting_bid=event_config.wildcard_starting_bid,
            wildcard_preview_seconds=event_config.wildcard_preview_seconds,
            wildcard_bid_seconds=event_config.wildcard_bid_seconds,
            coding_duration_seconds=event_config.coding_duration_seconds,
        ),
        timing=EventTiming(**event_timing(config)),
    )

@router.get("/event/snapshot")
def get_event_snapshot(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return event_snapshot(db)

@router.get("/participant/problems")
def get_participant_problems(
    round: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Visible problems for the auction UI, with EventConfig-driven starting bids."""
    config = get_or_create_game_config(db)
    allowed_states = {
        1: {"ROUND1_PREVIEW", "ROUND1_BIDDING", "ROUND1_RESULT"},
        2: {"WILDCARD_PREVIEW", "WILDCARD_BIDDING", "WILDCARD_SELECTION"},
    }
    if round not in allowed_states or config.state not in allowed_states[round]:
        raise HTTPException(status_code=409, detail=f"Problem pool is not visible in state {config.state}.")
    event_config = get_or_create_event_config(db)
    starting_bid = event_config.wildcard_starting_bid if round == 2 else event_config.round1_minimum_bid
    problems = db.query(ProblemStatement).filter(
        ProblemStatement.round == round,
        ProblemStatement.status == "visible",
    ).all()
    return [
        {
            "id": ps.id,
            "number": idx + 1,
            "title": ps.title,
            "summary": ps.description or "",
            "description": ps.description or "",
            "startingBid": starting_bid,
            "available": True,
        }
        for idx, ps in enumerate(problems)
    ]

@router.get("/participant/leaderboard", response_model=list[LeaderboardEntry])
def get_leaderboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    config = get_or_create_game_config(db)
    if config.state not in ("ROUND1_BIDDING", "ROUND1_RESULT", "ROUND1_PREVIEW", "WILDCARD_APPLICATION", "WILDCARD_BIDDING", "WILDCARD_SELECTION"):
        # still show the current standings
        pass

    round_no = 1 if config.current_round == 1 else 2
    teams = db.query(Team).all()
    # current effective bid per team for this round
    bids = db.query(Bid).filter(Bid.round == round_no).order_by(Bid.timestamp.desc()).all()
    latest_by_team = {}
    for bid in bids:
        if bid.team_id not in latest_by_team:
            latest_by_team[bid.team_id] = bid

    ranked = sorted(
        [{"team": t, "bid": latest_by_team.get(t.id)} for t in teams],
        key=lambda item: (item["bid"].amount if item["bid"] else -1),
        reverse=True,
    )

    result = []
    for idx, item in enumerate(ranked, start=1):
        t = item["team"]
        bid = item["bid"]
        ps = None
        if t.ps_id:
            ps_obj = db.query(ProblemStatement).filter(ProblemStatement.id == t.ps_id).first()
            ps = ps_obj.title if ps_obj else None
        result.append(LeaderboardEntry(
            rank=idx,
            team_id=t.id,
            team_name=t.team_name,
            coins=t.coins,
            ps_title=ps,
            bid_amount=bid.amount if bid else None,
        ))
    return result

# ---------------------------------------------------------------- Submissions

@router.post("/submissions/me", status_code=201)
async def create_submission(
    submission: SubmissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team = ensure_leader(db, current_user)
    if not team.ps_id:
        raise HTTPException(status_code=400, detail="Team has no allocated problem.")
    if not submission.repository_url.startswith("https://github.com/"):
        raise HTTPException(status_code=400, detail="Repository URL must be a valid GitHub URL starting with https://github.com/")

    existing = db.query(Submission).filter(Submission.team_id == team.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Submission already exists. Use PUT /submissions/me to update.")

    new_submission = Submission(
        team_id=team.id,
        problem_id=team.ps_id,
        repository_url=submission.repository_url,
    )
    db.add(new_submission)
    db.commit()
    db.refresh(new_submission)

    await manager.broadcast_json({
        "type": "submission_updated",
        "team_name": team.team_name,
    })
    return DashboardSubmission(
        id=new_submission.id, problem_id=new_submission.problem_id,
        repository_url=new_submission.repository_url,
        submitted_at=new_submission.submitted_at, updated_at=new_submission.updated_at,
    )

@router.put("/submissions/me")
async def update_submission(
    submission: SubmissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team = ensure_leader(db, current_user)
    if not submission.repository_url.startswith("https://github.com/"):
        raise HTTPException(status_code=400, detail="Repository URL must be a valid GitHub URL starting with https://github.com/")

    existing = db.query(Submission).filter(Submission.team_id == team.id).first()
    if not existing:
        # act as create if none exists yet
        new_submission = Submission(
            team_id=team.id,
            problem_id=team.ps_id,
            repository_url=submission.repository_url,
        )
        db.add(new_submission)
        db.commit()
        db.refresh(new_submission)
        result = new_submission
    else:
        existing.repository_url = submission.repository_url
        existing.updated_at = member_utcnow()
        db.commit()
        db.refresh(existing)
        result = existing
    return DashboardSubmission(
        id=result.id, problem_id=result.problem_id,
        repository_url=result.repository_url,
        submitted_at=result.submitted_at, updated_at=result.updated_at,
    )

@router.get("/submissions/me")
def get_my_submission(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    team = get_team_for_user(db, current_user)
    if not team:
        raise HTTPException(status_code=404, detail="No team linked to this account")
    submission = db.query(Submission).filter(Submission.team_id == team.id).first()
    if not submission:
        return None
    return DashboardSubmission(
        id=submission.id, problem_id=submission.problem_id,
        repository_url=submission.repository_url,
        submitted_at=submission.submitted_at, updated_at=submission.updated_at,
    )

def member_utcnow():
    from datetime import datetime
    return datetime.utcnow()
