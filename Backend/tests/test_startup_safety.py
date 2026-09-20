import asyncio

from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app import main
from app.models.models import Lab, LabAssignment, ProblemStatement, Team, User
from app.services import lab_allocation


def test_database_pool_timeouts_are_counted(monkeypatch):
    monkeypatch.setattr(main, "pool_timeout_count", 0)
    response = asyncio.run(
        main.database_error_handler(None, SQLAlchemyTimeoutError("pool exhausted"))
    )

    assert response.status_code == 503
    assert main.pool_timeout_count == 1


def test_startup_does_not_generate_or_replace_lab_assignments(db, session_factory, monkeypatch):
    user = User(name="Leader", email="startup@test.dev", password_hash="unused", role="leader")
    problem = ProblemStatement(ps_number="PS-STARTUP", title="Startup", description="Safety", round=1)
    lab = Lab(name="Startup Lab", capacity=5, sort_order=1, active=True)
    db.add_all([user, problem, lab])
    db.flush()
    team = Team(team_name="Startup Team", leader_id=user.id, coins=5000, is_approved=True, ps_id=problem.id)
    db.add(team)
    db.flush()
    assignment = LabAssignment(
        team_id=team.id,
        effective_ps_id=problem.id,
        original_lab_id=lab.id,
        current_lab_id=lab.id,
        assignment_source="AUTO",
    )
    db.add(assignment)
    db.commit()
    assignment_id = assignment.id

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Lab allocation must not run during FastAPI startup")

    monkeypatch.setattr(lab_allocation, "allocate_labs", forbidden)
    monkeypatch.setattr(lab_allocation, "try_allocate_labs", forbidden)
    monkeypatch.setattr(main, "SessionLocal", session_factory)
    monkeypatch.setattr(main, "initialize_database", lambda: None)

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run_lifespan())

    db.expire_all()
    persisted = db.query(LabAssignment).filter(LabAssignment.id == assignment_id).one()
    assert persisted.team_id == team.id
    assert persisted.current_lab_id == lab.id
    assert db.query(LabAssignment).count() == 1
