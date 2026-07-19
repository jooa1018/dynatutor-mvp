"""Minimal pint stand-in for offline harness runs.

Implements ONLY what the bounded physics_core/mechanics unit adapters touch:
  - UnitRegistry().Quantity(value, unit_str)
  - Quantity.to(unit_str), .magnitude, .dimensionality
  - DimensionalityError

Unit strings are the normalized forms produced by units._UNIT_ALIASES
(e.g. "meter/second**2", "kilometer/hour", "newton*meter", "degree").
All factors are exact, so numeric results match real pint for these units.

This module must NEVER ship as a runtime dependency substitute — it exists so
diagnostic tooling can run in environments where pint cannot be installed.
"""
from __future__ import annotations

import math

# Seven SI base dimensions; plane angle remains dimensionless like real Pint.
_BASE = {
    "": (1.0, {}),
    "dimensionless": (1.0, {}),
    "meter": (1.0, {"L": 1}),
    "centimeter": (0.01, {"L": 1}),
    "millimeter": (0.001, {"L": 1}),
    "kilometer": (1000.0, {"L": 1}),
    "second": (1.0, {"T": 1}),
    "minute": (60.0, {"T": 1}),
    "hour": (3600.0, {"T": 1}),
    "kilogram": (1.0, {"M": 1}),
    "gram": (0.001, {"M": 1}),
    "newton": (1.0, {"M": 1, "L": 1, "T": -2}),
    "joule": (1.0, {"M": 1, "L": 2, "T": -2}),
    "radian": (1.0, {}),
    "degree": (math.pi / 180.0, {}),
    "ampere": (1.0, {"I": 1}),
    "kelvin": (1.0, {"Th": 1}),
    "mole": (1.0, {"N": 1}),
    "candela": (1.0, {"Jv": 1}),
    # 축약 토큰 (실제 pint가 아는 표기)
    "m": (1.0, {"L": 1}),
    "cm": (0.01, {"L": 1}),
    "mm": (0.001, {"L": 1}),
    "km": (1000.0, {"L": 1}),
    "s": (1.0, {"T": 1}),
    "min": (60.0, {"T": 1}),
    "h": (3600.0, {"T": 1}),
    "hr": (3600.0, {"T": 1}),
    "kg": (1.0, {"M": 1}),
    "g": (0.001, {"M": 1}),
    "mg": (1e-6, {"M": 1}),
    "N": (1.0, {"M": 1, "L": 1, "T": -2}),
    "J": (1.0, {"M": 1, "L": 2, "T": -2}),
    "rad": (1.0, {}),
    "deg": (math.pi / 180.0, {}),
    "A": (1.0, {"I": 1}),
    "K": (1.0, {"Th": 1}),
    "mol": (1.0, {"N": 1}),
    "cd": (1.0, {"Jv": 1}),
}


class DimensionalityError(ValueError):
    def __init__(self, units1="", units2="", dim1="", dim2="", extra_msg=""):
        super().__init__(f"Cannot convert {units1} ({dim1}) to {units2} ({dim2}) {extra_msg}")


def _merge(dims: dict, other: dict, sign: int) -> None:
    for k, v in other.items():
        dims[k] = dims.get(k, 0) + sign * v
        if dims[k] == 0:
            del dims[k]


def _parse_unit(unit: str) -> tuple[float, dict]:
    unit = (unit or "").strip()
    if unit in _BASE:
        return _BASE[unit]
    # bracket dimension strings like "[mass] * [length] / [time] ** 2"
    if "[" in unit:
        return _parse_bracket_dims(unit)
    factor, dims = 1.0, {}
    # split into numerator/denominator by '/'; normalize '**'→'^' FIRST so the
    # '*' split cannot destroy exponents ("second**2".split("*") == ['second','','2']).
    parts = unit.replace("**", "^").split("/")
    for pi, part in enumerate(parts):
        sign = 1 if pi == 0 else -1
        for token in part.split("*"):
            token = token.strip()
            if not token:
                continue
            power = 1
            if "^" in token:
                token, p = token.split("^")
                token, power = token.strip(), int(p.strip())
            if token not in _BASE:
                raise DimensionalityError(unit, extra_msg=f"unknown unit token {token!r}")
            f, d = _BASE[token]
            factor *= f ** (sign * power)
            _merge(dims, {k: v * power for k, v in d.items()}, sign)
    return factor, dims


_BRACKET = {"[mass]": {"M": 1}, "[length]": {"L": 1}, "[time]": {"T": 1}}


def _parse_bracket_dims(expr: str) -> tuple[float, dict]:
    dims: dict = {}
    for pi, part in enumerate(expr.split("/")):
        sign = 1 if pi == 0 else -1
        for token in part.split("*"):
            token = token.strip()
            if not token:
                continue
            power = 1
            if token.isdigit():  # came from "** 2" split on '*'
                # previous token already merged with power 1; adjust:
                # handled below via two-pass, so raise instead
                raise DimensionalityError(expr, extra_msg="unexpected bare power")
            if token not in _BRACKET:
                raise DimensionalityError(expr, extra_msg=f"unknown dim token {token!r}")
            _merge(dims, {k: v * power for k, v in _BRACKET[token].items()}, sign)
    return 1.0, dims


def _parse_dim_expr(expr: str) -> dict:
    """Parse '[mass] * [length] / [time] ** 2' handling ** powers."""
    dims: dict = {}
    num_den = expr.split("/")
    for pi, part in enumerate(num_den):
        sign = 1 if pi == 0 else -1
        # normalize '**' so it doesn't split on '*'
        part = part.replace("**", "^")
        for token in part.split("*"):
            token = token.strip()
            if not token:
                continue
            power = 1
            if "^" in token:
                token, p = token.split("^")
                token, power = token.strip(), int(p.strip())
            if token not in _BRACKET:
                raise DimensionalityError(expr, extra_msg=f"unknown dim token {token!r}")
            _merge(dims, {k: v * power for k, v in _BRACKET[token].items()}, sign)
    return dims


class _Dimensionality(dict):
    def __bool__(self) -> bool:
        return bool(len(self))

    def __str__(self) -> str:
        if not self:
            return "dimensionless"
        names = {
            "M": "[mass]", "L": "[length]", "T": "[time]",
            "I": "[current]", "Th": "[temperature]", "N": "[substance]",
            "Jv": "[luminosity]",
        }
        num = [f"{names[k]}{'' if v == 1 else f' ** {v}'}" for k, v in sorted(self.items()) if v > 0]
        den = [f"{names[k]}{'' if v == -1 else f' ** {-v}'}" for k, v in sorted(self.items()) if v < 0]
        s = " * ".join(num) if num else "1"
        return s + (" / " + " / ".join(den) if den else "")


class _Quantity:
    __slots__ = ("magnitude", "_factor", "_dims", "_unit")

    def __init__(self, value: float, unit: str = ""):
        if "[" in (unit or ""):
            self._factor, dims = 1.0, _parse_dim_expr(unit)
        else:
            self._factor, dims = _parse_unit(unit)
        self.magnitude = float(value)
        self._dims = _Dimensionality(dims)
        self._unit = unit or ""

    @property
    def dimensionality(self) -> _Dimensionality:
        return self._dims

    def to(self, unit: str) -> "_Quantity":
        target_factor, target_dims = _parse_unit(unit)
        if _Dimensionality(target_dims) != self._dims:
            raise DimensionalityError(self._unit, unit, str(self._dims), str(_Dimensionality(target_dims)))
        out = _Quantity(self.magnitude * self._factor / target_factor, unit)
        return out

    @classmethod
    def _from_si(cls, si_value: float, dims: dict) -> "_Quantity":
        q = cls.__new__(cls)
        q.magnitude = si_value
        q._factor = 1.0
        q._dims = _Dimensionality(dims)
        q._unit = "<derived>"
        return q

    def _si(self) -> float:
        return self.magnitude * self._factor

    def __mul__(self, other):
        if isinstance(other, _Quantity):
            dims = dict(self._dims)
            _merge(dims, other._dims, +1)
            return _Quantity._from_si(self._si() * other._si(), dims)
        return _Quantity._from_si(self._si() * float(other), dict(self._dims))

    __rmul__ = __mul__

    def __truediv__(self, other):
        if isinstance(other, _Quantity):
            dims = dict(self._dims)
            _merge(dims, other._dims, -1)
            return _Quantity._from_si(self._si() / other._si(), dims)
        return _Quantity._from_si(self._si() / float(other), dict(self._dims))

    def __repr__(self) -> str:
        return f"{self.magnitude} {self._unit}"


class UnitRegistry:
    def Quantity(self, value, unit: str = ""):
        return _Quantity(value, unit)


__all__ = ["UnitRegistry", "DimensionalityError"]
