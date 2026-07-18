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


def text_hash(normalized_problem_text: str) -> str:
    return hashlib.sha256(normalized_problem_text.encode("utf-8")).hexdigest()


__all__ = [
    "MODEL_PRICING_USD_PER_MILLION",
    "PRICING_VERSION",
    "UsageSummary",
    "estimate_cost",
    "text_hash",
]
