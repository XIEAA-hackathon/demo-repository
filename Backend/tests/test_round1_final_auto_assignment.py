from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, WalletTransaction
from app.services.round1_auto_assignment import (
    auto_assign_final_problem,
    final_problem_price,
    update_round1_winning_bid_aggregate,
)


def _seed_final_problem_case(db, remaining_count: int, *, prices: list[int] | None = None, base_price: int = 150):
    db.add_all([EventConfig(round1_minimum_bid=base_price), GameConfig(state="ROUND1_RESULT")])
    prior = ProblemStatement(ps_number="R1-1", title="Prior", description="Prior", round=1, status="completed")
    final = ProblemStatement(ps_number="R1-2", title="Final", description="Final description", round=1, status="available")
    control = RoundControl(
        round_type="ROUND1",
        status="READY",
        round1_winning_bid_sum=sum(prices or []),
        round1_winning_bid_count=len(prices or []),
    )
    db.add_all([prior, final, control])
    db.flush()
    for index, amount in enumerate(prices or []):
        team = Team(team_name=f"Winner {index}", coins=1000 - amount, ps_id=prior.id, round1_problem_id=prior.id, is_approved=True)
        db.add(team)
        db.flush()
        db.add(WalletTransaction(
            team_id=team.id,
            transaction_type="ROUND1_WIN",
            amount=-amount,
            description=f"Prior winner {index}",
        ))
    for index in range(remaining_count):
        db.add(Team(team_name=f"Remaining {index}", coins=1000, is_approved=True))
    db.commit()
    return control.id, final.id


@pytest.mark.parametrize("remaining_count", [5, 3, 7])
def test_final_problem_assigns_any_number_of_remaining_teams_at_running_average(db, remaining_count):
    control_id, final_id = _seed_final_problem_case(db, remaining_count, prices=[100, 200, 300, 400])
    result = auto_assign_final_problem(db, db.get(RoundControl, control_id))
    db.commit()

    assert result["status"] == "COMPLETED"
    assert result["team_count"] == remaining_count
    assert result["calculated_cost"] == 250
    teams = db.query(Team).filter(Team.team_name.like("Remaining %")).all()
    assert len(teams) == remaining_count
    assert all(team.round1_problem_id == final_id and team.ps_id == final_id for team in teams)
    assert all(team.round1_assignment_type == "AUTO_FINAL_PROBLEM" for team in teams)
    assert all(team.round1_assignment_cost == 250 and team.coins == 750 for team in teams)
    control = db.get(RoundControl, control_id)
    assert control.round1_winning_bid_sum == 1000
    assert control.round1_winning_bid_count == 4
    assert control.status == "READY" and control.ended is not True and control.current_problem_id is None
    assert db.query(GameConfig).one().state == "ROUND1_RESULT"


def test_final_problem_uses_base_price_and_caps_charge_at_balance(db):
    control_id, final_id = _seed_final_problem_case(db, 2, base_price=150)
    teams = db.query(Team).filter(Team.team_name.like("Remaining %")).order_by(Team.id).all()
    teams[0].coins = 40
    teams[1].coins = 0
    db.commit()

    result = auto_assign_final_problem(db, db.get(RoundControl, control_id))
    db.commit()

    assert result["calculated_cost"] == 150
    db.expire_all()
    teams = db.query(Team).filter(Team.team_name.like("Remaining %")).order_by(Team.id).all()
    assert [(team.round1_problem_id, team.round1_assignment_cost, team.coins) for team in teams] == [
        (final_id, 40, 0),
        (final_id, 0, 0),
    ]


def test_final_problem_double_finalization_is_idempotent(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'round1-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with factory() as db:
        control_id, final_id = _seed_final_problem_case(db, 3, prices=[100, 200, 300])

    def finalize():
        with factory() as session:
            result = auto_assign_final_problem(session, session.get(RoundControl, control_id))
            session.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: finalize(), range(2)))

    with factory() as db:
        teams = db.query(Team).filter(Team.team_name.like("Remaining %")).all()
        transactions = db.query(WalletTransaction).filter(
            WalletTransaction.transaction_type == "ROUND1_AUTO_FINAL"
        ).all()
        assert all(team.round1_problem_id == final_id and team.coins == 800 for team in teams)
        assert len(transactions) == 3
        assert db.get(RoundControl, control_id).final_auto_assignment_team_count == 3
    assert all(result["status"] == "COMPLETED" for result in results)
    engine.dispose()


def test_running_aggregate_uses_final_winners_only_and_rounds_half_up(db):
    db.add_all([EventConfig(round1_minimum_bid=75), GameConfig(state="ROUND1_RESULT")])
    control = RoundControl(round_type="ROUND1", status="READY")
    db.add(control)
    db.flush()
    auctions = [
        [100, 200, 300, 400, 500],
        [200, 300, 400, 500, 600],
        [300, 400, 500, 600, 700],
    ]
    expected = [(1500, 5, 300), (3500, 10, 350), (6000, 15, 400)]
    for index, (amounts, aggregate) in enumerate(zip(auctions, expected), start=1):
        problem = ProblemStatement(
            ps_number=f"R1-{index}",
            title=f"Problem {index}",
            description="Normal auction",
            round=1,
            status="current",
        )
        db.add(problem)
        db.flush()
        assert update_round1_winning_bid_aggregate(control, problem, amounts) is True
        problem.status = "completed"
        assert update_round1_winning_bid_aggregate(control, problem, amounts) is False
        assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == aggregate[:2]
        assert final_problem_price(db, control) == aggregate[2]


def test_reset_event_clears_aggregate_but_reset_credentials_preserves_it(client, admin_headers, db):
    control = RoundControl(round_type="ROUND1", status="READY")
    db.add(control)
    db.flush()
    control.round1_winning_bid_sum = 6000
    control.round1_winning_bid_count = 15
    db.commit()

    credentials_reset = client.post(
        "/admin/registration/credentials/reset",
        headers=admin_headers,
        json={"confirmation": "RESET CREDENTIALS"},
    )
    assert credentials_reset.status_code == 200, credentials_reset.text
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one()
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (6000, 15)

    event_reset = client.post(
        "/admin/event-data/reset",
        headers=admin_headers,
        json={"confirmation": "RESET EVENT"},
    )
    assert event_reset.status_code == 200, event_reset.text
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one()
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (0, 0)


def test_legacy_normal_finalize_updates_aggregate_once(client, admin_headers, db):
    problem = ProblemStatement(
        ps_number="R1-LEGACY",
        title="Legacy finalize",
        description="Normal Round 1 auction",
        round=1,
        status="current",
    )
    db.add(problem)
    db.flush()
    for index, amount in enumerate((100, 200, 300, 400, 500, 600), start=1):
        team = Team(team_name=f"Legacy Team {index}", coins=1000, is_approved=True)
        db.add(team)
        db.flush()
        db.add(Bid(team_id=team.id, ps_id=problem.id, amount=amount, round=1))
    db.query(GameConfig).one().state = "ROUND1_BIDDING"
    db.commit()

    first = client.post(f"/admin/auction/{problem.id}/finalize", headers=admin_headers)
    assert first.status_code == 200, first.text
    second = client.post(f"/admin/auction/{problem.id}/finalize", headers=admin_headers)
    assert second.status_code == 200, second.text
    db.expire_all()
    control = db.query(RoundControl).filter(RoundControl.round_type == "ROUND1").one()
    assert (control.round1_winning_bid_sum, control.round1_winning_bid_count) == (2000, 5)
