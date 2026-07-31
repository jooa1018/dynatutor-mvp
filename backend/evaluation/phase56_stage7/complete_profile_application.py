"""Transactional application of one complete profile to one Draft.

Which layer this belongs to was audited before it was written, and the answer
is: the evaluator, not the product runtime.

The Draft is the Stage 6 modeler's output contract.  `modeler_repair` lists
`reference_frames`, `points`, `interactions`, `constraints`, and
`state_conditions` among the structural roots a model may author and repair, and
`multimodal_revision` lets a revision add or replace a frame outright.  On the
other side, the compiler synthesises no IR record at all — its single generated
artifact is the query symbol — and the Phase 55 parser adapter also hands over
`reference_frames=[]`, `points=[]`, `constraints=[]`.  Graph structure is
therefore the modeler's authority end to end.  A runtime closure stage that
created frames, points, or interactions would move that authority from the
modeler to the server, which is exactly the boundary change that must not happen
silently.  So closure lives here, on the evaluator's own projected Draft, where
the corpus's typed structure plays the role the modeler plays in production.

**Product-path limitation.**  Nothing in this module runs in the product path.
A production Draft that arrives without the frame and axis a law needs is still
blocked exactly as it was; closing that gap requires the Stage 6 modeler to
supply the profile, or an explicit, separately reviewed decision to move the
authority boundary.  This module does not make that decision.

Application is transactional.  A new Draft payload is built in full and swapped
in only once it validates; on any failure the original Draft is returned
untouched.  No half-built free body — a weight without its normal, a rope
pulling on one side — is ever visible to the runtime, because no intermediate
Draft is ever produced.

Values of generated unknowns stay unknown.  Only their existence is derived.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from engine.mechanics.contracts import MechanicsProblemDraftV1
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import AssumptionAuthorization

from evaluation.phase56_stage7.complete_profile import (
    CompleteProfilePlanV1,
    PlanDisposition,
    ProfileId,
    draft_structure_fingerprint,
)

COMPLETE_PROFILE_APPLICATION_VERSION = (
    "phase56-stage7-complete-profile-application-v7"
)


@dataclass(frozen=True, slots=True)
class TransactionAuthority:
    """What the authority stage issued, read-only, for transactions to consume.

    A transaction may *consume* an authorization the Lane B authority stage
    issued; it may never mint, widen, or restyle one.  The empty default is the
    fail-closed posture: with no authority supplied, any profile that needs a
    server-valued quantity simply refuses.
    """

    approved_assumption_ids: frozenset[str] = frozenset()
    authorized_assumptions: Mapping[str, AssumptionAuthorization] = field(
        default_factory=lambda: MappingProxyType({})
    )

# The axis a source's own stated direction names, and the sign it carries on
# that axis.  This is the *same* closed table the planner classified as
# `server_derivable`; the applier may not widen it.
_SEMANTIC_AXIS_BINDING: Mapping[str, tuple[str, int]] = {
    "right": ("x", 1),
    "left": ("x", -1),
    "upward": ("y", 1),
    "downward": ("y", -1),
}


def _directed_scalar_axis_sign(
    direction_sign: int, raw_value: Any
) -> int | None:
    """Resolve one axis sign for a scalar that states a direction *and* a value.

    One typed contract, stated once and applied everywhere: **a scalar that
    carries a semantic direction has stated its direction separately, so its
    value is a magnitude and the direction owns the sign.**  The component the
    engine forms is then ``direction_sign * raw_value``, and it never applies
    a sign twice.

    A magnitude is never negative.  A source that writes a *negative* value
    next to a stated direction has encoded the sign twice, and the two
    encodings cannot be reconciled from typed structure alone: whether the
    number or the word wins depends on an axis orientation the source never
    states, and the two readings are not the same physics.  Guessing would
    answer a mirror-image problem with full confidence, so this fails closed.

    This is a statement about scalars, not about any one problem family: it
    reads only a sign and a number — never a role, a subject, an event, a
    family, or an answer.
    """

    if direction_sign not in {-1, 1}:
        return None
    if type(raw_value) is not str:
        return None
    try:
        value = float(raw_value)
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0.0:
        return None
    return direction_sign


def _directionless_zero_scalar(quantity: Mapping[str, Any]) -> bool:
    """True for a source scalar that is exactly zero and states no direction.

    ``not_applicable`` is the source saying this quantity has no direction —
    which the projection records as the magnitude component with no direction
    binding.  For every other value that is a real gap: a magnitude of 3 m/s
    does not say which way the body is going, and no rule may supply one.
    Zero is the single exception, and only because it is not a direction
    question at all: +0 and -0 are the same number on any axis, so a body whose
    speed is exactly zero has exactly one velocity vector on the line of
    impact.  Anything that is merely small is not zero and is refused.
    """

    raw_value = quantity.get("raw_value")
    if (
        quantity.get("direction") is not None
        or quantity.get("component") != "magnitude"
        or type(raw_value) is not str
    ):
        return False
    try:
        value = float(raw_value)
    except ValueError:
        return False
    return value == 0.0
# Roles whose physical identity includes a component.  A scalar invariant — a
# mass, a duration — is left exactly as the source stated it.
_COMPONENT_ROLES: frozenset[str] = frozenset(
    {
        "position",
        "displacement",
        "velocity",
        "speed",
        "acceleration",
        "force",
        "moment",
        "torque",
        "momentum",
        "angular_momentum",
        "impulse",
        "angular_position",
        "angular_velocity",
        "angular_acceleration",
    }
)

DERIVED_FRAME_ID = "frm_closure_axis"
MOTION_AXIS_FRAME_ID = "frm_closure_motion_axis"
ENERGY_SPEED_FRAME_ID = "frm_closure_energy_speed"
DIRECT_WORK_FRAME_ID = "frm_closure_direct_work"
DIRECT_WORK_INTERACTION_ID = "rel_closure_direct_work"
DIRECT_WORK_ASSUMPTION_ID = "asm_closure_direct_constant_force_work"
POLAR_COORDINATE_ENTITY_ID = "entity_closure_polar_coordinate"
POLAR_FRAME_ID = "frm_closure_polar_state"
POLAR_RADIUS_RELATION_ID = "geo_closure_polar_radius"
WORLD_FRAME_ID = "frm_closure_world"
OBSERVER_FRAME_ID = "frm_closure_observer"
SLOT_PIN_FRAME_ID = "frm_closure_slot_radial"
ROTATING_WORLD_FRAME_ID = "frm_closure_coriolis_world"
ROTATING_FRAME_ID = "frm_closure_coriolis_rotating"
ROTATION_POINT_ID = "pt_closure_coriolis_pivot"
FIXED_PULLEY_FRAME_ID = "frm_closure_fixed_pulley"
FIXED_PULLEY_GRAVITY_QUANTITY_ID = "qty_closure_fixed_pulley_gravity"
FIXED_PULLEY_GRAVITY_SYMBOL_ID = "sym_closure_fixed_pulley_gravity"
FIXED_PULLEY_GRAVITY_LIGHT_ID = "rel_closure_fixed_pulley_gravity_light"
FIXED_PULLEY_GRAVITY_HEAVY_ID = "rel_closure_fixed_pulley_gravity_heavy"
FIXED_PULLEY_ROPE_INTERACTION_ID = "rel_closure_fixed_pulley_rope"
FIXED_PULLEY_WRAP_ID = "geo_closure_fixed_pulley_wrap"
FIXED_PULLEY_ATTACH_LIGHT_ID = "geo_closure_fixed_pulley_attach_light"
FIXED_PULLEY_ATTACH_HEAVY_ID = "geo_closure_fixed_pulley_attach_heavy"
FIXED_PULLEY_TAUT_STATE_ID = "state_closure_fixed_pulley_rope_taut"
FIXED_PULLEY_FIXED_STATE_ID = "state_closure_fixed_pulley_fixed"

INCLINE_HANGING_ROPE_ID = "entity_closure_fixed_pulley_rope"
INCLINE_HANGING_WORLD_ID = "entity_closure_incline_hanging_world"
INCLINE_HANGING_WORLD_FRAME_ID = "frm_closure_incline_hanging_world"
INCLINE_HANGING_INCLINE_FRAME_ID = "frm_closure_incline_hanging_slope"
INCLINE_HANGING_CONTACT_POINT_ID = "pt_closure_incline_hanging_contact"
INCLINE_HANGING_GRAVITY_ID = "qty_closure_incline_hanging_gravity"
INCLINE_HANGING_GRAVITY_SYMBOL_ID = "sym_closure_incline_hanging_gravity"

TABLE_PULLEY_WORLD_ID = "entity_closure_table_pulley_world"
TABLE_PULLEY_WORLD_FRAME_ID = "frm_closure_table_pulley_world"
TABLE_PULLEY_SUPPORT_FRAME_ID = "frm_closure_table_pulley_support"
TABLE_PULLEY_ORIENTATION_RELATION_ID = "geo_closure_table_pulley_orientation"
TABLE_PULLEY_CONTACT_POINT_ID = "pt_closure_table_pulley_contact"
TABLE_PULLEY_GRAVITY_ID = "qty_closure_table_pulley_gravity"
TABLE_PULLEY_GRAVITY_SYMBOL_ID = "sym_closure_table_pulley_gravity"

INCLINE_SLIDING_WORLD_ID = "entity_closure_incline_sliding_world"
INCLINE_SLIDING_WORLD_FRAME_ID = "frm_closure_incline_sliding_world"
INCLINE_SLIDING_SLOPE_FRAME_ID = "frm_closure_incline_sliding_slope"
INCLINE_SLIDING_CONTACT_POINT_ID = "pt_closure_incline_sliding_contact"
INCLINE_SLIDING_GRAVITY_ID = "qty_closure_incline_sliding_gravity"
INCLINE_SLIDING_GRAVITY_SYMBOL_ID = "sym_closure_incline_sliding_gravity"
RIGID_AXIS_POINT_ID = "pt_closure_rigid_axis_material"
TWO_POINT_SPEED_KNOWN_POINT_ID = "pt_closure_two_point_speed_known"
TWO_POINT_SPEED_QUERY_POINT_ID = "pt_closure_two_point_speed_query"
TWO_POINT_SPEED_OMEGA_QUANTITY_ID = "qty_closure_two_point_speed_omega"
TWO_POINT_SPEED_OMEGA_SYMBOL_ID = "sym_closure_two_point_speed_omega"
RESULTANT_FORCE_FRAME_ID = "frm_closure_resultant_force"
RESULTANT_FORCE_INTERACTION_ID = "rel_closure_resultant_force"
VERTICAL_CIRCLE_GRAVITY_QUANTITY_ID = "qty_closure_vertical_circle_gravity"
VERTICAL_CIRCLE_GRAVITY_SYMBOL_ID = "sym_closure_vertical_circle_gravity"
COLLISION_RESTITUTION_FRAME_ID = "frame_closure_collision_restitution_world"
COLLISION_PARTNER_AFTER_QUANTITY_ID = "qty_closure_collision_partner_after"
COLLISION_PARTNER_AFTER_SYMBOL_ID = "sym_closure_collision_partner_after"
ROLLING_GRAVITY_QUANTITY_ID = "qty_closure_rolling_gravity"
ROLLING_GRAVITY_SYMBOL_ID = "sym_closure_rolling_gravity"

_FIXED_PULLEY_SCOPED_ASSUMPTIONS: Mapping[str, str] = {
    "massless_rope": "asm_closure_fixed_pulley_massless_rope",
    "inextensible_rope": "asm_closure_fixed_pulley_inextensible_rope",
    "fixed_pulley": "asm_closure_fixed_pulley_fixed",
    "ideal_massless_frictionless_pulley": "asm_closure_fixed_pulley_ideal",
}
_MASS_DIMENSION = DimensionVector(mass=1)
# A body typed as sliding on an incline moves along the slope tangent, so a
# source-stated downward velocity is the down-slope sense (+1 on the
# down-slope-positive tangent) and an upward one is the up-slope sense.
# Nothing else resolves a slope sense, so nothing else appears here.
_INCLINE_SLIDE_TANGENT_SIGNS: dict[str, int] = {
    "downward": 1,
    "upward": -1,
}
_FORCE_DIMENSION: dict[str, int] = {"mass": 1, "length": 1, "time": -2}

_POLAR_COMPONENT_IDS: Mapping[tuple[str, str], tuple[str, str]] = {
    ("velocity", "radial"): (
        "qty_closure_polar_velocity_radial",
        "sym_closure_polar_velocity_radial",
    ),
    ("velocity", "transverse"): (
        "qty_closure_polar_velocity_transverse",
        "sym_closure_polar_velocity_transverse",
    ),
    ("speed", "magnitude"): (
        "qty_closure_polar_speed",
        "sym_closure_polar_speed",
    ),
    ("acceleration", "radial"): (
        "qty_closure_polar_acceleration_radial",
        "sym_closure_polar_acceleration_radial",
    ),
    ("acceleration", "transverse"): (
        "qty_closure_polar_acceleration_transverse",
        "sym_closure_polar_acceleration_transverse",
    ),
    ("acceleration", "magnitude"): (
        "qty_closure_polar_acceleration_magnitude",
        "sym_closure_polar_acceleration_magnitude",
    ),
}

# A source that said a quantity has no direction stated its *magnitude*, and a
# magnitude is not a signed component of anything.  Restamping it onto an axis
# would hand the solver a sign the source never gave, so a magnitude is left
# exactly as the source wrote it.
_DIRECTIONLESS_COMPONENT = "magnitude"
_SIGNED_AXIS_COMPONENTS: frozenset[str] = frozenset({"x", "y", "z"})

# Every ID-bearing namespace of the Draft contract, as (field, id_field) pairs.
# A transaction's generated IDs must be fresh across ALL of them: Draft
# references resolve by bare identifier, so a generated ID that echoes an
# authored ID in *any* namespace — an entity, an event, a constraint, an
# assumption — would splice the created records into the Draft's existing
# reference space instead of standing beside it.  The collision precheck runs
# before anything is built, and a hit abandons the transaction whole: the
# caller keeps the exact Draft it passed in.
_DRAFT_ID_NAMESPACES: tuple[tuple[str, str], ...] = (
    ("source_assets", "asset_id"),
    ("source_evidence", "evidence_id"),
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
    ("principle_hints", "hint_id"),
    ("assumptions", "assumption_id"),
    ("ambiguities", "ambiguity_id"),
    ("unsupported_features", "feature_code"),
)


def _authored_draft_ids(payload: Mapping[str, Any]) -> frozenset[str]:
    """Every authored ID in every Draft namespace, as one collision domain."""

    ids: set[str] = set()
    for field_name, id_field in _DRAFT_ID_NAMESPACES:
        for item in payload[field_name]:
            value = item.get(id_field)
            if value is not None:
                ids.add(value)
    return frozenset(ids)


def _query_axis_conflicts(query: dict[str, Any], axis: str) -> bool:
    """Whether binding this axis would change what the question asks.

    A question about a magnitude is a different question from one about a
    signed component, and a question about another axis is about another axis.
    Either way the transaction is abandoned rather than the question rewritten.
    """

    component = query["target"].get("component")
    if component in _SIGNED_AXIS_COMPONENTS:
        return component != axis
    return component == _DIRECTIONLESS_COMPONENT


class ApplicationOutcome(str, Enum):
    """What the applier did.  There is no partial outcome."""

    applied = "applied"
    # The plan did not authorise any change.
    not_applied = "not_applied"
    # The plan authorised a change that could not be built as a whole.
    rejected = "rejected"


@dataclass(frozen=True, slots=True)
class ProfileApplication:
    """The result of one transaction: a whole new Draft, or the original."""

    outcome: ApplicationOutcome
    draft: MechanicsProblemDraftV1
    profile_id: ProfileId | None = None
    created_record_ids: tuple[str, ...] = ()
    rebound_quantity_ids: tuple[str, ...] = ()
    sanitized_reason: str | None = None

    @property
    def applied(self) -> bool:
        return self.outcome is ApplicationOutcome.applied


def _axis_binding(quantities: list[dict[str, Any]], subject_id: str) -> str | None:
    """The single axis every stated direction on this subject agrees on."""

    axes = set()
    for quantity in quantities:
        if quantity["subject_id"] != subject_id:
            continue
        direction = quantity.get("direction") or {}
        if direction.get("kind") != "semantic":
            continue
        binding = _SEMANTIC_AXIS_BINDING.get(direction.get("direction", ""))
        if binding is not None:
            axes.add(binding[0])
    if len(axes) != 1:
        return None
    return next(iter(axes))


def _impulse_momentum_transaction(
    payload: dict[str, Any], _authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Bind one subject's stated directions to one derived signed axis.

    `linear_impulse_momentum` pairs its mass, its two endpoint velocities, and
    its impulse by component.  A source that states `left` and `right` has named
    the axis but not written it down, so the frame, the axis, and every
    component binding that depends on them are created here — as one step, since
    any of them alone leaves the emitter exactly as blocked.

    No value changes.  A direction the source stated becomes the same direction
    expressed against a named axis, and the queried unknown gains the component
    it is already being asked for.  Nothing gains a direction the source did not
    state.
    """

    if not payload["queries"]:
        return None
    query = payload["queries"][0]
    subject_id = query["target"]["subject_id"]
    axis = _axis_binding(payload["quantities"], subject_id)
    if axis is None:
        return None
    if _query_axis_conflicts(query, axis):
        return None
    if DERIVED_FRAME_ID in _authored_draft_ids(payload):
        return None

    frame = {
        "frame_id": DERIVED_FRAME_ID,
        "frame_type": "cartesian_2d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": name,
                "direction": {
                    "kind": "axis",
                    "frame_id": DERIVED_FRAME_ID,
                    "axis": name,
                    "sign": 1,
                },
            }
            for name in ("x", "y")
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }

    rebound: list[str] = []
    quantities: list[dict[str, Any]] = []
    for original in payload["quantities"]:
        quantity = dict(original)
        if quantity["subject_id"] != subject_id:
            quantities.append(quantity)
            continue
        if quantity["role"] not in _COMPONENT_ROLES:
            quantities.append(quantity)
            continue
        direction = quantity.get("direction") or {}
        if direction.get("kind") == "semantic":
            binding = _SEMANTIC_AXIS_BINDING.get(direction.get("direction", ""))
            if binding is None or binding[0] != axis:
                # A direction on another axis cannot be folded into this one.
                return None
            quantity["direction"] = {
                "kind": "axis",
                "frame_id": DERIVED_FRAME_ID,
                "axis": axis,
                "sign": binding[1],
            }
        elif direction or quantity.get("component") == _DIRECTIONLESS_COMPONENT:
            # An already-bound direction, or a magnitude the source stated as
            # directionless, is left exactly as it is.
            quantities.append(quantity)
            continue
        quantity["component"] = axis
        quantity["frame_id"] = DERIVED_FRAME_ID
        quantities.append(quantity)
        rebound.append(quantity["quantity_id"])

    if not rebound:
        return None

    queries = [dict(item) for item in payload["queries"]]
    target = dict(queries[0]["target"])
    target["component"] = axis
    target["frame_id"] = DERIVED_FRAME_ID
    queries[0]["target"] = target

    closed = dict(payload)
    closed["reference_frames"] = [*payload["reference_frames"], frame]
    closed["quantities"] = quantities
    closed["queries"] = queries
    return closed, (DERIVED_FRAME_ID,), tuple(rebound)


def _signed_constant_acceleration_1d_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Bind a source-stated braking interval to its intrinsic motion axis.

    The source already states the positive sign (``along_motion``), the
    negative sign (``opposite_motion``), and an evidenced final rest boundary.
    The transaction writes one Cartesian axis and re-expresses those same
    statements on it.  It creates no value, force, equation, or answer.
    """

    if (
        len(payload["queries"]) != 1
        or len(payload["motion_intervals"]) != 1
        or len(payload["entities"]) != 1
        or payload["reference_frames"]
        or payload["points"]
        or payload["geometry"]
        or payload["interactions"]
        or payload["constraints"]
        or len(payload["quantities"]) != 4
        or MOTION_AXIS_FRAME_ID in _authored_draft_ids(payload)
    ):
        return None

    query = payload["queries"][0]
    target = query["target"]
    interval = payload["motion_intervals"][0]
    subject_ids = interval.get("subject_ids") or []
    if (
        target.get("role") != "duration"
        or target.get("interval_id") != interval.get("interval_id")
        or target.get("subject_id") not in subject_ids
        or len(subject_ids) != 1
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or target.get("event_id") is not None
        or target.get("frame_id") is not None
        or target.get("direction") not in (None, {})
        or target.get("component") not in {"magnitude", "unspecified"}
    ):
        return None
    subject_id = subject_ids[0]
    interval_id = interval["interval_id"]
    start_event_id = interval["start_event_id"]
    end_event_id = interval["end_event_id"]

    quantities = {item["quantity_id"]: item for item in payload["quantities"]}
    query_quantity = quantities.get(target.get("target_quantity_id"))
    if (
        query_quantity is None
        or query_quantity.get("role") != "duration"
        or query_quantity.get("subject_id") != subject_id
        or query_quantity.get("interval_id") != interval_id
        or query_quantity.get("event_id") is not None
        or query_quantity.get("raw_value") is not None
        or query_quantity.get("raw_unit") is not None
    ):
        return None

    velocities = [
        item
        for item in payload["quantities"]
        if item.get("role") == "velocity"
        and item.get("subject_id") == subject_id
        and item.get("interval_id") == interval_id
    ]
    accelerations = [
        item
        for item in payload["quantities"]
        if item.get("role") == "acceleration"
        and item.get("subject_id") == subject_id
        and item.get("interval_id") == interval_id
        and item.get("event_id") is None
    ]
    if len(velocities) != 2 or len(accelerations) != 1:
        return None
    by_event = {item.get("event_id"): item for item in velocities}
    start = by_event.get(start_event_id)
    end = by_event.get(end_event_id)
    acceleration = accelerations[0]
    if start is None or end is None:
        return None

    start_direction = start.get("direction") or {}
    acceleration_direction = acceleration.get("direction") or {}
    if (
        start_direction
        != {"kind": "semantic", "direction": "along_motion"}
        or acceleration_direction
        != {"kind": "semantic", "direction": "opposite_motion"}
        or start.get("raw_value") is None
        or start.get("raw_unit") is None
        or acceleration.get("raw_value") is None
        or acceleration.get("raw_unit") is None
        or end.get("raw_value") is not None
        or end.get("raw_unit") is not None
        or end.get("direction") not in (None, {})
        or end.get("component") != "magnitude"
    ):
        return None

    rest_states = [
        item
        for item in payload["state_conditions"]
        if item.get("state") == "at_rest"
        and item.get("kind") == "final"
        and item.get("subject_id") == subject_id
        and item.get("interval_id") == interval_id
        and item.get("event_id") == end_event_id
        and item.get("quantity_ids") == [end["quantity_id"]]
        and item.get("evidence_refs")
    ]
    if len(rest_states) != 1:
        return None
    if not any(
        item.get("kind") == "constant_acceleration"
        and item.get("subject_id") == subject_id
        and item.get("interval_id") == interval_id
        and item.get("assumption_id") in authority.approved_assumption_ids
        for item in payload["assumptions"]
    ):
        return None

    frame = {
        "frame_id": MOTION_AXIS_FRAME_ID,
        "frame_type": "cartesian_1d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": "x",
                "direction": {
                    "kind": "axis",
                    "frame_id": MOTION_AXIS_FRAME_ID,
                    "axis": "x",
                    "sign": 1,
                },
            }
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }

    rebound: list[str] = []
    rewritten_quantities: list[dict[str, Any]] = []
    for original in payload["quantities"]:
        quantity = dict(original)
        if quantity["quantity_id"] == start["quantity_id"]:
            quantity.update(
                frame_id=MOTION_AXIS_FRAME_ID,
                component="x",
                direction={
                    "kind": "axis",
                    "frame_id": MOTION_AXIS_FRAME_ID,
                    "axis": "x",
                    "sign": 1,
                },
            )
            rebound.append(quantity["quantity_id"])
        elif quantity["quantity_id"] == acceleration["quantity_id"]:
            quantity.update(
                frame_id=MOTION_AXIS_FRAME_ID,
                component="x",
                direction={
                    "kind": "axis",
                    "frame_id": MOTION_AXIS_FRAME_ID,
                    "axis": "x",
                    "sign": -1,
                },
            )
            rebound.append(quantity["quantity_id"])
        elif quantity["quantity_id"] == end["quantity_id"]:
            quantity.update(
                frame_id=MOTION_AXIS_FRAME_ID,
                component="x",
                direction=None,
            )
            rebound.append(quantity["quantity_id"])
        rewritten_quantities.append(quantity)

    rewritten_interval = dict(interval)
    rewritten_interval["frame_id"] = MOTION_AXIS_FRAME_ID
    closed = dict(payload)
    closed["reference_frames"] = [frame]
    closed["motion_intervals"] = [rewritten_interval]
    closed["quantities"] = rewritten_quantities
    return closed, (MOTION_AXIS_FRAME_ID,), tuple(sorted(rebound))


def _particle_work_energy_speed_transaction(
    payload: dict[str, Any], _authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one scalar endpoint work--energy balance without inventing data.

    The source provides a positive scalar along the motion at the start and
    explicitly requests the endpoint magnitude.  Those are speed magnitudes,
    not signed components.  This transaction writes one intrinsic Cartesian
    1-D frame, reclassifies only those two scalar velocity records as `speed`,
    and restores mass to its source-declared timeless scope.  Raw values,
    units, evidence, and every unrelated record remain unchanged.
    """

    if (
        len(payload["queries"]) != 1
        or len(payload["motion_intervals"]) != 1
        or len(payload["entities"]) != 1
        or payload["reference_frames"]
        or payload["points"]
        or payload["geometry"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
        or payload["assumptions"]
        or payload["ambiguities"]
        or payload["unsupported_features"]
        or len(payload["quantities"]) != 4
        or ENERGY_SPEED_FRAME_ID in _authored_draft_ids(payload)
    ):
        return None

    entity = payload["entities"][0]
    if entity.get("primitive") not in {"particle", "rigid_body"}:
        return None

    interval = payload["motion_intervals"][0]
    subject_ids = interval.get("subject_ids") or []
    start_event_id = interval.get("start_event_id")
    end_event_id = interval.get("end_event_id")
    if (
        len(subject_ids) != 1
        or subject_ids[0] != entity.get("entity_id")
        or start_event_id is None
        or end_event_id is None
        or start_event_id == end_event_id
        or interval.get("frame_id") is not None
    ):
        return None
    subject_id = subject_ids[0]
    interval_id = interval["interval_id"]

    query = payload["queries"][0]
    target = query["target"]
    if (
        target.get("role") != "velocity"
        or target.get("subject_id") != subject_id
        or target.get("interval_id") != interval_id
        or target.get("event_id") != end_event_id
        or target.get("component") != "magnitude"
        or target.get("frame_id") is not None
        or target.get("direction") not in (None, {})
    ):
        return None

    by_id = {item["quantity_id"]: item for item in payload["quantities"]}
    query_quantity = by_id.get(target.get("target_quantity_id"))
    masses = [item for item in payload["quantities"] if item.get("role") == "mass"]
    works = [item for item in payload["quantities"] if item.get("role") == "work"]
    velocities = [
        item for item in payload["quantities"] if item.get("role") == "velocity"
    ]
    if (
        query_quantity is None
        or len(masses) != 1
        or len(works) != 1
        or len(velocities) != 2
    ):
        return None
    mass = masses[0]
    work = works[0]
    velocity_by_event = {item.get("event_id"): item for item in velocities}
    start = velocity_by_event.get(start_event_id)
    end = velocity_by_event.get(end_event_id)
    if end is not query_quantity or start is None:
        return None

    if (
        mass.get("subject_id") != subject_id
        or mass.get("event_id") is not None
        or mass.get("frame_id") is not None
        or mass.get("raw_value") is None
        or mass.get("raw_unit") is None
        or work.get("subject_id") != subject_id
        or work.get("interval_id") != interval_id
        or work.get("event_id") is not None
        or work.get("frame_id") is not None
        or work.get("raw_value") is None
        or work.get("raw_unit") is None
        or start.get("subject_id") != subject_id
        or start.get("interval_id") != interval_id
        or start.get("frame_id") is not None
        or start.get("component") != "unspecified"
        or start.get("direction")
        != {"kind": "semantic", "direction": "along_motion"}
        or start.get("raw_value") is None
        or start.get("raw_unit") is None
        or end.get("subject_id") != subject_id
        or end.get("interval_id") != interval_id
        or end.get("frame_id") is not None
        or end.get("component") != "magnitude"
        or end.get("direction") not in (None, {})
        or end.get("raw_value") is not None
        or end.get("raw_unit") is not None
    ):
        return None

    frame = {
        "frame_id": ENERGY_SPEED_FRAME_ID,
        "frame_type": "cartesian_1d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": "x",
                "direction": {
                    "kind": "axis",
                    "frame_id": ENERGY_SPEED_FRAME_ID,
                    "axis": "x",
                    "sign": 1,
                },
            }
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }

    rewritten_quantities: list[dict[str, Any]] = []
    rebound: list[str] = []
    for original in payload["quantities"]:
        quantity = dict(original)
        if quantity["quantity_id"] == mass["quantity_id"]:
            quantity["interval_id"] = None
            rebound.append(quantity["quantity_id"])
        elif quantity["quantity_id"] in {
            start["quantity_id"],
            end["quantity_id"],
        }:
            quantity.update(
                role="speed",
                frame_id=ENERGY_SPEED_FRAME_ID,
                component="magnitude",
                direction=None,
            )
            rebound.append(quantity["quantity_id"])
        rewritten_quantities.append(quantity)

    rewritten_interval = dict(interval)
    rewritten_interval["frame_id"] = ENERGY_SPEED_FRAME_ID
    rewritten_query = dict(query)
    rewritten_target = dict(target)
    rewritten_target.update(
        role="speed",
        frame_id=ENERGY_SPEED_FRAME_ID,
        component="magnitude",
        direction=None,
    )
    rewritten_query["target"] = rewritten_target

    closed = dict(payload)
    closed["reference_frames"] = [frame]
    closed["motion_intervals"] = [rewritten_interval]
    closed["quantities"] = rewritten_quantities
    closed["queries"] = [rewritten_query]
    return closed, (ENERGY_SPEED_FRAME_ID,), tuple(sorted(rebound))


def _direct_constant_force_work_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one direct constant-force work balance from exact typed structure.

    No value is generated.  The transaction writes one intrinsic 1-D work
    coordinate, retypes the source's whole-interval path length as displacement
    on that coordinate, binds the source's ``along_motion`` force to its positive
    axis, and links the three existing quantities through one applied-force
    interaction.  Every value, unit, scope, subject, and evidence reference is
    preserved.
    """

    if (
        len(payload["queries"]) != 1
        or len(payload["motion_intervals"]) != 1
        or len(payload["entities"]) != 1
        or payload["reference_frames"]
        or payload["points"]
        or payload["geometry"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
        or payload["ambiguities"]
        or payload["unsupported_features"]
        or len(payload["assumptions"]) != 1
        or len(payload["quantities"]) != 3
        or {DIRECT_WORK_FRAME_ID, DIRECT_WORK_INTERACTION_ID}
        & _authored_draft_ids(payload)
    ):
        return None

    entity = payload["entities"][0]
    if entity.get("primitive") not in {"particle", "rigid_body", "body_component"}:
        return None
    subject_id = entity.get("entity_id")
    interval = payload["motion_intervals"][0]
    interval_id = interval.get("interval_id")
    if (
        interval.get("subject_ids") != [subject_id]
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or interval.get("start_event_id") == interval.get("end_event_id")
        or interval.get("frame_id") is not None
    ):
        return None

    assumption = payload["assumptions"][0]
    if (
        assumption.get("assumption_id") != DIRECT_WORK_ASSUMPTION_ID
        or assumption.get("kind") != "constant_force"
        or assumption.get("subject_id") != subject_id
        or assumption.get("interval_id") != interval_id
        or assumption.get("disposition") != "approved"
        or assumption.get("proposed_role") is not None
        or assumption.get("proposed_value") is not None
        or assumption.get("proposed_unit") is not None
        or not assumption.get("evidence_refs")
        or authority.approved_assumption_ids != frozenset({DIRECT_WORK_ASSUMPTION_ID})
    ):
        return None

    query = payload["queries"][0]
    target = query["target"]
    if (
        target.get("role") != "work"
        or target.get("subject_id") != subject_id
        or target.get("interval_id") != interval_id
        or target.get("event_id") is not None
        or target.get("component") != "magnitude"
        or target.get("frame_id") is not None
        or target.get("direction") not in (None, {})
        or not target.get("target_quantity_id")
    ):
        return None

    by_role: dict[str, list[dict[str, Any]]] = {}
    for item in payload["quantities"]:
        by_role.setdefault(item.get("role"), []).append(item)
    if not all(len(by_role.get(role, ())) == 1 for role in ("force", "distance", "work")):
        return None
    force = by_role["force"][0]
    distance = by_role["distance"][0]
    work = by_role["work"][0]
    if work.get("quantity_id") != target.get("target_quantity_id"):
        return None

    common_known = (
        lambda item: (
            item.get("subject_id") == subject_id
            and item.get("interval_id") == interval_id
            and item.get("event_id") is None
            and item.get("shape") == "scalar"
            and item.get("frame_id") is None
            and item.get("raw_value") is not None
            and item.get("raw_unit") is not None
            and item.get("provenance") == "explicit_source"
            and bool(item.get("evidence_refs"))
        )
    )
    if (
        not common_known(force)
        or force.get("component") != "unspecified"
        or force.get("direction")
        != {"kind": "semantic", "direction": "along_motion"}
        or not common_known(distance)
        or distance.get("component") != "magnitude"
        or distance.get("direction") is not None
        or work.get("subject_id") != subject_id
        or work.get("interval_id") != interval_id
        or work.get("event_id") is not None
        or work.get("shape") != "scalar"
        or work.get("component") != "magnitude"
        or work.get("frame_id") is not None
        or work.get("direction") is not None
        or work.get("raw_value") is not None
        or work.get("raw_unit") is not None
        or work.get("provenance") != "unknown"
        or not work.get("symbol_id")
    ):
        return None
    source_evidence = sorted(
        set(force["evidence_refs"])
        | set(distance["evidence_refs"])
        | set(assumption["evidence_refs"])
    )
    if not set(assumption["evidence_refs"]).issubset(source_evidence):
        return None

    frame = {
        "frame_id": DIRECT_WORK_FRAME_ID,
        "frame_type": "cartesian_1d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": "x",
                "direction": {
                    "kind": "axis",
                    "frame_id": DIRECT_WORK_FRAME_ID,
                    "axis": "x",
                    "sign": 1,
                },
            }
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": source_evidence,
    }
    interaction = {
        "interaction_id": DIRECT_WORK_INTERACTION_ID,
        "kind": "applied_force",
        "participant_ids": [subject_id],
        "point_ids": [],
        "frame_id": DIRECT_WORK_FRAME_ID,
        "interval_id": interval_id,
        "event_id": None,
        "quantity_ids": [
            work["quantity_id"],
            force["quantity_id"],
            distance["quantity_id"],
        ],
        "evidence_refs": source_evidence,
    }

    rebound: list[str] = []
    rewritten_quantities: list[dict[str, Any]] = []
    for original in payload["quantities"]:
        quantity = dict(original)
        if quantity["quantity_id"] == force["quantity_id"]:
            quantity.update(
                frame_id=DIRECT_WORK_FRAME_ID,
                component="x",
                direction={
                    "kind": "axis",
                    "frame_id": DIRECT_WORK_FRAME_ID,
                    "axis": "x",
                    "sign": 1,
                },
            )
            rebound.append(quantity["quantity_id"])
        elif quantity["quantity_id"] == distance["quantity_id"]:
            quantity.update(
                role="displacement",
                frame_id=DIRECT_WORK_FRAME_ID,
                component="x",
                direction={
                    "kind": "axis",
                    "frame_id": DIRECT_WORK_FRAME_ID,
                    "axis": "x",
                    "sign": 1,
                },
            )
            rebound.append(quantity["quantity_id"])
        elif quantity["quantity_id"] == work["quantity_id"]:
            quantity["frame_id"] = DIRECT_WORK_FRAME_ID
            rebound.append(quantity["quantity_id"])
        rewritten_quantities.append(quantity)

    rewritten_interval = dict(interval)
    rewritten_interval["frame_id"] = DIRECT_WORK_FRAME_ID
    rewritten_query = dict(query)
    rewritten_target = dict(target)
    rewritten_target["frame_id"] = DIRECT_WORK_FRAME_ID
    rewritten_query["target"] = rewritten_target

    closed = dict(payload)
    closed["reference_frames"] = [frame]
    closed["motion_intervals"] = [rewritten_interval]
    closed["quantities"] = rewritten_quantities
    closed["interactions"] = [interaction]
    closed["queries"] = [rewritten_query]
    return (
        closed,
        (DIRECT_WORK_FRAME_ID, DIRECT_WORK_INTERACTION_ID),
        tuple(sorted(rebound)),
    )


def _polar_kinematics_state_transaction(
    payload: dict[str, Any], _authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact, source-typed instantaneous polar state.

    The transaction creates no value, equation, force, assumption, solver
    choice, candidate, or answer.  It preserves all five source values and
    writes only the polar coordinate/frame/radius topology, six value-free
    component unknowns, and the query binding consumed by the existing verified
    polar law graph.
    """

    reserved_ids = {
        POLAR_COORDINATE_ENTITY_ID,
        POLAR_FRAME_ID,
        POLAR_RADIUS_RELATION_ID,
        *(
            item
            for pair in _POLAR_COMPONENT_IDS.values()
            for item in pair
        ),
    }
    if (
        len(payload["entities"]) != 1
        or len(payload["motion_intervals"]) != 1
        or len(payload["queries"]) != 1
        or len(payload["events"]) != 3
        or len(payload["quantities"]) != 6
        or len(payload["symbols"]) != 6
        or payload["reference_frames"]
        or payload["points"]
        or payload["geometry"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
        or payload["principle_hints"]
        or payload["ambiguities"]
        or payload["unsupported_features"]
        or payload["figure_dependency"] != {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        }
        or reserved_ids & _authored_draft_ids(payload)
    ):
        return None

    particle = payload["entities"][0]
    if particle.get("primitive") != "particle":
        return None
    particle_id = particle.get("entity_id")
    interval = payload["motion_intervals"][0]
    interval_id = interval.get("interval_id")
    start_id = interval.get("start_event_id")
    finish_id = interval.get("end_event_id")
    if (
        interval.get("subject_ids") != [particle_id]
        or interval.get("frame_id") is not None
        or start_id is None
        or finish_id is None
        or start_id == finish_id
    ):
        return None

    source_evidence_ids = {
        item.get("evidence_id") for item in payload["source_evidence"]
    }
    if not set(interval.get("evidence_refs", ())).issubset(source_evidence_ids):
        return None
    if any(
        item.get("subject_id") != particle_id
        or item.get("interval_id") not in {None, interval_id}
        or item.get("proposed_role") is not None
        or item.get("proposed_value") is not None
        or item.get("proposed_unit") is not None
        or not item.get("evidence_refs")
        or not set(item["evidence_refs"]).issubset(source_evidence_ids)
        for item in payload["assumptions"]
    ):
        return None

    events = {item.get("event_id"): item for item in payload["events"]}
    if len(events) != 3:
        return None
    start = events.get(start_id)
    finish = events.get(finish_id)
    occurrences = [
        item for item in payload["events"]
        if item.get("event_id") not in {start_id, finish_id}
    ]
    if (
        start is None
        or finish is None
        or len(occurrences) != 1
        or start.get("kind") != "start"
        or finish.get("kind") != "finish"
        or occurrences[0].get("kind") != "other"
        or any(
            item.get("subject_ids") != [particle_id]
            or item.get("time_quantity_id") is not None
            or item.get("evidence_refs")
            for item in payload["events"]
        )
        or start.get("interval_ids") != [interval_id]
        or finish.get("interval_ids") != [interval_id]
        or start.get("occurs_in_interval_ids")
        or finish.get("occurs_in_interval_ids")
        or occurrences[0].get("interval_ids")
        or occurrences[0].get("occurs_in_interval_ids") != [interval_id]
    ):
        return None
    instant_id = occurrences[0]["event_id"]

    query = payload["queries"][0]
    target = query["target"]
    target_quantity_id = target.get("target_quantity_id")
    target_quantities = [
        item for item in payload["quantities"]
        if item.get("quantity_id") == target_quantity_id
    ]
    query_key = (target.get("role"), target.get("component"))
    if query_key == ("velocity", "magnitude"):
        closed_query_key = ("speed", "magnitude")
    else:
        closed_query_key = query_key
    if (
        len(target_quantities) != 1
        or closed_query_key not in _POLAR_COMPONENT_IDS
        or query.get("shape") != "scalar"
        or query.get("evidence_refs")
        or target.get("subject_id") != particle_id
        or target.get("point_id") is not None
        or target.get("frame_id") is not None
        or target.get("interval_id") != interval_id
        or target.get("event_id") != instant_id
        or target.get("direction") not in (None, {})
    ):
        return None
    query_quantity = target_quantities[0]
    if (
        query_quantity.get("role") != query_key[0]
        or query_quantity.get("subject_id") != particle_id
        or query_quantity.get("point_id") is not None
        or query_quantity.get("frame_id") is not None
        or query_quantity.get("interval_id") != interval_id
        or query_quantity.get("event_id") != instant_id
        or query_quantity.get("component") != query_key[1]
        or query_quantity.get("direction") not in (None, {})
        or query_quantity.get("shape") != "scalar"
        or query_quantity.get("raw_value") is not None
        or query_quantity.get("raw_unit") is not None
        or query_quantity.get("provenance") != "unknown"
        or not query_quantity.get("symbol_id")
        or query_quantity.get("evidence_refs")
        or query.get("output_dimension") != query_quantity.get("dimension")
    ):
        return None

    known = [
        item for item in payload["quantities"]
        if item.get("quantity_id") != target_quantity_id
    ]

    def source_quantity(
        role: str,
        component: str | None,
        directions: frozenset[str],
    ) -> dict[str, Any] | None:
        matches = [
            item
            for item in known
            if item.get("role") == role
            and (component is None or item.get("component") == component)
            and (item.get("direction") or {}).get("kind") == "semantic"
            and (item.get("direction") or {}).get("direction") in directions
        ]
        if len(matches) != 1:
            return None
        item = matches[0]
        stated_direction = item["direction"]["direction"]
        expected_component = (
            stated_direction if role.startswith("angular_") else component
        )
        refs = set(item.get("evidence_refs", ()))
        if (
            item.get("subject_id") != particle_id
            or item.get("point_id") is not None
            or item.get("frame_id") is not None
            or item.get("interval_id") != interval_id
            or item.get("event_id") != instant_id
            or item.get("component") != expected_component
            or item.get("shape") != "scalar"
            or item.get("raw_value") is None
            or item.get("raw_unit") is None
            or item.get("provenance") != "explicit_source"
            or not item.get("symbol_id")
            or not refs
            or not refs.issubset(source_evidence_ids)
        ):
            return None
        return item

    radius = source_quantity("radius", "radial", frozenset({"radial"}))
    radial_rate = source_quantity(
        "velocity", "radial", frozenset({"radial"})
    )
    radial_acceleration = source_quantity(
        "acceleration", "radial", frozenset({"radial"})
    )
    omega = source_quantity(
        "angular_velocity", None, frozenset({"clockwise", "counterclockwise"})
    )
    alpha = source_quantity(
        "angular_acceleration",
        None,
        frozenset({"clockwise", "counterclockwise"}),
    )
    source_state = (
        radius,
        radial_rate,
        radial_acceleration,
        omega,
        alpha,
    )
    if (
        any(item is None for item in source_state)
        or len({item["quantity_id"] for item in source_state if item is not None}) != 5
        or omega["direction"]["direction"] != alpha["direction"]["direction"]
    ):
        return None
    state_evidence = sorted(
        {
            evidence_id
            for item in source_state
            for evidence_id in item["evidence_refs"]
        }
    )
    if not state_evidence or len(state_evidence) > 16:
        return None

    symbols_by_quantity: dict[str, list[dict[str, Any]]] = {}
    for symbol in payload["symbols"]:
        symbols_by_quantity.setdefault(symbol.get("quantity_id"), []).append(symbol)
    if any(
        len(symbols_by_quantity.get(item.get("quantity_id"), ())) != 1
        or symbols_by_quantity[item["quantity_id"]][0].get("symbol_id")
        != item.get("symbol_id")
        or symbols_by_quantity[item["quantity_id"]][0].get("dimension")
        != item.get("dimension")
        or symbols_by_quantity[item["quantity_id"]][0].get("shape") != "scalar"
        for item in payload["quantities"]
    ):
        return None

    def axis_direction(axis: str, sign: int = 1) -> dict[str, Any]:
        return {
            "kind": "axis",
            "frame_id": POLAR_FRAME_ID,
            "axis": axis,
            "sign": sign,
        }

    frame = {
        "frame_id": POLAR_FRAME_ID,
        "frame_type": "radial_transverse",
        "origin": {"kind": "world"},
        "axes": [
            {"axis": axis, "direction": axis_direction(axis)}
            for axis in ("radial", "transverse")
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": state_evidence,
    }
    coordinate = {
        "entity_id": POLAR_COORDINATE_ENTITY_ID,
        "primitive": "reference_frame",
        "label": "polar coordinate",
        "aliases": [],
        "component_of_entity_id": None,
        "evidence_refs": state_evidence,
        "model_confidence": None,
    }

    rewritten_particle = dict(particle)
    rewritten_particle["evidence_refs"] = sorted(
        set(particle.get("evidence_refs", ())) | set(state_evidence)
    )
    if len(rewritten_particle["evidence_refs"]) > 16:
        return None

    angular_sign = (
        -1 if omega["direction"]["direction"] == "clockwise" else 1
    )
    source_by_id = {
        radius["quantity_id"]: ("radial", 1),
        radial_rate["quantity_id"]: ("radial", 1),
        radial_acceleration["quantity_id"]: ("radial", 1),
        omega["quantity_id"]: ("transverse", angular_sign),
        alpha["quantity_id"]: ("transverse", angular_sign),
    }
    rewritten_quantities: list[dict[str, Any]] = []
    rebound: list[str] = []
    for original in payload["quantities"]:
        if original["quantity_id"] == target_quantity_id:
            continue
        quantity = dict(original)
        axis, sign = source_by_id[quantity["quantity_id"]]
        quantity.update(
            subject_id=POLAR_COORDINATE_ENTITY_ID,
            frame_id=POLAR_FRAME_ID,
            interval_id=interval_id,
            event_id=None,
            component=axis,
            direction=axis_direction(axis, sign),
        )
        rewritten_quantities.append(quantity)
        rebound.append(quantity["quantity_id"])

    generated_quantities: list[dict[str, Any]] = []
    generated_symbols: list[dict[str, Any]] = []
    created: set[str] = {
        POLAR_COORDINATE_ENTITY_ID,
        POLAR_FRAME_ID,
        POLAR_RADIUS_RELATION_ID,
    }
    component_dimensions = {
        ("velocity", "radial"): radial_rate["dimension"],
        ("velocity", "transverse"): radial_rate["dimension"],
        ("speed", "magnitude"): radial_rate["dimension"],
        ("acceleration", "radial"): radial_acceleration["dimension"],
        ("acceleration", "transverse"): radial_acceleration["dimension"],
        ("acceleration", "magnitude"): radial_acceleration["dimension"],
    }
    closed_query_quantity: dict[str, Any] | None = None
    for component_key, (quantity_id, symbol_id) in _POLAR_COMPONENT_IDS.items():
        role, component = component_key
        direction = (
            axis_direction(component)
            if component in {"radial", "transverse"} else None
        )
        if component_key == closed_query_key:
            item = dict(query_quantity)
            item.update(
                role=role,
                subject_id=particle_id,
                point_id=None,
                frame_id=POLAR_FRAME_ID,
                interval_id=interval_id,
                event_id=None,
                component=component,
                direction=direction,
                evidence_refs=state_evidence,
            )
            closed_query_quantity = item
            rebound.append(item["quantity_id"])
            rewritten_quantities.append(item)
            continue
        item = {
            "quantity_id": quantity_id,
            "symbol_id": symbol_id,
            "role": role,
            "subject_id": particle_id,
            "point_id": None,
            "frame_id": POLAR_FRAME_ID,
            "interval_id": interval_id,
            "event_id": None,
            "component": component,
            "direction": direction,
            "shape": "scalar",
            "dimension": component_dimensions[component_key],
            "provenance": "inferred",
            "evidence_refs": state_evidence,
            "assumption_policy_ref": None,
            "correction_id": None,
            "model_confidence": None,
            "raw_value": None,
            "raw_unit": None,
        }
        generated_quantities.append(item)
        generated_symbols.append(
            {
                "symbol_id": symbol_id,
                "quantity_id": quantity_id,
                "dimension": component_dimensions[component_key],
                "shape": "scalar",
                "vector_length": None,
            }
        )
        created.update({quantity_id, symbol_id})
    if closed_query_quantity is None:
        return None

    rewritten_interval = dict(interval)
    rewritten_interval.update(
        subject_ids=[particle_id, POLAR_COORDINATE_ENTITY_ID],
        frame_id=POLAR_FRAME_ID,
        start_event_id=None,
        end_event_id=None,
        evidence_refs=state_evidence,
    )
    rewritten_query = dict(query)
    rewritten_target = dict(target)
    rewritten_target.update(
        role=closed_query_key[0],
        subject_id=particle_id,
        point_id=None,
        frame_id=POLAR_FRAME_ID,
        interval_id=interval_id,
        event_id=None,
        component=closed_query_key[1],
        direction=closed_query_quantity["direction"],
        target_quantity_id=target_quantity_id,
    )
    rewritten_query.update(
        target=rewritten_target,
        evidence_refs=state_evidence,
    )
    radius_relation = {
        "relation_id": POLAR_RADIUS_RELATION_ID,
        "kind": "radius",
        "participant_ids": [particle_id, POLAR_COORDINATE_ENTITY_ID],
        "expression": None,
        "quantity_ids": [radius["quantity_id"]],
        "interval_id": interval_id,
        "evidence_refs": list(radius["evidence_refs"]),
    }

    closed = dict(payload)
    closed["entities"] = [rewritten_particle, coordinate]
    closed["reference_frames"] = [frame]
    closed["motion_intervals"] = [rewritten_interval]
    closed["events"] = []
    closed["symbols"] = [*payload["symbols"], *generated_symbols]
    closed["quantities"] = [*rewritten_quantities, *generated_quantities]
    closed["geometry"] = [radius_relation]
    closed["queries"] = [rewritten_query]
    return closed, tuple(sorted(created)), tuple(sorted(rebound))


def _slot_pin_relative_frame_transaction(
    payload: dict[str, Any], _authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Derive one radial/transverse frame from one exact pin-slot relation.

    The transaction creates no value, interaction, force, point, constraint,
    state, or assumption.  It rebinds only the single unknown quantity named by
    the single query and the query target itself.  Its only intended downstream
    effect is the compiler's existing typed deferred terminal.
    """

    if len(payload["queries"]) != 1:
        return None
    query = payload["queries"][0]
    target = query["target"]
    if (
        target.get("role") not in {"velocity", "acceleration"}
        or target.get("component") not in {"radial", "transverse"}
        or target.get("frame_id") is not None
        or not target.get("target_quantity_id")
        or not target.get("subject_id")
        or not target.get("interval_id")
    ):
        return None

    target_quantity_id = target["target_quantity_id"]
    query_quantities = [
        item
        for item in payload["quantities"]
        if item["quantity_id"] == target_quantity_id
    ]
    if len(query_quantities) != 1:
        return None
    query_quantity = query_quantities[0]
    if (
        query_quantity.get("role") != target.get("role")
        or query_quantity.get("subject_id") != target.get("subject_id")
        or query_quantity.get("point_id") != target.get("point_id")
        or query_quantity.get("interval_id") != target.get("interval_id")
        or query_quantity.get("event_id") != target.get("event_id")
        or query_quantity.get("component") != target.get("component")
        or query_quantity.get("frame_id") is not None
        or query_quantity.get("direction") is not None
        or query_quantity.get("raw_value") is not None
        or query_quantity.get("raw_unit") is not None
        or query_quantity.get("shape") != "scalar"
    ):
        return None

    entities = {item["entity_id"]: item for item in payload["entities"]}
    points = {item["point_id"]: item for item in payload["points"]}
    subject_id = target["subject_id"]
    query_point = points.get(target.get("point_id") or "")
    point_owner = query_point.get("owner_entity_id") if query_point else None
    allowed_pin_primitives = {"joint", "particle", "body_component"}
    pin_candidates = {
        entity_id
        for entity_id in {subject_id, point_owner}
        if entity_id in entities
        and entities[entity_id]["primitive"] in allowed_pin_primitives
    }
    if len(pin_candidates) != 1:
        return None
    pin_id = next(iter(pin_candidates))
    owned_point_ids = {
        item["point_id"]
        for item in payload["points"]
        if item.get("owner_entity_id") == pin_id
    }
    slot_ids = {
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "slot"
    }
    relations = []
    for relation in payload["geometry"]:
        if (
            relation.get("kind") != "lies_on"
            or relation.get("interval_id") not in {None, target["interval_id"]}
        ):
            continue
        participants = set(relation.get("participant_ids") or ())
        matching_slots = participants & slot_ids
        matching_pins = participants & {pin_id, *owned_point_ids}
        if len(matching_slots) == 1 and matching_pins:
            relations.append((relation, next(iter(matching_slots))))
    if len(relations) != 1:
        return None
    relation, slot_id = relations[0]
    if slot_id == pin_id:
        return None

    if SLOT_PIN_FRAME_ID in _authored_draft_ids(payload):
        return None
    frame = {
        "frame_id": SLOT_PIN_FRAME_ID,
        "frame_type": "radial_transverse",
        "origin": {"kind": "entity", "entity_id": slot_id},
        "axes": [
            {
                "axis": axis,
                "direction": {
                    "kind": "axis",
                    "frame_id": SLOT_PIN_FRAME_ID,
                    "axis": axis,
                    "sign": 1,
                },
            }
            for axis in ("radial", "transverse")
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": list(relation.get("evidence_refs") or ()),
    }

    quantities = []
    for original in payload["quantities"]:
        quantity = dict(original)
        if quantity["quantity_id"] == target_quantity_id:
            quantity["frame_id"] = SLOT_PIN_FRAME_ID
        quantities.append(quantity)
    queries = [dict(query)]
    query_target = dict(target)
    query_target["frame_id"] = SLOT_PIN_FRAME_ID
    queries[0]["target"] = query_target

    closed = dict(payload)
    closed["reference_frames"] = [*payload["reference_frames"], frame]
    closed["quantities"] = quantities
    closed["queries"] = queries
    return closed, (SLOT_PIN_FRAME_ID,), (target_quantity_id,)


def _rotating_relative_frame_transaction(
    payload: dict[str, Any], _authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Write one exact source-implied rotating frame, without an answer.

    One point-like subject, one rigid carrier, one topology edge, one signed
    carrier angular velocity, one radial/transverse relative velocity, and one
    radius are required.  The transaction creates only a world frame, a
    rotating child frame, and its reference point; it re-expresses the source's
    own directions in those frames and binds the existing unknown query.
    """

    if len(payload["queries"]) != 1 or payload["reference_frames"] or payload["points"]:
        return None
    query = payload["queries"][0]
    target = query["target"]
    target_quantity_id = target.get("target_quantity_id")
    interval_id = target.get("interval_id")
    if (
        query.get("shape") != "scalar"
        or target.get("role") != "acceleration"
        or target.get("component") not in {"magnitude", "unspecified"}
        or target.get("frame_id") is not None
        or target.get("direction") is not None
        or target.get("point_id") is not None
        or target_quantity_id is None
        or interval_id is None
    ):
        return None

    entities = {item["entity_id"]: item for item in payload["entities"]}
    moving_id = target.get("subject_id")
    if (
        moving_id not in entities
        or entities[moving_id]["primitive"]
        not in {"joint", "particle", "body_component"}
    ):
        return None
    observers = [
        item["entity_id"] for item in payload["entities"]
        if item["primitive"] == "reference_frame"
    ]
    if len(observers) != 1:
        return None
    intervals = [
        item for item in payload["motion_intervals"]
        if item["interval_id"] == interval_id
    ]
    if (
        len(intervals) != 1
        or moving_id not in intervals[0]["subject_ids"]
        or intervals[0].get("frame_id") is not None
    ):
        return None

    targets = [
        item for item in payload["quantities"]
        if item["quantity_id"] == target_quantity_id
    ]
    if len(targets) != 1:
        return None
    target_quantity = targets[0]
    if (
        target_quantity.get("role") != "acceleration"
        or target_quantity.get("subject_id") != moving_id
        or target_quantity.get("point_id") is not None
        or target_quantity.get("interval_id") != interval_id
        or target_quantity.get("event_id") != target.get("event_id")
        or target_quantity.get("component") != target.get("component")
        or target_quantity.get("shape") != "scalar"
        or target_quantity.get("frame_id") is not None
        or target_quantity.get("direction") is not None
        or target_quantity.get("raw_value") is not None
        or target_quantity.get("raw_unit") is not None
        or target_quantity.get("provenance") != "unknown"
        or target_quantity.get("symbol_id") is None
    ):
        return None

    angular = [
        item for item in payload["quantities"]
        if item["role"] == "angular_velocity"
        and item.get("interval_id") == interval_id
        and item.get("event_id") == target.get("event_id")
        and item.get("raw_value") is not None
        and item.get("raw_unit") is not None
        and item.get("symbol_id") is not None
        and item.get("frame_id") is None
        and item.get("shape") == "scalar"
        and item.get("subject_id") in entities
        and entities[item["subject_id"]]["primitive"] == "rigid_body"
        and (item.get("direction") or {}).get("kind") == "semantic"
        and (item.get("direction") or {}).get("direction")
        in {"clockwise", "counterclockwise"}
    ]
    relatives = [
        item for item in payload["quantities"]
        if item["role"] in {"velocity", "speed"}
        and item.get("subject_id") == moving_id
        and item.get("point_id") is None
        and item.get("interval_id") == interval_id
        and item.get("event_id") == target.get("event_id")
        and item.get("raw_value") is not None
        and item.get("raw_unit") is not None
        and item.get("symbol_id") is not None
        and item.get("frame_id") is None
        and item.get("shape") == "scalar"
        and item.get("component") in {"radial", "transverse"}
        and (item.get("direction") or {}).get("kind") == "semantic"
        and (item.get("direction") or {}).get("direction")
        == item.get("component")
    ]
    radii = [
        item for item in payload["quantities"]
        if item["role"] == "radius"
        and item.get("subject_id") == moving_id
        and item.get("interval_id") == interval_id
        and item.get("event_id") == target.get("event_id")
        and item.get("raw_value") is not None
        and item.get("raw_unit") is not None
        and item.get("symbol_id") is not None
        and item.get("shape") == "scalar"
    ]
    if len(angular) != 1 or len(relatives) != 1 or len(radii) != 1:
        return None
    carrier_id = angular[0]["subject_id"]
    if carrier_id == moving_id or carrier_id not in intervals[0]["subject_ids"]:
        return None
    relations = [
        item for item in payload["geometry"]
        if item["kind"] == "topology_connects"
        and item.get("interval_id") in {None, interval_id}
        and not item.get("quantity_ids")
        and item.get("expression") is None
        and len(item["participant_ids"]) == 2
        and set(item["participant_ids"]) == {moving_id, carrier_id}
    ]
    if len(relations) != 1:
        return None

    created = {ROTATING_WORLD_FRAME_ID, ROTATING_FRAME_ID, ROTATION_POINT_ID}
    if _authored_draft_ids(payload) & created:
        return None
    world = {
        "frame_id": ROTATING_WORLD_FRAME_ID,
        "frame_type": "cartesian_3d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": axis,
                "direction": {
                    "kind": "axis",
                    "frame_id": ROTATING_WORLD_FRAME_ID,
                    "axis": axis,
                    "sign": 1,
                },
            }
            for axis in ("x", "y", "z")
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }
    point = {
        "point_id": ROTATION_POINT_ID,
        "role": "reference",
        "owner_entity_id": carrier_id,
        "frame_id": ROTATING_WORLD_FRAME_ID,
        "label": None,
        "evidence_refs": list(relations[0].get("evidence_refs") or []),
    }
    rotating = {
        "frame_id": ROTATING_FRAME_ID,
        "frame_type": "rotating",
        "origin": {"kind": "point", "point_id": ROTATION_POINT_ID},
        "axes": [
            {
                "axis": axis,
                "direction": {
                    "kind": "axis",
                    "frame_id": ROTATING_FRAME_ID,
                    "axis": axis,
                    "sign": 1,
                },
            }
            for axis in ("radial", "transverse", "z")
        ],
        "parent_frame_id": ROTATING_WORLD_FRAME_ID,
        "translating_with_entity_id": carrier_id,
        "rotating_about_point_id": ROTATION_POINT_ID,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": list(relations[0].get("evidence_refs") or []),
    }

    angular_id = angular[0]["quantity_id"]
    relative_id = relatives[0]["quantity_id"]
    rebound: list[str] = []
    quantities: list[dict[str, Any]] = []
    for original in payload["quantities"]:
        quantity = dict(original)
        if quantity["quantity_id"] == angular_id:
            semantic = (quantity.get("direction") or {}).get("direction")
            quantity["frame_id"] = ROTATING_FRAME_ID
            quantity["component"] = "z"
            quantity["direction"] = {
                "kind": "axis",
                "frame_id": ROTATING_FRAME_ID,
                "axis": "z",
                "sign": 1 if semantic == "counterclockwise" else -1,
            }
            rebound.append(quantity["quantity_id"])
        elif quantity["quantity_id"] == relative_id:
            axis = quantity["component"]
            quantity["frame_id"] = ROTATING_FRAME_ID
            quantity["direction"] = {
                "kind": "axis",
                "frame_id": ROTATING_FRAME_ID,
                "axis": axis,
                "sign": 1,
            }
            rebound.append(quantity["quantity_id"])
        elif quantity["quantity_id"] == target_quantity_id:
            quantity["frame_id"] = ROTATING_FRAME_ID
            rebound.append(quantity["quantity_id"])
        quantities.append(quantity)
    if set(rebound) != {angular_id, relative_id, target_quantity_id}:
        return None

    intervals_out: list[dict[str, Any]] = []
    for original in payload["motion_intervals"]:
        interval = dict(original)
        if interval["interval_id"] == interval_id:
            interval["frame_id"] = ROTATING_FRAME_ID
        intervals_out.append(interval)
    queries = [dict(item) for item in payload["queries"]]
    target_out = dict(queries[0]["target"])
    target_out["frame_id"] = ROTATING_FRAME_ID
    queries[0]["target"] = target_out

    closed = dict(payload)
    closed["points"] = [*payload["points"], point]
    closed["reference_frames"] = [*payload["reference_frames"], world, rotating]
    closed["motion_intervals"] = intervals_out
    closed["quantities"] = quantities
    closed["queries"] = queries
    return (
        closed,
        (ROTATING_WORLD_FRAME_ID, ROTATING_FRAME_ID, ROTATION_POINT_ID),
        tuple(sorted(rebound)),
    )


def _relative_translating_frame_transaction(
    payload: dict[str, Any], _authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Write down the observer the source already named.

    The corpus states an observer as an entity of primitive `reference_frame`
    and states one body's motion relative to it.  The compiler recognises that
    situation only as a typed frame pair — a world frame, and a `translating`
    frame parented to it and carried by the observer entity — and then defers the
    readout with a precise code.  Neither frame alone reaches that recognition,
    so both, the axis, and every component binding are created together.

    This creates no force and no interaction, so it cannot assemble a partial
    free body.  It also cannot produce an answer: the only terminal it can reach
    is the engine's own deferral.
    """

    if not payload["queries"]:
        return None
    query = payload["queries"][0]
    subject_id = query["target"]["subject_id"]
    observers = [
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "reference_frame"
    ]
    if len(observers) != 1 or observers[0] == subject_id:
        return None
    observer_id = observers[0]
    axis = _axis_binding(payload["quantities"], subject_id)
    if axis is None:
        return None
    if _axis_binding(payload["quantities"], observer_id) not in {None, axis}:
        return None
    if _query_axis_conflicts(query, axis):
        return None
    if _authored_draft_ids(payload) & {WORLD_FRAME_ID, OBSERVER_FRAME_ID}:
        return None

    world = {
        "frame_id": WORLD_FRAME_ID,
        "frame_type": "cartesian_2d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": name,
                "direction": {
                    "kind": "axis",
                    "frame_id": WORLD_FRAME_ID,
                    "axis": name,
                    "sign": 1,
                },
            }
            for name in ("x", "y")
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }
    moving = {
        **world,
        "frame_id": OBSERVER_FRAME_ID,
        "frame_type": "translating",
        "axes": [
            {
                "axis": name,
                "direction": {
                    "kind": "axis",
                    "frame_id": OBSERVER_FRAME_ID,
                    "axis": name,
                    "sign": 1,
                },
            }
            for name in ("x", "y")
        ],
        "parent_frame_id": WORLD_FRAME_ID,
        "translating_with_entity_id": observer_id,
    }

    target_quantity_id = query["target"].get("target_quantity_id")
    rebound: list[str] = []
    quantities: list[dict[str, Any]] = []
    for original in payload["quantities"]:
        quantity = dict(original)
        owner = quantity["subject_id"]
        if owner not in {subject_id, observer_id}:
            quantities.append(quantity)
            continue
        if quantity["role"] not in _COMPONENT_ROLES:
            quantities.append(quantity)
            continue
        direction = quantity.get("direction") or {}
        if direction.get("kind") == "semantic":
            binding = _SEMANTIC_AXIS_BINDING.get(direction.get("direction", ""))
            if binding is None or binding[0] != axis:
                return None
            # What the source states about the body is stated *relative to* the
            # observer it named; what it states about the observer is that
            # observer's own motion, which the world frame carries.
            frame_id = OBSERVER_FRAME_ID if owner == subject_id else WORLD_FRAME_ID
            quantity["direction"] = {
                "kind": "axis",
                "frame_id": frame_id,
                "axis": axis,
                "sign": binding[1],
            }
            quantity["component"] = axis
            quantity["frame_id"] = frame_id
            quantities.append(quantity)
            rebound.append(quantity["quantity_id"])
            continue
        if (
            quantity["quantity_id"] == target_quantity_id
            and not direction
            and quantity.get("component") != _DIRECTIONLESS_COMPONENT
        ):
            # The unknown the question asks for: the body's motion as the world
            # sees it.  It gains a component and a frame, never a direction.
            quantity["component"] = axis
            quantity["frame_id"] = WORLD_FRAME_ID
            quantities.append(quantity)
            rebound.append(quantity["quantity_id"])
            continue
        quantities.append(quantity)

    if target_quantity_id not in rebound or len(rebound) < 2:
        # The absolute unknown and at least one stated relative quantity must
        # both land, or the transaction has not built the profile at all.
        return None

    queries = [dict(item) for item in payload["queries"]]
    target = dict(queries[0]["target"])
    # The question is the body's motion as the *world* sees it.
    target["component"] = axis
    target["frame_id"] = WORLD_FRAME_ID
    queries[0]["target"] = target

    closed = dict(payload)
    closed["reference_frames"] = [*payload["reference_frames"], world, moving]
    closed["quantities"] = quantities
    closed["queries"] = queries
    return closed, (WORLD_FRAME_ID, OBSERVER_FRAME_ID), tuple(rebound)


# Every record the free-flight transaction creates, under one namespace so a
# collision with any authored ID abandons the transaction instead of merging
# with it.
GRAVITY_QUANTITY_ID = "qty_closure_gravity"
GRAVITY_SYMBOL_ID = "sym_closure_gravity"
GRAVITY_INTERACTION_ID = "rel_closure_gravity"
VERTICAL_ACCELERATION_QUANTITY_ID = "qty_closure_accel_y"
VERTICAL_ACCELERATION_SYMBOL_ID = "sym_closure_accel_y"

_ACCELERATION_DIMENSION: dict[str, int] = {"length": 1, "time": -2}
_GRAVITY_ROLE = "gravity"
_VERTICAL_AXIS = "y"


def _free_flight_gravity_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Free flight under gravity alone, closed as one whole or not at all.

    Creates together the pieces the planner proved must be created together:
    the world frame and its axes, the vertical binding of the subject's own
    stated directions, the gravity interaction, the server-valued gravity
    magnitude, and the unknown vertical acceleration the gravity law writes
    about (`a_y = -g`).

    The gravity value is not invented here and cannot be.  It is admitted only
    as the exact immutable :class:`AssumptionAuthorization` the Lane B
    authority stage issued for this Draft's own approved `constant_gravity`
    assumption — same subject, same interval, same role, same value, same unit
    — and the quantity carries `assumption_policy_ref` so `validate_draft`
    holds it to that authorization to the character.  No authorization, or an
    authorization about another subject or no interval, refuses the whole
    transaction.

    Deliberately narrow.  A Draft that already carries any gravity quantity,
    any gravity interaction, or any acceleration for this subject and interval
    is not the shape this transaction closes; a subject whose stated
    directions bind a horizontal axis needs the vector decomposition this
    profile does not have; and a stated direction is only ever re-expressed
    against the axis it already names — nothing gains a direction the source
    did not state.  The query is left exactly as asked: a magnitude question
    stays a magnitude question.
    """

    if not payload["queries"]:
        return None
    query = payload["queries"][0]
    subject_id = query["target"]["subject_id"]

    # Exactly one approved constant_gravity assumption, and the authority
    # stage must have issued its authorization.
    candidates = [
        item
        for item in payload["assumptions"]
        if item["kind"] == "constant_gravity"
        and item["disposition"] == "approved"
        and item["assumption_id"] in authority.approved_assumption_ids
    ]
    if len(candidates) != 1:
        return None
    assumption = candidates[0]
    authorization = authority.authorized_assumptions.get(
        assumption["assumption_id"]
    )
    if type(authorization) is not AssumptionAuthorization:
        return None
    if authorization.assumption_id != assumption["assumption_id"]:
        return None
    if str(getattr(authorization.role, "value", authorization.role)) != _GRAVITY_ROLE:
        return None
    # The authorization must restate the Draft's own approved proposal to the
    # character.  The bundle already guarantees this; the transaction checks it
    # again so a forged map cannot make closure write any value the Draft's own
    # authority does not carry.  (The validator and the compiler each verify it
    # a further time.)
    if (
        str(assumption.get("proposed_role") or "") != _GRAVITY_ROLE
        or assumption.get("proposed_value") != authorization.raw_value
        or assumption.get("proposed_unit") != authorization.raw_unit
        or assumption.get("subject_id") != authorization.subject_id
        or assumption.get("interval_id") != authorization.interval_id
    ):
        return None
    if authorization.subject_id != subject_id:
        # Gravity authorised for another entity licenses nothing about this
        # body's flight.
        return None
    interval_id = authorization.interval_id
    if interval_id is None:
        # Free flight is an interval regime; an authority scoped to no
        # interval names none.
        return None
    if not any(
        item["interval_id"] == interval_id for item in payload["motion_intervals"]
    ):
        return None

    # A Draft already carrying gravity structure, or an acceleration for this
    # subject and interval, is not this shape.
    for item in payload["quantities"]:
        if item["role"] == _GRAVITY_ROLE:
            return None
        if (
            item["role"] == "acceleration"
            and item["subject_id"] == subject_id
            and item["interval_id"] == interval_id
        ):
            return None
    for item in payload["interactions"]:
        if item["kind"] == "gravity":
            return None

    # Created IDs must be fresh across the whole Draft, not just the four
    # namespaces the created records enter.
    created_ids = {
        GRAVITY_QUANTITY_ID,
        GRAVITY_SYMBOL_ID,
        GRAVITY_INTERACTION_ID,
        VERTICAL_ACCELERATION_QUANTITY_ID,
        VERTICAL_ACCELERATION_SYMBOL_ID,
        WORLD_FRAME_ID,
    }
    if _authored_draft_ids(payload) & created_ids:
        return None

    # Gravity fixes the vertical.  Stated directions on the subject may only
    # agree with it: a stated horizontal axis is a shape this profile cannot
    # close without the vector decomposition it does not have.
    stated_axis = _axis_binding(payload["quantities"], subject_id)
    if stated_axis not in (None, _VERTICAL_AXIS):
        return None
    axis = _VERTICAL_AXIS

    world = {
        "frame_id": WORLD_FRAME_ID,
        "frame_type": "cartesian_2d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": name,
                "direction": {
                    "kind": "axis",
                    "frame_id": WORLD_FRAME_ID,
                    "axis": name,
                    "sign": 1,
                },
            }
            for name in ("x", "y")
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }

    rebound: list[str] = []
    quantities: list[dict[str, Any]] = []
    for original in payload["quantities"]:
        quantity = dict(original)
        if (
            quantity["subject_id"] != subject_id
            or quantity["role"] not in _COMPONENT_ROLES
        ):
            quantities.append(quantity)
            continue
        direction = quantity.get("direction") or {}
        if direction.get("kind") == "semantic":
            binding = _SEMANTIC_AXIS_BINDING.get(direction.get("direction", ""))
            if binding is None or binding[0] != axis:
                # A direction on another axis cannot be folded into this one.
                return None
            quantity["direction"] = {
                "kind": "axis",
                "frame_id": WORLD_FRAME_ID,
                "axis": axis,
                "sign": binding[1],
            }
            quantity["component"] = axis
            quantity["frame_id"] = WORLD_FRAME_ID
            rebound.append(quantity["quantity_id"])
        # A magnitude, an already-bound direction, or a directionless unknown
        # is left exactly as the source stated it: this transaction never
        # invents a direction.
        quantities.append(quantity)

    gravity_quantity = {
        "quantity_id": GRAVITY_QUANTITY_ID,
        "symbol_id": GRAVITY_SYMBOL_ID,
        "role": _GRAVITY_ROLE,
        "subject_id": authorization.subject_id,
        "point_id": None,
        "frame_id": None,
        "interval_id": interval_id,
        "event_id": None,
        "component": "magnitude",
        "shape": "scalar",
        "dimension": dict(_ACCELERATION_DIMENSION),
        "provenance": "server_default",
        "raw_value": authorization.raw_value,
        "raw_unit": authorization.raw_unit,
        "assumption_policy_ref": authorization.assumption_id,
        "evidence_refs": [],
    }
    acceleration_quantity = {
        "quantity_id": VERTICAL_ACCELERATION_QUANTITY_ID,
        "symbol_id": VERTICAL_ACCELERATION_SYMBOL_ID,
        "role": "acceleration",
        "subject_id": subject_id,
        "point_id": None,
        "frame_id": WORLD_FRAME_ID,
        "interval_id": interval_id,
        "event_id": None,
        "component": axis,
        "shape": "scalar",
        "dimension": dict(_ACCELERATION_DIMENSION),
        "provenance": "unknown",
        "evidence_refs": [],
    }
    symbols = [
        *payload["symbols"],
        {
            "symbol_id": GRAVITY_SYMBOL_ID,
            "quantity_id": GRAVITY_QUANTITY_ID,
            "dimension": dict(_ACCELERATION_DIMENSION),
            "shape": "scalar",
        },
        {
            "symbol_id": VERTICAL_ACCELERATION_SYMBOL_ID,
            "quantity_id": VERTICAL_ACCELERATION_QUANTITY_ID,
            "dimension": dict(_ACCELERATION_DIMENSION),
            "shape": "scalar",
        },
    ]
    interaction = {
        "interaction_id": GRAVITY_INTERACTION_ID,
        "kind": "gravity",
        "participant_ids": [subject_id],
        "point_ids": [],
        "frame_id": WORLD_FRAME_ID,
        "interval_id": interval_id,
        "event_id": None,
        "quantity_ids": [
            VERTICAL_ACCELERATION_QUANTITY_ID,
            GRAVITY_QUANTITY_ID,
        ],
        "evidence_refs": [],
    }

    closed = dict(payload)
    closed["reference_frames"] = [*payload["reference_frames"], world]
    closed["quantities"] = [*quantities, gravity_quantity, acceleration_quantity]
    closed["symbols"] = symbols
    closed["interactions"] = [*payload["interactions"], interaction]
    return (
        closed,
        (
            WORLD_FRAME_ID,
            GRAVITY_INTERACTION_ID,
            GRAVITY_QUANTITY_ID,
            VERTICAL_ACCELERATION_QUANTITY_ID,
        ),
        tuple(rebound),
    )


def _fixed_pulley_mass_value(quantity: Mapping[str, Any]) -> float | None:
    raw_value = quantity.get("raw_value")
    raw_unit = quantity.get("raw_unit")
    if raw_value is None or raw_unit is None:
        return None
    try:
        normalized = normalize_quantity(
            raw_value,
            raw_unit,
            "scalar",
            _MASS_DIMENSION,
        )
    except Exception:
        return None
    value = normalized.value
    return value if type(value) is float and value > 0.0 else None


def _exact_zero_source_angle(quantity: Mapping[str, Any]) -> bool:
    """True only for a stated angle whose value is exactly zero.

    Zero is the one angle that reads the same in every angular unit, so the
    check needs no unit policy and cannot be widened by one: a value that is
    absent, non-numeric, non-finite, or merely small is not a stated zero.
    """

    raw_value = quantity.get("raw_value")
    if type(raw_value) is not str:
        return False
    try:
        value = float(raw_value)
    except ValueError:
        return False
    return value == 0.0


def _fixed_pulley_acceleration_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact ideal fixed-pulley acceleration problem.

    The source has already identified the two moving bodies, one rope, one
    non-inertial pulley, their wraps/connects topology, and the idealisations
    scoped by the projection.  This transaction supplies the complete free
    body that the existing Newton/rope laws require.  It never changes an
    entity primitive, never writes a number other than the separately
    authorised gravity default, and leaves the aggregate magnitude query in
    place for a reusable readout law.
    """

    if len(payload["queries"]) != 1 or len(payload["motion_intervals"]) != 1:
        return None
    query = payload["queries"][0]
    target = query["target"]
    if (
        target.get("role") != "acceleration"
        or target.get("component") != "magnitude"
        or target.get("frame_id") is not None
        or target.get("point_id") is not None
        or target.get("event_id") is not None
        or target.get("direction") is not None
        or query.get("shape") != "scalar"
    ):
        return None
    interval = payload["motion_intervals"][0]
    interval_id = interval["interval_id"]
    if target.get("interval_id") != interval_id:
        return None

    primitive_by_id = {
        item["entity_id"]: item["primitive"] for item in payload["entities"]
    }
    system_id = target.get("subject_id")
    if primitive_by_id.get(system_id) != "system":
        return None
    # A support primitive with no typed support relation is not an inert
    # bystander: whether a body rests on it decides the whole free body, so
    # the vertical two-body shape refuses rather than guessing it away.
    if any(
        item["primitive"] in {"surface", "incline"}
        for item in payload["entities"]
    ):
        return None
    rope_ids = tuple(
        sorted(
            item["entity_id"]
            for item in payload["entities"]
            if item["primitive"] == "rope"
        )
    )
    pulley_ids = tuple(
        sorted(
            item["entity_id"]
            for item in payload["entities"]
            if item["primitive"] == "pulley"
        )
    )
    if len(rope_ids) != 1 or len(pulley_ids) != 1:
        return None
    rope_id = rope_ids[0]
    pulley_id = pulley_ids[0]
    if pulley_id in interval["subject_ids"]:
        return None

    query_quantities = tuple(
        item
        for item in payload["quantities"]
        if item["quantity_id"] == target.get("target_quantity_id")
    )
    if (
        len(query_quantities) != 1
        or query_quantities[0]["role"] != "acceleration"
        or query_quantities[0]["subject_id"] != system_id
        or query_quantities[0].get("raw_value") is not None
        or query_quantities[0].get("raw_unit") is not None
        or query_quantities[0].get("frame_id") is not None
        or query_quantities[0].get("component") != "magnitude"
    ):
        return None

    mass_records: list[tuple[float, dict[str, Any]]] = []
    for item in payload["quantities"]:
        if item["role"] != "mass":
            continue
        if primitive_by_id.get(item["subject_id"]) not in {
            "particle",
            "rigid_body",
            "body_component",
        }:
            continue
        value = _fixed_pulley_mass_value(item)
        if value is None:
            return None
        mass_records.append((value, item))
    if len(mass_records) != 2:
        return None
    mass_records.sort(key=lambda item: (item[0], item[1]["subject_id"]))
    if mass_records[0][0] == mass_records[1][0]:
        return None
    light_mass = mass_records[0][1]
    heavy_mass = mass_records[1][1]
    light_id = light_mass["subject_id"]
    heavy_id = heavy_mass["subject_id"]
    moving_ids = {light_id, heavy_id}
    if not moving_ids.issubset(interval["subject_ids"]):
        return None

    # This adapter owns the entire simple FBD.  Existing partial structure or
    # an inertial/angular pulley is a different profile and is refused.
    if (
        payload["reference_frames"]
        or payload["points"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
        or any(
            item["role"] in {"force", "gravity"}
            or (
                item["role"] == "acceleration"
                and item["quantity_id"] != target.get("target_quantity_id")
            )
            for item in payload["quantities"]
        )
        or any(
            item["subject_id"] == pulley_id
            and item["role"]
            in {
                "moment_of_inertia",
                "angular_position",
                "angular_velocity",
                "angular_acceleration",
            }
            for item in payload["quantities"]
        )
    ):
        return None

    wraps = tuple(
        item
        for item in payload["geometry"]
        if item["kind"] == "wraps" and item["interval_id"] == interval_id
    )
    connects = tuple(
        item
        for item in payload["geometry"]
        if item["kind"] == "topology_connects"
        and item["interval_id"] == interval_id
    )
    if (
        len(payload["geometry"]) != 2
        or len(wraps) != 1
        or len(connects) != 1
        or set(connects[0]["participant_ids"]) != moving_ids
        or set(wraps[0]["participant_ids"]) != {*moving_ids, pulley_id}
    ):
        return None

    assumption_by_kind: dict[str, dict[str, Any]] = {}
    for kind, assumption_id in _FIXED_PULLEY_SCOPED_ASSUMPTIONS.items():
        matches = tuple(
            item
            for item in payload["assumptions"]
            if item["assumption_id"] == assumption_id
            and item["kind"] == kind
            and item["disposition"] == "approved"
            and item["assumption_id"] in authority.approved_assumption_ids
            and item["interval_id"] == interval_id
            and item["evidence_refs"]
        )
        if len(matches) != 1:
            return None
        assumption_by_kind[kind] = matches[0]
    if (
        assumption_by_kind["massless_rope"]["subject_id"] != rope_id
        or assumption_by_kind["inextensible_rope"]["subject_id"] != rope_id
        or assumption_by_kind["fixed_pulley"]["subject_id"] != pulley_id
        or assumption_by_kind["ideal_massless_frictionless_pulley"]["subject_id"]
        != pulley_id
    ):
        return None

    gravity_assumptions = tuple(
        item
        for item in payload["assumptions"]
        if item["kind"] == "constant_gravity"
        and item["disposition"] == "approved"
        and item["assumption_id"] in authority.approved_assumption_ids
        and item["interval_id"] == interval_id
        and item["subject_id"] == system_id
    )
    if len(gravity_assumptions) != 1:
        return None
    gravity_assumption = gravity_assumptions[0]
    gravity_authorization = authority.authorized_assumptions.get(
        gravity_assumption["assumption_id"]
    )
    if type(gravity_authorization) is not AssumptionAuthorization:
        return None
    if (
        gravity_authorization.assumption_id
        != gravity_assumption["assumption_id"]
        or gravity_authorization.subject_id != system_id
        or gravity_authorization.interval_id != interval_id
        or str(
            getattr(gravity_authorization.role, "value", gravity_authorization.role)
        )
        != "gravity"
        or gravity_assumption.get("proposed_value")
        != gravity_authorization.raw_value
        or gravity_assumption.get("proposed_unit")
        != gravity_authorization.raw_unit
    ):
        return None

    suffixes = {light_id: "light", heavy_id: "heavy"}
    quantity_ids: dict[tuple[str, str], str] = {}
    symbol_ids: dict[tuple[str, str], str] = {}
    for subject_id, suffix in suffixes.items():
        for role, short in (
            ("weight", "weight"),
            ("tension", "tension"),
            ("acceleration", "accel"),
        ):
            quantity_ids[(subject_id, role)] = (
                f"qty_closure_fixed_pulley_{short}_{suffix}"
            )
            symbol_ids[(subject_id, role)] = (
                f"sym_closure_fixed_pulley_{short}_{suffix}"
            )

    created_ids = {
        FIXED_PULLEY_FRAME_ID,
        FIXED_PULLEY_GRAVITY_QUANTITY_ID,
        FIXED_PULLEY_GRAVITY_SYMBOL_ID,
        FIXED_PULLEY_GRAVITY_LIGHT_ID,
        FIXED_PULLEY_GRAVITY_HEAVY_ID,
        FIXED_PULLEY_ROPE_INTERACTION_ID,
        FIXED_PULLEY_WRAP_ID,
        FIXED_PULLEY_ATTACH_LIGHT_ID,
        FIXED_PULLEY_ATTACH_HEAVY_ID,
        FIXED_PULLEY_TAUT_STATE_ID,
        FIXED_PULLEY_FIXED_STATE_ID,
        *quantity_ids.values(),
        *symbol_ids.values(),
    }
    if _authored_draft_ids(payload) & created_ids:
        return None

    rope_evidence = tuple(
        sorted(
            set(assumption_by_kind["massless_rope"]["evidence_refs"])
            | set(assumption_by_kind["inextensible_rope"]["evidence_refs"])
        )
    )
    pulley_evidence = tuple(
        sorted(
            set(assumption_by_kind["fixed_pulley"]["evidence_refs"])
            | set(
                assumption_by_kind[
                    "ideal_massless_frictionless_pulley"
                ]["evidence_refs"]
            )
        )
    )
    gravity_evidence = tuple(gravity_assumption["evidence_refs"])
    topology_evidence = tuple(
        sorted(set(rope_evidence) | set(pulley_evidence))
    )
    frame_evidence = tuple(
        sorted(set(topology_evidence) | set(gravity_evidence))
    )

    frame = {
        "frame_id": FIXED_PULLEY_FRAME_ID,
        "frame_type": "cartesian_1d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": "y",
                "direction": {
                    "kind": "axis",
                    "frame_id": FIXED_PULLEY_FRAME_ID,
                    "axis": "y",
                    "sign": 1,
                },
            }
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": list(frame_evidence),
    }
    gravity_quantity = {
        "quantity_id": FIXED_PULLEY_GRAVITY_QUANTITY_ID,
        "symbol_id": FIXED_PULLEY_GRAVITY_SYMBOL_ID,
        "role": "gravity",
        "subject_id": system_id,
        "point_id": None,
        "frame_id": None,
        "interval_id": interval_id,
        "event_id": None,
        "component": "magnitude",
        "shape": "scalar",
        "dimension": dict(_ACCELERATION_DIMENSION),
        "provenance": "server_default",
        "raw_value": gravity_authorization.raw_value,
        "raw_unit": gravity_authorization.raw_unit,
        "assumption_policy_ref": gravity_authorization.assumption_id,
        "evidence_refs": list(gravity_evidence),
    }
    generated_quantities: list[dict[str, Any]] = [gravity_quantity]
    generated_symbols: list[dict[str, Any]] = [
        {
            "symbol_id": FIXED_PULLEY_GRAVITY_SYMBOL_ID,
            "quantity_id": FIXED_PULLEY_GRAVITY_QUANTITY_ID,
            "dimension": dict(_ACCELERATION_DIMENSION),
            "shape": "scalar",
        }
    ]
    for subject_id, mass in ((light_id, light_mass), (heavy_id, heavy_mass)):
        mass_evidence = tuple(mass["evidence_refs"])
        signs = {
            "weight": -1,
            "tension": 1,
            "acceleration": 1 if subject_id == light_id else -1,
        }
        evidence_by_role = {
            "weight": tuple(sorted(set(mass_evidence) | set(gravity_evidence))),
            "tension": topology_evidence,
            "acceleration": topology_evidence,
        }
        for role in ("weight", "tension", "acceleration"):
            physical_role = "force" if role in {"weight", "tension"} else role
            dimension = (
                dict(_FORCE_DIMENSION)
                if physical_role == "force"
                else dict(_ACCELERATION_DIMENSION)
            )
            quantity_id = quantity_ids[(subject_id, role)]
            symbol_id = symbol_ids[(subject_id, role)]
            generated_quantities.append(
                {
                    "quantity_id": quantity_id,
                    "symbol_id": symbol_id,
                    "role": physical_role,
                    "subject_id": subject_id,
                    "point_id": None,
                    "frame_id": FIXED_PULLEY_FRAME_ID,
                    "interval_id": interval_id,
                    "event_id": None,
                    "component": "y",
                    "direction": {
                        "kind": "axis",
                        "frame_id": FIXED_PULLEY_FRAME_ID,
                        "axis": "y",
                        "sign": signs[role],
                    },
                    "shape": "scalar",
                    "dimension": dimension,
                    "provenance": "unknown",
                    "evidence_refs": list(evidence_by_role[role]),
                }
            )
            generated_symbols.append(
                {
                    "symbol_id": symbol_id,
                    "quantity_id": quantity_id,
                    "dimension": dimension,
                    "shape": "scalar",
                }
            )

    gravity_interactions = []
    for subject_id, mass, interaction_id in (
        (light_id, light_mass, FIXED_PULLEY_GRAVITY_LIGHT_ID),
        (heavy_id, heavy_mass, FIXED_PULLEY_GRAVITY_HEAVY_ID),
    ):
        gravity_interactions.append(
            {
                "interaction_id": interaction_id,
                "kind": "gravity",
                "participant_ids": [subject_id],
                "point_ids": [],
                "frame_id": FIXED_PULLEY_FRAME_ID,
                "interval_id": interval_id,
                "event_id": None,
                "quantity_ids": [
                    mass["quantity_id"],
                    FIXED_PULLEY_GRAVITY_QUANTITY_ID,
                    quantity_ids[(subject_id, "weight")],
                ],
                "evidence_refs": list(
                    sorted(set(mass["evidence_refs"]) | set(gravity_evidence))
                ),
            }
        )
    rope_interaction = {
        "interaction_id": FIXED_PULLEY_ROPE_INTERACTION_ID,
        "kind": "rope_tension",
        "participant_ids": [light_id, heavy_id, rope_id, pulley_id],
        "point_ids": [],
        "frame_id": FIXED_PULLEY_FRAME_ID,
        "interval_id": interval_id,
        "event_id": None,
        "quantity_ids": [
            quantity_ids[(light_id, "tension")],
            quantity_ids[(heavy_id, "tension")],
        ],
        "evidence_refs": list(topology_evidence),
    }
    canonical_geometry = [
        {
            "relation_id": FIXED_PULLEY_WRAP_ID,
            "kind": "wraps",
            "participant_ids": [rope_id, pulley_id],
            "expression": None,
            "quantity_ids": [],
            "interval_id": interval_id,
            "evidence_refs": list(pulley_evidence),
        },
        {
            "relation_id": FIXED_PULLEY_ATTACH_LIGHT_ID,
            "kind": "attached",
            "participant_ids": [rope_id, light_id],
            "expression": None,
            "quantity_ids": [],
            "interval_id": interval_id,
            "evidence_refs": list(rope_evidence),
        },
        {
            "relation_id": FIXED_PULLEY_ATTACH_HEAVY_ID,
            "kind": "attached",
            "participant_ids": [rope_id, heavy_id],
            "expression": None,
            "quantity_ids": [],
            "interval_id": interval_id,
            "evidence_refs": list(rope_evidence),
        },
    ]
    states = [
        {
            "state_condition_id": FIXED_PULLEY_TAUT_STATE_ID,
            "kind": "rope",
            "state": "taut",
            "subject_id": rope_id,
            "interval_id": interval_id,
            "event_id": None,
            "quantity_ids": [],
            "evidence_refs": list(rope_evidence),
        },
        {
            "state_condition_id": FIXED_PULLEY_FIXED_STATE_ID,
            "kind": "motion",
            "state": "at_rest",
            "subject_id": pulley_id,
            "interval_id": interval_id,
            "event_id": None,
            "quantity_ids": [],
            "evidence_refs": list(pulley_evidence),
        },
    ]
    closed_interval = dict(interval)
    closed_interval["frame_id"] = FIXED_PULLEY_FRAME_ID
    closed_interval["subject_ids"] = sorted(
        set(interval["subject_ids"]) | {rope_id, pulley_id}
    )
    closed_interval["evidence_refs"] = list(frame_evidence)

    closed = dict(payload)
    closed["reference_frames"] = [frame]
    closed["motion_intervals"] = [closed_interval]
    closed["symbols"] = [*payload["symbols"], *generated_symbols]
    closed["quantities"] = [*payload["quantities"], *generated_quantities]
    closed["geometry"] = canonical_geometry
    closed["interactions"] = [*gravity_interactions, rope_interaction]
    closed["state_conditions"] = states
    return closed, tuple(sorted(created_ids)), ()



def _incline_hanging_pulley_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact frictionless incline/hanging fixed-pulley graph.

    The source already supplies two masses, one incline angle, one unique
    connected/wrapped/lying-on topology and the idealisations.  This adapter
    derives only the frames, force-bearing interactions, contact/rope state and
    unknown component quantities required by the existing generic laws.  The
    aggregate acceleration-magnitude query is rebound to one rope-constrained
    body axis whose sign is fixed by the source-valued drive comparison; no
    acceleration value or answer is written here.
    """

    if (
        len(payload["queries"]) != 1
        or len(payload["motion_intervals"]) != 1
        or payload["reference_frames"]
        or payload["points"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
    ):
        return None
    query = payload["queries"][0]
    target = query["target"]
    interval = payload["motion_intervals"][0]
    interval_id = interval["interval_id"]
    if (
        target.get("role") != "acceleration"
        or target.get("component") != "magnitude"
        or target.get("frame_id") is not None
        or target.get("point_id") is not None
        or target.get("event_id") is not None
        or target.get("direction") is not None
        or target.get("interval_id") != interval_id
        or query.get("shape") != "scalar"
    ):
        return None

    primitive_by_id = {
        item["entity_id"]: item["primitive"] for item in payload["entities"]
    }
    system_id = target.get("subject_id")
    if primitive_by_id.get(system_id) != "system":
        return None
    rope_ids = tuple(
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "rope"
    )
    pulley_ids = tuple(
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "pulley"
    )
    incline_ids = tuple(
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "incline"
    )
    if len(rope_ids) != 1 or len(pulley_ids) != 1 or len(incline_ids) != 1:
        return None
    rope_id = rope_ids[0]
    pulley_id = pulley_ids[0]
    incline_id = incline_ids[0]
    if pulley_id in interval["subject_ids"]:
        return None

    query_quantity = next(
        (
            item
            for item in payload["quantities"]
            if item["quantity_id"] == target.get("target_quantity_id")
        ),
        None,
    )
    if (
        query_quantity is None
        or query_quantity["role"] != "acceleration"
        or query_quantity["subject_id"] != system_id
        or query_quantity.get("raw_value") is not None
        or query_quantity.get("raw_unit") is not None
        or query_quantity.get("evidence_refs")
    ):
        return None

    mass_records: list[tuple[float, dict[str, Any]]] = []
    for item in payload["quantities"]:
        if item["role"] != "mass":
            continue
        if primitive_by_id.get(item["subject_id"]) not in {
            "particle", "rigid_body", "body_component"
        }:
            continue
        value = _fixed_pulley_mass_value(item)
        if value is None or not item.get("evidence_refs"):
            return None
        mass_records.append((value, item))
    if len(mass_records) != 2:
        return None
    mass_by_id = {item[1]["subject_id"]: item for item in mass_records}

    angle_records = tuple(
        item for item in payload["quantities"]
        if item["role"] == "angle" and item["subject_id"] == incline_id
    )
    if len(angle_records) != 1 or not angle_records[0].get("evidence_refs"):
        return None
    angle_quantity = angle_records[0]
    try:
        angle_value = normalize_quantity(
            angle_quantity["raw_value"],
            angle_quantity["raw_unit"],
            "scalar",
            DimensionVector.dimensionless(),
        ).value
    except Exception:
        return None
    if type(angle_value) is not float or not 0.0 <= angle_value < 1.5707963267948966:
        return None

    wraps = tuple(item for item in payload["geometry"] if item["kind"] == "wraps")
    connects = tuple(
        item for item in payload["geometry"] if item["kind"] == "topology_connects"
    )
    supports = tuple(item for item in payload["geometry"] if item["kind"] == "lies_on")
    if (
        len(payload["geometry"]) != 3
        or len(wraps) != 1
        or len(connects) != 1
        or len(supports) != 1
        or any(item.get("interval_id") != interval_id for item in payload["geometry"])
    ):
        return None
    moving_ids = set(mass_by_id)
    if (
        set(connects[0]["participant_ids"]) != moving_ids
        or set(wraps[0]["participant_ids"]) != {*moving_ids, pulley_id}
        or len(set(supports[0]["participant_ids"]) & moving_ids) != 1
        or incline_id not in supports[0]["participant_ids"]
    ):
        return None
    incline_body_id = next(iter(set(supports[0]["participant_ids"]) & moving_ids))
    hanging_body_id = next(iter(moving_ids - {incline_body_id}))
    mass_incline_value, mass_incline = mass_by_id[incline_body_id]
    mass_hanging_value, mass_hanging = mass_by_id[hanging_body_id]
    drive = mass_incline_value * __import__("math").sin(angle_value) - mass_hanging_value
    scale = max(1.0, abs(mass_incline_value), abs(mass_hanging_value))
    if abs(drive) <= 1.0e-12 * scale:
        return None
    incline_sign = 1 if drive > 0.0 else -1
    hanging_sign = -incline_sign

    if any(
        item["role"] in {"force", "gravity", "coefficient_friction"}
        or (
            item["role"] == "acceleration"
            and item["quantity_id"] != query_quantity["quantity_id"]
        )
        or (
            item["subject_id"] == pulley_id
            and item["role"] in {
                "moment_of_inertia", "angular_position", "angular_velocity",
                "angular_acceleration", "moment", "torque",
            }
        )
        for item in payload["quantities"]
    ):
        return None

    assumption_by_kind: dict[str, dict[str, Any]] = {}
    for kind, assumption_id in _FIXED_PULLEY_SCOPED_ASSUMPTIONS.items():
        matches = tuple(
            item for item in payload["assumptions"]
            if item["assumption_id"] == assumption_id
            and item["kind"] == kind
            and item["disposition"] == "approved"
            and assumption_id in authority.approved_assumption_ids
            and item["interval_id"] == interval_id
            and item.get("evidence_refs")
        )
        if len(matches) != 1:
            return None
        assumption_by_kind[kind] = matches[0]
    if (
        assumption_by_kind["massless_rope"]["subject_id"] != rope_id
        or assumption_by_kind["inextensible_rope"]["subject_id"] != rope_id
        or assumption_by_kind["fixed_pulley"]["subject_id"] != pulley_id
        or assumption_by_kind["ideal_massless_frictionless_pulley"]["subject_id"] != pulley_id
    ):
        return None

    gravity_assumptions = tuple(
        item for item in payload["assumptions"]
        if item["kind"] == "constant_gravity"
        and item["disposition"] == "approved"
        and item["assumption_id"] in authority.approved_assumption_ids
        and item["interval_id"] == interval_id
        and item["subject_id"] == system_id
        and item.get("evidence_refs")
    )
    frictionless = tuple(
        item for item in payload["assumptions"]
        if item["kind"] == "frictionless"
        and item["disposition"] == "approved"
        and item["assumption_id"] in authority.approved_assumption_ids
        and item["interval_id"] == interval_id
        and item["subject_id"] == system_id
        and item.get("evidence_refs")
    )
    if len(gravity_assumptions) != 1 or len(frictionless) != 1:
        return None
    gravity_assumption = gravity_assumptions[0]
    gravity_authorization = authority.authorized_assumptions.get(
        gravity_assumption["assumption_id"]
    )
    if (
        type(gravity_authorization) is not AssumptionAuthorization
        or gravity_authorization.assumption_id != gravity_assumption["assumption_id"]
        or gravity_authorization.subject_id != system_id
        or gravity_authorization.interval_id != interval_id
        or str(getattr(gravity_authorization.role, "value", gravity_authorization.role)) != "gravity"
        or gravity_assumption.get("proposed_value") != gravity_authorization.raw_value
        or gravity_assumption.get("proposed_unit") != gravity_authorization.raw_unit
    ):
        return None

    ids = {
        "world": INCLINE_HANGING_WORLD_ID,
        "world_frame": INCLINE_HANGING_WORLD_FRAME_ID,
        "incline_frame": INCLINE_HANGING_INCLINE_FRAME_ID,
        "point": INCLINE_HANGING_CONTACT_POINT_ID,
        "gravity": INCLINE_HANGING_GRAVITY_ID,
        "gravity_symbol": INCLINE_HANGING_GRAVITY_SYMBOL_ID,
        "gravity_tangent": "qty_closure_incline_hanging_gravity_tangent",
        "gravity_tangent_symbol": "sym_closure_incline_hanging_gravity_tangent",
        "gravity_normal": "qty_closure_incline_hanging_gravity_normal",
        "gravity_normal_symbol": "sym_closure_incline_hanging_gravity_normal",
        "weight_hanging": "qty_closure_incline_hanging_weight",
        "weight_hanging_symbol": "sym_closure_incline_hanging_weight",
        "normal": "qty_closure_incline_hanging_normal",
        "normal_symbol": "sym_closure_incline_hanging_normal",
        "tension_incline": "qty_closure_incline_hanging_tension_incline",
        "tension_incline_symbol": "sym_closure_incline_hanging_tension_incline",
        "tension_hanging": "qty_closure_incline_hanging_tension_hanging",
        "tension_hanging_symbol": "sym_closure_incline_hanging_tension_hanging",
        "rope_tension": "qty_closure_incline_hanging_rope_tension",
        "rope_tension_symbol": "sym_closure_incline_hanging_rope_tension",
        "accel_incline": "qty_closure_incline_hanging_accel_incline",
        "accel_incline_symbol": "sym_closure_incline_hanging_accel_incline",
        "accel_normal": "qty_closure_incline_hanging_accel_normal",
        "accel_normal_symbol": "sym_closure_incline_hanging_accel_normal",
        "rope_accel": "qty_closure_incline_hanging_rope_accel",
        "rope_accel_symbol": "sym_closure_incline_hanging_rope_accel",
        "angle_relation": "geo_closure_incline_hanging_angle",
        "wrap": "geo_closure_incline_hanging_wrap",
        "attach_incline": "geo_closure_incline_hanging_attach_incline",
        "attach_hanging": "geo_closure_incline_hanging_attach_hanging",
        "gravity_incline": "rel_closure_incline_hanging_gravity_incline",
        "gravity_hanging": "rel_closure_incline_hanging_gravity_hanging",
        "contact": "rel_closure_incline_hanging_contact",
        "rope_interaction": "rel_closure_incline_hanging_rope",
        "rope_state": "state_closure_incline_hanging_rope_taut",
        "pulley_state": "state_closure_incline_hanging_pulley_fixed",
        "contact_state": "state_closure_incline_hanging_contact",
        "incline_state": "state_closure_incline_hanging_incline_fixed",
        "friction_state": "state_closure_incline_hanging_frictionless",
    }
    if _authored_draft_ids(payload) & set(ids.values()):
        return None

    rope_evidence = tuple(sorted(
        set(assumption_by_kind["massless_rope"]["evidence_refs"])
        | set(assumption_by_kind["inextensible_rope"]["evidence_refs"])
    ))
    pulley_evidence = tuple(sorted(
        set(assumption_by_kind["fixed_pulley"]["evidence_refs"])
        | set(assumption_by_kind["ideal_massless_frictionless_pulley"]["evidence_refs"])
    ))
    gravity_evidence = tuple(gravity_assumption["evidence_refs"])
    contact_evidence = tuple(frictionless[0]["evidence_refs"])
    angle_evidence = tuple(angle_quantity["evidence_refs"])
    mass_incline_evidence = tuple(mass_incline["evidence_refs"])
    mass_hanging_evidence = tuple(mass_hanging["evidence_refs"])
    orientation_evidence = tuple(sorted(
        set(rope_evidence) | set(pulley_evidence) | set(contact_evidence)
        | set(angle_evidence) | set(gravity_evidence)
    ))
    query_evidence = tuple(sorted(
        set(orientation_evidence) | set(mass_incline_evidence) | set(mass_hanging_evidence)
    ))

    def axis_direction(frame_id: str, axis: str, sign: int) -> dict[str, Any]:
        return {"kind": "axis", "frame_id": frame_id, "axis": axis, "sign": sign}

    world_frame = {
        "frame_id": ids["world_frame"], "frame_type": "cartesian_2d",
        "origin": {"kind": "world"},
        "axes": [
            {"axis": "x", "direction": axis_direction(ids["world_frame"], "x", 1)},
            {"axis": "y", "direction": axis_direction(ids["world_frame"], "y", 1)},
        ],
        "evidence_refs": list(orientation_evidence),
    }
    incline_frame = {
        "frame_id": ids["incline_frame"], "frame_type": "tangential_normal",
        "origin": {"kind": "entity", "entity_id": incline_id},
        "axes": [
            {"axis": "tangent", "direction": axis_direction(ids["incline_frame"], "tangent", 1)},
            {"axis": "normal", "direction": axis_direction(ids["incline_frame"], "normal", 1)},
        ],
        "parent_frame_id": ids["world_frame"],
        "evidence_refs": list(orientation_evidence),
    }

    generated_quantities: list[dict[str, Any]] = []
    generated_symbols: list[dict[str, Any]] = []
    def add_unknown(key: str, role: str, subject: str, dimension: dict[str, int], *,
                    frame: str | None = None, component: str = "magnitude",
                    sign: int | None = None, point: str | None = None,
                    evidence: tuple[str, ...] = ()) -> None:
        qid=ids[key]; sid=ids[f"{key}_symbol"]
        item={
            "quantity_id": qid, "symbol_id": sid, "role": role,
            "subject_id": subject, "point_id": point, "frame_id": frame,
            "interval_id": interval_id, "event_id": None,
            "component": component, "shape": "scalar",
            "dimension": dict(dimension), "provenance": "unknown",
            "evidence_refs": list(evidence),
        }
        if sign is not None and frame is not None:
            axis = "tangent" if component == "tangential" else component
            item["direction"] = axis_direction(frame, axis, sign)
        generated_quantities.append(item)
        generated_symbols.append({
            "symbol_id": sid, "quantity_id": qid,
            "dimension": dict(dimension), "shape": "scalar",
        })

    gravity_quantity = {
        "quantity_id": ids["gravity"], "symbol_id": ids["gravity_symbol"],
        "role": "gravity", "subject_id": system_id,
        "point_id": None, "frame_id": None, "interval_id": interval_id,
        "event_id": None, "component": "magnitude", "shape": "scalar",
        "dimension": dict(_ACCELERATION_DIMENSION),
        "provenance": "server_default",
        "raw_value": gravity_authorization.raw_value,
        "raw_unit": gravity_authorization.raw_unit,
        "assumption_policy_ref": gravity_authorization.assumption_id,
        "evidence_refs": list(gravity_evidence),
    }
    generated_quantities.append(gravity_quantity)
    generated_symbols.append({
        "symbol_id": ids["gravity_symbol"], "quantity_id": ids["gravity"],
        "dimension": dict(_ACCELERATION_DIMENSION), "shape": "scalar",
    })
    add_unknown("gravity_tangent", "force", incline_body_id, _FORCE_DIMENSION,
                frame=ids["incline_frame"], component="tangential", sign=1,
                evidence=tuple(sorted(set(gravity_evidence)|set(angle_evidence)|set(orientation_evidence))))
    add_unknown("gravity_normal", "force", incline_body_id, _FORCE_DIMENSION,
                frame=ids["incline_frame"], component="normal", sign=-1,
                evidence=tuple(sorted(set(gravity_evidence)|set(angle_evidence)|set(orientation_evidence))))
    add_unknown("weight_hanging", "force", hanging_body_id, _FORCE_DIMENSION,
                frame=ids["world_frame"], component="y", sign=1,
                evidence=tuple(sorted(set(gravity_evidence)|set(orientation_evidence))))
    add_unknown("normal", "force", incline_body_id, _FORCE_DIMENSION,
                frame=ids["incline_frame"], component="normal", sign=1,
                point=ids["point"], evidence=contact_evidence)
    add_unknown("tension_incline", "force", incline_body_id, _FORCE_DIMENSION,
                frame=ids["incline_frame"], component="tangential", sign=-1,
                evidence=rope_evidence)
    add_unknown("tension_hanging", "force", hanging_body_id, _FORCE_DIMENSION,
                frame=ids["world_frame"], component="y", sign=-1,
                evidence=rope_evidence)
    add_unknown("rope_tension", "force", rope_id, _FORCE_DIMENSION,
                evidence=rope_evidence)
    add_unknown("accel_incline", "acceleration", incline_body_id, _ACCELERATION_DIMENSION,
                frame=ids["incline_frame"], component="tangential", sign=incline_sign,
                evidence=query_evidence)
    add_unknown("accel_normal", "acceleration", incline_body_id, _ACCELERATION_DIMENSION,
                frame=ids["incline_frame"], component="normal", sign=1,
                evidence=contact_evidence)
    add_unknown("rope_accel", "acceleration", rope_id, _ACCELERATION_DIMENSION,
                evidence=rope_evidence)

    rebound_query_quantity = dict(query_quantity)
    rebound_query_quantity.update({
        "subject_id": hanging_body_id,
        "frame_id": ids["world_frame"],
        "interval_id": interval_id,
        "event_id": None,
        "component": "y",
        "direction": axis_direction(ids["world_frame"], "y", hanging_sign),
        "evidence_refs": list(query_evidence),
    })
    quantities = []
    unscoped_source_ids = {
        mass_incline["quantity_id"],
        mass_hanging["quantity_id"],
        angle_quantity["quantity_id"],
    }
    for item in payload["quantities"]:
        if item["quantity_id"] == query_quantity["quantity_id"]:
            quantities.append(rebound_query_quantity)
        elif item["quantity_id"] in unscoped_source_ids:
            entry = dict(item)
            entry["interval_id"] = None
            entry["event_id"] = None
            quantities.append(entry)
        else:
            quantities.append(item)
    quantities.extend(generated_quantities)

    entities=[]
    evidence_by_entity={
        system_id: query_evidence,
        incline_body_id: tuple(sorted(set(mass_incline_evidence)|set(contact_evidence))),
        hanging_body_id: tuple(sorted(set(mass_hanging_evidence)|set(rope_evidence))),
        incline_id: tuple(sorted(set(angle_evidence)|set(contact_evidence)|set(orientation_evidence))),
        pulley_id: pulley_evidence,
        rope_id: rope_evidence,
    }
    for item in payload["entities"]:
        entry=dict(item)
        entry["evidence_refs"]=list(evidence_by_entity.get(item["entity_id"], tuple(item.get("evidence_refs",()))))
        entities.append(entry)
    entities.append({
        "entity_id": ids["world"], "primitive": "environment",
        "evidence_refs": list(tuple(sorted(set(gravity_evidence)|set(orientation_evidence)))),
    })

    updated_interval=dict(interval)
    updated_interval.update({
        "subject_ids": sorted({item["entity_id"] for item in entities}),
        "frame_id": None, "start_event_id": None, "end_event_id": None,
        "evidence_refs": list(query_evidence),
    })
    events=payload["events"]
    if (
        len(events) != 2
        or {item["event_id"] for item in events} != {interval.get("start_event_id"), interval.get("end_event_id")}
        or any(item.get("evidence_refs") or item.get("time_quantity_id") for item in events)
        or any(item.get("event_id") is not None for item in payload["quantities"])
    ):
        return None

    geometry=[
        {"relation_id": ids["angle_relation"], "kind": "angle",
         "participant_ids": [incline_id, ids["world"]],
         "expression": None, "quantity_ids": [angle_quantity["quantity_id"]],
         "interval_id": None, "evidence_refs": list(angle_evidence)},
        {"relation_id": ids["wrap"], "kind": "wraps",
         "participant_ids": [rope_id, pulley_id], "expression": None,
         "quantity_ids": [ids["rope_tension"], ids["rope_accel"]],
         "interval_id": interval_id, "evidence_refs": list(pulley_evidence)},
        {"relation_id": ids["attach_incline"], "kind": "attached",
         "participant_ids": [rope_id, incline_body_id], "expression": None,
         "quantity_ids": [ids["tension_incline"], ids["accel_incline"], ids["rope_tension"], ids["rope_accel"]],
         "interval_id": interval_id, "evidence_refs": list(rope_evidence)},
        {"relation_id": ids["attach_hanging"], "kind": "attached",
         "participant_ids": [rope_id, hanging_body_id], "expression": None,
         "quantity_ids": [ids["tension_hanging"], query_quantity["quantity_id"], ids["rope_tension"], ids["rope_accel"]],
         "interval_id": interval_id, "evidence_refs": list(rope_evidence)},
    ]
    interactions=[
        {"interaction_id": ids["gravity_incline"], "kind": "gravity",
         "participant_ids": [incline_body_id, ids["world"]], "point_ids": [],
         "frame_id": ids["incline_frame"], "interval_id": interval_id, "event_id": None,
         "quantity_ids": [mass_incline["quantity_id"], ids["gravity"], ids["gravity_tangent"], ids["gravity_normal"]],
         "evidence_refs": list(tuple(sorted(set(mass_incline_evidence)|set(gravity_evidence)|set(angle_evidence)|set(orientation_evidence))))},
        {"interaction_id": ids["gravity_hanging"], "kind": "gravity",
         "participant_ids": [hanging_body_id, ids["world"]], "point_ids": [],
         "frame_id": ids["world_frame"], "interval_id": interval_id, "event_id": None,
         "quantity_ids": [mass_hanging["quantity_id"], ids["gravity"], ids["weight_hanging"]],
         "evidence_refs": list(tuple(sorted(set(mass_hanging_evidence)|set(gravity_evidence)|set(orientation_evidence))))},
        {"interaction_id": ids["contact"], "kind": "contact",
         "participant_ids": [incline_body_id, incline_id], "point_ids": [ids["point"]],
         "frame_id": ids["incline_frame"], "interval_id": interval_id, "event_id": None,
         "quantity_ids": [ids["normal"], ids["accel_normal"]],
         "evidence_refs": list(contact_evidence)},
        {"interaction_id": ids["rope_interaction"], "kind": "rope_tension",
         "participant_ids": [incline_body_id, hanging_body_id, rope_id, pulley_id],
         "point_ids": [], "frame_id": None, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [ids["tension_incline"], ids["tension_hanging"], ids["accel_incline"], query_quantity["quantity_id"], ids["rope_tension"], ids["rope_accel"]],
         "evidence_refs": list(tuple(sorted(set(rope_evidence)|set(pulley_evidence)|set(orientation_evidence))))},
    ]
    states=[
        {"state_condition_id": ids["rope_state"], "kind": "rope", "state": "taut",
         "subject_id": rope_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(rope_evidence)},
        {"state_condition_id": ids["pulley_state"], "kind": "motion", "state": "at_rest",
         "subject_id": pulley_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(pulley_evidence)},
        {"state_condition_id": ids["contact_state"], "kind": "contact", "state": "touching",
         "subject_id": incline_body_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [ids["normal"], ids["accel_normal"]], "evidence_refs": list(contact_evidence)},
        {"state_condition_id": ids["incline_state"], "kind": "motion", "state": "at_rest",
         "subject_id": incline_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(contact_evidence)},
        {"state_condition_id": ids["friction_state"], "kind": "friction", "state": "inactive",
         "subject_id": incline_body_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(contact_evidence)},
    ]
    queries=[dict(item) for item in payload["queries"]]
    query_target=dict(queries[0]["target"])
    query_target.update({
        "subject_id": hanging_body_id, "frame_id": ids["world_frame"],
        "interval_id": interval_id, "event_id": None, "component": "y",
        "direction": axis_direction(ids["world_frame"], "y", hanging_sign),
        "target_quantity_id": query_quantity["quantity_id"],
    })
    queries[0]["target"]=query_target
    queries[0]["evidence_refs"]=list(query_evidence)

    closed=dict(payload)
    closed.update({
        "entities": entities,
        "points": [{"point_id": ids["point"], "role": "contact", "owner_entity_id": incline_body_id,
                    "frame_id": ids["incline_frame"], "evidence_refs": list(contact_evidence)}],
        "reference_frames": [world_frame, incline_frame],
        "motion_intervals": [updated_interval],
        "events": [],
        "symbols": [*payload["symbols"], *generated_symbols],
        "quantities": quantities,
        "geometry": geometry,
        "interactions": interactions,
        "state_conditions": states,
        "queries": queries,
        # The aggregate source assumptions have been consumed to create exact
        # rope/pulley scope.  Retain the authorized gravity policy because the
        # server-default quantity references it; retain only the four derived
        # structural assumptions for the law graph.
        "assumptions": [
            gravity_assumption,
            *(assumption_by_kind[kind] for kind in (
                "massless_rope",
                "inextensible_rope",
                "fixed_pulley",
                "ideal_massless_frictionless_pulley",
            )),
        ],
    })
    return closed, tuple(sorted(ids.values())), (query_quantity["quantity_id"],)

def _table_pulley_two_body_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact frictionless table/hanging fixed-pulley graph.

    The source already supplies two masses, one horizontal-surface support,
    one unique connected/wrapped/lying-on topology and the idealisations.
    The support is the typed ``surface`` primitive; an incline support, an
    invented angle, or a stated friction coefficient is a different shape and
    is refused.  This adapter derives only the world frame, the force-bearing
    interactions, the contact/rope states and value-free unknown components
    required by the existing weight/Newton/contact/rope laws.  The aggregate
    acceleration-magnitude query is rebound to the hanging body's downward
    axis component; no acceleration value or answer is written here.
    """

    if (
        len(payload["queries"]) != 1
        or len(payload["motion_intervals"]) != 1
        or payload["reference_frames"]
        or payload["points"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
    ):
        return None
    query = payload["queries"][0]
    target = query["target"]
    interval = payload["motion_intervals"][0]
    interval_id = interval["interval_id"]
    if (
        target.get("role") != "acceleration"
        or target.get("component") != "magnitude"
        or target.get("frame_id") is not None
        or target.get("point_id") is not None
        or target.get("event_id") is not None
        or target.get("direction") is not None
        or target.get("interval_id") != interval_id
        or query.get("shape") != "scalar"
    ):
        return None

    primitive_by_id = {
        item["entity_id"]: item["primitive"] for item in payload["entities"]
    }
    system_id = target.get("subject_id")
    if primitive_by_id.get(system_id) != "system":
        return None
    rope_ids = tuple(
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "rope"
    )
    pulley_ids = tuple(
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "pulley"
    )
    surface_ids = tuple(
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "surface"
    )
    if any(item["primitive"] == "incline" for item in payload["entities"]):
        return None
    if len(rope_ids) != 1 or len(pulley_ids) != 1 or len(surface_ids) != 1:
        return None
    rope_id = rope_ids[0]
    pulley_id = pulley_ids[0]
    surface_id = surface_ids[0]
    if pulley_id in interval["subject_ids"]:
        return None

    query_quantity = next(
        (
            item
            for item in payload["quantities"]
            if item["quantity_id"] == target.get("target_quantity_id")
        ),
        None,
    )
    if (
        query_quantity is None
        or query_quantity["role"] != "acceleration"
        or query_quantity["subject_id"] != system_id
        or query_quantity.get("raw_value") is not None
        or query_quantity.get("raw_unit") is not None
        or query_quantity.get("evidence_refs")
    ):
        return None

    mass_records: list[tuple[float, dict[str, Any]]] = []
    for item in payload["quantities"]:
        if item["role"] != "mass":
            continue
        if primitive_by_id.get(item["subject_id"]) not in {
            "particle", "rigid_body", "body_component"
        }:
            continue
        value = _fixed_pulley_mass_value(item)
        if value is None or not item.get("evidence_refs"):
            return None
        mass_records.append((value, item))
    if len(mass_records) != 2:
        return None
    mass_by_id = {item[1]["subject_id"]: item for item in mass_records}

    # The support's orientation is the source's own statement or nothing.
    # Exactly one evidenced angle, owned by the support entity, whose value is
    # exactly zero, states that the support plane is horizontal — that the
    # support tangent is the world horizontal axis and the support normal the
    # world vertical one.  A generic `surface` primitive proves none of that
    # on its own: the same primitive carries banked roads and vertical tracks.
    # A missing angle is silence, not a zero, and a stated non-zero angle is a
    # different contact shape.
    support_angles = tuple(
        item
        for item in payload["quantities"]
        if item["role"] == "angle"
        and item["subject_id"] == surface_id
        and item.get("evidence_refs")
        and item.get("raw_value") is not None
        and _exact_zero_source_angle(item)
    )
    if len(support_angles) != 1:
        return None
    support_angle = support_angles[0]
    if any(
        item["role"] == "angle" and item["quantity_id"] != support_angle["quantity_id"]
        for item in payload["quantities"]
    ):
        return None

    # A friction coefficient or a stated force is typed evidence of a
    # different contact shape.
    if any(
        item["role"] in {"force", "gravity", "coefficient_friction"}
        or (
            item["role"] == "acceleration"
            and item["quantity_id"] != query_quantity["quantity_id"]
        )
        or (
            item["subject_id"] == pulley_id
            and item["role"] in {
                "moment_of_inertia", "angular_position", "angular_velocity",
                "angular_acceleration", "moment", "torque",
            }
        )
        for item in payload["quantities"]
    ):
        return None

    wraps = tuple(item for item in payload["geometry"] if item["kind"] == "wraps")
    connects = tuple(
        item for item in payload["geometry"] if item["kind"] == "topology_connects"
    )
    supports = tuple(item for item in payload["geometry"] if item["kind"] == "lies_on")
    if (
        len(payload["geometry"]) != 3
        or len(wraps) != 1
        or len(connects) != 1
        or len(supports) != 1
        or any(item.get("interval_id") != interval_id for item in payload["geometry"])
    ):
        return None
    moving_ids = set(mass_by_id)
    if (
        set(connects[0]["participant_ids"]) != moving_ids
        or set(wraps[0]["participant_ids"]) != {*moving_ids, pulley_id}
        or len(set(supports[0]["participant_ids"]) & moving_ids) != 1
        or surface_id not in supports[0]["participant_ids"]
        or len(supports[0]["participant_ids"]) != 2
    ):
        return None
    table_body_id = next(iter(set(supports[0]["participant_ids"]) & moving_ids))
    hanging_body_id = next(iter(moving_ids - {table_body_id}))
    mass_table_value, mass_table = mass_by_id[table_body_id]
    mass_hanging_value, mass_hanging = mass_by_id[hanging_body_id]
    if mass_table_value <= 0.0 or mass_hanging_value <= 0.0:
        return None

    assumption_by_kind: dict[str, dict[str, Any]] = {}
    for kind, assumption_id in _FIXED_PULLEY_SCOPED_ASSUMPTIONS.items():
        matches = tuple(
            item for item in payload["assumptions"]
            if item["assumption_id"] == assumption_id
            and item["kind"] == kind
            and item["disposition"] == "approved"
            and assumption_id in authority.approved_assumption_ids
            and item["interval_id"] == interval_id
            and item.get("evidence_refs")
        )
        if len(matches) != 1:
            return None
        assumption_by_kind[kind] = matches[0]
    if (
        assumption_by_kind["massless_rope"]["subject_id"] != rope_id
        or assumption_by_kind["inextensible_rope"]["subject_id"] != rope_id
        or assumption_by_kind["fixed_pulley"]["subject_id"] != pulley_id
        or assumption_by_kind["ideal_massless_frictionless_pulley"]["subject_id"] != pulley_id
    ):
        return None

    gravity_assumptions = tuple(
        item for item in payload["assumptions"]
        if item["kind"] == "constant_gravity"
        and item["disposition"] == "approved"
        and item["assumption_id"] in authority.approved_assumption_ids
        and item["interval_id"] == interval_id
        and item["subject_id"] == system_id
        and item.get("evidence_refs")
    )
    frictionless = tuple(
        item for item in payload["assumptions"]
        if item["kind"] == "frictionless"
        and item["disposition"] == "approved"
        and item["assumption_id"] in authority.approved_assumption_ids
        and item["interval_id"] == interval_id
        and item["subject_id"] == system_id
        and item.get("evidence_refs")
    )
    if len(gravity_assumptions) != 1 or len(frictionless) != 1:
        return None
    gravity_assumption = gravity_assumptions[0]
    gravity_authorization = authority.authorized_assumptions.get(
        gravity_assumption["assumption_id"]
    )
    if (
        type(gravity_authorization) is not AssumptionAuthorization
        or gravity_authorization.assumption_id != gravity_assumption["assumption_id"]
        or gravity_authorization.subject_id != system_id
        or gravity_authorization.interval_id != interval_id
        or str(getattr(gravity_authorization.role, "value", gravity_authorization.role)) != "gravity"
        or gravity_assumption.get("proposed_value") != gravity_authorization.raw_value
        or gravity_assumption.get("proposed_unit") != gravity_authorization.raw_unit
    ):
        return None

    ids = {
        "world": TABLE_PULLEY_WORLD_ID,
        "world_frame": TABLE_PULLEY_WORLD_FRAME_ID,
        "support_frame": TABLE_PULLEY_SUPPORT_FRAME_ID,
        "orientation": TABLE_PULLEY_ORIENTATION_RELATION_ID,
        "point": TABLE_PULLEY_CONTACT_POINT_ID,
        "gravity": TABLE_PULLEY_GRAVITY_ID,
        "gravity_symbol": TABLE_PULLEY_GRAVITY_SYMBOL_ID,
        "weight_table": "qty_closure_table_pulley_weight_table",
        "weight_table_symbol": "sym_closure_table_pulley_weight_table",
        "weight_hanging": "qty_closure_table_pulley_weight_hanging",
        "weight_hanging_symbol": "sym_closure_table_pulley_weight_hanging",
        "normal": "qty_closure_table_pulley_normal",
        "normal_symbol": "sym_closure_table_pulley_normal",
        "accel_normal": "qty_closure_table_pulley_accel_normal",
        "accel_normal_symbol": "sym_closure_table_pulley_accel_normal",
        "tension_table": "qty_closure_table_pulley_tension_table",
        "tension_table_symbol": "sym_closure_table_pulley_tension_table",
        "tension_hanging": "qty_closure_table_pulley_tension_hanging",
        "tension_hanging_symbol": "sym_closure_table_pulley_tension_hanging",
        "accel_table": "qty_closure_table_pulley_accel_table",
        "accel_table_symbol": "sym_closure_table_pulley_accel_table",
        "wrap": "geo_closure_table_pulley_wrap",
        "attach_table": "geo_closure_table_pulley_attach_table",
        "attach_hanging": "geo_closure_table_pulley_attach_hanging",
        "gravity_table": "rel_closure_table_pulley_gravity_table",
        "gravity_hanging": "rel_closure_table_pulley_gravity_hanging",
        "contact": "rel_closure_table_pulley_contact",
        "rope_interaction": "rel_closure_table_pulley_rope",
        "rope_state": "state_closure_table_pulley_rope_taut",
        "pulley_state": "state_closure_table_pulley_pulley_fixed",
        "contact_state": "state_closure_table_pulley_contact",
        "surface_state": "state_closure_table_pulley_surface_fixed",
        "friction_state": "state_closure_table_pulley_frictionless",
    }
    if _authored_draft_ids(payload) & set(ids.values()):
        return None

    rope_evidence = tuple(sorted(
        set(assumption_by_kind["massless_rope"]["evidence_refs"])
        | set(assumption_by_kind["inextensible_rope"]["evidence_refs"])
    ))
    pulley_evidence = tuple(sorted(
        set(assumption_by_kind["fixed_pulley"]["evidence_refs"])
        | set(assumption_by_kind["ideal_massless_frictionless_pulley"]["evidence_refs"])
    ))
    gravity_evidence = tuple(gravity_assumption["evidence_refs"])
    contact_evidence = tuple(frictionless[0]["evidence_refs"])
    mass_table_evidence = tuple(mass_table["evidence_refs"])
    mass_hanging_evidence = tuple(mass_hanging["evidence_refs"])
    # The world axes exist because the source stated the support angle is
    # zero; that statement is their evidence.
    support_angle_evidence = tuple(support_angle["evidence_refs"])
    orientation_evidence = tuple(sorted(
        set(support_angle_evidence) | set(rope_evidence) | set(pulley_evidence)
        | set(contact_evidence) | set(gravity_evidence)
    ))
    query_evidence = tuple(sorted(
        set(orientation_evidence) | set(mass_table_evidence) | set(mass_hanging_evidence)
    ))

    def axis_direction(frame_id: str, axis: str, sign: int) -> dict[str, Any]:
        return {"kind": "axis", "frame_id": frame_id, "axis": axis, "sign": sign}

    world_frame = {
        "frame_id": ids["world_frame"], "frame_type": "cartesian_2d",
        "origin": {"kind": "world"},
        "axes": [
            {"axis": "x", "direction": axis_direction(ids["world_frame"], "x", 1)},
            {"axis": "y", "direction": axis_direction(ids["world_frame"], "y", 1)},
        ],
        "evidence_refs": list(orientation_evidence),
    }
    # The stated zero support angle, written down as the typed thing it means:
    # the support's tangent is the world horizontal axis and the support's
    # normal is the world vertical axis.  Nothing else in this transaction may
    # bind a world axis, so if the statement is ever removed the whole world
    # frame goes with it.
    support_frame = {
        "frame_id": ids["support_frame"], "frame_type": "cartesian_2d",
        "origin": {"kind": "entity", "entity_id": surface_id},
        "parent_frame_id": ids["world_frame"],
        "axes": [
            {"axis": "tangent",
             "direction": axis_direction(ids["world_frame"], "x", 1)},
            {"axis": "normal",
             "direction": axis_direction(ids["world_frame"], "y", 1)},
        ],
        "evidence_refs": list(support_angle_evidence),
    }

    generated_quantities: list[dict[str, Any]] = []
    generated_symbols: list[dict[str, Any]] = []

    def add_unknown(key: str, role: str, subject: str, dimension: dict[str, int], *,
                    component: str, sign: int, point: str | None = None,
                    evidence: tuple[str, ...] = ()) -> None:
        qid = ids[key]
        sid = ids[f"{key}_symbol"]
        generated_quantities.append({
            "quantity_id": qid, "symbol_id": sid, "role": role,
            "subject_id": subject, "point_id": point,
            "frame_id": ids["world_frame"],
            "interval_id": interval_id, "event_id": None,
            "component": component, "shape": "scalar",
            "direction": axis_direction(ids["world_frame"], component, sign),
            "dimension": dict(dimension), "provenance": "unknown",
            "evidence_refs": list(evidence),
        })
        generated_symbols.append({
            "symbol_id": sid, "quantity_id": qid,
            "dimension": dict(dimension), "shape": "scalar",
        })

    gravity_quantity = {
        "quantity_id": ids["gravity"], "symbol_id": ids["gravity_symbol"],
        "role": "gravity", "subject_id": system_id,
        "point_id": None, "frame_id": None, "interval_id": interval_id,
        "event_id": None, "component": "magnitude", "shape": "scalar",
        "dimension": dict(_ACCELERATION_DIMENSION),
        "provenance": "server_default",
        "raw_value": gravity_authorization.raw_value,
        "raw_unit": gravity_authorization.raw_unit,
        "assumption_policy_ref": gravity_authorization.assumption_id,
        "evidence_refs": list(gravity_evidence),
    }
    generated_quantities.append(gravity_quantity)
    generated_symbols.append({
        "symbol_id": ids["gravity_symbol"], "quantity_id": ids["gravity"],
        "dimension": dict(_ACCELERATION_DIMENSION), "shape": "scalar",
    })
    add_unknown("weight_table", "force", table_body_id, _FORCE_DIMENSION,
                component="y", sign=-1,
                evidence=tuple(sorted(set(gravity_evidence) | set(mass_table_evidence))))
    add_unknown("weight_hanging", "force", hanging_body_id, _FORCE_DIMENSION,
                component="y", sign=-1,
                evidence=tuple(sorted(set(gravity_evidence) | set(mass_hanging_evidence))))
    add_unknown("normal", "force", table_body_id, _FORCE_DIMENSION,
                component="y", sign=1, point=ids["point"],
                evidence=contact_evidence)
    add_unknown("accel_normal", "acceleration", table_body_id, _ACCELERATION_DIMENSION,
                component="y", sign=1, evidence=contact_evidence)
    add_unknown("tension_table", "force", table_body_id, _FORCE_DIMENSION,
                component="x", sign=1, evidence=rope_evidence)
    add_unknown("tension_hanging", "force", hanging_body_id, _FORCE_DIMENSION,
                component="y", sign=1, evidence=rope_evidence)
    add_unknown("accel_table", "acceleration", table_body_id, _ACCELERATION_DIMENSION,
                component="x", sign=1, evidence=query_evidence)

    rebound_query_quantity = dict(query_quantity)
    rebound_query_quantity.update({
        "subject_id": hanging_body_id,
        "frame_id": ids["world_frame"],
        "interval_id": interval_id,
        "event_id": None,
        "component": "y",
        "direction": axis_direction(ids["world_frame"], "y", -1),
        "evidence_refs": list(query_evidence),
    })
    quantities = []
    unscoped_source_ids = {
        mass_table["quantity_id"],
        mass_hanging["quantity_id"],
        support_angle["quantity_id"],
    }
    for item in payload["quantities"]:
        if item["quantity_id"] == query_quantity["quantity_id"]:
            quantities.append(rebound_query_quantity)
        elif item["quantity_id"] in unscoped_source_ids:
            entry = dict(item)
            entry["interval_id"] = None
            entry["event_id"] = None
            quantities.append(entry)
        else:
            quantities.append(item)
    quantities.extend(generated_quantities)

    entities = []
    evidence_by_entity = {
        system_id: query_evidence,
        table_body_id: tuple(sorted(set(mass_table_evidence) | set(contact_evidence))),
        hanging_body_id: tuple(sorted(set(mass_hanging_evidence) | set(rope_evidence))),
        surface_id: tuple(sorted(set(contact_evidence) | set(orientation_evidence))),
        pulley_id: pulley_evidence,
        rope_id: rope_evidence,
    }
    for item in payload["entities"]:
        entry = dict(item)
        entry["evidence_refs"] = list(
            evidence_by_entity.get(item["entity_id"], tuple(item.get("evidence_refs", ())))
        )
        entities.append(entry)
    entities.append({
        "entity_id": ids["world"], "primitive": "environment",
        "evidence_refs": list(tuple(sorted(set(gravity_evidence) | set(orientation_evidence)))),
    })

    updated_interval = dict(interval)
    updated_interval.update({
        "subject_ids": sorted({item["entity_id"] for item in entities}),
        "frame_id": ids["world_frame"],
        "start_event_id": None, "end_event_id": None,
        "evidence_refs": list(query_evidence),
    })
    events = payload["events"]
    if (
        len(events) != 2
        or {item["event_id"] for item in events}
        != {interval.get("start_event_id"), interval.get("end_event_id")}
        or any(item.get("evidence_refs") or item.get("time_quantity_id") for item in events)
        or any(item.get("event_id") is not None for item in payload["quantities"])
    ):
        return None

    geometry = [
        {"relation_id": ids["orientation"], "kind": "angle",
         "participant_ids": [surface_id, ids["world"]], "expression": None,
         "quantity_ids": [support_angle["quantity_id"]],
         "interval_id": interval_id,
         "evidence_refs": list(support_angle_evidence)},
        {"relation_id": ids["wrap"], "kind": "wraps",
         "participant_ids": [rope_id, pulley_id], "expression": None,
         "quantity_ids": [], "interval_id": interval_id,
         "evidence_refs": list(pulley_evidence)},
        {"relation_id": ids["attach_table"], "kind": "attached",
         "participant_ids": [rope_id, table_body_id], "expression": None,
         "quantity_ids": [], "interval_id": interval_id,
         "evidence_refs": list(rope_evidence)},
        {"relation_id": ids["attach_hanging"], "kind": "attached",
         "participant_ids": [rope_id, hanging_body_id], "expression": None,
         "quantity_ids": [], "interval_id": interval_id,
         "evidence_refs": list(rope_evidence)},
    ]
    interactions = [
        {"interaction_id": ids["gravity_table"], "kind": "gravity",
         "participant_ids": [table_body_id, ids["world"]], "point_ids": [],
         "frame_id": ids["world_frame"], "interval_id": interval_id, "event_id": None,
         "quantity_ids": [mass_table["quantity_id"], ids["gravity"], ids["weight_table"]],
         "evidence_refs": list(tuple(sorted(
             set(mass_table_evidence) | set(gravity_evidence) | set(orientation_evidence)
         )))},
        {"interaction_id": ids["gravity_hanging"], "kind": "gravity",
         "participant_ids": [hanging_body_id, ids["world"]], "point_ids": [],
         "frame_id": ids["world_frame"], "interval_id": interval_id, "event_id": None,
         "quantity_ids": [mass_hanging["quantity_id"], ids["gravity"], ids["weight_hanging"]],
         "evidence_refs": list(tuple(sorted(
             set(mass_hanging_evidence) | set(gravity_evidence) | set(orientation_evidence)
         )))},
        {"interaction_id": ids["contact"], "kind": "contact",
         "participant_ids": [table_body_id, surface_id], "point_ids": [ids["point"]],
         "frame_id": ids["world_frame"], "interval_id": interval_id, "event_id": None,
         "quantity_ids": [ids["normal"], ids["accel_normal"]],
         "evidence_refs": list(contact_evidence)},
        {"interaction_id": ids["rope_interaction"], "kind": "rope_tension",
         "participant_ids": [table_body_id, hanging_body_id, rope_id, pulley_id],
         "point_ids": [], "frame_id": ids["world_frame"], "interval_id": interval_id,
         "event_id": None,
         "quantity_ids": [ids["tension_table"], ids["tension_hanging"]],
         "evidence_refs": list(tuple(sorted(
             set(rope_evidence) | set(pulley_evidence) | set(orientation_evidence)
         )))},
    ]
    states = [
        {"state_condition_id": ids["rope_state"], "kind": "rope", "state": "taut",
         "subject_id": rope_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(rope_evidence)},
        {"state_condition_id": ids["pulley_state"], "kind": "motion", "state": "at_rest",
         "subject_id": pulley_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(pulley_evidence)},
        {"state_condition_id": ids["contact_state"], "kind": "contact", "state": "touching",
         "subject_id": table_body_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [ids["normal"], ids["accel_normal"]],
         "evidence_refs": list(contact_evidence)},
        {"state_condition_id": ids["surface_state"], "kind": "motion", "state": "at_rest",
         "subject_id": surface_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(contact_evidence)},
        {"state_condition_id": ids["friction_state"], "kind": "friction", "state": "inactive",
         "subject_id": table_body_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(contact_evidence)},
    ]
    queries = [dict(item) for item in payload["queries"]]
    query_target = dict(queries[0]["target"])
    query_target.update({
        "subject_id": hanging_body_id, "frame_id": ids["world_frame"],
        "interval_id": interval_id, "event_id": None, "component": "y",
        "direction": axis_direction(ids["world_frame"], "y", -1),
        "target_quantity_id": query_quantity["quantity_id"],
    })
    queries[0]["target"] = query_target
    queries[0]["evidence_refs"] = list(query_evidence)

    closed = dict(payload)
    closed.update({
        "entities": entities,
        "points": [{"point_id": ids["point"], "role": "contact",
                    "owner_entity_id": table_body_id,
                    "frame_id": ids["world_frame"],
                    "evidence_refs": list(contact_evidence)}],
        "reference_frames": [world_frame, support_frame],
        "motion_intervals": [updated_interval],
        "events": [],
        "symbols": [*payload["symbols"], *generated_symbols],
        "quantities": quantities,
        "geometry": geometry,
        "interactions": interactions,
        "state_conditions": states,
        "queries": queries,
        # The aggregate source assumptions have been consumed to create exact
        # rope/pulley scope.  Retain the authorized gravity policy because the
        # server-default quantity references it; retain only the four derived
        # structural assumptions for the law graph.
        "assumptions": [
            gravity_assumption,
            *(assumption_by_kind[kind] for kind in (
                "massless_rope",
                "inextensible_rope",
                "fixed_pulley",
                "ideal_massless_frictionless_pulley",
            )),
        ],
    })
    return closed, tuple(sorted(ids.values())), (query_quantity["quantity_id"],)


def _incline_kinetic_sliding_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact gravity-driven kinetic slide on one incline.

    The source supplies the body, the incline, the support relation, the
    angle, the coefficient, and the gravity authority; the projection's own
    closed policy has already authorised the down-slope reading of the
    declared slide.  This adapter derives only the two frames, the contact
    record with its regime states, and the value-free tangential unknown the
    sliding-regime law reads.  No force, mass value, acceleration value,
    equation, or answer is written here.
    """

    if (
        len(payload["queries"]) != 1
        or len(payload["motion_intervals"]) != 1
        or payload["reference_frames"]
        or payload["points"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
    ):
        return None
    query = payload["queries"][0]
    target = query["target"]
    interval = payload["motion_intervals"][0]
    interval_id = interval["interval_id"]
    if (
        target.get("role") != "acceleration"
        or target.get("component") != "tangential"
        or target.get("frame_id") is not None
        or target.get("point_id") is not None
        or target.get("event_id") is not None
        or target.get("direction") is not None
        or target.get("interval_id") != interval_id
        or query.get("shape") != "scalar"
    ):
        return None

    primitive_by_id = {
        item["entity_id"]: item["primitive"] for item in payload["entities"]
    }
    body_id = target.get("subject_id")
    if primitive_by_id.get(body_id) not in {
        "particle", "rigid_body", "body_component"
    }:
        return None
    incline_ids = tuple(
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "incline"
    )
    if len(payload["entities"]) != 2 or len(incline_ids) != 1:
        return None
    incline_id = incline_ids[0]

    query_quantity = next(
        (
            item
            for item in payload["quantities"]
            if item["quantity_id"] == target.get("target_quantity_id")
        ),
        None,
    )
    if (
        query_quantity is None
        or query_quantity["role"] != "acceleration"
        or query_quantity["subject_id"] != body_id
        or query_quantity.get("raw_value") is not None
        or query_quantity.get("raw_unit") is not None
        or query_quantity.get("evidence_refs")
    ):
        return None

    angle_records = tuple(
        item for item in payload["quantities"]
        if item["role"] == "angle" and item["subject_id"] == incline_id
    )
    coefficient_records = tuple(
        item for item in payload["quantities"]
        if item["role"] == "coefficient_friction"
        and item["subject_id"] == body_id
    )
    mass_records = tuple(
        item for item in payload["quantities"]
        if item["role"] == "mass" and item["subject_id"] == body_id
    )
    # The source's own statement of which way the slide is going.  Kinetic
    # friction opposes the motion that exists, so without this the tangential
    # equation has no determined sign and the closure must refuse.
    motion_records = tuple(
        item for item in payload["quantities"]
        if item["role"] == "velocity"
        and item["subject_id"] == body_id
        and item.get("direction", {}).get("kind") == "semantic"
        and item["direction"].get("direction") in _INCLINE_SLIDE_TANGENT_SIGNS
    )
    if (
        len(angle_records) != 1
        or not angle_records[0].get("evidence_refs")
        or len(coefficient_records) != 1
        or not coefficient_records[0].get("evidence_refs")
        or len(mass_records) > 1
        or any(not item.get("evidence_refs") for item in mass_records)
        or len(motion_records) != 1
        or not motion_records[0].get("evidence_refs")
        or any(
            item["role"] == "velocity"
            and item["quantity_id"] != motion_records[0]["quantity_id"]
            for item in payload["quantities"]
        )
        or len(payload["quantities"])
        != 2 + len(mass_records) + 1 + 1
    ):
        return None
    angle_quantity = angle_records[0]
    coefficient_quantity = coefficient_records[0]
    motion_quantity = motion_records[0]
    motion_sign = _INCLINE_SLIDE_TANGENT_SIGNS[
        motion_quantity["direction"]["direction"]
    ]
    try:
        motion_speed = normalize_quantity(
            motion_quantity["raw_value"],
            motion_quantity["raw_unit"],
            "scalar",
            DimensionVector(length=1, time=-1),
        ).value
    except Exception:
        return None
    if type(motion_speed) is not float or motion_speed <= 0.0:
        return None
    try:
        angle_value = normalize_quantity(
            angle_quantity["raw_value"],
            angle_quantity["raw_unit"],
            "scalar",
            DimensionVector.dimensionless(),
        ).value
    except Exception:
        return None
    if type(angle_value) is not float or not 0.0 <= angle_value < 1.5707963267948966:
        return None
    try:
        coefficient_value = normalize_quantity(
            coefficient_quantity["raw_value"],
            coefficient_quantity["raw_unit"],
            "scalar",
            DimensionVector.dimensionless(),
        ).value
    except Exception:
        return None
    if type(coefficient_value) is not float or coefficient_value < 0.0:
        return None
    if mass_records:
        value = _fixed_pulley_mass_value(mass_records[0])
        if value is None or value <= 0.0:
            return None

    supports = tuple(
        item for item in payload["geometry"] if item["kind"] == "lies_on"
    )
    if (
        len(payload["geometry"]) != 1
        or len(supports) != 1
        or supports[0].get("interval_id") != interval_id
        or set(supports[0]["participant_ids"]) != {body_id, incline_id}
        or len(supports[0]["participant_ids"]) != 2
    ):
        return None
    support = supports[0]

    gravity_assumptions = tuple(
        item for item in payload["assumptions"]
        if item["kind"] == "constant_gravity"
        and item["disposition"] == "approved"
        and item["assumption_id"] in authority.approved_assumption_ids
        and item["interval_id"] in {None, interval_id}
        and item["subject_id"] == body_id
        and item.get("evidence_refs")
    )
    motion_authorities = tuple(
        item for item in payload["assumptions"]
        if item["kind"] == "typed_incline_slide_motion"
        and item["assumption_id"] == "asm_closure_incline_slide_motion"
        and item["disposition"] == "approved"
        and item["assumption_id"] in authority.approved_assumption_ids
        and item["interval_id"] == interval_id
        and item["subject_id"] == body_id
        and item.get("evidence_refs")
    )
    if (
        len(gravity_assumptions) != 1
        or len(motion_authorities) != 1
        or len(payload["assumptions"]) != 2
    ):
        return None
    gravity_assumption = gravity_assumptions[0]
    motion_authority = motion_authorities[0]
    gravity_authorization = authority.authorized_assumptions.get(
        gravity_assumption["assumption_id"]
    )
    if (
        type(gravity_authorization) is not AssumptionAuthorization
        or gravity_authorization.assumption_id != gravity_assumption["assumption_id"]
        or gravity_authorization.subject_id != body_id
        or gravity_authorization.interval_id != gravity_assumption["interval_id"]
        or str(getattr(gravity_authorization.role, "value", gravity_authorization.role)) != "gravity"
        or gravity_assumption.get("proposed_value") != gravity_authorization.raw_value
        or gravity_assumption.get("proposed_unit") != gravity_authorization.raw_unit
    ):
        return None

    ids = {
        "world": INCLINE_SLIDING_WORLD_ID,
        "world_frame": INCLINE_SLIDING_WORLD_FRAME_ID,
        "slope_frame": INCLINE_SLIDING_SLOPE_FRAME_ID,
        "point": INCLINE_SLIDING_CONTACT_POINT_ID,
        "gravity": INCLINE_SLIDING_GRAVITY_ID,
        "gravity_symbol": INCLINE_SLIDING_GRAVITY_SYMBOL_ID,
        "angle_relation": "geo_closure_incline_sliding_angle",
        "contact": "rel_closure_incline_sliding_contact",
        "contact_state": "state_closure_incline_sliding_contact",
        "friction_state": "state_closure_incline_sliding_friction",
        "motion_state": "state_closure_incline_sliding_motion",
        "incline_state": "state_closure_incline_sliding_incline_fixed",
    }
    if _authored_draft_ids(payload) & set(ids.values()):
        return None

    gravity_evidence = tuple(gravity_assumption["evidence_refs"])
    motion_authority_evidence = tuple(motion_authority["evidence_refs"])
    motion_evidence = tuple(motion_quantity["evidence_refs"])
    angle_evidence = tuple(angle_quantity["evidence_refs"])
    coefficient_evidence = tuple(coefficient_quantity["evidence_refs"])
    # The source states the support as a relation without its own quote; the
    # slide-motion authority's evidence is the typed reading of that support.
    support_evidence = motion_authority_evidence
    orientation_evidence = tuple(sorted(
        set(gravity_evidence) | set(angle_evidence) | set(support_evidence)
    ))
    query_evidence = tuple(sorted(
        set(orientation_evidence)
        | set(coefficient_evidence)
        | set(motion_authority_evidence)
    ))

    def axis_direction(frame_id: str, axis: str, sign: int) -> dict[str, Any]:
        return {"kind": "axis", "frame_id": frame_id, "axis": axis, "sign": sign}

    world_frame = {
        "frame_id": ids["world_frame"], "frame_type": "cartesian_2d",
        "origin": {"kind": "world"},
        "axes": [
            {"axis": "x", "direction": axis_direction(ids["world_frame"], "x", 1)},
            {"axis": "y", "direction": axis_direction(ids["world_frame"], "y", 1)},
        ],
        "evidence_refs": list(orientation_evidence),
    }
    slope_frame = {
        "frame_id": ids["slope_frame"], "frame_type": "tangential_normal",
        "origin": {"kind": "entity", "entity_id": incline_id},
        "axes": [
            {"axis": "tangent", "direction": axis_direction(ids["slope_frame"], "tangent", 1)},
            {"axis": "normal", "direction": axis_direction(ids["slope_frame"], "normal", 1)},
        ],
        "parent_frame_id": ids["world_frame"],
        "evidence_refs": list(orientation_evidence),
    }

    gravity_quantity = {
        "quantity_id": ids["gravity"], "symbol_id": ids["gravity_symbol"],
        "role": "gravity", "subject_id": body_id,
        "point_id": None, "frame_id": None,
        "interval_id": gravity_assumption["interval_id"],
        "event_id": None, "component": "magnitude", "shape": "scalar",
        "dimension": dict(_ACCELERATION_DIMENSION),
        "provenance": "server_default",
        "raw_value": gravity_authorization.raw_value,
        "raw_unit": gravity_authorization.raw_unit,
        "assumption_policy_ref": gravity_authorization.assumption_id,
        "evidence_refs": list(gravity_evidence),
    }

    rebound_query_quantity = dict(query_quantity)
    rebound_query_quantity.update({
        "frame_id": ids["slope_frame"],
        "interval_id": interval_id,
        "event_id": None,
        "component": "tangential",
        "direction": axis_direction(ids["slope_frame"], "tangent", 1),
        "evidence_refs": list(query_evidence),
    })
    # The source's velocity keeps its own value and evidence; the closure only
    # writes down, in typed form, the slope axis the source's own direction
    # already named.  No speed, sign, or direction is invented here.
    rebound_motion_quantity = dict(motion_quantity)
    rebound_motion_quantity.update({
        "frame_id": ids["slope_frame"],
        "interval_id": interval_id,
        "event_id": None,
        "component": "tangential",
        "direction": axis_direction(ids["slope_frame"], "tangent", motion_sign),
    })
    quantities = []
    unscoped_source_ids = {
        angle_quantity["quantity_id"],
        coefficient_quantity["quantity_id"],
        *(item["quantity_id"] for item in mass_records),
    }
    for item in payload["quantities"]:
        if item["quantity_id"] == query_quantity["quantity_id"]:
            quantities.append(rebound_query_quantity)
        elif item["quantity_id"] == motion_quantity["quantity_id"]:
            quantities.append(rebound_motion_quantity)
        elif item["quantity_id"] in unscoped_source_ids:
            entry = dict(item)
            entry["interval_id"] = None
            entry["event_id"] = None
            quantities.append(entry)
        else:
            quantities.append(item)
    quantities.append(gravity_quantity)
    symbols = [
        *payload["symbols"],
        {
            "symbol_id": ids["gravity_symbol"], "quantity_id": ids["gravity"],
            "dimension": dict(_ACCELERATION_DIMENSION), "shape": "scalar",
        },
    ]

    entities = []
    evidence_by_entity = {
        body_id: query_evidence,
        incline_id: tuple(sorted(set(angle_evidence) | set(support_evidence))),
    }
    for item in payload["entities"]:
        entry = dict(item)
        entry["evidence_refs"] = list(
            evidence_by_entity.get(item["entity_id"], tuple(item.get("evidence_refs", ())))
        )
        entities.append(entry)
    entities.append({
        "entity_id": ids["world"], "primitive": "environment",
        "evidence_refs": list(tuple(sorted(set(gravity_evidence) | set(orientation_evidence)))),
    })

    updated_interval = dict(interval)
    updated_interval.update({
        "subject_ids": sorted({item["entity_id"] for item in entities}),
        "frame_id": None,
        "start_event_id": None, "end_event_id": None,
        "evidence_refs": list(query_evidence),
    })
    events = payload["events"]
    if (
        len(events) != 2
        or {item["event_id"] for item in events}
        != {interval.get("start_event_id"), interval.get("end_event_id")}
        or any(item.get("evidence_refs") or item.get("time_quantity_id") for item in events)
        or any(item.get("event_id") is not None for item in payload["quantities"])
    ):
        return None

    closed_support = dict(support)
    closed_support["evidence_refs"] = list(support_evidence)
    geometry = [
        closed_support,
        {"relation_id": ids["angle_relation"], "kind": "angle",
         "participant_ids": [incline_id, ids["world"]],
         "expression": None, "quantity_ids": [angle_quantity["quantity_id"]],
         "interval_id": None, "evidence_refs": list(angle_evidence)},
    ]
    interactions = [
        {"interaction_id": ids["contact"], "kind": "contact",
         "participant_ids": [body_id, incline_id], "point_ids": [ids["point"]],
         "frame_id": ids["slope_frame"], "interval_id": interval_id, "event_id": None,
         "quantity_ids": [coefficient_quantity["quantity_id"]],
         "evidence_refs": list(tuple(sorted(
             set(support_evidence) | set(coefficient_evidence)
         )))},
    ]
    states = [
        {"state_condition_id": ids["contact_state"], "kind": "contact", "state": "touching",
         "subject_id": body_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(support_evidence)},
        {"state_condition_id": ids["friction_state"], "kind": "friction", "state": "sliding",
         "subject_id": body_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [coefficient_quantity["quantity_id"]],
         "evidence_refs": list(tuple(sorted(
             set(coefficient_evidence) | set(motion_authority_evidence)
         )))},
        {"state_condition_id": ids["motion_state"], "kind": "motion", "state": "moving",
         "subject_id": body_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [motion_quantity["quantity_id"]],
         "evidence_refs": list(motion_evidence)},
        {"state_condition_id": ids["incline_state"], "kind": "motion", "state": "at_rest",
         "subject_id": incline_id, "interval_id": interval_id, "event_id": None,
         "quantity_ids": [], "evidence_refs": list(support_evidence)},
    ]
    queries = [dict(item) for item in payload["queries"]]
    query_target = dict(queries[0]["target"])
    query_target.update({
        "frame_id": ids["slope_frame"],
        "interval_id": interval_id, "event_id": None,
        "component": "tangential",
        "direction": axis_direction(ids["slope_frame"], "tangent", 1),
        "target_quantity_id": query_quantity["quantity_id"],
    })
    queries[0]["target"] = query_target
    queries[0]["evidence_refs"] = list(query_evidence)

    closed = dict(payload)
    closed.update({
        "entities": entities,
        "points": [{"point_id": ids["point"], "role": "contact",
                    "owner_entity_id": body_id,
                    "frame_id": ids["slope_frame"],
                    "evidence_refs": list(support_evidence)}],
        "reference_frames": [world_frame, slope_frame],
        "motion_intervals": [updated_interval],
        "events": [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": geometry,
        "interactions": interactions,
        "state_conditions": states,
        "queries": queries,
        "assumptions": [gravity_assumption, motion_authority],
    })
    return closed, tuple(sorted(ids.values())), (query_quantity["quantity_id"],)


# Only a profile whose partial-attachment hazards already have engine-level
# negative controls, or which creates no force at all, may appear here.
# Everything else plans, is measured by the census, and is not built.
def _rigid_fixed_axis_point_speed_transaction(
    payload: dict[str, Any], _authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact source-typed fixed-axis point-speed readout.

    The transaction creates no value, equation, force, assumption, solver
    choice, candidate, or answer.  It materialises the typed material-point
    record the source's point-on-body relation already states, rebinds the
    source radius and the value-free query unknown onto the rotating body's
    scope, and normalises the scalar velocity-magnitude query into the
    equivalent speed magnitude read by the existing ``fixed_axis_speed`` law.
    """

    reserved_ids = {RIGID_AXIS_POINT_ID}
    if (
        len(payload["entities"]) != 2
        or len(payload["motion_intervals"]) != 1
        or len(payload["queries"]) != 1
        or len(payload["events"]) != 2
        or len(payload["geometry"]) != 2
        or payload["reference_frames"]
        or payload["points"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
        or payload["principle_hints"]
        or payload["ambiguities"]
        or payload["unsupported_features"]
        or payload["figure_dependency"] != {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        }
        or reserved_ids & _authored_draft_ids(payload)
    ):
        return None

    bodies = [
        item for item in payload["entities"]
        if item.get("primitive") == "rigid_body"
    ]
    point_entities = [
        item for item in payload["entities"] if item.get("primitive") == "point"
    ]
    if len(bodies) != 1 or len(point_entities) != 1:
        return None
    body_id = bodies[0].get("entity_id")
    point_entity = point_entities[0]
    point_entity_id = point_entity.get("entity_id")
    subject_ids = {body_id, point_entity_id}

    interval = payload["motion_intervals"][0]
    interval_id = interval.get("interval_id")
    if (
        set(interval.get("subject_ids", ())) != subject_ids
        or len(interval.get("subject_ids", ())) != 2
        or interval.get("frame_id") is not None
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or interval.get("start_event_id") == interval.get("end_event_id")
    ):
        return None

    source_evidence_ids = {
        item.get("evidence_id") for item in payload["source_evidence"]
    }

    def evidenced(item: dict[str, Any]) -> bool:
        refs = set(item.get("evidence_refs", ()))
        return bool(refs) and refs.issubset(source_evidence_ids)

    if any(
        item.get("subject_id") not in subject_ids
        or item.get("interval_id") not in {None, interval_id}
        or item.get("proposed_role") is not None
        or item.get("proposed_value") is not None
        or item.get("proposed_unit") is not None
        or not evidenced(item)
        for item in payload["assumptions"]
    ):
        return None

    events = {item.get("event_id"): item for item in payload["events"]}
    start = events.get(interval.get("start_event_id"))
    finish = events.get(interval.get("end_event_id"))
    if (
        len(events) != 2
        or start is None
        or finish is None
        or start.get("kind") != "start"
        or finish.get("kind") != "finish"
        or any(
            set(item.get("subject_ids", ())) != subject_ids
            or item.get("time_quantity_id") is not None
            or item.get("interval_ids") != [interval_id]
            or item.get("occurs_in_interval_ids")
            for item in payload["events"]
        )
    ):
        return None

    lies_on = [
        item for item in payload["geometry"] if item.get("kind") == "lies_on"
    ]
    coincident = [
        item for item in payload["geometry"] if item.get("kind") == "coincident"
    ]
    if (
        len(lies_on) != 1
        or len(coincident) != 1
        or any(
            set(item.get("participant_ids", ())) != subject_ids
            or len(item.get("participant_ids", ())) != 2
            or item.get("interval_id") not in {None, interval_id}
            or item.get("quantity_ids")
            or item.get("expression") is not None
            for item in payload["geometry"]
        )
    ):
        return None

    query = payload["queries"][0]
    target = dict(query.get("target") or {})
    target_quantity_id = target.get("target_quantity_id")
    quantities = {
        item.get("quantity_id"): item for item in payload["quantities"]
    }
    target_quantity = quantities.get(target_quantity_id)
    if (
        len(quantities) != len(payload["quantities"])
        or target_quantity is None
        or query.get("shape") != "scalar"
        or (target.get("role"), target.get("component"))
        not in {("velocity", "magnitude"), ("speed", "magnitude")}
        or target.get("subject_id") != point_entity_id
        or target.get("point_id") is not None
        or target.get("frame_id") is not None
        or target.get("interval_id") != interval_id
        or target.get("event_id") is not None
        or target.get("direction") is not None
        or target_quantity.get("subject_id") != point_entity_id
        or target_quantity.get("point_id") is not None
        or target_quantity.get("frame_id") is not None
        or target_quantity.get("interval_id") != interval_id
        or target_quantity.get("event_id") is not None
        or target_quantity.get("role") != target.get("role")
        or target_quantity.get("component") != target.get("component")
        or target_quantity.get("direction") is not None
        or target_quantity.get("shape") != "scalar"
        or target_quantity.get("raw_value") is not None
        or target_quantity.get("raw_unit") is not None
        or target_quantity.get("provenance") != "unknown"
        or target_quantity.get("symbol_id") is None
        or target_quantity.get("evidence_refs")
        or query.get("output_dimension") != target_quantity.get("dimension")
        or query.get("evidence_refs")
    ):
        return None

    symbol_counts: Counter[str | None] = Counter(
        item.get("quantity_id") for item in payload["symbols"]
    )
    if len(payload["symbols"]) != len(payload["quantities"]) or any(
        item.get("symbol_id") is None
        or symbol_counts[item.get("quantity_id")] != 1
        for item in payload["quantities"]
    ):
        return None

    known = [
        item
        for item in payload["quantities"]
        if item.get("quantity_id") != target_quantity_id
    ]

    def scoped(item: dict[str, Any]) -> bool:
        return (
            item.get("point_id") is None
            and item.get("frame_id") is None
            and item.get("interval_id") in {None, interval_id}
            and item.get("event_id") is None
            and item.get("shape") == "scalar"
        )

    def valued_source(item: dict[str, Any]) -> bool:
        return (
            item.get("raw_value") is not None
            and item.get("raw_unit") is not None
            and item.get("provenance") == "explicit_source"
            and item.get("symbol_id") is not None
            and evidenced(item)
        )

    angular = [item for item in known if item.get("role") == "angular_velocity"]
    radii = [item for item in known if item.get("role") == "radius"]
    masses = [item for item in known if item.get("role") == "mass"]
    if len(angular) != 1 or len(radii) != 1 or len(masses) > 1:
        return None
    omega = angular[0]
    omega_direction = (omega.get("direction") or {}).get("direction")
    if (
        omega.get("subject_id") != body_id
        or not scoped(omega)
        or omega.get("interval_id") != interval_id
        or not valued_source(omega)
        or not (
            (
                omega_direction is None
                and omega.get("component") in {"unspecified", "magnitude"}
            )
            or (
                omega_direction in {"clockwise", "counterclockwise"}
                and omega.get("component") == omega_direction
            )
        )
    ):
        return None
    radius = radii[0]
    if (
        radius.get("subject_id") != point_entity_id
        or not scoped(radius)
        or radius.get("component") != "unspecified"
        or radius.get("direction") is not None
        or not valued_source(radius)
    ):
        return None
    if any(
        item.get("subject_id") != body_id
        or not scoped(item)
        or not valued_source(item)
        for item in masses
    ):
        return None
    accounted = {
        omega.get("quantity_id"),
        radius.get("quantity_id"),
        target_quantity_id,
        *(item.get("quantity_id") for item in masses),
    }
    if len(accounted) != len(payload["quantities"]):
        return None

    point_evidence = sorted(
        set(point_entity.get("evidence_refs", ()))
        | set(radius.get("evidence_refs", ()))
    )
    if not point_evidence or len(point_evidence) > 16:
        return None
    material_point = {
        "point_id": RIGID_AXIS_POINT_ID,
        "role": "material",
        "owner_entity_id": body_id,
        "frame_id": None,
        "label": None,
        "evidence_refs": point_evidence,
    }

    rewritten_quantities: list[dict[str, Any]] = []
    rebound: list[str] = []
    for original in payload["quantities"]:
        item = dict(original)
        if item.get("quantity_id") == radius.get("quantity_id"):
            item.update(
                subject_id=body_id,
                point_id=RIGID_AXIS_POINT_ID,
            )
            rebound.append(item["quantity_id"])
        elif item.get("quantity_id") == target_quantity_id:
            item.update(
                role="speed",
                subject_id=body_id,
                point_id=RIGID_AXIS_POINT_ID,
            )
            rebound.append(item["quantity_id"])
        rewritten_quantities.append(item)

    rewritten_query = dict(query)
    rewritten_target = dict(target)
    rewritten_target.update(
        role="speed",
        subject_id=body_id,
        point_id=RIGID_AXIS_POINT_ID,
        target_quantity_id=target_quantity_id,
    )
    rewritten_query.update(target=rewritten_target)

    closed = dict(payload)
    closed["points"] = [material_point]
    closed["quantities"] = rewritten_quantities
    closed["queries"] = [rewritten_query]
    return closed, (RIGID_AXIS_POINT_ID,), tuple(sorted(rebound))


_ANGULAR_SPEED_DIMENSION: dict[str, int] = {"time": -1}


def _rigid_two_point_speed_transfer_transaction(
    payload: dict[str, Any], _authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact source-typed two-point speed-transfer readout.

    The transaction creates no value, equation, force, assumption, solver
    choice, candidate, or answer.  It materialises the two typed material
    points the source's point-on-body relations already state, rebinds both
    source radii and both scalar speed magnitudes onto the rotating body's
    scope, normalises the scalar velocity magnitudes into the equivalent
    speed magnitudes, and adds the single value-free shared angular-speed
    unknown through which the existing ``fixed_axis_speed`` law couples the
    two points at the source-declared instant.

    The coupling is licensed only by the source's own fixed rotation
    centre: exactly one ``coincident`` rotation relation must bind the body
    to a third, otherwise-inert centre point.  That single typed centre is
    what makes both radii the same rotation's radii; without it — or with
    two candidate centres, or a centre that acts, carries a quantity, or is
    bound as an on-body point — the transaction refuses and closes nothing.
    """

    reserved_ids = {
        TWO_POINT_SPEED_KNOWN_POINT_ID,
        TWO_POINT_SPEED_QUERY_POINT_ID,
        TWO_POINT_SPEED_OMEGA_QUANTITY_ID,
        TWO_POINT_SPEED_OMEGA_SYMBOL_ID,
    }
    if (
        len(payload["motion_intervals"]) != 1
        or len(payload["queries"]) != 1
        or len(payload["events"]) != 3
        or len(payload["quantities"]) != 4
        or payload["reference_frames"]
        or payload["points"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
        or payload["principle_hints"]
        or payload["ambiguities"]
        or payload["unsupported_features"]
        or payload["figure_dependency"] != {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        }
        or reserved_ids & _authored_draft_ids(payload)
    ):
        return None

    bodies = [
        item for item in payload["entities"]
        if item.get("primitive") == "rigid_body"
    ]
    point_entities = [
        item for item in payload["entities"] if item.get("primitive") == "point"
    ]
    if (
        len(bodies) != 1
        or len(point_entities) != 3
        or len(payload["entities"]) != 1 + len(point_entities)
    ):
        return None
    body_id = bodies[0].get("entity_id")
    point_ids = {item.get("entity_id") for item in point_entities}

    lies_on = [
        item for item in payload["geometry"] if item.get("kind") == "lies_on"
    ]
    centre_relations = [
        item for item in payload["geometry"] if item.get("kind") == "coincident"
    ]
    interval = payload["motion_intervals"][0]
    interval_id = interval.get("interval_id")
    if (
        len(payload["geometry"]) != 3
        or len(lies_on) != 2
        or len(centre_relations) != 1
        or any(
            len(item.get("participant_ids", ())) != 2
            or body_id not in item.get("participant_ids", ())
            or not (set(item.get("participant_ids", ())) - {body_id})
            <= point_ids
            or item.get("interval_id") not in {None, interval_id}
            or item.get("quantity_ids")
            or item.get("expression") is not None
            for item in (*lies_on, *centre_relations)
        )
    ):
        return None
    bound_ids = sorted(
        {
            participant
            for item in lies_on
            for participant in item.get("participant_ids", ())
            if participant != body_id
        }
    )
    if len(bound_ids) != 2 or len(point_ids - set(bound_ids)) != 1:
        return None
    centre_id = next(iter(point_ids - set(bound_ids)))
    if {
        participant
        for item in centre_relations
        for participant in item.get("participant_ids", ())
        if participant != body_id
    } != {centre_id}:
        return None
    subject_ids = {body_id, *bound_ids}

    if (
        set(interval.get("subject_ids", ())) != subject_ids
        or len(interval.get("subject_ids", ())) != 3
        or interval.get("frame_id") is not None
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or interval.get("start_event_id") == interval.get("end_event_id")
    ):
        return None

    events = {item.get("event_id"): item for item in payload["events"]}
    start = events.get(interval.get("start_event_id"))
    finish = events.get(interval.get("end_event_id"))
    instants = [
        item
        for item in payload["events"]
        if item.get("event_id")
        not in {interval.get("start_event_id"), interval.get("end_event_id")}
    ]
    if (
        len(events) != 3
        or start is None
        or finish is None
        or len(instants) != 1
        or start.get("kind") != "start"
        or finish.get("kind") != "finish"
        or instants[0].get("kind") != "other"
        or any(
            set(item.get("subject_ids", ())) != subject_ids
            or item.get("time_quantity_id") is not None
            for item in payload["events"]
        )
        or start.get("interval_ids") != [interval_id]
        or finish.get("interval_ids") != [interval_id]
        or start.get("occurs_in_interval_ids")
        or finish.get("occurs_in_interval_ids")
        or instants[0].get("interval_ids")
        or instants[0].get("occurs_in_interval_ids") != [interval_id]
    ):
        return None
    instant_id = instants[0].get("event_id")

    source_evidence_ids = {
        item.get("evidence_id") for item in payload["source_evidence"]
    }

    def evidenced(item: dict[str, Any]) -> bool:
        refs = set(item.get("evidence_refs", ()))
        return bool(refs) and refs.issubset(source_evidence_ids)

    if any(
        item.get("subject_id") not in subject_ids
        or item.get("interval_id") not in {None, interval_id}
        or item.get("proposed_role") is not None
        or item.get("proposed_value") is not None
        or item.get("proposed_unit") is not None
        or not evidenced(item)
        for item in payload["assumptions"]
    ):
        return None

    def scoped(item: dict[str, Any]) -> bool:
        return (
            item.get("point_id") is None
            and item.get("frame_id") is None
            and item.get("interval_id") == interval_id
            and item.get("event_id") == instant_id
            and item.get("shape") == "scalar"
        )

    def valued_source(item: dict[str, Any]) -> bool:
        return (
            item.get("raw_value") is not None
            and item.get("raw_unit") is not None
            and item.get("provenance") == "explicit_source"
            and item.get("symbol_id") is not None
            and evidenced(item)
        )

    query = payload["queries"][0]
    target = dict(query.get("target") or {})
    target_quantity_id = target.get("target_quantity_id")
    quantities = {
        item.get("quantity_id"): item for item in payload["quantities"]
    }
    target_quantity = quantities.get(target_quantity_id)
    if (
        len(quantities) != len(payload["quantities"])
        or target_quantity is None
        or query.get("shape") != "scalar"
        or (target.get("role"), target.get("component"))
        not in {("velocity", "magnitude"), ("speed", "magnitude")}
        or target.get("subject_id") not in bound_ids
        or target.get("point_id") is not None
        or target.get("frame_id") is not None
        or target.get("interval_id") != interval_id
        or target.get("event_id") != instant_id
        or target.get("direction") is not None
        or target_quantity.get("subject_id") != target.get("subject_id")
        or not scoped(target_quantity)
        or target_quantity.get("role") != target.get("role")
        or target_quantity.get("component") != target.get("component")
        or target_quantity.get("direction") is not None
        or target_quantity.get("raw_value") is not None
        or target_quantity.get("raw_unit") is not None
        or target_quantity.get("provenance") != "unknown"
        or target_quantity.get("symbol_id") is None
        or target_quantity.get("evidence_refs")
        or query.get("output_dimension") != target_quantity.get("dimension")
        or query.get("evidence_refs")
    ):
        return None
    query_point_entity_id = target.get("subject_id")
    known_point_entity_id = next(
        item for item in bound_ids if item != query_point_entity_id
    )

    symbol_counts: Counter[str | None] = Counter(
        item.get("quantity_id") for item in payload["symbols"]
    )
    if len(payload["symbols"]) != len(payload["quantities"]) or any(
        item.get("symbol_id") is None
        or symbol_counts[item.get("quantity_id")] != 1
        for item in payload["quantities"]
    ):
        return None

    known = [
        item
        for item in payload["quantities"]
        if item.get("quantity_id") != target_quantity_id
    ]
    radii = [item for item in known if item.get("role") == "radius"]
    speeds = [
        item for item in known if item.get("role") in {"velocity", "speed"}
    ]
    if len(radii) != 2 or len(speeds) != 1 or len(known) != 3:
        return None
    radii_by_subject = {item.get("subject_id"): item for item in radii}
    if set(radii_by_subject) != set(bound_ids) or any(
        not scoped(item)
        or item.get("component") != "unspecified"
        or item.get("direction") is not None
        or not valued_source(item)
        for item in radii
    ):
        return None
    known_speed = speeds[0]
    if (
        known_speed.get("subject_id") != known_point_entity_id
        or not scoped(known_speed)
        or known_speed.get("component") not in {"unspecified", "magnitude"}
        or known_speed.get("direction") is not None
        or not valued_source(known_speed)
    ):
        return None

    entities_by_id = {
        item.get("entity_id"): item for item in payload["entities"]
    }
    material_points: list[dict[str, Any]] = []
    point_id_for_entity: dict[str, str] = {
        known_point_entity_id: TWO_POINT_SPEED_KNOWN_POINT_ID,
        query_point_entity_id: TWO_POINT_SPEED_QUERY_POINT_ID,
    }
    for entity_id in (known_point_entity_id, query_point_entity_id):
        point_evidence = sorted(
            set(entities_by_id[entity_id].get("evidence_refs", ()))
            | set(radii_by_subject[entity_id].get("evidence_refs", ()))
        )
        if not point_evidence or len(point_evidence) > 16:
            return None
        material_points.append(
            {
                "point_id": point_id_for_entity[entity_id],
                "role": "material",
                "owner_entity_id": body_id,
                "frame_id": None,
                "label": None,
                "evidence_refs": point_evidence,
            }
        )

    rewritten_quantities: list[dict[str, Any]] = []
    rebound: list[str] = []
    for original in payload["quantities"]:
        item = dict(original)
        subject_id = item.get("subject_id")
        if item.get("quantity_id") in {
            radii_by_subject[known_point_entity_id].get("quantity_id"),
            radii_by_subject[query_point_entity_id].get("quantity_id"),
        }:
            item.update(
                subject_id=body_id,
                point_id=point_id_for_entity[subject_id],
            )
            rebound.append(item["quantity_id"])
        elif item.get("quantity_id") == known_speed.get("quantity_id"):
            item.update(
                role="speed",
                subject_id=body_id,
                point_id=point_id_for_entity[subject_id],
            )
            rebound.append(item["quantity_id"])
        elif item.get("quantity_id") == target_quantity_id:
            item.update(
                role="speed",
                subject_id=body_id,
                point_id=point_id_for_entity[subject_id],
            )
            rebound.append(item["quantity_id"])
        rewritten_quantities.append(item)

    omega_quantity = {
        "quantity_id": TWO_POINT_SPEED_OMEGA_QUANTITY_ID,
        "symbol_id": TWO_POINT_SPEED_OMEGA_SYMBOL_ID,
        "role": "angular_velocity",
        "subject_id": body_id,
        "point_id": None,
        "frame_id": None,
        "interval_id": interval_id,
        "event_id": instant_id,
        "component": "magnitude",
        "shape": "scalar",
        "dimension": dict(_ANGULAR_SPEED_DIMENSION),
        "provenance": "unknown",
        "evidence_refs": [],
    }
    omega_symbol = {
        "symbol_id": TWO_POINT_SPEED_OMEGA_SYMBOL_ID,
        "quantity_id": TWO_POINT_SPEED_OMEGA_QUANTITY_ID,
        "dimension": dict(_ANGULAR_SPEED_DIMENSION),
        "shape": "scalar",
    }

    rewritten_query = dict(query)
    rewritten_target = dict(target)
    rewritten_target.update(
        role="speed",
        subject_id=body_id,
        point_id=TWO_POINT_SPEED_QUERY_POINT_ID,
        target_quantity_id=target_quantity_id,
    )
    rewritten_query.update(target=rewritten_target)

    closed = dict(payload)
    closed["points"] = material_points
    closed["quantities"] = [*rewritten_quantities, omega_quantity]
    closed["symbols"] = [*payload["symbols"], omega_symbol]
    closed["queries"] = [rewritten_query]
    return (
        closed,
        (
            TWO_POINT_SPEED_KNOWN_POINT_ID,
            TWO_POINT_SPEED_QUERY_POINT_ID,
            TWO_POINT_SPEED_OMEGA_QUANTITY_ID,
        ),
        tuple(sorted(rebound)),
    )


def _collision_restitution_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact source-typed 1D restitution-impact readout.

    The transaction creates no value, equation, force, assumption, solver
    choice, candidate, or answer.  It materialises the world frame, rebinds
    each source-stated approach direction onto that frame's signed x axis,
    links the impact's own masses, velocities, and restitution coefficient
    into the collision record the source already states, and — when the
    source asks for only one body's separation velocity — generates the
    partner's value-free separation unknown so the two existing generic
    laws (``system_momentum_conservation`` under the projection's own
    per-body impulse-isolation authority, and ``direct_restitution``) can
    couple the impact.  Both authorities must be spent verbatim; anything
    beyond the exact impact shape refuses and closes nothing.
    """

    reserved_ids = {
        COLLISION_RESTITUTION_FRAME_ID,
        COLLISION_PARTNER_AFTER_QUANTITY_ID,
        COLLISION_PARTNER_AFTER_SYMBOL_ID,
    }
    if (
        len(payload["entities"]) != 2
        or len(payload["motion_intervals"]) != 1
        or len(payload["queries"]) != 1
        or len(payload["events"]) != 2
        or len(payload["interactions"]) != 1
        or len(payload["assumptions"]) != 2
        or payload["reference_frames"]
        or payload["points"]
        or payload["geometry"]
        or payload["constraints"]
        or payload["state_conditions"]
        or payload["principle_hints"]
        or payload["ambiguities"]
        or payload["unsupported_features"]
        or payload["figure_dependency"] != {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        }
        or reserved_ids & _authored_draft_ids(payload)
    ):
        return None

    if any(
        item.get("primitive") not in {"particle", "rigid_body"}
        for item in payload["entities"]
    ):
        return None
    body_ids = {item.get("entity_id") for item in payload["entities"]}

    interval = payload["motion_intervals"][0]
    interval_id = interval.get("interval_id")
    if (
        set(interval.get("subject_ids", ())) != body_ids
        or len(interval.get("subject_ids", ())) != 2
        or interval.get("frame_id") is not None
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or interval.get("start_event_id") == interval.get("end_event_id")
    ):
        return None

    events = {item.get("event_id"): item for item in payload["events"]}
    start = events.get(interval.get("start_event_id"))
    end = events.get(interval.get("end_event_id"))
    if (
        len(events) != 2
        or start is None
        or end is None
        or start.get("kind") != "collision_start"
        or end.get("kind") != "collision_end"
        or any(
            set(item.get("subject_ids", ())) != body_ids
            or item.get("time_quantity_id") is not None
            or item.get("interval_ids") != [interval_id]
            or item.get("occurs_in_interval_ids")
            for item in payload["events"]
        )
    ):
        return None
    start_id = start.get("event_id")
    end_id = end.get("event_id")

    impact = payload["interactions"][0]
    if (
        impact.get("kind") != "collision"
        or set(impact.get("participant_ids", ())) != body_ids
        or len(impact.get("participant_ids", ())) != 2
        or impact.get("point_ids")
        or impact.get("frame_id") is not None
        or impact.get("interval_id") != interval_id
        or impact.get("event_id") is not None
        or impact.get("quantity_ids")
    ):
        return None

    source_evidence_ids = {
        item.get("evidence_id") for item in payload["source_evidence"]
    }

    def evidenced(item: dict[str, Any]) -> bool:
        refs = set(item.get("evidence_refs", ()))
        return bool(refs) and refs.issubset(source_evidence_ids)

    authority_subjects = set()
    for assumption in payload["assumptions"]:
        if (
            assumption.get("kind") != "external_impulse_negligible"
            or assumption.get("disposition") != "approved"
            or assumption.get("assumption_id")
            not in authority.approved_assumption_ids
            or assumption.get("subject_id") not in body_ids
            or assumption.get("interval_id") != interval_id
            or assumption.get("proposed_role") is not None
            or assumption.get("proposed_value") is not None
            or assumption.get("proposed_unit") is not None
            or not evidenced(assumption)
        ):
            return None
        authority_subjects.add(assumption.get("subject_id"))
    if authority_subjects != body_ids:
        return None

    def valued_source(item: dict[str, Any]) -> bool:
        return (
            item.get("raw_value") is not None
            and item.get("raw_unit") is not None
            and item.get("provenance") == "explicit_source"
            and item.get("symbol_id") is not None
            and evidenced(item)
        )

    quantities = {
        item.get("quantity_id"): item for item in payload["quantities"]
    }
    if len(quantities) != len(payload["quantities"]):
        return None

    query_subjects: list[str] = []
    unknown_ids: set[str] = set()
    for query in payload["queries"]:
        target = dict(query.get("target") or {})
        target_quantity = quantities.get(target.get("target_quantity_id"))
        if (
            target_quantity is None
            or query.get("shape") != "scalar"
            or query.get("objective") is not None
            or target.get("role") != "velocity"
            or target.get("component") != "x"
            or target.get("subject_id") not in body_ids
            or target.get("point_id") is not None
            or target.get("frame_id") is not None
            or target.get("interval_id") != interval_id
            or target.get("event_id") != end_id
            or target.get("direction") is not None
            or target_quantity.get("subject_id") != target.get("subject_id")
            or target_quantity.get("point_id") is not None
            or target_quantity.get("frame_id") is not None
            or target_quantity.get("interval_id") != interval_id
            or target_quantity.get("event_id") != end_id
            or target_quantity.get("role") != "velocity"
            or target_quantity.get("component") != "x"
            or target_quantity.get("direction") is not None
            or target_quantity.get("shape") != "scalar"
            or target_quantity.get("raw_value") is not None
            or target_quantity.get("raw_unit") is not None
            or target_quantity.get("provenance") != "unknown"
            or target_quantity.get("symbol_id") is None
            or target_quantity.get("evidence_refs")
            or query.get("output_dimension") != target_quantity.get("dimension")
            or query.get("evidence_refs")
        ):
            return None
        query_subjects.append(target.get("subject_id"))
        unknown_ids.add(target.get("target_quantity_id"))
    if len(set(query_subjects)) != len(query_subjects):
        return None

    symbol_counts: Counter[str | None] = Counter(
        item.get("quantity_id") for item in payload["symbols"]
    )
    if len(payload["symbols"]) != len(payload["quantities"]) or any(
        item.get("symbol_id") is None
        or symbol_counts[item.get("quantity_id")] != 1
        for item in payload["quantities"]
    ):
        return None

    known = [
        item
        for item in payload["quantities"]
        if item.get("quantity_id") not in unknown_ids
    ]
    masses = [item for item in known if item.get("role") == "mass"]
    approach = [
        item for item in known if item.get("role") in {"velocity", "speed"}
    ]
    coefficients = [
        item for item in known if item.get("role") == "coefficient_restitution"
    ]
    if (
        len(masses) != 2
        or len(approach) != 2
        or len(coefficients) != 1
        or len(known) != 5
    ):
        return None
    masses_by_subject = {item.get("subject_id"): item for item in masses}
    approach_by_subject = {item.get("subject_id"): item for item in approach}
    if set(masses_by_subject) != body_ids or set(approach_by_subject) != body_ids:
        return None
    if any(
        item.get("point_id") is not None
        or item.get("frame_id") is not None
        or item.get("interval_id") not in {None, interval_id}
        or item.get("event_id") is not None
        or item.get("shape") != "scalar"
        or item.get("component") != "unspecified"
        or item.get("direction") is not None
        or not valued_source(item)
        for item in masses
    ):
        return None
    approach_axis: dict[str, tuple[str, int]] = {}
    for item in approach:
        direction = (item.get("direction") or {}).get("direction")
        binding = _SEMANTIC_AXIS_BINDING.get(str(direction))
        if (
            item.get("role") != "velocity"
            or item.get("point_id") is not None
            or item.get("frame_id") is not None
            or item.get("interval_id") != interval_id
            or item.get("event_id") != start_id
            or item.get("shape") != "scalar"
            or not valued_source(item)
        ):
            return None
        if _directionless_zero_scalar(item):
            # Exactly zero, and the source said this quantity has no direction
            # at all.  Zero is the one value for which that is not a gap: it is
            # the same number on either sign of the line of impact, so binding
            # it to the impact axis adds no direction the source withheld.
            approach_axis[item.get("quantity_id")] = ("x", 1)
            continue
        axis_sign = (
            None
            if binding is None
            else _directed_scalar_axis_sign(binding[1], item.get("raw_value"))
        )
        if (
            item.get("component") != "unspecified"
            or (item.get("direction") or {}).get("kind") != "semantic"
            or direction not in {"left", "right"}
            or binding is None
            or axis_sign is None
        ):
            return None
        approach_axis[item.get("quantity_id")] = (binding[0], axis_sign)
    coefficient = coefficients[0]
    if (
        coefficient.get("subject_id") not in body_ids
        or coefficient.get("point_id") is not None
        or coefficient.get("frame_id") is not None
        or coefficient.get("interval_id") not in {None, interval_id}
        or coefficient.get("event_id") is not None
        or coefficient.get("shape") != "scalar"
        or coefficient.get("component") != "unspecified"
        or coefficient.get("direction") is not None
        or not valued_source(coefficient)
    ):
        return None

    frame_evidence = sorted(
        {
            evidence_id
            for item in (*masses, *approach)
            for evidence_id in item.get("evidence_refs", ())
        }
    )
    if not frame_evidence or len(frame_evidence) > 16:
        return None
    world = {
        "frame_id": COLLISION_RESTITUTION_FRAME_ID,
        "frame_type": "cartesian_2d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": name,
                "direction": {
                    "kind": "axis",
                    "frame_id": COLLISION_RESTITUTION_FRAME_ID,
                    "axis": name,
                    "sign": 1,
                },
            }
            for name in ("x", "y")
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": frame_evidence,
    }

    rewritten_quantities: list[dict[str, Any]] = []
    rebound: list[str] = []
    for original in payload["quantities"]:
        item = dict(original)
        quantity_id = item.get("quantity_id")
        if quantity_id in approach_axis:
            axis, sign = approach_axis[quantity_id]
            item.update(
                frame_id=COLLISION_RESTITUTION_FRAME_ID,
                component=axis,
                direction={
                    "kind": "axis",
                    "frame_id": COLLISION_RESTITUTION_FRAME_ID,
                    "axis": axis,
                    "sign": sign,
                },
            )
            rebound.append(quantity_id)
        elif quantity_id in unknown_ids:
            item.update(frame_id=COLLISION_RESTITUTION_FRAME_ID)
            rebound.append(quantity_id)
        rewritten_quantities.append(item)

    generated_ids: list[str] = [COLLISION_RESTITUTION_FRAME_ID]
    extra_quantities: list[dict[str, Any]] = []
    extra_symbols: list[dict[str, Any]] = []
    partner_ids = sorted(body_ids - set(query_subjects))
    if partner_ids:
        partner_id = partner_ids[0]
        template = quantities[next(iter(unknown_ids))]
        extra_quantities.append(
            {
                "quantity_id": COLLISION_PARTNER_AFTER_QUANTITY_ID,
                "symbol_id": COLLISION_PARTNER_AFTER_SYMBOL_ID,
                "role": "velocity",
                "subject_id": partner_id,
                "point_id": None,
                "frame_id": COLLISION_RESTITUTION_FRAME_ID,
                "interval_id": interval_id,
                "event_id": end_id,
                "component": "x",
                "shape": "scalar",
                "dimension": dict(template.get("dimension") or {}),
                "provenance": "unknown",
                "evidence_refs": [],
            }
        )
        extra_symbols.append(
            {
                "symbol_id": COLLISION_PARTNER_AFTER_SYMBOL_ID,
                "quantity_id": COLLISION_PARTNER_AFTER_QUANTITY_ID,
                "dimension": dict(template.get("dimension") or {}),
                "shape": "scalar",
            }
        )
        generated_ids.append(COLLISION_PARTNER_AFTER_QUANTITY_ID)

    linked_quantity_ids = sorted(
        {
            *(item.get("quantity_id") for item in masses),
            *(item.get("quantity_id") for item in approach),
            coefficient.get("quantity_id"),
            *unknown_ids,
            *(item["quantity_id"] for item in extra_quantities),
        }
    )
    rewritten_interaction = dict(impact)
    rewritten_interaction.update(
        frame_id=COLLISION_RESTITUTION_FRAME_ID,
        quantity_ids=linked_quantity_ids,
    )

    rewritten_queries: list[dict[str, Any]] = []
    for query in payload["queries"]:
        rewritten_query = dict(query)
        rewritten_target = dict(query.get("target") or {})
        rewritten_target.update(frame_id=COLLISION_RESTITUTION_FRAME_ID)
        rewritten_query.update(target=rewritten_target)
        rewritten_queries.append(rewritten_query)

    closed = dict(payload)
    closed["reference_frames"] = [world]
    closed["interactions"] = [rewritten_interaction]
    closed["quantities"] = [*rewritten_quantities, *extra_quantities]
    closed["symbols"] = [*payload["symbols"], *extra_symbols]
    closed["queries"] = rewritten_queries
    return (
        closed,
        tuple(generated_ids),
        tuple(sorted(rebound)),
    )


def _explicit_resultant_force_transaction(
    payload: dict[str, Any], _authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact free-particle single-applied-force readout.

    The transaction creates no value, equation, assumption, solver choice,
    candidate, or answer.  It materialises the world frame, binds the
    source's horizontally directed force and the value-free x-component
    acceleration query onto that frame's axis, and records the
    applied-force interaction the source's force statement already is, so
    the existing ``particle_newton_second`` generic law does all solving on
    the typed model's entire — single-force — free body.
    """

    reserved_ids = {RESULTANT_FORCE_FRAME_ID, RESULTANT_FORCE_INTERACTION_ID}
    if (
        len(payload["entities"]) != 1
        or len(payload["motion_intervals"]) != 1
        or len(payload["queries"]) != 1
        or len(payload["events"]) != 2
        or len(payload["quantities"]) != 3
        or payload["reference_frames"]
        or payload["points"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["state_conditions"]
        or payload["principle_hints"]
        or payload["ambiguities"]
        or payload["unsupported_features"]
        or payload["geometry"]
        or payload["figure_dependency"] != {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        }
        or reserved_ids & _authored_draft_ids(payload)
    ):
        return None

    particle = payload["entities"][0]
    if particle.get("primitive") != "particle":
        return None
    particle_id = particle.get("entity_id")

    interval = payload["motion_intervals"][0]
    interval_id = interval.get("interval_id")
    if (
        interval.get("subject_ids") != [particle_id]
        or interval.get("frame_id") is not None
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or interval.get("start_event_id") == interval.get("end_event_id")
    ):
        return None

    events = {item.get("event_id"): item for item in payload["events"]}
    start = events.get(interval.get("start_event_id"))
    finish = events.get(interval.get("end_event_id"))
    if (
        len(events) != 2
        or start is None
        or finish is None
        or start.get("kind") != "start"
        or finish.get("kind") != "finish"
        or any(
            item.get("subject_ids") != [particle_id]
            or item.get("time_quantity_id") is not None
            or item.get("interval_ids") != [interval_id]
            or item.get("occurs_in_interval_ids")
            for item in payload["events"]
        )
    ):
        return None

    source_evidence_ids = {
        item.get("evidence_id") for item in payload["source_evidence"]
    }

    def evidenced(item: dict[str, Any]) -> bool:
        refs = set(item.get("evidence_refs", ()))
        return bool(refs) and refs.issubset(source_evidence_ids)

    if any(
        item.get("subject_id") != particle_id
        or item.get("interval_id") not in {None, interval_id}
        or item.get("proposed_role") is not None
        or item.get("proposed_value") is not None
        or item.get("proposed_unit") is not None
        or not evidenced(item)
        for item in payload["assumptions"]
    ):
        return None

    def valued_source(item: dict[str, Any]) -> bool:
        return (
            item.get("raw_value") is not None
            and item.get("raw_unit") is not None
            and item.get("provenance") == "explicit_source"
            and item.get("symbol_id") is not None
            and evidenced(item)
        )

    query = payload["queries"][0]
    target = dict(query.get("target") or {})
    target_quantity_id = target.get("target_quantity_id")
    quantities = {
        item.get("quantity_id"): item for item in payload["quantities"]
    }
    target_quantity = quantities.get(target_quantity_id)
    if (
        len(quantities) != len(payload["quantities"])
        or target_quantity is None
        or query.get("shape") != "scalar"
        or target.get("role") != "acceleration"
        or target.get("component") != "x"
        or target.get("subject_id") != particle_id
        or target.get("point_id") is not None
        or target.get("frame_id") is not None
        or target.get("interval_id") != interval_id
        or target.get("event_id") is not None
        or target.get("direction") is not None
        or target_quantity.get("subject_id") != particle_id
        or target_quantity.get("point_id") is not None
        or target_quantity.get("frame_id") is not None
        or target_quantity.get("interval_id") != interval_id
        or target_quantity.get("event_id") is not None
        or target_quantity.get("role") != "acceleration"
        or target_quantity.get("component") != "x"
        or target_quantity.get("direction") is not None
        or target_quantity.get("shape") != "scalar"
        or target_quantity.get("raw_value") is not None
        or target_quantity.get("raw_unit") is not None
        or target_quantity.get("provenance") != "unknown"
        or target_quantity.get("symbol_id") is None
        or target_quantity.get("evidence_refs")
        or query.get("output_dimension") != target_quantity.get("dimension")
        or query.get("evidence_refs")
    ):
        return None

    symbol_counts: Counter[str | None] = Counter(
        item.get("quantity_id") for item in payload["symbols"]
    )
    if len(payload["symbols"]) != len(payload["quantities"]) or any(
        item.get("symbol_id") is None
        or symbol_counts[item.get("quantity_id")] != 1
        for item in payload["quantities"]
    ):
        return None

    known = [
        item
        for item in payload["quantities"]
        if item.get("quantity_id") != target_quantity_id
    ]
    masses = [item for item in known if item.get("role") == "mass"]
    forces = [item for item in known if item.get("role") == "force"]
    if len(masses) != 1 or len(forces) != 1 or len(known) != 2:
        return None
    mass = masses[0]
    if (
        mass.get("subject_id") != particle_id
        or mass.get("point_id") is not None
        or mass.get("frame_id") is not None
        or mass.get("interval_id") not in {None, interval_id}
        or mass.get("event_id") is not None
        or mass.get("shape") != "scalar"
        or mass.get("component") != "unspecified"
        or mass.get("direction") is not None
        or not valued_source(mass)
    ):
        return None
    force = forces[0]
    force_direction = (force.get("direction") or {}).get("direction")
    if (
        force.get("subject_id") != particle_id
        or force.get("point_id") is not None
        or force.get("frame_id") is not None
        or force.get("interval_id") != interval_id
        or force.get("event_id") is not None
        or force.get("shape") != "scalar"
        or force.get("component") != "unspecified"
        or (force.get("direction") or {}).get("kind") != "semantic"
        or force_direction not in {"right", "left"}
        or not valued_source(force)
    ):
        return None
    axis, sign = _SEMANTIC_AXIS_BINDING[force_direction]

    frame_evidence = sorted(set(force.get("evidence_refs", ())))
    if not frame_evidence or len(frame_evidence) > 16:
        return None
    world = {
        "frame_id": RESULTANT_FORCE_FRAME_ID,
        "frame_type": "cartesian_2d",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": name,
                "direction": {
                    "kind": "axis",
                    "frame_id": RESULTANT_FORCE_FRAME_ID,
                    "axis": name,
                    "sign": 1,
                },
            }
            for name in ("x", "y")
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": frame_evidence,
    }

    rewritten_quantities: list[dict[str, Any]] = []
    rebound: list[str] = []
    for original in payload["quantities"]:
        item = dict(original)
        quantity_id = item.get("quantity_id")
        if quantity_id == force.get("quantity_id"):
            item.update(
                frame_id=RESULTANT_FORCE_FRAME_ID,
                component=axis,
                direction={
                    "kind": "axis",
                    "frame_id": RESULTANT_FORCE_FRAME_ID,
                    "axis": axis,
                    "sign": sign,
                },
            )
            rebound.append(quantity_id)
        elif quantity_id == target_quantity_id:
            item.update(frame_id=RESULTANT_FORCE_FRAME_ID)
            rebound.append(quantity_id)
        rewritten_quantities.append(item)

    interaction = {
        "interaction_id": RESULTANT_FORCE_INTERACTION_ID,
        "kind": "applied_force",
        "participant_ids": [particle_id],
        "point_ids": [],
        "frame_id": RESULTANT_FORCE_FRAME_ID,
        "interval_id": interval_id,
        "event_id": None,
        "quantity_ids": [force.get("quantity_id")],
        "evidence_refs": frame_evidence,
    }

    rewritten_query = dict(query)
    rewritten_target = dict(target)
    rewritten_target.update(
        frame_id=RESULTANT_FORCE_FRAME_ID,
        target_quantity_id=target_quantity_id,
    )
    rewritten_query.update(target=rewritten_target)

    closed = dict(payload)
    closed["reference_frames"] = [world]
    closed["interactions"] = [interaction]
    closed["quantities"] = rewritten_quantities
    closed["queries"] = [rewritten_query]
    return (
        closed,
        (RESULTANT_FORCE_FRAME_ID, RESULTANT_FORCE_INTERACTION_ID),
        tuple(sorted(rebound)),
    )


def _vertical_circle_top_speed_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact vertical-circle limiting-contact minimum readout.

    The transaction creates no equation, force, frame, point, solver choice,
    candidate, or answer, and the only value it materialises is the gravity
    magnitude the Lane B authority stage has already authorised from the
    source's own approved server-valued proposal — the free-flight
    consumption contract, checked field for field.  The existing
    ``vertical_circle_top_minimum_speed`` generic law does all solving.

    The boundary reading must be typed in full before anything closes: the
    query's own ``minimum`` objective, the contact's ``inward`` side, a
    maintained ``contact``/``touching`` state over the interval, and an
    active ``boundary`` state at the highest-point instant.  A plain speed
    question, an unstated or outward orientation, or missing boundary
    states refuse — the equality ``v^2 = g r`` states the asked-for
    boundary only when the source asked for that boundary.
    """

    reserved_ids = {
        VERTICAL_CIRCLE_GRAVITY_QUANTITY_ID,
        VERTICAL_CIRCLE_GRAVITY_SYMBOL_ID,
    }
    if (
        len(payload["entities"]) != 2
        or len(payload["motion_intervals"]) != 1
        or len(payload["queries"]) != 1
        or len(payload["events"]) != 3
        or len(payload["interactions"]) != 1
        or len(payload["assumptions"]) != 1
        or len(payload["quantities"]) != 2
        or len(payload["state_conditions"]) != 2
        or payload["reference_frames"]
        or payload["points"]
        or payload["geometry"]
        or payload["constraints"]
        or payload["principle_hints"]
        or payload["ambiguities"]
        or payload["unsupported_features"]
        or payload["figure_dependency"] != {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        }
        or reserved_ids & _authored_draft_ids(payload)
    ):
        return None

    particles = [
        item for item in payload["entities"]
        if item.get("primitive") == "particle"
    ]
    surfaces = [
        item for item in payload["entities"]
        if item.get("primitive") == "surface"
    ]
    if len(particles) != 1 or len(surfaces) != 1:
        return None
    particle_id = particles[0].get("entity_id")
    surface_id = surfaces[0].get("entity_id")

    interval = payload["motion_intervals"][0]
    interval_id = interval.get("interval_id")
    if (
        interval.get("subject_ids") != [particle_id]
        or interval.get("frame_id") is not None
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or interval.get("start_event_id") == interval.get("end_event_id")
    ):
        return None

    contact = payload["interactions"][0]
    if (
        contact.get("kind") != "contact"
        or contact.get("contact_side") != "inward"
        or set(contact.get("participant_ids", ())) != {particle_id, surface_id}
        or len(contact.get("participant_ids", ())) != 2
        or contact.get("point_ids")
        or contact.get("frame_id") is not None
        or contact.get("interval_id") not in {None, interval_id}
        or contact.get("event_id") is not None
        or contact.get("quantity_ids")
    ):
        return None

    events = {item.get("event_id"): item for item in payload["events"]}
    start = events.get(interval.get("start_event_id"))
    finish = events.get(interval.get("end_event_id"))
    instants = [
        item
        for item in payload["events"]
        if item.get("event_id")
        not in {interval.get("start_event_id"), interval.get("end_event_id")}
    ]
    if (
        len(events) != 3
        or start is None
        or finish is None
        or len(instants) != 1
        or start.get("kind") != "start"
        or finish.get("kind") != "finish"
        or instants[0].get("kind") != "highest_point"
        or any(
            item.get("subject_ids") != [particle_id]
            or item.get("time_quantity_id") is not None
            for item in payload["events"]
        )
        or start.get("interval_ids") != [interval_id]
        or finish.get("interval_ids") != [interval_id]
        or start.get("occurs_in_interval_ids")
        or finish.get("occurs_in_interval_ids")
        or instants[0].get("interval_ids")
        or instants[0].get("occurs_in_interval_ids") != [interval_id]
    ):
        return None
    top_id = instants[0].get("event_id")

    touching_states = [
        item
        for item in payload["state_conditions"]
        if item.get("kind") == "contact" and item.get("state") == "touching"
    ]
    boundary_states = [
        item
        for item in payload["state_conditions"]
        if item.get("kind") == "boundary" and item.get("state") == "active"
    ]
    if (
        len(touching_states) != 1
        or len(boundary_states) != 1
        or touching_states[0].get("subject_id") != particle_id
        or touching_states[0].get("interval_id") != interval_id
        or touching_states[0].get("event_id") is not None
        or touching_states[0].get("expression") is not None
        or touching_states[0].get("quantity_ids")
        or boundary_states[0].get("subject_id") != particle_id
        or boundary_states[0].get("interval_id") != interval_id
        or boundary_states[0].get("event_id") != top_id
        or boundary_states[0].get("expression") is not None
        or boundary_states[0].get("quantity_ids")
    ):
        return None

    source_evidence_ids = {
        item.get("evidence_id") for item in payload["source_evidence"]
    }

    def evidenced(item: dict[str, Any]) -> bool:
        refs = set(item.get("evidence_refs", ()))
        return bool(refs) and refs.issubset(source_evidence_ids)

    # Exactly one approved constant_gravity assumption, and the authority
    # stage must have issued its authorization — the free-flight contract.
    assumption = payload["assumptions"][0]
    if (
        assumption.get("kind") != "constant_gravity"
        or assumption.get("disposition") != "approved"
        or assumption.get("assumption_id")
        not in authority.approved_assumption_ids
        or not evidenced(assumption)
    ):
        return None
    authorization = authority.authorized_assumptions.get(
        assumption.get("assumption_id")
    )
    if type(authorization) is not AssumptionAuthorization:
        return None
    if (
        authorization.assumption_id != assumption.get("assumption_id")
        or str(getattr(authorization.role, "value", authorization.role))
        != _GRAVITY_ROLE
        or str(assumption.get("proposed_role") or "") != _GRAVITY_ROLE
        or assumption.get("proposed_value") != authorization.raw_value
        or assumption.get("proposed_unit") != authorization.raw_unit
        or assumption.get("subject_id") != authorization.subject_id
        or assumption.get("interval_id") != authorization.interval_id
        or authorization.subject_id != particle_id
        or authorization.interval_id != interval_id
    ):
        return None

    if not (evidenced(touching_states[0]) and evidenced(boundary_states[0])):
        return None

    def valued_source(item: dict[str, Any]) -> bool:
        return (
            item.get("raw_value") is not None
            and item.get("raw_unit") is not None
            and item.get("provenance") == "explicit_source"
            and item.get("symbol_id") is not None
            and evidenced(item)
        )

    query = payload["queries"][0]
    target = dict(query.get("target") or {})
    target_quantity_id = target.get("target_quantity_id")
    quantities = {
        item.get("quantity_id"): item for item in payload["quantities"]
    }
    target_quantity = quantities.get(target_quantity_id)
    if (
        len(quantities) != len(payload["quantities"])
        or target_quantity is None
        or query.get("shape") != "scalar"
        or query.get("objective") != "minimum"
        or target.get("role") != "speed"
        or target.get("component") != "magnitude"
        or target.get("subject_id") != particle_id
        or target.get("point_id") is not None
        or target.get("frame_id") is not None
        or target.get("interval_id") != interval_id
        or target.get("event_id") != top_id
        or target.get("direction") is not None
        or target_quantity.get("subject_id") != particle_id
        or target_quantity.get("point_id") is not None
        or target_quantity.get("frame_id") is not None
        or target_quantity.get("interval_id") != interval_id
        or target_quantity.get("event_id") != top_id
        or target_quantity.get("role") != "speed"
        or target_quantity.get("component") != "magnitude"
        or target_quantity.get("direction") is not None
        or target_quantity.get("shape") != "scalar"
        or target_quantity.get("raw_value") is not None
        or target_quantity.get("raw_unit") is not None
        or target_quantity.get("provenance") != "unknown"
        or target_quantity.get("symbol_id") is None
        or target_quantity.get("evidence_refs")
        or query.get("output_dimension") != target_quantity.get("dimension")
        or query.get("evidence_refs")
    ):
        return None

    symbol_counts: Counter[str | None] = Counter(
        item.get("quantity_id") for item in payload["symbols"]
    )
    if len(payload["symbols"]) != len(payload["quantities"]) or any(
        item.get("symbol_id") is None
        or symbol_counts[item.get("quantity_id")] != 1
        for item in payload["quantities"]
    ):
        return None

    radii = [
        item
        for item in payload["quantities"]
        if item.get("quantity_id") != target_quantity_id
    ]
    if len(radii) != 1 or radii[0].get("role") != "radius":
        return None
    radius = radii[0]
    if (
        radius.get("subject_id") != particle_id
        or radius.get("point_id") is not None
        or radius.get("frame_id") is not None
        or radius.get("interval_id") != interval_id
        or radius.get("event_id") is not None
        or radius.get("shape") != "scalar"
        or radius.get("component") != "unspecified"
        or radius.get("direction") is not None
        or not valued_source(radius)
    ):
        return None

    gravity_quantity = {
        "quantity_id": VERTICAL_CIRCLE_GRAVITY_QUANTITY_ID,
        "symbol_id": VERTICAL_CIRCLE_GRAVITY_SYMBOL_ID,
        "role": _GRAVITY_ROLE,
        "subject_id": authorization.subject_id,
        "point_id": None,
        "frame_id": None,
        "interval_id": interval_id,
        "event_id": None,
        "component": "magnitude",
        "shape": "scalar",
        "dimension": dict(_ACCELERATION_DIMENSION),
        "provenance": "server_default",
        "raw_value": authorization.raw_value,
        "raw_unit": authorization.raw_unit,
        "assumption_policy_ref": authorization.assumption_id,
        "evidence_refs": [],
    }
    gravity_symbol = {
        "symbol_id": VERTICAL_CIRCLE_GRAVITY_SYMBOL_ID,
        "quantity_id": VERTICAL_CIRCLE_GRAVITY_QUANTITY_ID,
        "dimension": dict(_ACCELERATION_DIMENSION),
        "shape": "scalar",
    }

    closed = dict(payload)
    closed["quantities"] = [*payload["quantities"], gravity_quantity]
    closed["symbols"] = [*payload["symbols"], gravity_symbol]
    return (
        closed,
        (VERTICAL_CIRCLE_GRAVITY_QUANTITY_ID,),
        (),
    )


def _rolling_incline_energy_speed_transaction(
    payload: dict[str, Any], authority: TransactionAuthority
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]] | None:
    """Close one exact pure-rolling incline energy-endpoint readout.

    The transaction creates no equation, force, frame, point, solver choice,
    candidate, or answer.  The only value it materialises is the gravity
    magnitude the Lane B authority stage has already authorised from the
    source's own approved server-valued proposal; the rest-release descent
    sub-shape keeps its start speed a value-free unknown whose zero is
    stated by the projected at_rest boundary itself.  The existing
    ``rolling_general_principal_energy`` generic law does all solving.
    """

    reserved_ids = {ROLLING_GRAVITY_QUANTITY_ID, ROLLING_GRAVITY_SYMBOL_ID}
    if (
        len(payload["entities"]) != 2
        or len(payload["motion_intervals"]) != 1
        or len(payload["queries"]) != 1
        or len(payload["events"]) != 2
        or len(payload["geometry"]) != 1
        or len(payload["quantities"]) != 6
        or len(payload["assumptions"]) not in {2, 3}
        or len(payload["state_conditions"]) > 1
        or payload["reference_frames"]
        or payload["points"]
        or payload["interactions"]
        or payload["constraints"]
        or payload["principle_hints"]
        or payload["ambiguities"]
        or payload["unsupported_features"]
        or payload["figure_dependency"] != {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        }
        or reserved_ids & _authored_draft_ids(payload)
    ):
        return None

    bodies = [
        item for item in payload["entities"]
        if item.get("primitive") == "rigid_body"
    ]
    inclines = [
        item for item in payload["entities"]
        if item.get("primitive") == "incline"
    ]
    if len(bodies) != 1 or len(inclines) != 1:
        return None
    body_id = bodies[0].get("entity_id")
    incline_id = inclines[0].get("entity_id")

    interval = payload["motion_intervals"][0]
    interval_id = interval.get("interval_id")
    if (
        interval.get("subject_ids") != [body_id]
        or interval.get("frame_id") is not None
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or interval.get("start_event_id") == interval.get("end_event_id")
    ):
        return None

    tangent = payload["geometry"][0]
    if (
        tangent.get("kind") != "tangent"
        or set(tangent.get("participant_ids", ())) != {body_id, incline_id}
        or len(tangent.get("participant_ids", ())) != 2
        or tangent.get("interval_id") not in {None, interval_id}
        or tangent.get("quantity_ids")
        or tangent.get("expression") is not None
    ):
        return None

    events = {item.get("event_id"): item for item in payload["events"]}
    start = events.get(interval.get("start_event_id"))
    finish = events.get(interval.get("end_event_id"))
    if (
        len(events) != 2
        or start is None
        or finish is None
        or any(
            item.get("subject_ids") != [body_id]
            or item.get("time_quantity_id") is not None
            or item.get("interval_ids") != [interval_id]
            or item.get("occurs_in_interval_ids")
            for item in payload["events"]
        )
    ):
        return None
    descent = (
        start.get("kind") == "release" and finish.get("kind") == "finish"
    )
    climb = (
        start.get("kind") == "start"
        and finish.get("kind") == "reaches_condition"
    )
    if descent == climb:
        return None

    source_evidence_ids = {
        item.get("evidence_id") for item in payload["source_evidence"]
    }

    def evidenced(item: dict[str, Any]) -> bool:
        refs = set(item.get("evidence_refs", ()))
        return bool(refs) and refs.issubset(source_evidence_ids)

    def approved(item: dict[str, Any]) -> bool:
        return (
            item.get("disposition") == "approved"
            and item.get("subject_id") == body_id
            and item.get("interval_id") == interval_id
            and evidenced(item)
        )

    by_kind: dict[str, dict[str, Any]] = {}
    for item in payload["assumptions"]:
        if item.get("kind") in by_kind:
            return None
        by_kind[item.get("kind")] = item
    rolling = by_kind.get("pure_rolling")
    gravity_assumption = by_kind.get("constant_gravity")
    rest_assumption = by_kind.get("starts_from_rest")
    if (
        rolling is None
        or gravity_assumption is None
        or not approved(rolling)
        or rolling.get("proposed_role") is not None
        or rolling.get("proposed_value") is not None
        or rolling.get("proposed_unit") is not None
        or not approved(gravity_assumption)
        or set(by_kind)
        != (
            {"pure_rolling", "constant_gravity", "starts_from_rest"}
            if descent
            else {"pure_rolling", "constant_gravity"}
        )
    ):
        return None
    if descent and (
        rest_assumption is None or not approved(rest_assumption)
    ):
        return None

    def authorization_for(
        assumption: dict[str, Any], role: str
    ) -> AssumptionAuthorization | None:
        if assumption.get("assumption_id") not in authority.approved_assumption_ids:
            return None
        authorization = authority.authorized_assumptions.get(
            assumption.get("assumption_id")
        )
        if type(authorization) is not AssumptionAuthorization:
            return None
        if (
            authorization.assumption_id != assumption.get("assumption_id")
            or str(getattr(authorization.role, "value", authorization.role))
            != role
            or str(assumption.get("proposed_role") or "") != role
            or assumption.get("proposed_value") != authorization.raw_value
            or assumption.get("proposed_unit") != authorization.raw_unit
            or assumption.get("subject_id") != authorization.subject_id
            or assumption.get("interval_id") != authorization.interval_id
            or authorization.subject_id != body_id
            or authorization.interval_id != interval_id
        ):
            return None
        return authorization

    gravity_authorization = authorization_for(gravity_assumption, _GRAVITY_ROLE)
    if gravity_authorization is None:
        return None

    def scalar_scoped(item: dict[str, Any]) -> bool:
        return (
            item.get("point_id") is None
            and item.get("frame_id") is None
            and item.get("interval_id") == interval_id
            and item.get("shape") == "scalar"
        )

    def valued_source(item: dict[str, Any]) -> bool:
        return (
            item.get("raw_value") is not None
            and item.get("raw_unit") is not None
            and item.get("provenance") == "explicit_source"
            and item.get("symbol_id") is not None
            and evidenced(item)
        )

    query = payload["queries"][0]
    target = dict(query.get("target") or {})
    target_quantity_id = target.get("target_quantity_id")
    quantities = {
        item.get("quantity_id"): item for item in payload["quantities"]
    }
    target_quantity = quantities.get(target_quantity_id)
    if (
        len(quantities) != len(payload["quantities"])
        or target_quantity is None
        or query.get("shape") != "scalar"
        or target.get("role") != "velocity"
        or target.get("component") != "magnitude"
        or target.get("subject_id") != body_id
        or target.get("point_id") is not None
        or target.get("frame_id") is not None
        or target.get("interval_id") != interval_id
        or target.get("event_id") != interval.get("end_event_id")
        or target.get("direction") is not None
        or target_quantity.get("subject_id") != body_id
        or not scalar_scoped(target_quantity)
        or target_quantity.get("event_id") != interval.get("end_event_id")
        or target_quantity.get("role") != "velocity"
        or target_quantity.get("component") != "magnitude"
        or target_quantity.get("direction") is not None
        or target_quantity.get("raw_value") is not None
        or target_quantity.get("raw_unit") is not None
        or target_quantity.get("provenance") != "unknown"
        or target_quantity.get("symbol_id") is None
        or target_quantity.get("evidence_refs")
        or query.get("output_dimension") != target_quantity.get("dimension")
        or query.get("evidence_refs")
    ):
        return None

    symbol_counts: Counter[str | None] = Counter(
        item.get("quantity_id") for item in payload["symbols"]
    )
    if len(payload["symbols"]) != len(payload["quantities"]) or any(
        item.get("symbol_id") is None
        or symbol_counts[item.get("quantity_id")] != 1
        for item in payload["quantities"]
    ):
        return None

    known = [
        item
        for item in payload["quantities"]
        if item.get("quantity_id") != target_quantity_id
    ]

    def one_plain(role: str) -> dict[str, Any] | None:
        matches = [item for item in known if item.get("role") == role]
        if len(matches) != 1:
            return None
        item = matches[0]
        if (
            item.get("subject_id") == body_id
            and scalar_scoped(item)
            and item.get("event_id") is None
            and item.get("component") == "unspecified"
            and item.get("direction") is None
            and valued_source(item)
        ):
            return item
        return None

    mass = one_plain("mass")
    radius = one_plain("radius")
    inertia = one_plain("moment_of_inertia")
    if mass is None or radius is None or inertia is None:
        return None

    heights = [item for item in known if item.get("role") == "height"]
    start_speeds = [
        item
        for item in known
        if item.get("role") == "velocity"
        and item.get("event_id") == interval.get("start_event_id")
    ]
    if len(heights) != 1 or len(start_speeds) != 1 or len(known) != 5:
        return None
    height = heights[0]
    start_speed = start_speeds[0]
    height_direction = (height.get("direction") or {}).get("direction")
    if (
        height.get("subject_id") != body_id
        or not scalar_scoped(height)
        or height.get("component") != "unspecified"
        or height_direction
        not in ({None, "downward"} if descent else {None, "upward"})
        or not valued_source(height)
        or height.get("event_id")
        != (None if descent else interval.get("end_event_id"))
    ):
        return None
    if descent:
        if (
            start_speed.get("subject_id") != body_id
            or not scalar_scoped(start_speed)
            or start_speed.get("component") != "magnitude"
            or start_speed.get("direction") is not None
            or start_speed.get("raw_value") is not None
            or start_speed.get("raw_unit") is not None
            or start_speed.get("provenance") != "unknown"
            or start_speed.get("symbol_id") is None
        ):
            return None
    else:
        start_direction = (start_speed.get("direction") or {}).get("direction")
        if (
            start_speed.get("subject_id") != body_id
            or not scalar_scoped(start_speed)
            or start_speed.get("component") not in {"unspecified", "magnitude"}
            or start_direction not in {None, "along_motion"}
            or not valued_source(start_speed)
        ):
            return None

    if descent:
        if len(payload["state_conditions"]) != 1:
            return None
        rest_state = payload["state_conditions"][0]
        if (
            rest_state.get("kind") != "initial"
            or rest_state.get("state") != "at_rest"
            or rest_state.get("subject_id") != body_id
            or rest_state.get("interval_id") != interval_id
            or rest_state.get("event_id") != interval.get("start_event_id")
            or rest_state.get("expression") is not None
            or rest_state.get("quantity_ids")
            != [start_speed.get("quantity_id")]
            or not evidenced(rest_state)
        ):
            return None
    elif payload["state_conditions"]:
        return None

    gravity_quantity = {
        "quantity_id": ROLLING_GRAVITY_QUANTITY_ID,
        "symbol_id": ROLLING_GRAVITY_SYMBOL_ID,
        "role": _GRAVITY_ROLE,
        "subject_id": gravity_authorization.subject_id,
        "point_id": None,
        "frame_id": None,
        "interval_id": interval_id,
        "event_id": None,
        "component": "magnitude",
        "shape": "scalar",
        "dimension": dict(_ACCELERATION_DIMENSION),
        "provenance": "server_default",
        "raw_value": gravity_authorization.raw_value,
        "raw_unit": gravity_authorization.raw_unit,
        "assumption_policy_ref": gravity_authorization.assumption_id,
        "evidence_refs": [],
    }
    gravity_symbol = {
        "symbol_id": ROLLING_GRAVITY_SYMBOL_ID,
        "quantity_id": ROLLING_GRAVITY_QUANTITY_ID,
        "dimension": dict(_ACCELERATION_DIMENSION),
        "shape": "scalar",
    }

    # A directionless scalar velocity magnitude is the equivalent speed
    # magnitude — the same normalisation the sealed fixed-axis packages
    # apply — so the endpoint readouts reach the energy law's own typed
    # role without any value changing.
    speed_ids = {
        start_speed.get("quantity_id"),
        target_quantity_id,
    }
    rewritten_quantities: list[dict[str, Any]] = []
    rebound: list[str] = []
    for original in payload["quantities"]:
        item = dict(original)
        if item.get("quantity_id") in speed_ids:
            item.update(role="speed")
            rebound.append(item["quantity_id"])
        rewritten_quantities.append(item)

    rewritten_query = dict(query)
    rewritten_target = dict(target)
    rewritten_target.update(role="speed", target_quantity_id=target_quantity_id)
    rewritten_query.update(target=rewritten_target)

    closed = dict(payload)
    closed["quantities"] = [*rewritten_quantities, gravity_quantity]
    closed["symbols"] = [*payload["symbols"], gravity_symbol]
    closed["queries"] = [rewritten_query]
    return (
        closed,
        (ROLLING_GRAVITY_QUANTITY_ID,),
        tuple(sorted(rebound)),
    )


_TRANSACTIONS = {
    ProfileId.signed_constant_acceleration_1d: (
        _signed_constant_acceleration_1d_transaction
    ),
    ProfileId.particle_work_energy_speed: (
        _particle_work_energy_speed_transaction
    ),
    ProfileId.direct_constant_force_work: (
        _direct_constant_force_work_transaction
    ),
    ProfileId.polar_kinematics_state: _polar_kinematics_state_transaction,
    ProfileId.free_flight_gravity: _free_flight_gravity_transaction,
    ProfileId.impulse_momentum: _impulse_momentum_transaction,
    ProfileId.fixed_pulley: _fixed_pulley_acceleration_transaction,
    ProfileId.incline_hanging_pulley: _incline_hanging_pulley_transaction,
    ProfileId.table_pulley_two_body: _table_pulley_two_body_transaction,
    ProfileId.incline_kinetic_sliding: _incline_kinetic_sliding_transaction,
    ProfileId.rigid_two_point_speed: (
        _rigid_two_point_speed_transfer_transaction
    ),
    ProfileId.collision_restitution: (
        _collision_restitution_transaction
    ),
    ProfileId.explicit_resultant_force: (
        _explicit_resultant_force_transaction
    ),
    ProfileId.vertical_circle_top_speed: (
        _vertical_circle_top_speed_transaction
    ),
    ProfileId.rolling_incline_energy_speed: (
        _rolling_incline_energy_speed_transaction
    ),
    ProfileId.rigid_fixed_axis: (
        _rigid_fixed_axis_point_speed_transaction
    ),
    ProfileId.slot_pin_relative_frame: _slot_pin_relative_frame_transaction,
    ProfileId.rotating_relative_frame: _rotating_relative_frame_transaction,
    ProfileId.relative_translating_frame: _relative_translating_frame_transaction,
}
# A profile whose only unmet prerequisite is a declared engine capability may be
# built even though its plan is `unsupported`: the structure it creates cannot
# produce an answer, it can only turn an undifferentiated underdetermined graph
# into the precise refusal the engine already knows how to make.
_DEFERRAL_ONLY_PROFILES: frozenset[ProfileId] = frozenset(
    {
        ProfileId.slot_pin_relative_frame,
        ProfileId.rotating_relative_frame,
        ProfileId.relative_translating_frame,
    }
)


def apply_complete_profile(
    plan: CompleteProfilePlanV1,
    draft: MechanicsProblemDraftV1,
    authority: TransactionAuthority | None = None,
) -> ProfileApplication:
    """Apply one complete plan to one Draft, entirely or not at all.

    The plan must be `complete` and must have been computed against *this*
    Draft; a plan from a different Draft is refused rather than re-planned,
    because re-planning here would make the planning phase a mutation.

    `authority` is what the Lane B authority stage issued for this Draft.
    Omitting it is the fail-closed default: a transaction that needs an
    authorization then refuses, and no transaction can mint one here.
    """

    authorised = plan.disposition is PlanDisposition.complete or (
        plan.disposition is PlanDisposition.unsupported
        and plan.profile_id in _DEFERRAL_ONLY_PROFILES
        and plan.structurally_complete
    )
    if not authorised:
        return ProfileApplication(
            ApplicationOutcome.not_applied, draft, sanitized_reason="plan_not_complete"
        )
    if plan.draft_fingerprint != draft_structure_fingerprint(draft):
        return ProfileApplication(
            ApplicationOutcome.rejected, draft, sanitized_reason="plan_draft_mismatch"
        )
    transaction = _TRANSACTIONS.get(plan.profile_id)
    if transaction is None:
        return ProfileApplication(
            ApplicationOutcome.not_applied,
            draft,
            sanitized_reason="profile_not_enabled",
        )

    payload = draft.model_dump(mode="json", warnings="none")
    try:
        built = transaction(payload, authority or TransactionAuthority())
    except Exception as exc:
        return ProfileApplication(
            ApplicationOutcome.rejected, draft, sanitized_reason=type(exc).__name__
        )
    if built is None:
        return ProfileApplication(
            ApplicationOutcome.rejected,
            draft,
            plan.profile_id,
            sanitized_reason="profile_shape_not_closable",
        )

    closed_payload, created, rebound = built
    try:
        closed = MechanicsProblemDraftV1.model_validate(closed_payload)
    except Exception as exc:
        # The transaction is abandoned whole.  The caller still holds the exact
        # Draft it passed in; no record from the attempt survives anywhere.
        return ProfileApplication(
            ApplicationOutcome.rejected,
            draft,
            plan.profile_id,
            sanitized_reason=type(exc).__name__,
        )
    return ProfileApplication(
        ApplicationOutcome.applied,
        closed,
        plan.profile_id,
        created_record_ids=created,
        rebound_quantity_ids=rebound,
    )


# The authoritative statement of which profiles have a built transaction.
# An unbuilt profile can be *measured* by the census, but it cannot be
# applied, and any instrument reporting on it must say "not implemented"
# rather than crediting a zero it never earned.
IMPLEMENTED_PROFILE_IDS: frozenset[ProfileId] = frozenset(_TRANSACTIONS)


def profile_has_transaction(profile_id: ProfileId) -> bool:
    """True when this profile's transaction is actually built."""

    return profile_id in _TRANSACTIONS


def apply_selected_profile(
    draft: MechanicsProblemDraftV1,
    profile_id: ProfileId,
    *,
    approved_assumption_ids: tuple[str, ...] = (),
    authorized_assumptions: Mapping[str, AssumptionAuthorization] | None = None,
) -> ProfileApplication:
    """Plan and apply exactly one selected profile against the pristine Draft.

    The isolation instrument's primitive: no declaration-order walk, no
    first-wins, no reuse of another profile's outcome.  The plan is computed
    by `plan_complete_profile` — which resolves the profile by identity and
    never reads the declaration table — and the application is the same
    all-or-nothing `apply_complete_profile` the closure uses, spending the
    same issued authority and never minting one.
    """

    from evaluation.phase56_stage7.complete_profile import plan_complete_profile

    authority = TransactionAuthority(
        approved_assumption_ids=frozenset(approved_assumption_ids),
        authorized_assumptions=(
            MappingProxyType(dict(authorized_assumptions))
            if authorized_assumptions is not None
            else MappingProxyType({})
        ),
    )
    plan = plan_complete_profile(
        profile_id, draft, approved_assumption_ids=approved_assumption_ids
    )
    if plan.disposition is PlanDisposition.not_applicable:
        return ProfileApplication(
            ApplicationOutcome.not_applied,
            draft,
            profile_id,
            sanitized_reason="profile_not_applicable",
        )
    return apply_complete_profile(plan, draft, authority)


def close_projected_draft(
    draft: MechanicsProblemDraftV1,
    *,
    approved_assumption_ids: tuple[str, ...] = (),
    authorized_assumptions: Mapping[str, AssumptionAuthorization] | None = None,
) -> ProfileApplication:
    """Plan every profile and apply at most one authorised transaction.

    Bounded and deterministic: profiles are considered in their declared order
    and the first authorised transaction wins, so one Draft is closed by exactly
    one profile or by none.  Planning happens first and in full, so no
    transaction ever runs against a Draft another transaction has already
    touched.

    `authorized_assumptions` is the Lane B authority bundle's own immutable
    map, passed through for transactions to consume.  Closure can spend that
    authority; it can never create it.
    """

    from evaluation.phase56_stage7.complete_profile import plan_every_profile

    authority = TransactionAuthority(
        approved_assumption_ids=frozenset(approved_assumption_ids),
        authorized_assumptions=(
            MappingProxyType(dict(authorized_assumptions))
            if authorized_assumptions is not None
            else MappingProxyType({})
        ),
    )
    for plan in plan_every_profile(
        draft, approved_assumption_ids=approved_assumption_ids
    ):
        if plan.disposition is PlanDisposition.not_applicable:
            continue
        result = apply_complete_profile(plan, draft, authority)
        if result.applied:
            return result
    return ProfileApplication(
        ApplicationOutcome.not_applied, draft, sanitized_reason="no_profile_authorised"
    )


__all__ = [
    "COMPLETE_PROFILE_APPLICATION_VERSION",
    "DERIVED_FRAME_ID",
    "MOTION_AXIS_FRAME_ID",
    "ENERGY_SPEED_FRAME_ID",
    "DIRECT_WORK_ASSUMPTION_ID",
    "DIRECT_WORK_FRAME_ID",
    "DIRECT_WORK_INTERACTION_ID",
    "POLAR_COORDINATE_ENTITY_ID",
    "POLAR_FRAME_ID",
    "POLAR_RADIUS_RELATION_ID",
    "RIGID_AXIS_POINT_ID",
    "TWO_POINT_SPEED_KNOWN_POINT_ID",
    "TWO_POINT_SPEED_QUERY_POINT_ID",
    "TWO_POINT_SPEED_OMEGA_QUANTITY_ID",
    "TWO_POINT_SPEED_OMEGA_SYMBOL_ID",
    "RESULTANT_FORCE_FRAME_ID",
    "RESULTANT_FORCE_INTERACTION_ID",
    "VERTICAL_CIRCLE_GRAVITY_QUANTITY_ID",
    "VERTICAL_CIRCLE_GRAVITY_SYMBOL_ID",
    "ROLLING_GRAVITY_QUANTITY_ID",
    "ROLLING_GRAVITY_SYMBOL_ID",
    "TABLE_PULLEY_WORLD_ID",
    "TABLE_PULLEY_WORLD_FRAME_ID",
    "TABLE_PULLEY_SUPPORT_FRAME_ID",
    "TABLE_PULLEY_ORIENTATION_RELATION_ID",
    "TABLE_PULLEY_CONTACT_POINT_ID",
    "TABLE_PULLEY_GRAVITY_ID",
    "TABLE_PULLEY_GRAVITY_SYMBOL_ID",
    "INCLINE_SLIDING_WORLD_ID",
    "INCLINE_SLIDING_WORLD_FRAME_ID",
    "INCLINE_SLIDING_SLOPE_FRAME_ID",
    "INCLINE_SLIDING_CONTACT_POINT_ID",
    "INCLINE_SLIDING_GRAVITY_ID",
    "INCLINE_SLIDING_GRAVITY_SYMBOL_ID",
    "GRAVITY_INTERACTION_ID",
    "GRAVITY_QUANTITY_ID",
    "GRAVITY_SYMBOL_ID",
    "VERTICAL_ACCELERATION_QUANTITY_ID",
    "VERTICAL_ACCELERATION_SYMBOL_ID",
    "close_projected_draft",
    "IMPLEMENTED_PROFILE_IDS",
    "OBSERVER_FRAME_ID",
    "ROTATING_FRAME_ID",
    "ROTATING_WORLD_FRAME_ID",
    "ROTATION_POINT_ID",
    "SLOT_PIN_FRAME_ID",
    "WORLD_FRAME_ID",
    "ApplicationOutcome",
    "ProfileApplication",
    "TransactionAuthority",
    "apply_complete_profile",
    "apply_selected_profile",
    "profile_has_transaction",
]
