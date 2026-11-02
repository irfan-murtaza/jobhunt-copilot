"""RemoteOK public API: https://remoteok.com/api (JSON).

Terms: the first array element is a legal notice; listings must link back to RemoteOK.
"""

from __future__ import annotations

from datetime import UTC, datetime

from jobhunt.models import JobSource
from jobhunt.sources.base import RawJob
from jobhunt.sources.html import html_to_text
from jobhunt.sources.http import SourceHttpClient

API_URL = "https://remoteok.com/api"


class RemoteOKSource:
    name = JobSource.REMOTEOK
    attribution = (
        "Jobs from RemoteOK (remoteok.com). "
        "Listings link back to RemoteOK as its API terms require."
    )
    cooldown_seconds = 600
    cache_ttl_seconds = 3600

    async def fetch(self, http: SourceHttpClient) -> list[RawJob]:
        result = await http.get(
            API_URL,
            source=self.name,
            cache_ttl=self.cache_ttl_seconds,
            cooldown=self.cooldown_seconds,
        )
        jobs: list[RawJob] = []
        for item in result.json():
            if not isinstance(item, dict) or "legal" in item or not item.get("id"):
                continue
            salary = _salary_text(item.get("salary_min"), item.get("salary_max"))
            jobs.append(
                RawJob(
                    source=self.name,
                    source_id=str(item["id"]),
                    url=item.get("url")
                    or f"https://remoteok.com/remote-jobs/{item.get('slug', item['id'])}",
                    title=item.get("position") or "Untitled",
                    company=item.get("company") or "Unknown",
                    description=html_to_text(item.get("description")),
                    location_text=item.get("location") or None,
                    salary_text=salary,
                    tags=[t for t in (item.get("tags") or []) if isinstance(t, str)],
                    posted_at=_posted_at(item),
                )
            )
        return jobs


def _salary_text(low: object, high: object) -> str | None:
    if isinstance(low, int | float) and isinstance(high, int | float) and (low or high):
        return f"${int(low):,} - ${int(high):,} USD/year"
    return None


def _posted_at(item: dict[str, object]) -> datetime | None:
    epoch = item.get("epoch")
    if isinstance(epoch, int | float) and epoch > 0:
        return datetime.fromtimestamp(epoch, tz=UTC)
    date = item.get("date")
    if isinstance(date, str):
        try:
            parsed = datetime.fromisoformat(date.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None
