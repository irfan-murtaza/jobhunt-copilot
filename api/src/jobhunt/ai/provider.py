"""Provider-agnostic LLM interface.

The rest of the application only ever asks for "a structured completion of schema T using
the model for role R". Which vendor serves it, how usage is priced and how the call is
traced are all decided here, so swapping providers is a one-line env change.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ModelRole(enum.StrEnum):
    """Why we are calling the model. Each role maps to a configured model id."""

    EXTRACT = "extract"  # cheap, high volume: parse jobs and resumes into structure
    JUDGE = "judge"  # strong: score fit with cited evidence
    WRITE = "write"  # strong: tailor resume and cover letter


@dataclass(slots=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(slots=True)
class LLMResult[T: BaseModel]:
    output: T
    model: str
    usage: LLMUsage
    latency_ms: int
    cost_usd: float | None  # None when the model is not in the pricing table
    provider: str
    request_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class LLMError(Exception):
    """Base class for provider failures the caller may want to retry or surface."""


class LLMRefusalError(LLMError):
    """The model declined to answer. Not retryable with the same input."""


class LLMProvider(Protocol):
    name: str

    async def complete_structured(
        self,
        *,
        model: str,
        schema: type[T],
        system: str,
        prompt: str,
        max_tokens: int = 4096,
        effort: str | None = None,
    ) -> LLMResult[T]: ...


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
