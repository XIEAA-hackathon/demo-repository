from __future__ import annotations

from datetime import datetime, timezone
import secrets

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
from app.core.security import get_password_hash
from app.core.event_constants import ROUND1_BASE_BID_DEFAULT, ROUND1_WINNER_COUNT, WILDCARD_BASE_BID_DEFAULT


def reset_imported_participant_credentials(db: Session, *, actor: User) -> dict:
    """Invalidate imported participant authentication without touching event data."""
    accounts = db.query(User).filter(
        User.account_source == "IMPORTED",
        User.role.in_(("leader", "member")),
        User.is_system_account.is_(False),
    ).all()
    for account in accounts:
        account.password_hash = get_password_hash(secrets.token_urlsafe(48))
        account.session_id = secrets.token_hex(32)
        account.credentials_active = False

    record_event(
        db,
        "registration.credentials_reset",
        actor=actor,
        metadata={"reset_participant_accounts": len(accounts)},
    )
    return {
        "participant_accounts": len(accounts),
        "sessions_invalidated": len(accounts),
    }


def reset_event_and_imported_participants(db: Session, *, actor: User, action: str) -> dict:
    """Stage an event-only reset without touching account credentials or identities."""
    event = get_or_create_event_config(db)
    game = get_or_create_game_config(db)

    deleted = {
        "teams": 0,
        "participant_users": 0,
        "team_members": 0,
        "registration_imports": 0,
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

    # Delete dependent event records before uploaded problems. Registration,
    # teams, users, password hashes, credential state, and sessions are identity
    # data and deliberately remain outside this transaction's reset scope.
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
    db.query(EventActivityLog).delete(synchronize_session=False)

    for team in db.query(Team).all():
        team.coins = event.starting_coins
        team.ps_id = None
        team.round1_problem_id = None
        team.wildcard_problem_id = None
        team.round1_assignment_type = None
        team.round1_assignment_cost = None
        team.is_approved = True
        db.add(WalletTransaction(
            team_id=team.id,
            transaction_type="INITIAL_ALLOCATION",
            amount=event.starting_coins,
            description="Initial AlumniCoins after event reset",
        ))

    db.query(RoundControl).delete(synchronize_session=False)
    db.query(ProblemStatement).delete(synchronize_session=False)
    db.add_all([
        RoundControl(
            round_type="ROUND1",
            status="IDLE",
            ended=False,
            applications_open=False,
            round1_winning_bid_sum=0,
            round1_winning_bid_count=0,
        ),
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
            "preserved_teams": db.query(Team).count(),
            "authentication_records_touched": False,
        },
    )
    return deleted
