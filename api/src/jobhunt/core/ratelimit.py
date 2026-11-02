"""API rate limiting via slowapi.

Keyed by authenticated user when a bearer token is present, otherwise by client IP, so a
single abusive account cannot exhaust the anonymous budget of everyone behind one NAT.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from jobhunt.core.config import get_settings


def _rate_limit_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and len(auth) > 7:
        # Cheap and sufficient: the token itself identifies the session.
        return f"token:{auth[7:][:64]}"
    return f"ip:{get_remote_address(request)}"


def build_limiter() -> Limiter:
    settings = get_settings()
    return Limiter(
        key_func=_rate_limit_key,
        default_limits=[settings.rate_limit_default],
        storage_uri=str(settings.redis_url),
        enabled=not settings.is_test,
        headers_enabled=True,
    )


limiter = build_limiter()
