---
type: "query"
date: "2026-09-20T14:15:20.680025+00:00"
question: "Optimize the single-process BidToBuild architecture for 500-600 participants without changing business semantics"
contributor: "graphify"
outcome: "useful"
source_nodes: ["WebSocket", "ParticipantContext", "RoundControl", "database.py"]
---

# Q: Optimize the single-process BidToBuild architecture for 500-600 participants without changing business semantics

## Answer

Expanded via graph vocabulary: websocket, broadcast, queue, heartbeat, session, participant, reconciliation, auction, wildcard, database, pool, timer. Verified current source, then added throttled session validation, bounded per-client sender queues with slow-client isolation and cleanup, preserved authoritative RoundControl locks while shortening Round 1 preflight work, delayed healthy-socket reconciliation, added diagnostics and authenticated load tooling. Capacity remains unverified without production-like load tests.

## Outcome

- Signal: useful

## Source Nodes

- WebSocket
- ParticipantContext
- RoundControl
- database.py