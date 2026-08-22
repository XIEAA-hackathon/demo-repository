import csv
import io

from app.core.security import get_password_hash
from app.models.models import (
    Bid,
    EventActivityLog,
    GameConfig,
    Member,
    ProblemStatement,
    RoundControl,
    Submission,
    Team,
    User,
    Wildcard,
    WildcardBid,
    WildcardSelectionPool,
)


def _team(db, name, email, *, system=False):
    leader = User(
        name=f"{name} Leader",
        email=email,
        role="leader",
        password_hash=get_password_hash("temp-pass"),
        is_system_account=system,
    )
    db.add(leader)
    db.flush()
    team = Team(
        team_name=name,
        leader_id=leader.id,
        coins=1000,
        is_approved=True,
        is_system_team=system,
    )
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.add(Member(team_id=team.id, member_name="Member", email=f"member-{team.id}@reset.test"))
    db.commit()
    return leader, team


def _login(client, email, password="temp-pass"):
    response = client.post("/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_event_data_reset_preserves_system_access_and_supports_fresh_import(client, admin_headers, db):
    system_leader, system_team = _team(db, "Demo Team", "leader@demo.example.com", system=True)
    imported_alpha, alpha_team = _team(db, "Imported Team Alpha", "alpha@reset.test")
    imported_alpha_email = imported_alpha.email
    _imported_beta, beta_team = _team(db, "Imported Team Beta", "beta@reset.test")
    alpha_headers = _login(client, imported_alpha.email)
    assert client.post("/admin/event-data/reset", headers=alpha_headers, json={"confirmation": "RESET EVENT"}).status_code == 403
    assert client.post("/admin/event-data/reset", json={"confirmation": "RESET EVENT"}).status_code == 401

    round1 = ProblemStatement(ps_number="R1-1", title="Round", description="Round", round=1, status="current")
    wildcard_problem = ProblemStatement(ps_number="WC-1", title="Wildcard", description="Wildcard", round=2, status="allocated")
    db.add_all([round1, wildcard_problem])
    db.flush()
    alpha_team.ps_id = round1.id
    alpha_team.round1_problem_id = round1.id
    beta_team.ps_id = wildcard_problem.id
    beta_team.wildcard_problem_id = wildcard_problem.id
    db.add_all([
        Bid(team_id=alpha_team.id, ps_id=round1.id, amount=200, round=1),
        Wildcard(team_id=beta_team.id, status="selected", rank=1, winning_bid=300, problem_id=wildcard_problem.id),
        WildcardBid(team_id=beta_team.id, amount=300),
        WildcardSelectionPool(position=1, problem_id=wildcard_problem.id, selected_by_team_id=beta_team.id),
        Submission(team_id=alpha_team.id, problem_id=round1.id, submitted_by_user_id=imported_alpha.id, repository_url="https://github.com/example/reset"),
        RoundControl(round_type="ROUND1", status="READY", current_problem_id=round1.id),
        RoundControl(round_type="WILDCARD", status="COMPLETE", ended=True, slot_count=1),
    ])
    game = db.query(GameConfig).first()
    game.state = "ROUND1_BIDDING"
    db.commit()

    blocked = client.post("/admin/event-data/reset", headers=admin_headers, json={"confirmation": "RESET EVENT"})
    assert blocked.status_code == 409
    game.state = "WAITING"
    db.commit()

    reset = client.post("/admin/event-data/reset", headers=admin_headers, json={"confirmation": "RESET EVENT"})
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["status"] == "reset_complete"
    assert body["deleted"]["teams"] == 2
    assert body["deleted"]["participant_users"] == 2
    assert body["deleted"]["round1_problems"] == 1
    assert body["deleted"]["wildcard_problems"] == 1
    assert body["event_state"] == "WAITING"

    db.expire_all()
    assert db.query(Team).filter(Team.is_system_team.is_(False)).count() == 0
    assert db.query(User).filter(User.role.in_(("leader", "member")), User.is_system_account.is_(False)).count() == 0
    assert db.query(ProblemStatement).count() == 0
    assert db.query(Bid).count() == 0
    assert db.query(Wildcard).count() == 0
    assert db.query(WildcardBid).count() == 0
    assert db.query(WildcardSelectionPool).count() == 0
    assert db.query(Submission).count() == 0
    assert db.query(EventActivityLog).count() == 1
    controls = {row.round_type: row for row in db.query(RoundControl).all()}
    assert controls["ROUND1"].status == "IDLE" and controls["ROUND1"].current_problem_id is None
    assert controls["WILDCARD"].status == "NOT_STARTED" and controls["WILDCARD"].slot_count is None
    assert db.query(GameConfig).first().auction_timer_end is None

    # Existing Admin bearer token and permanent demo leader credentials remain valid.
    assert client.get("/admin/state", headers=admin_headers).status_code == 200
    assert _login(client, system_leader.email)
    assert client.post("/login", data={"username": imported_alpha_email, "password": "temp-pass"}).status_code == 401
    assert db.query(Team).filter(Team.id == system_team.id, Team.is_system_team.is_(True)).count() == 1

    registration = (
        "Team Name,Leader Name,Leader Email,Member 1 Name,Member 1 Email,Member 2 Name,Member 2 Email\n"
        "Real Event Team,Real Leader,real.leader@event.test,Member One,one@event.test,Member Two,two@event.test\n"
    ).encode()
    imported = client.post(
        "/admin/registration/import",
        headers=admin_headers,
        files={"file": ("real-event.csv", registration, "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["teams_created"] == 1
    download = client.get(
        f"/admin/registration/import/download/{imported.json()['download_token']}",
        headers=admin_headers,
    )
    assert download.status_code == 200
    row = next(csv.DictReader(io.StringIO(download.content.decode("utf-8-sig"))))
    generated = client.post(
        "/login",
        data={"username": row["Leader Login Email"], "password": row["Leader Password"]},
    )
    assert generated.status_code == 200
