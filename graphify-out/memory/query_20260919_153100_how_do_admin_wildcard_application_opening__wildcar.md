---
type: "query"
date: "2026-09-19T15:31:00.616240+00:00"
question: "How do admin wildcard application opening, wildcard lifecycle state, event transitions, coding submission availability, and admin wildcard tabs connect?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["open_applications", "transition_event_state", "WildcardControlPage", "create_submission", "update_submission", "get_or_create_round_control"]
---

# Q: How do admin wildcard application opening, wildcard lifecycle state, event transitions, coding submission availability, and admin wildcard tabs connect?

## Answer

Wildcard application opening is handled by rounds.open_applications and requires Round 1 ended plus a fresh NOT_STARTED, non-ended Wildcard. All normal event changes route through transition_event_state, so CODING now synchronizes submission availability true and every other state false. Participant submission endpoints and permissions derive authority from GameConfig.state. WildcardControlPage maps each backend status to four distinct tabs, with FINAL_CHOICE and COMPLETE on the fourth tab.

## Outcome

- Signal: useful

## Source Nodes

- open_applications
- transition_event_state
- WildcardControlPage
- create_submission
- update_submission
- get_or_create_round_control