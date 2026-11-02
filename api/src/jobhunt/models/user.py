from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobhunt.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from jobhunt.models.profile import Profile


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))

    profile: Mapped[Profile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    preferences: Mapped[Preferences | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Preferences(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-user hard-filter settings that gate which jobs are worth scoring."""

    __tablename__ = "preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # ISO 3166-1 alpha-2 country the candidate lives in, e.g. "PK". Drives location eligibility.
    country: Mapped[str | None] = mapped_column(String(2))
    timezone: Mapped[str | None] = mapped_column(String(64))  # IANA zone, e.g. "Asia/Karachi"
    min_salary_usd: Mapped[int | None] = mapped_column(Integer)
    seniority_levels: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    excluded_keywords: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list)
    required_keywords: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list)
    shortlist_size: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    judge_pool_size: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    digest_email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="preferences")
