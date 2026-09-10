from __future__ import annotations

import json

from sqlalchemy import text

from app.core.database import SessionLocal


with SessionLocal() as db:
    rows = db.execute(
        text(
            "SELECT con.conname, child.relname AS child_table, "
            "pg_get_constraintdef(con.oid) AS definition "
            "FROM pg_constraint con "
            "JOIN pg_class child ON child.oid=con.conrelid "
            "JOIN pg_class parent ON parent.oid=con.confrelid "
            "WHERE con.contype='f' AND (child.relname='users' OR parent.relname='users') "
            "ORDER BY child.relname, con.conname"
        )
    ).all()
    print(json.dumps({"user_foreign_keys": [list(row) for row in rows]}))
