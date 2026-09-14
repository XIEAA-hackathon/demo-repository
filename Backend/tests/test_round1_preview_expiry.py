import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.main import process_expiry_cycle
from app.models.models import EventActivityLog, EventConfig, GameConfig, ProblemStatement, RoundControl


def prepare(client, db, headers):
    settings = db.query(EventConfig).one()
    settings.round1_preview_seconds = 5
    settings.round1_bid_seconds = 10
    problem = ProblemStatement(ps_number="R1-EXPIRY", title="Preview regression", round=1, status="available")
    db.add(problem)
    db.commit()
    assert client.post(f"/admin/rounds/round-1/problems/{problem.id}/select", headers=headers).status_code == 200
    return problem


@pytest.mark.parametrize("expire", [False, True])
def test_preview_to_new_bidding_timer(client, db, admin_headers, session_factory, expire):
    prepare(client, db, admin_headers)
    preview = client.post("/admin/rounds/round-1/preview/start", headers=admin_headers)
    assert preview.status_code == 200
    previous_start = preview.json()["event"]["timing"]["started_at"]
    if expire:
        db.expire_all()
        db.query(GameConfig).one().auction_timer_end = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        events = []

        class Capture:
            async def broadcast_event(self, event_type, payload):
                events.append((event_type, payload))

        # Multiple worker cycles must emit one expiry event, not start bidding.
        assert asyncio.run(process_expiry_cycle(session_factory, Capture())) == ["round1.preview_expired"]
        assert asyncio.run(process_expiry_cycle(session_factory, Capture(), emit_timer_sync=True)) == []
        assert len(events) == 1
        kind, snapshot = events[0]
        assert kind == "event_state_changed"
        assert snapshot["rounds"]["ROUND1"]["status"] == "PREVIEW_EXPIRED"
        assert snapshot["event_state"] == "ROUND1_PREVIEW"
        assert snapshot["timing"]["ends_at"] is None
        assert snapshot["timing"]["remaining_seconds"] in (0, None)
        assert snapshot["timing"]["paused"] is False
    response = client.post("/admin/rounds/round-1/bidding/start", headers=admin_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "BIDDING"
    assert payload["event"]["event_state"] == "ROUND1_BIDDING"
    timing = payload["event"]["timing"]
    assert timing["started_at"] != previous_start
    assert (datetime.fromisoformat(timing["ends_at"]) - datetime.fromisoformat(timing["started_at"])).total_seconds() == 10
    assert timing["paused"] is False
    # A repeated click succeeds without restarting the new timer.
    repeated = client.post("/admin/rounds/round-1/bidding/start", headers=admin_headers)
    assert repeated.json()["event"]["timing"]["ends_at"] == timing["ends_at"]


@pytest.mark.parametrize("status,state", [("READY", "WAITING"), ("READY", "ROUND1_RESULT"), ("PREVIEW_EXPIRED", "ROUND1_RESULT")])
def test_start_bidding_rejects_invalid_source(client, db, admin_headers, status, state):
    prepare(client, db, admin_headers)
    db.expire_all()
    db.query(RoundControl).filter_by(round_type="ROUND1").one().status = status
    db.query(GameConfig).one().state = state
    db.commit()
    assert client.post("/admin/rounds/round-1/bidding/start", headers=admin_headers).status_code == 409
    db.expire_all()
    assert db.query(GameConfig).one().auction_timer_end is None


def test_concurrent_start_clicks_share_one_timer(client, db, admin_headers):
    prepare(client, db, admin_headers)
    assert client.post("/admin/rounds/round-1/preview/start", headers=admin_headers).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post("/admin/rounds/round-1/bidding/start", headers=admin_headers), range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["event"]["timing"]["ends_at"] for response in responses}) == 1
    assert db.query(EventActivityLog).filter_by(action="round1.bidding_started").count() == 1


def test_wildcard_expiry_still_waits_for_finalization(db, session_factory):
    db.add_all([EventConfig(), RoundControl(round_type="WILDCARD", status="BIDDING_OPEN"),
                GameConfig(state="WILDCARD_BIDDING", auction_timer_end=datetime.now(timezone.utc) - timedelta(seconds=1))])
    db.commit()

    class Capture:
        async def broadcast_event(self, kind, payload):
            assert payload["rounds"]["WILDCARD"]["status"] == "BIDDING_CLOSED"
            assert payload["event_state"] == "WILDCARD_BIDDING"
            assert payload["timing"]["ends_at"] is None

    assert asyncio.run(process_expiry_cycle(session_factory, Capture())) == ["wildcard.bidding_expired"]
