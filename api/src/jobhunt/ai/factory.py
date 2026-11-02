"""Wire settings to concrete providers. The only module that knows vendor class names."""

from __future__ import annotations

from functools import lru_cache

from jobhunt.ai.embeddings import HashEmbeddingProvider, OpenAIEmbeddingProvider
from jobhunt.ai.provider import EmbeddingProvider, LLMProvider, ModelRole
from jobhunt.ai.tracing import Tracer, build_tracer
from jobhunt.core.config import Settings, get_settings
from jobhunt.core.logging import get_logger

log = get_logger(__name__)


class ProviderConfigurationError(RuntimeError):
    pass


@lru_cache
def get_tracer() -> Tracer:
    return build_tracer(get_settings())


def model_for(role: ModelRole, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return {
        ModelRole.EXTRACT: settings.model_extract,
        ModelRole.JUDGE: settings.model_judge,
        ModelRole.WRITE: settings.model_write,
    }[role]


def build_llm_provider(settings: Settings, tracer: Tracer) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ProviderConfigurationError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is unset"
            )
        from jobhunt.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings.anthropic_api_key.get_secret_value(), tracer)
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise ProviderConfigurationError("LLM_PROVIDER=openai but OPENAI_API_KEY is unset")
        from jobhunt.ai.openai_provider import OpenAIProvider

        return OpenAIProvider(settings.openai_api_key.get_secret_value(), tracer)
    raise ProviderConfigurationError(f"unknown LLM_PROVIDER {settings.llm_provider!r}")


def build_embedding_provider(settings: Settings, tracer: Tracer) -> EmbeddingProvider:
    if settings.is_test or settings.embedding_provider == "hash":
        if not settings.is_test:
            log.warning(
                "embeddings.hash_provider",
                msg="EMBEDDING_PROVIDER=hash: offline, demo-quality embeddings",
            )
        return HashEmbeddingProvider(dimensions=settings.embedding_dimensions)
    if not settings.openai_api_key:
        raise ProviderConfigurationError("OPENAI_API_KEY is required for embeddings")
    return OpenAIEmbeddingProvider(
        settings.openai_api_key.get_secret_value(),
        settings.embedding_model,
        settings.embedding_dimensions,
        tracer,
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    return build_llm_provider(get_settings(), get_tracer())


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return build_embedding_provider(get_settings(), get_tracer())
