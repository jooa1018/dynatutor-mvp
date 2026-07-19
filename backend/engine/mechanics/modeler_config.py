"""Bounded, rollout-safe configuration for the Phase-56 mechanics modeler."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import os

from engine.mechanics.modeler_telemetry import ModelPriceSchedule


DEFAULT_MECHANICS_MODELER_MODEL = "gpt-5.4-mini-2026-03-17"
REASONING_EFFORTS = frozenset({"low", "medium", "high"})


class MechanicsIRMode(str, Enum):
    off = "off"
    shadow = "shadow"
    confirm = "confirm"
    auto = "auto"
    required = "required"


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _integer(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _number(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    return min(max(_integer(name, default), low), high)


def _bounded_float(name: str, default: float, low: float, high: float) -> float:
    return min(max(_number(name, default), low), high)


@dataclass(frozen=True)
class MechanicsModelerConfig:
    enabled: bool = False
    mode: MechanicsIRMode = MechanicsIRMode.off
    model: str = DEFAULT_MECHANICS_MODELER_MODEL
    # An unset figure override deliberately uses ``model``.  There is no second
    # guessed default snapshot.
    figure_model: str | None = None
    store: bool = False
    max_retries: int = 1
    timeout_seconds: float = 20.0
    reasoning_effort: str = "low"
    figure_enabled: bool = False
    max_problem_chars: int = 12_000
    max_images: int = 4
    max_image_bytes: int = 5_000_000
    max_total_image_bytes: int = 12_000_000
    max_output_tokens: int = 8_000
    max_inflight: int = 8
    max_total_cost_usd: float = 2.0
    model_price_schedule: ModelPriceSchedule | None = None
    cache_enabled: bool = False
    cache_path: str | None = None
    cache_ttl_seconds: int = 604_800
    cache_l1_entries: int = 256
    cache_l2_entries: int = 5_000

    def __post_init__(self) -> None:
        for name in ("enabled", "store", "figure_enabled", "cache_enabled"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        if not isinstance(self.mode, MechanicsIRMode):
            raise ValueError("mode must use MechanicsIRMode")
        for name in (
            "max_retries",
            "max_problem_chars",
            "max_images",
            "max_image_bytes",
            "max_total_image_bytes",
            "max_output_tokens",
            "max_inflight",
            "cache_ttl_seconds",
            "cache_l1_entries",
            "cache_l2_entries",
        ):
            if not isinstance(getattr(self, name), int) or isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be an integer")
        for name in ("timeout_seconds", "max_total_cost_usd"):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"{name} must be finite numeric")
        if self.store:
            raise ValueError("MECHANICS_MODELER_STORE must remain false")
        if (
            not isinstance(self.model, str)
            or not self.model
            or self.model != self.model.strip()
            or len(self.model) > 128
        ):
            raise ValueError("MECHANICS_MODELER_MODEL must be non-empty")
        if self.figure_model is not None and (
            not isinstance(self.figure_model, str)
            or not self.figure_model.strip()
            or self.figure_model != self.figure_model.strip()
            or len(self.figure_model) > 128
        ):
            raise ValueError("MECHANICS_FIGURE_MODEL must be non-empty when set")
        if self.cache_path is not None and (
            not isinstance(self.cache_path, str) or len(self.cache_path) > 1_024
        ):
            raise ValueError("mechanics cache path is too long")
        if self.model_price_schedule is not None and not isinstance(
            self.model_price_schedule, ModelPriceSchedule
        ):
            raise ValueError("model price schedule is invalid")
        if (
            not isinstance(self.reasoning_effort, str)
            or self.reasoning_effort not in REASONING_EFFORTS
        ):
            raise ValueError(
                "MECHANICS_MODELER_REASONING_EFFORT must be low, medium, or high"
            )
        if self.max_retries not in {0, 1}:
            raise ValueError("mechanics modeler retries must be 0 or 1")
        if not 1.0 <= self.timeout_seconds <= 60.0:
            raise ValueError("mechanics modeler timeout must be between 1 and 60 seconds")
        if not 500 <= self.max_problem_chars <= 50_000:
            raise ValueError("mechanics problem character budget is out of bounds")
        if not 1 <= self.max_images <= 8:
            raise ValueError("mechanics image count budget is out of bounds")
        if not 1_024 <= self.max_image_bytes <= 20_000_000:
            raise ValueError("mechanics per-image byte budget is out of bounds")
        if not self.max_image_bytes <= self.max_total_image_bytes <= 50_000_000:
            raise ValueError("mechanics total image byte budget is out of bounds")
        if not 512 <= self.max_output_tokens <= 16_000:
            raise ValueError("mechanics output token budget is out of bounds")
        if not 1 <= self.max_inflight <= 32:
            raise ValueError("mechanics inflight budget is out of bounds")
        if not 0.001 <= self.max_total_cost_usd <= 2.0:
            raise ValueError("mechanics total cost budget is out of bounds")
        if not 60 <= self.cache_ttl_seconds <= 2_592_000:
            raise ValueError("mechanics cache TTL is out of bounds")
        if not 1 <= self.cache_l1_entries <= 2_048:
            raise ValueError("mechanics L1 cache size is out of bounds")
        if not 10 <= self.cache_l2_entries <= 50_000:
            raise ValueError("mechanics L2 cache size is out of bounds")

    @property
    def active(self) -> bool:
        return self.enabled and self.mode is not MechanicsIRMode.off

    def selected_model(self, *, has_images: bool) -> str:
        if has_images and self.figure_model is not None:
            return self.figure_model
        return self.model

    @classmethod
    def from_env(cls) -> "MechanicsModelerConfig":
        enabled = _bool("MECHANICS_IR_ENABLED", False)
        try:
            mode = MechanicsIRMode(os.getenv("MECHANICS_IR_MODE", "off").strip().lower())
        except ValueError as exc:
            raise ValueError(
                "MECHANICS_IR_MODE must be off, shadow, confirm, auto, or required"
            ) from exc
        if not enabled:
            mode = MechanicsIRMode.off
        store = _bool("MECHANICS_MODELER_STORE", False)
        if store:
            raise ValueError("MECHANICS_MODELER_STORE must remain false")
        reasoning_effort = os.getenv(
            "MECHANICS_MODELER_REASONING_EFFORT", "low"
        ).strip().lower()
        if reasoning_effort not in REASONING_EFFORTS:
            raise ValueError(
                "MECHANICS_MODELER_REASONING_EFFORT must be low, medium, or high"
            )
        figure_override = os.getenv("MECHANICS_FIGURE_MODEL")
        figure_model = figure_override.strip() if figure_override else None
        cache_path = os.getenv("MECHANICS_MODELER_CACHE_PATH") or None
        price_env_names = (
            "MECHANICS_MODELER_PRICE_MODEL",
            "MECHANICS_MODELER_INPUT_USD_PER_MILLION",
            "MECHANICS_MODELER_CACHED_INPUT_USD_PER_MILLION",
            "MECHANICS_MODELER_OUTPUT_USD_PER_MILLION",
            "MECHANICS_MODELER_IMAGE_TOKEN_UPPER_BOUND",
        )
        price_values = tuple(os.getenv(name) for name in price_env_names)
        if any(value is not None for value in price_values):
            if any(value is None for value in price_values):
                raise ValueError("all mechanics model price schedule fields are required")
            model_price_schedule = ModelPriceSchedule(
                model=str(price_values[0]).strip(),
                input_usd_per_million=_number(price_env_names[1], 0.0),
                cached_input_usd_per_million=_number(price_env_names[2], 0.0),
                output_usd_per_million=_number(price_env_names[3], 0.0),
                image_tokens_per_image_upper_bound=_integer(price_env_names[4], 0),
            )
        else:
            model_price_schedule = None
        max_image_bytes = _bounded_int(
            "MECHANICS_MODELER_MAX_IMAGE_BYTES", 5_000_000, 1_024, 20_000_000
        )
        max_total_image_bytes = _bounded_int(
            "MECHANICS_MODELER_MAX_TOTAL_IMAGE_BYTES",
            12_000_000,
            max_image_bytes,
            50_000_000,
        )
        return cls(
            enabled=enabled,
            mode=mode,
            model=os.getenv(
                "MECHANICS_MODELER_MODEL", DEFAULT_MECHANICS_MODELER_MODEL
            ).strip(),
            figure_model=figure_model,
            store=False,
            max_retries=min(
                max(_integer("MECHANICS_MODELER_MAX_RETRIES", 1), 0), 1
            ),
            timeout_seconds=_bounded_float(
                "MECHANICS_MODELER_TIMEOUT_SECONDS", 20.0, 1.0, 60.0
            ),
            reasoning_effort=reasoning_effort,
            figure_enabled=_bool("MECHANICS_FIGURE_ENABLED", False),
            max_problem_chars=_bounded_int(
                "MECHANICS_MODELER_MAX_PROBLEM_CHARS", 12_000, 500, 50_000
            ),
            max_images=_bounded_int("MECHANICS_MODELER_MAX_IMAGES", 4, 1, 8),
            max_image_bytes=max_image_bytes,
            max_total_image_bytes=max_total_image_bytes,
            max_output_tokens=_bounded_int(
                "MECHANICS_MODELER_MAX_OUTPUT_TOKENS", 8_000, 512, 16_000
            ),
            max_inflight=_bounded_int(
                "MECHANICS_MODELER_MAX_INFLIGHT", 8, 1, 32
            ),
            max_total_cost_usd=_bounded_float(
                "MECHANICS_MODELER_MAX_COST_USD", 2.0, 0.001, 2.0
            ),
            model_price_schedule=model_price_schedule,
            cache_enabled=_bool("MECHANICS_MODELER_CACHE_ENABLED", False),
            cache_path=cache_path,
            cache_ttl_seconds=_bounded_int(
                "MECHANICS_MODELER_CACHE_TTL_SECONDS", 604_800, 60, 2_592_000
            ),
            cache_l1_entries=_bounded_int(
                "MECHANICS_MODELER_CACHE_L1_ENTRIES", 256, 1, 2_048
            ),
            cache_l2_entries=_bounded_int(
                "MECHANICS_MODELER_CACHE_L2_ENTRIES", 5_000, 10, 50_000
            ),
        )


__all__ = [
    "DEFAULT_MECHANICS_MODELER_MODEL",
    "MechanicsIRMode",
    "MechanicsModelerConfig",
    "REASONING_EFFORTS",
]
