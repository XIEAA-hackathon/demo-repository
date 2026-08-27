from sqlalchemy.orm import Session

from app.models.models import Team, User


def participant_presence_payload(db: Session) -> dict[str, int]:
    """Count unique approved teams with a currently valid participant session."""
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

    registered_team_ids = {
        team_id
        for (team_id,) in db.query(Team.id)
        .filter(Team.is_approved.is_(True), Team.is_system_team.is_(False))
        .all()
    }
    return {
        "participant_logged_in_count": len(active_team_ids & registered_team_ids),
        "registered_participant_count": len(registered_team_ids),
    }
