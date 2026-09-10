from io import BytesIO

from openpyxl import Workbook

from app.core.security import get_password_hash
from app.models.models import Bid, ProblemStatement, RoundControl, Team, User, WalletTransaction
from app.services.round1_assignment import EXTERNAL_PROBLEM_ROUND


def _workbook(*rows: tuple[int, str, str]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Problem Number", "Title", "Description"])
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _import(client, admin_headers, *rows: tuple[int, str, str]):
    return client.post(
        "/admin/rounds/round-1/assignments/external-problems/import",
        headers=admin_headers,
        files={
            "file": (
                "external-problems.xlsx",
                _workbook(*rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def _problem(db, number: int) -> ProblemStatement:
    problem = ProblemStatement(
        ps_number=f"R1-{number}",
        title=f"Round Problem {number}",
        description=f"Round description {number}",
        round=1,
        status="completed",
    )
    db.add(problem)
    db.flush()
    return problem


def _team(db, name: str, problem: ProblemStatement | None = None, *, coins: int = 1500) -> Team:
    slug = name.lower().replace(" ", "-")
    leader = User(
        name=f"{name} Leader",
        email=f"{slug}@external.test",
        password_hash=get_password_hash("temp-pass"),
        role="leader",
    )
    db.add(leader)
    db.flush()
    team = Team(
        team_name=name,
        leader_id=leader.id,
        coins=coins,
        ps_id=problem.id if problem else None,
        round1_problem_id=problem.id if problem else None,
        round1_assignment_type="BID_WINNER" if problem else None,
        round1_assignment_cost=225 if problem else None,
        is_approved=True,
        is_system_team=False,
    )
    db.add(team)
    db.flush()
    leader.team_id = team.id
    return team


def _control(db) -> RoundControl:
    control = RoundControl(
        round_type="ROUND1",
        status="CLOSED",
        ended=True,
        round1_winning_bid_sum=900,
        round1_winning_bid_count=3,
    )
    db.add(control)
    db.flush()
    return control


def _assign(client, admin_headers, team_id: int, problem_id: int):
    return client.put(
        f"/admin/rounds/round-1/assignments/{team_id}",
        headers=admin_headers,
        json={"target_problem_id": problem_id},
    )


def test_excel_import_persists_external_problems_without_entering_round_one_queue(client, admin_headers, db):
    _problem(db, 1)
    _problem(db, 2)
    db.commit()
    before = client.get("/admin/rounds/round-1", headers=admin_headers).json()

    response = _import(
        client,
        admin_headers,
        (21, "Smart Parking Optimization", "Optimize parking availability and routing."),
        (22, "Disaster Communication System", "Build resilient disaster communications."),
    )

    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 2
    assert [row["source"] for row in response.json()["external_problems"]] == ["EXTERNAL", "EXTERNAL"]
    stored = db.query(ProblemStatement).filter(ProblemStatement.round == EXTERNAL_PROBLEM_ROUND).all()
    assert [problem.ps_number for problem in stored] == ["EX-21", "EX-22"]
    after = client.get("/admin/rounds/round-1", headers=admin_headers).json()
    assert [(row["id"], row["problem_number"]) for row in after["problems"]] == [
        (row["id"], row["problem_number"]) for row in before["problems"]
    ]
    assert all(row["problem_number"] not in {"21", "22"} for row in after["remaining_problems"]["problems"])


def test_assign_external_problem_to_unassigned_team_has_no_financial_or_auction_effect(client, admin_headers, db):
    team = _team(db, "External Assignment Team", coins=1775)
    control = _control(db)
    db.commit()
    imported = _import(client, admin_headers, (21, "External 21", "Full external description."))
    target = imported.json()["external_problems"][0]

    response = _assign(client, admin_headers, team.id, target["id"])

    assert response.status_code == 200, response.text
    db.expire_all()
    team = db.get(Team, team.id)
    control = db.get(RoundControl, control.id)
    assert team.ps_id == target["id"] and team.round1_problem_id == target["id"]
    assert team.coins == 1775 and team.round1_assignment_cost == 0
    assert db.query(Bid).filter(Bid.team_id == team.id).count() == 0
    assert db.query(WalletTransaction).filter(WalletTransaction.team_id == team.id).count() == 0
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (900, 3)
    assert response.json()["unassigned_teams"] == []


def test_replace_round_one_problem_with_external_preserves_historical_bid(client, admin_headers, db):
    original = _problem(db, 1)
    team = _team(db, "Historical Team", original, coins=1275)
    control = _control(db)
    bid = Bid(team_id=team.id, ps_id=original.id, amount=225, round=1)
    db.add(bid)
    db.commit()
    imported = _import(client, admin_headers, (21, "External 21", "External replacement."))
    target = imported.json()["external_problems"][0]

    response = _assign(client, admin_headers, team.id, target["id"])

    assert response.status_code == 200, response.text
    db.expire_all()
    team = db.get(Team, team.id)
    assert team.ps_id == target["id"] and team.round1_problem_id == target["id"]
    assert team.coins == 1275
    assert db.query(Bid).filter(Bid.id == bid.id, Bid.ps_id == original.id, Bid.amount == 225).count() == 1
    control = db.get(RoundControl, control.id)
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (900, 3)


def test_external_problem_capacity_is_enforced_by_backend(client, admin_headers, db):
    _control(db)
    db.commit()
    imported = _import(client, admin_headers, (21, "Capacity Problem", "External capacity test."))
    target_id = imported.json()["external_problems"][0]["id"]
    target = db.get(ProblemStatement, target_id)
    for index in range(5):
        _team(db, f"Occupied External {index}", target)
    waiting = _team(db, "Sixth External Team")
    db.commit()

    response = _assign(client, admin_headers, waiting.id, target_id)

    assert response.status_code == 409
    assert "full (5/5)" in response.json()["detail"]
    db.expire_all()
    assert db.get(Team, waiting.id).round1_problem_id is None


def test_duplicate_external_spreadsheet_is_skipped_without_overwrite(client, admin_headers, db):
    first = _import(client, admin_headers, (21, "Original title", "Original description."))
    second = _import(client, admin_headers, (21, "Changed title", "Changed description."))

    assert first.status_code == 200 and first.json()["imported"] == 1
    assert second.status_code == 200, second.text
    assert second.json()["imported"] == 0
    assert second.json()["skipped_duplicate_count"] == 1
    stored = db.query(ProblemStatement).filter(ProblemStatement.ps_number == "EX-21").one()
    assert stored.title == "Original title" and stored.description == "Original description."
    assert db.query(ProblemStatement).filter(ProblemStatement.ps_number == "EX-21").count() == 1


def test_external_import_rejects_round_number_collision_and_malformed_rows(client, admin_headers, db):
    _problem(db, 3)
    db.commit()

    collision = _import(client, admin_headers, (3, "Collision", "Must not overwrite Round 1."))
    malformed = client.post(
        "/admin/rounds/round-1/assignments/external-problems/import",
        headers=admin_headers,
        files={"file": ("invalid.csv", b"Problem Number,Title,Description\n24,Missing Description,\n", "text/csv")},
    )

    assert collision.status_code == 409
    assert "already exists in Round 1" in collision.json()["detail"][0]
    assert malformed.status_code == 422
    assert "Row 2: problem description is required." in malformed.json()["detail"]
    assert db.query(ProblemStatement).filter(ProblemStatement.round == EXTERNAL_PROBLEM_ROUND).count() == 0


def test_external_assignment_realtime_event_and_refresh_use_normal_participant_path(client, admin_headers, db):
    team = _team(db, "Realtime External Team")
    _control(db)
    db.commit()
    imported = _import(client, admin_headers, (21, "Realtime External", "Complete realtime description."))
    target = imported.json()["external_problems"][0]
    login = client.post("/login", data={"username": "realtime-external-team@external.test", "password": "temp-pass"})
    participant_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    with client.websocket_connect(f"/ws/auction?token={login.json()['access_token']}") as websocket:
        assert websocket.receive_json()["type"] == "event_snapshot"
        changed = _assign(client, admin_headers, team.id, target["id"])
        event = websocket.receive_json()

    assert changed.status_code == 200, changed.text
    assert event["type"] == "round1_assignment_changed"
    assert event["payload"]["problem"]["source"] == "EXTERNAL"
    assert event["payload"]["problem"]["description"] == "Complete realtime description."
    dashboard = client.get("/participant/dashboard", headers=participant_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["currentProblem"]["id"] == target["id"]
    assert dashboard.json()["currentProblem"]["description"] == "Complete realtime description."


def test_import_and_multiple_external_assignments_leave_winning_average_unchanged(client, admin_headers, db):
    first = _team(db, "Aggregate External A")
    second = _team(db, "Aggregate External B")
    control = _control(db)
    db.commit()
    imported = _import(
        client,
        admin_headers,
        (21, "External Aggregate 21", "First external problem."),
        (22, "External Aggregate 22", "Second external problem."),
    ).json()

    assert _assign(client, admin_headers, first.id, imported["external_problems"][0]["id"]).status_code == 200
    assert _assign(client, admin_headers, second.id, imported["external_problems"][1]["id"]).status_code == 200
    db.expire_all()
    control = db.get(RoundControl, control.id)
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (900, 3)
    assert db.query(Bid).count() == 0
    assert db.query(WalletTransaction).count() == 0
