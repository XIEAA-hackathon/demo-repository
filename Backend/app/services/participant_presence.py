from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Team, User
from app.services.participant_session import participant_session_is_stale, utc_now


def participant_presence_payload(
    db: Session,
    *,
    connected_team_ids: Iterable[int] | None = None,
    now: datetime | None = None,
) -> dict[str, int | list[int]]:
    """Return separate realtime-presence and authentication-session state.

    ``connected_team_ids`` is supplied by the WebSocket manager in production.
    A missing value falls back to active sessions for diagnostic callers that
    do not own the in-memory connection registry.
    """
    current_time = now or utc_now()
    session_rows = (
        db.query(
            func.coalesce(User.team_id, Team.id).label("team_id"),
            User.session_last_seen_at,
        )
        .outerjoin(Team, Team.leader_id == User.id)
        .filter(
            User.role.in_(("leader", "member")),
            User.credentials_active.is_(True),
            User.session_id.is_not(None),
        )
        .all()
    )
    active_session_team_ids = {
        team_id
        for team_id, last_seen_at in session_rows
        if team_id is not None
        and not participant_session_is_stale(last_seen_at, now=current_time)
    }
    stale_session_team_ids = {
        team_id
        for team_id, last_seen_at in session_rows
        if team_id is not None
        and participant_session_is_stale(last_seen_at, now=current_time)
    }
    online_team_ids = (
        active_session_team_ids
        if connected_team_ids is None
        else {int(team_id) for team_id in connected_team_ids}
    )

    registered_team_ids = {
        team_id
        for (team_id,) in db.query(Team.id)
        .filter(Team.is_approved.is_(True), Team.is_system_team.is_(False))
        .all()
    }
    online_ids = sorted(online_team_ids & registered_team_ids)
    active_ids = sorted(active_session_team_ids & registered_team_ids)
    stale_ids = sorted(stale_session_team_ids & registered_team_ids)
    return {
        # Backwards-compatible aliases used by the current Admin UI.
        "logged_in_team_ids": online_ids,
        "participant_logged_in_count": len(online_ids),
        "online_team_ids": online_ids,
        "participant_online_count": len(online_ids),
        "active_session_team_ids": active_ids,
        "participant_active_session_count": len(active_ids),
        "stale_session_team_ids": stale_ids,
        "participant_stale_session_count": len(stale_ids),
        "registered_participant_count": len(registered_team_ids),
    }
