"""Privacy-safe modeler usage and conservative cost accounting."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math


MECHANICS_PRICING_VERSION = "mechanics-openai-pricing-2026-07-18"
MECHANICS_IMAGE_TOKEN_BOUND_VERSION = "openai-image-input-bound-2026-07-19"


@dataclass(frozen=True)
class ModelPriceSchedule:
    model: str
    input_usd_per_million: float
    cached_input_usd_per_million: float
    output_usd_per_million: float
    image_tokens_per_image_upper_bound: int
    pricing_version: str = MECHANICS_PRICING_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model or len(self.model) > 128:
            raise ValueError("price schedule model is invalid")
        for name in (
            "input_usd_per_million",
            "cached_input_usd_per_million",
            "output_usd_per_million",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1_000.0
            ):
                raise ValueError("price schedule rate is invalid")
        if (
            float(self.input_usd_per_million) <= 0.0
            or float(self.output_usd_per_million) <= 0.0
            or float(self.cached_input_usd_per_million)
            > float(self.input_usd_per_million)
        ):
            raise ValueError("price schedule cannot weaken conservative billing")
        if (
            not isinstance(self.image_tokens_per_image_upper_bound, int)
            or isinstance(self.image_tokens_per_image_upper_bound, bool)
            or not 1 <= self.image_tokens_per_image_upper_bound <= 1_000_000
        ):
            raise ValueError("image token upper bound is invalid")
        if (
            not isinstance(self.pricing_version, str)
            or not 1 <= len(self.pricing_version) <= 80
        ):
            raise ValueError("pricing version is invalid")


OFFICIAL_MECHANICS_PRICE_SCHEDULES = {
    "gpt-5.4-mini-2026-03-17": ModelPriceSchedule(
        model="gpt-5.4-mini-2026-03-17",
        input_usd_per_million=0.75,
        cached_input_usd_per_million=0.075,
        output_usd_per_million=4.50,
        image_tokens_per_image_upper_bound=16_384,
    )
}
MECHANICS_MODEL_PRICING_USD_PER_MILLION = {
    model: {
        "input": schedule.input_usd_per_million,
        "cached_input": schedule.cached_input_usd_per_million,
        "output": schedule.output_usd_per_million,
    }
    for model, schedule in OFFICIAL_MECHANICS_PRICE_SCHEDULES.items()
}


class UnpricedModelError(ValueError):
    """No authorized conservative price/token ceiling exists for a model."""


def resolve_price_schedule(
    model: str,
    supplied: ModelPriceSchedule | None = None,
) -> ModelPriceSchedule:
    official = OFFICIAL_MECHANICS_PRICE_SCHEDULES.get(model)
    if official is not None:
        return official
    if supplied is not None and supplied.model == model:
        return supplied
    raise UnpricedModelError("selected model has no authorized price schedule")


@dataclass(frozen=True)
class ModelerUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    measured_cost_usd: float = 0.0
    cost_known: bool = False
    pricing_version: str = MECHANICS_PRICING_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def measured_usage(
    model: str,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
    supplied_schedule: ModelPriceSchedule | None = None,
) -> ModelerUsage:
    input_tokens = max(int(input_tokens), 0)
    cached_input_tokens = min(max(int(cached_input_tokens), 0), input_tokens)
    output_tokens = max(int(output_tokens), 0)
    reasoning_tokens = max(int(reasoning_tokens), 0)
    try:
        schedule = resolve_price_schedule(model, supplied_schedule)
    except UnpricedModelError:
        return ModelerUsage(
            input_tokens,
            cached_input_tokens,
            output_tokens,
            reasoning_tokens,
            0.0,
            False,
        )
    uncached = input_tokens - cached_input_tokens
    cost = (
        uncached * schedule.input_usd_per_million
        + cached_input_tokens * schedule.cached_input_usd_per_million
        + output_tokens * schedule.output_usd_per_million
    ) / 1_000_000
    return ModelerUsage(
        input_tokens,
        cached_input_tokens,
        output_tokens,
        reasoning_tokens,
        round(cost, 9),
        True,
        schedule.pricing_version,
    )


def aggregate_usage(
    model: str,
    attempts: tuple[ModelerUsage, ...],
    *,
    supplied_schedule: ModelPriceSchedule | None = None,
) -> ModelerUsage:
    if not attempts:
        return ModelerUsage()
    result = measured_usage(
        model,
        input_tokens=sum(item.input_tokens for item in attempts),
        cached_input_tokens=sum(item.cached_input_tokens for item in attempts),
        output_tokens=sum(item.output_tokens for item in attempts),
        reasoning_tokens=sum(item.reasoning_tokens for item in attempts),
        supplied_schedule=supplied_schedule,
    )
    if attempts and not all(item.cost_known for item in attempts):
        return ModelerUsage(
            result.input_tokens,
            result.cached_input_tokens,
            result.output_tokens,
            result.reasoning_tokens,
            round(sum(item.measured_cost_usd for item in attempts), 9),
            False,
        )
    return result


def conservative_attempt_cost(
    model: str,
    *,
    input_token_ceiling: int,
    max_output_tokens: int,
    supplied_schedule: ModelPriceSchedule | None = None,
) -> float:
    schedule = resolve_price_schedule(model, supplied_schedule)
    cost = (
        max(input_token_ceiling, 0) * schedule.input_usd_per_million
        + max(max_output_tokens, 0) * schedule.output_usd_per_million
    ) / 1_000_000
    return round(cost, 9)


def safe_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "MECHANICS_MODEL_PRICING_USD_PER_MILLION",
    "MECHANICS_IMAGE_TOKEN_BOUND_VERSION",
    "MECHANICS_PRICING_VERSION",
    "ModelPriceSchedule",
    "ModelerUsage",
    "OFFICIAL_MECHANICS_PRICE_SCHEDULES",
    "UnpricedModelError",
    "aggregate_usage",
    "conservative_attempt_cost",
    "measured_usage",
    "resolve_price_schedule",
    "safe_hash",
]
