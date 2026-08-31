"""Reset every existing account credential from one authoritative registration file.

The command is dry-run by default. ``--apply`` first creates a PostgreSQL custom
format backup, then updates only authentication columns on existing ``users``
rows. It never creates/deletes users, teams, or event data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash, is_bcrypt_password_hash, is_sha256_password_hash
from app.models.models import Team, User
from app.services.registration_import import parse_registration_file


CONFIRMATION = "RESET-ALL-CREDENTIALS"


class CredentialResetError(RuntimeError):
    pass


def _normalized_email(value: str) -> str:
    return value.strip().lower()


def registration_passwords(path: Path) -> dict[str, str]:
    parsed = parse_registration_file(path.name, path.read_bytes())
    if parsed["errors"]:
        raise CredentialResetError(
            f"Registration file failed validation with {len(parsed['errors'])} error(s)."
        )

    credentials: dict[str, str] = {}
    for row in parsed["rows"]:
        if row.get("leader_password_hash"):
            raise CredentialResetError(
                "Credential reset requires plaintext Leader Password values; pre-hashed input is not accepted."
            )
        leader_password = row.get("leader_password") or ""
        if not leader_password:
            raise CredentialResetError(
                f"Registration row {row['row_number']} has no plaintext leader password."
            )
        credentials[_normalized_email(row["leader_email"])] = leader_password

        for member in row["members"]:
            email = _normalized_email(member.get("email") or "")
            if not email:
                continue
            if member.get("password_hash"):
                raise CredentialResetError(
                    "Credential reset requires plaintext Member Password values; pre-hashed input is not accepted."
                )
            password = member.get("password") or ""
            if not password:
                raise CredentialResetError(
                    f"Registration row {row['row_number']} has no plaintext password for member {member['number']}."
                )
            if email in credentials:
                raise CredentialResetError("A login email appears more than once in the registration credentials.")
            credentials[email] = password
    return credentials


def configured_system_passwords() -> dict[str, str]:
    candidates = (
        (settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD),
        (settings.DEMO_ADMIN_EMAIL, settings.DEMO_ADMIN_PASSWORD),
        (settings.DEMO_LEADER_EMAIL, settings.DEMO_LEADER_PASSWORD),
        (settings.LEADERBOARD_DISPLAY_EMAIL, settings.LEADERBOARD_DISPLAY_PASSWORD),
    )
    return {
        _normalized_email(email): password
        for email, password in candidates
        if email and password
    }


def plan_reset(db: Session, registration_file: Path) -> tuple[list[User], dict[str, str], dict]:
    registration = registration_passwords(registration_file)
    users = db.query(User).order_by(User.id).all()
    users_by_email = {_normalized_email(user.email): user for user in users}
    system = configured_system_passwords()
    credentials = {**system, **registration}

    uncovered = [user.id for user in users if _normalized_email(user.email) not in credentials]
    inactive = [user.id for user in users if not user.credentials_active]
    unknown_registration_rows = [
        email for email in registration if email not in users_by_email
    ]
    if uncovered or unknown_registration_rows:
        raise CredentialResetError(
            "Credential coverage is incomplete: "
            f"{len(uncovered)} existing account(s) lack authoritative passwords and "
            f"{len(unknown_registration_rows)} registration account(s) do not exist in users."
        )
    if inactive:
        raise CredentialResetError(
            f"Expected every account to be active, but found {len(inactive)} inactive account(s); "
            "credentials_active is never changed automatically."
        )

    # Verify participant/team identity links before touching credentials.
    broken_relationships = 0
    teams = {team.id: team for team in db.query(Team).all()}
    for user in users:
        if user.role not in {"leader", "member"}:
            continue
        team = teams.get(user.team_id)
        if team is None or (user.role == "leader" and team.leader_id != user.id):
            broken_relationships += 1
    if broken_relationships:
        raise CredentialResetError(
            f"Found {broken_relationships} broken participant/team relationship(s); reset aborted."
        )

    summary = {
        "expected_accounts": len(users),
        "active_accounts": len(users) - len(inactive),
        "registration_credentials": len(registration),
        "configured_accounts_matched": sum(
            email in users_by_email and email not in registration for email in system
        ),
        "accounts_covered": len(users),
        "broken_relationships": 0,
    }
    return users, credentials, summary


def create_postgresql_backup(output: Path) -> None:
    if output.exists():
        raise CredentialResetError(f"Backup destination already exists: {output}")
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise CredentialResetError("pg_dump is required but was not found in PATH.")

    output.parent.mkdir(parents=True, exist_ok=True)
    url = make_url(settings.DATABASE_URL)
    command = [pg_dump, "--format=custom", "--file", str(output)]
    if url.host:
        command.extend(["--host", url.host])
    if url.port:
        command.extend(["--port", str(url.port)])
    if url.username:
        command.extend(["--username", url.username])
    command.append(url.database or "")
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    subprocess.run(command, env=environment, check=True)
    output.chmod(0o600)


def apply_reset(db: Session, users: list[User], credentials: dict[str, str]) -> dict:
    relationship_snapshot = {
        "users": {
            (
                user.id,
                user.team_id,
                user.role,
                user.account_source,
                user.credentials_active,
                user.is_system_account,
            )
            for user in users
        },
        "teams": {
            (team.id, team.leader_id, team.is_system_team)
            for team in db.query(Team).all()
        },
    }
    try:
        for user in users:
            user.password_hash = get_password_hash(credentials[_normalized_email(user.email)])
            user.session_id = None
            user.session_created_at = None
            user.session_last_seen_at = None
        db.flush()

        total = db.query(User).count()
        sha256_count = sum(
            is_sha256_password_hash(value)
            for (value,) in db.query(User.password_hash).all()
        )
        bcrypt_count = sum(
            is_bcrypt_password_hash(value)
            for (value,) in db.query(User.password_hash).all()
        )
        active_accounts = db.query(User).filter(User.credentials_active.is_(True)).count()
        active_sessions = db.query(User).filter(User.session_id.is_not(None)).count()
        relationships_preserved = relationship_snapshot == {
            "users": {
                (
                    user.id,
                    user.team_id,
                    user.role,
                    user.account_source,
                    user.credentials_active,
                    user.is_system_account,
                )
                for user in db.query(User).all()
            },
            "teams": {
                (team.id, team.leader_id, team.is_system_team)
                for team in db.query(Team).all()
            },
        }
        if (
            active_accounts != total
            or sha256_count != total
            or bcrypt_count
            or active_sessions
            or not relationships_preserved
        ):
            raise CredentialResetError("Post-reset verification failed; transaction was rolled back.")
        db.commit()
        return {
            "accounts_reset": total,
            "active_accounts": active_accounts,
            "sha256_accounts": sha256_count,
            "bcrypt_hashes": bcrypt_count,
            "active_sessions": active_sessions,
            "relationships_preserved": relationships_preserved,
        }
    except Exception:
        db.rollback()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registration-file", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--backup-output", type=Path)
    args = parser.parse_args()

    with SessionLocal() as db:
        users, credentials, summary = plan_reset(db, args.registration_file)
        if not args.apply:
            print(json.dumps({"mode": "dry-run", **summary}))
            return
        if args.confirm != CONFIRMATION:
            raise CredentialResetError(f"--confirm {CONFIRMATION} is required with --apply.")
        if args.backup_output is None:
            raise CredentialResetError("--backup-output is required with --apply.")
        create_postgresql_backup(args.backup_output)
        result = apply_reset(db, users, credentials)
        print(json.dumps({"mode": "applied", "backup": str(args.backup_output), **summary, **result}))


if __name__ == "__main__":
    main()
