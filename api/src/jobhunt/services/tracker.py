"""Application tracker: a Kanban of saved jobs with an append-only event history.

Stage transitions and notes are events, so the board can always answer "what happened
and when". Moving to Applied stamps `applied_at` and schedules a follow-up reminder.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jobhunt.core.logging import get_logger
from jobhunt.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    ApplicationStage,
    Job,
    JobScore,
    User,
)

log = get_logger(__name__)

FOLLOW_UP_AFTER = timedelta(days=7)
TERMINAL_STAGES = {ApplicationStage.OFFER, ApplicationStage.REJECTED}


class TrackerError(Exception):
    pass


class TrackerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, user: User) -> list[Application]:
        rows = await self._session.scalars(
            select(Application)
            .where(Application.user_id == user.id)
            .options(selectinload(Application.events))
            .order_by(Application.updated_at.desc())
        )
        return list(rows)

    async def get(self, user: User, application_id: uuid.UUID) -> Application | None:
        """Load (or reload in place, with events) one application. Safe to call after mutations."""
        return await self._session.scalar(
            select(Application)
            .where(Application.user_id == user.id, Application.id == application_id)
            .options(selectinload(Application.events))
            .execution_options(populate_existing=True)
        )

    async def for_job(self, user: User, job_id: uuid.UUID) -> Application | None:
        return await self._session.scalar(
            select(Application)
            .where(Application.user_id == user.id, Application.job_id == job_id)
            .options(selectinload(Application.events))
        )

    async def create(
        self,
        user: User,
        job_id: uuid.UUID,
        *,
        stage: ApplicationStage = ApplicationStage.SAVED,
        note: str | None = None,
        source: str = "user",
    ) -> Application:
        job = await self._session.get(Job, job_id)
        if job is None:
            raise TrackerError("Job not found")
        if await self.for_job(user, job_id) is not None:
            raise TrackerError("This job is already on your board")
        application = Application(user_id=user.id, job_id=job_id, stage=stage)
        self._session.add(application)
        await self._session.flush()
        self._add_event(
            application,
            ApplicationEventKind.STAGE_CHANGE,
            f"Added as {stage.value}",
            {"from": None, "to": stage.value},
            source,
        )
        if stage == ApplicationStage.APPLIED:
            self._mark_applied(application, source)
        if note:
            self._add_event(application, ApplicationEventKind.NOTE, note, {}, source)
        await self._session.flush()
        log.info("tracker.created", application_id=str(application.id), stage=stage.value)
        return await self._reload(application)

    async def move(
        self, application: Application, stage: ApplicationStage, *, source: str = "user"
    ) -> Application:
        if stage == application.stage:
            return application
        previous = application.stage
        application.stage = stage
        self._add_event(
            application,
            ApplicationEventKind.STAGE_CHANGE,
            f"Moved from {previous.value} to {stage.value}",
            {"from": previous.value, "to": stage.value},
            source,
        )
        if stage == ApplicationStage.APPLIED and application.applied_at is None:
            self._mark_applied(application, source)
        if stage in TERMINAL_STAGES:
            application.follow_up_at = None  # nothing left to chase
        await self._session.flush()
        return application

    async def add_note(
        self, application: Application, body: str, *, source: str = "user"
    ) -> ApplicationEvent:
        event = self._add_event(application, ApplicationEventKind.NOTE, body, {}, source)
        await self._session.flush()
        return event

    async def set_follow_up(
        self, application: Application, when: datetime | None, *, source: str = "user"
    ) -> None:
        application.follow_up_at = when
        self._add_event(
            application,
            ApplicationEventKind.REMINDER,
            f"Follow-up set for {when.date().isoformat()}" if when else "Follow-up cleared",
            {"follow_up_at": when.isoformat() if when else None},
            source,
        )
        await self._session.flush()

    async def delete(self, application: Application) -> None:
        await self._session.delete(application)
        await self._session.flush()

    async def due_reminders(self, user: User, now: datetime | None = None) -> list[Application]:
        now = now or datetime.now(UTC)
        rows = await self._session.scalars(
            select(Application)
            .where(
                Application.user_id == user.id,
                Application.follow_up_at.is_not(None),
                Application.follow_up_at <= now,
            )
            .options(selectinload(Application.events))
            .order_by(Application.follow_up_at)
        )
        return list(rows)

    async def judge_scores(
        self, user: User, job_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int | None]:
        if not job_ids:
            return {}
        rows = await self._session.execute(
            select(JobScore.job_id, JobScore.judge_score).where(
                JobScore.user_id == user.id, JobScore.job_id.in_(job_ids)
            )
        )
        return {job_id: score for job_id, score in rows}

    def _mark_applied(self, application: Application, source: str) -> None:
        now = datetime.now(UTC)
        application.applied_at = now
        application.follow_up_at = now + FOLLOW_UP_AFTER
        self._add_event(
            application,
            ApplicationEventKind.REMINDER,
            f"Follow up if no reply by {application.follow_up_at.date().isoformat()}",
            {"follow_up_at": application.follow_up_at.isoformat()},
            source,
        )

    def _add_event(
        self,
        application: Application,
        kind: ApplicationEventKind,
        body: str,
        data: dict[str, object],
        source: str,
    ) -> ApplicationEvent:
        event = ApplicationEvent(
            application_id=application.id,
            kind=kind,
            body=body,
            data=data,
            source=source,
            created_at=datetime.now(UTC),
        )
        self._session.add(event)
        return event

    async def _reload(self, application: Application) -> Application:
        reloaded = await self._session.scalar(
            select(Application)
            .where(Application.id == application.id)
            .options(selectinload(Application.events))
            .execution_options(populate_existing=True)
        )
        assert reloaded is not None
        return reloaded
