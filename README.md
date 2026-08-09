# Bid to Build

Bid to Build is a FastAPI/SQLAlchemy event backend with three React/Vite applications.

| Application | Directory | Production path |
|---|---|---|
| Public website | `frontend-website` | `/` |
| Participant portal | `frontend-participant` | `/participant/` |
| Admin control center | `frontend-admin` | `/admin/` |
| FastAPI backend | `Backend` | `/api/` and `/ws/` |

## Local verification

```bash
cd Backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q

cd ../frontend-website && npm ci && npm run build
cd ../frontend-participant && npm ci && npm run build
cd ../frontend-admin && npm ci && npm run build
```

Copy the relevant `.env.example` file for local overrides. Production frontends use same-origin `/api` and derive WebSocket protocol/host from the browser. Database credentials remain backend-only.

## Automatic AWS Deployment

Production deploys only from committed `origin/main` through `.github/workflows/deploy-aws.yml`:

```bash
git add -A
git commit -m "Describe the production change"
git push origin main
```

The main-branch push runs the backend tests and builds all three frontends on a GitHub-hosted runner. It packages the tested output under the exact commit SHA, then the repository-scoped EC2 runner invokes `deploy/aws/deploy-release.sh`. The server installs backend dependencies, validates the application with the production Python/runtime configuration, atomically promotes `/opt/casino_hackathon/current`, restarts the backend, reloads Nginx, and verifies internal and public health/version endpoints.

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
