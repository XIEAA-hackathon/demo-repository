# Bid to Build

Bid to Build is a FastAPI/SQLAlchemy event backend with one React/Vite umbrella frontend.

| Surface | Active source | Production path |
|---|---|---|
| Public website | `frontend-website/src/pages/public` | `/` and `/event` |
| Participant portal | `frontend-website/src/participant` | `/participant/*` |
| Admin control center | `frontend-website/src/admin` | `/admin/*` |
| Leaderboard display | `frontend-website/src/leaderboard` | `/leaderboard` |
| FastAPI backend | `Backend` | `/api/` and `/ws/` |

`frontend-website` is the only production frontend entrypoint and build. The existing
`frontend-participant` and `frontend-admin` directories remain as buildable reference
implementations; production CI/CD no longer compiles or serves them.

## Frontend Consolidation

Previously, the public website, participant portal, and admin control center were
three separate Vite applications. Production now uses one entrypoint, one router,
and one build from `frontend-website`. The old `frontend-participant` and
`frontend-admin` applications are retained temporarily for rollback/reference and
have not been deleted.

| Route | Destination |
|---|---|
| `/` and `/event` | Public website |
| `/admin/*` | Admin login and control center |
| `/participant/*` | Participant login and event workflow |
| `/leaderboard` | Authenticated event leaderboard display |
| `/api/*` | FastAPI HTTP API |
| `/ws/*` | FastAPI WebSocket endpoints |

## Local verification

```bash
cd Backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q

cd ../frontend-website
npm ci
npm run test:permissions
npm run build
```

Copy the relevant `.env.example` file for local overrides. Production frontends use same-origin `/api` and derive WebSocket protocol/host from the browser. Database credentials remain backend-only.

## Demo Credentials

Demo Team:
`Demo Team`

Leader:

- Email: `leader@demo.example.com`
- Password: `DemoLeader@123`

Admin:

- Email: `admin.demo@bidtobuild.example.com`
- Password: `DemoAdmin@123`

Leaderboard Display:

- ID: `leaderboard@bidtobuild.example.com`
- Password: `Leaderboard@123`

All three accounts use the normal database-backed password hashing and login flow. They are explicitly marked as permanent system records, so **Reset Event Data**, **Reset Participant Credentials**, and **Reset Managed Users** preserve these accounts and `Demo Team` while continuing to remove imported event participants or non-system management accounts.

### Changing Demo Credentials

Copy [Backend/.env.example](Backend/.env.example) to `Backend/.env`, then edit these backend-only environment variables:

```dotenv
DEMO_ADMIN_EMAIL=admin.demo@bidtobuild.example.com
DEMO_ADMIN_PASSWORD=DemoAdmin@123
DEMO_LEADER_EMAIL=leader@demo.example.com
DEMO_LEADER_PASSWORD=DemoLeader@123
DEMO_TEAM_NAME=Demo Team
LEADERBOARD_DISPLAY_EMAIL=leaderboard@bidtobuild.example.com
LEADERBOARD_DISPLAY_PASSWORD=Leaderboard@123
```

Restart the FastAPI backend after changing them. The values are loaded by `Backend/app/core/config.py`, and startup runs the idempotent provisioning logic in `Backend/app/services/demo_seed.py`. It creates missing permanent records and safely replaces the stored password hash for a configured demo/display account when its password changes. The standalone equivalent is `python -m scripts.seed_demo`, run from `Backend`.

## Automatic AWS Deployment

Production deploys automatically from committed `origin/main1` through `.github/workflows/deploy-main1.yml`:

```bash
git add -A
git commit -m "Describe the production change"
git push origin main1
```

The `main1` push starts a disposable PostgreSQL 16 service, applies every Alembic migration, runs the complete Backend test suite, and builds the umbrella frontend on a GitHub-hosted runner. The repository-scoped `casino-production` runner then downloads the tested artifact on EC2, fetches the exact `origin/main1` commit, preserves environment files and the venv, applies PostgreSQL migrations, restarts `casino-backend.service`, validates `/health`, promotes the frontend into the existing `static/public`, `static/admin`, and `static/participant` layout, validates Nginx, and verifies the public routes. This outbound runner path avoids opening EC2 SSH to GitHub-hosted runner addresses.

The PostgreSQL connection is supplied only through `DATABASE_URL` in `/etc/casino-hackathon/backend.env`. No database credentials or database files are stored in a release.

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

The previous `main` self-hosted-runner workflow remains manual-only as `.github/workflows/deploy-aws.yml`; it no longer deploys automatically on `main` pushes. See `deploy/aws/README.md` for SSH secrets, EC2 verification, failure logs, and recovery details.
