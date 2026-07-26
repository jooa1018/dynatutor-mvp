"""Elapsed-duration queries: proven by typed structure, never by wording.

A `time` question is an elapsed duration exactly when the typed fields prove
it: the queried segment's interval declares both boundaries, they are
distinct physical events, and the question names either no event or
precisely that interval's own end.  The duration is defined relationally by
the interval's two boundary events — no epoch exists anywhere in the
contract, so no `t0` can be invented — and the rebind changes only the
role, unit, dimension, and event scope of the unknown.  Everything
unprovable declines and keeps the plain `time` binding: a start-event
question, an instant inside the span, a one-sided or degenerate span, a
foreign interval's boundary, and every `period` question.

Every fixture is independently authored.  None reads a case ID, family,
split, expected terminal, or expected answer in any path under test.
"""

from __future__ import annotations

from test_phase56_stage7_event_boundary_semantics import _record

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.lane_b_draft_projection import (
    _ELAPSED_QUERY_KEYS,
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    run_lane_b_case,
)


def _query(**overrides) -> dict:
    query = {
        "role": "q1",
        "output_key": "time",
        "subject_role": "stone",
        "segment_role": "fall",
        "component": "magnitude",
        "event_role": "top",
    }
    query.update(overrides)
    return query


def _project(record: dict):
    projection = project_case_to_draft(PublicCorpusCaseV1(**record))
    assert projection.projected, projection.sanitized_reason
    return projection


def _target(projection):
    (query,) = projection.draft.queries
    return query


# --------------------------------------------------------------------------
# The provable class rebinds to the interval's own duration
# --------------------------------------------------------------------------


def test_a_time_question_at_the_intervals_end_is_its_elapsed_duration():
    projection = _project(_record(queries=[_query(event_role="top")]))
    query = _target(projection)
    assert query.target.role.value == "duration"
    assert query.target.interval_id == "fall"
    assert query.target.event_id is None
    assert query.output_unit == "s"
    (unknown,) = [
        q
        for q in projection.draft.quantities
        if q.quantity_id == query.target.target_quantity_id
    ]
    assert unknown.role.value == "duration"
    assert unknown.interval_id == "fall"
    assert unknown.event_id is None


def test_a_bare_interval_time_question_is_its_elapsed_duration():
    projection = _project(_record(queries=[_query(event_role=None)]))
    query = _target(projection)
    assert query.target.role.value == "duration"
    assert query.target.interval_id == "fall"
    assert query.target.event_id is None


def test_the_rebind_changes_scope_and_role_only():
    projection = _project(_record(queries=[_query(event_role="top")]))
    query = _target(projection)
    (unknown,) = [
        q
        for q in projection.draft.quantities
        if q.quantity_id == query.target.target_quantity_id
    ]
    # The question's own identity survives untouched: subject, component,
    # shape, provenance.  No sign, no direction, no value appears.
    assert unknown.subject_id == "stone"
    assert unknown.component.value == "magnitude"
    assert unknown.shape.value == "scalar"
    assert unknown.provenance.value == "unknown"
    assert unknown.direction is None
    assert unknown.raw_value is None
    assert unknown.evidence_refs == []
    (symbol_id,) = [unknown.symbol_id]
    assert symbol_id in projection.unknown_symbol_ids


# --------------------------------------------------------------------------
# Everything unprovable declines and keeps the plain time binding
# --------------------------------------------------------------------------


def test_a_start_event_time_question_never_invents_an_epoch():
    projection = _project(_record(queries=[_query(event_role="go")]))
    query = _target(projection)
    assert query.target.role.value == "time"
    assert query.target.event_id == "go"
    assert query.target.interval_id == "fall"


def test_a_time_question_with_no_interval_stays_a_plain_time():
    projection = _project(
        _record(queries=[_query(segment_role=None, event_role="top")])
    )
    query = _target(projection)
    assert query.target.role.value == "time"
    assert query.target.interval_id is None
    assert query.target.event_id == "top"


def test_a_one_sided_span_has_no_elapsed_duration():
    record = _record(queries=[_query(event_role="top")])
    record["gold"]["motion_segments"][0]["end_event_role"] = None
    projection = _project(record)
    query = _target(projection)
    assert query.target.role.value == "time"
    # After the occupancy contract the internal instant keeps its interval —
    # as an occurrence, never as a boundary.
    assert query.target.event_id == "top"
    assert query.target.interval_id == "fall"


def test_a_degenerate_span_has_no_elapsed_duration():
    record = _record(queries=[_query(event_role=None)])
    record["gold"]["motion_segments"][0]["end_event_role"] = "go"
    record["gold"]["events"] = [
        event for event in record["gold"]["events"] if event["role"] != "top"
    ]
    projection = _project(record)
    query = _target(projection)
    assert query.target.role.value == "time"


def test_another_intervals_end_event_earns_no_duration_here():
    record = _record(queries=[_query(event_role="stop2")])
    gold = record["gold"]
    gold["motion_segments"] = gold["motion_segments"] + [
        {
            "role": "roll",
            "order": 2,
            "actor_roles": ["stone"],
            "motion_model": "constant_acceleration_1d",
            "relevance": "context",
            "start_event_role": "top",
            "end_event_role": "stop2",
        }
    ]
    gold["events"] = gold["events"] + [
        {
            "role": "stop2",
            "kind": "finish",
            "subject_roles": ["stone"],
            "segment_role": "roll",
            "evidence_quote": None,
        }
    ]
    projection = _project(record)
    query = _target(projection)
    assert query.target.role.value == "time"
    assert query.target.interval_id is None
    assert query.target.event_id == "stop2"


def test_an_interior_instant_time_question_stays_an_instant():
    record = _record(queries=[_query(event_role="top")])
    gold = record["gold"]
    gold["motion_segments"][0]["end_event_role"] = "land"
    gold["events"] = gold["events"] + [
        {
            "role": "land",
            "kind": "finish",
            "subject_roles": ["stone"],
            "segment_role": "fall",
            "evidence_quote": None,
        }
    ]
    projection = _project(record)
    query = _target(projection)
    assert query.target.role.value == "time"
    assert query.target.event_id == "top"
    assert query.target.interval_id == "fall"


def test_the_elapsed_query_vocabulary_is_exactly_time():
    assert set(_ELAPSED_QUERY_KEYS) == {"time"}


# --------------------------------------------------------------------------
# No silent solve, and identity never routes the binding
# --------------------------------------------------------------------------


def test_the_rebound_question_still_terminates_typed_and_answerless():
    """The rebind connects the question to the equations and nothing more.

    With the duration binding the graph now closes — the apex zero, the
    constant-acceleration velocity law, and the gravity binding meet the
    query symbol — but the solver's static-boundary waiver vocabulary does
    not yet cover the extremum-endpoint shape, so the lane terminates at a
    typed `solve_rejected` with no answer, no exception, and no silent
    solve.  Closing that waiver is a separately recorded engine-contract
    decision, not a side effect this package is allowed to smuggle in.
    """

    projection = _project(_record(queries=[_query(event_role="top")]))
    result = run_lane_b_case(projection, execution_token="e" * 32)
    assert result.terminal in {
        LaneBTerminal.compiler_failure,
        LaneBTerminal.compiler_unsupported,
        LaneBTerminal.needs_confirmation,
        LaneBTerminal.solve_rejected,
    }
    assert result.stage_exception is None
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


def test_gold_tampering_never_changes_the_duration_binding():
    baseline_record = _record(queries=[_query(event_role="top")])
    tampered_record = _record(queries=[_query(event_role="top")])
    tampered_record["case_id"] = "renamed_identity"
    tampered_record["family"] = "renamed_family"
    tampered_record["gold"]["answers"] = []
    baseline = _project(baseline_record)
    tampered = _project(tampered_record)
    assert (
        baseline.draft.model_dump_json() == tampered.draft.model_dump_json()
    )
    assert _target(baseline).target.role.value == "duration"
