"""LLM-as-judge: a strong model scores fit, citing the candidate's own evidence.

The judge only sees evidence we retrieved, each labelled E1..En. Its strengths must cite
those labels, and anything citing an unknown label is dropped and counted. That makes the
verdict traceable to real profile facts before any resume is ever written.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobhunt.ai.provider import LLMProvider
from jobhunt.core.logging import get_logger
from jobhunt.models import Evidence, Job
from jobhunt.schemas.job import JobExtraction
from jobhunt.schemas.profile import ProfileDocument
from jobhunt.schemas.scoring import FitJudgement

log = get_logger(__name__)

JUDGE_SYSTEM = """You are a rigorous technical recruiter assessing whether a candidate should apply
to a job. You will see the job's extracted requirements and description, then the candidate's
profile summary and a numbered list of evidence items (E1, E2, ...) taken verbatim from their
resume.

Scoring guide (0-100):
- 85-100: meets every must-have with direct evidence; apply.
- 65-84: meets most must-haves, gaps are learnable or nice-to-haves; apply or maybe.
- 40-64: meaningful gaps in must-haves or seniority; maybe at best.
- 0-39: wrong role family, seniority or clear eligibility problem; skip.

Rules:
- strengths must reference evidence by its id (E3) and quote the evidence text exactly as
  given. Never invent evidence or paraphrase a quote.
- gaps are must-have requirements with no supporting evidence. Be specific.
- risks cover eligibility, timezone, contract type or anything that makes applying pointless.
- The verdict is one plain sentence a job seeker can act on."""


@dataclass(slots=True)
class JudgeInput:
    job: Job
    extraction: JobExtraction
    profile: ProfileDocument
    evidence: list[Evidence]  # already ranked, most relevant first
    candidate_country: str | None


@dataclass(slots=True)
class JudgeResult:
    judgement: FitJudgement
    evidence_by_ref: dict[str, Evidence]
    dropped_citations: int
    model: str
    cost_usd: float | None
    latency_ms: int


def build_judge_prompt(inp: JudgeInput) -> tuple[str, dict[str, Evidence]]:
    ex = inp.extraction
    lines = [
        f"# Job: {inp.job.title} at {inp.job.company}",
        f"Summary: {ex.summary}",
        f"Seniority: {ex.seniority.value}; min years: {ex.years_experience_min or 'unspecified'}",
        f"Must-have skills: {', '.join(ex.must_have_skills) or 'none stated'}",
        f"Nice-to-have skills: {', '.join(ex.nice_to_have_skills) or 'none stated'}",
        f"Location eligibility: {ex.location.scope.value} {ex.location.text or ''}".strip(),
        f"Employment: {ex.employment_type.value}; remote: {ex.remote.value}; "
        f"visa: {ex.visa_sponsorship.value}",
        "",
        "## Job description (excerpt)",
        inp.job.description[:6000],
        "",
        "# Candidate",
        f"Headline: {inp.profile.headline or 'n/a'}",
        f"Location: {inp.profile.location or 'n/a'} ({inp.candidate_country or 'country unknown'})",
        f"Years of experience: {inp.profile.years_of_experience or 'unknown'}",
        f"Skills listed: {', '.join(inp.profile.skills) or 'none'}",
        f"Summary: {inp.profile.summary or 'n/a'}",
        "",
        "## Evidence (quote these by id)",
    ]
    refs: dict[str, Evidence] = {}
    for index, item in enumerate(inp.evidence, 1):
        ref = f"E{index}"
        refs[ref] = item
        context = f" [{item.context}]" if item.context else ""
        lines.append(f"{ref}{context}: {item.text}")
    return "\n".join(lines), refs


async def judge_fit(
    llm: LLMProvider, *, model: str, inp: JudgeInput, effort: str = "medium"
) -> JudgeResult:
    prompt, refs = build_judge_prompt(inp)
    result = await llm.complete_structured(
        model=model,
        schema=FitJudgement,
        system=JUDGE_SYSTEM,
        prompt=prompt,
        max_tokens=3000,
        effort=effort,
    )
    judgement = result.output
    kept = [s for s in judgement.strengths if s.evidence_ref in refs]
    dropped = len(judgement.strengths) - len(kept)
    if dropped:
        log.warning("judge.dropped_citations", job_id=str(inp.job.id), dropped=dropped)
        judgement = judgement.model_copy(update={"strengths": kept})
    log.info(
        "judge.done",
        job_id=str(inp.job.id),
        score=judgement.score,
        recommendation=judgement.recommendation.value,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
    return JudgeResult(judgement, refs, dropped, result.model, result.cost_usd, result.latency_ms)
