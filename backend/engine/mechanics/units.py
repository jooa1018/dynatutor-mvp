"""Bounded, whitelist-only conversion of mechanics raw quantities to SI.

This module intentionally does not expose Pint's parser to untrusted text.  A
raw unit must first match one of the finite aliases below; only the associated
trusted Pint expression is ever passed to the registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Final

try:
    from pint import DimensionalityError, UnitRegistry
except ModuleNotFoundError:  # pragma: no cover - exercised by offline harnesses
    from tools._pint_shim import DimensionalityError, UnitRegistry

from engine.mechanics.math_ast import DimensionVector
from engine.textbook_parser.evidence_alignment import (
    _normalized_number,
    _normalized_unit,
    quantity_occurrences,
)


_MAX_RAW_VALUE = 80
_MAX_RAW_UNIT = 48
_MAX_SI_MAGNITUDE = 1.0e300
_MAX_NORMALIZED_NUMBER = 80
_MAX_NORMALIZED_UNIT = 48
_MAX_SAFE_DECIMAL_EXPONENT = 10_000
_UREG = UnitRegistry()


class UnitNormalizationError(ValueError):
    """Base exception for deliberately non-diagnostic unit normalization."""


class UnitParseError(UnitNormalizationError):
    pass


class UnitDimensionError(UnitNormalizationError):
    pass


class UnitNonFiniteError(UnitNormalizationError):
    pass


@dataclass(frozen=True)
class NormalizedQuantity:
    value: float | tuple[float, ...]
    si_unit: str
    dimension: DimensionVector


def _dim(
    mass: int = 0,
    length: int = 0,
    time: int = 0,
    current: int = 0,
    temperature: int = 0,
    amount: int = 0,
    luminous_intensity: int = 0,
) -> DimensionVector:
    return DimensionVector(
        mass=mass,
        length=length,
        time=time,
        current=current,
        temperature=temperature,
        amount=amount,
        luminous_intensity=luminous_intensity,
    )


_D0: Final = _dim()
_DM: Final = _dim(mass=1)
_DL: Final = _dim(length=1)
_DT: Final = _dim(time=1)
_DV: Final = _dim(length=1, time=-1)
_DA: Final = _dim(length=1, time=-2)
_DF: Final = _dim(mass=1, length=1, time=-2)
_DE: Final = _dim(mass=1, length=2, time=-2)
_DP: Final = _dim(mass=1, length=1, time=-1)
_DK: Final = _dim(mass=1, time=-2)
_DI: Final = _dim(mass=1, length=2)
_DFREQ: Final = _dim(time=-1)
_DANGULAR_ACCELERATION: Final = _dim(time=-2)
_DCURRENT: Final = _dim(current=1)
_DTEMPERATURE: Final = _dim(temperature=1)
_DAMOUNT: Final = _dim(amount=1)
_DLUMINOUS: Final = _dim(luminous_intensity=1)
_TWO_PI: Final = Decimal("6.283185307179586476925286766559")


@dataclass(frozen=True)
class _UnitSpec:
    pint_expression: str
    factor: Decimal
    dimension: DimensionVector
    # Degrees and radians share a dimension with ordinary scalars but are
    # semantically angles, whose calculation unit is always rad.
    angle: bool = False


def _spec(expr: str, factor: str, dimension: DimensionVector, *, angle: bool = False) -> _UnitSpec:
    return _UnitSpec(expr, Decimal(factor), dimension, angle)


# Keys are already safely case-folded and stripped of only horizontal spaces.
# Add aliases here rather than broadening any parser.
_ALIASES: Final[dict[str, _UnitSpec]] = {
    "": _spec("", "1", _D0), "1": _spec("", "1", _D0), "%": _spec("", "0.01", _D0),
    "m": _spec("meter", "1", _DL), "cm": _spec("centimeter", "1", _DL),
    "mm": _spec("millimeter", "1", _DL), "km": _spec("kilometer", "1", _DL), "미터": _spec("meter", "1", _DL),
    "s": _spec("second", "1", _DT), "sec": _spec("second", "1", _DT), "초": _spec("second", "1", _DT),
    "min": _spec("minute", "1", _DT), "분": _spec("minute", "1", _DT), "h": _spec("hour", "1", _DT), "시간": _spec("hour", "1", _DT),
    "m/s": _spec("meter/second", "1", _DV), "m/sec": _spec("meter/second", "1", _DV), "mps": _spec("meter/second", "1", _DV),
    "m·s^-1": _spec("meter/second", "1", _DV), "m*s^-1": _spec("meter/second", "1", _DV),
    "km/h": _spec("kilometer/hour", "1", _DV), "km/hr": _spec("kilometer/hour", "1", _DV), "kmph": _spec("kilometer/hour", "1", _DV),
    "m/s2": _spec("meter/second**2", "1", _DA), "m/s^2": _spec("meter/second**2", "1", _DA), "m/s²": _spec("meter/second**2", "1", _DA), "m/sec2": _spec("meter/second**2", "1", _DA), "m/sec^2": _spec("meter/second**2", "1", _DA), "m/sec²": _spec("meter/second**2", "1", _DA),
    "m·s^-2": _spec("meter/second**2", "1", _DA), "m*s^-2": _spec("meter/second**2", "1", _DA),
    "cm/s2": _spec("centimeter/second**2", "1", _DA), "cm/s^2": _spec("centimeter/second**2", "1", _DA), "cm/s²": _spec("centimeter/second**2", "1", _DA),
    "kg": _spec("kilogram", "1", _DM), "g": _spec("gram", "1", _DM),
    "n": _spec("newton", "1", _DF), "kn": _spec("newton", "1000", _DF), "j": _spec("joule", "1", _DE),
    "n*m": _spec("newton*meter", "1", _DE), "n·m": _spec("newton*meter", "1", _DE), "nm": _spec("newton*meter", "1", _DE),
    "n*s": _spec("newton*second", "1", _DP), "n·s": _spec("newton*second", "1", _DP), "n/m": _spec("newton/meter", "1", _DK),
    "kg*m^2": _spec("kilogram*meter**2", "1", _DI), "kg*m²": _spec("kilogram*meter**2", "1", _DI),
    "kg·m^2": _spec("kilogram*meter**2", "1", _DI), "kg·m²": _spec("kilogram*meter**2", "1", _DI), "kg·m2": _spec("kilogram*meter**2", "1", _DI),
    "kg*m2": _spec("kilogram*meter**2", "1", _DI), "kgm^2": _spec("kilogram*meter**2", "1", _DI), "kgm²": _spec("kilogram*meter**2", "1", _DI),
    "deg": _spec("degree", "1", _D0, angle=True), "도": _spec("degree", "1", _D0, angle=True), "°": _spec("degree", "1", _D0, angle=True), "rad": _spec("radian", "1", _D0, angle=True),
    "rad/s": _spec("radian/second", "1", _DFREQ, angle=True), "rpm": _spec("radian/minute", str(_TWO_PI), _DFREQ, angle=True),
    "rad/s2": _spec("radian/second**2", "1", _DANGULAR_ACCELERATION, angle=True), "rad/s^2": _spec("radian/second**2", "1", _DANGULAR_ACCELERATION, angle=True), "rad/s²": _spec("radian/second**2", "1", _DANGULAR_ACCELERATION, angle=True),
    "hz": _spec("second**-1", "1", _DFREQ),
    "a": _spec("ampere", "1", _DCURRENT), "ampere": _spec("ampere", "1", _DCURRENT),
    "k": _spec("kelvin", "1", _DTEMPERATURE), "kelvin": _spec("kelvin", "1", _DTEMPERATURE),
    "mol": _spec("mole", "1", _DAMOUNT), "mole": _spec("mole", "1", _DAMOUNT),
    "cd": _spec("candela", "1", _DLUMINOUS), "candela": _spec("candela", "1", _DLUMINOUS),
}


def _bounded_string(value: object, maximum: int, *, allow_empty: bool = False) -> str:
    if type(value) is not str or len(value) > maximum or (not allow_empty and not value):
        raise UnitParseError("raw quantity is not a bounded exact string")
    return value


def parse_scalar(raw_value: object) -> Decimal:
    """Parse the intentionally small Phase-55 scalar language exactly."""
    text = _bounded_string(raw_value, _MAX_RAW_VALUE)
    try:
        occurrences = quantity_occurrences(text)
    except Exception as exc:
        raise UnitParseError("numeric token could not be inspected safely") from exc
    if (
        len(occurrences) != 1
        or occurrences[0].start != 0
        or occurrences[0].end != len(text)
        or occurrences[0].raw_value != text
        or occurrences[0].raw_unit != ""
    ):
        raise UnitParseError("numeric token is outside the supported grammar")
    try:
        normalized = _normalized_number(occurrences[0].raw_value)
    except Exception as exc:
        raise UnitParseError("numeric token normalization failed") from exc
    if type(normalized) is not str or not normalized or len(normalized) > _MAX_NORMALIZED_NUMBER:
        raise UnitParseError("normalized numeric token exceeds its bound")
    try:
        if "/" in normalized:
            numerator, denominator = normalized.split("/", 1)
            denominator_value = Decimal(denominator)
            if denominator_value == 0:
                raise UnitParseError("fraction denominator is zero")
            value = Decimal(numerator) / denominator_value
        else:
            exponent_marker = normalized.lower().find("e")
            if exponent_marker >= 0:
                exponent_text = normalized[exponent_marker + 1 :]
                unsigned_exponent = exponent_text.lstrip("+-").lstrip("0") or "0"
                if len(unsigned_exponent) > 5:
                    raise UnitNonFiniteError("scientific exponent is outside the safe bound")
                exponent = int(exponent_text)
                if abs(exponent) > _MAX_SAFE_DECIMAL_EXPONENT:
                    raise UnitNonFiniteError("scientific exponent is outside the safe bound")
            value = Decimal(normalized)
    except UnitNormalizationError:
        raise
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise UnitParseError("numeric token cannot be represented exactly") from exc
    if not value.is_finite() or (value != 0 and value.adjusted() > 300):
        raise UnitNonFiniteError("numeric value is non-finite or out of range")
    try:
        float_value = float(value)
    except (OverflowError, ValueError) as exc:
        raise UnitNonFiniteError("numeric value cannot be represented as a finite float") from exc
    if not math.isfinite(float_value) or abs(float_value) > _MAX_SI_MAGNITUDE or (value != 0 and float_value == 0.0):
        raise UnitNonFiniteError("numeric value cannot be represented as a finite bounded float")
    return value


def parse_vector(raw_value: object) -> tuple[Decimal, ...]:
    text = _bounded_string(raw_value, _MAX_RAW_VALUE)
    # Newlines and other unicode spaces are deliberately not separators.
    parts = text.split(",")
    if not 2 <= len(parts) <= 3:
        raise UnitParseError("vector requires two or three comma-separated components")
    values: list[Decimal] = []
    for part in parts:
        token = part.strip(" \t")
        if not token:
            raise UnitParseError("vector components must be complete scalar tokens")
        values.append(parse_scalar(token))
    return tuple(values)


def _unit_spec(raw_unit: object) -> _UnitSpec:
    text = _bounded_string(raw_unit, _MAX_RAW_UNIT, allow_empty=True)
    if any(character in "\t\r\n\v\f" for character in text):
        raise UnitParseError("unit has unsupported whitespace")
    try:
        key = _normalized_unit(text)
    except Exception as exc:
        raise UnitParseError("unit normalization failed") from exc
    if type(key) is not str or len(key) > _MAX_NORMALIZED_UNIT:
        raise UnitParseError("normalized unit exceeds its bound")
    try:
        return _ALIASES[key]
    except KeyError as exc:
        raise UnitParseError("unit is not in the approved alias whitelist") from exc


def _base_expression(dimension: DimensionVector) -> str:
    factors: list[str] = []
    for unit, exponent in (
        ("kilogram", dimension.mass),
        ("meter", dimension.length),
        ("second", dimension.time),
        ("ampere", dimension.current),
        ("kelvin", dimension.temperature),
        ("mole", dimension.amount),
        ("candela", dimension.luminous_intensity),
    ):
        if exponent:
            factors.append(unit if exponent == 1 else f"{unit}**{exponent}")
    return "*".join(factors)


def _pint_dimension_matches(quantity: object, expected: DimensionVector) -> bool:
    """Compare all seven fields through trusted expressions, not display text."""
    try:
        return quantity.dimensionality == _UREG.Quantity(1, _base_expression(expected)).dimensionality
    except Exception:
        return False


def _si_display_unit(dimension: DimensionVector, *, angle: bool) -> str:
    if angle and dimension == _D0:
        return "rad"
    if angle and dimension == _DFREQ:
        return "rad/s"
    if angle and dimension == _DANGULAR_ACCELERATION:
        return "rad/s^2"
    names = (("kg", dimension.mass), ("m", dimension.length), ("s", dimension.time), ("A", dimension.current), ("K", dimension.temperature), ("mol", dimension.amount), ("cd", dimension.luminous_intensity))
    fields = [name if exponent == 1 else f"{name}^{exponent}" for name, exponent in names if exponent]
    unit = "*".join(fields)
    if len(unit) > _MAX_RAW_UNIT:
        raise UnitParseError("normalized SI unit exceeds contract bounds")
    return unit


def _pint_si_target(dimension: DimensionVector, *, angle: bool) -> str:
    if angle and dimension == _D0:
        return "radian"
    if angle and dimension == _DFREQ:
        return "radian/second"
    if angle and dimension == _DANGULAR_ACCELERATION:
        return "radian/second**2"
    if dimension == _D0:
        return ""
    # The finite aliases only use M/L/T.  This is deliberately explicit so the
    # shim and real Pint receive the same trusted grammar.
    if dimension == _DF:
        return "newton"
    if dimension == _DE:
        return "joule"
    if dimension == _DP:
        return "newton*second"
    if dimension == _DK:
        return "newton/meter"
    if dimension == _DI:
        return "kilogram*meter**2"
    target = _base_expression(dimension)
    if not target:
        raise UnitDimensionError("dimension has no approved SI conversion target")
    return target


def normalize_quantity(
    raw_value: object,
    raw_unit: object,
    shape: object,
    expected_dimension: DimensionVector,
) -> NormalizedQuantity:
    """Normalize one scalar/vector raw pair, rejecting all unsupported forms."""
    if not isinstance(expected_dimension, DimensionVector):
        raise UnitDimensionError("expected dimension is not a DimensionVector")
    shape_value = getattr(shape, "value", shape)
    if shape_value == "tensor":
        raise UnitParseError("raw tensor normalization is not supported")
    if shape_value == "scalar":
        parsed: tuple[Decimal, ...] = (parse_scalar(raw_value),)
        scalar = True
    elif shape_value == "vector":
        parsed = parse_vector(raw_value)
        scalar = False
    else:
        raise UnitParseError("quantity shape is not supported")
    spec = _unit_spec(raw_unit)
    if spec.dimension != expected_dimension:
        raise UnitDimensionError("raw unit dimension differs from the declared quantity dimension")
    try:
        sample = _UREG.Quantity(1, spec.pint_expression)
        if not _pint_dimension_matches(sample, spec.dimension):
            raise UnitDimensionError("trusted unit conversion produced an unexpected dimension")
        target = _pint_si_target(spec.dimension, angle=spec.angle)
        converted = [float((_UREG.Quantity(float(value * spec.factor), spec.pint_expression)).to(target).magnitude) for value in parsed]
    except UnitNormalizationError:
        raise
    except (DimensionalityError, ValueError, TypeError, OverflowError) as exc:
        raise UnitParseError("trusted unit conversion failed") from exc
    if any(
        not math.isfinite(value)
        or abs(value) > _MAX_SI_MAGNITUDE
        or (source != 0 and value == 0.0)
        for source, value in zip(parsed, converted, strict=True)
    ):
        raise UnitNonFiniteError("converted SI value is non-finite or out of range")
    value: float | tuple[float, ...] = converted[0] if scalar else tuple(converted)
    return NormalizedQuantity(value=value, si_unit=_si_display_unit(spec.dimension, angle=spec.angle), dimension=spec.dimension)


__all__ = [
    "NormalizedQuantity", "UnitDimensionError", "UnitNonFiniteError",
    "UnitNormalizationError", "UnitParseError", "normalize_quantity",
    "parse_scalar", "parse_vector",
]
