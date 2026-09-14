from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.exc import IntegrityError
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.models.models import GameConfig, Lab, LabAssignment, ProblemStatement, RoundControl, Team, User
from app.services.lab_admin import provision_lab_admin_account
from app.services.lab_allocation import LabAllocationError, move_team


def _finish_wildcard(db):
    db.add(RoundControl(round_type="WILDCARD", status="COMPLETE", ended=True))
    game = db.query(GameConfig).first()
    if game:
        game.state = "CODING"
    else:
        db.add(GameConfig(state="CODING"))
    db.commit()


def _problem(db, number, round_no=1):
    row = ProblemStatement(ps_number=number, title=number, round=round_no, status="allocated")
    db.add(row)
    db.flush()
    return row


def _team(db, name, problem, *, original=None, wildcard=None):
    row = Team(
        team_name=name,
        ps_id=problem.id,
        round1_problem_id=(original or problem).id,
        wildcard_problem_id=wildcard.id if wildcard else None,
        is_approved=True,
        is_system_team=False,
    )
    db.add(row)
    db.flush()
    return row


def _lab_admin_headers(client, db):
    user = provision_lab_admin_account(db)
    db.commit()
    response = client.post(
        "/lab-admin/login",
        data={"username": user.email, "password": settings.LAB_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_lab_admin_login_and_role_boundaries(client, db, admin_headers):
    headers = _lab_admin_headers(client, db)
    assert client.get("/lab-admin/session", headers=headers).status_code == 200
    assert client.post(
        "/lab-admin/login",
        data={"username": settings.LAB_ADMIN_EMAIL, "password": "wrong-password"},
    ).status_code == 401
    assert client.get("/admin/state", headers=headers).status_code == 403
    assert client.get("/lab-allocation", headers=admin_headers).status_code == 200


def test_lab_admin_websocket_delivery_and_logout_revocation(client, db, admin_headers):
    headers = _lab_admin_headers(client, db)
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws/auction?token={token}") as socket:
        assert socket.receive_json()["type"] == "event_snapshot"
        created = client.post(
            "/admin/labs",
            headers=admin_headers,
            json={"name": "CC Lab", "capacity": 2},
        )
        assert created.status_code == 201, created.text
        assert socket.receive_json()["type"] == "lab_configuration_updated"
        assert client.post("/logout", headers=headers).status_code == 200
        with pytest.raises(WebSocketDisconnect) as disconnected:
            socket.receive_json()
        assert disconnected.value.code == 4401


def test_lab_admin_email_cannot_take_over_another_role(db):
    db.add(User(name="Existing Admin", email=settings.LAB_ADMIN_EMAIL, password_hash="x", role="admin"))
    db.commit()
    with pytest.raises(RuntimeError, match="distinct email"):
        provision_lab_admin_account(db)


def test_lab_name_is_unique_case_insensitively(db):
    db.add(Lab(name="CC Lab", capacity=2))
    db.commit()
    db.add(Lab(name="cc lab", capacity=2))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_lab_crud_empty_board_and_persistence(client, db, admin_headers):
    created = client.post(
        "/admin/labs",
        headers=admin_headers,
        json={"name": "CC Lab", "capacity": 9, "sort_order": 2},
    )
    assert created.status_code == 201, created.text
    lab_id = created.json()["id"]
    board = client.get("/lab-allocation", headers=admin_headers).json()
    assert board["status"] == "NOT_READY"
    assert board["labs"][0]["occupancy"] == 0
    assert board["labs"][0]["capacity"] == 9
    updated = client.put(
        f"/admin/labs/{lab_id}",
        headers=admin_headers,
        json={"capacity": 8, "sort_order": 1},
    )
    assert updated.status_code == 200
    assert client.get("/admin/labs", headers=admin_headers).json()[0]["capacity"] == 8
    assert client.delete(f"/admin/labs/{lab_id}", headers=admin_headers).status_code == 200


def test_max_flow_wildcard_effective_problem_and_strict_moves(client, db, admin_headers):
    _finish_wildcard(db)
    ps1 = _problem(db, "PS1")
    ps2 = _problem(db, "PS2")
    ws1 = _problem(db, "WS1", round_no=2)
    first = _team(db, "Alpha", ps1)
    second = _team(db, "Beta", ps1)
    wildcard = _team(db, "Gamma", ws1, original=ps2, wildcard=ws1)
    db.add_all([Lab(name="CC Lab", capacity=3, sort_order=1), Lab(name="Software Lab", capacity=3, sort_order=2)])
    db.commit()

    allocated = client.post("/admin/lab-allocation/allocate", headers=admin_headers)
    assert allocated.status_code == 200, allocated.text
    board = allocated.json()
    assert board["status"] == "ALLOCATED"
    assigned = [team for lab in board["labs"] for team in lab["teams"]]
    assert {team["id"] for team in assigned} == {first.id, second.id, wildcard.id}
    for lab in board["labs"]:
        problem_ids = [team["effective_problem"]["id"] for team in lab["teams"]]
        assert len(problem_ids) == len(set(problem_ids))
        assert lab["occupancy"] <= lab["capacity"]
    wildcard_row = next(team for team in assigned if team["id"] == wildcard.id)
    assert wildcard_row["effective_problem"]["number"] == "WS1"
    assert wildcard_row["changed_from"] == "PS2"

    ps1_rows = [team for team in assigned if team["effective_problem"]["number"] == "PS1"]
    source = ps1_rows[0]
    target_lab = next(lab for lab in board["labs"] if any(team["id"] == ps1_rows[1]["id"] for team in lab["teams"]))
    warning = client.put(
        f"/lab-allocation/assignments/{source['assignment_id']}/move",
        headers=admin_headers,
        json={"target_lab_id": target_lab["id"], "expected_version": source["version"]},
    )
    assert warning.status_code == 409
    assert warning.json()["detail"]["code"] == "duplicate_effective_problem"
    moved = client.put(
        f"/lab-allocation/assignments/{source['assignment_id']}/move",
        headers=admin_headers,
        json={
            "target_lab_id": target_lab["id"],
            "expected_version": source["version"],
            "allow_constraint_override": True,
        },
    )
    assert moved.status_code == 409, moved.text
    source = wildcard_row
    target_lab = next(lab for lab in board["labs"] if lab["id"] != source["current_lab_id"])
    moved = client.put(f"/lab-allocation/assignments/{source['assignment_id']}/move", headers=admin_headers,
                       json={"target_lab_id": target_lab["id"], "expected_version": source["version"]})
    assert moved.status_code == 200, moved.text
    assert moved.json()["constraint_override"] is False

    stale = client.put(
        f"/lab-allocation/assignments/{source['assignment_id']}/move",
        headers=admin_headers,
        json={"target_lab_id": source["current_lab_id"], "expected_version": source["version"]},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_assignment"

    replacement_problem = _problem(db, "PS3")
    db.query(Team).filter(Team.id == source["id"]).update({Team.ps_id: replacement_problem.id})
    db.commit()
    regenerated = client.post("/admin/lab-allocation/allocate", headers=admin_headers)
    assert regenerated.status_code == 200, regenerated.text
    regenerated_team = next(team for lab in regenerated.json()["labs"] for team in lab["teams"] if team["id"] == source["id"])
    assert regenerated_team["effective_problem"]["number"] == "PS3"
    assert regenerated_team["assignment_source"] == "AUTO"


def test_manual_wildcard_end_triggers_automatic_allocation(client, db, admin_headers):
    problem = _problem(db, "PS1")
    team = _team(db, "Alpha", problem)
    db.add(Lab(name="CC Lab", capacity=1, sort_order=1))
    db.commit()

    response = client.post("/admin/rounds/wildcard/end", headers=admin_headers)

    assert response.status_code == 200, response.text
    assignment = db.query(LabAssignment).filter(LabAssignment.team_id == team.id).one()
    assert assignment.effective_ps_id == problem.id
    board = client.get("/lab-allocation", headers=admin_headers).json()
    assert board["status"] == "ALLOCATED"
    assert board["team_count"] == 1


@pytest.mark.parametrize("same_problem", [False, True])
def test_concurrent_moves_cannot_overfill_lab_or_duplicate_ps(db, session_factory, same_problem):
    _finish_wildcard(db)
    problems = [_problem(db, f"PS{i}") for i in range(1, 4)]
    teams = [_team(db, f"Team {i}", problems[0] if same_problem else problems[i - 1]) for i in range(1, 4)]
    target = Lab(name="Target", capacity=3 if same_problem else 1, sort_order=1)
    sources = [Lab(name="Source A", capacity=2, sort_order=2), Lab(name="Source B", capacity=2, sort_order=3)]
    actor = User(name="Lab Admin", email="lab-race@test.dev", password_hash="x", role="lab_admin")
    db.add_all([target, *sources, actor])
    db.flush()
    assignments = [
        LabAssignment(team_id=teams[0].id, original_lab_id=sources[0].id, current_lab_id=sources[0].id, effective_ps_id=problems[0].id),
        LabAssignment(team_id=teams[1].id, original_lab_id=sources[1].id, current_lab_id=sources[1].id, effective_ps_id=teams[1].ps_id),
    ]
    db.add_all(assignments)
    db.commit()
    assignment_ids = [row.id for row in assignments]
    target_id = target.id
    actor_id = actor.id

    def attempt(assignment_id):
        with session_factory() as session:
            current_actor = session.query(User).filter(User.id == actor_id).one()
            try:
                move_team(
                    session,
                    assignment_id=assignment_id,
                    target_lab_id=target_id,
                    expected_version=1,
                    allow_constraint_override=False,
                    actor=current_actor,
                )
                return "moved"
            except LabAllocationError as exc:
                session.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(attempt, assignment_ids))
    assert outcomes == ["duplicate_effective_problem" if same_problem else "capacity_reached", "moved"]
    assert db.query(LabAssignment).filter(LabAssignment.current_lab_id == target_id).count() == 1


def test_no_wildcard_winners_still_allocates_labs(client, db, admin_headers):
    problem = _problem(db, "NO-WC")
    team = _team(db, "No wildcard winner", problem)
    db.add_all([Lab(name="Final Lab", capacity=3), RoundControl(round_type="WILDCARD", status="BIDDING_CLOSED", slot_count=0)])
    db.commit()
    response = client.post("/admin/wildcard/finalize", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["winners"] == []
    assert db.query(LabAssignment).filter_by(team_id=team.id).one().effective_ps_id == problem.id
    assert client.get("/lab-allocation", headers=admin_headers).json()["can_move"] is True


def test_one_team_one_lab_is_allocated_and_visible_to_participant(client, db, admin_headers):
    from app.core.security import get_password_hash
    problem = _problem(db, "ONE-PS")
    user = User(name="Only Participant", email="one-team@test.dev", password_hash=get_password_hash("one-team-pass"), role="leader")
    db.add(user); db.flush()
    team = Team(team_name="Only Team", leader_id=user.id, ps_id=problem.id, round1_problem_id=None, is_approved=True, is_system_team=False)
    db.add(team); db.flush(); user.team_id = team.id
    db.add(Lab(name="Only Lab", capacity=1)); db.commit()
    _finish_wildcard(db)

    allocated = client.post("/admin/lab-allocation/allocate", headers=admin_headers)
    assert allocated.status_code == 200, allocated.text
    assert allocated.json()["eligible_team_count"] == allocated.json()["assigned_count"] == allocated.json()["max_flow_value"] == 1
    assert db.query(LabAssignment).filter_by(team_id=team.id).count() == 1
    token = client.post("/login", data={"username": user.email, "password": "one-team-pass"}).json()["access_token"]
    dashboard = client.get("/participant/dashboard", headers={"Authorization": f"Bearer {token}"}).json()
    assert dashboard["finalProblem"]["id"] == problem.id
    assert dashboard["lab"]["name"] == "Only Lab"
    assert dashboard["labAllocationStatus"] == "ASSIGNED"
    db.query(LabAssignment).filter_by(team_id=team.id).delete(); db.commit()
    inconsistent = client.get("/participant/dashboard", headers={"Authorization": f"Bearer {token}"}).json()
    assert inconsistent["lab"] is None
    assert inconsistent["labAllocationStatus"] == "UNAVAILABLE"


def test_one_team_seven_labs_receives_exactly_one_assignment(client, db, admin_headers):
    _finish_wildcard(db)
    problem = _problem(db, "ONE-SEVEN")
    team = _team(db, "One of seven", problem)
    db.add_all([Lab(name=f"Lab {index}", capacity=1, sort_order=index) for index in range(1, 8)])
    db.commit()
    response = client.post("/admin/lab-allocation/allocate", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["max_flow_value"] == 1
    assert db.query(LabAssignment).filter_by(team_id=team.id).count() == 1


def test_three_same_ps_teams_are_spread_across_three_labs(client, db, admin_headers):
    _finish_wildcard(db)
    problem = _problem(db, "SHARED")
    teams = [_team(db, f"Shared {index}", problem) for index in range(3)]
    db.add_all([Lab(name=f"Distinct {index}", capacity=3) for index in range(3)]); db.commit()
    response = client.post("/admin/lab-allocation/allocate", headers=admin_headers)
    assert response.status_code == 200, response.text
    rows = db.query(LabAssignment).filter(LabAssignment.team_id.in_([team.id for team in teams])).all()
    assert len(rows) == 3
    assert len({row.current_lab_id for row in rows}) == 3


def test_infeasible_capacity_reports_partial_flow_and_commits_nothing(client, db, admin_headers):
    _finish_wildcard(db)
    teams = [_team(db, f"Capacity {index}", _problem(db, f"CAP-{index}")) for index in range(4)]
    db.add_all([Lab(name="Capacity A", capacity=2), Lab(name="Capacity B", capacity=1)]); db.commit()
    response = client.post("/admin/lab-allocation/allocate", headers=admin_headers)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["eligible_team_count"] == 4 and detail["max_flow"] == 3
    assert len(detail["unassigned_teams"]) == 1
    assert db.query(LabAssignment).count() == 0
    board = client.get("/lab-allocation", headers=admin_headers).json()
    assert board["eligible_team_count"] == 4 and board["assigned_count"] == 0
    assert board["unassigned_count"] == 4 and board["max_flow_value"] == 3


def test_participant_lab_visibility_unassigned_move_and_persistence(client, db, admin_headers):
    from app.core.security import get_password_hash
    problem = _problem(db, "R1-7")
    replacement = _problem(db, "WC-2", round_no=2)
    team = _team(db, "Lab Participant", replacement, original=problem, wildcard=replacement)
    user = User(name="Lab Participant", email="lab-participant@test.dev", role="leader", password_hash=get_password_hash("test-lab-pass"))
    db.add(user); db.flush(); team.leader_id = user.id; user.team_id = team.id
    labs = [Lab(name=f"Lab {name}", capacity=3) for name in "ABC"]
    db.add_all(labs); db.commit()
    lab_ids, team_id = [lab.id for lab in labs], team.id
    lab_headers = _lab_admin_headers(client, db)
    token = client.post('/login', data={'username': user.email, 'password': 'test-lab-pass'}).json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    before = client.get('/participant/dashboard', headers=headers).json()
    assert before['lab'] is None and not before['labAllocationReady']
    assert client.put(f'/lab-admin/teams/{team_id}/lab', headers=lab_headers, json={'lab_id': lab_ids[0]}).status_code == 409
    _finish_wildcard(db)
    assert client.get('/participant/dashboard', headers=headers).json()['labAllocationReady'] is True
    assert client.get('/participant/dashboard', headers=headers).json()['lab'] is None
    version = 0
    for lab_id in lab_ids:
        moved = client.put(f'/lab-admin/teams/{team_id}/lab', headers=lab_headers, json={'lab_id': lab_id, 'expected_version': version})
        assert moved.status_code == 200, moved.text
        version = moved.json()['version']
        dashboard = client.get('/participant/dashboard', headers=headers).json()
        assert dashboard['lab']['id'] == lab_id
        assert dashboard['finalProblem']['id'] == replacement.id
    assert db.query(LabAssignment).filter_by(team_id=team_id).count() == 1
    # A stale assignment must not be shown after a final PS correction.
    db.query(Team).filter_by(id=team_id).update({'ps_id': problem.id}); db.commit()
    assert client.get('/participant/dashboard', headers=headers).json()['lab'] is None


def test_lab_delta_only_reaches_affected_team_and_observers():
    import asyncio
    from app.api.websockets import ConnectionManager
    class Socket:
        def __init__(self): self.messages = []
        async def send_json(self, message): self.messages.append(message)
    async def scenario():
        manager = ConnectionManager()
        own, other, admin = Socket(), Socket(), Socket()
        manager.active_connections = {own: {'team_id': 1, 'role': 'leader'}, other: {'team_id': 2, 'role': 'leader'}, admin: {'role': 'lab_admin'}}
        manager.publish_event('lab_allocation_updated', {'assignments': [{'team_id': 1, 'lab': {'id': 3, 'name': 'Lab C'}}]}, roles={'admin', 'lab_admin'})
        await manager.wait_for_pending()
        assert [row['type'] for row in own.messages] == ['lab_assignment_changed']
        assert other.messages == []
        assert [row['type'] for row in admin.messages] == ['lab_assignment_changed', 'lab_allocation_updated']
        assert manager._version == 0
        await manager.stop()
    asyncio.run(scenario())


def test_automatic_allocator_preserves_manual_placement(db):
    from app.services.lab_allocation import allocate_labs
    _finish_wildcard(db)
    problem = _problem(db, 'R1-KEEP')
    team = _team(db, 'Keep placement', problem)
    labs = [Lab(name='Keep A', capacity=3), Lab(name='Keep B', capacity=3)]
    actor = User(name='Lab Admin', email='keep@test.dev', password_hash='unused', role='lab_admin')
    db.add_all([*labs, actor]); db.commit()
    allocate_labs(db)
    row = db.query(LabAssignment).filter_by(team_id=team.id).one()
    destination = next(lab for lab in labs if lab.id != row.current_lab_id)
    move_team(db, assignment_id=row.id, target_lab_id=destination.id, expected_version=1, allow_constraint_override=False, actor=actor)
    assert allocate_labs(db)[0] is False
    assert db.query(LabAssignment).filter_by(team_id=team.id).one().current_lab_id == destination.id
