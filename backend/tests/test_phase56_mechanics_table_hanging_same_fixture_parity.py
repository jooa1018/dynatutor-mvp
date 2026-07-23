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
from engine.mechanics.laws.core import apply_core_laws
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
from engine.mechanics.solver import (
    CandidateCoverage,
    CandidateRejectionReason,
    SolveBackendKind,
)
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import ValidationTerminal
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity, SolverResult
from engine.solvers.pulley.table_hanging import TableHangingPulleySolver
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


FRAME_ID = "worldFrame"
INTERVAL_ID = "motionInterval"
VELOCITY = DimensionVector(length=1, time=-1)
IMPULSE = DimensionVector(mass=1, length=1, time=-1)
MOMENT_OF_INERTIA = DimensionVector(mass=1, length=2)
APPROVED_ASSUMPTION_IDS = (
    "fixedPulley",
    "idealPulley",
    "inextensibleRope",
    "masslessRope",
)


@dataclass(frozen=True)
class TableHangingSource:
    problem_text: str
    mass_a_si: float
    mass_b_si: float
    gravity_si: float
    regime: str
    coefficient: float | None
    b_acceleration_sign: int
    query_role: str
    query_direction: str
    motion_sign: int
    friction_sign: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.mass_a_si, "mass A"),
            (self.mass_b_si, "mass B"),
            (self.gravity_si, "gravity"),
        ):
            if type(value) is not float or not math.isfinite(value):
                raise ValueError(f"{label} must be one finite float")
        if self.regime not in {"inactive", "sticking", "sliding"}:
            raise ValueError("regime must be inactive, sticking, or sliding")
        if self.regime == "inactive" and self.coefficient is not None:
            raise ValueError("inactive friction must not carry a coefficient")
        if self.regime != "inactive" and (
            type(self.coefficient) is not float
            or not math.isfinite(self.coefficient)
        ):
            raise ValueError("active friction needs one finite coefficient")
        if self.b_acceleration_sign not in {-1, 1}:
            raise ValueError("hanging acceleration direction must be one axis sign")
        if self.query_role not in {"acceleration", "tension"}:
            raise ValueError("query role must be acceleration or tension")
        expected_direction = (
            "upward"
            if self.query_role == "tension" or self.b_acceleration_sign == 1
            else "downward"
        )
        if self.query_direction != expected_direction:
            raise ValueError("query wording and typed direction must agree")
        if self.motion_sign != 1 or self.friction_sign != -1:
            raise ValueError("the fixture binds rightward motion and leftward friction")

    @property
    def is_static(self) -> bool:
        return self.regime == "sticking"

    @property
    def is_sliding(self) -> bool:
        return self.regime == "sliding"

    @property
    def expected_acceleration_down_si(self) -> float:
        if self.is_static:
            return 0.0
        friction = (
            0.0
            if self.regime == "inactive"
            else float(self.coefficient) * self.mass_a_si * self.gravity_si
        )
        return (
            self.mass_b_si * self.gravity_si - friction
        ) / (self.mass_a_si + self.mass_b_si)

    @property
    def expected_normal_si(self) -> float:
        return self.mass_a_si * self.gravity_si

    @property
    def expected_friction_si(self) -> float:
        if self.regime == "inactive":
            return 0.0
        if self.is_static:
            return self.mass_b_si * self.gravity_si
        return float(self.coefficient) * self.expected_normal_si

    @property
    def expected_tension_si(self) -> float:
        return self.mass_b_si * (
            self.gravity_si - self.expected_acceleration_down_si
        )

    @property
    def expected_query_value_si(self) -> float:
        if self.query_role == "tension":
            return self.expected_tension_si
        return -self.b_acceleration_sign * self.expected_acceleration_down_si

    @property
    def query_symbol_id(self) -> str:
        return "tB" if self.query_role == "tension" else "aBy"


def _source(
    regime: str,
    *,
    mass_a_si: float = 2.0,
    mass_b_si: float = 1.0,
    gravity_si: float = 9.81,
    coefficient: float | None = None,
    b_acceleration_sign: int = -1,
    query_role: str = "acceleration",
) -> TableHangingSource:
    query_direction = (
        "upward"
        if query_role == "tension" or b_acceleration_sign == 1
        else "downward"
    )
    if regime == "inactive":
        regime_sentences = (
            "The contact is explicitly frictionless.",
        )
    elif regime == "sticking":
        regime_sentences = (
            "The contact is in the sticking static-friction regime.",
            f"The coefficient of static friction is {float(coefficient):g}.",
            "Block A remains at rest throughout the interval.",
            "The hanging block tends to descend and static friction on block A acts left.",
        )
    else:
        regime_sentences = (
            "The contact is in the sliding kinetic-friction regime.",
            f"The coefficient of kinetic friction is {float(coefficient):g}.",
            "Block A is moving right at 1 m/s.",
            "Kinetic friction on block A acts left.",
        )
    query_sentence = (
        "Find the tension acting upward on block B."
        if query_role == "tension"
        else f"Find the acceleration of block B along the {query_direction} direction."
    )
    problem_text = " ".join(
        (
            f"Block A has mass {mass_a_si:g} kg.",
            "Block A remains in touching contact with a fixed horizontal table.",
            f"Block B has mass {mass_b_si:g} kg and hangs vertically.",
            f"Take g = {gravity_si:g} m/s^2.",
            *regime_sentences,
            "The blocks are joined by one massless, inextensible rope.",
            "The rope is taut.",
            "The rope wraps over one ideal massless frictionless pulley.",
            "The pulley is fixed and remains at rest.",
            "The rope is attached to block A.",
            "The rope is attached to block B.",
            "The +x axis points right and the +y axis points upward.",
            query_sentence,
        )
    )
    return TableHangingSource(
        problem_text=problem_text,
        mass_a_si=float(mass_a_si),
        mass_b_si=float(mass_b_si),
        gravity_si=float(gravity_si),
        regime=regime,
        coefficient=None if coefficient is None else float(coefficient),
        b_acceleration_sign=b_acceleration_sign,
        query_role=query_role,
        query_direction=query_direction,
        motion_sign=1,
        friction_sign=-1,
    )


NO_FRICTION = _source("inactive")
KINETIC = _source("sliding", coefficient=0.2)
IMPULSE_CARRIER_SOURCE = TableHangingSource(
    problem_text=(
        f"{KINETIC.problem_text} "
        "The alternate typed motion carrier is reported as 1 N*s."
    ),
    mass_a_si=KINETIC.mass_a_si,
    mass_b_si=KINETIC.mass_b_si,
    gravity_si=KINETIC.gravity_si,
    regime=KINETIC.regime,
    coefficient=KINETIC.coefficient,
    b_acceleration_sign=KINETIC.b_acceleration_sign,
    query_role=KINETIC.query_role,
    query_direction=KINETIC.query_direction,
    motion_sign=KINETIC.motion_sign,
    friction_sign=KINETIC.friction_sign,
)
KINETIC_ZERO_MU = _source("sliding", coefficient=0.0)
STATIC_HOLD = _source("sticking", coefficient=0.8)
STATIC_BOUNDARY = _source("sticking", coefficient=0.5)
B_UP_QUERY = _source("sliding", coefficient=0.2, b_acceleration_sign=1)
TENSION_QUERY = _source("sliding", coefficient=0.2, query_role="tension")
STATIC_INFEASIBLE = _source("sticking", coefficient=0.49)


@dataclass(frozen=True)
class TableHangingResiduals:
    weight_a: float
    weight_b: float
    table_tangent_newton: float
    table_normal_newton: float
    hanging_newton: float
    no_penetration: float
    equal_tension: float
    rope_acceleration: float
    friction_equality: float
    static_acceleration: float
    acceleration_closed_form: float
    tension_closed_form: float
    friction_margin: float
    tension_a_si: float
    tension_b_si: float
    normal_si: float
    friction_si: float
    directions_opposed: bool

    @property
    def passed(self) -> bool:
        equalities = (
            self.weight_a,
            self.weight_b,
            self.table_tangent_newton,
            self.table_normal_newton,
            self.hanging_newton,
            self.no_penetration,
            self.equal_tension,
            self.rope_acceleration,
            self.friction_equality,
            self.static_acceleration,
            self.acceleration_closed_form,
            self.tension_closed_form,
        )
        return (
            all(abs(value) <= 1.0e-10 for value in equalities)
            and self.friction_margin >= -1.0e-10
            and self.tension_a_si >= -1.0e-10
            and self.tension_b_si >= -1.0e-10
            and self.normal_si >= -1.0e-10
            and self.friction_si >= -1.0e-10
            and self.directions_opposed
        )


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport
    residuals: TableHangingResiduals


def _direction(axis: str, sign: int) -> dict[str, object]:
    return _axis_direction(axis, sign, frame_id=FRAME_ID)


def _draft_payload(source: TableHangingSource) -> dict[str, object]:
    mass_a_raw = f"{source.mass_a_si:g}"
    mass_b_raw = f"{source.mass_b_si:g}"
    gravity_raw = f"{source.gravity_si:g}"
    coefficient_raw = (
        None if source.coefficient is None else f"{source.coefficient:g}"
    )
    mass_a_quote = f"Block A has mass {mass_a_raw} kg."
    mass_b_quote = f"Block B has mass {mass_b_raw} kg and hangs vertically."
    gravity_quote = f"Take g = {gravity_raw} m/s^2."
    contact_quote = "Block A remains in touching contact with a fixed horizontal table."
    rope_quote = "The blocks are joined by one massless, inextensible rope."
    taut_quote = "The rope is taut."
    wrap_quote = "The rope wraps over one ideal massless frictionless pulley."
    fixed_pulley_quote = "The pulley is fixed and remains at rest."
    attach_a_quote = "The rope is attached to block A."
    attach_b_quote = "The rope is attached to block B."
    orientation_quote = "The +x axis points right and the +y axis points upward."
    if source.regime == "inactive":
        regime_quote = "The contact is explicitly frictionless."
        coefficient_quote = None
        motion_quote = None
        friction_quote = None
    elif source.is_static:
        regime_quote = "The contact is in the sticking static-friction regime."
        coefficient_quote = (
            f"The coefficient of static friction is {coefficient_raw}."
        )
        motion_quote = "Block A remains at rest throughout the interval."
        friction_quote = (
            "The hanging block tends to descend and static friction on block A acts left."
        )
    else:
        regime_quote = "The contact is in the sliding kinetic-friction regime."
        coefficient_quote = (
            f"The coefficient of kinetic friction is {coefficient_raw}."
        )
        motion_quote = "Block A is moving right at 1 m/s."
        friction_quote = "Kinetic friction on block A acts left."
    query_quote = (
        "Find the tension acting upward on block B."
        if source.query_role == "tension"
        else (
            "Find the acceleration of block B along the "
            f"{source.query_direction} direction."
        )
    )
    evidence_specs: list[tuple[str, str, str | None]] = [
        ("massAEvidence", mass_a_quote, f"{mass_a_raw} kg"),
        ("massBEvidence", mass_b_quote, f"{mass_b_raw} kg"),
        ("gravityEvidence", gravity_quote, f"{gravity_raw} m/s^2"),
        ("contactEvidence", contact_quote, None),
        ("regimeEvidence", regime_quote, None),
        ("ropeEvidence", rope_quote, None),
        ("tautEvidence", taut_quote, None),
        ("wrapEvidence", wrap_quote, None),
        ("fixedPulleyEvidence", fixed_pulley_quote, None),
        ("attachAEvidence", attach_a_quote, None),
        ("attachBEvidence", attach_b_quote, None),
        ("orientationEvidence", orientation_quote, None),
        ("queryEvidence", query_quote, None),
    ]
    if coefficient_quote is not None and coefficient_raw is not None:
        evidence_specs.append(
            ("coefficientEvidence", coefficient_quote, coefficient_raw)
        )
    if motion_quote is not None:
        evidence_specs.append(
            (
                "motionEvidence",
                motion_quote,
                "1 m/s" if source.is_sliding else None,
            )
        )
    if friction_quote is not None:
        evidence_specs.append(("frictionDirectionEvidence", friction_quote, None))
    evidence = [
        _text_evidence(
            source.problem_text,
            evidence_id=evidence_id,
            quote=quote,
            quantity_token=quantity_token,
        )
        for evidence_id, quote, quantity_token in evidence_specs
    ]

    symbol_specs = [
        ("mA", "massA", MASS),
        ("mB", "massB", MASS),
        ("g", "gravity", ACCELERATION),
        ("wA", "weightA", FORCE),
        ("wB", "weightB", FORCE),
        ("nA", "normalA", FORCE),
        ("tA", "tensionA", FORCE),
        ("tB", "tensionB", FORCE),
        ("aAx", "accelerationAx", ACCELERATION),
        ("aAy", "accelerationAy", ACCELERATION),
        ("aBy", "accelerationBy", ACCELERATION),
    ]
    if source.regime != "inactive":
        symbol_specs.extend(
            (("fA", "frictionA", FORCE), ("muA", "coefficientA", DIMENSIONLESS))
        )
    if source.is_sliding:
        symbol_specs.append(("vAx", "velocityAx", VELOCITY))
    symbols = [_symbol(*spec) for spec in symbol_specs]

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
            direction=_direction("y", -1),
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
            direction=_direction("y", -1),
            evidence_refs=("gravityEvidence", "orientationEvidence"),
        ),
        _quantity(
            "normalA",
            "nA",
            "force",
            "bodyA",
            FORCE,
            point_id="contactA",
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction("y", 1),
            evidence_refs=("contactEvidence", "orientationEvidence"),
        ),
        _quantity(
            "tensionA",
            "tA",
            "force",
            "bodyA",
            FORCE,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="x",
            direction=_direction("x", 1),
            evidence_refs=(
                "ropeEvidence",
                "tautEvidence",
                "wrapEvidence",
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
            direction=_direction("y", 1),
            evidence_refs=(
                "ropeEvidence",
                "tautEvidence",
                "wrapEvidence",
                "attachBEvidence",
                "orientationEvidence",
                *(("queryEvidence",) if source.query_role == "tension" else ()),
            ),
        ),
        _quantity(
            "accelerationAx",
            "aAx",
            "acceleration",
            "bodyA",
            ACCELERATION,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="x",
            direction=_direction("x", 1),
            evidence_refs=("ropeEvidence", "orientationEvidence"),
        ),
        _quantity(
            "accelerationAy",
            "aAy",
            "acceleration",
            "bodyA",
            ACCELERATION,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction("y", 1),
            evidence_refs=("contactEvidence", "orientationEvidence"),
        ),
        _quantity(
            "accelerationBy",
            "aBy",
            "acceleration",
            "bodyB",
            ACCELERATION,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction("y", source.b_acceleration_sign),
            evidence_refs=(
                "ropeEvidence",
                "orientationEvidence",
                *(("queryEvidence",) if source.query_role == "acceleration" else ()),
            ),
        ),
    ]
    if source.regime != "inactive":
        assert coefficient_raw is not None
        quantities.extend(
            (
                _quantity(
                    "frictionA",
                    "fA",
                    "force",
                    "bodyA",
                    FORCE,
                    point_id="contactA",
                    frame_id=FRAME_ID,
                    interval_id=INTERVAL_ID,
                    component="x",
                    direction=_direction("x", -1),
                    evidence_refs=(
                        "contactEvidence",
                        "regimeEvidence",
                        "frictionDirectionEvidence",
                    ),
                ),
                _quantity(
                    "coefficientA",
                    "muA",
                    "coefficient_friction",
                    "bodyA",
                    DIMENSIONLESS,
                    provenance="explicit_source",
                    evidence_refs=("coefficientEvidence",),
                    raw_value=coefficient_raw,
                    raw_unit="",
                ),
            )
        )
    if source.is_sliding:
        quantities.append(
            _quantity(
                "velocityAx",
                "vAx",
                "velocity",
                "bodyA",
                VELOCITY,
                frame_id=FRAME_ID,
                interval_id=INTERVAL_ID,
                component="x",
                direction=_direction("x", 1),
                provenance="explicit_source",
                evidence_refs=("motionEvidence",),
                raw_value="1",
                raw_unit="m/s",
            )
        )

    contact_quantity_ids = ["normalA", "accelerationAy"]
    if source.regime != "inactive":
        contact_quantity_ids.extend(("frictionA", "coefficientA"))
    friction_quantity_ids = (
        []
        if source.regime == "inactive"
        else ["frictionA", "normalA", "coefficientA"]
    )
    states: list[dict[str, object]] = [
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
        {
            "state_condition_id": "contactState",
            "kind": "contact",
            "state": "touching",
            "subject_id": "bodyA",
            "interval_id": INTERVAL_ID,
            "quantity_ids": ["normalA", "accelerationAy"],
            "evidence_refs": ["contactEvidence"],
        },
        {
            "state_condition_id": "surfaceFixedState",
            "kind": "motion",
            "state": "at_rest",
            "subject_id": "table",
            "interval_id": INTERVAL_ID,
            "quantity_ids": [],
            "evidence_refs": ["contactEvidence"],
        },
        {
            "state_condition_id": "frictionState",
            "kind": "friction",
            "state": source.regime,
            "subject_id": "bodyA",
            "interval_id": INTERVAL_ID,
            "quantity_ids": friction_quantity_ids,
            "evidence_refs": ["regimeEvidence"],
        },
    ]
    if source.regime != "inactive":
        states.append(
            {
                "state_condition_id": "bodyMotionState",
                "kind": "motion",
                "state": "at_rest" if source.is_static else "moving",
                "subject_id": "bodyA",
                "interval_id": INTERVAL_ID,
                "quantity_ids": [] if source.is_static else ["velocityAx"],
                "evidence_refs": ["motionEvidence"],
            }
        )

    query_quantity_id = (
        "tensionB" if source.query_role == "tension" else "accelerationBy"
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
            "system_type": "diagnosticTableHangingLabel",
            "subtype": "diagnosticFrictionRegimeLabel",
            "model_id": "sameFixtureTableHangingTest",
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
                "evidence_refs": ["massAEvidence", "contactEvidence", "attachAEvidence"],
            },
            {
                "entity_id": "bodyB",
                "primitive": "particle",
                "evidence_refs": ["massBEvidence", "attachBEvidence"],
            },
            {
                "entity_id": "table",
                "primitive": "surface",
                "evidence_refs": ["contactEvidence"],
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
        "points": [
            {
                "point_id": "contactA",
                "role": "contact",
                "owner_entity_id": "bodyA",
                "frame_id": FRAME_ID,
                "evidence_refs": ["contactEvidence"],
            }
        ],
        "reference_frames": [
            {
                "frame_id": FRAME_ID,
                "frame_type": "cartesian_2d",
                "origin": {"kind": "world"},
                "axes": [
                    _axis_binding("x", frame_id=FRAME_ID),
                    _axis_binding("y", frame_id=FRAME_ID),
                ],
                "evidence_refs": ["orientationEvidence"],
            }
        ],
        "motion_intervals": [
            {
                "interval_id": INTERVAL_ID,
                "order": 1,
                "subject_ids": [
                    "bodyA",
                    "bodyB",
                    "table",
                    "rope",
                    "pulley",
                    "world",
                ],
                "frame_id": FRAME_ID,
                "evidence_refs": [
                    "contactEvidence",
                    "regimeEvidence",
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
                "interaction_id": "contactInteraction",
                "kind": "contact",
                "participant_ids": ["bodyA", "table"],
                "point_ids": ["contactA"],
                "frame_id": FRAME_ID,
                "interval_id": INTERVAL_ID,
                "quantity_ids": contact_quantity_ids,
                "evidence_refs": ["contactEvidence", "regimeEvidence"],
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
        "state_conditions": states,
        "queries": [
            {
                "query_id": "queryB",
                "target": {
                    "role": "force" if source.query_role == "tension" else "acceleration",
                    "subject_id": "bodyB",
                    "frame_id": FRAME_ID,
                    "interval_id": INTERVAL_ID,
                    "component": "y",
                    "direction": _direction("y", query_direction_sign),
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
    source: TableHangingSource,
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


def _build_ir(source: TableHangingSource) -> MechanicsProblemIRV1:
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
    source: TableHangingSource,
    values: dict[str, float],
) -> TableHangingResiduals:
    required = {"wA", "wB", "nA", "tA", "tB", "aAx", "aAy", "aBy"}
    if source.regime != "inactive":
        required.add("fA")
    assert required.issubset(values)
    friction = 0.0 if source.regime == "inactive" else values["fA"]
    physical_b_acceleration_y = source.b_acceleration_sign * values["aBy"]
    friction_equality = (
        friction - float(source.coefficient) * values["nA"]
        if source.is_sliding
        else 0.0
    )
    friction_margin = (
        float(source.coefficient) * values["nA"] - abs(friction)
        if source.is_static
        else 0.0
    )
    return TableHangingResiduals(
        weight_a=values["wA"] - source.mass_a_si * source.gravity_si,
        weight_b=values["wB"] - source.mass_b_si * source.gravity_si,
        table_tangent_newton=(
            values["tA"] - friction - source.mass_a_si * values["aAx"]
        ),
        table_normal_newton=(
            values["nA"] - values["wA"] - source.mass_a_si * values["aAy"]
        ),
        hanging_newton=(
            values["tB"]
            - values["wB"]
            - source.mass_b_si * physical_b_acceleration_y
        ),
        no_penetration=values["aAy"],
        equal_tension=values["tA"] - values["tB"],
        rope_acceleration=values["aAx"] + physical_b_acceleration_y,
        friction_equality=friction_equality,
        static_acceleration=values["aAx"] if source.is_static else 0.0,
        acceleration_closed_form=(
            values["aAx"] - source.expected_acceleration_down_si
        ),
        tension_closed_form=values["tA"] - source.expected_tension_si,
        friction_margin=friction_margin,
        tension_a_si=values["tA"],
        tension_b_si=values["tB"],
        normal_si=values["nA"],
        friction_si=friction,
        directions_opposed=(source.friction_sign == -source.motion_sign),
    )


def _legacy_answer_value(result: SolverResult, symbol: str) -> float:
    item = next(answer for answer in result.answers if answer.symbol == symbol)
    assert type(item.numeric) is float
    return item.numeric


def _observe_legacy(
    source: TableHangingSource,
) -> tuple[LegacyObservation, SolverResult]:
    knowns = {
        "m1": Quantity("m1", source.mass_a_si, "kg"),
        "m2": Quantity("m2", source.mass_b_si, "kg"),
        "g": Quantity("g", source.gravity_si, "m/s^2"),
    }
    friction_type = {
        "inactive": "none",
        "sticking": "static",
        "sliding": "kinetic",
    }[source.regime]
    if source.is_static:
        knowns["mu_s"] = Quantity("mu_s", source.coefficient, "")
    elif source.is_sliding:
        knowns["mu_k"] = Quantity("mu_k", source.coefficient, "")
    problem = CanonicalProblem(
        system_type="pulley_table_hanging",
        friction_type=friction_type,
        knowns=knowns,
        unknowns=["acceleration", "tension"],
        requested_outputs=["acceleration", "tension"],
    )
    assert problem.raw_text == ""
    result = TableHangingPulleySolver().solve(problem)
    assert result.ok is True
    assert result.verification.passed is True
    acceleration = _legacy_answer_value(result, "a")
    tension = _legacy_answer_value(result, "T")
    if source.is_static:
        assert result.selection_decision is None
        assert acceleration == 0.0
        friction = _legacy_answer_value(result, "f_s")
    else:
        decision = result.selection_decision
        assert decision is not None and decision.status == "selected"
        assert decision.selected_candidate is not None
        mapping = decision.selected_candidate.numerical_mapping
        assert {"T", "T1", "a"}.issubset(mapping)
        assert decision.valid_alternatives == []
        assert decision.rejected_candidates == []
        acceleration = mapping["a"]
        tension = mapping["T"]
        friction = 0.0 if source.regime == "inactive" else mapping["F"]
    residual_passed = (
        math.isclose(
            acceleration,
            source.expected_acceleration_down_si,
            rel_tol=0.0,
            abs_tol=1.0e-10,
        )
        and math.isclose(
            tension,
            source.expected_tension_si,
            rel_tol=0.0,
            abs_tol=1.0e-10,
        )
        and math.isclose(
            friction,
            source.expected_friction_si,
            rel_tol=0.0,
            abs_tol=1.0e-10,
        )
    )
    assert residual_passed is True
    selected = (
        tension
        if source.query_role == "tension"
        else -source.b_acceleration_sign * acceleration
    )
    normalized = normalize_quantity(
        str(selected),
        "N" if source.query_role == "tension" else "m/s^2",
        "scalar",
        FORCE if source.query_role == "tension" else ACCELERATION,
    )
    assert type(normalized.value) is float
    observation = LegacyObservation(
        case_id=(
            f"tableHanging{source.regime.title()}Ma{source.mass_a_si:g}"
            f"Mb{source.mass_b_si:g}{source.query_role.title()}"
            f"{source.query_direction.title()}"
        ).replace(".", "p"),
        diagnostic_kernel_id="tableHangingPulleyDirectV1",
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


def _same_fixture(source: TableHangingSource) -> SameFixtureEvidence:
    ir = _build_ir(source)
    assert "raw_text" not in type(ir).model_fields

    execution = _execute(ir)
    assert execution.terminal is MigrationProbeTerminal.solved, (
        None
        if execution.compiler_result is None
        else execution.compiler_result.issues
    )
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is not None
    assert execution.solve_result is not None
    generic_signature = build_generic_result_invariance_signature(
        execution.solve_result
    )
    frozen_graph_fingerprint = execution.compiler_result.graph.fingerprint
    frozen_plan_fingerprint = execution.solve_result.plan.plan_fingerprint
    candidate_values = _candidate_values(execution)
    frozen_candidate_values = tuple(sorted(candidate_values.items()))
    residuals = _independent_residuals(source, candidate_values)
    assert residuals.passed is True

    observation, _ = _observe_legacy(source)
    report = build_legacy_differential_report(execution.solve_result, observation)
    assert build_generic_result_invariance_signature(
        execution.solve_result
    ) == generic_signature
    assert execution.compiler_result.graph.fingerprint == frozen_graph_fingerprint
    assert execution.solve_result.plan.plan_fingerprint == frozen_plan_fingerprint
    assert tuple(sorted(_candidate_values(execution).items())) == frozen_candidate_values
    assert _independent_residuals(source, _candidate_values(execution)) == residuals
    return SameFixtureEvidence(
        registry_entry="pulley_table_hanging",
        ir=ir,
        execution=execution,
        observation=observation,
        report=report,
        residuals=residuals,
    )


POSITIVE_CASES = (
    NO_FRICTION,
    KINETIC,
    KINETIC_ZERO_MU,
    STATIC_HOLD,
    STATIC_BOUNDARY,
    B_UP_QUERY,
    TENSION_QUERY,
)


@pytest.mark.slow
@pytest.mark.parametrize(
    "source",
    POSITIVE_CASES,
    ids=(
        "explicit-no-friction",
        "kinetic",
        "kinetic-zero-mu",
        "static-hold",
        "static-exact-boundary",
        "hanging-up-signed-query",
        "tension-query",
    ),
)
def test_table_hanging_same_fixture_full_parity(source: TableHangingSource) -> None:
    evidence = _same_fixture(source)
    execution = evidence.execution
    compiler = execution.compiler_result
    result = execution.solve_result
    assert evidence.registry_entry == "pulley_table_hanging"
    assert compiler is not None and compiler.graph is not None
    assert execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert execution.solve_terminal is MechanicsSolveTerminal.solved

    law_counts = Counter(item.law_id for item in compiler.graph.equations)
    expected = Counter(
        {
            "particle_weight": 2,
            "particle_newton_second": 3,
            "fixed_contact_no_penetration": 1,
            "contact_normal_bound": 1,
            "rope_massless_tension": 1,
            "rope_fixed_pulley_motion": 1,
        }
    )
    if source.is_static:
        expected.update(
            {
                "contact_friction_bound": 2,
                "contact_sticking_static_acceleration": 1,
            }
        )
    elif source.is_sliding:
        expected["contact_sliding_friction"] = 1
    assert law_counts == expected

    required_source_quantity_ids = {
        "massA",
        "massB",
        "gravity",
        "weightA",
        "weightB",
        "normalA",
        "tensionA",
        "tensionB",
        "accelerationAx",
        "accelerationAy",
        "accelerationBy",
    }
    if source.regime != "inactive":
        required_source_quantity_ids.update(("frictionA", "coefficientA"))
    if source.is_sliding:
        required_source_quantity_ids.add("velocityAx")
    observed_source_quantity_ids = {
        quantity_id
        for equation in compiler.graph.equations
        for quantity_id in equation.source_quantity_ids
    }
    assert required_source_quantity_ids.issubset(observed_source_quantity_ids)
    derived_ids = {
        "weightA",
        "weightB",
        "normalA",
        "tensionA",
        "tensionB",
        "accelerationAx",
        "accelerationAy",
        "accelerationBy",
        "frictionA",
    }
    assert not any(
        quantity.si_value is not None
        for quantity in evidence.ir.quantities
        if quantity.quantity_id in derived_ids
    )
    assert evidence.ir.constraints == ()

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
    if source is STATIC_BOUNDARY:
        assert evidence.residuals.friction_margin == pytest.approx(
            0.0, rel=0.0, abs=1.0e-10
        )
    if source is KINETIC_ZERO_MU:
        assert evidence.residuals.friction_si == pytest.approx(0.0, abs=1.0e-10)
        assert candidate.query_value_si == pytest.approx(
            NO_FRICTION.expected_query_value_si,
            rel=0.0,
            abs=1.0e-10,
        )
        assert source.expected_tension_si == pytest.approx(
            NO_FRICTION.expected_tension_si,
            rel=0.0,
            abs=1.0e-10,
        )
    assert evidence.observation.residual_passed is True
    assert evidence.report.status is DifferentialStatus.full_parity
    assert evidence.report.discrepancies == ()
    assert evidence.report.observation_terminal is LegacyTerminal.solved
    assert evidence.report.generic_terminal is MechanicsSolveTerminal.solved


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
            b"unrelated diagnostic wording"
        ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


@pytest.mark.slow
def test_table_hanging_diagnostic_metadata_is_invariant() -> None:
    evidence = _same_fixture(KINETIC)
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


def _forbid_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> SolverResult:
        raise AssertionError("a rejected generic table fixture must not call legacy")

    monkeypatch.setattr(TableHangingPulleySolver, "solve", forbidden)


@pytest.mark.slow
def test_table_hanging_infeasible_sticking_is_rejected_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ir = _build_ir(STATIC_INFEASIBLE)
    _forbid_legacy_call(monkeypatch)

    execution = _execute(ir)

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


def _record(
    payload: dict[str, object],
    collection_name: str,
    id_field: str,
    record_id: str,
) -> dict[str, object]:
    collection = payload[collection_name]
    assert isinstance(collection, list)
    return next(
        item
        for item in collection
        if isinstance(item, dict) and item.get(id_field) == record_id
    )


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


def _clear_evidence(
    collection_name: str,
    id_field: str,
    record_id: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(payload, collection_name, id_field, record_id)["evidence_refs"] = []

    return mutate


def _set_primitive(entity_id: str, primitive: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(payload, "entities", "entity_id", entity_id)["primitive"] = primitive

    return mutate


def _set_state(state_id: str, value: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(
            payload, "state_conditions", "state_condition_id", state_id
        )["state"] = value

    return mutate


def _set_quantity_direction(
    quantity_id: str,
    axis: str,
    sign: int,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(payload, "quantities", "quantity_id", quantity_id)["direction"] = (
            _direction(axis, sign)
        )

    return mutate


def _clear_quantity_symbol(quantity_id: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        quantity = _record(payload, "quantities", "quantity_id", quantity_id)
        symbol_id = quantity["symbol_id"]
        assert isinstance(symbol_id, str)
        quantity["symbol_id"] = None
        symbols = payload["symbols"]
        assert isinstance(symbols, list)
        payload["symbols"] = [
            item
            for item in symbols
            if not isinstance(item, dict) or item.get("symbol_id") != symbol_id
        ]

    return mutate


def _set_impulse_velocity_carrier(payload: dict[str, object]) -> None:
    quote = "The alternate typed motion carrier is reported as 1 N*s."
    quantity_token = "1 N*s"
    start = IMPULSE_CARRIER_SOURCE.problem_text.index(quote)
    quantity_start = start + quote.index(quantity_token)
    evidence = _record(
        payload, "source_evidence", "evidence_id", "motionEvidence"
    )
    evidence.update(
        {
            "quote": quote,
            "source_span": {"start": start, "end": start + len(quote)},
            "quantity_span": {
                "start": quantity_start,
                "end": quantity_start + len(quantity_token),
            },
            "occurrence_index": 0,
        }
    )
    velocity = _record(payload, "quantities", "quantity_id", "velocityAx")
    velocity["dimension"] = IMPULSE.model_dump(mode="json")
    velocity["raw_unit"] = "N*s"
    _record(payload, "symbols", "symbol_id", "vAx")["dimension"] = (
        IMPULSE.model_dump(mode="json")
    )


def _append_duplicate_x_axis(payload: dict[str, object]) -> None:
    frame = _record(payload, "reference_frames", "frame_id", FRAME_ID)
    axes = frame["axes"]
    assert isinstance(axes, list)
    axes.append(_axis_binding("x", frame_id=FRAME_ID))


def _remove_contact_point(payload: dict[str, object]) -> None:
    _record(
        payload, "interactions", "interaction_id", "contactInteraction"
    )["point_ids"] = []


def _append_rope_participant(payload: dict[str, object]) -> None:
    interaction = _record(payload, "interactions", "interaction_id", "ropeTension")
    participants = interaction["participant_ids"]
    assert isinstance(participants, list)
    participants.append("table")


def _remove_interaction_quantity(
    interaction_id: str,
    quantity_id: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        interaction = _record(
            payload, "interactions", "interaction_id", interaction_id
        )
        quantity_ids = interaction["quantity_ids"]
        assert isinstance(quantity_ids, list)
        interaction["quantity_ids"] = [
            item for item in quantity_ids if item != quantity_id
        ]

    return mutate


def _remove_motion_carrier(payload: dict[str, object]) -> None:
    _record(
        payload, "state_conditions", "state_condition_id", "bodyMotionState"
    )["quantity_ids"] = []


def _set_contact_kind_to_applied_force(payload: dict[str, object]) -> None:
    _record(
        payload, "interactions", "interaction_id", "contactInteraction"
    )["kind"] = "applied_force"


def _append_pulley_inertia(payload: dict[str, object]) -> None:
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


def _append_client_equation(payload: dict[str, object]) -> None:
    constraints = payload["constraints"]
    assert isinstance(constraints, list)
    constraints.append(
        {
            "constraint_id": "clientAccelerationEquation",
            "kind": "dynamic",
            "expression": {
                "op": "equality",
                "left": {
                    "op": "symbol",
                    "symbol_id": "aAx",
                    "dimension": ACCELERATION.model_dump(mode="json"),
                },
                "right": {
                    "op": "literal",
                    "value": 0.0,
                    "dimension": ACCELERATION.model_dump(mode="json"),
                },
            },
            "subject_ids": ["bodyA"],
            "interval_id": INTERVAL_ID,
            "evidence_refs": ["queryEvidence"],
        }
    )


def _set_derived_numeric_value(payload: dict[str, object]) -> None:
    quantity = _record(payload, "quantities", "quantity_id", "tensionA")
    quantity["provenance"] = "explicit_source"
    quantity["raw_value"] = "1"
    quantity["raw_unit"] = "N"


def _set_inactive_with_active_quantities(payload: dict[str, object]) -> None:
    state = _record(
        payload, "state_conditions", "state_condition_id", "frictionState"
    )
    state["state"] = "inactive"


@dataclass(frozen=True)
class CompilerRejectCase:
    label: str
    source: TableHangingSource
    mutation: PayloadMutation


COMPILER_REJECT_CASES = (
    CompilerRejectCase(
        "massless-assumption-missing",
        KINETIC,
        _remove_record("assumptions", "assumption_id", "masslessRope"),
    ),
    CompilerRejectCase(
        "inextensible-assumption-missing",
        KINETIC,
        _remove_record("assumptions", "assumption_id", "inextensibleRope"),
    ),
    CompilerRejectCase(
        "fixed-pulley-assumption-missing",
        KINETIC,
        _remove_record("assumptions", "assumption_id", "fixedPulley"),
    ),
    CompilerRejectCase(
        "ideal-assumption-unevidenced",
        KINETIC,
        _clear_evidence("assumptions", "assumption_id", "idealPulley"),
    ),
    CompilerRejectCase(
        "malformed-incline-surface",
        KINETIC,
        _set_primitive("table", "incline"),
    ),
    CompilerRejectCase(
        "malformed-atwood-contact-kind",
        KINETIC,
        _set_contact_kind_to_applied_force,
    ),
    CompilerRejectCase(
        "wrap-missing",
        KINETIC,
        _remove_record("geometry", "relation_id", "ropeWrap"),
    ),
    CompilerRejectCase(
        "attachment-missing",
        KINETIC,
        _remove_record("geometry", "relation_id", "ropeAttachedA"),
    ),
    CompilerRejectCase(
        "contact-point-missing",
        KINETIC,
        _remove_contact_point,
    ),
    CompilerRejectCase(
        "rope-extra-surface-participant",
        KINETIC,
        _append_rope_participant,
    ),
    CompilerRejectCase(
        "gravity-weight-cardinality",
        KINETIC,
        _remove_interaction_quantity("gravityB", "weightB"),
    ),
    CompilerRejectCase(
        "contact-normal-cardinality",
        KINETIC,
        _remove_interaction_quantity("contactInteraction", "normalA"),
    ),
    CompilerRejectCase(
        "duplicate-world-x-axis",
        KINETIC,
        _append_duplicate_x_axis,
    ),
    CompilerRejectCase(
        "frame-unevidenced",
        KINETIC,
        _clear_evidence("reference_frames", "frame_id", FRAME_ID),
    ),
    CompilerRejectCase(
        "interval-unevidenced",
        KINETIC,
        _clear_evidence("motion_intervals", "interval_id", INTERVAL_ID),
    ),
    CompilerRejectCase(
        "contact-state-missing",
        KINETIC,
        _remove_record("state_conditions", "state_condition_id", "contactState"),
    ),
    CompilerRejectCase(
        "surface-fixed-state-missing",
        KINETIC,
        _remove_record(
            "state_conditions", "state_condition_id", "surfaceFixedState"
        ),
    ),
    CompilerRejectCase(
        "friction-state-missing",
        KINETIC,
        _remove_record("state_conditions", "state_condition_id", "frictionState"),
    ),
    CompilerRejectCase(
        "rope-slack",
        KINETIC,
        _set_state("ropeTautState", "slack"),
    ),
    CompilerRejectCase(
        "moving-pulley",
        KINETIC,
        _set_state("pulleyFixedState", "moving"),
    ),
    CompilerRejectCase(
        "moving-surface",
        KINETIC,
        _set_state("surfaceFixedState", "moving"),
    ),
    CompilerRejectCase(
        "sliding-carrier-missing",
        KINETIC,
        _remove_motion_carrier,
    ),
    CompilerRejectCase(
        "sliding-carrier-symbol-missing",
        KINETIC,
        _clear_quantity_symbol("velocityAx"),
    ),
    CompilerRejectCase(
        "sliding-carrier-impulse-dimension",
        IMPULSE_CARRIER_SOURCE,
        _set_impulse_velocity_carrier,
    ),
    CompilerRejectCase(
        "friction-follows-motion",
        KINETIC,
        _set_quantity_direction("frictionA", "x", 1),
    ),
    CompilerRejectCase(
        "normal-points-down",
        KINETIC,
        _set_quantity_direction("normalA", "y", -1),
    ),
    CompilerRejectCase(
        "table-tension-points-left",
        KINETIC,
        _set_quantity_direction("tensionA", "x", -1),
    ),
    CompilerRejectCase(
        "table-acceleration-points-left",
        KINETIC,
        _set_quantity_direction("accelerationAx", "x", -1),
    ),
    CompilerRejectCase(
        "tension-query-hanging-acceleration-up",
        TENSION_QUERY,
        _set_quantity_direction("accelerationBy", "y", 1),
    ),
    CompilerRejectCase(
        "inactive-regime-retains-friction-quantities",
        KINETIC,
        _set_inactive_with_active_quantities,
    ),
    CompilerRejectCase(
        "incomplete-massive-pulley-profile",
        KINETIC,
        _append_pulley_inertia,
    ),
    CompilerRejectCase(
        "client-authored-dynamic-equation",
        KINETIC,
        _append_client_equation,
    ),
)


@pytest.mark.parametrize(
    "case",
    COMPILER_REJECT_CASES,
    ids=lambda case: case.label,
)
def test_table_hanging_structural_contract_fails_closed_without_legacy(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized = _normalize(case.source, mutation=case.mutation)
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


@pytest.mark.parametrize(
    "source",
    (
        _source("inactive", mass_a_si=0.0),
        _source("inactive", mass_b_si=-1.0),
        _source("inactive", gravity_si=0.0),
        _source("inactive", gravity_si=-9.81),
        _source("sliding", coefficient=-0.1),
    ),
    ids=(
        "zero-table-mass",
        "negative-hanging-mass",
        "zero-gravity",
        "negative-gravity",
        "negative-friction-coefficient",
    ),
)
def test_table_hanging_invalid_domain_fails_closed_without_legacy(
    source: TableHangingSource,
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


def _declare_direction_ambiguity(payload: dict[str, object]) -> None:
    payload["ambiguities"] = [
        {
            "ambiguity_id": "tableDirectionAmbiguity",
            "kind": "direction",
            "referenced_ids": [
                "velocityAx",
                "frictionA",
                "accelerationAx",
                "accelerationBy",
                "queryB",
            ],
            "description": "The table motion, friction, or hanging direction is unresolved.",
            "blocking": True,
            "evidence_refs": ["motionEvidence", "queryEvidence"],
        }
    ]


def _mismatch_query_direction(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    target = query["target"]
    assert isinstance(target, dict)
    target["direction"] = _direction("y", 1)


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
        (
            _set_derived_numeric_value,
            APPROVED_ASSUMPTION_IDS,
            ValidationTerminal.invalid,
        ),
    ),
    ids=(
        "assumption-unapproved",
        "blocking-direction-ambiguity",
        "query-direction-mismatch",
        "derived-tension-smuggled-as-source",
    ),
)
def test_table_hanging_validation_gates_before_compile_and_legacy(
    mutation: PayloadMutation | None,
    approved_assumption_ids: tuple[str, ...],
    expected_terminal: ValidationTerminal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)

    normalized = _normalize(
        KINETIC,
        mutation=mutation,
        approved_assumption_ids=approved_assumption_ids,
    )

    assert normalized.terminal is expected_terminal
    assert normalized.accepted is False
    assert normalized.ir is None


def _direct_core_law_ids(
    ir: MechanicsProblemIRV1,
    approved_assumption_ids: tuple[str, ...] = APPROVED_ASSUMPTION_IDS,
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
    assert context is not None
    assert query_symbol_id == query_quantity.symbol_id
    return tuple(emission.rule.law_id for emission in apply_core_laws(context))


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            NO_FRICTION,
            Counter(
                {
                    "particle_weight": 2,
                    "particle_newton_second": 3,
                    "fixed_contact_no_penetration": 1,
                    "contact_normal_bound": 1,
                    "rope_massless_tension": 1,
                    "rope_fixed_pulley_motion": 1,
                }
            ),
        ),
        (
            KINETIC,
            Counter(
                {
                    "particle_weight": 2,
                    "particle_newton_second": 3,
                    "fixed_contact_no_penetration": 1,
                    "contact_normal_bound": 1,
                    "contact_sliding_friction": 1,
                    "rope_massless_tension": 1,
                    "rope_fixed_pulley_motion": 1,
                }
            ),
        ),
        (
            STATIC_HOLD,
            Counter(
                {
                    "particle_weight": 2,
                    "particle_newton_second": 3,
                    "fixed_contact_no_penetration": 1,
                    "contact_normal_bound": 1,
                    "contact_friction_bound": 2,
                    "contact_sticking_static_acceleration": 1,
                    "rope_massless_tension": 1,
                    "rope_fixed_pulley_motion": 1,
                }
            ),
        ),
    ),
    ids=("inactive", "sliding", "sticking"),
)
def test_table_hanging_core_emits_exact_regime_law_multiset(
    source: TableHangingSource,
    expected: Counter[str],
) -> None:
    ir = _build_ir(source)

    assert Counter(_direct_core_law_ids(ir)) == expected


def test_missing_ideal_authority_suppresses_rope_laws_and_compiler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ir = _build_ir(KINETIC)
    approved = tuple(
        assumption_id
        for assumption_id in APPROVED_ASSUMPTION_IDS
        if assumption_id != "idealPulley"
    )
    _forbid_legacy_call(monkeypatch)

    execution = _execute(ir, approved_assumption_ids=approved)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    law_counts = Counter(_direct_core_law_ids(ir, approved))
    assert law_counts["rope_massless_tension"] == 0
    assert law_counts["rope_fixed_pulley_motion"] == 0
