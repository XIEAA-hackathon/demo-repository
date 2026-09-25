from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models.models import (
    Bid,
    Lab,
    LabAllocationState,
    LabAssignment,
    ProblemStatement,
    RoundControl,
    Team,
    User,
    Wildcard,
)

logger = logging.getLogger("uvicorn.error")


class LabAllocationError(ValueError):
    def __init__(self, code: str, message: str, **context: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.context}


def _state_row(db: Session, *, lock: bool = False) -> LabAllocationState:
    query = db.query(LabAllocationState).filter(LabAllocationState.id == 1)
    if lock:
        query = query.with_for_update()
    state = query.one_or_none()
    if state is None:
        db.execute(insert(LabAllocationState).values(id=1, status="NOT_READY").on_conflict_do_nothing(index_elements=["id"]))
        state = query.populate_existing().one()
    return state


def _event_is_final(db: Session) -> bool:
    wildcard = db.query(RoundControl.status, RoundControl.ended).filter(
        RoundControl.round_type == "WILDCARD"
    ).one_or_none()
    return bool(wildcard and wildcard.ended)


def get_final_problem_id(team: Team) -> int | None:
    """Canonical final PS: Team.ps_id already reflects Round 1 or Wildcard replacement."""
    return team.ps_id


def _participant_teams(db: Session, *, lock: bool = False) -> list[Team]:
    query = db.query(Team).filter(Team.is_approved.is_(True), Team.is_system_team.is_(False)).order_by(Team.id.asc())
    return query.with_for_update().all() if lock else query.all()


def _eligible_teams(db: Session, *, lock: bool = False) -> list[Team]:
    """Teams with an authoritative final PS; round results and sessions are irrelevant."""
    query = db.query(Team).filter(
        Team.is_approved.is_(True),
        Team.is_system_team.is_(False),
        Team.ps_id.is_not(None),
    ).order_by(Team.id.asc())
    return query.with_for_update().all() if lock else query.all()


def _active_labs(db: Session, *, lock: bool = False) -> list[Lab]:
    query = db.query(Lab).filter(Lab.active.is_(True)).order_by(Lab.sort_order.asc(), Lab.id.asc())
    return query.with_for_update().all() if lock else query.all()


def _readiness(
    db: Session,
    teams: list[Team],
    labs: list[Lab],
    *,
    event_is_final: bool | None = None,
) -> tuple[bool, str]:
    if not labs:
        return False, "Configure at least one active lab."
    if not teams:
        return False, "Waiting for approved participant teams with final problem assignments."
    if not (_event_is_final(db) if event_is_final is None else event_is_final):
        return False, "Waiting for Wildcard and final problem assignments to finish."
    return True, "Final problem assignments are ready for lab allocation."


def _max_flow_assignment(teams: list[Team], labs: list[Lab]) -> tuple[dict[int, int], int]:
    """Deterministic max flow: source -> team -> (effective PS, lab) -> lab -> sink."""
    source = ("source",)
    sink = ("sink",)
    residual: dict[tuple, dict[tuple, int]] = {}
    order: dict[tuple, list[tuple]] = {}

    def add_edge(left: tuple, right: tuple, capacity: int) -> None:
        residual.setdefault(left, {})[right] = capacity
        residual.setdefault(right, {}).setdefault(left, 0)
        order.setdefault(left, []).append(right)
        order.setdefault(right, []).append(left)

    for lab in labs:
        add_edge(("lab", lab.id), sink, lab.capacity)

    for index, team in enumerate(teams):
        team_node = ("team", team.id)
        add_edge(source, team_node, 1)
        rotated_labs = labs[index % len(labs):] + labs[:index % len(labs)]
        for lab in rotated_labs:
            pair_node = ("pair", get_final_problem_id(team), lab.id)
            add_edge(team_node, pair_node, 1)
            if ("lab", lab.id) not in residual.get(pair_node, {}):
                add_edge(pair_node, ("lab", lab.id), 1)

    flow = 0
    while True:
        parents: dict[tuple, tuple | None] = {source: None}
        queue = deque([source])
        while queue and sink not in parents:
            node = queue.popleft()
            for neighbor in order.get(node, []):
                if neighbor not in parents and residual[node].get(neighbor, 0) > 0:
                    parents[neighbor] = node
                    queue.append(neighbor)
        if sink not in parents:
            break
        cursor = sink
        while parents[cursor] is not None:
            parent = parents[cursor]
            residual[parent][cursor] -= 1
            residual[cursor][parent] += 1
            cursor = parent
        flow += 1

    result: dict[int, int] = {}
    for team in teams:
        team_node = ("team", team.id)
        selected = [
            node for node in order[team_node]
            if node[0] == "pair" and residual[node].get(team_node, 0) == 1
        ]
        if len(selected) == 1:
            result[team.id] = int(selected[0][2])
    return result, flow


def _verify_persisted_allocation(db: Session, teams: list[Team], labs: list[Lab]) -> int:
    """Validate the flushed transaction before it is allowed to commit."""
    db.flush()
    rows = db.query(LabAssignment).order_by(LabAssignment.id.asc()).with_for_update().populate_existing().all()
    if not _assignments_are_current(teams, labs, rows):
        raise LabAllocationError(
            "integrity_failed",
            "Lab allocation persistence failed its integrity check; no assignments were committed.",
            eligible_team_count=len(teams),
            persisted_assignment_count=len(rows),
        )
    return len(rows)


def _assignments_are_current(teams: list[Team], labs: list[Lab], assignments: list[LabAssignment]) -> bool:
    if not teams or not labs:
        return False
    team_by_id = {team.id: team for team in teams}
    lab_by_id = {lab.id: lab for lab in labs}
    if len(assignments) != len(teams) or {row.team_id for row in assignments} != set(team_by_id):
        return False
    occupancy: dict[int, int] = {}
    pairs = set()
    for row in assignments:
        team = team_by_id[row.team_id]
        if row.current_lab_id not in lab_by_id or row.effective_ps_id != get_final_problem_id(team):
            return False
        pair = (row.current_lab_id, row.effective_ps_id)
        if pair in pairs:
            return False
        pairs.add(pair)
        occupancy[row.current_lab_id] = occupancy.get(row.current_lab_id, 0) + 1
    return all(occupancy.get(lab.id, 0) <= lab.capacity for lab in labs)


def allocate_labs(
    db: Session,
    *,
    actor: User | None = None,
    replace_manual: bool = False,
) -> tuple[bool, int]:
    """Allocate every approved participant team once, under one database transaction."""
    state = _state_row(db, lock=True)
    labs = _active_labs(db, lock=True)
    teams = _eligible_teams(db, lock=True)
    ready, message = _readiness(db, teams, labs)
    logger.info("Lab allocation started eligible_teams=%d labs=%d", len(teams), len(labs))
    if not ready:
        raise LabAllocationError("not_ready", message)

    assignments = db.query(LabAssignment).order_by(LabAssignment.id.asc()).with_for_update().all()
    if _assignments_are_current(teams, labs, assignments):
        return False, len(assignments)
    if not replace_manual and any(row.assignment_source == "MANUAL_OVERRIDE" for row in assignments):
        raise LabAllocationError(
            "manual_history_present",
            "Automatic allocation will not replace manual moves. An Event Admin can explicitly generate a fresh allocation.",
        )

    generated, flow = _max_flow_assignment(teams, labs)
    logger.info("Lab allocation max_flow=%d expected=%d", flow, len(teams))
    if flow != len(teams) or len(generated) != flow:
        unassigned = [team for team in teams if team.id not in generated]
        diagnostics = [
            {"team_id": team.id, "team_name": team.team_name, "final_problem_id": team.ps_id,
             "reason": "no compatible lab slot available"}
            for team in unassigned
        ]
        logger.error(
            "Lab allocation incomplete expected=%d flow=%d unassigned_team_ids=%s",
            len(teams), flow, [team.id for team in unassigned],
        )
        raise LabAllocationError(
            "constraints_unsatisfied",
            f"Lab allocation incomplete. {flow} / {len(teams)} teams can be placed. {len(unassigned)} team(s) are unassigned.",
            eligible_team_count=len(teams),
            max_flow=flow,
            unassigned_teams=diagnostics,
        )

    state.status = "ALLOCATING"
    db.query(LabAssignment).delete(synchronize_session=False)
    for team in teams:
        lab_id = generated[team.id]
        db.add(LabAssignment(
            team_id=team.id,
            original_lab_id=lab_id,
            current_lab_id=lab_id,
            assignment_source="AUTO",
            constraint_override=False,
            effective_ps_id=get_final_problem_id(team),
            version=1,
        ))
    now = datetime.now(timezone.utc)
    state.status = "ALLOCATED"
    state.allocated_at = now
    state.finalized_at = None
    persisted = _verify_persisted_allocation(db, teams, labs)
    logger.info("Lab allocation persisted assignments=%d", persisted)
    db.commit()
    db.info["lab_assignment_changes"] = lab_assignment_payloads(db)
    return True, len(teams)


def try_allocate_labs(db: Session) -> int | None:
    """Best-effort hook used when the final Wildcard assignment becomes known."""
    try:
        changed, count = allocate_labs(db)
        return count if changed else None
    except LabAllocationError as exc:
        db.rollback()
        logger.warning("Automatic lab allocation deferred code=%s detail=%s", exc.code, exc.message)
        return None


def move_team(
    db: Session,
    *,
    assignment_id: int | None,
    target_lab_id: int,
    expected_version: int,
    allow_constraint_override: bool,
    actor: User,
    team_id: int | None = None,
) -> LabAssignment:
    # ponytail: serialize low-volume lab edits with allocation; use finer locks if throughput requires it.
    _state_row(db, lock=True)
    if not _event_is_final(db):
        raise LabAllocationError("not_ready", "Lab assignments become editable after Wildcard is complete.")
    snapshot = db.query(LabAssignment.id, LabAssignment.current_lab_id).filter(
        LabAssignment.team_id == team_id if team_id is not None else LabAssignment.id == assignment_id
    ).one_or_none()
    if snapshot is None and team_id is None:
        raise LabAllocationError("assignment_not_found", "Lab assignment not found.")

    lab_ids = sorted({snapshot.current_lab_id, target_lab_id} if snapshot else {target_lab_id})
    labs = db.query(Lab).filter(Lab.id.in_(lab_ids)).order_by(Lab.id.asc()).with_for_update().all()
    lab_by_id = {lab.id: lab for lab in labs}
    target = lab_by_id.get(target_lab_id)
    if target is None or not target.active:
        raise LabAllocationError("target_lab_not_found", "Target lab is unavailable.")

    assignment = db.query(LabAssignment).filter(LabAssignment.id == snapshot.id).with_for_update().populate_existing().one() if snapshot else None
    if assignment and (assignment.version != expected_version or assignment.current_lab_id != snapshot.current_lab_id):
        raise LabAllocationError(
            "stale_assignment",
            "This team was moved by another session. Refresh the board before trying again.",
            current_version=assignment.version,
        )
    team = db.query(Team).filter(Team.id == (assignment.team_id if assignment else team_id)).with_for_update().populate_existing().one_or_none()
    if team is None or not team.is_approved or team.is_system_team or team.ps_id is None:
        raise LabAllocationError("invalid_team", "An approved participant team with a final problem is required.")
    if assignment and get_final_problem_id(team) != assignment.effective_ps_id:
        raise LabAllocationError(
            "stale_allocation",
            "The team's final problem changed. Regenerate the lab allocation before moving it.",
        )

    target_rows = db.query(LabAssignment).filter(
        LabAssignment.current_lab_id == target_lab_id,
        LabAssignment.team_id != team.id,
    ).order_by(LabAssignment.id.asc()).with_for_update().all()
    if len(target_rows) >= target.capacity:
        raise LabAllocationError(
            "capacity_reached",
            f"{target.name} is at capacity {len(target_rows)} / {target.capacity}.",
            target_lab_id=target.id,
            capacity=target.capacity,
        )

    duplicate = db.query(Team).filter(Team.id.in_([row.team_id for row in target_rows]), Team.ps_id == get_final_problem_id(team)).first()
    if duplicate:
        problem = db.query(ProblemStatement).filter(ProblemStatement.id == get_final_problem_id(team)).one()
        raise LabAllocationError(
            "duplicate_effective_problem",
            f"Cannot move {team.team_name} to {target.name}. It already contains {duplicate.team_name} with Problem {problem.ps_number}.",
            target_lab_id=target.id,
            target_lab_name=target.name,
            effective_problem=problem.ps_number,
        )

    source_lab_id = assignment.current_lab_id if assignment else None
    if assignment and source_lab_id == target_lab_id:
        return assignment
    if assignment is None:
        assignment = LabAssignment(team_id=team.id, original_lab_id=target.id, current_lab_id=target.id, effective_ps_id=get_final_problem_id(team), version=0)
        db.add(assignment)
    assignment.current_lab_id = target.id
    assignment.assignment_source = "MANUAL_OVERRIDE"
    assignment.constraint_override = False
    assignment.moved_by_user_id = actor.id
    assignment.moved_at = datetime.now(timezone.utc)
    assignment.version += 1
    db.commit()
    db.refresh(assignment)
    db.info["lab_assignment_changes"] = [{**lab_assignment_payloads(db, team_id=team.id)[0], "previous_lab_id": source_lab_id}]
    return assignment


def lab_assignment_payloads(db: Session, *, team_id: int | None = None) -> list[dict]:
    query = db.query(LabAssignment, Lab, Team).join(Lab, Lab.id == LabAssignment.current_lab_id).join(Team, Team.id == LabAssignment.team_id)
    if team_id is not None:
        query = query.filter(Team.id == team_id)
    return [{"team_id": team.id, "assignment_id": assignment.id, "version": assignment.version,
             "effective_ps_id": assignment.effective_ps_id, "current_lab_id": lab.id,
             "original_lab_id": assignment.original_lab_id, "assignment_source": assignment.assignment_source,
             "lab": {"id": lab.id, "name": lab.name, "assignment_id": assignment.id, "version": assignment.version}, "labAllocationReady": True}
            for assignment, lab, team in query.all() if lab.active and assignment.effective_ps_id == get_final_problem_id(team)]


def lab_board(db: Session, *, logged_in_team_ids: set[int] | None = None) -> dict[str, Any]:
    logged_in_team_ids = logged_in_team_ids or set()
    labs = _active_labs(db)
    participant_teams = _participant_teams(db)
    teams = [team for team in participant_teams if team.ps_id is not None]
    assignments = db.query(LabAssignment).order_by(LabAssignment.id.asc()).all()
    problem_ids = {
        problem_id
        for team in participant_teams
        for problem_id in (team.ps_id, team.round1_problem_id, team.wildcard_problem_id)
        if problem_id is not None
    }
    problems = db.query(ProblemStatement).filter(ProblemStatement.id.in_(problem_ids)).all() if problem_ids else []
    participant_team_ids = [team.id for team in participant_teams]
    wildcards = db.query(Wildcard).filter(Wildcard.team_id.in_(participant_team_ids)).all()
    round1_problem_ids = {
        team.round1_problem_id for team in participant_teams if team.round1_problem_id is not None
    }
    bids = (
        db.query(Bid)
        .filter(Bid.round == 1, Bid.ps_id.in_(round1_problem_ids))
        .order_by(Bid.ps_id.asc(), Bid.amount.desc(), Bid.timestamp.asc(), Bid.team_id.asc())
        .all()
    )
    problem_by_id = {problem.id: problem for problem in problems}
    team_by_id = {team.id: team for team in teams}
    wildcard_by_team = {wildcard.team_id: wildcard for wildcard in wildcards}
    participant_team_by_id = {team.id: team for team in participant_teams}
    round1_places: dict[int, int] = {}
    place_by_problem: dict[int, int] = {}
    for bid in bids:
        team = participant_team_by_id.get(bid.team_id)
        if not team or team.round1_assignment_type != "BID_WINNER" or team.round1_problem_id != bid.ps_id:
            continue
        place_by_problem[bid.ps_id] = place_by_problem.get(bid.ps_id, 0) + 1
        round1_places[team.id] = place_by_problem[bid.ps_id]
    active_lab_ids = {lab.id for lab in labs}
    assignment_by_team = {}
    assigned_pairs = set()
    for row in assignments:
        team = team_by_id.get(row.team_id)
        pair = (row.current_lab_id, row.effective_ps_id)
        if team and row.current_lab_id in active_lab_ids and row.effective_ps_id == get_final_problem_id(team) and pair not in assigned_pairs:
            assignment_by_team[row.team_id] = row
            assigned_pairs.add(pair)
    event_is_final = _event_is_final(db)
    ready, readiness_message = _readiness(db, teams, labs, event_is_final=event_is_final)
    current = _assignments_are_current(teams, labs, assignments)
    state = db.query(LabAllocationState).filter(LabAllocationState.id == 1).one_or_none()
    status = (state.status if state and state.status == "FINALIZED" else "ALLOCATED") if current else ("READY" if ready else "NOT_READY")
    message = (
        "Final lab allocation is available."
        if current
        else "Final assignments changed; generate a fresh lab allocation."
        if assignments and ready
        else readiness_message
    )

    def team_payload(team: Team) -> dict[str, Any]:
        effective = problem_by_id.get(team.ps_id)
        original = problem_by_id.get(team.round1_problem_id)
        wildcard_problem = problem_by_id.get(team.wildcard_problem_id)
        wildcard_row = wildcard_by_team.get(team.id)
        wildcard = bool(team.wildcard_problem_id and team.wildcard_problem_id == team.ps_id)
        return {
            "id": team.id,
            "team_code": f"T-{team.id:03d}",
            "team_name": team.team_name,
            "effective_problem": (
                {"id": effective.id, "number": effective.ps_number, "title": effective.title}
                if effective else None
            ),
            "original_problem": (
                {"id": original.id, "number": original.ps_number, "title": original.title}
                if original else None
            ),
            "wildcard": wildcard,
            "changed_from": original.ps_number if wildcard and original and original.id != team.ps_id else None,
            "logged_in": team.id in logged_in_team_ids,
            "round1": (
                {
                    "id": original.id,
                    "problem_number": original.ps_number,
                    "problem_title": original.title,
                    "winning_bid": team.round1_assignment_cost,
                    "assignment_type": team.round1_assignment_type,
                    "place": round1_places.get(team.id),
                }
                if original else None
            ),
            "wildcard_history": {
                "selected": wildcard_problem is not None,
                **(
                    {
                        "id": wildcard_problem.id,
                        "problem_number": wildcard_problem.ps_number,
                        "problem_title": wildcard_problem.title,
                    }
                    if wildcard_problem else {}
                ),
                "winning_bid": wildcard_row.winning_bid if wildcard_row else None,
                "place": wildcard_row.rank if wildcard_row else None,
            },
            "final_problem": (
                {"id": effective.id, "problem_number": effective.ps_number, "problem_title": effective.title}
                if effective else None
            ),
        }

    team_rows = [team_payload(team) for team in participant_teams]
    payload_by_team = {row["id"]: row for row in team_rows}
    buckets = []
    for lab in labs:
        rows = []
        for assignment in assignments:
            if assignment_by_team.get(assignment.team_id) is not assignment or assignment.current_lab_id != lab.id or assignment.team_id not in payload_by_team:
                continue
            rows.append({
                **payload_by_team[assignment.team_id],
                "assignment_id": assignment.id,
                "original_lab_id": assignment.original_lab_id,
                "current_lab_id": assignment.current_lab_id,
                "assignment_source": assignment.assignment_source,
                "constraint_override": assignment.constraint_override,
                "version": assignment.version,
                "moved_at": assignment.moved_at,
            })
        rows.sort(key=lambda row: (row["effective_problem"]["number"] if row["effective_problem"] else "", row["team_code"]))
        buckets.append({
            "id": lab.id,
            "name": lab.name,
            "capacity": lab.capacity,
            "sort_order": lab.sort_order,
            "active": lab.active,
            "occupancy": len(rows),
            "teams": rows,
        })

    valid_assigned_ids = set(assignment_by_team)
    eligible_unassigned = [team for team in teams if team.id not in valid_assigned_ids]
    generated, max_flow = _max_flow_assignment(teams, labs) if ready and not current else ({}, len(teams) if current else 0)
    if current:
        message = f"Final lab allocation is available. {len(teams)} / {len(teams)} eligible teams assigned."
    elif ready and max_flow < len(teams):
        message = f"Lab allocation incomplete. {max_flow} / {len(teams)} eligible teams can be placed; {len(teams) - max_flow} remain unassigned."
    elif ready:
        message = f"Lab allocation pending. {len(valid_assigned_ids)} / {len(teams)} eligible teams assigned."

    return {
        "status": status,
        "message": message,
        "can_allocate": ready and not current,
        "can_move": event_is_final,
        "allocated_at": state.allocated_at if state else None,
        "labs": buckets,
        "teams": team_rows,
        "unassigned_team_ids": [team.id for team in participant_teams if team.id not in assignment_by_team],
        "unassigned_teams": [
            {**team_payload(team), "reason": "no compatible lab slot available" if ready and team.id not in generated else "allocation pending"}
            for team in eligible_unassigned
        ],
        "eligible_team_count": len(teams),
        "assigned_count": len(valid_assigned_ids),
        "unassigned_count": len(eligible_unassigned),
        "max_flow_value": max_flow,
        "team_count": len(participant_teams),
        "logged_in_team_ids": sorted(logged_in_team_ids),
        "participant_logged_in_count": sum(team.id in logged_in_team_ids for team in participant_teams),
        "total_capacity": sum(lab.capacity for lab in labs),
    }
