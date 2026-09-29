"""Read-only leaderboard projections; auction persistence/finalization stays unchanged."""
from sqlalchemy.orm import Session

from app.models.models import Bid, ProblemStatement, RoundControl, Team, WalletTransaction
from app.services.wildcard_service import ranked_wildcard_bids

LEADERBOARD_LIMIT = 10
WILDCARD_FINAL_STATUSES = {"PROBLEM_SELECTION", "FINAL_CHOICE", "COMPLETE"}


def round1_result_problem(db: Session, control: RoundControl) -> ProblemStatement | None:
    if control.current_problem_id is not None:
        return None  # The next selected auction always takes precedence.
    # Assign Winners clears current_problem_id. The committed winner ledger
    # identifies the latest assignment without assuming problem-ID order.
    latest = (db.query(WalletTransaction.description)
              .filter(WalletTransaction.transaction_type == "ROUND1_WIN")
              .order_by(WalletTransaction.id.desc()).first())
    if not latest:
        return None
    return next((problem for problem in db.query(ProblemStatement)
                 .filter(ProblemStatement.round == 1, ProblemStatement.status.in_(("completed", "allocated"))).all()
                 if latest.description == f"Round 1 win for problem {problem.ps_number.split('-', 1)[-1]}"), None)


def round1_rows(db: Session, problem_id: int | None, *, finalized: bool = False) -> list[dict]:
    if problem_id is None:
        return []  # Never combine bids from different R1 problems.
    query = db.query(Bid, Team).join(Team, Team.id == Bid.team_id).filter(Bid.round == 1, Bid.ps_id == problem_id)
    if finalized:
        query = query.filter(Team.round1_problem_id == problem_id, Team.round1_assignment_type == "BID_WINNER")
    rows = query.order_by((Team.round1_assignment_cost if finalized else Bid.amount).desc(), Bid.timestamp.asc(), Bid.team_id.asc())
    if not finalized:
        rows = rows.limit(LEADERBOARD_LIMIT)
    return [{"rank": rank, "team_id": team.id, "team_name": team.team_name,
             "value": team.round1_assignment_cost if finalized else bid.amount,
             "timestamp": bid.timestamp, "problem_id": problem_id, "finalized": finalized,
             "qualified": True if finalized else None, "coins": team.coins}
            for rank, (bid, team) in enumerate(rows.all(), start=1)]


def wildcard_rows(db: Session, control: RoundControl) -> list[dict]:
    finalized = control.status in WILDCARD_FINAL_STATUSES
    ranked = ranked_wildcard_bids(db)
    if finalized:
        # Persisted qualification/rank override live price order. Ineligible
        # high bidders must never displace an actually qualified team.
        ranked.sort(key=lambda row: (0, row[2].rank) if row[2].status in {"qualified", "selected"} else (1, 0))
    return [{"rank": rank, "team_id": team.id, "team_name": team.team_name,
             "value": application.winning_bid if finalized and application.status in {"qualified", "selected"} else bid.amount,
             "timestamp": bid.timestamp, "qualified": application.status in {"qualified", "selected"},
             "finalized": finalized, "coins": team.coins}
            for rank, (bid, team, application) in enumerate(ranked[:LEADERBOARD_LIMIT], start=1)]
