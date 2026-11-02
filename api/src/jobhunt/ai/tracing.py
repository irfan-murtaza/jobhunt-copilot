"""Langfuse tracing for every LLM and embedding call.

When Langfuse keys are not configured this degrades to a no-op so local development and
CI never need an observability account.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol

from jobhunt.core.config import Settings
from jobhunt.core.logging import get_logger

log = get_logger(__name__)


class Generation(Protocol):
    def record(
        self,
        *,
        output: Any,
        usage: dict[str, int] | None = None,
        cost_usd: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    def fail(self, error: str) -> None: ...


class Tracer(Protocol):
    @contextmanager
    def generation(
        self, *, name: str, model: str, input: Any, metadata: dict[str, Any] | None = None
    ) -> Iterator[Generation]: ...

    def flush(self) -> None: ...


class _NoopGeneration:
    def record(self, **_: Any) -> None:
        return None

    def fail(self, error: str) -> None:
        return None


class NoopTracer:
    @contextmanager
    def generation(self, **_: Any) -> Iterator[Generation]:
        yield _NoopGeneration()

    def flush(self) -> None:
        return None


class _LangfuseGeneration:
    def __init__(self, span: Any) -> None:
        self._span = span

    def record(
        self,
        *,
        output: Any,
        usage: dict[str, int] | None = None,
        cost_usd: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._span.update(
            output=output,
            usage_details=usage,
            cost_details={"total": cost_usd} if cost_usd is not None else None,
            metadata=metadata,
        )

    def fail(self, error: str) -> None:
        self._span.update(level="ERROR", status_message=error)


class LangfuseTracer:
    def __init__(self, settings: Settings) -> None:
        from langfuse import Langfuse

        assert settings.langfuse_public_key and settings.langfuse_secret_key
        self._client = Langfuse(
            public_key=settings.langfuse_public_key.get_secret_value(),
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            base_url=settings.langfuse_host,
            environment=settings.app_env,
        )

    @contextmanager
    def generation(
        self, *, name: str, model: str, input: Any, metadata: dict[str, Any] | None = None
    ) -> Iterator[Generation]:
        with self._client.start_as_current_observation(
            as_type="generation", name=name, model=model, input=input, metadata=metadata
        ) as span:
            yield _LangfuseGeneration(span)

    def flush(self) -> None:
        self._client.flush()


def build_tracer(settings: Settings) -> Tracer:
    if settings.langfuse_enabled:
        log.info("tracing.enabled", host=settings.langfuse_host)
        return LangfuseTracer(settings)
    return NoopTracer()
