from __future__ import annotations

from typing import Any
try:
    from pint import UnitRegistry, DimensionalityError
except ModuleNotFoundError:  # offline/test harness fallback; production requirements still install pint
    from tools._pint_shim import UnitRegistry, DimensionalityError

from engine.models import Quantity

ureg = UnitRegistry()
Q_ = ureg.Quantity

_UNIT_ALIASES = {
    None: "",
    "": "",
    "m/s²": "meter/second**2",
    "m/s^2": "meter/second**2",
    "m/s2": "meter/second**2",
    "m/s": "meter/second",
    "cm/s2": "centimeter/second**2",
    "cm/s²": "centimeter/second**2",
    "cm/s^2": "centimeter/second**2",
    "km/hr": "kilometer/hour",
    "kmph": "kilometer/hour",
    "km/h": "kilometer/hour",
    "kg": "kilogram",
    "g": "gram",
    "m": "meter",
    "cm": "centimeter",
    "mm": "millimeter",
    "km": "kilometer",
    "s": "second",
    "min": "minute",
    "N": "newton",
    "J": "joule",
    "N*m": "newton*meter",
    "Nm": "newton*meter",
    "N/m": "newton/meter",
    "kg*m^2": "kilogram*meter**2",
    "kgm^2": "kilogram*meter**2",
    "rad/s": "radian/second",
    "rad/s^2": "radian/second**2",
    "rad/s²": "radian/second**2",
    "rad/s2": "radian/second**2",
    "N·s": "newton*second",
    "N*s": "newton*second",
    "N·m": "newton*meter",
    "kg·m^2": "kilogram*meter**2",
    "kg·m²": "kilogram*meter**2",
    "kg*m²": "kilogram*meter**2",
    "deg": "degree",
    "rad": "radian",
}

_EXPECTED_DIMS = {
    "mass": "[mass]",
    "length": "[length]",
    "time": "[time]",
    "velocity": "[length] / [time]",
    "acceleration": "[length] / [time] ** 2",
    "force": "[mass] * [length] / [time] ** 2",
    "work": "[mass] * [length] ** 2 / [time] ** 2",
    "energy": "[mass] * [length] ** 2 / [time] ** 2",
    "torque": "[mass] * [length] ** 2 / [time] ** 2",
    "inertia": "[mass] * [length] ** 2",
    "stiffness": "[mass] / [time] ** 2",
    "dimensionless": "dimensionless",
}


def _unit(unit: str | None) -> str:
    return _UNIT_ALIASES.get(unit, unit or "")


def to_pint(quantity: Quantity | float | int | Any):
    if hasattr(quantity, "to") and hasattr(quantity, "dimensionality"):
        return quantity
    if isinstance(quantity, Quantity):
        if quantity.value is None:
            raise ValueError(f"{quantity.symbol} has no numeric value")
        return Q_(quantity.value, _unit(quantity.unit))
    if isinstance(quantity, (int, float)):
        return Q_(quantity, "")
    raise TypeError(f"Unsupported quantity type: {type(quantity)!r}")


def to_si(quantity: Quantity | Any, target_unit: str):
    q = to_pint(quantity)
    try:
        return q.to(_unit(target_unit))
    except DimensionalityError as e:
        raise ValueError(f"단위 차원이 맞지 않습니다: {q} -> {target_unit}") from e


def assert_dimension(pint_quantity, expected_dim: str):
    q = to_pint(pint_quantity)
    dim = _EXPECTED_DIMS.get(expected_dim, expected_dim)
    if dim == "dimensionless":
        if q.dimensionality:
            raise ValueError(f"Expected dimensionless, got {q.dimensionality}")
        return True
    try:
        # Pint dimensionality equality with parsed unit.
        target = Q_(1, dim)
        if q.dimensionality != target.dimensionality:
            raise ValueError(f"Expected {dim}, got {q.dimensionality}")
    except Exception:
        # Fallback for string dimensionalities.
        if str(q.dimensionality) != dim:
            raise ValueError(f"Expected {dim}, got {q.dimensionality}")
    return True


def magnitude_si(quantity: Quantity | Any, target_unit: str) -> float:
    return float(to_si(quantity, target_unit).magnitude)


def make_quantity(value: float, unit: str, symbol: str = "") -> Quantity:
    q = Q_(value, _unit(unit)).to(_unit(unit))
    return Quantity(symbol=symbol, value=float(q.magnitude), unit=unit, source_text=f"{value} {unit}")


def angle_to_radians(quantity: Quantity | Any) -> float:
    """Convert an explicitly-unitized dimensionless angle to radians."""

    q = to_pint(quantity)
    assert_dimension(q, "dimensionless")
    try:
        return float(q.to("radian").magnitude)
    except (DimensionalityError, ValueError) as exc:
        raise ValueError(f"각도를 radian으로 변환할 수 없습니다: {q}") from exc


def radians_to_degrees(value: float) -> float:
    """Explicit display conversion; internal angular calculations use radians."""

    return float(Q_(value, "radian").to("degree").magnitude)
