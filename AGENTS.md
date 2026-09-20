# BidToBuild Agent Rules

This repository contains a live event platform.

Production behavior must be protected.

## Architecture

Frontend:
- React
- Vite

Backend:
- FastAPI
- Uvicorn

Database:
- SQLite

Realtime:
- WebSockets

Production:
- Nginx
- systemd-managed backend

## Critical Rules

Never run a second production Uvicorn process.

Never modify business logic simply for performance.

Preserve:

- Round 1 flow
- wildcard flow
- problem allocation
- bidding behavior
- timers
- authentication
- session restrictions
- lab allocation
- leaderboard behavior
- submission behavior

Optimization must target computational, database, network,
rendering, memory, build or delivery inefficiencies.

Do not:

- push automatically
- deploy automatically
- restart production
- modify secrets
- rewrite large systems without strong justification

Prefer:

measure -> isolate -> optimize -> test -> review