import uuid

from app.core.security import create_access_token, get_password_hash
from app.models.models import EventConfig, GameConfig, ProblemStatement, RoundControl, Team, User


def _participant_headers(email: str, session_id: str) -> dict[str, str]:
    token = create_access_token({"sub": email, "role": "leader", "session_id": session_id})
    return {"Authorization": f"Bearer {token}"}


def test_each_round_one_problem_restarts_the_normal_auction_lifecycle(client, admin_headers, db):
    shared_hash = get_password_hash("round-one-test")
    participants = []
    for index in range(20):
        session_id = uuid.uuid4().hex
        email = f"round1-team-{index}@test.local"
        leader = User(
            name=f"Leader {index}",
            email=email,
            password_hash=shared_hash,
            role="leader",
            session_id=session_id,
        )
        db.add(leader)
        db.flush()
        team = Team(team_name=f"Round 1 Team {index}", coins=1000, leader_id=leader.id, is_approved=True)
        db.add(team)
        db.flush()
        leader.team_id = team.id
        participants.append((team.id, _participant_headers(email, session_id)))

    problems = [
        ProblemStatement(
            ps_number=f"R1-{index}",
            title=f"Problem {index}",
            description=f"Round 1 problem {index}",
            round=1,
            status="available",
        )
        for index in range(1, 5)
    ]
    db.add_all(problems)
    db.flush()
    db.add(RoundControl(round_type="ROUND1", status="READY"))
    event_config = db.query(EventConfig).one()
    event_config.bid_cooldown_seconds = 0
    game = db.query(GameConfig).one()
    game.state = "WAITING"
    game.current_round = 1
    db.commit()

    aggregate_count = 0
    for auction_index, problem in enumerate(problems[:3]):
        selected = client.post(
            f"/admin/rounds/round-1/problems/{problem.id}/select",
            headers=admin_headers,
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["event"]["event_state"] == "WAITING"
        assert selected.json()["current_problem"]["id"] == problem.id
        assert selected.json()["highest_bid"] is None
        assert selected.json()["final_auto_assignment"] is None

        preview = client.post("/admin/rounds/round-1/preview/start", headers=admin_headers)
        assert preview.status_code == 200, preview.text
        assert preview.json()["event"]["event_state"] == "ROUND1_PREVIEW"

        bidding = client.post("/admin/rounds/round-1/bidding/start", headers=admin_headers)
        assert bidding.status_code == 200, bidding.text
        assert bidding.json()["event"]["event_state"] == "ROUND1_BIDDING"

        eligible = participants[auction_index * 5:(auction_index + 1) * 5]
        for _team_id, headers in eligible:
            bid = client.post("/bid", headers=headers, json={"ps_id": problem.id, "increment": 5})
            assert bid.status_code == 200, bid.text

        leaderboard = client.get("/participant/leaderboard", headers=eligible[0][1])
        assert leaderboard.status_code == 200, leaderboard.text
        assert {row["team_id"] for row in leaderboard.json()} == {team_id for team_id, _headers in eligible}

        if auction_index:
            locked = client.post(
                "/bid",
                headers=participants[0][1],
                json={"ps_id": problem.id, "increment": 5},
            )
            assert locked.status_code == 409

        closed = client.post("/admin/rounds/round-1/bidding/close", headers=admin_headers)
        assert closed.status_code == 200, closed.text
        assigned = client.post("/admin/rounds/round-1/assign-winners", headers=admin_headers)
        assert assigned.status_code == 200, assigned.text
        assert len(assigned.json()["winners"]) == 5
        repeated = client.post("/admin/rounds/round-1/assign-winners", headers=admin_headers)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["winners"] == []
        aggregate_count += 5

        db.expire_all()
        control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one()
        assert control.round1_winning_bid_count == aggregate_count

    status = client.get("/admin/rounds/round-1", headers=admin_headers)
    assert status.status_code == 200
    final_auto = status.json()["final_auto_assignment"]
    assert final_auto["status"] == "PENDING"
    assert final_auto["problem"]["id"] == problems[3].id
    assert final_auto["team_count"] == 5
