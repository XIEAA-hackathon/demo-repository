from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import EventActivityLog, User


_BLOCKED_METADATA_KEYS = {
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}


def _safe_metadata(metadata: dict[str, Any] | None) -> str:
    safe: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if any(blocked in key.lower() for blocked in _BLOCKED_METADATA_KEYS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, tuple)):
            safe[key] = [item for item in value if isinstance(item, (str, int, float, bool)) or item is None]
    return json.dumps(safe, separators=(",", ":"), sort_keys=True)


def record_event(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    actor_type: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> EventActivityLog:
    """Stage an append-only operational event in the caller's transaction."""
    row = EventActivityLog(
        actor_type=actor_type or (actor.role if actor else "system"),
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=_safe_metadata(metadata),
    )
    db.add(row)
    return row


def activity_payload(row: EventActivityLog) -> dict:
    try:
        metadata = json.loads(row.metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return {
        "id": row.id,
        "timestamp": row.timestamp,
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "metadata": metadata,
    }
