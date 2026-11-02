"""Email + password authentication with short-lived access and cookie-borne refresh tokens."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from sqlalchemy import select

from jobhunt.api.deps import CurrentUser, SessionDep, SettingsDep
from jobhunt.core.config import get_settings
from jobhunt.core.ratelimit import limiter
from jobhunt.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from jobhunt.models import Preferences, User
from jobhunt.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead
from jobhunt.schemas.common import Message

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "jobhunt_refresh"


def _auth_limit() -> str:
    return get_settings().rate_limit_auth


def _set_refresh_cookie(response: Response, token: str, settings: SettingsDep) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/auth",
    )


def _token_response(response: Response, settings: SettingsDep, user: User) -> TokenResponse:
    _set_refresh_cookie(response, create_refresh_token(settings, user.id), settings)
    return TokenResponse(
        access_token=create_access_token(settings, user.id),
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(_auth_limit)
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    email = body.email.lower()
    exists = await session.scalar(select(User.id).where(User.email == email))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email, password_hash=hash_password(body.password), display_name=body.display_name
    )
    user.preferences = Preferences()
    session.add(user)
    await session.flush()
    return _token_response(response, settings, user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(_auth_limit)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    # Verify even when the user is missing so timing does not reveal which emails exist.
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _token_response(response, settings, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")
    try:
        user_id = decode_token(settings, refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return _token_response(response, settings, user)


@router.post("/logout", response_model=Message)
async def logout(response: Response) -> Message:
    response.delete_cookie(REFRESH_COOKIE, path="/auth")
    return Message(detail="Logged out")


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> User:
    return user


_DUMMY_HASH = hash_password("not-a-real-password-just-for-constant-time")
