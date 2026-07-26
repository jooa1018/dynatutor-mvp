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

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from engine.mechanics.contracts import MechanicsProblemDraftV1

from evaluation.phase56_stage7.complete_profile import (
    CompleteProfilePlanV1,
    PlanDisposition,
    ProfileId,
    draft_structure_fingerprint,
)

COMPLETE_PROFILE_APPLICATION_VERSION = (
    "phase56-stage7-complete-profile-application-v1"
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
    payload: dict[str, Any]
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
    component = query["target"].get("component")
    if component in {"x", "y", "z"} and component != axis:
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
        elif direction:
            # An already-bound direction is left exactly as it is.
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
    payload: dict[str, Any]
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
        if quantity["quantity_id"] == target_quantity_id and not direction:
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


# Only a profile whose partial-attachment hazards already have engine-level
# negative controls, or which creates no force at all, may appear here.
# Everything else plans, is measured by the census, and is not built.
_TRANSACTIONS = {
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
) -> ProfileApplication:
    """Apply one complete plan to one Draft, entirely or not at all.

    The plan must be `complete` and must have been computed against *this*
    Draft; a plan from a different Draft is refused rather than re-planned,
    because re-planning here would make the planning phase a mutation.
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
        built = transaction(payload)
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


def close_projected_draft(
    draft: MechanicsProblemDraftV1,
    *,
    approved_assumption_ids: tuple[str, ...] = (),
) -> ProfileApplication:
    """Plan every profile and apply at most one authorised transaction.

    Bounded and deterministic: profiles are considered in their declared order
    and the first authorised transaction wins, so one Draft is closed by exactly
    one profile or by none.  Planning happens first and in full, so no
    transaction ever runs against a Draft another transaction has already
    touched.
    """

    from evaluation.phase56_stage7.complete_profile import plan_every_profile

    for plan in plan_every_profile(
        draft, approved_assumption_ids=approved_assumption_ids
    ):
        if plan.disposition is PlanDisposition.not_applicable:
            continue
        result = apply_complete_profile(plan, draft)
        if result.applied:
            return result
    return ProfileApplication(
        ApplicationOutcome.not_applied, draft, sanitized_reason="no_profile_authorised"
    )


__all__ = [
    "COMPLETE_PROFILE_APPLICATION_VERSION",
    "DERIVED_FRAME_ID",
    "close_projected_draft",
    "OBSERVER_FRAME_ID",
    "WORLD_FRAME_ID",
    "ApplicationOutcome",
    "ProfileApplication",
    "apply_complete_profile",
]
