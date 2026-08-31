from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import User


PARTICIPANT_ROLES = ("leader", "member")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def participant_session_is_stale(
    last_seen_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether an existing participant session may be replaced."""
    current_time = now or utc_now()
    last_seen = _as_utc(last_seen_at)
    if last_seen is None:
        # Legacy session rows gain nullable timestamps during migration. A
        # matching JWT may revive one, while a new login may safely replace it.
        return True
    return current_time - last_seen > timedelta(
        seconds=settings.SESSION_STALE_SECONDS,
    )


def participant_session_needs_touch(
    last_seen_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    previous_seen = _as_utc(last_seen_at)
    if previous_seen is None:
        return True
    return (now or utc_now()) - previous_seen >= timedelta(
        seconds=settings.SESSION_TOUCH_INTERVAL_SECONDS,
    )


def acquire_participant_session(
    db: Session,
    *,
    user_id: int,
    password_hash: str,
    new_session_id: str,
    now: datetime | None = None,
) -> bool:
    """Atomically acquire a free or stale participant session.

    The conditional UPDATE is intentionally the first write after password
    verification.
    PostgreSQL evaluates the predicate atomically, so no check-then-update
    window can create two successful sessions.
    """
    current_time = now or utc_now()
    stale_before = current_time - timedelta(
        seconds=settings.SESSION_STALE_SECONDS,
    )
    acquired = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.credentials_active.is_(True),
            User.password_hash == password_hash,
            or_(
                User.session_id.is_(None),
                User.session_last_seen_at.is_(None),
                User.session_last_seen_at < stale_before,
            ),
        )
        .update(
            {
                User.session_id: new_session_id,
                User.session_created_at: current_time,
                User.session_last_seen_at: current_time,
            },
            synchronize_session=False,
        )
    )
    return acquired == 1


def touch_participant_session(
    db: Session,
    *,
    user_id: int,
    session_id: str,
    last_seen_at: datetime | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> bool:
    """Refresh activity for the matching session without excessive writes."""
    current_time = now or utc_now()
    if not force and not participant_session_needs_touch(last_seen_at, now=current_time):
        return True

    matching_session = (
        User.id == user_id,
        User.role.in_(PARTICIPANT_ROLES),
        User.credentials_active.is_(True),
        User.session_id == session_id,
    )
    update_query = db.query(User).filter(*matching_session)
    if not force:
        update_query = update_query.filter(
            or_(
                User.session_last_seen_at.is_(None),
                User.session_last_seen_at
                < current_time - timedelta(seconds=settings.SESSION_TOUCH_INTERVAL_SECONDS),
            )
        )
    touched = update_query.update(
        {User.session_last_seen_at: current_time},
        synchronize_session=False,
    )
    if touched == 1:
        db.commit()
        return True
    db.rollback()
    if not force:
        # A recent heartbeat legitimately needs no write. Still verify that the
        # session was not revoked while this request was in flight.
        return db.query(User.id).filter(*matching_session).first() is not None
    return False


def clear_user_session(user: User) -> None:
    user.session_id = None
    user.session_created_at = None
    user.session_last_seen_at = None


def cleared_session_values() -> dict:
    return {
        User.session_id: None,
        User.session_created_at: None,
        User.session_last_seen_at: None,
    }
