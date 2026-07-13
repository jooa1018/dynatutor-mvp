from __future__ import annotations

"""Offline Phase 49 solver-path consistency and independent analytic adapters."""

from dataclasses import dataclass, field
import json
import math
import re
import unicodedata
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
PRIMARY_OUTPUT_CONTRACT = MappingProxyType(
    {
        "incline": ("acceleration",),
        "pulley": ("acceleration",),
        "collision": ("v1_after", "v2_after"),
        "rolling": ("final_velocity",),
        "work_energy": ("final_velocity",),
        "fixed_axis_rotation": ("angular_acceleration",),
    }
)
EQUATION_ROLE_CONTRACT = MappingProxyType(
    {
        "incline": ("newton_second_law_tangent",),
        "pulley": ("newton_second_law_string_system",),
        "collision": (
            "linear_momentum_conservation",
            "coefficient_of_restitution",
        ),
        "rolling": (
            "mechanical_energy_conservation",
            "pure_rolling_constraint",
            "rigid_body_inertia_model",
        ),
        "work_energy": ("work_energy_theorem",),
        "fixed_axis_rotation": ("fixed_axis_torque_balance",),
    }
)
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


def _compact_equation(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    text = value
    for source, target in (
        ("²", "^2"),
        ("⁻", "-"),
        ("Σ", "sum"),
        ("∑", "sum"),
        ("α", "alpha"),
        ("β", "beta"),
        ("ω", "omega"),
        ("θ", "theta"),
        ("μ", "mu"),
        ("τ", "tau"),
        ("Δ", "delta"),
        ("×", "*"),
        ("·", "*"),
        ("⋅", "*"),
        ("−", "-"),
        ("→", "->"),
        ("≤", "<="),
        ("≥", ">="),
    ):
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("\\left", "").replace("\\right", "")
    return re.sub(r"[\\\s_{}]", "", text)


def _normalize_unit(value: str) -> str:
    """Canonicalize notation spelling without converting dimensions or magnitude."""
    text = value
    for source, target in (
        ("²", "^2"),
        ("⁻", "-"),
        ("·", "*"),
        ("⋅", "*"),
        ("×", "*"),
        ("−", "-"),
    ):
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"\s+", "", text).replace("**", "^")
    aliases = {
        "m/s2": "m/s^2",
        "rad/s2": "rad/s^2",
    }
    return aliases.get(text, text)


def _roles_from_raw_equations(
    family: str,
    equations: Sequence[str],
) -> tuple[str, ...]:
    compact = tuple(
        item for item in (_compact_equation(value) for value in equations) if item
    )
    found: set[str] = set()
    if family == "incline":
        if any(
            equation in {
                "sumfx=ma",
                "mgsintheta=ma",
                "mgsintheta-f=ma",
                "mgsintheta-mumgcostheta=ma",
            }
            or (
                equation.endswith("=ma")
                and ("mgsintheta" in equation or "sumfx" in equation)
            )
            or (
                "mgsintheta" in equation
                and "a=0" in equation
                and ("<=" in equation or "=" in equation)
            )
            for equation in compact
        ):
            found.add("newton_second_law_tangent")
    elif family == "pulley":
        m1_balance = any(
            equation.endswith("=m1a")
            and equation.split("=", 1)[0]
            and "t" in equation.split("=", 1)[0]
            for equation in compact
        )
        m2_balance = any(
            equation.endswith("=m2a")
            and "m2g" in equation.split("=", 1)[0]
            and "t" in equation.split("=", 1)[0]
            for equation in compact
        )
        static_balance = any(
            "m1g" in equation
            and "m2g" in equation
            and "a=0" in equation
            and ("<=" in equation or "=" in equation)
            for equation in compact
        )
        if (m1_balance and m2_balance) or static_balance:
            found.add("newton_second_law_string_system")
    elif family == "collision":
        if any(
            all(token in equation for token in ("m1", "m2", "v1", "v2", "="))
            and "+" in equation
            and "e*" not in equation
            for equation in compact
        ):
            found.add("linear_momentum_conservation")
        if any(
            all(token in equation for token in ("v1", "v2", "e", "="))
            and ("after" in equation or "'" in equation)
            for equation in compact
        ):
            found.add("coefficient_of_restitution")
    elif family == "rolling":
        if any(
            "mgh=" in equation
            and "mv^2" in equation
            and ("iomega^2" in equation or "betam" in equation)
            for equation in compact
        ):
            found.add("mechanical_energy_conservation")
        if any(
            equation in {"v=omegar", "|vcm|=|omega|r"}
            or ("v=" in equation and "omegar" in equation)
            for equation in compact
        ):
            found.add("pure_rolling_constraint")
        explicit_shape = any(
            equation in {"i=betamr^2", "i=kmr^2"}
            or ("i=" in equation and "mr^2" in equation)
            for equation in compact
        )
        explicit_inertia = (
            any("iomega^2" in equation for equation in compact)
            and any("i/r^2" in equation for equation in compact)
        )
        if explicit_shape or explicit_inertia:
            found.add("rigid_body_inertia_model")
    elif family == "work_energy":
        if any(
            equation in {"w=deltak", "wnet=deltak"}
            or ("w=" in equation and "vf^2" in equation and "vi^2" in equation)
            for equation in compact
        ):
            found.add("work_energy_theorem")
    elif family == "fixed_axis_rotation":
        if any(
            equation in {"summ=ialpha", "tau=ialpha", "alpha=tau/i"}
            for equation in compact
        ):
            found.add("fixed_axis_torque_balance")
    return tuple(
        role for role in EQUATION_ROLE_CONTRACT[family] if role in found
    )


def _check_payload(check: Any) -> Mapping[str, Any]:
    if isinstance(check, Mapping):
        return check
    return {
        "category": getattr(check, "category", None),
        "status": getattr(check, "status", None),
        "source_equation_ids": getattr(check, "source_equation_ids", ()),
    }


def _derive_product_equation_roles(
    family: str,
    result: Any,
) -> tuple[tuple[str, ...], str, tuple[str, ...], tuple[str, ...]]:
    raw_value = getattr(result, "used_equations", None)
    if not isinstance(raw_value, (list, tuple)):
        raise ConsistencyContractError("result.used_equations must be a sequence")
    raw = tuple(_text(item, "result.used_equations") for item in raw_value)
    roles = _roles_from_raw_equations(family, raw)
    structured_ids: list[str] = []
    source = "SolverResult.used_equations" if raw else "none"
    if family == "collision" and not raw:
        verification = getattr(result, "verification", None)
        checks = getattr(verification, "structured_checks", ()) if verification else ()
        valid_statuses = {
            VerificationStatus.PASSED.value,
            VerificationStatus.PASSED_WITH_WARNING.value,
        }
        accepted_categories: set[str] = set()
        for raw_check in checks or ():
            check = _check_payload(raw_check)
            status = str(getattr(check.get("status"), "value", check.get("status")))
            category = str(check.get("category") or "")
            ids = check.get("source_equation_ids") or ()
            if (
                status not in valid_statuses
                or category not in {"collision_momentum", "collision_restitution"}
                or not isinstance(ids, (list, tuple))
                or not ids
            ):
                continue
            candidate_ids = tuple(str(item) for item in ids)
            mapped = set(_roles_from_raw_equations("collision", candidate_ids))
            required_role = (
                "linear_momentum_conservation"
                if category == "collision_momentum"
                else "coefficient_of_restitution"
            )
            if required_role in mapped:
                accepted_categories.add(category)
                structured_ids.extend(candidate_ids)
        role_set = set(roles)
        if "collision_momentum" in accepted_categories:
            role_set.add("linear_momentum_conservation")
        if "collision_restitution" in accepted_categories:
            role_set.add("coefficient_of_restitution")
        roles = tuple(
            role for role in EQUATION_ROLE_CONTRACT[family] if role in role_set
        )
        if accepted_categories:
            source = "VerificationReport.structured_checks"
    return roles, source, raw, tuple(structured_ids)


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
    *,
    canonical: Any,
    family: str,
    path_id: str,
    solver_id: str,
    semantic_output_keys: Sequence[str] | None = None,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
    assumptions: Sequence[str] | None = None,
    equation_ids: Sequence[str] | None = None,
    frame: str | None = None,
    positive_direction: str | None = None,
) -> SolverPathObservation:
    """Snapshot product-path evidence under the central Phase 49 contracts.

    Callers may repeat the complete primary-output contract for compatibility,
    but cannot select a fixture-specific subset.  Equation role IDs are derived
    fail-closed from actual solver or Phase 48 collision-verification evidence.
    """
    if family not in PRIMARY_OUTPUT_CONTRACT:
        raise ConsistencyContractError(f"unsupported family {family!r}")
    injected = {
        name
        for name, value in {
            "assumptions": assumptions,
            "equation_ids": equation_ids,
            "frame": frame,
            "positive_direction": positive_direction,
        }.items()
        if value is not None
    }
    if injected:
        raise ConsistencyContractError(
            "product observation metadata must be derived from actual sources; "
            f"caller overrides are forbidden: {sorted(injected)}"
        )

    primary_keys = PRIMARY_OUTPUT_CONTRACT[family]
    if semantic_output_keys is not None:
        requested_keys = _unique_strings(
            semantic_output_keys,
            "semantic_output_keys",
            allow_empty=False,
        )
        if requested_keys != primary_keys:
            raise ConsistencyContractError(
                "semantic_output_keys must equal the central primary-output "
                f"contract for {family}: {primary_keys!r}"
            )

    answers = getattr(result, "answers", None)
    if not isinstance(answers, (list, tuple)):
        raise ConsistencyContractError("result.answers must be a sequence")
    selected_set = set(primary_keys)
    selected: list[Any] = []
    ignored_keys: list[str] = []
    for item in tuple(answers):
        key = getattr(item, "output_key", None)
        if isinstance(key, str) and key in selected_set:
            selected.append(item)
        else:
            ignored_keys.append(key if isinstance(key, str) and key else "<untyped>")

    canonical_assumptions = getattr(canonical, "assumptions", None)
    if not isinstance(canonical_assumptions, (list, tuple)):
        raise ConsistencyContractError("canonical.assumptions must be a sequence")
    coordinate_data = getattr(canonical, "coordinate_data", None)
    if not isinstance(coordinate_data, Mapping):
        raise ConsistencyContractError("canonical.coordinate_data must be a mapping")
    actual_frame = coordinate_data.get("coordinate_frame", coordinate_data.get("frame"))
    actual_direction = coordinate_data.get("positive_direction")
    if not isinstance(actual_frame, str) or not actual_frame.strip():
        raise ConsistencyContractError(
            "canonical.coordinate_data must record coordinate_frame"
        )
    if not isinstance(actual_direction, str) or not actual_direction.strip():
        raise ConsistencyContractError(
            "canonical.coordinate_data must record positive_direction"
        )

    roles, equation_source, raw_equations, structured_equations = (
        _derive_product_equation_roles(family, result)
    )
    required_roles = EQUATION_ROLE_CONTRACT[family]
    missing_roles = tuple(role for role in required_roles if role not in roles)

    fallback_output: ObservedSemanticOutput | None = None
    fallback_rejected_reason: str | None = None
    if not selected and len(primary_keys) == 1:
        if missing_roles:
            fallback_rejected_reason = "required_equation_roles_missing"
        else:
            representative = getattr(result, "answer", None)
            if representative is None:
                fallback_rejected_reason = "representative_answer_missing"
            else:
                representative_numeric = getattr(representative, "numeric", None)
                representative_unit = getattr(representative, "unit", None)
                if representative_numeric is None:
                    fallback_rejected_reason = "representative_numeric_missing"
                else:
                    numeric = _finite(
                        representative_numeric,
                        "result.answer.numeric",
                    )
                    if not isinstance(representative_unit, str):
                        fallback_rejected_reason = "representative_unit_not_typed"
                    else:
                        fallback_output = ObservedSemanticOutput(
                            output_key=primary_keys[0],
                            numeric=numeric,
                            unit=representative_unit,
                            sign=_numeric_sign(numeric, policy),
                            frame=actual_frame,
                            positive_direction=actual_direction,
                            assumptions=tuple(canonical_assumptions),
                            equation_ids=roles,
                        )
    elif selected:
        fallback_rejected_reason = "typed_answer_items_present"
    else:
        fallback_rejected_reason = "multiple_semantic_keys"

    if fallback_output is not None:
        outputs = (fallback_output,)
        answer_source = "SolverResult.answer.numeric/unit"
    else:
        snapshot = observation_from_answer_items(
            tuple(selected),
            family=family,
            path_id=path_id,
            solver_id=solver_id,
            frame=actual_frame,
            positive_direction=actual_direction,
            assumptions=tuple(canonical_assumptions),
            equation_ids=roles,
            policy=policy,
        )
        outputs = snapshot.outputs
        answer_source = "SolverResult.answers[].output_key"

    return SolverPathObservation(
        path_id=path_id,
        family=family,
        solver_id=solver_id,
        outputs=outputs,
        policy_version=policy.policy_version,
        metadata={
            "source": answer_source,
            "answer_source": answer_source,
            "equation_source": equation_source,
            "equation_evidence_source": equation_source,
            "raw_equation_evidence": raw_equations,
            "structured_equation_evidence": structured_equations,
            "equation_role_ids": roles,
            "missing_equation_roles": missing_roles,
            "assumption_source": "CanonicalProblem.assumptions",
            "coordinate_source": "CanonicalProblem.coordinate_data",
            "semantic_output_keys": primary_keys,
            "ignored_output_keys": tuple(ignored_keys),
            "legacy_single_output_fallback": fallback_output is not None,
            "fallback_rejected_reason": fallback_rejected_reason,
        },
    )



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
    primary_contract = PRIMARY_OUTPUT_CONTRACT[oracle.family]
    expected_contract_keys = tuple(oracle.output_by_key)
    oracle_primary_ok = expected_contract_keys == primary_contract
    _add(
        report,
        check_id=f"{prefix}:primary_output_contract",
        category="path_contract",
        status=_same_status(oracle_primary_ok),
        observed=expected_contract_keys,
        expected=primary_contract,
        message=(
            "oracle uses the central primary-output contract"
            if oracle_primary_ok
            else "oracle violates the central primary-output contract"
        ),
        policy=policy,
    )
    required_roles = EQUATION_ROLE_CONTRACT[oracle.family]
    oracle_role_ok = all(
        tuple(output.equation_ids) == required_roles
        for output in oracle.expected_outputs
    )
    _add(
        report,
        check_id=f"{prefix}:equation_role_contract",
        category="path_contract",
        status=_same_status(oracle_role_ok),
        observed={
            output.output_key: tuple(output.equation_ids)
            for output in oracle.expected_outputs
        },
        expected=required_roles,
        message=(
            "oracle uses stable semantic equation roles"
            if oracle_role_ok
            else "oracle equation IDs violate the semantic-role contract"
        ),
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
        observed_unit = _normalize_unit(actual.unit)
        expected_unit = _normalize_unit(expected.unit)
        unit_ok = observed_unit == expected_unit
        _add(
            report,
            check_id=f"{check_prefix}:unit",
            category="unit_dimension",
            status=_same_status(unit_ok),
            observed={"raw": actual.unit, "normalized": observed_unit},
            expected={"raw": expected.unit, "normalized": expected_unit},
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
        actual_assumptions = tuple(actual.assumptions)
        expected_assumptions = tuple(expected.assumptions)
        assumptions_ok = actual_assumptions == expected_assumptions
        _add(
            report,
            check_id=f"{check_prefix}:assumptions",
            category="assumptions",
            status=_same_status(assumptions_ok),
            observed=actual_assumptions,
            expected=expected_assumptions,
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
        actual_equations = tuple(actual.equation_ids)
        expected_equations = tuple(expected.equation_ids)
        equations_ok = actual_equations == expected_equations
        _add(
            report,
            check_id=f"{check_prefix}:equations",
            category="equation_ids",
            status=_same_status(equations_ok),
            observed={
                "values": actual_equations,
                "missing": tuple(
                    role for role in expected_equations if role not in actual_equations
                ),
                "extra": tuple(
                    role for role in actual_equations if role not in expected_equations
                ),
            },
            expected=expected_equations,
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
    analytic_extras: Mapping[str, Any] | None = None,
) -> SolverPathObservation:
    path_id = f"{SECONDARY_PATH_PREFIX}{family}"
    output_tuple = tuple(outputs)
    if applicability is VerificationApplicability.APPLICABLE:
        actual_keys = tuple(output.output_key for output in output_tuple)
        if actual_keys != PRIMARY_OUTPUT_CONTRACT[family]:
            raise ConsistencyContractError(
                f"secondary {family} outputs {actual_keys!r} violate central "
                f"primary-output contract {PRIMARY_OUTPUT_CONTRACT[family]!r}"
            )
    return SolverPathObservation(
        path_id=path_id,
        family=family,
        solver_id=path_id,
        outputs=output_tuple,
        policy_version=policy.policy_version,
        applicability=applicability,
        message=message,
        metadata={
            "independent": True,
            "offline_only": True,
            "formula_ids": tuple(formula_ids),
            "analytic_extras": dict(analytic_extras or {}),
            "equation_role_ids": EQUATION_ROLE_CONTRACT[family],
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
        formulas = ("P49-INCLINE-FREE:a=g*sin(theta)",)
    elif mode == "kinetic":
        mu_k = _number(inputs, "mu_k")
        if mu_k < 0:
            raise ConsistencyContractError("mu_k must be non-negative")
        acceleration = gravity * (math.sin(theta) - mu_k * math.cos(theta))
        assumptions = ("kinetic_friction", "constant_gravity", "particle_model")
        formulas = ("P49-INCLINE-KINETIC:a=g*(sin(theta)-mu_k*cos(theta))",)
    elif mode == "static":
        mu_s = _number(inputs, "mu_s")
        if mu_s < 0:
            raise ConsistencyContractError("mu_s must be non-negative")
        drive = gravity * math.sin(theta)
        limit = mu_s * gravity * math.cos(theta)
        static_formula = "P49-INCLINE-STATIC:|g*sin(theta)|<=mu_s*g*cos(theta)"
        if drive > limit + policy.tolerance("constraint", scale=max(drive, limit, 1.0)):
            return _secondary_observation(
                "incline",
                (),
                policy=policy,
                applicability=VerificationApplicability.NOT_APPLICABLE,
                message="requested static state exceeds the static-friction limit",
                formula_ids=(static_formula,),
            )
        acceleration = 0.0
        assumptions = ("static_friction", "constant_gravity", "particle_model")
        formulas = (static_formula, "P49-INCLINE-STATIC:a=0")
    else:
        raise ConsistencyContractError(f"unsupported friction_mode {mode!r}")
    output = _semantic(
        "acceleration",
        acceleration,
        "m/s^2",
        frame,
        direction,
        assumptions,
        EQUATION_ROLE_CONTRACT["incline"],
        policy,
    )
    return _secondary_observation(
        "incline", (output,), policy=policy, formula_ids=formulas
    )


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
    extras: dict[str, Any] = {
        "tension_1": {"numeric": t1, "unit": "N"},
        "tension_2": {"numeric": t2, "unit": "N"},
    }
    if radius is not None:
        extras["angular_acceleration"] = {
            "numeric": acceleration / radius,
            "unit": "rad/s^2",
        }
    output = _semantic(
        "acceleration",
        acceleration,
        "m/s^2",
        "pulley_string",
        "mass2_down",
        assumptions,
        EQUATION_ROLE_CONTRACT["pulley"],
        policy,
    )
    return _secondary_observation(
        "pulley",
        (output,),
        policy=policy,
        formula_ids=(formula,),
        analytic_extras=extras,
    )


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
    formulas = (
        "P49-COLLISION-MOMENTUM:m1*u1+m2*u2=m1*v1+m2*v2",
        "P49-COLLISION-RESTITUTION:v2-v1=e*(u1-u2)",
    )
    roles = EQUATION_ROLE_CONTRACT["collision"]
    outputs = (
        _semantic("v1_after", v1, "m/s", "one_dimensional_lab", "right", assumptions, roles, policy),
        _semantic("v2_after", v2, "m/s", "one_dimensional_lab", "right", assumptions, roles, policy),
    )
    return _secondary_observation("collision", outputs, policy=policy, formula_ids=formulas)


def _rolling(inputs: Mapping[str, Any], policy: TolerancePolicy) -> SolverPathObservation:
    _allowed_keys(inputs, {"height", "gravity", "inertia_factor", "radius"})
    height = _number(inputs, "height")
    gravity = _number(inputs, "gravity", positive=True)
    factor = _number(inputs, "inertia_factor")
    if height < 0 or factor < 0:
        raise ConsistencyContractError("height and inertia_factor must be non-negative")
    velocity = math.sqrt(2 * gravity * height / (1 + factor))
    assumptions = ("pure_rolling", "no_energy_loss", "starts_from_rest")
    formula = "P49-ROLLING:v=sqrt(2*g*h/(1+k))"
    extras: dict[str, Any] = {}
    if "radius" in inputs:
        radius = _number(inputs, "radius", positive=True)
        extras["angular_velocity"] = {
            "numeric": velocity / radius,
            "unit": "rad/s",
        }
    output = _semantic(
        "final_velocity",
        velocity,
        "m/s",
        "path_tangent",
        "direction_of_motion",
        assumptions,
        EQUATION_ROLE_CONTRACT["rolling"],
        policy,
    )
    return _secondary_observation(
        "rolling",
        (output,),
        policy=policy,
        formula_ids=(formula,),
        analytic_extras=extras,
    )


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
    formula = "P49-WORK-ENERGY:vf^2=vi^2+2W/m"
    output = _semantic(
        "final_velocity",
        velocity,
        "m/s",
        "path_tangent",
        "direction_of_motion",
        assumptions,
        EQUATION_ROLE_CONTRACT["work_energy"],
        policy,
    )
    return _secondary_observation(
        "work_energy", (output,), policy=policy, formula_ids=(formula,)
    )


def _fixed_axis(inputs: Mapping[str, Any], policy: TolerancePolicy) -> SolverPathObservation:
    _allowed_keys(inputs, {"torque", "inertia", "initial_angular_velocity", "time", "radius"})
    torque = _number(inputs, "torque")
    inertia = _number(inputs, "inertia", positive=True)
    alpha = torque / inertia
    assumptions = ("fixed_axis", "constant_net_torque")
    formulas = ["P49-ROTATION-TORQUE:alpha=tau/I"]
    extras: dict[str, Any] = {}
    has_kinematics = "initial_angular_velocity" in inputs or "time" in inputs
    if has_kinematics:
        omega0 = _number(inputs, "initial_angular_velocity")
        time = _number(inputs, "time")
        if time < 0:
            raise ConsistencyContractError("time must be non-negative")
        omega = omega0 + alpha * time
        formulas.append("P49-ROTATION-KINEMATICS:omega=omega0+alpha*t")
        extras["angular_velocity"] = {"numeric": omega, "unit": "rad/s"}
        if "radius" in inputs:
            radius = _number(inputs, "radius", positive=True)
            formulas.append("P49-ROTATION-TANGENTIAL:v=omega*R")
            extras["tangential_velocity"] = {
                "numeric": omega * radius,
                "unit": "m/s",
            }
    elif "radius" in inputs:
        raise ConsistencyContractError("radius requires angular velocity inputs")
    output = _semantic(
        "angular_acceleration",
        alpha,
        "rad/s^2",
        "fixed_axis",
        "counterclockwise",
        assumptions,
        EQUATION_ROLE_CONTRACT["fixed_axis_rotation"],
        policy,
    )
    return _secondary_observation(
        "fixed_axis_rotation",
        (output,),
        policy=policy,
        formula_ids=tuple(formulas),
        analytic_extras=extras,
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
    "PRIMARY_OUTPUT_CONTRACT",
    "EQUATION_ROLE_CONTRACT",
    "ConsistencyContractError",
    "DisagreementReport",
    "ObservedSemanticOutput",
    "SolverPathObservation",
    "compare_oracle_observation",
    "evaluate_secondary_analytic",
    "observation_from_answer_items",
    "observation_from_solver_result",
]
