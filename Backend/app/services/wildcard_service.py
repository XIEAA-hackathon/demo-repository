from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.models import (
    EventConfig,
    ProblemStatement,
    RoundControl,
    Team,
    WalletTransaction,
    Wildcard,
    WildcardBid,
    WildcardSelectionPool,
)
from app.services.activity_log import record_event
from app.services.event_service import (
    _remaining_seconds,
    event_snapshot,
    get_or_create_event_config,
    get_or_create_game_config,
    get_or_create_round_control,
)

WILDCARD_STATES = (
    "NOT_STARTED",
    "APPLICATIONS_OPEN",
    "APPLICATIONS_CLOSED",
    "BIDDING_OPEN",
    "BIDDING_CLOSED",
    "PROBLEM_SELECTION",
    "COMPLETE",
)


def display_problem_number(problem: ProblemStatement) -> str:
    return problem.ps_number.split("-", 1)[-1]


def wildcard_problems(db: Session) -> list[ProblemStatement]:
    return (
        db.query(ProblemStatement)
        .filter(ProblemStatement.round == 2)
        .order_by(ProblemStatement.id.asc())
        .all()
    )


def available_wildcard_problems(db: Session) -> list[ProblemStatement]:
    pool_exists = db.query(WildcardSelectionPool.id).first() is not None
    if pool_exists:
        return (
            db.query(ProblemStatement)
            .join(WildcardSelectionPool, WildcardSelectionPool.problem_id == ProblemStatement.id)
            .filter(WildcardSelectionPool.selected_by_team_id.is_(None))
            .order_by(WildcardSelectionPool.position.asc())
            .all()
        )
    return (
        db.query(ProblemStatement)
        .filter(
            ProblemStatement.round == 2,
            ProblemStatement.status.in_(("available", "visible")),
        )
        .order_by(ProblemStatement.id.asc())
        .all()
    )


def selection_pool(db: Session) -> list[WildcardSelectionPool]:
    return db.query(WildcardSelectionPool).order_by(WildcardSelectionPool.position.asc()).all()


def freeze_selection_pool(db: Session, control: RoundControl) -> list[WildcardSelectionPool]:
    """Create the deterministic, immutable N-problem selection snapshot once."""
    existing = selection_pool(db)
    if existing:
        if len(existing) != (control.slot_count or 0):
            raise ValueError("The persisted Wildcard pool does not match the confirmed slot count.")
        return existing

    slot_count = control.slot_count or 0
    problems = (
        db.query(ProblemStatement)
        .filter(
            ProblemStatement.round == 2,
            ProblemStatement.status.in_(("available", "visible")),
        )
        .order_by(ProblemStatement.id.asc())
        .limit(slot_count)
        .all()
    )
    if len(problems) != slot_count:
        raise ValueError(f"Wildcard requires {slot_count} available problems but only {len(problems)} remain.")
    now = datetime.utcnow()
    rows = [
        WildcardSelectionPool(position=index, problem_id=problem.id, frozen_at=now)
        for index, problem in enumerate(problems, start=1)
    ]
    db.add_all(rows)
    control.selection_pool_frozen_at = now
    db.flush()
    return rows


def problem_payload(problem: ProblemStatement) -> dict:
    return {
        "id": problem.id,
        "problem_number": display_problem_number(problem),
        "problem_statement": problem.description or problem.title,
        "status": "SELECTED" if problem.status == "allocated" else "AVAILABLE",
    }


def sync_application_window(db: Session, control: RoundControl | None = None) -> RoundControl:
    control = control or get_or_create_round_control(db, "WILDCARD")
    game = get_or_create_game_config(db)
    if control.status == "APPLICATIONS_OPEN" and control.applications_open and _remaining_seconds(game) == 0:
        control.applications_open = False
        control.status = "APPLICATIONS_CLOSED"
        db.commit()
        db.refresh(control)
    return control


def eligible_team_count(db: Session) -> int:
    return db.query(Team).filter(Team.is_approved.is_(True)).count()


def ranked_wildcard_bids(db: Session) -> list[tuple[WildcardBid, Team, Wildcard]]:
    return (
        db.query(WildcardBid, Team, Wildcard)
        .join(Team, Team.id == WildcardBid.team_id)
        .join(Wildcard, Wildcard.team_id == WildcardBid.team_id)
        .filter(Wildcard.status.in_(("applied", "qualified", "selected", "eliminated")))
        .order_by(WildcardBid.amount.desc(), WildcardBid.timestamp.asc(), WildcardBid.team_id.asc())
        .all()
    )


def ranking_payload(db: Session, control: RoundControl | None = None) -> list[dict]:
    control = control or get_or_create_round_control(db, "WILDCARD")
    finalized = control.status in {"PROBLEM_SELECTION", "COMPLETE"}
    rows = []
    for position, (bid, team, application) in enumerate(ranked_wildcard_bids(db), start=1):
        rows.append({
            "rank": application.rank if finalized and application.rank else position,
            "team_id": team.id,
            "team_name": team.team_name,
            "value": bid.amount,
            "qualified": application.status in {"qualified", "selected"},
        })
    return rows


def ordered_qualifications(db: Session) -> list[tuple[Wildcard, Team]]:
    return (
        db.query(Wildcard, Team)
        .join(Team, Team.id == Wildcard.team_id)
        .filter(Wildcard.status.in_(("qualified", "selected")), Wildcard.rank.is_not(None))
        .order_by(Wildcard.rank.asc())
        .all()
    )


def current_selection(db: Session) -> tuple[Wildcard, Team] | None:
    return (
        db.query(Wildcard, Team)
        .join(Team, Team.id == Wildcard.team_id)
        .filter(Wildcard.status == "qualified", Wildcard.problem_id.is_(None))
        .order_by(Wildcard.rank.asc())
        .first()
    )


def finalize_slot_bidding(db: Session, control: RoundControl, *, commit: bool = True) -> list[dict]:
    """Persist the deterministic top-N result and charge each winner once.

    Ordering is bid amount descending, then the earlier timestamp at which the
    team's final amount was reached, then team id as a stable final fallback.
    """
    if control.status in {"PROBLEM_SELECTION", "COMPLETE"}:
        return [
            {
                "rank": application.rank,
                "team_id": team.id,
                "team_name": team.team_name,
                "winning_bid": application.winning_bid,
            }
            for application, team in ordered_qualifications(db)
        ]

    slot_count = control.slot_count or 0
    rows = [
        (bid, team, application)
        for bid, team, application in ranked_wildcard_bids(db)
        if application.status == "applied" and bid.amount <= team.coins
    ]
    if len(rows) < slot_count:
        raise ValueError(f"At least {slot_count} valid Wildcard bids are required before finalization.")
    freeze_selection_pool(db, control)
    applicants = db.query(Wildcard).filter(Wildcard.status == "applied").all()
    for application in applicants:
        application.status = "eliminated"
        application.rank = None
        application.winning_bid = None

    winners = []
    for rank, (bid, team, application) in enumerate(rows[:slot_count], start=1):
        application.status = "qualified"
        application.rank = rank
        application.winning_bid = bid.amount
        application.coins_paid = bid.amount
        team.coins -= bid.amount
        db.add(WalletTransaction(
            team_id=team.id,
            transaction_type="WILDCARD_WIN",
            amount=-bid.amount,
            description=f"Wildcard slot rank #{rank}",
        ))
        record_event(
            db,
            "wildcard.team_qualified",
            actor_type="system",
            entity_type="team",
            entity_id=team.id,
            metadata={"rank": rank, "winning_bid": bid.amount},
        )
        winners.append({
            "rank": rank,
            "team_id": team.id,
            "team_name": team.team_name,
            "winning_bid": bid.amount,
        })

    control.status = "PROBLEM_SELECTION" if winners else "COMPLETE"
    control.ended = not winners
    record_event(
        db,
        "wildcard.selection_pool_frozen",
        actor_type="system",
        metadata={"slot_count": slot_count, "problem_ids": [row.problem_id for row in selection_pool(db)]},
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return winners


def wildcard_payload(db: Session) -> dict:
    control = sync_application_window(db)
    config: EventConfig = get_or_create_event_config(db)
    applications = db.query(Wildcard).all()
    eligible = eligible_team_count(db)
    applied = sum(record.status in {"applied", "qualified", "selected", "eliminated"} for record in applications)
    declined = sum(record.status == "declined" for record in applications)
    problems = wildcard_problems(db)
    pool_rows = selection_pool(db)
    problem_by_id = {problem.id: problem for problem in problems}
    available = available_wildcard_problems(db)
    qualifications = []
    active = current_selection(db)
    for application, team in ordered_qualifications(db):
        selected_problem = next((problem for problem in problems if problem.id == application.problem_id), None)
        qualifications.append({
            "rank": application.rank,
            "team_id": team.id,
            "team_name": team.team_name,
            "winning_bid": application.winning_bid,
            "status": "SELECTED" if application.status == "selected" else "CHOOSING" if active and active[0].team_id == team.id else "WAITING",
            "problem": problem_payload(selected_problem) if selected_problem else None,
        })
    max_slots = min(applied, len(problems))
    return {
        "round_type": "WILDCARD",
        "status": control.status,
        "ended": control.ended,
        "problems": [problem_payload(problem) for problem in problems],
        "applications": {
            "open": control.status == "APPLICATIONS_OPEN" and control.applications_open,
            "status": "OPEN" if control.status == "APPLICATIONS_OPEN" else "COMPLETE" if control.status not in {"NOT_STARTED", "APPLICATIONS_CLOSED"} else "CLOSED",
            "eligible": eligible,
            "applied": applied,
            "declined": declined,
            "pending": max(0, eligible - applied - declined),
        },
        "slots": {
            "count": control.slot_count,
            "confirmed": control.slot_count is not None,
            "maximum": max_slots,
        },
        "bidding": {
            "open": control.status == "BIDDING_OPEN",
            "ranking": ranking_payload(db, control),
        },
        "selection": {
            "current_rank": active[0].rank if active else None,
            "current_team_id": active[1].id if active else None,
            "current_team": active[1].team_name if active else None,
            "qualifications": qualifications,
            "available_problems": [problem_payload(problem) for problem in available],
            "pool_frozen": bool(pool_rows),
            "pool_frozen_at": control.selection_pool_frozen_at,
            "pool": [
                {
                    "position": row.position,
                    "selected": row.selected_by_team_id is not None,
                    "selected_by_team_id": row.selected_by_team_id,
                    "problem": problem_payload(problem_by_id[row.problem_id]),
                }
                for row in pool_rows
                if row.problem_id in problem_by_id
            ],
        },
        "settings": {
            "application_seconds": config.wildcard_application_seconds,
            "bidding_seconds": config.wildcard_bid_seconds,
            "wildcard_slots": control.slot_count or config.wildcard_slots,
        },
        "event": event_snapshot(db),
    }
