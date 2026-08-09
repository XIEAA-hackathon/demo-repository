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
        # ``create_all`` does not add columns to an existing SQLite database.
        # Keep this small migration-less project upgrade-safe for local users.
        if database_backend == "sqlite":
            columns = {column["name"] for column in inspect(engine).get_columns("game_config")}
            if "phase_started_at" not in columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE game_config ADD COLUMN phase_started_at DATETIME"))
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
