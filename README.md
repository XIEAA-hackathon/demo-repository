# Bid to Build

> A real-time hackathon auction and event operations platform built for the Bid2Build Hackathon organized by the XIE Alumni Committee.

Bid to Build brings team registration, problem auctions, virtual coin wallets, Wildcard qualification, physical lab allocation, coding submissions and judging into one coordinated system. Event administrators control the workflow while participants and authenticated event displays follow the same server-authoritative state.

## Built for Bid2Build

The platform was developed for the Bid2Build Hackathon organized by the XIE Alumni Committee. Its workflow reflects the operational needs of a live event: simultaneous bids, timed rounds, deterministic winner assignment, second-chance problem selection and clear transitions from auction to coding and results. It is an event operations system, not just a collection of CRUD screens.

## Key Features

- **Registration and access:** team/account management, CSV and Excel registration imports, credential administration, role-based authentication and participant session tracking.
- **Round 1 auctions:** problem-bank management, preview and bidding phases, configurable timers, wallet-aware bid validation, cooldowns, deterministic ranking and winner assignment.
- **Wildcard:** applications, slot bidding, persisted qualification ranks, timed problem-selection turns and final choice between Round 1 and Wildcard problems where applicable.
- **Assignments and labs:** administrative correction of current/final problems without rewriting auction history; capacity-aware automatic lab allocation with one team per effective problem per lab and explicit manual conflict overrides.
- **Coding and results:** team-leader GitHub repository submissions during coding, submission review, administrative winner selection and explicit result publishing.
- **Live operations:** WebSocket updates, authoritative HTTP reconciliation, authenticated leaderboard displays, timer controls and recovery/resynchronization tools.
- **Persistence:** PostgreSQL, SQLAlchemy transactions, wallet transaction records and versioned Alembic migrations.

## User Surfaces

| Surface | Responsibilities |
| --- | --- |
| Event Admin | Event state, teams, credentials, timers, problem banks, Round 1, Wildcard, assignments, submissions, judging and recovery |
| Participant / Team Leader | Sign in, follow event phases, bid, monitor the wallet, participate in Wildcard, inspect assigned/final problems and submit a repository; write actions require the team leader |
| Lab Admin | Restricted team details and lab allocation management, including controlled manual moves |
| Leaderboard Display | Authenticated live standings, finalized round outcomes and published event results |

The public site provides event information and entry points to the portals.

## Event Flow

```text
Registration
  → Round 1 preview → bidding → winner assignment
  → Wildcard applications → slot bidding → ranked problem selection
  → Final problem choice → lab allocation
  → Coding → repository submission → judging → published results
```

Round 1 preview, bidding and assignment repeat for the selected problems. Wildcard uses its own multi-stage control state; teams with both assignments receive a final-choice window. Lab allocation is an operation after final problems are available, not a separate event-state value. Coding opens through an explicit administrative transition.

## Architecture

```mermaid
flowchart TD
    subgraph Browser["Browser clients"]
        Public["Public site"]
        Participant["Participant portal"]
        Admin["Admin control center"]
        Lab["Lab Admin"]
        Display["Leaderboard display"]
        Frontend["React + Vite"]
    end
    Public --> Frontend
    Participant --> Frontend
    Admin --> Frontend
    Lab --> Frontend
    Display --> Frontend
    Frontend <-->|REST + WebSockets| API["FastAPI"]
    API --> ORM["SQLAlchemy"]
    ORM --> DB[("PostgreSQL")]
    Migrations["Alembic migrations"] -.->|Schema versions| DB
```

One frontend entry point serves all five surfaces. FastAPI owns event transitions and mutations; WebSockets deliver updates, and clients reconcile with persisted state over HTTP.

| Layer | Technology |
| --- | --- |
| Frontend | React 18, Vite 5, TypeScript / JavaScript, React Router, Lucide React, Tailwind CSS and scoped CSS |
| Backend | Python, FastAPI, Uvicorn, SQLAlchemy, Pydantic, JWT authentication and WebSockets |
| Database | PostgreSQL with the psycopg driver; Alembic for migrations |

## Engineering Details

- **Server-authoritative state:** event phases, deadlines, assignments and results are persisted on the backend. WebSocket delivery is paired with HTTP reconciliation so a missed message does not become the source of truth.
- **Deterministic bidding:** finalization ranks bids by amount descending, then the earlier timestamp at which the final amount was reached, then team ID. Eligibility and wallet balance are checked before assigning winners.
- **Transactional wallets:** winning charges and assignment changes share transaction boundaries. Signed wallet ledger records and operation uniqueness support auditability and idempotent settlement.
- **History versus current assignment:** `round1_problem_id` records the historical Round 1 result, `wildcard_problem_id` records the historical Wildcard result, and `ps_id` is the effective current/final problem. Administrative correction can change the effective assignment while preserving the original results.

See [PRODUCT.md](PRODUCT.md) for the product and engineering case study and [Database](Backend/database/README.md) for the complete schema reference.

## Running Locally

### Prerequisites

- Git
- Python 3.10+; validation was performed with Python 3.12
- Node.js and npm; validation was performed with Node.js 24
- PostgreSQL; the migration snapshot was validated with PostgreSQL 16

**PostgreSQL is required.** The runtime rejects SQLite database URLs. No production database, service or credentials are needed for local development.

### 1. Clone the repository

```bash
git clone https://github.com/XIEAA-hackathon/demo-repository.git
cd demo-repository
git switch main1
```

### 2. Create a PostgreSQL database

Start PostgreSQL and connect using your local PostgreSQL username and password. In `psql` or a database client, run:

```sql
CREATE DATABASE bidtobuild;
```

The account used by the backend must have permission to create and alter objects in this database.

### 3. Set up the backend environment

```bash
cd Backend
python -m venv .venv
```

Activate it in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on macOS/Linux:

```bash
source .venv/bin/activate
```

Then install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure local environment variables

From `Backend`, copy the tracked example.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Edit `Backend/.env` with your own local values:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/bidtobuild
SECRET_KEY=replace-with-a-long-local-development-secret

ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me
ADMIN_NAME=Event Admin

LAB_ADMIN_EMAIL=labadmin@example.com
LAB_ADMIN_PASSWORD=change-me-too
LAB_ADMIN_NAME=Lab Admin
```

These are placeholders, not shared credentials. Replace the passwords and signing secret; percent-encode special characters in the database URL. Keep `.env` outside Git. The Event Admin and single Lab Admin accounts are provisioned at startup when their password settings are supplied.

Optional demo accounts are configured in the same file using the `DEMO_*` and `LEADERBOARD_DISPLAY_*` settings in [Backend/.env.example](Backend/.env.example). Leave optional passwords blank unless you want demo provisioning. Event Admin can create participant and display accounts through the application.

### 5. Apply database migrations

From `Backend`, with the virtual environment active:

```bash
python -m alembic upgrade head
```

This creates or upgrades the PostgreSQL schema. Startup verifies the schema; it does not apply migrations automatically. Use Alembic, not `schema.sql`, to initialize or upgrade the application database.

### 6. Start the backend

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: [localhost:8000](http://localhost:8000)
- Swagger documentation: [localhost:8000/docs](http://localhost:8000/docs)
- Health check: [localhost:8000/health](http://localhost:8000/health)

### 7. Start the frontend

In a new terminal, from the repository root:

```bash
cd frontend-website
npm ci
npm run dev
```

The development frontend defaults to `http://localhost:8000` for API calls. Optional `VITE_API_URL` and `VITE_WS_URL` overrides belong in `frontend-website/.env`. If you use another browser origin, include it in backend `CORS_ORIGINS`.

| Surface | Local URL |
| --- | --- |
| Public site | [localhost:5173](http://localhost:5173/) |
| Event Admin | [localhost:5173/admin/login](http://localhost:5173/admin/login) |
| Participant | [localhost:5173/participant/login](http://localhost:5173/participant/login) |
| Lab Admin | [localhost:5173/lab-admin/login](http://localhost:5173/lab-admin/login) |
| Leaderboard display | [localhost:5173/leaderboard](http://localhost:5173/leaderboard) |

### Local validation

From `Backend`, with the environment configured:

```bash
python -m compileall -q app scripts migrations
python -c "from app.main import app; assert app"
python -m alembic current
```

From `frontend-website`:

```bash
npm run typecheck
npm run build
```

## Repository Structure

```text
demo-repository/
├── Backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── migrations/versions/
│   ├── database/
│   │   ├── README.md
│   │   └── schema.sql
│   ├── scripts/
│   ├── requirements.txt
│   └── .env.example
├── frontend-website/
│   ├── src/
│   │   ├── admin/
│   │   ├── participant/
│   │   ├── lab-admin/
│   │   ├── labs/
│   │   ├── leaderboard/
│   │   └── pages/public/
│   └── package.json
├── PRODUCT.md
├── README.md
└── LICENSE
```

## License

See [LICENSE](LICENSE).
