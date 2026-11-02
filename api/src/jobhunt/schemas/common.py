from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base for all request/response models: ORM-friendly and strict about unknown keys."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Message(APIModel):
    detail: str
