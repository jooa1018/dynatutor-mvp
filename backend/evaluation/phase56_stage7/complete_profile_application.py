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
WORLD_FRAME_ID = "frm_closure_world"
OBSERVER_FRAME_ID = "frm_closure_observer"

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
    ProfileId.free_flight_gravity: _free_flight_gravity_transaction,
    ProfileId.impulse_momentum: _impulse_momentum_transaction,
    ProfileId.relative_translating_frame: _relative_translating_frame_transaction,
}
# A profile whose only unmet prerequisite is a declared engine capability may be
# built even though its plan is `unsupported`: the structure it creates cannot
# produce an answer, it can only turn an undifferentiated underdetermined graph
# into the precise refusal the engine already knows how to make.
_DEFERRAL_ONLY_PROFILES: frozenset[ProfileId] = frozenset(
    {ProfileId.relative_translating_frame}
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
    "GRAVITY_INTERACTION_ID",
    "GRAVITY_QUANTITY_ID",
    "GRAVITY_SYMBOL_ID",
    "VERTICAL_ACCELERATION_QUANTITY_ID",
    "VERTICAL_ACCELERATION_SYMBOL_ID",
    "close_projected_draft",
    "IMPLEMENTED_PROFILE_IDS",
    "OBSERVER_FRAME_ID",
    "WORLD_FRAME_ID",
    "ApplicationOutcome",
    "ProfileApplication",
    "TransactionAuthority",
    "apply_complete_profile",
    "apply_selected_profile",
    "profile_has_transaction",
]
