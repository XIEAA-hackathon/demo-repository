from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models.models import EventConfig, Team, User, WalletTransaction
from app.services.participant_session import clear_user_session


def _set_password(user: User, password: str) -> None:
    if not user.password_hash or not verify_password(password, user.password_hash):
        user.password_hash = get_password_hash(password)
        clear_user_session(user)


def provision_demo_accounts(db: Session) -> dict[str, str]:
    """Create or repair the explicitly configured permanent system accounts."""
    team_name = settings.DEMO_TEAM_NAME.strip()
    leader_email = settings.DEMO_LEADER_EMAIL.strip().lower()
    admin_email = settings.DEMO_ADMIN_EMAIL.strip().lower()
    display_email = settings.LEADERBOARD_DISPLAY_EMAIL.strip().lower()
    if not all((
        team_name,
        leader_email,
        settings.DEMO_LEADER_PASSWORD,
        admin_email,
        settings.DEMO_ADMIN_PASSWORD,
        display_email,
        settings.LEADERBOARD_DISPLAY_PASSWORD,
    )):
        raise RuntimeError("Demo and leaderboard display account settings are required.")

    event_config = db.query(EventConfig).first()
    starting_coins = event_config.starting_coins if event_config else 5000

    admin = db.query(User).filter(User.email == admin_email).first()
    if admin is None:
        admin = User(name="Demo Admin", email=admin_email, role="admin", password_hash="")
        db.add(admin)
    admin.name = "Demo Admin"
    admin.role = "admin"
    admin.is_system_account = True
    _set_password(admin, settings.DEMO_ADMIN_PASSWORD)

    display = db.query(User).filter(User.email == display_email).first()
    if display is None:
        display = User(name="Leaderboard Display", email=display_email, role="display", password_hash="")
        db.add(display)
    display.name = "Leaderboard Display"
    display.role = "display"
    display.team_id = None
    display.is_system_account = True
    _set_password(display, settings.LEADERBOARD_DISPLAY_PASSWORD)

    leader = db.query(User).filter(User.email == leader_email).first()
    if leader is None:
        leader = User(name="Demo Leader", email=leader_email, role="leader", password_hash="")
        db.add(leader)
        db.flush()
    leader.name = "Demo Leader"
    leader.role = "leader"
    leader.is_system_account = True
    _set_password(leader, settings.DEMO_LEADER_PASSWORD)

    team = db.query(Team).filter(Team.team_name == team_name).first()
    if team is None:
        team = Team(team_name=team_name, coins=starting_coins, is_approved=True)
        db.add(team)
        db.flush()
    team.leader_id = leader.id
    team.is_approved = True
    team.is_system_team = True
    if team.coins is None:
        team.coins = starting_coins
    leader.team_id = team.id

    has_initial_allocation = db.query(WalletTransaction).filter(
        WalletTransaction.team_id == team.id,
        WalletTransaction.transaction_type == "INITIAL_ALLOCATION",
    ).first()
    if not has_initial_allocation:
        db.add(WalletTransaction(
            team_id=team.id,
            transaction_type="INITIAL_ALLOCATION",
            amount=team.coins,
            description="Demo team initial allocation",
        ))

    return {"team": team_name, "leader": leader_email, "admin": admin_email, "display": display_email}
