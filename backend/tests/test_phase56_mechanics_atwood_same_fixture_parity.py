from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
from typing import Callable

import pytest

from engine.mechanics.compiler import (
    CompilerIssueCode,
    CompilerStatus,
    MechanicsCompiler,
    authorize_validated_mechanics_ir,
)
from engine.mechanics.compiler.compiler import _build_law_context
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
from engine.mechanics.laws.core import apply_core_laws
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.normalization import NormalizationResult, normalize_draft
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import ValidationTerminal
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity, SolverResult
from engine.solvers.pulley.atwood import AtwoodPulleySolver
from test_phase56_mechanics_incline_same_fixture_parity import (
    ACCELERATION,
    FORCE,
    MASS,
    _axis_binding,
    _axis_direction,
    _quantity,
    _symbol,
    _text_evidence,
)


FRAME_ID = "worldFrame"
INTERVAL_ID = "motionInterval"
MOMENT_OF_INERTIA = DimensionVector(mass=1, length=2)
APPROVED_ASSUMPTION_IDS = (
    "fixedPulley",
    "idealPulley",
    "inextensibleRope",
    "masslessRope",
)


@dataclass(frozen=True)
class AtwoodSource:
    problem_text: str
    mass_a_si: float
    mass_b_si: float
    gravity_si: float
    b_acceleration_sign: int
    query_role: str
    query_direction: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.mass_a_si, "mass A"),
            (self.mass_b_si, "mass B"),
            (self.gravity_si, "gravity"),
        ):
            if type(value) is not float or not math.isfinite(value):
                raise ValueError(f"{label} must be one finite float")
        if self.b_acceleration_sign not in {-1, 1}:
            raise ValueError("mass B acceleration direction must be one axis sign")
        if self.query_role not in {"acceleration", "tension"}:
            raise ValueError("query role must be acceleration or tension")
        expected = (
            "upward"
            if self.query_role == "tension" or self.b_acceleration_sign == 1
            else "downward"
        )
        if self.query_direction != expected:
            raise ValueError("query direction text and typed direction must agree")

    @property
    def legacy_acceleration_si(self) -> float:
        return (
            (self.mass_b_si - self.mass_a_si)
            * self.gravity_si
            / (self.mass_a_si + self.mass_b_si)
        )

    @property
    def legacy_tension_si(self) -> float:
        return (
            2.0
            * self.mass_a_si
            * self.mass_b_si
            * self.gravity_si
            / (self.mass_a_si + self.mass_b_si)
        )

    @property
    def expected_query_value_si(self) -> float:
        if self.query_role == "tension":
            return self.legacy_tension_si
        return -self.b_acceleration_sign * self.legacy_acceleration_si

    @property
    def query_symbol_id(self) -> str:
        return "tB" if self.query_role == "tension" else "aB"


def _source(
    mass_a_si: float,
    mass_b_si: float,
    *,
    gravity_si: float = 9.81,
    b_acceleration_sign: int = -1,
    query_role: str = "acceleration",
) -> AtwoodSource:
    query_direction = (
        "upward"
        if query_role == "tension" or b_acceleration_sign == 1
        else "downward"
    )
    query_sentence = (
        f"Find the tension acting {query_direction} on mass B."
        if query_role == "tension"
        else f"Find the acceleration of mass B along the {query_direction} direction."
    )
    problem_text = " ".join(
        (
            f"Mass A is {mass_a_si:g} kg.",
            f"Mass B is {mass_b_si:g} kg.",
            f"Take g = {gravity_si:g} m/s^2.",
            "Both particles hang from opposite ends of one massless, inextensible rope.",
            "The rope is taut.",
            "The rope wraps over one ideal massless frictionless pulley.",
            "The pulley is fixed and remains at rest.",
            "The rope is attached to mass A.",
            "The rope is attached to mass B.",
            "The +y axis points upward.",
            query_sentence,
        )
    )
    return AtwoodSource(
        problem_text=problem_text,
        mass_a_si=float(mass_a_si),
        mass_b_si=float(mass_b_si),
        gravity_si=float(gravity_si),
        b_acceleration_sign=b_acceleration_sign,
        query_role=query_role,
        query_direction=query_direction,
    )


BASELINE = _source(2.0, 5.0)
EQUAL_MASSES = _source(2.0, 2.0)
MASS_SWAP = _source(5.0, 2.0)
B_UP_QUERY = _source(2.0, 5.0, b_acceleration_sign=1)
TENSION_QUERY = _source(
    2.0,
    5.0,
    b_acceleration_sign=1,
    query_role="tension",
)


@dataclass(frozen=True)
class AtwoodResiduals:
    weight_a: float
    weight_b: float
    newton_a: float
    newton_b: float
    equal_tension: float
    rope_acceleration: float
    acceleration_closed_form: float
    tension_closed_form: float
    tension_a_si: float
    tension_b_si: float

    @property
    def passed(self) -> bool:
        residuals = (
            self.weight_a,
            self.weight_b,
            self.newton_a,
            self.newton_b,
            self.equal_tension,
            self.rope_acceleration,
            self.acceleration_closed_form,
            self.tension_closed_form,
        )
        return (
            all(abs(value) <= 1.0e-10 for value in residuals)
            and self.tension_a_si >= -1.0e-10
            and self.tension_b_si >= -1.0e-10
        )


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport
    residuals: AtwoodResiduals


def _direction(sign: int) -> dict[str, object]:
    return _axis_direction("y", sign, frame_id=FRAME_ID)


def _draft_payload(source: AtwoodSource) -> dict[str, object]:
    mass_a_raw = f"{source.mass_a_si:g}"
    mass_b_raw = f"{source.mass_b_si:g}"
    gravity_raw = f"{source.gravity_si:g}"
    mass_a_quote = f"Mass A is {mass_a_raw} kg."
    mass_b_quote = f"Mass B is {mass_b_raw} kg."
    gravity_quote = f"Take g = {gravity_raw} m/s^2."
    rope_quote = (
        "Both particles hang from opposite ends of one massless, inextensible rope."
    )
    taut_quote = "The rope is taut."
    wrap_quote = "The rope wraps over one ideal massless frictionless pulley."
    fixed_quote = "The pulley is fixed and remains at rest."
    attach_a_quote = "The rope is attached to mass A."
    attach_b_quote = "The rope is attached to mass B."
    orientation_quote = "The +y axis points upward."
    query_quote = (
        f"Find the tension acting {source.query_direction} on mass B."
        if source.query_role == "tension"
        else (
            "Find the acceleration of mass B along the "
            f"{source.query_direction} direction."
        )
    )
    evidence_specs = (
        ("massAEvidence", mass_a_quote, f"{mass_a_raw} kg"),
        ("massBEvidence", mass_b_quote, f"{mass_b_raw} kg"),
        ("gravityEvidence", gravity_quote, f"{gravity_raw} m/s^2"),
        ("ropeEvidence", rope_quote, None),
        ("tautEvidence", taut_quote, None),
        ("wrapEvidence", wrap_quote, None),
        ("fixedPulleyEvidence", fixed_quote, None),
        ("attachAEvidence", attach_a_quote, None),
        ("attachBEvidence", attach_b_quote, None),
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
            ("mB", "massB", MASS),
            ("g", "gravity", ACCELERATION),
            ("wA", "weightA", FORCE),
            ("wB", "weightB", FORCE),
            ("tA", "tensionA", FORCE),
            ("tB", "tensionB", FORCE),
            ("aA", "accelerationA", ACCELERATION),
            ("aB", "accelerationB", ACCELERATION),
        )
    ]
    tension_b_evidence_refs = (
        "ropeEvidence",
        "tautEvidence",
        "attachBEvidence",
        "orientationEvidence",
    ) + (("queryEvidence",) if source.query_role == "tension" else ())
    acceleration_b_evidence_refs = (
        "ropeEvidence",
        "orientationEvidence",
    ) + (("queryEvidence",) if source.query_role == "acceleration" else ())
    quantities = [
        _quantity(
            "massA",
            "mA",
            "mass",
            "bodyA",
            MASS,
            provenance="explicit_source",
            evidence_refs=("massAEvidence",),
            raw_value=mass_a_raw,
            raw_unit="kg",
        ),
        _quantity(
            "massB",
            "mB",
            "mass",
            "bodyB",
            MASS,
            provenance="explicit_source",
            evidence_refs=("massBEvidence",),
            raw_value=mass_b_raw,
            raw_unit="kg",
        ),
        _quantity(
            "gravity",
            "g",
            "gravity",
            "world",
            ACCELERATION,
            provenance="explicit_source",
            evidence_refs=("gravityEvidence",),
            raw_value=gravity_raw,
            raw_unit="m/s^2",
        ),
        _quantity(
            "weightA",
            "wA",
            "force",
            "bodyA",
            FORCE,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction(-1),
            evidence_refs=("gravityEvidence", "orientationEvidence"),
        ),
        _quantity(
            "weightB",
            "wB",
            "force",
            "bodyB",
            FORCE,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction(-1),
            evidence_refs=("gravityEvidence", "orientationEvidence"),
        ),
        _quantity(
            "tensionA",
            "tA",
            "force",
            "bodyA",
            FORCE,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction(1),
            evidence_refs=(
                "ropeEvidence",
                "tautEvidence",
                "attachAEvidence",
                "orientationEvidence",
            ),
        ),
        _quantity(
            "tensionB",
            "tB",
            "force",
            "bodyB",
            FORCE,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction(1),
            evidence_refs=tension_b_evidence_refs,
        ),
        _quantity(
            "accelerationA",
            "aA",
            "acceleration",
            "bodyA",
            ACCELERATION,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction(1),
            evidence_refs=("ropeEvidence", "orientationEvidence"),
        ),
        _quantity(
            "accelerationB",
            "aB",
            "acceleration",
            "bodyB",
            ACCELERATION,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction(source.b_acceleration_sign),
            evidence_refs=acceleration_b_evidence_refs,
        ),
    ]
    query_quantity_id = (
        "tensionB" if source.query_role == "tension" else "accelerationB"
    )
    query_direction_sign = (
        1 if source.query_role == "tension" else source.b_acceleration_sign
    )
    query_dimension = FORCE if source.query_role == "tension" else ACCELERATION
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnosticAtwoodLabel",
            "subtype": "diagnosticIdealFixedPulleyLabel",
            "model_id": "sameFixtureAtwoodTest",
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
                    "massAEvidence",
                    "ropeEvidence",
                    "attachAEvidence",
                ],
            },
            {
                "entity_id": "bodyB",
                "primitive": "particle",
                "evidence_refs": [
                    "massBEvidence",
                    "ropeEvidence",
                    "attachBEvidence",
                ],
            },
            {
                "entity_id": "rope",
                "primitive": "rope",
                "evidence_refs": [
                    "ropeEvidence",
                    "tautEvidence",
                    "wrapEvidence",
                    "attachAEvidence",
                    "attachBEvidence",
                ],
            },
            {
                "entity_id": "pulley",
                "primitive": "pulley",
                "evidence_refs": ["wrapEvidence", "fixedPulleyEvidence"],
            },
            {
                "entity_id": "world",
                "primitive": "environment",
                "evidence_refs": ["gravityEvidence", "orientationEvidence"],
            },
        ],
        "points": [],
        "reference_frames": [
            {
                "frame_id": FRAME_ID,
                "frame_type": "cartesian_1d",
                "origin": {"kind": "world"},
                "axes": [_axis_binding("y", frame_id=FRAME_ID)],
                "evidence_refs": ["orientationEvidence"],
            }
        ],
        "motion_intervals": [
            {
                "interval_id": INTERVAL_ID,
                "order": 1,
                "subject_ids": ["bodyA", "bodyB", "rope", "pulley", "world"],
                "frame_id": FRAME_ID,
                "evidence_refs": [
                    "ropeEvidence",
                    "tautEvidence",
                    "wrapEvidence",
                    "fixedPulleyEvidence",
                    "attachAEvidence",
                    "attachBEvidence",
                ],
            }
        ],
        "events": [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": [
            {
                "relation_id": "ropeWrap",
                "kind": "wraps",
                "participant_ids": ["rope", "pulley"],
                "quantity_ids": [],
                "interval_id": INTERVAL_ID,
                "evidence_refs": ["wrapEvidence"],
            },
            {
                "relation_id": "ropeAttachedA",
                "kind": "attached",
                "participant_ids": ["rope", "bodyA"],
                "quantity_ids": [],
                "interval_id": INTERVAL_ID,
                "evidence_refs": ["attachAEvidence"],
            },
            {
                "relation_id": "ropeAttachedB",
                "kind": "attached",
                "participant_ids": ["rope", "bodyB"],
                "quantity_ids": [],
                "interval_id": INTERVAL_ID,
                "evidence_refs": ["attachBEvidence"],
            },
        ],
        "interactions": [
            {
                "interaction_id": "gravityA",
                "kind": "gravity",
                "participant_ids": ["bodyA", "world"],
                "frame_id": FRAME_ID,
                "interval_id": INTERVAL_ID,
                "quantity_ids": ["massA", "gravity", "weightA"],
                "evidence_refs": [
                    "massAEvidence",
                    "gravityEvidence",
                    "orientationEvidence",
                ],
            },
            {
                "interaction_id": "gravityB",
                "kind": "gravity",
                "participant_ids": ["bodyB", "world"],
                "frame_id": FRAME_ID,
                "interval_id": INTERVAL_ID,
                "quantity_ids": ["massB", "gravity", "weightB"],
                "evidence_refs": [
                    "massBEvidence",
                    "gravityEvidence",
                    "orientationEvidence",
                ],
            },
            {
                "interaction_id": "ropeTension",
                "kind": "rope_tension",
                "participant_ids": ["bodyA", "bodyB", "rope", "pulley"],
                "frame_id": FRAME_ID,
                "interval_id": INTERVAL_ID,
                "quantity_ids": ["tensionA", "tensionB"],
                "evidence_refs": [
                    "ropeEvidence",
                    "tautEvidence",
                    "wrapEvidence",
                    "attachAEvidence",
                    "attachBEvidence",
                    "orientationEvidence",
                ],
            },
        ],
        "constraints": [],
        "state_conditions": [
            {
                "state_condition_id": "ropeTautState",
                "kind": "rope",
                "state": "taut",
                "subject_id": "rope",
                "interval_id": INTERVAL_ID,
                "quantity_ids": [],
                "evidence_refs": ["tautEvidence"],
            },
            {
                "state_condition_id": "pulleyFixedState",
                "kind": "motion",
                "state": "at_rest",
                "subject_id": "pulley",
                "interval_id": INTERVAL_ID,
                "quantity_ids": [],
                "evidence_refs": ["fixedPulleyEvidence"],
            },
        ],
        "queries": [
            {
                "query_id": "queryB",
                "target": {
                    "role": "force" if source.query_role == "tension" else "acceleration",
                    "subject_id": "bodyB",
                    "frame_id": FRAME_ID,
                    "interval_id": INTERVAL_ID,
                    "component": "y",
                    "direction": _direction(query_direction_sign),
                    "target_quantity_id": query_quantity_id,
                },
                "output_unit": "N" if source.query_role == "tension" else "m/s^2",
                "output_dimension": query_dimension.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": ["queryEvidence"],
            }
        ],
        "principle_hints": [],
        "assumptions": [
            {
                "assumption_id": "masslessRope",
                "kind": "massless_rope",
                "subject_id": "rope",
                "interval_id": INTERVAL_ID,
                "disposition": "approved",
                "reason": "The source explicitly identifies one massless rope.",
                "evidence_refs": ["ropeEvidence"],
            },
            {
                "assumption_id": "inextensibleRope",
                "kind": "inextensible_rope",
                "subject_id": "rope",
                "interval_id": INTERVAL_ID,
                "disposition": "approved",
                "reason": "The source explicitly identifies one inextensible rope.",
                "evidence_refs": ["ropeEvidence"],
            },
            {
                "assumption_id": "fixedPulley",
                "kind": "fixed_pulley",
                "subject_id": "pulley",
                "interval_id": INTERVAL_ID,
                "disposition": "approved",
                "reason": "The source explicitly fixes the pulley center.",
                "evidence_refs": ["fixedPulleyEvidence"],
            },
            {
                "assumption_id": "idealPulley",
                "kind": "ideal_massless_frictionless_pulley",
                "subject_id": "pulley",
                "interval_id": INTERVAL_ID,
                "disposition": "approved",
                "reason": "The source explicitly identifies an ideal pulley.",
                "evidence_refs": ["wrapEvidence"],
            },
        ],
        "ambiguities": [],
        "figure_dependency": {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        },
        "unsupported_features": [],
    }


PayloadMutation = Callable[[dict[str, object]], None]


def _normalize(
    source: AtwoodSource,
    *,
    mutation: PayloadMutation | None = None,
    approved_assumption_ids: tuple[str, ...] = APPROVED_ASSUMPTION_IDS,
) -> NormalizationResult:
    payload = _draft_payload(source)
    if mutation is not None:
        mutation(payload)
    draft = MechanicsProblemDraftV1.model_validate(payload)
    return normalize_draft(
        source.problem_text,
        draft,
        approved_assumption_ids=approved_assumption_ids,
    )


def _build_ir(source: AtwoodSource) -> MechanicsProblemIRV1:
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert normalization.accepted is True
    assert type(normalization.ir) is MechanicsProblemIRV1
    return normalization.ir


def _execute(
    ir: MechanicsProblemIRV1,
    *,
    approved_assumption_ids: tuple[str, ...] = APPROVED_ASSUMPTION_IDS,
) -> MechanicsMigrationProbeExecution:
    return execute_mechanics_ir_probe(
        ir,
        approved_assumption_ids=approved_assumption_ids,
    )


def _candidate_values(execution: MechanicsMigrationProbeExecution) -> dict[str, float]:
    result = execution.solve_result
    assert result is not None
    assert len(result.candidate_set.candidates) == 1
    values = {
        item.symbol_id: item.value_si
        for item in result.candidate_set.candidates[0].values
    }
    assert all(type(value) is float for value in values.values())
    return {key: value for key, value in values.items() if type(value) is float}


def _independent_residuals(
    source: AtwoodSource,
    values: dict[str, float],
) -> AtwoodResiduals:
    # Candidate values contain solved unknowns; explicit source knowns are checked
    # independently through the typed source fixture below.
    required = {"wA", "wB", "tA", "tB", "aA", "aB"}
    assert required.issubset(values)
    expected_acceleration = source.legacy_acceleration_si
    expected_tension = source.legacy_tension_si
    physical_b_acceleration = source.b_acceleration_sign * values["aB"]
    return AtwoodResiduals(
        weight_a=values["wA"] - source.mass_a_si * source.gravity_si,
        weight_b=values["wB"] - source.mass_b_si * source.gravity_si,
        newton_a=(
            values["tA"]
            - values["wA"]
            - source.mass_a_si * values["aA"]
        ),
        newton_b=(
            values["tB"]
            - values["wB"]
            - source.mass_b_si * physical_b_acceleration
        ),
        equal_tension=values["tA"] - values["tB"],
        rope_acceleration=values["aA"] + physical_b_acceleration,
        acceleration_closed_form=values["aA"] - expected_acceleration,
        tension_closed_form=values["tA"] - expected_tension,
        tension_a_si=values["tA"],
        tension_b_si=values["tB"],
    )


def _observe_legacy(
    source: AtwoodSource,
) -> tuple[LegacyObservation, SolverResult]:
    # Compatibility labels exist only inside this post-freeze diagnostic adapter.
    problem = CanonicalProblem(
        system_type="pulley_atwood",
        pulley_topology="atwood",
        knowns={
            "m1": Quantity("m1", source.mass_a_si, "kg"),
            "m2": Quantity("m2", source.mass_b_si, "kg"),
            "g": Quantity("g", source.gravity_si, "m/s^2"),
        },
        unknowns=["acceleration", "tension"],
        requested_outputs=["acceleration", "tension"],
    )
    assert problem.raw_text == ""
    result = AtwoodPulleySolver().solve(problem)
    assert result.ok is True
    assert result.verification.passed is True
    decision = result.selection_decision
    assert decision is not None and decision.status == "selected"
    assert decision.selected_candidate is not None
    selected = decision.selected_candidate
    assert set(selected.numerical_mapping) == {"T", "a"}
    assert decision.valid_alternatives == []
    assert decision.rejected_candidates == []
    if source.query_role == "tension":
        value = selected.numerical_mapping["T"]
        unit = next(item.unit for item in result.answers if item.symbol == "T")
        dimension = FORCE
    else:
        value = -source.b_acceleration_sign * selected.numerical_mapping["a"]
        assert result.answer is not None
        unit = result.answer.unit
        dimension = ACCELERATION
    assert type(value) is float and unit is not None
    normalized = normalize_quantity(str(value), unit, "scalar", dimension)
    assert type(normalized.value) is float
    residual_passed = (
        math.isclose(
            selected.numerical_mapping["a"],
            source.legacy_acceleration_si,
            rel_tol=0.0,
            abs_tol=1.0e-10,
        )
        and math.isclose(
            selected.numerical_mapping["T"],
            source.legacy_tension_si,
            rel_tol=0.0,
            abs_tol=1.0e-10,
        )
        and selected.numerical_mapping["T"] >= 0.0
    )
    assert residual_passed is True
    observation = LegacyObservation(
        case_id=(
            f"atwoodMa{source.mass_a_si:g}Mb{source.mass_b_si:g}"
            f"{source.query_role.title()}{source.query_direction.title()}"
        ).replace(".", "p"),
        diagnostic_kernel_id="atwoodPulleyDirectV1",
        terminal=LegacyTerminal.solved,
        query_symbol_id=source.query_symbol_id,
        si_unit=normalized.si_unit,
        selected_scalar_si=normalized.value,
        complete_candidate_scalars_si=(
            LegacyCandidateScalar(value_si=normalized.value, multiplicity=1),
        ),
        residual_passed=residual_passed,
    )
    return observation, result


def _same_fixture(source: AtwoodSource) -> SameFixtureEvidence:
    ir = _build_ir(source)
    assert "raw_text" not in type(ir).model_fields

    # Freeze the generic result, complete candidate, and independent residuals first.
    execution = _execute(ir)
    assert execution.terminal is MigrationProbeTerminal.solved, (
        None
        if execution.compiler_result is None
        else execution.compiler_result.issues
    )
    assert execution.solve_result is not None
    generic_signature = build_generic_result_invariance_signature(
        execution.solve_result
    )
    candidate_values = _candidate_values(execution)
    frozen_candidate_values = tuple(sorted(candidate_values.items()))
    residuals = _independent_residuals(source, candidate_values)
    assert residuals.passed is True

    observation, _ = _observe_legacy(source)
    report = build_legacy_differential_report(execution.solve_result, observation)
    assert build_generic_result_invariance_signature(
        execution.solve_result
    ) == generic_signature
    assert tuple(sorted(_candidate_values(execution).items())) == frozen_candidate_values
    assert _independent_residuals(source, _candidate_values(execution)) == residuals
    return SameFixtureEvidence(
        registry_entry="pulley_atwood",
        ir=ir,
        execution=execution,
        observation=observation,
        report=report,
        residuals=residuals,
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    "source",
    (BASELINE, EQUAL_MASSES, MASS_SWAP, B_UP_QUERY, TENSION_QUERY),
    ids=(
        "baseline-b-down",
        "equal-masses",
        "mass-swap-signed",
        "b-up-signed-query",
        "tension-query",
    ),
)
def test_pulley_atwood_same_fixture_full_parity(source: AtwoodSource) -> None:
    evidence = _same_fixture(source)
    execution = evidence.execution
    compiler = execution.compiler_result
    result = execution.solve_result
    assert evidence.registry_entry == "pulley_atwood"
    assert compiler is not None and compiler.graph is not None
    assert execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert execution.solve_terminal is MechanicsSolveTerminal.solved

    law_counts = Counter(item.law_id for item in compiler.graph.equations)
    assert law_counts == Counter(
        {
            "particle_weight": 2,
            "particle_newton_second": 2,
            "rope_massless_tension": 1,
            "rope_fixed_pulley_motion": 1,
        }
    )
    source_quantity_ids = {
        quantity_id
        for equation in compiler.graph.equations
        for quantity_id in equation.source_quantity_ids
    }
    assert {
        "massA",
        "massB",
        "gravity",
        "weightA",
        "weightB",
        "tensionA",
        "tensionB",
        "accelerationA",
        "accelerationB",
    }.issubset(source_quantity_ids)
    assert not any(
        quantity.si_value is not None
        for quantity in evidence.ir.quantities
        if quantity.quantity_id
        in {
            "weightA",
            "weightB",
            "tensionA",
            "tensionB",
            "accelerationA",
            "accelerationB",
        }
    )

    assert result.plan.primary_backend is SolveBackendKind.linear_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert result.candidate_set.generation_complete is True
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    assert candidate.query_symbol_id == source.query_symbol_id
    assert candidate.root_multiplicity == 1
    assert candidate.query_value_si == pytest.approx(
        source.expected_query_value_si,
        rel=0.0,
        abs=1.0e-10,
    )
    assert candidate.query_value_si == pytest.approx(
        evidence.observation.selected_scalar_si,
        rel=0.0,
        abs=1.0e-10,
    )
    assert evidence.observation.si_unit == (
        "kg*m*s^-2" if source.query_role == "tension" else "m*s^-2"
    )

    assert len(result.verification_outcomes) == 1
    outcome = result.verification_outcomes[0]
    assert outcome.passed is True
    assert {
        VerificationCheckKind.equation_residual,
        VerificationCheckKind.unit_consistency,
        VerificationCheckKind.query_binding,
        VerificationCheckKind.source_evidence,
    }.issubset({check.kind for check in outcome.checks})
    residual_checks = tuple(
        check
        for check in outcome.checks
        if check.kind is VerificationCheckKind.equation_residual
    )
    assert len(residual_checks) == 1
    assert residual_checks[0].status is VerificationCheckStatus.passed
    assert residual_checks[0].measured_error == pytest.approx(0.0, abs=1.0e-10)

    assert evidence.residuals.passed is True
    assert evidence.observation.residual_passed is True
    assert len(evidence.observation.complete_candidate_scalars_si) == 1
    assert evidence.report.status is DifferentialStatus.full_parity
    assert evidence.report.discrepancies == ()
    assert evidence.report.observation_terminal is LegacyTerminal.solved
    assert evidence.report.generic_terminal is MechanicsSolveTerminal.solved


def _forbid_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> SolverResult:
        raise AssertionError("a rejected generic fixture must not call legacy")

    monkeypatch.setattr(AtwoodPulleySolver, "solve", forbidden)


def _record(
    payload: dict[str, object],
    collection_name: str,
    id_field: str,
    record_id: str,
) -> dict[str, object]:
    collection = payload[collection_name]
    assert isinstance(collection, list)
    record = next(
        item
        for item in collection
        if isinstance(item, dict) and item.get(id_field) == record_id
    )
    return record


def _remove_record(
    collection_name: str,
    id_field: str,
    record_id: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        collection = payload[collection_name]
        assert isinstance(collection, list)
        payload[collection_name] = [
            item
            for item in collection
            if not isinstance(item, dict) or item.get(id_field) != record_id
        ]

    return mutate


def _clear_record_evidence(
    collection_name: str,
    id_field: str,
    record_id: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(payload, collection_name, id_field, record_id)["evidence_refs"] = []

    return mutate


def _append_wrap_participant(payload: dict[str, object]) -> None:
    relation = _record(payload, "geometry", "relation_id", "ropeWrap")
    participants = relation["participant_ids"]
    assert isinstance(participants, list)
    participants.append("bodyA")


def _append_rope_interaction_participant(payload: dict[str, object]) -> None:
    interaction = _record(
        payload,
        "interactions",
        "interaction_id",
        "ropeTension",
    )
    participants = interaction["participant_ids"]
    assert isinstance(participants, list)
    participants.append("world")


def _remove_gravity_weight(payload: dict[str, object]) -> None:
    interaction = _record(payload, "interactions", "interaction_id", "gravityA")
    quantity_ids = interaction["quantity_ids"]
    assert isinstance(quantity_ids, list)
    interaction["quantity_ids"] = [
        quantity_id for quantity_id in quantity_ids if quantity_id != "weightA"
    ]


def _append_duplicate_axis(payload: dict[str, object]) -> None:
    frame = _record(payload, "reference_frames", "frame_id", FRAME_ID)
    axes = frame["axes"]
    assert isinstance(axes, list) and len(axes) == 1
    axes.append(deepcopy(axes[0]))


def _append_pulley_motion_quantity(payload: dict[str, object]) -> None:
    symbols = payload["symbols"]
    quantities = payload["quantities"]
    assert isinstance(symbols, list) and isinstance(quantities, list)
    symbols.append(_symbol("aP", "pulleyAcceleration", ACCELERATION))
    quantities.append(
        _quantity(
            "pulleyAcceleration",
            "aP",
            "acceleration",
            "pulley",
            ACCELERATION,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction(1),
            evidence_refs=("fixedPulleyEvidence", "orientationEvidence"),
        )
    )
    fixed_state = _record(
        payload,
        "state_conditions",
        "state_condition_id",
        "pulleyFixedState",
    )
    fixed_state["quantity_ids"] = ["pulleyAcceleration"]


def _append_incomplete_pulley_inertia(payload: dict[str, object]) -> None:
    symbols = payload["symbols"]
    quantities = payload["quantities"]
    assert isinstance(symbols, list) and isinstance(quantities, list)
    symbols.append(_symbol("iP", "pulleyInertia", MOMENT_OF_INERTIA))
    quantities.append(
        _quantity(
            "pulleyInertia",
            "iP",
            "moment_of_inertia",
            "pulley",
            MOMENT_OF_INERTIA,
            interval_id=INTERVAL_ID,
            evidence_refs=("wrapEvidence", "fixedPulleyEvidence"),
        )
    )


def _set_state(state_id: str, value: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(
            payload,
            "state_conditions",
            "state_condition_id",
            state_id,
        )["state"] = value

    return mutate


def _set_quantity_direction(quantity_id: str, sign: int) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(payload, "quantities", "quantity_id", quantity_id)["direction"] = (
            _direction(sign)
        )

    return mutate


def _use_rigid_moving_entities(payload: dict[str, object]) -> None:
    for entity_id in ("bodyA", "bodyB"):
        _record(payload, "entities", "entity_id", entity_id)["primitive"] = (
            "rigid_body"
        )


@dataclass(frozen=True)
class AtwoodCompilerRejectCase:
    label: str
    mutation: PayloadMutation


ATWOOD_COMPILER_REJECT_CASES = (
    AtwoodCompilerRejectCase(
        "massless-assumption-missing",
        _remove_record("assumptions", "assumption_id", "masslessRope"),
    ),
    AtwoodCompilerRejectCase(
        "inextensible-assumption-missing",
        _remove_record("assumptions", "assumption_id", "inextensibleRope"),
    ),
    AtwoodCompilerRejectCase(
        "fixed-pulley-assumption-missing",
        _remove_record("assumptions", "assumption_id", "fixedPulley"),
    ),
    AtwoodCompilerRejectCase(
        "ideal-pulley-assumption-missing",
        _remove_record("assumptions", "assumption_id", "idealPulley"),
    ),
    AtwoodCompilerRejectCase(
        "assumption-unevidenced",
        _clear_record_evidence("assumptions", "assumption_id", "idealPulley"),
    ),
    AtwoodCompilerRejectCase(
        "wrap-missing",
        _remove_record("geometry", "relation_id", "ropeWrap"),
    ),
    AtwoodCompilerRejectCase("wrap-extra-participant", _append_wrap_participant),
    AtwoodCompilerRejectCase(
        "attachment-missing",
        _remove_record("geometry", "relation_id", "ropeAttachedA"),
    ),
    AtwoodCompilerRejectCase(
        "attachment-unevidenced",
        _clear_record_evidence("geometry", "relation_id", "ropeAttachedB"),
    ),
    AtwoodCompilerRejectCase(
        "rope-interaction-extra-participant",
        _append_rope_interaction_participant,
    ),
    AtwoodCompilerRejectCase("gravity-quantity-cardinality", _remove_gravity_weight),
    AtwoodCompilerRejectCase("duplicate-frame-axis", _append_duplicate_axis),
    AtwoodCompilerRejectCase("extra-pulley-motion", _append_pulley_motion_quantity),
    AtwoodCompilerRejectCase(
        "incomplete-pulley-inertia",
        _append_incomplete_pulley_inertia,
    ),
    AtwoodCompilerRejectCase(
        "frame-unevidenced",
        _clear_record_evidence("reference_frames", "frame_id", FRAME_ID),
    ),
    AtwoodCompilerRejectCase(
        "interval-unevidenced",
        _clear_record_evidence(
            "motion_intervals",
            "interval_id",
            INTERVAL_ID,
        ),
    ),
    AtwoodCompilerRejectCase(
        "particle-unevidenced",
        _clear_record_evidence("entities", "entity_id", "bodyA"),
    ),
    AtwoodCompilerRejectCase(
        "rope-interaction-unevidenced",
        _clear_record_evidence(
            "interactions",
            "interaction_id",
            "ropeTension",
        ),
    ),
    AtwoodCompilerRejectCase(
        "taut-state-missing",
        _remove_record(
            "state_conditions",
            "state_condition_id",
            "ropeTautState",
        ),
    ),
    AtwoodCompilerRejectCase(
        "taut-state-unevidenced",
        _clear_record_evidence(
            "state_conditions",
            "state_condition_id",
            "ropeTautState",
        ),
    ),
    AtwoodCompilerRejectCase(
        "rope-declared-slack",
        _set_state("ropeTautState", "slack"),
    ),
    AtwoodCompilerRejectCase(
        "fixed-state-missing",
        _remove_record(
            "state_conditions",
            "state_condition_id",
            "pulleyFixedState",
        ),
    ),
    AtwoodCompilerRejectCase(
        "weight-direction-up",
        _set_quantity_direction("weightA", 1),
    ),
    AtwoodCompilerRejectCase(
        "tension-direction-down",
        _set_quantity_direction("tensionB", -1),
    ),
    AtwoodCompilerRejectCase(
        "body-a-acceleration-direction-down",
        _set_quantity_direction("accelerationA", -1),
    ),
)


@pytest.mark.parametrize(
    "case",
    ATWOOD_COMPILER_REJECT_CASES,
    ids=lambda case: case.label,
)
def test_pulley_atwood_structural_contract_fails_closed_without_legacy(
    case: AtwoodCompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized = _normalize(BASELINE, mutation=case.mutation)
    assert normalized.terminal is ValidationTerminal.accepted, normalized.issues
    assert type(normalized.ir) is MechanicsProblemIRV1
    _forbid_legacy_call(monkeypatch)

    execution = _execute(normalized.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def test_rigid_body_pair_retains_generic_fixed_pulley_rope_laws() -> None:
    normalized = _normalize(BASELINE, mutation=_use_rigid_moving_entities)
    assert normalized.terminal is ValidationTerminal.accepted, normalized.issues
    assert type(normalized.ir) is MechanicsProblemIRV1
    ir = normalized.ir

    result = MechanicsCompiler().compile(
        ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(ir),
        approved_assumption_ids=APPROVED_ASSUMPTION_IDS,
    )

    assert result.status in {
        CompilerStatus.ready,
        CompilerStatus.overdetermined,
        CompilerStatus.underdetermined,
    }
    assert result.graph is not None
    law_counts = Counter(equation.law_id for equation in result.graph.equations)
    assert law_counts["rope_massless_tension"] == 1
    assert law_counts["rope_fixed_pulley_motion"] == 1
    assert not any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in result.issues
    )


def test_tension_query_b_down_acceleration_fails_closed_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized = _normalize(
        TENSION_QUERY,
        mutation=_set_quantity_direction("accelerationB", -1),
    )
    assert normalized.terminal is ValidationTerminal.accepted, normalized.issues
    assert type(normalized.ir) is MechanicsProblemIRV1
    acceleration_b = next(
        item
        for item in normalized.ir.quantities
        if item.quantity_id == "accelerationB"
    )
    tension_b = next(
        item
        for item in normalized.ir.quantities
        if item.quantity_id == "tensionB"
    )
    assert "queryEvidence" not in acceleration_b.evidence_refs
    assert "queryEvidence" in tension_b.evidence_refs
    _forbid_legacy_call(monkeypatch)

    execution = _execute(normalized.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


@pytest.mark.parametrize(
    "source",
    (
        _source(0.0, 5.0),
        _source(-2.0, 5.0),
        _source(2.0, 5.0, gravity_si=0.0),
        _source(2.0, 5.0, gravity_si=-9.81),
    ),
    ids=("zero-mass", "negative-mass", "zero-gravity", "negative-gravity"),
)
def test_pulley_atwood_invalid_domain_fails_closed_without_legacy(
    source: AtwoodSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized = _normalize(source)
    assert normalized.terminal is ValidationTerminal.accepted, normalized.issues
    assert type(normalized.ir) is MechanicsProblemIRV1
    _forbid_legacy_call(monkeypatch)

    execution = _execute(normalized.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.invalid
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.invalid_domain
        for issue in execution.compiler_result.issues
    )


def _direct_core_law_ids(
    ir: MechanicsProblemIRV1,
    approved_assumption_ids: tuple[str, ...],
) -> tuple[str, ...]:
    relevant: set[str] = set()
    for collection_name, id_field in (
        ("entities", "entity_id"),
        ("points", "point_id"),
        ("reference_frames", "frame_id"),
        ("motion_intervals", "interval_id"),
        ("events", "event_id"),
        ("symbols", "symbol_id"),
        ("quantities", "quantity_id"),
        ("geometry", "relation_id"),
        ("interactions", "interaction_id"),
        ("constraints", "constraint_id"),
        ("state_conditions", "state_condition_id"),
        ("queries", "query_id"),
        ("assumptions", "assumption_id"),
    ):
        relevant.update(
            getattr(record, id_field)
            for record in getattr(ir, collection_name)
        )
    query = ir.queries[0]
    query_quantity = next(
        quantity
        for quantity in ir.quantities
        if quantity.quantity_id == query.target.target_quantity_id
    )
    context, _, query_symbol_id, issue = _build_law_context(
        ir,
        query,
        query_quantity,
        relevant,
        {symbol.symbol_id: symbol for symbol in ir.symbols},
        frozenset(approved_assumption_ids),
    )
    assert issue is None
    assert context is not None and query_symbol_id == BASELINE.query_symbol_id
    return tuple(emission.rule.law_id for emission in apply_core_laws(context))


@pytest.mark.parametrize(
    "remove_ideal_assumption",
    (False, True),
    ids=("ideal-approval-missing", "ideal-assumption-missing"),
)
def test_missing_ideal_authority_blocks_fixed_pulley_law_and_compiler(
    remove_ideal_assumption: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = tuple(
        assumption_id
        for assumption_id in APPROVED_ASSUMPTION_IDS
        if not (
            not remove_ideal_assumption and assumption_id == "idealPulley"
        )
    )
    if remove_ideal_assumption:
        normalized = _normalize(
            BASELINE,
            mutation=_remove_record(
                "assumptions",
                "assumption_id",
                "idealPulley",
            ),
        )
        assert normalized.terminal is ValidationTerminal.accepted, normalized.issues
        assert type(normalized.ir) is MechanicsProblemIRV1
        ir = normalized.ir
    else:
        ir = _build_ir(BASELINE)
    _forbid_legacy_call(monkeypatch)

    execution = _execute(ir, approved_assumption_ids=approved)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert "rope_fixed_pulley_motion" in _direct_core_law_ids(
        _build_ir(BASELINE),
        APPROVED_ASSUMPTION_IDS,
    )
    assert "rope_fixed_pulley_motion" not in _direct_core_law_ids(ir, approved)


def _declare_direction_ambiguity(payload: dict[str, object]) -> None:
    payload["ambiguities"] = [
        {
            "ambiguity_id": "atwoodDirectionAmbiguity",
            "kind": "direction",
            "referenced_ids": ["accelerationA", "accelerationB", "queryB"],
            "description": "The two particle directions are unresolved.",
            "blocking": True,
            "evidence_refs": ["ropeEvidence", "queryEvidence"],
        }
    ]


def _mismatch_query_direction(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    target = query["target"]
    assert isinstance(target, dict)
    target["direction"] = _direction(1)


@pytest.mark.parametrize(
    ("mutation", "approved_assumption_ids", "expected_terminal"),
    (
        (
            None,
            tuple(
                assumption_id
                for assumption_id in APPROVED_ASSUMPTION_IDS
                if assumption_id != "masslessRope"
            ),
            ValidationTerminal.needs_confirmation,
        ),
        (
            _declare_direction_ambiguity,
            APPROVED_ASSUMPTION_IDS,
            ValidationTerminal.needs_confirmation,
        ),
        (
            _mismatch_query_direction,
            APPROVED_ASSUMPTION_IDS,
            ValidationTerminal.invalid,
        ),
    ),
    ids=(
        "assumption-unapproved",
        "blocking-direction-ambiguity",
        "query-direction-mismatch",
    ),
)
def test_pulley_atwood_validation_gates_before_compile_and_legacy(
    mutation: PayloadMutation | None,
    approved_assumption_ids: tuple[str, ...],
    expected_terminal: ValidationTerminal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)

    normalized = _normalize(
        BASELINE,
        mutation=mutation,
        approved_assumption_ids=approved_assumption_ids,
    )

    assert normalized.terminal is expected_terminal
    assert normalized.accepted is False
    assert normalized.ir is None


def _diagnostic_variant(
    ir: MechanicsProblemIRV1,
    *,
    remove: bool,
) -> MechanicsProblemIRV1:
    payload = ir.model_dump(mode="python", warnings="none")
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
            b"unrelated diagnostic source"
        ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


@pytest.mark.slow
def test_pulley_atwood_diagnostic_metadata_is_invariant() -> None:
    evidence = _same_fixture(BASELINE)
    changed = _diagnostic_variant(evidence.ir, remove=False)
    removed = _diagnostic_variant(evidence.ir, remove=True)
    assert changed.source_evidence == removed.source_evidence == evidence.ir.source_evidence
    invariance: MechanicsMigrationInvarianceComparison = compare_mechanics_ir_invariance(
        evidence.execution,
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
        approved_assumption_ids=APPROVED_ASSUMPTION_IDS,
    )
    assert invariance.all_invariant is True, tuple(
        (
            item.label,
            tuple(field.value for field in item.differing_fields),
            item.note,
        )
        for item in invariance.variants
    )
    assert all(item.matches_baseline for item in invariance.variants)
