"""Scoring schemas: the judge's structured verdict and the match API models."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jobhunt.schemas.common import APIModel
from jobhunt.schemas.job import JobRead


class Recommendation(StrEnum):
    APPLY = "apply"
    MAYBE = "maybe"
    SKIP = "skip"


class JudgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceMatch(JudgeModel):
    evidence_ref: str = Field(description="The E<n> id of the evidence item, exactly as listed")
    quote: str = Field(max_length=600, description="The evidence text, quoted verbatim")
    requirement: str = Field(max_length=200, description="Which job requirement this satisfies")


class FitJudgement(JudgeModel):
    """LLM-as-judge output. Strengths must cite listed evidence; gaps are free text."""

    score: int = Field(ge=0, le=100, description="0 = no fit, 100 = ideal candidate")
    verdict: str = Field(
        max_length=200, description="One line: should the candidate apply, and why"
    )
    recommendation: Recommendation
    strengths: list[EvidenceMatch] = Field(default_factory=list, max_length=8)
    gaps: list[str] = Field(
        default_factory=list, max_length=8, description="Requirements the profile does not show"
    )
    risks: list[str] = Field(
        default_factory=list, max_length=5, description="Eligibility or practical concerns"
    )

    @field_validator("gaps", "risks")
    @classmethod
    def _trim(cls, items: list[str]) -> list[str]:
        return [i.strip()[:300] for i in items if i.strip()]


# ---- API ----


class StrengthRead(APIModel):
    evidence_id: uuid.UUID | None
    path: str | None
    quote: str
    requirement: str


class JudgementRead(APIModel):
    score: int
    verdict: str
    recommendation: Recommendation
    strengths: list[StrengthRead]
    gaps: list[str]
    risks: list[str]
    model: str | None
    cost_usd: float | None
    latency_ms: int | None
    judged_at: datetime | None
    dropped_citations: int = 0  # strengths the judge cited that did not map to real evidence


class MatchedEvidenceRead(APIModel):
    evidence_id: uuid.UUID
    path: str
    text: str
    similarity: float


class SkillCoverageRead(APIModel):
    required: list[str]
    matched: list[str]
    missing: list[str]
    ratio: float | None


class MatchRead(APIModel):
    job: JobRead
    profile_version: int
    passed_filters: bool
    filter_reasons: list[str]
    similarity_score: float | None
    skill_coverage: float | None
    hybrid_score: float | None
    judge_score: int | None
    judgement: JudgementRead | None
    scored_at: datetime


class MatchDetail(MatchRead):
    matched_evidence: list[MatchedEvidenceRead]
    skills: SkillCoverageRead | None


class MatchList(APIModel):
    items: list[MatchRead]
    total: int
    limit: int
    offset: int


class ScoreSummary(APIModel):
    considered: int
    filtered_out: int
    scored: int
    judged: int
    judge_cost_usd: float
    profile_version: int


class PreferencesRead(APIModel):
    country: str | None
    timezone: str | None
    min_salary_usd: int | None
    seniority_levels: list[str]
    excluded_keywords: list[str]
    required_keywords: list[str]
    shortlist_size: int
    judge_pool_size: int
    digest_email_enabled: bool


class PreferencesUpdate(APIModel):
    country: str | None = Field(default=None, min_length=2, max_length=2)
    timezone: str | None = Field(default=None, max_length=64)
    min_salary_usd: int | None = Field(default=None, ge=0, le=2_000_000)
    seniority_levels: list[str] = Field(default_factory=list, max_length=10)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=50)
    required_keywords: list[str] = Field(default_factory=list, max_length=20)
    shortlist_size: int = Field(default=10, ge=1, le=50)
    judge_pool_size: int = Field(default=30, ge=1, le=200)
    digest_email_enabled: bool = True

    @field_validator("country")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("timezone")
    @classmethod
    def _valid_zone(cls, value: str | None) -> str | None:
        if value:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"unknown IANA timezone {value!r}") from exc
        return value
