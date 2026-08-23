"""Idempotently provision database-backed demo accounts.

Credentials can be overridden with environment variables. This script is safe
to run after every deployment.
"""

from app.core.database import SessionLocal, initialize_database
from app.services.demo_seed import provision_demo_accounts


def seed_demo() -> dict[str, str]:
    initialize_database()
    db = SessionLocal()
    try:
        result = provision_demo_accounts(db)
        db.commit()
        return result
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
