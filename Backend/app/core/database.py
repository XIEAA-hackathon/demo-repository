import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

database_url = make_url(settings.DATABASE_URL)
database_backend = database_url.get_backend_name()
engine_options = {}
if database_backend == "sqlite":
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def initialize_database() -> None:
    """Create tables for this migration-less project and explain connection failures."""
    backend_labels = {"sqlite": "SQLite", "postgresql": "PostgreSQL"}
    backend_label = backend_labels.get(database_backend, database_backend)
    logger.info("Database backend: %s", backend_label)

    try:
        Base.metadata.create_all(bind=engine)
        event_columns = {column["name"] for column in inspect(engine).get_columns("event_config")}
        if "bid_cooldown_seconds" not in event_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE event_config ADD COLUMN bid_cooldown_seconds INTEGER DEFAULT 5"))
        if "wildcard_selection_seconds" not in event_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE event_config ADD COLUMN wildcard_selection_seconds INTEGER DEFAULT 30"))

        datetime_type = "TIMESTAMP WITH TIME ZONE" if database_backend == "postgresql" else "DATETIME"
        round_control_columns = {column["name"] for column in inspect(engine).get_columns("round_controls")}
        for column_name, definition in {
            "current_selection_rank": "INTEGER",
            "selection_started_at": datetime_type,
            "selection_ends_at": datetime_type,
            "selection_duration_seconds": "INTEGER",
        }.items():
            if column_name not in round_control_columns:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE round_controls ADD COLUMN {column_name} {definition}"))

        wildcard_columns = {column["name"] for column in inspect(engine).get_columns("wildcards")}
        if "selection_method" not in wildcard_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE wildcards ADD COLUMN selection_method VARCHAR"))

        user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
        if "created_at" not in user_columns:
            created_at_type = "TIMESTAMP WITH TIME ZONE" if database_backend == "postgresql" else "DATETIME"
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN created_at {created_at_type}"))
        with engine.begin() as connection:
            connection.execute(text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

        registration_import_columns = {column["name"] for column in inspect(engine).get_columns("registration_imports")}
        if "source_headers_json" not in registration_import_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE registration_imports ADD COLUMN source_headers_json TEXT NOT NULL DEFAULT '[]'"))
        registration_row_columns = {column["name"] for column in inspect(engine).get_columns("registration_import_rows")}
        for column_name, definition in {
            "source_values_json": "TEXT NOT NULL DEFAULT '[]'",
            "team_id": "INTEGER",
        }.items():
            if column_name not in registration_row_columns:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE registration_import_rows ADD COLUMN {column_name} {definition}"))

        # ``create_all`` does not add columns to an existing SQLite database.
        # Keep this small migration-less project upgrade-safe for local users.
        if database_backend == "sqlite":
            columns = {column["name"] for column in inspect(engine).get_columns("game_config")}
            if "phase_started_at" not in columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE game_config ADD COLUMN phase_started_at DATETIME"))
            event_columns = {column["name"] for column in inspect(engine).get_columns("event_config")}
            if "wildcard_application_seconds" not in event_columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE event_config ADD COLUMN wildcard_application_seconds INTEGER DEFAULT 60"))
            targeted_columns = {
                "problem_statements": {
                    "title": "VARCHAR(255)",
                    "description": "TEXT",
                },
                "round_controls": {
                    "slot_count": "INTEGER",
                    "selection_pool_frozen_at": "DATETIME",
                },
                "teams": {
                    "round1_problem_id": "INTEGER REFERENCES problem_statements(id)",
                    "wildcard_problem_id": "INTEGER REFERENCES problem_statements(id)",
                    "is_system_team": "BOOLEAN NOT NULL DEFAULT 0",
                },
                "users": {
                    "is_system_account": "BOOLEAN NOT NULL DEFAULT 0",
                },
                "wildcards": {
                    "applied_at": "DATETIME",
                    "rank": "INTEGER",
                    "winning_bid": "INTEGER",
                    "problem_id": "INTEGER REFERENCES problem_statements(id)",
                    "selected_at": "DATETIME",
                },
                "submissions": {
                    "submitted_by_user_id": "INTEGER REFERENCES users(id)",
                },
                "event_config": {
                    "submissions_open": "BOOLEAN DEFAULT 0",
                },
                "game_config": {
                    "last_state_update": "DATETIME",
                },
            }
            for table_name, additions in targeted_columns.items():
                existing = {column["name"] for column in inspect(engine).get_columns(table_name)}
                for column_name, definition in additions.items():
                    if column_name not in existing:
                        with engine.begin() as connection:
                            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))

            # Preserve legacy assignments before ``ps_id`` becomes the final active
            # problem pointer. Existing Round 1 assignments are copied once.
            with engine.begin() as connection:
                problem_columns = {column["name"] for column in inspect(engine).get_columns("problem_statements")}
                if "problem_statement" in problem_columns:
                    connection.execute(text(
                        "UPDATE problem_statements SET description = problem_statement "
                        "WHERE (description IS NULL OR TRIM(description) = '') AND problem_statement IS NOT NULL"
                    ))
                connection.execute(text(
                    "UPDATE problem_statements SET title = 'Problem ' || ps_number "
                    "WHERE title IS NULL OR TRIM(title) = ''"
                ))
                connection.execute(text(
                    "UPDATE problem_statements SET description = title "
                    "WHERE description IS NULL OR TRIM(description) = ''"
                ))
                connection.execute(text(
                    "UPDATE teams SET round1_problem_id = ps_id "
                    "WHERE round1_problem_id IS NULL AND ps_id IN "
                    "(SELECT id FROM problem_statements WHERE round = 1)"
                ))
                connection.execute(text(
                    "UPDATE teams SET wildcard_problem_id = ps_id "
                    "WHERE wildcard_problem_id IS NULL AND ps_id IN "
                    "(SELECT id FROM problem_statements WHERE round = 2)"
                ))
                connection.execute(text("UPDATE event_config SET wildcard_application_seconds = 60 WHERE wildcard_application_seconds = 30"))
                connection.execute(text("UPDATE round_controls SET status = 'NOT_STARTED' WHERE round_type = 'WILDCARD' AND status IN ('IDLE', 'READY')"))
                connection.execute(text("UPDATE round_controls SET status = 'BIDDING_OPEN' WHERE round_type = 'WILDCARD' AND status = 'BIDDING'"))
                connection.execute(text("UPDATE wildcards SET status = 'applied' WHERE status = 'bid'"))
                connection.execute(text("UPDATE wildcards SET status = 'qualified' WHERE status = 'won'"))
                connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_wildcards_problem_id ON wildcards(problem_id) WHERE problem_id IS NOT NULL"))
                connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_wildcards_rank ON wildcards(rank) WHERE rank IS NOT NULL"))
                connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_bid_team_problem_round ON bids(team_id, ps_id, round)"))
                connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_wallet_operation ON wallet_transactions(team_id, transaction_type, description)"))
                connection.execute(text("UPDATE game_config SET last_state_update = CURRENT_TIMESTAMP WHERE last_state_update IS NULL"))

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        required_tables = {
            "users", "teams", "problem_statements", "round_controls", "game_config", "event_config",
            "wildcards", "wildcard_selection_pool", "submissions", "final_results", "event_activity_log",
        }
        missing = required_tables.difference(inspect(engine).get_table_names())
        if missing:
            raise RuntimeError(f"Database startup check failed; missing required tables: {sorted(missing)}")
    except OperationalError:
        if database_backend == "postgresql":
            host = database_url.host or "localhost"
            port = database_url.port or 5432
            logger.error(
                "PostgreSQL connection failed at %s:%s. Start PostgreSQL or update "
                "DATABASE_URL. For local development, remove DATABASE_URL or set it "
                "to sqlite:///./casino_hackathon.db.",
                host,
                port,
            )
        else:
            logger.error("Database initialization failed for %s.", database_url.render_as_string(hide_password=True))
        raise

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
