from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.models import (
    User, Team, Member, EventConfig, GameConfig,
    RegistrationImport, RegistrationImportRow, WalletTransaction, ProblemStatement,
)
from app.schemas.schemas import (
    EventConfigUpdate, EventConfigResponse,
    ImportPreviewResponse, ImportConfirmResponse, ImportRowPreview,
    CredentialRow, ManualTeamCredentialsRequest, ManualTeamCredentialsResponse,
    EventStateUpdate, EVENT_STATES,
)
from app.api.auth import get_current_active_admin
from app.api.websockets import manager
from app.services.event_service import (
    event_snapshot,
    get_or_create_event_config,
    get_or_create_game_config,
    transition_event_state,
)
from app.services.registration_import import (
    parse_registration_file, generate_credentials, _default_password, _is_valid_email,
)
from app.core.security import get_password_hash
import json

router = APIRouter()


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
    if "starting_coins" in data and data["starting_coins"] < 0:
        raise HTTPException(status_code=400, detail="starting_coins must be >= 0")
    for field in ["round1_preview_seconds", "round1_bid_seconds", "wildcard_preview_seconds", "wildcard_bid_seconds"]:
        if field in data and data[field] < 0:
            raise HTTPException(status_code=400, detail=f"{field} must be >= 0")
    if "round1_winner_count" in data and data["round1_winner_count"] <= 0:
        raise HTTPException(status_code=400, detail="round1_winner_count must be > 0")
    if "round1_minimum_bid" in data and data["round1_minimum_bid"] < 0:
        raise HTTPException(status_code=400, detail="round1_minimum_bid must be >= 0")
    if "round1_bid_increment" in data and data["round1_bid_increment"] <= 0:
        raise HTTPException(status_code=400, detail="round1_bid_increment must be > 0")
    if "wildcard_slots" in data and data["wildcard_slots"] < 0:
        raise HTTPException(status_code=400, detail="wildcard_slots must be >= 0")
    if "wildcard_problem_count" in data and data["wildcard_problem_count"] < 0:
        raise HTTPException(status_code=400, detail="wildcard_problem_count must be >= 0")
    if "coding_duration_seconds" in data and data["coding_duration_seconds"] < 0:
        raise HTTPException(status_code=400, detail="coding_duration_seconds must be >= 0")
    if "bid_cooldown_seconds" in data and data["bid_cooldown_seconds"] < 0:
        raise HTTPException(status_code=400, detail="bid_cooldown_seconds must be >= 0")
    if "royalty_coins_per_point" in data and data["royalty_coins_per_point"] < 0:
        raise HTTPException(status_code=400, detail="royalty_coins_per_point must be >= 0")
    if "royalty_max_points" in data and data["royalty_max_points"] < 0:
        raise HTTPException(status_code=400, detail="royalty_max_points must be >= 0")

    for field, value in data.items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    await manager.broadcast_event("config_updated", {"config": EventConfigResponse.model_validate(config).model_dump(mode="json")})
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return config

@router.put("/admin/cooldown")
async def set_bid_cooldown(seconds: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if seconds < 0:
        raise HTTPException(status_code=400, detail="Cooldown seconds must be >= 0")
    config = get_or_create_event_config(db)
    config.bid_cooldown_seconds = seconds
    db.commit()
    db.refresh(config)
    await manager.broadcast_event("config_updated", {"config": EventConfigResponse.model_validate(config).model_dump(mode="json")})
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return {"message": f"Bid cooldown updated to {seconds} seconds", "bid_cooldown_seconds": seconds}

@router.post("/admin/cooldown/add")
async def add_bid_cooldown(seconds: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="Seconds to add must be > 0")
    config = get_or_create_event_config(db)
    config.bid_cooldown_seconds = (config.bid_cooldown_seconds or 0) + seconds
    db.commit()
    db.refresh(config)
    await manager.broadcast_event("config_updated", {"config": EventConfigResponse.model_validate(config).model_dump(mode="json")})
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return {"message": f"Added {seconds} second(s) to bid cooldown. New cooldown: {config.bid_cooldown_seconds}s", "bid_cooldown_seconds": config.bid_cooldown_seconds}

@router.post("/admin/cooldown/reduce")
async def reduce_bid_cooldown(seconds: int, db: Session = Depends(get_db), current_user = Depends(get_current_active_admin)):
    if seconds <= 0:
        raise HTTPException(status_code=400, detail="Seconds to reduce must be > 0")
    config = get_or_create_event_config(db)
    current_val = config.bid_cooldown_seconds or 0
    config.bid_cooldown_seconds = max(0, current_val - seconds)
    db.commit()
    db.refresh(config)
    await manager.broadcast_event("config_updated", {"config": EventConfigResponse.model_validate(config).model_dump(mode="json")})
    await manager.broadcast_event("event_state_changed", event_snapshot(db))
    return {"message": f"Reduced bid cooldown by {seconds} second(s). New cooldown: {config.bid_cooldown_seconds}s", "bid_cooldown_seconds": config.bid_cooldown_seconds}

# ---------------------------------------------------------------- Event State

async def _apply_event_state(payload: EventStateUpdate, db: Session):
    config = transition_event_state(db, payload.state)
    snapshot = event_snapshot(db)
    await manager.broadcast_event("event_state_changed", snapshot)
    return snapshot

@router.put("/admin/event/state")
async def set_event_state(
    payload: EventStateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    return await _apply_event_state(payload, db)

@router.post("/admin/state")
async def set_event_state_legacy(
    payload: EventStateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Backward-compatible alias. New clients use PUT /admin/event/state."""
    result = await _apply_event_state(payload, db)
    return {"state": result["event_state"], **result}

@router.get("/admin/state")
def get_event_state_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    snapshot = event_snapshot(db)
    return {"state": snapshot["event_state"], **snapshot, "allowed_states": EVENT_STATES}

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
def reset_participant_password(
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
    db.commit()
    supplied_email = account.email if "@" in account.email else ""
    return _credential(account, team, password, supplied_email)


# ---------------------------------------------------------------- Registration Import

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

@router.post("/admin/registration/import/preview", response_model=ImportPreviewResponse)
async def preview_registration_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    if file.filename:
        ext = file.filename.lower()
        if not (ext.endswith(".csv") or ext.endswith(".xlsx") or ext.endswith(".xls")):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .csv, .xlsx, and .xls files are allowed.")

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

@router.post("/admin/registration/import/confirm", response_model=ImportConfirmResponse)
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
        row_as_dict = {
            "team_name": row.team_name,
            "leader_name": row.leader_name,
            "leader_email": row.leader_email,
        }
        if not leader:
            created_password = generate_credentials([row_as_dict])[0]["temporary_password"]
            leader = User(
                name=row.leader_name,
                email=leader_email,
                password_hash=get_password_hash(created_password),
                role="leader",
                team_id=team.id,
            )
            db.add(leader)
            db.flush()
            accounts_created += 1
            credentials.append(_credential(leader, team, created_password, leader_email))

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
                created_password = _default_password()
                member_user = User(
                    name=member_name,
                    email=login_id,
                    password_hash=get_password_hash(created_password),
                    role="member",
                    team_id=team.id,
                )
                db.add(member_user)
                db.flush()
                accounts_created += 1
                credentials.append(_credential(member_user, team, created_password, member_email))
            else:
                member_user.name = member_name
                member_user.role = "member"
                member_user.team_id = team.id
            db.add(Member(team_id=team.id, member_name=member_name, email=login_id))

        team.is_approved = True

    import_record.status = "committed"
    import_record.committed_at = datetime.now(timezone.utc)
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
    """NOTE: temporary passwords are only shown once at confirm time and are not
    stored. This endpoint returns the account list without passwords for re-checks."""
    import_record = db.query(RegistrationImport).filter(RegistrationImport.id == import_id).first()
    if not import_record:
        raise HTTPException(status_code=404, detail="Import not found")
    rows = db.query(RegistrationImportRow).filter(RegistrationImportRow.import_id == import_id).all()
    lines = ["Team Name,Participant/Leader Name,Email,Username,Role"]
    for row in rows:
        lines.append(f"{row.team_name},{row.leader_name},{row.leader_email},{row.leader_email},leader")
        for member in json.loads(row.members_json or "[]"):
            if member.get("email"):
                lines.append(f"{row.team_name},{member.get('name', '')},{member['email']},{member['email']},member")
    return JSONResponse(
        content={"content": "\n".join(lines)},
    )
