from __future__ import annotations

from threading import RLock

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.models import ProblemStatement, RoundControl, Team, User, WalletTransaction
from app.services.activity_log import record_event
from app.services.event_service import get_or_create_event_config, get_or_create_round_control, transition_event_state


ROUND1_BID_WINNER = "BID_WINNER"
ROUND1_MANUAL_ASSIGNMENT = "MANUAL_ASSIGNMENT"
ROUND1_MANUAL_TRANSACTION = "ROUND1_MANUAL_ASSIGN"
ROUND1_PROBLEM_CAPACITY = 5
EXTERNAL_PROBLEM_ROUND = 0
ROUND1_FINALIZATION_LOCK = RLock()


class Round1AssignmentError(ValueError):
    pass


def _display_number(problem: ProblemStatement) -> str:
    return problem.ps_number.split("-", 1)[-1]


def assigned_team_count(db: Session, problem_id: int) -> int:
    return db.query(Team).filter(Team.round1_problem_id == problem_id).count()


def remaining_capacity(db: Session, problem_id: int) -> int:
    return max(0, ROUND1_PROBLEM_CAPACITY - assigned_team_count(db, problem_id))


def _management_problem_payload(problem: ProblemStatement, assigned_count: int) -> dict:
    source = "EXTERNAL" if problem.round == EXTERNAL_PROBLEM_ROUND else "ROUND1"
    return {
        "id": problem.id,
        "problem_number": _display_number(problem),
        "title": problem.title,
        "description": problem.description or "",
        "status": problem.status,
        "source": source,
        "source_label": "External" if source == "EXTERNAL" else "Round 1",
        "assigned_team_count": assigned_count,
        "capacity": ROUND1_PROBLEM_CAPACITY,
        "capacity_remaining": max(0, ROUND1_PROBLEM_CAPACITY - assigned_count),
        "is_full": assigned_count >= ROUND1_PROBLEM_CAPACITY,
    }


def round1_assignment_management_payload(db: Session) -> dict:
    """Return the authoritative current Round 1 assignment correction snapshot."""
    problems = (
        db.query(ProblemStatement)
        .filter(ProblemStatement.round.in_([1, EXTERNAL_PROBLEM_ROUND]))
        .order_by(ProblemStatement.round.desc(), ProblemStatement.id.asc())
        .all()
    )
    counts = dict(
        db.query(Team.round1_problem_id, func.count(Team.id))
        .filter(Team.round1_problem_id.is_not(None))
        .group_by(Team.round1_problem_id)
        .all()
    )
    problem_rows = [
        _management_problem_payload(problem, int(counts.get(problem.id, 0)))
        for problem in problems
    ]
    problems_by_id = {problem["id"]: problem for problem in problem_rows}

    teams = (
        db.query(Team)
        .filter(Team.is_approved.is_(True), Team.is_system_team.is_(False))
        .order_by(Team.team_name.asc(), Team.id.asc())
        .all()
    )
    leader_ids = [team.leader_id for team in teams if team.leader_id is not None]
    leaders = {
        leader.id: leader
        for leader in db.query(User).filter(User.id.in_(leader_ids)).all()
    } if leader_ids else {}

    team_rows = []
    for team in teams:
        leader = leaders.get(team.leader_id)
        current_problem = problems_by_id.get(team.round1_problem_id)
        team_rows.append({
            "team_id": team.id,
            "team_name": team.team_name,
            "leader_name": leader.name if leader else None,
            "leader_email": leader.email if leader else None,
            "coins": team.coins or 0,
            "assignment_status": "ASSIGNED" if current_problem else "NOT_ASSIGNED",
            "assignment_type": team.round1_assignment_type,
            "assignment_cost": team.round1_assignment_cost,
            "current_problem": current_problem,
        })

    return {
        "capacity_per_problem": ROUND1_PROBLEM_CAPACITY,
        "problems": problem_rows,
        "round1_problems": [row for row in problem_rows if row["source"] == "ROUND1"],
        "external_problems": [row for row in problem_rows if row["source"] == "EXTERNAL"],
        "teams": team_rows,
        "unassigned_teams": [row for row in team_rows if row["current_problem"] is None],
    }


def change_round1_problem_assignment(
    db: Session,
    team_id: int,
    target_problem_id: int,
    *,
    new_balance: int | None = None,
    actor=None,
) -> dict:
    """Move an assignment and optionally set an unassigned team's final balance atomically."""
    if new_balance is not None and (isinstance(new_balance, bool) or not isinstance(new_balance, int)):
        raise Round1AssignmentError("New balance must be a whole number.")
    if new_balance is not None and not 0 <= new_balance <= 1_000_000:
        raise Round1AssignmentError("New balance must be between 0 and 1,000,000 coins.")
    with ROUND1_FINALIZATION_LOCK:
        try:
            control = get_or_create_round_control(db, "ROUND1")
            if db.get_bind().dialect.name == "sqlite":
                # SQLite ignores SELECT FOR UPDATE. A harmless write against the
                # singleton Round 1 row acquires its database write reservation
                # before capacity is read, serializing competing Admin tabs.
                db.execute(
                    text("UPDATE round_controls SET status = status WHERE id = :control_id"),
                    {"control_id": control.id},
                )

            control = (
                db.query(RoundControl)
                .filter(RoundControl.id == control.id)
                .with_for_update()
                .populate_existing()
                .one()
            )
            team = (
                db.query(Team)
                .filter(Team.id == team_id)
                .with_for_update()
                .populate_existing()
                .first()
            )
            if not team:
                raise Round1AssignmentError("Team not found.")
            if not team.is_approved or team.is_system_team:
                raise Round1AssignmentError("Only approved participant teams can receive a Round 1 problem.")

            target = (
                db.query(ProblemStatement)
                .filter(
                    ProblemStatement.id == target_problem_id,
                    ProblemStatement.round.in_([1, EXTERNAL_PROBLEM_ROUND]),
                )
                .with_for_update()
                .populate_existing()
                .first()
            )
            if not target:
                raise Round1AssignmentError("Target problem is not eligible for manual assignment.")

            previous_problem_id = team.round1_problem_id
            previous_problem = (
                db.query(ProblemStatement).filter(ProblemStatement.id == previous_problem_id).first()
                if previous_problem_id else None
            )
            if previous_problem_id == target.id:
                if new_balance is not None and team.coins != new_balance:
                    raise Round1AssignmentError(
                        "Balance can only be set while assigning a team that does not yet have a problem."
                    )
                snapshot = round1_assignment_management_payload(db)
                db.commit()
                return {
                    "idempotent": True,
                    "change": {
                        "team_id": team.id,
                        "team_name": team.team_name,
                        "previous_problem_id": previous_problem_id,
                        "problem": _management_problem_payload(target, assigned_team_count(db, target.id)),
                        "coins": team.coins or 0,
                        "coins_before": team.coins or 0,
                        "balance_changed": False,
                    },
                    **snapshot,
                }

            target_count = assigned_team_count(db, target.id)
            if target_count >= ROUND1_PROBLEM_CAPACITY:
                raise Round1AssignmentError(
                    f"Problem {target.ps_number} is full ({target_count}/{ROUND1_PROBLEM_CAPACITY}). "
                    "The original assignment was not changed."
                )

            coins_before = team.coins or 0
            if previous_problem_id is not None and new_balance is not None:
                raise Round1AssignmentError(
                    "Balance can only be set while assigning a team that does not yet have a problem."
                )
            final_problem = (
                db.query(ProblemStatement).filter(ProblemStatement.id == team.ps_id).first()
                if team.ps_id else None
            )
            team.round1_problem_id = target.id
            # Round 1 remains the team's final/current problem until a later
            # Wildcard selection replaces it. Never overwrite that later result.
            if team.ps_id is None or team.ps_id == previous_problem_id or (final_problem and final_problem.round == 1):
                team.ps_id = target.id
            if previous_problem_id is None:
                team.round1_assignment_type = ROUND1_MANUAL_ASSIGNMENT
                team.round1_assignment_cost = 0
                if new_balance is not None:
                    team.coins = new_balance

            record_event(
                db,
                "round1.assignment_changed",
                actor=actor,
                entity_type="team",
                entity_id=team.id,
                metadata={
                    "previous_problem_id": previous_problem_id,
                    "target_problem_id": target.id,
                    "coins_before": coins_before,
                    "coins_after": team.coins or 0,
                    "balance_changed": coins_before != (team.coins or 0),
                    "balance_override_requested": new_balance is not None,
                    "round1_closed": bool(control.ended),
                },
            )
            db.flush()
            db.commit()

            target_count = assigned_team_count(db, target.id)
            result = {
                "idempotent": False,
                "change": {
                    "team_id": team.id,
                    "team_name": team.team_name,
                    "previous_problem_id": previous_problem.id if previous_problem else None,
                    "problem": _management_problem_payload(target, target_count),
                    "coins": team.coins or 0,
                    "coins_before": coins_before,
                    "balance_changed": coins_before != (team.coins or 0),
                },
                **round1_assignment_management_payload(db),
            }
            return result
        except Exception:
            db.rollback()
            raise


def eligible_round1_teams(db: Session, *, lock: bool = False) -> list[Team]:
    query = (
        db.query(Team)
        .filter(
            Team.is_approved.is_(True),
            Team.is_system_team.is_(False),
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
    """Add one auction attempt's actual winners; zero/manual assignments add nothing."""
    if problem.status in {"completed", "allocated", "no_bids"} or not winner_amounts:
        return False
    control.round1_winning_bid_sum = (control.round1_winning_bid_sum or 0) + sum(winner_amounts)
    control.round1_winning_bid_count = (control.round1_winning_bid_count or 0) + len(winner_amounts)
    return True


def suggested_assignment_deduction(db: Session, control: RoundControl) -> int:
    count = control.round1_winning_bid_count or 0
    if count <= 0:
        return max(0, get_or_create_event_config(db).round1_minimum_bid)
    total = control.round1_winning_bid_sum or 0
    return (total + (count // 2)) // count


def remaining_problems_payload(db: Session, control: RoundControl) -> dict:
    problems = (
        db.query(ProblemStatement)
        .filter(ProblemStatement.round == 1)
        .order_by(ProblemStatement.id.asc())
        .all()
    )
    assigned = (
        db.query(Team)
        .filter(Team.round1_problem_id.is_not(None))
        .order_by(Team.id.asc())
        .all()
    )
    teams_by_problem: dict[int, list[Team]] = {}
    for team in assigned:
        teams_by_problem.setdefault(team.round1_problem_id, []).append(team)
    eligible = eligible_round1_teams(db)
    no_active_auction = control.current_problem_id is None and control.status not in {"PREVIEW", "BIDDING"}
    rows = []
    for problem in problems:
        problem_teams = teams_by_problem.get(problem.id, [])
        count = len(problem_teams)
        capacity = max(0, ROUND1_PROBLEM_CAPACITY - count)
        assignment_status = "ASSIGNED" if capacity == 0 else "PARTIAL" if count else "UNASSIGNED"
        actionable = not control.ended and no_active_auction and capacity > 0
        rows.append({
            "id": problem.id,
            "problem_number": _display_number(problem),
            "title": problem.title,
            "description": problem.description or "",
            "auction_status": problem.status,
            "assignment_status": assignment_status,
            "assigned_team_count": count,
            "capacity_remaining": capacity,
            "assigned_teams": [
                {
                    "team_id": team.id,
                    "team_name": team.team_name,
                    "assignment_type": team.round1_assignment_type,
                    "assignment_cost": team.round1_assignment_cost or 0,
                }
                for team in problem_teams
            ],
            "can_rebid": actionable,
            "can_assign": actionable and bool(eligible),
        })
    return {
        "problems": rows,
        "eligible_teams": [
            {"team_id": team.id, "team_name": team.team_name, "coins": team.coins or 0}
            for team in eligible
        ],
        "unassigned_team_count": len(eligible),
        "suggested_deduction": suggested_assignment_deduction(db, control),
        "round1_winning_bid_sum": control.round1_winning_bid_sum or 0,
        "round1_winning_bid_count": control.round1_winning_bid_count or 0,
    }


def _manual_description(problem: ProblemStatement) -> str:
    return f"Round 1 manual assignment for {problem.ps_number}"


def manually_assign_problem(
    db: Session,
    control: RoundControl,
    problem_id: int,
    team_ids: list[int],
    deduction: int,
    *,
    actor=None,
) -> dict:
    if deduction < 0:
        raise Round1AssignmentError("Coins to deduct must be a whole number of zero or greater.")
    if not team_ids:
        raise Round1AssignmentError("Select at least one eligible team.")
    if len(set(team_ids)) != len(team_ids):
        raise Round1AssignmentError("Each selected team may appear only once.")

    with ROUND1_FINALIZATION_LOCK:
        db.flush()
        control = (
            db.query(RoundControl)
            .filter(RoundControl.id == control.id)
            .with_for_update()
            .populate_existing()
            .one()
        )
        problem = (
            db.query(ProblemStatement)
            .filter(ProblemStatement.id == problem_id, ProblemStatement.round == 1)
            .with_for_update()
            .first()
        )
        if not problem:
            raise Round1AssignmentError("Round 1 problem not found.")
        selected = (
            db.query(Team)
            .filter(Team.id.in_(team_ids))
            .order_by(Team.id.asc())
            .with_for_update()
            .all()
        )
        if len(selected) != len(team_ids):
            raise Round1AssignmentError("One or more selected teams no longer exist.")

        description = _manual_description(problem)
        already_applied = all(
            team.round1_problem_id == problem.id
            and db.query(WalletTransaction).filter(
                WalletTransaction.team_id == team.id,
                WalletTransaction.transaction_type == ROUND1_MANUAL_TRANSACTION,
                WalletTransaction.description == description,
            ).first() is not None
            for team in selected
        )
        if already_applied:
            return {
                "idempotent": True,
                "problem_id": problem.id,
                "assignments": [
                    {
                        "team_id": team.id,
                        "team_name": team.team_name,
                        "amount": team.round1_assignment_cost or 0,
                    }
                    for team in selected
                ],
            }

        if control.ended:
            raise Round1AssignmentError("Round 1 is closed.")
        if control.current_problem_id is not None or control.status in {"PREVIEW", "BIDDING"}:
            raise Round1AssignmentError("Complete the current auction before assigning teams manually.")
        invalid = [
            team.team_name
            for team in selected
            if not team.is_approved
            or team.is_system_team
            or team.round1_problem_id is not None
            or team.ps_id is not None
        ]
        if invalid:
            raise Round1AssignmentError(
                "Only unassigned eligible Round 1 teams may be selected. "
                f"Unavailable: {', '.join(invalid)}."
            )

        current_count = assigned_team_count(db, problem.id)
        capacity = max(0, ROUND1_PROBLEM_CAPACITY - current_count)
        if len(selected) > capacity:
            raise Round1AssignmentError(
                f"Problem {problem.ps_number} has room for {capacity} more "
                f"team{'s' if capacity != 1 else ''}; {len(selected)} were selected."
            )
        insufficient = [team.team_name for team in selected if (team.coins or 0) < deduction]
        if insufficient:
            raise Round1AssignmentError(
                f"The {deduction}-coin deduction exceeds the available balance for: "
                f"{', '.join(insufficient)}. Lower the deduction or change the selection."
            )

        assignments = []
        for team in selected:
            team.coins -= deduction
            team.ps_id = problem.id
            team.round1_problem_id = problem.id
            team.round1_assignment_type = ROUND1_MANUAL_ASSIGNMENT
            team.round1_assignment_cost = deduction
            db.add(WalletTransaction(
                team_id=team.id,
                transaction_type=ROUND1_MANUAL_TRANSACTION,
                amount=-deduction,
                description=description,
            ))
            assignments.append({
                "team_id": team.id,
                "team_name": team.team_name,
                "amount": deduction,
            })

        problem.status = "completed"
        db.flush()
        remaining_eligible = db.query(Team).filter(
            Team.is_approved.is_(True),
            Team.is_system_team.is_(False),
            Team.round1_problem_id.is_(None),
        ).count()
        if remaining_eligible <= 0:
            control.status = "COMPLETE"
            control.ended = True
            transition_event_state(db, "ROUND1_RESULT", validate=False, commit=False)
        else:
            control.status = "READY"
        record_event(
            db,
            "round1.problem_manually_assigned",
            actor=actor,
            entity_type="problem",
            entity_id=problem.id,
            metadata={
                "team_ids": [team.id for team in selected],
                "deduction_per_team": deduction,
            },
        )
        db.flush()
        return {
            "idempotent": False,
            "problem_id": problem.id,
            "assignments": assignments,
        }
