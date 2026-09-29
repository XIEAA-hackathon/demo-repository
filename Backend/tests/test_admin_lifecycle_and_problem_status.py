from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import operations, rounds
from app.api.auth import get_current_active_admin
from app.core.database import get_db
from app.models.models import Bid, EventConfig, GameConfig, Lab, LabAssignment, ProblemStatement, RoundControl, Team, User, Wildcard
from app.services.lab_allocation import lab_board


def test_two_run_round1_end_reset_wildcard_open(db, monkeypatch):
    async def broadcast(*args, **kwargs): pass
    monkeypatch.setattr(rounds.manager, "broadcast_event", broadcast)
    admin = User(name="Admin", email="admin@test.local", password_hash="fixture", role="admin")
    db.add_all([admin, Team(team_name="Participant"), EventConfig(), GameConfig(state="WAITING", current_round=1),
                RoundControl(round_type="ROUND1", status="IDLE", ended=False),
                RoundControl(round_type="WILDCARD", status="NOT_STARTED", ended=False)])
    db.commit()
    app = FastAPI()
    app.include_router(rounds.router); app.include_router(operations.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_admin] = lambda: admin
    with TestClient(app) as client:
        for run in range(2):
            assert client.post("/admin/rounds/wildcard/applications/open").status_code == 409
            problem = ProblemStatement(ps_number="R1-1", title=f"Run {run + 1}", round=1, status="visible")
            db.add(problem); db.commit()
            problem_id = problem.id
            assert client.post(f"/admin/rounds/round-1/problems/{problem_id}/select").status_code == 200
            assert client.post("/admin/rounds/round-1/preview/start").status_code == 200
            assert client.post("/admin/rounds/round-1/bidding/start").status_code == 200
            ended = client.post("/admin/rounds/round-1/end")
            assert ended.status_code == 200
            assert ended.json()["ended"] is True and ended.json()["status"] == "CLOSED"
            reloaded = client.get("/admin/rounds/round-1").json()
            assert reloaded["ended"] is True and reloaded["status"] == "CLOSED"
            opened = client.post("/admin/rounds/wildcard/applications/open")
            assert opened.status_code == 200 and opened.json()["status"] == "APPLICATIONS_OPEN"
            game = db.query(GameConfig).one()
            assert game.state == "WILDCARD_APPLICATION" and game.current_round == 2
            if run == 0:
                reset = client.post("/admin/event-data/reset", json={"confirmation": "RESET EVENT"})
                assert reset.status_code == 200 and reset.json()["event_state"] == "WAITING"
                controls = {row.round_type: row for row in db.query(RoundControl).all()}
                assert controls["ROUND1"].ended is False and controls["ROUND1"].status == "IDLE"
                assert controls["WILDCARD"].ended is False and controls["WILDCARD"].status == "NOT_STARTED"
                assert controls["WILDCARD"].slot_count is None
                game = db.query(GameConfig).one()
                assert game.state == "WAITING" and game.current_round == 1


def test_lab_problem_status_history_and_display_only_legacy_fallback(db):
    r1 = ProblemStatement(ps_number="R1-2", title="Round 1", round=1)
    wc = ProblemStatement(ps_number="WC-1", title="Wildcard", round=2)
    team = Team(team_name="Team Alpha", coins=5000)
    lab = Lab(name="CC Lab", capacity=10, sort_order=1)
    db.add_all([r1, wc, team, lab, RoundControl(round_type="ROUND1", ended=False),
                RoundControl(round_type="WILDCARD", ended=False)])
    db.commit()
    def row(): return next(item for item in lab_board(db)["teams"] if item["id"] == team.id)
    assert row()["problem_assignment_status"] == "not_allocated"
    assert row()["allocation_status"] == "awaiting_problem"
    team.ps_id = team.round1_problem_id = r1.id
    team.round1_assignment_type = "BID_WINNER"; team.round1_assignment_cost = 100
    db.add(Bid(team_id=team.id, ps_id=r1.id, round=1, amount=100)); db.commit()
    assigned = row()
    assert assigned["problem_assignment_status"] == "allocated"
    assert assigned["allocation_status"] == "lab_pending"
    assert assigned["final_problem"]["problem_number"] == "R1-2"
    assert assigned["round1"]["place"] == 1 and assigned["round1"]["winning_bid"] == 100
    # Read-only safety fallback must not repair or change graph eligibility.
    team.ps_id = None; db.commit()
    legacy = row()
    assert legacy["problem_assignment_status"] == "allocated" and legacy["allocation_status"] == "lab_pending"
    assert legacy["final_problem"]["id"] == r1.id and team.ps_id is None and not db.dirty
    team.ps_id = r1.id; team.wildcard_problem_id = wc.id
    db.add(Wildcard(team_id=team.id, status="selected", winning_bid=200, rank=1)); db.commit()
    assert row()["problem_assignment_status"] == "allocated" and row()["round1"]["id"] == r1.id
    team.final_problem_choice = "WILDCARD"; team.ps_id = wc.id; db.commit()
    final = row()
    assert final["round1"]["id"] == r1.id and final["wildcard_history"]["id"] == wc.id
    assert final["final_problem"]["id"] == wc.id and final["problem_assignment_status"] == "allocated"
    db.add(LabAssignment(team_id=team.id, original_lab_id=lab.id, current_lab_id=lab.id, effective_ps_id=wc.id)); db.commit()
    allocated = lab_board(db)
    assert row()["allocation_status"] == "allocated" and row()["problem_assignment_status"] == "allocated"
    assert allocated["labs"][0]["teams"][0]["team_name"] == "Team Alpha"
