---
type: "architecture"
date: "2026-09-20T11:37:45.684145+00:00"
question: "Trace and fix Coding duration persistence/open timer behavior; audit Wildcard-to-lab-allocation transaction safety, worker, WebSocket, and migrations."
contributor: "graphify"
outcome: "useful"
source_nodes: ["EventConfig", "GameConfig", "update_event_config_admin", "open_submissions", "transition_event_state", "CodingRoundAdminPage", "assign_wildcard_selection", "reconcile_wildcard_selection", "try_allocate_labs", "event_snapshot"]
---

# Q: Trace and fix Coding duration persistence/open timer behavior; audit Wildcard-to-lab-allocation transaction safety, worker, WebSocket, and migrations.

## Answer

The backend timer already derives CODING expiry from EventConfig.coding_duration_seconds. The admin UI edited a shared config object locally without persisting it, and background refresh restored the DB default before Open Coding. Fixed with a dirty local hours draft and save-before-open ordering. Serialized open with a GameConfig row lock so duplicate/concurrent requests cannot restart the timer. Found and fixed a separate Wildcard transaction-integrity bug: best-effort lab allocation committed or rolled back the caller's selection transaction; selection now commits first and allocation runs afterward. Alembic also exposed model metadata drift for wildcard_final_choice_seconds, aligned nullable=False with the existing migration. Full backend, frontend, migration, worker/WebSocket audits passed.

## Outcome

- Signal: useful

## Source Nodes

- EventConfig
- GameConfig
- update_event_config_admin
- open_submissions
- transition_event_state
- CodingRoundAdminPage
- assign_wildcard_selection
- reconcile_wildcard_selection
- try_allocate_labs
- event_snapshot