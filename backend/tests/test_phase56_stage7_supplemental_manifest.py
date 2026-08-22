from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

from evaluation.phase56_stage7.corpus_records import (
    CorpusAssumptionV1,
    CorpusEntityV1,
    CorpusEventV1,
    CorpusFactV1,
    CorpusFigureDependencyV1,
    CorpusQueryV1,
    CorpusRelationV1,
    CorpusSegmentV1,
)
from evaluation.phase56_stage7.corpus_v2.migration import (
    assert_manifest_has_no_answer_authority,
)
from evaluation.phase56_stage7.corpus_v2.records import (
    ConstraintAuthority,
    FrameType,
    QueryObjective,
)
from evaluation.phase56_stage7.corpus_v2.supplemental_campaign import (
    EXPECTED_COHORT_SIZE,
    EXPECTED_SELECTED_CONTEXTS,
    SOURCE_ONLY_FIELDS,
    SUPPLEMENTAL_CAMPAIGN_ID,
    SourceOnlyCaseV1,
    SupplementalCohort,
    SupplementalManifestReason,
    SupplementalManifestRefused,
    build_supplemental_manifest,
    discover_supplemental_cohorts,
    source_only_case,
    supplemental_manifest_body,
)


def _entity(role: str, kind: str) -> CorpusEntityV1:
    return CorpusEntityV1(role=role, kind=kind)


def _segment(model: str, actors: tuple[str, ...]) -> CorpusSegmentV1:
    return CorpusSegmentV1(
        role="motion_1",
        order=1,
        actor_roles=actors,
        motion_model=model,
        relevance="target",
        start_event_role="start",
        end_event_role="finish",
    )


def _event(role: str, kind: str, actors: tuple[str, ...]) -> CorpusEventV1:
    return CorpusEventV1(
        role=role,
        kind=kind,
        subject_roles=actors,
        segment_role="motion_1",
    )


def _fact(
    role: str,
    semantic_key: str,
    *,
    subject: str,
    event: str | None = None,
) -> CorpusFactV1:
    return CorpusFactV1(
        role=role,
        semantic_key=semantic_key,
        raw_value="source-value",
        raw_unit="m",
        subject_role=subject,
        segment_role="motion_1",
        event_role=event,
        temporal_role="at_event" if event else "timeless",
        direction="not_applicable",
        relevance="solver_input",
    )


def _relation(role: str, participants: tuple[str, ...]) -> CorpusRelationV1:
    return CorpusRelationV1(
        role=role,
        kind="point_on_body" if role != "contact" else "contact_with",
        participant_roles=participants,
        segment_role="motion_1",
    )


def _assumption(role: str, kind: str) -> CorpusAssumptionV1:
    return CorpusAssumptionV1(
        role=role,
        kind=kind,
        subject_role="vehicle",
        segment_role="motion_1",
    )


def _query(output: str, subject: str, event: str | None = None) -> CorpusQueryV1:
    return CorpusQueryV1(
        role="q1",
        output_key=output,
        subject_role=subject,
        segment_role="motion_1",
        component="magnitude",
        event_role=event,
    )


def _banked(suffix: str = "") -> SourceOnlyCaseV1:
    return SourceOnlyCaseV1(
        problem_text=f"경사진 원형 곡선 {suffix} 충분히 긴 문제 문장입니다.",
        figure_dependency=CorpusFigureDependencyV1(level="none"),
        entities=(_entity("vehicle", "vehicle"), _entity("road", "surface")),
        motion_segments=(_segment("unknown", ("vehicle",)),),
        events=(_event("start", "start", ("vehicle",)),),
        explicit_facts=(
            _fact("radius", "radius", subject="vehicle"),
            _fact("angle", "angle", subject="road"),
        ),
        relations=(_relation("contact", ("vehicle", "road")),),
        assumption_proposals=(
            _assumption("gravity", "constant_gravity"),
            _assumption("frictionless", "frictionless"),
        ),
        queries=(_query("final_velocity", "vehicle"),),
    )


def _flat(suffix: str = "") -> SourceOnlyCaseV1:
    return SourceOnlyCaseV1(
        problem_text=(
            f"승용차가 수평 원형도로를 돈다 {suffix}. "
            "미끄러지지 않는 최대 속력의 크기를 구하여라."
        ),
        figure_dependency=CorpusFigureDependencyV1(level="none"),
        entities=(_entity("vehicle", "vehicle"), _entity("road", "surface")),
        motion_segments=(_segment("unknown", ("vehicle",)),),
        events=(_event("start", "start", ("vehicle",)),),
        explicit_facts=(
            _fact("mu", "coefficient_of_friction", subject="road"),
            _fact("radius", "radius", subject="vehicle"),
        ),
        relations=(_relation("contact", ("vehicle", "road")),),
        assumption_proposals=(_assumption("gravity", "constant_gravity"),),
        queries=(_query("final_velocity", "vehicle"),),
    )


def _instant(suffix: str = "") -> SourceOnlyCaseV1:
    return SourceOnlyCaseV1(
        problem_text=(
            f"막대 AB의 한 순간 {suffix}. "
            "순간중심 방법으로 점 B의 속력 크기를 구하여라."
        ),
        figure_dependency=CorpusFigureDependencyV1(level="none"),
        entities=(
            _entity("body", "rigid_body"),
            _entity("point_a", "point"),
            _entity("point_b", "point"),
            _entity("ic", "point"),
        ),
        motion_segments=(
            _segment("general_plane_motion", ("body", "point_a", "point_b")),
        ),
        events=(_event("instant", "other", ("body", "point_a", "point_b")),),
        explicit_facts=(
            _fact("rA", "radius", subject="point_a", event="instant"),
            _fact("rB", "radius", subject="point_b", event="instant"),
            _fact("vA", "velocity", subject="point_a", event="instant"),
        ),
        relations=(
            _relation("a_body", ("body", "point_a")),
            _relation("b_body", ("body", "point_b")),
        ),
        assumption_proposals=(),
        queries=(_query("tangential_velocity", "point_b", "instant"),),
    )


def _population() -> tuple[SourceOnlyCaseV1, ...]:
    return tuple(
        [*(_banked(str(i)) for i in range(3))]
        + [*(_flat(str(i)) for i in range(3))]
        + [*(_instant(str(i)) for i in range(3))]
    )


def _public_case(source: SourceOnlyCaseV1, identity: int):
    gold = SimpleNamespace(
        figure_dependency=source.figure_dependency,
        entities=source.entities,
        motion_segments=source.motion_segments,
        events=source.events,
        explicit_facts=source.explicit_facts,
        relations=source.relations,
        assumption_proposals=source.assumption_proposals,
        queries=source.queries,
    )
    record = {
        "schema_version": "synthetic-source-record-v1",
        "identity": identity,
        # This answer-bearing field is deliberately present only in the opaque
        # record fingerprint input.  It cannot fit in SourceOnlyCaseV1.
        "gold": {"answers": [{"numeric": identity + 0.5}]},
    }
    return SimpleNamespace(
        problem_text=source.problem_text,
        gold=gold,
        model_dump=lambda **_: record,
    )


def test_source_only_view_is_a_closed_non_evaluation_schema() -> None:
    expected = (
        "problem_text",
        "figure_dependency",
        "entities",
        "motion_segments",
        "events",
        "explicit_facts",
        "relations",
        "assumption_proposals",
        "queries",
    )
    assert SOURCE_ONLY_FIELDS == expected
    assert tuple(item.name for item in fields(SourceOnlyCaseV1)) == expected
    assert not set(expected) & {
        "case_id",
        "split",
        "family",
        "answers",
        "expected_terminal",
        "expected_failure_codes",
        "tolerance",
        "solver_result",
    }


def test_converter_reads_only_the_closed_source_view() -> None:
    source = _flat()
    converted = source_only_case(_public_case(source, 1))
    assert converted == source


def test_discovery_selects_three_per_frozen_typed_signature() -> None:
    selection = discover_supplemental_cohorts(_population())

    assert len(selection.selected_positions) == EXPECTED_SELECTED_CONTEXTS
    assert all(
        len(positions) == EXPECTED_COHORT_SIZE
        for _, positions in selection.by_cohort
    )
    assert tuple(cohort for cohort, _ in selection.by_cohort) == tuple(
        SupplementalCohort
    )


def test_discovery_refuses_population_drift_instead_of_reselecting() -> None:
    with pytest.raises(SupplementalManifestRefused) as caught:
        discover_supplemental_cohorts((*_population(), _flat("extra")))

    assert caught.value.reason is SupplementalManifestReason.cohort_cardinality_mismatch


def test_manifest_binds_identity_only_after_source_selection() -> None:
    source = _population()
    cases = tuple(_public_case(item, index) for index, item in enumerate(source))

    built = build_supplemental_manifest(cases)

    assert len(built.manifest.entries) == EXPECTED_SELECTED_CONTEXTS
    assert len(built.selection.selected_positions) == EXPECTED_SELECTED_CONTEXTS
    assert len(built.selection_identity_digest) == 64
    assert all(
        entry.authoring_provenance.startswith(SUPPLEMENTAL_CAMPAIGN_ID)
        for entry in built.manifest.entries
    )
    assert_manifest_has_no_answer_authority(built.manifest.model_dump(mode="json"))


def test_manifest_carriers_are_source_evidenced_and_scope_preserving() -> None:
    cases = tuple(
        _public_case(item, index) for index, item in enumerate(_population())
    )
    built = build_supplemental_manifest(cases)
    entries = built.manifest.entries

    assert all(entries[index].augmentation.is_empty for index in range(3))
    for entry in entries[3:6]:
        augmentation = entry.augmentation
        assert len(augmentation.source_quotes) == 2
        assert tuple(item.frame_type for item in augmentation.reference_frames) == (
            FrameType.world_cartesian,
            FrameType.surface_tangent_normal,
        )
        assert len(augmentation.query_objectives) == 1
        assert augmentation.query_objectives[0].objective is QueryObjective.maximum
    for entry in entries[6:9]:
        augmentation = entry.augmentation
        assert len(augmentation.source_quotes) == 1
        assert len(augmentation.constraint_authorities) == 1
        constraint = augmentation.constraint_authorities[0]
        assert constraint.authority is ConstraintAuthority.instantaneous_center
        assert constraint.event_id == "instant"
        assert constraint.interval_id is None
        assert set(constraint.participant_ids) == {"body", "ic"}


def test_manifest_bytes_are_deterministic_and_end_with_one_newline() -> None:
    cases = tuple(
        _public_case(item, index) for index, item in enumerate(_population())
    )
    first = build_supplemental_manifest(cases)
    second = build_supplemental_manifest(cases)

    first_body = supplemental_manifest_body(first.manifest)
    assert first.manifest.digest == second.manifest.digest
    assert first_body == supplemental_manifest_body(second.manifest)
    assert first_body.endswith("\n") and not first_body.endswith("\n\n")
