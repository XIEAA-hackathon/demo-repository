# Bid to Build — Product & Engineering Overview

## Background

Bid to Build was developed as the event operations system for the Bid2Build Hackathon organized by the XIE Alumni Committee.

A live hackathon auction requires teams, problem statements, virtual wallets, simultaneous bids, timers and round transitions to stay coordinated. Qualification and assignment must then carry through Wildcard opportunities, physical labs, coding submissions and published results. The platform centralizes these operations around persisted event state and role-specific interfaces.

## Product Goals

- Maintain one authoritative event state and synchronize participants in real time.
- Make auction finalization deterministic and preserve historical assignments.
- Give administrators explicit control over important transitions and corrections.
- Reduce manual coordination between auctions, problem selection, labs and coding.
- Keep wallet and assignment mutations transactional.
- Separate event administration, team participation, lab operations and event displays.

## User Roles

### Event Admin

Configures problem banks, teams, imported registrations, credentials and timing; runs Round 1 and Wildcard; corrects current assignments; reviews submissions; selects and publishes winners; and uses recovery controls.

### Participant / Team Leader

Follows the event lifecycle and wallet balance through the participant portal. The team leader performs authorized bid, Wildcard-selection and repository-submission actions. Participant sessions are checked against stored session identity and activity.

### Lab Admin

Uses a separate restricted portal for Team Details, problem results and lab allocation. It exposes operational team/problem history and controlled lab moves without granting Event Admin permissions.

### Leaderboard Display

Uses authenticated display access to show live bidding ranks, finalized round outcomes and published winners.

## Core Workflow

1. **Registration:** administrators create/manage accounts or import CSV/Excel team registrations.
2. **Round 1:** a selected problem moves through preview, timed bidding and explicit winner assignment. The process repeats across the problem bank; supported manual assignment handles remaining teams.
3. **Wildcard:** teams apply, compete for configured slots and receive persisted qualification ranks. Qualified teams select from a frozen problem pool in ranked, timed turns.
4. **Final/current problem:** teams with both Round 1 and Wildcard assignments choose their effective problem. Timeout/default handling resolves pending choices. Administrative correction updates the current assignment without rewriting historical results.
5. **Lab allocation:** allocation uses effective problems and configured physical capacities once final assignments are available.
6. **Coding and submission:** administrators explicitly open coding; team leaders submit or update a GitHub repository URL for their assigned problem.
7. **Judging and results:** administrators review submissions, save three winner positions and explicitly publish results to participants and displays.

These are operational stages, not a claim that every stage has its own event-state enum. Round controls hold detailed auction/Wildcard sub-states alongside the broader event state.

## Engineering Architecture

A single React/Vite application contains the public site, participant portal, Event Admin, Lab Admin and leaderboard. FastAPI provides REST endpoints for authoritative reads and mutations, with WebSockets for event delivery.

PostgreSQL stores identities, teams, bids, round controls, wallets, assignments, submissions and results. SQLAlchemy manages persistence and transaction boundaries; Alembic versions the schema. Backend authorization separates roles and validates participant session identity before protected actions.

The event lifecycle combines a broad state machine with per-round controls and persisted deadlines. Clients render server state and reconcile through HTTP rather than treating a local timer or a received message as independent authority.

## Engineering Challenges

### Deterministic Auction Finalization

Both Round 1 and Wildcard ranking order bids by amount descending, the timestamp at which the final bid amount was reached ascending, then team ID ascending. Finalization checks eligibility and affordability, persists winners and charges them in the settlement transaction. Persisted outcomes and idempotency guards prevent a repeated finalization request from charging the same result again.

### Realtime Synchronization

WebSocket events deliver committed changes to connected clients. Authoritative HTTP refreshes reconcile missed updates, while reconnect handling and bounded healthy/recovery polling restore the participant view. Persisted deadlines and timer reconciliation keep event timing anchored to the server rather than browser countdowns.

### Wildcard State Machine

Wildcard separates applications, slot confirmation, bidding, qualification, ranked problem selection and final choice. A frozen selection pool, persisted ranks, unique selections and timeout handling make recovery possible without reconstructing the workflow from transient UI state.

### Historical vs Current Problem Assignment

| Field | Meaning |
| --- | --- |
| `round1_problem_id` | Historical Round 1 assignment |
| `wildcard_problem_id` | Historical Wildcard assignment |
| `ps_id` | Current/final effective problem |

Keeping these independent allows operational corrections while retaining what happened during the original rounds. Participant views, lab allocation and submissions use the effective assignment; historical details remain available for administration.

### Lab Allocation

Automatic allocation uses a capacity-constrained max-flow assignment, with at most one team per effective problem per lab. It reports unallocated/conflicting teams when the configured labs cannot satisfy the constraints.

Administrative moves preserve original/current lab information and a versioned assignment record. An explicit conflict override may relax problem uniqueness for a manual placement, but it cannot exceed physical lab capacity.

### Recovery

Administrative controls expose the current phase, round sub-state, selection rank and server timing. Operators can reload persisted state, resume a paused timer, resynchronize clients or retry expiry reconciliation. Startup verifies the database schema, and background expiry processing reconciles persisted deadlines before broadcasting committed updates.

### Database Integrity

PostgreSQL foreign keys define cascade, restrict and set-null behavior across the domain. Unique constraints protect per-team submissions, bid identities, Wildcard selections and wallet operation identities; check constraints validate lab capacity and assignment state.

Critical mutation paths use row locking and transactional commits. Wallet ledger entries record signed coin movements alongside the related operation. Alembic migration history—not a runtime `create_all` call or the SQL reference file—is the authoritative schema upgrade mechanism.

See the [complete schema snapshot](Backend/database/schema.sql) and [database guide](Backend/database/README.md).

## Portfolio / Resume Summary

Developed a real-time hackathon auction and event operations platform for the XIE Alumni Committee's Bid2Build event using React, FastAPI, PostgreSQL, SQLAlchemy and WebSockets. Implemented deterministic problem auctions, multi-stage Wildcard workflows, transactional wallet accounting, role-specific administration, capacity-aware lab allocation, coding submissions and live participant reconciliation.
