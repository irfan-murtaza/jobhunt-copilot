"""The candidate profile document.

This is both the LLM extraction target and the user-editable source of truth, so it is
deliberately plain: strings and lists, no derived fields. Dates are ISO-ish strings
("2021-03" or "2021") because resumes are rarely more precise than a month.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DATE_RE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")


def _clean_date(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in {"present", "current", "now", "ongoing"}:
        return None
    if not _DATE_RE.match(value):
        raise ValueError(f"dates must look like YYYY or YYYY-MM, got {value!r}")
    return value


class ProfileSection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Role(ProfileSection):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    start: str | None = Field(default=None, description="YYYY or YYYY-MM")
    end: str | None = Field(default=None, description="YYYY or YYYY-MM; null means present")
    bullets: list[str] = Field(default_factory=list, description="Achievement bullets, verbatim")

    _dates = field_validator("start", "end")(_clean_date)

    @property
    def period(self) -> str:
        return f"{self.start or '?'} to {self.end or 'present'}"


class Project(ProfileSection):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    url: str | None = Field(default=None, max_length=500)
    technologies: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)


class Education(ProfileSection):
    institution: str = Field(min_length=1, max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field: str | None = Field(default=None, max_length=200)
    start: str | None = None
    end: str | None = None

    _dates = field_validator("start", "end")(_clean_date)


class Link(ProfileSection):
    label: str = Field(max_length=50)
    url: str = Field(max_length=500)


class ProfileDocument(ProfileSection):
    name: str | None = Field(default=None, max_length=120)
    headline: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    country_code: str | None = Field(
        default=None, min_length=2, max_length=2, description="ISO 3166-1 alpha-2 if stated"
    )
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    links: list[Link] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=2000)
    roles: list[Role] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    @field_validator("skills", "certifications", "languages")
    @classmethod
    def _dedupe_preserving_order(cls, items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(item.strip())
        return result

    @property
    def years_of_experience(self) -> float | None:
        """Rough tenure from the earliest role start to the latest end (or now)."""
        from datetime import UTC, datetime

        starts = [r.start for r in self.roles if r.start]
        if not starts:
            return None

        def to_months(value: str) -> int:
            year, _, month = value.partition("-")
            return int(year) * 12 + (int(month) if month else 1)

        now = datetime.now(UTC)
        ends = [to_months(r.end) if r.end else now.year * 12 + now.month for r in self.roles]
        return round((max(ends) - min(to_months(s) for s in starts)) / 12, 1)


class ProfileRead(BaseModel):
    """API response: the document plus storage metadata."""

    model_config = ConfigDict(from_attributes=True)

    document: ProfileDocument
    version: int
    source_filename: str | None
    evidence_count: int = 0


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    path: str
    text: str
    context: str | None
