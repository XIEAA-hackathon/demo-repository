from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import (
    Bid,
    EventActivityLog,
    ExchangeRequest,
    FinalResult,
    Member,
    ProblemStatement,
    RegistrationImport,
    RegistrationImportRow,
    RoundControl,
    Submission,
    Team,
    User,
    WalletTransaction,
    Wildcard,
    WildcardBid,
    WildcardSelectionPool,
)
from app.services.activity_log import record_event
from app.services.event_service import get_or_create_event_config, get_or_create_game_config
from app.core.event_constants import ROUND1_BASE_BID_DEFAULT, ROUND1_WINNER_COUNT, WILDCARD_BASE_BID_DEFAULT


def reset_event_and_imported_participants(db: Session, *, actor: User, action: str) -> dict:
    """Stage a complete event reset in the caller's database transaction.

    Imported participants, problem uploads, and their registration records are
    removed to preserve the existing Reset Event contract. Marked system/demo
    accounts and teams, plus unrelated global EventConfig values, are retained.
    """
    event = get_or_create_event_config(db)
    game = get_or_create_game_config(db)
    non_system_teams = db.query(Team).filter(Team.is_system_team.is_(False)).all()
    non_system_team_ids = [team.id for team in non_system_teams]
    participant_users = db.query(User).filter(
        User.role.in_(("leader", "member")),
        User.is_system_account.is_(False),
    ).all()
    participant_user_ids = [user.id for user in participant_users]

    deleted = {
        "teams": len(non_system_teams),
        "participant_users": len(participant_users),
        "team_members": db.query(Member).filter(Member.team_id.in_(non_system_team_ids)).count() if non_system_team_ids else 0,
        "registration_imports": db.query(RegistrationImport).count(),
        "round1_problems": db.query(ProblemStatement).filter(ProblemStatement.round == 1).count(),
        "wildcard_problems": db.query(ProblemStatement).filter(ProblemStatement.round == 2).count(),
        "bids": db.query(Bid).count(),
        "wildcard_applications": db.query(Wildcard).count(),
        "wildcard_bids": db.query(WildcardBid).count(),
        "wildcard_selections": db.query(WildcardSelectionPool).count(),
        "submissions": db.query(Submission).count(),
        "final_results": db.query(FinalResult).count(),
        "exchange_requests": db.query(ExchangeRequest).count(),
        "wallet_transactions": db.query(WalletTransaction).count(),
        "activity_entries": db.query(EventActivityLog).count(),
    }

    # Delete dependent event records before teams, users, and problems.
    for model in (
        FinalResult,
        Submission,
        WildcardSelectionPool,
        WildcardBid,
        Wildcard,
        Bid,
        ExchangeRequest,
        WalletTransaction,
    ):
        db.query(model).delete(synchronize_session=False)
    db.query(RegistrationImportRow).delete(synchronize_session=False)
    db.query(RegistrationImport).delete(synchronize_session=False)
    db.query(EventActivityLog).delete(synchronize_session=False)

    for team in db.query(Team).filter(Team.is_system_team.is_(True)).all():
        team.coins = event.starting_coins
        team.ps_id = None
        team.round1_problem_id = None
        team.wildcard_problem_id = None
        team.is_approved = True

    if non_system_team_ids:
        db.query(Member).filter(Member.team_id.in_(non_system_team_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.team_id.in_(non_system_team_ids)).update(
            {User.team_id: None, User.session_id: None},
            synchronize_session=False,
        )
        db.query(Team).filter(Team.id.in_(non_system_team_ids)).delete(synchronize_session=False)
    if participant_user_ids:
        db.query(User).filter(User.id.in_(participant_user_ids)).delete(synchronize_session=False)

    db.query(RoundControl).delete(synchronize_session=False)
    db.query(ProblemStatement).delete(synchronize_session=False)
    db.add_all([
        RoundControl(round_type="ROUND1", status="IDLE", ended=False, applications_open=False),
        RoundControl(round_type="WILDCARD", status="NOT_STARTED", ended=False, applications_open=False),
    ])

    now = datetime.now(timezone.utc)
    game.state = "WAITING"
    game.current_round = 1
    game.phase_started_at = None
    game.auction_timer_end = None
    game.timer_paused = False
    game.timer_paused_remaining_seconds = None
    game.timer_bias_seconds = 0
    game.wildcards_visible = False
    game.last_state_update = now
    event.submissions_open = False
    event.round1_winner_count = ROUND1_WINNER_COUNT
    event.round1_minimum_bid = ROUND1_BASE_BID_DEFAULT
    event.wildcard_starting_bid = WILDCARD_BASE_BID_DEFAULT

    record_event(
        db,
        action,
        actor=actor,
        metadata={
            "deleted_teams": deleted["teams"],
            "deleted_participant_users": deleted["participant_users"],
        },
    )
    return deleted
