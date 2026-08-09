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
Add this section to your root `README.md`:

````md
## Automatic AWS Deployment Workflow

The production deployment uses a release-based structure on the EC2 server.

### Release Layout

The application is deployed under:

```text
/opt/casino_hackathon/
├── releases/
│   ├── <commit-sha>/
│   ├── <commit-sha>/
│   └── ...
├── current -> /opt/casino_hackathon/releases/<active-commit-sha>
└── data/
    └── casino_hackathon.db
````

Each push to `main` creates a new release directory using the Git commit SHA.

Example:

```text
/opt/casino_hackathon/releases/7da234d3e8a218dd2aa0102a5458806191653d2c
```

The application should only be considered deployed after the `current` symbolic link is updated to point to the new release.

---

### Normal Update Workflow

Development changes are pushed normally:

```bash
git add -A
git commit -m "update"
git push origin main
```

The deployment automation should then perform:

```text
GitHub main updated
        ↓
New commit detected
        ↓
Create new release directory
        ↓
Install/backend preparation
        ↓
Build frontend applications
        ↓
Run deployment validation
        ↓
Switch /opt/casino_hackathon/current
        ↓
Restart/reload application services
        ↓
Health check
        ↓
New release becomes live
```

No manual `git pull` should normally be required on the EC2 server.

---

### Release Promotion

Creating a release directory alone does **not** make that release live.

For example, the following releases may both exist:

```text
7da234d3e8a218dd2aa0102a5458806191653d2c
39683b1526b9182ce57809de9ef718dacaf0754d
```

To determine which version is actually serving production traffic, run:

```bash
readlink -f /opt/casino_hackathon/current
```

Example:

```text
/opt/casino_hackathon/releases/7da234d3e8a218dd2aa0102a5458806191653d2c
```

The commit SHA shown in the `current` path is the active production release.

---

### Manual Release Promotion

If deployment successfully creates and builds a new release but fails to update `current`, the new release can be promoted manually.

Example:

```bash
sudo ln -sfn \
/opt/casino_hackathon/releases/7da234d3e8a218dd2aa0102a5458806191653d2c \
/opt/casino_hackathon/current
```

Verify:

```bash
readlink -f /opt/casino_hackathon/current
```

Then validate and reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Restart the backend service if required:

```bash
sudo systemctl restart <backend-service-name>
```

Use the actual configured backend service name.

---

### Important Deployment Rule

The deployment order should be:

```text
1. Fetch new commit
2. Create release
3. Install dependencies
4. Build frontend
5. Prepare backend
6. Validate release
7. Update current symlink
8. Restart/reload services
9. Perform health check
```

The `current` symlink must be changed **only after the new release has built successfully**.

This prevents a failed frontend/backend build from replacing the working production version.

---

### Verifying the Deployed Version

Because the release directories do not necessarily contain a `.git` directory, this command may fail:

```bash
cd /opt/casino_hackathon/current
git rev-parse HEAD
```

with:

```text
fatal: not a git repository
```

This is expected for the release-based deployment.

Instead, check:

```bash
readlink -f /opt/casino_hackathon/current
```

The directory name contains the deployed Git commit SHA.

To see available releases:

```bash
ls -lt /opt/casino_hackathon/releases | head
```

Example:

```text
7da234d3e8a218dd2aa0102a5458806191653d2c
39683b1526b9182ce57809de9ef718dacaf0754d
```

The newest directory is the latest generated release, but it is not necessarily the active release.

Always check `current`.

---

### Verify GitHub vs Production

On the developer machine:

```bash
git rev-parse HEAD
```

Example:

```text
7da234d3e8a218dd2aa0102a5458806191653d2c
```

On EC2:

```bash
readlink -f /opt/casino_hackathon/current
```

The SHA should match.

If they match:

```text
GitHub main SHA
=
EC2 current release SHA
```

the expected version is deployed.

---

### Deployment Troubleshooting

#### New release exists but website still shows old version

Check:

```bash
ls -lt /opt/casino_hackathon/releases | head
```

Then:

```bash
readlink -f /opt/casino_hackathon/current
```

If the new release exists but `current` still points to an older SHA, the deployment completed the release creation/build stage but failed during release promotion.

Investigate the deployment logs and the command responsible for:

```bash
ln -sfn <new-release> /opt/casino_hackathon/current
```

---

#### Frontend changes are not visible

Verify that the frontend production build exists inside the active release:

```bash
ls -la /opt/casino_hackathon/current/frontend-website/dist
```

Then inspect the Nginx document root:

```bash
sudo nginx -T 2>/dev/null | grep -n "root "
```

The Nginx configuration must ultimately serve the frontend files from the active release, either directly through `/opt/casino_hackathon/current/...` or through another deployment-managed path.

After deployment, reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Also perform a browser hard refresh:

```text
Ctrl + Shift + R
```

---

#### Backend health check

The deployed backend health endpoint is:

```text
http://23.21.6.215/api/health
```

Expected response:

```json
{"status":"ok"}
```

The backend Uvicorn process is bound internally to:

```text
127.0.0.1:8000
```

Nginx exposes the backend externally through `/api`.

---

### Persistent Database

Production currently uses SQLite through SQLAlchemy.

Persistent database:

```text
/opt/casino_hackathon/data/casino_hackathon.db
```

The database is stored **outside individual release directories**.

Therefore switching:

```text
current
→ new release
```

must not replace or reset production database data.

Application releases are disposable.

Production data is persistent.

---

### Rollback

Because releases are stored separately, rollback can be performed by repointing `current` to a previous known-good release.

Example:

```bash
sudo ln -sfn \
/opt/casino_hackathon/releases/39683b1526b9182ce57809de9ef718dacaf0754d \
/opt/casino_hackathon/current
```

Then reload/restart the required services:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl restart <backend-service-name>
```

Verify:

```bash
readlink -f /opt/casino_hackathon/current
```

and:

```bash
curl http://127.0.0.1:8000/api/health
```

This allows fast rollback without modifying Git history.

---

### Deployment Status Definitions

Use the following meanings consistently:

| Status          | Meaning                                             |
| --------------- | --------------------------------------------------- |
| Pushed          | Commit exists on `origin/main`                      |
| Release Created | `/releases/<sha>` exists                            |
| Built           | Frontend/backend preparation completed successfully |
| Promoted        | `current` points to the new release                 |
| Healthy         | Backend/Nginx health checks pass                    |
| Live            | New release is promoted and healthy                 |

A release should only be reported as **LIVE** when:

```text
release created
+
build successful
+
current symlink updated
+
services healthy
```

```

I’d especially keep the distinction between **“release created”** and **“release promoted/live”** in the README, because that is exactly what happened with `7da234d`: AWS created the release, but `current` was still pointing to `39683b`.
```

Copy the relevant `.env.example` file for local overrides. Production frontends use same-origin `/api` and derive WebSocket protocol/host from the browser. Database credentials remain backend-only.

Production deploys only from committed `origin/main` through GitHub Actions. See `deploy/aws/README.md` for layout, rollback, and required secrets.
