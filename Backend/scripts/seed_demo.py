"""Idempotently provision database-backed demo accounts.

Credentials are read from environment variables so working passwords never
enter source control. This script is safe to run after every deployment.
"""

import os

from app.core.database import SessionLocal, initialize_database
from app.core.security import get_password_hash
from app.models.models import EventConfig, Member, Team, User, WalletTransaction


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def seed_demo() -> dict[str, str]:
    team_name = os.getenv("DEMO_TEAM_NAME", "Demo Team").strip() or "Demo Team"
    leader_email = required("DEMO_LEADER_EMAIL").lower()
    leader_password = required("DEMO_LEADER_PASSWORD")
    admin_email = required("DEMO_ADMIN_EMAIL").lower()
    admin_password = required("DEMO_ADMIN_PASSWORD")

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
        admin.password_hash = get_password_hash(admin_password)

        leader = db.query(User).filter(User.email == leader_email).first()
        if leader is None:
            leader = User(name="Demo Leader", email=leader_email, role="leader", password_hash="")
            db.add(leader)
            db.flush()
        leader.name = "Demo Leader"
        leader.role = "leader"
        leader.password_hash = get_password_hash(leader_password)

        team = db.query(Team).filter(Team.team_name == team_name).first()
        if team is None:
            team = Team(team_name=team_name, coins=starting_coins, is_approved=True)
            db.add(team)
            db.flush()
        team.leader_id = leader.id
        team.is_approved = True
        if team.coins is None:
            team.coins = starting_coins
        leader.team_id = team.id

        member_rows = [
            ("Demo Member One", "member.one@demo.example.com"),
            ("Demo Member Two", "member.two@demo.example.com"),
        ]
        existing_emails = {member.email for member in db.query(Member).filter(Member.team_id == team.id).all()}
        for name, email in member_rows:
            if email not in existing_emails:
                db.add(Member(team_id=team.id, member_name=name, email=email))

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
    print(f"Demo data ready: team={result['team']}, leader={result['leader']}, admin={result['admin']}")
