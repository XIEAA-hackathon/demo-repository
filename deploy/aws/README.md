# AWS production deployment

The legacy immutable-release path is `.github/workflows/deploy-aws.yml`. It is manual-only; its former automatic `main` trigger is disabled so it cannot compete with the live `main1` SSH pipeline for port 8000 or the Nginx static tree.

Persistent state is outside releases:

- Environment: `/etc/casino-hackathon/backend.env`
- SQLite database: `/opt/casino_hackathon/data/casino_hackathon.db`
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

## SSH deployment from `main1`

`.github/workflows/deploy-main1.yml` is a separate deployment path for the existing EC2 checkout at `/home/ec2-user/demo-repository`. It triggers only for pushes to `main1`, runs the complete Backend test suite, builds the umbrella Vite frontend on GitHub Actions, and uploads only the tested frontend artifact plus the remote deployment script over SSH.

The EC2 script fetches the exact pushed commit from `origin/main1` into an isolated staging tree. It does not use `git reset --hard`, and it does not require the EC2 checkout's frontend worktree to be clean. Backend promotion preserves `Backend/.env`, `Backend/venv`, SQLite files, logs, and caches. The existing SQLite database remains at `/home/ec2-user/demo-repository/Backend/casino_hackathon.db`; moving it is a separate maintenance operation and is not performed by deployment.

The single frontend build is materialized according to the live Nginx layout:

- the complete bundle is deployed to `/opt/casino_hackathon/current/static/public`;
- its `index.html` is also installed at `/opt/casino_hackathon/current/static/admin/index.html`;
- its `index.html` is also installed at `/opt/casino_hackathon/current/static/participant/index.html`.

This works because the repository now contains one BrowserRouter application and the live Nginx configuration serves `/assets` from `static/public` while using the Admin and participant files as route entry points.

Before either Backend or static content changes, `deploy-main1-remote.sh` saves a rollback snapshot under `/opt/casino_hackathon/main1-backups`. At most five snapshots are retained. A failed Backend health check or Nginx/frontend check restores the previous snapshot; database migrations are never rolled back automatically. The deployed SHA is recorded at `/home/ec2-user/deploy-state/main1-deployed-sha`. Both AWS workflows share the `production-aws` GitHub concurrency group and `/var/lock/casino-hackathon-deploy.lock`, so the existing `main` release pipeline and this `main1` pipeline cannot promote at the same time.

Create these repository Actions secrets under **Settings → Secrets and variables → Actions → New repository secret**:

- `EC2_HOST`: the EC2 public DNS name;
- `EC2_USER`: `ec2-user`;
- `EC2_SSH_KEY`: the complete private PEM key, including its BEGIN/END lines.

Never commit the PEM file. The workflow writes it to an ephemeral GitHub runner with mode `0600`, pins the server's ED25519 host key in `known_hosts`, and removes the temporary files after the job.

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

Follow the run under **GitHub → Actions → Deploy main1 to EC2**. A successful run logs the commit SHA, Backend tests, frontend build, SSH verification, dependency installation, service restart, Backend health, Nginx validation, and final public checks without printing secrets.

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

Database schema changes require an application-specific forward fix; do not copy or reverse the SQLite database as part of a source rollback.
