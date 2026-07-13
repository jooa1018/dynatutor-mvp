from __future__ import annotations

"""Typed, applicability-aware physics invariant validation.

Invariant checks are deliberately conservative: they only consume canonical
facts and semantically identified solver outputs.  They never invent a zero,
a unit mass, a gravity constant, or a direction in order to make a check run.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Callable, Iterable, Mapping, Sequence

from engine.models import AnswerItem, CanonicalProblem, SolverResult
from engine.physics_core.units import magnitude_si
from engine.verification.policy import DEFAULT_TOLERANCE_POLICY, TolerancePolicy
from engine.verification.residuals import run_residual_checks


class InvariantStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class InvariantCheck:
    check_id: str
    validator_id: str
    status: InvariantStatus
    message: str
    observed: Any = None
    expected: Any = None
    absolute_error: float | None = None
    relative_error: float | None = None
    tolerance: float | None = None
    evidence: tuple[str, ...] = ()
    source_equation_ids: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status is InvariantStatus.PASSED

    @property
    def blocking(self) -> bool:
        return self.status is InvariantStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "validator_id": self.validator_id,
            "status": self.status.value,
            "message": self.message,
            "observed": self.observed,
            "expected": self.expected,
            "absolute_error": self.absolute_error,
            "relative_error": self.relative_error,
            "tolerance": self.tolerance,
            "evidence": list(self.evidence),
            "source_equation_ids": list(self.source_equation_ids),
        }


@dataclass(frozen=True)
class InvariantContext:
    canonical: CanonicalProblem
    result: SolverResult
    answer_pool: Mapping[str, float] = field(default_factory=dict)
    policy: TolerancePolicy = field(default_factory=lambda: DEFAULT_TOLERANCE_POLICY)
    engine_id: str | None = None


InvariantEvaluator = Callable[[InvariantContext], list[InvariantCheck]]


_AMBIGUOUS_SYMBOLS = frozenset({"T", "f", "omega", "ω"})
_CONSERVATION_VALIDATORS = frozenset(
    {"collision_momentum", "collision_restitution", "work_energy"}
)


def _tolerance_category(validator_id: str) -> str:
    if validator_id == "equation_residual":
        return "residual"
    if validator_id in _CONSERVATION_VALIDATORS:
        return "conservation"
    return "constraint"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _known(cp: CanonicalProblem, symbols: Sequence[str], unit: str) -> float | None:
    for symbol in symbols:
        quantity = cp.knowns.get(symbol)
        if quantity is None or quantity.value is None:
            continue
        try:
            value = float(magnitude_si(quantity, unit))
        except Exception:
            continue
        if math.isfinite(value):
            return value
    return None


def _answer_items(ctx: InvariantContext) -> list[AnswerItem]:
    items = list(ctx.result.answers or [])
    representative = ctx.result.answer
    if representative is not None and not any(item is representative for item in items):
        items.append(representative)
    return items


def _ambiguous_output_key(
    canonical: CanonicalProblem,
    symbol: str,
) -> tuple[str, str] | None:
    """Return ``(required_output_key, residual_pool_symbol)`` when unambiguous.

    Raw legacy ``answer_pool`` entries never reach this function and remain
    excluded.  A colliding symbol is reconstructed only from a typed
    ``AnswerItem`` and only when the active physical model fixes its meaning.
    """

    system_type = canonical.system_type
    if system_type == "spring_mass_vibration":
        return {
            "T": ("period", "T"),
            "f": ("frequency", "f"),
            "omega": ("angular_frequency", "omega"),
            "ω": ("angular_frequency", "omega"),
        }.get(symbol)
    if symbol == "T" and system_type in {
        "pulley_atwood",
        "pulley_table_hanging",
        "pulley_incline_hanging",
        "massive_pulley_atwood",
        "vertical_circle",
    }:
        return "tension", "T"
    if symbol == "f" and system_type in {
        "particle_on_incline",
        "pulley_table_hanging",
        "pulley_incline_hanging",
        "horizontal_friction_force",
        "flat_curve_friction",
    }:
        return "friction_force", "f"
    if symbol in {"omega", "ω"} and system_type in {
        "fixed_axis_rotation",
        "instant_center_velocity",
        "pure_rolling_energy",
        "rolling_energy_general",
        "polar_kinematics",
        "slot_pin_relative_motion",
        "coriolis_relative_motion",
        "plane_rigid_body_velocity",
        "plane_rigid_body_acceleration",
    }:
        return "angular_velocity", "omega"
    return None


def _semantic_values(
    ctx: InvariantContext,
    output_key: str,
    *,
    safe_symbols: Sequence[str] = (),
) -> list[tuple[str, float]]:
    """Return actual outputs without guessing the meaning of T/f/omega.

    ``output_key`` is authoritative.  Symbol fallback is only available for
    explicitly supplied, unambiguous symbols.  A legacy representative answer
    is usable only when the canonical request contains exactly one semantic
    output, which is the same compatibility contract used by Phase 47.
    """

    found: list[tuple[str, float]] = []
    for item in _answer_items(ctx):
        if item.output_key != output_key:
            continue
        value = _finite(item.numeric)
        if value is not None:
            found.append((item.symbol or output_key, value))
    if found:
        return found

    allowed_symbols = set(safe_symbols) - _AMBIGUOUS_SYMBOLS
    if allowed_symbols:
        for item in _answer_items(ctx):
            if item.symbol not in allowed_symbols:
                continue
            value = _finite(item.numeric)
            if value is not None:
                found.append((item.symbol or output_key, value))
    if found:
        return found

    requested = [
        value
        for value in (ctx.canonical.requested_outputs or [])
        if value and value != "auto"
    ]
    representative = ctx.result.answer
    if (
        len(requested) == 1
        and requested[0] == output_key
        and representative is not None
    ):
        value = _finite(representative.numeric)
        if value is not None:
            return [(output_key, value)]
    return []


def _symbol_values(
    ctx: InvariantContext, symbols: Sequence[str]
) -> list[tuple[str, float]]:
    wanted = set(symbols) - _AMBIGUOUS_SYMBOLS
    found: list[tuple[str, float]] = []
    for item in _answer_items(ctx):
        if item.symbol not in wanted:
            continue
        value = _finite(item.numeric)
        if value is not None:
            found.append((item.symbol or "answer", value))
    for symbol in wanted:
        value = _finite(ctx.answer_pool.get(symbol))
        if value is not None and not any(name == symbol for name, _ in found):
            found.append((symbol, value))
    return found


def _one(values: Sequence[tuple[str, float]]) -> float | None:
    return values[0][1] if len(values) == 1 else None


def _status_check(
    validator_id: str,
    status: InvariantStatus,
    message: str,
    *,
    suffix: str = "applicability",
    observed: Any = None,
    expected: Any = None,
    evidence: Iterable[str] = (),
    equations: Iterable[str] = (),
) -> InvariantCheck:
    return InvariantCheck(
        check_id=f"{validator_id}:{suffix}",
        validator_id=validator_id,
        status=status,
        message=message,
        observed=observed,
        expected=expected,
        evidence=tuple(evidence),
        source_equation_ids=tuple(equations),
    )


def _residual_check(
    ctx: InvariantContext,
    validator_id: str,
    suffix: str,
    message: str,
    residual: float,
    scale: float,
    *,
    expected: Any = 0.0,
    equations: Iterable[str] = (),
    evidence: Iterable[str] = (),
) -> InvariantCheck:
    scale = max(abs(float(scale)), 1.0)
    tolerance = ctx.policy.tolerance(
        _tolerance_category(validator_id),
        scale=scale,
        engine_id=ctx.engine_id,
    )
    absolute_error = abs(float(residual))
    return InvariantCheck(
        check_id=f"{validator_id}:{suffix}",
        validator_id=validator_id,
        status=(
            InvariantStatus.PASSED
            if absolute_error <= tolerance
            else InvariantStatus.FAILED
        ),
        message=message,
        observed=residual,
        expected=expected,
        absolute_error=absolute_error,
        relative_error=absolute_error / scale,
        tolerance=tolerance,
        evidence=tuple(evidence),
        source_equation_ids=tuple(equations),
    )


def governing_equation_residual(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "equation_residual"
    # A legacy pool is symbol-only.  Strip the collision-prone aliases before
    # rebuilding them from semantically typed AnswerItems below.
    pool = {
        symbol: value
        for symbol, value in ctx.answer_pool.items()
        if symbol not in _AMBIGUOUS_SYMBOLS
    }
    for item in _answer_items(ctx):
        value = _finite(item.numeric)
        symbol = item.symbol or ""
        if symbol in _AMBIGUOUS_SYMBOLS:
            semantic = _ambiguous_output_key(ctx.canonical, symbol)
            if semantic is None or value is None:
                continue
            required_output_key, pool_symbol = semantic
            if item.output_key != required_output_key:
                continue
            pool.setdefault(pool_symbol, value)
        elif symbol and value is not None:
            pool.setdefault(symbol, value)
    display = ctx.result.answer.display if ctx.result.answer else None
    residuals, supported = run_residual_checks(ctx.canonical, pool, display)
    if not supported:
        return [
            _status_check(
                validator_id,
                InvariantStatus.NOT_APPLICABLE,
                f"no governing residual adapter for {ctx.canonical.system_type}",
            )
        ]
    if not residuals:
        return [
            _status_check(
                validator_id,
                InvariantStatus.INCONCLUSIVE,
                "governing residual is applicable but required actual values are absent",
            )
        ]
    checks: list[InvariantCheck] = []
    for index, residual in enumerate(residuals):
        checks.append(
            _residual_check(
                ctx,
                validator_id,
                str(index),
                residual.describe(),
                residual.residual,
                residual.scale,
                equations=[residual.name],
            )
        )
    return checks


_PULLEY_TYPES = frozenset(
    {
        "pulley_atwood",
        "pulley_table_hanging",
        "pulley_incline_hanging",
        "massive_pulley_atwood",
    }
)


def string_constraint(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "string_constraint"
    if ctx.canonical.system_type not in _PULLEY_TYPES:
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "no string constraint in this model")]
    a1 = _one(_symbol_values(ctx, ("a1", "a_1")))
    a2 = _one(_symbol_values(ctx, ("a2", "a_2")))
    v1 = _one(_symbol_values(ctx, ("v1_string", "v_1_string")))
    v2 = _one(_symbol_values(ctx, ("v2_string", "v_2_string")))
    if a1 is not None and a2 is not None:
        return [
            _residual_check(
                ctx,
                validator_id,
                "acceleration",
                "inextensible string requires equal endpoint acceleration magnitudes",
                abs(a1) - abs(a2),
                max(abs(a1), abs(a2)),
                equations=["|a_1|=|a_2|"],
            )
        ]
    if v1 is not None and v2 is not None:
        return [
            _residual_check(
                ctx,
                validator_id,
                "velocity",
                "inextensible string requires equal endpoint speed magnitudes",
                abs(v1) - abs(v2),
                max(abs(v1), abs(v2)),
                equations=["|v_1|=|v_2|"],
            )
        ]
    return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "string model applies, but two actual endpoint velocities/accelerations were not published")]


def pure_rolling(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "pure_rolling"
    if ctx.canonical.system_type not in {"pure_rolling_energy", "rolling_energy_general"}:
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "pure rolling is not part of this model")]
    velocity = _one(_semantic_values(ctx, "final_velocity", safe_symbols=("v", "v_f", "vf")))
    omega = _one(_semantic_values(ctx, "angular_velocity"))
    radius = _known(ctx.canonical, ("R", "r"), "m")
    if velocity is None or omega is None or radius is None:
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "v=omega*R applies, but actual v, semantic angular_velocity, and R are not all available")]
    return [
        _residual_check(
            ctx,
            validator_id,
            "no_slip",
            "pure rolling no-slip condition",
            abs(velocity) - abs(omega) * radius,
            max(abs(velocity), abs(omega * radius)),
            equations=["|v_CM|=|omega|R"],
        )
    ]


def _collision_outputs(ctx: InvariantContext) -> tuple[float | None, float | None]:
    common = _one(
        _semantic_values(
            ctx,
            "post_collision_velocity",
            safe_symbols=("v_f", "vf"),
        )
    )
    if common is not None:
        return common, common
    v1_after = _one(
        _semantic_values(ctx, "v1_after", safe_symbols=("v1'", "v1p", "v1f"))
    )
    v2_after = _one(
        _semantic_values(ctx, "v2_after", safe_symbols=("v2'", "v2p", "v2f"))
    )
    return v1_after, v2_after


def collision_momentum(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "collision_momentum"
    if ctx.canonical.system_type != "collision_1d":
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "not a one-dimensional collision")]
    m1 = _known(ctx.canonical, ("m1",), "kg")
    m2 = _known(ctx.canonical, ("m2",), "kg")
    v1 = _known(ctx.canonical, ("v1",), "m/s")
    v2 = _known(ctx.canonical, ("v2",), "m/s")
    v1_after, v2_after = _collision_outputs(ctx)
    if None in (m1, m2, v1, v2, v1_after, v2_after):
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "momentum invariant applies, but masses or signed before/after velocities are absent")]
    before = m1 * v1 + m2 * v2
    after = m1 * v1_after + m2 * v2_after
    return [
        _residual_check(
            ctx,
            validator_id,
            "linear",
            "one-dimensional linear momentum conservation",
            after - before,
            max(abs(before), abs(after)),
            equations=["m1*v1+m2*v2=m1*v1_after+m2*v2_after"],
        )
    ]


def collision_restitution(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "collision_restitution"
    if ctx.canonical.system_type != "collision_1d":
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "not a one-dimensional collision")]
    e = _known(ctx.canonical, ("e",), "")
    if e is None and (ctx.canonical.flags or {}).get("elastic"):
        e = 1.0
    if e is None and (ctx.canonical.flags or {}).get("perfectly_inelastic"):
        e = 0.0
    v1 = _known(ctx.canonical, ("v1",), "m/s")
    v2 = _known(ctx.canonical, ("v2",), "m/s")
    v1_after, v2_after = _collision_outputs(ctx)
    if None in (e, v1, v2, v1_after, v2_after):
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "restitution relation applies, but e or signed before/after velocities are absent")]
    separation = v2_after - v1_after
    expected = e * (v1 - v2)
    return [
        _residual_check(
            ctx,
            validator_id,
            "relative_velocity",
            "coefficient-of-restitution relative-velocity relation",
            separation - expected,
            max(abs(separation), abs(expected)),
            equations=["v2_after-v1_after=e*(v1-v2)"],
        )
    ]


def work_energy(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "work_energy"
    if ctx.canonical.system_type != "work_energy_speed":
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "not a work-energy speed model")]
    mass = _known(ctx.canonical, ("m",), "kg")
    initial = _known(ctx.canonical, ("v0",), "m/s")
    work = _known(ctx.canonical, ("W",), "J")
    if work is None:
        work = _one(_semantic_values(ctx, "work", safe_symbols=("W",)))
    final = _one(_semantic_values(ctx, "final_velocity", safe_symbols=("v_f", "vf", "v")))
    if None in (mass, initial, work, final):
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "Delta-K=W applies, but explicit m, v0, W, and final_velocity are not all available")]
    delta_k = 0.5 * mass * (final * final - initial * initial)
    return [
        _residual_check(
            ctx,
            validator_id,
            "delta_k",
            "net work equals the change in kinetic energy",
            delta_k - work,
            max(abs(delta_k), abs(work)),
            equations=["W_net=0.5*m*(v_f^2-v_0^2)"],
        )
    ]


_CONTACT_TYPES = frozenset(
    {
        "particle_on_incline",
        "horizontal_friction_force",
        "flat_curve_friction",
        "banked_curve_no_friction",
        "vertical_circle",
        "pure_rolling_energy",
        "rolling_energy_general",
    }
)


def contact_normal(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "contact_normal"
    if ctx.canonical.system_type not in _CONTACT_TYPES:
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "model has no unilateral normal-contact constraint")]
    normals = _semantic_values(ctx, "normal_force", safe_symbols=("N", "N1", "N2"))
    if not normals:
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "contact model applies, but no actual normal_force output is available")]
    checks: list[InvariantCheck] = []
    for symbol, value in normals:
        checks.append(
            _residual_check(
                ctx,
                validator_id,
                symbol,
                f"unilateral contact requires {symbol} >= 0",
                min(value, 0.0),
                max(abs(value), 1.0),
                expected=">= 0",
                equations=[f"{symbol}>=0"],
            )
        )
    return checks


def tension_slack(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "tension_slack"
    if ctx.canonical.system_type not in _PULLEY_TYPES | {"vertical_circle"}:
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "model has no unilateral string-tension constraint")]
    tensions = _semantic_values(ctx, "tension", safe_symbols=("T1", "T2"))
    if not tensions:
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "string model applies, but no semantic tension output is available; bare T is intentionally not guessed")]
    checks: list[InvariantCheck] = []
    for symbol, value in tensions:
        checks.append(
            _residual_check(
                ctx,
                validator_id,
                symbol,
                f"taut string requires {symbol} >= 0; a negative value means slack/contact transition",
                min(value, 0.0),
                max(abs(value), 1.0),
                expected=">= 0",
                equations=[f"{symbol}>=0"],
            )
        )
    return checks


_FRICTION_TYPES = frozenset(
    {
        "particle_on_incline",
        "pulley_table_hanging",
        "pulley_incline_hanging",
        "horizontal_friction_force",
        "flat_curve_friction",
    }
)


def friction_regime(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "friction_regime"
    if ctx.canonical.system_type not in _FRICTION_TYPES:
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "friction regime is not part of this model")]
    frictions = _semantic_values(ctx, "friction_force", safe_symbols=("f_s", "f_s,max", "f_k", "F_f"))
    if not frictions:
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "friction model applies, but no semantic friction_force output is available; bare f is intentionally not guessed")]
    normal = _one(_semantic_values(ctx, "normal_force", safe_symbols=("N",)))
    if normal is None:
        normal = _known(ctx.canonical, ("N",), "N")
    if normal is None:
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "friction output exists, but actual normal force is unavailable")]

    regime = (ctx.canonical.friction_type or "").lower()
    symbols = {symbol for symbol, _ in frictions}
    if not regime:
        if any(symbol.startswith("f_s") for symbol in symbols):
            regime = "static"
        elif "f_k" in symbols:
            regime = "kinetic"
    if regime in {"static", "정지", "static_friction"}:
        coefficient = _known(ctx.canonical, ("mu_s", "mu"), "")
        if coefficient is None:
            return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "static friction requires an explicit mu_s (or regime-bound mu)")]
        checks: list[InvariantCheck] = []
        limit = coefficient * normal
        for symbol, value in frictions:
            violation = max(0.0, abs(value) - limit)
            checks.append(
                _residual_check(
                    ctx,
                    validator_id,
                    symbol,
                    "actual static friction must not exceed mu_s*N",
                    violation,
                    max(abs(value), abs(limit)),
                    expected=f"|{symbol}| <= mu_s*N",
                    equations=["|f_s|<=mu_s*N"],
                )
            )
        return checks
    if regime in {"kinetic", "운동", "kinetic_friction"}:
        coefficient = _known(ctx.canonical, ("mu_k", "mu"), "")
        if coefficient is None:
            return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "kinetic friction requires an explicit mu_k (or regime-bound mu)")]
        expected_magnitude = coefficient * normal
        return [
            _residual_check(
                ctx,
                validator_id,
                symbol,
                "kinetic friction magnitude must equal mu_k*N",
                abs(value) - expected_magnitude,
                max(abs(value), abs(expected_magnitude)),
                equations=["|f_k|=mu_k*N"],
            )
            for symbol, value in frictions
        ]
    return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "friction force is available, but the static/kinetic regime is not explicit")]


def pulley_no_slip(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "pulley_no_slip"
    if ctx.canonical.system_type != "massive_pulley_atwood":
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "rotating massive-pulley no-slip constraint is absent")]
    acceleration = _one(_semantic_values(ctx, "acceleration", safe_symbols=("a",)))
    angular_acceleration = _one(_semantic_values(ctx, "angular_acceleration", safe_symbols=("alpha", "α")))
    radius = _known(ctx.canonical, ("Rp", "R"), "m")
    if None in (acceleration, angular_acceleration, radius):
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "a=alpha*R applies, but actual acceleration, angular_acceleration, and R are not all available")]
    return [
        _residual_check(
            ctx,
            validator_id,
            "acceleration",
            "string/pulley no-slip acceleration constraint",
            abs(acceleration) - abs(angular_acceleration) * radius,
            max(abs(acceleration), abs(angular_acceleration * radius)),
            equations=["|a|=|alpha|R"],
        )
    ]


def _coordinate_pair(cp: CanonicalProblem, prefix: str, unit: str) -> tuple[float, float] | None:
    x_key, y_key = f"{prefix}x", f"{prefix}y"
    data = cp.coordinate_data or {}
    if x_key in data and y_key in data:
        x, y = _finite(data[x_key]), _finite(data[y_key])
        if x is not None and y is not None:
            return x, y
    x = _known(cp, (x_key,), unit)
    y = _known(cp, (y_key,), unit)
    return (x, y) if x is not None and y is not None else None


def _fixed_reference(cp: CanonicalProblem, kind: str, unit: str) -> tuple[float, float] | None:
    pair = _coordinate_pair(cp, f"{kind}A", unit)
    if pair is not None:
        return pair
    scalar = _known(cp, (f"{kind}A",), unit)
    fixed = any(
        phrase in (cp.raw_text or "")
        for phrase in ("고정점", "A점이 고정", "A점은 고정", "A점 고정", "A is fixed")
    )
    if fixed or (scalar is not None and abs(scalar) <= 1e-12):
        return 0.0, 0.0
    return None


def rigid_relative_velocity(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "rigid_relative_velocity"
    if ctx.canonical.system_type != "plane_rigid_body_velocity":
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "not a plane rigid-body velocity model")]
    reference = _fixed_reference(ctx.canonical, "v", "m/s")
    radius = _coordinate_pair(ctx.canonical, "rBA", "m")
    omega = _known(ctx.canonical, ("omega",), "rad/s")
    sign = (ctx.canonical.coordinate_data or {}).get("omega_sign")
    if sign is None:
        sign = (ctx.canonical.coordinate_data or {}).get("angular_sign")
    vx = _one(_symbol_values(ctx, ("v_Bx",)))
    vy = _one(_symbol_values(ctx, ("v_By",)))
    if reference is None or radius is None or omega is None or sign not in (-1, 1) or (vx is None and vy is None):
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "v_B=v_A+omega cross r applies, but reference/radius vector, signed omega, or output components are absent")]
    vax, vay = reference
    rx, ry = radius
    signed_omega = float(sign) * abs(omega)
    expected_x = vax - signed_omega * ry
    expected_y = vay + signed_omega * rx
    checks: list[InvariantCheck] = []
    if vx is not None:
        checks.append(_residual_check(ctx, validator_id, "x", "rigid-body relative velocity x component", vx - expected_x, max(abs(vx), abs(expected_x)), equations=["v_Bx=v_Ax-omega*r_y"]))
    if vy is not None:
        checks.append(_residual_check(ctx, validator_id, "y", "rigid-body relative velocity y component", vy - expected_y, max(abs(vy), abs(expected_y)), equations=["v_By=v_Ay+omega*r_x"]))
    return checks


def rigid_relative_acceleration(ctx: InvariantContext) -> list[InvariantCheck]:
    validator_id = "rigid_relative_acceleration"
    if ctx.canonical.system_type != "plane_rigid_body_acceleration":
        return [_status_check(validator_id, InvariantStatus.NOT_APPLICABLE, "not a plane rigid-body acceleration model")]
    reference = _fixed_reference(ctx.canonical, "a", "m/s^2")
    radius = _coordinate_pair(ctx.canonical, "rBA", "m")
    omega = _known(ctx.canonical, ("omega",), "rad/s")
    alpha = _known(ctx.canonical, ("alpha",), "rad/s^2")
    data = ctx.canonical.coordinate_data or {}
    omega_sign = data.get("omega_sign", data.get("angular_sign"))
    alpha_sign = data.get("alpha_sign", data.get("angular_sign"))
    ax = _one(_symbol_values(ctx, ("a_Bx",)))
    ay = _one(_symbol_values(ctx, ("a_By",)))
    if reference is None or radius is None or omega is None or alpha is None or omega_sign not in (-1, 1) or alpha_sign not in (-1, 1) or (ax is None and ay is None):
        return [_status_check(validator_id, InvariantStatus.INCONCLUSIVE, "a_B=a_A+alpha cross r+omega cross (omega cross r) applies, but signed angular data, vectors, or output components are absent")]
    aax, aay = reference
    rx, ry = radius
    signed_omega = float(omega_sign) * abs(omega)
    signed_alpha = float(alpha_sign) * abs(alpha)
    expected_x = aax - signed_alpha * ry - signed_omega * signed_omega * rx
    expected_y = aay + signed_alpha * rx - signed_omega * signed_omega * ry
    checks: list[InvariantCheck] = []
    if ax is not None:
        checks.append(_residual_check(ctx, validator_id, "x", "rigid-body relative acceleration x component", ax - expected_x, max(abs(ax), abs(expected_x)), equations=["a_Bx=a_Ax-alpha*r_y-omega^2*r_x"]))
    if ay is not None:
        checks.append(_residual_check(ctx, validator_id, "y", "rigid-body relative acceleration y component", ay - expected_y, max(abs(ay), abs(expected_y)), equations=["a_By=a_Ay+alpha*r_x-omega^2*r_y"]))
    return checks


INVARIANT_EVALUATORS: Mapping[str, InvariantEvaluator] = {
    "equation_residual": governing_equation_residual,
    "string_constraint": string_constraint,
    "pure_rolling": pure_rolling,
    "collision_momentum": collision_momentum,
    "collision_restitution": collision_restitution,
    "work_energy": work_energy,
    "contact_normal": contact_normal,
    "tension_slack": tension_slack,
    "friction_regime": friction_regime,
    "pulley_no_slip": pulley_no_slip,
    "rigid_relative_velocity": rigid_relative_velocity,
    "rigid_relative_acceleration": rigid_relative_acceleration,
}


def evaluate_invariants(
    canonical: CanonicalProblem,
    result: SolverResult,
    *,
    validator_ids: Iterable[str] | None = None,
    answer_pool: Mapping[str, float] | None = None,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
    engine_id: str | None = None,
) -> list[InvariantCheck]:
    requested = list(validator_ids or INVARIANT_EVALUATORS)
    unknown = sorted(set(requested) - set(INVARIANT_EVALUATORS))
    if unknown:
        raise ValueError("unknown invariant validator IDs: " + ", ".join(unknown))
    context = InvariantContext(
        canonical=canonical,
        result=result,
        answer_pool=dict(answer_pool or {}),
        policy=policy,
        engine_id=engine_id,
    )
    checks: list[InvariantCheck] = []
    for validator_id in requested:
        checks.extend(INVARIANT_EVALUATORS[validator_id](context))
    return checks


__all__ = [
    "INVARIANT_EVALUATORS",
    "InvariantCheck",
    "InvariantContext",
    "InvariantEvaluator",
    "InvariantStatus",
    "evaluate_invariants",
]
