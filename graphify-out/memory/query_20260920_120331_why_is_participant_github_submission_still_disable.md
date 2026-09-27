---
type: "query"
date: "2026-09-20T12:03:31.824568+00:00"
question: "Why is participant GitHub submission still disabled after removing submissionsOpen from the Coding gate?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["CodingPage.tsx", "permissions.ts", "get_participant_dashboard"]
---

# Q: Why is participant GitHub submission still disabled after removing submissionsOpen from the Coding gate?

## Answer

Expanded via graph vocabulary: [coding, dashboard, leader, permissions, repository, state, submission]. Current commit 25d0dc5 already removes submissionsOpen from both frontend guards. The live local database reports GameConfig.state=CODING and every participant account as the team leader, so the URL field evaluates enabled. However 34 of 35 teams have Team.ps_id null, making dashboard.finalProblem null; CodingPage intentionally disables the submit button when finalProblem is absent. Removing that remaining blocker would violate the explicit requirement that a final problem must exist. Need the affected team/account or confirmation whether the URL field itself, rather than only the submit button, is disabled.

## Outcome

- Signal: useful

## Source Nodes

- CodingPage.tsx
- permissions.ts
- get_participant_dashboard