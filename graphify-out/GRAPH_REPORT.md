# Graph Report - demo-repository  (2026-09-10)

## Corpus Check
- Large corpus: 252 files · ~526,340 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 1809 nodes · 5555 edges · 134 communities (103 shown, 10 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 749 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Authentication and Sessions
- Participant API Contracts
- Response Schema Models
- Account Access Tests
- Participant Realtime State
- Admin Control Interface
- Frontend Dependencies
- Core Domain Models
- Wildcard Model Tests
- Participant Stage Routing
- Round Operations API
- Problem Assignment Service
- Rules Page Components
- Admin Operations Pages
- Load Test Authentication
- Wildcard Selection Service
- WebSocket Event Fanout
- Reliability Regression Tests
- Participant UI Components
- Admin Configuration API
- Visual UI Primitives
- Bid API Error Handling
- TypeScript Configuration
- Wildcard API Operations
- SQLite Migration Utility
- Event and Bid Timing
- Timer Reconciliation
- Participant Bidding Interface
- Round One Transactions
- Event Configuration Tests
- Managed User Accounts
- Participant Submission API
- Credential Export Pipeline
- Participant Wildcard Experience
- Assignment Export Pipeline
- Credential Management API
- Home Rules Cards
- Judging and Public Display
- Public Navigation Shell
- Test API Utilities
- Application Lifecycle
- Round One Load Test
- Marketing Page Sections
- Auction Timer Routes
- Recovery and Expiry
- Auction Behavior Tests
- Frontend Route Shell
- Balance Assignment Tests
- Team Credential Workflow
- Registration Import Pipeline
- Database Concurrency Tests
- Pytest Infrastructure
- Participant Session Tests
- Admin API Client
- Security Import Tests
- Runtime Configuration
- Sensitive Log Redaction
- Round Operations Tests
- Node TypeScript Configuration
- Simulation Audit Report
- Team Management API
- Initial Database Migration
- Password Lifecycle Tests
- AWS Release Script
- Problem Change Interface
- Evaluation Rules Content
- WebSocket Authentication
- WebSocket Test Page
- Assignment Export Tests
- Load Fixture Inspector
- Remote Deployment Script
- Managed Users Interface
- Wildcard Rules Content
- Round One Problem Catalog
- Event Integration Tests
- Socket Test Doubles
- Royalty Rules Content
- Simulation Output Previews
- End to End Audit
- PostgreSQL Migration Guide
- Immutable Release Automation
- Public Visual System
- Admin Timer Controls
- Hackathon Format Content
- Casino Hall Artwork
- Registration Account Preview
- Deployment Pipeline Overview
- Legacy AWS Deployment
- Main EC2 Deployment
- Desktop Admin Review
- Mobile Admin Review
- Wildcard Poster Artwork
- Casino Background Artwork
- Round One Poster
- External Problem Catalog
- Cross Round Problem Catalog
- Legacy Load Script
- Registration Roster Preview
- Wildcard Problem Catalog
- Round One TV Review
- Dependency Manifests
- Brand Image Assets
- Scoring Rules Content
- Load Testing Guide
- Simulation Workbook Builder
- Demo Environment Template
- Acceptance Test Script
- Server Setup Script
- Frontend HTML Shell
- Credential Status Guide
- Output Validation Script
- Final Problem Confirmation
- Submission Prototype

## God Nodes (most connected - your core abstractions)
1. `User` - 212 edges
2. `Team` - 186 edges
3. `ProblemStatement` - 133 edges
4. `RoundControl` - 103 edges
5. `GameConfig` - 88 edges
6. `request()` - 83 edges
7. `record_event()` - 76 edges
8. `get_password_hash()` - 68 edges
9. `EventConfig` - 64 edges
10. `Bid` - 61 edges

## Surprising Connections (you probably didn't know these)
- `Bid and Round Events` --semantically_similar_to--> `WebSocket Event Broadcasting`  [INFERRED] [semantically similar]
  websocket_test.html → Backend/README.md
- `seed()` --calls--> `get_password_hash()`  [INFERRED]
  work/prepare_local_load.py → Backend/app/core/security.py
- `seed()` --uses--> `User`  [INFERRED]
  work/prepare_local_load.py → Backend/app/models/models.py
- `seed()` --uses--> `ProblemStatement`  [INFERRED]
  work/prepare_local_load.py → Backend/app/models/models.py
- `seed()` --uses--> `RoundControl`  [INFERRED]
  work/prepare_local_load.py → Backend/app/models/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Simulation Registration and Assignment Export Flow** — graphify_out_converted_simulation_registration_30_teams_bea9309a_thirty_team_registration_dataset, graphify_out_converted_simulation_final_registration_export_2b6b3bed_participant_assignments_export, outputs_hackathon_simulation_20260825_hackathon_simulation_report_thirty_team_full_simulation [INFERRED 0.95]
- **Tested Production Deployment Paths** — _github_workflows_deploy_aws_legacy_manual_aws_deployment, _github_workflows_deploy_main1_ec2_deployment, deploy_aws_readme_aws_production_deployment [EXTRACTED 1.00]
- **Five-Step Build Process** — frontend_website_src_components_home_round2_final_problem_statement_confirmed, frontend_website_src_components_home_round2_functional_prototype, frontend_website_src_components_home_round2_prototype_submission, frontend_website_src_components_home_round2_alumni_evaluation, frontend_website_src_components_home_round2_scoring_with_royalty_bonus [EXTRACTED 1.00]

## Communities (134 total, 10 thin omitted)

### Community 0 - "Authentication and Sessions"
Cohesion: 0.06
Nodes (67): _acquire_participant_session(), BidAuthClaims, _complete_login_claim(), decode_bid_auth_claims(), get_bid_auth_claims(), get_current_active_participant(), get_current_user(), _issue_session() (+59 more)

### Community 1 - "Participant API Contracts"
Cohesion: 0.05
Nodes (42): formatTime(), LeaderboardDisplay(), formatTime(), ProblemStatementDisplay(), formatTime(), LeaderboardRow, PublicDisplay, RoundLeaderboard() (+34 more)

### Community 2 - "Response Schema Models"
Cohesion: 0.07
Nodes (61): _dashboard_problem(), get_participant_dashboard(), create_ps(), get_pss(), get_pss_admin(), get, post, put (+53 more)

### Community 3 - "Account Access Tests"
Cohesion: 0.07
Nodes (38): get_password_hash(), Compatibility name used by account creation; always emits salted SHA-256., Team, provision_demo_accounts(), Session, Create or repair the explicitly configured permanent system accounts., _set_password(), _login() (+30 more)

### Community 4 - "Participant Realtime State"
Cohesion: 0.09
Nodes (30): ParticipantContext, ParticipantContextValue, mapBidAcceptance(), mapDashboard(), mapProblem(), participantService, problemNumber(), RawBidAcceptance (+22 more)

### Community 5 - "Admin Control Interface"
Cohesion: 0.12
Nodes (43): Dashboard(), formatTime(), RegistrationImport(), RoundControlPage(), WildcardControlPage(), assignRoundOneProblem(), assignRoundWinners(), closeRoundBidding() (+35 more)

### Community 6 - "Frontend Dependencies"
Cohesion: 0.05
Nodes (40): autoprefixer, allowScripts, esbuild@0.21.5, dependencies, lucide-react, react, react-dom, react-router-dom (+32 more)

### Community 7 - "Core Domain Models"
Cohesion: 0.13
Nodes (33): activity_log(), admin_health(), _check(), development_reset(), DevelopmentResetRequest, EventDataResetRequest, preflight(), BaseModel (+25 more)

### Community 8 - "Wildcard Model Tests"
Cohesion: 0.12
Nodes (33): delete_ps(), delete, Immutable problem snapshot used by one live-event Wildcard selection., Wildcard, WildcardSelectionPool, _leader_headers(), Focused coverage for backend functionality synchronized from Pictures., test_round_one_bid_cooldown_and_positive_validation() (+25 more)

### Community 9 - "Participant Stage Routing"
Cohesion: 0.13
Nodes (24): EventRoute(), ParticipantLayout(), ProblemPreview(), StageNavigation(), CodingPage(), DashboardPage(), nextAction, roundLabel (+16 more)

### Community 10 - "Round Operations API"
Cohesion: 0.18
Nodes (34): assign_problem_manually(), assign_winners(), ChangeProblemAssignmentRequest, close_applications(), close_bidding(), _display_number(), end_round_one(), external_problem_sample() (+26 more)

### Community 11 - "Problem Assignment Service"
Cohesion: 0.17
Nodes (33): change_round_one_assignment(), put, assigned_team_count(), change_round1_problem_assignment(), _display_number(), eligible_round1_teams(), _management_problem_payload(), _manual_description() (+25 more)

### Community 12 - "Rules Page Components"
Cohesion: 0.09
Nodes (21): formulaParts, RoyaltySection(), frames, RulesAuctionDemo(), RulesMotionBackground(), chapters, Five(), number() (+13 more)

### Community 13 - "Admin Operations Pages"
Cohesion: 0.10
Nodes (28): ActivityLogPage(), JudgingAdminPage(), labels, ParticipantCredentials(), Problems(), RecoveryPage(), SubmissionAdminPage(), Teams() (+20 more)

### Community 14 - "Load Test Authentication"
Cohesion: 0.12
Nodes (28): authParams(), baseUrl, credentials, credentialsFile, login(), logout(), requireUsers(), tokenFrom() (+20 more)

### Community 15 - "Wildcard Selection Service"
Cohesion: 0.21
Nodes (30): as_utc(), _assign_locked_selection(), assign_wildcard_selection(), clear_selection_timer(), current_selection(), display_problem_number(), eligible_team_count(), finalize_slot_bidding() (+22 more)

### Community 16 - "WebSocket Event Fanout"
Cohesion: 0.13
Nodes (15): ConnectionManager, make_event(), Any, Queue a committed hot-path event without waiting on client sockets., Compatibility adapter for existing REST routes while keeping one envelope., In-memory fan-out for the single-instance hackathon deployment., Start one bounded, ordered fan-out worker for the current event loop., Wait until events already accepted by the bounded queue are delivered. (+7 more)

### Community 17 - "Reliability Regression Tests"
Cohesion: 0.14
Nodes (26): RoundControl, _leader(), _login(), parametrize, test_bid_in_fractional_final_second_is_accepted(), test_duplicate_leader_login_is_rejected_without_revoking_original_session(), test_expired_round_one_bid_rejects_without_running_expiry_transition(), test_leader_logout_revokes_old_token_and_relogin_works() (+18 more)

### Community 18 - "Participant UI Components"
Cohesion: 0.20
Nodes (14): AdvanceButton(), Countdown(), format(), Modal(), ResultCard(), RoundOneComplete(), Avatar(), Button() (+6 more)

### Community 19 - "Admin Configuration API"
Cohesion: 0.18
Nodes (28): add_bid_cooldown(), adjust_event_timer_admin(), _apply_event_state(), _broadcast_bid_cooldown(), force_logout_participant(), list_imported_participant_accounts(), _participant_account_payload(), ParticipantCredentialResetRequest (+20 more)

### Community 20 - "Visual UI Primitives"
Cohesion: 0.11
Nodes (18): GlassCard(), GlassCardProps, glowStyles, NeonButton(), NeonButtonProps, Size, sizeStyles, Variant (+10 more)

### Community 21 - "Bid API Error Handling"
Cohesion: 0.16
Nodes (25): place_bid(), Request, Response, place_wildcard_bid(), Request, database_error_handler(), Request, bid_cooldown_rejection() (+17 more)

### Community 22 - "TypeScript Configuration"
Cohesion: 0.08
Nodes (25): compilerOptions, allowImportingTsExtensions, allowJs, checkJs, isolatedModules, jsx, lib, module (+17 more)

### Community 23 - "Wildcard API Operations"
Cohesion: 0.19
Nodes (23): apply_wildcard(), close_wildcard_slot_bidding(), confirm_wildcard_slots(), decline_wildcard(), end_wildcard(), end_wildcard_selection_turn(), finalize_wildcard_alias(), get_wildcard_status() (+15 more)

### Community 24 - "SQLite Migration Utility"
Cohesion: 0.16
Nodes (22): _arguments(), _coerce_value(), _counts(), _insertion_plan(), main(), migrate(), _model_tables(), _print_counts() (+14 more)

### Community 25 - "Event and Bid Timing"
Cohesion: 0.17
Nodes (21): _assert_state(), get_bid_history(), get_leaderboard(), get, Visible to all authenticated participants; cutoff is a display concern handled…, Round1BidResult, _place_wildcard_bid_transaction(), GameConfig (+13 more)

### Community 26 - "Timer Reconciliation"
Cohesion: 0.16
Nodes (21): AdminApplication(), useServerCountdown(), getAdminConfig(), getAdminHealth(), getBidHistory(), getProblemStatements(), getTeams(), classifyApiStatus() (+13 more)

### Community 27 - "Participant Bidding Interface"
Cohesion: 0.19
Nodes (17): BID_INCREMENTS, BiddingPanel(), Leaderboard(), QualificationBadge(), CoinBalance(), BID_INCREMENTS, WildcardBiddingPage(), ParticipantProvider() (+9 more)

### Community 28 - "Round One Transactions"
Cohesion: 0.22
Nodes (20): BidCooldownActive, finalize_round_one(), _place_round1_bid_transaction(), RuntimeError, Top N winners (N = EventConfig.round1_winner_count) for ONE problem statement.…, Commit one bid while holding only the auction row and bidding team row., Bid, Add one auction attempt's actual winners; zero/manual assignments add nothing. (+12 more)

### Community 29 - "Event Configuration Tests"
Cohesion: 0.16
Nodes (15): EventConfig, Upgrade wallets created with the former 1,000-coin allocation once., upgrade_legacy_starting_coins(), Admin config API and event state transitions., test_event_state_transitions(), test_import_uses_event_config_starting_coins(), test_legacy_starting_coins_upgrade_is_idempotent(), test_round_controls() (+7 more)

### Community 30 - "Managed User Accounts"
Cohesion: 0.24
Nodes (19): create_admin_user(), create_leaderboard_user(), _create_user(), list_admin_users(), list_leaderboard_users(), _list_role(), ManagedPasswordReset, ManagedUserCreate (+11 more)

### Community 31 - "Participant Submission API"
Cohesion: 0.22
Nodes (20): close_submissions(), create_submission(), get_admin_submissions(), get_event_snapshot(), get_leaderboard(), get_my_submission(), get_participant_problems(), member_utcnow() (+12 more)

### Community 32 - "Credential Export Pipeline"
Cohesion: 0.19
Nodes (19): build_registration_credential_csv(), build_registration_credential_workbook(), _column_series(), _credential_export_frame(), _detect_columns(), _is_password_hash_header(), _is_valid_email(), _norm_header() (+11 more)

### Community 33 - "Participant Wildcard Experience"
Cohesion: 0.12
Nodes (17): SubmissionPage(), WildcardApplicationPage(), WildcardSelectionPage(), applyLeaderSelection(), getLeader(), getParticipantPermissions(), isCurrentUserLeader(), ParticipantPermissions (+9 more)

### Community 34 - "Assignment Export Pipeline"
Cohesion: 0.16
Nodes (19): _assigned_problem_label(), _assignment_export_data(), _assignment_problem_values(), _assignment_workbook_response(), download_final_event_results(), download_registration_assignments(), download_registration_credentials(), download_round_one_assignments() (+11 more)

### Community 35 - "Credential Management API"
Cohesion: 0.16
Nodes (18): confirm_registration_import(), create_team_credentials(), _credential(), _disabled_password_hash(), export_credentials_csv(), get_team_credentials(), _participant_id(), Team (+10 more)

### Community 36 - "Home Rules Cards"
Cohesion: 0.14
Nodes (8): iconMap, ruleIcon(), GOLD_TERMS, RuleList(), TimelineSection(), eventFlowSteps, RuleIconKey, RuleItem

### Community 37 - "Judging and Public Display"
Cohesion: 0.24
Nodes (16): get_current_active_admin(), get_current_active_display(), get_admin_judging(), public_event_display(), _public_problem_payload(), publish_winners(), get, post (+8 more)

### Community 38 - "Public Navigation Shell"
Cohesion: 0.22
Nodes (10): ScrollToHash(), ScrollToTop(), ContactSection(), footerNav, PublicFooter(), navItems, PublicNavbar(), PublicLayout() (+2 more)

### Community 39 - "Test API Utilities"
Cohesion: 0.26
Nodes (11): Api, close_assign(), fail(), load_state(), login(), phase_finish(), phase_publish(), phase_setup() (+3 more)

### Community 40 - "Application Lifecycle"
Cohesion: 0.19
Nodes (14): initialize_database(), Verify connectivity and schema without performing startup migrations. SQLite…, expiry_worker(), health_check(), lifespan(), process_expiry_cycle(), get, Persist one expiry cycle, then publish its committed authoritative snapshot. (+6 more)

### Community 41 - "Round One Load Test"
Cohesion: 0.12
Nodes (14): bid429, bid4xx, bid5xx, bidAttempts, bidDuration, BIDS_PER_USER, bidSuccess, COOLDOWN_SECONDS (+6 more)

### Community 42 - "Marketing Page Sections"
Cohesion: 0.21
Nodes (10): SectionHeading(), SectionHeadingProps, AboutSection(), details, EventDetailsSection(), FAQSection(), FinalCtaSection(), HeroSection() (+2 more)

### Community 43 - "Auction Timer Routes"
Cohesion: 0.30
Nodes (14): add_time(), end_bidding(), next_problem(), pause_timer(), post, Session, Close Round 1 for teams that already won a problem; move on., remove_time() (+6 more)

### Community 44 - "Recovery and Expiry"
Cohesion: 0.29
Nodes (14): post, Session, recovery_reload_state(), recovery_resume_timer(), recovery_resync_clients(), recovery_retry_transition(), recovery_snapshot(), Any (+6 more)

### Community 45 - "Auction Behavior Tests"
Cohesion: 0.37
Nodes (13): ProblemStatement, _activate_problem(), _import_and_get_client_state(), Round 1 auction: leader-only bidding, EventConfig rules, finalization., Import the 3-team CSV and return email/password for a leader and a member., test_bid_bounds_from_event_config(), test_bid_does_not_deduct_coins_immediately(), test_broadcast_queue_failure_after_commit_does_not_undo_bid() (+5 more)

### Community 46 - "Frontend Route Shell"
Cohesion: 0.21
Nodes (9): AdminRoute(), App(), Dashboard(), EventsPage(), HomePage(), LoginPage(), ParticipantRoute(), StyleBoundary() (+1 more)

### Community 47 - "Balance Assignment Tests"
Cohesion: 0.58
Nodes (12): _assign(), _control(), _problem(), _team(), test_admin_refresh_returns_persisted_problem_and_balance(), test_assignment_can_set_a_higher_final_balance(), test_assignment_can_set_a_lower_final_balance(), test_assignment_with_unchanged_final_balance() (+4 more)

### Community 48 - "Team Credential Workflow"
Cohesion: 0.41
Nodes (12): activate_round_one_problem(), create_team(), credentials_by_role(), login(), login_token(), team_payload(), test_admin_can_reset_password_once_without_storing_plaintext(), test_admin_generates_individual_accounts_and_shared_team_wallet() (+4 more)

### Community 49 - "Registration Import Pipeline"
Cohesion: 0.23
Nodes (12): import_registrations(), _participant_id_from_users(), preview_registration_import(), UploadFile, Resolve an imported participant ID from the preloaded user cache., Import participant identities and hash passwords supplied by the Admin., _store_credential_export(), _validate_registration_filename() (+4 more)

### Community 50 - "Database Concurrency Tests"
Cohesion: 0.32
Nodes (9): get_db(), session_factory(), _concurrent_login_app(), test_fifty_distinct_leaders_can_login_concurrently(), test_login_releases_database_connection_before_password_verification(), test_ten_simultaneous_logins_acquire_exactly_one_leader_session(), More sockets than pool slots must not block ordinary HTTP requests., test_idle_websockets_do_not_exhaust_the_database_pool() (+1 more)

### Community 51 - "Pytest Infrastructure"
Cohesion: 0.29
Nodes (11): admin_headers(), _clean_db(), client(), _create_admin(), _create_event_defaults(), _create_problem(), csv_bytes(), display_headers() (+3 more)

### Community 52 - "Participant Session Tests"
Cohesion: 0.42
Nodes (11): _headers(), _login(), _participant(), parametrize, test_admin_force_logout_revokes_session_and_allows_immediate_login(), test_first_login_invalid_credentials_active_rejection_and_reload(), test_logout_clears_all_session_fields_and_allows_immediate_login(), test_participant_cannot_force_logout_and_admin_login_still_replaces_admin_session() (+3 more)

### Community 53 - "Admin API Client"
Cohesion: 0.23
Nodes (10): App(), Login(), ApiError, clearToken(), getAdminState(), getToken(), hasToken(), login() (+2 more)

### Community 54 - "Security Import Tests"
Cohesion: 0.27
Nodes (9): get_event_state_admin(), User, participant_presence_payload(), Session, Return separate realtime-presence and authentication-session state.…, test_bcrypt_hashes_are_not_accepted_by_login(), test_registration_import_creates_sha256_leader_and_member_credentials(), test_registration_import_rejects_bcrypt_hash_input() (+1 more)

### Community 55 - "Runtime Configuration"
Cohesion: 0.22
Nodes (6): Route common PostgreSQL URL schemes through the installed psycopg 3 driver., Settings, test_common_postgresql_urls_use_installed_psycopg_driver(), test_explicit_psycopg_url_is_unchanged(), BaseSettings, field_validator

### Community 56 - "Sensitive Log Redaction"
Cohesion: 0.27
Nodes (8): install_sensitive_query_redaction(), Any, Remove bearer tokens embedded in request/WebSocket query strings., _redact_query_tokens(), SensitiveQueryRedactionFilter, test_plain_log_records_are_unchanged(), test_websocket_query_token_is_redacted_from_log_arguments(), LogRecord

### Community 57 - "Round Operations Tests"
Cohesion: 0.40
Nodes (8): login_headers_factory(), _problem_csv(), _team(), test_problem_import_validation_and_admin_authorization(), test_round_leaderboards_do_not_mix_rounds(), test_round_one_import_arbitrary_selection_and_team_lockout(), test_round_one_live_board_uses_current_problem_and_reflects_bid_updates(), test_wildcard_applications_and_separate_problem_pool()

### Community 58 - "Node TypeScript Configuration"
Cohesion: 0.20
Nodes (9): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, strict, include (+1 more)

### Community 59 - "Simulation Audit Report"
Cohesion: 0.22
Nodes (10): Final Problem Resolution, Participant Assignments Export, Round 1 Assignments, Wildcard Assignments, Thirty-Team Registration Dataset, Live Event Readiness, Round 1 Full Assignment, Submission Completion (+2 more)

### Community 60 - "Team Management API"
Cohesion: 0.33
Nodes (8): approve_team(), delete_team(), get_all_teams(), get_dashboard(), delete, get, put, Session

### Community 61 - "Initial Database Migration"
Cohesion: 0.31
Nodes (7): _has_foreign_key(), _id_column(), Initial Bid to Build schema. Revision ID: 20260829_0001 Revises: None, Bring the known pre-Alembic production schema to this baseline. Alembic creates…, _reconcile_legacy_schema(), upgrade(), Column

### Community 62 - "Password Lifecycle Tests"
Cohesion: 0.47
Nodes (8): _import(), _login(), _registration_csv(), _set_password(), test_imported_password_lifecycle_and_resets(), test_later_assignment_export_does_not_expose_imported_passwords(), test_new_account_with_blank_password_is_rejected_per_row(), test_sample_and_xlsx_import_include_and_preserve_password()

### Community 63 - "AWS Release Script"
Cohesion: 0.50
Nodes (8): cleanup_stage(), cleanup_temporary_files(), log(), prune_releases(), restore_service_configuration(), rollback(), set_stage(), deploy-release.sh script

### Community 64 - "Problem Change Interface"
Cohesion: 0.42
Nodes (8): AssignmentDialog(), ChangeProblemPage(), problemLabel(), ProblemSelect(), changeRoundOneAssignment(), downloadExternalProblemSample(), getRoundOneAssignments(), importExternalProblems()

### Community 65 - "Evaluation Rules Content"
Cohesion: 0.22
Nodes (9): Alumni Evaluation Score, Final Score, Final Score and Evaluation Poster, Highest Final Score Wins, Impact and Relevance 20 Percent, Presentation and Clarity 20 Percent, Royalty Bonus, Teamwork and Execution 20 Percent (+1 more)

### Community 66 - "WebSocket Authentication"
Cohesion: 0.50
Nodes (7): _authenticate_socket(), broadcast_presence_snapshot(), Session, _safe_close(), _touch_socket_identity(), websocket_auction(), db()

### Community 67 - "WebSocket Test Page"
Cohesion: 0.25
Nodes (8): Auction Resolution Algorithm, Casino Hackathon Backend Service Architecture, FastAPI and SQLAlchemy Stack, JWT Role-Based Access Control, WebSocket Event Broadcasting, Auction WebSocket, Bid and Round Events, Live Auction WebSocket Test

### Community 68 - "Assignment Export Tests"
Cohesion: 0.46
Nodes (7): _assignment_rows(), _assignment_workbook_rows(), _credentials(), _login(), _round_problem_csv(), test_top_five_lockout_base_prices_and_current_assignment_export(), _twelve_team_registration()

### Community 69 - "Load Fixture Inspector"
Cohesion: 0.25
Nodes (7): dataRows, emailDigests, emailIndex, normalizedHeaders, passwordIndex, sheet, used

### Community 70 - "Remote Deployment Script"
Cohesion: 0.67
Nodes (6): finish(), log(), restore_backend(), restore_frontend(), safe_remove_tree(), deploy-main1-remote.sh script

### Community 71 - "Managed Users Interface"
Cohesion: 0.29
Nodes (7): ManagedUsersPage(), createManagedAdminUser(), createManagedLeaderboardUser(), getManagedAdminUsers(), getManagedLeaderboardUsers(), resetManagedUserPassword(), resetManagedUsers()

### Community 72 - "Wildcard Rules Content"
Cohesion: 0.29
Nodes (7): Bonus Problem Statements, Limited Wild Cards, Scarcity Drives Bidding, Switch Your Challenge, Top Bidders Win, Round 1 Part 2 Wild Card Auction, Wild Card Auction Poster

### Community 73 - "Round One Problem Catalog"
Cohesion: 0.29
Nodes (7): Adaptive Noise Cancellation, Autonomous Logistics, Disaster Mapping, Emergency Communication, Round 1 Problem Catalog, Secure Field Network, Tropical Cyclone Prediction

### Community 74 - "Event Integration Tests"
Cohesion: 0.40
Nodes (3): _participant_headers(), test_participant_cannot_use_admin_state(), test_websocket_event_envelope_is_structured()

### Community 76 - "Royalty Rules Content"
Cohesion: 0.33
Nodes (6): Maximum Royalty Bonus of 10 Points, One Point per 100 AlumniCoins, Remaining AlumniCoins, Royalty Bonus, Royalty Bonus Poster, Save Coins to Score Higher

### Community 77 - "Simulation Output Previews"
Cohesion: 0.53
Nodes (6): Final Problem Assignments, Final Registration Export Preview, Leader Login Accounts, Round 1 Problem Assignments, 30-Team Registration Records, Wildcard Problem Assignments

### Community 78 - "End to End Audit"
Cohesion: 0.33
Nodes (6): Authenticated Browser Coverage Gap, BTB-001 Logout Revocation Defect, BTB-002 Wildcard Pool Contract Defect, BTB-004 Fixed Polling Defect, Core Event Workflow, Bid to Build End-to-End Test and Audit

### Community 79 - "PostgreSQL Migration Guide"
Cohesion: 0.40
Nodes (5): Alembic Schema Upgrade, Emergency Cutover Rollback, Database Maintenance Window, SQLite to PostgreSQL Production Migration, Transactional SQLite Data Transfer

### Community 80 - "Immutable Release Automation"
Cohesion: 0.40
Nodes (5): Atomic Symlink Promotion, AWS Production Deployment, Legacy Immutable Release Path, Main1 Runner Deployment Pipeline, Rollback Snapshots

### Community 81 - "Public Visual System"
Cohesion: 0.40
Nodes (5): Casino Design System, Centralized Event Content, Presentation-Only Limitation, XIE Alumni Hackathon Public Frontend, React Vite Frontend Stack

### Community 82 - "Admin Timer Controls"
Cohesion: 0.40
Nodes (5): TimerButtons(), addTime(), pauseTimer(), removeTime(), resumeTimer()

### Community 83 - "Hackathon Format Content"
Cohesion: 0.40
Nodes (5): Four Hour Duration, Functional Prototype or Solution, The Build, Round 2 The Build Poster, Two to Four Team Members

### Community 84 - "Casino Hall Artwork"
Cohesion: 0.40
Nodes (5): ALUMINI — BID TO BUILD Signage, Casino Gaming Hall, Ornate Chandeliers, Roulette Tables, Slot Machines

### Community 85 - "Registration Account Preview"
Cohesion: 0.60
Nodes (5): Leader Identity Records, Leader Login Email Column, Leader Password Column, Registration Credentials Preview, 30 Team Accounts

### Community 86 - "Deployment Pipeline Overview"
Cohesion: 0.40
Nodes (5): Automatic Main1 Deployment, Bid to Build Platform, Permanent Demo Accounts, Rollback by Revert Commit, Umbrella Frontend Consolidation

### Community 87 - "Legacy AWS Deployment"
Cohesion: 0.50
Nodes (4): Legacy Manual AWS Deployment, PostgreSQL 16 CI Service, Public Deployment Verification, Tested Immutable Release

### Community 88 - "Main EC2 Deployment"
Cohesion: 0.50
Nodes (4): Main1 EC2 Deployment, Public Route Health Checks, Repository-Scoped Production Runner, Tested Frontend Payload

### Community 89 - "Desktop Admin Review"
Cohesion: 0.50
Nodes (4): Assignment Capacity Summary, Change Problem Admin Dashboard, External Problem Statements Panel, Stale Live Data Warning

### Community 90 - "Mobile Admin Review"
Cohesion: 0.50
Nodes (4): Change Problem Mobile Layout, Collapsed Admin Navigation, Stacked External Problem Cards, Stale Data Status Banner

### Community 91 - "Wildcard Poster Artwork"
Cohesion: 0.50
Nodes (4): Crown Playing Card Emblem, Displayed Casino Chips and Cards, Luxury Casino Poster Scene, Purple Chandeliers

### Community 92 - "Casino Background Artwork"
Cohesion: 0.50
Nodes (4): Luxury Casino Interior, Luxury Gaming Atmosphere, Roulette Tables, Slot Machines

### Community 93 - "Round One Poster"
Cohesion: 0.50
Nodes (4): 1000 AlumniCoins, Problem Statement Auction, Round 1 Problem Statement Auction Poster, Top Five Bidders Win

### Community 94 - "External Problem Catalog"
Cohesion: 0.50
Nodes (4): AI Waste Sorting, Disaster Communication System, External Problem Catalog, Smart Parking Optimization

### Community 95 - "Cross Round Problem Catalog"
Cohesion: 0.50
Nodes (4): Disaster Response Problem Set, Round 1 Problem Catalog, Resilient Response Problem Set, Wildcard Problem Catalog

### Community 96 - "Legacy Load Script"
Cohesion: 0.50
Nodes (3): csv, options, users

### Community 97 - "Registration Roster Preview"
Cohesion: 0.67
Nodes (4): Leader Email Addresses, Registration Roster Preview, Team Leaders, 30 Registered Teams

### Community 98 - "Wildcard Problem Catalog"
Cohesion: 0.50
Nodes (4): Adaptive Relief Routing, Community Signal Mesh, Offline Medical Triage, Wildcard Problem Catalog

### Community 99 - "Round One TV Review"
Cohesion: 0.67
Nodes (3): Waiting for First Bid Empty State, Live Status Indicator, Round 1 Live Leaderboard

### Community 102 - "Dependency Manifests"
Cohesion: 0.67
Nodes (3): Backend Runtime Dependencies, Backend Test Dependencies, PostgreSQL Async API Stack

### Community 103 - "Brand Image Assets"
Cohesion: 0.67
Nodes (3): Gold Rounded Frame, Purple Dual-Triangle Mark, Spade Favicon

### Community 104 - "Scoring Rules Content"
Cohesion: 0.67
Nodes (3): Alumni Evaluation, Innovation Functionality Impact Technology and Presentation, Scoring with Royalty Bonus

### Community 105 - "Load Testing Guide"
Cohesion: 0.67
Nodes (3): Authentication Load Tests, Round 1 Concurrency Acceptance Test, WebSocket Delivery Observers

## Knowledge Gaps
- **266 isolated node(s):** `acceptance.sh script`, `setup-server.sh script`, `name`, `private`, `version` (+261 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 490 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `Security Import Tests` to `Authentication and Sessions`, `Response Schema Models`, `Account Access Tests`, `Core Domain Models`, `Wildcard Model Tests`, `Problem Assignment Service`, `Reliability Regression Tests`, `Admin Configuration API`, `Bid API Error Handling`, `Wildcard API Operations`, `SQLite Migration Utility`, `Event and Bid Timing`, `Round One Transactions`, `Event Configuration Tests`, `Managed User Accounts`, `Participant Submission API`, `Assignment Export Pipeline`, `Credential Management API`, `Judging and Public Display`, `Application Lifecycle`, `Recovery and Expiry`, `Auction Behavior Tests`, `Balance Assignment Tests`, `Team Credential Workflow`, `Registration Import Pipeline`, `Database Concurrency Tests`, `Pytest Infrastructure`, `Participant Session Tests`, `Round Operations Tests`, `Team Management API`, `Password Lifecycle Tests`, `WebSocket Authentication`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Why does `Team` connect `Account Access Tests` to `Authentication and Sessions`, `Response Schema Models`, `Core Domain Models`, `Wildcard Model Tests`, `Round Operations API`, `Problem Assignment Service`, `Wildcard Selection Service`, `Reliability Regression Tests`, `Admin Configuration API`, `Bid API Error Handling`, `Wildcard API Operations`, `SQLite Migration Utility`, `Event and Bid Timing`, `Round One Transactions`, `Event Configuration Tests`, `Participant Submission API`, `Assignment Export Pipeline`, `Credential Management API`, `Judging and Public Display`, `Auction Behavior Tests`, `Balance Assignment Tests`, `Team Credential Workflow`, `Registration Import Pipeline`, `Database Concurrency Tests`, `Participant Session Tests`, `Security Import Tests`, `Round Operations Tests`, `Team Management API`, `Assignment Export Tests`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `ProblemStatement` connect `Auction Behavior Tests` to `Response Schema Models`, `Account Access Tests`, `Core Domain Models`, `Wildcard Model Tests`, `Round Operations API`, `Problem Assignment Service`, `Wildcard Selection Service`, `Reliability Regression Tests`, `Admin Configuration API`, `Bid API Error Handling`, `Wildcard API Operations`, `Event and Bid Timing`, `Round One Transactions`, `Event Configuration Tests`, `Participant Submission API`, `Assignment Export Pipeline`, `Judging and Public Display`, `Recovery and Expiry`, `Balance Assignment Tests`, `Team Credential Workflow`, `Pytest Infrastructure`, `Round Operations Tests`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Are the 126 inferred relationships involving `User` (e.g. with `add_bid_cooldown()` and `adjust_event_timer_admin()`) actually correct?**
  _`User` has 126 INFERRED edges - model-reasoned connections that need verification._
- **Are the 109 inferred relationships involving `Team` (e.g. with `_assignment_export_data()` and `confirm_registration_import()`) actually correct?**
  _`Team` has 109 INFERRED edges - model-reasoned connections that need verification._
- **Are the 60 inferred relationships involving `ProblemStatement` (e.g. with `_assigned_problem_label()` and `_assignment_export_data()`) actually correct?**
  _`ProblemStatement` has 60 INFERRED edges - model-reasoned connections that need verification._
- **Are the 52 inferred relationships involving `RoundControl` (e.g. with `finalize_round_one()` and `_place_round1_bid_transaction()`) actually correct?**
  _`RoundControl` has 52 INFERRED edges - model-reasoned connections that need verification._