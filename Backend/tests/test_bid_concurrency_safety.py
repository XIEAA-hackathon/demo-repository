import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi import HTTPException

from app.api import auction
from app.api.auction import BidCooldownActive, _place_round1_bid_transaction, finalize_round_one
from app.models.models import (
    Bid,
    EventActivityLog,
    EventConfig,
    GameConfig,
    ProblemStatement,
    RoundControl,
    Team,
    User,
    WalletTransaction,
)
from app.services.event_service import sync_expired_event_state


def _active_round_one(db, *, team_count: int, cooldown_seconds: int = 0, expired: bool = False):
    problem = ProblemStatement(
        ps_number="PS-CONCURRENCY",
        title="Concurrency",
        description="Lock safety",
        round=1,
        status="current",
    )
    db.add(problem)
    db.flush()
    db.add(
        GameConfig(
            state="ROUND1_BIDDING",
            current_round=1,
            auction_timer_end=(datetime.now(timezone.utc) - timedelta(seconds=1)) if expired else None,
        )
    )
    db.add(
        EventConfig(
            round1_minimum_bid=25,
            bid_cooldown_seconds=cooldown_seconds,
        )
    )
    db.add(
        RoundControl(
            round_type="ROUND1",
            current_problem_id=problem.id,
            status="BIDDING",
        )
    )
    accounts = []
    for index in range(team_count):
        session_id = f"session-{index}"
        user = User(
            name=f"Leader {index}",
            email=f"leader-{index}@bid-race.test",
            password_hash="unused-test-hash",
            role="leader",
            session_id=session_id,
            credentials_active=True,
        )
        db.add(user)
        db.flush()
        team = Team(
            team_name=f"Race Team {index}",
            leader_id=user.id,
            coins=5000,
            is_approved=True,
        )
        db.add(team)
        db.flush()
        user.team_id = team.id
        accounts.append((user.email, session_id, team.id))
    db.commit()
    return problem.id, accounts


def _bid_once(session_factory, problem_id: int, account, increment: int = 5):
    email, session_id, _team_id = account
    return _place_round1_bid_transaction(
        session_factory,
        email=email,
        session_id=session_id,
        problem_id=problem_id,
        increment=increment,
    )


def test_two_simultaneous_bids_are_sequential_and_unique(db, session_factory):
    problem_id, accounts = _active_round_one(db, team_count=2)
    barrier = Barrier(3)

    def race(account):
        barrier.wait(timeout=10)
        return _bid_once(session_factory, problem_id, account)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(race, account) for account in accounts]
        barrier.wait(timeout=10)
        results = [future.result(timeout=20) for future in futures]

    assert sorted(result.amount for result in results) == [30, 35]
    assert db.query(Bid).filter(Bid.ps_id == problem_id).count() == 2


def test_ten_simultaneous_bids_are_unique_sequential_and_preserve_wallets(db, session_factory):
    problem_id, accounts = _active_round_one(db, team_count=10)
    barrier = Barrier(11)

    def race(account):
        barrier.wait(timeout=10)
        return _bid_once(session_factory, problem_id, account)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(race, account) for account in accounts]
        barrier.wait(timeout=10)
        results = [future.result(timeout=20) for future in futures]

    db.expire_all()
    amounts = sorted(row.amount for row in db.query(Bid).filter(Bid.ps_id == problem_id).all())
    assert amounts == list(range(30, 80, 5))
    assert len({result.amount for result in results}) == 10
    assert db.query(Team).filter(Team.coins != 5000).count() == 0
    assert db.query(EventActivityLog).filter(EventActivityLog.action == "round1.bid_placed").count() == 10


def test_rapid_duplicate_bid_is_blocked_by_server_cooldown(db, session_factory):
    problem_id, accounts = _active_round_one(db, team_count=1, cooldown_seconds=5)
    first = _bid_once(session_factory, problem_id, accounts[0])
    with pytest.raises(BidCooldownActive) as rejected:
        _bid_once(session_factory, problem_id, accounts[0])

    assert 0 < rejected.value.remaining_seconds <= 5
    db.expire_all()
    assert db.query(Bid).filter(Bid.ps_id == problem_id).one().amount == first.amount
    assert db.query(EventActivityLog).filter(EventActivityLog.action == "round1.bid_placed").count() == 1


def test_two_tabs_cannot_bypass_team_cooldown(db, session_factory):
    problem_id, accounts = _active_round_one(db, team_count=1, cooldown_seconds=5)
    barrier = Barrier(3)

    def race_duplicate():
        barrier.wait(timeout=10)
        try:
            return _bid_once(session_factory, problem_id, accounts[0])
        except BidCooldownActive:
            return "cooldown"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(race_duplicate) for _ in range(2)]
        barrier.wait(timeout=10)
        outcomes = [future.result(timeout=20) for future in futures]

    assert sum(outcome == "cooldown" for outcome in outcomes) == 1
    db.expire_all()
    assert db.query(Bid).count() == 1
    assert db.query(EventActivityLog).filter(EventActivityLog.action == "round1.bid_placed").count() == 1


def test_bid_racing_expiry_cannot_enter_after_authoritative_deadline(db, session_factory):
    problem_id, accounts = _active_round_one(db, team_count=1, expired=True)
    barrier = Barrier(3)

    def bid_after_deadline():
        barrier.wait(timeout=10)
        try:
            return _bid_once(session_factory, problem_id, accounts[0])
        except HTTPException as exc:
            return exc.status_code

    def expire_round():
        barrier.wait(timeout=10)
        with session_factory() as expiry_db:
            return sync_expired_event_state(expiry_db)

    with ThreadPoolExecutor(max_workers=2) as executor:
        bid_future = executor.submit(bid_after_deadline)
        expiry_future = executor.submit(expire_round)
        barrier.wait(timeout=10)
        bid_outcome = bid_future.result(timeout=20)
        expiry_future.result(timeout=20)

    db.expire_all()
    assert bid_outcome == 409
    assert db.query(Bid).count() == 0
    assert db.query(GameConfig).one().state == "ROUND1_RESULT"
    assert db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one().status == "READY"


def test_session_revoked_while_waiting_for_auction_lock_cannot_bid(db, session_factory):
    problem_id, accounts = _active_round_one(db, team_count=1)
    email, session_id, _team_id = accounts[0]

    with session_factory() as lock_db:
        lock_db.query(RoundControl).filter(
            RoundControl.round_type == "ROUND1",
        ).with_for_update().one()

        with ThreadPoolExecutor(max_workers=1) as executor:
            bid_future = executor.submit(
                _place_round1_bid_transaction,
                session_factory,
                email=email,
                session_id=session_id,
                problem_id=problem_id,
                increment=5,
            )
            with session_factory() as revoke_db:
                revoke_db.query(User).filter(User.email == email).update({User.session_id: None})
                revoke_db.commit()
            lock_db.commit()

            with pytest.raises(HTTPException) as rejected:
                bid_future.result(timeout=20)

    assert rejected.value.status_code == 401
    assert db.query(Bid).count() == 0


def test_bid_racing_finalization_is_atomic_and_charges_at_most_once(
    db,
    session_factory,
    monkeypatch,
):
    problem_id, accounts = _active_round_one(db, team_count=1)
    admin = User(
        name="Race Admin",
        email="race-admin@test.local",
        password_hash="unused-test-hash",
        role="admin",
        session_id="admin-session",
    )
    db.add(admin)
    db.commit()
    admin_id = admin.id
    barrier = Barrier(3)

    async def no_broadcast(_event_type, _payload):
        return None

    monkeypatch.setattr(auction.manager, "broadcast_event", no_broadcast)

    def bid_now():
        barrier.wait(timeout=10)
        try:
            return _bid_once(session_factory, problem_id, accounts[0])
        except HTTPException as exc:
            return exc.status_code

    def finalize_now():
        barrier.wait(timeout=10)
        with session_factory() as finalize_db:
            current_admin = finalize_db.query(User).filter(User.id == admin_id).one()
            return asyncio.run(
                finalize_round_one(problem_id, db=finalize_db, current_user=current_admin)
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        bid_future = executor.submit(bid_now)
        finalize_future = executor.submit(finalize_now)
        barrier.wait(timeout=10)
        bid_outcome = bid_future.result(timeout=20)
        finalize_future.result(timeout=20)

    db.expire_all()
    bids = db.query(Bid).filter(Bid.ps_id == problem_id).all()
    charges = db.query(WalletTransaction).filter(WalletTransaction.transaction_type == "ROUND1_WIN").all()
    team = db.query(Team).filter(Team.id == accounts[0][2]).one()
    if isinstance(bid_outcome, int):
        assert bid_outcome in {400, 409}
        assert bids == []
        assert charges == []
        assert team.coins == 5000
    else:
        assert len(bids) == 1
        assert len(charges) == 1
        assert charges[0].amount == -bids[0].amount
        assert team.coins == 5000 - bids[0].amount


def test_database_failure_rolls_back_bid_and_activity(db, session_factory, monkeypatch):
    problem_id, accounts = _active_round_one(db, team_count=1)

    def fail_event_recording(*_args, **_kwargs):
        raise RuntimeError("injected activity log failure")

    monkeypatch.setattr(auction, "record_event", fail_event_recording)
    with pytest.raises(RuntimeError, match="injected activity log failure"):
        _bid_once(session_factory, problem_id, accounts[0])

    db.expire_all()
    assert db.query(Bid).count() == 0
    assert db.query(EventActivityLog).count() == 0


def test_finalization_failure_rolls_back_wallet_and_assignment(db, session_factory, monkeypatch):
    problem_id, accounts = _active_round_one(db, team_count=1)
    placed = _bid_once(session_factory, problem_id, accounts[0])
    admin = User(
        name="Rollback Admin",
        email="rollback-admin@test.local",
        password_hash="unused-test-hash",
        role="admin",
        session_id="rollback-admin-session",
    )
    db.add(admin)
    db.commit()
    admin_id = admin.id

    def fail_finalization_event(*_args, **_kwargs):
        raise RuntimeError("injected finalization event failure")

    monkeypatch.setattr(auction, "record_event", fail_finalization_event)
    with pytest.raises(RuntimeError, match="injected finalization event failure"):
        with session_factory() as finalize_db:
            current_admin = finalize_db.query(User).filter(User.id == admin_id).one()
            asyncio.run(finalize_round_one(problem_id, db=finalize_db, current_user=current_admin))

    db.expire_all()
    team = db.query(Team).filter(Team.id == accounts[0][2]).one()
    assert team.coins == 5000
    assert team.ps_id is None
    assert team.round1_problem_id is None
    assert db.query(WalletTransaction).filter(WalletTransaction.team_id == team.id).count() == 0
    assert db.query(Bid).filter(Bid.id == placed.bid_id).count() == 1
