"""Stage 7 Lane B: direct corpus-structure to Draft projection invariants.

The projection reads only source-grounded corpus structure and emits a Draft
for the product pipeline.  These tests pin the gold whitelist, the two
preserved corpus structures, evidence exactness, and every fail-closed
rejection the projection owes.
"""

from __future__ import annotations

import pytest

from engine.mechanics.validation import validate_draft
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import (
    FORBIDDEN_MEMBERS,
    PERMITTED_CASE_MEMBERS,
    PERMITTED_GOLD_MEMBERS,
    DraftProjectionReason,
    DraftProjectionTerminal,
    project_case_to_draft,
)
from support.phase56_stage7_corpus_fixtures import build_case


def _case(**overrides) -> PublicCorpusCaseV1:
    record = build_case(
        index=3,
        split="public_dev",
        family="single_particle_newton",
        future_terminal="accepted",
        with_answer=True,
    )
    record["split"] = PublicSplit.public_dev
    record.update(overrides)
    return PublicCorpusCaseV1(**record)


def _with_gold(case: PublicCorpusCaseV1, **gold_updates) -> PublicCorpusCaseV1:
    return case.model_copy(update={"gold": case.gold.model_copy(update=gold_updates)})


def _project(case: PublicCorpusCaseV1):
    return project_case_to_draft(case)


# --------------------------------------------------------------------------
# Whitelist and end-to-end validity
# --------------------------------------------------------------------------


def test_permitted_and_forbidden_members_are_disjoint() -> None:
    assert PERMITTED_CASE_MEMBERS & FORBIDDEN_MEMBERS == frozenset()
    assert PERMITTED_GOLD_MEMBERS & FORBIDDEN_MEMBERS == frozenset()
    for forbidden in (
        "case_id",
        "family",
        "split",
        "chapter",
        "expected_system_type",
        "future_expected_terminal",
        "answers",
        "expected_failure_codes",
    ):
        assert forbidden in FORBIDDEN_MEMBERS


def test_projected_draft_is_accepted_by_the_product_validator() -> None:
    projection = _project(_case())
    assert projection.terminal is DraftProjectionTerminal.projected
    result = validate_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert result.accepted, [
        (getattr(issue.code, "value", issue.code), issue.path) for issue in result.issues
    ]


def test_projection_is_deterministic() -> None:
    first = _project(_case())
    second = _project(_case())
    assert first.draft == second.draft


# --------------------------------------------------------------------------
# Tampering invariance
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("case_id", "zzz_other_9999"),
        ("family", "spring_mass_vibration"),
        ("split", PublicSplit.public_adversarial),
        ("difficulty", 5),
        ("tags", ("routing-bait",)),
    ),
)
def test_case_level_tampering_never_changes_the_draft(field: str, value: object) -> None:
    baseline = _project(_case()).draft
    assert _project(_case(**{field: value})).draft == baseline


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("expected_system_type", "slot_pin_relative_motion"),
        ("future_expected_terminal", "needs_confirmation"),
        ("phase55_expected_terminal", "accepted"),
        ("parse_status", "unsupported"),
        ("answers", ()),
        ("expected_failure_codes", ("bait",)),
    ),
)
def test_gold_label_tampering_never_changes_the_draft(field: str, value: object) -> None:
    case = _case()
    baseline = _project(case).draft
    assert _project(_with_gold(case, **{field: value})).draft == baseline


def test_entity_and_fact_order_does_not_change_the_draft_content() -> None:
    case = _case()
    baseline = _project(case).draft
    reordered = _with_gold(
        case,
        entities=tuple(reversed(case.gold.entities)),
        explicit_facts=tuple(reversed(case.gold.explicit_facts)),
    )
    projected = _project(reordered).draft
    assert {item.entity_id for item in projected.entities} == {
        item.entity_id for item in baseline.entities
    }
    assert {item.quantity_id for item in projected.quantities} == {
        item.quantity_id for item in baseline.quantities
    }
    assert {
        (item.quantity_id, item.subject_id, item.raw_value, item.raw_unit)
        for item in projected.quantities
    } == {
        (item.quantity_id, item.subject_id, item.raw_value, item.raw_unit)
        for item in baseline.quantities
    }


# --------------------------------------------------------------------------
# Blocker A — segment-internal event
# --------------------------------------------------------------------------


def _with_segment_internal_event(case: PublicCorpusCaseV1) -> PublicCorpusCaseV1:
    events = case.gold.events + (
        case.gold.events[0].model_copy(
            update={"role": "instant", "kind": "reaches_position"}
        ),
    )
    query = case.gold.queries[0].model_copy(update={"event_role": "instant"})
    return _with_gold(case, events=events, queries=(query,))


def test_blocker_a_event_keeps_interval_membership_without_faking_a_boundary() -> None:
    projection = _project(_with_segment_internal_event(_case()))
    assert projection.terminal is DraftProjectionTerminal.projected
    draft = projection.draft
    interval = draft.motion_intervals[0]
    mid = next(event for event in draft.events if event.event_id == "instant")
    assert interval.interval_id in mid.interval_ids
    assert interval.start_event_id != "instant"
    assert interval.end_event_id != "instant"
    assert "instant" in projection.segment_internal_event_ids
    target = draft.queries[0].target
    assert target.interval_id == interval.interval_id
    assert target.event_id == "instant"
    assert target.subject_id == "box"


def test_blocker_a_dangling_query_event_is_rejected() -> None:
    case = _case()
    broken = _with_gold(
        case, queries=(case.gold.queries[0].model_copy(update={"event_role": "ghost"}),)
    )
    projection = _project(broken)
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.dangling_event_reference.value
    )


# --------------------------------------------------------------------------
# Blocker B — relation-scoped timeless environment fact
# --------------------------------------------------------------------------


def _with_environment_fact(case: PublicCorpusCaseV1) -> PublicCorpusCaseV1:
    """Attach the friction coefficient to the surface, not to the moving box."""

    quote = case.gold.explicit_facts[0].evidence_quote
    environment_fact = case.gold.explicit_facts[0].model_copy(
        update={
            "role": "mu",
            "semantic_key": "coefficient_of_friction",
            "subject_role": "surface",
            "segment_role": "motion_1",
            "raw_unit": "",
            "raw_value": case.gold.explicit_facts[0].raw_value,
            "evidence_quote": quote,
        }
    )
    return _with_gold(case, explicit_facts=case.gold.explicit_facts + (environment_fact,))


def test_blocker_b_environment_entity_is_never_promoted_to_an_interval_subject() -> None:
    projection = _project(_with_environment_fact(_case()))
    assert projection.terminal is DraftProjectionTerminal.projected
    draft = projection.draft
    interval = draft.motion_intervals[0]
    assert "surface" not in interval.subject_ids
    scoped = next(item for item in draft.quantities if item.quantity_id == "qty_mu")
    assert scoped.subject_id == "surface"
    assert scoped.interval_id == interval.interval_id
    assert "qty_mu" in projection.environment_scoped_quantity_ids


def test_blocker_b_requires_an_interval_scoped_relation() -> None:
    case = _with_environment_fact(_case())
    without_relation = _with_gold(case, relations=())
    projection = _project(without_relation)
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.environment_relation_absent.value
    )


def test_blocker_b_rejects_a_cross_interval_relation() -> None:
    case = _with_environment_fact(_case())
    other_interval = case.gold.motion_segments[0].model_copy(
        update={"role": "motion_2", "order": 2, "start_event_role": None}
    )
    cross = _with_gold(
        case,
        motion_segments=case.gold.motion_segments + (other_interval,),
        relations=(case.gold.relations[0].model_copy(update={"segment_role": "motion_2"}),),
    )
    projection = _project(cross)
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.environment_relation_cross_interval.value
    )


def test_blocker_b_rejects_an_ambiguous_environment_link() -> None:
    case = _with_environment_fact(_case())
    second_actor = case.gold.entities[0].model_copy(update={"role": "box2"})
    segment = case.gold.motion_segments[0].model_copy(
        update={"actor_roles": ("box", "box2")}
    )
    ambiguous = _with_gold(
        case,
        entities=case.gold.entities + (second_actor,),
        motion_segments=(segment,),
        relations=(
            case.gold.relations[0],
            case.gold.relations[0].model_copy(
                update={"role": "contact2", "participant_roles": ("box2", "surface")}
            ),
        ),
    )
    projection = _project(ambiguous)
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.environment_relation_ambiguous.value
    )


# --------------------------------------------------------------------------
# Source evidence exactness
# --------------------------------------------------------------------------


def test_every_explicit_quantity_span_covers_its_value_and_unit() -> None:
    projection = _project(_case())
    text = projection.problem_text
    evidence = {item.evidence_id: item for item in projection.draft.source_evidence}
    for quantity in projection.draft.quantities:
        assert quantity.evidence_refs
        item = evidence[quantity.evidence_refs[0]]
        assert text[item.source_span.start : item.source_span.end] == item.quote
        span = item.quantity_span
        assert span is not None
        assert item.source_span.start <= span.start < span.end <= item.source_span.end
        covered = text[span.start : span.end]
        assert quantity.raw_value in covered
        if quantity.raw_unit:
            assert covered.strip() != quantity.raw_value


def test_a_value_absent_from_its_quote_is_rejected_before_the_draft() -> None:
    case = _case()
    invented = case.gold.explicit_facts[0].model_copy(update={"raw_value": "987654"})
    projection = _project(
        _with_gold(case, explicit_facts=(invented,) + case.gold.explicit_facts[1:])
    )
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.evidence_value_not_in_quote.value
    )


def test_a_fact_without_an_evidence_quote_is_rejected() -> None:
    case = _case()
    unquoted = case.gold.explicit_facts[0].model_copy(update={"evidence_quote": None})
    projection = _project(
        _with_gold(case, explicit_facts=(unquoted,) + case.gold.explicit_facts[1:])
    )
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.missing_evidence_for_explicit_value.value
    )


# --------------------------------------------------------------------------
# Dangling references and neutral pre-runtime terminals
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gold_update", "reason"),
    (
        (
            {"explicit_facts": "subject"},
            DraftProjectionReason.dangling_entity_reference,
        ),
        (
            {"explicit_facts": "interval"},
            DraftProjectionReason.dangling_interval_reference,
        ),
    ),
)
def test_dangling_fact_references_are_rejected(gold_update, reason) -> None:
    case = _case()
    field = "subject_role" if gold_update["explicit_facts"] == "subject" else "segment_role"
    broken = case.gold.explicit_facts[0].model_copy(update={field: "ghost"})
    projection = _project(
        _with_gold(case, explicit_facts=(broken,) + case.gold.explicit_facts[1:])
    )
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == reason.value


def test_needs_figure_returns_a_neutral_pre_runtime_terminal() -> None:
    case = _case()
    projection = _project(
        _with_gold(
            case,
            figure_dependency=case.gold.figure_dependency.model_copy(
                update={"level": "required"}
            ),
        )
    )
    assert projection.terminal is DraftProjectionTerminal.needs_figure
    assert projection.draft is None


def test_absent_query_returns_a_neutral_pre_runtime_terminal() -> None:
    projection = _project(_with_gold(_case(), queries=()))
    assert projection.terminal is DraftProjectionTerminal.insufficient_information
    assert projection.draft is None


# --------------------------------------------------------------------------
# No answer, graph, solver, or root authority; no legacy fallback
# --------------------------------------------------------------------------


def test_projected_draft_carries_no_answer_or_solver_authority() -> None:
    projection = _project(_case())
    payload = projection.draft.model_dump_json()
    for forbidden in (
        "expected_answer",
        "final_answer",
        "solver_result",
        "selected_root",
        "selected_equations",
        "verification_result",
        "reference_expression",
        "legacy",
    ):
        assert forbidden not in payload
    assert projection.draft.constraints == []
    assert projection.draft.principle_hints == []
