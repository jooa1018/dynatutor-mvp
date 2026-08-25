from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
from typing import Callable

import pytest

from engine.equation_generators.energy_momentum import (
    solve_energy_momentum_system,
)
from engine.mechanics.compiler import (
    CompilerIssueCode,
    CompilerStatus,
    MechanicsCompiler,
    authorize_validated_mechanics_ir,
)
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
)
from engine.mechanics.math_ast import (
    Add,
    DimensionVector,
    Divide,
    Equality,
    LiteralNode,
    Multiply,
    Power,
    Sqrt,
    SymbolRef,
)
from engine.mechanics.migration import (
    DifferentialStatus,
    LegacyCandidateScalar,
    LegacyDifferentialReport,
    LegacyObservation,
    LegacyTerminal,
    MechanicsMigrationProbeExecution,
    MigrationProbeTerminal,
    build_generic_result_invariance_signature,
    build_legacy_differential_report,
    execute_mechanics_ir_probe,
)
from engine.mechanics.normalization import NormalizationResult, normalize_draft
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.solver._audit import (
    CompletenessAuditStatus,
    audit_solve_plan,
)
from engine.mechanics.solver.backends import WorkerStatus, run_backend
from engine.mechanics.solver.planner import plan_equation_graph
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import ValidationTerminal
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
    render_canonical_si_unit,
)
from engine.models import CanonicalProblem, Quantity, SolverResult
from engine.physics_core.inertia import INERTIA_BETA
from engine.solvers.rolling.rolling_energy import PureRollingEnergySolver
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
from test_phase56_mechanics_incline_same_fixture_parity import (
    ACCELERATION,
    MASS,
    _axis_binding,
    _quantity,
    _symbol,
    _text_evidence,
)
from test_phase56_mechanics_solver_execution import _graph as _direct_solver_graph


ROLLING_INTERVAL_ID = "rollingInterval"
WORLD_FRAME_ID = "worldFrame"
BODY_ID = "rollingBody"
SURFACE_ID = "rollingIncline"
WORLD_ID = "world"
CENTER_POINT_ID = "massCenter"
CONTACT_POINT_ID = "contactPoint"

DIMENSIONLESS = DimensionVector.dimensionless()
LENGTH = DimensionVector(length=1)
SPEED = DimensionVector(length=1, time=-1)
ANGULAR_VELOCITY = DimensionVector(time=-1)
MOMENT_OF_INERTIA = DimensionVector(mass=1, length=2)

SHAPE_BETA = {
    "solid_sphere": 2.0 / 5.0,
    "hollow_sphere": 2.0 / 3.0,
    "solid_cylinder": 1.0 / 2.0,
    "disk": 1.0 / 2.0,
    "hoop": 1.0,
    "ring": 1.0,
}
SHAPE_LABEL = {
    "solid_sphere": "uniform solid sphere",
    "hollow_sphere": "thin hollow sphere",
    "solid_cylinder": "uniform solid cylinder",
    "disk": "uniform disk",
    "hoop": "thin hoop",
    "ring": "thin ring",
}
APPROVED_ASSUMPTION_IDS = ("shapeAuthority", "noEnergyLoss")


@dataclass(frozen=True)
class RawScalar:
    value: str
    unit: str


@dataclass(frozen=True)
class PureRollingSource:
    problem_text: str
    shape: str
    mass_si: float
    radius_si: float
    gravity_si: float
    height_si: float
    initial_speed_si: float
    mass_raw: RawScalar
    radius_raw: RawScalar
    gravity_raw: RawScalar
    height_raw: RawScalar
    initial_speed_raw: RawScalar | None

    def __post_init__(self) -> None:
        if self.shape not in SHAPE_BETA:
            raise ValueError("shape must be one exact supported rolling shape")
        for value, label in (
            (self.mass_si, "mass"),
            (self.radius_si, "radius"),
            (self.gravity_si, "gravity"),
            (self.height_si, "height"),
            (self.initial_speed_si, "initial speed"),
        ):
            if type(value) is not float or not math.isfinite(value):
                raise ValueError(f"{label} must be one finite float")

    @property
    def beta(self) -> float:
        return SHAPE_BETA[self.shape]

    @property
    def expected_inertia_si(self) -> float:
        return self.beta * self.mass_si * self.radius_si**2

    @property
    def expected_initial_omega_si(self) -> float:
        return self.initial_speed_si / self.radius_si

    @property
    def expected_final_speed_si(self) -> float:
        return math.sqrt(
            self.initial_speed_si**2
            + 2.0 * self.gravity_si * self.height_si / (1.0 + self.beta)
        )

    @property
    def expected_final_omega_si(self) -> float:
        return self.expected_final_speed_si / self.radius_si

    @property
    def starts_from_rest(self) -> bool:
        return self.initial_speed_raw is None


def _source(
    shape: str,
    *,
    mass_si: float = 2.0,
    radius_si: float = 0.3,
    gravity_si: float = 9.81,
    height_si: float = 1.2,
    initial_speed_si: float = 0.0,
    evidenced_rest: bool = True,
    raw_scalars: tuple[RawScalar, RawScalar, RawScalar, RawScalar, RawScalar]
    | None = None,
    paraphrase_prefix: str = "",
) -> PureRollingSource:
    if raw_scalars is None:
        raw_scalars = (
            RawScalar(f"{mass_si:g}", "kg"),
            RawScalar(f"{radius_si:g}", "m"),
            RawScalar(f"{gravity_si:g}", "m/s^2"),
            RawScalar(f"{height_si:g}", "m"),
            RawScalar(f"{initial_speed_si:g}", "m/s"),
        )
    mass_raw, radius_raw, gravity_raw, height_raw, supplied_initial_raw = raw_scalars
    if evidenced_rest:
        if initial_speed_si != 0.0:
            raise ValueError("an evidenced rest state requires zero initial speed")
        initial_speed_raw = None
        initial_sentence = "It starts from rest."
    else:
        initial_speed_raw = supplied_initial_raw
        initial_sentence = (
            "Its initial center-of-mass speed is "
            f"{initial_speed_raw.value} {initial_speed_raw.unit}."
        )
    shape_label = SHAPE_LABEL.get(shape, shape.replace("_", " "))
    problem_text = " ".join(
        (
            paraphrase_prefix,
            f"A {mass_raw.value} {mass_raw.unit} rolling body is a {shape_label}.",
            f"Its radius is {radius_raw.value} {radius_raw.unit}.",
            f"Take g = {gravity_raw.value} {gravity_raw.unit}.",
            f"It descends through a vertical height of {height_raw.value} {height_raw.unit}.",
            initial_sentence,
            "It rolls on one fixed surface without slipping throughout the motion.",
            "Use a fixed Cartesian x-y world frame.",
            "Mechanical energy is conserved and there are no dissipative losses.",
            "Find its final nonnegative center-of-mass speed.",
        )
    ).strip()
    return PureRollingSource(
        problem_text=problem_text,
        shape=shape,
        mass_si=float(mass_si),
        radius_si=float(radius_si),
        gravity_si=float(gravity_si),
        height_si=float(height_si),
        initial_speed_si=float(initial_speed_si),
        mass_raw=mass_raw,
        radius_raw=radius_raw,
        gravity_raw=gravity_raw,
        height_raw=height_raw,
        initial_speed_raw=initial_speed_raw,
    )


BASELINE = _source("solid_sphere")
SHAPE_CASES = tuple(_source(shape) for shape in SHAPE_BETA)
NONZERO_INITIAL_SPEED = _source(
    "disk",
    initial_speed_si=0.8,
    evidenced_rest=False,
)
ZERO_HEIGHT = _source("hoop", height_si=0.0)
UNIT_NORMALIZED = _source(
    "hollow_sphere",
    mass_si=2.0,
    radius_si=0.3,
    gravity_si=9.81,
    height_si=1.2,
    initial_speed_si=0.4,
    evidenced_rest=False,
    raw_scalars=(
        RawScalar("2000", "g"),
        RawScalar("30", "cm"),
        RawScalar("9.81", "m/s^2"),
        RawScalar("120", "cm"),
        RawScalar("0.4", "m/s"),
    ),
)
MASS_INVARIANT = _source("solid_sphere", mass_si=7.0)
RADIUS_INVARIANT = _source("solid_sphere", radius_si=0.8)
GH_INVARIANT = _source(
    "solid_sphere",
    gravity_si=4.905,
    height_si=2.4,
)
POSITIVE_CASES = (
    *SHAPE_CASES,
    NONZERO_INITIAL_SPEED,
    ZERO_HEIGHT,
    UNIT_NORMALIZED,
    MASS_INVARIANT,
    RADIUS_INVARIANT,
    GH_INVARIANT,
)


def _ref(symbol_id: str, dimension: DimensionVector) -> SymbolRef:
    return SymbolRef(symbol_id=symbol_id, dimension=dimension)


def _literal(value: float, dimension: DimensionVector) -> LiteralNode:
    return LiteralNode(value=value, dimension=dimension)


def _square(symbol_id: str, dimension: DimensionVector) -> Power:
    squared_dimension = dimension.plus(dimension)
    assert squared_dimension is not None
    return Power(
        base=_ref(symbol_id, dimension),
        exponent=_literal(2.0, DIMENSIONLESS),
        dimension=squared_dimension,
    )


def _shape_inertia_expression(beta: float) -> Equality:
    radius_squared = _square("R", LENGTH)
    return Equality(
        left=_ref("I", MOMENT_OF_INERTIA),
        right=Multiply(
            factors=(
                _literal(beta, DIMENSIONLESS),
                _ref("m", MASS),
                radius_squared,
            ),
            dimension=MOMENT_OF_INERTIA,
        ),
    )


def _no_slip_expression(speed_symbol: str, omega_symbol: str) -> Equality:
    return Equality(
        left=_ref(speed_symbol, SPEED),
        right=Multiply(
            factors=(
                _ref("R", LENGTH),
                _ref(omega_symbol, ANGULAR_VELOCITY),
            ),
            dimension=SPEED,
        ),
    )


def _principal_root_energy_expression() -> Equality:
    speed_squared = SPEED.plus(SPEED)
    assert speed_squared is not None
    radius_squared = _square("R", LENGTH)
    inertia_over_radius_squared = Divide(
        numerator=_ref("I", MOMENT_OF_INERTIA),
        denominator=radius_squared,
        dimension=MASS,
    )
    effective_mass = Add(
        terms=(_ref("m", MASS), inertia_over_radius_squared),
        dimension=MASS,
    )
    potential_drop = Multiply(
        factors=(
            _literal(2.0, DIMENSIONLESS),
            _ref("m", MASS),
            _ref("g", ACCELERATION),
            _ref("h", LENGTH),
        ),
        dimension=DimensionVector(mass=1, length=2, time=-2),
    )
    gained_speed_squared = Divide(
        numerator=potential_drop,
        denominator=effective_mass,
        dimension=speed_squared,
    )
    radicand = Add(
        terms=(_square("v0", SPEED), gained_speed_squared),
        dimension=speed_squared,
    )
    return Equality(
        left=_ref("vf", SPEED),
        right=Sqrt(operand=radicand, dimension=SPEED),
    )


PayloadMutation = Callable[[dict[str, object]], None]


def _draft_payload(source: PureRollingSource) -> dict[str, object]:
    shape_quote = (
        f"A {source.mass_raw.value} {source.mass_raw.unit} rolling body is a "
        f"{SHAPE_LABEL.get(source.shape, source.shape.replace('_', ' '))}."
    )
    radius_quote = (
        f"Its radius is {source.radius_raw.value} {source.radius_raw.unit}."
    )
    gravity_quote = (
        f"Take g = {source.gravity_raw.value} {source.gravity_raw.unit}."
    )
    height_quote = (
        "It descends through a vertical height of "
        f"{source.height_raw.value} {source.height_raw.unit}."
    )
    if source.initial_speed_raw is None:
        initial_quote = "It starts from rest."
        initial_token = None
    else:
        initial_quote = (
            "Its initial center-of-mass speed is "
            f"{source.initial_speed_raw.value} {source.initial_speed_raw.unit}."
        )
        initial_token = (
            f"{source.initial_speed_raw.value} {source.initial_speed_raw.unit}"
        )
    rolling_quote = (
        "It rolls on one fixed surface without slipping throughout the motion."
    )
    orientation_quote = "Use a fixed Cartesian x-y world frame."
    energy_quote = (
        "Mechanical energy is conserved and there are no dissipative losses."
    )
    query_quote = "Find its final nonnegative center-of-mass speed."
    evidence_specs = (
        (
            "shapeEvidence",
            shape_quote,
            f"{source.mass_raw.value} {source.mass_raw.unit}",
        ),
        (
            "radiusEvidence",
            radius_quote,
            f"{source.radius_raw.value} {source.radius_raw.unit}",
        ),
        (
            "gravityEvidence",
            gravity_quote,
            f"{source.gravity_raw.value} {source.gravity_raw.unit}",
        ),
        (
            "heightEvidence",
            height_quote,
            f"{source.height_raw.value} {source.height_raw.unit}",
        ),
        (
            "initialEvidence",
            initial_quote,
            initial_token,
        ),
        ("rollingEvidence", rolling_quote, None),
        ("orientationEvidence", orientation_quote, None),
        ("energyEvidence", energy_quote, None),
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
        _symbol(symbol_id, quantity_id, dimension)
        for symbol_id, quantity_id, dimension in (
            ("m", "mass", MASS),
            ("R", "radius", LENGTH),
            ("g", "gravity", ACCELERATION),
            ("h", "heightDrop", LENGTH),
            ("v0", "initialSpeed", SPEED),
            ("I", "shapeInertia", MOMENT_OF_INERTIA),
            ("omega0", "initialAngularSpeed", ANGULAR_VELOCITY),
            ("vf", "finalSpeed", SPEED),
            ("omegaf", "finalAngularSpeed", ANGULAR_VELOCITY),
        )
    ]
    quantities = [
        _quantity(
            "mass",
            "m",
            "mass",
            BODY_ID,
            MASS,
            provenance="explicit_source",
            evidence_refs=("shapeEvidence",),
            raw_value=source.mass_raw.value,
            raw_unit=source.mass_raw.unit,
        ),
        _quantity(
            "radius",
            "R",
            "radius",
            BODY_ID,
            LENGTH,
            provenance="explicit_source",
            evidence_refs=("radiusEvidence", "rollingEvidence"),
            raw_value=source.radius_raw.value,
            raw_unit=source.radius_raw.unit,
        ),
        _quantity(
            "gravity",
            "g",
            "gravity",
            WORLD_ID,
            ACCELERATION,
            provenance="explicit_source",
            evidence_refs=("gravityEvidence",),
            raw_value=source.gravity_raw.value,
            raw_unit=source.gravity_raw.unit,
        ),
        _quantity(
            "heightDrop",
            "h",
            "height",
            BODY_ID,
            LENGTH,
            provenance="explicit_source",
            evidence_refs=("heightEvidence",),
            raw_value=source.height_raw.value,
            raw_unit=source.height_raw.unit,
        ),
        _quantity(
            "initialSpeed",
            "v0",
            "speed",
            BODY_ID,
            SPEED,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="magnitude",
            provenance=(
                "inferred" if source.starts_from_rest else "explicit_source"
            ),
            evidence_refs=("initialEvidence", "rollingEvidence"),
            raw_value=(
                None
                if source.initial_speed_raw is None
                else source.initial_speed_raw.value
            ),
            raw_unit=(
                None
                if source.initial_speed_raw is None
                else source.initial_speed_raw.unit
            ),
        ),
        _quantity(
            "shapeInertia",
            "I",
            "moment_of_inertia",
            BODY_ID,
            MOMENT_OF_INERTIA,
            point_id=CENTER_POINT_ID,
            interval_id=ROLLING_INTERVAL_ID,
            provenance="inferred",
            evidence_refs=("shapeEvidence", "radiusEvidence"),
        ),
        _quantity(
            "initialAngularSpeed",
            "omega0",
            "angular_velocity",
            BODY_ID,
            ANGULAR_VELOCITY,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="clockwise",
            direction={"kind": "semantic", "direction": "clockwise"},
            provenance="inferred",
            evidence_refs=("initialEvidence", "radiusEvidence", "rollingEvidence"),
        ),
        _quantity(
            "finalSpeed",
            "vf",
            "speed",
            BODY_ID,
            SPEED,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="magnitude",
            provenance="inferred",
            evidence_refs=("heightEvidence", "rollingEvidence", "energyEvidence", "queryEvidence"),
        ),
        _quantity(
            "finalAngularSpeed",
            "omegaf",
            "angular_velocity",
            BODY_ID,
            ANGULAR_VELOCITY,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="clockwise",
            direction={"kind": "semantic", "direction": "clockwise"},
            provenance="inferred",
            evidence_refs=("radiusEvidence", "rollingEvidence", "queryEvidence"),
        ),
    ]
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnosticPureRollingLabel",
            "subtype": "diagnosticShapeEnergyLabel",
            "model_id": "sameFixturePureRollingTest",
            "source_text_sha256": hashlib.sha256(
                source.problem_text.encode("utf-8")
            ).hexdigest(),
        },
        "source_assets": [],
        "source_evidence": evidence,
        "entities": [
            {
                "entity_id": BODY_ID,
                "primitive": "rigid_body",
                "evidence_refs": [
                    "shapeEvidence",
                    "radiusEvidence",
                    "heightEvidence",
                    "initialEvidence",
                    "rollingEvidence",
                    "queryEvidence",
                ],
            },
            {
                "entity_id": SURFACE_ID,
                "primitive": "incline",
                "evidence_refs": ["rollingEvidence"],
            },
            {
                "entity_id": WORLD_ID,
                "primitive": "environment",
                "evidence_refs": ["gravityEvidence"],
            },
        ],
        "points": [
            {
                "point_id": CENTER_POINT_ID,
                "role": "mass_center",
                "owner_entity_id": BODY_ID,
                "frame_id": WORLD_FRAME_ID,
                "evidence_refs": [
                    "shapeEvidence",
                    "radiusEvidence",
                    "initialEvidence",
                    "queryEvidence",
                ],
            },
            {
                "point_id": CONTACT_POINT_ID,
                "role": "contact",
                "owner_entity_id": BODY_ID,
                "frame_id": WORLD_FRAME_ID,
                "evidence_refs": ["radiusEvidence", "rollingEvidence"],
            },
        ],
        "reference_frames": [
            {
                "frame_id": WORLD_FRAME_ID,
                "frame_type": "cartesian_2d",
                "origin": {"kind": "world"},
                "axes": [
                    _axis_binding("x", frame_id=WORLD_FRAME_ID),
                    _axis_binding("y", frame_id=WORLD_FRAME_ID),
                ],
                "evidence_refs": ["orientationEvidence"],
            }
        ],
        "motion_intervals": [
            {
                "interval_id": ROLLING_INTERVAL_ID,
                "order": 1,
                "subject_ids": [BODY_ID, SURFACE_ID, WORLD_ID],
                "frame_id": WORLD_FRAME_ID,
                "evidence_refs": [
                    "heightEvidence",
                    "initialEvidence",
                    "rollingEvidence",
                    "energyEvidence",
                    "orientationEvidence",
                ],
            }
        ],
        "events": [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": [
            {
                "relation_id": "bodyRadiusGeometry",
                "kind": "radius",
                "participant_ids": [BODY_ID, CENTER_POINT_ID, CONTACT_POINT_ID],
                "quantity_ids": ["radius"],
                "interval_id": ROLLING_INTERVAL_ID,
                "evidence_refs": ["radiusEvidence", "rollingEvidence"],
            },
            {
                "relation_id": "rollingContactGeometry",
                "kind": "lies_on",
                "participant_ids": [BODY_ID, SURFACE_ID, CONTACT_POINT_ID],
                "quantity_ids": [],
                "interval_id": ROLLING_INTERVAL_ID,
                "evidence_refs": ["rollingEvidence"],
            },
        ],
        "interactions": [
            {
                "interaction_id": "gravityInteraction",
                "kind": "gravity",
                "participant_ids": [BODY_ID, WORLD_ID],
                "frame_id": WORLD_FRAME_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": ["mass", "gravity", "heightDrop"],
                "evidence_refs": ["shapeEvidence", "gravityEvidence", "heightEvidence"],
            },
            {
                "interaction_id": "rollingContact",
                "kind": "contact",
                "participant_ids": [BODY_ID, SURFACE_ID],
                "point_ids": [CONTACT_POINT_ID],
                "frame_id": WORLD_FRAME_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": ["radius"],
                "evidence_refs": ["radiusEvidence", "rollingEvidence"],
            },
        ],
        "constraints": [],
        "state_conditions": [
            {
                "state_condition_id": "touchingState",
                "kind": "contact",
                "state": "touching",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": [],
                "evidence_refs": ["rollingEvidence"],
            },
            {
                "state_condition_id": "fixedInclineState",
                "kind": "motion",
                "state": "at_rest",
                "subject_id": SURFACE_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": [],
                "evidence_refs": ["rollingEvidence"],
            },
            {
                "state_condition_id": "initialState",
                "kind": "initial",
                "state": "at_rest" if source.starts_from_rest else "moving",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": ["initialSpeed"],
                "evidence_refs": ["initialEvidence", "rollingEvidence"],
            },
            {
                "state_condition_id": "finalRollingState",
                "kind": "final",
                "state": "rolling",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": ["finalSpeed", "finalAngularSpeed"],
                "evidence_refs": [
                    "heightEvidence",
                    "rollingEvidence",
                    "energyEvidence",
                    "queryEvidence",
                ],
            },
            {
                "state_condition_id": "pureRollingState",
                "kind": "rolling",
                "state": "no_slip",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": [
                    "radius",
                    "initialSpeed",
                    "initialAngularSpeed",
                    "finalSpeed",
                    "finalAngularSpeed",
                ],
                "evidence_refs": ["radiusEvidence", "rollingEvidence"],
            }
        ],
        "queries": [
            {
                "query_id": "queryTarget",
                "target": {
                    "role": "speed",
                    "subject_id": BODY_ID,
                    "point_id": CENTER_POINT_ID,
                    "frame_id": WORLD_FRAME_ID,
                    "interval_id": ROLLING_INTERVAL_ID,
                    "component": "magnitude",
                    "target_quantity_id": "finalSpeed",
                },
                "output_unit": "m/s",
                "output_dimension": SPEED.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": ["queryEvidence"],
            }
        ],
        "principle_hints": [],
        "assumptions": [
            {
                "assumption_id": "shapeAuthority",
                "kind": source.shape,
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "disposition": "approved",
                "reason": (
                    "The source explicitly identifies the rolling body's exact "
                    "shape; the server maps that closed shape kind to beta."
                ),
                "evidence_refs": ["shapeEvidence"],
            },
            {
                "assumption_id": "noEnergyLoss",
                "kind": "no_energy_loss",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "disposition": "approved",
                "reason": (
                    "The source explicitly states that mechanical energy is "
                    "conserved without dissipative losses."
                ),
                "evidence_refs": ["energyEvidence"],
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


def _normalize(
    source: PureRollingSource,
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


def _build_ir(source: PureRollingSource) -> MechanicsProblemIRV1:
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


@dataclass(frozen=True)
class PureRollingResiduals:
    shape_inertia: float
    initial_no_slip: float
    final_no_slip: float
    reduced_energy: float
    final_speed_si: float

    @property
    def passed(self) -> bool:
        return (
            all(
                abs(value) <= 1.0e-9
                for value in (
                    self.shape_inertia,
                    self.initial_no_slip,
                    self.final_no_slip,
                    self.reduced_energy,
                )
            )
            and self.final_speed_si >= -1.0e-12
        )


def _independent_residuals(
    source: PureRollingSource,
    values: dict[str, float],
) -> PureRollingResiduals:
    assert {"I", "omega0", "omegaf", "vf"}.issubset(values)
    return PureRollingResiduals(
        shape_inertia=(
            values["I"]
            - source.beta * source.mass_si * source.radius_si**2
        ),
        initial_no_slip=(
            source.initial_speed_si - source.radius_si * values["omega0"]
        ),
        final_no_slip=(
            values["vf"] - source.radius_si * values["omegaf"]
        ),
        reduced_energy=(
            (1.0 + source.beta)
            * (values["vf"] ** 2 - source.initial_speed_si**2)
            - 2.0 * source.gravity_si * source.height_si
        ),
        final_speed_si=values["vf"],
    )


def _legacy_problem(source: PureRollingSource) -> CanonicalProblem:
    knowns = {
        "m": Quantity("m", source.mass_si, "kg"),
        "R": Quantity("R", source.radius_si, "m"),
        "g": Quantity("g", source.gravity_si, "m/s^2"),
        "h": Quantity("h", source.height_si, "m"),
    }
    if not source.starts_from_rest:
        knowns["v0"] = Quantity("v0", source.initial_speed_si, "m/s")
    return CanonicalProblem(
        raw_text=source.problem_text,
        system_type="pure_rolling_energy",
        knowns=knowns,
        unknowns=["final_velocity"],
        requested_outputs=["final_velocity"],
        body_shape=source.shape,
        flags={
            "pure_rolling": True,
            "no_slip": True,
            "starts_from_rest": source.starts_from_rest,
        },
    )


def _observe_legacy(
    source: PureRollingSource,
) -> tuple[LegacyObservation, SolverResult]:
    problem = _legacy_problem(source)

    # The legacy rolling solver does not expose its pre-delivery value through
    # SolverResult.  Capture the exact raw v from the same legacy kernel and the
    # same CanonicalProblem, then require the direct solver's rounded delivery
    # to agree.  This is one principal-root candidate, never a fabricated +/-
    # multiset.
    generated = solve_energy_momentum_system(problem)
    assert generated.ok is True, generated.errors
    assert set(generated.solution) == {"v", "v0", "beta", "mode"}
    raw_v = generated.solution["v"]
    assert type(raw_v) is float and math.isfinite(raw_v) and raw_v >= 0.0
    assert generated.solution["mode"] == "shape"
    assert generated.solution["beta"] == pytest.approx(source.beta, abs=0.0)

    result = PureRollingEnergySolver().solve(problem)
    assert result.ok is True, result.unsupported_reason
    assert result.verification.passed is True
    assert result.answer is not None
    assert result.answer.symbolic is not None
    assert result.answer.numeric == pytest.approx(
        round(raw_v, 6), rel=0.0, abs=1.0e-12
    )
    speed_answer = next(item for item in result.answers if item.symbol == "v")
    assert speed_answer.numeric == pytest.approx(
        round(raw_v, 6), rel=0.0, abs=1.0e-12
    )
    omega_answers = tuple(item for item in result.answers if item.symbol == "omega")
    assert len(omega_answers) == 1
    assert omega_answers[0].numeric == pytest.approx(
        round(raw_v / source.radius_si, 6), rel=0.0, abs=1.0e-12
    )
    normalized = normalize_quantity("%r" % raw_v, "m/s", "scalar", SPEED)
    assert type(normalized.value) is float
    observation = LegacyObservation(
        case_id=(
            "pureRolling"
            + hashlib.sha256(source.problem_text.encode("utf-8")).hexdigest()[:32]
        ),
        diagnostic_kernel_id="pureRollingEnergyDirectV1",
        terminal=LegacyTerminal.solved,
        query_symbol_id="vf",
        si_unit=render_canonical_si_unit(SPEED),
        selected_scalar_si=normalized.value,
        complete_candidate_scalars_si=(
            LegacyCandidateScalar(value_si=normalized.value, multiplicity=1),
        ),
        residual_passed=math.isclose(
            raw_v,
            source.expected_final_speed_si,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
    )
    return observation, result


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport
    residuals: PureRollingResiduals


def _same_fixture(source: PureRollingSource) -> SameFixtureEvidence:
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
    frozen_signature = build_generic_result_invariance_signature(
        execution.solve_result
    )
    frozen_graph = execution.compiler_result.graph.fingerprint
    frozen_plan = execution.solve_result.plan.plan_fingerprint
    frozen_values = tuple(sorted(_candidate_values(execution).items()))
    residuals = _independent_residuals(source, _candidate_values(execution))
    assert residuals.passed is True

    observation, _ = _observe_legacy(source)
    report = build_legacy_differential_report(execution.solve_result, observation)
    assert build_generic_result_invariance_signature(
        execution.solve_result
    ) == frozen_signature
    assert execution.compiler_result.graph.fingerprint == frozen_graph
    assert execution.solve_result.plan.plan_fingerprint == frozen_plan
    assert tuple(sorted(_candidate_values(execution).items())) == frozen_values
    assert _independent_residuals(source, _candidate_values(execution)) == residuals
    return SameFixtureEvidence(
        registry_entry="pure_rolling_energy",
        ir=ir,
        execution=execution,
        observation=observation,
        report=report,
        residuals=residuals,
    )


def _forbid_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> SolverResult:
        raise AssertionError("a generic pure-rolling case must not call legacy")

    monkeypatch.setattr(PureRollingEnergySolver, "solve", forbidden)


def test_pure_rolling_exact_profile_compiles_fast_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    ir = _build_ir(BASELINE)
    result = MechanicsCompiler().compile(
        ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(ir),
        approved_assumption_ids=APPROVED_ASSUMPTION_IDS,
    )
    assert result.status is CompilerStatus.ready, result.issues
    assert result.graph is not None
    assert Counter(item.law_id for item in result.graph.equations) == Counter(
        {
            "state_at_rest": 1,
            "rolling_no_slip": 2,
            "pure_rolling_shape_inertia": 1,
            "pure_rolling_principal_energy": 1,
        }
    )


def test_exact_algebraic_completeness_never_certifies_nonreal_or_nonfull_rank_rhs(
) -> None:
    root_negative_one = Sqrt(
        operand=_literal(-1.0, DIMENSIONLESS),
        dimension=DIMENSIONLESS,
    )
    complex_plan = plan_equation_graph(
        _direct_solver_graph(
            (
                Equality(
                    left=_ref("x", DIMENSIONLESS),
                    right=root_negative_one,
                    dimension=DIMENSIONLESS,
                ),
            )
        )
    )
    assert complex_plan.primary_backend is SolveBackendKind.linear_symbolic
    assert audit_solve_plan(
        complex_plan, complex_plan.primary_backend
    ) == {"status": CompletenessAuditStatus.unsupported.value}
    complex_backend = run_backend(complex_plan, complex_plan.primary_backend)
    assert complex_backend["status"] == WorkerStatus.backend_failure.value
    assert complex_backend["complete"] is False
    assert complex_backend["roots"] == []
    assert complex_backend["certificate"] is None

    unknown_root_plan = plan_equation_graph(
        _direct_solver_graph(
            (
                Equality(
                    left=_ref("x", DIMENSIONLESS),
                    right=Sqrt(
                        operand=_ref("x", DIMENSIONLESS),
                        dimension=DIMENSIONLESS,
                    ),
                    dimension=DIMENSIONLESS,
                ),
            )
        )
    )
    assert unknown_root_plan.primary_backend is SolveBackendKind.nonlinear_symbolic

    root_two = Sqrt(
        operand=_literal(2.0, DIMENSIONLESS),
        dimension=DIMENSIONLESS,
    )
    rectangular_equation = Equality(
        left=_ref("x", DIMENSIONLESS),
        right=root_two,
        dimension=DIMENSIONLESS,
    )
    rectangular_plan = plan_equation_graph(
        _direct_solver_graph((rectangular_equation, rectangular_equation))
    )
    assert rectangular_plan.primary_backend is SolveBackendKind.linear_symbolic
    assert audit_solve_plan(
        rectangular_plan, rectangular_plan.primary_backend
    ) == {"status": CompletenessAuditStatus.unsupported.value}

    inconsistent_rectangular_plan = plan_equation_graph(
        _direct_solver_graph(
            (
                rectangular_equation,
                Equality(
                    left=_ref("x", DIMENSIONLESS),
                    right=Sqrt(
                        operand=_literal(3.0, DIMENSIONLESS),
                        dimension=DIMENSIONLESS,
                    ),
                    dimension=DIMENSIONLESS,
                ),
            )
        )
    )
    assert (
        inconsistent_rectangular_plan.primary_backend
        is SolveBackendKind.linear_symbolic
    )
    assert audit_solve_plan(
        inconsistent_rectangular_plan,
        inconsistent_rectangular_plan.primary_backend,
    ) == {"status": CompletenessAuditStatus.unsupported.value}

    rank_deficient_equation = Equality(
        left=Add(
            terms=(
                _ref("x", DIMENSIONLESS),
                _ref("y", DIMENSIONLESS),
            ),
            dimension=DIMENSIONLESS,
        ),
        right=root_two,
        dimension=DIMENSIONLESS,
    )
    rank_deficient_plan = plan_equation_graph(
        _direct_solver_graph(
            (rank_deficient_equation, rank_deficient_equation),
            unknown_ids=("x", "y"),
        )
    )
    assert rank_deficient_plan.primary_backend is SolveBackendKind.linear_symbolic
    assert audit_solve_plan(
        rank_deficient_plan, rank_deficient_plan.primary_backend
    ) == {"status": CompletenessAuditStatus.unsupported.value}


@pytest.mark.slow
@pytest.mark.parametrize(
    "source",
    POSITIVE_CASES,
    ids=(
        "solid-sphere-beta-two-fifths",
        "hollow-sphere-beta-two-thirds",
        "solid-cylinder-beta-one-half",
        "disk-beta-one-half",
        "hoop-beta-one",
        "ring-beta-one",
        "nonzero-initial-speed",
        "zero-height-drop",
        "mixed-source-unit-normalization",
        "mass-invariance",
        "radius-invariance",
        "gravity-height-product-invariance",
    ),
)
def test_pure_rolling_same_fixture_full_parity(
    source: PureRollingSource,
) -> None:
    evidence = _same_fixture(source)
    compiler = evidence.execution.compiler_result
    result = evidence.execution.solve_result
    assert evidence.registry_entry == "pure_rolling_energy"
    assert compiler is not None and compiler.graph is not None
    assert evidence.execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert evidence.execution.solve_terminal is MechanicsSolveTerminal.solved

    graph = compiler.graph
    expected_laws = Counter(
        {
            "rolling_no_slip": 2,
            "pure_rolling_shape_inertia": 1,
            "pure_rolling_principal_energy": 1,
        }
    )
    if source.starts_from_rest:
        expected_laws["state_at_rest"] = 1
    assert Counter(item.law_id for item in graph.equations) == expected_laws
    assert evidence.ir.constraints == ()

    equations_by_law = {
        law_id: tuple(item for item in graph.equations if item.law_id == law_id)
        for law_id in expected_laws
    }
    shape_equation = equations_by_law["pure_rolling_shape_inertia"]
    assert len(shape_equation) == 1
    assert shape_equation[0].assumption_ids == ("shapeAuthority",)
    assert shape_equation[0].constraint_ids == ("bodyRadiusGeometry",)
    assert set(shape_equation[0].source_quantity_ids) == {
        "mass",
        "radius",
        "shapeInertia",
    }
    no_slip_equations = equations_by_law["rolling_no_slip"]
    assert len(no_slip_equations) == 2
    assert {
        frozenset(item.source_quantity_ids) for item in no_slip_equations
    } == {
        frozenset(("radius", "initialSpeed", "initialAngularSpeed")),
        frozenset(("radius", "finalSpeed", "finalAngularSpeed")),
    }
    assert all(
        {
            "bodyRadiusGeometry",
            "pureRollingState",
            "touchingState",
            "fixedInclineState",
        }.issubset(item.constraint_ids)
        for item in no_slip_equations
    )
    principal_energy = equations_by_law["pure_rolling_principal_energy"]
    assert len(principal_energy) == 1
    assert principal_energy[0].assumption_ids == (
        "noEnergyLoss",
        "shapeAuthority",
    )
    assert {
        "initialState",
        "finalRollingState",
        "pureRollingState",
        "touchingState",
        "fixedInclineState",
        "bodyRadiusGeometry",
        "rollingContactGeometry",
    }.issubset(principal_energy[0].constraint_ids)
    assert set(principal_energy[0].source_quantity_ids) == {
        "initialSpeed",
        "finalSpeed",
        "gravity",
        "heightDrop",
    }
    assert result.plan.primary_backend in {
        SolveBackendKind.linear_symbolic,
        SolveBackendKind.nonlinear_symbolic,
    }
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert result.candidate_set.generation_complete is True
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    assert candidate.query_symbol_id == "vf"
    assert candidate.root_multiplicity == 1
    assert candidate.query_value_si >= 0.0
    assert candidate.query_value_si == pytest.approx(
        source.expected_final_speed_si, rel=0.0, abs=1.0e-9
    )
    assert candidate.query_value_si == pytest.approx(
        evidence.observation.selected_scalar_si, rel=0.0, abs=1.0e-9
    )
    values = _candidate_values(evidence.execution)
    assert values["I"] == pytest.approx(source.expected_inertia_si, abs=1.0e-9)
    assert values["omega0"] == pytest.approx(
        source.expected_initial_omega_si, abs=1.0e-9
    )
    assert values["vf"] == pytest.approx(
        source.expected_final_speed_si, abs=1.0e-9
    )
    assert values["omegaf"] == pytest.approx(
        source.expected_final_omega_si, abs=1.0e-9
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
    assert residual_checks[0].measured_error == pytest.approx(0.0, abs=1.0e-9)
    assert evidence.residuals.passed is True
    assert evidence.observation.residual_passed is True
    assert evidence.report.status is DifferentialStatus.full_parity
    assert evidence.report.discrepancies == ()
    assert evidence.report.observation_terminal is LegacyTerminal.solved
    assert evidence.report.generic_terminal is MechanicsSolveTerminal.solved

    if source is ZERO_HEIGHT:
        assert values["vf"] == pytest.approx(0.0, abs=1.0e-12)
        assert values["omegaf"] == pytest.approx(0.0, abs=1.0e-12)
    if source is UNIT_NORMALIZED:
        known_by_id = {item.quantity_id: item for item in evidence.ir.quantities}
        assert known_by_id["mass"].si_value == pytest.approx(2.0)
        assert known_by_id["radius"].si_value == pytest.approx(0.3)
        assert known_by_id["gravity"].si_value == pytest.approx(9.81)
        assert known_by_id["heightDrop"].si_value == pytest.approx(1.2)
        assert known_by_id["initialSpeed"].si_value == pytest.approx(0.4)
    if source in {MASS_INVARIANT, RADIUS_INVARIANT, GH_INVARIANT}:
        assert values["vf"] == pytest.approx(
            BASELINE.expected_final_speed_si,
            rel=0.0,
            abs=1.0e-9,
        )
    if source is MASS_INVARIANT:
        assert values["I"] != pytest.approx(BASELINE.expected_inertia_si)
    if source is RADIUS_INVARIANT:
        assert values["I"] != pytest.approx(BASELINE.expected_inertia_si)
        assert values["omegaf"] != pytest.approx(
            BASELINE.expected_final_omega_si
        )


def _record(
    payload: dict[str, object],
    collection_name: str,
    id_field: str,
    record_id: str,
) -> dict[str, object]:
    collection = payload[collection_name]
    assert isinstance(collection, list)
    return next(item for item in collection if item[id_field] == record_id)


def _remove_record(
    collection_name: str,
    id_field: str,
    record_id: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        collection = payload[collection_name]
        assert isinstance(collection, list)
        payload[collection_name] = [
            item for item in collection if item[id_field] != record_id
        ]

    return mutate


def _set_field(
    collection_name: str,
    id_field: str,
    record_id: str,
    field_name: str,
    value: object,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(payload, collection_name, id_field, record_id)[field_name] = value

    return mutate


def _compose(*mutations: PayloadMutation) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        for mutation in mutations:
            mutation(payload)

    return mutate


def _append_event(payload: dict[str, object]) -> None:
    events = payload["events"]
    assert isinstance(events, list)
    events.append(
        {
            "event_id": "decoyEvent",
            "kind": "other",
            "subject_ids": [BODY_ID],
            "interval_ids": [],
            "evidence_refs": ["rollingEvidence"],
        }
    )


def _append_decoy_quantity(payload: dict[str, object]) -> None:
    symbols = payload["symbols"]
    quantities = payload["quantities"]
    assert isinstance(symbols, list) and isinstance(quantities, list)
    symbols.append(_symbol("decoySpeedSymbol", "decoySpeed", SPEED))
    quantities.append(
        _quantity(
            "decoySpeed",
            "decoySpeedSymbol",
            "speed",
            BODY_ID,
            SPEED,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="magnitude",
            evidence_refs=("queryEvidence",),
        )
    )


def _append_client_equation(payload: dict[str, object]) -> None:
    constraints = payload["constraints"]
    assert isinstance(constraints, list)
    constraints.append(
        {
            "constraint_id": "clientShapeInertiaContamination",
            "kind": "constitutive",
            "expression": _shape_inertia_expression(
                SHAPE_BETA["solid_sphere"]
            ).model_dump(mode="json"),
            "subject_ids": [BODY_ID],
            "interval_id": ROLLING_INTERVAL_ID,
            "evidence_refs": ["shapeEvidence", "radiusEvidence"],
        }
    )


@dataclass(frozen=True)
class CompilerRejectCase:
    label: str
    mutation: PayloadMutation


COMPILER_REJECT_CASES = (
    CompilerRejectCase(
        "incline-primitive-erased",
        _set_field("entities", "entity_id", SURFACE_ID, "primitive", "surface"),
    ),
    CompilerRejectCase(
        "point-roles-erased",
        _compose(
            _set_field("points", "point_id", CENTER_POINT_ID, "role", "material"),
            _set_field("points", "point_id", CONTACT_POINT_ID, "role", "material"),
        ),
    ),
    CompilerRejectCase(
        "world-frame-is-not-cartesian-2d",
        _set_field(
            "reference_frames",
            "frame_id",
            WORLD_FRAME_ID,
            "frame_type",
            "body_fixed",
        ),
    ),
    CompilerRejectCase("event-contamination", _append_event),
    CompilerRejectCase(
        "radius-and-contact-topology-deleted",
        _compose(
            _remove_record("geometry", "relation_id", "bodyRadiusGeometry"),
            _remove_record("geometry", "relation_id", "rollingContactGeometry"),
        ),
    ),
    CompilerRejectCase(
        "gravity-and-contact-interactions-incomplete",
        _compose(
            _remove_record("interactions", "interaction_id", "gravityInteraction"),
            _set_field(
                "interactions",
                "interaction_id",
                "rollingContact",
                "point_ids",
                [],
            ),
        ),
    ),
    CompilerRejectCase(
        "touching-and-fixed-incline-states-contradict",
        _compose(
            _set_field(
                "state_conditions",
                "state_condition_id",
                "touchingState",
                "state",
                "separated",
            ),
            _set_field(
                "state_conditions",
                "state_condition_id",
                "fixedInclineState",
                "state",
                "moving",
            ),
        ),
    ),
    CompilerRejectCase(
        "initial-state-deleted",
        _remove_record("state_conditions", "state_condition_id", "initialState"),
    ),
    CompilerRejectCase(
        "final-state-deleted",
        _remove_record(
            "state_conditions", "state_condition_id", "finalRollingState"
        ),
    ),
    CompilerRejectCase(
        "no-slip-carrier-deleted",
        _remove_record(
            "state_conditions", "state_condition_id", "pureRollingState"
        ),
    ),
    CompilerRejectCase(
        "shape-and-loss-evidence-erased",
        _compose(
            _set_field(
                "assumptions",
                "assumption_id",
                "shapeAuthority",
                "evidence_refs",
                [],
            ),
            _set_field(
                "assumptions",
                "assumption_id",
                "noEnergyLoss",
                "evidence_refs",
                [],
            ),
        ),
    ),
    CompilerRejectCase(
        "shape-assumption-deleted",
        _remove_record("assumptions", "assumption_id", "shapeAuthority"),
    ),
    CompilerRejectCase(
        "loss-assumption-deleted",
        _remove_record("assumptions", "assumption_id", "noEnergyLoss"),
    ),
    CompilerRejectCase("extra-quantity-authority", _append_decoy_quantity),
    CompilerRejectCase("client-equation-contamination", _append_client_equation),
    CompilerRejectCase(
        "derived-scope-and-rotation-direction-corrupted",
        _compose(
            _set_field(
                "quantities",
                "quantity_id",
                "shapeInertia",
                "point_id",
                CONTACT_POINT_ID,
            ),
            _set_field(
                "quantities",
                "quantity_id",
                "initialAngularSpeed",
                "direction",
                {"kind": "semantic", "direction": "counterclockwise"},
            ),
        ),
    ),
)


def test_pure_rolling_source_quantity_evidence_deletion_stops_in_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(
        BASELINE,
        mutation=_set_field(
            "quantities", "quantity_id", "radius", "evidence_refs", []
        ),
    )
    assert normalization.terminal is ValidationTerminal.invalid
    assert normalization.ir is None


@pytest.mark.parametrize("case", COMPILER_REJECT_CASES, ids=lambda case: case.label)
def test_pure_rolling_exact_contract_mismatches_are_precisely_unsupported(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=case.mutation)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


INVALID_DOMAIN_CASES = (
    _source("solid_sphere", mass_si=0.0),
    _source("solid_sphere", radius_si=0.0),
    _source("solid_sphere", gravity_si=0.0),
    _source("solid_sphere", height_si=-0.1),
    _source(
        "solid_sphere",
        initial_speed_si=-0.1,
        evidenced_rest=False,
    ),
)


@pytest.mark.parametrize(
    "source",
    INVALID_DOMAIN_CASES,
    ids=(
        "zero-mass",
        "zero-radius",
        "zero-gravity",
        "negative-height-drop",
        "negative-source-initial-speed",
    ),
)
def test_pure_rolling_invalid_numeric_domain_fails_without_legacy(
    source: PureRollingSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.invalid
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.invalid_domain
        for issue in execution.compiler_result.issues
    )


def test_pure_rolling_source_inertia_is_reserved_for_entry9_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    payload = _build_ir(BASELINE).model_dump(mode="python", warnings="none")
    inertia = next(
        item
        for item in payload["quantities"]
        if item["quantity_id"] == "shapeInertia"
    )
    inertia.update(
        {
            "provenance": "explicit_source",
            "raw_value": "0.072",
            "raw_unit": "kg*m^2",
            "si_value": 0.072,
            "si_unit": "kg*m^2",
        }
    )
    contaminated = MechanicsProblemIRV1.model_validate(payload)
    execution = _execute(contaminated)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


@pytest.mark.parametrize("omitted_id", APPROVED_ASSUMPTION_IDS)
def test_pure_rolling_unapproved_assumption_stops_at_confirmation(
    omitted_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(
        BASELINE,
        approved_assumption_ids=tuple(
            item for item in APPROVED_ASSUMPTION_IDS if item != omitted_id
        ),
    )
    assert normalization.terminal is ValidationTerminal.needs_confirmation
    assert normalization.ir is None


def _query_quantity(
    payload: dict[str, object],
    quantity_id: str,
    *,
    output_unit: str,
    shape: str = "scalar",
) -> None:
    quantity = _record(payload, "quantities", "quantity_id", quantity_id)
    query = _record(payload, "queries", "query_id", "queryTarget")
    query["target"] = {
        "role": quantity["role"],
        "subject_id": quantity["subject_id"],
        "point_id": quantity.get("point_id"),
        "frame_id": quantity.get("frame_id"),
        "interval_id": quantity.get("interval_id"),
        "component": quantity.get("component", "unspecified"),
        "direction": quantity.get("direction"),
        "target_quantity_id": quantity_id,
    }
    query["output_unit"] = output_unit
    query["output_dimension"] = quantity["dimension"]
    query["shape"] = shape


def _query_target(quantity_id: str, output_unit: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _query_quantity(payload, quantity_id, output_unit=output_unit)

    return mutate


def _unbind_query(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryTarget")
    target = query["target"]
    assert isinstance(target, dict)
    target["target_quantity_id"] = None


UNSUPPORTED_QUERY_CASES = (
    CompilerRejectCase(
        "initial-speed-query",
        _query_target("initialSpeed", "m/s"),
    ),
    CompilerRejectCase(
        "final-angular-speed-query",
        _query_target("finalAngularSpeed", "rad/s"),
    ),
    CompilerRejectCase(
        "derived-inertia-query",
        _query_target("shapeInertia", "kg*m^2"),
    ),
    CompilerRejectCase(
        "source-radius-query",
        _query_target("radius", "m"),
    ),
    CompilerRejectCase(
        "source-mass-query",
        _query_target("mass", "kg"),
    ),
)


@pytest.mark.parametrize(
    "case", UNSUPPORTED_QUERY_CASES, ids=lambda case: case.label
)
def test_pure_rolling_internal_or_unbound_queries_are_unsupported(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=case.mutation)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def test_pure_rolling_unbound_ambiguous_query_is_invalid_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=_unbind_query)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.invalid
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.unresolved_query
        for issue in execution.compiler_result.issues
    )


QUERY_INDEPENDENT_DELETION_CASES = (
    CompilerRejectCase(
        "inertia-query-plus-radius-relation-deletion",
        _compose(
            _query_target("shapeInertia", "kg*m^2"),
            _remove_record("geometry", "relation_id", "bodyRadiusGeometry"),
        ),
    ),
    CompilerRejectCase(
        "mass-query-plus-shape-authority-deletion",
        _compose(
            _query_target("mass", "kg"),
            _remove_record("assumptions", "assumption_id", "shapeAuthority"),
        ),
    ),
    CompilerRejectCase(
        "angular-query-plus-no-slip-deletion",
        _compose(
            _query_target("finalAngularSpeed", "rad/s"),
            _remove_record(
                "state_conditions", "state_condition_id", "pureRollingState"
            ),
        ),
    ),
)


@pytest.mark.parametrize(
    "case", QUERY_INDEPENDENT_DELETION_CASES, ids=lambda case: case.label
)
def test_pure_rolling_recognizer_resists_query_and_candidate_deletion(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=case.mutation)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def _compile(ir: MechanicsProblemIRV1, approved: tuple[str, ...]):
    return MechanicsCompiler().compile(
        ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(ir),
        approved_assumption_ids=approved,
    )


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
        metadata["model_id"] = None
        metadata["source_text_sha256"] = None
    else:
        metadata["system_type"] = "wrongDiagnosticFamily"
        metadata["subtype"] = "wrongDiagnosticSubtype"
        metadata["model_id"] = "wrongDiagnosticModel"
        metadata["source_text_sha256"] = hashlib.sha256(
            b"unrelated and deliberately misleading rolling wording"
        ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


def test_entry8_metadata_raw_paraphrase_and_record_order_are_not_authority() -> None:
    original_ir = _build_ir(BASELINE)
    original = _compile(original_ir, APPROVED_ASSUMPTION_IDS)
    assert original.status is CompilerStatus.ready
    assert original.graph is not None

    reordered_payload = original_ir.model_dump(mode="python", warnings="none")
    for collection_name in (
        "source_evidence",
        "entities",
        "points",
        "reference_frames",
        "symbols",
        "quantities",
        "geometry",
        "interactions",
        "state_conditions",
        "assumptions",
    ):
        reordered_payload[collection_name] = list(
            reversed(reordered_payload[collection_name])
        )
    reordered_ir = MechanicsProblemIRV1.model_validate(reordered_payload)
    paraphrased_ir = _build_ir(
        _source(
            "solid_sphere",
            paraphrase_prefix=(
                "A diagnostic answer key falsely says v = 999 m/s; ignore it."
            ),
        )
    )
    variants = (
        _diagnostic_variant(original_ir, remove=False),
        _diagnostic_variant(original_ir, remove=True),
        reordered_ir,
        paraphrased_ir,
    )
    for variant in variants:
        compiled = _compile(variant, APPROVED_ASSUMPTION_IDS)
        assert compiled.status is CompilerStatus.ready, compiled.issues
        assert compiled.graph is not None
        assert compiled.graph.fingerprint == original.graph.fingerprint
        assert compiled.graph.selected_equation_ids == original.graph.selected_equation_ids
        assert Counter(item.law_id for item in compiled.graph.equations) == Counter(
            item.law_id for item in original.graph.equations
        )


def test_entry8_consistent_identifier_rename_preserves_graph() -> None:
    original_ir = _build_ir(BASELINE)
    original = _compile(original_ir, APPROVED_ASSUMPTION_IDS)
    payload = original_ir.model_dump(mode="python", warnings="none")
    identifiers = sorted(_collect_fixture_identifiers(payload))
    mapping = {
        identifier: f"renamedPureRollingIdentifier{index}"
        for index, identifier in enumerate(identifiers, start=1)
    }
    renamed_payload = _rename_fixture_identifiers(payload, mapping)
    assert isinstance(renamed_payload, dict)
    renamed_ir = MechanicsProblemIRV1.model_validate(renamed_payload)
    renamed = _compile(
        renamed_ir,
        tuple(mapping[item] for item in APPROVED_ASSUMPTION_IDS),
    )

    assert original.status is renamed.status is CompilerStatus.ready
    assert original.graph is not None and renamed.graph is not None
    assert original.graph.fingerprint == renamed.graph.fingerprint
    assert original.graph.selected_equation_ids == renamed.graph.selected_equation_ids
    assert Counter(item.law_id for item in original.graph.equations) == Counter(
        item.law_id for item in renamed.graph.equations
    )


@pytest.mark.parametrize(
    "left_shape,right_shape",
    (("solid_cylinder", "disk"), ("hoop", "ring")),
    ids=("cylinder-disk", "hoop-ring"),
)
def test_entry8_shape_aliases_emit_the_same_beta_graph(
    left_shape: str,
    right_shape: str,
) -> None:
    left_source = _source(left_shape)
    right_source = _source(right_shape)
    left = _compile(_build_ir(left_source), APPROVED_ASSUMPTION_IDS)
    right = _compile(_build_ir(right_source), APPROVED_ASSUMPTION_IDS)
    assert left.status is right.status is CompilerStatus.ready
    assert left.graph is not None and right.graph is not None
    assert left_source.beta == right_source.beta
    assert left_source.expected_final_speed_si == pytest.approx(
        right_source.expected_final_speed_si,
        rel=0.0,
        abs=1.0e-12,
    )
    assert left.graph.fingerprint != right.graph.fingerprint
    assert Counter(item.law_id for item in left.graph.equations) == Counter(
        item.law_id for item in right.graph.equations
    )
    left_semantics = tuple(
        sorted(
            (
                item.law_id,
                repr(item.expression.model_dump(mode="json")),
            )
            for item in left.graph.equations
        )
    )
    right_semantics = tuple(
        sorted(
            (
                item.law_id,
                repr(item.expression.model_dump(mode="json")),
            )
            for item in right.graph.equations
        )
    )
    assert left_semantics == right_semantics
