---
type: "query"
date: "2026-09-23T20:24:51.051313+00:00"
question: "How is the Lab Admin Problem Results read-only view implemented?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["labs.py", "LabAdminApp.jsx", "ProblemStatement", "Team", "Bid", "Wildcard", "FinalResult"]
---

# Q: How is the Lab Admin Problem Results read-only view implemented?

## Answer

Expanded from the repository vocabulary via lab, admin, problem, results, assignment, wildcard, final, placement, team, bid, auth, round. Backend/app/api/labs.py exposes a Lab-Admin-only read endpoint using five fixed data queries and maps Round 1 history from Team.round1_problem_id, Wildcard history from Team.wildcard_problem_id, canonical final problems from Team.ps_id, and placements from published FinalResult. LabAdminApp.jsx reuses the existing WebSocket and ProblemResultsPage.jsx uses a revision-safe loader, client-side filters, read-only details, and no mutation controls.

## Outcome

- Signal: useful

## Source Nodes

- labs.py
- LabAdminApp.jsx
- ProblemStatement
- Team
- Bid
- Wildcard
- FinalResult