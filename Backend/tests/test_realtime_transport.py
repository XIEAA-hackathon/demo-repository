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
