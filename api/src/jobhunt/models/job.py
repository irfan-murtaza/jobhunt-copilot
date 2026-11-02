from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobhunt.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from jobhunt.models.profile import EMBEDDING_DIMENSIONS


class JobSource(enum.StrEnum):
    REMOTIVE = "remotive"
    REMOTEOK = "remoteok"
    WEWORKREMOTELY = "weworkremotely"
    HACKERNEWS = "hackernews"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    MANUAL = "manual"


class ExtractionStatus(enum.StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A normalized job posting. Shared across users; nothing user-specific lives here."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_jobs_source_source_id"),
        Index("ix_jobs_posted_at", "posted_at"),
        Index("ix_jobs_dedup_group_id", "dedup_group_id"),
        Index(
            "ix_jobs_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    source: Mapped[JobSource] = mapped_column(str_enum(JobSource, "job_source"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    company_normalized: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    location_text: Mapped[str | None] = mapped_column(String(300))
    salary_text: Mapped[str | None] = mapped_column(String(200))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Dedup: jobs in the same group are the same posting seen on several boards.
    # The group id is the id of the first job seen (the canonical one).
    dedup_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # LLM extraction (schemas.job.JobExtraction) and its bookkeeping
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        str_enum(ExtractionStatus, "extraction_status"),
        default=ExtractionStatus.PENDING,
        nullable=False,
    )
    extraction_error: Mapped[str | None] = mapped_column(Text)
    extraction_model: Mapped[str | None] = mapped_column(String(100))
    extraction_cost_usd: Mapped[float | None] = mapped_column(Float)
    extraction_latency_ms: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    # Who added it, for manual pastes. Null for feed sources.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    scores: Mapped[list[JobScore]] = relationship(back_populates="job", passive_deletes=True)


class JobScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-user fit assessment of one job: filters, hybrid score and the LLM judgement."""

    __tablename__ = "job_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_job_scores_user_id_job_id"),
        Index("ix_job_scores_user_hybrid", "user_id", "hybrid_score"),
        Index("ix_job_scores_user_judge", "user_id", "judge_score"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Stage 1: hard filters
    passed_filters: Mapped[bool] = mapped_column(Boolean, nullable=False)
    filter_reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    # Stage 2: hybrid score (0..1)
    similarity_score: Mapped[float | None] = mapped_column(Float)
    skill_coverage: Mapped[float | None] = mapped_column(Float)
    hybrid_score: Mapped[float | None] = mapped_column(Float)
    matched_evidence_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)

    # Stage 3: LLM-as-judge (0..100), schemas.scoring.FitJudgement
    judge_score: Mapped[int | None] = mapped_column(Integer)
    judgement: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    judge_model: Mapped[str | None] = mapped_column(String(100))
    judge_cost_usd: Mapped[float | None] = mapped_column(Float)
    judge_latency_ms: Mapped[int | None] = mapped_column(Integer)
    judged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[Job] = relationship(back_populates="scores")
