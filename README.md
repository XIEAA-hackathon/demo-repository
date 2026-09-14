# Bid to Build

Bid to Build is a FastAPI/SQLAlchemy event backend with one React/Vite umbrella frontend.

| Surface | Active source | Production path |
|---|---|---|
| Public website | `frontend-website/src/pages/public` | `/` and `/event` |
| Participant portal | `frontend-website/src/participant` | `/participant/*` |
| Admin control center | `frontend-website/src/admin` | `/admin/*` |
| Lab Admin allocation | `frontend-website/src/lab-admin` | `/lab-admin/*` |
| Leaderboard display | `frontend-website/src/leaderboard` | `/leaderboard` |
| FastAPI backend | `Backend` | `/api/` and `/ws/` |

`frontend-website` is the only production frontend entrypoint and build. Retired
split-frontend implementations are preserved on the full-backup `main` branch and
are intentionally absent from production `main1`.

## Frontend Consolidation

Previously, the public website, participant portal, and admin control center were
three separate Vite applications. Production now uses one entrypoint, one router,
and one build from `frontend-website`.

| Route | Destination |
|---|---|
| `/` and `/event` | Public website |
| `/admin/*` | Admin login and control center |
| `/lab-admin/login` and `/lab-admin/*` | Dedicated Lab Admin login and allocation board |
| `/participant/*` | Participant login and event workflow |
| `/leaderboard` | Authenticated event leaderboard display |
| `/api/*` | FastAPI HTTP API |
| `/ws/*` | FastAPI WebSocket endpoints |

## Local verification

```bash
cd Backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m compileall -q app scripts migrations
.venv/bin/python -c "from app.main import app; assert app"

cd ../frontend-website
npm ci
npm run typecheck
npm run build
```

Before running Alembic or starting the backend, copy `Backend/.env.example` to
`Backend/.env` and set `DATABASE_URL` to an existing development PostgreSQL database.
Settings load that file regardless of the shell's working directory. An empty
database requires `alembic upgrade head` before startup. On Windows use
`.venv\Scripts\python.exe -m pip`, `.venv\Scripts\python.exe -m alembic`, and
`.venv\Scripts\python.exe -m uvicorn` in place of the Unix environment commands.
Production frontends use same-origin `/api`; database credentials remain backend-only.

Both bidding rounds accept whole-number increments from 1 to 25. The input previews
the next bid and remaining wallet balance; the server calculates the accepted price
from the latest bid and enforces the configured cooldown (five seconds by default).
Run backend tests with `TEST_DATABASE_URL` pointing to a disposable database and
`pip install -r requirements-dev.txt`, then `pytest tests`. Frontend checks are
`npm test`, `npm run typecheck`, and `npm run build`.

## Optional Demo Accounts

Copy [Backend/.env.example](Backend/.env.example) to `Backend/.env`, then edit these backend-only environment variables:

```dotenv
DEMO_ADMIN_EMAIL=admin.demo@bidtobuild.example.com
DEMO_ADMIN_PASSWORD=replace-with-a-demo-password
DEMO_LEADER_EMAIL=leader@demo.example.com
DEMO_LEADER_PASSWORD=replace-with-a-demo-password
DEMO_TEAM_NAME=Demo Team
LEADERBOARD_DISPLAY_EMAIL=leaderboard@bidtobuild.example.com
LEADERBOARD_DISPLAY_PASSWORD=replace-with-a-display-password
```

No demo passwords are committed or enabled by default. When all values are supplied,
startup runs the idempotent provisioning logic in `Backend/app/services/demo_seed.py`.
The standalone equivalent is `python -m scripts.seed_demo`, run from `Backend`.

The single Lab Admin account is provisioned or repaired at backend startup from
`LAB_ADMIN_EMAIL`, `LAB_ADMIN_PASSWORD`, and `LAB_ADMIN_NAME`. The password is
backend-only and must be supplied in `Backend/.env` locally or the production
service environment; tracked examples contain placeholders only.

## Automatic AWS Deployment

Pushing `origin/main1` runs the test/build workflow in `.github/workflows/deploy.yml`.
Its legacy production runner is currently offline; use the existing deployment
script over SSH with the Ubuntu paths documented in `deploy/aws/README.md`:

```bash
git add -A
git commit -m "Describe the production change"
git push origin main1
```

The `main1` push starts a disposable PostgreSQL 16 service, applies every Alembic
migration, validates the FastAPI runtime, type-checks and builds the umbrella frontend,
then packages the production payload. The repository-scoped `casino-production` runner
deploys that exact commit, validates the services and Nginx, and verifies public routes.

The PostgreSQL connection and Lab Admin password are supplied only through
`DATABASE_URL` and `LAB_ADMIN_PASSWORD` in `/etc/casino-hackathon/backend.env`.
No database credentials or database files are stored in a release.

The deployed main1 SHA is recorded at:

```bash
cat /home/ec2-user/deploy-state/main1-deployed-sha
```

If a post-promotion check fails, `deploy/aws/deploy-main1-remote.sh` restores the previous Backend/static snapshot and restarts/reloads the same services. The server retains the latest five rollback snapshots under `/opt/casino_hackathon/main1-backups`; database migrations require an application-specific forward fix or a separately managed PostgreSQL backup restore.

For a deliberate rollback, revert the bad commit and push the revert through the same pipeline:

```bash
git switch main1
git pull --ff-only origin main1
git revert <bad-deployment-commit-sha>
git push origin main1
```

See `deploy/aws/README.md` for EC2 verification, failure logs, and recovery details.
