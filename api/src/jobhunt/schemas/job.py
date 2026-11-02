"""Job schemas: the LLM extraction target and API read models."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jobhunt.models import ExtractionStatus, JobSource
from jobhunt.schemas.common import APIModel


class Seniority(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    UNSPECIFIED = "unspecified"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    UNSPECIFIED = "unspecified"


class LocationScope(StrEnum):
    WORLDWIDE = "worldwide"  # anyone anywhere
    REGIONS = "regions"  # e.g. "EMEA", "Americas", "Europe", "LATAM", "APAC"
    COUNTRIES = "countries"  # explicit country list
    TIMEZONE = "timezone"  # defined by overlap with a timezone band
    UNSPECIFIED = "unspecified"  # remote but no constraint stated


class RemoteType(StrEnum):
    FULLY_REMOTE = "fully_remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNSPECIFIED = "unspecified"


class VisaSponsorship(StrEnum):
    YES = "yes"
    NO = "no"
    UNSPECIFIED = "unspecified"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Salary(ExtractionModel):
    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, description="ISO 4217, e.g. USD")
    period: str | None = Field(default=None, description="year | month | hour | day")
    text: str | None = Field(default=None, description="The salary as written")


class LocationEligibility(ExtractionModel):
    scope: LocationScope = LocationScope.UNSPECIFIED
    countries: list[str] = Field(
        default_factory=list, description="ISO 3166-1 alpha-2 codes when scope is countries"
    )
    regions: list[str] = Field(
        default_factory=list, description="Named regions when scope is regions"
    )
    timezone_min_utc_offset: int | None = Field(default=None, ge=-12, le=14)
    timezone_max_utc_offset: int | None = Field(default=None, ge=-12, le=14)
    excluded_countries: list[str] = Field(default_factory=list)
    text: str | None = Field(default=None, description="The eligibility statement as written")

    @field_validator("countries", "excluded_countries")
    @classmethod
    def _upper_alpha2(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip().upper() for v in values if len(v.strip()) == 2]
        return list(dict.fromkeys(cleaned))


class JobExtraction(ExtractionModel):
    """What we need to know about a posting to filter and score it."""

    title: str = Field(max_length=300, description="Cleaned job title")
    company: str | None = Field(default=None, max_length=200)
    seniority: Seniority = Seniority.UNSPECIFIED
    years_experience_min: int | None = Field(default=None, ge=0, le=40)
    must_have_skills: list[str] = Field(
        default_factory=list, description="Required skills, tools and technologies, as named"
    )
    nice_to_have_skills: list[str] = Field(default_factory=list)
    salary: Salary | None = None
    location: LocationEligibility = Field(default_factory=LocationEligibility)
    remote: RemoteType = RemoteType.UNSPECIFIED
    employment_type: EmploymentType = EmploymentType.UNSPECIFIED
    visa_sponsorship: VisaSponsorship = VisaSponsorship.UNSPECIFIED
    summary: str = Field(max_length=400, description="One sentence: what the role is")
    confidence: Confidence = Field(
        default=Confidence.MEDIUM, description="How clearly the posting states the above"
    )

    @field_validator("must_have_skills", "nice_to_have_skills")
    @classmethod
    def _dedupe(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for v in values:
            key = v.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(v.strip())
        return out[:40]


# ---- API models ----


class JobRead(APIModel):
    id: uuid.UUID
    source: JobSource
    url: str
    title: str
    company: str
    location_text: str | None
    salary_text: str | None
    tags: list[str]
    posted_at: datetime | None
    fetched_at: datetime
    extraction_status: ExtractionStatus
    extraction: JobExtraction | None
    dedup_group_id: uuid.UUID | None
    is_duplicate: bool = False


class JobDetail(JobRead):
    description: str
    extraction_model: str | None
    extraction_cost_usd: float | None
    extraction_latency_ms: int | None


class JobList(APIModel):
    items: list[JobRead]
    total: int
    limit: int
    offset: int


class ManualJobCreate(APIModel):
    url: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=50_000)
    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=200)


class SourceStatus(APIModel):
    name: str
    attribution: str
    last_fetched_at: datetime | None
    last_status_code: int | None
    last_items_seen: int | None
    last_items_new: int | None
    last_error: str | None


class IngestionSummary(APIModel):
    sources: dict[str, Any]
    fetched: int
    new: int
    updated: int
    duplicates: int
    errors: dict[str, str]
