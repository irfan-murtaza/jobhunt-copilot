from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from jobhunt.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class DocumentKind(enum.StrEnum):
    RESUME = "resume"
    COVER_LETTER = "cover_letter"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tailored resume or cover letter generated for one job.

    `content` is the structured document (schemas.tailoring). `grounding_report` records,
    per generated claim, which evidence supports it and any unsupported claims found.
    Export is blocked while `grounding_report.blocking_issues` is non-empty and the user
    has not approved them.
    """

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_user_job_kind", "user_id", "job_id", "kind"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[DocumentKind] = mapped_column(
        str_enum(DocumentKind, "document_kind"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    grounding_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(512))
    model: Mapped[str | None] = mapped_column(String(100))
    cost_usd: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
