---
type: "query"
date: "2026-09-23T19:48:23.493334+00:00"
question: "Fix participant Wildcard turn and dedicated leaderboard final-results dropped-refresh races."
contributor: "graphify"
outcome: "useful"
source_nodes: ["ParticipantContext", "RefreshRunner", "PreviewRealtime.test.tsx", "LeaderboardDisplay.jsx", "LeaderboardDisplay.test.jsx"]
---

# Q: Fix participant Wildcard turn and dedicated leaderboard final-results dropped-refresh races.

## Answer

Expanded from original query via graph vocab: [context, participant, realtime, refresh, results, revision, selection, turn]. Confirmed both races. ParticipantContext now schedules a silent follow-up whenever an HTTP snapshot revision is stale, including after a dashboard already exists. LeaderboardDisplay records a refresh requested during an in-flight fetch and schedules one 250ms follow-up after completion. Focused tests cover enabled Wildcard selection and automatic final-results rendering.

## Outcome

- Signal: useful

## Source Nodes

- ParticipantContext
- RefreshRunner
- PreviewRealtime.test.tsx
- LeaderboardDisplay.jsx
- LeaderboardDisplay.test.jsx