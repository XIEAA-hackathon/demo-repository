from __future__ import annotations

import json

from sqlalchemy import text

from app.core.database import SessionLocal


with SessionLocal() as db:
    rows = db.execute(
        text(
            "SELECT pid, usename, application_name, client_addr::text, state, wait_event_type, "
            "wait_event, pg_blocking_pids(pid), "
            "round(extract(epoch FROM (clock_timestamp()-query_start))::numeric, 3), "
            "left(regexp_replace(query, '\\s+', ' ', 'g'), 500) "
            "FROM pg_stat_activity WHERE datname=current_database() "
            "AND pid <> pg_backend_pid() AND (state <> 'idle' OR wait_event_type='Lock') "
            "ORDER BY query_start"
        )
    ).all()
    ungranted = db.execute(text("SELECT count(*) FROM pg_locks WHERE NOT granted")).scalar_one()
    serializable = [
        [row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], float(row[8]), row[9]]
        for row in rows
    ]
    print(json.dumps({"active": serializable, "ungranted_locks": ungranted}))
