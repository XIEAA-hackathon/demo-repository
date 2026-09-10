from __future__ import annotations

from datetime import datetime, timezone
import math

from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.models.models import Bid, WildcardBid


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def bid_cooldown_remaining(
    db: Session,
    team_id: int,
    cooldown_seconds: int,
    *,
    round_type: str,
    problem_id: int | None = None,
    round_number: int = 1,
    now: datetime | None = None,
) -> float:
    """Return the cooldown remaining in the team's active bidding stream."""
    if cooldown_seconds <= 0:
        return 0.0

    if round_type == "ROUND1":
        latest = (
            db.query(Bid.timestamp)
            .filter(
                Bid.team_id == team_id,
                Bid.ps_id == problem_id,
                Bid.round == round_number,
            )
            .order_by(Bid.timestamp.desc())
            .limit(1)
            .scalar()
        )
    elif round_type == "WILDCARD":
        latest = (
            db.query(WildcardBid.timestamp)
            .filter(WildcardBid.team_id == team_id)
            .order_by(WildcardBid.timestamp.desc())
            .limit(1)
            .scalar()
        )
    else:
        raise ValueError(f"Unsupported bidding round: {round_type}")

    if latest is None:
        return 0.0

    elapsed = ((now or datetime.now(timezone.utc)) - _as_utc(latest)).total_seconds()
    return max(0.0, cooldown_seconds - elapsed)


def bid_cooldown_rejection(remaining_seconds: float) -> JSONResponse:
    retry_after = max(1, math.ceil(remaining_seconds))
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Bid cooldown active.",
            "retry_after_seconds": round(remaining_seconds, 1),
        },
        headers={"Retry-After": str(retry_after)},
    )
