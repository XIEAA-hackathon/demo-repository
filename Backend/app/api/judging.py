from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.auth import get_current_active_admin, get_current_active_display
from app.api.rounds import public_round_leaderboard
from app.api.websockets import manager
from app.core.database import get_db
from app.models.models import FinalResult, ProblemStatement, Team, User
from app.schemas.schemas import JudgingWinnersUpdate
from app.services.activity_log import record_event
from app.services.event_service import (
    event_snapshot,
    get_or_create_game_config,
    get_or_create_round_control,
    sync_expired_event_state,
    transition_event_state,
)

router = APIRouter()


def _team_payload(team: Team | None) -> dict | None:
    return {"team_id": team.id, "team_name": team.team_name} if team else None


def _result_payload(db: Session, result: FinalResult | None, *, include_waiting_winners: bool) -> dict:
    ids = [] if not result else [
        result.first_place_team_id,
        result.second_place_team_id,
        result.third_place_team_id,
    ]
    teams = {team.id: team for team in db.query(Team).filter(Team.id.in_(ids)).all()} if ids else {}
    visible = bool(result and (include_waiting_winners or result.result_status == "PUBLISHED"))
    return {
        "result_status": result.result_status if result else "WAITING",
        "first_place": _team_payload(teams.get(result.first_place_team_id)) if visible and result else None,
        "second_place": _team_payload(teams.get(result.second_place_team_id)) if visible and result else None,
        "third_place": _team_payload(teams.get(result.third_place_team_id)) if visible and result else None,
        "saved_at": result.saved_at if result else None,
        "published_at": result.published_at if result and result.result_status == "PUBLISHED" else None,
    }


def _validated_teams(db: Session, payload: JudgingWinnersUpdate) -> dict[int, Team]:
    ids = [payload.first_place_team_id, payload.second_place_team_id, payload.third_place_team_id]
    if len(set(ids)) != 3:
        raise HTTPException(status_code=400, detail="The same team cannot occupy multiple positions.")
    teams = {team.id: team for team in db.query(Team).filter(Team.id.in_(ids)).all()}
    if len(teams) != 3:
        raise HTTPException(status_code=400, detail="All winner positions must reference valid registered teams.")
    return teams


@router.get("/admin/judging")
def get_admin_judging(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    del current_user
    result = db.query(FinalResult).first()
    return {
        **_result_payload(db, result, include_waiting_winners=True),
        "teams": [
            {"team_id": team.id, "team_name": team.team_name}
            for team in db.query(Team).order_by(Team.team_name.asc()).all()
        ],
    }


@router.put("/admin/judging/winners")
def save_winners(
    payload: JudgingWinnersUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    _validated_teams(db, payload)
    result = db.query(FinalResult).first()
    if result and result.result_status == "PUBLISHED":
        raise HTTPException(status_code=409, detail="Published results cannot be changed. Reset the event to enter new winners.")
    if not result:
        result = FinalResult()
        db.add(result)
    result.first_place_team_id = payload.first_place_team_id
    result.second_place_team_id = payload.second_place_team_id
    result.third_place_team_id = payload.third_place_team_id
    result.saved_at = datetime.now(timezone.utc)
    result.published_at = None
    result.result_status = "WAITING"
    record_event(db, "judging.winners_saved", actor=current_user)
    db.commit()
    db.refresh(result)
    return _result_payload(db, result, include_waiting_winners=True)


@router.post("/admin/judging/publish")
async def publish_winners(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    result = db.query(FinalResult).first()
    winner_ids = [] if not result else [
        result.first_place_team_id,
        result.second_place_team_id,
        result.third_place_team_id,
    ]
    if not result or any(team_id is None for team_id in winner_ids):
        raise HTTPException(status_code=409, detail="Save all three winners before displaying results.")
    _validated_teams(db, JudgingWinnersUpdate(
        first_place_team_id=result.first_place_team_id,
        second_place_team_id=result.second_place_team_id,
        third_place_team_id=result.third_place_team_id,
    ))
    if result.result_status != "PUBLISHED":
        result.result_status = "PUBLISHED"
        result.published_at = datetime.now(timezone.utc)
        transition_event_state(db, "RESULTS", validate=False, commit=False)
        record_event(db, "judging.results_published", actor=current_user)
        db.commit()
    public_result = _result_payload(db, result, include_waiting_winners=False)
    await manager.broadcast_event("results_published", {"result_status": "PUBLISHED"})
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return public_result


@router.get("/public/leaderboard")
def public_event_display(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_display),
):
    del current_user
    response.headers["Cache-Control"] = "no-store"
    sync_expired_event_state(db)
    game = get_or_create_game_config(db)
    result = db.query(FinalResult).filter(FinalResult.result_status == "PUBLISHED").first()
    timing = event_snapshot(db)["timing"]
    if result:
        return {
            "mode": "RESULTS_PUBLISHED",
            "event_state": game.state,
            "status_label": "Final Results",
            "results": _result_payload(db, result, include_waiting_winners=False),
            "rows": [],
            "timing": timing,
        }

    if game.state == "ROUND1_BIDDING":
        board = public_round_leaderboard("round-1", response, db)
        control = get_or_create_round_control(db, "ROUND1")
        problem = db.query(ProblemStatement).filter(ProblemStatement.id == control.current_problem_id).first()
        return {
            "mode": "ROUND1_LIVE",
            "event_state": game.state,
            "status_label": "Round 1 — Live Bidding",
            "problem": ({
                "problem_number": problem.ps_number.split("-", 1)[-1],
                "number": problem.ps_number.split("-", 1)[-1],
                "title": problem.title,
                "description": problem.description,
            } if problem else None),
            "rows": board["rows"],
            "slot_count": None,
            "results": None,
            "timing": timing,
        }

    if game.state == "WILDCARD_BIDDING":
        board = public_round_leaderboard("wildcard", response, db)
        return {
            "mode": "WILDCARD_LIVE",
            "event_state": game.state,
            "status_label": "Wildcard — Live Bidding",
            "problem": None,
            "rows": board["rows"],
            "slot_count": board["slot_count"],
            "results": None,
            "timing": timing,
        }

    labels = {
        "WAITING": "Waiting for next round",
        "ROUND1_PREVIEW": "Problem preview",
        "ROUND1_RESULT": "Round 1 results",
        "WILDCARD_APPLICATION": "Wildcard applications",
        "WILDCARD_SELECTION": "Wildcard problem selection",
        "CODING": "Coding in progress",
        "SUBMISSION": "Submission window",
        "JUDGING_WAIT": "Judging in progress",
        "RESULTS": "Waiting for results",
    }
    problem = None
    if game.state.startswith("ROUND1"):
        control = get_or_create_round_control(db, "ROUND1")
        if control.current_problem_id:
            problem = db.query(ProblemStatement).filter(ProblemStatement.id == control.current_problem_id).first()
    elif game.state.startswith("WILDCARD"):
        control = get_or_create_round_control(db, "WILDCARD")
        if control.current_problem_id:
            problem = db.query(ProblemStatement).filter(ProblemStatement.id == control.current_problem_id).first()
    return {
        "mode": "JUDGING_WAITING" if game.state == "JUDGING_WAIT" else "RESULTS_WAITING" if game.state == "RESULTS" else "WAITING",
        "event_state": game.state,
        "status_label": labels.get(game.state, "Waiting for next round"),
        "problem": ({
            "problem_number": problem.ps_number.split("-", 1)[-1],
            "number": problem.ps_number.split("-", 1)[-1],
            "title": problem.title,
            "description": problem.description,
        } if problem else None),
        "rows": [],
        "slot_count": None,
        "results": None,
        "timing": timing,
    }
