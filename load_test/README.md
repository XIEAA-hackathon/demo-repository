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

On the 2-vCPU production-shaped host, repeat the mixed test with
`AUTH_BCRYPT_CONCURRENCY` set to 3, 4, and 6. Compare login queue/bcrypt timing
logs with dashboard/bid p95, WebSocket continuity, CPU, memory, PostgreSQL lock
waits/deadlocks, pool timeouts, and service restarts. Start with 4; keep the value that protects existing
traffic rather than the one that merely minimizes burst-login latency.
