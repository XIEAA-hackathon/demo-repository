# Graph Report - demo-repository  (2026-09-20)

## Corpus Check
- 208 files · ~149,458 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1673 nodes · 5247 edges · 101 communities (77 shown, 6 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 678 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `fbe3353f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- get_password_hash
- LabAdminApp.jsx
- participant.py
- place_bid
- ParticipantContext.tsx
- admin/services/api.js
- devDependencies
- Wildcard
- ParticipantApp.tsx
- record_event
- ProblemStatement
- eventContent.ts
- App.jsx
- wildcard.py
- Team
- ui.tsx
- admin.py
- NeonButton.tsx
- compilerOptions
- conftest.py
- migrate_sqlite_to_postgres.py
- auction.py
- index.ts
- Bid
- User
- LabAssignment
- RuleCards.tsx
- judging.py
- PublicLayout.tsx
- main.py
- HomePage.tsx
- apiClient.ts
- operations.py
- App.tsx
- FastAPI
- team.py
- AdminApplication.test.jsx
- auth.py
- Settings
- SQLite to PostgreSQL production migration
- compilerOptions
- request
- 20260829_0001_initial_schema.py
- deploy-release.sh
- ChangeProblem.jsx
- Casino Hackathon Backend Service Architecture
- deploy-main1-remote.sh
- apiParticipantService.ts
- SQLite to PostgreSQL Production Migration
- AWS production deployment
- XIE Alumni Hackathon Public Frontend
- XIE Alumni Hackathon — Bid to Build (Frontend)
- Casino Gaming Hall
- Bid to Build Platform
- Main1 EC2 Deployment
- Luxury Casino Interior
- Backend Runtime Dependencies
- Spade Favicon
- acceptance.sh
- setup-server.sh
- Spade Favicon
- websockets.py
- CodingRoundAdminPage
- ConnectionManager
- test_auth_role_separation.py
- EventsPage.tsx
- load_participants.py
- LabConfiguration.jsx
- Bid to Build
- _Socket
- Q: Which former-main files are obsolete versus current main1 application code and current test tooling?
- Q: Audit and safely improve non-bidding performance on main1: images, route loading, redundant requests, async blocking, N+1 queries, startup, dependencies, and instrumentation.
- Q: Where should Wildcard final choice and Coding repository submission integrate without changing bidding mechanics?
- Q: How do admin wildcard application opening, wildcard lifecycle state, event transitions, coding submission availability, and admin wildcard tabs connect?
- Q: Where does Wildcard completion automatically start Coding, and what action should own the Coding transition?
- Q: Trace and fix Coding duration persistence/open timer behavior; audit Wildcard-to-lab-allocation transaction safety, worker, WebSocket, and migrations.
- Q: Fix only the participant GitHub submission enablement bug: Coding leaders must not depend on dashboard.submissionsOpen.
- Q: Why is participant GitHub submission still disabled after removing submissionsOpen from the Coding gate?
- Q: Investigate ONLY why the participant GitHub submission button is still not working.
- Q: Optimize the single-process BidToBuild architecture for 500-600 participants without changing business semantics
- BidToBuild Agent Rules
- deploy.sh
- PRODUCT.md

## God Nodes (most connected - your core abstractions)
1. `User` - 177 edges
2. `Team` - 128 edges
3. `RoundControl` - 90 edges
4. `request()` - 89 edges
5. `record_event()` - 87 edges
6. `ProblemStatement` - 83 edges
7. `_post()` - 74 edges
8. `GameConfig` - 68 edges
9. `event_snapshot()` - 66 edges
10. `EventConfig` - 47 edges

## Surprising Connections (you probably didn't know these)
- `_assert_state()` --uses--> `GameConfig`  [INFERRED]
  Backend/app/api/auction.py → Backend/app/models/models.py
- `get_current_active_lab_admin()` --uses--> `User`  [INFERRED]
  Backend/app/api/auth.py → Backend/app/models/models.py
- `_user_by_login()` --uses--> `User`  [INFERRED]
  Backend/app/api/admin.py → Backend/app/models/models.py
- `_participant_id_from_users()` --uses--> `User`  [INFERRED]
  Backend/app/api/admin.py → Backend/app/models/models.py
- `_credential()` --uses--> `Team`  [INFERRED]
  Backend/app/api/admin.py → Backend/app/models/models.py

## Import Cycles
- None detected.

## Communities (101 total, 6 thin omitted)

### Community 0 - "get_password_hash"
Cohesion: 0.20
Nodes (19): register(), get_password_hash(), hash_password(), is_bcrypt_password_hash(), is_sha256_password_hash(), Detect every known bcrypt prefix for reset verification only., Compatibility name used by account creation; always emits salted SHA-256., apply_reset() (+11 more)

### Community 1 - "LabAdminApp.jsx"
Cohesion: 0.06
Nodes (52): useServerCountdown(), LeaderboardDashboard, LabAdminApp(), LabAdminBoard(), ready, team, waiting, clearLabAdminToken() (+44 more)

### Community 2 - "participant.py"
Cohesion: 0.07
Nodes (67): _dashboard_problem(), get_participant_dashboard(), member_utcnow(), put, _submission_realtime_payload(), update_submission(), _valid_github_url(), create_ps() (+59 more)

### Community 3 - "place_bid"
Cohesion: 0.22
Nodes (9): place_bid(), Request, Response, database_error_handler(), Request, bid_cooldown_rejection(), exception_handler, JSONResponse (+1 more)

### Community 4 - "ParticipantContext.tsx"
Cohesion: 0.16
Nodes (17): BiddingPanel(), BidIncrementForm(), accepted, Leaderboard(), QualificationBadge(), CoinBalance(), WildcardBiddingPage(), ParticipantContext (+9 more)

### Community 5 - "admin/services/api.js"
Cohesion: 0.13
Nodes (25): RoundControlPage(), WildcardControlPage(), initial, assignRoundOneProblem(), assignRoundWinners(), closeRoundBidding(), closeWildcardApplications(), closeWildcardSlotBidding() (+17 more)

### Community 6 - "devDependencies"
Cohesion: 0.05
Nodes (42): autoprefixer, allowScripts, esbuild@0.21.5, dependencies, lucide-react, react, react-dom, react-router-dom (+34 more)

### Community 7 - "Wildcard"
Cohesion: 0.19
Nodes (24): development_reset(), delete_ps(), delete, ExchangeRequest, LabAllocationState, Member, Immutable problem snapshot used by one live-event Wildcard selection., RegistrationImport (+16 more)

### Community 9 - "ParticipantApp.tsx"
Cohesion: 0.12
Nodes (28): dashboard, useParticipant, EventRoute(), ParticipantLayout(), StageNavigation(), CodingPage(), DashboardPage(), nextAction (+20 more)

### Community 10 - "record_event"
Cohesion: 0.11
Nodes (58): adjust_event_timer_admin(), pause_event_timer_admin(), resume_event_timer_admin(), end_bidding(), next_problem(), Close Round 1 for teams that already won a problem; move on., start_bidding(), start_preview() (+50 more)

### Community 11 - "ProblemStatement"
Cohesion: 0.23
Nodes (20): ProblemStatement, assigned_team_count(), change_round1_problem_assignment(), _display_number(), eligible_round1_teams(), _management_problem_payload(), _manual_description(), manually_assign_problem() (+12 more)

### Community 12 - "eventContent.ts"
Cohesion: 0.09
Nodes (21): formulaParts, RoyaltySection(), frames, RulesAuctionDemo(), RulesMotionBackground(), chapters, Five(), number() (+13 more)

### Community 13 - "App.jsx"
Cohesion: 0.09
Nodes (31): ActivityLogPage(), JudgingAdminPage(), LabAllocationAdminPage(), labels, ManagedUsersPage(), ParticipantCredentials(), Problems(), Teams() (+23 more)

### Community 15 - "wildcard.py"
Cohesion: 0.12
Nodes (56): apply_wildcard(), choose_final_problem(), close_wildcard_slot_bidding(), confirm_wildcard_slots(), decline_wildcard(), end_wildcard_final_choice(), end_wildcard_selection_turn(), get_wildcard_status() (+48 more)

### Community 17 - "Team"
Cohesion: 0.12
Nodes (44): process_expiry_cycle(), Persist one expiry cycle, then publish its committed authoritative snapshot., EventConfig, GameConfig, RoundControl, Team, finalize_slot_bidding(), Persist the deterministic top-N result and charge each winner once. Ordering is… (+36 more)

### Community 18 - "ui.tsx"
Cohesion: 0.16
Nodes (17): AdvanceButton(), Countdown(), format(), Modal(), ResultCard(), RoundOneComplete(), Avatar(), Button() (+9 more)

### Community 19 - "admin.py"
Cohesion: 0.06
Nodes (89): add_bid_cooldown(), _apply_event_state(), _assigned_problem_label(), _assignment_export_data(), _assignment_problem_values(), _assignment_workbook_response(), _broadcast_bid_cooldown(), confirm_registration_import() (+81 more)

### Community 20 - "NeonButton.tsx"
Cohesion: 0.15
Nodes (11): NeonButton(), NeonButtonProps, Size, sizeStyles, Variant, variantStyles, FinalCtaSection(), HeroSection() (+3 more)

### Community 22 - "compilerOptions"
Cohesion: 0.08
Nodes (25): compilerOptions, allowImportingTsExtensions, allowJs, checkJs, isolatedModules, jsx, lib, module (+17 more)

### Community 23 - "conftest.py"
Cohesion: 0.13
Nodes (24): _complete_login_claim(), login(), _lookup_login_candidate(), Request, Complete a PARTICIPANT login only., place_wildcard_bid(), _place_wildcard_bid_transaction(), Request (+16 more)

### Community 24 - "migrate_sqlite_to_postgres.py"
Cohesion: 0.20
Nodes (20): _arguments(), _coerce_value(), _counts(), _insertion_plan(), main(), migrate(), _model_tables(), _print_counts() (+12 more)

### Community 25 - "auction.py"
Cohesion: 0.12
Nodes (34): add_time(), _assert_state(), get_bid_history(), get_leaderboard(), pause_timer(), get, Session, Visible to all authenticated participants; cutoff is a display concern handled… (+26 more)

### Community 27 - "index.ts"
Cohesion: 0.08
Nodes (25): AllocatedLab(), ProblemPreview(), RoundOneBiddingPage(), RoundOnePreviewPage(), ParticipantContextValue, isCurrentUserLeader(), ParticipantPermissions, initial (+17 more)

### Community 28 - "Bid"
Cohesion: 0.22
Nodes (22): BidCooldownActive, finalize_round_one(), _place_round1_bid_transaction(), RuntimeError, Top N winners (N = EventConfig.round1_winner_count) for ONE problem statement.…, Commit one bid while holding only the auction row and bidding team row., Round1BidResult, Bid (+14 more)

### Community 30 - "User"
Cohesion: 0.17
Nodes (27): force_logout_participant(), Request, get_current_active_admin(), create_admin_user(), create_leaderboard_user(), _create_user(), list_admin_users(), list_leaderboard_users() (+19 more)

### Community 34 - "LabAssignment"
Cohesion: 0.09
Nodes (64): create_lab(), delete_lab(), generate_lab_allocation(), get_lab_allocation(), _lab_payload(), LabCreate, LabMoveRequest, LabUpdate (+56 more)

### Community 36 - "RuleCards.tsx"
Cohesion: 0.14
Nodes (8): iconMap, ruleIcon(), GOLD_TERMS, RuleList(), TimelineSection(), eventFlowSteps, RuleIconKey, RuleItem

### Community 37 - "judging.py"
Cohesion: 0.34
Nodes (14): get_admin_judging(), public_event_display(), _public_problem_payload(), publish_winners(), get, put, Response, Session (+6 more)

### Community 38 - "PublicLayout.tsx"
Cohesion: 0.21
Nodes (11): ScrollToHash(), ScrollToTop(), ContactSection(), footerNav, PublicFooter(), navItems, PublicNavbar(), eventContent (+3 more)

### Community 40 - "main.py"
Cohesion: 0.11
Nodes (22): get_db(), initialize_database(), Verify connectivity and schema without performing startup migrations.…, install_sensitive_query_redaction(), Any, Remove bearer tokens embedded in request/WebSocket query strings., _redact_query_tokens(), SensitiveQueryRedactionFilter (+14 more)

### Community 42 - "HomePage.tsx"
Cohesion: 0.18
Nodes (12): GlassCard(), GlassCardProps, glowStyles, SectionHeading(), SectionHeadingProps, AboutSection(), details, EventDetailsSection() (+4 more)

### Community 43 - "apiClient.ts"
Cohesion: 0.15
Nodes (22): AuthContext, AuthContextValue, AuthProvider(), LoginProbe(), protectedTree(), session, useAuth(), ProtectedRoute() (+14 more)

### Community 44 - "operations.py"
Cohesion: 0.22
Nodes (18): activity_log(), admin_health(), _check(), DevelopmentResetRequest, EventDataResetRequest, preflight(), BaseModel, get (+10 more)

### Community 46 - "App.tsx"
Cohesion: 0.22
Nodes (6): AdminRoute, App(), LabAdminRoute, ParticipantRoute, StyleBoundary(), StyleBoundaryProps

### Community 50 - "FastAPI"
Cohesion: 0.40
Nodes (3): More sockets than pool slots must not block ordinary HTTP requests., test_idle_websockets_do_not_exhaust_the_database_pool(), FastAPI

### Community 52 - "team.py"
Cohesion: 0.29
Nodes (9): get_current_user(), approve_team(), delete_team(), get_all_teams(), get_dashboard(), delete, get, put (+1 more)

### Community 53 - "AdminApplication.test.jsx"
Cohesion: 0.14
Nodes (19): fullLoadMocks, AdminApplication(), App(), Login(), clearToken(), getAdminConfig(), getAdminHealth(), getAdminState() (+11 more)

### Community 54 - "auth.py"
Cohesion: 0.16
Nodes (21): admin_login(), BidAuthClaims, decode_bid_auth_claims(), get_bid_auth_claims(), get_current_active_admin_or_lab_admin(), get_current_active_display(), get_current_active_lab_admin(), get_current_active_participant() (+13 more)

### Community 55 - "Settings"
Cohesion: 0.25
Nodes (4): field_validator, Route common PostgreSQL URL schemes through the installed psycopg 3 driver., Settings, BaseSettings

### Community 56 - "SQLite to PostgreSQL production migration"
Cohesion: 0.08
Nodes (23): 1. Provision PostgreSQL, 2. Enter a maintenance window and back up SQLite, 3. Install code and dependencies, 4. Create the PostgreSQL schema, 5. Validate and transfer data, 6. Switch the service, 7. Emergency rollback during cutover, SQLite to PostgreSQL production migration (+15 more)

### Community 58 - "compilerOptions"
Cohesion: 0.20
Nodes (9): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, strict, include (+1 more)

### Community 60 - "request"
Cohesion: 0.13
Nodes (24): RecoveryPage(), RegistrationImport(), confirmRegistrationImport(), developmentReset(), downloadRegistrationAssignments(), downloadRegistrationCredentials(), downloadRegistrationDemo(), downloadRegistrationSample() (+16 more)

### Community 61 - "20260829_0001_initial_schema.py"
Cohesion: 0.31
Nodes (7): _has_foreign_key(), _id_column(), Initial Bid to Build schema. Revision ID: 20260829_0001 Revises: None, Bring the known pre-Alembic production schema to this baseline. Alembic creates…, _reconcile_legacy_schema(), upgrade(), Column

### Community 63 - "deploy-release.sh"
Cohesion: 0.50
Nodes (8): cleanup_stage(), cleanup_temporary_files(), log(), prune_releases(), restore_service_configuration(), rollback(), set_stage(), deploy-release.sh script

### Community 64 - "ChangeProblem.jsx"
Cohesion: 0.23
Nodes (11): AssignmentDialog(), ChangeProblemPage(), completionBoundaries(), problemLabel(), ProblemSelect(), initial, updated, changeRoundOneAssignment() (+3 more)

### Community 67 - "Casino Hackathon Backend Service Architecture"
Cohesion: 0.40
Nodes (5): Auction Resolution Algorithm, Casino Hackathon Backend Service Architecture, FastAPI and SQLAlchemy Stack, JWT Role-Based Access Control, WebSocket Event Broadcasting

### Community 70 - "deploy-main1-remote.sh"
Cohesion: 0.67
Nodes (6): finish(), log(), restore_backend(), restore_frontend(), safe_remove_tree(), deploy-main1-remote.sh script

### Community 71 - "apiParticipantService.ts"
Cohesion: 0.08
Nodes (19): apiRequest(), ApiParticipantService, mapBidAcceptance(), mapDashboard(), mapProblem(), participantService, problemNumber(), RawBidAcceptance (+11 more)

### Community 79 - "SQLite to PostgreSQL Production Migration"
Cohesion: 0.40
Nodes (5): Alembic Schema Upgrade, Emergency Cutover Rollback, Database Maintenance Window, SQLite to PostgreSQL Production Migration, Transactional SQLite Data Transfer

### Community 80 - "AWS production deployment"
Cohesion: 0.29
Nodes (6): Atomic Symlink Promotion, Automatic deployment from `main1`, AWS production deployment, Legacy Immutable Release Path, Main1 Runner Deployment Pipeline, Rollback Snapshots

### Community 81 - "XIE Alumni Hackathon Public Frontend"
Cohesion: 0.40
Nodes (5): Casino Design System, Centralized Event Content, Presentation-Only Limitation, XIE Alumni Hackathon Public Frontend, React Vite Frontend Stack

### Community 82 - "XIE Alumni Hackathon — Bid to Build (Frontend)"
Cohesion: 0.11
Nodes (17): Accessibility, Available Scripts, Content Configuration, Current Limitations, Design System & Theme, Getting Started, Homepage Section Order, How to Replace a Homepage Image (+9 more)

### Community 84 - "Casino Gaming Hall"
Cohesion: 0.40
Nodes (5): ALUMINI — BID TO BUILD Signage, Casino Gaming Hall, Ornate Chandeliers, Roulette Tables, Slot Machines

### Community 86 - "Bid to Build Platform"
Cohesion: 0.40
Nodes (5): Automatic Main1 Deployment, Bid to Build Platform, Permanent Demo Accounts, Rollback by Revert Commit, Umbrella Frontend Consolidation

### Community 88 - "Main1 EC2 Deployment"
Cohesion: 0.50
Nodes (4): Main1 EC2 Deployment, Public Route Health Checks, Repository-Scoped Production Runner, Tested Frontend Payload

### Community 92 - "Luxury Casino Interior"
Cohesion: 0.50
Nodes (4): Luxury Casino Interior, Luxury Gaming Atmosphere, Roulette Tables, Slot Machines

### Community 102 - "Backend Runtime Dependencies"
Cohesion: 0.67
Nodes (3): Backend Runtime Dependencies, Backend Test Dependencies, PostgreSQL Async API Stack

### Community 103 - "Spade Favicon"
Cohesion: 0.67
Nodes (3): Gold Rounded Frame, Purple Dual-Triangle Mark, Spade Favicon

### Community 134 - "websockets.py"
Cohesion: 0.17
Nodes (27): _acquire_participant_session(), Atomically claim a free or stale participant credential., _authenticate_socket(), broadcast_presence_snapshot(), _heartbeat_frame(), Session, _touch_socket_identity(), _validate_socket_identity() (+19 more)

### Community 135 - "CodingRoundAdminPage"
Cohesion: 0.21
Nodes (11): applySubmissionUpdate(), CodingRoundAdminPage(), Dashboard(), formatTime(), closeSubmissions(), downloadFinalEventResults(), getAdminSubmissions(), openSubmissions() (+3 more)

### Community 136 - "ConnectionManager"
Cohesion: 0.12
Nodes (13): ConnectionManager, make_event(), Any, Test helper: wait until currently queued broadcasts reach client senders., Queue a committed hot-path event without waiting on client sockets., Coalesce participant connection churn into one authoritative refresh., Compatibility adapter for existing REST routes while keeping one envelope., In-memory fan-out for the single-instance hackathon deployment. (+5 more)

### Community 138 - "test_auth_role_separation.py"
Cohesion: 0.56
Nodes (9): _create_portal_users(), _login(), parametrize, test_admin_login_role_matrix(), test_lab_admin_login_role_matrix(), test_leaderboard_login_role_matrix(), test_participant_login_role_matrix(), test_participant_session_rejects_wrong_portal_tokens() (+1 more)

### Community 139 - "EventsPage.tsx"
Cohesion: 0.25
Nodes (7): dotStyles, ringStyles, Status, StatusBadge(), StatusBadgeProps, EventsPage(), heroDetails

### Community 142 - "load_participants.py"
Cohesion: 0.33
Nodes (3): main(), percentile(), Authenticated single-process load driver for participant sockets and bids.…

### Community 144 - "LabConfiguration.jsx"
Cohesion: 0.48
Nodes (6): emptyForm, LabConfiguration(), createLab(), deleteLab(), getLabs(), updateLab()

### Community 147 - "Bid to Build"
Cohesion: 0.33
Nodes (5): Automatic AWS Deployment, Bid to Build, Frontend Consolidation, Local verification, Optional Demo Accounts

### Community 150 - "Q: Which former-main files are obsolete versus current main1 application code and current test tooling?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Which former-main files are obsolete versus current main1 application code and current test tooling?, Source Nodes

### Community 151 - "Q: Audit and safely improve non-bidding performance on main1: images, route loading, redundant requests, async blocking, N+1 queries, startup, dependencies, and instrumentation."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Audit and safely improve non-bidding performance on main1: images, route loading, redundant requests, async blocking, N+1 queries, startup, dependencies, and instrumentation., Source Nodes

### Community 152 - "Q: Where should Wildcard final choice and Coding repository submission integrate without changing bidding mechanics?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Where should Wildcard final choice and Coding repository submission integrate without changing bidding mechanics?, Source Nodes

### Community 153 - "Q: How do admin wildcard application opening, wildcard lifecycle state, event transitions, coding submission availability, and admin wildcard tabs connect?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: How do admin wildcard application opening, wildcard lifecycle state, event transitions, coding submission availability, and admin wildcard tabs connect?, Source Nodes

### Community 154 - "Q: Where does Wildcard completion automatically start Coding, and what action should own the Coding transition?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Where does Wildcard completion automatically start Coding, and what action should own the Coding transition?, Source Nodes

### Community 155 - "Q: Trace and fix Coding duration persistence/open timer behavior; audit Wildcard-to-lab-allocation transaction safety, worker, WebSocket, and migrations."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Trace and fix Coding duration persistence/open timer behavior; audit Wildcard-to-lab-allocation transaction safety, worker, WebSocket, and migrations., Source Nodes

### Community 156 - "Q: Fix only the participant GitHub submission enablement bug: Coding leaders must not depend on dashboard.submissionsOpen."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Fix only the participant GitHub submission enablement bug: Coding leaders must not depend on dashboard.submissionsOpen., Source Nodes

### Community 157 - "Q: Why is participant GitHub submission still disabled after removing submissionsOpen from the Coding gate?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Why is participant GitHub submission still disabled after removing submissionsOpen from the Coding gate?, Source Nodes

### Community 158 - "Q: Investigate ONLY why the participant GitHub submission button is still not working."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Investigate ONLY why the participant GitHub submission button is still not working., Source Nodes

### Community 159 - "Q: Optimize the single-process BidToBuild architecture for 500-600 participants without changing business semantics"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Optimize the single-process BidToBuild architecture for 500-600 participants without changing business semantics, Source Nodes

### Community 160 - "BidToBuild Agent Rules"
Cohesion: 0.50
Nodes (3): Architecture, BidToBuild Agent Rules, Critical Rules

## Knowledge Gaps
- **237 isolated node(s):** `deploy.sh script`, `acceptance.sh script`, `setup-server.sh script`, `name`, `private` (+232 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 476 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `CodingPage.tsx` (3× useful, score=2.993843206) _(code changed — re-verify)_
- `permissions.ts` (3× useful, score=2.993843206) _(code changed — re-verify)_
- `RoundControl` (2× useful, score=1.977770991) _(code changed — re-verify)_
- `ParticipantContext` (2× useful, score=1.977770991) _(code changed — re-verify)_
- `EventConfig` (2× useful, score=1.975245777) _(code changed — re-verify)_
- `GameConfig` (2× useful, score=1.975245777) _(code changed — re-verify)_

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `get_password_hash`, `participant.py`, `websockets.py`, `Wildcard`, `record_event`, `ProblemStatement`, `test_auth_role_separation.py`, `wildcard.py`, `Team`, `admin.py`, `conftest.py`, `auction.py`, `Bid`, `LabAssignment`, `judging.py`, `main.py`, `operations.py`, `FastAPI`, `team.py`, `auth.py`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Why does `Team` connect `Team` to `get_password_hash`, `participant.py`, `websockets.py`, `Wildcard`, `record_event`, `ProblemStatement`, `test_auth_role_separation.py`, `wildcard.py`, `admin.py`, `conftest.py`, `auction.py`, `Bid`, `User`, `LabAssignment`, `judging.py`, `main.py`, `operations.py`, `FastAPI`, `team.py`, `auth.py`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `record_event()` connect `record_event` to `LabAssignment`, `participant.py`, `judging.py`, `websockets.py`, `Wildcard`, `ProblemStatement`, `operations.py`, `wildcard.py`, `Team`, `admin.py`, `auth.py`, `conftest.py`, `auction.py`, `Bid`, `User`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Are the 116 inferred relationships involving `User` (e.g. with `add_bid_cooldown()` and `adjust_event_timer_admin()`) actually correct?**
  _`User` has 116 INFERRED edges - model-reasoned connections that need verification._
- **Are the 86 inferred relationships involving `Team` (e.g. with `_assignment_export_data()` and `confirm_registration_import()`) actually correct?**
  _`Team` has 86 INFERRED edges - model-reasoned connections that need verification._
- **Are the 52 inferred relationships involving `RoundControl` (e.g. with `finalize_round_one()` and `_place_round1_bid_transaction()`) actually correct?**
  _`RoundControl` has 52 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deploy.sh script`, `acceptance.sh script`, `setup-server.sh script` to the rest of the system?**
  _237 weakly-connected nodes found - possible documentation gaps or missing edges._