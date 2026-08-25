"""The law-prerequisite matrix: what a rule declares vs what it actually needs.

A rule names the roles, interactions, and approved assumptions it relates.  Its
emission function enforces more — frames with axes, typed point roles, component
and endpoint scope, interaction-owned quantities, cardinality — and that
difference is exactly what decides whether a source-grounded projection can
reach the law at all.

The matrix measures the difference in counts and nothing else, so a defect class
is visible while the record that produced it is not.
"""

from __future__ import annotations

import pytest

from engine.mechanics.laws.base import LawRule
from engine.mechanics.laws.core import core_law_catalog
from evaluation.phase56_stage7.law_prerequisites import (
    LAW_PREREQUISITE_MATRIX_VERSION,
    LawTopologyTier,
    build_law_prerequisite_matrix,
    law_context_for_projection,
    topology_tier,
)
from evaluation.phase56_stage7.corpus_records import (
    CorpusAssumptionV1,
    PublicCorpusCaseV1,
)
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import project_case_to_draft
from support.phase56_stage7_corpus_fixtures import build_case


def _case(**overrides) -> PublicCorpusCaseV1:
    record = build_case(
        index=3,
        split="public_dev",
        family="constant_acceleration_1d",
        future_terminal="accepted",
        with_answer=True,
    )
    record["split"] = PublicSplit.public_dev
    record.update(overrides)
    return PublicCorpusCaseV1(**record)


def _with_gold(case: PublicCorpusCaseV1, **gold_updates) -> PublicCorpusCaseV1:
    return case.model_copy(update={"gold": case.gold.model_copy(update=gold_updates)})


def _solvable() -> PublicCorpusCaseV1:
    """A rest-started constant-acceleration interval with travel and time."""

    case = _case()
    segment = case.gold.motion_segments[0].model_copy(
        update={"motion_model": "constant_acceleration_1d", "end_event_role": "finish"}
    )
    base = case.gold.explicit_facts[1]
    travel_quote = "이동 거리는 8.4 m"
    elapsed_quote = "걸린 시간은 3.0 s"
    travel = base.model_copy(
        update={
            "role": "travel",
            "semantic_key": "distance",
            "raw_value": "8.4",
            "raw_unit": "m",
            "evidence_quote": travel_quote,
            "temporal_role": "interval",
        }
    )
    elapsed = base.model_copy(
        update={
            "role": "elapsed",
            "semantic_key": "time",
            "raw_value": "3.0",
            "raw_unit": "s",
            "evidence_quote": elapsed_quote,
            "temporal_role": "interval",
        }
    )
    updated = case.model_copy(
        update={
            "problem_text": (
                f"{case.problem_text} {travel_quote} 이고 {elapsed_quote} 이다."
            )
        }
    )
    return _with_gold(
        updated,
        motion_segments=(segment,),
        explicit_facts=(case.gold.explicit_facts[0], travel, elapsed),
        assumption_proposals=(
            CorpusAssumptionV1(
                role="rest",
                kind="starts_from_rest",
                subject_role="box",
                segment_role="motion_1",
                supporting_quote=case.problem_text[:14],
                server_value_only=False,
            ),
        ),
        queries=(
            case.gold.queries[0].model_copy(
                update={"output_key": "acceleration", "component": "magnitude"}
            ),
        ),
    )


def _context(case: PublicCorpusCaseV1):
    return law_context_for_projection(project_case_to_draft(case))


def _matrix(cases):
    contexts = [item for item in (_context(case) for case in cases) if item is not None]
    assert contexts, "the fixture must reach the law stage"
    return build_law_prerequisite_matrix(contexts)


# --------------------------------------------------------------------------
# Tier derivation follows the catalogue, not a transcribed copy of it
# --------------------------------------------------------------------------


def test_every_catalogue_rule_has_exactly_one_tier() -> None:
    for rule in core_law_catalog():
        assert isinstance(topology_tier(rule), LawTopologyTier)


def test_a_declared_interaction_always_means_a_free_body_tier() -> None:
    for rule in core_law_catalog():
        if rule.required_interactions:
            assert topology_tier(rule) is LawTopologyTier.free_body


def test_the_rigid_body_category_is_its_own_tier() -> None:
    for rule in core_law_catalog():
        if rule.category == "rigid_body_kinematics" and not rule.required_interactions:
            assert topology_tier(rule) is LawTopologyTier.rigid_body


@pytest.mark.parametrize(
    "category, expected",
    [
        ("kinematics", LawTopologyTier.particle_kinematics),
        ("constraint", LawTopologyTier.particle_kinematics),
        ("work_energy", LawTopologyTier.particle_dynamics),
        ("impulse_momentum", LawTopologyTier.particle_dynamics),
    ],
)
def test_an_interaction_free_rule_takes_its_category_tier(category, expected) -> None:
    rule = LawRule(law_id="probe", category=category)
    assert topology_tier(rule) is expected


def test_the_matrix_covers_the_whole_catalogue_once() -> None:
    matrix = _matrix([_solvable()])
    ids = [item.law_id for item in matrix.laws]
    assert sorted(ids) == sorted(rule.law_id for rule in core_law_catalog())
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------
# Reachability is the engine's own answer
# --------------------------------------------------------------------------


def test_a_reachable_law_is_reported_as_emitting() -> None:
    matrix = _matrix([_solvable()])
    emitting = {item.law_id for item in matrix.reachable()}
    assert "particle_constant_acceleration_position" in emitting
    assert "state_at_rest" in emitting


def test_a_law_whose_declared_prerequisites_are_absent_is_not_blocked() -> None:
    matrix = _matrix([_solvable()])
    by_id = {item.law_id: item for item in matrix.laws}
    # No spring interaction and no stiffness in this fixture at all.
    spring = by_id["spring_force"]
    assert spring.declared_satisfied == 0
    assert spring.structural_gap == 0


def test_a_structural_gap_is_never_negative() -> None:
    matrix = _matrix([_solvable()])
    assert all(item.structural_gap >= 0 for item in matrix.laws)
    assert all(item.emitted <= item.declared_satisfied for item in matrix.laws)


def test_blocked_laws_are_ordered_by_how_much_they_would_unlock() -> None:
    matrix = _matrix([_solvable()])
    gaps = [item.structural_gap for item in matrix.blocked()]
    assert gaps == sorted(gaps, reverse=True)
    assert all(gap > 0 for gap in gaps)


def test_the_context_count_matches_the_contexts_given() -> None:
    matrix = _matrix([_solvable(), _solvable()])
    assert matrix.context_count == 2


def test_an_empty_run_reports_the_catalogue_with_no_reachability() -> None:
    matrix = build_law_prerequisite_matrix([])
    assert matrix.context_count == 0
    assert matrix.reachable() == ()
    assert matrix.blocked() == ()
    assert len(matrix.laws) == len(core_law_catalog())


# --------------------------------------------------------------------------
# Privacy: the matrix carries counts, never records
# --------------------------------------------------------------------------


def test_the_serialized_matrix_carries_only_counts_and_catalogue_names() -> None:
    payload = _matrix([_solvable()]).as_dict()
    assert payload["version"] == LAW_PREREQUISITE_MATRIX_VERSION
    catalogue_names = {rule.law_id for rule in core_law_catalog()}
    for entry in payload["laws"]:
        assert entry["law_id"] in catalogue_names
        assert isinstance(entry["declared_satisfied"], int)
        assert isinstance(entry["emitted"], int)
        assert set(entry) == {
            "law_id",
            "category",
            "tier",
            "required_roles",
            "required_interactions",
            "required_assumption_kinds",
            "declared_satisfied",
            "emitted",
            "structural_gap",
        }


def test_no_case_identity_or_source_text_survives_into_the_matrix() -> None:
    case = _solvable()
    payload = repr(_matrix([case]).as_dict())
    for secret in (
        case.case_id,
        case.problem_text,
        str(case.gold.answers[0].numeric),
        case.gold.future_expected_terminal,
    ):
        assert secret not in payload
    assert case.family is None or case.family not in payload


def test_gold_metadata_never_changes_the_matrix() -> None:
    case = _solvable()
    baseline = _matrix([case]).as_dict()
    tampered = case.model_copy(
        update={"family": "coriolis_relative_motion", "difficulty": 5}
    )
    assert _matrix([tampered]).as_dict() == baseline


def test_the_reference_answer_never_changes_the_matrix() -> None:
    case = _solvable()
    baseline = _matrix([case]).as_dict()
    answer = case.gold.answers[0]
    tampered = _with_gold(
        case, answers=(answer.model_copy(update={"numeric": answer.numeric * 11.0}),)
    )
    assert _matrix([tampered]).as_dict() == baseline


def test_a_case_that_never_reaches_the_law_stage_yields_no_context() -> None:
    blocked = _with_gold(
        _solvable(),
        figure_dependency=_solvable().gold.figure_dependency.model_copy(
            update={"level": "required", "missing_information": ("geometry",)}
        ),
    )
    assert _context(blocked) is None
