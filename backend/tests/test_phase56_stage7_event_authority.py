"""Event semantic authority: a typed kind alone licenses no numeric equation.

A corpus (or modeler) that types an event ``highest_point`` has made an
interpretation.  The interpretation is allowed — what is not allowed is the
interpretation acting as runtime equation authority on its label alone.  A
numeric-licensing event kind (``highest_point``, ``lowest_point``,
``turnaround``, ``comes_to_rest``) must carry its own source evidence: the
event's ``evidence_quote`` resolved to an exact, unique span of the problem
text, recorded as a ``source_evidence`` entry, and linked through
``Event.evidence_refs``.  Missing, unresolvable, or ambiguous evidence fails
closed — the event itself is preserved, but no v = 0 law may consume it.

No raw-text keyword or regex routing participates anywhere: quote resolution
is exact string occurrence of the modeler's own stated quote, the same grammar
the fact path already uses.

Every fixture is independently authored.  None reads a case ID, family, split,
expected terminal, or expected answer in any path under test.
"""

from __future__ import annotations

import pytest

import test_phase56_stage7_event_boundary_semantics as semantics
from test_phase56_stage7_event_boundary_semantics import (
    PROBLEM_TEXT,
    _closed_draft,
    _emissions,
    _law_ids,
    _projection,
    _record,
)

from engine.mechanics.contracts import EventKind
from evaluation.phase56_stage7 import event_boundary_derivation
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.event_boundary_derivation import (
    EventBoundaryOutcome,
    derive_event_boundaries,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    project_case_to_draft,
)

BOUNDARY_LAW_IDS = frozenset(
    {
        "event_vertical_extremum_velocity",
        "event_turnaround_axis_velocity",
        "event_comes_to_rest_velocity",
    }
)


def _events(*, top_kind: str, top_quote: str | None) -> list[dict]:
    return [
        {
            "role": "go",
            "kind": "release",
            "subject_roles": ["stone"],
            "segment_role": "fall",
            "evidence_quote": None,
        },
        {
            "role": "top",
            "kind": top_kind,
            "subject_roles": ["stone"],
            "segment_role": "fall",
            "evidence_quote": top_quote,
        },
    ]


def _authority_projection(*, top_kind: str = "highest_point", top_quote):
    return _projection(events=_events(top_kind=top_kind, top_quote=top_quote))


def _boundary_emissions(projection, draft):
    return tuple(
        emission
        for emission in _emissions(projection, draft)
        if emission.rule.law_id in BOUNDARY_LAW_IDS
    )


# --------------------------------------------------------------------------
# Fail-closed: an unproven licensing event is preserved but licenses nothing
# --------------------------------------------------------------------------


def test_a_licensing_event_without_an_evidence_quote_licenses_nothing():
    projection = _authority_projection(top_quote=None)
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert top.kind is EventKind.highest_point
    assert top.evidence_refs == []
    assert ("top", "missing_quote") in projection.event_authority_gaps

    derivation = derive_event_boundaries(projection.draft)
    assert derivation.outcome is EventBoundaryOutcome.not_applied
    assert derivation.created_quantity_ids == ()

    _, draft = _closed_draft(projection)
    derived = derive_event_boundaries(draft)
    assert derived.outcome is EventBoundaryOutcome.not_applied
    assert not _boundary_emissions(projection, derived.draft)


def test_an_event_quote_absent_from_the_source_licenses_nothing():
    projection = _authority_projection(top_quote="이 인용문은 본문 어디에도 없다")
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert top.evidence_refs == []
    assert ("top", "quote_not_found") in projection.event_authority_gaps

    _, draft = _closed_draft(projection)
    derived = derive_event_boundaries(draft)
    assert derived.outcome is EventBoundaryOutcome.not_applied
    assert not _boundary_emissions(projection, derived.draft)


def test_an_ambiguous_event_quote_licenses_nothing():
    # `처음` occurs twice in the problem text; no occurrence index exists for
    # event quotes, so no span may be chosen.
    assert PROBLEM_TEXT.count("처음") == 2
    projection = _authority_projection(top_quote="처음")
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert top.evidence_refs == []
    assert ("top", "quote_ambiguous") in projection.event_authority_gaps

    _, draft = _closed_draft(projection)
    derived = derive_event_boundaries(draft)
    assert derived.outcome is EventBoundaryOutcome.not_applied
    assert not _boundary_emissions(projection, derived.draft)


# --------------------------------------------------------------------------
# Positive control: proven authority licenses the zero and stays traceable
# --------------------------------------------------------------------------


def test_a_proven_event_quote_licenses_the_zero_and_binds_the_evidence():
    quote = "최고점에 도달"
    assert PROBLEM_TEXT.count(quote) == 1
    projection = _authority_projection(top_quote=quote)
    assert projection.event_authority_gaps == ()

    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert len(top.evidence_refs) == 1
    (evidence_id,) = top.evidence_refs
    (record,) = [
        item
        for item in projection.draft.source_evidence
        if item.evidence_id == evidence_id
    ]
    assert record.kind == "text"
    assert record.quote == quote
    start, end = record.source_span.start, record.source_span.end
    assert PROBLEM_TEXT[start:end] == quote

    _, draft = _closed_draft(projection)
    derived = derive_event_boundaries(draft)
    assert derived.outcome is EventBoundaryOutcome.applied

    emissions = _boundary_emissions(projection, derived.draft)
    assert emissions
    for emission in emissions:
        assert evidence_id in emission.source_evidence_ids


def test_a_non_licensing_event_needs_no_quote_and_mints_no_evidence():
    projection = _authority_projection(top_quote="최고점에 도달")
    (go,) = [e for e in projection.draft.events if e.event_id == "go"]
    assert go.evidence_refs == []
    assert all(gap[0] != "go" for gap in projection.event_authority_gaps)


# --------------------------------------------------------------------------
# The kind-swap attack is visible and every licence stays traceable
# --------------------------------------------------------------------------


def test_gold_kind_swap_changes_the_emission_and_stays_traceable():
    quote = "최고점에 도달"
    baseline = _authority_projection(top_kind="highest_point", top_quote=quote)
    swapped = _authority_projection(top_kind="comes_to_rest", top_quote=quote)

    _, baseline_draft = _closed_draft(baseline)
    _, swapped_draft = _closed_draft(swapped)
    baseline_laws = _law_ids(
        baseline, derive_event_boundaries(baseline_draft).draft
    ) & BOUNDARY_LAW_IDS
    swapped_laws = _law_ids(
        swapped, derive_event_boundaries(swapped_draft).draft
    ) & BOUNDARY_LAW_IDS

    # The corrupted label is not silently equivalent: the emitted law set
    # changes with the kind.
    assert baseline_laws != swapped_laws

    # And whichever equation each variant emits, its licence is traceable to
    # the event's own evidence record — never an unevidenced label.
    for projection, draft in ((baseline, baseline_draft), (swapped, swapped_draft)):
        (top,) = [e for e in projection.draft.events if e.event_id == "top"]
        derived = derive_event_boundaries(draft)
        for emission in _boundary_emissions(projection, derived.draft):
            assert set(top.evidence_refs) & set(emission.source_evidence_ids)


# --------------------------------------------------------------------------
# Evidence never substitutes for structural walls
# --------------------------------------------------------------------------


def test_proven_evidence_never_promotes_an_internal_event_to_a_boundary():
    quote = "최고점에 도달"
    record = _record(events=_events(top_kind="highest_point", top_quote=quote))
    # `top` stops being the interval's declared end boundary: the event is now
    # segment-internal, and its perfectly proven evidence must not promote it.
    record["gold"]["motion_segments"] = [
        {
            "role": "fall",
            "order": 1,
            "actor_roles": ["stone"],
            "motion_model": "projectile_free_flight",
            "relevance": "target",
            "start_event_role": "go",
            "end_event_role": None,
        }
    ]
    projection = project_case_to_draft(PublicCorpusCaseV1(**record))
    assert projection.projected, projection.sanitized_reason
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert top.evidence_refs, "authority exists — the wall under test is boundary structure"
    assert top.interval_ids == []

    # No closure is needed for this wall: with or without a profile, the
    # segment-internal event must never be promoted, evidence or not.
    derived = derive_event_boundaries(projection.draft)
    assert derived.outcome is EventBoundaryOutcome.not_applied
    assert not _boundary_emissions(projection, derived.draft)


# --------------------------------------------------------------------------
# Identity, order, and answer tampering never change event authority
# --------------------------------------------------------------------------


def test_event_evidence_is_order_invariant():
    quote = "최고점에 도달"
    forward = _authority_projection(top_quote=quote)
    reversed_events = list(reversed(_events(top_kind="highest_point", top_quote=quote)))
    backward = _projection(events=reversed_events)

    assert forward.draft.source_evidence == backward.draft.source_evidence
    forward_refs = {e.event_id: list(e.evidence_refs) for e in forward.draft.events}
    backward_refs = {e.event_id: list(e.evidence_refs) for e in backward.draft.events}
    assert forward_refs == backward_refs
    assert forward_refs["top"], "evidence must exist for the invariance to be meaningful"


def test_answer_and_identity_tampering_never_change_event_authority():
    quote = "최고점에 도달"
    baseline_record = _record(events=_events(top_kind="highest_point", top_quote=quote))
    tampered_record = _record(events=_events(top_kind="highest_point", top_quote=quote))
    tampered_record["case_id"] = "renamed_case_identity"
    tampered_record["family"] = "renamed_family"
    tampered_record["tags"] = ["renamed"]
    tampered_record["gold"]["answers"] = []

    baseline = project_case_to_draft(PublicCorpusCaseV1(**baseline_record))
    tampered = project_case_to_draft(PublicCorpusCaseV1(**tampered_record))
    assert baseline.projected and tampered.projected
    assert (
        baseline.draft.model_dump_json() == tampered.draft.model_dump_json()
    )
    (top,) = [e for e in baseline.draft.events if e.event_id == "top"]
    assert top.evidence_refs, "authority must exist for the invariance to be meaningful"


# --------------------------------------------------------------------------
# The engine and the derivation share one eligibility contract
# --------------------------------------------------------------------------


def test_the_eligibility_tables_are_shared_single_sources():
    from engine.mechanics.laws import core as laws_core
    from engine.mechanics.laws import event_boundary as shared

    assert (
        event_boundary_derivation._VERTICAL_EXTREMUM_EVENT_KINDS
        is shared.VERTICAL_EXTREMUM_EVENT_KINDS
    )
    assert (
        event_boundary_derivation._IMPULSIVE_EVENT_KINDS
        is shared.IMPULSIVE_EVENT_KINDS
    )
    assert (
        event_boundary_derivation._EXTREMUM_SMOOTH_INTERACTION_KINDS
        is shared.EXTREMUM_SMOOTH_INTERACTION_KINDS
    )
    assert (
        event_boundary_derivation._TURNAROUND_SMOOTH_INTERACTION_KINDS
        is shared.TURNAROUND_SMOOTH_INTERACTION_KINDS
    )
    assert laws_core._VERTICAL_EXTREMUM_EVENT_KINDS is shared.VERTICAL_EXTREMUM_EVENT_KINDS
    assert laws_core._IMPULSIVE_EVENT_KINDS is shared.IMPULSIVE_EVENT_KINDS
    assert (
        laws_core._EXTREMUM_SMOOTH_INTERACTION_KINDS
        is shared.EXTREMUM_SMOOTH_INTERACTION_KINDS
    )
    assert (
        laws_core._TURNAROUND_SMOOTH_INTERACTION_KINDS
        is shared.TURNAROUND_SMOOTH_INTERACTION_KINDS
    )
    assert frozenset(c.value for c in laws_core._SIGNED_AXIS_COMPONENT_SET) == (
        shared.SIGNED_AXIS_COMPONENTS
    )
    assert shared.NUMERIC_LICENSING_EVENT_KINDS == frozenset(
        {"highest_point", "lowest_point", "turnaround", "comes_to_rest"}
    )


@pytest.mark.parametrize("top_kind", ["highest_point", "turnaround", "comes_to_rest"])
@pytest.mark.parametrize(
    "top_quote",
    ["최고점에 도달", None],
    ids=["proven", "unproven"],
)
def test_derivation_candidates_match_engine_consumption(top_kind, top_quote):
    """Bounded equivalence: a candidate is created iff the law consumes it.

    The derivation's whole reason to exist is feeding the engine's boundary
    laws.  Over this matrix of licensing kinds and authority states, the
    derivation must create unknowns exactly when the engine law then emits an
    equation about them — a candidate the law refuses is a dead unknown, and
    an emission without a candidate could never have found its quantity.
    """

    projection = _authority_projection(top_kind=top_kind, top_quote=top_quote)
    _, draft = _closed_draft(projection)
    derived = derive_event_boundaries(draft)
    emissions = _boundary_emissions(projection, derived.draft)
    assert bool(derived.created_quantity_ids) == bool(emissions)
