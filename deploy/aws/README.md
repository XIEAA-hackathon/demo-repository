# AWS production deployment

Production is deployed only by `.github/workflows/deploy-aws.yml`. A push to `main` tests the FastAPI backend and builds all three Vite applications on a GitHub-hosted runner, creates an artifact identified by the exact Git SHA, and sends that artifact to the repository-scoped EC2 runner over its outbound HTTPS connection.

Persistent state is outside releases:

- Environment: `/etc/casino-hackathon/backend.env`
- SQLite database: `/opt/casino_hackathon/data/casino_hackathon.db`
- Immutable releases: `/opt/casino_hackathon/releases/<git-sha>`
- Active release: `/opt/casino_hackathon/current`

The deployment switches the `current` symlink only after validating the artifact and installing backend dependencies. A failed health/version check restores the previous release automatically. To roll back deliberately, run the workflow manually and enter a previous commit SHA from `main` in the `ref` input.

The only required GitHub Actions secret is `EC2_HOST`, used by the final GitHub-hosted public verification job. Deployment does not require inbound SSH from GitHub Actions.

The EC2 runner uses the labels `self-hosted`, `linux`, `x64`, and `casino-production`. It is installed as a systemd service under `/opt/actions-runner-casino` and must remain scoped to this private production repository.

First-time provisioning on Amazon Linux 2023 uses `sudo bash deploy/aws/setup-server.sh`. Existing environment and database files are preserved. Frontends are never compiled on the t3.micro instance.
