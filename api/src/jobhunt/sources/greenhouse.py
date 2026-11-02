"""Greenhouse public job boards: https://boards-api.greenhouse.io/v1/boards/{board}/jobs"""

from __future__ import annotations

from datetime import UTC, datetime

from jobhunt.models import JobSource
from jobhunt.sources.base import RawJob
from jobhunt.sources.html import html_to_text
from jobhunt.sources.http import SourceHttpClient


class GreenhouseSource:
    name = JobSource.GREENHOUSE
    attribution = "Jobs from company career pages hosted on Greenhouse."
    cooldown_seconds = 60
    cache_ttl_seconds = 1800

    def __init__(self, boards: list[str]) -> None:
        self._boards = boards

    async def fetch(self, http: SourceHttpClient) -> list[RawJob]:
        jobs: list[RawJob] = []
        for board in self._boards:
            result = await http.get(
                f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
                source=f"{self.name}:{board}",
                params={"content": "true"},
                cache_ttl=self.cache_ttl_seconds,
                cooldown=0,
            )
            payload = result.json()
            company = (payload.get("meta") or {}).get("name") or board
            for item in payload.get("jobs", []):
                if not item.get("id"):
                    continue
                location = (item.get("location") or {}).get("name")
                departments = [
                    d.get("name") for d in item.get("departments") or [] if d.get("name")
                ]
                jobs.append(
                    RawJob(
                        source=self.name,
                        source_id=f"{board}:{item['id']}",
                        url=item.get("absolute_url")
                        or f"https://boards.greenhouse.io/{board}/jobs/{item['id']}",
                        title=item.get("title") or "Untitled",
                        company=company,
                        description=html_to_text(item.get("content")),
                        location_text=location,
                        tags=departments,
                        posted_at=_parse(item.get("updated_at") or item.get("first_published")),
                    )
                )
        return jobs


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
