from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib


PRICING_VERSION = "openai-pricing-2026-07-18"
MODEL_PRICING_USD_PER_MILLION = {
    "gpt-5.4-mini-2026-03-17": {
        "input": 0.75,
        "cached_input": 0.075,
        "output": 4.50,
    }
}


@dataclass(frozen=True)
class UsageSummary:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_cost_usd: float = 0.0
    pricing_version: str = PRICING_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def estimate_cost(
    model: str,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
) -> UsageSummary:
    rates = MODEL_PRICING_USD_PER_MILLION.get(model)
    if rates is None:
        return UsageSummary(input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, 0.0)
    uncached = max(input_tokens - cached_input_tokens, 0)
    cost = (
        uncached * rates["input"]
        + cached_input_tokens * rates["cached_input"]
        + output_tokens * rates["output"]
    ) / 1_000_000
    return UsageSummary(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        estimated_cost_usd=round(cost, 9),
    )


def aggregate_usage(model: str, *attempts: UsageSummary) -> UsageSummary:
    """Aggregate every successful parser attempt, including repair attempts."""

    return estimate_cost(
        model,
        input_tokens=sum(item.input_tokens for item in attempts),
        cached_input_tokens=sum(item.cached_input_tokens for item in attempts),
        output_tokens=sum(item.output_tokens for item in attempts),
        reasoning_tokens=sum(item.reasoning_tokens for item in attempts),
    )


def conservative_attempt_cost_upper_bound(
    model: str,
    *,
    input_character_budget: int,
    max_output_tokens: int,
) -> float:
    """Reserve a privacy-safe upper estimate before an API request.

    One input token per source/prompt character is intentionally conservative.
    A successful response replaces this reservation with measured SDK usage. An
    exception without usage metadata retains the reservation, so missing usage
    can never make the bounded live runner appear cheaper than it may have been.
    """

    estimate = estimate_cost(
        model,
        input_tokens=max(input_character_budget, 0),
        cached_input_tokens=0,
        output_tokens=max(max_output_tokens, 0),
    )
    return estimate.estimated_cost_usd


def text_hash(normalized_problem_text: str) -> str:
    return hashlib.sha256(normalized_problem_text.encode("utf-8")).hexdigest()


__all__ = [
    "MODEL_PRICING_USD_PER_MILLION",
    "PRICING_VERSION",
    "UsageSummary",
    "aggregate_usage",
    "conservative_attempt_cost_upper_bound",
    "estimate_cost",
    "text_hash",
]
