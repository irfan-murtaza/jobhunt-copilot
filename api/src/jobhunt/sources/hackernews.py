"""Hacker News "Ask HN: Who is hiring?" via the Algolia HN Search API.

Posts are free text, so title, company and location are parsed heuristically from the
conventional first line "Company | Role | Location | REMOTE | ...". The LLM extraction
step cleans this up; anything that does not mention remote work is skipped here.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, cast

from jobhunt.models import JobSource
from jobhunt.sources.base import RawJob, SourceError
from jobhunt.sources.html import html_to_text
from jobhunt.sources.http import SourceHttpClient

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
COMMENTS_URL = "https://hn.algolia.com/api/v1/search"
_REMOTE = re.compile(r"\bremote\b", re.IGNORECASE)
_ONSITE_ONLY = re.compile(r"\b(no remote|onsite only|on-site only)\b", re.IGNORECASE)


class HackerNewsSource:
    name = JobSource.HACKERNEWS
    attribution = "Posts from Hacker News 'Who is hiring?' threads via the Algolia HN Search API."
    cooldown_seconds = 600
    cache_ttl_seconds = 3600

    def __init__(self, max_pages: int = 5) -> None:
        self._max_pages = max_pages

    async def fetch(self, http: SourceHttpClient) -> list[RawJob]:
        story = await self._latest_thread(http)
        story_id = str(story["objectID"])
        jobs: list[RawJob] = []
        for page in range(self._max_pages):
            result = await http.get(
                COMMENTS_URL,
                source=self.name,
                params={"tags": f"comment,story_{story_id}", "hitsPerPage": 200, "page": page},
                cache_ttl=self.cache_ttl_seconds,
                cooldown=self.cooldown_seconds if page == 0 else 0,
            )
            payload = result.json()
            for hit in payload.get("hits", []):
                if str(hit.get("parent_id")) != story_id:
                    continue  # replies, not postings
                job = parse_posting(hit, thread_title=story.get("title", ""))
                if job is not None:
                    jobs.append(job)
            if page + 1 >= int(payload.get("nbPages", 1)):
                break
        return jobs

    async def _latest_thread(self, http: SourceHttpClient) -> dict[str, Any]:
        result = await http.get(
            SEARCH_URL,
            source=self.name,
            params={"tags": "story,author_whoishiring", "query": "Who is hiring", "hitsPerPage": 5},
            cache_ttl=self.cache_ttl_seconds,
        )
        for hit in result.json().get("hits", []):
            if "who is hiring" in (hit.get("title") or "").lower():
                return cast("dict[str, Any]", hit)
        raise SourceError("No 'Who is hiring' thread found")


def parse_posting(hit: dict[str, Any], *, thread_title: str = "") -> RawJob | None:
    text = html_to_text(hit.get("comment_text"))
    if not text or not _REMOTE.search(text) or _ONSITE_ONLY.search(text):
        return None
    first_line, _, _ = text.partition("\n")
    segments = [s.strip() for s in first_line.split("|") if s.strip()]
    company = segments[0][:200] if segments else "Unknown"
    title = segments[1][:300] if len(segments) > 1 else first_line[:300]
    location = next(
        (s for s in segments[2:] if _REMOTE.search(s) or any(c.isupper() for c in s)), None
    )
    created = hit.get("created_at_i")
    return RawJob(
        source=JobSource.HACKERNEWS,
        source_id=str(hit["objectID"]),
        url=f"https://news.ycombinator.com/item?id={hit['objectID']}",
        title=title,
        company=company,
        description=text,
        location_text=location,
        tags=[thread_title] if thread_title else [],
        posted_at=datetime.fromtimestamp(created, tz=UTC) if isinstance(created, int) else None,
    )
