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
from engine.solvers.pulley.incline_hanging import (
    InclineHangingPulleySolver,
    _solve_candidate,
)
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


WORLD_FRAME_ID = "worldFrame"
INCLINE_FRAME_ID = "inclineFrame"
INTERVAL_ID = "motionInterval"
VELOCITY = type(ACCELERATION)(length=1, time=-1)
APPROVED_ASSUMPTION_IDS = (
    "accelerationNotOppositeMotion",
    "fixedPulley",
    "idealPulley",
    "inextensibleRope",
    "masslessRope",
)
MOTION_DIRECTION_ASSUMPTION_ID = "accelerationNotOppositeMotion"
SLIDING_DIRECTION_SENTENCE = (
    "Throughout the interval, block A's tangential acceleration is not opposite "
    "its stated direction of motion."
)


def _is_zero_static_drive(
    mass_a_si: float,
    mass_b_si: float,
    gravity_si: float,
    theta_deg: float,
) -> bool:
    incline_drive = mass_a_si * gravity_si * math.sin(math.radians(theta_deg))
    hanging_drive = mass_b_si * gravity_si
    scale = max(abs(incline_drive), abs(hanging_drive), 1.0)
    return abs(incline_drive - hanging_drive) <= 1.0e-12 * scale


@dataclass(frozen=True)
class InclineHangingSource:
    problem_text: str
    mass_a_si: float
    mass_b_si: float
    gravity_si: float
    theta_deg: float
    regime: str
    coefficient: float | None
    motion_sign: int
    query_role: str
    query_body: str
    query_direction_sign: int
    acceleration_not_opposite_motion: bool = False
    static_friction_axis_sign: int | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.mass_a_si, "incline mass"),
            (self.mass_b_si, "hanging mass"),
            (self.gravity_si, "gravity"),
            (self.theta_deg, "incline angle"),
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
        if self.motion_sign not in {-1, 0, 1}:
            raise ValueError("motion sign must be one signed tangent direction")
        if self.regime == "sticking" and self.motion_sign != 0:
            raise ValueError("sticking fixtures must have zero motion sign")
        if self.regime != "sticking" and self.motion_sign == 0:
            raise ValueError("non-sticking fixtures must declare one motion tendency")
        if self.query_role not in {"acceleration", "tension"}:
            raise ValueError("query role must be acceleration or tension")
        if self.query_body not in {"bodyA", "bodyB"}:
            raise ValueError("query body must be bodyA or bodyB")
        if self.query_direction_sign not in {-1, 1}:
            raise ValueError("query direction must be one signed axis direction")
        if self.query_role == "tension" and (
            self.query_body != "bodyB" or self.query_direction_sign != -1
        ):
            raise ValueError("the focused tension query is upward on hanging body B")
        if self.acceleration_not_opposite_motion and not self.is_sliding:
            raise ValueError("the motion-direction assumption is sliding-only")
        if self.static_friction_axis_sign is not None and (
            not self.is_static or self.static_friction_axis_sign not in {-1, 1}
        ):
            raise ValueError("a static friction-axis override is sticking-only and signed")

    @property
    def theta_rad(self) -> float:
        return math.radians(self.theta_deg)

    @property
    def is_static(self) -> bool:
        return self.regime == "sticking"

    @property
    def is_sliding(self) -> bool:
        return self.regime == "sliding"

    @property
    def is_zero_static_drive(self) -> bool:
        return self.is_static and _is_zero_static_drive(
            self.mass_a_si,
            self.mass_b_si,
            self.gravity_si,
            self.theta_deg,
        )

    @property
    def expected_normal_si(self) -> float:
        return self.mass_a_si * self.gravity_si * math.cos(self.theta_rad)

    @property
    def expected_friction_si(self) -> float:
        if self.regime == "inactive":
            return 0.0
        if self.is_static:
            return abs(
                self.mass_a_si * self.gravity_si * math.sin(self.theta_rad)
                - self.mass_b_si * self.gravity_si
            )
        return float(self.coefficient) * self.expected_normal_si

    @property
    def friction_sign(self) -> int:
        if self.regime == "inactive":
            return 0
        if self.is_sliding:
            return -self.motion_sign
        if self.static_friction_axis_sign is not None:
            return self.static_friction_axis_sign
        drive = (
            self.mass_a_si * self.gravity_si * math.sin(self.theta_rad)
            - self.mass_b_si * self.gravity_si
        )
        return -1 if drive >= 0.0 else 1

    @property
    def expected_acceleration_si(self) -> float:
        """Signed +tangent-downslope acceleration; world +y points downward."""

        if self.is_static:
            return 0.0
        signed_friction = self.friction_sign * self.expected_friction_si
        return (
            self.mass_a_si * self.gravity_si * math.sin(self.theta_rad)
            - self.mass_b_si * self.gravity_si
            + signed_friction
        ) / (self.mass_a_si + self.mass_b_si)

    @property
    def expected_tension_si(self) -> float:
        return self.mass_b_si * (
            self.gravity_si + self.expected_acceleration_si
        )

    @property
    def expected_query_value_si(self) -> float:
        if self.query_role == "tension":
            return self.expected_tension_si
        if self.query_body == "bodyA":
            return self.expected_acceleration_si / self.query_direction_sign
        physical_b_acceleration = -self.expected_acceleration_si
        return physical_b_acceleration / self.query_direction_sign

    @property
    def acceleration_a_sign(self) -> int:
        if self.query_role == "acceleration":
            return (
                self.query_direction_sign
                if self.query_body == "bodyA"
                else -self.query_direction_sign
            )
        if self.motion_sign != 0:
            return self.motion_sign
        return 1

    @property
    def acceleration_b_sign(self) -> int:
        return -self.acceleration_a_sign

    @property
    def query_symbol_id(self) -> str:
        if self.query_role == "tension":
            return "tB"
        return "aAT" if self.query_body == "bodyA" else "aBY"

    @property
    def direction_consistent(self) -> bool:
        return self.is_static or (
            self.expected_acceleration_si * self.motion_sign >= -1.0e-12
        )


def _source(
    regime: str,
    *,
    mass_a_si: float,
    mass_b_si: float,
    theta_deg: float,
    coefficient: float | None = None,
    gravity_si: float = 9.81,
    motion_sign: int,
    query_role: str = "acceleration",
    query_body: str = "bodyB",
    query_direction_sign: int | None = None,
    paraphrase_prefix: str = "",
    acceleration_not_opposite_motion: bool | None = None,
    static_friction_axis_sign: int | None = None,
) -> InclineHangingSource:
    carries_direction_assumption = (
        regime == "sliding"
        if acceleration_not_opposite_motion is None
        else acceleration_not_opposite_motion
    )
    query_sign = (
        -1
        if query_role == "tension"
        else (
            (
                (motion_sign if query_body == "bodyA" else -motion_sign)
                if motion_sign
                else 1
            )
            if query_direction_sign is None
            else query_direction_sign
        )
    )
    if regime == "inactive":
        regime_sentences = ("The contact is explicitly frictionless.",)
    elif regime == "sticking":
        natural_friction_sign = (
            -1
            if mass_a_si * math.sin(math.radians(theta_deg)) >= mass_b_si
            else 1
        )
        friction_axis_sign = (
            natural_friction_sign
            if static_friction_axis_sign is None
            else static_friction_axis_sign
        )
        tendency = "downslope" if friction_axis_sign == -1 else "upslope"
        friction_direction = "upslope" if friction_axis_sign == -1 else "downslope"
        if _is_zero_static_drive(
            float(mass_a_si),
            float(mass_b_si),
            float(gravity_si),
            float(theta_deg),
        ):
            static_direction_sentence = (
                "Represent the static-friction component on the "
                f"{friction_direction} tangent axis; its solved magnitude may be zero."
            )
        else:
            static_direction_sentence = (
                f"Block A tends to move {tendency} and static friction acts "
                f"{friction_direction}."
            )
        regime_sentences = (
            "The contact is in the sticking static-friction regime.",
            f"The coefficient of static friction is {float(coefficient):.15g}.",
            "Both particles remain at rest throughout the interval.",
            static_direction_sentence,
        )
    else:
        if motion_sign == 1:
            motion_sentence = (
                "Block A is moving downslope at 1 m/s while block B moves upward; "
                "the direction token is m1down."
            )
            friction_sentence = "Kinetic friction on block A acts upslope."
        else:
            motion_sentence = (
                "Block A is moving upslope at 1 m/s while block B descends; "
                "the direction token is m2down."
            )
            friction_sentence = "Kinetic friction on block A acts downslope."
        regime_sentences = (
            "The contact is in the sliding kinetic-friction regime.",
            f"The coefficient of kinetic friction is {float(coefficient):g}.",
            motion_sentence,
            friction_sentence,
            *((SLIDING_DIRECTION_SENTENCE,) if carries_direction_assumption else ()),
        )
    if query_role == "tension":
        query_sentence = "Find the tension acting upward on block B."
    else:
        if query_body == "bodyA":
            query_direction = "downslope" if query_sign == 1 else "upslope"
            query_sentence = (
                "Find the signed tangential acceleration of block A along the "
                f"{query_direction} direction."
            )
        else:
            query_direction = "downward" if query_sign == 1 else "upward"
            query_sentence = (
                f"Find the signed acceleration of block B along the {query_direction} direction."
            )
    problem_text = " ".join(
        (
            paraphrase_prefix,
            f"Block A has mass {mass_a_si:g} kg.",
            "Block A remains in touching contact with a fixed straight incline.",
            f"The incline angle is {theta_deg:g} deg above horizontal.",
            f"Block B has mass {mass_b_si:g} kg and hangs vertically.",
            f"Take g = {gravity_si:g} m/s^2.",
            *regime_sentences,
            "The blocks are joined by one massless, inextensible rope.",
            "The rope is taut.",
            "The rope wraps over one ideal massless frictionless pulley.",
            "The pulley is fixed and remains at rest.",
            "The rope is attached to block A.",
            "The rope is attached to block B.",
            (
                "The +tangent axis points downslope, the +normal axis points away "
                "from the incline, and the world +y axis points downward."
            ),
            query_sentence,
        )
    ).strip()
    return InclineHangingSource(
        problem_text=problem_text,
        mass_a_si=float(mass_a_si),
        mass_b_si=float(mass_b_si),
        gravity_si=float(gravity_si),
        theta_deg=float(theta_deg),
        regime=regime,
        coefficient=None if coefficient is None else float(coefficient),
        motion_sign=motion_sign,
        query_role=query_role,
        query_body=query_body,
        query_direction_sign=query_sign,
        acceleration_not_opposite_motion=carries_direction_assumption,
        static_friction_axis_sign=static_friction_axis_sign,
    )


FRICTIONLESS_A_DOWN = _source(
    "inactive",
    mass_a_si=10.0,
    mass_b_si=1.0,
    theta_deg=30.0,
    motion_sign=1,
)
FRICTIONLESS_A_DOWN_SIGNED_DOWN_QUERY = _source(
    "inactive",
    mass_a_si=10.0,
    mass_b_si=1.0,
    theta_deg=30.0,
    motion_sign=1,
    query_direction_sign=1,
)
FRICTIONLESS_THETA_ZERO = _source(
    "inactive",
    mass_a_si=1.0,
    mass_b_si=2.0,
    theta_deg=0.0,
    motion_sign=-1,
)
KINETIC_A_DOWN = _source(
    "sliding",
    mass_a_si=10.0,
    mass_b_si=1.0,
    theta_deg=30.0,
    coefficient=0.1,
    motion_sign=1,
)
KINETIC_B_DOWN = _source(
    "sliding",
    mass_a_si=10.0,
    mass_b_si=8.0,
    theta_deg=30.0,
    coefficient=0.2,
    motion_sign=-1,
)
KINETIC_B_DOWN_UP_QUERY = _source(
    "sliding",
    mass_a_si=10.0,
    mass_b_si=8.0,
    theta_deg=30.0,
    coefficient=0.2,
    motion_sign=-1,
    query_direction_sign=-1,
)
KINETIC_TENSION_QUERY = _source(
    "sliding",
    mass_a_si=10.0,
    mass_b_si=8.0,
    theta_deg=30.0,
    coefficient=0.2,
    motion_sign=-1,
    query_role="tension",
)
KINETIC_ZERO_MU = _source(
    "sliding",
    mass_a_si=10.0,
    mass_b_si=1.0,
    theta_deg=30.0,
    coefficient=0.0,
    motion_sign=1,
)
_STATIC_MASS_A = 4.0
_STATIC_MASS_B = 1.0
_STATIC_THETA_DEG = 30.0
_STATIC_BOUNDARY_MU = (
    _STATIC_MASS_A * math.sin(math.radians(_STATIC_THETA_DEG)) - _STATIC_MASS_B
) / (_STATIC_MASS_A * math.cos(math.radians(_STATIC_THETA_DEG)))
STATIC_BOUNDARY = _source(
    "sticking",
    mass_a_si=_STATIC_MASS_A,
    mass_b_si=_STATIC_MASS_B,
    theta_deg=_STATIC_THETA_DEG,
    coefficient=_STATIC_BOUNDARY_MU,
    motion_sign=0,
)
STATIC_HOLD = _source(
    "sticking",
    mass_a_si=_STATIC_MASS_A,
    mass_b_si=_STATIC_MASS_B,
    theta_deg=_STATIC_THETA_DEG,
    coefficient=_STATIC_BOUNDARY_MU * 1.5,
    motion_sign=0,
)
STATIC_ZERO_DRIVE = _source(
    "sticking",
    mass_a_si=2.0,
    mass_b_si=1.0,
    theta_deg=30.0,
    coefficient=0.2,
    motion_sign=0,
)
STATIC_ZERO_DRIVE_OPPOSITE_AXIS = _source(
    "sticking",
    mass_a_si=2.0,
    mass_b_si=1.0,
    theta_deg=30.0,
    coefficient=0.2,
    motion_sign=0,
    static_friction_axis_sign=-STATIC_ZERO_DRIVE.friction_sign,
)
_STATIC_B_HEAVY_MASS_B = 3.0
_STATIC_B_HEAVY_BOUNDARY_MU = (
    _STATIC_B_HEAVY_MASS_B
    - _STATIC_MASS_A * math.sin(math.radians(_STATIC_THETA_DEG))
) / (_STATIC_MASS_A * math.cos(math.radians(_STATIC_THETA_DEG)))
STATIC_BOUNDARY_B_HEAVY = _source(
    "sticking",
    mass_a_si=_STATIC_MASS_A,
    mass_b_si=_STATIC_B_HEAVY_MASS_B,
    theta_deg=_STATIC_THETA_DEG,
    coefficient=_STATIC_B_HEAVY_BOUNDARY_MU,
    motion_sign=0,
)
STATIC_BOUNDARY_B_HEAVY_A_QUERY = _source(
    "sticking",
    mass_a_si=_STATIC_MASS_A,
    mass_b_si=_STATIC_B_HEAVY_MASS_B,
    theta_deg=_STATIC_THETA_DEG,
    coefficient=_STATIC_B_HEAVY_BOUNDARY_MU,
    motion_sign=0,
    query_body="bodyA",
    query_direction_sign=1,
)
STATIC_BELOW_BOUNDARY = _source(
    "sticking",
    mass_a_si=_STATIC_MASS_A,
    mass_b_si=_STATIC_MASS_B,
    theta_deg=_STATIC_THETA_DEG,
    coefficient=_STATIC_BOUNDARY_MU * 0.99,
    motion_sign=0,
)
INCONSISTENT_B_DOWN = _source(
    "sliding",
    mass_a_si=10.0,
    mass_b_si=1.0,
    theta_deg=30.0,
    coefficient=0.1,
    motion_sign=-1,
)
KINETIC_DECELERATING_WITHOUT_DIRECTION_ASSUMPTION = _source(
    "sliding",
    mass_a_si=10.0,
    mass_b_si=1.0,
    theta_deg=30.0,
    coefficient=0.1,
    motion_sign=-1,
    acceleration_not_opposite_motion=False,
)


@dataclass(frozen=True)
class InclineHangingResiduals:
    gravity_tangent: float
    gravity_normal: float
    hanging_weight: float
    incline_tangent_newton: float
    incline_normal_newton: float
    hanging_newton: float
    no_penetration: float
    tension_transfer_a: float
    tension_transfer_b: float
    acceleration_transfer_a: float
    acceleration_transfer_b: float
    equal_tension: float
    rope_acceleration: float
    friction_equality: float
    friction_margin: float
    acceleration_closed_form: float
    tension_closed_form: float
    normal_si: float
    tension_a_si: float
    tension_b_si: float

    @property
    def passed(self) -> bool:
        residuals = (
            self.gravity_tangent,
            self.gravity_normal,
            self.hanging_weight,
            self.incline_tangent_newton,
            self.incline_normal_newton,
            self.hanging_newton,
            self.no_penetration,
            self.tension_transfer_a,
            self.tension_transfer_b,
            self.acceleration_transfer_a,
            self.acceleration_transfer_b,
            self.equal_tension,
            self.rope_acceleration,
            self.friction_equality,
            self.acceleration_closed_form,
            self.tension_closed_form,
        )
        return (
            all(abs(value) <= 1.0e-9 for value in residuals)
            and self.friction_margin >= -1.0e-9
            and self.normal_si >= -1.0e-9
            and self.tension_a_si >= -1.0e-9
            and self.tension_b_si >= -1.0e-9
        )


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport
    invariance: MechanicsMigrationInvarianceComparison
    residuals: InclineHangingResiduals


PayloadMutation = Callable[[dict[str, object]], None]


def _direction(frame_id: str, axis: str, sign: int) -> dict[str, object]:
    return _axis_direction(axis, sign, frame_id=frame_id)


def _draft_payload(source: InclineHangingSource) -> dict[str, object]:
    mass_a_raw = f"{source.mass_a_si:g}"
    mass_b_raw = f"{source.mass_b_si:g}"
    gravity_raw = f"{source.gravity_si:g}"
    theta_raw = f"{source.theta_deg:g}"
    coefficient_raw = (
        None if source.coefficient is None else f"{source.coefficient:.15g}"
    )
    mass_a_quote = f"Block A has mass {mass_a_raw} kg."
    contact_quote = "Block A remains in touching contact with a fixed straight incline."
    angle_quote = f"The incline angle is {theta_raw} deg above horizontal."
    mass_b_quote = f"Block B has mass {mass_b_raw} kg and hangs vertically."
    gravity_quote = f"Take g = {gravity_raw} m/s^2."
    rope_quote = "The blocks are joined by one massless, inextensible rope."
    taut_quote = "The rope is taut."
    wrap_quote = "The rope wraps over one ideal massless frictionless pulley."
    fixed_pulley_quote = "The pulley is fixed and remains at rest."
    attach_a_quote = "The rope is attached to block A."
    attach_b_quote = "The rope is attached to block B."
    orientation_quote = (
        "The +tangent axis points downslope, the +normal axis points away "
        "from the incline, and the world +y axis points downward."
    )
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
        motion_quote = "Both particles remain at rest throughout the interval."
        friction_direction = "upslope" if source.friction_sign == -1 else "downslope"
        if source.is_zero_static_drive:
            friction_quote = (
                "Represent the static-friction component on the "
                f"{friction_direction} tangent axis; its solved magnitude may be zero."
            )
        else:
            tendency = "downslope" if source.friction_sign == -1 else "upslope"
            friction_quote = (
                f"Block A tends to move {tendency} and static friction acts "
                f"{friction_direction}."
            )
    else:
        regime_quote = "The contact is in the sliding kinetic-friction regime."
        coefficient_quote = (
            f"The coefficient of kinetic friction is {float(source.coefficient):g}."
        )
        motion_quote = (
            "Block A is moving downslope at 1 m/s while block B moves upward; "
            "the direction token is m1down."
            if source.motion_sign == 1
            else (
                "Block A is moving upslope at 1 m/s while block B descends; "
                "the direction token is m2down."
            )
        )
        friction_quote = (
            "Kinetic friction on block A acts upslope."
            if source.friction_sign == -1
            else "Kinetic friction on block A acts downslope."
        )
    query_quote = (
        "Find the tension acting upward on block B."
        if source.query_role == "tension"
        else (
            (
                "Find the signed tangential acceleration of block A along the "
                f"{'downslope' if source.query_direction_sign == 1 else 'upslope'} direction."
            )
            if source.query_body == "bodyA"
            else (
                "Find the signed acceleration of block B along the "
                f"{'downward' if source.query_direction_sign == 1 else 'upward'} direction."
            )
        )
    )
    evidence_specs: list[tuple[str, str, str | None]] = [
        ("massAEvidence", mass_a_quote, f"{mass_a_raw} kg"),
        ("contactEvidence", contact_quote, None),
        ("angleEvidence", angle_quote, f"{theta_raw} deg"),
        ("massBEvidence", mass_b_quote, f"{mass_b_raw} kg"),
        ("gravityEvidence", gravity_quote, f"{gravity_raw} m/s^2"),
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
    if source.acceleration_not_opposite_motion:
        evidence_specs.append(
            (
                "accelerationDirectionEvidence",
                SLIDING_DIRECTION_SENTENCE,
                None,
            )
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

    symbol_specs = [
        ("mA", "massA", MASS),
        ("mB", "massB", MASS),
        ("g", "gravity", ACCELERATION),
        ("theta", "inclineAngle", DIMENSIONLESS),
        ("gAT", "gravityTangentA", FORCE),
        ("gAN", "gravityNormalA", FORCE),
        ("wB", "weightB", FORCE),
        ("nA", "normalA", FORCE),
        ("tA", "tensionA", FORCE),
        ("tB", "tensionB", FORCE),
        ("TR", "ropeTensionMagnitude", FORCE),
        ("aAT", "accelerationAT", ACCELERATION),
        ("aAN", "accelerationAN", ACCELERATION),
        ("aBY", "accelerationBY", ACCELERATION),
        ("aR", "ropeAccelerationCoordinate", ACCELERATION),
    ]
    if source.regime != "inactive":
        symbol_specs.extend(
            (("fA", "frictionA", FORCE), ("muA", "coefficientA", DIMENSIONLESS))
        )
    if source.is_sliding:
        symbol_specs.append(("vAT", "velocityAT", VELOCITY))
    symbols = [_symbol(*spec) for spec in symbol_specs]

    quantities = [
        _quantity(
            "massA", "mA", "mass", "bodyA", MASS,
            provenance="explicit_source", evidence_refs=("massAEvidence",),
            raw_value=mass_a_raw, raw_unit="kg",
        ),
        _quantity(
            "massB", "mB", "mass", "bodyB", MASS,
            provenance="explicit_source", evidence_refs=("massBEvidence",),
            raw_value=mass_b_raw, raw_unit="kg",
        ),
        _quantity(
            "gravity", "g", "gravity", "world", ACCELERATION,
            provenance="explicit_source", evidence_refs=("gravityEvidence",),
            raw_value=gravity_raw, raw_unit="m/s^2",
        ),
        _quantity(
            "inclineAngle", "theta", "angle", "incline", DIMENSIONLESS,
            provenance="explicit_source", evidence_refs=("angleEvidence",),
            raw_value=theta_raw, raw_unit="deg",
        ),
        _quantity(
            "gravityTangentA", "gAT", "force", "bodyA", FORCE,
            frame_id=INCLINE_FRAME_ID, interval_id=INTERVAL_ID,
            component="tangential",
            direction=_direction(INCLINE_FRAME_ID, "tangent", 1),
            evidence_refs=("gravityEvidence", "angleEvidence", "orientationEvidence"),
        ),
        _quantity(
            "gravityNormalA", "gAN", "force", "bodyA", FORCE,
            frame_id=INCLINE_FRAME_ID, interval_id=INTERVAL_ID,
            component="normal",
            direction=_direction(INCLINE_FRAME_ID, "normal", -1),
            evidence_refs=("gravityEvidence", "angleEvidence", "orientationEvidence"),
        ),
        _quantity(
            "weightB", "wB", "force", "bodyB", FORCE,
            frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID,
            component="y", direction=_direction(WORLD_FRAME_ID, "y", 1),
            evidence_refs=("gravityEvidence", "orientationEvidence"),
        ),
        _quantity(
            "normalA", "nA", "force", "bodyA", FORCE,
            point_id="contactA", frame_id=INCLINE_FRAME_ID,
            interval_id=INTERVAL_ID, component="normal",
            direction=_direction(INCLINE_FRAME_ID, "normal", 1),
            evidence_refs=("contactEvidence", "orientationEvidence"),
        ),
        _quantity(
            "tensionA", "tA", "force", "bodyA", FORCE,
            frame_id=INCLINE_FRAME_ID, interval_id=INTERVAL_ID,
            component="tangential",
            direction=_direction(INCLINE_FRAME_ID, "tangent", -1),
            evidence_refs=(
                "ropeEvidence", "tautEvidence", "wrapEvidence",
                "attachAEvidence", "orientationEvidence",
            ),
        ),
        _quantity(
            "tensionB", "tB", "force", "bodyB", FORCE,
            frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID,
            component="y", direction=_direction(WORLD_FRAME_ID, "y", -1),
            evidence_refs=(
                "ropeEvidence", "tautEvidence", "wrapEvidence",
                "attachBEvidence", "orientationEvidence",
                *(("queryEvidence",) if source.query_role == "tension" else ()),
            ),
        ),
        _quantity(
            "ropeTensionMagnitude", "TR", "force", "rope", FORCE,
            interval_id=INTERVAL_ID,
            evidence_refs=(
                "ropeEvidence", "wrapEvidence", "attachAEvidence", "attachBEvidence",
            ),
        ),
        _quantity(
            "accelerationAT", "aAT", "acceleration", "bodyA", ACCELERATION,
            frame_id=INCLINE_FRAME_ID, interval_id=INTERVAL_ID,
            component="tangential",
            direction=_direction(
                INCLINE_FRAME_ID, "tangent", source.acceleration_a_sign
            ),
            evidence_refs=(
                "ropeEvidence", "orientationEvidence",
                *(("queryEvidence",) if source.query_role == "acceleration" and source.query_body == "bodyA" else ()),
            ),
        ),
        _quantity(
            "accelerationAN", "aAN", "acceleration", "bodyA", ACCELERATION,
            frame_id=INCLINE_FRAME_ID, interval_id=INTERVAL_ID,
            component="normal",
            direction=_direction(INCLINE_FRAME_ID, "normal", 1),
            evidence_refs=("contactEvidence", "orientationEvidence"),
        ),
        _quantity(
            "accelerationBY", "aBY", "acceleration", "bodyB", ACCELERATION,
            frame_id=WORLD_FRAME_ID, interval_id=INTERVAL_ID,
            component="y",
            direction=_direction(
                WORLD_FRAME_ID, "y", source.acceleration_b_sign
            ),
            evidence_refs=(
                "ropeEvidence", "orientationEvidence",
                *(("queryEvidence",) if source.query_role == "acceleration" and source.query_body == "bodyB" else ()),
            ),
        ),
        _quantity(
            "ropeAccelerationCoordinate", "aR", "acceleration", "rope",
            ACCELERATION, interval_id=INTERVAL_ID,
            evidence_refs=(
                "ropeEvidence", "wrapEvidence", "fixedPulleyEvidence",
                "attachAEvidence", "attachBEvidence",
            ),
        ),
    ]
    if source.regime != "inactive":
        assert coefficient_raw is not None
        quantities.extend(
            (
                _quantity(
                    "frictionA", "fA", "force", "bodyA", FORCE,
                    point_id="contactA", frame_id=INCLINE_FRAME_ID,
                    interval_id=INTERVAL_ID, component="tangential",
                    direction=_direction(
                        INCLINE_FRAME_ID, "tangent", source.friction_sign
                    ),
                    evidence_refs=(
                        "contactEvidence", "regimeEvidence",
                        "frictionDirectionEvidence", "motionEvidence",
                    ),
                ),
                _quantity(
                    "coefficientA", "muA", "coefficient_friction", "bodyA",
                    DIMENSIONLESS, provenance="explicit_source",
                    evidence_refs=("coefficientEvidence",),
                    raw_value=coefficient_raw, raw_unit="",
                ),
            )
        )
    if source.is_sliding:
        quantities.append(
            _quantity(
                "velocityAT", "vAT", "velocity", "bodyA", VELOCITY,
                frame_id=INCLINE_FRAME_ID, interval_id=INTERVAL_ID,
                component="tangential",
                direction=_direction(
                    INCLINE_FRAME_ID, "tangent", source.motion_sign
                ),
                provenance="explicit_source", evidence_refs=("motionEvidence",),
                raw_value="1", raw_unit="m/s",
            )
        )

    contact_quantity_ids = ["normalA", "accelerationAN"]
    friction_quantity_ids: list[str] = []
    if source.regime != "inactive":
        contact_quantity_ids.extend(("frictionA", "coefficientA"))
        friction_quantity_ids.extend(("frictionA", "normalA", "coefficientA"))
    states: list[dict[str, object]] = [
        {
            "state_condition_id": "ropeTautState", "kind": "rope", "state": "taut",
            "subject_id": "rope", "interval_id": INTERVAL_ID,
            "quantity_ids": [], "evidence_refs": ["tautEvidence"],
        },
        {
            "state_condition_id": "pulleyFixedState", "kind": "motion",
            "state": "at_rest", "subject_id": "pulley",
            "interval_id": INTERVAL_ID, "quantity_ids": [],
            "evidence_refs": ["fixedPulleyEvidence"],
        },
        {
            "state_condition_id": "contactState", "kind": "contact",
            "state": "touching", "subject_id": "bodyA",
            "interval_id": INTERVAL_ID,
            "quantity_ids": ["normalA", "accelerationAN"],
            "evidence_refs": ["contactEvidence"],
        },
        {
            "state_condition_id": "inclineFixedState", "kind": "motion",
            "state": "at_rest", "subject_id": "incline",
            "interval_id": INTERVAL_ID, "quantity_ids": [],
            "evidence_refs": ["contactEvidence"],
        },
        {
            "state_condition_id": "frictionState", "kind": "friction",
            "state": source.regime, "subject_id": "bodyA",
            "interval_id": INTERVAL_ID, "quantity_ids": friction_quantity_ids,
            "evidence_refs": ["regimeEvidence"],
        },
    ]
    if source.regime != "inactive":
        states.append(
            {
                "state_condition_id": "bodyMotionState", "kind": "motion",
                "state": "at_rest" if source.is_static else "moving",
                "subject_id": "bodyA", "interval_id": INTERVAL_ID,
                "quantity_ids": [] if source.is_static else ["velocityAT"],
                "evidence_refs": ["motionEvidence"],
            }
        )

    query_quantity_id = (
        "tensionB"
        if source.query_role == "tension"
        else (
            "accelerationAT" if source.query_body == "bodyA" else "accelerationBY"
        )
    )
    query_dimension = FORCE if source.query_role == "tension" else ACCELERATION
    query_subject_id = "bodyB" if source.query_role == "tension" else source.query_body
    query_frame_id = (
        WORLD_FRAME_ID
        if query_subject_id == "bodyB"
        else INCLINE_FRAME_ID
    )
    query_component = "y" if query_subject_id == "bodyB" else "tangential"
    query_axis = "y" if query_subject_id == "bodyB" else "tangent"
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en", "correction_revision": 0,
            "system_type": "diagnosticInclineHangingLabel",
            "subtype": "diagnosticDirectionLabel",
            "model_id": "sameFixtureInclineHangingTest",
            "source_text_sha256": hashlib.sha256(
                source.problem_text.encode("utf-8")
            ).hexdigest(),
        },
        "source_assets": [],
        "source_evidence": evidence,
        "entities": [
            {"entity_id": "bodyA", "primitive": "particle", "evidence_refs": ["massAEvidence", "contactEvidence", "attachAEvidence"]},
            {"entity_id": "bodyB", "primitive": "particle", "evidence_refs": ["massBEvidence", "attachBEvidence"]},
            {"entity_id": "incline", "primitive": "incline", "evidence_refs": ["contactEvidence", "angleEvidence", "orientationEvidence"]},
            {"entity_id": "rope", "primitive": "rope", "evidence_refs": ["ropeEvidence", "tautEvidence", "wrapEvidence", "attachAEvidence", "attachBEvidence"]},
            {"entity_id": "pulley", "primitive": "pulley", "evidence_refs": ["wrapEvidence", "fixedPulleyEvidence"]},
            {"entity_id": "world", "primitive": "environment", "evidence_refs": ["gravityEvidence", "orientationEvidence"]},
        ],
        "points": [
            {"point_id": "contactA", "role": "contact", "owner_entity_id": "bodyA", "frame_id": INCLINE_FRAME_ID, "evidence_refs": ["contactEvidence"]}
        ],
        "reference_frames": [
            {
                "frame_id": WORLD_FRAME_ID, "frame_type": "cartesian_2d",
                "origin": {"kind": "world"},
                "axes": [
                    _axis_binding("x", frame_id=WORLD_FRAME_ID),
                    _axis_binding("y", frame_id=WORLD_FRAME_ID),
                ],
                "evidence_refs": ["orientationEvidence"],
            },
            {
                "frame_id": INCLINE_FRAME_ID, "frame_type": "tangential_normal",
                "origin": {"kind": "entity", "entity_id": "incline"},
                "axes": [
                    _axis_binding("tangent", frame_id=INCLINE_FRAME_ID),
                    _axis_binding("normal", frame_id=INCLINE_FRAME_ID),
                ],
                "parent_frame_id": WORLD_FRAME_ID,
                "evidence_refs": ["orientationEvidence"],
            },
        ],
        "motion_intervals": [
            {
                "interval_id": INTERVAL_ID, "order": 1,
                "subject_ids": ["bodyA", "bodyB", "incline", "rope", "pulley", "world"],
                "evidence_refs": ["contactEvidence", "angleEvidence", "regimeEvidence", "ropeEvidence", "tautEvidence", "wrapEvidence", "fixedPulleyEvidence", "attachAEvidence", "attachBEvidence"],
            }
        ],
        "events": [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": [
            {"relation_id": "angleOfIncline", "kind": "angle", "participant_ids": ["incline", "world"], "quantity_ids": ["inclineAngle"], "evidence_refs": ["angleEvidence", "orientationEvidence"]},
            {"relation_id": "ropeWrap", "kind": "wraps", "participant_ids": ["rope", "pulley"], "quantity_ids": ["ropeTensionMagnitude", "ropeAccelerationCoordinate"], "interval_id": INTERVAL_ID, "evidence_refs": ["wrapEvidence"]},
            {"relation_id": "ropeAttachedA", "kind": "attached", "participant_ids": ["rope", "bodyA"], "quantity_ids": ["tensionA", "accelerationAT", "ropeTensionMagnitude", "ropeAccelerationCoordinate"], "interval_id": INTERVAL_ID, "evidence_refs": ["attachAEvidence"]},
            {"relation_id": "ropeAttachedB", "kind": "attached", "participant_ids": ["rope", "bodyB"], "quantity_ids": ["tensionB", "accelerationBY", "ropeTensionMagnitude", "ropeAccelerationCoordinate"], "interval_id": INTERVAL_ID, "evidence_refs": ["attachBEvidence"]},
        ],
        "interactions": [
            {"interaction_id": "gravityA", "kind": "gravity", "participant_ids": ["bodyA", "world"], "frame_id": INCLINE_FRAME_ID, "interval_id": INTERVAL_ID, "quantity_ids": ["massA", "gravity", "gravityTangentA", "gravityNormalA"], "evidence_refs": ["massAEvidence", "gravityEvidence", "angleEvidence", "orientationEvidence"]},
            {"interaction_id": "gravityB", "kind": "gravity", "participant_ids": ["bodyB", "world"], "frame_id": WORLD_FRAME_ID, "interval_id": INTERVAL_ID, "quantity_ids": ["massB", "gravity", "weightB"], "evidence_refs": ["massBEvidence", "gravityEvidence", "orientationEvidence"]},
            {"interaction_id": "contactInteraction", "kind": "contact", "participant_ids": ["bodyA", "incline"], "point_ids": ["contactA"], "frame_id": INCLINE_FRAME_ID, "interval_id": INTERVAL_ID, "quantity_ids": contact_quantity_ids, "evidence_refs": ["contactEvidence", "regimeEvidence"]},
            {"interaction_id": "ropeTension", "kind": "rope_tension", "participant_ids": ["bodyA", "bodyB", "rope", "pulley"], "interval_id": INTERVAL_ID, "quantity_ids": ["tensionA", "tensionB", "accelerationAT", "accelerationBY", "ropeTensionMagnitude", "ropeAccelerationCoordinate"], "evidence_refs": ["ropeEvidence", "tautEvidence", "wrapEvidence", "attachAEvidence", "attachBEvidence", "orientationEvidence"]},
        ],
        "constraints": [],
        "state_conditions": states,
        "queries": [
            {
                "query_id": "queryB",
                "target": {
                    "role": "force" if source.query_role == "tension" else "acceleration",
                    "subject_id": query_subject_id, "frame_id": query_frame_id,
                    "interval_id": INTERVAL_ID, "component": query_component,
                    "direction": _direction(query_frame_id, query_axis, -1 if source.query_role == "tension" else source.query_direction_sign),
                    "target_quantity_id": query_quantity_id,
                },
                "output_unit": "N" if source.query_role == "tension" else "m/s^2",
                "output_dimension": query_dimension.model_dump(mode="json"),
                "shape": "scalar", "evidence_refs": ["queryEvidence"],
            }
        ],
        "principle_hints": [],
        "assumptions": [
            {"assumption_id": "masslessRope", "kind": "massless_rope", "subject_id": "rope", "interval_id": INTERVAL_ID, "disposition": "approved", "reason": "The source explicitly identifies one massless rope.", "evidence_refs": ["ropeEvidence"]},
            {"assumption_id": "inextensibleRope", "kind": "inextensible_rope", "subject_id": "rope", "interval_id": INTERVAL_ID, "disposition": "approved", "reason": "The source explicitly identifies one inextensible rope.", "evidence_refs": ["ropeEvidence"]},
            {"assumption_id": "fixedPulley", "kind": "fixed_pulley", "subject_id": "pulley", "interval_id": INTERVAL_ID, "disposition": "approved", "reason": "The source explicitly fixes the pulley center.", "evidence_refs": ["fixedPulleyEvidence"]},
            {"assumption_id": "idealPulley", "kind": "ideal_massless_frictionless_pulley", "subject_id": "pulley", "interval_id": INTERVAL_ID, "disposition": "approved", "reason": "The source explicitly identifies an ideal pulley.", "evidence_refs": ["wrapEvidence"]},
            *(
                (
                    {
                        "assumption_id": MOTION_DIRECTION_ASSUMPTION_ID,
                        "kind": "acceleration_not_opposite_motion",
                        "subject_id": "bodyA",
                        "interval_id": INTERVAL_ID,
                        "disposition": "approved",
                        "reason": (
                            "The source explicitly states that tangential acceleration "
                            "is not opposite the motion direction."
                        ),
                        "evidence_refs": [
                            "accelerationDirectionEvidence",
                            "motionEvidence",
                        ],
                    },
                )
                if source.acceleration_not_opposite_motion
                else ()
            ),
        ],
        "ambiguities": [],
        "figure_dependency": {"level": "none", "missing_information": [], "evidence_refs": []},
        "unsupported_features": [],
    }


def _normalize(
    source: InclineHangingSource,
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


def _build_ir(source: InclineHangingSource) -> MechanicsProblemIRV1:
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
    source: InclineHangingSource,
    values: dict[str, float],
) -> InclineHangingResiduals:
    required = {
        "gAT", "gAN", "wB", "nA", "tA", "tB",
        "TR", "aAT", "aAN", "aBY", "aR",
    }
    if source.regime != "inactive":
        required.add("fA")
    assert required.issubset(values)
    friction = 0.0 if source.regime == "inactive" else values["fA"]
    physical_a_tangent = source.acceleration_a_sign * values["aAT"]
    physical_b_down = source.acceleration_b_sign * values["aBY"]
    signed_friction = source.friction_sign * friction
    friction_equality = (
        friction - float(source.coefficient) * values["nA"]
        if source.is_sliding
        else 0.0
    )
    friction_margin = (
        float(source.coefficient) * values["nA"] - friction
        if source.is_static
        else 0.0
    )
    return InclineHangingResiduals(
        gravity_tangent=(
            values["gAT"]
            - source.mass_a_si * source.gravity_si * math.sin(source.theta_rad)
        ),
        gravity_normal=(
            values["gAN"]
            - source.mass_a_si * source.gravity_si * math.cos(source.theta_rad)
        ),
        hanging_weight=values["wB"] - source.mass_b_si * source.gravity_si,
        incline_tangent_newton=(
            values["gAT"]
            - values["tA"]
            + signed_friction
            - source.mass_a_si * physical_a_tangent
        ),
        incline_normal_newton=(
            values["nA"]
            - values["gAN"]
            - source.mass_a_si * values["aAN"]
        ),
        hanging_newton=(
            values["wB"]
            - values["tB"]
            - source.mass_b_si * physical_b_down
        ),
        no_penetration=values["aAN"],
        tension_transfer_a=values["tA"] - values["TR"],
        tension_transfer_b=values["tB"] - values["TR"],
        acceleration_transfer_a=physical_a_tangent - values["aR"],
        acceleration_transfer_b=physical_b_down + values["aR"],
        equal_tension=values["tA"] - values["tB"],
        rope_acceleration=physical_a_tangent + physical_b_down,
        friction_equality=friction_equality,
        friction_margin=friction_margin,
        acceleration_closed_form=(
            physical_a_tangent - source.expected_acceleration_si
        ),
        tension_closed_form=values["tA"] - source.expected_tension_si,
        normal_si=values["nA"],
        tension_a_si=values["tA"],
        tension_b_si=values["tB"],
    )


def _legacy_answer_value(result: SolverResult, symbol: str) -> float:
    answer = next(item for item in result.answers if item.symbol == symbol)
    assert type(answer.numeric) is float
    return answer.numeric


def _observe_legacy(
    source: InclineHangingSource,
) -> tuple[LegacyObservation, SolverResult]:
    knowns = {
        "m1": Quantity("m1", source.mass_a_si, "kg"),
        "m2": Quantity("m2", source.mass_b_si, "kg"),
        "g": Quantity("g", source.gravity_si, "m/s^2"),
        "theta": Quantity("theta", source.theta_deg, "deg"),
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
        raw_text=source.problem_text,
        system_type="pulley_incline_hanging",
        pulley_topology="incline_hanging",
        friction_type=friction_type,
        knowns=knowns,
        unknowns=["acceleration", "tension"],
        requested_outputs=["acceleration", "tension"],
    )
    result = InclineHangingPulleySolver().solve(problem)
    assert result.ok is True, result.unsupported_reason
    assert result.verification.passed is True
    delivered_acceleration = _legacy_answer_value(result, "a")
    delivered_tension = _legacy_answer_value(result, "T")
    if source.is_static:
        legacy_acceleration_magnitude = 0.0
        tension = source.mass_b_si * source.gravity_si
        friction = source.expected_friction_si
    else:
        legacy_direction = "m1_down" if source.motion_sign == 1 else "m2_down"
        (
            legacy_acceleration_magnitude,
            tension,
            _,
            _,
        ) = _solve_candidate(
            source.mass_a_si,
            source.mass_b_si,
            source.theta_rad,
            0.0 if source.regime == "inactive" else float(source.coefficient),
            source.gravity_si,
            legacy_direction,
        )
        friction = source.expected_friction_si
    assert delivered_acceleration == pytest.approx(
        round(legacy_acceleration_magnitude, 6),
        rel=0.0,
        abs=1.0e-12,
    )
    assert delivered_tension == pytest.approx(
        round(tension, 6),
        rel=0.0,
        abs=1.0e-12,
    )
    if source.regime != "inactive":
        delivered_friction = _legacy_answer_value(
            result,
            "f_s" if source.is_static else "f_k",
        )
        assert delivered_friction == pytest.approx(
            round(friction, 6),
            rel=0.0,
            abs=1.0e-12,
        )
    physical_a_tangent = source.motion_sign * legacy_acceleration_magnitude
    residual_passed = (
        math.isclose(
            physical_a_tangent,
            source.expected_acceleration_si,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
        and math.isclose(
            tension,
            source.expected_tension_si,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
        and math.isclose(
            friction,
            source.expected_friction_si,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
    )
    assert residual_passed is True
    selected = (
        tension
        if source.query_role == "tension"
        else (
            physical_a_tangent / source.query_direction_sign
            if source.query_body == "bodyA"
            else -physical_a_tangent / source.query_direction_sign
        )
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
            "inclineHanging"
            + hashlib.sha256(source.problem_text.encode("utf-8")).hexdigest()[:32]
        ),
        diagnostic_kernel_id="inclineHangingPulleyDirectV1",
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
            b"unrelated diagnostic incline-hanging wording"
        ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


def _paraphrased_ir(source: InclineHangingSource) -> MechanicsProblemIRV1:
    paraphrase = _source(
        source.regime,
        mass_a_si=source.mass_a_si,
        mass_b_si=source.mass_b_si,
        theta_deg=source.theta_deg,
        coefficient=source.coefficient,
        gravity_si=source.gravity_si,
        motion_sign=source.motion_sign,
        query_role=source.query_role,
        query_body=source.query_body,
        query_direction_sign=source.query_direction_sign,
        acceleration_not_opposite_motion=(
            source.acceleration_not_opposite_motion
        ),
        static_friction_axis_sign=source.static_friction_axis_sign,
        paraphrase_prefix=(
            "Using an equivalent source paraphrase, model this same typed system."
        ),
    )
    return _build_ir(paraphrase)


def _same_fixture(source: InclineHangingSource) -> SameFixtureEvidence:
    ir = _build_ir(source)
    assert "raw_text" not in type(ir).model_fields
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
    report = build_legacy_differential_report(
        execution.solve_result,
        observation,
    )
    assert build_generic_result_invariance_signature(
        execution.solve_result
    ) == frozen_signature
    assert execution.compiler_result.graph.fingerprint == frozen_graph
    assert execution.solve_result.plan.plan_fingerprint == frozen_plan
    assert tuple(sorted(_candidate_values(execution).items())) == frozen_values
    assert _independent_residuals(source, _candidate_values(execution)) == residuals

    changed = _diagnostic_variant(ir, remove=False)
    removed = _diagnostic_variant(ir, remove=True)
    paraphrased = _paraphrased_ir(source)
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
            LabelledIRProbeVariant(
                label="rawTextParaphrase",
                kind=InvarianceVariantKind.raw_text_paraphrase,
                ir=paraphrased,
            ),
        ),
        approved_assumption_ids=APPROVED_ASSUMPTION_IDS,
    )
    return SameFixtureEvidence(
        registry_entry="pulley_incline_hanging",
        ir=ir,
        execution=execution,
        observation=observation,
        report=report,
        invariance=invariance,
        residuals=residuals,
    )


POSITIVE_CASES = (
    FRICTIONLESS_A_DOWN,
    FRICTIONLESS_A_DOWN_SIGNED_DOWN_QUERY,
    FRICTIONLESS_THETA_ZERO,
    KINETIC_A_DOWN,
    KINETIC_B_DOWN,
    KINETIC_B_DOWN_UP_QUERY,
    KINETIC_TENSION_QUERY,
    KINETIC_ZERO_MU,
    STATIC_HOLD,
    STATIC_ZERO_DRIVE,
    STATIC_ZERO_DRIVE_OPPOSITE_AXIS,
    STATIC_BOUNDARY,
    STATIC_BOUNDARY_B_HEAVY,
    STATIC_BOUNDARY_B_HEAVY_A_QUERY,
)


@pytest.mark.slow
@pytest.mark.parametrize(
    "source",
    POSITIVE_CASES,
    ids=(
        "frictionless-a-down-b-up",
        "frictionless-opposite-signed-query",
        "frictionless-zero-angle-endpoint",
        "kinetic-a-down-b-up",
        "kinetic-b-down-a-up",
        "kinetic-signed-upward-query",
        "kinetic-tension-query",
        "kinetic-zero-mu-reduction",
        "static-strictly-inside-bound",
        "static-zero-drive",
        "static-zero-drive-opposite-friction-axis",
        "static-exact-boundary",
        "static-exact-boundary-b-heavy",
        "static-exact-boundary-b-heavy-body-a-query",
    ),
)
def test_incline_hanging_same_fixture_full_parity(
    source: InclineHangingSource,
) -> None:
    evidence = _same_fixture(source)
    execution = evidence.execution
    compiler = execution.compiler_result
    result = execution.solve_result
    assert evidence.registry_entry == "pulley_incline_hanging"
    assert compiler is not None and compiler.graph is not None
    assert execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert execution.solve_terminal is MechanicsSolveTerminal.solved

    expected_laws = Counter(
        {
            "incline_gravity_tangent_projection": 1,
            "incline_gravity_normal_projection": 1,
            "particle_weight": 1,
            "particle_newton_second": 3,
            "fixed_contact_no_penetration": 1,
            "contact_normal_bound": 1,
            "rope_attachment_tension_transfer": 2,
            "rope_attachment_acceleration_transfer": 2,
        }
    )
    if source.is_static:
        expected_laws.update(
            {
                "contact_friction_bound": 2,
                "incline_sticking_static_acceleration": 1,
            }
        )
    elif source.is_sliding:
        expected_laws["contact_sliding_friction"] = 1
        expected_laws["incline_hanging_sliding_direction_consistency"] = 1
    assert Counter(item.law_id for item in compiler.graph.equations) == expected_laws

    tension_transfers = tuple(
        item
        for item in compiler.graph.equations
        if item.law_id == "rope_attachment_tension_transfer"
    )
    assert len(tension_transfers) == 2
    for equation in tension_transfers:
        assert equation.assumption_ids == ("idealPulley", "masslessRope")
        assert {"ropeWrap", "ropeTautState"}.issubset(equation.constraint_ids)
        attachment_ids = {"ropeAttachedA", "ropeAttachedB"}.intersection(
            equation.constraint_ids
        )
        assert len(attachment_ids) == 1
        attachment_id = next(iter(attachment_ids))
        attachment_evidence_id = (
            "attachAEvidence"
            if attachment_id == "ropeAttachedA"
            else "attachBEvidence"
        )
        assert {
            attachment_evidence_id,
            "ropeEvidence",
            "tautEvidence",
            "wrapEvidence",
        }.issubset(equation.source_evidence_ids)

    acceleration_transfers = tuple(
        item
        for item in compiler.graph.equations
        if item.law_id == "rope_attachment_acceleration_transfer"
    )
    assert len(acceleration_transfers) == 2
    for equation in acceleration_transfers:
        assert equation.assumption_ids == ("fixedPulley", "inextensibleRope")
        assert {
            "pulleyFixedState",
            "ropeWrap",
            "ropeTautState",
        }.issubset(equation.constraint_ids)
        attachment_ids = {"ropeAttachedA", "ropeAttachedB"}.intersection(
            equation.constraint_ids
        )
        assert len(attachment_ids) == 1
        attachment_id = next(iter(attachment_ids))
        attachment_evidence_id = (
            "attachAEvidence"
            if attachment_id == "ropeAttachedA"
            else "attachBEvidence"
        )
        assert {
            attachment_evidence_id,
            "fixedPulleyEvidence",
            "ropeEvidence",
            "wrapEvidence",
        }.issubset(equation.source_evidence_ids)

    direction_equations = tuple(
        item
        for item in compiler.graph.equations
        if item.law_id == "incline_hanging_sliding_direction_consistency"
    )
    if source.is_sliding:
        assert len(direction_equations) == 1
        direction_equation = direction_equations[0]
        assert direction_equation.assumption_ids == (
            MOTION_DIRECTION_ASSUMPTION_ID,
        )
        assert direction_equation.constraint_ids == (
            "bodyMotionState",
            "frictionState",
        )
        assert "motionEvidence" in direction_equation.source_evidence_ids
    else:
        assert direction_equations == ()

    observed_quantity_ids = {
        quantity_id
        for equation in compiler.graph.equations
        for quantity_id in equation.source_quantity_ids
    }
    expected_quantity_ids = {
        "massA", "massB", "gravity", "inclineAngle",
        "gravityTangentA", "gravityNormalA", "weightB", "normalA",
        "tensionA", "tensionB", "ropeTensionMagnitude",
        "accelerationAT", "accelerationAN", "accelerationBY",
        "ropeAccelerationCoordinate",
    }
    if source.regime != "inactive":
        expected_quantity_ids.update(("frictionA", "coefficientA"))
    if source.is_sliding:
        expected_quantity_ids.add("velocityAT")
    assert expected_quantity_ids.issubset(observed_quantity_ids)
    assert evidence.ir.constraints == ()
    assert next(
        item for item in evidence.ir.motion_intervals
        if item.interval_id == INTERVAL_ID
    ).frame_id is None
    rope_interaction = next(
        item for item in evidence.ir.interactions
        if item.interaction_id == "ropeTension"
    )
    assert rope_interaction.frame_id is None
    quantity_by_id = {item.quantity_id: item for item in evidence.ir.quantities}
    assert quantity_by_id["accelerationAT"].frame_id == INCLINE_FRAME_ID
    assert quantity_by_id["accelerationBY"].frame_id == WORLD_FRAME_ID
    assert quantity_by_id["tensionA"].frame_id == INCLINE_FRAME_ID
    assert quantity_by_id["tensionB"].frame_id == WORLD_FRAME_ID
    for intermediate_id in (
        "ropeTensionMagnitude",
        "ropeAccelerationCoordinate",
    ):
        intermediate = quantity_by_id[intermediate_id]
        assert intermediate.subject_id == "rope"
        assert intermediate.frame_id is None
        assert intermediate.interval_id == INTERVAL_ID
        assert intermediate.component.value == "unspecified"
        assert intermediate.direction is None
        assert intermediate.si_value is None
        assert all(
            query.target.target_quantity_id != intermediate_id
            for query in evidence.ir.queries
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
        abs=1.0e-9,
    )
    assert candidate.query_value_si == pytest.approx(
        evidence.observation.selected_scalar_si,
        rel=0.0,
        abs=1.0e-9,
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
    assert residual_checks[0].measured_error == pytest.approx(0.0, abs=1.0e-9)

    assert evidence.residuals.passed is True
    if source in {
        STATIC_BOUNDARY,
        STATIC_BOUNDARY_B_HEAVY,
        STATIC_BOUNDARY_B_HEAVY_A_QUERY,
    }:
        assert evidence.residuals.friction_margin == pytest.approx(
            0.0, rel=0.0, abs=1.0e-9
        )
    if source is KINETIC_ZERO_MU:
        assert evidence.residuals.friction_equality == pytest.approx(
            0.0, rel=0.0, abs=1.0e-9
        )
        assert candidate.query_value_si == pytest.approx(
            FRICTIONLESS_A_DOWN.expected_query_value_si,
            rel=0.0,
            abs=1.0e-9,
        )
    assert source.direction_consistent is True
    assert evidence.observation.residual_passed is True
    assert len(evidence.observation.complete_candidate_scalars_si) == 1
    assert evidence.report.status is DifferentialStatus.full_parity
    assert evidence.report.discrepancies == ()
    assert evidence.report.observation_terminal is LegacyTerminal.solved
    assert evidence.report.generic_terminal is MechanicsSolveTerminal.solved
    assert evidence.invariance.all_invariant is True, tuple(
        {
            "label": item.label,
            "calculation_fingerprint_matches": (
                item.calculation_fingerprint_matches
            ),
            "compiler_result_matches": item.compiler_result_matches,
            "terminal_matches": item.terminal_matches,
            "failure_matches": item.failure_matches,
            "solve_shape_matches": item.solve_shape_matches,
            "generic_signature_matches": item.generic_signature_matches,
            "variant_terminal": item.variant_terminal.value,
            "variant_failure": (
                None
                if item.variant_failure is None
                else item.variant_failure.value
            ),
            "differing_fields": (
                ()
                if item.generic_comparison is None
                else tuple(
                    field.value
                    for field in item.generic_comparison.differing_fields
                )
            ),
        }
        for item in evidence.invariance.variants
    )
    assert all(item.matches_baseline for item in evidence.invariance.variants)


def _forbid_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> SolverResult:
        raise AssertionError("a rejected generic incline-hanging case must not call legacy")

    monkeypatch.setattr(InclineHangingPulleySolver, "solve", forbidden)


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


def _remove_rope_interaction_and_wrap(payload: dict[str, object]) -> None:
    """Remove both topology carriers to exercise the combined fail-closed path."""

    _remove_record(
        "interactions",
        "interaction_id",
        "ropeTension",
    )(payload)
    _remove_record(
        "geometry",
        "relation_id",
        "ropeWrap",
    )(payload)


def _clear_evidence(
    collection_name: str,
    id_field: str,
    record_id: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(payload, collection_name, id_field, record_id)["evidence_refs"] = []

    return mutate


def _remove_quantity_from_relation(
    relation_id: str,
    quantity_id: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        relation = _record(payload, "geometry", "relation_id", relation_id)
        quantity_ids = relation["quantity_ids"]
        assert isinstance(quantity_ids, list)
        relation["quantity_ids"] = [
            item for item in quantity_ids if item != quantity_id
        ]

    return mutate


def _set_quantity_frame(
    quantity_id: str,
    frame_id: str | None,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        quantity = _record(payload, "quantities", "quantity_id", quantity_id)
        if frame_id is None:
            quantity.pop("frame_id", None)
        else:
            quantity["frame_id"] = frame_id

    return mutate


def _clear_motion_carrier(payload: dict[str, object]) -> None:
    state = _record(
        payload,
        "state_conditions",
        "state_condition_id",
        "bodyMotionState",
    )
    state["quantity_ids"] = []


def _same_direction_friction(payload: dict[str, object]) -> None:
    friction = _record(payload, "quantities", "quantity_id", "frictionA")
    friction["direction"] = _direction(
        INCLINE_FRAME_ID,
        "tangent",
        KINETIC_A_DOWN.motion_sign,
    )


def _append_rope_participant(payload: dict[str, object]) -> None:
    interaction = _record(
        payload,
        "interactions",
        "interaction_id",
        "ropeTension",
    )
    participants = interaction["participant_ids"]
    assert isinstance(participants, list)
    participants.append("world")


def _set_tension_b_wrong_direction(payload: dict[str, object]) -> None:
    tension = _record(payload, "quantities", "quantity_id", "tensionB")
    tension["direction"] = _direction(WORLD_FRAME_ID, "y", 1)


def _set_shared_interval_frame(payload: dict[str, object]) -> None:
    interval = _record(
        payload,
        "motion_intervals",
        "interval_id",
        INTERVAL_ID,
    )
    interval["frame_id"] = INCLINE_FRAME_ID


def _query_rope_intermediate(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    query["target"] = {
        "role": "force",
        "subject_id": "rope",
        "interval_id": INTERVAL_ID,
        "component": "unspecified",
        "target_quantity_id": "ropeTensionMagnitude",
    }
    query["output_unit"] = "N"
    query["output_dimension"] = FORCE.model_dump(mode="json")


def _query_rope_acceleration_intermediate(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    query["target"] = {
        "role": "acceleration",
        "subject_id": "rope",
        "interval_id": INTERVAL_ID,
        "component": "unspecified",
        "target_quantity_id": "ropeAccelerationCoordinate",
    }
    query["output_unit"] = "m/s^2"
    query["output_dimension"] = ACCELERATION.model_dump(mode="json")


def _query_normal_force(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    query["target"] = {
        "role": "force",
        "subject_id": "bodyA",
        "point_id": "contactA",
        "frame_id": INCLINE_FRAME_ID,
        "interval_id": INTERVAL_ID,
        "component": "normal",
        "direction": _direction(INCLINE_FRAME_ID, "normal", 1),
        "target_quantity_id": "normalA",
    }
    query["output_unit"] = "N"
    query["output_dimension"] = FORCE.model_dump(mode="json")


def _query_gravity_projection(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    query["target"] = {
        "role": "force",
        "subject_id": "bodyA",
        "frame_id": INCLINE_FRAME_ID,
        "interval_id": INTERVAL_ID,
        "component": "tangential",
        "direction": _direction(INCLINE_FRAME_ID, "tangent", 1),
        "target_quantity_id": "gravityTangentA",
    }
    query["output_unit"] = "N"
    query["output_dimension"] = FORCE.model_dump(mode="json")


def _query_normal_acceleration(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    query["target"] = {
        "role": "acceleration",
        "subject_id": "bodyA",
        "frame_id": INCLINE_FRAME_ID,
        "interval_id": INTERVAL_ID,
        "component": "normal",
        "direction": _direction(INCLINE_FRAME_ID, "normal", 1),
        "target_quantity_id": "accelerationAN",
    }
    query["output_unit"] = "m/s^2"
    query["output_dimension"] = ACCELERATION.model_dump(mode="json")


def _query_known_mass(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    query["target"] = {
        "role": "mass",
        "subject_id": "bodyA",
        "component": "unspecified",
        "target_quantity_id": "massA",
    }
    query["output_unit"] = "kg"
    query["output_dimension"] = MASS.model_dump(mode="json")


def _query_active_friction(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    query["target"] = {
        "role": "force",
        "subject_id": "bodyA",
        "point_id": "contactA",
        "frame_id": INCLINE_FRAME_ID,
        "interval_id": INTERVAL_ID,
        "component": "tangential",
        "direction": _direction(
            INCLINE_FRAME_ID,
            "tangent",
            KINETIC_A_DOWN.friction_sign,
        ),
        "target_quantity_id": "frictionA",
    }
    query["output_unit"] = "N"
    query["output_dimension"] = FORCE.model_dump(mode="json")


def _query_vector_acceleration(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryB")
    query["shape"] = "vector"


@dataclass(frozen=True)
class CompilerRejectCase:
    label: str
    source: InclineHangingSource
    mutation: PayloadMutation


COMPILER_REJECT_CASES = (
    CompilerRejectCase(
        "angle-relation-unevidenced",
        KINETIC_A_DOWN,
        _clear_evidence("geometry", "relation_id", "angleOfIncline"),
    ),
    CompilerRejectCase(
        "wrap-unevidenced",
        KINETIC_A_DOWN,
        _clear_evidence("geometry", "relation_id", "ropeWrap"),
    ),
    CompilerRejectCase(
        "rope-interaction-and-wrap-both-missing",
        KINETIC_A_DOWN,
        _remove_rope_interaction_and_wrap,
    ),
    CompilerRejectCase(
        "attachment-missing-local-acceleration-transfer",
        KINETIC_A_DOWN,
        _remove_quantity_from_relation("ropeAttachedA", "accelerationAT"),
    ),
    CompilerRejectCase(
        "attachment-missing-rope-tension-transfer",
        KINETIC_A_DOWN,
        _remove_quantity_from_relation("ropeAttachedB", "ropeTensionMagnitude"),
    ),
    CompilerRejectCase(
        "rope-state-missing",
        KINETIC_A_DOWN,
        _remove_record("state_conditions", "state_condition_id", "ropeTautState"),
    ),
    CompilerRejectCase(
        "pulley-state-unevidenced",
        KINETIC_A_DOWN,
        _clear_evidence("state_conditions", "state_condition_id", "pulleyFixedState"),
    ),
    CompilerRejectCase(
        "contact-state-missing",
        KINETIC_A_DOWN,
        _remove_record("state_conditions", "state_condition_id", "contactState"),
    ),
    CompilerRejectCase(
        "fixed-incline-state-missing",
        KINETIC_A_DOWN,
        _remove_record("state_conditions", "state_condition_id", "inclineFixedState"),
    ),
    CompilerRejectCase(
        "friction-regime-missing",
        KINETIC_A_DOWN,
        _remove_record("state_conditions", "state_condition_id", "frictionState"),
    ),
    CompilerRejectCase(
        "motion-direction-assumption-missing",
        KINETIC_A_DOWN,
        _remove_record(
            "assumptions",
            "assumption_id",
            MOTION_DIRECTION_ASSUMPTION_ID,
        ),
    ),
    CompilerRejectCase(
        "motion-direction-carrier-missing",
        KINETIC_A_DOWN,
        _clear_motion_carrier,
    ),
    CompilerRejectCase(
        "friction-same-as-motion",
        KINETIC_A_DOWN,
        _same_direction_friction,
    ),
    CompilerRejectCase(
        "rope-interaction-extra-participant",
        KINETIC_A_DOWN,
        _append_rope_participant,
    ),
    CompilerRejectCase(
        "rope-tension-intermediate-framed",
        KINETIC_A_DOWN,
        _set_quantity_frame("ropeTensionMagnitude", WORLD_FRAME_ID),
    ),
    CompilerRejectCase(
        "rope-acceleration-intermediate-framed",
        KINETIC_A_DOWN,
        _set_quantity_frame("ropeAccelerationCoordinate", INCLINE_FRAME_ID),
    ),
    CompilerRejectCase(
        "rope-tension-intermediate-query-bypass",
        FRICTIONLESS_A_DOWN,
        _query_rope_intermediate,
    ),
    CompilerRejectCase(
        "rope-acceleration-intermediate-query-bypass",
        FRICTIONLESS_A_DOWN,
        _query_rope_acceleration_intermediate,
    ),
    CompilerRejectCase(
        "normal-force-query-bypass",
        FRICTIONLESS_A_DOWN,
        _query_normal_force,
    ),
    CompilerRejectCase(
        "projected-gravity-query-bypass",
        FRICTIONLESS_A_DOWN,
        _query_gravity_projection,
    ),
    CompilerRejectCase(
        "normal-acceleration-query-bypass",
        FRICTIONLESS_A_DOWN,
        _query_normal_acceleration,
    ),
    CompilerRejectCase(
        "known-mass-query-bypass",
        FRICTIONLESS_A_DOWN,
        _query_known_mass,
    ),
    CompilerRejectCase(
        "active-friction-query-bypass",
        KINETIC_A_DOWN,
        _query_active_friction,
    ),
    CompilerRejectCase(
        "hanging-tension-wrong-direction",
        KINETIC_A_DOWN,
        _set_tension_b_wrong_direction,
    ),
)


@pytest.mark.parametrize("case", COMPILER_REJECT_CASES, ids=lambda case: case.label)
def test_incline_hanging_structural_authority_fails_closed_without_legacy(
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


def test_cross_frame_interval_collapse_is_invalid_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized = _normalize(
        KINETIC_A_DOWN,
        mutation=_set_shared_interval_frame,
    )
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
        issue.code is CompilerIssueCode.invalid_binding
        for issue in execution.compiler_result.issues
    )


def test_valid_sliding_deceleration_without_branch_assumption_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = KINETIC_DECELERATING_WITHOUT_DIRECTION_ASSUMPTION
    assert source.direction_consistent is False
    assert source.acceleration_not_opposite_motion is False
    assert SLIDING_DIRECTION_SENTENCE not in source.problem_text
    normalized = _normalize(source)
    assert normalized.terminal is ValidationTerminal.accepted, normalized.issues
    assert type(normalized.ir) is MechanicsProblemIRV1
    assert all(
        item.kind != "acceleration_not_opposite_motion"
        for item in normalized.ir.assumptions
    )
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
        _source("inactive", mass_a_si=0.0, mass_b_si=1.0, theta_deg=30.0, motion_sign=-1),
        _source("inactive", mass_a_si=1.0, mass_b_si=-1.0, theta_deg=30.0, motion_sign=1),
        _source("inactive", mass_a_si=1.0, mass_b_si=1.0, theta_deg=30.0, gravity_si=0.0, motion_sign=1),
        _source("sliding", mass_a_si=10.0, mass_b_si=1.0, theta_deg=30.0, coefficient=-0.1, motion_sign=1),
        _source("inactive", mass_a_si=1.0, mass_b_si=1.0, theta_deg=-1.0, motion_sign=-1),
        _source("inactive", mass_a_si=2.0, mass_b_si=1.0, theta_deg=90.0, motion_sign=1),
        _source("inactive", mass_a_si=2.0, mass_b_si=1.0, theta_deg=91.0, motion_sign=1),
    ),
    ids=(
        "zero-incline-mass",
        "negative-hanging-mass",
        "zero-gravity",
        "negative-friction-coefficient",
        "negative-angle",
        "right-angle-legacy-domain-boundary",
        "angle-above-right-angle",
    ),
)
def test_incline_hanging_invalid_domain_fails_closed_without_legacy(
    source: InclineHangingSource,
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


@pytest.mark.slow
@pytest.mark.parametrize(
    "source",
    (STATIC_BELOW_BOUNDARY, INCONSISTENT_B_DOWN),
    ids=("static-just-below-boundary", "stated-motion-direction-contradiction"),
)
def test_incline_hanging_infeasible_candidate_is_rejected_without_legacy(
    source: InclineHangingSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ir = _build_ir(source)
    _forbid_legacy_call(monkeypatch)

    execution = _execute(ir)

    assert execution.terminal is MigrationProbeTerminal.solve_rejected
    assert execution.compiler_status is CompilerStatus.ready
    result = execution.solve_result
    assert result is not None
    assert result.terminal is MechanicsSolveTerminal.insufficient_conditions
    assert result.verified_candidates == ()
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert result.candidate_set.generation_complete is True
    assert len(result.candidate_set.candidates) == 1
    assert any(
        rejection.reason is CandidateRejectionReason.inequality_violation
        for rejection in result.rejections
    )


def _declare_direction_ambiguity(payload: dict[str, object]) -> None:
    payload["ambiguities"] = [
        {
            "ambiguity_id": "inclineHangingDirectionAmbiguity",
            "kind": "direction",
            "referenced_ids": [
                "velocityAT", "frictionA", "accelerationAT",
                "accelerationBY", "queryB",
            ],
            "description": (
                "The incline motion, hanging motion, or friction direction is unresolved."
            ),
            "blocking": True,
            "evidence_refs": ["motionEvidence", "queryEvidence"],
        }
    ]


@pytest.mark.parametrize(
    ("mutation", "approved_assumption_ids", "expected_terminal"),
    (
        (
            None,
            tuple(
                item for item in APPROVED_ASSUMPTION_IDS
                if item != "inextensibleRope"
            ),
            ValidationTerminal.needs_confirmation,
        ),
        (
            None,
            tuple(
                item for item in APPROVED_ASSUMPTION_IDS
                if item != MOTION_DIRECTION_ASSUMPTION_ID
            ),
            ValidationTerminal.needs_confirmation,
        ),
        (
            _declare_direction_ambiguity,
            APPROVED_ASSUMPTION_IDS,
            ValidationTerminal.needs_confirmation,
        ),
        (
            _query_vector_acceleration,
            APPROVED_ASSUMPTION_IDS,
            ValidationTerminal.invalid,
        ),
    ),
    ids=(
        "rope-authority-not-approved",
        "motion-direction-authority-not-approved",
        "blocking-direction-ambiguity",
        "non-scalar-query-binding",
    ),
)
def test_incline_hanging_validation_gates_before_compile_and_legacy(
    mutation: PayloadMutation | None,
    approved_assumption_ids: tuple[str, ...],
    expected_terminal: ValidationTerminal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)

    normalized = _normalize(
        KINETIC_A_DOWN,
        mutation=mutation,
        approved_assumption_ids=approved_assumption_ids,
    )

    assert normalized.terminal is expected_terminal
    assert normalized.accepted is False
    assert normalized.ir is None


def test_entry6_connected_generic_families_remain_compiler_ready() -> None:
    from test_phase56_mechanics_atwood_same_fixture_parity import (
        APPROVED_ASSUMPTION_IDS as ATWOOD_APPROVED_ASSUMPTION_IDS,
        BASELINE as ATWOOD_BASELINE,
        _build_ir as build_atwood_ir,
    )
    from test_phase56_mechanics_incline_friction_same_fixture_parity import (
        SLIDING_DOWNSLOPE,
        _build_incline_friction_ir,
    )
    from test_phase56_mechanics_incline_same_fixture_parity import (
        INTERIOR_DOWNSLOPE,
        _build_incline_ir,
    )
    from test_phase56_mechanics_table_hanging_same_fixture_parity import (
        APPROVED_ASSUMPTION_IDS as TABLE_APPROVED_ASSUMPTION_IDS,
        KINETIC as TABLE_KINETIC,
        _build_ir as build_table_ir,
    )

    fixtures = (
        (_build_incline_ir(INTERIOR_DOWNSLOPE), ()),
        (_build_incline_friction_ir(SLIDING_DOWNSLOPE), ()),
        (build_atwood_ir(ATWOOD_BASELINE), ATWOOD_APPROVED_ASSUMPTION_IDS),
        (build_table_ir(TABLE_KINETIC), TABLE_APPROVED_ASSUMPTION_IDS),
    )
    for ir, approved in fixtures:
        result = MechanicsCompiler().compile(
            ir,
            validated_ir_authorization=authorize_validated_mechanics_ir(ir),
            approved_assumption_ids=approved,
        )
        assert result.status is CompilerStatus.ready, result.issues
        assert result.graph is not None


_RENAMABLE_IDENTIFIER_KEYS = frozenset(
    {
        "assumption_id",
        "constraint_id",
        "entity_id",
        "event_id",
        "evidence_id",
        "frame_id",
        "interaction_id",
        "interval_id",
        "point_id",
        "quantity_id",
        "query_id",
        "relation_id",
        "state_condition_id",
        "symbol_id",
    }
)


def _collect_fixture_identifiers(value: object) -> set[str]:
    collected: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _RENAMABLE_IDENTIFIER_KEYS and isinstance(item, str):
                collected.add(item)
            collected.update(_collect_fixture_identifiers(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            collected.update(_collect_fixture_identifiers(item))
    return collected


def _rename_fixture_identifiers(
    value: object,
    mapping: dict[str, str],
    *,
    parent_key: str | None = None,
) -> object:
    if isinstance(value, dict):
        return {
            key: _rename_fixture_identifiers(item, mapping, parent_key=key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _rename_fixture_identifiers(item, mapping, parent_key=parent_key)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _rename_fixture_identifiers(item, mapping, parent_key=parent_key)
            for item in value
        )
    if isinstance(value, str) and (
        parent_key in _RENAMABLE_IDENTIFIER_KEYS
        or (
            parent_key is not None
            and parent_key.endswith("_id")
            and parent_key not in {"axis_id", "model_id"}
        )
        or (parent_key is not None and parent_key.endswith("_ids"))
        or parent_key in {"evidence_refs", "referenced_ids"}
    ):
        return mapping.get(value, value)
    return value


def test_entry6_consistent_global_identifier_rename_preserves_graph() -> None:
    original_ir = _build_ir(KINETIC_A_DOWN)
    original = MechanicsCompiler().compile(
        original_ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(original_ir),
        approved_assumption_ids=APPROVED_ASSUMPTION_IDS,
    )
    payload = original_ir.model_dump(mode="python", warnings="none")
    identifiers = sorted(_collect_fixture_identifiers(payload))
    mapping = {
        identifier: f"renamedIdentifier{index}"
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
