from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import sympy as sp


@dataclass
class EquationSystem:
    equations: list
    unknowns: list
    substitutions: dict = field(default_factory=dict)

    def solve(self) -> list[dict]:
        eqs = [eq.subs(self.substitutions) if hasattr(eq, "subs") else eq for eq in self.equations]
        raw = sp.solve(eqs, self.unknowns, dict=True)
        return filter_physical_solutions(raw)


def _physical_value(v: Any) -> float | None:
    try:
        if getattr(v, "is_real", None) is False:
            return None
        return float(sp.N(v))
    except Exception:
        return None


def filter_physical_solutions(raw: list[dict]) -> list[dict]:
    filtered = []
    for sol in raw:
        ok = True
        for sym, val in sol.items():
            name = str(sym)
            fv = _physical_value(val)
            if fv is None:
                ok = False
                break
            if name in {"t", "time", "T", "T1", "T2", "m", "m1", "m2", "R", "I", "k"} and fv < -1e-10:
                ok = False
                break
            if name in {"v", "speed"} and fv < -1e-10:
                ok = False
                break
        if ok:
            filtered.append(sol)
    return filtered
