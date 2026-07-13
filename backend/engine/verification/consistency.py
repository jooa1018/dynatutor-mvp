from __future__ import annotations

"""Offline Phase 49 solver-path consistency and independent analytic adapters."""

from dataclasses import dataclass, field
import json
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from engine.models import VerificationReport
from engine.verification.checks import (
    ensure_structured_checks,
    record_verification_check,
)
from engine.verification.oracles import (
    PHASE49_FAMILIES,
    ExpectedSemanticOutput,
    OracleCase,
)
from engine.verification.policy import (
    DEFAULT_TOLERANCE_POLICY,
    TolerancePolicy,
)
from engine.verification.types import (
    VerificationApplicability,
    VerificationCheck,
    VerificationStatus,
)


DISAGREEMENT_REPORT_VERSION = "phase49-disagreement-report-v1"
SECONDARY_PATH_PREFIX = "phase49.secondary."
_ALLOWED_SIGNS = frozenset(
    {"positive", "negative", "zero", "nonnegative", "nonpositive", "any"}
)


class ConsistencyContractError(ValueError):
    """Raised for malformed observation or comparison contracts."""


def _text(value: Any, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ConsistencyContractError(f"{name} must be a string" + ("" if empty else " and non-empty"))
    return value.strip()


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConsistencyContractError(f"{name} must be a real number")
    number = float(value)
    if not math.isfinite(number):
        raise ConsistencyContractError(f"{name} must be finite")
    return number


def _unique_strings(
    values: Iterable[Any], name: str, *, allow_empty: bool = True
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set, frozenset)):
        raise ConsistencyContractError(f"{name} must be a sequence")
    result = tuple(_text(value, name) for value in values)
    if not allow_empty and not result:
        raise ConsistencyContractError(f"{name} must not be empty")
    if len(result) != len(set(result)):
        raise ConsistencyContractError(f"{name} contains duplicates")
    return result


def _frozen_mapping(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConsistencyContractError(f"{name} must be a mapping")
    copied: dict[str, Any] = {}
    for key, item in value.items():
        text_key = _text(key, f"{name} key")
        if isinstance(item, float) and not math.isfinite(item):
            raise ConsistencyContractError(f"{name}.{text_key} must be finite")
        if isinstance(item, Mapping):
            item = _frozen_mapping(item, f"{name}.{text_key}")
        elif isinstance(item, (list, tuple)):
            item = tuple(item)
        copied[text_key] = item
    return MappingProxyType(copied)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value"):
        return _json_safe(value.value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def _numeric_sign(value: float, policy: TolerancePolicy) -> str:
    if policy.is_near_zero(value, scale=max(abs(value), 1.0)):
        return "zero"
    return "positive" if value > 0 else "negative"


@dataclass(frozen=True)
class ObservedSemanticOutput:
    output_key: str
    numeric: float
    unit: str
    sign: str
    frame: str
    positive_direction: str
    assumptions: tuple[str, ...] = ()
    root_count: int = 1
    multiplicity: tuple[int, ...] = (1,)
    ambiguity: bool = False
    equation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_key", _text(self.output_key, "output_key"))
        object.__setattr__(self, "numeric", _finite(self.numeric, "numeric"))
        object.__setattr__(self, "unit", _text(self.unit, "unit", empty=True))
        sign = _text(self.sign, "sign").lower()
        if sign not in _ALLOWED_SIGNS:
            raise ConsistencyContractError(f"unsupported sign {sign!r}")
        object.__setattr__(self, "sign", sign)
        object.__setattr__(self, "frame", _text(self.frame, "frame"))
        object.__setattr__(
            self,
            "positive_direction",
            _text(self.positive_direction, "positive_direction"),
        )
        object.__setattr__(
            self, "assumptions", _unique_strings(self.assumptions, "assumptions")
        )
        if isinstance(self.root_count, bool) or not isinstance(self.root_count, int):
            raise ConsistencyContractError("root_count must be an integer")
        if self.root_count < 1:
            raise ConsistencyContractError("root_count must be at least one")
        multiplicity = tuple(self.multiplicity)
        if len(multiplicity) != self.root_count or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 1
            for item in multiplicity
        ):
            raise ConsistencyContractError(
                "multiplicity must contain one positive integer per root"
            )
        object.__setattr__(self, "multiplicity", multiplicity)
        if not isinstance(self.ambiguity, bool):
            raise ConsistencyContractError("ambiguity must be boolean")
        object.__setattr__(
            self, "equation_ids", _unique_strings(self.equation_ids, "equation_ids")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_key": self.output_key,
            "numeric": self.numeric,
            "unit": self.unit,
            "sign": self.sign,
            "frame": self.frame,
            "positive_direction": self.positive_direction,
            "assumptions": list(self.assumptions),
            "root_count": self.root_count,
            "multiplicity": list(self.multiplicity),
            "ambiguity": self.ambiguity,
            "equation_ids": list(self.equation_ids),
        }


@dataclass(frozen=True)
class SolverPathObservation:
    path_id: str
    family: str
    solver_id: str
    outputs: tuple[ObservedSemanticOutput, ...]
    policy_version: str
    applicability: VerificationApplicability = VerificationApplicability.APPLICABLE
    message: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    _output_by_key: Mapping[str, ObservedSemanticOutput] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "path_id", _text(self.path_id, "path_id"))
        family = _text(self.family, "family")
        if family not in PHASE49_FAMILIES:
            raise ConsistencyContractError(f"unsupported family {family!r}")
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "solver_id", _text(self.solver_id, "solver_id"))
        object.__setattr__(
            self, "policy_version", _text(self.policy_version, "policy_version")
        )
        if not isinstance(self.applicability, VerificationApplicability):
            object.__setattr__(
                self,
                "applicability",
                VerificationApplicability(self.applicability),
            )
        outputs = tuple(self.outputs)
        if not all(isinstance(item, ObservedSemanticOutput) for item in outputs):
            raise ConsistencyContractError("outputs must be typed semantic outputs")
        if self.applicability is VerificationApplicability.APPLICABLE and not outputs:
            raise ConsistencyContractError("applicable observation must contain outputs")
        keys = [item.output_key for item in outputs]
        if len(keys) != len(set(keys)):
            raise ConsistencyContractError("outputs contains duplicate output_key")
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(
            self, "_output_by_key", MappingProxyType({item.output_key: item for item in outputs})
        )
        if not isinstance(self.message, str):
            raise ConsistencyContractError("message must be a string")
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata, "metadata"))

    @property
    def output_by_key(self) -> Mapping[str, ObservedSemanticOutput]:
        return self._output_by_key

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "family": self.family,
            "solver_id": self.solver_id,
            "outputs": [item.to_dict() for item in self.outputs],
            "policy_version": self.policy_version,
            "applicability": self.applicability.value,
            "message": self.message,
            "metadata": _json_safe(self.metadata),
        }


@dataclass(frozen=True)
class DisagreementReport:
    family: str
    oracle_id: str
    expected_path_id: str
    observed_path_id: str
    oracle_version: str
    benchmark_version: str
    policy_version: str
    verification_report: VerificationReport
    report_version: str = DISAGREEMENT_REPORT_VERSION

    @property
    def passed(self) -> bool:
        return bool(self.verification_report.passed)

    @property
    def disagreements(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(dict(check))
            for check in self.verification_report.structured_checks
            if str(check.get("status")) not in {
                VerificationStatus.PASSED.value,
                VerificationStatus.PASSED_WITH_WARNING.value,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        report = self.verification_report
        return {
            "report_version": self.report_version,
            "family": self.family,
            "oracle_id": self.oracle_id,
            "expected_path_id": self.expected_path_id,
            "observed_path_id": self.observed_path_id,
            "oracle_version": self.oracle_version,
            "benchmark_version": self.benchmark_version,
            "policy_version": self.policy_version,
            "passed": self.passed,
            "verification_report": {
                "passed": report.passed,
                "dimension_summary": report.dimension_summary,
                "checks": list(report.checks),
                "warnings": list(report.warnings),
                "errors": list(report.errors),
                "structured_checks": [
                    _json_safe(dict(check)) for check in report.structured_checks
                ],
                "policy_version": report.policy_version,
            },
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )


def observation_from_answer_items(
    answer_items: Sequence[Any],
    *,
    family: str,
    path_id: str,
    solver_id: str,
    frame: str,
    positive_direction: str,
    assumptions: Sequence[str] = (),
    equation_ids: Sequence[str] = (),
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> SolverPathObservation:
    """Snapshot semantic AnswerItem fields; display text is never inspected."""
    outputs: list[ObservedSemanticOutput] = []
    for index, item in enumerate(tuple(answer_items)):
        output_key = getattr(item, "output_key", None)
        numeric = getattr(item, "numeric", None)
        if not isinstance(output_key, str) or not output_key.strip():
            raise ConsistencyContractError(
                f"answer_items[{index}] is missing semantic output_key"
            )
        value = _finite(numeric, f"answer_items[{index}].numeric")
        unit = getattr(item, "unit", "")
        outputs.append(
            ObservedSemanticOutput(
                output_key=output_key,
                numeric=value,
                unit="" if unit is None else unit,
                sign=_numeric_sign(value, policy),
                frame=frame,
                positive_direction=positive_direction,
                assumptions=tuple(assumptions),
                equation_ids=tuple(equation_ids),
            )
        )
    return SolverPathObservation(
        path_id=path_id,
        family=family,
        solver_id=solver_id,
        outputs=tuple(outputs),
        policy_version=policy.policy_version,
        metadata={"source": "AnswerItem.output_key"},
    )


def observation_from_solver_result(
    result: Any,
    **kwargs: Any,
) -> SolverPathObservation:
    """Adapt a result through typed answer items without mutating it."""
    answers = getattr(result, "answers", None)
    if not isinstance(answers, (list, tuple)):
        raise ConsistencyContractError("result.answers must be a sequence")
    return observation_from_answer_items(tuple(answers), **kwargs)


def _add(
    report: VerificationReport,
    *,
    check_id: str,
    category: str,
    status: VerificationStatus,
    observed: Any,
    expected: Any,
    message: str,
    policy: TolerancePolicy,
    applicability: VerificationApplicability = VerificationApplicability.APPLICABLE,
    absolute_error: float | None = None,
    relative_error: float | None = None,
    tolerance: float | None = None,
    evidence: Sequence[str] = (),
    equation_ids: Sequence[str] = (),
) -> None:
    record_verification_check(
        report,
        VerificationCheck(
            check_id=check_id,
            category=category,
            status=status,
            applicability=applicability,
            observed=observed,
            expected=expected,
            absolute_error=absolute_error,
            relative_error=relative_error,
            tolerance=tolerance,
            message=message,
            evidence=tuple(evidence),
            source_equation_ids=tuple(equation_ids),
            metadata={"policy_version": policy.policy_version, "offline_only": True},
        ),
    )


def _same_status(equal: bool) -> VerificationStatus:
    return VerificationStatus.PASSED if equal else VerificationStatus.FAILED


def compare_oracle_observation(
    oracle: OracleCase,
    observed: SolverPathObservation,
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> DisagreementReport:
    """Compare independent expectations with one semantic product-path snapshot."""
    report = VerificationReport(passed=True, policy_version=policy.policy_version)
    prefix = f"phase49:{oracle.oracle_id}"
    if oracle.policy_version != policy.policy_version or observed.policy_version != policy.policy_version:
        _add(
            report,
            check_id=f"{prefix}:policy",
            category="policy",
            status=VerificationStatus.ERROR,
            observed={
                "oracle": oracle.policy_version,
                "observation": observed.policy_version,
            },
            expected=policy.policy_version,
            message="comparison policy version mismatch",
            policy=policy,
        )
    if observed.family != oracle.family:
        _add(
            report,
            check_id=f"{prefix}:family",
            category="path_contract",
            status=VerificationStatus.ERROR,
            observed=observed.family,
            expected=oracle.family,
            message="solver path family does not match oracle family",
            policy=policy,
        )
    if observed.applicability is not VerificationApplicability.APPLICABLE:
        status = (
            VerificationStatus.NOT_APPLICABLE
            if observed.applicability is VerificationApplicability.NOT_APPLICABLE
            else VerificationStatus.INCONCLUSIVE
        )
        _add(
            report,
            check_id=f"{prefix}:applicability",
            category="applicability",
            status=status,
            applicability=observed.applicability,
            observed=observed.message,
            expected="applicable complete observation",
            message=observed.message or "required observation is not applicable",
            policy=policy,
        )
        report.passed = False
        return DisagreementReport(
            family=oracle.family,
            oracle_id=oracle.oracle_id,
            expected_path_id=f"{SECONDARY_PATH_PREFIX}{oracle.family}",
            observed_path_id=observed.path_id,
            oracle_version=oracle.oracle_version,
            benchmark_version=oracle.benchmark_version,
            policy_version=policy.policy_version,
            verification_report=ensure_structured_checks(report, prefix=prefix),
        )

    expected_keys = set(oracle.output_by_key)
    observed_keys = set(observed.output_by_key)
    missing = sorted(expected_keys - observed_keys)
    extra = sorted(observed_keys - expected_keys)
    output_sets_equal = not missing and not extra
    _add(
        report,
        check_id=f"{prefix}:semantic_outputs",
        category="semantic_outputs",
        status=_same_status(output_sets_equal),
        observed={"keys": sorted(observed_keys), "missing": missing, "extra": extra},
        expected=sorted(expected_keys),
        message=(
            "semantic output keys agree"
            if output_sets_equal
            else "missing or extra semantic output keys"
        ),
        policy=policy,
    )

    for output_key in sorted(expected_keys & observed_keys):
        expected: ExpectedSemanticOutput = oracle.output_by_key[output_key]
        actual = observed.output_by_key[output_key]
        check_prefix = f"{prefix}:{output_key}"
        scale = max(abs(expected.numeric), abs(actual.numeric), 1.0)
        tolerance = policy.tolerance(
            "absolute", scale=scale, engine_id=observed.solver_id
        )
        absolute_error = abs(actual.numeric - expected.numeric)
        denominator = max(abs(expected.numeric), policy.near_zero_tol)
        relative_error = absolute_error / denominator
        numeric_ok = absolute_error <= tolerance
        _add(
            report,
            check_id=f"{check_prefix}:numeric",
            category="numeric",
            status=_same_status(numeric_ok),
            observed=actual.numeric,
            expected=expected.numeric,
            absolute_error=absolute_error,
            relative_error=relative_error,
            tolerance=tolerance,
            message="numeric value agrees" if numeric_ok else "numeric disagreement",
            policy=policy,
            evidence=(oracle.derivation, oracle.independence_note),
            equation_ids=expected.equation_ids,
        )
        unit_ok = actual.unit.strip() == expected.unit.strip()
        _add(
            report,
            check_id=f"{check_prefix}:unit",
            category="unit_dimension",
            status=_same_status(unit_ok),
            observed=actual.unit,
            expected=expected.unit,
            message="unit agrees" if unit_ok else "unit or dimension disagreement",
            policy=policy,
            equation_ids=expected.equation_ids,
        )
        sign_ok = (
            expected.sign == "any"
            or actual.sign == expected.sign
            or expected.sign == "nonnegative" and actual.sign in {"positive", "zero", "nonnegative"}
            or expected.sign == "nonpositive" and actual.sign in {"negative", "zero", "nonpositive"}
        )
        _add(
            report,
            check_id=f"{check_prefix}:sign",
            category="sign",
            status=_same_status(sign_ok),
            observed=actual.sign,
            expected=expected.sign,
            message="sign convention agrees" if sign_ok else "sign disagreement",
            policy=policy,
        )
        frame_ok = actual.frame == expected.frame
        _add(
            report,
            check_id=f"{check_prefix}:frame",
            category="coordinate_frame",
            status=_same_status(frame_ok),
            observed=actual.frame,
            expected=expected.frame,
            message="coordinate frame agrees" if frame_ok else "coordinate frame disagreement",
            policy=policy,
        )
        direction_ok = actual.positive_direction == expected.positive_direction
        _add(
            report,
            check_id=f"{check_prefix}:positive_direction",
            category="positive_direction",
            status=_same_status(direction_ok),
            observed=actual.positive_direction,
            expected=expected.positive_direction,
            message="positive direction agrees" if direction_ok else "positive direction disagreement",
            policy=policy,
        )
        actual_assumptions = set(actual.assumptions)
        expected_assumptions = set(expected.assumptions)
        assumptions_ok = actual_assumptions == expected_assumptions
        _add(
            report,
            check_id=f"{check_prefix}:assumptions",
            category="assumptions",
            status=_same_status(assumptions_ok),
            observed={
                "values": sorted(actual_assumptions),
                "missing": sorted(expected_assumptions - actual_assumptions),
                "extra": sorted(actual_assumptions - expected_assumptions),
            },
            expected=sorted(expected_assumptions),
            message="assumptions agree" if assumptions_ok else "assumption disagreement",
            policy=policy,
        )
        roots_ok = (
            actual.root_count == expected.root_count
            and actual.multiplicity == expected.multiplicity
        )
        _add(
            report,
            check_id=f"{check_prefix}:roots",
            category="root_structure",
            status=_same_status(roots_ok),
            observed={
                "root_count": actual.root_count,
                "multiplicity": list(actual.multiplicity),
            },
            expected={
                "root_count": expected.root_count,
                "multiplicity": list(expected.multiplicity),
            },
            message="root structure agrees" if roots_ok else "root count or multiplicity disagreement",
            policy=policy,
        )
        ambiguity_ok = actual.ambiguity == expected.ambiguity
        _add(
            report,
            check_id=f"{check_prefix}:ambiguity",
            category="ambiguity",
            status=_same_status(ambiguity_ok),
            observed=actual.ambiguity,
            expected=expected.ambiguity,
            message="ambiguity classification agrees" if ambiguity_ok else "ambiguity disagreement",
            policy=policy,
        )
        actual_equations = set(actual.equation_ids)
        expected_equations = set(expected.equation_ids)
        equations_ok = actual_equations == expected_equations
        _add(
            report,
            check_id=f"{check_prefix}:equations",
            category="equation_ids",
            status=_same_status(equations_ok),
            observed={
                "values": sorted(actual_equations),
                "missing": sorted(expected_equations - actual_equations),
                "extra": sorted(actual_equations - expected_equations),
            },
            expected=sorted(expected_equations),
            message="equation IDs agree" if equations_ok else "equation ID disagreement",
            policy=policy,
        )

    ensure_structured_checks(report, prefix=prefix)
    accepted = {
        VerificationStatus.PASSED.value,
        VerificationStatus.PASSED_WITH_WARNING.value,
    }
    report.passed = bool(report.structured_checks) and all(
        str(check.get("status")) in accepted for check in report.structured_checks
    )
    return DisagreementReport(
        family=oracle.family,
        oracle_id=oracle.oracle_id,
        expected_path_id=f"{SECONDARY_PATH_PREFIX}{oracle.family}",
        observed_path_id=observed.path_id,
        oracle_version=oracle.oracle_version,
        benchmark_version=oracle.benchmark_version,
        policy_version=policy.policy_version,
        verification_report=report,
    )


def _number(inputs: Mapping[str, Any], key: str, *, positive: bool = False) -> float:
    if key not in inputs:
        raise ConsistencyContractError(f"missing canonical input {key!r}")
    value = _finite(inputs[key], f"canonical_inputs.{key}")
    if positive and value <= 0:
        raise ConsistencyContractError(f"canonical_inputs.{key} must be positive")
    return value


def _allowed_keys(inputs: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(inputs) - allowed
    if unknown:
        raise ConsistencyContractError(f"unknown canonical inputs: {sorted(unknown)}")


def _angle(inputs: Mapping[str, Any]) -> float:
    present = [key for key in ("angle_rad", "angle_deg") if key in inputs]
    if len(present) != 1:
        raise ConsistencyContractError("exactly one of angle_rad or angle_deg is required")
    theta = _number(inputs, present[0])
    if present[0] == "angle_deg":
        theta = math.radians(theta)
    if not 0 <= theta < math.pi / 2:
        raise ConsistencyContractError("incline angle must be in [0, pi/2)")
    return theta


def _semantic(
    output_key: str,
    numeric: float,
    unit: str,
    frame: str,
    positive_direction: str,
    assumptions: Sequence[str],
    equation_ids: Sequence[str],
    policy: TolerancePolicy,
) -> ObservedSemanticOutput:
    return ObservedSemanticOutput(
        output_key=output_key,
        numeric=numeric,
        unit=unit,
        sign=_numeric_sign(numeric, policy),
        frame=frame,
        positive_direction=positive_direction,
        assumptions=tuple(assumptions),
        equation_ids=tuple(equation_ids),
    )


def _secondary_observation(
    family: str,
    outputs: Sequence[ObservedSemanticOutput],
    *,
    policy: TolerancePolicy,
    applicability: VerificationApplicability = VerificationApplicability.APPLICABLE,
    message: str = "",
    formula_ids: Sequence[str] = (),
) -> SolverPathObservation:
    path_id = f"{SECONDARY_PATH_PREFIX}{family}"
    return SolverPathObservation(
        path_id=path_id,
        family=family,
        solver_id=path_id,
        outputs=tuple(outputs),
        policy_version=policy.policy_version,
        applicability=applicability,
        message=message,
        metadata={
            "independent": True,
            "offline_only": True,
            "formula_ids": tuple(formula_ids),
        },
    )


def _incline(inputs: Mapping[str, Any], policy: TolerancePolicy) -> SolverPathObservation:
    _allowed_keys(inputs, {"gravity", "angle_rad", "angle_deg", "friction_mode", "mu_k", "mu_s"})
    gravity = _number(inputs, "gravity", positive=True)
    theta = _angle(inputs)
    mode = _text(inputs.get("friction_mode", "frictionless"), "friction_mode")
    frame = "incline_tangent"
    direction = "down_slope"
    if mode == "frictionless":
        acceleration = gravity * math.sin(theta)
        assumptions = ("frictionless", "constant_gravity", "particle_model")
        equations = ("P49-INCLINE-FREE:a=g*sin(theta)",)
    elif mode == "kinetic":
        mu_k = _number(inputs, "mu_k")
        if mu_k < 0:
            raise ConsistencyContractError("mu_k must be non-negative")
        acceleration = gravity * (math.sin(theta) - mu_k * math.cos(theta))
        assumptions = ("kinetic_friction", "constant_gravity", "particle_model")
        equations = ("P49-INCLINE-KINETIC:a=g*(sin(theta)-mu_k*cos(theta))",)
    elif mode == "static":
        mu_s = _number(inputs, "mu_s")
        if mu_s < 0:
            raise ConsistencyContractError("mu_s must be non-negative")
        drive = gravity * math.sin(theta)
        limit = mu_s * gravity * math.cos(theta)
        if drive > limit + policy.tolerance("constraint", scale=max(drive, limit, 1.0)):
            return _secondary_observation(
                "incline",
                (),
                policy=policy,
                applicability=VerificationApplicability.NOT_APPLICABLE,
                message="requested static state exceeds the static-friction limit",
                formula_ids=("P49-INCLINE-STATIC:|g*sin(theta)|<=mu_s*g*cos(theta)",),
            )
        acceleration = 0.0
        assumptions = ("static_friction", "constant_gravity", "particle_model")
        equations = ("P49-INCLINE-STATIC:a=0",)
    else:
        raise ConsistencyContractError(f"unsupported friction_mode {mode!r}")
    output = _semantic(
        "acceleration", acceleration, "m/s^2", frame, direction, assumptions, equations, policy
    )
    return _secondary_observation("incline", (output,), policy=policy, formula_ids=equations)


def _pulley(inputs: Mapping[str, Any], policy: TolerancePolicy) -> SolverPathObservation:
    _allowed_keys(inputs, {"m1", "m2", "gravity", "pulley_inertia", "pulley_radius"})
    m1 = _number(inputs, "m1", positive=True)
    m2 = _number(inputs, "m2", positive=True)
    gravity = _number(inputs, "gravity", positive=True)
    has_inertia = "pulley_inertia" in inputs or "pulley_radius" in inputs
    if has_inertia and not {"pulley_inertia", "pulley_radius"} <= set(inputs):
        raise ConsistencyContractError("massive pulley requires inertia and radius")
    if has_inertia:
        inertia = _number(inputs, "pulley_inertia")
        radius = _number(inputs, "pulley_radius", positive=True)
        if inertia < 0:
            raise ConsistencyContractError("pulley_inertia must be non-negative")
        denominator = m1 + m2 + inertia / radius**2
        assumptions = ("massless_string", "no_slip", "frictionless_axle", "rigid_pulley")
        formula = "P49-PULLEY-MASSIVE:a=(m2-m1)*g/(m1+m2+I/R^2)"
    else:
        radius = None
        denominator = m1 + m2
        assumptions = ("massless_string", "massless_pulley", "frictionless_axle")
        formula = "P49-PULLEY-IDEAL:a=(m2-m1)*g/(m1+m2)"
    acceleration = (m2 - m1) * gravity / denominator
    t1 = m1 * (gravity + acceleration)
    t2 = m2 * (gravity - acceleration)
    outputs = [
        _semantic("acceleration", acceleration, "m/s^2", "pulley_string", "mass2_down", assumptions, (formula,), policy),
        _semantic("tension_1", t1, "N", "pulley_string", "away_from_mass1", assumptions, ("P49-PULLEY-T1:T1=m1*(g+a)",), policy),
        _semantic("tension_2", t2, "N", "pulley_string", "away_from_mass2", assumptions, ("P49-PULLEY-T2:T2=m2*(g-a)",), policy),
    ]
    if radius is not None:
        outputs.append(
            _semantic(
                "angular_acceleration",
                acceleration / radius,
                "rad/s^2",
                "pulley_axis",
                "mass2_down_rotation",
                assumptions,
                ("P49-PULLEY-NOSLIP:alpha=a/R",),
                policy,
            )
        )
    return _secondary_observation("pulley", outputs, policy=policy, formula_ids=(formula,))


def _collision(inputs: Mapping[str, Any], policy: TolerancePolicy) -> SolverPathObservation:
    _allowed_keys(inputs, {"m1", "m2", "v1_before", "v2_before", "restitution"})
    m1 = _number(inputs, "m1", positive=True)
    m2 = _number(inputs, "m2", positive=True)
    u1 = _number(inputs, "v1_before")
    u2 = _number(inputs, "v2_before")
    restitution = _number(inputs, "restitution")
    if not 0 <= restitution <= 1:
        raise ConsistencyContractError("restitution must be in [0, 1]")
    denominator = m1 + m2
    v1 = (m1 * u1 + m2 * u2 - m2 * restitution * (u1 - u2)) / denominator
    v2 = (m1 * u1 + m2 * u2 + m1 * restitution * (u1 - u2)) / denominator
    assumptions = ("one_dimensional_impact", "isolated_during_impact", "newton_restitution")
    equations = (
        "P49-COLLISION-MOMENTUM:m1*u1+m2*u2=m1*v1+m2*v2",
        "P49-COLLISION-RESTITUTION:v2-v1=e*(u1-u2)",
    )
    outputs = (
        _semantic("v1_after", v1, "m/s", "one_dimensional_lab", "right", assumptions, equations, policy),
        _semantic("v2_after", v2, "m/s", "one_dimensional_lab", "right", assumptions, equations, policy),
    )
    return _secondary_observation("collision", outputs, policy=policy, formula_ids=equations)


def _rolling(inputs: Mapping[str, Any], policy: TolerancePolicy) -> SolverPathObservation:
    _allowed_keys(inputs, {"height", "gravity", "inertia_factor", "radius"})
    height = _number(inputs, "height")
    gravity = _number(inputs, "gravity", positive=True)
    factor = _number(inputs, "inertia_factor")
    if height < 0 or factor < 0:
        raise ConsistencyContractError("height and inertia_factor must be non-negative")
    velocity = math.sqrt(2 * gravity * height / (1 + factor))
    assumptions = ("pure_rolling", "no_energy_loss", "starts_from_rest")
    equation = "P49-ROLLING:v=sqrt(2*g*h/(1+k))"
    outputs = [
        _semantic("final_velocity", velocity, "m/s", "path_tangent", "direction_of_motion", assumptions, (equation,), policy)
    ]
    if "radius" in inputs:
        radius = _number(inputs, "radius", positive=True)
        outputs.append(
            _semantic(
                "angular_velocity",
                velocity / radius,
                "rad/s",
                "body_center",
                "rolling_rotation",
                assumptions,
                ("P49-ROLLING-NOSLIP:omega=v/R",),
                policy,
            )
        )
    return _secondary_observation("rolling", outputs, policy=policy, formula_ids=(equation,))


def _work_energy(inputs: Mapping[str, Any], policy: TolerancePolicy) -> SolverPathObservation:
    _allowed_keys(inputs, {"mass", "initial_velocity", "net_work"})
    mass = _number(inputs, "mass", positive=True)
    initial = _number(inputs, "initial_velocity")
    work = _number(inputs, "net_work")
    radicand = initial**2 + 2 * work / mass
    threshold = policy.tolerance("absolute", scale=max(initial**2, abs(2 * work / mass), 1.0))
    if radicand < -threshold:
        return _secondary_observation(
            "work_energy",
            (),
            policy=policy,
            applicability=VerificationApplicability.NOT_APPLICABLE,
            message="specified final state is unreachable with the supplied net work",
            formula_ids=("P49-WORK-ENERGY:vf^2=vi^2+2W/m",),
        )
    velocity = math.sqrt(max(radicand, 0.0))
    assumptions = ("particle_model", "net_work_known", "speed_is_nonnegative")
    equation = "P49-WORK-ENERGY:vf^2=vi^2+2W/m"
    output = _semantic(
        "final_velocity", velocity, "m/s", "path_tangent", "direction_of_motion", assumptions, (equation,), policy
    )
    return _secondary_observation("work_energy", (output,), policy=policy, formula_ids=(equation,))


def _fixed_axis(inputs: Mapping[str, Any], policy: TolerancePolicy) -> SolverPathObservation:
    _allowed_keys(inputs, {"torque", "inertia", "angular_acceleration", "initial_angular_velocity", "time", "radius"})
    if "angular_acceleration" in inputs:
        alpha = _number(inputs, "angular_acceleration")
        alpha_equation = "P49-ROTATION-GIVEN:alpha=given"
        assumptions = ("fixed_axis", "constant_angular_acceleration")
    else:
        torque = _number(inputs, "torque")
        inertia = _number(inputs, "inertia", positive=True)
        alpha = torque / inertia
        alpha_equation = "P49-ROTATION-TORQUE:alpha=tau/I"
        assumptions = ("fixed_axis", "constant_net_torque")
    outputs = [
        _semantic("angular_acceleration", alpha, "rad/s^2", "fixed_axis", "counterclockwise", assumptions, (alpha_equation,), policy)
    ]
    if "initial_angular_velocity" in inputs or "time" in inputs:
        omega0 = _number(inputs, "initial_angular_velocity")
        time = _number(inputs, "time")
        if time < 0:
            raise ConsistencyContractError("time must be non-negative")
        omega = omega0 + alpha * time
        outputs.append(
            _semantic(
                "angular_velocity",
                omega,
                "rad/s",
                "fixed_axis",
                "counterclockwise",
                assumptions,
                ("P49-ROTATION-KINEMATICS:omega=omega0+alpha*t",),
                policy,
            )
        )
        if "radius" in inputs:
            radius = _number(inputs, "radius", positive=True)
            outputs.append(
                _semantic(
                    "tangential_velocity",
                    omega * radius,
                    "m/s",
                    "body_tangent",
                    "counterclockwise_tangent",
                    assumptions,
                    ("P49-ROTATION-TANGENTIAL:v=omega*R",),
                    policy,
                )
            )
    elif "radius" in inputs:
        raise ConsistencyContractError("radius requires angular velocity inputs")
    return _secondary_observation(
        "fixed_axis_rotation", outputs, policy=policy, formula_ids=(alpha_equation,)
    )


_SECONDARY_ADAPTERS = MappingProxyType(
    {
        "incline": _incline,
        "pulley": _pulley,
        "collision": _collision,
        "rolling": _rolling,
        "work_energy": _work_energy,
        "fixed_axis_rotation": _fixed_axis,
    }
)


def evaluate_secondary_analytic(
    family: str,
    canonical_inputs: Mapping[str, Any],
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> SolverPathObservation:
    """Evaluate a Phase 49 closed form without calling production solver paths."""
    if family not in PHASE49_FAMILIES:
        raise ConsistencyContractError(f"unsupported family {family!r}")
    if not isinstance(canonical_inputs, Mapping):
        raise ConsistencyContractError("canonical_inputs must be a mapping")
    try:
        return _SECONDARY_ADAPTERS[family](dict(canonical_inputs), policy)
    except ConsistencyContractError as exc:
        return _secondary_observation(
            family,
            (),
            policy=policy,
            applicability=VerificationApplicability.UNDETERMINED,
            message=str(exc),
            formula_ids=(),
        )


__all__ = [
    "DISAGREEMENT_REPORT_VERSION",
    "SECONDARY_PATH_PREFIX",
    "ConsistencyContractError",
    "DisagreementReport",
    "ObservedSemanticOutput",
    "SolverPathObservation",
    "compare_oracle_observation",
    "evaluate_secondary_analytic",
    "observation_from_answer_items",
    "observation_from_solver_result",
]
