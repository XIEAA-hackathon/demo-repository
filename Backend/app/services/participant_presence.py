from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.models import Team, User


def participant_presence_payload(
    db: Session,
    *,
    connected_team_ids: Iterable[int] | None = None,
) -> dict[str, int | list[int]]:
    """Return unique approved-team presence from authenticated live connections.

    ``connected_team_ids`` is supplied by the WebSocket manager in production.
    Falling back to valid database sessions keeps the helper useful for
    diagnostics and existing callers that do not own connection state.
    """
    if connected_team_ids is None:
        active_users = (
            db.query(User)
            .filter(
                User.role.in_(("leader", "member")),
                User.credentials_active.is_(True),
                User.session_id.is_not(None),
            )
            .all()
        )
        active_user_ids = {user.id for user in active_users}
        active_team_ids = {user.team_id for user in active_users if user.team_id is not None}
        if active_user_ids:
            active_team_ids.update(
                team_id
                for (team_id,) in db.query(Team.id)
                .filter(Team.leader_id.in_(active_user_ids))
                .all()
            )
    else:
        active_team_ids = {int(team_id) for team_id in connected_team_ids}

    registered_team_ids = {
        team_id
        for (team_id,) in db.query(Team.id)
        .filter(Team.is_approved.is_(True), Team.is_system_team.is_(False))
        .all()
    }
    logged_in_team_ids = sorted(active_team_ids & registered_team_ids)
    return {
        "logged_in_team_ids": logged_in_team_ids,
        "participant_logged_in_count": len(logged_in_team_ids),
        "registered_participant_count": len(registered_team_ids),
    }
