"""Typed direct-impulse closure for the authoritative Lane B path.

The generic impulse profile already owns the transaction that binds source-stated
left/right or up/down directions to one named axis. Its generic catalogue
capability remains conservative because most event-scoped equation graphs are
not static algebraic systems. A directly stated impulse is the bounded
exception: mass, one stated endpoint velocity, one impulse, the opposite
endpoint unknown, and one bounded before/after interval form an exact algebraic
impulse--momentum graph accepted by the engine's exact waiver.

This module does not inspect text, family, case identity, an expected terminal,
or an expected answer. It only upgrades the single capability prerequisite of
that already-complete typed profile, and only inside the Lane B path after a
verified immutable authority bundle has been supplied. The existing transaction
remains all-or-nothing and changes no numerical value.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Callable

from engine.mechanics.validation import AssumptionAuthorization

from evaluation.phase56_stage7.complete_profile import (
    CompleteProfilePlanV1,
    CompleteProfilePrerequisiteV1,
    PlanDisposition,
    PrerequisiteDisposition,
    PrerequisiteKind,
    ProfileId,
    plan_complete_profile,
)
import evaluation.phase56_stage7.complete_profile_application as _application

DIRECT_IMPULSE_PROFILE_VERSION = "phase56-stage7-direct-impulse-profile-v2"
_CAPABILITY_ID = "capability_event_scoped_solve_plan"
_installed = False
_original_close: Callable[..., Any] | None = None
_original_impulse_transaction: Callable[..., Any] | None = None


def plan_direct_impulse_profile(
    draft: Any, *, approved_assumption_ids: tuple[str, ...] = ()
) -> CompleteProfilePlanV1 | None:
    """Return a complete direct-impulse plan, or ``None`` fail-closed.

    Every non-capability prerequisite comes from the existing generic profile:
    bounded interval, mass, velocity, impulse, and a single source-proven signed
    axis. Only the event-scoped solver capability is upgraded, because the
    engine extension recognises exactly this direct algebraic graph (optionally
    plus one evidenced at-rest boundary equation).
    """

    measured = plan_complete_profile(
        ProfileId.impulse_momentum,
        draft,
        approved_assumption_ids=approved_assumption_ids,
    )
    capability = tuple(
        item
        for item in measured.prerequisites
        if item.prerequisite_id == _CAPABILITY_ID
    )
    if (
        measured.profile_id is not ProfileId.impulse_momentum
        or measured.disposition is not PlanDisposition.unsupported
        or len(capability) != 1
        or capability[0].kind is not PrerequisiteKind.capability
        or capability[0].disposition is not PrerequisiteDisposition.unsupported
        or not measured.structurally_complete
    ):
        return None

    prerequisites = tuple(
        CompleteProfilePrerequisiteV1(
            prerequisite_id=item.prerequisite_id,
            kind=item.kind,
            disposition=(
                PrerequisiteDisposition.explicit_source
                if item.prerequisite_id == _CAPABILITY_ID
                else item.disposition
            ),
        )
        for item in measured.prerequisites
    )
    return measured.model_copy(
        update={
            "disposition": PlanDisposition.complete,
            "prerequisites": prerequisites,
        }
    )


def _evidenced_rest_zero_quantity_ids(payload: dict[str, Any]) -> frozenset[str]:
    """The exact zero-velocity quantities a source-grounded rest state owns."""

    out: set[str] = set()
    intervals = {item["interval_id"]: item for item in payload["motion_intervals"]}
    for state in payload["state_conditions"]:
        if (
            state.get("state") != "at_rest"
            or not state.get("evidence_refs")
            or len(state.get("quantity_ids") or ()) != 1
            or state.get("subject_id") is None
            or state.get("interval_id") is None
            or state.get("event_id") is None
        ):
            continue
        interval = intervals.get(state["interval_id"])
        if (
            interval is None
            or state["subject_id"] not in interval["subject_ids"]
            or state["event_id"]
            not in {interval.get("start_event_id"), interval.get("end_event_id")}
        ):
            continue
        out.add(state["quantity_ids"][0])
    return frozenset(out)


def _direct_impulse_transaction(
    payload: dict[str, Any], authority: _application.TransactionAuthority
):
    """Extend the existing transaction only by the zero-vector theorem.

    A source-grounded ``at_rest`` condition states the velocity vector is zero.
    Therefore its scalar component is zero on the single axis independently
    proven by the other source-stated directions.  This is not a direction
    choice and changes no value.  Arbitrary magnitudes, unsupported questions,
    and unevidenced state conditions remain untouched.
    """

    assert _original_impulse_transaction is not None
    built = _original_impulse_transaction(payload, authority)
    if built is None:
        return None
    closed, created, rebound = built
    if not closed["queries"]:
        return None
    target = closed["queries"][0]["target"]
    axis = target.get("component")
    frame_id = target.get("frame_id")
    if axis not in {"x", "y", "z"} or frame_id != _application.DERIVED_FRAME_ID:
        return None

    rest_ids = _evidenced_rest_zero_quantity_ids(closed)
    if not rest_ids:
        return built
    changed: list[str] = []
    quantities: list[dict[str, Any]] = []
    for original in closed["quantities"]:
        quantity = dict(original)
        if quantity["quantity_id"] not in rest_ids:
            quantities.append(quantity)
            continue
        if (
            quantity.get("role") != "velocity"
            or quantity.get("subject_id") != target.get("subject_id")
            or quantity.get("interval_id") != target.get("interval_id")
            or quantity.get("component") != "magnitude"
            or quantity.get("direction") not in (None, {})
            or quantity.get("raw_value") is not None
            or quantity.get("raw_unit") is not None
        ):
            return None
        quantity["component"] = axis
        quantity["frame_id"] = frame_id
        quantities.append(quantity)
        changed.append(quantity["quantity_id"])

    if not changed:
        return built
    rewritten = dict(closed)
    rewritten["quantities"] = quantities
    return rewritten, created, tuple(sorted(set(rebound) | set(changed)))


def _extended_close(
    draft: Any,
    *,
    approved_assumption_ids: tuple[str, ...] = (),
    authorized_assumptions: Mapping[str, AssumptionAuthorization] | None = None,
):
    assert _original_close is not None
    baseline = _original_close(
        draft,
        approved_assumption_ids=approved_assumption_ids,
        authorized_assumptions=authorized_assumptions,
    )
    if baseline.applied or authorized_assumptions is None:
        return baseline

    plan = plan_direct_impulse_profile(
        draft, approved_assumption_ids=approved_assumption_ids
    )
    if plan is None:
        return baseline
    authority = _application.TransactionAuthority(
        approved_assumption_ids=frozenset(approved_assumption_ids),
        authorized_assumptions=MappingProxyType(dict(authorized_assumptions)),
    )
    result = _application.apply_complete_profile(plan, draft, authority)
    return result if result.applied else baseline


def install_direct_impulse_profile() -> None:
    """Install once before Lane B imports the closure function."""

    global _installed, _original_close, _original_impulse_transaction
    if _installed:
        return
    current = _application.close_projected_draft
    if getattr(current, "_direct_impulse_profile_v1", False):
        _installed = True
        return
    if current.__module__ != "evaluation.phase56_stage7.complete_profile_application":
        raise RuntimeError("unexpected complete-profile closure patch order")
    transaction = _application._TRANSACTIONS.get(ProfileId.impulse_momentum)
    if transaction is None:
        raise RuntimeError("impulse-momentum transaction is unavailable")
    _original_close = current
    _original_impulse_transaction = transaction
    _application._TRANSACTIONS[ProfileId.impulse_momentum] = (
        _direct_impulse_transaction
    )
    _extended_close._direct_impulse_profile_v1 = True  # type: ignore[attr-defined]
    _application.close_projected_draft = _extended_close
    _installed = True


__all__ = [
    "DIRECT_IMPULSE_PROFILE_VERSION",
    "install_direct_impulse_profile",
    "plan_direct_impulse_profile",
]
