# Bid to Build — 30 Team Full Simulation

## Summary

Overall result: PASS  
Ready for live event: Yes  
Teams: 30 imported event teams (the Admin readiness total is 31 because it correctly includes the permanent seeded Demo Team)  
Round 1 problems: 6  
Round 1 assignments: 30/30  
Wildcard applicants: 8  
Wildcard slots: 3  
Wildcard assignments: 3/3  
Submissions: 30/30

The run used an isolated SQLite database. No application code or production data was changed.

## Registration

PASS

- Imported exactly 30 teams and 30 leaders through the real XLSX registration endpoint.
- Downloaded the one-time XLSX credential output; all 30 leader-password cells were populated.
- Authenticated all 30 generated leader accounts through the normal login endpoint.
- A duplicate import created zero additional teams and preserved every team ID.

## Round 1

PASS

- Problem 1 winners: Team 01, Team 02, Team 03, Team 04, Team 05
- Problem 2 winners: Team 06, Team 07, Team 08, Team 09, Team 10
- Problem 3 winners: Team 11, Team 12, Team 13, Team 14, Team 15
- Problem 4 winners: Team 16, Team 17, Team 18, Team 19, Team 20
- Problem 5 winners: Team 21, Team 22, Team 23, Team 24, Team 25
- Problem 6 winners: Team 26, Team 27, Team 28, Team 29, Team 30
- Each team received exactly one Round 1 problem; no problem exceeded five winners.
- Fixed +5/+10/+25 increments worked. Cooldown, balance, assignment, and later-auction eligibility were enforced server-side.
- The live TV ranking updated without refresh; the Problem Display matched Problem #1, Adaptive Noise Cancellation, and its description.

## Wildcard

PASS

- Applicants: Team 01 through Team 08
- Top 3: Team 01, Team 02, Team 03
- Selection 3→2→1: PASS
- Rank #1 selected manually; a concurrent duplicate request produced exactly one assignment.
- Rank #2 timed out and received the first remaining frozen problem automatically.
- Rank #3 received one remaining choice and selected it manually with a fresh timer.
- All three Wildcard assignments were unique. Round 1 history remained populated, and Final Problem resolved to the Wildcard problem.
- All 27 non-Wildcard teams retained Round 1 as their Final Problem.

## Submission

PASS

- Submitted count: 30/30
- Each imported team had one stored submission with its final problem, submitter, timestamp, and GitHub URL.
- Team 01 updated the same submission record before close.
- New/update requests after close returned HTTP 409.

## Admin

PASS

- Admin login, Overview, Judging, saved-winner privacy, publication confirmation, and event-readiness checks worked.
- While the backend was stopped, the Overview preserved stale statistics and displayed “Cannot reach the event server.”
- After restart, the error cleared automatically, the completed event remained intact, and every readiness check returned READY.

## Leaderboard

PASS

- The authenticated live leaderboard showed the current Round 1 problem, five ordered bids, bid values, and timer with no Admin controls.
- A later Team 01 bid moved it to rank #1 at 105 coins without manual refresh.
- Problem Statement Display showed the exact Problem Number, Title, and Description.
- Saved-but-unpublished winners were not exposed.
- After publication, the existing leaderboard automatically showed Team 01, Team 02, and Team 03 as 1st/2nd/3rd without refresh.
- Admin, Participant, Problem Display, and Leaderboard browser consoles had no errors; only React Router future-version warnings appeared.

## Final Export

Rows: 30  
Round 1 assignments: 30  
Wildcard assignments: 3  
Null Wildcard rows: 27

The XLSX preserved the original Team Name, Leader Name, and Leader Email columns and included Round 1, Wildcard, and Final Problem number/title/description columns. Wildcard winners retained their Round 1 columns.

## Loophole Tests

| Test | Result | Notes |
|---|---|---|
| Assigned Round 1 team bids again | PASS | HTTP 409; no later bid recorded. |
| Same team bids from two clients during cooldown | PASS | HTTP 429; other teams remained unaffected. |
| Bid below base price | PASS | Arbitrary/low amount contract rejected with HTTP 422; only fixed increments are accepted. |
| Bid exceeding available balance | PASS | HTTP 400. |
| Duplicate registration import | PASS | Idempotent update; zero new teams and stable team IDs. |
| Duplicate Wildcard application | PASS | Idempotent confirmation; one application record. |
| Late Wildcard application | PASS | HTTP 409. |
| Non-applicant Wildcard bid | PASS | HTTP 403. |
| Rank #2 selects before Rank #1 | PASS | HTTP 409. |
| Two requests select the same Wildcard problem | PASS | Exactly one HTTP 200 and one HTTP 409. |
| Participant selects as timer expires | PASS | Targeted concurrency tests confirm exactly one manual-or-timeout outcome. |
| Submission after submissions close | PASS | HTTP 409. |
| Leaderboard account calls Admin endpoint | PASS | HTTP 403. |
| Participant calls Admin endpoint | PASS | HTTP 403. |
| Saved-but-unpublished winners requested publicly | PASS | Public payload contained no winners. |
| Old token used after logout | PASS | HTTP 401. |

Targeted Wildcard timeout/concurrency suite: 6 passed. Server restart preservation and UI disconnect/reconnect behavior also passed.

## Confirmed Problems

None.

## Final Verdict

Would this build safely run the hackathon right now? Yes.
