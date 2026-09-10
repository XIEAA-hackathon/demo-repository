from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.api.auth import decode_bid_auth_claims
from app.core.security import create_access_token


def test_bid_auth_claims_decode_without_database_access():
    token = create_access_token({
        "sub": "leader@example.com",
        "role": "leader",
        "session_id": "signed-session",
    })

    claims = decode_bid_auth_claims(token)

    assert claims.email == "leader@example.com"
    assert claims.session_id == "signed-session"
    assert claims.role == "leader"


@pytest.mark.parametrize("claims", [
    {"sub": "leader@example.com"},
    {"session_id": "signed-session"},
])
def test_bid_auth_claims_require_identity_and_session(claims):
    with pytest.raises(HTTPException) as rejected:
        decode_bid_auth_claims(create_access_token(claims))

    assert rejected.value.status_code == 401


def test_bid_auth_claims_reject_expired_token():
    token = create_access_token(
        {"sub": "leader@example.com", "session_id": "expired-session"},
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(HTTPException) as rejected:
        decode_bid_auth_claims(token)

    assert rejected.value.status_code == 401
