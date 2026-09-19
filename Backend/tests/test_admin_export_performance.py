import json
from datetime import datetime, timezone

from sqlalchemy import event

from app.api.admin import _assignment_export_data, list_imported_participant_accounts
from app.core.security import get_password_hash
from app.models.models import (
    Member,
    ProblemStatement,
    RegistrationImport,
    RegistrationImportRow,
    Submission,
    Team,
    User,
    Wildcard,
)


def _seed_export_rows(db, count=3):
    registration = RegistrationImport(
        filename="registrations.xlsx",
        status="committed",
        committed_at=datetime.now(timezone.utc),
        source_headers_json=json.dumps(["Team Name", "Leader Email", "Leader Password"]),
    )
    db.add(registration)
    db.flush()

    for index in range(1, count + 1):
        leader = User(
            name=f"Leader {index}",
            email=f"leader-{index}@test.example",
            password_hash=get_password_hash("password"),
            role="leader",
            account_source="IMPORTED",
            credentials_active=True,
            is_system_account=False,
        )
        round_one = ProblemStatement(
            ps_number=f"R1-{index}",
            title=f"Round One {index}",
            description="Round one description",
            round=1,
        )
        wildcard_problem = ProblemStatement(
            ps_number=f"WC-{index}",
            title=f"Wildcard {index}",
            description="Wildcard description",
            round=2,
        )
        db.add_all([leader, round_one, wildcard_problem])
        db.flush()
        team = Team(
            team_name=f"Team {index}",
            leader_id=leader.id,
            round1_problem_id=round_one.id,
            wildcard_problem_id=wildcard_problem.id,
            round1_assignment_type="BID_WINNER",
            round1_assignment_cost=100 + index,
            is_system_team=False,
        )
        db.add(team)
        db.flush()
        leader.team_id = team.id
        db.add_all([
            Member(team_id=team.id, member_name=f"Member {index}", email=f"member-{index}@test.example"),
            Wildcard(team_id=team.id, status="selected", problem_id=wildcard_problem.id, winning_bid=50 + index),
            Submission(team_id=team.id, problem_id=wildcard_problem.id, repository_url=f"https://github.com/team/{index}"),
            RegistrationImportRow(
                import_id=registration.id,
                row_number=index + 1,
                team_name=team.team_name,
                leader_name=leader.name,
                leader_email=leader.email,
                source_values_json=json.dumps([team.team_name, leader.email, "secret"]),
                team_id=team.id,
                status="committed",
            ),
        ])
    db.commit()


def _query_count(db, operation):
    count = 0

    def increment(*_args):
        nonlocal count
        count += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", increment)
    try:
        result = operation()
    finally:
        event.remove(engine, "before_cursor_execute", increment)
    return count, result


def test_assignment_export_preloads_related_rows(db):
    _seed_export_rows(db)

    query_count, (headers, rows, suffix) = _query_count(db, lambda: _assignment_export_data(db))

    assert query_count <= 8
    assert suffix == ".xlsx"
    assert len(rows) == 3
    first = dict(zip(headers, rows[0]))
    assert first["Leader Password"] == "NOT EXPORTED"
    assert first["Round 1 Assigned Problem"] == "R1-1 - Round One 1"
    assert first["Wildcard Assigned Problem"] == "WC-1 - Wildcard 1"
    assert first["GitHub Link"] == "https://github.com/team/1"


def test_participant_account_list_loads_teams_once(db):
    _seed_export_rows(db, count=5)
    admin = User(
        name="Admin",
        email="admin@test.example",
        password_hash=get_password_hash("password"),
        role="admin",
    )

    query_count, result = _query_count(
        db,
        lambda: list_imported_participant_accounts(db=db, current_user=admin),
    )

    assert query_count == 2
    assert result["count"] == 5
