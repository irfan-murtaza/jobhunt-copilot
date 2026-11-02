"""USD prices per million tokens, used to attribute cost to every job we process.

Prices change; this table is the single place to update them. A model missing from the
table yields `None` rather than a guessed number, so cost reports never contain
fabricated figures.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobhunt.ai.provider import LLMUsage


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float | None = None


# Anthropic first-party API list prices (Oct 2026). OpenAI prices as published on
# platform.openai.com/pricing at the time of writing. Update when they change.
PRICES: dict[str, ModelPrice] = {
    "claude-opus-5-5": ModelPrice(4.00, 20.00, 0.20),
    "claude-sonnet-5-5": ModelPrice(2.00, 10.00, 0.20),
    "claude-haiku-5-5": ModelPrice(0.10, 0.50, 0.01),
    "claude-opus-4-8": ModelPrice(5.00, 25.00, 0.50),
    "claude-sonnet-4-6": ModelPrice(3.00, 15.00, 0.30),
    "claude-haiku-4-5": ModelPrice(1.00, 5.00, 0.10),
    "gpt-4o-mini": ModelPrice(0.15, 0.60, 0.075),
    "gpt-4o": ModelPrice(2.50, 10.00, 1.25),
    "gpt-4.1": ModelPrice(2.00, 8.00, 0.50),
    "gpt-4.1-mini": ModelPrice(0.40, 1.60, 0.10),
    "text-embedding-3-small": ModelPrice(0.02, 0.0),
    "text-embedding-3-large": ModelPrice(0.13, 0.0),
}


def price_for(model: str) -> ModelPrice | None:
    if model in PRICES:
        return PRICES[model]
    # Tolerate dated snapshots such as "gpt-4o-2024-08-06".
    for known, price in PRICES.items():
        if model.startswith(known + "-"):
            return price
    return None


def estimate_cost_usd(model: str, usage: LLMUsage) -> float | None:
    price = price_for(model)
    if price is None:
        return None
    uncached = max(usage.input_tokens - usage.cached_input_tokens, 0)
    cached_rate = (
        price.cached_input_per_million
        if price.cached_input_per_million is not None
        else price.input_per_million
    )
    cost = (
        uncached * price.input_per_million
        + usage.cached_input_tokens * cached_rate
        + usage.output_tokens * price.output_per_million
    ) / 1_000_000
    return round(cost, 8)
