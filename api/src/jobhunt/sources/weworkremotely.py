"""We Work Remotely RSS feeds (https://weworkremotely.com/remote-jobs.rss)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from jobhunt.models import JobSource
from jobhunt.sources.base import RawJob
from jobhunt.sources.html import html_to_text
from jobhunt.sources.http import SourceHttpClient

DEFAULT_FEEDS = (
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
)


class WeWorkRemotelySource:
    name = JobSource.WEWORKREMOTELY
    attribution = "Jobs from We Work Remotely (weworkremotely.com)."
    cooldown_seconds = 600
    cache_ttl_seconds = 3600

    def __init__(self, feeds: tuple[str, ...] = DEFAULT_FEEDS) -> None:
        self._feeds = feeds

    async def fetch(self, http: SourceHttpClient) -> list[RawJob]:
        jobs: dict[str, RawJob] = {}
        for index, feed in enumerate(self._feeds):
            result = await http.get(
                feed,
                source=self.name,
                cache_ttl=self.cache_ttl_seconds,
                # One cooldown per run: only the first feed in a run pays it.
                cooldown=self.cooldown_seconds if index == 0 else 0,
            )
            for job in parse_feed(result.text):
                jobs.setdefault(job.source_id, job)
        return list(jobs.values())


def parse_feed(xml_text: str) -> list[RawJob]:
    root = ET.fromstring(xml_text)  # noqa: S314 - see module note
    jobs: list[RawJob] = []
    for item in root.iter("item"):
        link = _text(item, "link")
        title_raw = _text(item, "title")
        if not link or not title_raw:
            continue
        company, _, title = title_raw.partition(": ")
        if not title:
            company, title = "Unknown", title_raw
        guid = _text(item, "guid") or link
        jobs.append(
            RawJob(
                source=JobSource.WEWORKREMOTELY,
                source_id=guid.rstrip("/").rsplit("/", 1)[-1] or guid,
                url=link,
                title=title.strip(),
                company=company.strip(),
                description=html_to_text(_text(item, "description")),
                location_text=_text(item, "region") or None,
                tags=[t for t in (_text(item, "category"), _text(item, "type")) if t],
                posted_at=_parse_rfc822(_text(item, "pubDate")),
            )
        )
    return jobs


def _text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None else ""


def _parse_rfc822(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
