from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
from typing import Callable

import pytest

from engine.mechanics.compiler import CompilerIssueCode, CompilerStatus
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
)
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
from engine.mechanics.solver import (
    CandidateCoverage,
    CandidateRejectionReason,
    SolveBackendKind,
)
from engine.mechanics.units import normalize_quantity
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity, SolverResult
from engine.solvers.incline import InclineWithFrictionSolver
from test_phase56_mechanics_incline_same_fixture_parity import (
    ACCELERATION,
    DIMENSIONLESS,
    FORCE,
    MASS,
    _axis_binding,
    _axis_direction,
    _quantity,
    _symbol,
    _text_evidence,
)


VELOCITY = type(ACCELERATION)(length=1, time=-1)


@dataclass(frozen=True)
class FrictionInclineSource:
    problem_text: str
    mass_si: float
    gravity_si: float
    theta_deg: float
    coefficient: float
    regime: str
    query_sign: int
    query_direction: str
    motion_sign: int
    friction_sign: int
    velocity_si: float

    def __post_init__(self) -> None:
        if (
            type(self.mass_si) is not float
            or not math.isfinite(self.mass_si)
            or self.mass_si <= 0.0
        ):
            raise ValueError("mass must be one positive finite float")
        if (
            type(self.gravity_si) is not float
            or not math.isfinite(self.gravity_si)
            or self.gravity_si <= 0.0
        ):
            raise ValueError("gravity must be one positive finite float")
        if type(self.theta_deg) is not float or not math.isfinite(self.theta_deg):
            raise ValueError("incline angle must be one finite float")
        if type(self.coefficient) is not float or not math.isfinite(self.coefficient):
            raise ValueError("friction coefficient must be one finite float")
        if self.regime not in {"sticking", "sliding"}:
            raise ValueError("friction regime must be sticking or sliding")
        bound_direction = {1: "downslope", -1: "upslope"}.get(self.query_sign)
        if self.query_direction != bound_direction:
            raise ValueError("query direction text and typed sign must agree")
        if self.motion_sign != 1:
            raise ValueError("the fixture binds the tendency or motion downslope")
        if self.friction_sign != -1:
            raise ValueError("the valid fixture binds friction opposite that motion")
        if type(self.velocity_si) is not float or not math.isfinite(self.velocity_si):
            raise ValueError("velocity must be one finite float")
        if self.regime == "sticking" and self.velocity_si != 0.0:
            raise ValueError("the sticking fixture must be at rest")
        if self.regime == "sliding" and self.velocity_si <= 0.0:
            raise ValueError("the sliding direction carrier must be positive")

    @property
    def theta_rad(self) -> float:
        return math.radians(self.theta_deg)

    @property
    def is_static(self) -> bool:
        return self.regime == "sticking"


def _source(
    theta_deg: float,
    coefficient: float,
    regime: str,
    *,
    query_sign: int = 1,
) -> FrictionInclineSource:
    query_direction = "downslope" if query_sign == 1 else "upslope"
    theta_text = f"{theta_deg:g}"
    coefficient_text = f"{coefficient:g}"
    if regime == "sticking":
        regime_text = "The contact is in the sticking static-friction regime."
        coefficient_sentence = (
            f"The coefficient of static friction is {coefficient_text}."
        )
        motion_text = "The particle remains at rest throughout the interval."
        velocity_si = 0.0
    else:
        regime_text = "The contact is in the sliding kinetic-friction regime."
        coefficient_sentence = (
            f"The coefficient of kinetic friction is {coefficient_text}."
        )
        motion_text = (
            "The particle is moving downslope and its tangential velocity is 1 m/s."
        )
        velocity_si = 1.0
    problem_text = (
        "A 2 kg particle remains in touching contact with a straight incline "
        f"at {theta_text} deg. {regime_text} {coefficient_sentence} "
        f"{motion_text} The friction force acts upslope. Take g = 9.81 m/s^2. "
        "The straight incline is fixed. The +tangent axis points downslope and "
        "the +normal axis points away from the surface. Find its acceleration "
        f"along the {query_direction} direction."
    )
    return FrictionInclineSource(
        problem_text=problem_text,
        mass_si=2.0,
        gravity_si=9.81,
        theta_deg=float(theta_deg),
        coefficient=float(coefficient),
        regime=regime,
        query_sign=query_sign,
        query_direction=query_direction,
        motion_sign=1,
        friction_sign=-1,
        velocity_si=velocity_si,
    )


STATIC_HOLD = _source(30.0, 0.8, "sticking")
STATIC_BOUNDARY = _source(45.0, 1.0, "sticking")
STATIC_BELOW_BOUNDARY = _source(45.0, 0.99, "sticking")
SLIDING_DOWNSLOPE = _source(30.0, 0.2, "sliding")
SLIDING_UPSLOPE_QUERY = _source(30.0, 0.2, "sliding", query_sign=-1)
SLIDING_ZERO_MU = _source(37.0, 0.0, "sliding")


@dataclass(frozen=True)
class FrictionInclineResiduals:
    tangential_projection: float
    normal_projection: float
    tangential_newton: float
    normal_newton: float
    contact_acceleration: float
    projection_coherence: float
    regime_equality: float
    friction_margin: float
    normal_force_si: float
    friction_force_si: float
    directions_opposed: bool

    @property
    def passed(self) -> bool:
        equalities = (
            self.tangential_projection,
            self.normal_projection,
            self.tangential_newton,
            self.normal_newton,
            self.contact_acceleration,
            self.projection_coherence,
            self.regime_equality,
        )
        return (
            all(abs(value) <= 1.0e-10 for value in equalities)
            and self.friction_margin >= -1.0e-10
            and self.normal_force_si >= -1.0e-10
            and self.friction_force_si >= -1.0e-10
            and self.directions_opposed
        )


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport
    invariance: MechanicsMigrationInvarianceComparison
    residuals: FrictionInclineResiduals


def _draft_payload(source: FrictionInclineSource) -> dict[str, object]:
    mass_raw = f"{source.mass_si:g}"
    gravity_raw = f"{source.gravity_si:g}"
    theta_raw = f"{source.theta_deg:g}"
    coefficient_raw = f"{source.coefficient:g}"
    velocity_raw = f"{source.velocity_si:g}"
    mass_token = f"{mass_raw} kg"
    gravity_token = f"{gravity_raw} m/s^2"
    theta_token = f"{theta_raw} deg"
    velocity_token = f"{velocity_raw} m/s"
    contact_quote = "remains in touching contact with a straight incline"
    regime_quote = (
        "The contact is in the sticking static-friction regime"
        if source.is_static
        else "The contact is in the sliding kinetic-friction regime"
    )
    coefficient_quote = (
        f"coefficient of static friction is {coefficient_raw}"
        if source.is_static
        else f"coefficient of kinetic friction is {coefficient_raw}"
    )
    motion_quote = (
        "The particle remains at rest throughout the interval"
        if source.is_static
        else "The particle is moving downslope and its tangential velocity is 1 m/s"
    )
    friction_quote = "The friction force acts upslope"
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
        ("coefficientEvidence", coefficient_quote, coefficient_raw),
        ("contactEvidence", contact_quote, None),
        ("regimeEvidence", regime_quote, None),
        (
            "motionEvidence",
            motion_quote,
            None if source.is_static else velocity_token,
        ),
        ("frictionDirectionEvidence", friction_quote, None),
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
            ("muA", "coefficientA", DIMENSIONLESS),
            ("fgT", "gravityT", FORCE),
            ("fgN", "gravityN", FORCE),
            ("normalA", "normalForceA", FORCE),
            ("frictionA", "frictionForceA", FORCE),
            ("aT", "accelerationT", ACCELERATION),
            ("aN", "accelerationN", ACCELERATION),
        )
    ]
    if not source.is_static:
        symbols.append(_symbol("vT", "velocityT", VELOCITY))
    known_specs = [
        ("massA", "mA", "mass", "bodyA", MASS, "massEvidence", mass_raw, "kg", None, None, None),
        ("gravityA", "gA", "gravity", "worldA", ACCELERATION, "gravityEvidence", gravity_raw, "m/s^2", None, None, None),
        ("angleA", "thetaA", "angle", "inclineA", DIMENSIONLESS, "angleEvidence", theta_raw, "deg", None, None, None),
        ("coefficientA", "muA", "coefficient_friction", "bodyA", DIMENSIONLESS, "coefficientEvidence", coefficient_raw, "", None, None, None),
    ]
    if not source.is_static:
        known_specs.append(
            ("velocityT", "vT", "velocity", "bodyA", VELOCITY, "motionEvidence", velocity_raw, "m/s", "inclineFrame", "interval1", _axis_direction("tangent", source.motion_sign))
        )
    quantities = [
        _quantity(
            quantity_id,
            symbol_id,
            role,
            subject_id,
            dimension,
            frame_id=frame_id,
            interval_id=interval_id,
            component="tangential" if quantity_id == "velocityT" else "unspecified",
            direction=direction,
            provenance="explicit_source",
            evidence_refs=(evidence_id,),
            raw_value=raw_value,
            raw_unit=raw_unit,
        )
        for (
            quantity_id,
            symbol_id,
            role,
            subject_id,
            dimension,
            evidence_id,
            raw_value,
            raw_unit,
            frame_id,
            interval_id,
            direction,
        ) in known_specs
    ]
    unknown_specs = (
        ("gravityT", "fgT", "force", FORCE, None, "tangential", "tangent", 1, ("gravityEvidence", "orientationEvidence")),
        ("gravityN", "fgN", "force", FORCE, None, "normal", "normal", -1, ("gravityEvidence", "orientationEvidence")),
        ("normalForceA", "normalA", "force", FORCE, "contactA", "normal", "normal", 1, ("contactEvidence", "orientationEvidence")),
        ("frictionForceA", "frictionA", "force", FORCE, "contactA", "tangential", "tangent", source.friction_sign, ("contactEvidence", "regimeEvidence", "frictionDirectionEvidence", "motionEvidence")),
        ("accelerationT", "aT", "acceleration", ACCELERATION, None, "tangential", "tangent", source.query_sign, ("orientationEvidence", "queryEvidence")),
        ("accelerationN", "aN", "acceleration", ACCELERATION, None, "normal", "normal", 1, ("contactEvidence", "orientationEvidence")),
    )
    quantities.extend(
        _quantity(
            quantity_id,
            symbol_id,
            role,
            "bodyA",
            dimension,
            point_id=point_id,
            frame_id="inclineFrame",
            interval_id="interval1",
            component=component,
            direction=_axis_direction(axis, sign),
            evidence_refs=evidence_refs,
        )
        for (
            quantity_id,
            symbol_id,
            role,
            dimension,
            point_id,
            component,
            axis,
            sign,
            evidence_refs,
        ) in unknown_specs
    )
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnosticInclineFrictionLabel",
            "subtype": "diagnosticRegimeLabel",
            "model_id": "sameFixtureInclineFrictionTest",
            "source_text_sha256": hashlib.sha256(
                source.problem_text.encode("utf-8")
            ).hexdigest(),
        },
        "source_assets": [],
        "source_evidence": evidence,
        "entities": [
            {
                "entity_id": "bodyA",
                "primitive": "particle",
                "evidence_refs": [
                    "massEvidence",
                    "contactEvidence",
                    "regimeEvidence",
                    "motionEvidence",
                ],
            },
            {
                "entity_id": "inclineA",
                "primitive": "incline",
                "evidence_refs": [
                    "angleEvidence",
                    "contactEvidence",
                    "fixedInclineEvidence",
                    "orientationEvidence",
                ],
            },
            {
                "entity_id": "worldA",
                "primitive": "environment",
                "evidence_refs": ["gravityEvidence"],
            },
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
                    "regimeEvidence",
                    "motionEvidence",
                    "fixedInclineEvidence",
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
                "quantity_ids": ["massA", "gravityA", "gravityT", "gravityN"],
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
                "quantity_ids": [
                    "normalForceA",
                    "accelerationN",
                    "frictionForceA",
                    "coefficientA",
                ],
                "evidence_refs": [
                    "contactEvidence",
                    "regimeEvidence",
                    "motionEvidence",
                    "frictionDirectionEvidence",
                ],
            },
        ],
        "constraints": [],
        "state_conditions": [
            {
                "state_condition_id": "frictionState",
                "kind": "friction",
                "state": source.regime,
                "subject_id": "bodyA",
                "interval_id": "interval1",
                "quantity_ids": [
                    "frictionForceA",
                    "normalForceA",
                    "coefficientA",
                ],
                "evidence_refs": [
                    "regimeEvidence",
                    "frictionDirectionEvidence",
                ],
            },
            {
                "state_condition_id": "contactState",
                "kind": "contact",
                "state": "touching",
                "subject_id": "bodyA",
                "interval_id": "interval1",
                "quantity_ids": ["normalForceA", "accelerationN"],
                "evidence_refs": ["contactEvidence"],
            },
            {
                "state_condition_id": "fixedInclineState",
                "kind": "motion",
                "state": "at_rest",
                "subject_id": "inclineA",
                "interval_id": "interval1",
                "evidence_refs": ["fixedInclineEvidence"],
            },
            {
                "state_condition_id": "bodyMotionState",
                "kind": "motion",
                "state": "at_rest" if source.is_static else "moving",
                "subject_id": "bodyA",
                "interval_id": "interval1",
                "quantity_ids": [] if source.is_static else ["velocityT"],
                "evidence_refs": ["motionEvidence"],
            },
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


def _normalize_incline_friction(
    source: FrictionInclineSource,
    *,
    mutate: PayloadMutation | None = None,
) -> NormalizationResult:
    payload = _draft_payload(source)
    if mutate is not None:
        mutate(payload)
    draft = MechanicsProblemDraftV1.model_validate(payload)
    return normalize_draft(source.problem_text, draft)


def _build_incline_friction_ir(
    source: FrictionInclineSource,
) -> MechanicsProblemIRV1:
    normalization = _normalize_incline_friction(source)
    assert normalization.terminal.value == "accepted", normalization.issues
    assert normalization.accepted is True
    assert type(normalization.ir) is MechanicsProblemIRV1
    return normalization.ir


def _candidate_values(
    execution: MechanicsMigrationProbeExecution,
) -> dict[str, float]:
    result = execution.solve_result
    assert result is not None
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    values = {item.symbol_id: item.value_si for item in candidate.values}
    assert all(type(value) is float for value in values.values())
    return {key: value for key, value in values.items() if type(value) is float}


def _independent_generic_residuals(
    source: FrictionInclineSource,
    values: dict[str, float],
) -> FrictionInclineResiduals:
    required = {"aT", "aN", "fgT", "fgN", "normalA", "frictionA"}
    assert required.issubset(values)
    mass = source.mass_si
    gravity = source.gravity_si
    theta = source.theta_rad
    physical_downslope_acceleration = source.query_sign * values["aT"]
    regime_equality = (
        physical_downslope_acceleration
        if source.is_static
        else values["frictionA"] - source.coefficient * values["normalA"]
    )
    friction_margin = (
        source.coefficient * values["normalA"] - abs(values["frictionA"])
        if source.is_static
        else 0.0
    )
    return FrictionInclineResiduals(
        tangential_projection=(
            values["fgT"] - mass * gravity * math.sin(theta)
        ),
        normal_projection=(
            values["fgN"] - mass * gravity * math.cos(theta)
        ),
        tangential_newton=(
            values["fgT"]
            - values["frictionA"]
            - mass * physical_downslope_acceleration
        ),
        normal_newton=(
            values["normalA"] - values["fgN"] - mass * values["aN"]
        ),
        contact_acceleration=values["aN"],
        projection_coherence=(
            math.hypot(values["fgT"], values["fgN"]) - mass * gravity
        ),
        regime_equality=regime_equality,
        friction_margin=friction_margin,
        normal_force_si=values["normalA"],
        friction_force_si=values["frictionA"],
        directions_opposed=source.friction_sign == -source.motion_sign,
    )


def _observe_incline_friction_legacy(
    source: FrictionInclineSource,
) -> tuple[LegacyObservation, SolverResult]:
    # Compatibility labels live only inside this direct diagnostic adapter.
    # The generic result and its residuals are frozen before this function runs.
    coefficient_key = "mu_s" if source.is_static else "mu_k"
    problem = CanonicalProblem(
        system_type="particle_on_incline",
        subtype="with_friction",
        friction_type="static" if source.is_static else "kinetic",
        displacement_direction=None if source.is_static else "down_slope",
        knowns={
            "m": Quantity("m", source.mass_si, "kg"),
            "g": Quantity("g", source.gravity_si, "m/s^2"),
            "theta": Quantity("theta", source.theta_deg, "deg"),
            coefficient_key: Quantity(
                coefficient_key, source.coefficient, ""
            ),
        },
        unknowns=["acceleration"],
        requested_outputs=["acceleration"],
    )
    assert problem.raw_text == ""
    result = InclineWithFrictionSolver().solve(problem)
    assert result.ok is True
    assert result.answer is not None and result.answer.unit is not None
    assert result.verification.passed is True

    if source.is_static:
        assert result.selection_decision is None
        assert result.answer.numeric == 0.0
        unrounded_downslope = 0.0
    else:
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
        assert result.explanation_evidence is not None
        assert len(result.explanation_evidence.outputs) == 1
        delivered = result.explanation_evidence.outputs[0]
        assert delivered.candidate_id == selected.candidate_id
        assert delivered.candidate_numeric == unrounded_downslope

    assert result.answers == []
    transformed_query_value = source.query_sign * unrounded_downslope
    normalized = normalize_quantity(
        str(transformed_query_value),
        result.answer.unit,
        "scalar",
        ACCELERATION,
    )
    assert type(normalized.value) is float
    normal_force = (
        source.mass_si * source.gravity_si * math.cos(source.theta_rad)
    )
    tangential_gravity = (
        source.mass_si * source.gravity_si * math.sin(source.theta_rad)
    )
    if source.is_static:
        friction_force = tangential_gravity
        friction_residual_ok = (
            friction_force <= source.coefficient * normal_force + 1.0e-10
        )
    else:
        friction_force = source.coefficient * normal_force
        friction_residual_ok = math.isclose(
            friction_force,
            source.coefficient * normal_force,
            rel_tol=0.0,
            abs_tol=1.0e-10,
        )
    tangential_residual = (
        tangential_gravity
        - friction_force
        - source.mass_si * source.query_sign * normalized.value
    )
    projection_coherence = (
        math.hypot(tangential_gravity, normal_force)
        - source.mass_si * source.gravity_si
    )
    residual_passed = (
        math.isclose(tangential_residual, 0.0, rel_tol=0.0, abs_tol=1.0e-10)
        and math.isclose(
            projection_coherence, 0.0, rel_tol=0.0, abs_tol=1.0e-10
        )
        and normal_force >= -1.0e-10
        and friction_residual_ok
        and source.friction_sign == -source.motion_sign
    )
    assert residual_passed is True
    observation = LegacyObservation(
        case_id=(
            f"inclineWithFriction{source.regime.title()}"
            f"{source.theta_deg:g}DegMu{source.coefficient:g}"
            f"{source.query_direction.title()}"
        ).replace(".", "p"),
        diagnostic_kernel_id="inclineWithFrictionDirectV1",
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
            b"diagnostic wording changed after friction physics was frozen"
        ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


def _same_fixture_evidence(
    source: FrictionInclineSource,
) -> SameFixtureEvidence:
    ir = _build_incline_friction_ir(source)
    assert "raw_text" not in type(ir).model_fields

    # Generic authority, complete candidates, and independent residuals freeze first.
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
        source,
        _candidate_values(execution),
    )
    assert residuals.passed is True

    # The direct legacy implementation is diagnostics-only and runs after freeze.
    observation, _ = _observe_incline_friction_legacy(source)
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
        registry_entry="incline_with_friction",
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
        STATIC_HOLD,
        STATIC_BOUNDARY,
        SLIDING_DOWNSLOPE,
        SLIDING_UPSLOPE_QUERY,
        SLIDING_ZERO_MU,
    ),
    ids=(
        "static-hold",
        "static-exact-boundary",
        "sliding-downslope",
        "sliding-signed-upslope-query",
        "sliding-zero-mu-reduction",
    ),
)
def test_incline_with_friction_same_fixture_full_parity_and_invariance(
    source: FrictionInclineSource,
) -> None:
    evidence = _same_fixture_evidence(source)
    execution = evidence.execution
    compiler = execution.compiler_result
    result = execution.solve_result
    assert evidence.registry_entry == "incline_with_friction"
    assert compiler is not None and compiler.graph is not None
    assert execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert execution.solve_terminal is MechanicsSolveTerminal.solved

    equations = compiler.graph.equations
    law_ids = [item.law_id for item in equations]
    assert {
        "incline_gravity_tangent_projection",
        "incline_gravity_normal_projection",
        "fixed_contact_no_penetration",
        "contact_normal_bound",
        "particle_newton_second",
    }.issubset(law_ids)
    assert law_ids.count("particle_newton_second") == 2
    assert law_ids.count("contact_normal_bound") == 1
    if source.is_static:
        assert law_ids.count("contact_friction_bound") == 2
        assert law_ids.count("incline_sticking_static_acceleration") == 1
        assert "contact_sliding_friction" not in law_ids
    else:
        assert law_ids.count("contact_sliding_friction") == 1
        assert "contact_friction_bound" not in law_ids
        assert "incline_sticking_static_acceleration" not in law_ids

    source_quantity_ids = {
        quantity_id
        for equation in equations
        for quantity_id in equation.source_quantity_ids
    }
    required_source_quantity_ids = {
        "massA",
        "gravityA",
        "angleA",
        "coefficientA",
        "gravityT",
        "gravityN",
        "normalForceA",
        "frictionForceA",
        "accelerationT",
        "accelerationN",
    }
    if not source.is_static:
        required_source_quantity_ids.add("velocityT")
    assert required_source_quantity_ids.issubset(source_quantity_ids)
    assert not any(
        quantity.si_value is not None
        for quantity in evidence.ir.quantities
        if quantity.quantity_id
        in {
            "gravityT",
            "gravityN",
            "normalForceA",
            "frictionForceA",
            "accelerationT",
            "accelerationN",
        }
    )

    assert result.plan.primary_backend is SolveBackendKind.linear_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert result.candidate_set.generation_complete is True
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    assert candidate.query_symbol_id == "aT"
    assert candidate.root_multiplicity == 1
    expected_downslope = (
        0.0
        if source.is_static
        else source.gravity_si
        * (
            math.sin(source.theta_rad)
            - source.coefficient * math.cos(source.theta_rad)
        )
    )
    assert candidate.query_value_si == pytest.approx(
        source.query_sign * expected_downslope,
        rel=0.0,
        abs=1.0e-10,
    )
    assert candidate.query_value_si == pytest.approx(
        evidence.observation.selected_scalar_si,
        rel=0.0,
        abs=1.0e-10,
    )
    assert evidence.observation.si_unit == "m*s^-2"

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
    assert residual_checks[0].measured_error == pytest.approx(
        0.0,
        abs=1.0e-10,
    )

    assert evidence.residuals.passed is True
    if source is STATIC_BOUNDARY:
        assert evidence.residuals.friction_margin == pytest.approx(
            0.0,
            rel=0.0,
            abs=1.0e-10,
        )
    if source is SLIDING_ZERO_MU:
        assert evidence.residuals.friction_force_si == pytest.approx(
            0.0,
            rel=0.0,
            abs=1.0e-10,
        )
        assert candidate.query_value_si == pytest.approx(
            source.gravity_si * math.sin(source.theta_rad),
            rel=0.0,
            abs=1.0e-10,
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
            tuple(field.value for field in item.differing_fields),
            item.note,
        )
        for item in evidence.invariance.variants
    )
    assert all(item.matches_baseline for item in evidence.invariance.variants)


def _forbid_legacy_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> SolverResult:
        raise AssertionError("a rejected generic fixture must not call legacy")

    monkeypatch.setattr(InclineWithFrictionSolver, "solve", forbidden)


def test_incline_sticking_below_boundary_is_rejected_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ir = _build_incline_friction_ir(STATIC_BELOW_BOUNDARY)
    _forbid_legacy_call(monkeypatch)

    execution = execute_mechanics_ir_probe(ir)

    assert execution.terminal is MigrationProbeTerminal.solve_rejected
    assert execution.compiler_status is CompilerStatus.ready
    result = execution.solve_result
    assert result is not None
    assert result.terminal is MechanicsSolveTerminal.insufficient_conditions
    assert result.verified_candidates == ()
    assert len(result.candidate_set.candidates) == 1
    assert len(result.verification_outcomes) == 1
    assert result.verification_outcomes[0].passed is False
    assert any(
        rejection.reason is CandidateRejectionReason.inequality_violation
        for rejection in result.rejections
    )


def _same_direction_friction(payload: dict[str, object]) -> None:
    quantities = payload["quantities"]
    assert isinstance(quantities, list)
    friction = next(
        item
        for item in quantities
        if isinstance(item, dict) and item.get("quantity_id") == "frictionForceA"
    )
    friction["direction"] = _axis_direction("tangent", 1)


def test_sliding_friction_same_as_motion_direction_is_compiler_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized = _normalize_incline_friction(
        SLIDING_DOWNSLOPE,
        mutate=_same_direction_friction,
    )
    assert normalized.terminal.value == "accepted"
    assert type(normalized.ir) is MechanicsProblemIRV1
    _forbid_legacy_call(monkeypatch)

    execution = execute_mechanics_ir_probe(normalized.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_status is not CompilerStatus.ready
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def _remove_state(state_id: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        states = payload["state_conditions"]
        assert isinstance(states, list)
        payload["state_conditions"] = [
            state
            for state in states
            if not isinstance(state, dict)
            or state.get("state_condition_id") != state_id
        ]

    return mutate


def _clear_state_evidence(state_id: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        states = payload["state_conditions"]
        assert isinstance(states, list)
        state = next(
            item
            for item in states
            if isinstance(item, dict) and item.get("state_condition_id") == state_id
        )
        state["evidence_refs"] = []

    return mutate


def _remove_motion_carrier(payload: dict[str, object]) -> None:
    states = payload["state_conditions"]
    assert isinstance(states, list)
    state = next(
        item
        for item in states
        if isinstance(item, dict) and item.get("state_condition_id") == "bodyMotionState"
    )
    state["quantity_ids"] = []


@pytest.mark.parametrize(
    "mutate",
    (
        _remove_motion_carrier,
        _clear_state_evidence("bodyMotionState"),
        _remove_state("frictionState"),
        _clear_state_evidence("frictionState"),
        _remove_state("contactState"),
        _clear_state_evidence("contactState"),
        _remove_state("fixedInclineState"),
        _clear_state_evidence("fixedInclineState"),
    ),
    ids=(
        "motion-carrier-missing",
        "motion-authority-unevidenced",
        "regime-missing",
        "regime-unevidenced",
        "contact-missing",
        "contact-unevidenced",
        "fixed-incline-missing",
        "fixed-incline-unevidenced",
    ),
)
def test_incline_friction_missing_typed_authority_fails_closed(
    mutate: PayloadMutation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized = _normalize_incline_friction(
        SLIDING_DOWNSLOPE,
        mutate=mutate,
    )
    assert normalized.terminal.value == "accepted", normalized.issues
    assert type(normalized.ir) is MechanicsProblemIRV1
    _forbid_legacy_call(monkeypatch)

    execution = execute_mechanics_ir_probe(normalized.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_status is not CompilerStatus.ready


def _append_duplicate_incline_tangent_axis(payload: dict[str, object]) -> None:
    frames = payload["reference_frames"]
    assert isinstance(frames, list)
    incline_frame = next(
        item
        for item in frames
        if isinstance(item, dict) and item.get("frame_id") == "inclineFrame"
    )
    axes = incline_frame["axes"]
    assert isinstance(axes, list)
    axes.append(_axis_binding("tangent", frame_id="inclineFrame"))


def _clear_interval_evidence(payload: dict[str, object]) -> None:
    intervals = payload["motion_intervals"]
    assert isinstance(intervals, list)
    interval = next(
        item
        for item in intervals
        if isinstance(item, dict) and item.get("interval_id") == "interval1"
    )
    interval["evidence_refs"] = []


def _clear_entity_evidence(entity_id: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        entities = payload["entities"]
        assert isinstance(entities, list)
        entity = next(
            item
            for item in entities
            if isinstance(item, dict) and item.get("entity_id") == entity_id
        )
        entity["evidence_refs"] = []

    return mutate


@pytest.mark.parametrize(
    "mutate",
    (
        _append_duplicate_incline_tangent_axis,
        _clear_interval_evidence,
        _clear_entity_evidence("bodyA"),
        _clear_entity_evidence("inclineA"),
    ),
    ids=(
        "duplicate-incline-tangent-axis",
        "motion-interval-unevidenced",
        "body-entity-unevidenced",
        "incline-entity-unevidenced",
    ),
)
def test_incline_friction_structural_authority_bypasses_fail_closed(
    mutate: PayloadMutation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized = _normalize_incline_friction(
        SLIDING_DOWNSLOPE,
        mutate=mutate,
    )
    assert normalized.terminal.value == "accepted", normalized.issues
    assert type(normalized.ir) is MechanicsProblemIRV1
    _forbid_legacy_call(monkeypatch)

    execution = execute_mechanics_ir_probe(normalized.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_status is not CompilerStatus.ready


def test_negative_friction_coefficient_is_invalid_domain_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(30.0, -0.1, "sliding")
    ir = _build_incline_friction_ir(source)
    _forbid_legacy_call(monkeypatch)

    execution = execute_mechanics_ir_probe(ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.invalid_domain
        for issue in execution.compiler_result.issues
    )


def test_incline_friction_declared_direction_ambiguity_needs_confirmation() -> None:
    def declare(payload: dict[str, object]) -> None:
        payload["ambiguities"] = [
            {
                "ambiguity_id": "inclineFrictionDirectionAmbiguity",
                "kind": "direction",
                "referenced_ids": [
                    "velocityT",
                    "frictionForceA",
                    "accelerationT",
                    "queryA",
                ],
                "description": (
                    "The sliding direction, friction opposition, or query direction "
                    "is unresolved."
                ),
                "blocking": True,
                "evidence_refs": ["motionEvidence", "queryEvidence"],
            }
        ]

    normalized = _normalize_incline_friction(
        SLIDING_DOWNSLOPE,
        mutate=declare,
    )

    assert normalized.terminal.value == "needs_confirmation"
    assert normalized.ir is None
