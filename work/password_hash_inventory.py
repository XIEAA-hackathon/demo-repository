from __future__ import annotations

import json

from sqlalchemy import text

from app.core.database import SessionLocal


with SessionLocal() as db:
    row = db.execute(
        text(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE password_hash LIKE 'sha256$%') AS sha256, "
            "count(*) FILTER (WHERE password_hash ~ '^\\$2[aby]\\$') AS bcrypt, "
            "count(*) FILTER (WHERE password_hash NOT LIKE 'sha256$%' "
            "AND password_hash !~ '^\\$2[aby]\\$') AS other "
            "FROM users"
        )
    ).one()
    grouped = db.execute(
        text(
            "SELECT role, account_source, credentials_active, count(*) "
            "FROM users GROUP BY role, account_source, credentials_active "
            "ORDER BY role, account_source, credentials_active"
        )
    ).all()
    print(json.dumps({
        "total": row.total,
        "sha256": row.sha256,
        "bcrypt": row.bcrypt,
        "other": row.other,
        "groups": [list(item) for item in grouped],
    }))
