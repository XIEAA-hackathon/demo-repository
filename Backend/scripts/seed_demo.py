"""Idempotently provision database-backed demo accounts.

Credentials can be overridden with environment variables. This script is safe
to run after every deployment.
"""

import os

from app.core.database import SessionLocal, initialize_database
from app.core.security import get_password_hash
from app.models.models import EventConfig, Team, User, WalletTransaction


def seed_demo() -> dict[str, str]:
    team_name = os.getenv("DEMO_TEAM_NAME", "Demo Team").strip() or "Demo Team"
    leader_email = os.getenv("DEMO_LEADER_EMAIL", "leader@demo.example.com").strip().lower()
    leader_password = os.getenv("DEMO_LEADER_PASSWORD", "DemoLeader@123")
    admin_email = os.getenv("DEMO_ADMIN_EMAIL", "admin.demo@bidtobuild.example.com").strip().lower()
    admin_password = os.getenv("DEMO_ADMIN_PASSWORD", "DemoAdmin@123")

    initialize_database()
    db = SessionLocal()
    try:
        event_config = db.query(EventConfig).first()
        starting_coins = event_config.starting_coins if event_config else 1000

        admin = db.query(User).filter(User.email == admin_email).first()
        if admin is None:
            admin = User(name="Demo Admin", email=admin_email, role="admin", password_hash="")
            db.add(admin)
        admin.name = "Demo Admin"
        admin.role = "admin"
        admin.is_system_account = True
        admin.password_hash = get_password_hash(admin_password)

        leader = db.query(User).filter(User.email == leader_email).first()
        if leader is None:
            leader = User(name="Demo Leader", email=leader_email, role="leader", password_hash="")
            db.add(leader)
            db.flush()
        leader.name = "Demo Leader"
        leader.role = "leader"
        leader.is_system_account = True
        leader.password_hash = get_password_hash(leader_password)

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

        db.commit()
        return {"team": team_name, "leader": leader_email, "admin": admin_email}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    result = seed_demo()
    print(
        f"Demo data ready: team={result['team']}, leader={result['leader']}, "
        f"admin={result['admin']}"
    )
