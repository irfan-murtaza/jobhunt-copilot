"""HTTP client for job boards: cached, conditional, rate-limited and identifiable.

- Responses are cached in Redis for the source's TTL so re-runs (and tests of the
  pipeline) do not hammer upstreams.
- ETag / Last-Modified are stored and replayed for conditional requests.
- A per-source cooldown key in Redis enforces a minimum interval between live requests
  across every worker process.
- A descriptive User-Agent with a contact URL, as most boards request.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast

import httpx
from redis.asyncio import Redis

from jobhunt import __version__
from jobhunt.core.logging import get_logger

log = get_logger(__name__)

USER_AGENT = f"JobHuntCopilot/{__version__} (+https://github.com/irfan-murtaza/jobhunt-copilot)"


class CooldownActiveError(Exception):
    def __init__(self, source: str, retry_in: int) -> None:
        super().__init__(f"{source} was fetched recently; retry in {retry_in}s")
        self.retry_in = retry_in


@dataclass(slots=True)
class FetchResult:
    url: str
    status_code: int
    text: str
    from_cache: bool
    etag: str | None = None
    last_modified: str | None = None

    def json(self) -> Any:
        return json.loads(self.text)


class SourceHttpClient:
    def __init__(
        self,
        *,
        redis: Redis | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._redis = redis
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, application/xml, text/*",
            },
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(
        self,
        url: str,
        *,
        source: str,
        cache_ttl: int = 900,
        cooldown: int = 0,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FetchResult:
        key = self._cache_key(url, params)
        cached = await self._read_cache(key)
        if cached is not None:
            log.debug("source.cache_hit", source=source, url=url)
            return FetchResult(url, 200, cached["text"], True, cached.get("etag"), cached.get("lm"))

        await self._enforce_cooldown(source, cooldown)

        request_headers = dict(headers or {})
        if cached is None and self._redis is not None:
            validators = await cast(
                "Awaitable[dict[str, str]]", self._redis.hgetall(f"{key}:validators")
            )
            if validators.get("etag"):
                request_headers["If-None-Match"] = validators["etag"]
            if validators.get("lm"):
                request_headers["If-Modified-Since"] = validators["lm"]

        try:
            response = await self._client.get(url, params=params, headers=request_headers)
        except httpx.HTTPError as exc:
            raise httpx.HTTPError(f"{source}: {exc}") from exc

        if response.status_code == 304 and self._redis is not None:
            stale = await self._redis.get(f"{key}:stale")
            if stale is not None:
                log.info("source.not_modified", source=source, url=url)
                await self._redis.set(key, stale, ex=cache_ttl)
                data = json.loads(stale)
                return FetchResult(url, 304, data["text"], True, data.get("etag"), data.get("lm"))

        response.raise_for_status()
        result = FetchResult(
            url,
            response.status_code,
            response.text,
            False,
            response.headers.get("etag"),
            response.headers.get("last-modified"),
        )
        await self._write_cache(key, result, cache_ttl)
        log.info(
            "source.fetched",
            source=source,
            url=url,
            status=response.status_code,
            bytes=len(response.content),
        )
        return result

    @staticmethod
    def _cache_key(url: str, params: dict[str, Any] | None) -> str:
        raw = url + ("?" + json.dumps(params, sort_keys=True) if params else "")
        return "source:cache:" + hashlib.sha256(raw.encode()).hexdigest()

    async def _read_cache(self, key: str) -> dict[str, Any] | None:
        if self._redis is None:
            return None
        payload = await self._redis.get(key)
        return json.loads(payload) if payload else None

    async def _write_cache(self, key: str, result: FetchResult, ttl: int) -> None:
        if self._redis is None:
            return
        payload = json.dumps({"text": result.text, "etag": result.etag, "lm": result.last_modified})
        await self._redis.set(key, payload, ex=ttl)
        # Keep a long-lived copy for 304 replays and the validators to send next time.
        await self._redis.set(f"{key}:stale", payload, ex=7 * 24 * 3600)
        validators = {k: v for k, v in (("etag", result.etag), ("lm", result.last_modified)) if v}
        if validators:
            await cast("Awaitable[int]", self._redis.hset(f"{key}:validators", mapping=validators))
            await cast("Awaitable[int]", self._redis.expire(f"{key}:validators", 7 * 24 * 3600))

    async def _enforce_cooldown(self, source: str, cooldown: int) -> None:
        if self._redis is None or cooldown <= 0:
            return
        key = f"source:cooldown:{source}"
        acquired = await self._redis.set(key, "1", ex=cooldown, nx=True)
        if not acquired:
            ttl = await cast("Awaitable[int]", self._redis.ttl(key))
            raise CooldownActiveError(source, max(int(ttl), 1))
