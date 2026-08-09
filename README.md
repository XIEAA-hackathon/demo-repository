# Bid to Build

Bid to Build is a FastAPI/SQLAlchemy event backend with one React/Vite umbrella frontend.

| Surface | Active source | Production path |
|---|---|---|
| Public website | `frontend-website/src/pages/public` | `/` and `/event` |
| Participant portal | `frontend-website/src/participant` | `/participant/*` |
| Admin control center | `frontend-website/src/admin` | `/admin/*` |
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

## Automatic AWS Deployment

Production deploys only from committed `origin/main` through `.github/workflows/deploy-aws.yml`:

```bash
git add -A
git commit -m "Describe the production change"
git push origin main
```

The main-branch push runs the backend tests and builds the umbrella frontend once on a GitHub-hosted runner. It packages the tested output under the exact commit SHA, then the repository-scoped EC2 runner invokes `deploy/aws/deploy-release.sh`. The server installs backend dependencies, validates the application with the production Python/runtime configuration, atomically promotes `/opt/casino_hackathon/current`, restarts the backend, reloads Nginx, and verifies internal and public health/version endpoints.

Persistent configuration and the SQLite database remain outside immutable releases:

- `/etc/casino-hackathon/backend.env`
- `/opt/casino_hackathon/data/casino_hackathon.db`

Use the active symlink as the authoritative release check:

```bash
readlink -f /opt/casino_hackathon/current
```

A directory under `/opt/casino_hackathon/releases/<sha>` is only a prepared release. It is live only when `current` resolves to that SHA and the health checks pass. If post-promotion checks fail, the deployment script atomically restores the previous release and restarts/reloads the same services. The server retains the active release plus five recent rollback candidates.

For a deliberate rollback, dispatch the same workflow with a prior SHA already contained in `main`:

```bash
gh workflow run deploy-aws.yml --ref main -f ref=<full-main-commit-sha>
```

Deployment stage and rollback records are stored in `/var/log/casino-hackathon-deploy.log`. See `deploy/aws/README.md` for the detailed release model and recovery procedure.
