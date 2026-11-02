from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobhunt.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class ApplicationStage(enum.StrEnum):
    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_user_stage", "user_id", "stage"),
        Index("ix_applications_user_job", "user_id", "job_id", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[ApplicationStage] = mapped_column(
        str_enum(ApplicationStage, "application_stage"),
        default=ApplicationStage.SAVED,
        nullable=False,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The exact tailored resume version that was sent.
    resume_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    cover_letter_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )

    events: Mapped[list[ApplicationEvent]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEvent.created_at",
        lazy="selectin",  # always shown with the application; also lets AsyncSession.refresh work
    )


class ApplicationEventKind(enum.StrEnum):
    STAGE_CHANGE = "stage_change"
    NOTE = "note"
    REMINDER = "reminder"


class ApplicationEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only history for an application: stage changes, notes, reminders."""

    __tablename__ = "application_events"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[ApplicationEventKind] = mapped_column(
        str_enum(ApplicationEventKind, "application_event_kind"), nullable=False
    )
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    source: Mapped[str] = mapped_column(
        String(16), default="user", nullable=False
    )  # user|mcp|agent

    application: Mapped[Application] = relationship(back_populates="events")
