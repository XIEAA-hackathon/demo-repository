---
type: "query"
date: "2026-09-20T18:03:34.615474+00:00"
question: "Load-test the actual deployed BidToBuild website with at least 100 participants and report capacity, correctness, server, database, WebSocket, and session behavior."
contributor: "graphify"
outcome: "useful"
source_nodes: ["load_participants.py", "health_check()", "websocket_auction()", "GameConfig", "User", "nginx.conf"]
---

# Q: Load-test the actual deployed BidToBuild website with at least 100 participants and report capacity, correctness, server, database, WebSocket, and session behavior.

## Answer

Expanded from original query via graph vocab: [harness, participant, websocket, health, heartbeat, pool, bid, reconcile, auction, session, public, deployment]. The safety gate blocked participant and bidding load: production was in CODING with recent real activity, 10 active participant sessions, only 36 leader accounts, and no 100-account credential CSV. Read-only checks showed public API lives under /api while the harness uses root HTTP paths and would fail login; WSS root routing reaches the application. EC2 is m7a.large, one Uvicorn, PostgreSQL healthy, no pool timeouts, no queue pressure. No code was changed.

## Outcome

- Signal: useful

## Source Nodes

- load_participants.py
- health_check()
- websocket_auction()
- GameConfig
- User
- nginx.conf