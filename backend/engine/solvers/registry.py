from dataclasses import dataclass, field
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
    solver: BaseSolver | None = field(default=None, repr=False, compare=False)


@dataclass
class RouteDecision:
    status: str
    candidates: list[RouteCandidate]
    selected_solver_id: str | None = None
    question: str | None = None
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


_ROUTING_MARGIN = 0.08
_STRICT_CAPABILITY_SOLVERS = {"massive_pulley_atwood", "projectile_motion", "incline_with_friction"}


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
        if solver_id.startswith("pulley_") or solver_id == "massive_pulley_atwood":
            return "pulley"
        if "incline" in solver_id:
            return "incline"
        if "friction" in solver_id:
            return "friction"
        if solver_id.startswith("projectile"):
            return "projectile"
        return solver_id.split("_", 1)[0]

    def _has_symbol(self, c: CanonicalProblem, symbol: str) -> bool:
        if " and " in symbol:
            return all(self._has_symbol(c, part.strip()) for part in symbol.split(" and "))
        if " or " in symbol:
            return any(self._has_symbol(c, part.strip()) for part in symbol.split(" or "))
        if symbol in {"theta", "launch_angle_deg"}:
            return "theta" in c.knowns or c.launch_angle_deg is not None
        if symbol == "friction_type":
            return bool(c.friction_type)
        if symbol == "minimum_speed request":
            return "minimum_speed" in set(c.requested_outputs or c.unknowns or [])
        if symbol == "top subtype":
            return c.subtype == "top"
        if symbol == "bottom subtype":
            return c.subtype == "bottom"
        if symbol == "explicit no_friction":
            return c.friction_type in {"none", "no_friction"} or c.subtype == "no_friction"
        if c.flags.get(symbol):
            return True
        requested_aliases = {"vf": "final_velocity", "v0": "initial_velocity", "s": "distance"}
        requested = set(c.requested_outputs or c.unknowns or [])
        if requested_aliases.get(symbol, symbol) in requested:
            return True
        return symbol in c.knowns and c.knowns[symbol].value is not None

    def _missing_requirements(self, c: CanonicalProblem, capability: dict[str, Any]) -> list[str]:
        req = capability.get("required_inputs", {})
        missing: list[str] = []
        for symbol in req.get("all_of", []):
            if not self._has_symbol(c, symbol):
                missing.append(symbol)
        any_of = req.get("any_of", [])
        if any_of and not any(self._has_symbol(c, symbol) for symbol in any_of):
            missing.append("one of: " + ", ".join(any_of))
        for condition in req.get("conditional", []):
            if "one_of" in condition and not any(self._has_symbol(c, symbol) for symbol in condition["one_of"]):
                missing.append("one of: " + ", ".join(condition["one_of"]))
            if "minimum_present" in condition:
                symbols = condition.get("symbols", [])
                if sum(1 for symbol in symbols if self._has_symbol(c, symbol)) < int(condition["minimum_present"]):
                    missing.append(f"{condition['minimum_present']} of: {', '.join(symbols)}")
        return missing

    def _requested_output_contradictions(self, c: CanonicalProblem, supported: list[str]) -> list[str]:
        requested = [item for item in (c.requested_outputs or c.unknowns or []) if item != "auto"]
        if not requested or not supported:
            return []
        aliases = {"distance": "range", "x": "range", "height": "max_height", "a": "acceleration", "alpha": "angular_acceleration", "velocity": "final_velocity", "v": "final_velocity", "vf": "final_velocity"}
        supported_set = set(supported)
        bad: list[str] = []
        for out in requested:
            normalized = aliases.get(out, out)
            acceptable = {out, normalized}
            if normalized == "final_velocity":
                acceptable.add("post_collision_velocity")
            if out == "minimum_speed":
                acceptable.add("final_velocity")
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
        matches = [m for s in self.solvers if (m := s.match(c))]
        candidates: list[RouteCandidate] = []
        for match in matches:
            solver_id = match.solver.name
            capability = self._capabilities.get(solver_id, {})
            strict = capability and solver_id in _STRICT_CAPABILITY_SOLVERS
            missing = self._missing_requirements(c, capability) if strict else []
            contradictions = self._requested_output_contradictions(c, capability.get("requested_outputs", [])) if strict else []
            risk_flags: list[str] = []
            if "generic" in match.reason.lower() or solver_id == "single_particle_newton":
                risk_flags.append("generic_fallback")
            penalty = 0.15 * len(missing) + 0.2 * len(contradictions)
            normalized = max(0.0, min(1.0, match.score / 100.0 - penalty))
            candidates.append(RouteCandidate(
                solver_id=solver_id,
                family=self._family(solver_id),
                raw_score=match.score,
                normalized_score=round(normalized, 4),
                evidence=[match.reason],
                missing_requirements=missing,
                contradictions=contradictions,
                supported_outputs=capability.get("requested_outputs", []),
                risk_flags=risk_flags,
                solver=match.solver,
            ))
        candidates.sort(key=lambda item: item.normalized_score, reverse=True)
        if unsupported:
            return RouteDecision("unsupported", candidates, reason="; ".join(unsupported))
        if not candidates:
            return RouteDecision("unsupported", [], reason="No solver matched the canonical problem.")
        viable = [cand for cand in candidates if not cand.missing_requirements and not cand.contradictions]
        if not viable:
            return RouteDecision("clarify", candidates, question=self._clarification_question(candidates), reason="Matched solvers lack required inputs or requested outputs.")
        top = viable[0]
        warnings = ["generic fallback selected"] if "generic_fallback" in top.risk_flags else []
        if len(viable) > 1:
            second = viable[1]
            if top.normalized_score - second.normalized_score < _ROUTING_MARGIN:
                return RouteDecision("clarify", candidates, question=self._clarification_question(viable), reason="Top route margin is too small.")
            if top.family != second.family and top.normalized_score - second.normalized_score < (_ROUTING_MARGIN * 2):
                return RouteDecision("clarify", candidates, question=self._clarification_question(viable), reason="Different solver families are competing.")
        return RouteDecision("select", candidates, selected_solver_id=top.solver_id, warnings=warnings)

    def select(self, c: CanonicalProblem) -> BaseSolver | None:
        decision = self.route(c)
        self.last_route_decision = decision
        if decision.status == "unsupported":
            return None
        selected_solver_id = decision.selected_solver_id
        if selected_solver_id is None and decision.candidates:
            selected_solver_id = decision.candidates[0].solver_id
        if selected_solver_id is None:
            return None
        chosen = next(cand for cand in decision.candidates if cand.solver_id == selected_solver_id)
        assert chosen.solver is not None
        chosen.solver.reason = "; ".join(chosen.evidence)
        return chosen.solver
