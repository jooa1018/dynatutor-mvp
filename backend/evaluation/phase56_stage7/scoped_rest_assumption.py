"""Scope rest assumptions to the exact boundary they describe.

A source can state an initial velocity and independently state that the same
body is at rest at the interval's final boundary.  Those are different physical
states.  The baseline projection used a subject/role-only competition check, so
any explicit velocity suppressed either rest boundary even when the events were
distinct.

This evaluator-only adapter narrows that competition to typed scope.  It reads
only the source-grounded motion segment, explicit fact, and assumption fields
already permitted to the projection.  A same-boundary or unscoped explicit
velocity still wins and keeps the assumption rejected; another boundary does
not.  No case identity, family, expected terminal, expected answer, or raw-text
routing participates.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable

import evaluation.phase56_stage7.lane_b_draft_projection as _projection


SCOPED_REST_ASSUMPTION_VERSION = "phase56-stage7-scoped-rest-assumption-v1"


@dataclass(frozen=True, slots=True)
class _ExplicitScope:
    subject_id: str
    role: str
    interval_id: str | None
    event_id: str | None


@dataclass(frozen=True, slots=True)
class _ProjectionScope:
    default_subject_id: str
    intervals: dict[str, dict[str, Any]]
    explicit: tuple[_ExplicitScope, ...]


_scope: ContextVar[_ProjectionScope | None] = ContextVar(
    "phase56_stage7_scoped_rest_assumption", default=None
)
_installed = False
_original_build_payload: Callable[..., Any] | None = None
_original_authorize_assumption: Callable[..., tuple[str, str]] | None = None


def _fact_scope(fact: Any, intervals: dict[str, dict[str, Any]]) -> _ExplicitScope | None:
    mapped = _projection._FACT_ROLES.get(fact.semantic_key)
    if mapped is None:
        return None
    role = mapped[0]
    elapsed = _projection._ELAPSED_ROLES.get(fact.semantic_key)
    if (
        elapsed is not None
        and fact.event_role is None
        and fact.segment_role is not None
        and (fact.temporal_role or "") in _projection._INTERVAL_TEMPORAL_ROLES
    ):
        role = elapsed[0]
    event_id = _projection._stated_endpoint(
        _projection._ENDPOINT_TEMPORAL_ROLES.get(fact.temporal_role or ""),
        fact.segment_role,
        fact.event_role,
        intervals,
    )
    return _ExplicitScope(
        subject_id=fact.subject_role,
        role=role,
        interval_id=fact.segment_role,
        event_id=event_id,
    )


def _scoped_build_payload(gold: Any, problem_text: str):
    assert _original_build_payload is not None
    intervals = {
        segment.role: {
            "start_event_id": segment.start_event_role,
            "end_event_id": segment.end_event_role,
        }
        for segment in gold.motion_segments
    }
    explicit = tuple(
        scope
        for fact in gold.explicit_facts
        for scope in (_fact_scope(fact, intervals),)
        if scope is not None
    )
    default_subject = gold.entities[0].role if gold.entities else ""
    token = _scope.set(
        _ProjectionScope(
            default_subject_id=default_subject,
            intervals=intervals,
            explicit=explicit,
        )
    )
    try:
        return _original_build_payload(gold, problem_text)
    finally:
        _scope.reset(token)


def _scoped_authorize_assumption(
    *,
    assumption: Any,
    problem_text: str,
    proposal: tuple[str, str, str] | None,
    explicit_roles: Any,
) -> tuple[str, str]:
    assert _original_authorize_assumption is not None
    baseline = _original_authorize_assumption(
        assumption=assumption,
        problem_text=problem_text,
        proposal=proposal,
        explicit_roles=explicit_roles,
    )
    if (
        baseline[0] != "rejected"
        or assumption.kind not in _projection._REST_STATE_CONDITIONS
        or proposal is None
    ):
        return baseline

    context = _scope.get()
    if context is None:
        return baseline
    subject_id = assumption.subject_role or context.default_subject_id
    interval_id = assumption.segment_role
    interval = context.intervals.get(interval_id or "")
    if not subject_id or interval_id is None or interval is None:
        return baseline
    _state_kind, boundary_field = _projection._REST_STATE_CONDITIONS[assumption.kind]
    boundary_event = interval.get(boundary_field)
    if boundary_event is None:
        return baseline

    # Approval must still have one exact source span.  This is the same evidence
    # resolver the projection uses when it creates the state condition.
    if _projection._locate_quote(problem_text, assumption.supporting_quote) is None:
        return baseline

    role = proposal[0]
    for fact in context.explicit:
        if fact.subject_id != subject_id or fact.role != role:
            continue
        if fact.interval_id not in {None, interval_id}:
            continue
        # A value at the same boundary, or an unscoped value that could govern
        # every instant, competes.  A value tied to the opposite boundary does
        # not describe this state and therefore cannot suppress it.
        if fact.event_id in {None, boundary_event}:
            return baseline

    return ("approved", baseline[1])


def install_scoped_rest_assumption_policy() -> None:
    """Install the source-scope refinement once, before any projection runs."""

    global _installed, _original_build_payload, _original_authorize_assumption
    if _installed:
        return
    current_build = _projection._build_payload
    current_authorize = _projection._authorize_assumption
    if getattr(current_build, "_scoped_rest_assumption_v1", False):
        _installed = True
        return
    _original_build_payload = current_build
    _original_authorize_assumption = current_authorize
    _scoped_build_payload._scoped_rest_assumption_v1 = True  # type: ignore[attr-defined]
    _scoped_authorize_assumption._scoped_rest_assumption_v1 = True  # type: ignore[attr-defined]
    _projection._build_payload = _scoped_build_payload
    _projection._authorize_assumption = _scoped_authorize_assumption
    _installed = True


__all__ = [
    "SCOPED_REST_ASSUMPTION_VERSION",
    "install_scoped_rest_assumption_policy",
]
