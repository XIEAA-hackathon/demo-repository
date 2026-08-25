from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from urllib.parse import urlparse

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import User, Team, Member, Bid, Wildcard, WildcardBid, Submission, FinalResult, GameConfig, ProblemStatement
from app.schemas.schemas import (
    ParticipantDashboardResponse, DashboardUser, DashboardTeam, DashboardMember,
    DashboardLeader, DashboardProblem, DashboardBid, DashboardWildcard,
    DashboardSubmission, DashboardFinalResults, DashboardWinner, DashboardGameConfig, SubmissionCreate, SubmissionUpdate,
    EventTiming, LeaderboardEntry,
)
from app.api.auth import get_current_active_admin, get_current_active_participant
from app.services.event_service import (
    get_team_for_user, get_or_create_game_config, get_or_create_event_config, get_or_create_round_control,
    current_user_is_team_leader,
    ensure_leader, event_snapshot, event_timing, transition_event_state,
)
from app.api.websockets import manager
from app.services.wildcard_service import (
    available_wildcard_problems,
    current_selection,
    ranked_wildcard_bids,
    reconcile_wildcard_selection,
    selection_remaining_seconds,
)
from app.services.activity_log import record_event
from app.services.bid_cooldown import bid_cooldown_remaining

router = APIRouter()


def _dashboard_problem(problem: ProblemStatement | None) -> DashboardProblem | None:
    if not problem:
        return None
    return DashboardProblem(
        id=problem.id,
        ps_number=problem.ps_number.split("-", 1)[-1],
        title=problem.title,
        description=problem.description,
        round=problem.round,
        status=problem.status,
    )


def _valid_github_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    parts = [part for part in parsed.path.split("/") if part]
    return parsed.scheme == "https" and parsed.netloc.lower() in {"github.com", "www.github.com"} and len(parts) >= 2

@router.get("/participant/dashboard", response_model=ParticipantDashboardResponse)
def get_participant_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_participant)):
    reconcile_wildcard_selection(db)
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

    final_problem_obj = db.query(ProblemStatement).filter(ProblemStatement.id == team.ps_id).first() if team.ps_id else None
    round1_problem_obj = db.query(ProblemStatement).filter(ProblemStatement.id == team.round1_problem_id).first() if team.round1_problem_id else None
    wildcard_problem_obj = db.query(ProblemStatement).filter(ProblemStatement.id == team.wildcard_problem_id).first() if team.wildcard_problem_id else None
    # Compatibility for assignments created before explicit history fields existed.
    if final_problem_obj and final_problem_obj.round == 1 and not round1_problem_obj:
        round1_problem_obj = final_problem_obj
    if final_problem_obj and final_problem_obj.round == 2 and not wildcard_problem_obj:
        wildcard_problem_obj = final_problem_obj

    current_problem = _dashboard_problem(final_problem_obj)
    if not current_problem and config.state.startswith("ROUND1"):
        control = get_or_create_round_control(db, "ROUND1")
        current_problem = _dashboard_problem(
            db.query(ProblemStatement).filter(ProblemStatement.id == control.current_problem_id).first()
        )

    current_bid = None
    latest_bid = db.query(Bid).filter(Bid.team_id == team.id, Bid.round == 1).order_by(Bid.timestamp.desc()).first()
    if latest_bid:
        current_bid = DashboardBid(
            id=latest_bid.id, team_id=latest_bid.team_id, ps_id=latest_bid.ps_id,
            amount=latest_bid.amount, round=latest_bid.round, timestamp=latest_bid.timestamp,
        )

    wildcard = db.query(Wildcard).filter(Wildcard.team_id == team.id).first()
    wildcard_bid = db.query(WildcardBid).filter(WildcardBid.team_id == team.id).first()
    wildcard_out = None
    if wildcard:
        active_selection = current_selection(db)
        wildcard_control = get_or_create_round_control(db, "WILDCARD")
        wildcard_out = DashboardWildcard(
            status=wildcard.status,
            coins_paid=wildcard.coins_paid,
            used=wildcard.used,
            applied_at=wildcard.applied_at,
            rank=wildcard.rank,
            winning_bid=wildcard.winning_bid,
            problem_id=wildcard.problem_id,
            selected_at=wildcard.selected_at,
            selection_method=wildcard.selection_method,
            current_selection_rank=active_selection[0].rank if active_selection else None,
            current_selection_team=active_selection[1].team_name if active_selection else None,
            is_selection_turn=bool(active_selection and active_selection[1].id == team.id),
            available_problem_count=len(available_wildcard_problems(db)),
            slot_count=wildcard_control.slot_count,
            selection_started_at=wildcard_control.selection_started_at,
            selection_ends_at=wildcard_control.selection_ends_at,
            selection_duration_seconds=wildcard_control.selection_duration_seconds,
            selection_remaining_seconds=selection_remaining_seconds(wildcard_control),
        )

    submission = db.query(Submission).filter(Submission.team_id == team.id).first()
    submission_out = None
    if submission:
        submitter = db.query(User).filter(User.id == submission.submitted_by_user_id).first() if submission.submitted_by_user_id else None
        submission_out = DashboardSubmission(
            id=submission.id, problem_id=submission.problem_id,
            repository_url=submission.repository_url,
            submitted_at=submission.submitted_at, updated_at=submission.updated_at,
            submitted_by_user_id=submission.submitted_by_user_id,
            submitted_by_name=submitter.name if submitter else None,
        )

    final_results = None
    result = db.query(FinalResult).filter(FinalResult.result_status == "PUBLISHED").first()
    if result:
        winner_ids = [result.first_place_team_id, result.second_place_team_id, result.third_place_team_id]
        winning_teams = {row.id: row for row in db.query(Team).filter(Team.id.in_(winner_ids)).all()}
        if all(team_id in winning_teams for team_id in winner_ids):
            final_results = DashboardFinalResults(
                first_place=DashboardWinner(team_id=result.first_place_team_id, team_name=winning_teams[result.first_place_team_id].team_name),
                second_place=DashboardWinner(team_id=result.second_place_team_id, team_name=winning_teams[result.second_place_team_id].team_name),
                third_place=DashboardWinner(team_id=result.third_place_team_id, team_name=winning_teams[result.third_place_team_id].team_name),
            )

    cooldown_remaining = 0.0
    if config.state == "ROUND1_BIDDING":
        round_control = get_or_create_round_control(db, "ROUND1")
        cooldown_remaining = bid_cooldown_remaining(
            db,
            team.id,
            event_config.bid_cooldown_seconds or 0,
            round_type="ROUND1",
            problem_id=round_control.current_problem_id,
            round_number=config.current_round,
        )
    elif config.state == "WILDCARD_BIDDING":
        cooldown_remaining = bid_cooldown_remaining(
            db,
            team.id,
            event_config.bid_cooldown_seconds or 0,
            round_type="WILDCARD",
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
        round1Problem=_dashboard_problem(round1_problem_obj),
        wildcardProblem=_dashboard_problem(wildcard_problem_obj),
        finalProblem=_dashboard_problem(final_problem_obj),
        currentBid=current_bid,
        wildcardBidAmount=wildcard_bid.amount if wildcard_bid else None,
        wildcard=wildcard_out,
        submission=submission_out,
        finalResults=final_results,
        bidCooldownRemainingSeconds=cooldown_remaining,
        isLeader=is_leader,
        gameConfig=DashboardGameConfig(
            starting_coins=event_config.starting_coins,
            round1_winner_count=event_config.round1_winner_count,
            round1_minimum_bid=event_config.round1_minimum_bid,
            round1_bid_increment=event_config.round1_bid_increment,
            round1_preview_seconds=event_config.round1_preview_seconds,
            round1_bid_seconds=event_config.round1_bid_seconds,
            wildcard_slots=event_config.wildcard_slots,
            wildcard_application_seconds=event_config.wildcard_application_seconds,
            wildcard_starting_bid=event_config.wildcard_starting_bid,
            wildcard_bid_increment=event_config.wildcard_bid_increment,
            wildcard_preview_seconds=event_config.wildcard_preview_seconds,
            wildcard_bid_seconds=event_config.wildcard_bid_seconds,
            wildcard_selection_seconds=event_config.wildcard_selection_seconds,
            coding_duration_seconds=event_config.coding_duration_seconds,
            bid_cooldown_seconds=event_config.bid_cooldown_seconds,
        ),
        timing=EventTiming(**event_timing(config)),
        round1Assigned=round1_problem_obj is not None,
        wildcardEligible=bool(team.is_approved),
        wildcardApplicationsOpen=get_or_create_round_control(db, "WILDCARD").applications_open,
        submissionsOpen=bool(event_config.submissions_open),
    )

@router.get("/event/snapshot")
def get_event_snapshot(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_participant),
):
    return event_snapshot(db)

@router.get("/participant/problems")
def get_participant_problems(
    round: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_participant),
):
    """Visible problems for the auction UI, with EventConfig-driven starting bids."""
    config = get_or_create_game_config(db)
    allowed_states = {
        1: {"ROUND1_PREVIEW", "ROUND1_BIDDING", "ROUND1_RESULT"},
        2: {"WILDCARD_SELECTION"},
    }
    if round not in allowed_states or config.state not in allowed_states[round]:
        raise HTTPException(status_code=409, detail=f"Problem pool is not visible in state {config.state}.")
    event_config = get_or_create_event_config(db)
    starting_bid = event_config.round1_minimum_bid if round == 1 else 0
    if round == 2:
        reconcile_wildcard_selection(db)
        team = get_team_for_user(db, current_user)
        active = current_selection(db)
        if not team or not active or active[1].id != team.id:
            return []
        problems = available_wildcard_problems(db)
    else:
        control = get_or_create_round_control(db, "ROUND1")
        problems = db.query(ProblemStatement).filter(
            ProblemStatement.round == 1,
            ProblemStatement.id == control.current_problem_id,
        ).all()
    return [
        {
            "id": ps.id,
            "number": int(ps.ps_number.split("-", 1)[-1]) if ps.ps_number.split("-", 1)[-1].isdigit() else idx + 1,
            "title": ps.title,
            "summary": ps.description or "",
            "description": ps.description or "",
            "startingBid": starting_bid,
            "available": True,
        }
        for idx, ps in enumerate(problems)
    ]

@router.get("/participant/leaderboard", response_model=list[LeaderboardEntry])
def get_leaderboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_participant)):
    config = get_or_create_game_config(db)
    if config.current_round == 2:
        return [
            LeaderboardEntry(
                rank=index,
                team_id=team.id,
                team_name=team.team_name,
                coins=team.coins,
                ps_title=None,
                bid_amount=bid.amount,
            )
            for index, (bid, team, _application) in enumerate(ranked_wildcard_bids(db), start=1)
        ]

    control = get_or_create_round_control(db, "ROUND1")
    query = db.query(Bid, Team).join(Team, Team.id == Bid.team_id).filter(Bid.round == 1)
    if control.current_problem_id:
        query = query.filter(Bid.ps_id == control.current_problem_id)
    rows = query.order_by(Bid.amount.desc(), Bid.timestamp.asc(), Bid.team_id.asc()).all()
    return [
        LeaderboardEntry(
            rank=index,
            team_id=team.id,
            team_name=team.team_name,
            coins=team.coins,
            ps_title=None,
            bid_amount=bid.amount,
        )
        for index, (bid, team) in enumerate(rows, start=1)
    ]

# ---------------------------------------------------------------- Submissions

@router.post("/submissions/me", status_code=201)
async def create_submission(
    submission: SubmissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_participant),
):
    team = ensure_leader(db, current_user)
    if not get_or_create_event_config(db).submissions_open:
        raise HTTPException(status_code=409, detail="Submissions are closed.")
    if not team.ps_id:
        raise HTTPException(status_code=400, detail="Team has no allocated problem.")
    if not _valid_github_url(submission.repository_url):
        raise HTTPException(status_code=400, detail="Enter a valid public GitHub repository URL.")

    existing = db.query(Submission).filter(Submission.team_id == team.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Submission already exists. Use PUT /submissions/me to update.")

    new_submission = Submission(
        team_id=team.id,
        problem_id=team.ps_id,
        submitted_by_user_id=current_user.id,
        repository_url=submission.repository_url.strip(),
    )
    db.add(new_submission)
    record_event(db, "submission.created", actor=current_user, entity_type="team", entity_id=team.id, metadata={"problem_id": team.ps_id})
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
        submitted_by_user_id=current_user.id, submitted_by_name=current_user.name,
    )

@router.put("/submissions/me")
async def update_submission(
    submission: SubmissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_participant),
):
    team = ensure_leader(db, current_user)
    if not get_or_create_event_config(db).submissions_open:
        raise HTTPException(status_code=409, detail="Submissions are closed.")
    if not team.ps_id:
        raise HTTPException(status_code=400, detail="Team has no final problem.")
    if not _valid_github_url(submission.repository_url):
        raise HTTPException(status_code=400, detail="Enter a valid public GitHub repository URL.")

    existing = db.query(Submission).filter(Submission.team_id == team.id).first()
    if not existing:
        # act as create if none exists yet
        new_submission = Submission(
            team_id=team.id,
            problem_id=team.ps_id,
            submitted_by_user_id=current_user.id,
            repository_url=submission.repository_url.strip(),
        )
        db.add(new_submission)
        record_event(db, "submission.created", actor=current_user, entity_type="team", entity_id=team.id, metadata={"problem_id": team.ps_id})
        db.commit()
        db.refresh(new_submission)
        result = new_submission
    else:
        existing.repository_url = submission.repository_url.strip()
        existing.problem_id = team.ps_id
        existing.submitted_by_user_id = current_user.id
        existing.updated_at = member_utcnow()
        record_event(db, "submission.updated", actor=current_user, entity_type="team", entity_id=team.id, metadata={"problem_id": team.ps_id})
        db.commit()
        db.refresh(existing)
        result = existing
    return DashboardSubmission(
        id=result.id, problem_id=result.problem_id,
        repository_url=result.repository_url,
        submitted_at=result.submitted_at, updated_at=result.updated_at,
        submitted_by_user_id=current_user.id, submitted_by_name=current_user.name,
    )

@router.get("/submissions/me")
def get_my_submission(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_participant)):
    team = get_team_for_user(db, current_user)
    if not team:
        raise HTTPException(status_code=404, detail="No team linked to this account")
    submission = db.query(Submission).filter(Submission.team_id == team.id).first()
    if not submission:
        return None
    submitter = db.query(User).filter(User.id == submission.submitted_by_user_id).first() if submission.submitted_by_user_id else None
    return DashboardSubmission(
        id=submission.id, problem_id=submission.problem_id,
        repository_url=submission.repository_url,
        submitted_at=submission.submitted_at, updated_at=submission.updated_at,
        submitted_by_user_id=submission.submitted_by_user_id,
        submitted_by_name=submitter.name if submitter else None,
    )


@router.get("/admin/submissions")
def get_admin_submissions(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    del current_user
    config = get_or_create_event_config(db)
    rows = []
    teams = db.query(Team).order_by(Team.team_name.asc()).all()
    for team in teams:
        submission = db.query(Submission).filter(Submission.team_id == team.id).first()
        submitter = db.query(User).filter(User.id == submission.submitted_by_user_id).first() if submission and submission.submitted_by_user_id else None
        final_problem = db.query(ProblemStatement).filter(ProblemStatement.id == team.ps_id).first() if team.ps_id else None
        final_problem_payload = ({
            "id": final_problem.id,
            "ps_number": final_problem.ps_number.split("-", 1)[-1],
            "title": final_problem.title,
            "description": final_problem.description,
            "round": final_problem.round,
            "status": final_problem.status,
        } if final_problem else None)
        rows.append({
            "team_id": team.id,
            "team_name": team.team_name,
            "status": "SUBMITTED" if submission else "PENDING",
            "github_url": submission.repository_url if submission else None,
            "submitted_at": submission.submitted_at if submission else None,
            "updated_at": submission.updated_at if submission else None,
            "submitted_by": submitter.name if submitter else None,
            "final_problem": final_problem_payload,
        })
    submitted = sum(row["status"] == "SUBMITTED" for row in rows)
    return {
        "open": bool(config.submissions_open),
        "total": len(rows),
        "submitted": submitted,
        "pending": len(rows) - submitted,
        "rows": rows,
    }


@router.post("/admin/submissions/open")
async def open_submissions(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    if get_or_create_event_config(db).submissions_open:
        return get_admin_submissions(db, None)
    round_one = get_or_create_round_control(db, "ROUND1")
    wildcard_control = get_or_create_round_control(db, "WILDCARD")
    if not round_one.ended:
        raise HTTPException(status_code=409, detail="End Round 1 before opening submissions.")
    if wildcard_control.status not in {"NOT_STARTED", "COMPLETE"}:
        raise HTTPException(status_code=409, detail="Complete Wildcard problem selection before opening submissions.")
    event_config = get_or_create_event_config(db)
    event_config.submissions_open = True
    transition_event_state(db, "SUBMISSION", validate=False, commit=False)
    record_event(db, "submissions.opened", actor=current_user)
    db.commit()
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return get_admin_submissions(db, None)


@router.post("/admin/submissions/close")
async def close_submissions(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_admin)):
    event_config = get_or_create_event_config(db)
    if event_config.submissions_open:
        event_config.submissions_open = False
        record_event(db, "submissions.closed", actor=current_user)
    game = get_or_create_game_config(db)
    if game.state == "SUBMISSION":
        transition_event_state(db, "JUDGING_WAIT", commit=False)
        record_event(db, "judging.started", actor=current_user)
    db.commit()
    await manager.broadcast_event("submission_updated", {"action": "submissions_closed"})
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return get_admin_submissions(db, None)

def member_utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
