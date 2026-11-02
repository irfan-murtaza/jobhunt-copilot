"""Profile lifecycle: parse uploaded resumes, store the edited document, derive evidence.

Evidence rows are rebuilt from scratch whenever the document changes. They are a pure
function of the document, so there is nothing to migrate or reconcile: delete and recreate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobhunt.ai.provider import EmbeddingProvider, LLMProvider
from jobhunt.core.logging import get_logger
from jobhunt.models import Evidence, Profile, User
from jobhunt.schemas.profile import ProfileDocument

log = get_logger(__name__)

PROFILE_PARSER_SYSTEM = """You convert resume text into a structured candidate profile.

Rules:
- Copy facts exactly as written. Do not paraphrase achievements, do not add metrics, skills,
  employers or dates that are not in the text, and do not drop bullets.
- One bullet per achievement line. Keep the candidate's wording; fix only obvious line-wrap
  breaks from PDF extraction.
- Dates are "YYYY-MM" or "YYYY". A current role has end = null.
- `skills` is a flat list of tools, languages and technologies that appear anywhere in the
  text, each once. Do not infer skills that are not written down.
- `country_code` is the ISO 3166-1 alpha-2 code for the candidate's stated location, else null.
- If a LinkedIn export is also provided, merge it with the resume: prefer the resume's wording
  and add anything only LinkedIn mentions.
- Leave fields null or empty when the information is absent. Never guess."""


@dataclass(slots=True)
class ParsedProfile:
    document: ProfileDocument
    model: str
    cost_usd: float | None
    latency_ms: int


async def parse_resume_text(
    llm: LLMProvider, *, model: str, resume_text: str, linkedin_text: str | None = None
) -> ParsedProfile:
    prompt = f"<resume>\n{resume_text}\n</resume>"
    if linkedin_text:
        prompt += f"\n\n<linkedin_export>\n{linkedin_text}\n</linkedin_export>"
    result = await llm.complete_structured(
        model=model,
        schema=ProfileDocument,
        system=PROFILE_PARSER_SYSTEM,
        prompt=prompt,
        max_tokens=8000,
        effort="low",
    )
    log.info(
        "profile.parsed",
        model=result.model,
        roles=len(result.output.roles),
        bullets=sum(len(r.bullets) for r in result.output.roles),
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
    return ParsedProfile(result.output, result.model, result.cost_usd, result.latency_ms)


@dataclass(slots=True)
class EvidenceItem:
    kind: str  # bullet | project | skill | summary
    path: str
    text: str
    context: str | None

    @property
    def embedding_text(self) -> str:
        return f"{self.context}: {self.text}" if self.context else self.text


def build_evidence(document: ProfileDocument) -> list[EvidenceItem]:
    """Flatten the document into citable facts. Deterministic; order is stable."""
    items: list[EvidenceItem] = []
    if document.summary:
        items.append(EvidenceItem("summary", "summary", document.summary, None))
    for i, role in enumerate(document.roles):
        context = f"{role.title} at {role.company} ({role.period})"
        for j, bullet in enumerate(role.bullets):
            if bullet.strip():
                items.append(EvidenceItem("bullet", f"roles/{i}/bullets/{j}", bullet, context))
    for i, project in enumerate(document.projects):
        text = project.name if not project.description else f"{project.name}: {project.description}"
        if project.technologies:
            text += f" (technologies: {', '.join(project.technologies)})"
        items.append(EvidenceItem("project", f"projects/{i}", text, "Project"))
        for j, bullet in enumerate(project.bullets):
            if bullet.strip():
                items.append(
                    EvidenceItem(
                        "bullet", f"projects/{i}/bullets/{j}", bullet, f"Project {project.name}"
                    )
                )
    for i, skill in enumerate(document.skills):
        items.append(EvidenceItem("skill", f"skills/{i}", skill, None))
    return items


class ProfileService:
    def __init__(self, session: AsyncSession, embeddings: EmbeddingProvider) -> None:
        self._session = session
        self._embeddings = embeddings

    async def get(self, user: User) -> Profile | None:
        return await self._session.scalar(select(Profile).where(Profile.user_id == user.id))

    async def evidence_count(self, profile: Profile) -> int:
        return (
            await self._session.scalar(
                select(func.count()).select_from(Evidence).where(Evidence.profile_id == profile.id)
            )
            or 0
        )

    async def list_evidence(self, profile: Profile) -> list[Evidence]:
        result = await self._session.scalars(
            select(Evidence).where(Evidence.profile_id == profile.id).order_by(Evidence.path)
        )
        return list(result)

    async def save(
        self,
        user: User,
        document: ProfileDocument,
        *,
        raw_text: str | None = None,
        source_filename: str | None = None,
    ) -> Profile:
        """Upsert the document, bump the version and rebuild evidence with fresh embeddings."""
        profile = await self.get(user)
        if profile is None:
            profile = Profile(user_id=user.id, document={}, version=0)
            self._session.add(profile)
        profile.document = document.model_dump(mode="json")
        profile.version += 1
        if raw_text is not None:
            profile.raw_text = raw_text
        if source_filename is not None:
            profile.source_filename = source_filename
        await self._session.flush()
        await self._rebuild_evidence(profile, document)
        log.info("profile.saved", user_id=str(user.id), version=profile.version)
        return profile

    async def _rebuild_evidence(self, profile: Profile, document: ProfileDocument) -> None:
        items = build_evidence(document)
        vectors = await self._embeddings.embed([item.embedding_text for item in items])
        await self._session.execute(delete(Evidence).where(Evidence.profile_id == profile.id))
        self._session.add_all(
            Evidence(
                profile_id=profile.id,
                kind=item.kind,
                path=item.path,
                text=item.text,
                context=item.context,
                embedding=vector,
                profile_version=profile.version,
            )
            for item, vector in zip(items, vectors, strict=True)
        )
        await self._session.flush()


def store_upload(upload_dir: str, user_id: uuid.UUID, filename: str, data: bytes) -> Path:
    """Keep the original file so the profile can be re-parsed later. Never committed."""
    suffix = Path(filename).suffix.lower()[:8] or ".bin"
    target_dir = Path(upload_dir) / str(user_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4().hex}{suffix}"
    target.write_bytes(data)
    return target


def load_profile_document(profile: Profile) -> ProfileDocument:
    return ProfileDocument.model_validate(profile.document)
