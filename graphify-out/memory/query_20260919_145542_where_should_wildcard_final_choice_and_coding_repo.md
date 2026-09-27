---
type: "architecture"
date: "2026-09-19T14:55:42.149833+00:00"
question: "Where should Wildcard final choice and Coding repository submission integrate without changing bidding mechanics?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["wildcard_service", "Team", "RoundControl", "GameConfig", "EventConfig", "lab_allocation", "CodingPage", "ParticipantContext"]
---

# Q: Where should Wildcard final choice and Coding repository submission integrate without changing bidding mechanics?

## Answer

Wildcard selection stores only Team.wildcard_problem_id, then the final-choice state confirms/defaults Team.ps_id before marking Wildcard complete and invoking the existing lab allocator. Repository submission remains the existing API/model but is presented in Coding; opening only toggles submissions_open and closing transitions CODING to JUDGING_WAIT. Legacy SUBMISSION normalizes at backend and frontend boundaries.

## Outcome

- Signal: useful

## Source Nodes

- wildcard_service
- Team
- RoundControl
- GameConfig
- EventConfig
- lab_allocation
- CodingPage
- ParticipantContext