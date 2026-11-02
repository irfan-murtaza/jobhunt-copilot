from jobhunt.ai.pricing import estimate_cost_usd, price_for
from jobhunt.ai.provider import LLMUsage


def test_known_model_cost() -> None:
    usage = LLMUsage(input_tokens=1_000_000, output_tokens=0)
    assert estimate_cost_usd("claude-haiku-5-5", usage) == 0.10


def test_cached_tokens_are_cheaper() -> None:
    plain = estimate_cost_usd("claude-opus-5-5", LLMUsage(input_tokens=1000, output_tokens=0))
    cached = estimate_cost_usd(
        "claude-opus-5-5", LLMUsage(input_tokens=1000, output_tokens=0, cached_input_tokens=1000)
    )
    assert plain is not None and cached is not None and cached < plain


def test_unknown_model_yields_none_not_a_guess() -> None:
    assert price_for("some-future-model") is None
    assert estimate_cost_usd("some-future-model", LLMUsage(1, 1)) is None


def test_dated_snapshot_falls_back_to_base_price() -> None:
    assert price_for("gpt-4o-2024-08-06") == price_for("gpt-4o")
