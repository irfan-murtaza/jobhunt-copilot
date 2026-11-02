from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from jobhunt.schemas.common import APIModel


class RegisterRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenResponse(APIModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - token *type*, not a secret
    expires_in: int  # seconds


class UserRead(APIModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    created_at: datetime
