from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import get_password_hash
from app.models.models import (
    EventConfig,
    GameConfig,
    Lab,
    LabAssignment,
    ProblemStatement,
    RoundControl,
    Team,
    User,
    WalletTransaction,
    Wildcard,
    WildcardBid,
)
from app.services.wildcard_service import (
    assign_wildcard_selection,
    finalize_slot_bidding,
    reconcile_wildcard_final_choice,
)


def _seed_auction(db, *, team_name="Finalists", email="finalists@test.local", bid=250):
    leader = User(name=f"{team_name} Leader", email=email, password_hash=get_password_hash("temp-pass"), role="leader")
    round1 = ProblemStatement(ps_number=f"R1-{team_name}", title="Round 1 Problem", description="Original", round=1, status="completed")
    wildcard_problem = ProblemStatement(ps_number=f"W-{team_name}", title="Wildcard Problem", description="Alternative", round=2, status="visible")
    db.add_all([leader, round1, wildcard_problem])
    db.flush()
    team = Team(team_name=team_name, coins=1000, leader_id=leader.id, ps_id=round1.id, round1_problem_id=round1.id, is_approved=True)
    db.add(team); db.flush(); leader.team_id = team.id
    db.add_all([
        EventConfig(wildcard_selection_seconds=30, wildcard_final_choice_seconds=60),
        GameConfig(state="WILDCARD_BIDDING"),
        RoundControl(round_type="ROUND1", status="COMPLETE", ended=True),
        RoundControl(round_type="WILDCARD", status="BIDDING_CLOSED", ended=False, slot_count=1),
        Wildcard(team_id=team.id, status="applied"),
        WildcardBid(team_id=team.id, amount=bid),
        Lab(name="Final Lab", capacity=10, sort_order=1),
    ])
    db.commit()
    return leader, team, round1, wildcard_problem


def _finalize_and_select(db, team, wildcard_problem):
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    winners = finalize_slot_bidding(db, control)
    assert winners[0]["winning_bid"] == 250
    db.query(GameConfig).one().state = "WILDCARD_SELECTION"
    db.commit()
    result = assign_wildcard_selection(db, method="manual", team_id=team.id, problem_id=wildcard_problem.id)
    db.expire_all()
    return result


def test_round1_choice_preserves_selection_charge_and_allocates_by_final_problem(client, db, login_headers_factory):
    leader, team, round1, wildcard_problem = _seed_auction(db)
    _finalize_and_select(db, team, wildcard_problem)

    selected = db.query(Team).filter(Team.id == team.id).one()
    assert selected.wildcard_problem_id == wildcard_problem.id
    assert selected.ps_id == round1.id
    assert selected.coins == 750
    assert db.query(LabAssignment).count() == 0

    headers = login_headers_factory(leader.email)
    confirmed = client.post("/wildcard/final-choice", headers=headers, json={"choice": "ROUND1"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["completed"] is True
    db.expire_all()
    selected = db.query(Team).filter(Team.id == team.id).one()
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    assignment = db.query(LabAssignment).filter(LabAssignment.team_id == team.id).one()
    assert selected.ps_id == round1.id
    assert selected.final_problem_choice == "ROUND1"
    assert selected.final_problem_confirmed_at is not None
    assert selected.final_problem_defaulted is False
    assert selected.coins == 750
    assert wildcard_problem.id == selected.wildcard_problem_id
    assert db.query(ProblemStatement).filter(ProblemStatement.id == wildcard_problem.id).one().status == "allocated"
    assert control.status == "COMPLETE" and control.ended is True
    assert db.query(GameConfig).one().state == "CODING"
    assert assignment.effective_ps_id == selected.ps_id == round1.id

    duplicate = client.post("/wildcard/final-choice", headers=headers, json={"choice": "WILDCARD"})
    assert duplicate.status_code == 409
    db.expire_all()
    assert db.query(Team).filter(Team.id == team.id).one().coins == 750


@pytest.mark.parametrize("choice", ["ROUND1", "WILDCARD"])
def test_wildcard_payment_is_exactly_once_across_final_choice(db, choice):
    leader, team, round1, wildcard_problem = _seed_auction(db, team_name=f"Pay-{choice}", email=f"{choice.lower()}@pay.test")
    control = db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one()
    finalize_slot_bidding(db, control)
    finalize_slot_bidding(db, control)
    db.expire_all()
    assert db.query(Team).filter(Team.id == team.id).one().coins == 750
    assert db.query(WalletTransaction).filter(WalletTransaction.team_id == team.id, WalletTransaction.transaction_type == "WILDCARD_WIN").count() == 1

    db.query(GameConfig).one().state = "WILDCARD_SELECTION"; db.commit()
    assign_wildcard_selection(db, method="manual", team_id=team.id, problem_id=wildcard_problem.id)
    from app.services.wildcard_service import confirm_final_problem
    confirm_final_problem(db, team_id=team.id, choice=choice, actor=leader)
    db.expire_all()
    final_team = db.query(Team).filter(Team.id == team.id).one()
    assert final_team.coins == 750
    assert final_team.ps_id == (round1.id if choice == "ROUND1" else wildcard_problem.id)
    assert db.query(WalletTransaction).filter(WalletTransaction.team_id == team.id, WalletTransaction.transaction_type == "WILDCARD_WIN").count() == 1


def test_final_choice_rejects_member_and_non_winner(client, db, login_headers_factory):
    leader, team, _round1, wildcard_problem = _seed_auction(db)
    _finalize_and_select(db, team, wildcard_problem)
    member = User(name="Member", email="member@choice.test", password_hash=get_password_hash("temp-pass"), role="member", team_id=team.id)
    outsider_leader = User(name="Outsider", email="outsider@choice.test", password_hash=get_password_hash("temp-pass"), role="leader")
    db.add_all([member, outsider_leader]); db.flush()
    outsider = Team(team_name="Non winner", coins=1000, leader_id=outsider_leader.id, ps_id=team.round1_problem_id, round1_problem_id=team.round1_problem_id, wildcard_problem_id=wildcard_problem.id, is_approved=True)
    db.add(outsider); db.flush(); outsider_leader.team_id = outsider.id; db.commit()

    member_response = client.post("/wildcard/final-choice", headers=login_headers_factory(member.email), json={"choice": "ROUND1"})
    assert member_response.status_code == 403
    outsider_response = client.post("/wildcard/final-choice", headers=login_headers_factory(outsider_leader.email), json={"choice": "WILDCARD"})
    assert outsider_response.status_code == 409
    db.expire_all()
    assert db.query(Team).filter(Team.id == outsider.id).one().final_problem_confirmed_at is None


def test_final_choice_timeout_defaults_round1_without_refund_and_then_allocates(db):
    _leader, team, round1, wildcard_problem = _seed_auction(db)
    _finalize_and_select(db, team, wildcard_problem)
    game = db.query(GameConfig).one()
    game.auction_timer_end = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    result = reconcile_wildcard_final_choice(db, now=datetime.now(timezone.utc))
    assert result is not None
    db.expire_all()
    final_team = db.query(Team).filter(Team.id == team.id).one()
    assignment = db.query(LabAssignment).filter(LabAssignment.team_id == team.id).one()
    assert final_team.ps_id == round1.id
    assert final_team.final_problem_choice == "ROUND1"
    assert final_team.final_problem_defaulted is True
    assert final_team.final_problem_confirmed_at is not None
    assert final_team.coins == 750
    assert final_team.wildcard_problem_id == wildcard_problem.id
    assert assignment.effective_ps_id == final_team.ps_id
    assert db.query(RoundControl).filter(RoundControl.round_type == "WILDCARD").one().status == "COMPLETE"
