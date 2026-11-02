"""Password hashing and JWT issuance.

Access tokens are short-lived bearer tokens sent in the Authorization header.
Refresh tokens are longer-lived, carry a different `type` claim so one can never be
used in place of the other, and are delivered to the browser as an httpOnly cookie.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from pwdlib import PasswordHash

from jobhunt.core.config import Settings

TokenType = Literal["access", "refresh"]
ALGORITHM = "HS256"

_password_hasher = PasswordHash.recommended()  # argon2id


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hasher.verify(password, password_hash)


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or of the wrong type."""


def create_token(
    settings: Settings, *, subject: uuid.UUID, token_type: TokenType, expires_in: timedelta
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)


def create_access_token(settings: Settings, user_id: uuid.UUID) -> str:
    return create_token(
        settings,
        subject=user_id,
        token_type="access",
        expires_in=timedelta(minutes=settings.access_token_minutes),
    )


def create_refresh_token(settings: Settings, user_id: uuid.UUID) -> str:
    return create_token(
        settings,
        subject=user_id,
        token_type="refresh",
        expires_in=timedelta(days=settings.refresh_token_days),
    )


def decode_token(settings: Settings, token: str, *, expected_type: TokenType) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError(f"expected {expected_type} token")
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenError("invalid subject") from exc
