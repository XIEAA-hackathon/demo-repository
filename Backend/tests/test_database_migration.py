from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.models import Team, User
from scripts import migrate_sqlite_to_postgres as migration


def test_transfer_preserves_ids_and_cyclic_user_team_links(tmp_path, monkeypatch):
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    destination_url = f"sqlite:///{tmp_path / 'destination.db'}"
    source_engine = create_engine(source_url)
    destination_engine = create_engine(destination_url)
    Base.metadata.create_all(source_engine)
    Base.metadata.create_all(destination_engine)

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

    # Exercise the complete transfer transaction on SQLite in CI; backend URL
    # validation and PostgreSQL sequence reset are covered only by live PG runs.
    monkeypatch.setattr(migration, "_validate_backends", lambda *_args: None)
    monkeypatch.setattr(migration, "_reset_postgres_sequences", lambda *_args: None)
    migration.migrate(source_url, destination_url)

    with destination_engine.connect() as connection:
        copied_user = connection.execute(select(Base.metadata.tables["users"])).mappings().one()
        copied_team = connection.execute(select(Base.metadata.tables["teams"])).mappings().one()
    assert copied_user["id"] == 41
    assert copied_user["team_id"] == 73
    assert copied_team["id"] == 73
    assert copied_team["leader_id"] == 41


def test_transfer_refuses_nonempty_destination(tmp_path, monkeypatch):
    source_url = f"sqlite:///{tmp_path / 'empty-source.db'}"
    destination_url = f"sqlite:///{tmp_path / 'nonempty-destination.db'}"
    source_engine = create_engine(source_url)
    destination_engine = create_engine(destination_url)
    Base.metadata.create_all(source_engine)
    Base.metadata.create_all(destination_engine)
    with Session(destination_engine) as db:
        db.add(User(id=1, name="Existing", email="existing@example.com", password_hash="hash", role="admin"))
        db.commit()

    monkeypatch.setattr(migration, "_validate_backends", lambda *_args: None)
    monkeypatch.setattr(migration, "_reset_postgres_sequences", lambda *_args: None)
    try:
        migration.migrate(source_url, destination_url)
    except RuntimeError as exc:
        assert "Destination is not empty" in str(exc)
    else:
        raise AssertionError("Migration must refuse a non-empty destination")
