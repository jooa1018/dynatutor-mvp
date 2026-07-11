from __future__ import annotations

import math
import sympy as sp
from dataclasses import dataclass
from typing import Any

from engine.models import CanonicalProblem, StepCard
from engine.model_builder.model_types import GeneratedEquation, GeneratedEquationSystem, PhysicalModel
from engine.physics_core.direction_parser import infer_angle_between_force_and_displacement
from engine.physics_core.inertia import beta_for_shape
from engine.physics_core.units import magnitude_si


@dataclass
class EnergyMomentumSolve:
    ok: bool
    solution: dict[str, Any]
    system: GeneratedEquationSystem
    errors: list[str]


def _eq(kind: str, equation: str, *, unknowns: list[str], body_id: str | None = None, axis: str | None = None, source_forces: list[str] | None = None, notes: list[str] | None = None) -> GeneratedEquation:
    return GeneratedEquation(
        id=f"{kind}_{len(equation)}",
        kind=kind,
        body_id=body_id,
        axis=axis,
        equation=equation,
        sympy_repr=None,
        source_forces=source_forces or [],
        unknowns=unknowns,
        notes=notes or [],
    )


def _q(c: CanonicalProblem, key: str, unit: str) -> float | None:
    if key not in c.knowns:
        return None
    return magnitude_si(c.knowns[key], unit)


def _raw_q(c: CanonicalProblem, key: str) -> float | None:
    if key not in c.knowns or c.knowns[key].value is None:
        return None
    return float(c.knowns[key].value)


def build_energy_momentum_system(c: CanonicalProblem, model: PhysicalModel | None = None) -> GeneratedEquationSystem:
    st = c.system_type
    equations: list[GeneratedEquation] = []
    unknowns: list[str] = []
    subs: dict[str, float] = {}
    warnings: list[str] = []
    errors: list[str] = []

    if st == "constant_force_work":
        equations.append(_eq("work_definition", "W = F*s*cos(theta)", unknowns=["W"], body_id="body", axis="s", source_forces=["F"], notes=["힘과 변위의 내적입니다. 방향 또는 각도가 필요합니다."]))
        unknowns = ["W"]
    elif st == "work_energy_speed":
        equations.append(_eq("work_energy", "W_net = ΔK = 1/2*m*v_f^2 - 1/2*m*v_i^2", unknowns=["v_f"], body_id="body"))
        equations.append(_eq("speed_from_work", "v_f = sqrt(v_i^2 + 2*W_net/m)", unknowns=["v_f"], body_id="body"))
        unknowns = ["v_f"]
    elif st == "spring_mass_vibration":
        equations.append(_eq("spring_ode", "m*x_ddot + k*x = 0", unknowns=["omega_n"], body_id="body", source_forces=["kx"]))
        equations.append(_eq("natural_frequency", "omega_n = sqrt(k/m)", unknowns=["omega_n"], body_id="body"))
        equations.append(_eq("period_frequency", "T = 2*pi/omega_n, f = 1/T", unknowns=["T", "f"], body_id="body"))
        unknowns = ["omega_n", "T", "f"]
    elif st in {"spring_energy", "spring_energy_speed"}:
        equations.append(_eq("spring_energy", "1/2*k*x^2 = 1/2*m*v^2", unknowns=["v"], body_id="body", source_forces=["spring_force"]))
        equations.append(_eq("spring_speed", "v = x*sqrt(k/m)", unknowns=["v"], body_id="body"))
        unknowns = ["v"]
    elif st in {"pure_rolling_energy", "rolling_energy_general"}:
        equations.append(_eq("rolling_energy", "m*g*h = 1/2*m*v^2 + 1/2*I*omega^2", unknowns=["v"], body_id="body", source_forces=["mg"]))
        equations.append(_eq("rolling_constraint", "v = omega*R", unknowns=["omega"], body_id="body"))
        if "I" in c.knowns:
            equations.append(_eq("general_inertia", "v = sqrt(2*m*g*h/(m + I/R^2))", unknowns=["v"], body_id="body"))
        else:
            equations.append(_eq("shape_inertia", "I = beta*m*R^2, v = sqrt(2*g*h/(1+beta))", unknowns=["v"], body_id="body"))
        unknowns = ["v", "omega"]
    elif st == "impulse_momentum":
        equations.append(_eq("impulse", "J = F*Δt", unknowns=["J"], body_id="body", source_forces=["F"]))
        equations.append(_eq("impulse_momentum", "J = Δp = m*(v_f - v_i)", unknowns=["v_f"], body_id="body"))
        unknowns = ["J", "v_f"]
    elif st == "collision_1d":
        equations.append(_eq("linear_momentum", "m1*v1 + m2*v2 = m1*v1f + m2*v2f", unknowns=["v1f", "v2f"], body_id=None))
        if c.flags.get("perfectly_inelastic"):
            equations.append(_eq("perfectly_inelastic_constraint", "v1f = v2f = v_f", unknowns=["v_f"], body_id=None))
        elif c.flags.get("elastic") or "e" in c.knowns:
            equations.append(_eq("restitution", "v2f - v1f = e*(v1 - v2)", unknowns=["v1f", "v2f"], body_id=None))
        else:
            warnings.append("충돌은 운동량 보존식 하나만으로는 부족합니다. 완전비탄성/탄성/e가 필요합니다.")
        unknowns = ["v1f", "v2f"]
    else:
        errors.append(f"EnergyMomentum generator does not support {st}")

    ready = bool(equations) and not errors
    return GeneratedEquationSystem(
        generator="energy_momentum",
        equations=equations,
        unknowns=unknowns,
        substitutions=subs,
        equations_ready=ready,
        warnings=warnings,
        errors=errors,
    )


def solve_energy_momentum_system(c: CanonicalProblem, model: PhysicalModel | None = None) -> EnergyMomentumSolve:
    system = build_energy_momentum_system(c, model)
    if not system.equations_ready:
        return EnergyMomentumSolve(False, {}, system, system.errors or system.warnings or ["에너지/운동량 방정식 생성 실패"])

    st = c.system_type
    try:
        if st == "constant_force_work":
            F = _q(c, "F", "N")
            s = _q(c, "s", "m")
            angle = infer_angle_between_force_and_displacement(c.raw_text)
            if angle is None and ("force" in c.raw_text.lower() and "distance" in c.raw_text.lower()):
                angle = 0.0
            if angle is None and "theta" in c.knowns and c.knowns["theta"].value is not None:
                # 추출기('힘 방향으로 이동'→θ=0) 또는 clarification(set_known theta)이 채운 각도
                angle = float(c.knowns["theta"].value)
            if F is None or s is None or angle is None:
                return EnergyMomentumSolve(False, {}, system, ["힘 F, 이동거리 s, 힘-변위 사이 각도가 필요합니다."])
            W = F * s * math.cos(math.radians(angle))
            return EnergyMomentumSolve(True, {"W": W, "theta_deg": angle}, system, [])

        if st == "work_energy_speed":
            m = _q(c, "m", "kg")
            W = _q(c, "W", "J") if "W" in c.knowns else None
            if W is None and "F" in c.knowns and "s" in c.knowns:
                angle = _q(c, "theta", "deg") if "theta" in c.knowns else 0.0
                W = _q(c, "F", "N") * _q(c, "s", "m") * math.cos(math.radians(angle))
            v0 = _q(c, "v0", "m/s") if "v0" in c.knowns else _q(c, "v", "m/s") if "v" in c.knowns else 0.0
            if m is None or W is None:
                return EnergyMomentumSolve(False, {}, system, ["질량 m과 일 W 또는 F,s가 필요합니다."])
            vf2 = v0 * v0 + 2 * W / m
            if vf2 < 0:
                return EnergyMomentumSolve(False, {}, system, ["v_f^2가 음수입니다."])
            vf = math.sqrt(vf2)
            return EnergyMomentumSolve(True, {"v_f": vf, "W": W, "v_i": v0}, system, [])

        if st == "spring_mass_vibration":
            k = _q(c, "k", "N/m")
            m = _q(c, "m", "kg")
            if k is None or m is None:
                return EnergyMomentumSolve(False, {}, system, ["k와 m이 필요합니다."])
            omega = math.sqrt(k / m)
            period = 2 * math.pi / omega
            freq = 1 / period
            return EnergyMomentumSolve(True, {"omega_n": omega, "T": period, "f": freq}, system, [])

        if st in {"spring_energy", "spring_energy_speed"}:
            k = _q(c, "k", "N/m")
            m = _q(c, "m", "kg")
            x = _q(c, "x", "m") if "x" in c.knowns else _q(c, "A", "m") if "A" in c.knowns else None
            if k is None or m is None or x is None:
                return EnergyMomentumSolve(False, {}, system, ["k, x, m이 필요합니다."])
            v = x * math.sqrt(k / m)
            return EnergyMomentumSolve(True, {"v": v, "x": x, "k": k, "m": m}, system, [])

        if st in {"pure_rolling_energy", "rolling_energy_general"}:
            h = _q(c, "h", "m") if "h" in c.knowns else float(c.launch_height or 0.0)
            g = _q(c, "g", "m/s^2") or 9.81
            if "I" in c.knowns:
                m = _q(c, "m", "kg")
                R = _q(c, "R", "m")
                I = _q(c, "I", "kg*m^2")
                if m is None or R is None or I is None:
                    return EnergyMomentumSolve(False, {}, system, ["I 기반 구름운동에는 m, I, R이 필요합니다."])
                v = math.sqrt(2 * m * g * h / (m + I / R**2))
                omega = v / R
                beta = I / (m * R**2)
                return EnergyMomentumSolve(True, {"v": v, "omega": omega, "beta": beta, "mode": "I"}, system, [])
            beta = beta_for_shape(c.body_shape)
            if beta is None:
                return EnergyMomentumSolve(False, {}, system, ["물체 종류 또는 관성모멘트 I가 필요합니다."])
            v = math.sqrt(2 * g * h / (1 + beta))
            return EnergyMomentumSolve(True, {"v": v, "beta": beta, "mode": "shape"}, system, [])

        if st == "impulse_momentum":
            F = _q(c, "F", "N")
            dt = _q(c, "t", "s")
            if F is None or dt is None:
                return EnergyMomentumSolve(False, {}, system, ["힘 F와 시간 Δt가 필요합니다."])
            J = F * dt
            solution = {"J": J}
            m = _q(c, "m", "kg")
            vi = _q(c, "v0", "m/s") if "v0" in c.knowns else _q(c, "v", "m/s") if "v" in c.knowns else None
            if m is not None and vi is not None:
                solution["v_f"] = vi + J / m
                solution["v_i"] = vi
            return EnergyMomentumSolve(True, solution, system, [])

        if st == "collision_1d":
            m1 = _q(c, "m1", "kg")
            m2 = _q(c, "m2", "kg")
            v1 = _q(c, "v1", "m/s")
            v2 = _q(c, "v2", "m/s")
            if None in {m1, m2, v1, v2}:
                return EnergyMomentumSolve(False, {}, system, ["m1, m2, v1, v2가 필요합니다."])

            typed = getattr(model, "typed_model", None) if model is not None else None
            if typed is not None:
                residuals = [
                    constraint.expression
                    for constraint in typed.constraints
                    if isinstance(constraint.expression, sp.Expr)
                    and constraint.kind in {
                        "linear_momentum",
                        "restitution",
                        "common_final_velocity",
                    }
                ]
                if len(residuals) < 2:
                    return EnergyMomentumSolve(
                        False,
                        {},
                        system,
                        ["완전비탄성/완전탄성/반발계수 e 중 하나가 필요합니다."],
                    )
                symbol_by_name = {
                    str(symbol): symbol
                    for expression in residuals
                    for symbol in expression.free_symbols
                }
                substitutions = {
                    symbol_by_name["m1"]: m1,
                    symbol_by_name["m2"]: m2,
                    symbol_by_name["v1"]: v1,
                    symbol_by_name["v2"]: v2,
                }
                e = 1.0 if c.flags.get("elastic") else _raw_q(c, "e")
                if "e" in symbol_by_name and e is not None:
                    substitutions[symbol_by_name["e"]] = e
                unknowns = [symbol_by_name["v1f"], symbol_by_name["v2f"]]
                solved = sp.solve(
                    [sp.Eq(expression.subs(substitutions), 0) for expression in residuals],
                    unknowns,
                    dict=True,
                )
                if not solved:
                    return EnergyMomentumSolve(
                        False,
                        {},
                        system,
                        ["typed 충돌 constraint에서 물리 해를 찾지 못했습니다."],
                    )
                v1p = float(solved[0][unknowns[0]])
                v2p = float(solved[0][unknowns[1]])
                if c.flags.get("perfectly_inelastic"):
                    return EnergyMomentumSolve(True, {"v_f": v1p}, system, [])
                return EnergyMomentumSolve(
                    True,
                    {"v1f": v1p, "v2f": v2p, "e": e},
                    system,
                    [],
                )

            # Compatibility fallback for direct legacy generator callers.
            if c.flags.get("perfectly_inelastic"):
                vf = (m1 * v1 + m2 * v2) / (m1 + m2)
                return EnergyMomentumSolve(True, {"v_f": vf}, system, [])
            e = 1.0 if c.flags.get("elastic") else _raw_q(c, "e")
            if e is not None:
                v1p = (m1 * v1 + m2 * v2 - m2 * e * (v1 - v2)) / (m1 + m2)
                v2p = v1p + e * (v1 - v2)
                return EnergyMomentumSolve(True, {"v1f": v1p, "v2f": v2p, "e": e}, system, [])
            return EnergyMomentumSolve(False, {}, system, ["완전비탄성/완전탄성/반발계수 e 중 하나가 필요합니다."])
    except Exception as exc:
        return EnergyMomentumSolve(False, {}, system, [str(exc)])

    return EnergyMomentumSolve(False, {}, system, [f"지원하지 않는 유형: {st}"])


def generated_energy_momentum_step_card(system: GeneratedEquationSystem) -> StepCard:
    if not system.equations:
        body = "아직 이 유형은 Energy/Momentum generator 지원 범위 밖입니다."
    else:
        body = "\n".join(f"- {eq.equation}" for eq in system.equations)
    return StepCard("모델 기반 에너지/운동량 방정식", body, "W=\\Delta K,\\quad J=\\Delta p")
