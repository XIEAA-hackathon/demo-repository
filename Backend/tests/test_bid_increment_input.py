from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.api.auction import _place_round1_bid_transaction
from app.api.wildcard import _place_wildcard_bid_transaction
from app.core.security import create_access_token
from app.models.models import Bid, EventConfig, GameConfig, ProblemStatement, RoundControl, Team, User, Wildcard, WildcardBid


@pytest.fixture(params=['ROUND1', 'WILDCARD'])
def auction_setup(request, db):
    kind = request.param
    problem = ProblemStatement(ps_number='PS-INPUT', title='Input', round=1, status='current')
    db.add(problem)
    db.flush()
    db.add(EventConfig(round1_minimum_bid=100, wildcard_starting_bid=100, bid_cooldown_seconds=5))
    db.add(GameConfig(state=f'{kind}_BIDDING', current_round=1, auction_timer_end=datetime.now(timezone.utc) + timedelta(minutes=5)))
    db.add(RoundControl(round_type=kind, current_problem_id=problem.id if kind == 'ROUND1' else None,
                        status='BIDDING' if kind == 'ROUND1' else 'BIDDING_OPEN'))
    accounts = []
    for index in range(2):
        user = User(name=f'Leader {index}', email=f'input{index}@test.dev', password_hash='unused',
                    role='leader', session_id=f'input-session-{index}', credentials_active=True)
        db.add(user)
        db.flush()
        team = Team(team_name=f'Input {index}', leader_id=user.id, coins=900, is_approved=True)
        db.add(team)
        db.flush()
        user.team_id = team.id
        if kind == 'WILDCARD':
            db.add(Wildcard(team_id=team.id, status='applied'))
        token = create_access_token({'sub': user.email, 'session_id': user.session_id, 'role': 'leader'})
        accounts.append((user, team, {'Authorization': f'Bearer {token}'}))
    db.commit()
    return kind, problem.id, accounts


def _post(client, setup, increment, account=0):
    kind, problem_id, accounts = setup
    body = {'increment': increment}
    if kind == 'ROUND1':
        body['ps_id'] = problem_id
    return client.post('/bid' if kind == 'ROUND1' else '/wildcard/bid', json=body, headers=accounts[account][2])


@pytest.mark.parametrize('increment', [1, 2, 5, 10, 17, 25])
def test_integer_increment_accepted(client, auction_setup, increment):
    response = _post(client, auction_setup, increment)
    assert response.status_code == 200, response.text
    assert response.json()['amount'] == 100 + increment


@pytest.mark.parametrize('increment', [0, -1, -25, 26, 100, 999999, 1.5, 1.0, None, 'abc', '', '5', True])
def test_malformed_increment_never_reaches_calculation(client, db, auction_setup, increment):
    response = _post(client, auction_setup, increment)
    assert response.status_code == 422, response.text
    assert db.query(Bid).count() == db.query(WildcardBid).count() == 0


def test_wallet_cooldown_deadline_and_leader_guards(client, db, auction_setup):
    user, team, _ = auction_setup[2][0]
    team.coins = 100
    db.commit()
    assert _post(client, auction_setup, 1).status_code == 400
    team.coins = 900
    user.role = 'member'
    db.commit()
    assert _post(client, auction_setup, 1).status_code == 403
    user.role = 'leader'
    db.commit()
    assert _post(client, auction_setup, 1).status_code == 200
    cooldown = _post(client, auction_setup, 1)
    assert cooldown.status_code == 429
    assert 0 < cooldown.json()['retry_after_seconds'] <= 5
    db.query(GameConfig).one().auction_timer_end = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert _post(client, auction_setup, 1).status_code == 409


def test_waiting_bid_adds_to_latest_committed_price(db, session_factory, auction_setup):
    kind, problem_id, accounts = auction_setup
    user, _, _ = accounts[0]
    email, session_id = user.email, user.session_id
    other_team_id = accounts[1][1].id
    transaction = _place_round1_bid_transaction if kind == 'ROUND1' else _place_wildcard_bid_transaction
    arguments = {'email': email, 'session_id': session_id, 'increment': 20}
    if kind == 'ROUND1':
        arguments['problem_id'] = problem_id
    # Hold the same auction lock used by a competing request. Its 110 bid
    # commits before the waiting +20 request can read the current price.
    with session_factory() as competitor:
        competitor.query(RoundControl).filter(RoundControl.round_type == kind).with_for_update().one()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(transaction, session_factory, **arguments)
            if kind == 'ROUND1':
                competitor.add(Bid(team_id=other_team_id, ps_id=problem_id, amount=110, round=1))
            else:
                competitor.add(WildcardBid(team_id=other_team_id, amount=110))
            competitor.commit()
            assert pending.result(timeout=15).amount == 130
