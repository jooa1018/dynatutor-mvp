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


# --------------------------------------------------------------------------
# Evidence alignment reuse and the privacy-safe failure matrix
# --------------------------------------------------------------------------


def test_written_unit_is_carried_into_the_draft_not_the_corpus_spelling() -> None:
    """`raw_unit` is a raw source token, so the symbol written in the text wins."""

    case = _case()
    fact = case.gold.explicit_facts[1]
    assert fact.raw_unit == "m/s^2"
    text = case.problem_text.replace(f"{fact.raw_value} m/s^2", f"{fact.raw_value} m/s\u00b2")
    rewritten = fact.model_copy(
        update={"evidence_quote": f"\uac00\uc18d\ub3c4\ub294 {fact.raw_value} m/s\u00b2"}
    )
    projection = _project(
        case.model_copy(
            update={
                "problem_text": text,
                "gold": case.gold.model_copy(
                    update={
                        "explicit_facts": case.gold.explicit_facts[:1] + (rewritten,)
                    }
                ),
            }
        )
    )
    assert projection.terminal is DraftProjectionTerminal.projected
    quantity = next(
        item
        for item in projection.draft.quantities
        if item.quantity_id == "qty_acceleration"
    )
    assert quantity.raw_unit == "m/s\u00b2"


def test_a_dimensionally_wrong_written_unit_is_rejected() -> None:
    """A known declared unit must agree dimensionally with what the text says."""

    case = _case()
    fact = case.gold.explicit_facts[0]
    text = case.problem_text.replace(f"{fact.raw_value} kg", f"{fact.raw_value} s")
    rewritten = fact.model_copy(
        update={"evidence_quote": f"\uc9c8\ub7c9\uc740 {fact.raw_value} s"}
    )
    projection = _project(
        case.model_copy(
            update={
                "problem_text": text,
                "gold": case.gold.model_copy(
                    update={
                        "explicit_facts": (rewritten,) + case.gold.explicit_facts[1:]
                    }
                ),
            }
        )
    )
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.evidence_unit_dimension_mismatch.value
    )


def test_environment_link_requires_a_contact_type_relation() -> None:
    case = _with_environment_fact(_case())
    roped = _with_gold(
        case,
        relations=(case.gold.relations[0].model_copy(update={"kind": "connected_by_rope"}),),
    )
    projection = _project(roped)
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.environment_relation_absent.value
    )


def test_failure_matrix_is_privacy_safe_and_aggregate_only() -> None:
    from engine.mechanics.validation import validate_draft
    from evaluation.phase56_stage7.lane_b_failure_matrix import build_failure_matrix

    case = _case()
    matrix = build_failure_matrix([case], validate=validate_draft)
    payload = matrix.as_dict()

    assert payload["total_cases"] == 1
    assert payload["terminal_counts"] == {"projected": 1}
    assert payload["projection_rejection_counts"] == {}
    assert payload["structure_counts"]["validate_draft_accepted"] == 1

    import json

    serialized = json.dumps(payload, ensure_ascii=False)
    assert case.case_id not in serialized
    assert (case.family or "") not in serialized or not case.family
    assert case.problem_text[:12] not in serialized
    assert case.problem_hash not in serialized
    for forbidden in ("expected_answer", "future_expected_terminal", "reference_expression"):
        assert forbidden not in serialized
    # Index-stripped paths cannot identify an individual case.
    for entry in payload["validator_code_path_counts"]:
        assert ".N" in entry["path"] or entry["path"] == ""


# --------------------------------------------------------------------------
# 6-A direction/component preservation
# --------------------------------------------------------------------------


def _directed(case: PublicCorpusCaseV1, direction: str) -> PublicCorpusCaseV1:
    fact = case.gold.explicit_facts[1].model_copy(update={"direction": direction})
    return _with_gold(
        case, explicit_facts=case.gold.explicit_facts[:1] + (fact,)
    )


def _quantity(case: PublicCorpusCaseV1, quantity_id: str = "qty_acceleration"):
    draft = _project(case).draft
    return next(item for item in draft.quantities if item.quantity_id == quantity_id)


@pytest.mark.parametrize(
    ("first", "second"),
    (("left", "right"), ("clockwise", "counterclockwise"), ("upward", "downward")),
)
def test_opposite_directions_produce_different_drafts(first: str, second: str) -> None:
    case = _case()
    assert _project(_directed(case, first)).draft != _project(_directed(case, second)).draft


def test_direction_is_carried_into_the_typed_direction_field() -> None:
    quantity = _quantity(_directed(_case(), "downward"))
    assert quantity.direction is not None
    assert quantity.direction.kind == "semantic"
    assert quantity.direction.direction.value == "downward"


def test_component_directions_also_set_the_component() -> None:
    quantity = _quantity(_directed(_case(), "tangential"))
    assert quantity.component.value == "tangential"
    assert quantity.direction.direction.value == "tangential"


@pytest.mark.parametrize("absent", ("not_applicable", "unspecified"))
def test_absent_direction_is_never_invented(absent: str) -> None:
    quantity = _quantity(_directed(_case(), absent))
    assert quantity.direction is None
    assert quantity.component.value == "unspecified"


def test_one_fact_direction_does_not_contaminate_another_quantity() -> None:
    case = _directed(_case(), "left")
    mass = _quantity(case, "qty_mass")
    assert mass.direction is None


# --------------------------------------------------------------------------
# 6-B typed geometry / interaction split
# --------------------------------------------------------------------------


def _relation(case: PublicCorpusCaseV1, kind: str) -> PublicCorpusCaseV1:
    return _with_gold(
        case, relations=(case.gold.relations[0].model_copy(update={"kind": kind}),)
    )


@pytest.mark.parametrize(
    ("kind", "geometry_kind"),
    (
        ("connected_by_rope", "topology_connects"),
        ("passes_over_pulley", "wraps"),
        ("rolls_on", "tangent"),
        ("point_on_body", "lies_on"),
        ("rotates_about", "coincident"),
        ("moves_in_slot", "lies_on"),
    ),
)
def test_topological_relations_become_typed_geometry(kind: str, geometry_kind: str) -> None:
    draft = _project(_relation(_case(), kind)).draft
    assert draft.interactions == []
    assert len(draft.geometry) == 1
    assert draft.geometry[0].kind.value == geometry_kind
    assert draft.geometry[0].participant_ids == ["box", "surface"]


@pytest.mark.parametrize(
    ("kind", "interaction_kind"),
    (
        ("attached_to_spring", "spring"),
        ("contact_with", "contact"),
        ("collides_with", "collision"),
    ),
)
def test_force_relations_stay_interactions(kind: str, interaction_kind: str) -> None:
    draft = _project(_relation(_case(), kind)).draft
    assert draft.geometry == []
    assert draft.interactions[0].kind.value == interaction_kind


def test_participant_order_and_pulley_role_are_preserved() -> None:
    case = _case()
    pulley = case.gold.entities[1].model_copy(update={"role": "pulley", "kind": "pulley"})
    relation = case.gold.relations[0].model_copy(
        update={"kind": "passes_over_pulley", "participant_roles": ("pulley", "box")}
    )
    draft = _project(
        _with_gold(
            case, entities=(case.gold.entities[0], pulley), relations=(relation,)
        )
    ).draft
    assert draft.geometry[0].participant_ids == ["pulley", "box"]
    assert next(e for e in draft.entities if e.entity_id == "pulley").primitive.value == (
        "pulley"
    )


@pytest.mark.parametrize(
    "kind", ("shares_velocity_constraint", "shares_acceleration_constraint")
)
def test_relations_without_a_typed_contract_fail_closed(kind: str) -> None:
    projection = _project(_relation(_case(), kind))
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.relation_kind_has_no_typed_contract.value
    )


def test_relation_order_does_not_change_draft_content() -> None:
    case = _case()
    second = case.gold.relations[0].model_copy(
        update={"role": "contact_b", "kind": "slides_on"}
    )
    forward = _project(_with_gold(case, relations=(case.gold.relations[0], second))).draft
    reverse = _project(_with_gold(case, relations=(second, case.gold.relations[0]))).draft
    assert {item.relation_id for item in forward.geometry} == {
        item.relation_id for item in reverse.geometry
    }
    assert {item.interaction_id for item in forward.interactions} == {
        item.interaction_id for item in reverse.interactions
    }


# --------------------------------------------------------------------------
# 6-C closed assumption policy
# --------------------------------------------------------------------------


def _assumed(case: PublicCorpusCaseV1, **updates) -> PublicCorpusCaseV1:
    from evaluation.phase56_stage7.corpus_records import CorpusAssumptionV1

    base = {
        "role": "grav",
        "kind": "constant_gravity",
        "subject_role": "box",
        "segment_role": "motion_1",
        "supporting_quote": None,
        "server_value_only": True,
    }
    base.update(updates)
    return _with_gold(case, assumption_proposals=(CorpusAssumptionV1(**base),))


def test_server_default_assumption_is_approved() -> None:
    projection = _project(_assumed(_case()))
    assert projection.approvable_assumption_ids == ("asm_grav",)


def test_ungrounded_assumption_requires_confirmation_and_is_not_approved() -> None:
    projection = _project(_assumed(_case(), kind="frictionless", role="fr"))
    assert projection.approvable_assumption_ids == ()
    assert projection.draft.assumptions[0].disposition.value == "proposed"


def test_source_grounded_assumption_is_approved() -> None:
    case = _case()
    quote = case.problem_text[:14]
    projection = _project(
        _assumed(case, kind="starts_from_rest", role="rest", supporting_quote=quote)
    )
    assert projection.approvable_assumption_ids == ("asm_rest",)


def test_assumption_quote_absent_from_the_source_is_not_approved() -> None:
    projection = _project(
        _assumed(
            _case(),
            kind="starts_from_rest",
            role="rest",
            supporting_quote="이 문장은 문제에 없다",
        )
    )
    assert projection.approvable_assumption_ids == ()


def test_a_competing_explicit_fact_outranks_the_assumption() -> None:
    case = _case()
    # Restate the acceleration fact as an explicit final velocity so that a
    # rest assumption on the same role is contested by the source.
    velocity_fact = case.gold.explicit_facts[1].model_copy(
        update={"role": "vfinal", "semantic_key": "final_velocity"}
    )
    contested = _with_gold(
        case, explicit_facts=case.gold.explicit_facts[:1] + (velocity_fact,)
    )
    projection = _project(
        _assumed(
            contested,
            kind="ends_at_rest",
            role="rest",
            supporting_quote=case.problem_text[:14],
        )
    )
    assert projection.approvable_assumption_ids == ()
    assert projection.draft.assumptions[0].disposition.value == "rejected"


def test_unsupported_assumption_kind_is_rejected_not_approved() -> None:
    projection = _project(
        _assumed(_case(), kind="direction_choice", role="dir", supporting_quote="x")
    )
    assert projection.approvable_assumption_ids == ()
    assert projection.draft.assumptions[0].disposition.value == "rejected"


def test_assumption_keeps_its_authored_subject_and_interval() -> None:
    projection = _project(_assumed(_case()))
    assumption = projection.draft.assumptions[0]
    assert assumption.subject_id == "box"
    assert assumption.interval_id == "motion_1"


# --------------------------------------------------------------------------
# 6-D resolved evidence indices
# --------------------------------------------------------------------------


def test_recorded_occurrence_index_is_the_resolved_one() -> None:
    case = _case()
    fact = case.gold.explicit_facts[0].model_copy(update={"occurrence_index": 7})
    projection = _project(
        _with_gold(case, explicit_facts=(fact,) + case.gold.explicit_facts[1:])
    )
    assert projection.terminal is DraftProjectionTerminal.projected
    evidence = projection.draft.source_evidence[0]
    # The corpus index was out of range for a single occurrence; alignment
    # resolved it to 0 and the Draft records the resolved value.
    assert evidence.occurrence_index == 0
    text = projection.problem_text
    assert text[evidence.source_span.start : evidence.source_span.end] == evidence.quote
