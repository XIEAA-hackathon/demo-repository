---
type: "query"
date: "2026-09-20T11:53:29.620243+00:00"
question: "Fix only the participant GitHub submission enablement bug: Coding leaders must not depend on dashboard.submissionsOpen."
contributor: "graphify"
outcome: "useful"
source_nodes: ["permissions.ts", "CodingPage.tsx", "CodingFlow.test.tsx"]
---

# Q: Fix only the participant GitHub submission enablement bug: Coding leaders must not depend on dashboard.submissionsOpen.

## Answer

Expanded from original query via graph vocab: [coding, dashboard, event, leader, permissions, repository, state, submission, submissions]. The participant UI had duplicate submissionsOpen gates in getParticipantPermissions and CodingPage even though the backend authorizes submission from GameConfig.state == CODING. Removed only those two frontend flag checks. Existing focused tests now prove leader plus CODING is enabled even when submissionsOpen is false, non-leader plus CODING is disabled, and non-CODING is disabled even when submissionsOpen is true.

## Outcome

- Signal: useful

## Source Nodes

- permissions.ts
- CodingPage.tsx
- CodingFlow.test.tsx