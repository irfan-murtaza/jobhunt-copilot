"""SQLAlchemy models. Import this package so Alembic and `Base.metadata` see every table."""

from jobhunt.models.application import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    ApplicationStage,
)
from jobhunt.models.base import Base
from jobhunt.models.document import Document, DocumentKind
from jobhunt.models.evaluation import EvalLabel, FitLabel
from jobhunt.models.job import ExtractionStatus, Job, JobScore, JobSource
from jobhunt.models.profile import Evidence, Profile
from jobhunt.models.run import AgentRun, RunStatus
from jobhunt.models.source import SourceFetch
from jobhunt.models.user import Preferences, User

__all__ = [
    "AgentRun",
    "Application",
    "ApplicationEvent",
    "ApplicationEventKind",
    "ApplicationStage",
    "Base",
    "Document",
    "DocumentKind",
    "EvalLabel",
    "Evidence",
    "ExtractionStatus",
    "FitLabel",
    "Job",
    "JobScore",
    "JobSource",
    "Preferences",
    "Profile",
    "RunStatus",
    "SourceFetch",
    "User",
]
