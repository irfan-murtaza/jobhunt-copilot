from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jobhunt.models.base import Base, UUIDPrimaryKeyMixin


class SourceFetch(UUIDPrimaryKeyMixin, Base):
    """Log of every upstream request, for conditional requests and polite rate limiting."""

    __tablename__ = "source_fetches"
    __table_args__ = (Index("ix_source_fetches_source_fetched", "source", "fetched_at"),)

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(64))
    items_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
