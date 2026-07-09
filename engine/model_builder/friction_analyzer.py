from __future__ import annotations

import math
from dataclasses import asdict

from engine.models import CanonicalProblem
from engine.physics_core.friction import (
    decide_incline_static,
    decide_incline_hanging_static,
    decide_table_hanging_static,
)
from engine.physics_core.units import magnitude_si


def _q(c: CanonicalProblem, key: str, unit: str) -> float | None:
    if key not in c.knowns:
        return None
    try:
        return magnitude_si(c.knowns[key], unit)
    except Exception:
        return c.knowns[key].value


def build_friction_decisions(c: CanonicalProblem) -> list[dict]:
    """Return human/audit-facing friction decisions.

    These are not just descriptions; solvers also use the same physical criteria
    in Phase 16 to avoid solving static-friction problems as kinetic motion.
    """
    decisions: list[dict] = []
    if c.friction_type != "static":
        return decisions

    g = _q(c, "g", "m/s^2") or 9.81
    mu_s = c.knowns.get("mu_s") or c.knowns.get("mu")
    if not mu_s or mu_s.value is None:
        return decisions
    mu_s_val = float(mu_s.value)

    if c.system_type == "particle_on_incline" and "theta" in c.knowns:
        theta = math.radians(magnitude_si(c.knowns["theta"], "deg"))
        mass = _q(c, "m", "kg")
        decisions.append(asdict(decide_incline_static(theta, mu_s_val, mass=mass, g=g)))
    elif c.system_type == "pulley_table_hanging" and "m1" in c.knowns and "m2" in c.knowns:
        decisions.append(asdict(decide_table_hanging_static(_q(c, "m1", "kg"), _q(c, "m2", "kg"), mu_s_val, g=g)))
    elif c.system_type == "pulley_incline_hanging" and all(k in c.knowns for k in ["m1", "m2", "theta"]):
        theta = math.radians(magnitude_si(c.knowns["theta"], "deg"))
        decisions.append(asdict(decide_incline_hanging_static(_q(c, "m1", "kg"), _q(c, "m2", "kg"), theta, mu_s_val, g=g)))

    return decisions
