---
type: "query"
date: "2026-09-20T12:26:57.968572+00:00"
question: "Investigate ONLY why the participant GitHub submission button is still not working."
contributor: "graphify"
outcome: "useful"
source_nodes: ["CodingPage.tsx", "permissions.ts", "Submission", "Team"]
---

# Q: Investigate ONLY why the participant GitHub submission button is still not working.

## Answer

Expanded from original query via graph vocab: [submission, repository, coding, leader, permissions, final, problem, participant, team]. Source and live bundle are current. Active user 805 is leader in CODING, but team 802 has ps_id null, so dashboard finalProblem/currentProblem are null and the intact !finalProblem guard disables submit. Audit trail: event.data_reset preserved teams but removed all problems; Round 1 ended with 0 assigned/35 unassigned; Wildcard ended empty; Coding opened because open_submissions checks Wildcard completion but not final assignments.

## Outcome

- Signal: useful

## Source Nodes

- CodingPage.tsx
- permissions.ts
- Submission
- Team