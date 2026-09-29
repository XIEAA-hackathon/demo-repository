"""Post-R1 Extra/Grid allocation. Auction results and wallets are immutable here."""
from sqlalchemy.orm import Session

from app.models.models import ProblemStatement, RoundControl, Team
from app.services.round1_assignment import ROUND1_PROBLEM_CAPACITY, round1_assignment_management_payload


class ExtraAssignmentError(ValueError):
    pass


def extra_assignment_payload(db: Session) -> dict:
    # Reuse the existing grid projection, overlaying final/current assignments.
    payload = round1_assignment_management_payload(db)
    teams = db.query(Team).order_by(Team.id.asc()).all()
    counts = {}
    for team in teams:
        for problem_id in {team.round1_problem_id, team.ps_id} - {None}:
            counts[problem_id] = counts.get(problem_id, 0) + 1
    problems = {row["id"]: row for row in payload["problems"]}
    for row in problems.values():
        row["assigned_team_count"] = counts.get(row["id"], 0)
        row["capacity_remaining"] = max(0, ROUND1_PROBLEM_CAPACITY - row["assigned_team_count"])
        row["is_full"] = row["capacity_remaining"] == 0
    by_id = {team.id: team for team in teams}
    for row in payload["teams"]:
        team = by_id[row["team_id"]]
        row["current_problem"] = problems.get(team.ps_id)
        row["assignment_status"] = "ASSIGNED" if team.ps_id is not None else "NOT_ASSIGNED"
        row["extra_assignment"] = team.ps_id in problems and team.round1_problem_id is None
    payload["unassigned_teams"] = [row for row in payload["teams"] if row["assignment_status"] == "NOT_ASSIGNED"]
    control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one_or_none()
    payload["can_auto_assign"] = bool(control and control.ended)
    return payload


def automatically_assign_extra_problems(db: Session) -> dict:
    """Fill available capacity in ID order; retain every existing assignment."""
    try:
        # Match auction lock order, but never mutate RoundControl or R1 fields.
        control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").with_for_update().one_or_none()
        if not control or not control.ended:
            raise ExtraAssignmentError("End Round 1 before automatic Extra/Grid assignment.")
        problems = db.query(ProblemStatement).filter(ProblemStatement.round.in_([1, 0])).order_by(ProblemStatement.round.desc(), ProblemStatement.id.asc()).with_for_update().all()
        teams = db.query(Team).order_by(Team.id.asc()).with_for_update().populate_existing().all()
        usage = {}
        for team in teams:
            # Include reserved R1 places even if a Wildcard choice replaced them.
            for problem_id in {team.round1_problem_id, team.ps_id} - {None}:
                usage[problem_id] = usage.get(problem_id, 0) + 1
        assignments, failures = [], []
        for team in teams:
            if not team.is_approved or team.is_system_team or team.ps_id is not None:
                continue
            # Never replace a valid R1 or later Wildcard/final assignment.
            if team.round1_problem_id is not None or team.wildcard_problem_id is not None:
                failures.append({"team_id": team.id, "team_name": team.team_name, "reason": "Final problem resolution is pending"})
                continue
            problem = next((row for row in problems if usage.get(row.id, 0) < ROUND1_PROBLEM_CAPACITY), None)
            if problem is None:
                failures.append({"team_id": team.id, "team_name": team.team_name, "reason": "No remaining problem capacity"})
                continue
            team.ps_id = problem.id
            usage[problem.id] = usage.get(problem.id, 0) + 1
            assignments.append({"team_id": team.id, "team_name": team.team_name, "problem_id": problem.id})
        db.flush()
        result = {**extra_assignment_payload(db), "assignments": assignments, "failures": failures, "idempotent": not assignments}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
