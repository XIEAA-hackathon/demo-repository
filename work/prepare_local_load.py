from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Backend"))

from app.core.database import Base, SessionLocal
from app.core.security import get_password_hash
from app.models.models import EventConfig, GameConfig, ProblemStatement, RoundControl, Team, User


PASSWORD = "LoadTestOnly@2026"
ACCOUNT_COUNT = 110


def truncate() -> None:
    with SessionLocal() as db:
        quote = db.bind.dialect.identifier_preparer.quote
        tables = ", ".join(quote(name) for name in Base.metadata.tables)
        db.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
        db.commit()


def seed(credentials_path: Path) -> None:
    truncate()
    password_hash = get_password_hash(PASSWORD)
    with SessionLocal() as db:
        problem = ProblemStatement(
            ps_number="PS-LOCAL-LOAD",
            title="Disposable local concurrency load",
            description="Local-only load fixture",
            round=1,
            status="current",
        )
        db.add(problem)
        db.flush()
        problem_id = problem.id
        db.add_all(
            [
                EventConfig(
                    starting_coins=5000,
                    round1_minimum_bid=25,
                    round1_bid_increment=5,
                    bid_cooldown_seconds=5,
                ),
                GameConfig(
                    state="ROUND1_BIDDING",
                    current_round=1,
                    auction_timer_end=datetime.now(timezone.utc) + timedelta(minutes=20),
                ),
                RoundControl(
                    round_type="ROUND1",
                    current_problem_id=problem.id,
                    status="BIDDING",
                ),
                RoundControl(round_type="WILDCARD", status="NOT_STARTED"),
            ]
        )

        credentials = []
        for index in range(ACCOUNT_COUNT):
            email = f"load-leader-{index + 1:03d}@local.test"
            user = User(
                name=f"Load Leader {index + 1:03d}",
                email=email,
                password_hash=password_hash,
                role="leader",
                credentials_active=True,
                account_source="MANUAL",
            )
            db.add(user)
            db.flush()
            team = Team(
                team_name=f"Load Team {index + 1:03d}",
                leader_id=user.id,
                coins=5000,
                is_approved=True,
                is_system_team=False,
            )
            db.add(team)
            db.flush()
            user.team_id = team.id
            credentials.append({"username": email, "password": PASSWORD})
        db.commit()

    credentials_path.write_text(
        json.dumps(
            {
                "loginUsers": credentials[:100],
                "activeWebSocketUsers": credentials[100:],
            }
        ),
        encoding="utf-8",
    )
    print(json.dumps({"problem_id": problem_id, "bidders": 100, "observers": 10}))


def reset_run() -> None:
    with SessionLocal() as db:
        db.execute(text("TRUNCATE TABLE bids, event_activity_log RESTART IDENTITY CASCADE"))
        db.execute(
            text(
                "UPDATE users SET session_id = NULL, session_created_at = NULL, "
                "session_last_seen_at = NULL"
            )
        )
        db.execute(text("UPDATE teams SET coins = 5000, ps_id = NULL, round1_problem_id = NULL"))
        db.execute(text("UPDATE problem_statements SET status = 'current' WHERE ps_number = 'PS-LOCAL-LOAD'"))
        problem_id = db.execute(
            text("SELECT id FROM problem_statements WHERE ps_number = 'PS-LOCAL-LOAD'")
        ).scalar_one()
        db.execute(
            text(
                "UPDATE round_controls SET current_problem_id = :problem_id, status = 'BIDDING', "
                "ended = false WHERE round_type = 'ROUND1'"
            ),
            {"problem_id": problem_id},
        )
        db.execute(
            text(
                "UPDATE game_config SET state = 'ROUND1_BIDDING', current_round = 1, "
                "auction_timer_end = :ends_at, timer_paused = false, "
                "timer_paused_remaining_seconds = NULL"
            ),
            {"ends_at": datetime.now(timezone.utc) + timedelta(minutes=20)},
        )
        db.commit()
    print(json.dumps({"reset": True, "problem_id": problem_id}))


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "seed"
    credentials = Path(__file__).with_name("local-load-credentials.json")
    if action == "seed":
        seed(credentials)
    elif action == "reset":
        reset_run()
    elif action == "truncate":
        truncate()
        print(json.dumps({"truncated": True}))
    else:
        raise SystemExit(f"Unknown action: {action}")
