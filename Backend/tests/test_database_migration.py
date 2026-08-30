import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.models import Team, User
from scripts import migrate_sqlite_to_postgres as migration


def test_transfer_preserves_ids_and_cyclic_user_team_links(tmp_path, engine):
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    source_engine = create_engine(source_url)
    Base.metadata.create_all(source_engine)

    with Session(source_engine) as db:
        leader = User(
            id=41,
            name="Migration Leader",
            email="migration@example.com",
            password_hash="hash",
            role="leader",
        )
        db.add(leader)
        db.flush()
        team = Team(id=73, team_name="Migration Team", leader_id=leader.id, coins=4321)
        db.add(team)
        db.flush()
        leader.team_id = team.id
        db.commit()

    # The oldest preserved database predates these nullable session columns.
    # The transfer tool must fill them with NULL without mutating the source.
    with source_engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE users DROP COLUMN session_created_at")
        connection.exec_driver_sql("ALTER TABLE users DROP COLUMN session_last_seen_at")

    destination_url = engine.url.render_as_string(hide_password=False)
    migration.migrate(source_url, destination_url)

    with engine.connect() as connection:
        copied_user = connection.execute(select(Base.metadata.tables["users"])).mappings().one()
        copied_team = connection.execute(select(Base.metadata.tables["teams"])).mappings().one()
    assert copied_user["id"] == 41
    assert copied_user["team_id"] == 73
    assert copied_team["id"] == 73
    assert copied_team["leader_id"] == 41


def test_transfer_refuses_nonempty_destination(tmp_path, engine, session_factory):
    source_url = f"sqlite:///{tmp_path / 'empty-source.db'}"
    source_engine = create_engine(source_url)
    Base.metadata.create_all(source_engine)
    with session_factory() as db:
        db.add(User(id=1, name="Existing", email="existing@example.com", password_hash="hash", role="admin"))
        db.commit()

    with pytest.raises(RuntimeError, match="Destination is not empty"):
        destination_url = engine.url.render_as_string(hide_password=False)
        migration.migrate(source_url, destination_url)
