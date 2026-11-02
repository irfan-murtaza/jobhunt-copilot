"""Build the list of enabled sources from settings."""

from __future__ import annotations

from jobhunt.core.config import Settings
from jobhunt.models import JobSource
from jobhunt.sources.base import JobBoardSource
from jobhunt.sources.greenhouse import GreenhouseSource
from jobhunt.sources.hackernews import HackerNewsSource
from jobhunt.sources.lever import LeverSource
from jobhunt.sources.remoteok import RemoteOKSource
from jobhunt.sources.remotive import RemotiveSource
from jobhunt.sources.weworkremotely import WeWorkRemotelySource


def build_sources(settings: Settings, only: set[JobSource] | None = None) -> list[JobBoardSource]:
    sources: list[JobBoardSource] = [
        RemotiveSource(),
        RemoteOKSource(),
        WeWorkRemotelySource(),
        HackerNewsSource(),
    ]
    if settings.greenhouse_boards:
        sources.append(GreenhouseSource(settings.greenhouse_boards))
    if settings.lever_boards:
        sources.append(LeverSource(settings.lever_boards))
    if only:
        sources = [s for s in sources if s.name in only]
    return sources
