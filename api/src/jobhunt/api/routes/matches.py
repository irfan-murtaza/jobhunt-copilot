"""Ranked matches with the full reasoning chain: filters, evidence, judgement."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobhunt.ai.factory import model_for
from jobhunt.ai.provider import ModelRole
from jobhunt.api.deps import CurrentUser, LLMDep, SessionDep, SettingsDep
from jobhunt.api.routes.jobs import _to_read as job_to_read
from jobhunt.core.ratelimit import limiter
from jobhunt.models import Evidence, Job, JobScore, Preferences, Profile
from jobhunt.schemas.common import Message
from jobhunt.schemas.job import JobExtraction
from jobhunt.schemas.profile import ProfileDocument
from jobhunt.schemas.scoring import (
    JudgementRead,
    MatchDetail,
    MatchedEvidenceRead,
    MatchList,
    MatchRead,
    PreferencesRead,
    PreferencesUpdate,
    ScoreSummary,
    SkillCoverageRead,
    StrengthRead,
)
from jobhunt.services.scoring import ScoringService
from jobhunt.services.skills import skill_coverage
from jobhunt.worker.queue import enqueue

router = APIRouter(prefix="/matches", tags=["matches"])


def _judgement(score: JobScore) -> JudgementRead | None:
    if not score.judgement:
        return None
    j = score.judgement
    return JudgementRead(
        score=j["score"],
        verdict=j["verdict"],
        recommendation=j["recommendation"],
        strengths=[
            StrengthRead(
                evidence_id=s.get("evidence_id"),
                path=s.get("path"),
                quote=s["quote"],
                requirement=s["requirement"],
            )
            for s in j.get("strengths", [])
        ],
        gaps=j.get("gaps", []),
        risks=j.get("risks", []),
        model=score.judge_model,
        cost_usd=score.judge_cost_usd,
        latency_ms=score.judge_latency_ms,
        judged_at=score.judged_at,
        dropped_citations=j.get("dropped_citations", 0),
    )


def _match(score: JobScore, job: Job) -> MatchRead:
    return MatchRead(
        job=job_to_read(job),
        profile_version=score.profile_version,
        passed_filters=score.passed_filters,
        filter_reasons=score.filter_reasons or [],
        similarity_score=score.similarity_score,
        skill_coverage=score.skill_coverage,
        hybrid_score=score.hybrid_score,
        judge_score=score.judge_score,
        judgement=_judgement(score),
        scored_at=score.updated_at,
    )


@router.get("", response_model=MatchList)
async def list_matches(
    user: CurrentUser,
    session: SessionDep,
    include_filtered: bool = False,
    judged_only: bool = False,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MatchList:
    """Best matches first: judged score, then hybrid. Filtered-out jobs are hidden by default."""
    stmt = (
        select(JobScore, Job)
        .join(Job, Job.id == JobScore.job_id)
        .where(JobScore.user_id == user.id, Job.is_active.is_(True))
    )
    if not include_filtered:
        stmt = stmt.where(JobScore.passed_filters.is_(True))
    if judged_only:
        stmt = stmt.where(JobScore.judge_score.is_not(None))
    if min_score is not None:
        stmt = stmt.where(JobScore.judge_score >= min_score)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.execute(
        stmt.order_by(
            JobScore.judge_score.desc().nulls_last(),
            JobScore.hybrid_score.desc().nulls_last(),
            Job.fetched_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return MatchList(items=[_match(s, j) for s, j in rows], total=total, limit=limit, offset=offset)


@router.post("/score", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def queue_scoring(request: Request, response: Response, user: CurrentUser) -> Message:
    """Score every extracted job against the current profile in the background."""
    job_id = await enqueue("score_user", str(user.id))
    return Message(detail=f"Scoring queued ({job_id})")


@router.post("/score/sync", response_model=ScoreSummary)
@limiter.limit("2/minute")
async def score_now(
    request: Request,
    response: Response,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    llm: LLMDep,
    judge_pool: Annotated[int, Query(ge=0, le=50)] = 10,
) -> ScoreSummary:
    """Score inline (small pools only). Useful for development and the labelling page."""
    service = ScoringService(session, llm, judge_model=model_for(ModelRole.JUDGE, settings))
    report = await service.score_user(user, judge_pool=judge_pool)
    if report.errors and report.profile_version == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload a resume before scoring")
    return ScoreSummary(
        considered=report.considered,
        filtered_out=report.filtered_out,
        scored=report.scored,
        judged=report.judged,
        judge_cost_usd=round(report.judge_cost_usd, 6),
        profile_version=report.profile_version,
    )


@router.get("/{job_id}", response_model=MatchDetail)
async def get_match(job_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> MatchDetail:
    row = (
        await session.execute(
            select(JobScore, Job)
            .join(Job, Job.id == JobScore.job_id)
            .where(JobScore.user_id == user.id, JobScore.job_id == job_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No score for this job yet")
    score, job = row
    base = _match(score, job)
    evidence = await _matched_evidence(session, score)
    skills = await _skills(session, user.id, job)
    return MatchDetail(**base.model_dump(), matched_evidence=evidence, skills=skills)


@router.post("/{job_id}/judge", response_model=MatchDetail)
@limiter.limit("10/minute")
async def judge_one(
    request: Request,
    response: Response,
    job_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    llm: LLMDep,
) -> MatchDetail:
    """Run (or re-run) the judge for one job, e.g. one outside the automatic pool."""
    job = await session.get(Job, job_id)
    if job is None or not job.extraction:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found or not extracted yet")
    service = ScoringService(session, llm, judge_model=model_for(ModelRole.JUDGE, settings))
    score = await service.score_job(user, job)
    if score is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload a resume before scoring")
    if not score.passed_filters:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Job fails hard filters: {'; '.join(score.filter_reasons)}"
        )
    await service.judge(user, score)
    return await get_match(job_id, user, session)


async def _matched_evidence(session: AsyncSession, score: JobScore) -> list[MatchedEvidenceRead]:
    refs = {uuid.UUID(e["id"]): e["similarity"] for e in score.matched_evidence_ids or []}
    if not refs:
        return []
    rows = await session.scalars(select(Evidence).where(Evidence.id.in_(refs)))
    items = [
        MatchedEvidenceRead(evidence_id=e.id, path=e.path, text=e.text, similarity=refs[e.id])
        for e in rows
    ]
    return sorted(items, key=lambda i: -i.similarity)


async def _skills(session: AsyncSession, user_id: uuid.UUID, job: Job) -> SkillCoverageRead | None:
    if not job.extraction:
        return None
    profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        return None
    document = ProfileDocument.model_validate(profile.document)
    texts = [
        e.text
        for e in await session.scalars(select(Evidence).where(Evidence.profile_id == profile.id))
    ]
    coverage = skill_coverage(
        JobExtraction.model_validate(job.extraction).must_have_skills, document.skills, texts
    )
    return SkillCoverageRead(
        required=coverage.required,
        matched=coverage.matched,
        missing=coverage.missing,
        ratio=coverage.ratio,
    )


preferences_router = APIRouter(prefix="/preferences", tags=["preferences"])


async def _get_or_create(session: AsyncSession, user_id: uuid.UUID) -> Preferences:
    prefs = await session.scalar(select(Preferences).where(Preferences.user_id == user_id))
    if prefs is None:
        prefs = Preferences(user_id=user_id)
        session.add(prefs)
        await session.flush()
    return prefs


@preferences_router.get("", response_model=PreferencesRead)
async def get_preferences(user: CurrentUser, session: SessionDep) -> Preferences:
    return await _get_or_create(session, user.id)


@preferences_router.put("", response_model=PreferencesRead)
async def update_preferences(
    body: PreferencesUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> Preferences:
    prefs = await _get_or_create(session, user.id)
    for key, value in body.model_dump().items():
        setattr(prefs, key, value)
    await session.flush()
    return prefs
