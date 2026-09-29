import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# No production connection is opened: integration fixtures use isolated SQLite.
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost/bidtobuild_test"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.database import Base
from app.models import models  # noqa: F401


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    yield factory
    engine.dispose()


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session
