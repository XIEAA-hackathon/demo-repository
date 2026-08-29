import asyncio
import json
import time

from app.api.websockets import ConnectionManager, make_event


class FakeSocket:
    def __init__(self, delay: float = 0):
        self.delay = delay
        self.messages = []

    async def send_json(self, message):
        await asyncio.sleep(self.delay)
        self.messages.append(message)

    async def close(self, *, code, reason):
        self.closed = (code, reason)


def test_event_envelope_has_monotonic_version_and_compact_payload():
    first = make_event("bid_updated", {"team_id": 4, "amount": 250}, version=12)
    assert first["version"] == 12
    assert len(json.dumps(first).encode()) < 512


def test_broadcast_sends_concurrently_and_versions_in_order():
    async def scenario():
        manager = ConnectionManager()
        sockets = [FakeSocket(delay=0.05), FakeSocket(delay=0.05)]
        manager.active_connections = {socket: {"user_id": index} for index, socket in enumerate(sockets)}

        started = time.perf_counter()
        await manager.broadcast_event("first", {"value": 1})
        elapsed = time.perf_counter() - started
        await manager.broadcast_event("second", {"value": 2})

        assert elapsed < 0.09
        assert [[message["version"] for message in socket.messages] for socket in sockets] == [[1, 2], [1, 2]]

    asyncio.run(scenario())


def test_participant_connections_are_deduplicated_by_team_and_revocable_by_user():
    async def scenario():
        manager = ConnectionManager()
        first_tab = FakeSocket()
        second_tab = FakeSocket()
        other_team = FakeSocket()
        admin = FakeSocket()
        manager.active_connections = {
            first_tab: {"user_id": 10, "role": "leader", "team_id": 4},
            second_tab: {"user_id": 10, "role": "leader", "team_id": 4},
            other_team: {"user_id": 11, "role": "member", "team_id": 7},
            admin: {"user_id": 1, "role": "admin", "team_id": None},
        }

        assert manager.participant_team_ids() == {4, 7}
        assert await manager.disconnect_users({10}) == 2
        assert manager.participant_team_ids() == {7}
        assert first_tab.closed[0] == 4401 and second_tab.closed[0] == 4401
        assert admin in manager.active_connections

    asyncio.run(scenario())
