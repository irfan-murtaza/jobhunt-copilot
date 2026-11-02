from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobhunt.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from jobhunt.models.user import User

EMBEDDING_DIMENSIONS = 1536


class Profile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The candidate's structured profile.

    `document` holds the user-edited ProfileDocument (see schemas.profile) as JSON and is
    the single source of truth. `Evidence` rows are derived from it for retrieval.
    """

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    raw_text: Mapped[str | None] = mapped_column(Text)
    source_filename: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    user: Mapped[User] = relationship(back_populates="profile")
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )


class Evidence(UUIDPrimaryKeyMixin, Base):
    """One embeddable, citable fact from the profile (a bullet, project, skill or summary).

    `path` is a JSON-pointer-like locator into the profile document (e.g. "roles/0/bullets/2")
    so the grounding check can map a generated claim back to exactly where it came from.
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index(
            "ix_evidence_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # bullet|project|skill|summary
    path: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text)  # e.g. "Senior Engineer at Acme, 2021-2023"
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)

    profile: Mapped[Profile] = relationship(back_populates="evidence")
