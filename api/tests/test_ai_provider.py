import math

import pytest
from pydantic import BaseModel

from jobhunt.ai.embeddings import HashEmbeddingProvider
from jobhunt.ai.factory import ProviderConfigurationError, build_llm_provider, model_for
from jobhunt.ai.fake import FakeLLMProvider
from jobhunt.ai.provider import ModelRole
from jobhunt.ai.tracing import NoopTracer
from jobhunt.core.config import Settings


class Greeting(BaseModel):
    text: str


async def test_fake_provider_records_calls() -> None:
    provider = FakeLLMProvider()
    provider.respond_with(Greeting(text="hi"), schema=Greeting)
    result = await provider.complete_structured(
        model="m", schema=Greeting, system="sys", prompt="say hi", effort="low"
    )
    assert result.output.text == "hi"
    assert result.cost_usd == 0.0
    assert provider.calls[0].prompt == "say hi"
    assert provider.calls[0].effort == "low"


async def test_fake_provider_fails_loudly_without_script() -> None:
    provider = FakeLLMProvider()
    with pytest.raises(AssertionError):
        await provider.complete_structured(model="m", schema=Greeting, system="", prompt="")


def test_model_routing_follows_settings() -> None:
    settings = Settings(
        _env_file=None, model_extract="cheap", model_judge="strong", model_write="writer"
    )  # type: ignore[call-arg]
    assert model_for(ModelRole.EXTRACT, settings) == "cheap"
    assert model_for(ModelRole.JUDGE, settings) == "strong"
    assert model_for(ModelRole.WRITE, settings) == "writer"


def test_missing_api_key_is_a_configuration_error() -> None:
    settings = Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key=None)  # type: ignore[call-arg]
    with pytest.raises(ProviderConfigurationError):
        build_llm_provider(settings, NoopTracer())


async def test_hash_embeddings_are_unit_length_and_similarity_tracks_overlap() -> None:
    provider = HashEmbeddingProvider(dimensions=64)
    a, b, c = await provider.embed(
        ["python fastapi postgres", "python fastapi redis", "sales marketing seo"]
    )
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    sim = lambda u, v: sum(x * y for x, y in zip(u, v, strict=True))  # noqa: E731
    assert sim(a, b) > sim(a, c)
