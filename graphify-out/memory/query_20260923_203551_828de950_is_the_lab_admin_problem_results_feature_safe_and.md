---
type: "query"
date: "2026-09-23T20:35:51.302304+00:00"
question: "Is the Lab Admin Problem Results feature safe and correct at 100, 200, and 600 participants?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["labs.py", "LabAdminApp.jsx", "ProblemResultsPage.jsx", "Bid", "Team", "WebSocket"]
---

# Q: Is the Lab Admin Problem Results feature safe and correct at 100, 200, and 600 participants?

## Answer

Expanded from graph vocabulary via lab, admin, problem, results, team, bid, wildcard, final, websocket, session, query, participant. Review found no N+1, writes, locks, extra WebSocket, fanout, or participant-path coupling. Fixed burst refresh coalescing, request cancellation on unmount, overbroad Round 1 bid loading, repeated nested descriptions, and incomplete-data test gaps. Measured five feature data SELECTs at all sizes: 100 teams 15.85 ms and 72.8 KB; 200 teams 20.48 ms and 130.0 KB; 600 teams 45.66 ms and 358.6 KB. A normal authorized request adds one authentication SELECT. Remaining low concern is a large client DOM if one problem has 600 assignments expanded.

## Outcome

- Signal: useful

## Source Nodes

- labs.py
- LabAdminApp.jsx
- ProblemResultsPage.jsx
- Bid
- Team
- WebSocket