import uuid
from datetime import timedelta

import pytest

from jobhunt.core.config import get_settings
from jobhunt.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("hunter22-hunter22")
    assert hashed != "hunter22-hunter22"
    assert verify_password("hunter22-hunter22", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip() -> None:
    settings = get_settings()
    user_id = uuid.uuid4()
    token = create_access_token(settings, user_id)
    assert decode_token(settings, token, expected_type="access") == user_id


def test_refresh_token_cannot_be_used_as_access() -> None:
    settings = get_settings()
    token = create_refresh_token(settings, uuid.uuid4())
    with pytest.raises(TokenError):
        decode_token(settings, token, expected_type="access")


def test_expired_token_rejected() -> None:
    settings = get_settings()
    token = create_token(
        settings, subject=uuid.uuid4(), token_type="access", expires_in=timedelta(seconds=-1)
    )
    with pytest.raises(TokenError):
        decode_token(settings, token, expected_type="access")


def test_tampered_token_rejected() -> None:
    settings = get_settings()
    token = create_access_token(settings, uuid.uuid4())
    with pytest.raises(TokenError):
        decode_token(settings, token[:-3] + "abc", expected_type="access")
