from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import re
from typing import Any

from engine.models import CanonicalProblem
from engine.solvers.base import BaseSolver
from engine.solvers.incline import InclineNoFrictionSolver, InclineWithFrictionSolver
from engine.solvers.newton import SingleParticleNewtonSolver
from engine.solvers.pulley import AtwoodPulleySolver, TableHangingPulleySolver, InclineHangingPulleySolver, MassivePulleyAtwoodSolver
from engine.solvers.rolling import PureRollingEnergySolver, RollingEnergyGeneralSolver
from engine.solvers.vertical_circle import VerticalCircleSolver
from engine.solvers.collision import Collision1DSolver
from engine.solvers.kinematics import ConstantAcceleration1DSolver
from engine.solvers.projectile import ProjectileMotionSolver
from engine.solvers.work_rotation_impulse import ConstantForceWorkSolver, FixedAxisRotationSolver, ImpulseMomentumSolver
from engine.solvers.energy_vibration import SpringMassVibrationSolver, SpringEnergySpeedSolver, WorkEnergySpeedSolver, HorizontalFrictionForceSolver
from engine.solvers.curves import FlatCurveFrictionSolver, BankedCurveNoFrictionSolver
from engine.solvers.advanced_motion import PolarKinematicsSolver, InstantCenterVelocitySolver, SlotPinRelativeMotionSolver
from engine.solvers.advanced_dynamics import CoriolisRelativeMotionSolver
from engine.solvers.rigid_body_2d import PlaneRigidBodyVelocitySolver, PlaneRigidBodyAccelerationSolver, RelativeAccelerationTranslationSolver
from engine.routing.config import ROUTING_CONFIG
from engine.routing.evidence import TYPE_TO_FAMILY, rank_type_evidence


@dataclass
class RouteCandidate:
    solver_id: str
    family: str
    raw_score: int
    normalized_score: float
    evidence: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    supported_outputs: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    source_system_type: str | None = None
    source_subtype: str | None = None
    interpretation_score: float = 1.0
    solver: BaseSolver | None = field(default=None, repr=False, compare=False)


@dataclass
class RouteDecision:
    status: str
    candidates: list[RouteCandidate]
    selected_solver_id: str | None = None
    question: str | None = None
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


class SolverRegistry:
    def __init__(self) -> None:
        self.solvers: list[BaseSolver] = [
            SingleParticleNewtonSolver(),
            InclineNoFrictionSolver(),
            InclineWithFrictionSolver(),
            AtwoodPulleySolver(),
            TableHangingPulleySolver(),
            InclineHangingPulleySolver(),
            MassivePulleyAtwoodSolver(),
            PureRollingEnergySolver(),
            RollingEnergyGeneralSolver(),
            VerticalCircleSolver(),
            Collision1DSolver(),
            ConstantAcceleration1DSolver(),
            ProjectileMotionSolver(),
            ConstantForceWorkSolver(),
            FixedAxisRotationSolver(),
            HorizontalFrictionForceSolver(),
            ImpulseMomentumSolver(),
            WorkEnergySpeedSolver(),
            SpringMassVibrationSolver(),
            SpringEnergySpeedSolver(),
            FlatCurveFrictionSolver(),
            BankedCurveNoFrictionSolver(),
            RelativeAccelerationTranslationSolver(),
            CoriolisRelativeMotionSolver(),
            PlaneRigidBodyAccelerationSolver(),
            PolarKinematicsSolver(),
            InstantCenterVelocitySolver(),
            SlotPinRelativeMotionSolver(),
            PlaneRigidBodyVelocitySolver(),
        ]
        self.last_route_decision: RouteDecision | None = None
        self._capabilities = self._load_capabilities()

    def _load_capabilities(self) -> dict[str, dict[str, Any]]:
        path = Path(__file__).resolve().parents[1] / "capabilities" / "dynamics_capabilities.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return {entry["analytic_solver"]: entry for entry in data.get("capabilities", [])}

    def _family(self, solver_id: str) -> str:
        solver_family = {
            "incline_no_friction": "incline",
            "incline_with_friction": "incline",
            "horizontal_friction_force": "friction",
        }.get(solver_id)
        if solver_family:
            return solver_family
        return TYPE_TO_FAMILY.get(solver_id, solver_id.split("_", 1)[0])

    def _variant_specs(self, c: CanonicalProblem) -> list[tuple[str, str | None, float, list[str]]]:
        specs: dict[tuple[str, str | None], tuple[float, list[str]]] = {}

        def add(system_type: str, subtype: str | None, score: float, reason: str) -> None:
            key = (system_type, subtype)
            score = max(0.0, min(1.0, float(score)))
            if key not in specs:
                specs[key] = (score, [reason])
                return
            previous_score, reasons = specs[key]
            if reason not in reasons:
                reasons.append(reason)
            specs[key] = (max(previous_score, score), reasons)

        if c.canonical_v2 is not None:
            for parse_candidate in c.canonical_v2.parse_candidates:
                for type_candidate in parse_candidate.system_type_candidates:
                    add(
                        type_candidate.system_type,
                        type_candidate.subtype,
                        min(float(parse_candidate.score), float(type_candidate.score)),
                        type_candidate.reason,
                    )
        if (c.system_type, c.subtype) not in specs:
            add(c.system_type, c.subtype, 1.0, "canonical compatibility interpretation")

        evidence = rank_type_evidence(c)
        if (
            c.system_type == "unknown"
            and len(evidence) > 1
            and not (c.flags or {}).get("_clarify_model_chosen")
        ):
            for item in evidence:
                score = min(
                    ROUTING_CONFIG.evidence_candidate_ceiling,
                    ROUTING_CONFIG.evidence_candidate_base
                    + ROUTING_CONFIG.evidence_candidate_step * item.score,
                )
                add(
                    item.rep_type,
                    c.subtype if item.rep_type == c.system_type else None,
                    score,
                    f"{item.label} evidence: {', '.join(item.reasons)}",
                )
        return [
            (system_type, subtype, score, reasons)
            for (system_type, subtype), (score, reasons) in specs.items()
        ]

    def _has_symbol(self, c: CanonicalProblem, symbol: str) -> bool:
        expression = symbol.strip()
        requested = set(c.requested_outputs or c.unknowns or [])
        raw = (c.raw_text or "").lower()
        coordinate_data = c.coordinate_data or {}

        special = {
            "theta": "theta" in c.knowns or c.launch_angle_deg is not None,
            "v0": (
                ("v0" in c.knowns and c.knowns["v0"].value is not None)
                or self._starts_from_rest(c)
            ),
            "launch_angle_deg": c.launch_angle_deg is not None,
            "launch_height": c.launch_height is not None or "h" in c.knowns,
            "body_shape": bool(c.body_shape),
            "friction_type": bool(c.friction_type),
            "force_direction": bool(c.force_direction) or "theta" in c.knowns,
            "vA": (
                "vA" in c.knowns
                and c.knowns["vA"].value is not None
                and abs(float(c.knowns["vA"].value)) <= 1e-12
            ),
            "minimum_speed request": "minimum_speed" in requested,
            "top subtype": c.subtype == "top",
            "bottom subtype": c.subtype == "bottom",
            "explicit no_friction": (
                c.friction_type in {"none", "no_friction"}
                or c.subtype == "no_friction"
                or bool((c.flags or {}).get("no_friction"))
            ),
            "I plus m and R": all(key in c.knowns for key in ("I", "m", "R")),
            "alpha and t for angular velocity": (
                "alpha" in c.knowns and "t" in c.knowns
                and "angular_velocity" in requested
            ),
            "omega and r/R for tangential speed": (
                "omega" in c.knowns
                and ("r" in c.knowns or "R" in c.knowns)
                and "tangential_velocity" in requested
            ),
            "m1 when m2 absent": "m1" in c.knowns and "m2" not in c.knowns,
            "impulse request": "impulse" in requested,
            "m plus v0/v for final velocity": (
                "m" in c.knowns
                and ("v0" in c.knowns or "v" in c.knowns)
                and "final_velocity" in requested
            ),
            "m for speed": "m" in c.knowns,
            "elastic_energy request": "elastic_energy" in requested,
            "r/R": "r" in c.knowns or "R" in c.knowns,
            "v0/v": "v0" in c.knowns or "v" in c.knowns,
            "coordinate_data rBA vector": (
                "rBAx" in coordinate_data and "rBAy" in coordinate_data
            ),
            "coordinate_data vA vector": (
                "vAx" in coordinate_data and "vAy" in coordinate_data
            ),
            "A fixed statement": any(
                phrase in raw
                for phrase in (
                    "고정점",
                    "a점이 고정",
                    "a점은 고정",
                    "a점 고정",
                    "a is fixed",
                )
            ),
            "explicit rest condition": self._starts_from_rest(c),
            "force-displacement direction": (
                bool(c.force_direction) or "theta" in c.knowns
            ),
            "rBA vector": (
                ("rBAx" in coordinate_data and "rBAy" in coordinate_data)
                or ("rBAx" in c.knowns and "rBAy" in c.knowns)
            ),
            "vA vector": (
                ("vAx" in coordinate_data and "vAy" in coordinate_data)
                or ("vAx" in c.knowns and "vAy" in c.knowns)
            ),
            "aA vector": (
                ("aAx" in coordinate_data and "aAy" in coordinate_data)
                or ("aAx" in c.knowns and "aAy" in c.knowns)
            ),
            "zero vA": (
                "vA" in c.knowns
                and c.knowns["vA"].value is not None
                and abs(float(c.knowns["vA"].value)) <= 1e-12
            ),
            "zero aA": (
                "aA" in c.knowns
                and c.knowns["aA"].value is not None
                and abs(float(c.knowns["aA"].value)) <= 1e-12
            ),
            "fixed A plus scalar radius": (
                ("r" in c.knowns or "R" in c.knowns)
                and (
                    any(
                        phrase in raw
                        for phrase in (
                            "고정점",
                            "a점이 고정",
                            "a점은 고정",
                            "a점 고정",
                            "a is fixed",
                        )
                    )
                    or (
                        c.system_type == "plane_rigid_body_velocity"
                        and "vA" in c.knowns
                        and c.knowns["vA"].value is not None
                        and abs(float(c.knowns["vA"].value)) <= 1e-12
                    )
                    or (
                        c.system_type == "plane_rigid_body_acceleration"
                        and "aA" in c.knowns
                        and c.knowns["aA"].value is not None
                        and abs(float(c.knowns["aA"].value)) <= 1e-12
                    )
                )
            ),
        }
        if expression in special:
            return bool(special[expression])
        if " plus " in expression:
            return all(self._has_symbol(c, part) for part in expression.split(" plus "))
        if " and " in expression:
            return all(self._has_symbol(c, part) for part in expression.split(" and "))
        if " or " in expression:
            return any(self._has_symbol(c, part) for part in expression.split(" or "))
        if "/" in expression and " " not in expression:
            return any(self._has_symbol(c, part) for part in expression.split("/"))
        if (c.flags or {}).get(expression):
            return True
        return expression in c.knowns and c.knowns[expression].value is not None

    def _projectile_time_without_speed(self, c: CanonicalProblem) -> bool:
        requested = {
            item
            for item in (c.requested_outputs or c.unknowns or [])
            if item != "auto"
        }
        angle = c.launch_angle_deg
        if angle is None and "theta" in c.knowns:
            angle = c.knowns["theta"].value
        has_vertical_drop = c.launch_height is not None or "h" in c.knowns
        return bool(requested) and requested <= {"time"} and angle == 0 and has_vertical_drop

    def _starts_from_rest(self, c: CanonicalProblem) -> bool:
        raw = (c.raw_text or "").lower()
        return any(
            phrase in raw
            for phrase in (
                "정지 상태에서",
                "정지 상태로부터",
                "정지에서",
                "처음에는 정지",
                "초기에는 정지",
                "가만히 있다가",
                "starts from rest",
                "initially at rest",
            )
        )

    def _missing_requirements(
        self,
        c: CanonicalProblem,
        capability: dict[str, Any],
        solver_id: str,
    ) -> list[str]:
        req = capability.get("required_inputs", {})
        missing: list[str] = []
        for symbol in req.get("all_of", []):
            if not self._has_symbol(c, symbol):
                missing.append(symbol)
        any_of = req.get("any_of", [])
        if any_of and not any(self._has_symbol(c, symbol) for symbol in any_of):
            missing.append("one of: " + ", ".join(any_of))
        for condition in req.get("conditional", []):
            if "one_of" in condition:
                alternatives = condition["one_of"]
                if (
                    solver_id == "projectile_motion"
                    and set(alternatives) == {"v0", "v"}
                    and self._projectile_time_without_speed(c)
                ):
                    continue
                if not any(self._has_symbol(c, symbol) for symbol in alternatives):
                    missing.append("one of: " + ", ".join(alternatives))
            if "all_of" in condition:
                missing.extend(
                    symbol
                    for symbol in condition["all_of"]
                    if not self._has_symbol(c, symbol)
                )
            if "minimum_present" in condition:
                symbols = condition.get("symbols", [])
                if sum(1 for symbol in symbols if self._has_symbol(c, symbol)) < int(condition["minimum_present"]):
                    missing.append(f"{condition['minimum_present']} of: {', '.join(symbols)}")

        requested = set(c.requested_outputs or c.unknowns or [])
        if (
            solver_id == "vertical_circle"
            and "minimum_speed" not in requested
            and "m" not in c.knowns
        ):
            missing.append("m for force output")
        if solver_id == "work_energy_speed":
            if "v0" not in c.knowns and "v" not in c.knowns and not self._starts_from_rest(c):
                missing.append("initial velocity or explicit rest condition")
            if (
                "W" not in c.knowns
                and "F" in c.knowns
                and "s" in c.knowns
                and not self._has_symbol(c, "force_direction")
            ):
                missing.append("force-displacement direction or theta")
        if solver_id in {"pulley_table_hanging", "pulley_incline_hanging"}:
            if c.friction_type == "static" and not any(
                key in c.knowns for key in ("mu_s", "mu")
            ):
                missing.append("mu_s")
            if c.friction_type in {"kinetic", "unspecified"} and not any(
                key in c.knowns for key in ("mu_k", "mu")
            ):
                missing.append("mu_k")
        if solver_id in {"plane_rigid_body_velocity", "plane_rigid_body_acceleration"}:
            raw = c.raw_text or ""
            fixed_A = any(
                phrase in raw
                for phrase in ("고정점", "A점이 고정", "A점은 고정", "A점 고정", "A is fixed")
            )
            ref_symbol = "vA" if solver_id == "plane_rigid_body_velocity" else "aA"
            zero_reference = (
                ref_symbol in c.knowns
                and c.knowns[ref_symbol].value is not None
                and abs(float(c.knowns[ref_symbol].value)) <= 1e-12
            )
            prefix = "v" if solver_id == "plane_rigid_body_velocity" else "a"
            has_reference_vector = (
                f"{prefix}Ax" in (c.coordinate_data or {})
                and f"{prefix}Ay" in (c.coordinate_data or {})
            ) or (
                f"{prefix}Ax" in c.knowns and f"{prefix}Ay" in c.knowns
            )
            has_r_vector = (
                "rBAx" in (c.coordinate_data or {})
                and "rBAy" in (c.coordinate_data or {})
            ) or ("rBAx" in c.knowns and "rBAy" in c.knowns)
            has_scalar_r = "r" in c.knowns or "R" in c.knowns
            if not has_reference_vector and not fixed_A and not zero_reference:
                missing.append(f"{ref_symbol} vector or fixed A")
            if not has_r_vector and not ((fixed_A or zero_reference) and has_scalar_r):
                missing.append("rBA vector (scalar r only for fixed A magnitude)")
        return list(dict.fromkeys(missing))

    def _requested_output_contradictions(
        self,
        c: CanonicalProblem,
        supported: list[str],
    ) -> list[str]:
        requested = [
            item
            for item in (c.requested_outputs or [])
            if item != "auto"
        ]
        if not requested or not supported:
            return []
        aliases = {
            "distance": "range",
            "x": "range",
            "height": "max_height",
            "a": "acceleration",
            "alpha": "angular_acceleration",
            "velocity": "final_velocity",
            "v": "final_velocity",
            "vf": "final_velocity",
        }
        supported_set = set(supported)
        bad: list[str] = []
        for out in requested:
            normalized = aliases.get(out, out)
            acceptable = {out, normalized}
            if normalized == "final_velocity":
                acceptable.add("post_collision_velocity")
            if out == "minimum_speed":
                acceptable.add("final_velocity")
            if out == "tension":
                acceptable.add("force")
            if not (acceptable & supported_set):
                bad.append(out)
        return [f"unsupported requested output: {out}" for out in bad]

    def _unsupported_reasons(self, c: CanonicalProblem) -> list[str]:
        raw = c.raw_text.lower()
        reasons: list[str] = []
        if re.search(r"\b3d\b|3차원|three[- ]dimensional", raw):
            reasons.append("3D dynamics is outside the current supported solver scope.")
        if any(token in raw for token in ["변형체", "deformable", "비선형 접촉", "nonlinear contact", "finite element"]):
            reasons.append("deformable bodies or complex nonlinear contact are unsupported.")
        return reasons

    def _clarification_question(self, candidates: list[RouteCandidate]) -> str:
        missing = [m for cand in candidates[:2] for m in cand.missing_requirements]
        joined = ", ".join(dict.fromkeys(missing))
        if candidates and candidates[0].solver_id == "single_particle_newton":
            return "여러 힘의 방향 또는 각 힘의 합력(알짜힘), 그리고 질량을 알려 주세요."
        if any("mu" in item or "friction_type" in item for item in missing):
            return "정지마찰계수와 운동마찰계수 중 어떤 값인지, 그리고 실제 운동 방향/경향이 무엇인지 알려 주세요."
        if any(item in {"I", "R"} or "I" in item or "R" in item for item in missing):
            return "도르래 자체의 관성모멘트 I와 반지름 R을 제공하나요, 아니면 도르래 질량/관성을 무시하나요?"
        if any("theta" in item or "v0" in item or "launch_angle" in item for item in missing):
            return "포물선 운동에 필요한 초기속도와 발사각(또는 동등한 방향 정보)을 알려 주세요."
        if joined:
            return f"필요한 입력값을 구체적으로 알려 주세요: {joined}."
        return "두 풀이 유형이 비슷하게 감지되었습니다. 어떤 물리 상황인지 더 구체적으로 알려 주세요."

    def route(self, c: CanonicalProblem) -> RouteDecision:
        unsupported = self._unsupported_reasons(c)
        by_solver: dict[str, RouteCandidate] = {}

        for system_type, subtype, interpretation_score, interpretation_evidence in self._variant_specs(c):
            variant = replace(c, system_type=system_type, subtype=subtype)
            for solver in self.solvers:
                match = solver.match(variant)
                if match is None:
                    continue
                solver_id = match.solver.name
                capability = self._capabilities.get(solver_id, {})
                missing = self._missing_requirements(variant, capability, solver_id)
                contradictions = self._requested_output_contradictions(
                    variant,
                    capability.get("requested_outputs", []),
                )
                risk_flags: list[str] = []
                if "generic" in match.reason.lower() or solver_id == "single_particle_newton":
                    risk_flags.append("generic_fallback")
                if (system_type, subtype) != (c.system_type, c.subtype):
                    risk_flags.append("interpretation_variant")
                penalty = (
                    ROUTING_CONFIG.missing_requirement_penalty * len(missing)
                    + ROUTING_CONFIG.output_contradiction_penalty * len(contradictions)
                )
                normalized = max(
                    0.0,
                    min(1.0, match.score / 100.0 * interpretation_score - penalty),
                )
                evidence = [match.reason] + list(interpretation_evidence)
                candidate = RouteCandidate(
                    solver_id=solver_id,
                    family=self._family(solver_id),
                    raw_score=match.score,
                    normalized_score=round(normalized, 4),
                    evidence=list(dict.fromkeys(evidence)),
                    missing_requirements=missing,
                    contradictions=contradictions,
                    supported_outputs=capability.get("requested_outputs", []),
                    risk_flags=risk_flags,
                    source_system_type=system_type,
                    source_subtype=subtype,
                    interpretation_score=round(interpretation_score, 4),
                    solver=match.solver,
                )
                previous = by_solver.get(solver_id)
                if previous is None or candidate.normalized_score > previous.normalized_score:
                    by_solver[solver_id] = candidate
                elif candidate.normalized_score == previous.normalized_score:
                    previous.evidence = list(
                        dict.fromkeys(previous.evidence + candidate.evidence)
                    )

        candidates = sorted(
            by_solver.values(),
            key=lambda item: item.normalized_score,
            reverse=True,
        )
        if unsupported:
            return RouteDecision(
                "unsupported",
                candidates,
                reason="; ".join(unsupported),
            )
        if not candidates:
            return RouteDecision(
                "unsupported",
                [],
                reason="No solver matched any retained interpretation.",
            )

        viable = [
            candidate
            for candidate in candidates
            if not candidate.missing_requirements and not candidate.contradictions
        ]
        if not viable:
            return RouteDecision(
                "clarify",
                candidates,
                question=self._clarification_question(candidates),
                reason="Matched solvers lack required inputs or requested outputs.",
            )

        top = viable[0]
        warnings = (
            ["generic fallback selected"]
            if "generic_fallback" in top.risk_flags
            else []
        )
        if (
            (top.source_system_type, top.source_subtype)
            != (c.system_type, c.subtype)
            and not (c.flags or {}).get("_clarify_model_chosen")
        ):
            return RouteDecision(
                "clarify",
                candidates,
                question=self._clarification_question(viable),
                reason="The leading route is an unconfirmed alternative interpretation.",
            )
        if len(viable) > 1:
            second = viable[1]
            margin = top.normalized_score - second.normalized_score
            if margin < ROUTING_CONFIG.selection_margin:
                return RouteDecision(
                    "clarify",
                    candidates,
                    question=self._clarification_question(viable),
                    reason="Top route margin is too small.",
                )
            if (
                top.family != second.family
                and margin < ROUTING_CONFIG.cross_family_margin
            ):
                return RouteDecision(
                    "clarify",
                    candidates,
                    question=self._clarification_question(viable),
                    reason="Different solver families are competing.",
                )
        return RouteDecision(
            "select",
            candidates,
            selected_solver_id=top.solver_id,
            warnings=warnings,
        )

    def select(
        self,
        c: CanonicalProblem,
        decision: RouteDecision | None = None,
    ) -> BaseSolver | None:
        if (
            decision is None
            and self.last_route_decision is not None
            and getattr(self, "_last_route_problem_identity", None) == id(c)
        ):
            decision = self.last_route_decision
        decision = decision or self.route(c)
        self.last_route_decision = decision
        self._last_route_problem_identity = id(c)
        if decision.status != "select" or decision.selected_solver_id is None:
            return None
        chosen = next(
            (
                candidate
                for candidate in decision.candidates
                if candidate.solver_id == decision.selected_solver_id
            ),
            None,
        )
        if chosen is None or chosen.solver is None:
            return None
        chosen.solver.reason = "; ".join(chosen.evidence)
        return chosen.solver
