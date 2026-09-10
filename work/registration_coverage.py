from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core.database import SessionLocal
from app.models.models import User


digest_path = Path("/tmp/btb-authoritative-email-digests.json")
authoritative = set(json.loads(digest_path.read_text(encoding="utf-8"))["emailDigests"])

with SessionLocal() as db:
    users = db.query(User).all()
    matched = [
        user
        for user in users
        if hashlib.sha256(user.email.strip().lower().encode("utf-8")).hexdigest() in authoritative
    ]
    imported_leaders = [
        user for user in users
        if user.role == "leader" and user.account_source == "IMPORTED" and user.credentials_active
    ]
    print(json.dumps({
        "authoritative_rows": len(authoritative),
        "matched_active_users": sum(user.credentials_active for user in matched),
        "matched_imported_leaders": sum(
            user.role == "leader" and user.account_source == "IMPORTED"
            for user in matched
        ),
        "active_imported_leaders": len(imported_leaders),
        "active_imported_leaders_not_covered": len(imported_leaders) - sum(
            user in matched for user in imported_leaders
        ),
    }))
