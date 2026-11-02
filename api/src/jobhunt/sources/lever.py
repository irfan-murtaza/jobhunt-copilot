"""Lever public postings: https://api.lever.co/v0/postings/{company}?mode=json"""

from __future__ import annotations

from datetime import UTC, datetime

from jobhunt.models import JobSource
from jobhunt.sources.base import RawJob
from jobhunt.sources.http import SourceHttpClient


class LeverSource:
    name = JobSource.LEVER
    attribution = "Jobs from company career pages hosted on Lever."
    cooldown_seconds = 60
    cache_ttl_seconds = 1800

    def __init__(self, companies: list[str]) -> None:
        self._companies = companies

    async def fetch(self, http: SourceHttpClient) -> list[RawJob]:
        jobs: list[RawJob] = []
        for company in self._companies:
            result = await http.get(
                f"https://api.lever.co/v0/postings/{company}",
                source=f"{self.name}:{company}",
                params={"mode": "json"},
                cache_ttl=self.cache_ttl_seconds,
                cooldown=0,
            )
            for item in result.json():
                if not item.get("id"):
                    continue
                categories = item.get("categories") or {}
                parts = [item.get("descriptionPlain") or ""]
                for section in item.get("lists") or []:
                    from jobhunt.sources.html import html_to_text

                    parts.append(
                        f"{section.get('text', '')}\n{html_to_text(section.get('content'))}"
                    )
                parts.append(item.get("additionalPlain") or "")
                created = item.get("createdAt")
                jobs.append(
                    RawJob(
                        source=self.name,
                        source_id=f"{company}:{item['id']}",
                        url=item.get("hostedUrl")
                        or f"https://jobs.lever.co/{company}/{item['id']}",
                        title=item.get("text") or "Untitled",
                        company=company,
                        description="\n\n".join(p.strip() for p in parts if p.strip()),
                        location_text=categories.get("location") or item.get("workplaceType"),
                        tags=[
                            t
                            for t in (
                                categories.get("team"),
                                categories.get("commitment"),
                                item.get("workplaceType"),
                            )
                            if t
                        ],
                        posted_at=datetime.fromtimestamp(created / 1000, tz=UTC)
                        if isinstance(created, int | float)
                        else None,
                    )
                )
        return jobs
