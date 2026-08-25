from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
from typing import Callable

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
)
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.migration import (
    DifferentialStatus,
    InvarianceVariantKind,
    LabelledIRProbeVariant,
    LegacyCandidateScalar,
    LegacyDifferentialReport,
    LegacyObservation,
    LegacyTerminal,
    MechanicsMigrationInvarianceComparison,
    MechanicsMigrationProbeExecution,
    MigrationProbeTerminal,
    build_generic_result_invariance_signature,
    build_legacy_differential_report,
    compare_mechanics_ir_invariance,
    execute_mechanics_ir_probe,
)
from engine.mechanics.normalization import NormalizationResult, normalize_draft
from engine.mechanics.solver.contracts import CandidateCoverage, SolveBackendKind
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import ValidationTerminal
from engine.mechanics.verification.contracts import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity, SolverResult
from engine.solvers.incline import InclineNoFrictionSolver


DIMENSIONLESS = DimensionVector.dimensionless()
MASS = DimensionVector(mass=1)
FORCE = DimensionVector(mass=1, length=1, time=-2)
ACCELERATION = DimensionVector(length=1, time=-2)


@dataclass(frozen=True)
class InclineSource:
    problem_text: str
    mass_si: float
    gravity_si: float
    theta_deg: float
    query_sign: int
    query_direction: str

    def __post_init__(self) -> None:
        if type(self.mass_si) is not float or not math.isfinite(self.mass_si) or self.mass_si <= 0:
            raise ValueError("mass must be one positive finite float")
        if type(self.gravity_si) is not float or not math.isfinite(self.gravity_si) or self.gravity_si <= 0:
            raise ValueError("gravity must be one positive finite float")
        if type(self.theta_deg) is not float or not math.isfinite(self.theta_deg):
            raise ValueError("incline angle must be one finite float")
        bound_direction = {1: "downslope", -1: "upslope"}.get(self.query_sign)
        if self.query_direction != bound_direction:
            raise ValueError("query direction text and typed sign must agree")

    @property
    def theta_rad(self) -> float:
        return math.radians(self.theta_deg)


@dataclass(frozen=True)
class InclineResiduals:
    tangential_projection: float
    tangential_newton: float
    normal_projection: float
    normal_newton: float
    contact_acceleration: float
    projection_coherence: float
    normal_force_si: float

    @property
    def passed(self) -> bool:
        residuals = (
            self.tangential_projection, self.tangential_newton,
            self.normal_projection, self.normal_newton,
            self.contact_acceleration, self.projection_coherence,
        )
        return all(abs(value) <= 1.0e-10 for value in residuals) and self.normal_force_si >= -1.0e-10


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport
    invariance: MechanicsMigrationInvarianceComparison
    residuals: InclineResiduals


def _source(theta_deg: float, query_sign: int = 1) -> InclineSource:
    direction = "downslope" if query_sign == 1 else "upslope"
    theta_text = f"{theta_deg:g}"
    problem_text = (
        f"A 2 kg particle remains in frictionless contact with a straight incline "
        f"at {theta_text} deg. Take g = 9.81 m/s^2. The straight incline is fixed. "
        f"The +tangent axis points downslope and the +normal axis points away from "
        f"the surface. Find its acceleration along the {direction} direction."
    )
    return InclineSource(
        problem_text=problem_text,
        mass_si=2.0,
        gravity_si=9.81,
        theta_deg=float(theta_deg),
        query_sign=query_sign,
        query_direction=direction,
    )


INTERIOR_DOWNSLOPE = _source(37.0)


def _text_evidence(
    source_text: str,
    *,
    evidence_id: str,
    quote: str,
    quantity_token: str | None = None,
) -> dict[str, object]:
    start = source_text.index(quote)
    payload: dict[str, object] = {
        "kind": "text",
        "evidence_id": evidence_id,
        "quote": quote,
        "source_span": {"start": start, "end": start + len(quote)},
        "quantity_span": None,
        "occurrence_index": source_text[:start].count(quote),
    }
    if quantity_token is not None:
        quantity_start = start + quote.index(quantity_token)
        payload["quantity_span"] = {
            "start": quantity_start,
            "end": quantity_start + len(quantity_token),
        }
    return payload


def _symbol(
    symbol_id: str,
    quantity_id: str,
    dimension: DimensionVector,
) -> dict[str, object]:
    return {
        "symbol_id": symbol_id,
        "quantity_id": quantity_id,
        "dimension": dimension.model_dump(mode="json"),
        "shape": "scalar",
    }


def _quantity(
    quantity_id: str,
    symbol_id: str,
    role: str,
    subject_id: str,
    dimension: DimensionVector,
    *,
    point_id: str | None = None,
    frame_id: str | None = None,
    interval_id: str | None = None,
    component: str = "unspecified",
    direction: dict[str, object] | None = None,
    provenance: str = "inferred",
    evidence_refs: tuple[str, ...] = (),
    raw_value: str | None = None,
    raw_unit: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "quantity_id": quantity_id,
        "symbol_id": symbol_id,
        "role": role,
        "subject_id": subject_id,
        "component": component,
        "shape": "scalar",
        "dimension": dimension.model_dump(mode="json"),
        "provenance": provenance,
        "evidence_refs": list(evidence_refs),
    }
    for key, value in (
        ("point_id", point_id),
        ("frame_id", frame_id),
        ("interval_id", interval_id),
        ("direction", direction),
        ("raw_value", raw_value),
        ("raw_unit", raw_unit),
    ):
        if value is not None:
            payload[key] = value
    return payload


def _axis_direction(
    axis: str, sign: int = 1, frame_id: str = "inclineFrame"
) -> dict[str, object]:
    return {
        "kind": "axis",
        "frame_id": frame_id,
        "axis": axis,
        "sign": sign,
    }


def _axis_binding(axis: str, *, frame_id: str) -> dict[str, object]:
    return {"axis": axis, "direction": _axis_direction(axis, frame_id=frame_id)}


def _draft_payload(source: InclineSource) -> dict[str, object]:
    mass_raw = f"{source.mass_si:g}"
    gravity_raw = f"{source.gravity_si:g}"
    theta_raw = f"{source.theta_deg:g}"
    mass_token = f"{mass_raw} kg"
    gravity_token = f"{gravity_raw} m/s^2"
    theta_token = f"{theta_raw} deg"
    contact_quote = "remains in frictionless contact with a straight incline"
    fixed_quote = "The straight incline is fixed"
    orientation_quote = (
        "The +tangent axis points downslope and the +normal axis points away from "
        "the surface"
    )
    query_quote = f"along the {source.query_direction} direction"
    evidence_specs = (
        ("massEvidence", mass_token, mass_token),
        ("angleEvidence", theta_token, theta_token),
        ("gravityEvidence", gravity_token, gravity_token),
        ("contactEvidence", contact_quote, None),
        ("frictionlessEvidence", "frictionless", None),
        ("fixedInclineEvidence", fixed_quote, None),
        ("orientationEvidence", orientation_quote, None),
        ("queryEvidence", query_quote, None),
    )
    evidence = [
        _text_evidence(
            source.problem_text,
            evidence_id=evidence_id,
            quote=quote,
            quantity_token=quantity_token,
        )
        for evidence_id, quote, quantity_token in evidence_specs
    ]
    symbols = [
        _symbol(*spec)
        for spec in (
            ("mA", "massA", MASS),
            ("gA", "gravityA", ACCELERATION),
            ("thetaA", "angleA", DIMENSIONLESS),
            ("fgT", "gravityT", FORCE),
            ("fgN", "gravityN", FORCE),
            ("normalA", "normalForceA", FORCE),
            ("aT", "accelerationT", ACCELERATION),
            ("aN", "accelerationN", ACCELERATION),
        )
    ]
    known_specs = (
        ("massA", "mA", "mass", "bodyA", MASS, "massEvidence", mass_raw, "kg"),
        (
            "gravityA", "gA", "gravity", "worldA", ACCELERATION,
            "gravityEvidence", gravity_raw, "m/s^2",
        ),
        (
            "angleA", "thetaA", "angle", "inclineA", DIMENSIONLESS,
            "angleEvidence", theta_raw, "deg",
        ),
    )
    quantities = [
        _quantity(
            quantity_id, symbol_id, role, subject_id, dimension,
            provenance="explicit_source", evidence_refs=(evidence_id,),
            raw_value=raw_value, raw_unit=raw_unit,
        )
        for (
            quantity_id, symbol_id, role, subject_id, dimension,
            evidence_id, raw_value, raw_unit,
        ) in known_specs
    ]
    unknown_specs = (
        ("gravityT", "fgT", "force", FORCE, None, "tangential", "tangent", 1,
         ("gravityEvidence", "orientationEvidence")),
        ("gravityN", "fgN", "force", FORCE, None, "normal", "normal", -1,
         ("gravityEvidence", "orientationEvidence")),
        ("normalForceA", "normalA", "force", FORCE, "contactA", "normal", "normal", 1,
         ("contactEvidence", "orientationEvidence")),
        ("accelerationT", "aT", "acceleration", ACCELERATION, None,
         "tangential", "tangent", source.query_sign,
         ("orientationEvidence", "queryEvidence")),
        ("accelerationN", "aN", "acceleration", ACCELERATION, None,
         "normal", "normal", 1, ("contactEvidence", "orientationEvidence")),
    )
    quantities.extend(
        _quantity(
            quantity_id, symbol_id, role, "bodyA", dimension,
            point_id=point_id, frame_id="inclineFrame", interval_id="interval1",
            component=component, direction=_axis_direction(axis, sign),
            evidence_refs=evidence_refs,
        )
        for (
            quantity_id, symbol_id, role, dimension, point_id, component,
            axis, sign, evidence_refs,
        ) in unknown_specs
    )
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnosticInclineLabel",
            "subtype": "diagnosticFrictionLabel",
            "model_id": "sameFixtureInclineTest",
            "source_text_sha256": hashlib.sha256(
                source.problem_text.encode("utf-8")
            ).hexdigest(),
        },
        "source_assets": [],
        "source_evidence": evidence,
        "entities": [
            {"entity_id": "bodyA", "primitive": "particle",
             "evidence_refs": ["massEvidence", "contactEvidence"]},
            {"entity_id": "inclineA", "primitive": "incline",
             "evidence_refs": ["angleEvidence", "contactEvidence",
                               "fixedInclineEvidence", "orientationEvidence"]},
            {"entity_id": "worldA", "primitive": "environment",
             "evidence_refs": ["gravityEvidence"]},
        ],
        "points": [
            {
                "point_id": "contactA",
                "role": "contact",
                "owner_entity_id": "bodyA",
                "frame_id": "inclineFrame",
                "evidence_refs": ["contactEvidence"],
            }
        ],
        "reference_frames": [
            {
                "frame_id": "worldFrame",
                "frame_type": "cartesian_2d",
                "origin": {"kind": "world"},
                "axes": [
                    _axis_binding(axis, frame_id="worldFrame")
                    for axis in ("x", "y")
                ],
                "evidence_refs": ["gravityEvidence"],
            },
            {
                "frame_id": "inclineFrame",
                "frame_type": "tangential_normal",
                "origin": {"kind": "entity", "entity_id": "inclineA"},
                "axes": [
                    _axis_binding(axis, frame_id="inclineFrame")
                    for axis in ("tangent", "normal")
                ],
                "parent_frame_id": "worldFrame",
                "evidence_refs": ["orientationEvidence"],
            },
        ],
        "motion_intervals": [
            {
                "interval_id": "interval1",
                "order": 1,
                "subject_ids": ["bodyA", "inclineA", "worldA"],
                "frame_id": "inclineFrame",
                "evidence_refs": [
                    "contactEvidence",
                    "fixedInclineEvidence",
                    "frictionlessEvidence",
                ],
            }
        ],
        "events": [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": [
            {
                "relation_id": "angleOfIncline",
                "kind": "angle",
                "participant_ids": ["inclineA", "worldA"],
                "quantity_ids": ["angleA"],
                "evidence_refs": ["angleEvidence", "orientationEvidence"],
            }
        ],
        "interactions": [
            {
                "interaction_id": "gravityInteraction",
                "kind": "gravity",
                "participant_ids": ["bodyA", "worldA"],
                "frame_id": "inclineFrame",
                "interval_id": "interval1",
                "quantity_ids": [
                    "massA",
                    "gravityA",
                    "gravityT",
                    "gravityN",
                ],
                "evidence_refs": [
                    "gravityEvidence",
                    "angleEvidence",
                    "orientationEvidence",
                ],
            },
            {
                "interaction_id": "contactInteraction",
                "kind": "contact",
                "participant_ids": ["bodyA", "inclineA"],
                "point_ids": ["contactA"],
                "frame_id": "inclineFrame",
                "interval_id": "interval1",
                "quantity_ids": ["normalForceA", "accelerationN"],
                "evidence_refs": ["contactEvidence", "frictionlessEvidence"],
            },
        ],
        "constraints": [],
        "state_conditions": [
            {"state_condition_id": "frictionlessState", "kind": "friction",
             "state": "inactive", "subject_id": "bodyA", "interval_id": "interval1",
             "evidence_refs": ["frictionlessEvidence"]},
            {"state_condition_id": "contactState", "kind": "contact",
             "state": "touching", "subject_id": "bodyA", "interval_id": "interval1",
             "quantity_ids": ["normalForceA", "accelerationN"],
             "evidence_refs": ["contactEvidence"]},
            {"state_condition_id": "fixedInclineState", "kind": "motion",
             "state": "at_rest", "subject_id": "inclineA", "interval_id": "interval1",
             "evidence_refs": ["fixedInclineEvidence"]},
        ],
        "queries": [
            {
                "query_id": "queryA",
                "target": {
                    "role": "acceleration",
                    "subject_id": "bodyA",
                    "frame_id": "inclineFrame",
                    "interval_id": "interval1",
                    "component": "tangential",
                    "direction": _axis_direction("tangent", source.query_sign),
                    "target_quantity_id": "accelerationT",
                },
                "output_unit": "m/s^2",
                "output_dimension": ACCELERATION.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": ["queryEvidence"],
            }
        ],
        "principle_hints": [],
        "assumptions": [],
        "ambiguities": [],
        "figure_dependency": {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        },
        "unsupported_features": [],
    }


PayloadMutation = Callable[[dict[str, object]], None]


def _normalize_incline(
    source: InclineSource,
    *,
    mutate: PayloadMutation | None = None,
) -> NormalizationResult:
    payload = _draft_payload(source)
    if mutate is not None:
        mutate(payload)
    draft = MechanicsProblemDraftV1.model_validate(payload)
    return normalize_draft(source.problem_text, draft)


def _build_incline_ir(source: InclineSource) -> MechanicsProblemIRV1:
    normalization = _normalize_incline(source)
    assert normalization.terminal is ValidationTerminal.accepted
    assert normalization.accepted is True
    assert type(normalization.ir) is MechanicsProblemIRV1
    return normalization.ir


def _candidate_values(execution: MechanicsMigrationProbeExecution) -> dict[str, float]:
    result = execution.solve_result
    assert result is not None
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    values = {item.symbol_id: item.value_si for item in candidate.values}
    assert all(type(value) is float for value in values.values())
    return {key: value for key, value in values.items() if type(value) is float}


def _independent_generic_residuals(
    source: InclineSource,
    values: dict[str, float],
) -> InclineResiduals:
    required = {"aT", "aN", "fgT", "fgN", "normalA"}
    assert required.issubset(values)
    mass = source.mass_si
    gravity = source.gravity_si
    theta = source.theta_rad
    physical_downslope_acceleration = source.query_sign * values["aT"]
    return InclineResiduals(
        tangential_projection=(
            values["fgT"] - mass * gravity * math.sin(theta)
        ),
        tangential_newton=(
            values["fgT"] - mass * physical_downslope_acceleration
        ),
        normal_projection=(
            values["fgN"] - mass * gravity * math.cos(theta)
        ),
        normal_newton=(
            values["normalA"] - values["fgN"] - mass * values["aN"]
        ),
        contact_acceleration=values["aN"],
        projection_coherence=(
            math.hypot(values["fgT"], values["fgN"]) - mass * gravity
        ),
        normal_force_si=values["normalA"],
    )


def _observe_incline_legacy(
    source: InclineSource,
) -> tuple[LegacyObservation, SolverResult]:
    # These two labels exist only as the direct legacy solver's compatibility
    # adapter. The generic execution is already frozen before this is called.
    compatibility_system_type = "particle_on_incline"
    compatibility_subtype = "no_friction"
    problem = CanonicalProblem(
        system_type=compatibility_system_type,
        subtype=compatibility_subtype,
        knowns={
            "m": Quantity("m", source.mass_si, "kg"),
            "g": Quantity("g", source.gravity_si, "m/s^2"),
            "theta": Quantity("theta", source.theta_deg, "deg"),
        },
        unknowns=["acceleration"],
        requested_outputs=["acceleration"],
    )
    assert problem.raw_text == ""
    result = InclineNoFrictionSolver().solve(problem)
    assert result.ok is True
    assert result.answer is not None and result.answer.unit is not None
    assert result.verification.passed is True
    decision = result.selection_decision
    assert decision is not None
    assert decision.status == "selected"
    assert decision.selected_candidate is not None
    assert decision.valid_alternatives == []
    assert decision.rejected_candidates == []
    selected = decision.selected_candidate
    assert set(selected.numerical_mapping) == {"a"}
    unrounded_downslope = selected.numerical_mapping["a"]
    assert type(unrounded_downslope) is float
    assert result.answer.numeric == round(unrounded_downslope, 5)
    assert result.answers == []
    assert result.explanation_evidence is not None
    assert len(result.explanation_evidence.outputs) == 1
    delivered = result.explanation_evidence.outputs[0]
    assert delivered.candidate_id == selected.candidate_id
    assert delivered.candidate_numeric == unrounded_downslope
    transformed_query_value = source.query_sign * unrounded_downslope
    normalized = normalize_quantity(
        str(transformed_query_value),
        result.answer.unit,
        "scalar",
        ACCELERATION,
    )
    assert type(normalized.value) is float
    tangential_residual = (
        source.mass_si * source.gravity_si * math.sin(source.theta_rad)
        - source.mass_si * source.query_sign * normalized.value
    )
    projected_tangent = (
        source.mass_si * source.gravity_si * math.sin(source.theta_rad)
    )
    projected_normal = (
        source.mass_si * source.gravity_si * math.cos(source.theta_rad)
    )
    projection_coherence = (
        math.hypot(projected_tangent, projected_normal)
        - source.mass_si * source.gravity_si
    )
    contact_ok = projected_normal >= -1.0e-10 and (
        source.theta_deg != 90.0
        or math.isclose(projected_normal, 0.0, rel_tol=0.0, abs_tol=1.0e-10)
    )
    residual_passed = (
        math.isclose(tangential_residual, 0.0, rel_tol=0.0, abs_tol=1.0e-10)
        and math.isclose(
            projection_coherence, 0.0, rel_tol=0.0, abs_tol=1.0e-10
        )
        and contact_ok
    )
    assert residual_passed is True
    observation = LegacyObservation(
        case_id=(
            f"inclineNoFriction{source.theta_deg:g}Deg"
            f"{source.query_direction.title()}"
        ),
        diagnostic_kernel_id="inclineNoFrictionDirectV1",
        terminal=LegacyTerminal.solved,
        query_symbol_id="aT",
        si_unit=normalized.si_unit,
        selected_scalar_si=normalized.value,
        complete_candidate_scalars_si=(
            LegacyCandidateScalar(value_si=normalized.value, multiplicity=1),
        ),
        residual_passed=residual_passed,
    )
    return observation, result


def _diagnostic_variant(
    ir: MechanicsProblemIRV1,
    *,
    remove: bool,
) -> MechanicsProblemIRV1:
    payload = deepcopy(ir.model_dump(mode="python", warnings="none"))
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    if remove:
        metadata["system_type"] = None
        metadata["subtype"] = None
        metadata["model_hash"] = None
        metadata["prompt_hash"] = None
        metadata["source_text_sha256"] = None
    else:
        metadata["system_type"] = "wrongDiagnosticFamily"
        metadata["subtype"] = "wrongDiagnosticSubtype"
        metadata["model_hash"] = "1" * 64
        metadata["prompt_hash"] = "2" * 64
        metadata["source_text_sha256"] = hashlib.sha256(
            b"diagnostic wording changed after physical evidence was frozen"
        ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


def _same_fixture_evidence(source: InclineSource) -> SameFixtureEvidence:
    ir = _build_incline_ir(source)
    assert "raw_text" not in type(ir).model_fields

    # Generic authority, candidate values, and signature are frozen first.
    execution = execute_mechanics_ir_probe(ir)
    assert execution.terminal is MigrationProbeTerminal.solved, (
        None
        if execution.compiler_result is None
        else execution.compiler_result.issues
    )
    assert execution.solve_result is not None
    generic_signature = build_generic_result_invariance_signature(
        execution.solve_result
    )
    residuals = _independent_generic_residuals(
        source, _candidate_values(execution)
    )
    assert residuals.passed is True

    observation, _ = _observe_incline_legacy(source)
    report = build_legacy_differential_report(execution.solve_result, observation)
    assert build_generic_result_invariance_signature(
        execution.solve_result
    ) == generic_signature

    changed = _diagnostic_variant(ir, remove=False)
    removed = _diagnostic_variant(ir, remove=True)
    assert changed.source_evidence == removed.source_evidence == ir.source_evidence
    invariance = compare_mechanics_ir_invariance(
        execution,
        (
            LabelledIRProbeVariant(
                label="changedDiagnostics",
                kind=InvarianceVariantKind.system_type_changed,
                ir=changed,
            ),
            LabelledIRProbeVariant(
                label="removedDiagnostics",
                kind=InvarianceVariantKind.system_type_removed,
                ir=removed,
            ),
        ),
    )
    return SameFixtureEvidence(
        registry_entry="incline_no_friction",
        ir=ir,
        execution=execution,
        observation=observation,
        report=report,
        invariance=invariance,
        residuals=residuals,
    )


@pytest.mark.parametrize(
    "source",
    (
        _source(0.0),
        _source(90.0),
        INTERIOR_DOWNSLOPE,
        _source(37.0, -1),
    ),
    ids=(
        "zero-degree-downslope",
        "ninety-degree-downslope",
        "interior-downslope",
        "interior-upslope-negative",
    ),
)
def test_incline_no_friction_same_fixture_full_parity_and_invariance(
    source: InclineSource,
) -> None:
    evidence = _same_fixture_evidence(source)
    execution = evidence.execution
    compiler = execution.compiler_result
    result = execution.solve_result
    assert evidence.registry_entry == "incline_no_friction"
    assert compiler is not None and compiler.graph is not None
    assert execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert execution.solve_terminal is MechanicsSolveTerminal.solved

    graph = compiler.graph
    law_ids = {item.law_id for item in graph.equations}
    assert {
        "particle_newton_second",
        "incline_gravity_tangent_projection",
        "incline_gravity_normal_projection",
        "fixed_contact_no_penetration",
        "contact_normal_bound",
    }.issubset(law_ids)
    source_quantity_ids = {
        quantity_id
        for equation in graph.equations
        for quantity_id in equation.source_quantity_ids
    }
    assert {
        "massA",
        "gravityA",
        "angleA",
        "gravityT",
        "gravityN",
        "normalForceA",
        "accelerationT",
        "accelerationN",
    }.issubset(source_quantity_ids)
    assert not any(
        quantity.si_value is not None
        for quantity in evidence.ir.quantities
        if quantity.quantity_id in {"gravityT", "gravityN", "normalForceA"}
    )

    assert result.plan.primary_backend is SolveBackendKind.linear_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert result.candidate_set.generation_complete is True
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    assert candidate.query_symbol_id == "aT"
    assert candidate.root_multiplicity == 1
    assert candidate.query_value_si == pytest.approx(
        evidence.observation.selected_scalar_si,
        rel=0.0,
        abs=1.0e-10,
    )
    assert candidate.query_value_si == pytest.approx(
        source.query_sign * source.gravity_si * math.sin(source.theta_rad),
        rel=0.0,
        abs=1.0e-10,
    )
    assert len(result.verification_outcomes) == 1
    outcome = result.verification_outcomes[0]
    assert outcome.passed is True
    residual_checks = tuple(
        check
        for check in outcome.checks
        if check.kind is VerificationCheckKind.equation_residual
    )
    assert len(residual_checks) == 1
    assert residual_checks[0].status is VerificationCheckStatus.passed
    assert residual_checks[0].measured_error == pytest.approx(0.0, abs=1.0e-10)

    assert evidence.residuals.passed is True
    assert evidence.residuals.normal_force_si >= -1.0e-10
    if source.theta_deg == 90.0:
        assert evidence.residuals.normal_force_si == pytest.approx(
            0.0, rel=0.0, abs=1.0e-10
        )
    assert evidence.observation.residual_passed is True
    assert len(evidence.observation.complete_candidate_scalars_si) == 1
    assert evidence.report.status is DifferentialStatus.full_parity
    assert evidence.report.discrepancies == ()
    assert evidence.report.observation_terminal is LegacyTerminal.solved
    assert evidence.report.generic_terminal is MechanicsSolveTerminal.solved
    assert evidence.invariance.all_invariant is True, tuple(
        (
            item.label,
            item.variant_terminal,
            item.variant_failure,
            item.matches_baseline,
            item.generic_comparison,
        )
        for item in evidence.invariance.variants
    )
    assert all(item.matches_baseline for item in evidence.invariance.variants)


@pytest.mark.parametrize(
    "source",
    (_source(-1.0), _source(91.0)),
    ids=("negative-angle", "beyond-vertical-angle"),
)
def test_incline_no_friction_rejects_angle_outside_closed_domain(
    source: InclineSource,
) -> None:
    ir = _build_incline_ir(source)
    execution = execute_mechanics_ir_probe(ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_status is not CompilerStatus.ready


def _remove_state(state_id: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        states = payload["state_conditions"]
        assert isinstance(states, list)
        payload["state_conditions"] = [
            state for state in states if state["state_condition_id"] != state_id
        ]

    return mutate


def _remove_state_authority(state_id: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        states = payload["state_conditions"]
        assert isinstance(states, list)
        state = next(
            item for item in states if item["state_condition_id"] == state_id
        )
        state["evidence_refs"] = []

    return mutate


def _unresolve_slope_axis(payload: dict[str, object]) -> None:
    frames = payload["reference_frames"]
    assert isinstance(frames, list)
    incline = next(item for item in frames if item["frame_id"] == "inclineFrame")
    incline["axes"][0]["direction"] = {
        "kind": "semantic",
        "direction": "unspecified",
    }


def _unresolve_query_direction(payload: dict[str, object]) -> None:
    quantities = payload["quantities"]
    queries = payload["queries"]
    assert isinstance(quantities, list) and isinstance(queries, list)
    acceleration = next(
        item for item in quantities if item["quantity_id"] == "accelerationT"
    )
    acceleration["direction"] = None
    queries[0]["target"]["direction"] = None


@pytest.mark.parametrize(
    "mutate",
    (
        _remove_state("frictionlessState"),
        _remove_state_authority("frictionlessState"),
        _remove_state("contactState"),
        _remove_state_authority("contactState"),
        _remove_state("fixedInclineState"),
        _remove_state_authority("fixedInclineState"),
        _unresolve_slope_axis,
        _unresolve_query_direction,
    ),
    ids=(
        "frictionless-state-removed",
        "frictionless-authority-removed",
        "contact-state-removed",
        "contact-authority-removed",
        "fixed-incline-state-removed",
        "fixed-incline-authority-removed",
        "slope-axis-unresolved",
        "query-direction-unresolved",
    ),
)
def test_incline_no_friction_missing_typed_authority_fails_closed(
    mutate: PayloadMutation,
) -> None:
    normalized = _normalize_incline(INTERIOR_DOWNSLOPE, mutate=mutate)
    assert normalized.terminal is ValidationTerminal.accepted
    assert type(normalized.ir) is MechanicsProblemIRV1
    execution = execute_mechanics_ir_probe(normalized.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    graph = execution.compiler_result.graph
    assert graph is None or not any(
        "incline" in equation.law_id for equation in graph.equations
    )


def test_incline_no_friction_declared_direction_ambiguity_needs_confirmation() -> None:
    def declare(payload: dict[str, object]) -> None:
        payload["ambiguities"] = [
            {
                "ambiguity_id": "inclineDirectionAmbiguity",
                "kind": "direction",
                "referenced_ids": [
                    "inclineFrame",
                    "accelerationT",
                    "queryA",
                ],
                "description": (
                    "The slope orientation or requested query direction is unresolved."
                ),
                "blocking": True,
                "evidence_refs": ["queryEvidence"],
            }
        ]

    normalized = _normalize_incline(INTERIOR_DOWNSLOPE, mutate=declare)

    assert normalized.terminal is ValidationTerminal.needs_confirmation
    assert normalized.ir is None
