"""Admin current/final corrections must never rewrite auction history."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import participant, rounds
from app.api.auth import get_current_active_admin, get_current_active_participant
from app.core.database import get_db
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, User, WalletTransaction
from app.services.extra_assignment import extra_assignment_payload
from app.services.leaderboard_projection import round1_rows
from app.services.round1_assignment import Round1AssignmentError, change_round1_problem_assignment


@pytest.fixture
def correction(db, monkeypatch):
    r1 = ProblemStatement(ps_number="R1-4", title="Traffic", round=1)
    wc = ProblemStatement(ps_number="WC-18", title="Emergency", round=2)
    external = ProblemStatement(ps_number="EX-21", title="Legacy", round=0)
    leader = User(name="Leader", email="leader@example.test", password_hash="unused", role="leader")
    db.add_all([r1, wc, external, leader, EventConfig(), GameConfig(state="CODING"),
                RoundControl(round_type="ROUND1", status="COMPLETE", ended=True)])
    db.flush()
    team = Team(team_name="Team A", leader_id=leader.id, ps_id=r1.id, round1_problem_id=r1.id,
                round1_assignment_type="BID_WINNER", round1_assignment_cost=600, coins=4400)
    db.add(team); db.flush()
    leader.team_id = team.id
    db.add_all([Bid(team_id=team.id, ps_id=r1.id, round=1, amount=600),
                WalletTransaction(team_id=team.id, transaction_type="ROUND1_WIN", amount=-600,
                                  description="Round 1 win for problem 4")])
    db.commit()
    app = FastAPI()
    app.include_router(rounds.router)
    app.include_router(participant.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_admin] = lambda: leader
    app.dependency_overrides[get_current_active_participant] = lambda: leader
    events = []

    async def capture(kind, payload, **_kwargs):
        events.append((kind, payload))

    monkeypatch.setattr(rounds.manager, "broadcast_event", capture)
    with TestClient(app) as client:
        yield client, team, r1, wc, external, events


def test_payload_uses_current_assignments_and_only_r1_wildcard(db, correction):
    client, team, r1, wc, external, _ = correction
    team.ps_id = wc.id
    team.wildcard_problem_id = wc.id
    # Having historical R1 history alone does not mean a current assignment.
    unassigned = Team(team_name="No current", round1_problem_id=r1.id)
    legacy = Team(team_name="Legacy current", ps_id=external.id)
    db.add_all([unassigned, legacy]); db.commit()
    payload = client.get("/admin/rounds/round-1/assignments").json()
    assert {row["source"] for row in payload["problems"]} == {"ROUND1", "WILDCARD"}
    assert {row["id"] for row in payload["problems"]} == {r1.id, wc.id}
    assert "external_problems" not in payload and "capacity_per_problem" not in payload
    rows = {row["team_id"]: row for row in payload["teams"]}
    assert rows[team.id]["current_problem"]["id"] == wc.id
    assert rows[legacy.id]["assignment_status"] == "ASSIGNED"
    assert [row["team_id"] for row in payload["unassigned_teams"]] == [unassigned.id]
    assert payload["round1_problems"][0]["assigned_team_count"] == 0
    assert payload["wildcard_problems"][0]["assigned_team_count"] == 1
    # Extra/Grid remains R1 + legacy external, not WC.
    extra = extra_assignment_payload(db)
    assert {row["id"] for row in extra["problems"]} == {r1.id, external.id}
    assert extra["capacity_per_problem"] == 5


@pytest.mark.parametrize("direction", ["ROUND1_TO_WILDCARD", "WILDCARD_TO_ROUND1"])
def test_change_updates_current_dashboard_preserves_history_wallet_and_winners(db, correction, direction):
    client, team, r1, wc, _, events = correction
    team.wildcard_problem_id = wc.id
    if direction == "WILDCARD_TO_ROUND1":
        team.ps_id = wc.id
    db.commit()
    target = wc if direction == "ROUND1_TO_WILDCARD" else r1
    before_winners = round1_rows(db, r1.id, finalized=True)
    before_dashboard = client.get("/participant/dashboard").json()
    response = client.put(f"/admin/rounds/round-1/assignments/{team.id}", json={"target_problem_id": target.id})
    assert response.status_code == 200, response.text
    db.expire_all()
    assert team.ps_id == target.id
    assert (team.round1_problem_id, team.wildcard_problem_id, team.round1_assignment_type,
            team.round1_assignment_cost, team.coins) == (r1.id, wc.id, "BID_WINNER", 600, 4400)
    assert round1_rows(db, r1.id, finalized=True) == before_winners
    assert db.query(Bid).one().ps_id == r1.id
    ledger = db.query(WalletTransaction).one()
    assert (ledger.transaction_type, ledger.amount) == ("ROUND1_WIN", -600)
    dashboard = client.get("/participant/dashboard").json()
    assert dashboard["currentProblem"]["id"] == dashboard["finalProblem"]["id"] == target.id
    assert dashboard["round1Problem"] == before_dashboard["round1Problem"]
    assert dashboard["wildcardProblem"] == before_dashboard["wildcardProblem"]
    assert events[-1][0] == "round1_assignment_changed"
    assert events[-1][1]["problem"]["id"] == target.id
    repeated = client.put(f"/admin/rounds/round-1/assignments/{team.id}", json={"target_problem_id": target.id})
    assert repeated.status_code == 200 and repeated.json()["idempotent"] is True
    assert len(events) == 1


@pytest.mark.parametrize("target_round", [1, 2])
@pytest.mark.parametrize("new_balance", [None, 1200])
def test_unassigned_gets_either_current_problem_without_fabricated_history(db, correction, target_round, new_balance):
    client, team, r1, wc, _, _ = correction
    team.ps_id = team.round1_problem_id = team.wildcard_problem_id = None
    team.round1_assignment_type = team.round1_assignment_cost = None
    db.commit()
    target = r1 if target_round == 1 else wc
    body = {"target_problem_id": target.id}
    if new_balance is not None:
        body["new_balance"] = new_balance
    response = client.put(f"/admin/rounds/round-1/assignments/{team.id}", json=body)
    assert response.status_code == 200, response.text
    db.expire_all()
    assert team.ps_id == target.id and team.coins == (4400 if new_balance is None else new_balance)
    assert (team.round1_problem_id, team.wildcard_problem_id, team.round1_assignment_type, team.round1_assignment_cost) == (None, None, None, None)
    dashboard = client.get("/participant/dashboard").json()
    assert dashboard["finalProblem"]["id"] == dashboard["currentProblem"]["id"] == target.id
    assert dashboard["round1Problem"] is dashboard["wildcardProblem"] is None
    assert db.query(WalletTransaction).count() == 1  # No fabricated win/charge.


def test_rejects_external_and_assigned_balance_change_atomically(db, correction):
    client, team, r1, wc, external, events = correction
    for body in [{"target_problem_id": external.id}, {"target_problem_id": wc.id, "new_balance": 0}]:
        response = client.put(f"/admin/rounds/round-1/assignments/{team.id}", json=body)
        assert response.status_code == 409
        db.expire_all()
        assert team.ps_id == team.round1_problem_id == r1.id and team.coins == 4400
    assert not events
    assert db.query(ProblemStatement).filter_by(id=external.id).one().title == "Legacy"


def test_correction_ignores_auction_capacity(db, correction):
    _, team, r1, wc, _, _ = correction
    db.add_all([Team(team_name=f"Occupant {i}", ps_id=wc.id) for i in range(7)])
    db.commit()
    result = change_round1_problem_assignment(db, team.id, wc.id)
    assert result["change"]["problem"]["assigned_team_count"] == 8
    assert team.round1_problem_id == r1.id and team.coins == 4400


def test_removed_routes_and_shared_problem_bank_parser(correction):
    client, *_ = correction
    assert client.get("/admin/rounds/round-1/assignments/external-problems/sample.csv").status_code == 404
    assert client.post("/admin/rounds/round-1/assignments/external-problems/import").status_code == 404
    assert rounds._read_problem_rows("bank.csv", b"Problem Number,Title,Description\n1,Traffic,Routing\n") == [(1, "Traffic", "Routing")]


@pytest.mark.parametrize("round_slug,round_number", [("round-1", 1), ("wildcard", 2)])
def test_normal_problem_bank_import_still_works(db, correction, round_slug, round_number):
    client, *_ = correction
    response = client.post(f"/admin/rounds/{round_slug}/problems/import", files={
        "file": ("bank.csv", b"Problem Number,Title,Description\n30,New bank problem,Shared parser\n", "text/csv")
    })
    assert response.status_code == 200, response.text
    problem = db.query(ProblemStatement).filter_by(title="New bank problem").one()
    assert problem.round == round_number


@pytest.mark.parametrize("bad_balance", [-1, 1_000_001, True, 1.5])
def test_balance_validation_unchanged(db, correction, bad_balance):
    _, team, _, wc, _, _ = correction
    with pytest.raises(Round1AssignmentError):
        change_round1_problem_assignment(db, team.id, wc.id, new_balance=bad_balance)
