from __future__ import annotations

import json

from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, User


with SessionLocal() as db:
    game = db.query(GameConfig).order_by(GameConfig.id).first()
    event = db.query(EventConfig).order_by(EventConfig.id).first()
    controls = {
        row.round_type: {
            "status": row.status,
            "ended": row.ended,
            "current_problem_id": row.current_problem_id,
        }
        for row in db.query(RoundControl).order_by(RoundControl.round_type).all()
    }
    database_stats = db.execute(
        text(
            "SELECT (SELECT setting::int FROM pg_settings WHERE name='max_connections'), "
            "(SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()), "
            "(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()), "
            "(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
            " AND wait_event_type='Lock')"
        )
    ).one()
    print(
        json.dumps(
            {
                "game": {
                    "state": game.state if game else None,
                    "current_round": game.current_round if game else None,
                    "timer_active": bool(game and game.auction_timer_end),
                },
                "controls": controls,
                "event": {
                    "starting_coins": event.starting_coins if event else None,
                    "minimum_bid": event.round1_minimum_bid if event else None,
                    "configured_increment": event.round1_bid_increment if event else None,
                    "cooldown_seconds": event.bid_cooldown_seconds if event else None,
                },
                "counts": {
                    "users": db.query(User).count(),
                    "participant_users": db.query(User).filter(User.role.in_(("leader", "member"))).count(),
                    "teams": db.query(Team).count(),
                    "problems": db.query(ProblemStatement).count(),
                    "bids": db.query(Bid).count(),
                    "active_sessions": db.query(User).filter(User.session_id.is_not(None)).count(),
                },
                "postgresql": {
                    "max_connections": database_stats[0],
                    "deadlocks": database_stats[1],
                    "connections": database_stats[2],
                    "lock_waiters": database_stats[3],
                },
            }
        )
    )
