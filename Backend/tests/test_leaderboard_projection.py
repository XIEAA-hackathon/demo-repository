from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import judging, participant, rounds, wildcard
from app.api.auth import get_current_active_admin, get_current_active_display, get_current_active_participant
from app.core.database import get_db
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, WalletTransaction, Wildcard, WildcardBid


def client_for(db, monkeypatch):
    async def broadcast(*args, **kwargs): pass
    monkeypatch.setattr(rounds.manager, "broadcast_event", broadcast)
    app = FastAPI()
    for router in [rounds.router, judging.router, participant.router, wildcard.router]: app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    for auth in [get_current_active_admin, get_current_active_display, get_current_active_participant]:
        app.dependency_overrides[auth] = lambda: None
    return TestClient(app)


def test_r1_top10_actual_winners_and_next_problem(db, monkeypatch):
    now = datetime.now(timezone.utc)
    first, second = [ProblemStatement(ps_number=f"R1-{i}", title=f"Problem {i}", round=1, status="visible") for i in [4, 2]]
    db.add_all([first, second, EventConfig(), GameConfig(state="ROUND1_BIDDING", current_round=1, auction_timer_end=now + timedelta(minutes=5))]); db.flush()
    first_id, second_id = first.id, second.id
    db.add(RoundControl(round_type="ROUND1", current_problem_id=first.id, status="BIDDING"))
    teams = [Team(team_name=f"Bidder {i}", coins=0 if i == 0 else 5000) for i in range(12)]
    db.add_all(teams); db.flush()
    ids = [team.id for team in teams]
    db.add_all([Bid(team_id=team.id, ps_id=first.id, round=1, amount=1300 - i * 10, timestamp=now + timedelta(seconds=i)) for i, team in enumerate(teams)])
    db.add(Bid(team_id=teams[-1].id, ps_id=second.id, round=1, amount=2000, timestamp=now))
    db.commit()
    with client_for(db, monkeypatch) as client:
        live = client.get("/public/leaderboard").json()
        assert live["mode"] == "ROUND1_LIVE"
        assert [row["team_id"] for row in live["rows"]] == ids[:10]
        assert [row["rank"] for row in live["rows"]] == list(range(1, 11))
        assert len(client.get("/participant/leaderboard", params={"round_type": "ROUND1"}).json()) == 10
        assert db.query(Bid).filter(Bid.ps_id == first_id).count() == 12
        assert client.post("/admin/rounds/round-1/bidding/close").status_code == 200
        assigned = client.post("/admin/rounds/round-1/assign-winners")
        assert assigned.status_code == 200
        actual = assigned.json()["winners"]
        assert [row["team_id"] for row in actual] == ids[1:6]  # Highest live bidder is ineligible.
        final = client.get("/public/leaderboard").json()
        assert final["mode"] == "ROUND1_RESULT" and final["problem"]["id"] == first_id
        assert [row["team_id"] for row in final["rows"]] == [row["team_id"] for row in actual]
        participant_rows = client.get("/participant/leaderboard", params={"round_type": "ROUND1"}).json()
        assert all(row["finalized"] for row in participant_rows)
        assert [row["team_id"] for row in participant_rows] == ids[1:6]
        assert db.query(Bid).filter(Bid.ps_id == first_id).count() == 12
        assert db.query(WalletTransaction).filter_by(transaction_type="ROUND1_WIN").count() == 5
        assert client.post(f"/admin/rounds/round-1/problems/{second_id}/select").status_code == 200
        assert client.post("/admin/rounds/round-1/preview/start").status_code == 200
        assert client.post("/admin/rounds/round-1/bidding/start").status_code == 200
        next_live = client.get("/public/leaderboard").json()
        assert next_live["mode"] == "ROUND1_LIVE" and next_live["problem"]["id"] == second_id
        assert [row["team_id"] for row in next_live["rows"]] == [ids[-1]]
        assert client.get("/participant/leaderboard", params={"round_type": "ROUND1", "problem_id": first_id}).json() == []


def test_wildcard_top10_final_projection_uses_persisted_qualification(db, monkeypatch):
    now = datetime.now(timezone.utc)
    db.add_all([EventConfig(wildcard_slots=3), GameConfig(state="WILDCARD_BIDDING", current_round=2),
                RoundControl(round_type="WILDCARD", status="BIDDING_CLOSED", slot_count=3),
                RoundControl(round_type="ROUND1", ended=True)])
    db.add_all([ProblemStatement(ps_number=f"WC-{i}", title=f"Wildcard {i}", round=2, status="visible") for i in range(3)])
    teams = [Team(team_name=f"Wildcard bidder {i}", coins=0 if i == 0 else 5000) for i in range(12)]
    db.add_all(teams); db.flush()
    ids = [team.id for team in teams]
    db.add_all([Wildcard(team_id=team.id, status="applied") for team in teams])
    db.add_all([WildcardBid(team_id=team.id, amount=1300 - i * 10, timestamp=now + timedelta(seconds=i)) for i, team in enumerate(teams)])
    db.commit()
    with client_for(db, monkeypatch) as client:
        live = client.get("/public/leaderboard").json()
        assert live["mode"] == "WILDCARD_LIVE" and len(live["rows"]) == 10
        assert live["rows"][0]["team_id"] == ids[0]
        assert len(client.get("/participant/leaderboard", params={"round_type": "WILDCARD"}).json()) == 10
        response = client.post("/admin/wildcard/finalize")
        assert response.status_code == 200
        actual_ids = [row["team_id"] for row in response.json()["winners"]]
        assert actual_ids == ids[1:4]
        final = client.get("/public/leaderboard").json()
        assert final["mode"] == "WILDCARD_FINAL" and len(final["rows"]) == 10
        assert [row["team_id"] for row in final["rows"] if row["qualified"]] == actual_ids
        assert all(not row["qualified"] for row in final["rows"][3:])
        assert [row["rank"] for row in final["rows"]] == list(range(1, 11))
        assert all(row["finalized"] for row in client.get("/participant/leaderboard", params={"round_type": "WILDCARD"}).json())
        assert db.query(WildcardBid).count() == 12
        assert db.query(WalletTransaction).filter_by(transaction_type="WILDCARD_WIN").count() == 3


def test_all_live_projections_share_timestamp_then_team_id_ties(db, monkeypatch):
    now = datetime.now(timezone.utc)
    problem = ProblemStatement(ps_number="R1-1", title="Tie ordering", round=1)
    db.add_all([problem, EventConfig(), GameConfig(state="ROUND1_BIDDING", current_round=1)]); db.flush()
    db.add_all([RoundControl(round_type="ROUND1", status="BIDDING", current_problem_id=problem.id),
                RoundControl(round_type="WILDCARD", status="BIDDING_OPEN", slot_count=5)])
    teams = [Team(team_name=f"Tie team {i}") for i in range(12)]
    db.add_all(teams); db.flush()
    ids = [team.id for team in teams]
    for i, team in enumerate(teams):
        timestamp = now + timedelta(seconds=(11 - i) // 2)
        db.add_all([Bid(team_id=team.id, ps_id=problem.id, round=1, amount=100, timestamp=timestamp),
                    WildcardBid(team_id=team.id, amount=100, timestamp=timestamp), Wildcard(team_id=team.id, status="applied")])
    db.commit()
    expected = [ids[i] for i in [10, 11, 8, 9, 6, 7, 4, 5, 2, 3]]
    with client_for(db, monkeypatch) as client:
        assert [row["team_id"] for row in client.get("/public/leaderboard").json()["rows"]] == expected
        for round_type in ["ROUND1", "WILDCARD"]:
            assert [row["team_id"] for row in client.get("/participant/leaderboard", params={"round_type": round_type}).json()] == expected
