from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import secrets
import tempfile
import time
from pydantic import BaseModel

from app.core.database import get_db
from app.models.models import (
    User, Team, Member, EventConfig, Submission,
    RegistrationImport, RegistrationImportRow, WalletTransaction, ProblemStatement,
)
from app.schemas.schemas import (
    EventConfigUpdate, EventConfigResponse,
    ImportPreviewResponse, ImportConfirmResponse, ImportRowPreview,
    CredentialRow, ManualTeamCredentialsRequest, ManualTeamCredentialsResponse,
    EventStateUpdate, TimerAdjustment, EVENT_STATES,
)
from app.api.auth import get_current_active_admin
from app.api.websockets import manager
from app.services.participant_presence import participant_presence_payload
from app.services.event_service import (
    event_snapshot,
    get_or_create_event_config,
    get_or_create_game_config,
    transition_event_state,
    pause_event_timer,
    resume_event_timer,
    adjust_event_timer,
)
from app.services.registration_import import (
    parse_registration_file, _default_password, _is_valid_email,
    build_registration_credential_csv, build_registration_credential_workbook,
    build_registration_assignment_csv, build_registration_assignment_workbook,
    ASSIGNMENT_HEADERS,
)
from app.services.reset_service import reset_event_and_imported_participants, reset_imported_participant_credentials
from app.services.activity_log import record_event
from app.core.security import get_password_hash
from app.core.event_constants import ROUND1_WINNER_COUNT
import json

router = APIRouter()

_EXPORT_TTL_SECONDS = 15 * 60
_EXPORT_DIRECTORY = Path(tempfile.gettempdir()) / "bid_to_build_credential_exports"


@router.get("/admin/registration/sample.csv")
def registration_sample(current_user=Depends(get_current_active_admin)):
    sample = (
        "Team Name,Leader Name,Leader Email,Leader Password,Member 1 Name,Member 1 Email,Member 1 Password,Member 2 Name,Member 2 Email,Member 2 Password\r\n"
        "Demo Team,Demo Leader,leader@example.com,DemoLeader@123,Member One,member1@example.com,DemoMember1@123,Member Two,member2@example.com,DemoMember2@123\r\n"
    )
    return Response(sample, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=registration-import-sample.csv"})


@router.get("/admin/registration/demo.csv")
def registration_demo(current_user=Depends(get_current_active_admin)):
    sample = (
        "Team Name,Leader Name,Leader Email,Leader Password,Member 1 Name,Member 1 Email,Member 1 Password,Member 2 Name,Member 2 Email,Member 2 Password\r\n"
        "Team Alpha,Alice Sharma,alice@example.com,Alpha@123,Bob Kumar,bob@example.com,AlphaMember1@123,Carol Singh,carol@example.com,AlphaMember2@123\r\n"
        "Team Beta,David Rao,david@example.com,Beta@123,Esha Patel,esha@example.com,BetaMember1@123,Farhan Ali,farhan@example.com,BetaMember2@123\r\n"
    )
    return Response(sample, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=bid-to-build-demo-registration.csv"})


def _store_credential_export(content: bytes, suffix: str) -> str:
    _EXPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for export_path in _EXPORT_DIRECTORY.glob("*"):
        if now - export_path.stat().st_mtime > _EXPORT_TTL_SECONDS:
            export_path.unlink(missing_ok=True)
    token = secrets.token_urlsafe(24)
    (_EXPORT_DIRECTORY / f"{token}{suffix}").write_bytes(content)
    return token


def _user_by_login(db: Session, login_id: str) -> User | None:
    return db.query(User).filter(func.lower(User.email) == login_id.strip().lower()).first()


def _participant_id(db: Session, team_id: int, position: int) -> str:
    base = f"BTB-T{team_id:03d}-M{position:02d}"
    candidate = base
    suffix = 2
    existing = _user_by_login(db, candidate)
    if existing and existing.team_id == team_id:
        return candidate
    while existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
        existing = _user_by_login(db, candidate)
    return candidate


def _credential(user: User, team: Team, password: str, supplied_email: str = "") -> CredentialRow:
    return CredentialRow(
        user_id=user.id,
        team_name=team.team_name,
        name=user.name,
        email=supplied_email,
        username=user.email,
        participant_id=user.email,
        temporary_password=password,
        role=user.role,
    )

# ---------------------------------------------------------------- Event Config

@router.get("/admin/config", response_model=EventConfigResponse)
def get_event_config_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    return get_or_create_event_config(db)

@router.put("/admin/config", response_model=EventConfigResponse)
async def update_event_config_admin(
    updates: EventConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    config = get_or_create_event_config(db)
    data = updates.model_dump(exclude_unset=True)

    # Validation
    if "starting_coins" in data and not 0 <= data["starting_coins"] <= 1_000_000:
        raise HTTPException(status_code=400, detail="starting_coins must be between 0 and 1000000")
    for field in ["round1_preview_seconds", "round1_bid_seconds", "wildcard_application_seconds", "wildcard_preview_seconds", "wildcard_bid_seconds"]:
        if field in data and data[field] <= 0:
            raise HTTPException(status_code=400, detail=f"{field} must be > 0")
    if "wildcard_selection_seconds" in data and not 5 <= data["wildcard_selection_seconds"] <= 300:
        raise HTTPException(status_code=400, detail="wildcard_selection_seconds must be between 5 and 300")
    if "round1_winner_count" in data and data["round1_winner_count"] != ROUND1_WINNER_COUNT:
        raise HTTPException(status_code=400, detail=f"round1_winner_count must be exactly {ROUND1_WINNER_COUNT}")
    if "round1_minimum_bid" in data and data["round1_minimum_bid"] < 0:
        raise HTTPException(status_code=400, detail="round1_minimum_bid must be >= 0")
    if "round1_bid_increment" in data and data["round1_bid_increment"] <= 0:
        raise HTTPException(status_code=400, detail="round1_bid_increment must be > 0")
    if "wildcard_starting_bid" in data and data["wildcard_starting_bid"] < 0:
        raise HTTPException(status_code=400, detail="wildcard_starting_bid must be >= 0")
    if "wildcard_bid_increment" in data and data["wildcard_bid_increment"] <= 0:
        raise HTTPException(status_code=400, detail="wildcard_bid_increment must be > 0")
    if "wildcard_slots" in data and data["wildcard_slots"] < 0:
        raise HTTPException(status_code=400, detail="wildcard_slots must be >= 0")
    if "wildcard_problem_count" in data and data["wildcard_problem_count"] < 0:
        raise HTTPException(status_code=400, detail="wildcard_problem_count must be >= 0")
    if "coding_duration_seconds" in data and data["coding_duration_seconds"] < 0:
        raise HTTPException(status_code=400, detail="coding_duration_seconds must be >= 0")
    if "bid_cooldown_seconds" in data and not 0 <= data["bid_cooldown_seconds"] <= 60:
        raise HTTPException(status_code=400, detail="bid_cooldown_seconds must be between 0 and 60")
    if "royalty_coins_per_point" in data and data["royalty_coins_per_point"] < 0:
        raise HTTPException(status_code=400, detail="royalty_coins_per_point must be >= 0")
    if "royalty_max_points" in data and data["royalty_max_points"] < 0:
        raise HTTPException(status_code=400, detail="royalty_max_points must be >= 0")

    for field, value in data.items():
        setattr(config, field, value)
    record_event(db, "event.configuration_updated", actor=current_user, metadata={"fields": sorted(data)})
    db.commit()
    db.refresh(config)
    await manager.broadcast_event("config_updated", {"config": EventConfigResponse.model_validate(config).model_dump(mode="json")})
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return config


async def _broadcast_bid_cooldown(db: Session, config: EventConfig) -> None:
    serialized = EventConfigResponse.model_validate(config).model_dump(mode="json")
    await manager.broadcast_event("config_updated", {"config": serialized})
    await manager.broadcast_event("event_state_changed", event_snapshot(db))


@router.put("/admin/cooldown")
async def set_bid_cooldown(
    seconds: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    if not 0 <= seconds <= 60:
        raise HTTPException(status_code=400, detail="Cooldown seconds must be between 0 and 60")
    config = get_or_create_event_config(db)
    config.bid_cooldown_seconds = seconds
    record_event(db, "event.bid_cooldown_updated", actor=current_user, metadata={"seconds": seconds})
    db.commit()
    db.refresh(config)
    await _broadcast_bid_cooldown(db, config)
    return {"message": f"Bid cooldown updated to {seconds} seconds", "bid_cooldown_seconds": seconds}


@router.post("/admin/cooldown/add")
async def add_bid_cooldown(
    seconds: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="Seconds to add must be > 0")
    config = get_or_create_event_config(db)
    new_seconds = (config.bid_cooldown_seconds or 0) + seconds
    if new_seconds > 60:
        raise HTTPException(status_code=400, detail="Cooldown seconds must be between 0 and 60")
    config.bid_cooldown_seconds = new_seconds
    record_event(db, "event.bid_cooldown_updated", actor=current_user, metadata={"seconds": config.bid_cooldown_seconds})
    db.commit()
    db.refresh(config)
    await _broadcast_bid_cooldown(db, config)
    return {
        "message": f"Added {seconds} second(s) to bid cooldown. New cooldown: {config.bid_cooldown_seconds}s",
        "bid_cooldown_seconds": config.bid_cooldown_seconds,
    }


@router.post("/admin/cooldown/reduce")
async def reduce_bid_cooldown(
    seconds: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="Seconds to reduce must be > 0")
    config = get_or_create_event_config(db)
    config.bid_cooldown_seconds = max(0, (config.bid_cooldown_seconds or 0) - seconds)
    record_event(db, "event.bid_cooldown_updated", actor=current_user, metadata={"seconds": config.bid_cooldown_seconds})
    db.commit()
    db.refresh(config)
    await _broadcast_bid_cooldown(db, config)
    return {
        "message": f"Reduced bid cooldown by {seconds} second(s). New cooldown: {config.bid_cooldown_seconds}s",
        "bid_cooldown_seconds": config.bid_cooldown_seconds,
    }

# ---------------------------------------------------------------- Event State

async def _apply_event_state(payload: EventStateUpdate, db: Session, current_user: User):
    config = transition_event_state(db, payload.state, commit=False)
    record_event(db, "event.state_changed", actor=current_user, metadata={"state": config.state})
    db.commit()
    snapshot = event_snapshot(db)
    db.close()
    await manager.broadcast_event("event_state_changed", snapshot)
    return snapshot

@router.put("/admin/event/state")
async def set_event_state(
    payload: EventStateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    return await _apply_event_state(payload, db, current_user)


@router.post("/admin/event/transition")
async def transition_event(
    payload: EventStateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    return await _apply_event_state(payload, db, current_user)

@router.post("/admin/state")
async def set_event_state_legacy(
    payload: EventStateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Backward-compatible alias. New clients use PUT /admin/event/state."""
    result = await _apply_event_state(payload, db, current_user)
    return {"state": result["event_state"], **result}

@router.get("/admin/state")
def get_event_state_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    snapshot = event_snapshot(db)
    return {
        "state": snapshot["event_state"],
        **snapshot,
        "allowed_states": EVENT_STATES,
        "connected_clients": len(manager.active_connections),
        **participant_presence_payload(db, connected_team_ids=manager.participant_team_ids()),
    }


@router.post("/admin/event/timer/pause")
async def pause_event_timer_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    pause_event_timer(db)
    record_event(db, "event.timer_paused", actor=current_user)
    db.commit()
    snapshot = event_snapshot(db)
    db.close()
    await manager.broadcast_event("timer_sync", snapshot)
    return snapshot


@router.post("/admin/event/timer/resume")
async def resume_event_timer_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    resume_event_timer(db)
    record_event(db, "event.timer_resumed", actor=current_user)
    db.commit()
    snapshot = event_snapshot(db)
    db.close()
    await manager.broadcast_event("timer_sync", snapshot)
    return snapshot


@router.post("/admin/event/timer/adjust")
async def adjust_event_timer_admin(
    payload: TimerAdjustment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    adjust_event_timer(db, payload.seconds)
    record_event(db, "event.timer_adjusted", actor=current_user, metadata={"seconds": payload.seconds})
    db.commit()
    snapshot = event_snapshot(db)
    db.close()
    await manager.broadcast_event("timer_sync", {**snapshot, "delta": payload.seconds})
    return snapshot

# ---------------------------------------------------------------- Participant credentials

@router.post(
    "/admin/teams/credentials",
    response_model=ManualTeamCredentialsResponse,
    status_code=201,
)
async def create_team_credentials(
    payload: ManualTeamCredentialsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Create one team wallet and an individual account for every participant.

    Temporary passwords are returned once and never persisted as plaintext.
    """
    team_name = payload.team_name.strip()
    if db.query(Team).filter(func.lower(Team.team_name) == team_name.lower()).first():
        raise HTTPException(status_code=409, detail="TEAM ALREADY EXISTS")
    if not payload.leader.email:
        raise HTTPException(status_code=422, detail="Leader email is required.")

    supplied_logins = [str(payload.leader.email).strip().lower()]
    supplied_logins.extend(
        str(member.email).strip().lower() for member in payload.members if member.email
    )
    if len(supplied_logins) != len(set(supplied_logins)):
        raise HTTPException(status_code=409, detail="Each participant email/login ID must be unique.")
    for login_id in supplied_logins:
        if _user_by_login(db, login_id):
            raise HTTPException(status_code=409, detail=f"ACCOUNT ALREADY EXISTS: {login_id}")

    config = get_or_create_event_config(db)
    team = Team(team_name=team_name, coins=config.starting_coins, is_approved=True)
    db.add(team)
    db.flush()

    credentials: List[CredentialRow] = []
    leader_password = _default_password()
    leader_email = str(payload.leader.email).strip().lower()
    leader = User(
        name=payload.leader.name.strip(),
        email=leader_email,
        password_hash=get_password_hash(leader_password),
        role="leader",
        team_id=team.id,
    )
    db.add(leader)
    db.flush()
    team.leader_id = leader.id
    credentials.append(_credential(leader, team, leader_password, leader_email))

    for position, member in enumerate(payload.members, start=1):
        supplied_email = str(member.email).strip().lower() if member.email else ""
        login_id = supplied_email or _participant_id(db, team.id, position)
        password = _default_password()
        member_user = User(
            name=member.name.strip(),
            email=login_id,
            password_hash=get_password_hash(password),
            role="member",
            team_id=team.id,
        )
        db.add(member_user)
        db.flush()
        db.add(Member(
            team_id=team.id,
            member_name=member_user.name,
            email=login_id,
        ))
        credentials.append(_credential(member_user, team, password, supplied_email))

    db.add(WalletTransaction(
        team_id=team.id,
        transaction_type="INITIAL_ALLOCATION",
        amount=config.starting_coins,
        description="Initial AlumniCoins from EventConfig",
    ))
    db.commit()

    await manager.broadcast_event("team_updated", {
        "action": "team_credentials_created",
        "team_id": team.id,
        "team_name": team.team_name,
    })
    return ManualTeamCredentialsResponse(
        team_id=team.id,
        team_name=team.team_name,
        member_count=len(credentials),
        credentials=credentials,
    )


@router.get(
    "/admin/teams/{team_id}/credentials",
    response_model=ManualTeamCredentialsResponse,
)
def get_team_credentials(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """List existing participant login IDs without exposing passwords."""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    accounts = db.query(User).filter(or_(User.team_id == team.id, User.id == team.leader_id)).all()
    accounts.sort(key=lambda account: (account.id != team.leader_id, account.name.lower()))
    credentials = [
        _credential(account, team, "", account.email if "@" in account.email else "")
        for account in accounts
        if account.role in ("leader", "member")
    ]
    return ManualTeamCredentialsResponse(
        team_id=team.id,
        team_name=team.team_name,
        member_count=len(credentials),
        credentials=credentials,
    )


@router.post(
    "/admin/participant-accounts/{user_id}/reset-password",
    response_model=CredentialRow,
)
async def reset_participant_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    account = db.query(User).filter(User.id == user_id).first()
    if not account or account.role not in ("leader", "member"):
        raise HTTPException(status_code=404, detail="Participant account not found.")
    team = (
        db.query(Team).filter(Team.id == account.team_id).first()
        if account.team_id
        else db.query(Team).filter(Team.leader_id == account.id).first()
    )
    if not team:
        raise HTTPException(status_code=409, detail="Participant account is not assigned to a team.")
    password = _default_password()
    account.password_hash = get_password_hash(password)
    account.session_id = None
    account.credentials_active = True
    db.commit()
    await manager.disconnect_users({account.id})
    await manager.broadcast_event(
        "participant_presence_changed",
        participant_presence_payload(db, connected_team_ids=manager.participant_team_ids()),
    )
    supplied_email = account.email if "@" in account.email else ""
    return _credential(account, team, password, supplied_email)


# ---------------------------------------------------------------- Registration Import

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _validate_registration_filename(filename: str) -> None:
    if not filename.lower().endswith((".csv", ".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Invalid file type. Only .csv, .xlsx, and .xlsm files are allowed.")


class ParticipantCredentialResetRequest(BaseModel):
    confirmation: str


class ParticipantPasswordRequest(BaseModel):
    new_password: str
    confirm_password: str


def _disabled_password_hash() -> str:
    """Produce an unknowable placeholder hash guarded by credentials_active=False."""
    return get_password_hash(secrets.token_urlsafe(48))


def _participant_password_error(password: str) -> str | None:
    if len(password.encode("utf-8")) > 72:
        return "Password must be 72 bytes or fewer."
    return None


def _validate_participant_password(password: str, confirmation: str) -> None:
    if not password:
        raise HTTPException(status_code=422, detail="Password is required.")
    if password != confirmation:
        raise HTTPException(status_code=422, detail="Password confirmation does not match.")
    password_error = _participant_password_error(password)
    if password_error:
        raise HTTPException(status_code=422, detail=password_error)


def _participant_account_payload(db: Session, account: User) -> dict:
    team = db.query(Team).filter(Team.id == account.team_id).first() if account.team_id else None
    return {
        "user_id": account.id,
        "name": account.name,
        "login_id": account.email,
        "role": account.role,
        "team_id": team.id if team else None,
        "team_name": team.team_name if team else "Unassigned",
        "credential_status": "SET" if account.credentials_active else "NOT_SET",
    }


@router.post("/admin/registration/import")
async def import_registrations(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Import participant identities and hash passwords supplied by the Admin."""
    filename = file.filename or "registrations.xlsx"
    _validate_registration_filename(filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    parsed = parse_registration_file(filename, content)
    if not parsed["rows"] and not parsed.get("row_errors"):
        raise HTTPException(status_code=400, detail="; ".join(parsed["errors"]) or "No registration rows were found.")

    config = get_or_create_event_config(db)
    valid_rows = []
    errors = list(parsed.get("row_errors") or [])

    for row in parsed["rows"]:
        row_messages: list[str] = []
        team = db.query(Team).filter(func.lower(Team.team_name) == row["team_name"].lower()).first()
        leader = _user_by_login(db, row["leader_email"])
        if leader and leader.role != "leader":
            row_messages.append(f"Leader email '{row['leader_email']}' belongs to a non-leader account.")
        if leader and leader.team_id not in (None, team.id if team else None):
            row_messages.append(f"Leader email '{row['leader_email']}' already belongs to another team.")
        if team and team.leader_id and (not leader or team.leader_id != leader.id):
            row_messages.append(f"Team '{row['team_name']}' already has a different leader account.")
        leader_password = row.get("leader_password") or ""
        if not leader and not leader_password:
            row_messages.append("Leader Password is required for a new participant account.")
        elif leader_password:
            password_error = _participant_password_error(leader_password)
            if password_error:
                row_messages.append(f"Leader Password: {password_error}")

        for member in row["members"]:
            member_email = (member.get("email") or "").strip().lower()
            if not member_email:
                continue
            member_user = _user_by_login(db, member_email)
            member_password = member.get("password") or ""
            member_number = member.get("number") or ""
            if not member_user and not member_password:
                row_messages.append(
                    f"Member {member_number} Password is required for a new participant account."
                )
            elif member_password:
                password_error = _participant_password_error(member_password)
                if password_error:
                    row_messages.append(f"Member {member_number} Password: {password_error}")
            if member_user and (not team or member_user.team_id != team.id):
                row_messages.append(f"Member email '{member_email}' belongs to another account or team.")
            member_record = db.query(Member).filter(func.lower(Member.email) == member_email).first()
            if member_record and (not team or member_record.team_id != team.id):
                row_messages.append(f"Member email '{member_email}' is already assigned to another team.")

        if row_messages:
            errors.extend({"row_number": row["row_number"], "message": message} for message in row_messages)
        else:
            valid_rows.append(row)

    teams_created = 0
    teams_updated = 0
    leaders_created = 0
    existing_leaders = 0
    members_imported = 0
    leader_credentials: dict[int, dict[str, str]] = {}
    participant_accounts_created = 0
    invalidated_account_ids: set[int] = set()

    try:
        import_record = RegistrationImport(
            filename=filename,
            status="committed",
            committed_at=datetime.now(timezone.utc),
            source_name=filename,
            source_headers_json=json.dumps(parsed.get("source_headers") or []),
        )
        db.add(import_record)
        db.flush()
        for row in valid_rows:
            team = db.query(Team).filter(func.lower(Team.team_name) == row["team_name"].lower()).first()
            if team:
                teams_updated += 1
            else:
                team = Team(
                    team_name=row["team_name"],
                    coins=config.starting_coins,
                    is_approved=True,
                )
                db.add(team)
                db.flush()
                teams_created += 1
                db.add(WalletTransaction(
                    team_id=team.id,
                    transaction_type="INITIAL_ALLOCATION",
                    amount=config.starting_coins,
                    description="Initial AlumniCoins from registration import",
                ))

            leader_email = row["leader_email"].strip().lower()
            leader_password = row.get("leader_password") or ""
            leader = _user_by_login(db, leader_email)
            if leader:
                existing_leaders += 1
                if leader_password:
                    leader.password_hash = get_password_hash(leader_password)
                    leader.credentials_active = True
                    leader.session_id = None
                    invalidated_account_ids.add(leader.id)
            else:
                leader = User(
                    name=row["leader_name"],
                    email=leader_email,
                    password_hash=get_password_hash(leader_password),
                    role="leader",
                    team_id=team.id,
                    account_source="IMPORTED",
                    credentials_active=True,
                )
                db.add(leader)
                db.flush()
                leaders_created += 1

            leader.name = row["leader_name"]
            leader.role = "leader"
            leader.team_id = team.id
            team.leader_id = leader.id
            team.is_approved = True

            for existing_member in list(team.members):
                db.delete(existing_member)
            for position, member in enumerate(row["members"], start=1):
                member_name = (member.get("name") or "").strip()
                if not member_name:
                    continue
                member_email = (member.get("email") or "").strip().lower() or None
                member_password = member.get("password") or ""
                login_id = member_email if member_email and _is_valid_email(member_email) else _participant_id(db, team.id, position)
                member_user = _user_by_login(db, login_id)
                if not member_user:
                    member_user = User(
                        name=member_name,
                        email=login_id,
                        password_hash=(
                            get_password_hash(member_password)
                            if member_password else _disabled_password_hash()
                        ),
                        role="member",
                        team_id=team.id,
                        account_source="IMPORTED",
                        credentials_active=bool(member_password),
                    )
                    db.add(member_user)
                    db.flush()
                    participant_accounts_created += 1
                else:
                    member_user.name = member_name
                    member_user.role = "member"
                    member_user.team_id = team.id
                    if member_password:
                        member_user.password_hash = get_password_hash(member_password)
                        member_user.credentials_active = True
                        member_user.session_id = None
                        invalidated_account_ids.add(member_user.id)
                db.add(Member(team_id=team.id, member_name=member_name, email=login_id))
                members_imported += 1

            leader_credentials[row["row_number"]] = {
                "email": leader_email,
                "status": "PASSWORD SET" if leader.credentials_active else "PASSWORD NOT SET",
            }
            db.add(RegistrationImportRow(
                import_id=import_record.id,
                row_number=row["row_number"],
                team_name=row["team_name"],
                leader_name=row["leader_name"],
                leader_email=leader_email,
                members_json=json.dumps([
                    {key: value for key, value in member.items() if key != "password"}
                    for member in row["members"]
                ]),
                status="committed",
                warnings_json=json.dumps(row.get("warnings") or []),
                source_values_json=json.dumps(row.get("source_values") or []),
                team_id=team.id,
            ))

        is_csv = filename.lower().endswith(".csv")
        output_bytes = (
            build_registration_credential_csv(content, leader_credentials)
            if is_csv else build_registration_credential_workbook(filename, content, leader_credentials)
        )
        record_event(
            db,
            "registration.import_committed",
            actor=current_user,
            metadata={
                "filename": filename,
                "teams_created": teams_created,
                "teams_updated": teams_updated,
                "leaders_created": leaders_created,
                "rows_failed": len({error["row_number"] for error in errors}),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    output_suffix = ".csv" if is_csv else ".xlsx"
    output_filename = f"bid_to_build_registration_accounts_{datetime.utcnow().year}{output_suffix}"
    download_token = _store_credential_export(output_bytes, output_suffix)
    summary = {
        "teams_processed": len(valid_rows),
        "teams_created": teams_created,
        "teams_updated": teams_updated,
        "leaders_created": leaders_created,
        "existing_leaders": existing_leaders,
        "members_imported": members_imported,
        "participant_accounts_created": participant_accounts_created,
        "rows_failed": len({error["row_number"] for error in errors}),
        "errors": errors,
        "download_token": download_token,
        "download_filename": output_filename,
    }
    if invalidated_account_ids:
        await manager.disconnect_users(invalidated_account_ids)
        await manager.broadcast_event(
            "participant_presence_changed",
            participant_presence_payload(db, connected_team_ids=manager.participant_team_ids()),
        )
    await manager.broadcast_event("team_updated", {
        "action": "registrations_imported",
        "teams_created": teams_created,
        "teams_updated": teams_updated,
        "leaders_created": leaders_created,
        "members_imported": members_imported,
    })
    return summary


@router.post("/admin/registration/credentials/reset")
async def reset_registration_credentials(
    payload: ParticipantCredentialResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    if payload.confirmation != "RESET CREDENTIALS":
        raise HTTPException(status_code=422, detail="Enter RESET CREDENTIALS to confirm participant credential reset.")

    try:
        credential_reset = reset_imported_participant_credentials(db, actor=current_user)
        imported_user_ids = set(credential_reset.pop("user_ids"))
        db.commit()
    except Exception:
        db.rollback()
        raise

    credential_exports_removed = 0
    if _EXPORT_DIRECTORY.exists():
        for export_path in _EXPORT_DIRECTORY.glob("*"):
            try:
                export_path.unlink()
                credential_exports_removed += 1
            except OSError:
                pass

    game = get_or_create_game_config(db)
    sockets_closed = await manager.disconnect_users(imported_user_ids)
    presence = participant_presence_payload(db, connected_team_ids=manager.participant_team_ids())
    await manager.broadcast_event("participant_presence_changed", presence)
    await manager.broadcast_event("team_updated", {
        "action": "registration_credentials_reset",
        "participant_accounts": credential_reset["participant_accounts"],
        "teams_removed": credential_reset["deleted"]["teams"],
    })
    return {
        "status": "credentials_reset",
        "reset": {
            "participant_accounts": credential_reset["participant_accounts"],
            "sessions_invalidated": credential_reset["sessions_invalidated"],
            "presence_connections_closed": sockets_closed,
        },
        "deleted": {
            **credential_reset["deleted"],
            "credential_exports": credential_exports_removed,
        },
        "preserved": {
            "system_accounts": db.query(User).filter(User.is_system_account.is_(True)).count(),
            "system_teams": db.query(Team).filter(Team.is_system_team.is_(True)).count(),
            "admin_accounts": db.query(User).filter(User.role == "admin").count(),
            "display_accounts": db.query(User).filter(User.role == "display").count(),
        },
        "event_state": game.state,
        "event_lifecycle_reset": False,
    }


@router.get("/admin/registration/participant-accounts")
def list_imported_participant_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    del current_user
    accounts = (
        db.query(User)
        .filter(
            User.account_source == "IMPORTED",
            User.role.in_(("leader", "member")),
            User.is_system_account.is_(False),
        )
        .order_by(func.lower(User.email).asc())
        .all()
    )
    rows = [_participant_account_payload(db, account) for account in accounts]
    rows.sort(key=lambda row: (row["team_name"].lower(), row["role"] != "leader", row["login_id"].lower()))
    return {"accounts": rows, "count": len(rows)}


@router.put("/admin/registration/participant-accounts/{user_id}/password")
async def set_imported_participant_password(
    user_id: int,
    payload: ParticipantPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    _validate_participant_password(payload.new_password, payload.confirm_password)
    account = db.query(User).filter(
        User.id == user_id,
        User.account_source == "IMPORTED",
        User.role.in_(("leader", "member")),
        User.is_system_account.is_(False),
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Imported participant account not found.")
    account.password_hash = get_password_hash(payload.new_password)
    account.credentials_active = True
    account.session_id = None
    record_event(
        db,
        "registration.participant_password_set",
        actor=current_user,
        entity_type="user",
        entity_id=account.id,
        metadata={"login_id": account.email, "role": account.role},
    )
    db.commit()
    db.refresh(account)
    await manager.disconnect_users({account.id})
    await manager.broadcast_event(
        "participant_presence_changed",
        participant_presence_payload(db, connected_team_ids=manager.participant_team_ids()),
    )
    return {"status": "password_set", "account": _participant_account_payload(db, account)}


@router.get("/admin/registration/import/download/{download_token}")
def download_registration_credentials(
    download_token: str,
    current_user: User = Depends(get_current_active_admin),
):
    if not download_token or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in download_token):
        raise HTTPException(status_code=404, detail="Credential export expired or was already downloaded.")
    export_path = next((path for path in (_EXPORT_DIRECTORY / f"{download_token}.csv", _EXPORT_DIRECTORY / f"{download_token}.xlsx") if path.exists()), None)
    if not export_path or time.time() - export_path.stat().st_mtime > _EXPORT_TTL_SECONDS:
        if export_path:
            export_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="Credential export expired or was already downloaded.")
    content = export_path.read_bytes()
    suffix = export_path.suffix.lower()
    export_path.unlink(missing_ok=True)
    filename = f"bid_to_build_registration_accounts_{datetime.utcnow().year}{suffix}"
    return StreamingResponse(
        BytesIO(content),
        media_type="text/csv; charset=utf-8" if suffix == ".csv" else XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _assignment_problem_values(problem: ProblemStatement | None) -> list[str]:
    if not problem:
        return ["", "", ""]
    return [problem.ps_number, problem.title, problem.description or ""]


def _assigned_problem_label(problem: ProblemStatement | None) -> str:
    return f"{problem.ps_number} - {problem.title}" if problem else ""


def _assignment_export_data(db: Session) -> tuple[list[str], list[list[str]], str]:
    latest_import = (
        db.query(RegistrationImport)
        .filter(RegistrationImport.status == "committed")
        .order_by(RegistrationImport.committed_at.desc(), RegistrationImport.id.desc())
        .first()
    )
    source_headers = json.loads(latest_import.source_headers_json or "[]") if latest_import else []
    stored_rows = (
        db.query(RegistrationImportRow)
        .filter(RegistrationImportRow.import_id == latest_import.id)
        .order_by(RegistrationImportRow.row_number.asc())
        .all()
        if latest_import else []
    )

    if source_headers and stored_rows:
        headers = [str(header) for header in source_headers]
        source_rows = []
        for stored in stored_rows:
            values = [str(value or "") for value in json.loads(stored.source_values_json or "[]")]
            values.extend([""] * (len(headers) - len(values)))
            team = db.query(Team).filter(Team.id == stored.team_id).first() if stored.team_id else None
            if not team and stored.team_id is None and stored.leader_email:
                leader = db.query(User).filter(func.lower(User.email) == stored.leader_email.lower()).first()
                if leader:
                    team = db.query(Team).filter(or_(Team.id == leader.team_id, Team.leader_id == leader.id)).first()
            if not team and stored.team_id is None:
                team = db.query(Team).filter(func.lower(Team.team_name) == stored.team_name.lower()).first()
            source_rows.append((values[:len(headers)], team, stored.leader_email))
        suffix = ".xlsx" if latest_import.filename.lower().endswith((".xlsx", ".xlsm")) else ".csv"
    else:
        teams = db.query(Team).filter(Team.is_system_team.is_(False)).order_by(Team.team_name.asc()).all()
        max_members = max((len(team.members) for team in teams), default=0)
        headers = ["Team Name", "Leader Name", "Leader Email"]
        for position in range(1, max_members + 1):
            headers.extend([f"Member {position} Name", f"Member {position} Email"])
        source_rows = []
        for team in teams:
            leader = db.query(User).filter(User.id == team.leader_id).first()
            values = [team.team_name, leader.name if leader else "", leader.email if leader else ""]
            for member in team.members:
                values.extend([member.member_name, member.email or ""])
            values.extend([""] * (len(headers) - len(values)))
            source_rows.append((values, team, leader.email if leader else ""))
        suffix = ".csv"

    normalized_headers = ["".join(character for character in header.lower() if character.isalnum()) for header in headers]

    def ensure_column(label: str) -> int:
        normalized = "".join(character for character in label.lower() if character.isalnum())
        if normalized in normalized_headers:
            return normalized_headers.index(normalized)
        headers.append(label)
        normalized_headers.append(normalized)
        return len(headers) - 1

    login_index = ensure_column("Leader Login Email")
    credential_status_index = ensure_column("Credential Status")
    assignment_indexes = [ensure_column(label) for label in ASSIGNMENT_HEADERS]
    password_indexes = [
        index for index, normalized in enumerate(normalized_headers)
        if normalized in {"leaderpassword", "leaderloginpassword", "temporarypassword"}
        or normalized.endswith("password")
    ]

    output_rows: list[list[str]] = []
    for source_values, team, leader_email in source_rows:
        values = [*source_values, *([""] * (len(headers) - len(source_values)))]
        values[login_index] = leader_email
        leader_account = _user_by_login(db, leader_email) if leader_email else None
        values[credential_status_index] = (
            "PASSWORD SET" if leader_account and leader_account.credentials_active else "PASSWORD NOT SET"
        )
        for index in password_indexes:
            values[index] = "NOT EXPORTED"
        round1 = db.query(ProblemStatement).filter(ProblemStatement.id == team.round1_problem_id).first() if team and team.round1_problem_id else None
        wildcard = db.query(ProblemStatement).filter(ProblemStatement.id == team.wildcard_problem_id).first() if team and team.wildcard_problem_id else None
        submission = db.query(Submission).filter(Submission.team_id == team.id).first() if team else None
        final = wildcard or round1
        assignment_values = [
            _assigned_problem_label(round1),
            _assigned_problem_label(wildcard),
            submission.repository_url if submission else "",
            *_assignment_problem_values(round1),
            (team.round1_assignment_type or "BID_WINNER") if round1 and team else "",
            *_assignment_problem_values(wildcard),
            *_assignment_problem_values(final),
        ]
        for index, value in zip(assignment_indexes, assignment_values):
            values[index] = value
        output_rows.append(values)
    return headers, output_rows, suffix


def _assignment_workbook_response(db: Session, filename: str) -> StreamingResponse:
    headers, rows, _suffix = _assignment_export_data(db)
    if not rows:
        raise HTTPException(status_code=409, detail="No imported participant registration data is available to export.")
    return StreamingResponse(
        BytesIO(build_registration_assignment_workbook(headers, rows)),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/rounds/round-1/assignments/export")
def download_round_one_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    del current_user
    return _assignment_workbook_response(db, "bid_to_build_round_1_assignments.xlsx")


@router.get("/admin/rounds/wildcard/assignments/export")
def download_wildcard_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    del current_user
    return _assignment_workbook_response(db, "bid_to_build_wildcard_assignments.xlsx")


@router.get("/admin/registration/assignments")
def download_registration_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    headers, rows, suffix = _assignment_export_data(db)
    if not rows:
        raise HTTPException(status_code=409, detail="No imported participant registration data is available to export.")
    content = (
        build_registration_assignment_workbook(headers, rows)
        if suffix == ".xlsx" else build_registration_assignment_csv(headers, rows)
    )
    filename = f"bid_to_build_updated_registration_{datetime.utcnow().year}{suffix}"
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE if suffix == ".xlsx" else "text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/submissions/export/final")
def download_final_event_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    del current_user
    event_config = get_or_create_event_config(db)
    game_config = get_or_create_game_config(db)
    if event_config.submissions_open or game_config.state not in {"JUDGING_WAIT", "RESULTS"}:
        raise HTTPException(status_code=409, detail="Final export is available after submissions are closed.")
    headers, rows, suffix = _assignment_export_data(db)
    if not rows:
        raise HTTPException(status_code=409, detail="No imported participant registration data is available to export.")
    content = (
        build_registration_assignment_workbook(headers, rows)
        if suffix == ".xlsx" else build_registration_assignment_csv(headers, rows)
    )
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE if suffix == ".xlsx" else "text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="Bid_to_Build_Final_Results{suffix}"'},
    )

@router.post("/admin/registration/import/preview", response_model=ImportPreviewResponse, deprecated=True)
async def preview_registration_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    _validate_registration_filename(file.filename or "")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    parsed = parse_registration_file(file.filename or "upload", content)
    if parsed["errors"] and not parsed["rows"]:
        raise HTTPException(status_code=400, detail="; ".join(parsed["errors"]))

    # cross-check against existing DB to flag duplicates (idempotency)
    existing_teams = {t.team_name.lower(): t for t in db.query(Team).all()}
    existing_emails = {u.email.lower(): u for u in db.query(User).all()}

    all_warnings: List[str] = list(parsed["warnings"])
    preview_rows: List[ImportRowPreview] = []
    for row in parsed["rows"]:
        status = "new"
        row_warnings = list(row.get("warnings") or [])
        if row["team_name"].lower() in existing_teams:
            status = "update"
            row_warnings.append(f"Team '{row['team_name']}' already exists — existing record will be updated.")
        if row["leader_email"].lower() in existing_emails:
            status = "update" if status == "new" else status
            row_warnings.append(f"Leader email '{row['leader_email']}' already has an account — password will not be reset.")
        preview_rows.append(ImportRowPreview(
            row_number=row["row_number"],
            team_name=row["team_name"],
            leader_name=row["leader_name"],
            leader_email=row["leader_email"],
            members=row["members"],
            status=status,
            warnings=row_warnings,
        ))
        all_warnings.extend(row_warnings)

    # Persist a pending import record so "confirm" acts on a stable snapshot
    import_record = RegistrationImport(
        filename=file.filename or "registration.csv",
        status="pending",
        source_name=file.filename or "registration.csv",
        source_headers_json=json.dumps(parsed.get("source_headers") or []),
    )
    db.add(import_record)
    db.flush()

    for row in parsed["rows"]:
        row_record = RegistrationImportRow(
            import_id=import_record.id,
            row_number=row["row_number"],
            team_name=row["team_name"],
            leader_name=row["leader_name"],
            leader_email=row["leader_email"],
            members_json=json.dumps(row["members"]),
            status="new",
            warnings_json=json.dumps(row.get("warnings") or []),
            source_values_json=json.dumps(row.get("source_values") or []),
        )
        db.add(row_record)
    db.commit()

    return ImportPreviewResponse(
        import_id=import_record.id,
        filename=import_record.filename,
        teams_detected=len(preview_rows),
        members_detected=sum(len(r.members) for r in preview_rows),
        leaders_detected=len([r for r in preview_rows if r.leader_email]),
        warnings=all_warnings,
        errors=parsed["errors"],
        rows=preview_rows,
    )

@router.post("/admin/registration/import/confirm", response_model=ImportConfirmResponse, deprecated=True)
async def confirm_registration_import(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    import_id = payload.get("import_id")
    if not import_id:
        raise HTTPException(status_code=400, detail="import_id is required")

    import_record = db.query(RegistrationImport).filter(RegistrationImport.id == import_id).first()
    if not import_record:
        raise HTTPException(status_code=404, detail="Import not found")
    if import_record.status == "committed":
        raise HTTPException(status_code=400, detail="This import was already committed. Upload the file again for a fresh import.")

    config = get_or_create_event_config(db)
    starting_coins = config.starting_coins

    teams_created = 0
    teams_updated = 0
    accounts_created = 0
    credentials: List[CredentialRow] = []

    rows = db.query(RegistrationImportRow).filter(RegistrationImportRow.import_id == import_record.id).order_by(RegistrationImportRow.row_number).all()

    for row in rows:
        members = json.loads(row.members_json or "[]")

        # --- team: find by name or create ---
        team = db.query(Team).filter(Team.team_name == row.team_name).first()
        if team:
            teams_updated += 1
        else:
            team = Team(team_name=row.team_name, is_approved=True)
            team.coins = starting_coins
            db.add(team)
            db.flush()  # get team.id
            teams_created += 1
            db.add(WalletTransaction(team_id=team.id, transaction_type="INITIAL_ALLOCATION", amount=starting_coins, description="Initial AlumniCoins from EventConfig"))

        # --- leader user: find by email or create ---
        leader_email = row.leader_email.strip().lower()
        leader = _user_by_login(db, leader_email)
        if leader and leader.team_id not in (None, team.id):
            raise HTTPException(status_code=409, detail=f"ACCOUNT ALREADY EXISTS: {leader_email}")
        if not leader:
            leader = User(
                name=row.leader_name,
                email=leader_email,
                password_hash=_disabled_password_hash(),
                role="leader",
                team_id=team.id,
                account_source="IMPORTED",
                credentials_active=False,
            )
            db.add(leader)
            db.flush()
            accounts_created += 1

        team.leader_id = leader.id
        leader.team_id = team.id
        leader.name = row.leader_name
        leader.role = "leader"

        # --- members (replace member list; preserve member emails) ---
        for existing in team.members:
            db.delete(existing)
        for position, member in enumerate(members, start=1):
            member_name = (member.get("name") or "").strip()
            member_email = (member.get("email") or "").strip().lower()
            login_id = member_email if member_email and _is_valid_email(member_email) else _participant_id(db, team.id, position)
            member_user = _user_by_login(db, login_id)
            if member_user and member_user.team_id not in (None, team.id):
                raise HTTPException(status_code=409, detail=f"ACCOUNT ALREADY EXISTS: {login_id}")
            if not member_user:
                member_user = User(
                    name=member_name,
                    email=login_id,
                    password_hash=_disabled_password_hash(),
                    role="member",
                    team_id=team.id,
                    account_source="IMPORTED",
                    credentials_active=False,
                )
                db.add(member_user)
                db.flush()
                accounts_created += 1
            else:
                member_user.name = member_name
                member_user.role = "member"
                member_user.team_id = team.id
            db.add(Member(team_id=team.id, member_name=member_name, email=login_id))

        team.is_approved = True
        row.team_id = team.id

    import_record.status = "committed"
    import_record.committed_at = datetime.now(timezone.utc)
    record_event(
        db,
        "registration.legacy_import_committed",
        actor=current_user,
        entity_type="registration_import",
        entity_id=import_record.id,
        metadata={"teams_created": teams_created, "teams_updated": teams_updated, "accounts_created": accounts_created},
    )
    db.commit()

    await manager.broadcast_event("team_updated", {
        "action": "registrations_imported",
        "teams_created": teams_created,
        "teams_updated": teams_updated,
        "accounts_created": accounts_created,
    })

    return ImportConfirmResponse(
        import_id=import_record.id,
        teams_created=teams_created,
        teams_updated=teams_updated,
        accounts_created=accounts_created,
        credentials=credentials,
    )

@router.get("/admin/registration/imports")
def list_registration_imports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    imports = db.query(RegistrationImport).order_by(RegistrationImport.created_at.desc()).all()
    return [
        {
            "import_id": imp.id,
            "filename": imp.filename,
            "status": imp.status,
            "created_at": imp.created_at,
            "rows": len(imp.rows),
        }
        for imp in imports
    ]

@router.get("/admin/registration/import/{import_id}/credentials.csv")
def export_credentials_csv(
    import_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Return imported account identifiers and status without password material."""
    import_record = db.query(RegistrationImport).filter(RegistrationImport.id == import_id).first()
    if not import_record:
        raise HTTPException(status_code=404, detail="Import not found")
    rows = db.query(RegistrationImportRow).filter(RegistrationImportRow.import_id == import_id).all()
    lines = ["Team Name,Participant/Leader Name,Email,Username,Role,Credential Status"]
    for row in rows:
        leader = _user_by_login(db, row.leader_email)
        leader_status = "PASSWORD SET" if leader and leader.credentials_active else "PASSWORD NOT SET"
        lines.append(f"{row.team_name},{row.leader_name},{row.leader_email},{row.leader_email},leader,{leader_status}")
        for member in json.loads(row.members_json or "[]"):
            if member.get("email"):
                account = _user_by_login(db, member["email"])
                status_value = "PASSWORD SET" if account and account.credentials_active else "PASSWORD NOT SET"
                lines.append(f"{row.team_name},{member.get('name', '')},{member['email']},{member['email']},member,{status_value}")
    return JSONResponse(
        content={"content": "\n".join(lines)},
    )
