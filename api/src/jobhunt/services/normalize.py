"""Normalisation helpers used for storage and exact-match deduplication."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|inc\.|llc|ltd|ltd\.|limited|gmbh|corp|corp\.|corporation|co|co\.|plc|s\.a\.|ag|bv|b\.v\.|pty|oy|ab|sas|srl)\b\.?$",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "source",
    "gh_src",
    "lever-source",
    "src",
    "fbclid",
    "gclid",
}


def normalize_company(name: str) -> str:
    value = name.strip().lower()
    value = _COMPANY_SUFFIXES.sub("", value).strip(" ,.")
    return _NON_ALNUM.sub(" ", value).strip()


def normalize_title(title: str) -> str:
    value = title.lower()
    value = re.sub(r"\((.*?)\)|\[(.*?)\]", " ", value)  # drop "(Remote)" "[EMEA]"
    value = re.sub(
        r"\b(remote|worldwide|anywhere|fully|100%|us only|emea|europe|usa|uk)\b", " ", value
    )
    return _NON_ALNUM.sub(" ", value).strip()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower() or "https", parts.netloc.lower(), path, urlencode(sorted(query)), "")
    )


def content_hash(title: str, company: str, description: str) -> str:
    body = _NON_ALNUM.sub(" ", description.lower()).strip()
    payload = f"{normalize_title(title)}|{normalize_company(company)}|{body}"
    return hashlib.sha256(payload.encode()).hexdigest()
