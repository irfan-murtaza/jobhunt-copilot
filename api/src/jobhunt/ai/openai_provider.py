"""OpenAI implementation of LLMProvider (Responses API with structured outputs)."""

from __future__ import annotations

import time

import openai
from pydantic import BaseModel

from jobhunt.ai.pricing import estimate_cost_usd
from jobhunt.ai.provider import LLMError, LLMRefusalError, LLMResult, LLMUsage
from jobhunt.ai.tracing import Tracer
from jobhunt.core.logging import get_logger

log = get_logger(__name__)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, tracer: Tracer, *, max_retries: int = 3) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key, max_retries=max_retries)
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
        started = time.perf_counter()
        with self._tracer.generation(
            name=f"openai.{schema.__name__}",
            model=model,
            input={"system": system, "prompt": prompt},
            metadata={"schema": schema.__name__, "effort": effort},
        ) as gen:
            try:
                response = await self._client.responses.parse(
                    model=model,
                    instructions=system,
                    input=prompt,
                    text_format=schema,
                    max_output_tokens=max_tokens,
                )
            except openai.APIStatusError as exc:
                gen.fail(f"{exc.status_code}: {exc.message}")
                raise LLMError(f"openai {exc.status_code}: {exc.message}") from exc
            except openai.APIConnectionError as exc:
                gen.fail(str(exc))
                raise LLMError(f"openai connection error: {exc}") from exc

            latency_ms = int((time.perf_counter() - started) * 1000)
            parsed = response.output_parsed
            if parsed is None:
                # A refusal surfaces as an output item of type "refusal".
                for item in response.output:
                    content = getattr(item, "content", None) or []
                    if any(getattr(part, "type", "") == "refusal" for part in content):
                        gen.fail("refusal")
                        raise LLMRefusalError("model refused the request")
                gen.fail("no parsed output")
                raise LLMError("no structured output in response")

            usage_obj = response.usage
            cached = (
                usage_obj.input_tokens_details.cached_tokens
                if usage_obj and usage_obj.input_tokens_details
                else 0
            )
            usage = LLMUsage(
                input_tokens=usage_obj.input_tokens if usage_obj else 0,
                output_tokens=usage_obj.output_tokens if usage_obj else 0,
                cached_input_tokens=cached or 0,
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
