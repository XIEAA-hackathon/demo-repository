import pytest

from app.core.security import verify_password
from app.models.models import Team, User
from scripts.reset_credentials_sha256 import CredentialResetError, apply_reset, plan_reset


def _registration_file(tmp_path):
    path = tmp_path / "authoritative.csv"
    path.write_text(
        "Team Name,Leader Name,Leader Email,Leader Password\n"
        "Reset Team,Reset Leader,reset.leader@example.com,Fresh@123\n",
        encoding="utf-8",
    )
    return path


def _legacy_linked_user(db):
    user = User(
        name="Reset Leader",
        email="reset.leader@example.com",
        password_hash="$2b$12$.....................................................",
        role="leader",
        account_source="IMPORTED",
        credentials_active=True,
        session_id="stale-session",
    )
    db.add(user)
    db.flush()
    team = Team(team_name="Reset Team", leader_id=user.id, is_approved=True)
    db.add(team)
    db.flush()
    user.team_id = team.id
    db.commit()
    return user.id, team.id


def test_reset_overwrites_hash_and_sessions_without_breaking_team_links(db, tmp_path):
    user_id, team_id = _legacy_linked_user(db)
    users, credentials, summary = plan_reset(db, _registration_file(tmp_path))

    assert summary["accounts_covered"] == 1
    assert summary["expected_accounts"] == summary["active_accounts"] == 1
    result = apply_reset(db, users, credentials)

    db.expire_all()
    user = db.query(User).filter(User.id == user_id).one()
    team = db.query(Team).filter(Team.id == team_id).one()
    assert result == {
        "accounts_reset": 1,
        "active_accounts": 1,
        "sha256_accounts": 1,
        "bcrypt_hashes": 0,
        "active_sessions": 0,
        "relationships_preserved": True,
    }
    assert user.password_hash.startswith("sha256$")
    assert verify_password("Fresh@123", user.password_hash)
    assert not verify_password("wrong", user.password_hash)
    assert user.session_id is None
    assert user.session_created_at is None
    assert user.session_last_seen_at is None
    assert user.team_id == team.id
    assert team.leader_id == user.id


def test_reset_aborts_when_registration_does_not_cover_every_account(db, tmp_path):
    _legacy_linked_user(db)
    db.add(User(
        name="Uncovered",
        email="uncovered@example.com",
        password_hash="$2b$12$.....................................................",
        role="leader",
        account_source="IMPORTED",
        credentials_active=True,
    ))
    db.commit()

    with pytest.raises(CredentialResetError, match="coverage is incomplete"):
        plan_reset(db, _registration_file(tmp_path))

    assert db.query(User).filter(User.password_hash.like("$2%" )).count() == 2


def test_reset_refuses_to_change_credentials_active_state(db, tmp_path):
    _legacy_linked_user(db)
    user = db.query(User).filter(User.email == "reset.leader@example.com").one()
    user.credentials_active = False
    db.commit()

    with pytest.raises(CredentialResetError, match="inactive account"):
        plan_reset(db, _registration_file(tmp_path))

    db.refresh(user)
    assert user.credentials_active is False
    assert user.password_hash.startswith("$2b$")
