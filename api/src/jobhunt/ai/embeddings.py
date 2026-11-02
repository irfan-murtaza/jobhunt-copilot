"""Embedding providers. Anthropic has no embeddings API, so OpenAI is the default."""

from __future__ import annotations

import hashlib
import math
import time

import openai

from jobhunt.ai.pricing import estimate_cost_usd
from jobhunt.ai.provider import LLMError, LLMUsage
from jobhunt.ai.tracing import Tracer

MAX_BATCH = 256


class OpenAIEmbeddingProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, dimensions: int, tracer: Tracer) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key, max_retries=3)
        self.model = model
        self.dimensions = dimensions
        self._tracer = tracer

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            batch = texts[start : start + MAX_BATCH]
            started = time.perf_counter()
            with self._tracer.generation(
                name="openai.embeddings", model=self.model, input={"count": len(batch)}
            ) as gen:
                try:
                    response = await self._client.embeddings.create(
                        model=self.model, input=batch, dimensions=self.dimensions
                    )
                except (openai.APIStatusError, openai.APIConnectionError) as exc:
                    gen.fail(str(exc))
                    raise LLMError(f"openai embeddings: {exc}") from exc
                usage = LLMUsage(input_tokens=response.usage.prompt_tokens)
                gen.record(
                    output=None,
                    usage={"input": usage.input_tokens},
                    cost_usd=estimate_cost_usd(self.model, usage),
                    metadata={"latency_ms": int((time.perf_counter() - started) * 1000)},
                )
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return vectors


class HashEmbeddingProvider:
    """Deterministic, offline embeddings for tests and demos.

    Each token is hashed into one of `dimensions` buckets, so texts sharing words have a
    higher cosine similarity. Not semantically meaningful, but stable and free.
    """

    name = "hash"

    def __init__(self, dimensions: int = 1536, model: str = "hash-embedding") -> None:
        self.dimensions = dimensions
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]
