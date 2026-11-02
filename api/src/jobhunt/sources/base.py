"""Common types for job-board adapters.

Each adapter turns one public API or feed into a list of `RawJob`s. Adapters do no
persistence and no LLM work; they only know how to speak to one upstream politely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from jobhunt.models import JobSource
from jobhunt.sources.http import SourceHttpClient


@dataclass(slots=True)
class RawJob:
    source: JobSource
    source_id: str
    url: str
    title: str
    company: str
    description: str  # plain text, HTML already stripped
    location_text: str | None = None
    salary_text: str | None = None
    tags: list[str] = field(default_factory=list)
    posted_at: datetime | None = None


class JobBoardSource(Protocol):
    name: JobSource
    attribution: str  # how the upstream asks to be credited; shown in the UI
    cooldown_seconds: int  # minimum gap between live requests to this upstream
    cache_ttl_seconds: int  # how long a fetched response may be reused

    async def fetch(self, http: SourceHttpClient) -> list[RawJob]: ...


class SourceError(Exception):
    """Upstream failure for one source. Other sources keep going."""
