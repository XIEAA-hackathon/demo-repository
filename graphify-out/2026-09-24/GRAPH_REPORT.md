# Graph Report - demo-repository  (2026-09-24)

## Corpus Check
- 214 files · ~152,740 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1713 nodes · 5355 edges · 106 communities (82 shown, 6 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 689 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `04d7992e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- reset_credentials_sha256.py
- LabAdminApp.jsx
- participant.py
- RoundControl
- WildcardBiddingPage.tsx
- admin/services/api.js
- devDependencies
- request
- ParticipantApp.tsx
- ProblemStatement
- judging.py
- eventContent.ts
- App.jsx
- test_auth_role_separation.py
- wildcard.py
- import_registrations
- Team
- ui.tsx
- admin.py
- NeonButton.tsx
- load_participants.py
- compilerOptions
- CodingRoundAdminPage
- migrate_sqlite_to_postgres.py
- _post
- ParticipantContext.tsx
- index.ts
- get_current_active_admin
- initialize_database
- User
- confirm_registration_import
- WalletTransaction
- place_bid
- labs.py
- Q: Fix participant Wildcard turn and dedicated leaderboard final-results dropped-refresh races.
- RuleCards.tsx
- Q: Where is strict participant single-session behavior enforced?
- PublicLayout.tsx
- Q: Load-test the actual deployed BidToBuild website with at least 100 participants and report capacity, correctness, server, database, WebSocket, and session behavior.
- conftest.py
- _redact_query_tokens
- HomePage.tsx
- apiClient.ts
- websockets.py
- App.tsx
- main.py
- AdminApplication.test.jsx
- auth.py
- Settings
- SQLite to PostgreSQL production migration
- compilerOptions
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
- ConnectionManager
- EventsPage.tsx
- LabConfiguration.jsx
- Bid to Build
- test_websocket_pool.py
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
1. `User` - 183 edges
2. `Team` - 132 edges
3. `RoundControl` - 90 edges
4. `request()` - 89 edges
5. `ProblemStatement` - 88 edges
6. `record_event()` - 87 edges
7. `_post()` - 74 edges
8. `GameConfig` - 70 edges
9. `event_snapshot()` - 66 edges
10. `EventConfig` - 49 edges

## Surprising Connections (you probably didn't know these)
- `_assert_state()` --uses--> `GameConfig`  [INFERRED]
  Backend/app/api/auction.py → Backend/app/models/models.py
- `_user_by_login()` --uses--> `User`  [INFERRED]
  Backend/app/api/admin.py → Backend/app/models/models.py
- `_participant_id_from_users()` --uses--> `User`  [INFERRED]
  Backend/app/api/admin.py → Backend/app/models/models.py
- `_credential()` --uses--> `Team`  [INFERRED]
  Backend/app/api/admin.py → Backend/app/models/models.py
- `_credential()` --uses--> `User`  [INFERRED]
  Backend/app/api/admin.py → Backend/app/models/models.py

## Import Cycles
- None detected.

## Communities (106 total, 6 thin omitted)

### Community 0 - "reset_credentials_sha256.py"
Cohesion: 0.30
Nodes (14): is_bcrypt_password_hash(), Detect every known bcrypt prefix for reset verification only., apply_reset(), configured_system_passwords(), create_postgresql_backup(), CredentialResetError, main(), _normalized_email() (+6 more)

### Community 1 - "LabAdminApp.jsx"
Cohesion: 0.06
Nodes (57): useServerCountdown(), LabAdminApp(), LabAdminBoard(), alpha, ready, results, team, waiting (+49 more)

### Community 2 - "participant.py"
Cohesion: 0.07
Nodes (67): create_submission(), _dashboard_problem(), get_event_snapshot(), get_leaderboard(), get_my_submission(), get_participant_dashboard(), get_participant_problems(), member_utcnow() (+59 more)

### Community 3 - "RoundControl"
Cohesion: 0.12
Nodes (40): _leaderboard_payload(), public_round_leaderboard(), expiry_worker(), process_expiry_cycle(), Persist one expiry cycle, then publish its committed authoritative snapshot., EventConfig, GameConfig, RoundControl (+32 more)

### Community 4 - "WildcardBiddingPage.tsx"
Cohesion: 0.20
Nodes (13): BiddingPanel(), BidIncrementForm(), accepted, Leaderboard(), QualificationBadge(), CoinBalance(), WildcardBiddingPage(), applyBidDelta() (+5 more)

### Community 5 - "admin/services/api.js"
Cohesion: 0.13
Nodes (25): RoundControlPage(), WildcardControlPage(), initial, assignRoundOneProblem(), assignRoundWinners(), closeRoundBidding(), closeWildcardApplications(), closeWildcardSlotBidding() (+17 more)

### Community 6 - "devDependencies"
Cohesion: 0.05
Nodes (42): autoprefixer, allowScripts, esbuild@0.21.5, dependencies, lucide-react, react, react-dom, react-router-dom (+34 more)

### Community 7 - "request"
Cohesion: 0.13
Nodes (24): RecoveryPage(), RegistrationImport(), confirmRegistrationImport(), developmentReset(), downloadRegistrationAssignments(), downloadRegistrationCredentials(), downloadRegistrationDemo(), downloadRegistrationSample() (+16 more)

### Community 9 - "ParticipantApp.tsx"
Cohesion: 0.11
Nodes (29): dashboard, useParticipant, EventRoute(), ParticipantLayout(), StageNavigation(), CodingPage(), DashboardPage(), nextAction (+21 more)

### Community 10 - "ProblemStatement"
Cohesion: 0.12
Nodes (52): assign_problem_manually(), assign_winners(), change_round_one_assignment(), ChangeProblemAssignmentRequest, close_applications(), close_bidding(), _display_number(), end_round_one() (+44 more)

### Community 11 - "judging.py"
Cohesion: 0.21
Nodes (21): get_current_active_display(), get_admin_judging(), public_event_display(), _public_problem_payload(), publish_winners(), get, put, Response (+13 more)

### Community 12 - "eventContent.ts"
Cohesion: 0.08
Nodes (22): formulaParts, RoyaltySection(), frames, RulesAuctionDemo(), RulesMotionBackground(), chapters, Five(), number() (+14 more)

### Community 13 - "App.jsx"
Cohesion: 0.09
Nodes (31): ActivityLogPage(), JudgingAdminPage(), LabAllocationAdminPage(), labels, ManagedUsersPage(), ParticipantCredentials(), Problems(), Teams() (+23 more)

### Community 14 - "test_auth_role_separation.py"
Cohesion: 0.45
Nodes (12): _create_portal_users(), _login(), parametrize, test_admin_login_role_matrix(), test_duplicate_login_does_not_disconnect_first_participant_socket(), test_lab_admin_login_role_matrix(), test_leaderboard_login_role_matrix(), test_nonparticipant_relogin_behavior_is_unchanged() (+4 more)

### Community 15 - "wildcard.py"
Cohesion: 0.13
Nodes (58): apply_wildcard(), choose_final_problem(), confirm_wildcard_slots(), decline_wildcard(), end_wildcard(), end_wildcard_final_choice(), end_wildcard_selection_turn(), finalize_wildcard_alias() (+50 more)

### Community 16 - "import_registrations"
Cohesion: 0.11
Nodes (33): download_registration_assignments(), import_registrations(), _participant_id_from_users(), preview_registration_import(), Team, UploadFile, Resolve an imported participant ID from the preloaded user cache., Import participant identities and hash passwords supplied by the Admin. (+25 more)

### Community 17 - "Team"
Cohesion: 0.12
Nodes (34): BidCooldownActive, finalize_round_one(), _place_round1_bid_transaction(), RuntimeError, Top N winners (N = EventConfig.round1_winner_count) for ONE problem statement.…, Commit one bid while holding only the auction row and bidding team row., Round1BidResult, _place_wildcard_bid_transaction() (+26 more)

### Community 18 - "ui.tsx"
Cohesion: 0.16
Nodes (17): AdvanceButton(), Countdown(), format(), Modal(), ResultCard(), RoundOneComplete(), Avatar(), Button() (+9 more)

### Community 19 - "admin.py"
Cohesion: 0.11
Nodes (45): add_bid_cooldown(), adjust_event_timer_admin(), _apply_event_state(), _assignment_workbook_response(), _broadcast_bid_cooldown(), download_final_event_results(), download_registration_credentials(), download_round_one_assignments() (+37 more)

### Community 20 - "NeonButton.tsx"
Cohesion: 0.15
Nodes (11): NeonButton(), NeonButtonProps, Size, sizeStyles, Variant, variantStyles, FinalCtaSection(), HeroSection() (+3 more)

### Community 21 - "load_participants.py"
Cohesion: 0.33
Nodes (3): main(), percentile(), Authenticated single-process load driver for participant sockets and bids.…

### Community 22 - "compilerOptions"
Cohesion: 0.08
Nodes (25): compilerOptions, allowImportingTsExtensions, allowJs, checkJs, isolatedModules, jsx, lib, module (+17 more)

### Community 23 - "CodingRoundAdminPage"
Cohesion: 0.21
Nodes (11): applySubmissionUpdate(), CodingRoundAdminPage(), Dashboard(), formatTime(), closeSubmissions(), downloadFinalEventResults(), getAdminSubmissions(), openSubmissions() (+3 more)

### Community 24 - "migrate_sqlite_to_postgres.py"
Cohesion: 0.20
Nodes (20): _arguments(), _coerce_value(), _counts(), _insertion_plan(), main(), migrate(), _model_tables(), _print_counts() (+12 more)

### Community 25 - "_post"
Cohesion: 0.10
Nodes (57): add_time(), _assert_state(), end_bidding(), get_bid_history(), get_leaderboard(), next_problem(), pause_timer(), get (+49 more)

### Community 26 - "ParticipantContext.tsx"
Cohesion: 0.14
Nodes (19): AllocatedLab(), ProblemPreview(), RoundOneBiddingPage(), RoundOnePreviewPage(), ParticipantContext, ParticipantContextValue, ParticipantProvider(), RefreshRunner (+11 more)

### Community 27 - "index.ts"
Cohesion: 0.13
Nodes (13): isCurrentUserLeader(), ParticipantPermissions, EventState, FinalResults, FinalWinner, participantEventStates, RoundOneSettlement, Submission (+5 more)

### Community 28 - "get_current_active_admin"
Cohesion: 0.29
Nodes (9): get_current_active_admin(), approve_team(), delete_team(), get_all_teams(), get_dashboard(), delete, get, put (+1 more)

### Community 29 - "initialize_database"
Cohesion: 0.50
Nodes (4): initialize_database(), Verify connectivity and schema without performing startup migrations.…, Idempotently provision database-backed demo accounts. Credentials can be…, seed_demo()

### Community 30 - "User"
Cohesion: 0.14
Nodes (33): force_logout_participant(), Request, reset_participant_password(), create_admin_user(), create_leaderboard_user(), _create_user(), list_admin_users(), list_leaderboard_users() (+25 more)

### Community 31 - "confirm_registration_import"
Cohesion: 0.17
Nodes (16): confirm_registration_import(), create_team_credentials(), _credential(), _disabled_password_hash(), export_credentials_csv(), get_team_credentials(), _participant_id(), Return imported account identifiers and status without password material. (+8 more)

### Community 32 - "WalletTransaction"
Cohesion: 0.22
Nodes (19): _assigned_problem_label(), _assignment_export_data(), _assignment_problem_values(), list_imported_participant_accounts(), ExchangeRequest, Member, RegistrationImport, RegistrationImportRow (+11 more)

### Community 33 - "place_bid"
Cohesion: 0.13
Nodes (17): place_bid(), Request, Response, BidAuthClaims, decode_bid_auth_claims(), get_bid_auth_claims(), Signed identity claims; bidding transactions revalidate them in PostgreSQL., Validate a bidding JWT without opening a database session. (+9 more)

### Community 34 - "labs.py"
Cohesion: 0.08
Nodes (67): create_lab(), delete_lab(), generate_lab_allocation(), get_lab_allocation(), get_problem_results(), _lab_payload(), LabCreate, LabMoveRequest (+59 more)

### Community 35 - "Q: Fix participant Wildcard turn and dedicated leaderboard final-results dropped-refresh races."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Fix participant Wildcard turn and dedicated leaderboard final-results dropped-refresh races., Source Nodes

### Community 36 - "RuleCards.tsx"
Cohesion: 0.14
Nodes (8): iconMap, ruleIcon(), GOLD_TERMS, RuleList(), TimelineSection(), eventFlowSteps, RuleIconKey, RuleItem

### Community 37 - "Q: Where is strict participant single-session behavior enforced?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Where is strict participant single-session behavior enforced?, Source Nodes

### Community 38 - "PublicLayout.tsx"
Cohesion: 0.21
Nodes (11): ScrollToHash(), ScrollToTop(), ContactSection(), footerNav, PublicFooter(), navItems, PublicNavbar(), eventContent (+3 more)

### Community 39 - "Q: Load-test the actual deployed BidToBuild website with at least 100 participants and report capacity, correctness, server, database, WebSocket, and session behavior."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Load-test the actual deployed BidToBuild website with at least 100 participants and report capacity, correctness, server, database, WebSocket, and session behavior., Source Nodes

### Community 40 - "conftest.py"
Cohesion: 0.19
Nodes (18): _complete_login_claim(), Complete a PARTICIPANT login only., admin_headers(), _clean_db(), client(), _create_admin(), _create_event_defaults(), _create_problem() (+10 more)

### Community 41 - "_redact_query_tokens"
Cohesion: 0.50
Nodes (3): Any, _redact_query_tokens(), LogRecord

### Community 42 - "HomePage.tsx"
Cohesion: 0.20
Nodes (11): GlassCard(), GlassCardProps, glowStyles, SectionHeading(), SectionHeadingProps, AboutSection(), details, EventDetailsSection() (+3 more)

### Community 43 - "apiClient.ts"
Cohesion: 0.14
Nodes (24): AuthContext, AuthContextValue, AuthProvider(), LoginProbe(), protectedTree(), session, useAuth(), ProtectedRoute() (+16 more)

### Community 44 - "websockets.py"
Cohesion: 0.17
Nodes (25): _acquire_participant_session(), Atomically claim a free or stale participant credential., _authenticate_socket(), broadcast_presence_snapshot(), _heartbeat_frame(), Session, _touch_socket_identity(), _validate_socket_identity() (+17 more)

### Community 46 - "App.tsx"
Cohesion: 0.20
Nodes (7): AdminRoute, App(), LabAdminRoute, LeaderboardDashboard, ParticipantRoute, StyleBoundary(), StyleBoundaryProps

### Community 50 - "main.py"
Cohesion: 0.12
Nodes (22): create_ps(), delete_ps(), get_pss(), get_pss_admin(), delete, get, put, Session (+14 more)

### Community 53 - "AdminApplication.test.jsx"
Cohesion: 0.14
Nodes (19): fullLoadMocks, AdminApplication(), App(), Login(), clearToken(), getAdminConfig(), getAdminHealth(), getAdminState() (+11 more)

### Community 54 - "auth.py"
Cohesion: 0.15
Nodes (25): admin_login(), get_current_active_admin_or_lab_admin(), get_current_active_lab_admin(), get_current_active_participant(), get_current_user(), _issue_session(), lab_admin_login(), lab_admin_session() (+17 more)

### Community 55 - "Settings"
Cohesion: 0.25
Nodes (4): field_validator, Route common PostgreSQL URL schemes through the installed psycopg 3 driver., Settings, BaseSettings

### Community 56 - "SQLite to PostgreSQL production migration"
Cohesion: 0.08
Nodes (23): 1. Provision PostgreSQL, 2. Enter a maintenance window and back up SQLite, 3. Install code and dependencies, 4. Create the PostgreSQL schema, 5. Validate and transfer data, 6. Switch the service, 7. Emergency rollback during cutover, SQLite to PostgreSQL production migration (+15 more)

### Community 58 - "compilerOptions"
Cohesion: 0.20
Nodes (9): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, strict, include (+1 more)

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
Nodes (15): ApiParticipantService, mapBidAcceptance(), mapDashboard(), mapProblem(), problemNumber(), RawBidAcceptance, RawProblem, RawWinner (+7 more)

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

### Community 136 - "ConnectionManager"
Cohesion: 0.12
Nodes (13): ConnectionManager, make_event(), Any, Test helper: wait until currently queued broadcasts reach client senders., Queue a committed hot-path event without waiting on client sockets., Coalesce participant connection churn into one authoritative refresh., Compatibility adapter for existing REST routes while keeping one envelope., In-memory fan-out for the single-instance hackathon deployment. (+5 more)

### Community 139 - "EventsPage.tsx"
Cohesion: 0.25
Nodes (7): dotStyles, ringStyles, Status, StatusBadge(), StatusBadgeProps, EventsPage(), heroDetails

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
- **248 isolated node(s):** `deploy.sh script`, `acceptance.sh script`, `setup-server.sh script`, `name`, `private` (+243 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 493 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `ParticipantContext` (3× useful, score=2.834777098)
- `CodingPage.tsx` (3× useful, score=2.77777869)
- `permissions.ts` (3× useful, score=2.77777869)
- `GameConfig` (3× useful, score=2.763917048)
- `RoundControl` (2× useful, score=1.835036016)
- `EventConfig` (2× useful, score=1.832693047)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `reset_credentials_sha256.py`, `participant.py`, `RoundControl`, `ProblemStatement`, `judging.py`, `test_auth_role_separation.py`, `wildcard.py`, `import_registrations`, `Team`, `admin.py`, `test_websocket_pool.py`, `_post`, `get_current_active_admin`, `confirm_registration_import`, `WalletTransaction`, `labs.py`, `conftest.py`, `websockets.py`, `auth.py`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Why does `Team` connect `Team` to `reset_credentials_sha256.py`, `participant.py`, `RoundControl`, `ProblemStatement`, `judging.py`, `test_auth_role_separation.py`, `wildcard.py`, `import_registrations`, `admin.py`, `test_websocket_pool.py`, `_post`, `get_current_active_admin`, `User`, `confirm_registration_import`, `WalletTransaction`, `labs.py`, `conftest.py`, `websockets.py`, `main.py`, `auth.py`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `record_event()` connect `admin.py` to `WalletTransaction`, `labs.py`, `participant.py`, `ProblemStatement`, `judging.py`, `websockets.py`, `wildcard.py`, `import_registrations`, `Team`, `auth.py`, `_post`, `User`, `confirm_registration_import`?**
  _High betweenness centrality (0.015) - this node is a cross-community bridge._
- **Are the 120 inferred relationships involving `User` (e.g. with `add_bid_cooldown()` and `adjust_event_timer_admin()`) actually correct?**
  _`User` has 120 INFERRED edges - model-reasoned connections that need verification._
- **Are the 87 inferred relationships involving `Team` (e.g. with `_assignment_export_data()` and `confirm_registration_import()`) actually correct?**
  _`Team` has 87 INFERRED edges - model-reasoned connections that need verification._
- **Are the 52 inferred relationships involving `RoundControl` (e.g. with `finalize_round_one()` and `_place_round1_bid_transaction()`) actually correct?**
  _`RoundControl` has 52 INFERRED edges - model-reasoned connections that need verification._
- **Are the 52 inferred relationships involving `ProblemStatement` (e.g. with `_assigned_problem_label()` and `_assignment_export_data()`) actually correct?**
  _`ProblemStatement` has 52 INFERRED edges - model-reasoned connections that need verification._