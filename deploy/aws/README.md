# AWS production deployment

Production is deployed only by `.github/workflows/deploy-aws.yml`. A push to `main` tests the FastAPI backend, builds all three Vite applications on GitHub, creates an artifact identified by the exact Git SHA, and deploys it to Amazon Linux 2023.

Persistent state is outside releases:

- Environment: `/etc/casino-hackathon/backend.env`
- SQLite database: `/opt/casino_hackathon/data/casino_hackathon.db`
- Immutable releases: `/opt/casino_hackathon/releases/<git-sha>`
- Active release: `/opt/casino_hackathon/current`

The deployment switches the `current` symlink only after validating the artifact and installing backend dependencies. A failed health/version check restores the previous release automatically. To roll back deliberately, run the workflow manually and enter a previous commit SHA from `main` in the `ref` input.

Required GitHub Actions secrets are `EC2_HOST`, `EC2_USER`, and `EC2_SSH_KEY`. The key should be a dedicated deployment identity, not a personal workstation key.

First-time provisioning on Amazon Linux 2023 uses `sudo bash deploy/aws/setup-server.sh`. Existing environment and database files are preserved. Frontends are never compiled on the t3.micro instance.
