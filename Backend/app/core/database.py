import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

database_url = make_url(settings.DATABASE_URL)
database_backend = database_url.get_backend_name()

if database_backend != "postgresql" or database_url.drivername != "postgresql+psycopg":
    raise RuntimeError(
        "DATABASE_URL must be a PostgreSQL URL (postgresql+psycopg://...). "
        "Non-PostgreSQL runtime backends are not supported."
    )

# Keep the steady-state pool conservative for the production EC2 host while
# allowing bounded short bursts. Values are environment-configurable so the
# pool can be sized below the PostgreSQL server's connection budget.
engine_options: dict = {
    "pool_pre_ping": True,
    "pool_size": settings.DB_POOL_SIZE,
    "max_overflow": settings.DB_MAX_OVERFLOW,
    "pool_timeout": settings.DB_POOL_TIMEOUT_SECONDS,
    "pool_recycle": settings.DB_POOL_RECYCLE_SECONDS,
}

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

    PostgreSQL schemas must be upgraded explicitly with ``alembic upgrade head``
    before the service starts.
    """
    logger.info("Database backend: PostgreSQL")

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
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
        logger.error(
            "PostgreSQL connection failed at %s:%s. Verify DATABASE_URL and database availability.",
            database_url.host or "localhost",
            database_url.port or 5432,
        )
        raise


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
