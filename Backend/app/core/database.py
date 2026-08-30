import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

database_url = make_url(settings.DATABASE_URL)
database_backend = database_url.get_backend_name()

engine_options: dict = {"pool_pre_ping": True}
if database_backend == "sqlite":
    # SQLite remains the zero-configuration local/test backend only.
    engine_options["connect_args"] = {"check_same_thread": False}
elif database_backend == "postgresql":
    # At most 20 checked-out connections under short bursts. This is
    # intentionally conservative for a small EC2 host and ~60 participants.
    engine_options.update(
        pool_size=10,
        max_overflow=10,
        pool_timeout=10,
        pool_recycle=1800,
    )

engine = create_engine(settings.DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


REQUIRED_TABLES = {
    "bids",
    "event_activity_log",
    "event_config",
    "exchange_requests",
    "final_results",
    "game_config",
    "members",
    "problem_statements",
    "registration_import_rows",
    "registration_imports",
    "round_controls",
    "submissions",
    "teams",
    "users",
    "wallet_transactions",
    "wildcard_bids",
    "wildcard_selection_pool",
    "wildcards",
}

REQUIRED_USER_COLUMNS = {
    "session_created_at",
    "session_last_seen_at",
}


def initialize_database() -> None:
    """Verify connectivity and schema without performing startup migrations.

    SQLite development installs may still bootstrap an entirely empty database.
    PostgreSQL schemas and every existing database must be upgraded explicitly
    with ``alembic upgrade head`` before the service starts.
    """
    backend_labels = {"sqlite": "SQLite", "postgresql": "PostgreSQL"}
    logger.info("Database backend: %s", backend_labels.get(database_backend, database_backend))

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        if not table_names and database_backend == "sqlite":
            # Keep local development zero-configuration. create_all is only a
            # fresh-install bootstrap and is never used to upgrade a schema.
            Base.metadata.create_all(bind=engine)
            table_names = set(inspect(engine).get_table_names())

        missing = REQUIRED_TABLES.difference(table_names)
        if missing:
            raise RuntimeError(
                "Database schema is not at the required revision; missing tables: "
                f"{sorted(missing)}. Run 'alembic upgrade head'."
            )
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        missing_user_columns = REQUIRED_USER_COLUMNS.difference(user_columns)
        if missing_user_columns:
            raise RuntimeError(
                "Database schema is not at the required revision; missing users columns: "
                f"{sorted(missing_user_columns)}. Run 'alembic upgrade head'."
            )
    except OperationalError:
        if database_backend == "postgresql":
            logger.error(
                "PostgreSQL connection failed at %s:%s. Verify DATABASE_URL and database availability.",
                database_url.host or "localhost",
                database_url.port or 5432,
            )
        else:
            logger.error(
                "Database initialization failed for %s.",
                database_url.render_as_string(hide_password=True),
            )
        raise


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
