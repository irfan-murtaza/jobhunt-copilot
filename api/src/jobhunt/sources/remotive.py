"""Remotive public API: https://remotive.com/api/remote-jobs (JSON, no auth)."""

from __future__ import annotations

from datetime import datetime

from jobhunt.models import JobSource
from jobhunt.sources.base import RawJob
from jobhunt.sources.html import html_to_text
from jobhunt.sources.http import SourceHttpClient

API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource:
    name = JobSource.REMOTIVE
    attribution = "Jobs from Remotive (remotive.com). Link back to the original listing."
    cooldown_seconds = 300
    cache_ttl_seconds = 1800

    def __init__(self, category: str | None = "software-dev", limit: int | None = None) -> None:
        self._params = {k: v for k, v in (("category", category), ("limit", limit)) if v}

    async def fetch(self, http: SourceHttpClient) -> list[RawJob]:
        result = await http.get(
            API_URL,
            source=self.name,
            params=self._params or None,
            cache_ttl=self.cache_ttl_seconds,
            cooldown=self.cooldown_seconds,
        )
        jobs: list[RawJob] = []
        for item in result.json().get("jobs", []):
            if not item.get("id") or not item.get("title"):
                continue
            jobs.append(
                RawJob(
                    source=self.name,
                    source_id=str(item["id"]),
                    url=item.get("url") or f"https://remotive.com/remote-jobs/{item['id']}",
                    title=item["title"],
                    company=item.get("company_name") or "Unknown",
                    description=html_to_text(item.get("description")),
                    location_text=item.get("candidate_required_location") or None,
                    salary_text=item.get("salary") or None,
                    tags=[t for t in (item.get("tags") or []) if isinstance(t, str)]
                    + [t for t in (item.get("category"), item.get("job_type")) if t],
                    posted_at=_parse_dt(item.get("publication_date")),
                )
            )
        return jobs


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    from datetime import UTC

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
