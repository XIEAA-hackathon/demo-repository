# Bid to Build — End-to-End Test & Audit

## 1. Executive Summary

Overall status: **PARTIAL — core event workflow is operational, with two medium-severity defects and browser-authenticated UI coverage incomplete.**

Demo ready: **Yes, for a supervised demo after reviewing the known issues.**

Core workflow operational: **Yes.** Registration, Round 1, Wildcard auction/ranking, sequential assignment, public leaderboards, submissions, and authorization were exercised end to end.

Critical blockers: **None (P0: 0).**

High-priority blockers: **None classified P1.** Before a real event, fix token revocation and resolve the three-slot problem-pool contract.

| Area | Score |
| ---- | ----- |
| Admin workflow | 8.3/10 |
| Participant workflow | 8.0/10 |
| Round 1 | 9.4/10 |
| Wildcard | 8.1/10 |
| Leaderboard | 9.0/10 |
| Registration Import | 9.5/10 |
| Submission | 9.5/10 |
| Authorization | 8.8/10 |
| Persistence/Realtime | 8.8/10 |
| Overall readiness | 8.6/10 |

## 2. Test Environment

| Item | Value |
| ---- | ----- |
| Requested frontend | `http://localhost:5173` — HTTP 200 |
| Requested backend | `http://localhost:8000` — `/health` HTTP 200 |
| FastAPI docs | `http://localhost:8000/docs` — HTTP 200 |
| Stateful rehearsal frontend | `http://127.0.0.1:5175`, started with `VITE_API_URL=http://localhost:8001` |
| Stateful rehearsal backend | `http://localhost:8001` using the same application code |
| Reason for isolated ports | The existing port-8000 database was already at `WILDCARD_APPLICATION` with Round 1 closed. A supported rewind returned HTTP 409. The existing database and services were left untouched. |
| Browser | Connected Chrome session for public boards; API clients for authenticated role simulation |
| Database | SQLite; isolated `qa_e2e_1787419000.db` for the full rehearsal |
| Branch | `main1` |
| Commit | `6b16ea3` |
| Product code changes during test pass | None |

## 3. Test Accounts

Passwords are intentionally omitted.

| Identifier | Role | Source |
| ---------- | ---- | ------ |
| `admin.demo@bidtobuild.example.com` | Admin | Configured demo account |
| `leader@demo.example.com` | Team leader | Configured demo account |
| `alice@example.com` | Team Alpha leader | Exact downloaded demo CSV |
| `david@example.com` | Team Beta leader | Exact downloaded demo CSV |
| `qa-a-*` through `qa-h-*` | Team leaders | Registration-import-generated accounts |
| `current-*` | Team leader | Current single-step registration import endpoint |

Generated passwords were used only in memory and in the one-time credential output. They are not included in this report.

## 4. Admin Test Results

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Frontend/backend/docs reachability | All endpoints reachable | 5173, 8000 health, and 8000 docs returned HTTP 200 | PASS |
| Admin authentication | Demo Admin can authenticate | `/login` returned HTTP 200 and Admin APIs accepted the token | PASS |
| Browser session persistence | Refresh retains authenticated Admin UI | Authenticated browser entry was not performed because password entry in the controlled browser required separate sensitive-data confirmation | BLOCKED |
| Admin dashboard/navigation | Required event and management sections visible | Source configuration matches Overview, Round 1, Wildcard, Submission, Teams, Problems, Registration import, and Leaderboard; authenticated browser UI was not re-entered | PARTIAL |
| Obsolete navigation | Participant ID, Bidding Status, Judging, Results absent from Admin navigation | No such Admin navigation items are configured | PASS |
| Logout | Logout makes the active token unusable | `/logout` returned 200, but the same bearer token still accessed `/participant/dashboard` with 200 | FAIL |
| Registration import | Exact demo CSV processes successfully | Current import endpoint created/updated teams and produced one-time credentials | PASS |
| Round 1 problem import | Five rows import exactly | 5 imported; numbers 1–5 and statements A–E matched | PASS |
| Arbitrary problem selection | Admin can choose problem #3 | Problem ID/number 3 selected and shown to participants | PASS |
| Timer controls | Start, pause, resume, add, remove, refresh persist | All returned 200; paused time stayed at 13 seconds across a two-second wait; add/remove changed server remaining time | PASS |
| Round 1 bidding/assignment | Admin sees activity and assigns winners | Ten bids visible; top five assigned and charged exactly once | PASS |
| Wildcard controls | Import, applications, slots, auction, selection operate | Full server-side flow completed | PASS |
| Submission monitor | All teams and counters shown through API | 11 teams; counters changed from 0 submitted to 1 submitted | PASS |

## 5. Participant Test Results

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Generated leader login | Newly generated leader credentials authenticate | Multiple generated leaders, including the current import flow, logged in with HTTP 200 | PASS |
| Correct identity/team | Leader token resolves correct role and team | Role was `leader`; team-specific dashboard returned | PASS |
| Admin isolation | Leader cannot access Admin controls | Admin API attempts returned HTTP 403 | PASS |
| Round 1 preview | Current arbitrary problem is visible | Participant dashboard showed Test Round 1 Problem C | PASS |
| Round 1 bid | Valid bid accepted | Ten generated leaders placed valid bids; HTTP 200 | PASS |
| Assigned-team lockout | Assigned team cannot bid again | Assigned Team Alpha received HTTP 409; eligible Team Beta bid returned 200 | PASS |
| Wildcard application | Eligible leader can apply | Four applications returned 200 and Admin count became 4 | PASS |
| Duplicate/late application | No duplicate; late request rejected | Duplicate returned idempotent 200 message; post-close apply returned 409 | PASS |
| Wildcard selection UI | Current leader sees and selects available problems | Server order/security was exercised directly; the authenticated participant browser page was not entered | PARTIAL |
| Submission | Leader creates and updates one repository | POST 201, PUT 200, one Admin row retained | PASS |
| Participant browser session | Login, refresh, route rendering, logout | API behavior exercised; authenticated browser session not entered | BLOCKED |

## 6. Cross-Role Synchronization Tests

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Wildcard application count | Participant application increments Admin count | Four participant applications produced Admin applied count 4 | PASS |
| Round 1 live bidding | Participant bids appear to Admin | Admin highest bid/team updated through 200 coins | PASS |
| Round leaderboard | New bid appears without refresh | Public board changed to Team Alpha, 200 coins without reload | PASS |
| Wildcard live ranking | Participant update appears publicly | Team D changed from 350 to 375 within approximately 2.3 seconds | PASS |
| Problem selection turn | Only current rank can select; next turn advances | Early rank requests returned 409; successful selections advanced rank and completed Wildcard | PASS |
| Submission status | Participant submission updates Admin monitor | Pending changed to Submitted with URL, submitter, and timestamps | PASS |

## 7. Registration Import Tests

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Demo download | Exact application demo CSV downloads | HTTP 200, two data rows | PASS |
| Demo headers | Headers match importer | All seven expected source columns matched | PASS |
| Exact file import | Downloaded bytes upload without repair | Current single-step import returned HTTP 200 | PASS |
| Team/member creation | Teams, leaders, members created | Team/account counts matched the input | PASS |
| Credential columns | Original columns plus leader login/password | Output retained all original columns and appended both required columns | PASS |
| One-time download | Token can be used only once | First download 200; token reuse 404 | PASS |
| Generated login | Exported credentials authenticate | Generated leader login returned 200 | PASS |
| Re-import idempotency | No duplicates or password reset | Team count unchanged; 0 created, 2 updated, 0 new accounts; old passwords still worked | PASS |
| Existing marker | Re-import uses `EXISTING ACCOUNT` | Both output rows contained the marker | PASS |
| Plaintext exposure | Password only in one-time output | No password bodies appeared in FastAPI access logs or browser console; database uses password hashes | PASS |
| CSV roundtrip | CSV input returns CSV | Output parsed as CSV and retained two source rows | PASS |
| XLSX preservation | XLSX input returns XLSX | Covered by targeted integration test suite | PASS |

## 8. Round 1 Tests

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Sample problem CSV | Downloadable | HTTP 200 with `Problem Number,Problem Statement` | PASS |
| Five-problem import | No missing/duplicate rows | Exactly five problems, 1–5 | PASS |
| Arbitrary selection | Problem #3 selectable | Selected successfully | PASS |
| Default timers | Preview/bidding default 60 seconds | Both configuration values were 60 | PASS |
| Configurable timers | Admin can alter defaults | Changed to 75/80 through Admin API, then restored to 60/60 | PASS |
| Pause/resume | Countdown freezes and resumes | Paused value remained 13 for two seconds | PASS |
| Add/remove time | Server time adjusts | Remaining changed to 31 after add and 20 after remove/read delay | PASS |
| Refresh persistence | State and time do not restart | Repeated participant/dashboard reads retained state and server timestamp progression | PASS |
| Bidding/balance | Bid accepted; charge occurs at assignment | Bid did not prematurely deduct; winner balance 1000→800 on 200-coin assignment | PASS |
| Public board | Round 1 only and live | No Admin shell; 2-second polling updated the board | PASS |
| Assignment | Top N stored | Top five stored on problem #3; second auction assigned one eligible team | PASS |
| Assigned-team lockout | Backend rejects another bid | HTTP 409 with explicit assigned-team message | PASS |
| End Round 1 | Cannot end incomplete problem; ends once complete | First end attempt 409; after assigning current auction it returned 200 | PASS |
| Post-end bidding | Rejected | HTTP 409 | PASS |

## 9. Wildcard Tests

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Separate problem import | Five Wildcard problems separate from Round 1 | Round 1 count 5 and Wildcard count 5 with distinct statements | PASS |
| Application default | 60 seconds | Initial participant remaining time was 59 seconds after request latency | PASS |
| Apply/decline | Persist and update Admin counts | Applied 4, declined 1 | PASS |
| Duplicate apply | No duplicate record | Idempotent 200 message; Admin count remained 4 | PASS |
| Late apply | Server rejects after close | HTTP 409 | PASS |
| Slot validation | Reject 10, accept 3 | 10 returned 422 with max 4; 3 returned 200 | PASS |
| One slot auction | Bid is for rank, not problem | Four `/wildcard/bid?amount=` requests; no problem ID required | PASS |
| Top-N ordering | 500, 450, 400 qualify; lower bid does not | Ranks 1–3 qualified; rank 4 eliminated | PASS |
| Winner charging | Only qualified teams charged once | Balances 1000→500, 550, 600; rank 4 stayed 1000 | PASS |
| Public board | Wildcard only and live | No Round 1 entries; 375 update appeared without reload | PASS |
| Three-slot choice pool | Rank choices should be 3→2→1 | With five imported problems, backend exposed 5→4→3 (and two unused at completion) | FAIL |
| Selection order | #1, then #2, then #3 | Early/out-of-turn requests returned 409; ordered requests returned 200 | PASS |
| Selection security | Reject early, non-qualified, duplicate, same/unavailable problem | All invalid requests rejected with 409 | PASS |
| Completion | Third selection completes Wildcard | Status became `COMPLETE`; problem IDs were unique | PASS |
| Problem history | Round 1, Wildcard, and final fields remain distinct | Live separate-team cases passed; dual-history same-team case passed targeted integration test | PASS |

## 10. Submission Tests

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Admin list | All teams and counters | 11 total, initially 0 submitted/11 pending | PASS |
| Open submissions | Participant UI state/API enabled | Admin open returned 200 | PASS |
| Final problem | Wildcard winner sees Wildcard; normal winner sees Round 1 | Wildcard Problem A and Test Round 1 Problem C respectively | PASS |
| Create | Valid public GitHub URL accepted | HTTP 201 | PASS |
| Metadata | Timestamp and submitter stored | Admin row contained submitted/updated timestamps and `A Leader` | PASS |
| Update | Same team row updated | HTTP 200; one submitted row with updated URL | PASS |
| Close | Admin closes window | HTTP 200 | PASS |
| New after close | Rejected | HTTP 409 | PASS |
| Update after close | Rejected | HTTP 409 | PASS |

## 11. Authorization Tests

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Participant problem selection Admin API | 403 | 403 | PASS |
| Participant problem import | 403 | 403 | PASS |
| Participant timer control | 403 | 403 | PASS |
| Participant start bidding | 403 | 403 | PASS |
| Participant close Round 1 | 403 | 403 | PASS |
| Participant open applications | 403 | 403 | PASS |
| Participant slot configuration | 403 | 403 | PASS |
| Participant open submissions | 403 | 403 | PASS |
| Unauthenticated mutations | 401 | Four representative Admin mutations returned 401 | PASS |
| Logout revocation | Logged-out token rejected | Token remained accepted with HTTP 200 | FAIL |

## 12. Persistence Tests

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Round 1 preview refresh | Active problem/timer restore | Repeated dashboard reads retained problem #3 and server countdown | PASS |
| Paused timer refresh | Remaining time stays fixed | 13 seconds before and after two-second wait | PASS |
| Round 1 bidding refresh | Bids/highest value persist | Admin and public endpoints retained ranking | PASS |
| Wildcard application refresh | Application persists | Admin count and duplicate response confirmed persistence | PASS |
| Wildcard bidding refresh | Ranking persists | Admin/public rankings matched after repeated reads | PASS |
| Wildcard selection refresh | Turn/assignments persist | Admin selection payload advanced after each transaction | PASS |
| Submissions-open refresh | Open flag and row persist | Repeated Admin/participant reads retained state and row | PASS |
| Full browser refresh while authenticated | Local-storage session and route restore | Not executed in controlled browser | BLOCKED |

## 13. Realtime/Leaderboard Tests

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Round 1 public route | TV board, no Admin shell | Rendered six-row paginated board without sidebar | PASS |
| Round 1 update | Automatic | New 200-coin bid appeared without reload | PASS |
| Wildcard public route | Wildcard-only ranking/top N | Four Wildcard rows and “Top 3” copy | PASS |
| Wildcard update delay | Automatic near polling interval | 350→375 observed after approximately 2.3 seconds | PASS |
| Browser errors | No CORS/React runtime errors | No errors; only React Router v7 future warnings | PASS |
| Polling load | Avoid unnecessary repeated requests | Both boards continued polling every two seconds after phase completion | PARTIAL |

## 14. Import Validation Tests

| Test | Expected | Actual | Status |
| ---- | -------- | ------ | ------ |
| Empty registration file | Readable rejection | HTTP 400: no rows | PASS |
| Wrong registration headers | Readable rejection | HTTP 400 listing missing required columns | PASS |
| Duplicate leader email | Detected without commit | Preview HTTP 200 with explicit row-level duplicate errors | PASS |
| Missing leader email | Readable rejection | HTTP 400 with row/field | PASS |
| Unsupported registration type | Rejected | HTTP 400 | PASS |
| Empty problem file | Rejected | HTTP 400 | PASS |
| Wrong problem headers | Rejected | HTTP 400 | PASS |
| Duplicate problem numbers | Rejected | HTTP 422 with row number | PASS |
| Missing problem statement | Rejected | HTTP 422 with row number | PASS |
| Unsupported problem type | Rejected | HTTP 400 | PASS |

## 15. Confirmed Bugs

### BTB-001

ID: BTB-001  
Severity: P2 Medium  
Area: Authentication / session lifecycle  
Title: Logged-out bearer token remains valid

Observed behavior: `/logout` returns HTTP 200 and sets `user.session_id = None`, but the same bearer token continues to access participant APIs with HTTP 200.

Expected behavior: The token used for logout should be rejected immediately.

Steps to reproduce:

1. Log in and store the bearer token.
2. `POST /logout` with that token.
3. `GET /participant/dashboard` with the same token.
4. Observe HTTP 200 instead of 401.

Root cause: `Backend/app/api/auth.py:get_current_user` checks mismatch only when `user.session_id` is truthy. Logout sets it to `None`, causing the revocation check to be skipped.

Affected files: `Backend/app/api/auth.py`; frontend logout clients clear local storage but cannot revoke a copied token.

Recommended fix: Require token `session_id` to equal the database value, and reject when the database value is null. Add logout-revocation tests for Admin and participant tokens.

Confidence: High.

### BTB-002

ID: BTB-002  
Severity: P2 Medium  
Area: Wildcard problem selection  
Title: Three-slot flow exposes all remaining imported problems instead of a 3→2→1 pool

Observed behavior: With three slots and five available Wildcard problems, the selection payload/count progressed 5→4→3, leaving two unused problems at completion.

Expected behavior: The requested rehearsal contract specifies 3→2→1 choices for three slots.

Steps to reproduce:

1. Import five Wildcard problems.
2. Confirm three slots and qualify three teams.
3. Close bidding and inspect current-turn problem availability.
4. Select one problem per rank and observe counts 5, 4, 3.

Root cause: `available_wildcard_problems()` returns every unassigned round-2 problem. `Backend/app/api/participant.py` and `Backend/app/services/wildcard_service.py` expose the full list/count without limiting it to remaining selection positions.

Affected files: `Backend/app/services/wildcard_service.py`, `Backend/app/api/participant.py`, `Backend/app/api/wildcard.py`, `frontend-website/src/participant/pages/WildcardSelectionPage.tsx`.

Recommended fix: Decide the authoritative contract. If 3→2→1 is required, snapshot or deterministically limit the selection pool to slot count at bidding close, then reduce it after each choice. Extend the three-slot test to import five problems.

Confidence: High for observed mismatch; product decision required for desired behavior.

### BTB-003

ID: BTB-003  
Severity: P3 Low  
Area: Admin Wildcard UX  
Title: Disabled slot confirmation does not identify which prerequisite is zero

Observed behavior: The original Admin screen showed “Maximum now: 0” and a disabled button. Runtime data had zero applicants and zero Wildcard problems, but the UI did not enumerate those blockers.

Expected behavior: Explain that at least one application and one imported Wildcard problem are required, with direct recovery actions.

Root cause: `frontend-website/src/admin/App.jsx` derives one `maxSlots` value and disables the action without rendering the applicant/problem breakdown.

Affected files: `frontend-website/src/admin/App.jsx`, optionally its scoped CSS.

Recommended fix: Show “0 applied teams · 0 Wildcard problems” and links/actions to reopen applications and import problems. Do not weaken backend validation.

Confidence: High.

### BTB-004

ID: BTB-004  
Severity: P3 Low  
Area: Performance / realtime  
Title: Public leaderboards continue fixed two-second polling after phase completion

Observed behavior: Two open public boards generated continuous repeated GET requests throughout later phases and after completion.

Expected behavior: Live polling should slow or stop when the relevant phase is complete or the tab is hidden.

Root cause: `RoundLeaderboard.tsx` uses a fixed polling interval without terminal-state or page-visibility backoff.

Affected files: `frontend-website/src/pages/RoundLeaderboard.tsx`.

Recommended fix: Pause on `document.hidden`, add terminal-state backoff, and resume immediately on visibility change.

Confidence: High.

### BTB-005

ID: BTB-005  
Severity: P3 Low  
Area: Registration API consistency  
Title: Legacy preview/confirm credential export differs from the current one-time import contract

Observed behavior: The exposed legacy `/preview` + `/confirm` flow returns no existing-account credential rows on re-import, while `/credentials.csv` returns JSON account content without the original registration columns. The current frontend correctly uses the newer single-step endpoint.

Expected behavior: Publicly exposed registration workflows should have an unambiguous, consistent contract or be clearly deprecated.

Root cause: Both legacy and current registration import flows remain registered with different response/export semantics.

Affected files: `Backend/app/api/admin.py`, `frontend-website/src/admin/services/api.js`.

Recommended fix: Deprecate/remove the legacy routes after compatibility review, or document them explicitly and align their naming/content types.

Confidence: High.

## 16. UI/UX Problems

1. Slot confirmation at maximum zero is technically correct but not actionable; see BTB-003.
2. Authenticated Admin and participant browser flows were not entered in the controlled browser, so responsive/session UI behavior remains a coverage gap rather than a confirmed defect.
3. Public boards render cleanly and without Admin chrome, but fixed polling continues indefinitely.
4. Browser console showed only React Router v7 future warnings; no runtime or CORS errors were observed.

## 17. Backend/API Problems

1. Session revocation check is bypassed when logout sets `session_id` to null (BTB-001).
2. The three-slot problem-pool contract is not enforced when more problems than slots are imported (BTB-002).
3. Legacy and current registration APIs expose divergent credential export behavior (BTB-005).
4. No unexpected HTTP 500 responses were observed. Tested negative 401/403/409/422 responses were expected and readable.

## 18. Data Integrity Problems

No duplicate assignment, duplicate Wildcard selection, duplicate team/user, duplicate submission, or incorrect charge was observed.

| Integrity check | Result | Status |
| --------------- | ------ | ------ |
| Unique Round 1 assignments | Top-N stored once | PASS |
| Assigned-team bid lockout | HTTP 409 | PASS |
| Unique Wildcard problems | Three distinct IDs | PASS |
| Wrong-turn/same-problem selection | HTTP 409 | PASS |
| Round 1 history retention | Dual-history integration test passed | PASS |
| Final problem selection | Wildcard for Wildcard winner; Round 1 for normal winner | PASS |
| Registration duplicate prevention | Team count unchanged on re-import | PASS |
| Password reset prevention | Original generated passwords remained valid | PASS |
| Submission uniqueness | One row updated in place | PASS |
| Balance correctness | Charges matched winning bids; eliminated team unchanged | PASS |

## 19. Security / Authorization Findings

- Admin mutation authorization is consistently enforced: participants received 403 and unauthenticated clients received 401.
- Participant role separation was verified with registration-generated leader accounts.
- Password hashes are stored; plaintext was limited to one-time credential output.
- One-time credential tokens became unusable after download.
- Logout token revocation is defective (BTB-001) and should be fixed before a real event.

## 20. Performance / Realtime Issues

- Round 1 and Wildcard boards both updated automatically near the two-second interval.
- No failed polling, CORS errors, React exceptions, or WebSocket errors were observed.
- Fixed polling from multiple open boards produced a large volume of repeated successful GET requests. Add visibility/terminal-state backoff (BTB-004).
- Targeted backend suite completed 20 tests in 24.87 seconds with 371 warnings, mainly dependency/deprecation warnings and an SQLAlchemy table-sort cycle warning.

## 21. TOP 10 PROBLEMS

1. **P2 — Logged-out tokens remain valid** (confirmed).
2. **P2 — Three-slot selection exposes 5→4→3 rather than 3→2→1** (confirmed contract mismatch).
3. **P3 — Slot confirmation maximum zero lacks actionable prerequisite details** (confirmed UX issue).
4. **P3 — Public boards poll indefinitely after completion/while not needed** (confirmed performance issue).
5. **P3 — Legacy registration endpoints conflict with the current one-time export contract** (confirmed API consistency issue).
6. **Coverage risk — Authenticated browser login/refresh/logout was not exercised**; API and source behavior were tested instead.
7. **Operational risk — Existing event state has no supported rewind**, so rehearsals require an isolated database/environment.
8. **Concurrency coverage risk — Live selection attacks were sequential**; transactional/uniqueness behavior was additionally covered by integration tests, not a high-load race harness.
9. **Maintenance risk — 371 warnings in the targeted suite**, including timezone-naive `utcnow()` and dependency deprecations.
10. **Maintenance risk — React Router future warnings** appear on every tested frontend route.

## 22. Recommended Fix Order

### Fix before demo

1. Decide and enforce the three-slot problem-pool contract (BTB-002), or update the event rule/test expectation explicitly.
2. Improve the max-zero slot prerequisite message (BTB-003) so the Admin can recover without guessing.
3. Perform one manual authenticated Admin/participant browser rehearsal using the real display browsers.

### Fix before live event

1. Fix server-side logout revocation and add regression tests (BTB-001).
2. Add a concurrent same-problem/rank selection stress test against the production database engine.
3. Define a supported rehearsal/reset procedure that cannot be used accidentally during a live event.
4. Add polling visibility/terminal-state backoff (BTB-004).

### Can defer

1. Deprecate or align legacy registration endpoints (BTB-005).
2. Resolve React Router future warnings.
3. Migrate timezone-naive timestamp calls and dependency deprecations.

## 23. FINAL LIVE-EVENT VERDICT

1. Can an Admin run the event from start to submission? **Yes through the tested APIs; authenticated browser UI still needs one manual rehearsal.**
2. Can participants complete the workflow without manual DB intervention? **Yes in the isolated clean environment.**
3. Does Round 1 work? **Yes.**
4. Does Round 1 leaderboard update correctly? **Yes, automatically.**
5. Does Wildcard application work? **Yes.**
6. Does Wildcard slot bidding work? **Yes.**
7. Does ranked problem selection work correctly? **Order/security/data integrity: yes. Three-slot visible-pool contract: no; it exposed all five problems.**
8. Is problem history preserved? **Yes in targeted integration coverage; live separate Round 1/Wildcard/final fields were also correct.**
9. Do submissions work? **Yes.**
10. Is registration CSV roundtrip reliable? **Yes, including exact demo CSV, one-time credentials, generated login, and re-import marker.**
11. Are authorization rules enforced? **Yes for role/unauthenticated access; logout revocation is not.**
12. Will page refresh/reconnect break the event? **Server state/timers persisted across repeated reads; authenticated full-browser refresh remains untested.**
13. Would you run a real hackathon using this build today? **No. Fix logout revocation, settle the three-slot problem-pool rule, and complete one authenticated multi-browser rehearsal first.**

### Result Counts

PASS: 115  
FAIL: 3  
PARTIAL: 3  
BLOCKED: 3  
P0: 0  
P1: 0  
P2: 2  
P3: 3
