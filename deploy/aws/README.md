# AWS production deployment

The legacy immutable-release path is `.github/workflows/deploy-aws.yml`. It is manual-only; its former automatic `main` trigger is disabled so it cannot compete with the live `main1` SSH pipeline for port 8000 or the Nginx static tree.

Persistent state is outside releases:

- Environment: `/etc/casino-hackathon/backend.env`
- PostgreSQL URL: `DATABASE_URL` in `/etc/casino-hackathon/backend.env`
- Immutable releases: `/opt/casino_hackathon/releases/<git-sha>`
- Active release: `/opt/casino_hackathon/current`

The deployment script is `deploy/aws/deploy-release.sh`. It records `PUSH RECEIVED`, `FETCHING`, `RELEASE CREATED`, `INSTALLING`, `BUILDING`, `VALIDATING`, `PROMOTING`, `RESTARTING`, `HEALTH CHECK`, and `LIVE` in `/var/log/casino-hackathon-deploy.log`. A server-side `flock` on `/var/lock/casino-hackathon-deploy.lock` supplements GitHub Actions concurrency protection.

The tested umbrella frontend build arrives at `static/index.html` in the artifact and serves `/`, `/participant/*`, and `/admin/*` through the same SPA fallback. Before promotion, the server installs backend dependencies with its actual Python interpreter and imports the FastAPI application through a transient systemd unit that uses `/etc/casino-hackathon/backend.env`. This catches runtime-version and production-configuration failures before `current` changes.

Promotion uses an atomic temporary-symlink rename and immediately verifies `readlink -f /opt/casino_hackathon/current`. The deployment then restarts the real `casino-hackathon-backend.service`, confirms Uvicorn remains on `127.0.0.1:8000`, reloads Nginx after `nginx -t`, and checks internal health/version plus public-proxy and frontend routes. A release directory existing does not mean it is live.

If validation fails before promotion, the working `current` release is untouched. If a post-promotion check fails, the script restores the previous symlink and service configuration, restarts/reloads the services, and logs `ROLLBACK SUCCESS` or `ROLLBACK FAILED`. Failed release content is retained for diagnosis. After a successful deployment, retention keeps the active release plus five recent releases; `/opt/casino_hackathon/data` and `/etc/casino-hackathon` are never pruned.

To roll back deliberately, run the workflow manually and enter a previous commit SHA from `main` in the `ref` input, or use the equivalent CLI command from an authenticated administrator workstation:

```bash
gh workflow run deploy-aws.yml --ref main -f ref=<full-main-commit-sha>
```

This is the preferred manual recovery process because it reuses the same tested artifact and deployment script as automatic pushes. If an administrator already has a trusted workflow artifact on EC2, the same lower-level script can be invoked as:

```bash
bash /opt/casino_hackathon/current/deploy/aws/deploy-release.sh /path/to/casino-hackathon-<sha>.tar.gz <full-sha>
```

The only required GitHub Actions secret is `EC2_HOST`, used by the final GitHub-hosted public verification job. Deployment does not require inbound SSH from GitHub Actions.

The EC2 runner uses the labels `self-hosted`, `linux`, `x64`, and `casino-production`. It is installed as a systemd service under `/opt/actions-runner-casino` and must remain scoped to this private production repository.

First-time provisioning on Amazon Linux 2023 uses `sudo bash deploy/aws/setup-server.sh`. Existing environment and database files are preserved. Frontends are never compiled on the t3.micro instance.

## Automatic deployment from `main1`

`.github/workflows/deploy-main1.yml` is a separate deployment path for the existing EC2 checkout at `/home/ec2-user/demo-repository`. It triggers only for pushes to `main1`, runs the complete Backend test suite, builds the umbrella Vite frontend on a GitHub-hosted runner, then downloads only the tested frontend artifact plus deployment script through the repository-scoped `casino-production` runner on EC2. Inbound SSH from hosted runners is not required and no security-group change is needed.

The EC2 script fetches the exact pushed commit from `origin/main1` into an isolated staging tree. It does not use `git reset --hard`, and it does not require the EC2 checkout's frontend worktree to be clean. Backend promotion preserves `Backend/.env`, `Backend/venv`, logs, and caches. It validates the service's PostgreSQL `DATABASE_URL` and applies `alembic upgrade head` before restarting the systemd-managed service.

The live `casino-backend.service` must use the same canonical environment file
that deployment validates. The tracked drop-in clears legacy environment-file
entries before loading it. Install the drop-in once on an existing server, then
confirm the PostgreSQL URL and schema before restarting:

```bash
cd /home/ec2-user/demo-repository
sudo install -D -m 0644 deploy/aws/casino-backend-postgresql.conf \
  /etc/systemd/system/casino-backend.service.d/postgresql.conf
sudo chown root:ec2-user /etc/casino-hackathon/backend.env
sudo chmod 0640 /etc/casino-hackathon/backend.env
sudo systemctl daemon-reload
sudo systemctl show casino-backend.service --property=EnvironmentFiles --no-pager
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=ec2-user --gid=ec2-user \
  -p WorkingDirectory=/home/ec2-user/demo-repository/Backend \
  -p EnvironmentFile=/etc/casino-hackathon/backend.env \
  /home/ec2-user/demo-repository/Backend/venv/bin/python -m alembic upgrade head
sudo systemctl restart casino-backend.service
sudo systemctl is-active casino-backend.service
curl --fail http://127.0.0.1:8000/health/ready
```

Do not print `DATABASE_URL` or commit `backend.env`. If it still points to the
legacy database, complete `Backend/POSTGRESQL_MIGRATION.md` before restarting.

The single frontend build is materialized according to the live Nginx layout:

- the complete bundle is deployed to `/opt/casino_hackathon/current/static/public`;
- its `index.html` is also installed at `/opt/casino_hackathon/current/static/admin/index.html`;
- its `index.html` is also installed at `/opt/casino_hackathon/current/static/participant/index.html`.

This works because the repository now contains one BrowserRouter application and the live Nginx configuration serves `/assets` from `static/public` while using the Admin and participant files as route entry points.

Before either Backend or static content changes, `deploy-main1-remote.sh` saves a rollback snapshot under `/opt/casino_hackathon/main1-backups`. At most five snapshots are retained. A failed Backend health check or Nginx/frontend check restores the previous snapshot; database migrations are never rolled back automatically. The deployed SHA is recorded at `/home/ec2-user/deploy-state/main1-deployed-sha`. Both AWS workflows share the `production-aws` GitHub concurrency group and `/var/lock/casino-hackathon-deploy.lock`, so the existing `main` release pipeline and this `main1` pipeline cannot promote at the same time.

The deployment itself requires no EC2 private key in GitHub because the repository-scoped runner is already installed on the server. `EC2_HOST`, `EC2_USER`, and `EC2_SSH_KEY` may remain configured for administrator-operated diagnostics, but the automatic deployment does not read or print them.

The deployment requires only the commands listed in `deploy/aws/casino-main1-sudoers`. Install and validate that rule once on EC2:

```bash
cd /home/ec2-user/demo-repository
sudo install -o root -g root -m 0440 deploy/aws/casino-main1-sudoers /etc/sudoers.d/casino-main1-deploy
sudo visudo -cf /etc/sudoers.d/casino-main1-deploy
```

The standard Amazon Linux `ec2-user` image may already grant `NOPASSWD: ALL`. The narrow rule does not override a broader existing grant; removing that broader administrative access is a separate host-hardening decision and must not be done by an application deployment.

To deploy, commit and push the changes to `main1`:

```bash
git push origin main1
```

Follow the run under **GitHub → Actions → Deploy main1 to EC2**. A successful run logs the commit SHA, Backend tests, frontend build, runner staging, dependency installation, service restart, Backend health, Nginx validation, and final route checks without printing secrets.

On EC2, verify the active result with:

```bash
cat /home/ec2-user/deploy-state/main1-deployed-sha
sudo systemctl is-active casino-backend.service
curl --fail http://127.0.0.1:8000/health
sudo nginx -t
curl --fail http://127.0.0.1/api/health
curl --fail http://127.0.0.1/admin/
curl --fail http://127.0.0.1/participant/
```

For a failed deployment, open its Actions run and expand the failed step. Server-side details are also available with:

```bash
tail -n 200 /var/log/casino-hackathon-deploy.log
sudo journalctl --no-pager -u casino-backend.service -n 80
```

The remote script automatically restores the immediately preceding snapshot when a deployment fails after promotion. For a deliberate manual rollback, create and push a new revert commit so the same test/build/deploy pipeline remains authoritative:

```bash
git switch main1
git pull --ff-only origin main1
git revert <bad-deployment-commit-sha>
git push origin main1
```

Database schema changes require an application-specific forward fix or a separately managed PostgreSQL backup restore; source rollback does not reverse migrations automatically.
