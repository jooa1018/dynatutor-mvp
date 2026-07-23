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
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
)
from engine.mechanics.math_ast import DimensionVector, Equality, SymbolRef
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
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import ValidationTerminal
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
    render_canonical_si_unit,
)
from engine.models import CanonicalProblem, Quantity, SolverResult
from engine.solvers.pulley.massive_pulley import MassivePulleyAtwoodSolver
from test_phase56_mechanics_atwood_same_fixture_parity import (
    BASELINE as IDEAL_ATWOOD_BASELINE,
)
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
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


WORLD_FRAME_ID = "worldFrame"
INTERVAL_ID = "motionInterval"
LEFT_RIM_POINT_ID = "leftRim"
RIGHT_RIM_POINT_ID = "rightRim"
LENGTH = DimensionVector(length=1)
MOMENT_OF_INERTIA = DimensionVector(mass=1, length=2)
ANGULAR_ACCELERATION = DimensionVector(time=-2)
APPROVED_ASSUMPTION_IDS = (
    "fixedPulley",
    "frictionlessAxle",
    "inextensibleRope",
    "masslessRope",
)


@dataclass(frozen=True)
class MassivePulleySource:
    problem_text: str
    mass_a_si: float
    mass_b_si: float
    gravity_si: float
    inertia_si: float
    radius_si: float
    query_role: str
    query_body: str
    query_direction_sign: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.mass_a_si, "mass A"),
            (self.mass_b_si, "mass B"),
            (self.gravity_si, "gravity"),
            (self.inertia_si, "pulley inertia"),
            (self.radius_si, "pulley radius"),
        ):
            if type(value) is not float or not math.isfinite(value):
                raise ValueError(f"{label} must be one finite float")
        if self.query_role not in {
            "acceleration",
            "tension",
            "angular_acceleration",
        }:
            raise ValueError("unsupported focused query role")
        if self.query_direction_sign not in {-1, 1}:
            raise ValueError("query direction must be one exact axis sign")
        if self.query_role == "angular_acceleration":
            if self.query_body != "pulley":
                raise ValueError("angular acceleration belongs to the pulley")
        elif self.query_body not in {"bodyA", "bodyB"}:
            raise ValueError("particle query body must be A or B")
        if self.query_role == "tension" and self.query_direction_sign != -1:
            raise ValueError("local particle tensions point upward in the world frame")

    @property
    def expected_acceleration_si(self) -> float:
        """Signed rope coordinate: positive means right mass B descends."""

        return (
            (self.mass_b_si - self.mass_a_si)
            * self.gravity_si
            / (
                self.mass_a_si
                + self.mass_b_si
                + self.inertia_si / self.radius_si**2
            )
        )

    @property
    def expected_alpha_si(self) -> float:
        return self.expected_acceleration_si / self.radius_si

    @property
    def expected_tension_a_si(self) -> float:
        return self.mass_a_si * (
            self.gravity_si + self.expected_acceleration_si
        )

    @property
    def expected_tension_b_si(self) -> float:
        return self.mass_b_si * (
            self.gravity_si - self.expected_acceleration_si
        )

    @property
    def natural_motion_sign(self) -> int:
        return 1 if self.mass_b_si >= self.mass_a_si else -1

    @property
    def acceleration_a_sign(self) -> int:
        return -1

    @property
    def acceleration_b_sign(self) -> int:
        return 1

    @property
    def alpha_sign(self) -> int:
        return 1

    @property
    def query_symbol_id(self) -> str:
        if self.query_role == "tension":
            return "tA" if self.query_body == "bodyA" else "tB"
        if self.query_role == "angular_acceleration":
            return "alpha"
        return "aA" if self.query_body == "bodyA" else "aB"

    @property
    def expected_query_value_si(self) -> float:
        if self.query_role == "tension":
            return (
                self.expected_tension_a_si
                if self.query_body == "bodyA"
                else self.expected_tension_b_si
            )
        if self.query_role == "angular_acceleration":
            return self.expected_alpha_si
        return self.expected_acceleration_si


def _source(
    mass_a_si: float,
    mass_b_si: float,
    *,
    gravity_si: float = 9.81,
    inertia_si: float = 0.12,
    radius_si: float = 0.3,
    query_role: str = "acceleration",
    query_body: str = "bodyB",
    query_direction_sign: int | None = None,
    paraphrase_prefix: str = "",
) -> MassivePulleySource:
    signed_acceleration = (
        (mass_b_si - mass_a_si)
        * gravity_si
        / (mass_a_si + mass_b_si + inertia_si / radius_si**2)
        if radius_si != 0.0
        else 0.0
    )
    natural_sign = 1 if signed_acceleration >= 0.0 else -1
    if query_direction_sign is None:
        if query_role == "tension":
            query_sign = -1
        elif query_role == "angular_acceleration":
            query_sign = 1
        elif query_body == "bodyA":
            query_sign = -1
        else:
            query_sign = 1
    else:
        query_sign = query_direction_sign
    if query_role == "tension":
        query_sentence = (
            f"Find the tension acting upward on mass {'A' if query_body == 'bodyA' else 'B'}."
        )
    elif query_role == "angular_acceleration":
        query_sentence = (
            "Find the signed angular acceleration of the pulley along the "
            f"{'positive' if query_sign == 1 else 'negative'} z direction."
        )
    else:
        query_sentence = (
            f"Find the signed acceleration of mass {'A' if query_body == 'bodyA' else 'B'} "
            f"along the {'downward' if query_sign == 1 else 'upward'} direction."
        )
    problem_text = " ".join(
        (
            paraphrase_prefix,
            f"Mass A is {mass_a_si:g} kg and hangs on the left.",
            f"Mass B is {mass_b_si:g} kg and hangs on the right.",
            f"Take g = {gravity_si:g} m/s^2.",
            f"The pulley moment of inertia about its center is {inertia_si:g} kg*m^2.",
            f"The left pulley rim radius is {radius_si:g} m.",
            f"The right pulley rim radius is {radius_si:g} m.",
            "The left and right rim points lie from the center along the -x and +x axes, respectively.",
            "The particles are joined by one massless, inextensible rope.",
            "The rope is taut.",
            "The rope wraps around the massive pulley.",
            "The rope is attached to mass A on the left side.",
            "The rope is attached to mass B on the right side.",
            "The pulley center is fixed while the pulley remains free to rotate.",
            "The axle is frictionless and exerts no other torque on the pulley.",
            "The rope does not slip on the pulley rim.",
            "The world frame is Cartesian 3-D; +y points downward and +z is the positive rotation when the right mass descends.",
            query_sentence,
        )
    ).strip()
    return MassivePulleySource(
        problem_text=problem_text,
        mass_a_si=float(mass_a_si),
        mass_b_si=float(mass_b_si),
        gravity_si=float(gravity_si),
        inertia_si=float(inertia_si),
        radius_si=float(radius_si),
        query_role=query_role,
        query_body=query_body,
        query_direction_sign=query_sign,
    )


BASELINE = _source(2.0, 5.0)
MASS_SWAP = _source(5.0, 2.0)
OPPOSITE_SIGN_QUERY = _source(
    2.0,
    5.0,
    query_direction_sign=-1,
)
ACCELERATION_A_QUERY = _source(2.0, 5.0, query_body="bodyA")
TENSION_A_QUERY = _source(2.0, 5.0, query_role="tension", query_body="bodyA")
TENSION_B_QUERY = _source(2.0, 5.0, query_role="tension", query_body="bodyB")
ALPHA_QUERY = _source(
    2.0,
    5.0,
    query_role="angular_acceleration",
    query_body="pulley",
)
NEAR_IDEAL_LIMIT = _source(2.0, 5.0, inertia_si=1.0e-9)
EQUAL_MASSES = _source(3.0, 3.0)


def _direction(axis: str, sign: int) -> dict[str, object]:
    return _axis_direction(axis, sign, frame_id=WORLD_FRAME_ID)


PayloadMutation = Callable[[dict[str, object]], None]


def _draft_payload(source: MassivePulleySource) -> dict[str, object]:
    mass_a_raw = f"{source.mass_a_si:g}"
    mass_b_raw = f"{source.mass_b_si:g}"
    gravity_raw = f"{source.gravity_si:g}"
    inertia_raw = f"{source.inertia_si:g}"
    radius_raw = f"{source.radius_si:g}"
    mass_a_quote = f"Mass A is {mass_a_raw} kg and hangs on the left."
    mass_b_quote = f"Mass B is {mass_b_raw} kg and hangs on the right."
    gravity_quote = f"Take g = {gravity_raw} m/s^2."
    inertia_quote = (
        f"The pulley moment of inertia about its center is {inertia_raw} kg*m^2."
    )
    left_radius_quote = f"The left pulley rim radius is {radius_raw} m."
    right_radius_quote = f"The right pulley rim radius is {radius_raw} m."
    rim_quote = (
        "The left and right rim points lie from the center along the -x and +x "
        "axes, respectively."
    )
    rope_quote = "The particles are joined by one massless, inextensible rope."
    taut_quote = "The rope is taut."
    wrap_quote = "The rope wraps around the massive pulley."
    attach_a_quote = "The rope is attached to mass A on the left side."
    attach_b_quote = "The rope is attached to mass B on the right side."
    fixed_quote = "The pulley center is fixed while the pulley remains free to rotate."
    axle_quote = "The axle is frictionless and exerts no other torque on the pulley."
    no_slip_quote = "The rope does not slip on the pulley rim."
    orientation_quote = (
        "The world frame is Cartesian 3-D; +y points downward and +z is the "
        "positive rotation when the right mass descends."
    )
    if source.query_role == "tension":
        query_quote = (
            f"Find the tension acting upward on mass {'A' if source.query_body == 'bodyA' else 'B'}."
        )
    elif source.query_role == "angular_acceleration":
        query_quote = (
            "Find the signed angular acceleration of the pulley along the "
            f"{'positive' if source.query_direction_sign == 1 else 'negative'} z direction."
        )
    else:
        query_quote = (
            f"Find the signed acceleration of mass {'A' if source.query_body == 'bodyA' else 'B'} "
            f"along the {'downward' if source.query_direction_sign == 1 else 'upward'} direction."
        )
    evidence_specs = (
        ("massAEvidence", mass_a_quote, f"{mass_a_raw} kg"),
        ("massBEvidence", mass_b_quote, f"{mass_b_raw} kg"),
        ("gravityEvidence", gravity_quote, f"{gravity_raw} m/s^2"),
        ("inertiaEvidence", inertia_quote, f"{inertia_raw} kg*m^2"),
        ("leftRadiusEvidence", left_radius_quote, f"{radius_raw} m"),
        ("rightRadiusEvidence", right_radius_quote, f"{radius_raw} m"),
        ("rimEvidence", rim_quote, None),
        ("ropeEvidence", rope_quote, None),
        ("tautEvidence", taut_quote, None),
        ("wrapEvidence", wrap_quote, None),
        ("attachAEvidence", attach_a_quote, None),
        ("attachBEvidence", attach_b_quote, None),
        ("fixedPulleyEvidence", fixed_quote, None),
        ("axleEvidence", axle_quote, None),
        ("noSlipEvidence", no_slip_quote, None),
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
        _symbol(symbol_id, quantity_id, dimension)
        for symbol_id, quantity_id, dimension in (
            ("mA", "massA", MASS),
            ("mB", "massB", MASS),
            ("g", "gravity", ACCELERATION),
            ("I", "pulleyInertia", MOMENT_OF_INERTIA),
            ("rL", "leftRadius", LENGTH),
            ("rR", "rightRadius", LENGTH),
            ("wA", "weightA", FORCE),
            ("wB", "weightB", FORCE),
            ("tA", "tensionA", FORCE),
            ("tB", "tensionB", FORCE),
            ("TL", "leftPulleyTension", FORCE),
            ("TR", "rightPulleyTension", FORCE),
            ("aA", "accelerationA", ACCELERATION),
            ("aB", "accelerationB", ACCELERATION),
            ("aRope", "ropeAccelerationCoordinate", ACCELERATION),
            ("alpha", "angularAcceleration", ANGULAR_ACCELERATION),
        )
    ]
    query_target_quantity_id = {
        ("acceleration", "bodyA"): "accelerationA",
        ("acceleration", "bodyB"): "accelerationB",
        ("tension", "bodyA"): "tensionA",
        ("tension", "bodyB"): "tensionB",
        ("angular_acceleration", "pulley"): "angularAcceleration",
    }[(source.query_role, source.query_body)]
    query_evidence_quantity_id = query_target_quantity_id
    query_evidence_refs = lambda quantity_id, base: (
        (*base, "queryEvidence")
        if quantity_id == query_evidence_quantity_id
        else base
    )
    quantities = [
        _quantity("massA", "mA", "mass", "bodyA", MASS, provenance="explicit_source", evidence_refs=("massAEvidence",), raw_value=mass_a_raw, raw_unit="kg"),
        _quantity("massB", "mB", "mass", "bodyB", MASS, provenance="explicit_source", evidence_refs=("massBEvidence",), raw_value=mass_b_raw, raw_unit="kg"),
        _quantity("gravity", "g", "gravity", "world", ACCELERATION, provenance="explicit_source", evidence_refs=("gravityEvidence",), raw_value=gravity_raw, raw_unit="m/s^2"),
        _quantity("pulleyInertia", "I", "moment_of_inertia", "pulley", MOMENT_OF_INERTIA, provenance="explicit_source", evidence_refs=("inertiaEvidence", "fixedPulleyEvidence", "axleEvidence"), raw_value=inertia_raw, raw_unit="kg*m^2"),
        _quantity("leftRadius", "rL", "radius", "pulley", LENGTH, point_id=LEFT_RIM_POINT_ID, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="x", direction=_direction("x", -1), provenance="explicit_source", evidence_refs=("leftRadiusEvidence", "rimEvidence", "orientationEvidence"), raw_value=radius_raw, raw_unit="m"),
        _quantity("rightRadius", "rR", "radius", "pulley", LENGTH, point_id=RIGHT_RIM_POINT_ID, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="x", direction=_direction("x", 1), provenance="explicit_source", evidence_refs=("rightRadiusEvidence", "rimEvidence", "orientationEvidence"), raw_value=radius_raw, raw_unit="m"),
        _quantity("weightA", "wA", "force", "bodyA", FORCE, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="y", direction=_direction("y", 1), evidence_refs=("gravityEvidence", "orientationEvidence")),
        _quantity("weightB", "wB", "force", "bodyB", FORCE, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="y", direction=_direction("y", 1), evidence_refs=("gravityEvidence", "orientationEvidence")),
        _quantity("tensionA", "tA", "force", "bodyA", FORCE, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="y", direction=_direction("y", -1), evidence_refs=query_evidence_refs("tensionA", ("ropeEvidence", "tautEvidence", "attachAEvidence", "orientationEvidence"))),
        _quantity("tensionB", "tB", "force", "bodyB", FORCE, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="y", direction=_direction("y", -1), evidence_refs=query_evidence_refs("tensionB", ("ropeEvidence", "tautEvidence", "attachBEvidence", "orientationEvidence"))),
        _quantity("leftPulleyTension", "TL", "force", "pulley", FORCE, point_id=LEFT_RIM_POINT_ID, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="y", direction=_direction("y", 1), evidence_refs=("ropeEvidence", "wrapEvidence", "rimEvidence", "orientationEvidence")),
        _quantity("rightPulleyTension", "TR", "force", "pulley", FORCE, point_id=RIGHT_RIM_POINT_ID, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="y", direction=_direction("y", 1), evidence_refs=("ropeEvidence", "wrapEvidence", "rimEvidence", "orientationEvidence")),
        _quantity("accelerationA", "aA", "acceleration", "bodyA", ACCELERATION, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="y", direction=_direction("y", source.acceleration_a_sign), evidence_refs=query_evidence_refs("accelerationA", ("ropeEvidence", "fixedPulleyEvidence", "orientationEvidence"))),
        _quantity("accelerationB", "aB", "acceleration", "bodyB", ACCELERATION, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="y", direction=_direction("y", source.acceleration_b_sign), evidence_refs=query_evidence_refs("accelerationB", ("ropeEvidence", "fixedPulleyEvidence", "orientationEvidence"))),
        _quantity("ropeAccelerationCoordinate", "aRope", "acceleration", "rope", ACCELERATION, interval_id=INTERVAL_ID, evidence_refs=("ropeEvidence", "wrapEvidence", "noSlipEvidence", "fixedPulleyEvidence", "attachAEvidence", "attachBEvidence")),
        _quantity("angularAcceleration", "alpha", "angular_acceleration", "pulley", ANGULAR_ACCELERATION, frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID, component="z", direction=_direction("z", source.alpha_sign), evidence_refs=query_evidence_refs("angularAcceleration", ("inertiaEvidence", "rimEvidence", "noSlipEvidence", "axleEvidence", "orientationEvidence"))),
    ]
    if source.query_role == "angular_acceleration":
        query_target = {
            "role": "angular_acceleration",
            "subject_id": "pulley",
            "frame_id": WORLD_FRAME_ID,
            "interval_id": INTERVAL_ID,
            "component": "z",
            "direction": _direction("z", source.query_direction_sign),
            "target_quantity_id": "angularAcceleration",
        }
        query_unit = "rad/s^2"
        query_dimension = ANGULAR_ACCELERATION
    else:
        query_target = {
            "role": "force" if source.query_role == "tension" else "acceleration",
            "subject_id": source.query_body,
            "frame_id": WORLD_FRAME_ID,
            "interval_id": INTERVAL_ID,
            "component": "y",
            "direction": _direction("y", source.query_direction_sign),
            "target_quantity_id": query_target_quantity_id,
        }
        query_unit = "N" if source.query_role == "tension" else "m/s^2"
        query_dimension = FORCE if source.query_role == "tension" else ACCELERATION
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnosticMassivePulleyLabel",
            "subtype": "diagnosticInertialPulleyLabel",
            "model_id": "sameFixtureMassivePulleyTest",
            "source_text_sha256": hashlib.sha256(
                source.problem_text.encode("utf-8")
            ).hexdigest(),
        },
        "source_assets": [],
        "source_evidence": evidence,
        "entities": [
            {"entity_id": "bodyA", "primitive": "particle", "evidence_refs": ["massAEvidence", "ropeEvidence", "attachAEvidence"]},
            {"entity_id": "bodyB", "primitive": "particle", "evidence_refs": ["massBEvidence", "ropeEvidence", "attachBEvidence"]},
            {"entity_id": "rope", "primitive": "rope", "evidence_refs": ["ropeEvidence", "tautEvidence", "wrapEvidence", "attachAEvidence", "attachBEvidence"]},
            {"entity_id": "pulley", "primitive": "pulley", "evidence_refs": ["inertiaEvidence", "leftRadiusEvidence", "rightRadiusEvidence", "rimEvidence", "wrapEvidence", "fixedPulleyEvidence", "axleEvidence", "noSlipEvidence"]},
            {"entity_id": "world", "primitive": "environment", "evidence_refs": ["gravityEvidence", "orientationEvidence"]},
        ],
        "points": [
            {"point_id": LEFT_RIM_POINT_ID, "role": "contact", "owner_entity_id": "pulley", "frame_id": WORLD_FRAME_ID, "evidence_refs": ["leftRadiusEvidence", "rimEvidence", "wrapEvidence"]},
            {"point_id": RIGHT_RIM_POINT_ID, "role": "contact", "owner_entity_id": "pulley", "frame_id": WORLD_FRAME_ID, "evidence_refs": ["rightRadiusEvidence", "rimEvidence", "wrapEvidence"]},
        ],
        "reference_frames": [
            {
                "frame_id": WORLD_FRAME_ID,
                "frame_type": "cartesian_3d",
                "origin": {"kind": "world"},
                "axes": [
                    _axis_binding("x", frame_id=WORLD_FRAME_ID),
                    _axis_binding("y", frame_id=WORLD_FRAME_ID),
                    _axis_binding("z", frame_id=WORLD_FRAME_ID),
                ],
                "evidence_refs": ["orientationEvidence"],
            }
        ],
        "motion_intervals": [
            {
                "interval_id": INTERVAL_ID,
                "order": 1,
                "subject_ids": ["bodyA", "bodyB", "rope", "pulley", "world"],
                "frame_id": WORLD_FRAME_ID,
                "evidence_refs": ["ropeEvidence", "tautEvidence", "wrapEvidence", "fixedPulleyEvidence", "axleEvidence", "noSlipEvidence", "orientationEvidence"],
            }
        ],
        "events": [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": [
            {"relation_id": "leftRadiusGeometry", "kind": "radius", "participant_ids": ["pulley", LEFT_RIM_POINT_ID], "quantity_ids": ["leftRadius"], "interval_id": INTERVAL_ID, "evidence_refs": ["leftRadiusEvidence", "rimEvidence", "orientationEvidence"]},
            {"relation_id": "rightRadiusGeometry", "kind": "radius", "participant_ids": ["pulley", RIGHT_RIM_POINT_ID], "quantity_ids": ["rightRadius"], "interval_id": INTERVAL_ID, "evidence_refs": ["rightRadiusEvidence", "rimEvidence", "orientationEvidence"]},
            {"relation_id": "leftTangentGeometry", "kind": "tangent", "participant_ids": ["rope", "pulley", LEFT_RIM_POINT_ID], "quantity_ids": ["leftRadius", "leftPulleyTension"], "interval_id": INTERVAL_ID, "evidence_refs": ["rimEvidence", "wrapEvidence", "orientationEvidence"]},
            {"relation_id": "rightTangentGeometry", "kind": "tangent", "participant_ids": ["rope", "pulley", RIGHT_RIM_POINT_ID], "quantity_ids": ["rightRadius", "rightPulleyTension"], "interval_id": INTERVAL_ID, "evidence_refs": ["rimEvidence", "wrapEvidence", "orientationEvidence"]},
            {"relation_id": "ropeWrap", "kind": "wraps", "participant_ids": ["rope", "pulley", LEFT_RIM_POINT_ID, RIGHT_RIM_POINT_ID], "quantity_ids": ["leftRadius", "rightRadius", "leftPulleyTension", "rightPulleyTension", "ropeAccelerationCoordinate", "angularAcceleration"], "interval_id": INTERVAL_ID, "evidence_refs": ["wrapEvidence", "rimEvidence", "noSlipEvidence", "orientationEvidence"]},
            {"relation_id": "ropeAttachedA", "kind": "attached", "participant_ids": ["rope", "pulley", "bodyA", LEFT_RIM_POINT_ID], "quantity_ids": ["tensionA", "leftPulleyTension", "accelerationA", "ropeAccelerationCoordinate"], "interval_id": INTERVAL_ID, "evidence_refs": ["attachAEvidence", "fixedPulleyEvidence"]},
            {"relation_id": "ropeAttachedB", "kind": "attached", "participant_ids": ["rope", "pulley", "bodyB", RIGHT_RIM_POINT_ID], "quantity_ids": ["tensionB", "rightPulleyTension", "accelerationB", "ropeAccelerationCoordinate"], "interval_id": INTERVAL_ID, "evidence_refs": ["attachBEvidence", "fixedPulleyEvidence"]},
        ],
        "interactions": [
            {"interaction_id": "gravityA", "kind": "gravity", "participant_ids": ["bodyA", "world"], "frame_id": WORLD_FRAME_ID, "interval_id": INTERVAL_ID, "quantity_ids": ["massA", "gravity", "weightA"], "evidence_refs": ["massAEvidence", "gravityEvidence", "orientationEvidence"]},
            {"interaction_id": "gravityB", "kind": "gravity", "participant_ids": ["bodyB", "world"], "frame_id": WORLD_FRAME_ID, "interval_id": INTERVAL_ID, "quantity_ids": ["massB", "gravity", "weightB"], "evidence_refs": ["massBEvidence", "gravityEvidence", "orientationEvidence"]},
            {"interaction_id": "ropeTension", "kind": "rope_tension", "participant_ids": ["bodyA", "bodyB", "rope", "pulley"], "point_ids": [LEFT_RIM_POINT_ID, RIGHT_RIM_POINT_ID], "frame_id": WORLD_FRAME_ID, "interval_id": INTERVAL_ID, "quantity_ids": ["tensionA", "tensionB", "leftPulleyTension", "rightPulleyTension"], "evidence_refs": ["ropeEvidence", "tautEvidence", "wrapEvidence", "attachAEvidence", "attachBEvidence", "rimEvidence", "orientationEvidence"]},
        ],
        "constraints": [],
        "state_conditions": [
            {"state_condition_id": "ropeTautState", "kind": "rope", "state": "taut", "subject_id": "rope", "interval_id": INTERVAL_ID, "quantity_ids": [], "evidence_refs": ["tautEvidence"]},
            {"state_condition_id": "pulleyNoSlipState", "kind": "rolling", "state": "no_slip", "subject_id": "pulley", "interval_id": INTERVAL_ID, "quantity_ids": ["leftRadius", "rightRadius", "angularAcceleration"], "evidence_refs": ["noSlipEvidence", "leftRadiusEvidence", "rightRadiusEvidence", "orientationEvidence"]},
        ],
        "queries": [
            {
                "query_id": "queryTarget",
                "target": query_target,
                "output_unit": query_unit,
                "output_dimension": query_dimension.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": ["queryEvidence"],
            }
        ],
        "principle_hints": [],
        "assumptions": [
            {"assumption_id": "masslessRope", "kind": "massless_rope", "subject_id": "rope", "interval_id": INTERVAL_ID, "disposition": "approved", "reason": "The source explicitly identifies one massless rope.", "evidence_refs": ["ropeEvidence"]},
            {"assumption_id": "inextensibleRope", "kind": "inextensible_rope", "subject_id": "rope", "interval_id": INTERVAL_ID, "disposition": "approved", "reason": "The source explicitly identifies one inextensible rope.", "evidence_refs": ["ropeEvidence"]},
            {"assumption_id": "fixedPulley", "kind": "fixed_pulley", "subject_id": "pulley", "interval_id": INTERVAL_ID, "disposition": "approved", "reason": "The source explicitly fixes the pulley center while permitting rotation.", "evidence_refs": ["fixedPulleyEvidence"]},
            {"assumption_id": "frictionlessAxle", "kind": "frictionless_axle", "subject_id": "pulley", "interval_id": INTERVAL_ID, "disposition": "approved", "reason": "The source explicitly excludes axle friction and other applied torque.", "evidence_refs": ["axleEvidence"]},
        ],
        "ambiguities": [],
        "figure_dependency": {"level": "none", "missing_information": [], "evidence_refs": []},
        "unsupported_features": [],
    }


def _normalize(
    source: MassivePulleySource,
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


def _build_ir(source: MassivePulleySource) -> MechanicsProblemIRV1:
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
class MassivePulleyResiduals:
    weight_a: float
    weight_b: float
    particle_newton_a: float
    particle_newton_b: float
    tension_transfer_a: float
    tension_transfer_b: float
    acceleration_transfer_a: float
    acceleration_transfer_b: float
    no_slip_left: float
    no_slip_right: float
    pulley_newton_euler: float
    acceleration_closed_form: float
    alpha_closed_form: float
    tension_a_closed_form: float
    tension_b_closed_form: float
    tension_a_si: float
    tension_b_si: float

    @property
    def passed(self) -> bool:
        residuals = (
            self.weight_a,
            self.weight_b,
            self.particle_newton_a,
            self.particle_newton_b,
            self.tension_transfer_a,
            self.tension_transfer_b,
            self.acceleration_transfer_a,
            self.acceleration_transfer_b,
            self.no_slip_left,
            self.no_slip_right,
            self.pulley_newton_euler,
            self.acceleration_closed_form,
            self.alpha_closed_form,
            self.tension_a_closed_form,
            self.tension_b_closed_form,
        )
        return (
            all(abs(value) <= 1.0e-9 for value in residuals)
            and self.tension_a_si >= -1.0e-9
            and self.tension_b_si >= -1.0e-9
        )


def _independent_residuals(
    source: MassivePulleySource,
    values: dict[str, float],
) -> MassivePulleyResiduals:
    required = {
        "wA", "wB", "tA", "tB", "TL", "TR",
        "aA", "aB", "aRope", "alpha",
    }
    assert required.issubset(values)
    return MassivePulleyResiduals(
        weight_a=values["wA"] - source.mass_a_si * source.gravity_si,
        weight_b=values["wB"] - source.mass_b_si * source.gravity_si,
        particle_newton_a=(
            values["wA"] - values["tA"] + source.mass_a_si * values["aA"]
        ),
        particle_newton_b=(
            values["wB"] - values["tB"] - source.mass_b_si * values["aB"]
        ),
        tension_transfer_a=values["tA"] - values["TL"],
        tension_transfer_b=values["tB"] - values["TR"],
        acceleration_transfer_a=values["aA"] - values["aRope"],
        acceleration_transfer_b=values["aB"] - values["aRope"],
        no_slip_left=(
            values["aRope"] - source.radius_si * values["alpha"]
        ),
        no_slip_right=(
            values["aRope"] - source.radius_si * values["alpha"]
        ),
        pulley_newton_euler=(
            source.radius_si * (values["TR"] - values["TL"])
            - source.inertia_si * values["alpha"]
        ),
        acceleration_closed_form=(
            values["aRope"] - source.expected_acceleration_si
        ),
        alpha_closed_form=values["alpha"] - source.expected_alpha_si,
        tension_a_closed_form=(
            values["tA"] - source.expected_tension_a_si
        ),
        tension_b_closed_form=(
            values["tB"] - source.expected_tension_b_si
        ),
        tension_a_si=values["tA"],
        tension_b_si=values["tB"],
    )


def _legacy_answer_value(result: SolverResult, symbol: str) -> float:
    answer = next(item for item in result.answers if item.symbol == symbol)
    assert type(answer.numeric) is float
    return answer.numeric


def _observe_legacy(
    source: MassivePulleySource,
) -> tuple[LegacyObservation, SolverResult]:
    problem = CanonicalProblem(
        raw_text=source.problem_text,
        system_type="massive_pulley_atwood",
        knowns={
            "m1": Quantity("m1", source.mass_a_si, "kg"),
            "m2": Quantity("m2", source.mass_b_si, "kg"),
            "g": Quantity("g", source.gravity_si, "m/s^2"),
            "I": Quantity("I", source.inertia_si, "kg*m^2"),
            "R": Quantity("R", source.radius_si, "m"),
        },
        unknowns=["acceleration", "angular_acceleration", "tension"],
        requested_outputs=["acceleration", "angular_acceleration", "tension"],
    )
    result = MassivePulleyAtwoodSolver().solve(problem)
    assert result.ok is True, result.unsupported_reason
    assert result.verification.passed is True
    decision = result.selection_decision
    assert decision is not None and decision.status == "selected"
    assert decision.selected_candidate is not None
    assert decision.valid_alternatives == []
    assert decision.rejected_candidates == []
    mapping = decision.selected_candidate.numerical_mapping
    assert set(mapping) == {"a", "T1", "T2"}
    acceleration = mapping["a"]
    tension_a = mapping["T1"]
    tension_b = mapping["T2"]
    alpha = acceleration / source.radius_si
    assert all(
        type(value) is float
        for value in (acceleration, tension_a, tension_b, alpha)
    )
    assert result.answer is not None
    assert result.answer.numeric == pytest.approx(
        round(acceleration, 6), rel=0.0, abs=1.0e-12
    )
    assert _legacy_answer_value(result, "a") == pytest.approx(
        round(acceleration, 6), rel=0.0, abs=1.0e-12
    )
    assert _legacy_answer_value(result, "alpha") == pytest.approx(
        round(alpha, 6), rel=0.0, abs=1.0e-12
    )
    assert _legacy_answer_value(result, "T1") == pytest.approx(
        round(tension_a, 6), rel=0.0, abs=1.0e-12
    )
    assert _legacy_answer_value(result, "T2") == pytest.approx(
        round(tension_b, 6), rel=0.0, abs=1.0e-12
    )
    residual_passed = all(
        math.isclose(left, right, rel_tol=0.0, abs_tol=1.0e-9)
        for left, right in (
            (acceleration, source.expected_acceleration_si),
            (alpha, source.expected_alpha_si),
            (tension_a, source.expected_tension_a_si),
            (tension_b, source.expected_tension_b_si),
            (
                source.radius_si * (tension_b - tension_a),
                source.inertia_si * alpha,
            ),
        )
    )
    assert residual_passed is True
    if source.query_role == "tension":
        selected = tension_a if source.query_body == "bodyA" else tension_b
        unit, dimension = "N", FORCE
    elif source.query_role == "angular_acceleration":
        selected = alpha
        unit, dimension = "rad/s^2", ANGULAR_ACCELERATION
    else:
        selected = acceleration
        unit, dimension = "m/s^2", ACCELERATION
    normalized = normalize_quantity(str(selected), unit, "scalar", dimension)
    assert type(normalized.value) is float
    observation = LegacyObservation(
        case_id=(
            "massivePulley"
            + hashlib.sha256(source.problem_text.encode("utf-8")).hexdigest()[:32]
        ),
        diagnostic_kernel_id="massivePulleyAtwoodDirectV1",
        terminal=LegacyTerminal.solved,
        query_symbol_id=source.query_symbol_id,
        si_unit=render_canonical_si_unit(dimension),
        selected_scalar_si=normalized.value,
        complete_candidate_scalars_si=(
            LegacyCandidateScalar(value_si=normalized.value, multiplicity=1),
        ),
        residual_passed=residual_passed,
    )
    return observation, result


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport
    residuals: MassivePulleyResiduals


def _same_fixture(source: MassivePulleySource) -> SameFixtureEvidence:
    ir = _build_ir(source)
    assert "raw_text" not in type(ir).model_fields

    # Freeze the generic authority before the diagnostic-only legacy call.
    execution = _execute(ir)
    assert execution.terminal is MigrationProbeTerminal.solved, (
        None if execution.compiler_result is None else execution.compiler_result.issues
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
        registry_entry="massive_pulley_atwood",
        ir=ir,
        execution=execution,
        observation=observation,
        report=report,
        residuals=residuals,
    )


POSITIVE_CASES = (
    BASELINE,
    MASS_SWAP,
    ACCELERATION_A_QUERY,
    TENSION_A_QUERY,
    TENSION_B_QUERY,
    ALPHA_QUERY,
    NEAR_IDEAL_LIMIT,
    EQUAL_MASSES,
)


@pytest.mark.slow
@pytest.mark.parametrize(
    "source",
    POSITIVE_CASES,
    ids=(
        "baseline-body-b-acceleration",
        "mass-swap-negative-coordinate-scalars",
        "body-a-local-acceleration",
        "left-local-tension",
        "right-local-tension",
        "positive-z-angular-acceleration",
        "positive-inertia-near-ideal-limit",
        "equal-mass-zero-motion",
    ),
)
def test_massive_pulley_same_fixture_full_parity(
    source: MassivePulleySource,
) -> None:
    evidence = _same_fixture(source)
    execution = evidence.execution
    compiler = execution.compiler_result
    result = execution.solve_result
    assert evidence.registry_entry == "massive_pulley_atwood"
    assert compiler is not None and compiler.graph is not None
    assert execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert execution.solve_terminal is MechanicsSolveTerminal.solved

    expected_laws = Counter(
        {
            "particle_weight": 2,
            "particle_newton_second": 2,
            "rope_attachment_side_tension_transfer": 2,
            "rope_attachment_acceleration_transfer": 2,
            "pulley_no_slip_acceleration": 1,
            "pulley_newton_euler": 1,
        }
    )
    graph = compiler.graph
    assert Counter(item.law_id for item in graph.equations) == expected_laws
    assert evidence.ir.constraints == ()
    assert not any(item.kind == "ideal_pulley" for item in evidence.ir.assumptions)
    assert not any(
        item.subject_id == "pulley" and item.state.value == "at_rest"
        for item in evidence.ir.state_conditions
    )
    assert "rope_equal_tension" not in expected_laws
    assert "rope_fixed_pulley_motion" not in expected_laws

    equations_by_law = {
        law_id: tuple(item for item in graph.equations if item.law_id == law_id)
        for law_id in expected_laws
    }
    for equation in equations_by_law["rope_attachment_side_tension_transfer"]:
        assert equation.assumption_ids == ("masslessRope",)
        assert "ropeTautState" in equation.constraint_ids
        attachment_ids = {"ropeAttachedA", "ropeAttachedB"}.intersection(
            equation.constraint_ids
        )
        assert len(attachment_ids) == 1
        attachment_id = next(iter(attachment_ids))
        evidence_id = (
            "attachAEvidence"
            if attachment_id == "ropeAttachedA"
            else "attachBEvidence"
        )
        assert {evidence_id, "ropeEvidence", "tautEvidence"}.issubset(
            equation.source_evidence_ids
        )

    for equation in equations_by_law["rope_attachment_acceleration_transfer"]:
        assert equation.assumption_ids == ("fixedPulley", "inextensibleRope")
        assert "ropeTautState" in equation.constraint_ids
        attachment_ids = {"ropeAttachedA", "ropeAttachedB"}.intersection(
            equation.constraint_ids
        )
        assert len(attachment_ids) == 1
        assert "fixedPulleyEvidence" in equation.source_evidence_ids

    no_slip = equations_by_law["pulley_no_slip_acceleration"]
    assert len(no_slip) == 1
    assert no_slip[0].assumption_ids == ("fixedPulley", "inextensibleRope")
    assert {
        "leftRadiusGeometry",
        "rightRadiusGeometry",
        "leftTangentGeometry",
        "rightTangentGeometry",
        "ropeWrap",
        "pulleyNoSlipState",
    }.issubset(no_slip[0].constraint_ids)
    assert {
        "leftRadius",
        "rightRadius",
        "ropeAccelerationCoordinate",
        "angularAcceleration",
    }.issubset(no_slip[0].source_quantity_ids)
    assert {
        "noSlipEvidence",
        "leftRadiusEvidence",
        "rightRadiusEvidence",
        "wrapEvidence",
    }.issubset(no_slip[0].source_evidence_ids)

    rotation = equations_by_law["pulley_newton_euler"]
    assert len(rotation) == 1
    assert rotation[0].assumption_ids == ("fixedPulley", "frictionlessAxle")
    assert {
        "pulleyInertia",
        "leftRadius",
        "rightRadius",
        "leftPulleyTension",
        "rightPulleyTension",
        "angularAcceleration",
    }.issubset(rotation[0].source_quantity_ids)
    assert "axleEvidence" in rotation[0].source_evidence_ids

    for law_id, required_evidence in (
        ("rope_attachment_acceleration_transfer", "fixedPulleyEvidence"),
        ("pulley_newton_euler", "axleEvidence"),
    ):
        applications = tuple(
            item for item in graph.applications if item.law_id == law_id
        )
        assert applications
        assert all(
            required_evidence in application.source_evidence_ids
            for application in applications
        )

    quantity_by_id = {item.quantity_id: item for item in evidence.ir.quantities}
    assert quantity_by_id["accelerationA"].direction.sign == -1
    assert quantity_by_id["accelerationB"].direction.sign == 1
    assert quantity_by_id["angularAcceleration"].direction.sign == 1
    assert quantity_by_id["ropeAccelerationCoordinate"].subject_id == "rope"
    assert quantity_by_id["ropeAccelerationCoordinate"].frame_id is None
    assert quantity_by_id["ropeAccelerationCoordinate"].direction is None
    assert quantity_by_id["pulleyInertia"].point_id is None
    assert quantity_by_id["pulleyInertia"].frame_id is None
    assert quantity_by_id["pulleyInertia"].interval_id is None

    assert result.plan.primary_backend is SolveBackendKind.linear_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert result.candidate_set.generation_complete is True
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    assert candidate.query_symbol_id == source.query_symbol_id
    assert candidate.root_multiplicity == 1
    assert candidate.query_value_si == pytest.approx(
        source.expected_query_value_si, rel=0.0, abs=1.0e-9
    )
    assert candidate.query_value_si == pytest.approx(
        evidence.observation.selected_scalar_si, rel=0.0, abs=1.0e-9
    )
    values = _candidate_values(execution)
    assert values["aA"] == pytest.approx(source.expected_acceleration_si, abs=1.0e-9)
    assert values["aB"] == pytest.approx(source.expected_acceleration_si, abs=1.0e-9)
    assert values["aRope"] == pytest.approx(source.expected_acceleration_si, abs=1.0e-9)
    assert values["alpha"] == pytest.approx(source.expected_alpha_si, abs=1.0e-9)
    assert values["tA"] == pytest.approx(source.expected_tension_a_si, abs=1.0e-9)
    assert values["tB"] == pytest.approx(source.expected_tension_b_si, abs=1.0e-9)
    assert values["TL"] == pytest.approx(values["tA"], abs=1.0e-9)
    assert values["TR"] == pytest.approx(values["tB"], abs=1.0e-9)

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

    if source is BASELINE:
        assert values["aRope"] == pytest.approx(3.5316, rel=0.0, abs=1.0e-10)
        assert values["alpha"] == pytest.approx(11.772, rel=0.0, abs=1.0e-10)
        assert values["TL"] == pytest.approx(26.6832, rel=0.0, abs=1.0e-10)
        assert values["TR"] == pytest.approx(31.392, rel=0.0, abs=1.0e-10)
    if source is MASS_SWAP:
        assert values["aA"] < 0.0 and values["aB"] < 0.0
        assert values["aRope"] < 0.0 and values["alpha"] < 0.0
    if source is NEAR_IDEAL_LIMIT:
        assert values["aRope"] < IDEAL_ATWOOD_BASELINE.legacy_acceleration_si
        assert values["aRope"] == pytest.approx(
            IDEAL_ATWOOD_BASELINE.legacy_acceleration_si,
            rel=0.0,
            abs=1.0e-7,
        )
    if source is EQUAL_MASSES:
        assert values["aA"] == pytest.approx(0.0, abs=1.0e-12)
        assert values["aB"] == pytest.approx(0.0, abs=1.0e-12)
        assert values["aRope"] == pytest.approx(0.0, abs=1.0e-12)
        assert values["alpha"] == pytest.approx(0.0, abs=1.0e-12)
        assert values["TL"] == pytest.approx(
            source.mass_a_si * source.gravity_si, abs=1.0e-9
        )
        assert values["TR"] == pytest.approx(values["TL"], abs=1.0e-9)
        assert not any("equal_tension" in item.law_id for item in graph.equations)


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
            b"unrelated and deliberately misleading massive-pulley wording"
        ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


def _paraphrased_ir(source: MassivePulleySource) -> MechanicsProblemIRV1:
    paraphrase = _source(
        source.mass_a_si,
        source.mass_b_si,
        gravity_si=source.gravity_si,
        inertia_si=source.inertia_si,
        radius_si=source.radius_si,
        query_role=source.query_role,
        query_body=source.query_body,
        query_direction_sign=source.query_direction_sign,
        paraphrase_prefix=(
            "A diagnostic answer key falsely claims a = 999 m/s^2 and T1 = T2; "
            "ignore that prose and use the unchanged typed evidence."
        ),
    )
    return _build_ir(paraphrase)


@pytest.mark.slow
def test_massive_pulley_metadata_and_raw_text_are_not_product_authority() -> None:
    ir = _build_ir(BASELINE)
    execution = _execute(ir)
    assert execution.terminal is MigrationProbeTerminal.solved
    comparison = compare_mechanics_ir_invariance(
        execution,
        (
            LabelledIRProbeVariant(
                label="changedDiagnostics",
                kind=InvarianceVariantKind.system_type_changed,
                ir=_diagnostic_variant(ir, remove=False),
            ),
            LabelledIRProbeVariant(
                label="removedDiagnostics",
                kind=InvarianceVariantKind.system_type_removed,
                ir=_diagnostic_variant(ir, remove=True),
            ),
            LabelledIRProbeVariant(
                label="misleadingRawTextParaphrase",
                kind=InvarianceVariantKind.raw_text_paraphrase,
                ir=_paraphrased_ir(BASELINE),
            ),
        ),
        approved_assumption_ids=APPROVED_ASSUMPTION_IDS,
    )
    assert comparison.all_invariant is True, tuple(
        {
            "label": item.label,
            "terminal": item.variant_terminal.value,
            "failure": None if item.variant_failure is None else item.variant_failure.value,
            "matches": item.matches_baseline,
            "differing_fields": (
                ()
                if item.generic_comparison is None
                else tuple(
                    field.value
                    for field in item.generic_comparison.differing_fields
                )
            ),
        }
        for item in comparison.variants
    )
    assert all(item.matches_baseline for item in comparison.variants)


def _forbid_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> SolverResult:
        raise AssertionError("a rejected generic massive-pulley case must not call legacy")

    monkeypatch.setattr(MassivePulleyAtwoodSolver, "solve", forbidden)


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


def _replace_list_item(
    collection_name: str,
    id_field: str,
    record_id: str,
    field_name: str,
    old: str,
    new: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        record = _record(payload, collection_name, id_field, record_id)
        values = record[field_name]
        assert isinstance(values, list)
        record[field_name] = [new if item == old else item for item in values]

    return mutate


def _compose(*mutations: PayloadMutation) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        for mutation in mutations:
            mutation(payload)

    return mutate


def _flip_quantity_axis(
    quantity_id: str,
    *,
    component: str,
    axis: str,
    sign: int,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        quantity = _record(payload, "quantities", "quantity_id", quantity_id)
        quantity["component"] = component
        quantity["direction"] = _direction(axis, sign)

    return mutate


def _add_pulley_at_rest(payload: dict[str, object]) -> None:
    states = payload["state_conditions"]
    assert isinstance(states, list)
    states.append(
        {
            "state_condition_id": "pulleyAtRestContamination",
            "kind": "motion",
            "state": "at_rest",
            "subject_id": "pulley",
            "interval_id": INTERVAL_ID,
            "quantity_ids": [],
            "evidence_refs": ["fixedPulleyEvidence"],
        }
    )


def _add_equal_tension_constraint(payload: dict[str, object]) -> None:
    constraints = payload["constraints"]
    assert isinstance(constraints, list)
    constraints.append(
        {
            "constraint_id": "equalTensionContamination",
            "kind": "rope",
            "expression": Equality(
                left=SymbolRef(symbol_id="TL", dimension=FORCE),
                right=SymbolRef(symbol_id="TR", dimension=FORCE),
            ).model_dump(mode="json"),
            "subject_ids": ["rope", "pulley"],
            "interval_id": INTERVAL_ID,
            "evidence_refs": ["ropeEvidence"],
        }
    )


def _replace_frictionless_axle_with_ideal_pulley(
    payload: dict[str, object],
) -> None:
    assumption = _record(
        payload,
        "assumptions",
        "assumption_id",
        "frictionlessAxle",
    )
    assumption["kind"] = "ideal_pulley"
    assumption["reason"] = "Contaminating ideal-pulley authority must be rejected."


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


def _query_target(quantity_id: str, output_unit: str, *, shape: str = "scalar") -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _query_quantity(payload, quantity_id, output_unit=output_unit, shape=shape)

    return mutate


@dataclass(frozen=True)
class CompilerRejectCase:
    label: str
    mutation: PayloadMutation


COMPILER_REJECT_CASES = (
    CompilerRejectCase(
        "rim-point-role-not-contact",
        _set_field("points", "point_id", LEFT_RIM_POINT_ID, "role", "material"),
    ),
    CompilerRejectCase(
        "inertia-illegally-interval-scoped",
        _set_field(
            "quantities", "quantity_id", "pulleyInertia", "interval_id", INTERVAL_ID
        ),
    ),
    CompilerRejectCase(
        "alpha-illegally-point-bound",
        _set_field(
            "quantities", "quantity_id", "angularAcceleration", "point_id", LEFT_RIM_POINT_ID
        ),
    ),
    CompilerRejectCase(
        "left-radius-relation-removed",
        _remove_record("geometry", "relation_id", "leftRadiusGeometry"),
    ),
    CompilerRejectCase(
        "left-radius-relation-bound-to-right-point",
        _replace_list_item(
            "geometry",
            "relation_id",
            "leftRadiusGeometry",
            "participant_ids",
            LEFT_RIM_POINT_ID,
            RIGHT_RIM_POINT_ID,
        ),
    ),
    CompilerRejectCase(
        "both-radius-directions-positive-x",
        _flip_quantity_axis("leftRadius", component="x", axis="x", sign=1),
    ),
    CompilerRejectCase(
        "left-radius-orientation-not-x",
        _flip_quantity_axis("leftRadius", component="y", axis="y", sign=-1),
    ),
    CompilerRejectCase(
        "left-tangent-relation-removed",
        _remove_record("geometry", "relation_id", "leftTangentGeometry"),
    ),
    CompilerRejectCase(
        "left-tangent-uses-right-segment-tension",
        _replace_list_item(
            "geometry",
            "relation_id",
            "leftTangentGeometry",
            "quantity_ids",
            "leftPulleyTension",
            "rightPulleyTension",
        ),
    ),
    CompilerRejectCase(
        "wrap-removed",
        _remove_record("geometry", "relation_id", "ropeWrap"),
    ),
    CompilerRejectCase(
        "left-attachment-removed",
        _remove_record("geometry", "relation_id", "ropeAttachedA"),
    ),
    CompilerRejectCase(
        "left-attachment-crosses-to-right-rim",
        _replace_list_item(
            "geometry",
            "relation_id",
            "ropeAttachedA",
            "participant_ids",
            LEFT_RIM_POINT_ID,
            RIGHT_RIM_POINT_ID,
        ),
    ),
    CompilerRejectCase(
        "rope-interaction-removed",
        _remove_record("interactions", "interaction_id", "ropeTension"),
    ),
    CompilerRejectCase(
        "rope-interaction-extra-environment-participant",
        _set_field(
            "interactions",
            "interaction_id",
            "ropeTension",
            "participant_ids",
            ["bodyA", "bodyB", "rope", "pulley", "world"],
        ),
    ),
    CompilerRejectCase(
        "rope-interaction-carries-acceleration-bypass",
        _set_field(
            "interactions",
            "interaction_id",
            "ropeTension",
            "quantity_ids",
            [
                "tensionA",
                "tensionB",
                "leftPulleyTension",
                "rightPulleyTension",
                "ropeAccelerationCoordinate",
            ],
        ),
    ),
    CompilerRejectCase(
        "taut-state-removed",
        _remove_record("state_conditions", "state_condition_id", "ropeTautState"),
    ),
    CompilerRejectCase(
        "rope-state-slack",
        _set_field(
            "state_conditions", "state_condition_id", "ropeTautState", "state", "slack"
        ),
    ),
    CompilerRejectCase(
        "no-slip-state-removed",
        _remove_record(
            "state_conditions", "state_condition_id", "pulleyNoSlipState"
        ),
    ),
    CompilerRejectCase(
        "rolling-state-not-no-slip",
        _set_field(
            "state_conditions",
            "state_condition_id",
            "pulleyNoSlipState",
            "state",
            "rolling",
        ),
    ),
    CompilerRejectCase(
        "no-slip-state-missing-alpha-ref",
        _set_field(
            "state_conditions",
            "state_condition_id",
            "pulleyNoSlipState",
            "quantity_ids",
            ["leftRadius", "rightRadius"],
        ),
    ),
    CompilerRejectCase("pulley-at-rest-contamination", _add_pulley_at_rest),
    CompilerRejectCase(
        "massless-assumption-removed",
        _remove_record("assumptions", "assumption_id", "masslessRope"),
    ),
    CompilerRejectCase(
        "inextensible-assumption-removed",
        _remove_record("assumptions", "assumption_id", "inextensibleRope"),
    ),
    CompilerRejectCase(
        "fixed-pulley-assumption-removed",
        _remove_record("assumptions", "assumption_id", "fixedPulley"),
    ),
    CompilerRejectCase(
        "frictionless-axle-assumption-removed",
        _remove_record("assumptions", "assumption_id", "frictionlessAxle"),
    ),
    CompilerRejectCase(
        "ideal-pulley-contamination",
        _replace_frictionless_axle_with_ideal_pulley,
    ),
    CompilerRejectCase(
        "equal-tension-client-equation-contamination",
        _add_equal_tension_constraint,
    ),
    CompilerRejectCase(
        "body-a-acceleration-axis-wrong",
        _flip_quantity_axis("accelerationA", component="y", axis="y", sign=1),
    ),
    CompilerRejectCase(
        "alpha-axis-sign-wrong",
        _flip_quantity_axis("angularAcceleration", component="z", axis="z", sign=-1),
    ),
    CompilerRejectCase(
        "combined-wrap-and-tangents-deleted",
        _compose(
            _remove_record("geometry", "relation_id", "ropeWrap"),
            _remove_record("geometry", "relation_id", "leftTangentGeometry"),
            _remove_record("geometry", "relation_id", "rightTangentGeometry"),
        ),
    ),
    CompilerRejectCase(
        "combined-interaction-and-attachments-deleted",
        _compose(
            _remove_record("interactions", "interaction_id", "ropeTension"),
            _remove_record("geometry", "relation_id", "ropeAttachedA"),
            _remove_record("geometry", "relation_id", "ropeAttachedB"),
        ),
    ),
    CompilerRejectCase(
        "rim-tension-query-bypass",
        _query_target("leftPulleyTension", "N"),
    ),
    CompilerRejectCase(
        "rope-coordinate-query-bypass",
        _query_target("ropeAccelerationCoordinate", "m/s^2"),
    ),
    CompilerRejectCase(
        "radius-query-bypass",
        _query_target("leftRadius", "m"),
    ),
    CompilerRejectCase(
        "inertia-query-bypass",
        _query_target("pulleyInertia", "kg*m^2"),
    ),
    CompilerRejectCase(
        "weight-query-bypass",
        _query_target("weightA", "N"),
    ),
)


def _append_decoy_entity(payload: dict[str, object]) -> None:
    entities = payload["entities"]
    assert isinstance(entities, list)
    entities.append(
        {
            "entity_id": "decoyParticle",
            "primitive": "particle",
            "evidence_refs": ["massAEvidence"],
        }
    )


def _append_decoy_frame(payload: dict[str, object]) -> None:
    frames = payload["reference_frames"]
    assert isinstance(frames, list)
    frame_id = "decoyWorldFrame"
    frames.append(
        {
            "frame_id": frame_id,
            "frame_type": "cartesian_3d",
            "origin": {"kind": "world"},
            "axes": [
                _axis_binding("x", frame_id=frame_id),
                _axis_binding("y", frame_id=frame_id),
                _axis_binding("z", frame_id=frame_id),
            ],
            "evidence_refs": ["orientationEvidence"],
        }
    )


def _append_decoy_point(payload: dict[str, object]) -> None:
    points = payload["points"]
    assert isinstance(points, list)
    points.append(
        {
            "point_id": "decoyRimPoint",
            "role": "contact",
            "owner_entity_id": "pulley",
            "frame_id": WORLD_FRAME_ID,
            "evidence_refs": ["rimEvidence"],
        }
    )


def _append_decoy_geometry(payload: dict[str, object]) -> None:
    geometry = payload["geometry"]
    assert isinstance(geometry, list)
    geometry.append(
        {
            "relation_id": "decoyTopology",
            "kind": "topology_connects",
            "participant_ids": ["bodyA", "world"],
            "quantity_ids": [],
            "interval_id": INTERVAL_ID,
            "evidence_refs": ["orientationEvidence"],
        }
    )


def _append_decoy_interaction(payload: dict[str, object]) -> None:
    interactions = payload["interactions"]
    assert isinstance(interactions, list)
    interactions.append(
        {
            "interaction_id": "decoyInteraction",
            "kind": "other",
            "participant_ids": ["bodyA", "world"],
            "frame_id": WORLD_FRAME_ID,
            "interval_id": INTERVAL_ID,
            "quantity_ids": [],
            "evidence_refs": ["orientationEvidence"],
        }
    )


def _append_decoy_state(payload: dict[str, object]) -> None:
    states = payload["state_conditions"]
    assert isinstance(states, list)
    states.append(
        {
            "state_condition_id": "decoyMovingState",
            "kind": "motion",
            "state": "moving",
            "subject_id": "bodyA",
            "interval_id": INTERVAL_ID,
            "quantity_ids": [],
            "evidence_refs": ["orientationEvidence"],
        }
    )


def _append_decoy_assumption(payload: dict[str, object]) -> None:
    assumptions = payload["assumptions"]
    assert isinstance(assumptions, list)
    assumptions.append(
        {
            "assumption_id": "decoyRejectedAssumption",
            "kind": "diagnostic_decoy",
            "subject_id": "bodyA",
            "interval_id": INTERVAL_ID,
            "disposition": "rejected",
            "reason": "A disconnected rejected diagnostic assumption.",
            "evidence_refs": ["orientationEvidence"],
        }
    )


def _append_decoy_quantity_and_symbol(payload: dict[str, object]) -> None:
    symbols = payload["symbols"]
    quantities = payload["quantities"]
    assert isinstance(symbols, list) and isinstance(quantities, list)
    symbols.append(_symbol("decoyForceSymbol", "decoyForce", FORCE))
    quantities.append(
        _quantity(
            "decoyForce",
            "decoyForceSymbol",
            "force",
            "bodyA",
            FORCE,
            frame_id=WORLD_FRAME_ID,
            interval_id=INTERVAL_ID,
            component="y",
            direction=_direction("y", 1),
            evidence_refs=("orientationEvidence",),
        )
    )


def _append_decoy_event(payload: dict[str, object]) -> None:
    events = payload["events"]
    assert isinstance(events, list)
    events.append(
        {
            "event_id": "decoyEvent",
            "kind": "other",
            "subject_ids": ["bodyA"],
            "interval_ids": [],
            "evidence_refs": ["orientationEvidence"],
        }
    )


COMPILER_REJECT_CASES += (
    CompilerRejectCase("disconnected-extra-entity", _append_decoy_entity),
    CompilerRejectCase("disconnected-extra-frame", _append_decoy_frame),
    CompilerRejectCase("disconnected-extra-point", _append_decoy_point),
    CompilerRejectCase("disconnected-extra-geometry", _append_decoy_geometry),
    CompilerRejectCase("disconnected-extra-interaction", _append_decoy_interaction),
    CompilerRejectCase("disconnected-extra-state", _append_decoy_state),
    CompilerRejectCase("disconnected-extra-assumption", _append_decoy_assumption),
    CompilerRejectCase(
        "disconnected-extra-quantity-and-symbol",
        _append_decoy_quantity_and_symbol,
    ),
    CompilerRejectCase("disconnected-extra-event", _append_decoy_event),
)


def test_massive_pulley_exact_profile_compiles_fast_without_legacy(
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
            "particle_weight": 2,
            "particle_newton_second": 2,
            "rope_attachment_side_tension_transfer": 2,
            "rope_attachment_acceleration_transfer": 2,
            "pulley_no_slip_acceleration": 1,
            "pulley_newton_euler": 1,
        }
    )


@pytest.mark.parametrize("case", COMPILER_REJECT_CASES, ids=lambda case: case.label)
def test_massive_pulley_exact_contract_mismatches_are_precisely_unsupported(
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


def test_massive_pulley_opposite_direction_query_is_precisely_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)

    def leave_opposite_query_unbound(payload: dict[str, object]) -> None:
        query = _record(payload, "queries", "query_id", "queryTarget")
        query["target"]["target_quantity_id"] = None

    normalization = _normalize(
        OPPOSITE_SIGN_QUERY,
        mutation=leave_opposite_query_unbound,
    )
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    acceleration_b = next(
        item
        for item in normalization.ir.quantities
        if item.quantity_id == "accelerationB"
    )
    assert acceleration_b.direction is not None
    assert acceleration_b.direction.sign == 1
    execution = _execute(normalization.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


INVALID_DOMAIN_CASES = (
    _source(0.0, 5.0),
    _source(-2.0, 5.0),
    _source(2.0, 0.0),
    _source(2.0, -5.0),
    _source(2.0, 5.0, gravity_si=0.0),
    _source(2.0, 5.0, gravity_si=-9.81),
    _source(2.0, 5.0, inertia_si=0.0),
    _source(2.0, 5.0, inertia_si=-0.12),
    _source(2.0, 5.0, radius_si=0.0),
    _source(2.0, 5.0, radius_si=-0.3),
)


@pytest.mark.parametrize(
    "source",
    INVALID_DOMAIN_CASES,
    ids=(
        "zero-left-mass",
        "negative-left-mass",
        "zero-right-mass",
        "negative-right-mass",
        "zero-gravity",
        "negative-gravity",
        "zero-inertia-not-ideal-pulley",
        "negative-inertia",
        "zero-radius",
        "negative-radius",
    ),
)
def test_massive_pulley_nonpositive_domain_is_invalid_without_legacy(
    source: MassivePulleySource,
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


def test_massive_pulley_unequal_rim_radii_are_invalid_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    payload = _build_ir(BASELINE).model_dump(mode="python", warnings="none")
    quantities = payload["quantities"]
    assert isinstance(quantities, (list, tuple))
    right = next(
        item for item in quantities if item["quantity_id"] == "rightRadius"
    )
    right["raw_value"] = "0.4"
    right["si_value"] = 0.4
    unequal_ir = MechanicsProblemIRV1.model_validate(payload)
    execution = _execute(unequal_ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.invalid
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.invalid_domain
        for issue in execution.compiler_result.issues
    )


@pytest.mark.parametrize("omitted_id", APPROVED_ASSUMPTION_IDS)
def test_massive_pulley_unapproved_assumption_stops_at_confirmation(
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


def _declare_blocking_ambiguity(payload: dict[str, object]) -> None:
    payload["ambiguities"] = [
        {
            "ambiguity_id": "pulleySideOrientationAmbiguity",
            "kind": "direction",
            "referenced_ids": [
                LEFT_RIM_POINT_ID,
                RIGHT_RIM_POINT_ID,
                "leftRadius",
                "rightRadius",
                "angularAcceleration",
                "queryTarget",
            ],
            "description": "The pulley side orientation and torque sign are unresolved.",
            "blocking": True,
            "evidence_refs": ["orientationEvidence"],
        }
    ]


def test_massive_pulley_blocking_orientation_ambiguity_needs_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=_declare_blocking_ambiguity)
    assert normalization.terminal is ValidationTerminal.needs_confirmation
    assert normalization.ir is None


@pytest.mark.parametrize(
    "mutation",
    (
        _remove_record("points", "point_id", LEFT_RIM_POINT_ID),
        _query_target("accelerationB", "m/s^2", shape="vector"),
    ),
    ids=("missing-referenced-rim-point", "scalar-quantity-vector-query"),
)
def test_massive_pulley_invalid_references_or_query_shapes_stop_in_validation(
    mutation: PayloadMutation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=mutation)
    assert normalization.terminal is ValidationTerminal.invalid
    assert normalization.ir is None


def test_massive_pulley_wrong_point_ownership_is_invalid_binding_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(
        BASELINE,
        mutation=_set_field(
            "points",
            "point_id",
            LEFT_RIM_POINT_ID,
            "owner_entity_id",
            "bodyA",
        ),
    )
    assert normalization.terminal is ValidationTerminal.accepted
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.invalid
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.invalid_binding
        for issue in execution.compiler_result.issues
    )


def test_entry7_consistent_global_identifier_rename_preserves_graph() -> None:
    original_ir = _build_ir(BASELINE)
    original = MechanicsCompiler().compile(
        original_ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(original_ir),
        approved_assumption_ids=APPROVED_ASSUMPTION_IDS,
    )
    payload = original_ir.model_dump(mode="python", warnings="none")
    identifiers = sorted(_collect_fixture_identifiers(payload))
    mapping = {
        identifier: f"renamedMassivePulleyIdentifier{index}"
        for index, identifier in enumerate(identifiers, start=1)
    }
    renamed_payload = _rename_fixture_identifiers(payload, mapping)
    assert isinstance(renamed_payload, dict)
    renamed_ir = MechanicsProblemIRV1.model_validate(renamed_payload)
    renamed = MechanicsCompiler().compile(
        renamed_ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(renamed_ir),
        approved_assumption_ids=tuple(
            mapping[item] for item in APPROVED_ASSUMPTION_IDS
        ),
    )

    assert original.status is renamed.status is CompilerStatus.ready
    assert original.graph is not None and renamed.graph is not None
    assert original.graph.fingerprint == renamed.graph.fingerprint
    assert original.graph.selected_equation_ids == renamed.graph.selected_equation_ids
    assert tuple(item.equation_id for item in original.graph.equations) == tuple(
        item.equation_id for item in renamed.graph.equations
    )
    assert Counter(item.law_id for item in original.graph.equations) == Counter(
        item.law_id for item in renamed.graph.equations
    )


def test_entry7_preserves_old_broad_underdetermined_massive_pulley_fixture() -> None:
    from test_phase56_mechanics_compiler import (
        test_massive_pulley_suppresses_equal_tension_and_emits_signed_newton_euler,
    )

    test_massive_pulley_suppresses_equal_tension_and_emits_signed_newton_euler()
