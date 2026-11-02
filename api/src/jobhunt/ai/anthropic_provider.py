"""Anthropic implementation of LLMProvider using structured outputs."""

from __future__ import annotations

import time
from typing import Any

import anthropic
from pydantic import BaseModel

from jobhunt.ai.pricing import estimate_cost_usd
from jobhunt.ai.provider import LLMError, LLMRefusalError, LLMResult, LLMUsage
from jobhunt.ai.tracing import Tracer
from jobhunt.core.logging import get_logger

log = get_logger(__name__)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, tracer: Tracer, *, max_retries: int = 3) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=max_retries)
        self._tracer = tracer

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
        extra: dict[str, Any] = {}
        if effort:
            extra["output_config"] = {"effort": effort}
        started = time.perf_counter()
        with self._tracer.generation(
            name=f"anthropic.{schema.__name__}",
            model=model,
            input={"system": system, "prompt": prompt},
            metadata={"schema": schema.__name__, "effort": effort},
        ) as gen:
            try:
                response = await self._client.messages.parse(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    output_format=schema,
                    **extra,
                )
            except anthropic.APIStatusError as exc:
                gen.fail(f"{exc.status_code}: {exc.message}")
                raise LLMError(f"anthropic {exc.status_code}: {exc.message}") from exc
            except anthropic.APIConnectionError as exc:
                gen.fail(str(exc))
                raise LLMError(f"anthropic connection error: {exc}") from exc

            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.stop_reason == "refusal":
                gen.fail("refusal")
                raise LLMRefusalError("model refused the request")
            if response.stop_reason == "max_tokens":
                gen.fail("max_tokens")
                raise LLMError("response truncated at max_tokens; raise the limit")

            parsed = response.parsed_output
            if parsed is None:
                gen.fail("no parsed output")
                raise LLMError("no structured output in response")

            usage = LLMUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cached_input_tokens=response.usage.cache_read_input_tokens or 0,
            )
            cost = estimate_cost_usd(model, usage)
            gen.record(
                output=parsed.model_dump(mode="json"),
                usage={"input": usage.input_tokens, "output": usage.output_tokens},
                cost_usd=cost,
                metadata={"latency_ms": latency_ms, "request_id": response._request_id},
            )
            return LLMResult(
                output=parsed,
                model=response.model,
                usage=usage,
                latency_ms=latency_ms,
                cost_usd=cost,
                provider=self.name,
                request_id=response._request_id,
            )
