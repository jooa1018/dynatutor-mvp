"""Stage 7 Lane B adapter invariants.

These tests pin the properties that must hold no matter how the remaining
projection gaps are resolved: the gold whitelist, structural derivation of the
diagnostics-only system type, and determinism.
"""

from __future__ import annotations

import pytest

from engine.textbook_parser.contracts import ParserSystemType
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_adapter import (
    FORBIDDEN_GOLD_MEMBERS,
    PERMITTED_GOLD_MEMBERS,
    LaneBAdapterError,
    derive_parse_status,
    derive_system_type,
    project_case_to_parse,
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


def test_permitted_and_forbidden_gold_members_are_disjoint() -> None:
    assert PERMITTED_GOLD_MEMBERS & FORBIDDEN_GOLD_MEMBERS == frozenset()
    for forbidden in (
        "expected_system_type",
        "future_expected_terminal",
        "phase55_expected_terminal",
        "answers",
        "parse_status",
    ):
        assert forbidden in FORBIDDEN_GOLD_MEMBERS
        assert forbidden not in PERMITTED_GOLD_MEMBERS


def test_projection_is_deterministic() -> None:
    case = _case()
    first = project_case_to_parse(case)
    second = project_case_to_parse(case)
    assert first.parse == second.parse
    assert first.derived_system_type == second.derived_system_type


def test_family_and_expected_system_type_never_change_the_projection() -> None:
    baseline = project_case_to_parse(_case())
    for family in ("spring_mass_vibration", "coriolis_relative_motion", None):
        rerouted = project_case_to_parse(_case(family=family))
        assert rerouted.parse == baseline.parse
        assert rerouted.derived_system_type == baseline.derived_system_type

    case = _case()
    misleading = case.gold.model_copy(
        update={"expected_system_type": "slot_pin_relative_motion"}
    )
    assert (
        project_case_to_parse(case.model_copy(update={"gold": misleading})).parse
        == baseline.parse
    )


def test_expected_terminal_and_answers_never_change_the_projection() -> None:
    case = _case()
    baseline = project_case_to_parse(case)
    tampered = case.gold.model_copy(
        update={
            "future_expected_terminal": "needs_confirmation",
            "phase55_expected_terminal": "accepted",
            "parse_status": "unsupported",
            "answers": (),
        }
    )
    assert project_case_to_parse(case.model_copy(update={"gold": tampered})).parse == (
        baseline.parse
    )


def test_case_id_and_split_never_change_the_projection() -> None:
    baseline = project_case_to_parse(_case())
    renamed = project_case_to_parse(
        _case(case_id="zzz_other_9999", difficulty=5, tags=("bait",))
    )
    assert renamed.parse == baseline.parse


def test_system_type_is_derived_from_structure_not_from_labels() -> None:
    case = _case()
    baseline = derive_system_type(case)
    assert isinstance(baseline, ParserSystemType)

    spring = case.gold.model_copy(
        update={
            "relations": (
                case.gold.relations[0].model_copy(update={"kind": "attached_to_spring"}),
            )
        }
    )
    assert derive_system_type(case.model_copy(update={"gold": spring})) is not baseline

    collision = case.gold.model_copy(
        update={
            "relations": (
                case.gold.relations[0].model_copy(update={"kind": "collides_with"}),
            )
        }
    )
    assert (
        derive_system_type(case.model_copy(update={"gold": collision}))
        is ParserSystemType.collision_1d
    )


def test_parse_status_is_derived_structurally() -> None:
    case = _case()
    assert derive_parse_status(case) == "complete"
    needs_figure = case.gold.model_copy(
        update={
            "figure_dependency": case.gold.figure_dependency.model_copy(
                update={"level": "required"}
            )
        }
    )
    assert derive_parse_status(case.model_copy(update={"gold": needs_figure})) == (
        "needs_figure"
    )
    no_query = case.gold.model_copy(update={"queries": ()})
    assert derive_parse_status(case.model_copy(update={"gold": no_query})) == (
        "insufficient_information"
    )


def test_unmaterialised_segment_boundary_is_synthesised_from_its_slot() -> None:
    case = _case()
    segment = case.gold.motion_segments[0].model_copy(
        update={"start_event_role": "start", "end_event_role": "finish"}
    )
    gold = case.gold.model_copy(update={"motion_segments": (segment,)})
    projection = project_case_to_parse(case.model_copy(update={"gold": gold}))
    by_id = {event.event_id: event for event in projection.parse.events}
    assert by_id["finish"].kind.value == "finish"
    assert by_id["finish"].segment_id == segment.role
    # The start slot already existed in gold and keeps its authored kind.
    assert by_id["start"].kind.value == "start"


def test_projection_failure_is_a_typed_adapter_error() -> None:
    case = _case()
    broken = case.gold.model_copy(update={"entities": ()})
    with pytest.raises(LaneBAdapterError):
        project_case_to_parse(case.model_copy(update={"gold": broken}))
