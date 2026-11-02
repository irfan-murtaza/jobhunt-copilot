from __future__ import annotations

import enum
import uuid

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from jobhunt.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class FitLabel(enum.StrEnum):
    GOOD_FIT = "good_fit"
    NOT_FIT = "not_fit"


class EvalLabel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A human label for one (user, job) pair. The ground truth for ranking evals."""

    __tablename__ = "eval_labels"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_eval_labels_user_id_job_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[FitLabel] = mapped_column(str_enum(FitLabel, "fit_label"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
