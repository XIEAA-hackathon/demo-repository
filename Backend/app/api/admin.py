from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.models.models import (
    User, Team, Member, EventConfig, GameConfig,
    RegistrationImport, RegistrationImportRow, WalletTransaction, ProblemStatement,
)
from app.schemas.schemas import (
    EventConfigUpdate, EventConfigResponse,
    ImportPreviewResponse, ImportConfirmResponse, ImportRowPreview,
    CredentialRow, EventStateUpdate, EVENT_STATES,
)
from app.api.auth import get_current_active_admin
from app.api.websockets import manager
from app.services.event_service import (
    event_snapshot,
    get_or_create_event_config,
    get_or_create_game_config,
    transition_event_state,
)
from app.services.registration_import import parse_registration_file, generate_credentials, _is_valid_email
from app.core.security import get_password_hash
import json

router = APIRouter()

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
    if "royalty_coins_per_point" in data and data["royalty_coins_per_point"] < 0:
        raise HTTPException(status_code=400, detail="royalty_coins_per_point must be >= 0")
    if "royalty_max_points" in data and data["royalty_max_points"] < 0:
        raise HTTPException(status_code=400, detail="royalty_max_points must be >= 0")

    for field, value in data.items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    await manager.broadcast_event("config_updated", {"config": EventConfigResponse.model_validate(config).model_dump(mode="json")})
    return config

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

# ---------------------------------------------------------------- Registration Import

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

@router.post("/admin/registration/import/preview", response_model=ImportPreviewResponse)
async def preview_registration_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
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
        leader = db.query(User).filter(User.email == row.leader_email).first()
        row_as_dict = {
            "team_name": row.team_name,
            "leader_name": row.leader_name,
            "leader_email": row.leader_email,
        }
        if not leader:
            created_password = generate_credentials([row_as_dict])[0]["temporary_password"]
            leader = User(
                name=row.leader_name,
                email=row.leader_email,
                password_hash=get_password_hash(created_password),
                role="leader",
                team_id=team.id,
            )
            db.add(leader)
            db.flush()
            accounts_created += 1
            credentials.append(CredentialRow(
                team_name=row.team_name,
                name=row.leader_name,
                email=row.leader_email,
                username=row.leader_email,
                temporary_password=created_password,
                role="leader",
            ))

        team.leader_id = leader.id
        leader.team_id = team.id
        leader.name = row.leader_name

        # --- members (replace member list; preserve member emails) ---
        for existing in team.members:
            db.delete(existing)
        for member in members:
            db.add(Member(team_id=team.id, member_name=member.get("name", ""), email=member.get("email") or None))
            member_email = member.get("email")
            if member_email and _is_valid_email(member_email):
                member_user = db.query(User).filter(User.email == member_email).first()
                if not member_user:
                    created_password = generate_credentials([{
                        "team_name": row.team_name,
                        "leader_name": member.get("name", ""),
                        "leader_email": member_email,
                    }])[0]["temporary_password"]
                    member_user = User(
                        name=member.get("name", ""),
                        email=member_email,
                        password_hash=get_password_hash(created_password),
                        role="member",
                        team_id=team.id,
                    )
                    db.add(member_user)
                    accounts_created += 1
                    credentials.append(CredentialRow(
                        team_name=row.team_name,
                        name=member.get("name", ""),
                        email=member_email,
                        username=member_email,
                        temporary_password=created_password,
                        role="member",
                    ))
                else:
                    member_user.team_id = team.id

        team.is_approved = True

    import_record.status = "committed"
    import_record.committed_at = datetime.utcnow()
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
