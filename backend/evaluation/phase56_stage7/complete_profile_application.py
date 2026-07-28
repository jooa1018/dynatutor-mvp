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

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from engine.mechanics.contracts import MechanicsProblemDraftV1
from engine.mechanics.validation import AssumptionAuthorization

from evaluation.phase56_stage7.complete_profile import (
    CompleteProfilePlanV1,
    PlanDisposition,
    ProfileId,
    draft_structure_fingerprint,
)

COMPLETE_PROFILE_APPLICATION_VERSION = (
    "phase56-stage7-complete-profile-application-v3"
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
WORLD_FRAME_ID = "frm_closure_world"
OBSERVER_FRAME_ID = "frm_closure_observer"
SLOT_PIN_FRAME_ID = "frm_closure_slot_radial"
ROTATING_WORLD_FRAME_ID = "frm_closure_coriolis_world"
ROTATING_FRAME_ID = "frm_closure_coriolis_rotating"
ROTATION_POINT_ID = "pt_closure_coriolis_pivot"

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


# Only a profile whose partial-attachment hazards already have engine-level
# negative controls, or which creates no force at all, may appear here.
# Everything else plans, is measured by the census, and is not built.
_TRANSACTIONS = {
    ProfileId.signed_constant_acceleration_1d: (
        _signed_constant_acceleration_1d_transaction
    ),
    ProfileId.free_flight_gravity: _free_flight_gravity_transaction,
    ProfileId.impulse_momentum: _impulse_momentum_transaction,
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
