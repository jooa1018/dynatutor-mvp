from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import sympy as sp

from engine.models import CanonicalProblem, StepCard
from engine.model_builder.model_types import GeneratedEquation, GeneratedEquationSystem, PhysicalModel
from engine.physics_core import symbols as S
from engine.physics_core.equation_system import EquationSystem
from engine.physics_core.units import magnitude_si


@dataclass
class GeneratedSolve:
    ok: bool
    solution: dict[Any, Any]
    system: GeneratedEquationSystem
    errors: list[str]


def _ge(kind: str, body_id: str | None, axis: str | None, equation: str, sympy_eq: Any, *, source_forces: list[str], unknowns: list[str], notes: list[str] | None = None) -> GeneratedEquation:
    return GeneratedEquation(
        id=f"{kind}_{body_id or 'model'}_{axis or 'scalar'}",
        kind=kind,
        body_id=body_id,
        axis=axis,
        equation=equation,
        sympy_repr=str(sympy_eq) if sympy_eq is not None else None,
        source_forces=source_forces,
        unknowns=unknowns,
        notes=notes or [],
    )


def _common_subs(c: CanonicalProblem) -> dict:
    subs = {}
    for key, sym, unit in [
        ("m", S.m, "kg"),
        ("m1", S.m1, "kg"),
        ("m2", S.m2, "kg"),
        ("g", S.g, "m/s^2"),
        ("mu", S.mu, ""),
        ("mu_k", S.mu_k, ""),
        ("mu_s", S.mu_s, ""),
        ("theta", S.theta, "deg"),
        ("I", S.I, "kg*m^2"),
        ("R", S.R, "m"),
    ]:
        # If static friction failed and a kinetic coefficient is provided, the
        # generated kinetic-motion equations should use μ_k for the generic μ.
        if key == "mu" and c.friction_type == "static" and "mu_k" in c.knowns:
            qk = c.knowns["mu_k"]
            if qk.value is not None:
                subs[S.mu] = float(qk.value)
            continue
        if key not in c.knowns:
            continue
        q = c.knowns[key]
        if q.value is None:
            continue
        if unit == "":
            subs[sym] = float(q.value)
        elif unit == "deg":
            subs[sym] = math.radians(magnitude_si(q, "deg"))
        else:
            subs[sym] = magnitude_si(q, unit)
    if S.g not in subs and "g" in c.knowns:
        subs[S.g] = c.knowns["g"].value or 9.81
    return subs


def _model_subs(c: CanonicalProblem, typed) -> dict:
    """Keep Phase 45-only aliases out of the shared legacy substitution contract."""

    subs = _common_subs(c)
    if (
        typed is not None
        and c.system_type == "particle_on_incline"
        and "mu" not in c.knowns
        and "mu_k" in c.knowns
        and c.knowns["mu_k"].value is not None
    ):
        subs[S.mu] = float(c.knowns["mu_k"].value)
    return subs


def build_particle_newton_system(c: CanonicalProblem, model: PhysicalModel | None = None) -> GeneratedEquationSystem:
    st = c.system_type
    equations: list[GeneratedEquation] = []
    unknowns: list[Any] = []
    warnings: list[str] = []
    errors: list[str] = []
    typed = getattr(model, "typed_model", None) if model is not None else None

    # Phase 15 supports translational Newton systems. Energy/momentum/rigid-body
    # generators remain separate later phases.
    if st == "particle_on_incline":
        if c.subtype == "no_friction":
            eq_y = sp.Eq(S.T - S.m * S.g * sp.cos(S.theta), 0)  # informational N balance
            eq_x = (
                sp.Eq(
                    sp.expand(typed.sum_forces("body", "incline").x / S.m),
                    S.a,
                )
                if typed is not None
                else sp.Eq(S.g * sp.sin(S.theta), S.a)
            )
            equations.append(_ge("normal_balance", "body", "y", "N - m*g*cos(theta) = 0", None, source_forces=["N", "mg cosθ"], unknowns=["N"], notes=["설명/검산용 법선방향 평형식입니다."]))
            equations.append(_ge("newton_second_law", "body", "x", "g*sin(theta) = a", eq_x, source_forces=["mg sinθ"], unknowns=["a"], notes=["질량 m이 약분된 가속도식만 solve 대상으로 사용합니다."]))
            unknowns = [S.a]
        elif c.subtype == "with_friction":
            eq_y = sp.Eq(S.T - S.m * S.g * sp.cos(S.theta), 0)  # informational N balance
            eq_f = sp.Eq(S.F, S.mu * S.T)  # informational friction law
            eq_x = (
                sp.Eq(
                    sp.expand(typed.sum_forces("body", "incline").x / S.m),
                    S.a,
                )
                if typed is not None
                else sp.Eq(
                    S.g * sp.sin(S.theta) - S.mu * S.g * sp.cos(S.theta),
                    S.a,
                )
            )
            equations.append(_ge("normal_balance", "body", "y", "N - m*g*cos(theta) = 0", None, source_forces=["N", "mg cosθ"], unknowns=["N"], notes=["설명/검산용 법선방향 평형식입니다."]))
            equations.append(_ge("friction_law", "body", "x", "f = mu*N", None, source_forces=["f", "N"], unknowns=["f"], notes=["설명/검산용 마찰 구성식입니다."]))
            equations.append(_ge("newton_second_law", "body", "x", "g*sin(theta) - mu*g*cos(theta) = a", eq_x, source_forces=["mg sinθ", "f"], unknowns=["a"], notes=["N=mg cosθ, f=μN을 대입하고 m을 약분한 식입니다."]))
            unknowns = [S.a]
        else:
            errors.append("경사면 마찰 유무가 필요합니다.")
    elif st == "pulley_atwood":
        eq1 = sp.Eq(S.T - S.m1 * S.g, S.m1 * S.a)
        eq2 = sp.Eq(S.m2 * S.g - S.T, S.m2 * S.a)
        equations.append(_ge("newton_second_law", "body_1", "y", "T - m1*g = m1*a", eq1, source_forces=["T", "m1g"], unknowns=["T", "a"]))
        equations.append(_ge("newton_second_law", "body_2", "y", "m2*g - T = m2*a", eq2, source_forces=["m2g", "T"], unknowns=["T", "a"]))
        unknowns = [S.a, S.T]
    elif st == "pulley_table_hanging":
        mu = c.knowns.get("mu")
        friction_type = c.friction_type or ("none" if not mu else "kinetic")
        eq_y = sp.Eq(S.T1 - S.m1 * S.g, 0)  # T1 acts as normal N1 placeholder.
        equations.append(_ge("normal_balance", "body_1", "y", "N1 - m1*g = 0", eq_y, source_forces=["N1", "m1g"], unknowns=["N1"], notes=["T1 symbol is used as normal N1 placeholder"]))
        if friction_type in {"kinetic", "unspecified", "static"} and mu:
            eq_f = sp.Eq(S.F, S.mu * S.T1)
            eq_x1 = sp.Eq(S.T - S.F, S.m1 * S.a)
            equations.append(_ge("friction_law", "body_1", "x", "f = mu*N1", eq_f, source_forces=["f", "N1"], unknowns=["f"]))
            source = ["T", "f"]
            unknowns = [S.a, S.T, S.T1, S.F]
        else:
            eq_x1 = sp.Eq(S.T, S.m1 * S.a)
            source = ["T"]
            unknowns = [S.a, S.T, S.T1]
        eq_y2 = sp.Eq(S.m2 * S.g - S.T, S.m2 * S.a)
        equations.append(_ge("newton_second_law", "body_1", "x", "T - f = m1*a" if mu else "T = m1*a", eq_x1, source_forces=source, unknowns=["T", "a"]))
        equations.append(_ge("newton_second_law", "body_2", "y", "m2*g - T = m2*a", eq_y2, source_forces=["m2g", "T"], unknowns=["T", "a"]))
    elif st == "pulley_incline_hanging":
        mu = c.knowns.get("mu_k") or c.knowns.get("mu")
        friction_type = c.friction_type or ("none" if not mu else "kinetic")
        eq_n = sp.Eq(S.T1 - S.m1 * S.g * sp.cos(S.theta), 0)  # T1=N1 placeholder
        equations.append(_ge("normal_balance", "body_1", "y", "N1 - m1*g*cos(theta) = 0", eq_n, source_forces=["N1", "m1g cosθ"], unknowns=["N1"], notes=["T1 symbol is used as normal N1 placeholder"]))

        friction_sign = -1
        motion_note = "m2 하강/m1 경사면 상승 가정"
        try:
            m1v = magnitude_si(c.knowns["m1"], "kg")
            m2v = magnitude_si(c.knowns["m2"], "kg")
            gv = magnitude_si(c.knowns["g"], "m/s^2")
            thv = math.radians(magnitude_si(c.knowns["theta"], "deg"))
            driving = m2v * gv - m1v * gv * math.sin(thv)
            if driving < 0:
                friction_sign = +1
                motion_note = "m1 경사면 하강 경향이므로 마찰은 경사면 위쪽"
        except Exception:
            driving = None

        if friction_type in {"kinetic", "unspecified", "static"} and mu:
            eq_f = sp.Eq(S.F, S.mu * S.T1)
            if friction_sign > 0:
                eq_x1 = sp.Eq(S.T - S.m1 * S.g * sp.sin(S.theta) + S.F, S.m1 * S.a)
                x_text = "T - m1*g*sin(theta) + f = m1*a"
                source = ["T", "m1g sinθ", "f"]
            else:
                eq_x1 = sp.Eq(S.T - S.m1 * S.g * sp.sin(S.theta) - S.F, S.m1 * S.a)
                x_text = "T - m1*g*sin(theta) - f = m1*a"
                source = ["T", "m1g sinθ", "f"]
            equations.append(_ge("friction_law", "body_1", "x", "f = mu*N1", eq_f, source_forces=["f", "N1"], unknowns=["f"], notes=[motion_note]))
            unknowns = [S.a, S.T, S.T1, S.F]
        else:
            eq_x1 = sp.Eq(S.T - S.m1 * S.g * sp.sin(S.theta), S.m1 * S.a)
            unknowns = [S.a, S.T, S.T1]
            x_text = "T - m1*g*sin(theta) = m1*a"
            source = ["T", "m1g sinθ"]
        eq_y2 = sp.Eq(S.m2 * S.g - S.T, S.m2 * S.a)
        equations.append(_ge("newton_second_law", "body_1", "x", x_text, eq_x1, source_forces=source, unknowns=["T", "a"], notes=[motion_note]))
        equations.append(_ge("newton_second_law", "body_2", "y", "m2*g - T = m2*a", eq_y2, source_forces=["m2g", "T"], unknowns=["T", "a"]))
    elif st == "massive_pulley_atwood":
        if typed is not None:
            eq1 = sp.Eq(
                typed.sum_forces("body_1", "body_1_up").x,
                S.m1 * S.a,
            )
            eq2 = sp.Eq(
                typed.sum_forces("body_2", "body_2_down").x,
                S.m2 * S.a,
            )
            eq3 = sp.Eq(
                typed.moment_about(
                    "pulley",
                    typed.bodies["pulley"].center_of_mass,
                    frame_id="pulley",
                ),
                S.I * (S.a / S.R),
            )
        else:
            eq1 = sp.Eq(S.T1 - S.m1 * S.g, S.m1 * S.a)
            eq2 = sp.Eq(S.m2 * S.g - S.T2, S.m2 * S.a)
            eq3 = sp.Eq((S.T2 - S.T1) * S.R, S.I * (S.a / S.R))
        equations.extend([
            _ge("newton_second_law", "body_1", "y", "T1 - m1*g = m1*a", eq1, source_forces=["T1", "m1g"], unknowns=["T1", "a"]),
            _ge("newton_second_law", "body_2", "y", "m2*g - T2 = m2*a", eq2, source_forces=["m2g", "T2"], unknowns=["T2", "a"]),
            _ge("newton_euler", "pulley", "rotation", "(T2-T1)*R = I*(a/R)", eq3, source_forces=["T1", "T2"], unknowns=["T1", "T2", "a"]),
        ])
        unknowns = [S.a, S.T1, S.T2]
    else:
        errors.append(f"ParticleNewton generator does not support {st}")

    ready = bool(equations) and not errors
    return GeneratedEquationSystem(
        generator="particle_newton",
        equations=equations,
        unknowns=[str(u) for u in unknowns],
        substitutions={str(k): float(v) for k, v in _model_subs(c, typed).items()},
        equations_ready=ready,
        warnings=warnings,
        errors=errors,
    )


def _sympy_equations(system: GeneratedEquationSystem) -> list[Any]:
    eqs = []
    for eq in system.equations:
        if eq.sympy_repr:
            # Use sympify on Eq(...) representation. Safer than eval with full globals.
            eqs.append(sp.sympify(eq.sympy_repr, locals={
                "Eq": sp.Eq,
                "sin": sp.sin,
                "cos": sp.cos,
                "a": S.a, "T": S.T, "T1": S.T1, "T2": S.T2,
                "F": S.F, "m": S.m, "m1": S.m1, "m2": S.m2,
                "g": S.g, "mu": S.mu, "theta": S.theta, "I": S.I, "R": S.R,
            }))
    return eqs


def _unknown_symbols(system: GeneratedEquationSystem) -> list[Any]:
    mapping = {"a": S.a, "T": S.T, "T1": S.T1, "T2": S.T2, "F": S.F, "m": S.m, "m1": S.m1, "m2": S.m2}
    return [mapping[u] for u in system.unknowns if u in mapping]


def _subs_from_system(system: GeneratedEquationSystem) -> dict:
    mapping = {"a": S.a, "T": S.T, "T1": S.T1, "T2": S.T2, "F": S.F, "m": S.m, "m1": S.m1, "m2": S.m2, "g": S.g, "mu": S.mu, "theta": S.theta, "I": S.I, "R": S.R}
    return {mapping[k]: v for k, v in system.substitutions.items() if k in mapping}


def solve_particle_newton_system(c: CanonicalProblem, model: PhysicalModel | None = None) -> GeneratedSolve:
    system = (
        model.generated_equation_system
        if model is not None and model.generated_equation_system is not None
        else build_particle_newton_system(c, model)
    )
    if not system.equations_ready:
        return GeneratedSolve(False, {}, system, system.errors or ["방정식 생성 실패"])
    eqs = _sympy_equations(system)
    unknowns = _unknown_symbols(system)
    subs = _subs_from_system(system)
    solved = EquationSystem(eqs, unknowns, subs).solve()
    if not solved:
        return GeneratedSolve(False, {}, system, ["물리적으로 가능한 해를 찾지 못했습니다."])
    return GeneratedSolve(True, solved[0], system, [])


def generated_equation_step_card(system: GeneratedEquationSystem) -> StepCard:
    if not system.equations:
        body = "아직 이 유형은 Phase 15 Newton generator 지원 범위 밖입니다."
    else:
        body = "\n".join(f"- {eq.equation}" for eq in system.equations)
    return StepCard("모델 기반 방정식 생성", body, "\\Sigma F = ma")
