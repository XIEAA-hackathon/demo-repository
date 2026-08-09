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

Production deploys only from committed `origin/main` through GitHub Actions. See `deploy/aws/README.md` for layout, rollback, and required secrets.
