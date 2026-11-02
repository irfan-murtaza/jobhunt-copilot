"""Adapter tests against recorded fixture payloads served through an httpx mock transport."""

import json
from pathlib import Path

import httpx
import pytest

from jobhunt.models import JobSource
from jobhunt.sources.greenhouse import GreenhouseSource
from jobhunt.sources.hackernews import HackerNewsSource, parse_posting
from jobhunt.sources.html import html_to_text
from jobhunt.sources.http import SourceHttpClient
from jobhunt.sources.lever import LeverSource
from jobhunt.sources.remoteok import RemoteOKSource
from jobhunt.sources.remotive import RemotiveSource
from jobhunt.sources.weworkremotely import WeWorkRemotelySource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def mock_http(
    routes: dict[str, str], *, content_type: str = "application/json"
) -> SourceHttpClient:
    """Route URL substrings to fixture bodies; anything else is a 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        for needle, body in routes.items():
            if needle in str(request.url):
                return httpx.Response(200, text=body, headers={"content-type": content_type})
        return httpx.Response(404, text="not mocked: " + str(request.url))

    return SourceHttpClient(transport=httpx.MockTransport(handler))


def test_html_to_text_handles_lists_breaks_and_double_escaping() -> None:
    assert html_to_text("<p>Hi</p><ul><li>A</li><li>B</li></ul>x<br>y") == "Hi\n\n- A\n- B\nx\ny"
    assert (
        html_to_text("&lt;p&gt;Join&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Go&lt;/li&gt;&lt;/ul&gt;")
        == "Join\n\n- Go"
    )
    assert html_to_text("<script>alert(1)</script><p>safe</p>") == "safe"
    assert html_to_text(None) == ""


async def test_remotive_adapter() -> None:
    jobs = await RemotiveSource().fetch(mock_http({"remotive.com/api": fixture("remotive.json")}))
    assert [j.title for j in jobs] == ["Senior Backend Engineer", "Frontend Developer"]
    first = jobs[0]
    assert first.source == JobSource.REMOTIVE and first.source_id == "1900001"
    assert first.company == "Acme Robotics Inc."
    assert first.location_text == "Worldwide" and first.salary_text == "$120k - $150k"
    assert "- 5+ years Python" in first.description and "<" not in first.description
    assert "python" in first.tags and "full_time" in first.tags
    assert first.posted_at is not None and first.posted_at.tzinfo is not None


async def test_remoteok_adapter_skips_legal_notice_and_formats_salary() -> None:
    jobs = await RemoteOKSource().fetch(mock_http({"remoteok.com/api": fixture("remoteok.json")}))
    assert len(jobs) == 2
    assert jobs[0].salary_text == "$120,000 - $150,000 USD/year"
    assert jobs[1].salary_text is None
    assert jobs[0].url.startswith("https://remoteok.com/remote-jobs/")
    assert jobs[0].posted_at is not None


async def test_weworkremotely_adapter_splits_company_from_title() -> None:
    source = WeWorkRemotelySource(
        feeds=("https://weworkremotely.com/categories/remote-programming-jobs.rss",)
    )
    jobs = await source.fetch(
        mock_http(
            {"weworkremotely.com": fixture("weworkremotely.xml")},
            content_type="application/rss+xml",
        )
    )
    assert [(j.company, j.title) for j in jobs] == [
        ("Delta Health", "Staff Software Engineer (Python)"),
        ("Epsilon", "Backend Engineer"),
    ]
    assert jobs[0].location_text == "Anywhere in the World"
    assert jobs[0].source_id == "delta-health-staff-software-engineer-python"
    assert "- Python, Django" in jobs[0].description


async def test_hackernews_adapter_keeps_only_remote_top_level_posts() -> None:
    http = mock_http(
        {
            "search_by_date": fixture("hn_threads.json"),
            "api/v1/search?": fixture("hn_comments.json"),
        }
    )
    jobs = await HackerNewsSource().fetch(http)
    assert len(jobs) == 1  # onsite post and the reply are dropped
    job = jobs[0]
    assert job.company == "Zeta Analytics"
    assert job.title == "Senior Data Engineer"
    assert job.location_text == "REMOTE (US or Canada)"
    assert job.url == "https://news.ycombinator.com/item?id=45000101"
    assert "Snowflake" in job.description


def test_hackernews_parse_handles_unstructured_first_line() -> None:
    hit = {
        "objectID": "1",
        "comment_text": "We are a small remote team hiring a Rust developer.",
        "created_at_i": 1,
    }
    job = parse_posting(hit)
    assert job is not None and job.company == "We are a small remote team hiring a Rust developer."
    assert (
        parse_posting({"objectID": "2", "comment_text": "Onsite only in Berlin. No remote."})
        is None
    )


async def test_greenhouse_adapter_uses_board_company_and_unescapes_content() -> None:
    jobs = await GreenhouseSource(["iota"]).fetch(
        mock_http({"boards-api.greenhouse.io/v1/boards/iota/jobs": fixture("greenhouse.json")})
    )
    assert len(jobs) == 1
    assert jobs[0].company == "Iota Systems" and jobs[0].source_id == "iota:5100001"
    assert jobs[0].description == "Join Iota.\n\n- Go or Python\n- Kubernetes"
    assert jobs[0].tags == ["Engineering"]


async def test_lever_adapter_joins_sections() -> None:
    jobs = await LeverSource(["kappa"]).fetch(
        mock_http({"api.lever.co/v0/postings/kappa": fixture("lever.json")})
    )
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Site Reliability Engineer" and job.company == "kappa"
    assert "Requirements\n- Kubernetes\n- Terraform" in job.description
    assert "We sponsor visas." in job.description
    assert job.location_text == "Remote - Americas"
    assert job.posted_at is not None and job.posted_at.year == 2026


async def test_http_client_raises_for_upstream_errors() -> None:
    http = mock_http({})
    with pytest.raises(httpx.HTTPStatusError):
        await RemotiveSource().fetch(http)


async def test_http_client_caches_in_redis_and_enforces_cooldown() -> None:
    from jobhunt.core.redis import get_redis
    from jobhunt.sources.http import CooldownActiveError

    redis = get_redis()
    await redis.flushdb()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text=json.dumps({"n": calls["n"]}), headers={"etag": "v1"})

    http = SourceHttpClient(redis=redis, transport=httpx.MockTransport(handler))
    first = await http.get("https://example.test/feed", source="t", cache_ttl=60, cooldown=60)
    second = await http.get("https://example.test/feed", source="t", cache_ttl=60, cooldown=60)
    assert first.from_cache is False and second.from_cache is True
    assert second.json() == {"n": 1} and calls["n"] == 1

    # A different URL for the same source within the cooldown is refused, not fetched.
    with pytest.raises(CooldownActiveError):
        await http.get("https://example.test/other", source="t", cache_ttl=60, cooldown=60)
    assert calls["n"] == 1
    await redis.flushdb()
