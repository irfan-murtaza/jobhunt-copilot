from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jobhunt.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"  # finished, but some steps or items failed
    FAILED = "failed"


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of the daily LangGraph workflow for one user."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "run_status"), default=RunStatus.QUEUED, nullable=False
    )
    trigger: Mapped[str] = mapped_column(
        String(16), default="manual", nullable=False
    )  # manual|cron
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Counters per step: fetched, new, extracted, filtered, scored, judged, cost, latency...
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # The rendered digest (schemas.digest.DailyDigest) shown in the UI and emailed.
    digest: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    # LangGraph thread id, so a failed run can be resumed from its last checkpoint.
    thread_id: Mapped[str | None] = mapped_column(String(64))
