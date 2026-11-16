"""Model profiles and pricing.

Prices are USD per million tokens (Anthropic first-party list prices, cached 2026-11-03).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float
    # Long-prompt tier (Haiku 5.5 charges more above 100K input tokens).
    long_prompt_threshold: int | None = None
    long_input_per_mtok: float | None = None
    long_output_per_mtok: float | None = None
    cache_write_multiplier: float = 1.25
    cache_read_multiplier: float = 0.10


PRICES: dict[str, ModelPrice] = {
    "claude-haiku-5-5": ModelPrice(0.10, 0.50, 100_000, 0.50, 2.50),
    "claude-sonnet-5-5": ModelPrice(2.00, 10.00),
    "claude-opus-5-5": ModelPrice(4.00, 20.00),
}


@dataclass(frozen=True)
class ModelProfile:
    name: str
    main: str
    judge: str
    default_effort: Effort


PROFILES: dict[str, ModelProfile] = {
    "cheap": ModelProfile("cheap", "claude-haiku-5-5", "claude-haiku-5-5", "low"),
    "quality": ModelProfile("quality", "claude-opus-5-5", "claude-haiku-5-5", "medium"),
}


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Compute request cost. `input_tokens` excludes cached tokens, as in the API's usage object."""
    price = PRICES.get(model)
    if price is None:
        raise KeyError(f"No price registered for model {model!r}")
    total_prompt = input_tokens + cache_write_tokens + cache_read_tokens
    in_rate, out_rate = price.input_per_mtok, price.output_per_mtok
    if (
        price.long_prompt_threshold is not None
        and total_prompt > price.long_prompt_threshold
        and price.long_input_per_mtok is not None
        and price.long_output_per_mtok is not None
    ):
        in_rate, out_rate = price.long_input_per_mtok, price.long_output_per_mtok
    cost = (
        input_tokens * in_rate
        + cache_write_tokens * in_rate * price.cache_write_multiplier
        + cache_read_tokens * in_rate * price.cache_read_multiplier
        + output_tokens * out_rate
    )
    return cost / 1_000_000
