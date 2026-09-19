from app.core.security import get_password_hash
from app.models.models import GameConfig, RoundControl, Team, User, Wildcard
from app.services.event_service import get_or_create_round_control


def _leader_team(db, *, email="wildcard-leader@test.local"):
    leader = User(name="Wildcard Leader", email=email, password_hash=get_password_hash("temp-pass"), role="leader")
    db.add(leader)
    db.flush()
    team = Team(team_name=f"Team {leader.id}", coins=1000, leader_id=leader.id, is_approved=True)
    db.add(team)
    db.flush()
    leader.team_id = team.id
    db.commit()
    return leader, team


def test_fresh_wildcard_control_is_openable_state(db):
    wildcard = get_or_create_round_control(db, "WILDCARD")

    assert wildcard.status == "NOT_STARTED"
    assert wildcard.ended is False
    assert wildcard.applications_open is False
    assert wildcard.slot_count is None


def test_wildcard_applications_require_round_one_to_end(client, admin_headers, db):
    db.add_all([
        RoundControl(round_type="ROUND1", status="READY", ended=False),
        RoundControl(round_type="WILDCARD", status="NOT_STARTED", ended=False, applications_open=False),
    ])
    db.commit()

    response = client.post("/admin/rounds/wildcard/applications/open", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "End Round 1 before opening Wildcard applications."


def test_wildcard_applications_open_while_wildcard_is_not_ended(client, admin_headers, db):
    db.add_all([
        RoundControl(round_type="ROUND1", status="CLOSED", ended=True),
        RoundControl(round_type="WILDCARD", status="NOT_STARTED", ended=False, applications_open=False),
    ])
    db.commit()

    response = client.post("/admin/rounds/wildcard/applications/open", headers=admin_headers)

    assert response.status_code == 200, response.text
    db.expire_all()
    wildcard = db.query(RoundControl).filter_by(round_type="WILDCARD").one()
    game = db.query(GameConfig).one()
    assert wildcard.ended is False
    assert wildcard.status == "APPLICATIONS_OPEN"
    assert wildcard.applications_open is True
    assert game.state == "WILDCARD_APPLICATION"
    assert game.auction_timer_end is not None


def test_leader_can_apply_only_while_wildcard_applications_are_open(
    client, admin_headers, db, login_headers_factory,
):
    leader, team = _leader_team(db)
    db.add_all([
        RoundControl(round_type="ROUND1", status="CLOSED", ended=True),
        RoundControl(round_type="WILDCARD", status="NOT_STARTED", ended=False, applications_open=False),
    ])
    db.commit()
    assert client.post("/admin/rounds/wildcard/applications/open", headers=admin_headers).status_code == 200
    leader_headers = login_headers_factory(leader.email)

    applied = client.post("/wildcard/apply", headers=leader_headers)

    assert applied.status_code == 200, applied.text
    assert db.query(Wildcard).filter_by(team_id=team.id).one().status == "applied"
    assert client.post("/admin/rounds/wildcard/applications/close", headers=admin_headers).status_code == 200
    rejected = client.post("/wildcard/apply", headers=leader_headers)
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "Wildcard applications are closed."
