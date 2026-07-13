from __future__ import annotations

"""Offline Phase 49 product/oracle/metamorphic consistency runner.

This module is not imported by the normal solve path. Fixed expectations come
only from reviewed fixtures; current engine values are observation-only.
"""

import argparse
from copy import deepcopy
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from engine.capabilities.loader import load_capability_matrix
from engine.model_builder import build_physical_model
from engine.models import CanonicalProblem, Quantity, SolverResult, VerificationReport
from engine.physics_core.validators import (
    ValidationContext,
    validate_and_select,
    validate_output_candidates,
)
from engine.services import solve_problem
from engine.solvers.registry import SolverRegistry
from engine.verification.checks import merge_reports, record_verification_check
from engine.verification.consistency import (
    EQUATION_ROLE_CONTRACT,
    PRIMARY_OUTPUT_CONTRACT,
    ObservedSemanticOutput,
    SolverPathObservation,
    compare_oracle_observation,
    evaluate_secondary_analytic,
    observation_from_solver_result,
)
from engine.verification.oracles import (
    INDEPENDENT_PROVENANCE,
    ExpectedSemanticOutput,
    OracleCase,
    OracleSuite,
    load_oracle_suite,
)
from engine.verification.policy import DEFAULT_TOLERANCE_POLICY, TolerancePolicy
from engine.verification.suite import verify_result
from engine.verification.types import (
    VerificationApplicability,
    VerificationCheck,
    VerificationStatus,
)


REPORT_SCHEMA_VERSION = 1
REPORT_VERSION = "phase49-solver-consistency-report-v1"
DEFAULT_ORACLE_PATH = (
    BACKEND_ROOT / "tests" / "benchmarks" / "phase49_dynamics_oracles_v1.json"
)
DEFAULT_METAMORPHIC_PATH = (
    BACKEND_ROOT / "tests" / "benchmarks" / "phase49_metamorphic_v1.json"
)
DEFAULT_JSON_REPORT = BACKEND_ROOT / "reports" / "phase49_solver_consistency.json"
DEFAULT_MARKDOWN_REPORT = BACKEND_ROOT / "reports" / "phase49_solver_consistency.md"


class Phase49RunError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProductOptions:
    quantity_units: Mapping[str, str] | None = None
    quantity_values: Mapping[str, float] | None = None
    extra_inputs: Mapping[str, Any] | None = None
    coordinate_overrides: Mapping[str, str] | None = None


@dataclass
class ProductExecution:
    canonical: CanonicalProblem
    result: SolverResult
    observation: SolverPathObservation
    solver_id: str
    selection_status: str


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Phase49RunError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise Phase49RunError(f"{name} must be finite")
    return number


def _q(symbol: str, value: Any, unit: str) -> Quantity:
    return Quantity(
        symbol=symbol,
        value=_finite(value, symbol),
        unit=unit,
        source_text="phase49 fixed fixture",
    )


def _sign(value: float, policy: TolerancePolicy) -> str:
    if policy.is_near_zero(value, scale=max(abs(value), 1.0)):
        return "zero"
    return "positive" if value > 0 else "negative"


def _family_metadata(
    family: str, inputs: Mapping[str, Any]
) -> tuple[list[str], dict[str, str]]:
    if family == "incline":
        mode = str(inputs.get("friction_mode", "frictionless"))
        first = {
            "frictionless": "frictionless",
            "kinetic": "kinetic_friction",
            "static": "static_friction",
        }.get(mode)
        if first is None:
            raise Phase49RunError(f"unsupported friction mode {mode!r}")
        return [first, "constant_gravity", "particle_model"], {
            "coordinate_frame": "incline_tangent",
            "positive_direction": "down_slope",
        }
    if family == "pulley":
        assumptions = (
            ["massless_string", "no_slip", "frictionless_axle", "rigid_pulley"]
            if "pulley_inertia" in inputs
            else ["massless_string", "massless_pulley", "frictionless_axle"]
        )
        return assumptions, {
            "coordinate_frame": "pulley_string",
            "positive_direction": "mass2_down",
        }
    if family == "collision":
        return [
            "one_dimensional_impact",
            "isolated_during_impact",
            "newton_restitution",
        ], {
            "coordinate_frame": "one_dimensional_lab",
            "positive_direction": "right",
        }
    if family == "rolling":
        return ["pure_rolling", "no_energy_loss", "starts_from_rest"], {
            "coordinate_frame": "path_tangent",
            "positive_direction": "direction_of_motion",
        }
    if family == "work_energy":
        return ["particle_model", "net_work_known", "speed_is_nonnegative"], {
            "coordinate_frame": "path_tangent",
            "positive_direction": "direction_of_motion",
        }
    if family == "fixed_axis_rotation":
        return ["fixed_axis", "constant_net_torque"], {
            "coordinate_frame": "fixed_axis",
            "positive_direction": "counterclockwise",
        }
    raise Phase49RunError(f"unsupported family {family!r}")


def build_product_canonical(
    case: OracleCase,
    *,
    options: ProductOptions | None = None,
) -> CanonicalProblem:
    """Build typed product input from canonical inputs, never expected outputs."""

    inputs = deepcopy(dict(case.canonical_inputs))
    options = options or ProductOptions()
    units = dict(options.quantity_units or {})
    values = dict(options.quantity_values or {})
    extras = dict(options.extra_inputs or {})
    coordinate_overrides = dict(options.coordinate_overrides or {})
    assumptions, coordinates = _family_metadata(case.family, inputs)
    coordinates.update(coordinate_overrides)
    knowns: dict[str, Quantity] = {}
    system_type = case.solver_id
    subtype = None
    friction_type = None
    pulley_topology = None
    body_shape = None
    flags: dict[str, bool] = {}

    def quantity(symbol: str, value: Any, unit: str) -> Quantity:
        return _q(
            symbol,
            values.get(symbol, value),
            str(units.get(symbol, unit)),
        )

    if case.family == "incline":
        system_type = "particle_on_incline"
        mode = str(inputs.get("friction_mode", "frictionless"))
        subtype = "no_friction" if mode == "frictionless" else "with_friction"
        if "angle_deg" in inputs:
            knowns["theta"] = quantity("theta", inputs["angle_deg"], "deg")
        elif "angle_rad" in inputs:
            knowns["theta"] = quantity("theta", inputs["angle_rad"], "rad")
        else:
            raise Phase49RunError("incline needs angle_deg or angle_rad")
        knowns["g"] = quantity("g", inputs["gravity"], "m/s^2")
        mass = extras.pop("mass", {"value": 1.0, "unit": "kg"})
        if not isinstance(mass, Mapping):
            raise Phase49RunError("product mass extra must be an object")
        knowns["m"] = _q(
            "m",
            mass.get("value", 1.0),
            str(mass.get("unit", "kg")),
        )
        if mode == "kinetic":
            knowns["mu_k"] = quantity("mu_k", inputs["mu_k"], "")
            friction_type = "kinetic"
        elif mode == "static":
            knowns["mu_s"] = quantity("mu_s", inputs["mu_s"], "")
            friction_type = "static"
    elif case.family == "pulley":
        knowns = {
            "m1": quantity("m1", inputs["m1"], "kg"),
            "m2": quantity("m2", inputs["m2"], "kg"),
            "g": quantity("g", inputs["gravity"], "m/s^2"),
        }
        pulley_topology = "two_hanging"
        if "pulley_inertia" in inputs:
            knowns["I"] = quantity("I", inputs["pulley_inertia"], "kg*m^2")
            knowns["R"] = quantity("R", inputs["pulley_radius"], "m")
    elif case.family == "collision":
        knowns = {
            "m1": quantity("m1", inputs["m1"], "kg"),
            "m2": quantity("m2", inputs["m2"], "kg"),
            "v1": quantity("v1", inputs["v1_before"], "m/s"),
            "v2": quantity("v2", inputs["v2_before"], "m/s"),
            "e": quantity("e", inputs["restitution"], ""),
        }
    elif case.family == "rolling":
        radius = _finite(inputs["radius"], "radius")
        mass = 1.0
        inertia = _finite(inputs["inertia_factor"], "inertia_factor") * radius**2
        knowns = {
            "h": quantity("h", inputs["height"], "m"),
            "g": quantity("g", inputs["gravity"], "m/s^2"),
            "m": quantity("m", mass, "kg"),
            "R": quantity("R", radius, "m"),
            "I": quantity("I", inertia, "kg*m^2"),
            "v0": quantity("v0", 0.0, "m/s"),
        }
        flags["pure_rolling"] = True
        body_shape = "general_rigid_body"
    elif case.family == "work_energy":
        knowns = {
            "m": quantity("m", inputs["mass"], "kg"),
            "v0": quantity("v0", inputs["initial_velocity"], "m/s"),
            "W": quantity("W", inputs["net_work"], "J"),
        }
    elif case.family == "fixed_axis_rotation":
        knowns = {
            "tau": quantity("tau", inputs["torque"], "N*m"),
            "I": quantity("I", inputs["inertia"], "kg*m^2"),
        }
    else:
        raise Phase49RunError(f"unsupported family {case.family!r}")

    if extras:
        raise Phase49RunError(f"unsupported product extras: {sorted(extras)}")
    if set(units) - set(knowns) or set(values) - set(knowns):
        raise Phase49RunError("quantity override names must be actual product symbols")

    return CanonicalProblem(
        system_type=system_type,
        subtype=subtype,
        language="en",
        knowns=knowns,
        unknowns=list(PRIMARY_OUTPUT_CONTRACT[case.family]),
        flags=flags,
        assumptions=assumptions,
        missing_info=[],
        confidence="높음",
        raw_text=case.problem,
        pulley_topology=pulley_topology,
        friction_type=friction_type,
        body_shape=body_shape,
        coordinate_data=coordinates,
        requested_outputs=list(PRIMARY_OUTPUT_CONTRACT[case.family]),
    )


def _declared_solver(
    registry: SolverRegistry,
    case: OracleCase,
    canonical: CanonicalProblem,
) -> Any:
    roles = load_capability_matrix().path_roles_for_family(case.family)
    if roles is None or case.solver_id not in tuple(roles["student_answer_path"]):
        raise Phase49RunError(
            f"{case.oracle_id} solver is not a declared student path"
        )
    solver = next(
        (item for item in registry.solvers if item.name == case.solver_id),
        None,
    )
    if solver is None or solver.match(canonical) is None:
        raise Phase49RunError(
            f"{case.oracle_id} cannot use declared solver {case.solver_id}"
        )
    return solver


def _solve_validated(
    canonical: CanonicalProblem,
    solver: Any,
) -> tuple[SolverResult, str]:
    model = build_physical_model(canonical)
    batch = (
        solver.solve_candidates(canonical, model)
        if getattr(solver, "uses_prebuilt_physical_model", False)
        else solver.solve_candidates(canonical)
    )
    result = batch.result
    context = ValidationContext(
        requested_outputs=list(canonical.requested_outputs),
        selection_policy=f"{solver.name}:validated-candidate",
    )
    original = result.selection_decision
    output = (
        validate_output_candidates(batch.candidates, context)
        if original is not None
        else validate_and_select(batch.candidates, context)
    )
    if (
        original is None
        or (original.status == "selected" and output.status != "selected")
    ):
        result.selection_decision = output
    status = str(getattr(result.selection_decision, "status", "missing"))
    if not result.ok:
        raise Phase49RunError(
            f"{solver.name} failed: "
            f"{result.unsupported_reason or result.verification.errors}"
        )
    if status != "selected":
        raise Phase49RunError(
            f"{solver.name} candidate validation status is {status}"
        )
    phase48 = verify_result(canonical, result, solver_id=solver.name)
    result.verification = merge_reports(result.verification, phase48)
    if not result.verification.passed:
        raise Phase49RunError(
            f"{solver.name} failed Phase 48 verification"
        )
    return result, status


def run_product_case(
    case: OracleCase,
    *,
    options: ProductOptions | None = None,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> ProductExecution:
    canonical = build_product_canonical(case, options=options)
    registry = SolverRegistry()
    solver = _declared_solver(registry, case, canonical)
    result, status = _solve_validated(canonical, solver)
    observation = observation_from_solver_result(
        result,
        canonical=canonical,
        family=case.family,
        path_id=f"student.{case.solver_id}",
        solver_id=case.solver_id,
        policy=policy,
    )
    return ProductExecution(
        canonical=canonical,
        result=result,
        observation=observation,
        solver_id=solver.name,
        selection_status=status,
    )


def load_metamorphic_fixture(path: str | Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase49RunError(f"cannot load metamorphic fixture: {exc}") from exc
    required = {
        "schema_version",
        "relation_version",
        "oracle_version",
        "benchmark_version",
        "policy_version",
        "minimum_distinct_relations",
        "relations",
        "mutation_controls",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise Phase49RunError(
            f"metamorphic fields must be exactly {sorted(required)}"
        )
    if raw["schema_version"] != 1:
        raise Phase49RunError("metamorphic schema_version must be 1")
    if raw["policy_version"] != DEFAULT_TOLERANCE_POLICY.policy_version:
        raise Phase49RunError("metamorphic policy version mismatch")
    relations = raw["relations"]
    controls = raw["mutation_controls"]
    if not isinstance(relations, list) or not isinstance(controls, list):
        raise Phase49RunError("relations and mutation_controls must be lists")
    ids = [item.get("relation_id") for item in relations]
    kinds = [item.get("relation_kind") for item in relations]
    if len(ids) != len(set(ids)) or len(kinds) != len(set(kinds)):
        raise Phase49RunError("relation IDs and relation kinds must be unique")
    minimum = int(raw["minimum_distinct_relations"])
    if len(set(kinds)) < minimum:
        raise Phase49RunError("metamorphic relation coverage is below minimum")
    if len(controls) != 4:
        raise Phase49RunError("exactly four mutation controls are required")
    if {item.get("kind") for item in controls} != {
        "sign",
        "coefficient",
        "unit",
        "constraint_equation",
    }:
        raise Phase49RunError("mutation control kinds are incomplete")
    return raw


def _transform_inputs(
    base_inputs: Mapping[str, Any],
    transformation: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = deepcopy(dict(base_inputs))
    for key in transformation.get("canonical_inputs_remove", []):
        inputs.pop(str(key), None)
    for key, value in dict(
        transformation.get("canonical_inputs_patch", {})
    ).items():
        inputs[str(key)] = value
    for key, factor in dict(
        transformation.get("canonical_inputs_scale", {})
    ).items():
        if key not in inputs:
            raise Phase49RunError(f"cannot scale absent input {key}")
        inputs[str(key)] = _finite(inputs[key], str(key)) * _finite(
            factor, str(key)
        )
    for key, increment in dict(
        transformation.get("canonical_inputs_add", {})
    ).items():
        if key not in inputs:
            raise Phase49RunError(f"cannot add to absent input {key}")
        inputs[str(key)] = _finite(inputs[key], str(key)) + _finite(
            increment, str(key)
        )
    return inputs


def _product_options(transformation: Mapping[str, Any]) -> ProductOptions:
    return ProductOptions(
        quantity_units=transformation.get("product_quantity_units"),
        quantity_values=transformation.get("product_quantity_values"),
        extra_inputs=transformation.get("product_extra_inputs"),
        coordinate_overrides=transformation.get("product_coordinate_overrides"),
    )


def _relation_oracle(
    base: OracleCase,
    relation: Mapping[str, Any],
    transformed_inputs: Mapping[str, Any],
    *,
    secondary_coordinates: bool = False,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> OracleCase:
    raw_outputs = relation.get("transformed_expected_outputs")
    if not isinstance(raw_outputs, list):
        raise Phase49RunError("transformed_expected_outputs must be a list")
    by_key = {str(item["output_key"]): item for item in raw_outputs}
    if tuple(by_key) != PRIMARY_OUTPUT_CONTRACT[base.family]:
        raise Phase49RunError(
            f"{relation['relation_id']} violates primary output contract"
        )
    coordinate_overrides = dict(
        relation.get("transformation", {}).get(
            "product_coordinate_overrides", {}
        )
    )
    outputs: list[ExpectedSemanticOutput] = []
    for original in base.expected_outputs:
        raw = by_key[original.output_key]
        numeric = _finite(raw["numeric"], "transformed expected numeric")
        direction = original.positive_direction
        if not secondary_coordinates:
            direction = str(
                coordinate_overrides.get("positive_direction", direction)
            )
        outputs.append(
            replace(
                original,
                numeric=numeric,
                unit=str(raw["unit"]),
                sign=_sign(numeric, policy),
                root_values=(numeric,),
                positive_direction=direction,
            )
        )
    anchor = relation.get("analytic_anchor") or {}
    derivation = str(
        anchor.get("derivation")
        or relation.get("expected_relation", {}).get("statement")
        or "Fixed metamorphic relation."
    )
    return OracleCase(
        oracle_id=str(relation["relation_id"]),
        family=base.family,
        problem=f"Metamorphic transform of {base.oracle_id}",
        expected_outcome="solved",
        expected_applicability="applicable",
        canonical_inputs=transformed_inputs,
        solver_id=base.solver_id,
        expected_outputs=tuple(outputs),
        source="Independent hand-derived metamorphic fixture.",
        derivation=derivation,
        independence_note=(
            "The fixed expectation predates execution and is not copied from "
            "the product observation."
        ),
        provenance_kind=INDEPENDENT_PROVENANCE,
        oracle_version=base.oracle_version,
        benchmark_version=base.benchmark_version,
        policy_version=base.policy_version,
    )


def _payload(report: Any) -> dict[str, Any]:
    return report.to_dict()


def _passed_status(value: Any) -> bool:
    return str(value) in {
        VerificationStatus.PASSED.value,
        VerificationStatus.PASSED_WITH_WARNING.value,
    }


def _simple_report(report: VerificationReport) -> dict[str, Any]:
    return {
        "passed": bool(report.passed),
        "policy_version": report.policy_version,
        "checks": list(report.checks),
        "warnings": list(report.warnings),
        "errors": list(report.errors),
        "structured_checks": [dict(item) for item in report.structured_checks],
    }


def _add_numeric_check(
    report: VerificationReport,
    *,
    check_id: str,
    observed: float,
    expected: float,
    message: str,
    policy: TolerancePolicy,
) -> None:
    scale = max(abs(observed), abs(expected), 1.0)
    tolerance = policy.tolerance("absolute", scale=scale)
    absolute_error = abs(observed - expected)
    relative_error = absolute_error / max(abs(expected), policy.near_zero_tol)
    record_verification_check(
        report,
        VerificationCheck(
            check_id=check_id,
            category="numeric",
            status=(
                VerificationStatus.PASSED
                if absolute_error <= tolerance
                else VerificationStatus.FAILED
            ),
            applicability=VerificationApplicability.APPLICABLE,
            observed=observed,
            expected=expected,
            absolute_error=absolute_error,
            relative_error=relative_error,
            tolerance=tolerance,
            message=message,
            evidence=("typed numeric field; display text was not inspected",),
            source_equation_ids=EQUATION_ROLE_CONTRACT["incline"],
            metadata={
                "policy_version": policy.policy_version,
                "offline_only": True,
            },
        ),
    )


def _paraphrase_observation(
    relation_id: str,
    label: str,
    text: str,
    expected: float,
    *,
    policy: TolerancePolicy,
) -> tuple[dict[str, Any], float]:
    response = solve_problem(text)
    report = VerificationReport(passed=True, policy_version=policy.policy_version)
    selected = getattr(
        getattr(response, "route_decision", None),
        "selected_solver_id",
        None,
    )
    route_ok = bool(response.ok) and selected == "incline_no_friction"
    record_verification_check(
        report,
        VerificationCheck(
            check_id=f"{relation_id}:{label}:route",
            category="path_contract",
            status=(
                VerificationStatus.PASSED
                if route_ok
                else VerificationStatus.FAILED
            ),
            applicability=VerificationApplicability.APPLICABLE,
            observed={
                "ok": bool(response.ok),
                "selected_solver_id": selected,
            },
            expected={
                "ok": True,
                "selected_solver_id": "incline_no_friction",
            },
            message="actual extraction, routing, selection and solver path",
            evidence=(label + " problem text",),
            source_equation_ids=EQUATION_ROLE_CONTRACT["incline"],
            metadata={
                "policy_version": policy.policy_version,
                "offline_only": True,
            },
        ),
    )
    answer = getattr(response, "answer", None)
    numeric = getattr(answer, "numeric", None)
    observed = float(numeric) if numeric is not None else math.inf
    _add_numeric_check(
        report,
        check_id=f"{relation_id}:{label}:numeric",
        observed=observed,
        expected=expected,
        message="paraphrase preserves fixed analytic acceleration",
        policy=policy,
    )
    report.passed = all(
        _passed_status(item.get("status"))
        for item in report.structured_checks
    )
    return _simple_report(report), observed


def run_metamorphic_relation(
    relation: Mapping[str, Any],
    suite: OracleSuite,
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> dict[str, Any]:
    base = suite.by_id[str(relation["base_oracle_id"])]
    transformation = dict(relation["transformation"])
    transformed_inputs = _transform_inputs(
        base.canonical_inputs, transformation
    )
    transformed = _relation_oracle(
        base,
        relation,
        transformed_inputs,
        policy=policy,
    )
    secondary_transformed = _relation_oracle(
        base,
        relation,
        transformed_inputs,
        secondary_coordinates=True,
        policy=policy,
    )

    if relation["relation_kind"] == "actual_solver_paraphrase_invariance":
        expected = transformed.expected_outputs[0].numeric
        base_product, base_value = _paraphrase_observation(
            str(relation["relation_id"]),
            "base",
            str(transformation["base_problem_text"]),
            base.expected_outputs[0].numeric,
            policy=policy,
        )
        transformed_product, transformed_value = _paraphrase_observation(
            str(relation["relation_id"]),
            "transformed",
            str(transformation["transformed_problem_text"]),
            expected,
            policy=policy,
        )
        base_secondary = compare_oracle_observation(
            base,
            evaluate_secondary_analytic(
                base.family, base.canonical_inputs, policy=policy
            ),
            policy=policy,
        )
        transformed_secondary = compare_oracle_observation(
            secondary_transformed,
            evaluate_secondary_analytic(
                base.family, transformed_inputs, policy=policy
            ),
            policy=policy,
        )
        relation_error = abs(base_value - transformed_value)
        relation_tolerance = policy.tolerance(
            "absolute",
            scale=max(abs(base_value), abs(transformed_value), 1.0),
        )
        relation_passed = relation_error <= relation_tolerance
        passed = bool(
            base_product["passed"]
            and transformed_product["passed"]
            and base_secondary.passed
            and transformed_secondary.passed
            and relation_passed
        )
        return {
            "relation_id": relation["relation_id"],
            "relation_kind": relation["relation_kind"],
            "family": base.family,
            "passed": passed,
            "product_base_report": base_product,
            "product_transformed_report": transformed_product,
            "secondary_base_report": _payload(base_secondary),
            "secondary_transformed_report": _payload(
                transformed_secondary
            ),
            "relation_assertion": {
                "passed": relation_passed,
                "observed_absolute_difference": relation_error,
                "tolerance": relation_tolerance,
            },
            "analytic_anchor": relation["analytic_anchor"],
        }

    base_product_execution = run_product_case(base, policy=policy)
    transformed_product_execution = run_product_case(
        transformed,
        options=_product_options(transformation),
        policy=policy,
    )
    base_product = compare_oracle_observation(
        base, base_product_execution.observation, policy=policy
    )
    transformed_product = compare_oracle_observation(
        transformed,
        transformed_product_execution.observation,
        policy=policy,
    )
    base_secondary = compare_oracle_observation(
        base,
        evaluate_secondary_analytic(
            base.family, base.canonical_inputs, policy=policy
        ),
        policy=policy,
    )
    transformed_secondary = compare_oracle_observation(
        secondary_transformed,
        evaluate_secondary_analytic(
            base.family, transformed_inputs, policy=policy
        ),
        policy=policy,
    )
    anchor_ok = bool(
        relation.get("analytic_anchor", {}).get("equation_roles")
        and relation.get("analytic_anchor", {}).get("derivation")
    )
    relation_passed = bool(
        base_product.passed
        and transformed_product.passed
        and base_secondary.passed
        and transformed_secondary.passed
        and anchor_ok
    )
    return {
        "relation_id": relation["relation_id"],
        "relation_kind": relation["relation_kind"],
        "family": base.family,
        "passed": relation_passed,
        "product_base_report": _payload(base_product),
        "product_transformed_report": _payload(transformed_product),
        "secondary_base_report": _payload(base_secondary),
        "secondary_transformed_report": _payload(transformed_secondary),
        "relation_assertion": {
            "passed": relation_passed,
            "expected_relation": relation["expected_relation"],
        },
        "analytic_anchor": relation["analytic_anchor"],
    }


def _failed_categories(report: Any) -> set[str]:
    return {
        str(item.get("category"))
        for item in report.verification_report.structured_checks
        if not _passed_status(item.get("status"))
    }


def run_mutation_control(
    control: Mapping[str, Any],
    suite: OracleSuite,
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> dict[str, Any]:
    case = suite.by_id[str(control["baseline_oracle_id"])]
    actual = run_product_case(case, policy=policy)
    baseline = compare_oracle_observation(
        case, actual.observation, policy=policy
    )
    target = str(control["semantic_output_key"])
    mutation = dict(control["observation_mutation"])
    outputs: list[ObservedSemanticOutput] = []
    found = False
    for item in actual.observation.outputs:
        if item.output_key != target:
            outputs.append(item)
            continue
        found = True
        numeric = item.numeric
        unit = item.unit
        sign = item.sign
        equation_ids = item.equation_ids
        if mutation.get("numeric_transform") == "negate":
            numeric = -numeric
            sign = _sign(numeric, policy)
        if "replace_numeric" in mutation:
            numeric = _finite(
                mutation["replace_numeric"], "mutation numeric"
            )
            sign = _sign(numeric, policy)
        if "replace_unit" in mutation:
            unit = str(mutation["replace_unit"])
        if "replace_equation_ids" in mutation:
            equation_ids = tuple(
                str(value)
                for value in mutation["replace_equation_ids"]
            )
        outputs.append(
            replace(
                item,
                numeric=numeric,
                unit=unit,
                sign=sign,
                equation_ids=equation_ids,
            )
        )
    if not found:
        raise Phase49RunError(f"mutation target {target} is absent")
    mutated = SolverPathObservation(
        path_id=actual.observation.path_id + ".mutation",
        family=actual.observation.family,
        solver_id=actual.observation.solver_id,
        outputs=tuple(outputs),
        policy_version=actual.observation.policy_version,
        applicability=actual.observation.applicability,
        message=actual.observation.message,
        metadata={
            **dict(actual.observation.metadata),
            "mutation_id": control["mutation_id"],
        },
    )
    mutant = compare_oracle_observation(case, mutated, policy=policy)
    actual_failed = _failed_categories(mutant)
    expected_failed = {
        str(item) for item in control["expected_failed_categories"]
    }
    killed = bool(
        baseline.passed
        and not mutant.passed
        and expected_failed <= actual_failed
    )
    return {
        "mutation_id": control["mutation_id"],
        "kind": control["kind"],
        "baseline_oracle_id": case.oracle_id,
        "passed": killed,
        "baseline_passed": baseline.passed,
        "mutant_passed": mutant.passed,
        "expected_failed_categories": sorted(expected_failed),
        "actual_failed_categories": sorted(actual_failed),
        "baseline_report": _payload(baseline),
        "mutant_report": _payload(mutant),
    }


def _path_roles_payload() -> dict[str, Any]:
    matrix = load_capability_matrix()
    payload: dict[str, Any] = {}
    for family in sorted(PRIMARY_OUTPUT_CONTRACT):
        raw = matrix.path_roles_for_family(family)
        if raw is None:
            raise Phase49RunError(f"missing path roles for {family}")
        payload[family] = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in raw.items()
        }
    return payload


def run_suite(
    *,
    oracle_path: str | Path = DEFAULT_ORACLE_PATH,
    metamorphic_path: str | Path = DEFAULT_METAMORPHIC_PATH,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> dict[str, Any]:
    suite = load_oracle_suite(
        oracle_path,
        minimum_cases=60,
        minimum_per_family={
            family: 10 for family in PRIMARY_OUTPUT_CONTRACT
        },
    )
    if len(suite.cases) != 60:
        raise Phase49RunError("oracle suite must contain exactly 60 cases")
    scalar_outputs = sum(
        len(case.expected_outputs) for case in suite.cases
    )
    if scalar_outputs != 70:
        raise Phase49RunError(
            "oracle suite must contain exactly 70 scalar outputs"
        )
    metamorphic = load_metamorphic_fixture(metamorphic_path)
    if (
        metamorphic["oracle_version"] != suite.oracle_version
        or metamorphic["benchmark_version"] != suite.benchmark_version
    ):
        raise Phase49RunError("oracle/metamorphic version mismatch")
    if len(metamorphic["relations"]) != 21:
        raise Phase49RunError(
            "metamorphic fixture must contain exactly 21 relations"
        )

    case_reports: list[dict[str, Any]] = []
    for case in suite.cases:
        product_execution = run_product_case(case, policy=policy)
        product = compare_oracle_observation(
            case, product_execution.observation, policy=policy
        )
        secondary_observation = evaluate_secondary_analytic(
            case.family,
            case.canonical_inputs,
            policy=policy,
        )
        secondary = compare_oracle_observation(
            case, secondary_observation, policy=policy
        )
        case_passed = bool(product.passed and secondary.passed)
        case_reports.append(
            {
                "oracle_id": case.oracle_id,
                "family": case.family,
                "solver_id": case.solver_id,
                "passed": case_passed,
                "selection_status": product_execution.selection_status,
                "product_report": _payload(product),
                "secondary_report": _payload(secondary),
            }
        )

    relation_reports = [
        run_metamorphic_relation(item, suite, policy=policy)
        for item in metamorphic["relations"]
    ]
    failed_relations = [
        item["relation_id"]
        for item in relation_reports
        if not item["passed"]
    ]

    mutation_reports = [
        run_mutation_control(item, suite, policy=policy)
        for item in metamorphic["mutation_controls"]
    ]
    failed_mutations = [
        item["mutation_id"]
        for item in mutation_reports
        if not item["passed"]
    ]
    family_counts = {
        family: sum(
            case.family == family for case in suite.cases
        )
        for family in sorted(PRIMARY_OUTPUT_CONTRACT)
    }
    summary = {
        "oracle_cases": len(case_reports),
        "scalar_expected_outputs": scalar_outputs,
        "family_counts": family_counts,
        "product_path_passed": sum(
            bool(item["product_report"]["passed"])
            for item in case_reports
        ),
        "secondary_path_passed": sum(
            bool(item["secondary_report"]["passed"])
            for item in case_reports
        ),
        "distinct_metamorphic_relations": len(
            {
                item["relation_kind"]
                for item in relation_reports
            }
        ),
        "metamorphic_passed": sum(
            bool(item["passed"]) for item in relation_reports
        ),
        "mutation_controls": len(mutation_reports),
        "mutations_killed": sum(
            bool(item["passed"]) for item in mutation_reports
        ),
    }
    failed_cases = [
        item["oracle_id"] for item in case_reports if not item["passed"]
    ]
    disagreements = (
        [{"kind": "oracle_case", "id": item} for item in failed_cases]
        + [
            {"kind": "metamorphic_relation", "id": item}
            for item in failed_relations
        ]
        + [
            {"kind": "mutation_control", "id": item}
            for item in failed_mutations
        ]
    )
    all_passed = (
        not disagreements
        and summary["product_path_passed"] == 60
        and summary["secondary_path_passed"] == 60
        and summary["distinct_metamorphic_relations"] == 21
        and summary["metamorphic_passed"] == 21
        and summary["mutation_controls"] == 4
        and summary["mutations_killed"] == 4
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_version": REPORT_VERSION,
        "oracle_schema_version": 2,
        "status": "passed" if all_passed else "failed",
        "passed": all_passed,
        "oracle_version": suite.oracle_version,
        "benchmark_version": suite.benchmark_version,
        "relation_version": metamorphic["relation_version"],
        "policy_version": policy.policy_version,
        "offline_only": True,
        "student_answer_overwrite": False,
        "path_roles": _path_roles_payload(),
        "summary": summary,
        "disagreements": disagreements,
        "cases": case_reports,
        "metamorphic_relations": relation_reports,
        "mutation_controls": mutation_reports,
    }


def render_json(report: Mapping[str, Any]) -> str:
    return json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Phase 49 Solver Consistency Report",
        "",
        f"- Status: {str(report['status']).upper()}",
        f"- Oracle version: {report['oracle_version']}",
        f"- Benchmark version: {report['benchmark_version']}",
        f"- Metamorphic version: {report['relation_version']}",
        f"- Tolerance policy: {report['policy_version']}",
        "- Offline only; student answers are never overwritten.",
        "",
        "## Coverage",
        "",
        "| Evidence | Passed / Total |",
        "|---|---:|",
        (
            "| Product oracle paths | "
            f"{summary['product_path_passed']} / "
            f"{summary['oracle_cases']} |"
        ),
        (
            "| Secondary analytic paths | "
            f"{summary['secondary_path_passed']} / "
            f"{summary['oracle_cases']} |"
        ),
        (
            "| Distinct metamorphic relations | "
            f"{summary['metamorphic_passed']} / "
            f"{summary['distinct_metamorphic_relations']} |"
        ),
        (
            "| Mutation controls killed | "
            f"{summary['mutations_killed']} / "
            f"{summary['mutation_controls']} |"
        ),
        (
            "| Scalar fixed expectations | "
            f"{summary['scalar_expected_outputs']} |"
        ),
        "",
        "## Family coverage",
        "",
        "| Family | Cases |",
        "|---|---:|",
    ]
    for family, count in summary["family_counts"].items():
        lines.append(f"| {family} | {count} |")
    lines.extend(["", "## Path roles", ""])
    for family, roles in report["path_roles"].items():
        lines.append(
            f"- {family}: student={roles['student_answer_path']}; "
            f"secondary={roles['secondary_analytic_path']}; "
            f"numeric={roles['numeric_validation_path']}; "
            f"external={roles['external_validation_path']}; "
            f"fallback={roles['fallback_path']}"
        )
    failures: list[str] = []
    failures.extend(
        item["oracle_id"]
        for item in report["cases"]
        if not item["passed"]
    )
    failures.extend(
        item["relation_id"]
        for item in report["metamorphic_relations"]
        if not item["passed"]
    )
    failures.extend(
        item["mutation_id"]
        for item in report["mutation_controls"]
        if not item["passed"]
    )
    lines.extend(["", "## Disagreements", ""])
    if failures:
        lines.extend(f"- {item}" for item in failures)
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def write_reports(
    report: Mapping[str, Any],
    *,
    json_path: str | Path = DEFAULT_JSON_REPORT,
    markdown_path: str | Path = DEFAULT_MARKDOWN_REPORT,
) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(render_json(report), encoding="utf-8")
    markdown_target.write_text(
        render_markdown(report), encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--oracle", type=Path, default=DEFAULT_ORACLE_PATH
    )
    parser.add_argument(
        "--metamorphic",
        type=Path,
        default=DEFAULT_METAMORPHIC_PATH,
    )
    parser.add_argument(
        "--json-out", type=Path, default=DEFAULT_JSON_REPORT
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=DEFAULT_MARKDOWN_REPORT,
    )
    arguments = parser.parse_args(argv)
    try:
        report = run_suite(
            oracle_path=arguments.oracle,
            metamorphic_path=arguments.metamorphic,
        )
        write_reports(
            report,
            json_path=arguments.json_out,
            markdown_path=arguments.markdown_out,
        )
    except Exception as exc:
        print(f"Phase 49 consistency run failed: {exc}", file=sys.stderr)
        return 1
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
