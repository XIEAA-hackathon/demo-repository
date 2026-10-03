# Bid to Build Backend

FastAPI provides the authoritative API and WebSocket event delivery for Bid to Build. SQLAlchemy persists event state, bids, wallets, assignments, submissions and results in PostgreSQL; Alembic owns schema upgrades.

## Local Development

Follow [Running Locally](../README.md#running-locally) for PostgreSQL creation, virtual-environment setup and safe environment configuration. From this directory, with the environment activated and `DATABASE_URL` configured:

```bash
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at `http://localhost:8000`, interactive documentation at `/docs`, and liveness/readiness checks at `/health` and `/health/ready`.

## Source Layout

- `app/api/`: role-protected HTTP routes and WebSocket connections.
- `app/core/`: settings, database sessions, security and shared constants.
- `app/models/` and `app/schemas/`: ORM entities and request/response validation.
- `app/services/`: event lifecycle, assignments, Wildcard, labs, registration and participant sessions.
- `migrations/versions/`: authoritative schema history.
- `database/`: [schema snapshot and migration commands](database/README.md).
- `scripts/`: account/data utilities; consult each utility's arguments before use.

The runtime requires PostgreSQL. [Legacy data transfer](POSTGRESQL_MIGRATION.md) documents the retained read-only SQLite import utility; SQLite is not a supported application backend.

## Validation

```bash
python -m compileall -q app scripts migrations
python -c "from app.main import app; assert app"
python -m alembic current
```

Importing the app does not start an HTTP server or run startup provisioning. Startup verifies connectivity and the required schema rather than applying migrations.
