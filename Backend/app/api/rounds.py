from __future__ import annotations

import csv
import io
import re
from typing import Iterable

from fastapi import APIRouter, Depends, File, HTTPException, Response as FastAPIResponse, UploadFile
from fastapi.responses import Response
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.api.auth import get_current_active_admin, get_current_user
from app.api.websockets import manager
from app.core.database import get_db
from app.models.models import Bid, GameConfig, ProblemStatement, RoundControl, Team, WalletTransaction, Wildcard
from app.services.event_service import (
    _remaining_seconds,
    event_snapshot,
    get_or_create_event_config,
    get_or_create_game_config,
    get_or_create_round_control,
    sync_expired_event_state,
    transition_event_state,
)
from app.services.activity_log import record_event
from app.services.wildcard_service import ranking_payload, wildcard_payload

router = APIRouter()

ROUND_META = {
    "round-1": {"type": "ROUND1", "number": 1, "prefix": "R1", "label": "Round 1"},
    "wildcard": {"type": "WILDCARD", "number": 2, "prefix": "WC", "label": "Wildcard"},
}
NUMBER_HEADERS = {"problemnumber", "problemno", "problemid", "number", "id"}
STATEMENT_HEADERS = {"problemstatement", "statement", "description", "problem"}


def _meta(round_slug: str) -> dict:
    meta = ROUND_META.get(round_slug)
    if not meta:
        raise HTTPException(status_code=404, detail="Round not found")
    return meta


def _normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def _read_problem_rows(filename: str, content: bytes) -> list[tuple[int, str]]:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in {"csv", "xlsx"}:
        raise HTTPException(status_code=400, detail="Unsupported file. Upload an .xlsx or .csv file.")
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    if suffix == "csv":
        try:
            rows: Iterable[list[object]] = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise HTTPException(status_code=400, detail="The CSV file could not be read.") from exc
    else:
        try:
            sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
            rows = list(sheet.iter_rows(values_only=True))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="The XLSX file could not be read.") from exc

    rows = [list(row) for row in rows if any(str(cell or "").strip() for cell in row)]
    if not rows:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    headers = [_normalized(value) for value in rows[0]]
    number_index = next((index for index, value in enumerate(headers) if value in NUMBER_HEADERS), None)
    statement_index = next((index for index, value in enumerate(headers) if value in STATEMENT_HEADERS), None)
    if number_index is None:
        raise HTTPException(status_code=400, detail="Missing problem number column.")
    if statement_index is None:
        raise HTTPException(status_code=400, detail="Missing problem statement column.")

    parsed: list[tuple[int, str]] = []
    seen: set[int] = set()
    errors: list[str] = []
    for source_row, row in enumerate(rows[1:], start=2):
        raw_number = row[number_index] if number_index < len(row) else None
        statement = str(row[statement_index] if statement_index < len(row) else "").strip()
        try:
            number = int(raw_number)
            if number <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"Row {source_row}: problem number must be a positive whole number.")
            continue
        if number in seen:
            errors.append(f"Row {source_row}: duplicate problem number {number}.")
        if not statement:
            errors.append(f"Row {source_row}: problem statement is required.")
        if number not in seen and statement:
            parsed.append((number, statement))
        seen.add(number)
    if not parsed and not errors:
        errors.append("The file contains headers but no problems.")
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return parsed


def _display_number(problem: ProblemStatement) -> str:
    return problem.ps_number.split("-", 1)[-1]


def _problem_payload(problem: ProblemStatement, control: RoundControl) -> dict:
    if problem.id == control.current_problem_id:
        status = "CURRENT"
    elif problem.status in {"completed", "allocated"}:
        status = "COMPLETED"
    else:
        status = "AVAILABLE"
    return {
        "id": problem.id,
        "problem_number": _display_number(problem),
        "problem_statement": problem.description or problem.title,
        "status": status,
    }


def _sync_application_window(db: Session, control: RoundControl) -> None:
    if control.applications_open and _remaining_seconds(get_or_create_game_config(db)) == 0:
        control.applications_open = False
        db.commit()


def _round_payload(db: Session, meta: dict) -> dict:
    if meta["type"] == "WILDCARD":
        return wildcard_payload(db)
    control = get_or_create_round_control(db, meta["type"])
    config = get_or_create_event_config(db)
    problems = db.query(ProblemStatement).filter(ProblemStatement.round == meta["number"]).order_by(ProblemStatement.id).all()
    current = next((problem for problem in problems if problem.id == control.current_problem_id), None)
    current_bids = []
    if current:
        current_bids = db.query(Bid).filter(Bid.ps_id == current.id, Bid.round == meta["number"]).order_by(Bid.amount.desc(), Bid.timestamp.asc()).all()
    highest = current_bids[0] if current_bids else None
    highest_team = db.query(Team).filter(Team.id == highest.team_id).first() if highest else None
    payload = {
        "round_type": meta["type"],
        "status": control.status,
        "ended": control.ended,
        "current_problem": _problem_payload(current, control) if current else None,
        "problems": [_problem_payload(problem, control) for problem in problems],
        "highest_bid": highest.amount if highest else None,
        "highest_team": highest_team.team_name if highest_team else None,
        "settings": {
            "preview_seconds": config.round1_preview_seconds if meta["number"] == 1 else config.wildcard_preview_seconds,
            "bidding_seconds": config.round1_bid_seconds if meta["number"] == 1 else config.wildcard_bid_seconds,
        },
        "event": event_snapshot(db),
    }
    return payload


@router.get("/admin/rounds/{round_slug}")
def get_round(round_slug: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    return _round_payload(db, _meta(round_slug))


@router.post("/admin/rounds/{round_slug}/problems/import")
async def import_problems(round_slug: str, file: UploadFile = File(...), db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    meta = _meta(round_slug)
    rows = _read_problem_rows(file.filename or "", await file.read())
    created = updated = 0
    for number, statement in rows:
        internal_number = f"{meta['prefix']}-{number}"
        problem = db.query(ProblemStatement).filter(ProblemStatement.ps_number == internal_number).first()
        if problem and problem.status in {"current", "completed", "allocated"}:
            raise HTTPException(status_code=409, detail=f"Problem {number} is already current or completed and cannot be overwritten.")
        if problem:
            problem.title = statement
            problem.description = statement
            problem.status = "available"
            updated += 1
        else:
            db.add(ProblemStatement(ps_number=internal_number, title=statement, description=statement, round=meta["number"], status="available"))
            created += 1
    control = get_or_create_round_control(db, meta["type"])
    if meta["type"] == "ROUND1" and control.status == "IDLE":
        control.status = "READY"
    record_event(db, f"{meta['type'].lower()}.problems_imported", actor=current_user, metadata={"count": len(rows), "filename": file.filename or ""})
    db.commit()
    await manager.broadcast_event("round_updated", {"round": meta["type"], "action": "problems_imported"})
    return {"imported": len(rows), "created": created, "updated": updated, **_round_payload(db, meta)}


@router.get("/admin/rounds/{round_slug}/problems/sample.csv")
def problem_sample(round_slug: str, current_user=Depends(get_current_active_admin)):
    meta = _meta(round_slug)
    sample = "Problem Number,Problem Statement\r\n1,\"Develop an AI-enabled solution for ...\"\r\n2,\"Design a system that ...\"\r\n3,\"Build a platform that ...\"\r\n"
    return Response(sample, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={round_slug}-problems-sample.csv"})


@router.post("/admin/rounds/{round_slug}/problems/{problem_id}/select")
async def select_problem(round_slug: str, problem_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    meta = _meta(round_slug)
    if meta["type"] == "WILDCARD":
        raise HTTPException(status_code=409, detail="Wildcard problems are selected by qualified teams after slot bidding.")
    control = get_or_create_round_control(db, meta["type"])
    if control.current_problem_id == problem_id:
        return _round_payload(db, meta)
    if control.ended:
        raise HTTPException(status_code=409, detail=f"{meta['label']} is closed.")
    if control.current_problem_id:
        raise HTTPException(status_code=409, detail="Complete the current problem before selecting another one.")
    problem = db.query(ProblemStatement).filter(ProblemStatement.id == problem_id, ProblemStatement.round == meta["number"]).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found in this round.")
    if problem.status in {"completed", "allocated"}:
        raise HTTPException(status_code=409, detail="A completed problem cannot be selected again.")
    problem.status = "current"
    control.current_problem_id = problem.id
    control.status = "READY"
    record_event(db, "round1.problem_selected", actor=current_user, entity_type="problem", entity_id=problem.id)
    db.commit()
    await manager.broadcast_event("round_updated", {"round": meta["type"], "action": "problem_selected", "problem_id": problem.id})
    return _round_payload(db, meta)


@router.post("/admin/rounds/{round_slug}/preview/start")
async def start_preview(round_slug: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    meta = _meta(round_slug)
    if meta["type"] == "WILDCARD":
        raise HTTPException(status_code=409, detail="Wildcard no longer has a global problem preview phase.")
    control = get_or_create_round_control(db, meta["type"])
    if control.status in {"PREVIEW", "PREVIEW_EXPIRED"}:
        return _round_payload(db, meta)
    if control.ended or not control.current_problem_id:
        raise HTTPException(status_code=409, detail="Select an available problem before starting preview.")
    state = "ROUND1_PREVIEW" if meta["number"] == 1 else "WILDCARD_PREVIEW"
    transition_event_state(db, state, validate=False, commit=False)
    control.status = "PREVIEW"
    record_event(db, "round1.preview_started", actor=current_user, entity_type="problem", entity_id=control.current_problem_id)
    db.commit()
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return _round_payload(db, meta)


@router.post("/admin/rounds/{round_slug}/bidding/start")
async def start_bidding(round_slug: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    meta = _meta(round_slug)
    if meta["type"] == "WILDCARD":
        raise HTTPException(status_code=409, detail="Use the Wildcard slot bidding control.")
    control = get_or_create_round_control(db, meta["type"])
    sync_expired_event_state(db)
    db.refresh(control)
    if control.status == "BIDDING":
        return _round_payload(db, meta)
    if control.ended or not control.current_problem_id or control.status not in {"PREVIEW", "PREVIEW_EXPIRED", "READY"}:
        raise HTTPException(status_code=409, detail="Preview a selected problem before starting bidding.")
    state = "ROUND1_BIDDING" if meta["number"] == 1 else "WILDCARD_BIDDING"
    transition_event_state(db, state, validate=False, commit=False)
    control.status = "BIDDING"
    record_event(db, "round1.bidding_started", actor=current_user, entity_type="problem", entity_id=control.current_problem_id)
    db.commit()
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return _round_payload(db, meta)


@router.post("/admin/rounds/{round_slug}/bidding/close")
async def close_bidding(round_slug: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    meta = _meta(round_slug)
    if meta["type"] == "WILDCARD":
        raise HTTPException(status_code=409, detail="Use the Wildcard slot bidding control.")
    control = get_or_create_round_control(db, meta["type"])
    sync_expired_event_state(db)
    db.refresh(control)
    game = get_or_create_game_config(db)
    if control.status == "READY" and game.state == "ROUND1_RESULT":
        return _round_payload(db, meta)
    if control.status != "BIDDING":
        raise HTTPException(status_code=409, detail="Bidding is not active.")
    transition_event_state(db, "ROUND1_RESULT" if meta["number"] == 1 else "WILDCARD_SELECTION", validate=False, commit=False)
    control.status = "READY"
    record_event(db, "round1.bidding_closed", actor=current_user, entity_type="problem", entity_id=control.current_problem_id)
    db.commit()
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return _round_payload(db, meta)


@router.post("/admin/rounds/{round_slug}/assign-winners")
async def assign_winners(round_slug: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    meta = _meta(round_slug)
    if meta["type"] == "WILDCARD":
        raise HTTPException(status_code=409, detail="Wildcard slot winners are finalized when slot bidding closes.")
    control = get_or_create_round_control(db, meta["type"])
    if control.current_problem_id is None and control.status == "READY":
        return {"message": "Winner assignment already completed.", "winners": [], **_round_payload(db, meta)}
    problem = db.query(ProblemStatement).filter(ProblemStatement.id == control.current_problem_id, ProblemStatement.round == meta["number"]).first()
    if not problem or control.status != "READY":
        raise HTTPException(status_code=409, detail="Close bidding before assigning winners.")
    event_config = get_or_create_event_config(db)
    winner_limit = event_config.round1_winner_count if meta["number"] == 1 else event_config.wildcard_slots
    bids = db.query(Bid).filter(Bid.ps_id == problem.id, Bid.round == meta["number"]).order_by(Bid.amount.desc(), Bid.timestamp.asc()).all()
    winners = []
    for bid in bids:
        if len(winners) >= winner_limit:
            break
        team = db.query(Team).filter(Team.id == bid.team_id).first()
        if not team or team.ps_id is not None or team.coins < bid.amount:
            continue
        if meta["number"] == 2:
            application = db.query(Wildcard).filter(Wildcard.team_id == team.id, Wildcard.status == "applied").first()
            if not application:
                continue
            application.status = "selected"
            application.used = True
            application.coins_paid = bid.amount
        team.coins -= bid.amount
        team.ps_id = problem.id
        if meta["number"] == 1:
            team.round1_problem_id = problem.id
        db.add(WalletTransaction(team_id=team.id, transaction_type="ROUND1_WIN" if meta["number"] == 1 else "WILDCARD_WIN", amount=-bid.amount, description=f"{meta['label']} win for problem {_display_number(problem)}"))
        winners.append({"team_id": team.id, "team_name": team.team_name, "amount": bid.amount})
    problem.status = "completed"
    control.current_problem_id = None
    control.status = "READY"
    record_event(db, "round1.winners_assigned", actor=current_user, entity_type="problem", entity_id=problem.id, metadata={"winner_team_ids": [winner["team_id"] for winner in winners]})
    db.commit()
    await manager.broadcast_event("round_updated", {"round": meta["type"], "action": "winners_assigned", "winners": winners})
    return {"winners": winners, **_round_payload(db, meta)}


@router.post("/admin/rounds/round-1/end")
async def end_round_one(db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    control = get_or_create_round_control(db, "ROUND1")
    if control.ended:
        return _round_payload(db, ROUND_META["round-1"])
    if control.current_problem_id or control.status in {"PREVIEW", "BIDDING"}:
        raise HTTPException(status_code=409, detail="Complete the current problem before ending Round 1.")
    control.ended = True
    control.status = "CLOSED"
    transition_event_state(db, "ROUND1_RESULT", validate=False, commit=False)
    record_event(db, "round1.ended", actor=current_user)
    db.commit()
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return _round_payload(db, ROUND_META["round-1"])


@router.post("/admin/rounds/wildcard/applications/open")
async def open_applications(db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    round1 = get_or_create_round_control(db, "ROUND1")
    wildcard = get_or_create_round_control(db, "WILDCARD")
    if not round1.ended:
        raise HTTPException(status_code=409, detail="End Round 1 before opening Wildcard applications.")
    if wildcard.status == "APPLICATIONS_OPEN":
        return _round_payload(db, ROUND_META["wildcard"])
    if wildcard.status != "NOT_STARTED" or wildcard.slot_count is not None:
        raise HTTPException(status_code=409, detail=f"Wildcard applications cannot open from {wildcard.status}.")
    wildcard.applications_open = True
    wildcard.status = "APPLICATIONS_OPEN"
    transition_event_state(db, "WILDCARD_APPLICATION", validate=False, restart=True, commit=False)
    record_event(db, "wildcard.applications_opened", actor=current_user)
    db.commit()
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return _round_payload(db, ROUND_META["wildcard"])


@router.post("/admin/rounds/wildcard/applications/close")
async def close_applications(db: Session = Depends(get_db), current_user=Depends(get_current_active_admin)):
    control = get_or_create_round_control(db, "WILDCARD")
    sync_expired_event_state(db)
    db.refresh(control)
    if control.status == "APPLICATIONS_CLOSED":
        return _round_payload(db, ROUND_META["wildcard"])
    if control.status != "APPLICATIONS_OPEN":
        raise HTTPException(status_code=409, detail="Wildcard applications are not open.")
    control.applications_open = False
    control.status = "APPLICATIONS_CLOSED"
    game = get_or_create_game_config(db)
    game.auction_timer_end = None
    game.timer_paused = False
    game.timer_paused_remaining_seconds = None
    record_event(db, "wildcard.applications_closed", actor=current_user)
    db.commit()
    await manager.broadcast_event("wildcard_updated", {"action": "applications_closed"})
    return _round_payload(db, ROUND_META["wildcard"])


@router.get("/leaderboard/{round_slug}")
def public_round_leaderboard(round_slug: str, response: FastAPIResponse, db: Session = Depends(get_db)):
    meta = _meta(round_slug)
    response.headers["Cache-Control"] = "no-store"
    if meta["type"] == "WILDCARD":
        control = get_or_create_round_control(db, "WILDCARD")
        return {
            "round": "WILDCARD",
            "label": "Wildcard Slot Auction",
            "slot_count": control.slot_count,
            "finalized": control.status in {"PROBLEM_SELECTION", "COMPLETE"},
            "active": control.status == "BIDDING_OPEN",
            "rows": ranking_payload(db, control),
        }
    control = get_or_create_round_control(db, "ROUND1")
    query = db.query(Bid).filter(Bid.round == 1)
    if control.current_problem_id:
        query = query.filter(Bid.ps_id == control.current_problem_id)
    bids = query.order_by(Bid.amount.desc(), Bid.timestamp.asc(), Bid.team_id.asc()).all()
    highest_by_team = {}
    for bid in bids:
        if bid.team_id not in highest_by_team or bid.amount > highest_by_team[bid.team_id].amount:
            highest_by_team[bid.team_id] = bid
    rows = []
    for team_id, bid in highest_by_team.items():
        team = db.query(Team).filter(Team.id == team_id).first()
        if team:
            rows.append({"team_id": team.id, "team_name": team.team_name, "value": bid.amount, "problem_id": bid.ps_id})
    rows.sort(key=lambda row: (-row["value"], row["team_id"]))
    return {
        "round": meta["type"],
        "label": meta["label"],
        "active": control.status == "BIDDING",
        "finalized": control.ended or control.status == "CLOSED",
        "rows": [{**row, "rank": index} for index, row in enumerate(rows, start=1)],
    }
