"""Candidate profile: upload and parse a resume, read and edit the result, inspect evidence."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from jobhunt.ai.factory import model_for
from jobhunt.ai.provider import LLMError, LLMRefusalError, ModelRole
from jobhunt.api.deps import CurrentUser, EmbeddingsDep, LLMDep, SessionDep, SettingsDep
from jobhunt.schemas.profile import EvidenceRead, ProfileDocument, ProfileRead
from jobhunt.services.profile import (
    ProfileService,
    load_profile_document,
    parse_resume_text,
    store_upload,
)
from jobhunt.services.text_extraction import (
    EmptyDocumentError,
    UnsupportedFileError,
    extract_text,
)

router = APIRouter(prefix="/profile", tags=["profile"])


async def _read_upload(upload: UploadFile) -> str:
    data = await upload.read()
    try:
        return extract_text(data).text
    except (UnsupportedFileError, EmptyDocumentError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{upload.filename}: {exc}"
        ) from exc


async def _to_read(service: ProfileService, profile: object) -> ProfileRead:
    from jobhunt.models import Profile

    assert isinstance(profile, Profile)
    return ProfileRead(
        document=load_profile_document(profile),
        version=profile.version,
        source_filename=profile.source_filename,
        evidence_count=await service.evidence_count(profile),
    )


@router.post("/upload", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    llm: LLMDep,
    embeddings: EmbeddingsDep,
    resume: Annotated[UploadFile, File(description="Resume as PDF or DOCX")],
    linkedin: Annotated[UploadFile | None, File(description="Optional LinkedIn PDF export")] = None,
) -> ProfileRead:
    """Parse a resume (and optional LinkedIn export) into a draft profile and save it.

    The result replaces any existing profile. Review and edit it with PUT /profile.
    """
    resume_bytes = await resume.read()
    await resume.seek(0)
    resume_text = await _read_upload(resume)
    linkedin_text = await _read_upload(linkedin) if linkedin is not None else None

    try:
        parsed = await parse_resume_text(
            llm,
            model=model_for(ModelRole.EXTRACT, settings),
            resume_text=resume_text,
            linkedin_text=linkedin_text,
        )
    except LLMRefusalError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Parsing failed: {exc}") from exc

    store_upload(settings.upload_dir, user.id, resume.filename or "resume", resume_bytes)
    service = ProfileService(session, embeddings)
    raw_text = resume_text if not linkedin_text else f"{resume_text}\n\n---\n\n{linkedin_text}"
    profile = await service.save(
        user, parsed.document, raw_text=raw_text, source_filename=resume.filename
    )
    return await _to_read(service, profile)


@router.get("", response_model=ProfileRead)
async def get_profile(user: CurrentUser, session: SessionDep) -> ProfileRead:
    service = ProfileService(session)
    profile = await service.get(user)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile yet. Upload a resume first.")
    return await _to_read(service, profile)


@router.put("", response_model=ProfileRead)
async def update_profile(
    document: ProfileDocument, user: CurrentUser, session: SessionDep, embeddings: EmbeddingsDep
) -> ProfileRead:
    """Replace the profile document with the user's edited version and rebuild evidence."""
    service = ProfileService(session, embeddings)
    profile = await service.save(user, document)
    return await _to_read(service, profile)


@router.get("/evidence", response_model=list[EvidenceRead])
async def list_evidence(user: CurrentUser, session: SessionDep) -> list[EvidenceRead]:
    """The citable facts derived from the profile. Useful to see what retrieval can find."""
    service = ProfileService(session)
    profile = await service.get(user)
    if profile is None:
        return []
    return [
        EvidenceRead(id=str(e.id), kind=e.kind, path=e.path, text=e.text, context=e.context)
        for e in await service.list_evidence(profile)
    ]
