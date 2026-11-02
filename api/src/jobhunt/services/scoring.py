"""Fit scoring pipeline for one user.

    extracted jobs -> hard filters -> hybrid score (embeddings + skill coverage)
                   -> top-K by hybrid -> LLM judge -> ranked matches

Each stage writes to `job_scores`, so a crash loses at most the current job and a re-run
only does the work that is missing for the current profile version.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobhunt.ai.provider import LLMProvider
from jobhunt.core.logging import get_logger
from jobhunt.models import Evidence, ExtractionStatus, Job, JobScore, Preferences, Profile, User
from jobhunt.schemas.job import JobExtraction
from jobhunt.schemas.profile import ProfileDocument
from jobhunt.services.filters import CandidateContext, apply_filters
from jobhunt.services.judge import JudgeInput, judge_fit
from jobhunt.services.skills import SkillCoverage, skill_coverage

log = get_logger(__name__)

TOP_EVIDENCE = 8
SIMILARITY_WEIGHT = 0.5  # the rest goes to skill coverage


@dataclass(slots=True)
class RetrievedEvidence:
    evidence: Evidence
    similarity: float


@dataclass(slots=True)
class HybridScore:
    similarity: float
    coverage: SkillCoverage | None
    hybrid: float
    evidence: list[RetrievedEvidence] = field(default_factory=list)


@dataclass(slots=True)
class ScoreReport:
    profile_version: int
    considered: int = 0
    filtered_out: int = 0
    scored: int = 0
    judged: int = 0
    judge_cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


def combine(similarity: float, coverage: SkillCoverage | None) -> float:
    """Cosine similarity rescaled to 0..1 and blended with must-have coverage."""
    sim = max(0.0, min(1.0, (similarity + 1) / 2)) if similarity < 0 else min(similarity, 1.0)
    if coverage is None or coverage.ratio is None:
        return round(sim, 4)
    return round(SIMILARITY_WEIGHT * sim + (1 - SIMILARITY_WEIGHT) * coverage.ratio, 4)


class ScoringService:
    def __init__(self, session: AsyncSession, llm: LLMProvider, *, judge_model: str) -> None:
        self._session = session
        self._llm = llm
        self._judge_model = judge_model

    # ---- context ----

    async def _load_context(
        self, user: User
    ) -> tuple[Profile, ProfileDocument, Preferences, CandidateContext] | None:
        profile = await self._session.scalar(select(Profile).where(Profile.user_id == user.id))
        if profile is None or not profile.document:
            return None
        document = ProfileDocument.model_validate(profile.document)
        prefs = await self._session.scalar(
            select(Preferences).where(Preferences.user_id == user.id)
        )
        if prefs is None:
            prefs = Preferences(user_id=user.id)
            self._session.add(prefs)
            await self._session.flush()
        candidate = CandidateContext(
            country=prefs.country or document.country_code, timezone=prefs.timezone
        )
        return profile, document, prefs, candidate

    # ---- stages ----

    async def retrieve_evidence(
        self, profile: Profile, job: Job, k: int = TOP_EVIDENCE
    ) -> list[RetrievedEvidence]:
        if job.embedding is None:
            return []
        distance = Evidence.embedding.cosine_distance(job.embedding)
        rows = await self._session.execute(
            select(Evidence, distance.label("distance"))
            .where(Evidence.profile_id == profile.id, Evidence.embedding.is_not(None))
            .order_by(distance)
            .limit(k)
        )
        return [RetrievedEvidence(ev, round(1 - float(dist), 4)) for ev, dist in rows]

    async def hybrid_score(
        self, profile: Profile, document: ProfileDocument, job: Job, extraction: JobExtraction
    ) -> HybridScore:
        retrieved = await self.retrieve_evidence(profile, job)
        top = [r.similarity for r in retrieved[:3]]
        similarity = sum(top) / len(top) if top else 0.0
        all_evidence_texts = [
            e.text
            for e in await self._session.scalars(
                select(Evidence).where(Evidence.profile_id == profile.id)
            )
        ]
        coverage = (
            skill_coverage(extraction.must_have_skills, document.skills, all_evidence_texts)
            if extraction.must_have_skills
            else None
        )
        return HybridScore(
            similarity=round(similarity, 4),
            coverage=coverage,
            hybrid=combine(similarity, coverage),
            evidence=retrieved,
        )

    async def score_job(self, user: User, job: Job) -> JobScore | None:
        """Filters + hybrid for one job. Returns the stored JobScore (judge not yet run)."""
        context = await self._load_context(user)
        if context is None or not job.extraction:
            return None
        profile, document, prefs, candidate = context
        return await self._score_with_context(user, job, profile, document, prefs, candidate)

    async def _score_with_context(
        self,
        user: User,
        job: Job,
        profile: Profile,
        document: ProfileDocument,
        prefs: Preferences,
        candidate: CandidateContext,
    ) -> JobScore:
        extraction = JobExtraction.model_validate(job.extraction)
        score = await self._session.scalar(
            select(JobScore).where(JobScore.user_id == user.id, JobScore.job_id == job.id)
        )
        if score is None:
            score = JobScore(
                user_id=user.id,
                job_id=job.id,
                profile_version=profile.version,
                passed_filters=False,
            )
            self._session.add(score)
        verdict = apply_filters(
            extraction=extraction,
            title=job.title,
            description=job.description,
            preferences=prefs,
            candidate=candidate,
        )
        score.profile_version = profile.version
        score.passed_filters = verdict.passed
        score.filter_reasons = verdict.reasons + [f"note: {n}" for n in verdict.notes]
        if verdict.passed:
            hybrid = await self.hybrid_score(profile, document, job, extraction)
            score.similarity_score = hybrid.similarity
            score.skill_coverage = hybrid.coverage.ratio if hybrid.coverage else None
            score.hybrid_score = hybrid.hybrid
            score.matched_evidence_ids = [
                {"id": str(r.evidence.id), "similarity": r.similarity} for r in hybrid.evidence
            ]
        else:
            score.similarity_score = score.skill_coverage = score.hybrid_score = None
            score.matched_evidence_ids = []
        # A re-score invalidates an old judgement from a previous profile version.
        score.judge_score = None
        score.judgement = None
        score.judged_at = None
        await self._session.flush()
        return score

    async def judge(self, user: User, score: JobScore) -> JobScore:
        context = await self._load_context(user)
        assert context is not None
        _profile, document, _prefs, candidate = context
        job = await self._session.get(Job, score.job_id)
        assert job is not None and job.extraction is not None
        evidence_ids = [uuid.UUID(e["id"]) for e in score.matched_evidence_ids or []]
        evidence = (
            list(await self._session.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids))))
            if evidence_ids
            else []
        )
        evidence.sort(key=lambda e: evidence_ids.index(e.id))
        result = await judge_fit(
            self._llm,
            model=self._judge_model,
            inp=JudgeInput(
                job=job,
                extraction=JobExtraction.model_validate(job.extraction),
                profile=document,
                evidence=evidence,
                candidate_country=candidate.country,
            ),
        )
        payload = result.judgement.model_dump(mode="json")
        for strength in payload["strengths"]:
            ev = result.evidence_by_ref.get(strength["evidence_ref"])
            strength["evidence_id"] = str(ev.id) if ev else None
            strength["path"] = ev.path if ev else None
        payload["dropped_citations"] = result.dropped_citations
        score.judgement = payload
        score.judge_score = result.judgement.score
        score.judge_model = result.model
        score.judge_cost_usd = result.cost_usd
        score.judge_latency_ms = result.latency_ms
        score.judged_at = datetime.now(UTC)
        await self._session.flush()
        return score

    # ---- orchestration ----

    async def score_user(
        self, user: User, *, judge_pool: int | None = None, rescore: bool = False
    ) -> ScoreReport:
        context = await self._load_context(user)
        if context is None:
            return ScoreReport(profile_version=0, errors=["no profile"])
        profile, document, prefs, candidate = context
        report = ScoreReport(profile_version=profile.version)

        stale_or_missing = or_(JobScore.id.is_(None), JobScore.profile_version != profile.version)
        stmt = (
            select(Job)
            .outerjoin(JobScore, and_(JobScore.job_id == Job.id, JobScore.user_id == user.id))
            .where(
                Job.is_active.is_(True),
                Job.extraction_status == ExtractionStatus.DONE,
                or_(Job.dedup_group_id.is_(None), Job.dedup_group_id == Job.id),
            )
            .order_by(Job.fetched_at.desc())
        )
        if not rescore:
            stmt = stmt.where(stale_or_missing)
        jobs = list(await self._session.scalars(stmt))
        for job in jobs:
            report.considered += 1
            score = await self._score_with_context(user, job, profile, document, prefs, candidate)
            if score.passed_filters:
                report.scored += 1
            else:
                report.filtered_out += 1

        pool = judge_pool or prefs.judge_pool_size
        to_judge = list(
            await self._session.scalars(
                select(JobScore)
                .where(
                    JobScore.user_id == user.id,
                    JobScore.profile_version == profile.version,
                    JobScore.passed_filters.is_(True),
                    JobScore.judge_score.is_(None),
                )
                .order_by(JobScore.hybrid_score.desc())
                .limit(pool)
            )
        )
        for score in to_judge:
            try:
                await self.judge(user, score)
            except Exception as exc:
                report.errors.append(f"{score.job_id}: {exc}")
                log.warning("judge.failed", job_id=str(score.job_id), error=str(exc))
                continue
            report.judged += 1
            report.judge_cost_usd += score.judge_cost_usd or 0.0
        log.info(
            "score.done",
            user_id=str(user.id),
            **{k: v for k, v in asdict(report).items() if k != "errors"},
            errors=len(report.errors),
        )
        return report
