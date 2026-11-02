"""Application tracker endpoints (the Kanban board)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from jobhunt.api.deps import CurrentUser, SessionDep
from jobhunt.api.routes.jobs import _to_read as job_to_read
from jobhunt.models import Application, ApplicationStage, Job
from jobhunt.schemas.common import Message
from jobhunt.schemas.tracker import (
    ApplicationCreate,
    ApplicationEventRead,
    ApplicationRead,
    ApplicationUpdate,
    BoardRead,
    NoteCreate,
)
from jobhunt.services.tracker import TrackerError, TrackerService

router = APIRouter(prefix="/applications", tags=["tracker"])


def _read(
    application: Application, job: Job, judge_score: int | None, now: datetime
) -> ApplicationRead:
    return ApplicationRead(
        id=application.id,
        job=job_to_read(job),
        stage=application.stage,
        applied_at=application.applied_at,
        follow_up_at=application.follow_up_at,
        follow_up_due=application.follow_up_at is not None and application.follow_up_at <= now,
        resume_document_id=application.resume_document_id,
        cover_letter_document_id=application.cover_letter_document_id,
        judge_score=judge_score,
        events=[
            ApplicationEventRead(
                id=e.id,
                kind=e.kind,
                body=e.body,
                data=e.data or {},
                created_at=e.created_at,
                source=e.source,
            )
            for e in sorted(application.events, key=lambda e: e.created_at)
        ],
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


async def _read_one(
    service: TrackerService, user: CurrentUser, session: SessionDep, application: Application
) -> ApplicationRead:
    job = await session.get(Job, application.job_id)
    assert job is not None
    scores = await service.judge_scores(user, [job.id])
    return _read(application, job, scores.get(job.id), datetime.now(UTC))


@router.get("", response_model=BoardRead)
async def board(user: CurrentUser, session: SessionDep) -> BoardRead:
    service = TrackerService(session)
    applications = await service.list_all(user)
    jobs = {
        j.id: j for j in [await session.get(Job, a.job_id) for a in applications] if j is not None
    }
    scores = await service.judge_scores(user, list(jobs))
    now = datetime.now(UTC)
    columns: dict[ApplicationStage, list[ApplicationRead]] = {
        stage: [] for stage in ApplicationStage
    }
    for application in applications:
        columns[application.stage].append(
            _read(application, jobs[application.job_id], scores.get(application.job_id), now)
        )
    return BoardRead(
        columns=columns,
        reminders_due=sum(1 for a in applications if a.follow_up_at and a.follow_up_at <= now),
    )


@router.get("/reminders", response_model=list[ApplicationRead])
async def reminders(user: CurrentUser, session: SessionDep) -> list[ApplicationRead]:
    service = TrackerService(session)
    due = await service.due_reminders(user)
    return [await _read_one(service, user, session, a) for a in due]


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
async def create_application(
    body: ApplicationCreate, user: CurrentUser, session: SessionDep
) -> ApplicationRead:
    service = TrackerService(session)
    try:
        application = await service.create(user, body.job_id, stage=body.stage, note=body.note)
    except TrackerError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT if "already" in str(exc) else status.HTTP_404_NOT_FOUND,
            str(exc),
        ) from exc
    return await _read_one(service, user, session, application)


async def _refetch(
    service: TrackerService, user: CurrentUser, session: SessionDep, application: Application
) -> Application:
    """Reload columns and events after a mutation (async sessions cannot lazy-load)."""
    reloaded = await service.get(user, application.id)
    assert reloaded is not None
    return reloaded


async def _load(
    service: TrackerService, user: CurrentUser, application_id: uuid.UUID
) -> Application:
    application = await service.get(user, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return application


@router.get("/{application_id}", response_model=ApplicationRead)
async def get_application(
    application_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ApplicationRead:
    service = TrackerService(session)
    return await _read_one(service, user, session, await _load(service, user, application_id))


@router.patch("/{application_id}", response_model=ApplicationRead)
async def update_application(
    application_id: uuid.UUID, body: ApplicationUpdate, user: CurrentUser, session: SessionDep
) -> ApplicationRead:
    service = TrackerService(session)
    application = await _load(service, user, application_id)
    if body.stage is not None:
        await service.move(application, body.stage)
    if body.applied_at is not None:
        application.applied_at = body.applied_at
    if body.clear_follow_up:
        await service.set_follow_up(application, None)
    elif body.follow_up_at is not None:
        await service.set_follow_up(application, body.follow_up_at)
    if body.resume_document_id is not None:
        application.resume_document_id = body.resume_document_id
    if body.cover_letter_document_id is not None:
        application.cover_letter_document_id = body.cover_letter_document_id
    await session.flush()
    return await _read_one(
        service, user, session, await _refetch(service, user, session, application)
    )


@router.post(
    "/{application_id}/notes", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED
)
async def add_note(
    application_id: uuid.UUID, body: NoteCreate, user: CurrentUser, session: SessionDep
) -> ApplicationRead:
    service = TrackerService(session)
    application = await _load(service, user, application_id)
    await service.add_note(application, body.body)
    return await _read_one(
        service, user, session, await _refetch(service, user, session, application)
    )


@router.delete("/{application_id}", response_model=Message)
async def delete_application(
    application_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Message:
    service = TrackerService(session)
    await service.delete(await _load(service, user, application_id))
    return Message(detail="Removed from board")
