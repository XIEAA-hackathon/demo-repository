# Legacy SQLite Data Transfer

The application runtime requires PostgreSQL. `scripts/migrate_sqlite_to_postgres.py` is retained only for transferring an existing legacy SQLite dataset; it is not part of first-time local setup.

The utility opens the SQLite source read-only, checks the source/destination table set, refuses a non-empty destination and transfers data transactionally. It compares row counts before committing and repairs PostgreSQL sequence positions after import.

## Before Import

Work on a copy of the legacy database and a disposable PostgreSQL destination first. Keep the original source and a verified backup. Do not point an unreviewed import at a live event database.

From `Backend`, with dependencies installed, set `DATABASE_URL` in the process environment or ignored `.env` to the intended PostgreSQL destination. Create its schema using the current migration chain:

```bash
python -m alembic upgrade head
python -m alembic current
python -m scripts.migrate_sqlite_to_postgres --help
```

Review compatibility with the legacy dataset and the utility's empty-destination requirements. In particular, migrations seed the lab allocation singleton; do not delete seeded or event records merely to force an import to proceed.

## Inspect and Transfer

Using the absolute path to a copied legacy database:

```bash
python -m scripts.migrate_sqlite_to_postgres --sqlite-url sqlite:////ABSOLUTE/PATH/legacy-copy.db --dry-run
python -m scripts.migrate_sqlite_to_postgres --sqlite-url sqlite:////ABSOLUTE/PATH/legacy-copy.db
```

Do not proceed after a compatibility/count error; resolve it on disposable copies. Check the reported counts and migration revision before adopting the destination. The utility neither switches application services nor merges concurrent event writes.

Use [Running Locally](../README.md#running-locally) for a fresh installation and the [database guide](database/README.md) for schema management.
