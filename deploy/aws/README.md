# AWS production deployment

Production is deployed only by `.github/workflows/deploy-aws.yml`. A push to `main` tests the FastAPI backend and builds all three Vite applications on a GitHub-hosted runner, creates an artifact identified by the exact Git SHA, and sends that artifact to the repository-scoped EC2 runner over its outbound HTTPS connection.

Persistent state is outside releases:

- Environment: `/etc/casino-hackathon/backend.env`
- SQLite database: `/opt/casino_hackathon/data/casino_hackathon.db`
- Immutable releases: `/opt/casino_hackathon/releases/<git-sha>`
- Active release: `/opt/casino_hackathon/current`

The deployment script is `deploy/aws/deploy-release.sh`. It records `PUSH RECEIVED`, `FETCHING`, `RELEASE CREATED`, `INSTALLING`, `BUILDING`, `VALIDATING`, `PROMOTING`, `RESTARTING`, `HEALTH CHECK`, and `LIVE` in `/var/log/casino-hackathon-deploy.log`. A server-side `flock` on `/var/lock/casino-hackathon-deploy.lock` supplements GitHub Actions concurrency protection.

The tested frontend builds arrive in the artifact. Before promotion, the server installs backend dependencies with its actual Python interpreter and imports the FastAPI application through a transient systemd unit that uses `/etc/casino-hackathon/backend.env`. This catches runtime-version and production-configuration failures before `current` changes.

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
