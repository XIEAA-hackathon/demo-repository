---
type: "architecture"
date: "2026-09-10T13:38:18.058411+00:00"
question: "Where do Wildcard expiry, finalization, dashboard reads, timers, sessions, and WebSocket fan-out interact?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["RoundControl", "sync_expired_event_state", "reconcile_wildcard_selection", "finalize_slot_bidding", "wildcard_payload", "event_snapshot", "get_participant_dashboard", "ConnectionManager"]
---

# Q: Where do Wildcard expiry, finalization, dashboard reads, timers, sessions, and WebSocket fan-out interact?

## Answer

The critical bridge is RoundControl: expiry and bid/finalize paths serialize on it, while event_snapshot, wildcard_payload, and participant dashboard should remain projections. Timer sync belongs in the background worker and selection/bid deltas should update clients without broad dashboard refreshes.

## Outcome

- Signal: useful

## Source Nodes

- RoundControl
- sync_expired_event_state
- reconcile_wildcard_selection
- finalize_slot_bidding
- wildcard_payload
- event_snapshot
- get_participant_dashboard
- ConnectionManager