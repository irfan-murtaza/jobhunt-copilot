"""Fetch a job page the user pasted a URL for, with SSRF protection."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from jobhunt.sources.html import html_to_text
from jobhunt.sources.http import USER_AGENT

MAX_BYTES = 2 * 1024 * 1024


class UnsafeURLError(ValueError):
    pass


def assert_public_http_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise UnsafeURLError("Only http(s) URLs are allowed")
    if parts.username or parts.password:
        raise UnsafeURLError("Credentials in URLs are not allowed")
    host = parts.hostname
    if host in {"localhost"} or host.endswith((".local", ".internal")):
        raise UnsafeURLError("Local hostnames are not allowed")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve {host}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise UnsafeURLError("URL resolves to a private or reserved address")


async def fetch_page_text(url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    assert_public_http_url(url)
    async with (
        httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=20.0,
            follow_redirects=True,
            transport=transport,
        ) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            raise UnsafeURLError(f"Unsupported content type {content_type!r}")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                break
            chunks.append(chunk)
        body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    return html_to_text(body)
