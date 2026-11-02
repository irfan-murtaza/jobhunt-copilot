"""Application tracker schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from jobhunt.models import ApplicationEventKind, ApplicationStage
from jobhunt.schemas.common import APIModel
from jobhunt.schemas.job import JobRead


class ApplicationCreate(APIModel):
    job_id: uuid.UUID
    stage: ApplicationStage = ApplicationStage.SAVED
    note: str | None = Field(default=None, max_length=5000)


class ApplicationUpdate(APIModel):
    stage: ApplicationStage | None = None
    applied_at: datetime | None = None
    follow_up_at: datetime | None = None
    clear_follow_up: bool = False
    resume_document_id: uuid.UUID | None = None
    cover_letter_document_id: uuid.UUID | None = None


class NoteCreate(APIModel):
    body: str = Field(min_length=1, max_length=5000)


class ApplicationEventRead(APIModel):
    id: uuid.UUID
    kind: ApplicationEventKind
    body: str | None
    data: dict[str, object]
    created_at: datetime
    source: str


class ApplicationRead(APIModel):
    id: uuid.UUID
    job: JobRead
    stage: ApplicationStage
    applied_at: datetime | None
    follow_up_at: datetime | None
    follow_up_due: bool
    resume_document_id: uuid.UUID | None
    cover_letter_document_id: uuid.UUID | None
    judge_score: int | None
    events: list[ApplicationEventRead]
    created_at: datetime
    updated_at: datetime


class BoardRead(APIModel):
    columns: dict[ApplicationStage, list[ApplicationRead]]
    reminders_due: int
