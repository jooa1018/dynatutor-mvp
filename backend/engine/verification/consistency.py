from __future__ import annotations

"""Offline Phase 49 solver-path consistency and independent analytic adapters."""

from dataclasses import dataclass, field
import json
import math
import re
import unicodedata
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from engine.capabilities.loader import load_capability_matrix
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


DISAGREEMENT_REPORT_VERSION = "phase49-disagreement-report-v2"
CROSS_PATH_REPORT_VERSION = "phase49-cross-path-report-v1"
THREE_WAY_REPORT_VERSION = "phase49-three-way-report-v1"
SECONDARY_PATH_PREFIX = "phase49.secondary."
PRODUCT_PATH_PREFIX = "student."
ORACLE_PATH_PREFIX = "phase49.oracle."
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


def _require_central_policy(policy: TolerancePolicy) -> None:
    if not isinstance(policy, TolerancePolicy):
        raise ConsistencyContractError("policy must be the central tolerance policy")
    if policy.to_dict() != DEFAULT_TOLERANCE_POLICY.to_dict():
        raise ConsistencyContractError(
            "policy values must exactly match the central tolerance policy"
        )


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


def _numbers_close(
    left: float,
    right: float,
    policy: TolerancePolicy,
    *,
    engine_id: str | None = None,
) -> bool:
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) <= policy.tolerance(
        "absolute", scale=scale, engine_id=engine_id
    )


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
        ("√", "sqrt"),
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


_RAW_EQUATION_SIGNATURES = MappingProxyType(
    {
        "incline": (
            ("sumfx=ma", "mgsintheta=ma", "a=gsintheta"),
            ("mgsintheta<=musmgcostheta->a=0",),
            ("n=mgcostheta", "f=mun", "mgsintheta-f=ma"),
        ),
        "pulley": (
            ("m2g-t=m2a", "t-m1g=m1a"),
            ("t1-m1g=m1a", "m2g-t2=m2a", "(t2-t1)r=i(a/r)"),
        ),
        "collision": (
            (
                "m1*v1+m2*v2=m1*v1after+m2*v2after",
                "v2after-v1after=e*(v1-v2)",
            ),
        ),
        "rolling": (
            (
                "mgh=1/2mv^2+1/2iomega^2",
                "v=omegar",
                "i=betamr^2",
            ),
            (
                "mgh=1/2mv^2+1/2iomega^2",
                "v=omegar",
                "v=sqrt(2mgh/(m+i/r^2))",
            ),
        ),
        "work_energy": (
            ("w=deltak", "vf=sqrt(vi^2+2w/m)"),
        ),
        "fixed_axis_rotation": (("summ=ialpha",),),
    }
)
_COLLISION_STRUCTURED_ROLE_BY_SIGNATURE = MappingProxyType(
    {
        "m1*v1+m2*v2=m1*v1after+m2*v2after": (
            "collision_momentum",
            "collision_momentum:linear",
            "linear_momentum_conservation",
        ),
        "v2after-v1after=e*(v1-v2)": (
            "collision_restitution",
            "collision_restitution:relative_velocity",
            "coefficient_of_restitution",
        ),
    }
)


def _roles_from_raw_equations(
    family: str,
    equations: Sequence[str],
) -> tuple[str, ...]:
    """Return roles only for an exact selected-solver semantic signature."""
    compact = tuple(
        item for item in (_compact_equation(value) for value in equations) if item
    )
    if compact not in _RAW_EQUATION_SIGNATURES[family]:
        return ()
    return EQUATION_ROLE_CONTRACT[family]


def _check_payload(check: Any) -> Mapping[str, Any]:
    if isinstance(check, Mapping):
        return check
    return {
        "check_id": getattr(check, "check_id", None),
        "category": getattr(check, "category", None),
        "status": getattr(check, "status", None),
        "applicability": getattr(check, "applicability", None),
        "source_equation_ids": getattr(check, "source_equation_ids", ()),
        "metadata": getattr(check, "metadata", {}),
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
        report_policy = getattr(verification, "policy_version", None)
        report_passed = getattr(verification, "passed", None) is True
        accepted_by_role: dict[str, list[str]] = {}
        for raw_check in checks or ():
            check = _check_payload(raw_check)
            status = str(getattr(check.get("status"), "value", check.get("status")))
            applicability = str(
                getattr(
                    check.get("applicability"),
                    "value",
                    check.get("applicability"),
                )
            )
            check_id = str(check.get("check_id") or "")
            category = str(check.get("category") or "")
            ids = check.get("source_equation_ids") or ()
            metadata = check.get("metadata") or {}
            if (
                report_policy != DEFAULT_TOLERANCE_POLICY.policy_version
                or not report_passed
                or status not in valid_statuses
                or applicability != VerificationApplicability.APPLICABLE.value
                or not isinstance(ids, (list, tuple))
                or len(ids) != 1
                or not isinstance(metadata, Mapping)
                or metadata.get("policy_version")
                != DEFAULT_TOLERANCE_POLICY.policy_version
            ):
                continue
            raw_id = ids[0]
            if not isinstance(raw_id, str) or not raw_id.strip():
                continue
            signature = _compact_equation(raw_id)
            expected = _COLLISION_STRUCTURED_ROLE_BY_SIGNATURE.get(signature)
            if (
                expected is None
                or expected[0] != category
                or expected[1] != check_id
            ):
                continue
            accepted_by_role.setdefault(expected[2], []).append(raw_id.strip())
        accepted_roles = {
            role for role, evidence in accepted_by_role.items() if len(evidence) == 1
        }
        structured_ids = [
            accepted_by_role[role][0]
            for role in EQUATION_ROLE_CONTRACT[family]
            if role in accepted_roles
        ]
        roles = tuple(
            role for role in EQUATION_ROLE_CONTRACT[family] if role in accepted_roles
        )
        if roles:
            source = "VerificationReport.structured_checks"
    return roles, source, raw, tuple(structured_ids)


@dataclass(frozen=True)
class _SelectionRootEvidence:
    outcome: str
    root_values_by_key: Mapping[str, tuple[float, ...]]
    multiplicity: tuple[int, ...]
    ambiguity: bool
    candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    selection_status: str


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _sequence_field(value: Any, name: str) -> tuple[Any, ...]:
    raw = _field(value, name, ())
    if not isinstance(raw, (list, tuple)):
        raise ConsistencyContractError(
            f"selection_decision.{name} must be a sequence"
        )
    return tuple(raw)


def _candidate_record(value: Any, *, rejected: bool = False) -> Any:
    if rejected:
        nested = _field(value, "candidate", None)
        if nested is not None:
            return nested
    return value


def _candidate_id(value: Any, name: str) -> str:
    candidate_id = _field(value, "candidate_id", None)
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ConsistencyContractError(f"{name} is missing candidate_id")
    return candidate_id.strip()


def _selection_root_evidence(
    result: Any,
    primary_keys: tuple[str, ...],
    selected_items: Sequence[Any],
    *,
    policy: TolerancePolicy,
) -> _SelectionRootEvidence:
    """Read complete physical roots only from the Phase 47 decision object."""
    decision = getattr(result, "selection_decision", None)
    if decision is None:
        raise ConsistencyContractError(
            "result.selection_decision is required Phase 47 evidence"
        )
    status = _field(decision, "status", None)
    if status != "selected":
        raise ConsistencyContractError(
            "result.selection_decision must be selected; "
            f"observed {status!r}"
        )
    decision_policy = _field(decision, "policy_version", None)
    if decision_policy != policy.policy_version:
        raise ConsistencyContractError(
            "selection_decision policy_version does not match the central policy"
        )
    selected_candidate = _field(decision, "selected_candidate", None)
    if selected_candidate is None:
        raise ConsistencyContractError(
            "selected selection_decision requires selected_candidate"
        )
    alternatives = _sequence_field(decision, "valid_alternatives")
    rejected = tuple(
        _candidate_record(item, rejected=True)
        for item in _sequence_field(decision, "rejected_candidates")
    )
    records = (selected_candidate,) + alternatives

    aliases: dict[str, list[str]] = {key: [key] for key in primary_keys}
    selected_numeric: dict[str, float] = {}
    for index, item in enumerate(tuple(selected_items)):
        key = getattr(item, "output_key", None)
        if key not in aliases:
            continue
        symbol = getattr(item, "symbol", None)
        if isinstance(symbol, str) and symbol.strip() and symbol not in aliases[key]:
            aliases[key].append(symbol)
        numeric = getattr(item, "numeric", None)
        if numeric is not None:
            selected_numeric[key] = _finite(
                numeric, f"selected answer item {index} numeric"
            )
    representative = getattr(result, "answer", None)
    if len(primary_keys) == 1 and primary_keys[0] not in selected_numeric:
        numeric = getattr(representative, "numeric", None) if representative else None
        if numeric is not None:
            selected_numeric[primary_keys[0]] = _finite(
                numeric, "result.answer.numeric"
            )

    rows: list[tuple[int | None, str, Mapping[str, float], int | None]] = []
    seen_ids: set[str] = set()
    selected_id = _candidate_id(selected_candidate, "selected candidate")
    for index, candidate in enumerate(records):
        candidate_id = _candidate_id(candidate, f"selection candidate {index}")
        if candidate_id in seen_ids:
            raise ConsistencyContractError(
                "selection_decision contains duplicate candidate_id"
            )
        seen_ids.add(candidate_id)
        mapping = _field(candidate, "numerical_mapping", None)
        if not isinstance(mapping, Mapping):
            raise ConsistencyContractError(
                f"selection candidate {candidate_id} lacks numerical_mapping"
            )
        values: dict[str, float] = {}
        for key in primary_keys:
            direct_aliases = [alias for alias in aliases[key] if alias in mapping]
            if direct_aliases:
                matches = [
                    _finite(mapping[alias], f"selection candidate {candidate_id}.{alias}")
                    for alias in direct_aliases
                ]
                if any(
                    not _numbers_close(value, matches[0], policy)
                    for value in matches[1:]
                ):
                    raise ConsistencyContractError(
                        f"selection candidate {candidate_id} has conflicting aliases for {key}"
                    )
                values[key] = matches[0]
                continue
            raise ConsistencyContractError(
                f"selection candidate {candidate_id} lacks root value for {key}"
            )
        branch = _field(candidate, "branch_info", None)
        if branch is None:
            branch = _field(candidate, "branch_information", {})
        if not isinstance(branch, Mapping):
            raise ConsistencyContractError(
                f"selection candidate {candidate_id} branch information must be a mapping"
            )
        root_index = branch.get("root_index")
        if root_index is not None and (
            isinstance(root_index, bool) or not isinstance(root_index, int)
        ):
            raise ConsistencyContractError("root_index must be an integer")
        multiplicity = branch.get("multiplicity")
        if multiplicity is not None and (
            isinstance(multiplicity, bool)
            or not isinstance(multiplicity, int)
            or multiplicity < 1
        ):
            raise ConsistencyContractError(
                "root multiplicity must be a positive integer"
            )
        rows.append((root_index, candidate_id, values, multiplicity))

    if len(rows) == 1 and rows[0][3] is None:
        rows[0] = (rows[0][0], rows[0][1], rows[0][2], 1)
    if any(row[3] is None for row in rows):
        raise ConsistencyContractError(
            "multi-root selection evidence requires branch multiplicity for every root"
        )
    if all(row[0] is not None for row in rows):
        indexes = [int(row[0]) for row in rows]
        if len(indexes) != len(set(indexes)):
            raise ConsistencyContractError(
                "selection root_index values must be unique"
            )
        rows.sort(key=lambda row: int(row[0]))
    elif any(row[0] is not None for row in rows):
        raise ConsistencyContractError(
            "selection root_index must be present for every root or none"
        )
    else:
        rows.sort(key=lambda row: row[1])

    selected_values = next(row[2] for row in rows if row[1] == selected_id)
    for key, actual in selected_numeric.items():
        if not _numbers_close(selected_values[key], actual, policy):
            raise ConsistencyContractError(
                f"selected candidate root for {key} disagrees with typed answer"
            )

    rejected_ids = tuple(
        _candidate_id(candidate, f"rejected candidate {index}")
        for index, candidate in enumerate(rejected)
    )
    if seen_ids.intersection(rejected_ids) or len(rejected_ids) != len(set(rejected_ids)):
        raise ConsistencyContractError(
            "selection_decision contains duplicate candidate_id"
        )
    return _SelectionRootEvidence(
        outcome="solved",
        root_values_by_key=MappingProxyType(
            {
                key: tuple(row[2][key] for row in rows)
                for key in primary_keys
            }
        ),
        multiplicity=tuple(int(row[3]) for row in rows),
        ambiguity=False,
        candidate_ids=tuple(row[1] for row in rows),
        rejected_candidate_ids=rejected_ids,
        selection_status=status,
    )


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
    root_values: tuple[float, ...] = ()
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
        root_values = tuple(
            _finite(value, f"root_values[{index}]")
            for index, value in enumerate(tuple(self.root_values))
        )
        if len(root_values) != self.root_count:
            raise ConsistencyContractError(
                "root_values must contain one finite value per root"
            )
        for left_index, left in enumerate(root_values):
            for right in root_values[left_index + 1 :]:
                separation = abs(left - right) / max(abs(left), abs(right), 1.0)
                if separation <= DEFAULT_TOLERANCE_POLICY.root_separation_tol:
                    raise ConsistencyContractError(
                        "root_values must contain distinct roots under the central "
                        "root-separation policy; repeated roots use multiplicity"
                    )
        if not any(
            _numbers_close(self.numeric, root, DEFAULT_TOLERANCE_POLICY)
            for root in root_values
        ):
            raise ConsistencyContractError(
                "numeric must identify one value in root_values"
            )
        object.__setattr__(self, "root_values", root_values)
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
        if self.ambiguity and self.root_count < 2:
            raise ConsistencyContractError(
                "ambiguous output requires at least two roots"
            )
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
            "root_values": list(self.root_values),
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
    outcome: str
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
        outcome = _text(self.outcome, "outcome").lower()
        if outcome not in {"solved", "ambiguous", "no_valid_solution"}:
            raise ConsistencyContractError(f"unsupported outcome {outcome!r}")
        object.__setattr__(self, "outcome", outcome)
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
        if outcome == "no_valid_solution":
            if outputs:
                raise ConsistencyContractError(
                    "no_valid_solution observation must not contain outputs"
                )
        else:
            if self.applicability is not VerificationApplicability.APPLICABLE:
                raise ConsistencyContractError(
                    "solved or ambiguous observations must be applicable"
                )
            if not outputs:
                raise ConsistencyContractError(
                    "solved or ambiguous observations require typed outputs"
                )
            if outcome == "ambiguous" and any(
                not item.ambiguity or item.root_count < 2 for item in outputs
            ):
                raise ConsistencyContractError(
                    "ambiguous observation requires complete multi-root outputs"
                )
            if outcome == "solved" and any(item.ambiguity for item in outputs):
                raise ConsistencyContractError(
                    "solved observation cannot mark outputs ambiguous"
                )
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
            "outcome": self.outcome,
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


@dataclass(frozen=True)
class CrossPathAgreementReport:
    family: str
    oracle_id: str
    product_path_id: str
    secondary_path_id: str
    policy_version: str
    verification_report: VerificationReport
    report_version: str = CROSS_PATH_REPORT_VERSION

    @property
    def passed(self) -> bool:
        return bool(self.verification_report.passed)

    @property
    def disagreements(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(dict(check))
            for check in self.verification_report.structured_checks
            if str(check.get("status"))
            not in {
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
            "product_path_id": self.product_path_id,
            "secondary_path_id": self.secondary_path_id,
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


@dataclass(frozen=True)
class ThreeWayConsistencyReport:
    oracle: OracleCase
    product_observation: SolverPathObservation
    secondary_observation: SolverPathObservation
    oracle_product_report: DisagreementReport
    oracle_secondary_report: DisagreementReport
    product_secondary_report: CrossPathAgreementReport
    report_version: str = THREE_WAY_REPORT_VERSION

    @property
    def passed(self) -> bool:
        return bool(
            self.oracle_product_report.passed
            and self.oracle_secondary_report.passed
            and self.product_secondary_report.passed
        )

    @property
    def disagreements(self) -> tuple[Mapping[str, Any], ...]:
        combined: list[Mapping[str, Any]] = []
        for leg, report in (
            ("oracle_product", self.oracle_product_report),
            ("oracle_secondary", self.oracle_secondary_report),
            ("product_secondary", self.product_secondary_report),
        ):
            for check in report.disagreements:
                combined.append(
                    MappingProxyType({"leg": leg, **dict(check)})
                )
        return tuple(combined)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_version": self.report_version,
            "oracle_id": self.oracle.oracle_id,
            "family": self.oracle.family,
            "oracle_version": self.oracle.oracle_version,
            "benchmark_version": self.oracle.benchmark_version,
            "policy_version": self.oracle.policy_version,
            "status": "passed" if self.passed else "failed",
            "passed": self.passed,
            "direct_product_secondary_agreement": self.product_secondary_report.passed,
            "oracle": self.oracle.to_dict(),
            "observations": {
                "product": self.product_observation.to_dict(),
                "secondary": self.secondary_observation.to_dict(),
            },
            "legs": {
                "oracle_product": self.oracle_product_report.to_dict(),
                "oracle_secondary": self.oracle_secondary_report.to_dict(),
                "product_secondary": self.product_secondary_report.to_dict(),
            },
            "disagreements": [
                _json_safe(dict(item)) for item in self.disagreements
            ],
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
    root_values_by_key: Mapping[str, Sequence[float]],
    multiplicity: Sequence[int],
    outcome: str,
    ambiguity: bool,
    assumptions: Sequence[str] = (),
    equation_ids: Sequence[str] = (),
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> SolverPathObservation:
    """Snapshot semantic AnswerItem fields; display text is never inspected."""
    _require_central_policy(policy)
    if not isinstance(root_values_by_key, Mapping):
        raise ConsistencyContractError("root_values_by_key must be a mapping")
    multiplicity_tuple = tuple(multiplicity)
    outputs: list[ObservedSemanticOutput] = []
    for index, item in enumerate(tuple(answer_items)):
        output_key = getattr(item, "output_key", None)
        numeric = getattr(item, "numeric", None)
        if not isinstance(output_key, str) or not output_key.strip():
            raise ConsistencyContractError(
                f"answer_items[{index}] is missing semantic output_key"
            )
        value = _finite(numeric, f"answer_items[{index}].numeric")
        roots_raw = root_values_by_key.get(output_key)
        if not isinstance(roots_raw, (list, tuple)) or not roots_raw:
            raise ConsistencyContractError(
                f"missing complete root evidence for {output_key}"
            )
        roots = tuple(
            _finite(root, f"root_values_by_key.{output_key}")
            for root in roots_raw
        )
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
                root_count=len(roots),
                root_values=roots,
                multiplicity=multiplicity_tuple,
                ambiguity=ambiguity,
                equation_ids=tuple(equation_ids),
            )
        )
    return SolverPathObservation(
        path_id=path_id,
        family=family,
        solver_id=solver_id,
        outputs=tuple(outputs),
        policy_version=policy.policy_version,
        outcome=outcome,
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
    _require_central_policy(policy)
    if getattr(result, "ok", None) is not True:
        raise ConsistencyContractError(
            "result.ok must be the boolean True for a product observation"
        )
    if family not in PRIMARY_OUTPUT_CONTRACT:
        raise ConsistencyContractError(f"unsupported family {family!r}")
    roles_config = load_capability_matrix().path_roles_for_family(family)
    if roles_config is None:
        raise ConsistencyContractError(
            f"capability matrix has no solver path roles for {family}"
        )
    if solver_id not in tuple(roles_config["student_answer_path"]):
        raise ConsistencyContractError(
            f"solver_id {solver_id!r} is not a declared student path for {family}"
        )
    expected_path_id = f"{PRODUCT_PATH_PREFIX}{solver_id}"
    if path_id != expected_path_id:
        raise ConsistencyContractError(
            f"product path_id must be {expected_path_id!r}"
        )
    if load_capability_matrix().for_solver(solver_id) is None:
        raise ConsistencyContractError(
            f"solver_id {solver_id!r} is absent from the capability matrix"
        )
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
    unrelated_typed_keys: list[str] = []
    for item in tuple(answers):
        key = getattr(item, "output_key", None)
        if isinstance(key, str) and key in selected_set:
            selected.append(item)
        else:
            ignored = key if isinstance(key, str) and key else "<untyped>"
            ignored_keys.append(ignored)
            if isinstance(key, str) and key.strip():
                unrelated_typed_keys.append(key)

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
    selection = _selection_root_evidence(
        result,
        primary_keys,
        selected,
        policy=policy,
    )

    fallback_output: ObservedSemanticOutput | None = None
    fallback_rejected_reason: str | None = None
    if not selected and len(primary_keys) == 1:
        if unrelated_typed_keys:
            fallback_rejected_reason = "unrelated_typed_answer_items_present"
        elif missing_roles:
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
                        roots = selection.root_values_by_key[primary_keys[0]]
                        fallback_output = ObservedSemanticOutput(
                            output_key=primary_keys[0],
                            numeric=numeric,
                            unit=representative_unit,
                            sign=_numeric_sign(numeric, policy),
                            frame=actual_frame,
                            positive_direction=actual_direction,
                            assumptions=tuple(canonical_assumptions),
                            root_count=len(roots),
                            root_values=roots,
                            multiplicity=selection.multiplicity,
                            ambiguity=selection.ambiguity,
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
            root_values_by_key=selection.root_values_by_key,
            multiplicity=selection.multiplicity,
            outcome=selection.outcome,
            ambiguity=selection.ambiguity,
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
        outcome=selection.outcome,
        metadata={
            "source": answer_source,
            "answer_source": answer_source,
            "equation_source": equation_source,
            "equation_evidence_source": equation_source,
            "raw_equation_evidence": raw_equations,
            "structured_equation_evidence": structured_equations,
            "equation_role_ids": roles,
            "missing_equation_roles": missing_roles,
            "equation_signature_valid": not missing_roles,
            "assumption_source": "CanonicalProblem.assumptions",
            "coordinate_source": "CanonicalProblem.coordinate_data",
            "selection_evidence_source": "SolverResult.selection_decision",
            "selection_status": selection.selection_status,
            "selection_candidate_ids": selection.candidate_ids,
            "rejected_selection_candidate_ids": selection.rejected_candidate_ids,
            "semantic_output_keys": primary_keys,
            "ignored_output_keys": tuple(ignored_keys),
            "unrelated_typed_output_keys": tuple(unrelated_typed_keys),
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


def _identity_expectation(
    oracle: OracleCase,
    observed: SolverPathObservation,
) -> tuple[str, str, str, bool]:
    roles = load_capability_matrix().path_roles_for_family(oracle.family)
    if roles is None:
        return "unknown", "", "", False
    if observed.path_id.startswith(PRODUCT_PATH_PREFIX):
        expected_path = f"{PRODUCT_PATH_PREFIX}{oracle.solver_id}"
        expected_solver = oracle.solver_id
        declared = oracle.solver_id in tuple(roles["student_answer_path"])
        return "product", expected_path, expected_solver, declared
    if observed.path_id.startswith(SECONDARY_PATH_PREFIX):
        expected_path = str(roles["secondary_analytic_path"])
        return "secondary", expected_path, expected_path, True
    return "unknown", f"{PRODUCT_PATH_PREFIX}{oracle.solver_id}", oracle.solver_id, False


def _root_pairs(
    root_values: Sequence[float],
    multiplicity: Sequence[int],
) -> tuple[tuple[float, int], ...]:
    return tuple(
        sorted(
            zip(tuple(root_values), tuple(multiplicity)),
            key=lambda item: (item[0], item[1]),
        )
    )


def _roots_agree(
    expected: ExpectedSemanticOutput | ObservedSemanticOutput,
    actual: ObservedSemanticOutput,
    *,
    policy: TolerancePolicy,
    engine_id: str,
) -> tuple[bool, tuple[Mapping[str, Any], ...]]:
    expected_pairs = _root_pairs(expected.root_values, expected.multiplicity)
    actual_pairs = _root_pairs(actual.root_values, actual.multiplicity)
    diagnostics: list[Mapping[str, Any]] = []
    if len(expected_pairs) != len(actual_pairs):
        return False, ()
    all_match = expected.root_count == actual.root_count
    for index, ((expected_value, expected_mult), (actual_value, actual_mult)) in enumerate(
        zip(expected_pairs, actual_pairs)
    ):
        scale = max(abs(expected_value), abs(actual_value), 1.0)
        tolerance = policy.tolerance(
            "absolute", scale=scale, engine_id=engine_id
        )
        error = abs(expected_value - actual_value)
        matched = error <= tolerance and expected_mult == actual_mult
        all_match = all_match and matched
        diagnostics.append(
            MappingProxyType(
                {
                    "index": index,
                    "expected_value": expected_value,
                    "observed_value": actual_value,
                    "expected_multiplicity": expected_mult,
                    "observed_multiplicity": actual_mult,
                    "absolute_error": error,
                    "tolerance": tolerance,
                    "matched": matched,
                }
            )
        )
    return all_match, tuple(diagnostics)


def compare_oracle_observation(
    oracle: OracleCase,
    observed: SolverPathObservation,
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> DisagreementReport:
    """Compare independent expectations with one semantic product-path snapshot."""
    _require_central_policy(policy)
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
    path_kind, expected_path, expected_solver, declared = _identity_expectation(
        oracle, observed
    )
    path_ok = path_kind != "unknown" and observed.path_id == expected_path
    solver_ok = declared and observed.solver_id == expected_solver
    _add(
        report,
        check_id=f"{prefix}:path_identity",
        category="path_identity",
        status=_same_status(path_ok),
        observed={"kind": path_kind, "path_id": observed.path_id},
        expected={"kind": "product_or_secondary", "path_id": expected_path},
        message="solver path identity agrees" if path_ok else "solver path identity disagreement",
        policy=policy,
    )
    _add(
        report,
        check_id=f"{prefix}:solver_identity",
        category="solver_identity",
        status=_same_status(solver_ok),
        observed=observed.solver_id,
        expected=expected_solver,
        message=(
            "declared solver identity agrees"
            if solver_ok
            else "solver identity is not the declared path solver"
        ),
        policy=policy,
    )
    outcome_ok = observed.outcome == oracle.expected_outcome
    _add(
        report,
        check_id=f"{prefix}:outcome",
        category="outcome",
        status=_same_status(outcome_ok),
        observed=observed.outcome,
        expected=oracle.expected_outcome,
        message="outcome agrees" if outcome_ok else "outcome disagreement",
        policy=policy,
    )
    applicability_ok = observed.applicability.value == oracle.expected_applicability
    _add(
        report,
        check_id=f"{prefix}:applicability",
        category="applicability",
        status=_same_status(applicability_ok),
        applicability=observed.applicability,
        observed={
            "applicability": observed.applicability.value,
            "message": observed.message,
        },
        expected=oracle.expected_applicability,
        message=(
            "applicability agrees"
            if applicability_ok
            else "applicability disagreement"
        ),
        policy=policy,
    )
    primary_contract = (
        ()
        if oracle.expected_outcome == "no_valid_solution"
        else PRIMARY_OUTPUT_CONTRACT[oracle.family]
    )
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
    required_roles = (
        ()
        if oracle.expected_outcome == "no_valid_solution"
        else EQUATION_ROLE_CONTRACT[oracle.family]
    )
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
        roots_ok, root_diagnostics = _roots_agree(
            expected,
            actual,
            policy=policy,
            engine_id=observed.solver_id,
        )
        _add(
            report,
            check_id=f"{check_prefix}:roots",
            category="root_structure",
            status=_same_status(roots_ok),
            observed={
                "root_count": actual.root_count,
                "root_values": list(actual.root_values),
                "multiplicity": list(actual.multiplicity),
                "matches": root_diagnostics,
            },
            expected={
                "root_count": expected.root_count,
                "root_values": list(expected.root_values),
                "multiplicity": list(expected.multiplicity),
            },
            message=(
                "complete root multiset agrees"
                if roots_ok
                else "root values, count, or multiplicity disagree"
            ),
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
        expected_path_id=expected_path,
        observed_path_id=observed.path_id,
        oracle_version=oracle.oracle_version,
        benchmark_version=oracle.benchmark_version,
        policy_version=policy.policy_version,
        verification_report=report,
    )


def compare_path_observations(
    oracle: OracleCase,
    product: SolverPathObservation,
    secondary: SolverPathObservation,
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> CrossPathAgreementReport:
    """Compare product and secondary observations directly, without oracle values."""
    _require_central_policy(policy)
    report = VerificationReport(passed=True, policy_version=policy.policy_version)
    prefix = f"phase49:{oracle.oracle_id}:product-secondary"
    product_kind, product_path, product_solver, product_declared = (
        _identity_expectation(oracle, product)
    )
    secondary_kind, secondary_path, secondary_solver, secondary_declared = (
        _identity_expectation(oracle, secondary)
    )
    product_identity_ok = bool(
        product_kind == "product"
        and product.path_id == product_path
        and product.solver_id == product_solver
        and product_declared
    )
    secondary_identity_ok = bool(
        secondary_kind == "secondary"
        and secondary.path_id == secondary_path
        and secondary.solver_id == secondary_solver
        and secondary_declared
    )
    for label, observation, identity_ok, expected_path, expected_solver in (
        (
            "product",
            product,
            product_identity_ok,
            product_path,
            product_solver,
        ),
        (
            "secondary",
            secondary,
            secondary_identity_ok,
            secondary_path,
            secondary_solver,
        ),
    ):
        _add(
            report,
            check_id=f"{prefix}:{label}:identity",
            category="path_identity",
            status=_same_status(identity_ok),
            observed={
                "path_id": observation.path_id,
                "solver_id": observation.solver_id,
            },
            expected={
                "path_id": expected_path,
                "solver_id": expected_solver,
            },
            message=(
                f"{label} path identity agrees"
                if identity_ok
                else f"{label} path identity disagreement"
            ),
            policy=policy,
        )

    policy_ok = bool(
        oracle.policy_version == policy.policy_version
        and product.policy_version == policy.policy_version
        and secondary.policy_version == policy.policy_version
    )
    _add(
        report,
        check_id=f"{prefix}:policy",
        category="policy",
        status=_same_status(policy_ok),
        observed={
            "oracle": oracle.policy_version,
            "product": product.policy_version,
            "secondary": secondary.policy_version,
        },
        expected=policy.policy_version,
        message="path policies agree" if policy_ok else "path policy mismatch",
        policy=policy,
    )
    family_ok = product.family == secondary.family == oracle.family
    _add(
        report,
        check_id=f"{prefix}:family",
        category="path_contract",
        status=_same_status(family_ok),
        observed={"product": product.family, "secondary": secondary.family},
        expected=oracle.family,
        message="path families agree" if family_ok else "path family disagreement",
        policy=policy,
    )
    outcome_ok = product.outcome == secondary.outcome
    _add(
        report,
        check_id=f"{prefix}:outcome",
        category="outcome",
        status=_same_status(outcome_ok),
        observed=secondary.outcome,
        expected=product.outcome,
        message="path outcomes agree" if outcome_ok else "path outcome disagreement",
        policy=policy,
    )
    applicability_ok = product.applicability is secondary.applicability
    _add(
        report,
        check_id=f"{prefix}:applicability",
        category="applicability",
        status=_same_status(applicability_ok),
        applicability=secondary.applicability,
        observed=secondary.applicability.value,
        expected=product.applicability.value,
        message=(
            "path applicability agrees"
            if applicability_ok
            else "path applicability disagreement"
        ),
        policy=policy,
    )

    product_keys = set(product.output_by_key)
    secondary_keys = set(secondary.output_by_key)
    missing = sorted(product_keys - secondary_keys)
    extra = sorted(secondary_keys - product_keys)
    keys_ok = not missing and not extra
    _add(
        report,
        check_id=f"{prefix}:semantic_outputs",
        category="semantic_outputs",
        status=_same_status(keys_ok),
        observed={
            "keys": sorted(secondary_keys),
            "missing": missing,
            "extra": extra,
        },
        expected=sorted(product_keys),
        message=(
            "path semantic output keys agree"
            if keys_ok
            else "path semantic output keys disagree"
        ),
        policy=policy,
    )

    for output_key in sorted(product_keys & secondary_keys):
        expected = product.output_by_key[output_key]
        actual = secondary.output_by_key[output_key]
        check_prefix = f"{prefix}:{output_key}"
        scale = max(abs(expected.numeric), abs(actual.numeric), 1.0)
        tolerance = policy.tolerance(
            "absolute", scale=scale, engine_id=product.solver_id
        )
        absolute_error = abs(actual.numeric - expected.numeric)
        relative_error = absolute_error / max(
            abs(expected.numeric), policy.near_zero_tol
        )
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
            message=(
                "product and secondary numeric values agree"
                if numeric_ok
                else "product-secondary numeric disagreement"
            ),
            policy=policy,
        )
        exact_checks = (
            (
                "unit",
                "unit_dimension",
                _normalize_unit(actual.unit),
                _normalize_unit(expected.unit),
            ),
            ("sign", "sign", actual.sign, expected.sign),
            ("frame", "coordinate_frame", actual.frame, expected.frame),
            (
                "positive_direction",
                "positive_direction",
                actual.positive_direction,
                expected.positive_direction,
            ),
            (
                "assumptions",
                "assumptions",
                tuple(actual.assumptions),
                tuple(expected.assumptions),
            ),
            (
                "ambiguity",
                "ambiguity",
                actual.ambiguity,
                expected.ambiguity,
            ),
            (
                "equations",
                "equation_ids",
                tuple(actual.equation_ids),
                tuple(expected.equation_ids),
            ),
        )
        for suffix, category, observed_value, expected_value in exact_checks:
            equal = observed_value == expected_value
            _add(
                report,
                check_id=f"{check_prefix}:{suffix}",
                category=category,
                status=_same_status(equal),
                observed=observed_value,
                expected=expected_value,
                message=(
                    f"product and secondary {category} agree"
                    if equal
                    else f"product-secondary {category} disagreement"
                ),
                policy=policy,
            )
        roots_ok, root_diagnostics = _roots_agree(
            expected,
            actual,
            policy=policy,
            engine_id=product.solver_id,
        )
        _add(
            report,
            check_id=f"{check_prefix}:roots",
            category="root_structure",
            status=_same_status(roots_ok),
            observed={
                "root_count": actual.root_count,
                "root_values": list(actual.root_values),
                "multiplicity": list(actual.multiplicity),
                "matches": root_diagnostics,
            },
            expected={
                "root_count": expected.root_count,
                "root_values": list(expected.root_values),
                "multiplicity": list(expected.multiplicity),
            },
            message=(
                "product and secondary complete roots agree"
                if roots_ok
                else "product-secondary root disagreement"
            ),
            policy=policy,
        )

    ensure_structured_checks(report, prefix=prefix)
    accepted = {
        VerificationStatus.PASSED.value,
        VerificationStatus.PASSED_WITH_WARNING.value,
    }
    report.passed = bool(report.structured_checks) and all(
        str(check.get("status")) in accepted
        for check in report.structured_checks
    )
    return CrossPathAgreementReport(
        family=oracle.family,
        oracle_id=oracle.oracle_id,
        product_path_id=product.path_id,
        secondary_path_id=secondary.path_id,
        policy_version=policy.policy_version,
        verification_report=report,
    )


def compare_three_way(
    oracle: OracleCase,
    product: SolverPathObservation,
    secondary: SolverPathObservation,
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> ThreeWayConsistencyReport:
    """Evaluate all required oracle/product/secondary legs without overwrites."""
    _require_central_policy(policy)
    oracle_product = compare_oracle_observation(oracle, product, policy=policy)
    oracle_secondary = compare_oracle_observation(oracle, secondary, policy=policy)
    product_secondary = compare_path_observations(
        oracle, product, secondary, policy=policy
    )
    return ThreeWayConsistencyReport(
        oracle=oracle,
        product_observation=product,
        secondary_observation=secondary,
        oracle_product_report=oracle_product,
        oracle_secondary_report=oracle_secondary,
        product_secondary_report=product_secondary,
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
        root_count=1,
        root_values=(numeric,),
        multiplicity=(1,),
        ambiguity=False,
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
    outcome: str | None = None,
) -> SolverPathObservation:
    roles = load_capability_matrix().path_roles_for_family(family)
    if roles is None:
        raise ConsistencyContractError(
            f"capability matrix has no solver path roles for {family}"
        )
    path_id = str(roles["secondary_analytic_path"])
    expected_path = f"{SECONDARY_PATH_PREFIX}{family}"
    if path_id != expected_path:
        raise ConsistencyContractError(
            f"declared secondary path must be {expected_path!r}"
        )
    output_tuple = tuple(outputs)
    if applicability is VerificationApplicability.APPLICABLE:
        actual_keys = tuple(output.output_key for output in output_tuple)
        if actual_keys != PRIMARY_OUTPUT_CONTRACT[family]:
            raise ConsistencyContractError(
                f"secondary {family} outputs {actual_keys!r} violate central "
                f"primary-output contract {PRIMARY_OUTPUT_CONTRACT[family]!r}"
            )
    elif output_tuple:
        raise ConsistencyContractError(
            "non-applicable secondary observation must not contain outputs"
        )
    actual_outcome = outcome or (
        "solved"
        if applicability is VerificationApplicability.APPLICABLE
        else "no_valid_solution"
    )
    return SolverPathObservation(
        path_id=path_id,
        family=family,
        solver_id=path_id,
        outputs=output_tuple,
        policy_version=policy.policy_version,
        outcome=actual_outcome,
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
    _require_central_policy(policy)
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
    "CROSS_PATH_REPORT_VERSION",
    "DISAGREEMENT_REPORT_VERSION",
    "THREE_WAY_REPORT_VERSION",
    "PRODUCT_PATH_PREFIX",
    "SECONDARY_PATH_PREFIX",
    "PRIMARY_OUTPUT_CONTRACT",
    "EQUATION_ROLE_CONTRACT",
    "ConsistencyContractError",
    "CrossPathAgreementReport",
    "DisagreementReport",
    "ObservedSemanticOutput",
    "SolverPathObservation",
    "ThreeWayConsistencyReport",
    "compare_oracle_observation",
    "compare_path_observations",
    "compare_three_way",
    "evaluate_secondary_analytic",
    "observation_from_answer_items",
    "observation_from_solver_result",
]
