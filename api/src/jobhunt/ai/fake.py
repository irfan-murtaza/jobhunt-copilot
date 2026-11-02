"""A scripted LLM provider for unit tests and offline evals.

Register one response per schema type (or a callable that builds one from the prompt);
every call is recorded so tests can assert on prompts and routing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from jobhunt.ai.provider import LLMResult, LLMUsage

Responder = Callable[[str, str], BaseModel]


@dataclass(slots=True)
class RecordedCall:
    model: str
    schema: str
    system: str
    prompt: str
    effort: str | None


@dataclass
class FakeLLMProvider:
    name: str = "fake"
    responses: dict[type[BaseModel], BaseModel | Responder] = field(default_factory=dict)
    calls: list[RecordedCall] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=lambda: LLMUsage(input_tokens=500, output_tokens=200))

    def respond_with(self, response: BaseModel | Responder, *, schema: type[BaseModel]) -> None:
        self.responses[schema] = response

    async def complete_structured[T: BaseModel](
        self,
        *,
        model: str,
        schema: type[T],
        system: str,
        prompt: str,
        max_tokens: int = 4096,
        effort: str | None = None,
    ) -> LLMResult[T]:
        self.calls.append(RecordedCall(model, schema.__name__, system, prompt, effort))
        try:
            canned = self.responses[schema]
        except KeyError as exc:
            raise AssertionError(f"FakeLLMProvider has no response for {schema.__name__}") from exc
        output: Any = canned(system, prompt) if callable(canned) else canned
        if not isinstance(output, schema):
            output = schema.model_validate(output.model_dump())
        return LLMResult(
            output=output,
            model=model,
            usage=self.usage,
            latency_ms=1,
            cost_usd=0.0,
            provider=self.name,
        )
