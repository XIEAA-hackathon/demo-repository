from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_
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


def reset_imported_participant_credentials(db: Session, *, actor: User) -> dict:
    """Remove import-created participant registration without resetting the event."""
    accounts = db.query(User).filter(
        User.account_source == "IMPORTED",
        User.role.in_(("leader", "member")),
        User.is_system_account.is_(False),
    ).all()
    account_ids = {account.id for account in accounts}
    account_emails = {account.email for account in accounts}

    registration_team_ids = {
        team_id
        for (team_id,) in db.query(RegistrationImportRow.team_id)
        .filter(RegistrationImportRow.team_id.is_not(None))
        .distinct()
        .all()
    }
    imported_teams = []
    if registration_team_ids and account_ids:
        # Registration rows identify teams touched by an import. Requiring the
        # team's leader to carry the import source marker avoids deleting a
        # pre-existing manually managed team that was merely updated by a sheet.
        imported_teams = db.query(Team).filter(
            Team.id.in_(registration_team_ids),
            Team.leader_id.in_(account_ids),
            Team.is_system_team.is_(False),
        ).all()
    imported_team_ids = {team.id for team in imported_teams}

    deleted = {
        "participant_accounts": len(accounts),
        "teams": len(imported_team_ids),
        "member_records": 0,
        "registration_rows": db.query(RegistrationImportRow).count(),
        "registration_imports": db.query(RegistrationImport).count(),
        "team_event_records": 0,
    }

    if account_ids:
        # Preserve submissions owned by retained manual teams while removing a
        # deleted imported participant as their historical submitting identity.
        db.query(Submission).filter(Submission.submitted_by_user_id.in_(account_ids)).update(
            {Submission.submitted_by_user_id: None},
            synchronize_session=False,
        )

    if imported_team_ids:
        for result_column in (
            FinalResult.first_place_team_id,
            FinalResult.second_place_team_id,
            FinalResult.third_place_team_id,
        ):
            db.query(FinalResult).filter(result_column.in_(imported_team_ids)).update(
                {result_column: None},
                synchronize_session=False,
            )
        db.query(WildcardSelectionPool).filter(
            WildcardSelectionPool.selected_by_team_id.in_(imported_team_ids)
        ).update(
            {WildcardSelectionPool.selected_by_team_id: None},
            synchronize_session=False,
        )

        dependent_queries = (
            db.query(Submission).filter(Submission.team_id.in_(imported_team_ids)),
            db.query(WildcardBid).filter(WildcardBid.team_id.in_(imported_team_ids)),
            db.query(Wildcard).filter(Wildcard.team_id.in_(imported_team_ids)),
            db.query(Bid).filter(Bid.team_id.in_(imported_team_ids)),
            db.query(ExchangeRequest).filter(or_(
                ExchangeRequest.requester_team_id.in_(imported_team_ids),
                ExchangeRequest.receiver_team_id.in_(imported_team_ids),
            )),
            db.query(WalletTransaction).filter(WalletTransaction.team_id.in_(imported_team_ids)),
        )
        for query in dependent_queries:
            deleted["team_event_records"] += query.delete(synchronize_session=False)

        team_member_query = db.query(Member).filter(Member.team_id.in_(imported_team_ids))
        deleted["member_records"] += team_member_query.delete(synchronize_session=False)

        # User.team_id uses SET NULL at the database layer; clear it explicitly
        # so the ORM state and deletion order remain deterministic.
        db.query(User).filter(User.team_id.in_(imported_team_ids)).update(
            {User.team_id: None},
            synchronize_session=False,
        )
        db.query(Team).filter(Team.id.in_(imported_team_ids)).delete(synchronize_session=False)

    if account_emails:
        # Imported members can have been added to a retained manual team. Their
        # Member row is registration-owned even when the team itself is not.
        retained_member_query = db.query(Member).filter(Member.email.in_(account_emails))
        if imported_team_ids:
            retained_member_query = retained_member_query.filter(Member.team_id.notin_(imported_team_ids))
        deleted["member_records"] += retained_member_query.delete(synchronize_session=False)

    if account_ids:
        # Avoid an ON DELETE CASCADE removing a retained team in inconsistent
        # legacy data where an imported account is still its leader.
        db.query(Team).filter(Team.leader_id.in_(account_ids)).update(
            {Team.leader_id: None},
            synchronize_session=False,
        )
        db.query(User).filter(User.id.in_(account_ids)).delete(synchronize_session=False)

    db.query(RegistrationImportRow).delete(synchronize_session=False)
    db.query(RegistrationImport).delete(synchronize_session=False)

    record_event(
        db,
        "registration.credentials_reset",
        actor=actor,
        metadata={
            "deleted_participant_accounts": deleted["participant_accounts"],
            "deleted_imported_teams": deleted["teams"],
            "deleted_registration_rows": deleted["registration_rows"],
            "event_lifecycle_reset": False,
        },
    )
    return {
        "participant_accounts": deleted["participant_accounts"],
        "sessions_invalidated": len(accounts),
        "deleted": deleted,
        "user_ids": sorted(account_ids),
    }


def reset_event_and_imported_participants(db: Session, *, actor: User, action: str) -> dict:
    """Stage an event-only reset without touching account credentials or identities."""
    event = get_or_create_event_config(db)
    game = get_or_create_game_config(db)
    # Match the mutation lock order used by bidding: game, round controls,
    # event configuration, then teams. This prevents a reset from racing a bid,
    # winner charge, assignment, or timer transition in another worker.
    game = db.query(GameConfig).filter(GameConfig.id == game.id).with_for_update().one()
    db.query(RoundControl).order_by(RoundControl.id.asc()).with_for_update().all()
    event = db.query(EventConfig).filter(EventConfig.id == event.id).with_for_update().one()
    locked_teams = db.query(Team).order_by(Team.id.asc()).with_for_update().all()

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

    for team in locked_teams:
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
