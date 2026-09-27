---
type: "architecture"
date: "2026-09-20T11:11:48.279999+00:00"
question: "Where does Wildcard completion automatically start Coding, and what action should own the Coding transition?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["transition_event_state", "open_submissions", "close_submissions", "confirm_final_problem", "finish_final_choice", "assign_wildcard_selection"]
---

# Q: Where does Wildcard completion automatically start Coding, and what action should own the Coding transition?

## Answer

Wildcard completion started Coding from wildcard_service confirm/finish/Wildcard-only paths and wildcard.py finalize/manual-end paths. Removing those transitions and making POST /admin/submissions/open validate completed Wildcard then call transition_event_state(CODING, restart=True) makes the admin action authoritative and idempotent.

## Outcome

- Signal: useful

## Source Nodes

- transition_event_state
- open_submissions
- close_submissions
- confirm_final_problem
- finish_final_choice
- assign_wildcard_selection