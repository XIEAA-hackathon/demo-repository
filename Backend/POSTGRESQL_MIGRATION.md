# SQLite to PostgreSQL production migration

This is a maintenance-window procedure. It does not delete or modify the SQLite
source. Replace every angle-bracket placeholder before running a command. Keep
the database password out of Git and shell history.

## 1. Provision PostgreSQL

For managed PostgreSQL, create an empty database and login role, require TLS as
appropriate for the provider, then continue at section 2.

For Amazon Linux 2023 on the application EC2 host:

```bash
sudo dnf install -y postgresql15 postgresql15-server
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
sudo -u postgres psql
```

At the `psql` prompt:

```sql
CREATE ROLE casino_app LOGIN PASSWORD '<LONG_RANDOM_PASSWORD>';
CREATE DATABASE casino_hackathon OWNER casino_app;
\q
```

If PostgreSQL shares a small EC2 host with Uvicorn, budget memory explicitly.
The application can open at most 20 database connections. A reasonable starting
point for a 1-2 GiB host is `max_connections=50`, `shared_buffers=128MB`,
`work_mem=4MB`, and `maintenance_work_mem=64MB`; measure before increasing them.
A managed database or separate EC2 host gives better failure isolation.

## 2. Enter a maintenance window and back up SQLite

```bash
cd /home/ec2-user/demo-repository/Backend
sudo systemctl stop casino-backend.service
mkdir -p /home/ec2-user/database-backups
BACKUP_PATH="/home/ec2-user/database-backups/casino_hackathon-$(date -u +%Y%m%dT%H%M%SZ).db"
./venv/bin/python - "$BACKUP_PATH" <<'PY'
import sqlite3
import sys

source_path = "/home/ec2-user/demo-repository/Backend/casino_hackathon.db"
with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as source:
    with sqlite3.connect(sys.argv[1]) as backup:
        source.backup(backup)
        assert backup.execute("PRAGMA quick_check").fetchone() == ("ok",)
print(sys.argv[1])
PY
test -s "$BACKUP_PATH"
```

Do not remove the original SQLite database after this procedure.

## 3. Install code and dependencies

```bash
cd /home/ec2-user/demo-repository
git pull --ff-only
cd Backend
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

Define the destination URL for this shell. Percent-encode special characters in
the username or password when placing them in a URL.

```bash
read -rsp 'PostgreSQL URL: ' POSTGRES_URL; echo
export POSTGRES_URL
```

Enter a value in this form:

```text
postgresql+psycopg://casino_app:PERCENT_ENCODED_PASSWORD@127.0.0.1:5432/casino_hackathon
```

## 4. Create the PostgreSQL schema

The destination must be empty. Alembic reads `DATABASE_URL` from application
settings; credentials are not stored in `alembic.ini`.

```bash
DATABASE_URL="$POSTGRES_URL" ./venv/bin/alembic upgrade head
DATABASE_URL="$POSTGRES_URL" ./venv/bin/alembic current
```

The expected revision is `20260829_0001 (head)`.

## 5. Validate and transfer data

```bash
SQLITE_URL='sqlite:////home/ec2-user/demo-repository/Backend/casino_hackathon.db'
DATABASE_URL="$POSTGRES_URL" ./venv/bin/python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-url "$SQLITE_URL" --postgres-url "$POSTGRES_URL" --dry-run
DATABASE_URL="$POSTGRES_URL" ./venv/bin/python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-url "$SQLITE_URL" --postgres-url "$POSTGRES_URL" \
  | tee /home/ec2-user/database-backups/postgres-migration-counts.txt
```

Do not proceed unless the tool prints `Migration successful` and every source
and destination count matches. It rolls back the PostgreSQL transaction on a
count mismatch or insertion failure and refuses a non-empty destination.

## 6. Switch the service

Edit `/etc/casino-hackathon/backend.env` with `sudoedit`; preserve all existing
secrets and replace only/add these values:

```dotenv
DATABASE_URL=postgresql+psycopg://casino_app:PERCENT_ENCODED_PASSWORD@127.0.0.1:5432/casino_hackathon
APP_ENV=production
ENABLE_EVENT_RESET=false
```

Then start and verify:

```bash
sudo systemctl restart casino-backend.service
sudo systemctl is-active casino-backend.service
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:8000/health/ready
curl --fail --silent --show-error http://127.0.0.1:8000/version
sudo journalctl -u casino-backend.service --since '-10 minutes' --no-pager
```

Run the admin/participant/WebSocket event acceptance checklist before ending the
maintenance window. After acceptance, make a PostgreSQL backup:

```bash
pg_dump --format=custom --file=/home/ec2-user/database-backups/casino_hackathon-post-cutover.dump "$POSTGRES_URL"
```

## 7. Roll back to SQLite

Rollback does not merge writes made after PostgreSQL cutover. If rollback is
needed, stop traffic promptly, restore the old SQLite URL, and restart:

```bash
sudo systemctl stop casino-backend.service
sudoedit /etc/casino-hackathon/backend.env
```

Set:

```dotenv
DATABASE_URL=sqlite:////home/ec2-user/demo-repository/Backend/casino_hackathon.db
```

Then:

```bash
sudo systemctl restart casino-backend.service
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:8000/health/ready
sudo journalctl -u casino-backend.service --since '-10 minutes' --no-pager
```

Keep both the original SQLite database and its timestamped backup until the
PostgreSQL cutover has been accepted and backed up.
