from __future__ import annotations

from threading import RLock

from sqlalchemy.orm import Session

from app.models.models import ProblemStatement, RoundControl, Team, WalletTransaction
from app.services.activity_log import record_event
from app.services.event_service import get_or_create_event_config, transition_event_state


ROUND1_BID_WINNER = "BID_WINNER"
ROUND1_AUTO_FINAL_PROBLEM = "AUTO_FINAL_PROBLEM"
ROUND1_AUTO_TRANSACTION = "ROUND1_AUTO_FINAL"
_FINALIZATION_LOCK = RLock()


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


def final_problem_price(db: Session) -> int:
    """Return the median of completed Round 1 winner charges, or the configured base bid."""
    charges = sorted(
        abs(row.amount)
        for row in db.query(WalletTransaction)
        .filter(
            WalletTransaction.transaction_type == "ROUND1_WIN",
            WalletTransaction.amount < 0,
        )
        .all()
    )
    if not charges:
        return max(0, get_or_create_event_config(db).round1_minimum_bid)
    middle = len(charges) // 2
    if len(charges) % 2:
        return charges[middle]
    return (charges[middle - 1] + charges[middle]) // 2


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
        "calculated_cost": final_problem_price(db),
        "team_count": len(teams),
        "teams": [{"team_id": team.id, "team_name": team.team_name} for team in teams],
    }


def auto_assign_final_problem(db: Session, control: RoundControl, *, actor=None) -> dict | None:
    """Atomically settle the final no-choice Round 1 problem for every eligible team."""
    with _FINALIZATION_LOCK:
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
        price = final_problem_price(db)
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
            "team_count": len(assignments),
            "teams": assignments,
        }
