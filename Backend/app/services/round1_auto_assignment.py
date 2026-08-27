from __future__ import annotations

from threading import RLock

from sqlalchemy.orm import Session

from app.models.models import ProblemStatement, RoundControl, Team, WalletTransaction
from app.services.activity_log import record_event
from app.services.event_service import get_or_create_event_config, transition_event_state


ROUND1_BID_WINNER = "BID_WINNER"
ROUND1_AUTO_FINAL_PROBLEM = "AUTO_FINAL_PROBLEM"
ROUND1_AUTO_TRANSACTION = "ROUND1_AUTO_FINAL"
ROUND1_FINALIZATION_LOCK = RLock()


def _display_number(problem: ProblemStatement) -> str:
    return problem.ps_number.split("-", 1)[-1]


def _selectable_problems(db: Session, *, lock: bool = False) -> list[ProblemStatement]:
    query = (
        db.query(ProblemStatement)
        .filter(
            ProblemStatement.round == 1,
            ProblemStatement.status.in_(("available", "visible", "current")),
        )
        .order_by(ProblemStatement.id.asc())
    )
    if lock:
        query = query.with_for_update()
    return query.all()


def is_final_auto_allotment_problem(db: Session, problem_id: int | None) -> bool:
    """Return true when the referenced problem is the sole unused Round 1 problem."""
    if problem_id is None:
        return False
    problems = _selectable_problems(db)
    return len(problems) == 1 and problems[0].id == problem_id


def _eligible_teams(db: Session, *, lock: bool = False) -> list[Team]:
    query = (
        db.query(Team)
        .filter(
            Team.is_approved.is_(True),
            Team.round1_problem_id.is_(None),
            Team.ps_id.is_(None),
        )
        .order_by(Team.id.asc())
    )
    if lock:
        query = query.with_for_update()
    return query.all()


def update_round1_winning_bid_aggregate(
    control: RoundControl,
    problem: ProblemStatement,
    winner_amounts: list[int],
) -> bool:
    """Add one normal auction's final winner prices exactly once before completion."""
    if problem.status in {"completed", "allocated"} or not winner_amounts:
        return False
    control.round1_winning_bid_sum = (control.round1_winning_bid_sum or 0) + sum(winner_amounts)
    control.round1_winning_bid_count = (control.round1_winning_bid_count or 0) + len(winner_amounts)
    return True


def final_problem_price(db: Session, control: RoundControl) -> int:
    """Return the rounded running winner average, or the configured base bid."""
    winning_count = control.round1_winning_bid_count or 0
    if winning_count <= 0:
        return max(0, get_or_create_event_config(db).round1_minimum_bid)
    winning_sum = control.round1_winning_bid_sum or 0
    return (winning_sum + (winning_count // 2)) // winning_count


def _completed_normal_auction_count(db: Session, control: RoundControl) -> int:
    query = db.query(ProblemStatement).filter(
        ProblemStatement.round == 1,
        ProblemStatement.status.in_(("completed", "allocated")),
    )
    if control.final_auto_assignment_problem_id is not None:
        query = query.filter(ProblemStatement.id != control.final_auto_assignment_problem_id)
    return query.count()


def final_auto_assignment_summary(db: Session, control: RoundControl) -> dict | None:
    if control.final_auto_assignment_problem_id is not None:
        problem = db.query(ProblemStatement).filter(
            ProblemStatement.id == control.final_auto_assignment_problem_id
        ).first()
        teams = (
            db.query(Team)
            .filter(
                Team.round1_problem_id == control.final_auto_assignment_problem_id,
                Team.round1_assignment_type == ROUND1_AUTO_FINAL_PROBLEM,
            )
            .order_by(Team.id.asc())
            .all()
        )
        if not problem:
            return None
        return {
            "status": "COMPLETED",
            "problem": {
                "id": problem.id,
                "problem_number": _display_number(problem),
                "title": problem.title,
                "description": problem.description,
            },
            "calculated_cost": control.final_auto_assignment_price or 0,
            "suggested_deduction": final_problem_price(db, control),
            "deduction_per_team": control.final_auto_assignment_price or 0,
            "completed_auctions": _completed_normal_auction_count(db, control),
            "round1_winning_bid_sum": control.round1_winning_bid_sum or 0,
            "round1_winning_bid_count": control.round1_winning_bid_count or 0,
            "team_count": control.final_auto_assignment_team_count or len(teams),
            "teams": [{"team_id": team.id, "team_name": team.team_name} for team in teams],
        }

    problems = _selectable_problems(db)
    teams = _eligible_teams(db)
    if len(problems) != 1 or not teams:
        return None
    problem = problems[0]
    return {
        "status": "PENDING",
        "problem": {
            "id": problem.id,
            "problem_number": _display_number(problem),
            "title": problem.title,
            "description": problem.description,
        },
        "calculated_cost": final_problem_price(db, control),
        "suggested_deduction": final_problem_price(db, control),
        "deduction_per_team": final_problem_price(db, control),
        "completed_auctions": _completed_normal_auction_count(db, control),
        "round1_winning_bid_sum": control.round1_winning_bid_sum or 0,
        "round1_winning_bid_count": control.round1_winning_bid_count or 0,
        "team_count": len(teams),
        "teams": [{"team_id": team.id, "team_name": team.team_name} for team in teams],
    }


def auto_assign_final_problem(
    db: Session,
    control: RoundControl,
    *,
    actor=None,
    price_override: int | None = None,
) -> dict | None:
    """Atomically settle the final no-choice Round 1 problem for every eligible team."""
    with ROUND1_FINALIZATION_LOCK:
        db.flush()
        control = (
            db.query(RoundControl)
            .filter(RoundControl.id == control.id)
            .with_for_update()
            .populate_existing()
            .one()
        )
        if control.final_auto_assignment_problem_id is not None:
            return final_auto_assignment_summary(db, control)

        problems = _selectable_problems(db, lock=True)
        teams = _eligible_teams(db, lock=True)
        if len(problems) != 1 or not teams:
            return None

        problem = problems[0]
        price = final_problem_price(db, control) if price_override is None else max(0, int(price_override))
        assignments = []
        for team in teams:
            charge = min(price, max(0, team.coins or 0))
            team.coins = max(0, (team.coins or 0) - charge)
            team.ps_id = problem.id
            team.round1_problem_id = problem.id
            team.round1_assignment_type = ROUND1_AUTO_FINAL_PROBLEM
            team.round1_assignment_cost = charge
            db.add(WalletTransaction(
                team_id=team.id,
                transaction_type=ROUND1_AUTO_TRANSACTION,
                amount=-charge,
                description=f"Automatic final Round 1 assignment for problem {_display_number(problem)}",
            ))
            assignments.append({
                "team_id": team.id,
                "team_name": team.team_name,
                "amount": charge,
            })

        problem.status = "completed"
        control.current_problem_id = None
        control.status = "READY"
        control.final_auto_assignment_problem_id = problem.id
        control.final_auto_assignment_price = price
        control.final_auto_assignment_team_count = len(assignments)
        transition_event_state(db, "ROUND1_RESULT", validate=False, commit=False)
        record_event(
            db,
            "round1.final_problem_auto_assigned",
            actor=actor,
            entity_type="problem",
            entity_id=problem.id,
            metadata={
                "team_count": len(assignments),
                "calculated_cost": price,
                "team_ids": [assignment["team_id"] for assignment in assignments],
            },
        )
        db.flush()
        return {
            "status": "COMPLETED",
            "problem": {
                "id": problem.id,
                "problem_number": _display_number(problem),
                "title": problem.title,
                "description": problem.description,
            },
            "calculated_cost": price,
            "suggested_deduction": final_problem_price(db, control),
            "deduction_per_team": price,
            "completed_auctions": _completed_normal_auction_count(db, control),
            "round1_winning_bid_sum": control.round1_winning_bid_sum or 0,
            "round1_winning_bid_count": control.round1_winning_bid_count or 0,
            "team_count": len(assignments),
            "teams": assignments,
        }
