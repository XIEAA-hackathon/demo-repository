---
type: "explain"
date: "2026-09-20T17:45:34.935708+00:00"
question: "Where is strict participant single-session behavior enforced?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["_acquire_participant_session()", "acquire_participant_session()", "participant_session_is_stale()", "logout()", "test_auth_role_separation.py"]
---

# Q: Where is strict participant single-session behavior enforced?

## Answer

Participant login already uses atomic acquire_participant_session; fresh duplicates return 409 without changing session_id or disconnecting the first WebSocket, stale sessions use SESSION_STALE_SECONDS, and logout clears the matching session. Added focused regression coverage only.

## Outcome

- Signal: useful

## Source Nodes

- _acquire_participant_session()
- acquire_participant_session()
- participant_session_is_stale()
- logout()
- test_auth_role_separation.py