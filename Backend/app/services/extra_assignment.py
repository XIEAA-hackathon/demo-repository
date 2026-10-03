"""Extra/Grid assignment; auction results/history remain immutable."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Bid, EventConfig, ProblemStatement, RoundControl, Team, WalletTransaction
from app.services.round1_assignment import EXTERNAL_PROBLEM_ROUND, ROUND1_PROBLEM_CAPACITY, ROUND1_FINALIZATION_LOCK, current_problem_teams, problem_capacity_remaining, round1_assignment_management_payload


class ExtraAssignmentError(ValueError):
    pass


EXTRA_GRID_TRANSACTION = "EXTRA_GRID_AUTO_ASSIGN"


def is_extra_assignment_candidate(team: Team) -> bool:
    return (team.is_approved and not team.is_system_team and team.ps_id is None
            and team.round1_problem_id is None and team.wildcard_problem_id is None)


def automatic_assignment_price(db: Session) -> dict:
    # Include every persisted R1 bid across problems, including losing bids.
    total, count = db.query(func.coalesce(func.sum(Bid.amount), 0), func.count(Bid.id)).filter(Bid.round == 1).one()
    config = db.query(EventConfig.round1_minimum_bid).first() if not count else None
    deduction = ((total + count // 2) // count if count else
                 config.round1_minimum_bid if config else EventConfig.__table__.c.round1_minimum_bid.default.arg)
    return {"suggested_auto_deduction": deduction, "r1_bid_sum": total, "r1_bid_count": count,
            "automatic_price_source": "Average of all Round 1 bids"}


def extra_assignment_payload(db: Session) -> dict:
    # Reuse the existing grid projection, overlaying final/current assignments.
    payload = round1_assignment_management_payload(db, problem_rounds=(1, EXTERNAL_PROBLEM_ROUND))
    payload["capacity_per_problem"] = ROUND1_PROBLEM_CAPACITY
    payload["external_problems"] = [row for row in payload["problems"] if row["source"] == "EXTERNAL"]
    teams = db.query(Team).order_by(Team.id.asc()).all()
    groups = current_problem_teams(teams)
    problems = {row["id"]: row for row in payload["problems"]}
    for row in problems.values():
        row["assigned_team_count"] = len(groups.get(row["id"], []))
        row["capacity_remaining"] = problem_capacity_remaining(row["assigned_team_count"])
        row["is_full"] = row["capacity_remaining"] == 0
        row["capacity"] = row["auction_capacity"] = ROUND1_PROBLEM_CAPACITY
        row["auction_capacity_remaining"] = row["capacity_remaining"]
        row["auction_full"] = row["is_full"]
    by_id = {team.id: team for team in teams}
    for row in payload["teams"]:
        team = by_id[row["team_id"]]
        row["current_problem"] = problems.get(team.ps_id)
        row["assignment_status"] = "ASSIGNED" if team.ps_id is not None else "NOT_ASSIGNED"
        row["extra_assignment"] = team.ps_id in problems and team.round1_problem_id is None
    payload["unassigned_teams"] = [row for row in payload["teams"] if is_extra_assignment_candidate(by_id[row["team_id"]])]
    payload["remaining_team_count"] = len(payload["unassigned_teams"])
    payload["can_auto_assign"] = bool(payload["remaining_team_count"] and any(row["capacity_remaining"] > 0 for row in problems.values()))
    payload.update(automatic_assignment_price(db))
    return payload


def automatically_assign_extra_problems(db: Session, problem_id: int, deduction: int | None = None) -> dict:
    """Fill only the selected problem in team ID order; retain existing assignments."""
    with ROUND1_FINALIZATION_LOCK:
        return _assign_extra_problems(db, problem_id, deduction)


def _assign_extra_problems(db: Session, problem_id: int, deduction: int | None) -> dict:
    try:
        # Match auction lock order, but never change existing RoundControl or R1 assignment fields.
        control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").with_for_update().populate_existing().one_or_none()
        if control is None:
            # Ensure there is a serialization row even before R1 is initialized.
            db.add(RoundControl(round_type="ROUND1", status="IDLE"))
            db.flush()
        if deduction is None:
            deduction = automatic_assignment_price(db)["suggested_auto_deduction"]
        if isinstance(deduction, bool) or not isinstance(deduction, int) or deduction < 0:
            raise ExtraAssignmentError("Automatic deduction must be a whole number of zero or greater.")
        problem = db.query(ProblemStatement).filter(ProblemStatement.id == problem_id).with_for_update().populate_existing().one_or_none()
        if problem is None:
            raise ExtraAssignmentError("Target problem does not exist.")
        if problem.round not in (1, 0):
            raise ExtraAssignmentError("Target problem is not eligible for Extra/Grid assignment.")
        teams = db.query(Team).order_by(Team.id.asc()).with_for_update().populate_existing().all()
        free_slots = problem_capacity_remaining(len(current_problem_teams(teams).get(problem.id, [])))
        if free_slots <= 0:
            raise ExtraAssignmentError("Target problem has no remaining capacity.")
        assignments, failures = [], []
        for team in teams:
            if free_slots == 0:
                break
            if not is_extra_assignment_candidate(team):
                continue
            if team.coins < deduction:
                failures.append({"team_id": team.id, "team_name": team.team_name, "reason": "Insufficient coins",
                                 "required": deduction, "available": team.coins})
                continue
            team.ps_id = problem.id
            team.coins -= deduction
            db.add(WalletTransaction(team_id=team.id, transaction_type=EXTRA_GRID_TRANSACTION, amount=-deduction,
                                     description=f"Automatic Extra/Grid assignment for {problem.ps_number}"))
            free_slots -= 1
            assignments.append({"team_id": team.id, "team_name": team.team_name, "problem_id": problem.id,
                                "deduction": deduction, "coins": team.coins})
        db.flush()
        result = {**extra_assignment_payload(db), "assignments": assignments, "failures": failures,
                  "problem_id": problem.id, "deduction": deduction, "idempotent": not assignments}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
