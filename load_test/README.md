# Authentication load tests

These k6 scenarios intentionally contain no live URL or credentials. Copy
`credentials.example.json` to an ignored local file, populate it with dedicated
test accounts, and pass both the target and credentials explicitly.

PowerShell examples:

```powershell
$env:BASE_URL = 'http://127.0.0.1:8000'
$env:CREDENTIALS_FILE = './credentials.json'
$env:USERS = '40'
k6 run .\login-burst.js
```

Run `login-burst.js` with `USERS=25`, `40`, `50`, `75`, and `100`.
`mixed-workload.js` defaults to 15 active API users, 10 live WebSockets, and a
40-user login burst; use `BURST_USERS=100` for the stress case. Bids are disabled
unless `BID_PROBLEM_ID` is explicitly supplied for a disposable active event.
`login-logout-cycle.js` cleans up each successful test session.
`same-account-race.js` requires exactly one 200 and one 409.

For the Round 1 concurrency acceptance test, provide 100 unique bidder accounts
in `loginUsers` plus dedicated observer accounts in `activeWebSocketUsers`.
Set the active problem id explicitly, then run every required level:

```powershell
$env:BASE_URL = 'https://bidtobuild.dev/api'
$env:CREDENTIALS_FILE = './credentials.json'
$env:BID_PROBLEM_ID = '<active disposable problem database id>'
$env:USERS = '40';  k6 run .\r1-bid.js
$env:USERS = '80';  k6 run .\r1-bid.js
$env:USERS = '100'; k6 run .\r1-bid.js
```

`r1-bid.js` synchronizes the first bid, keeps the five-second client pacing,
measures only successful bids in its latency trend, classifies cooldown and
business-rule rejections separately, and uses dedicated WebSocket observers to
measure committed bid delivery latency.

On the production-shaped host, compare login and bid latency with WebSocket
continuity, CPU, memory, PostgreSQL lock waits/deadlocks, pool timeouts, and
service restarts. Password verification is constant-cost SHA-256 and has no
bcrypt worker-pool tuning.

## Wildcard mixed load

`wildcard-load.js` models the live Wildcard pressure point: 80 unique participant
WebSockets, 5–15 unique active bidders, and a synchronized dashboard-refresh
cohort. Use three disjoint credential groups so the single-session contract is
not itself the test bottleneck. The event must already be in `BIDDING_OPEN`, all
bidder accounts must have applied, and the target must be disposable.

```powershell
$env:BASE_URL = 'http://127.0.0.1:8000'
$env:CREDENTIALS_FILE = './credentials.json'
$env:SOCKETS = '80'
$env:BIDDERS = '10'
$env:DASHBOARD_USERS = '20'
k6 run .\wildcard-load.js

$env:SOCKETS = '150'
$env:BIDDERS = '15'
$env:DASHBOARD_USERS = '40'
k6 run .\wildcard-load.js
```

The k6 summary reports request success plus p50/p95/p99 for bid and dashboard
latency, unexpected 401s, 5xx responses, WebSocket disconnects, and received
events. Correlate the same timestamps with backend transaction logs and
PostgreSQL `pg_stat_activity` / `pg_locks` for pool usage and lock waits; those
server-side measurements cannot be inferred reliably by a client-only script.
