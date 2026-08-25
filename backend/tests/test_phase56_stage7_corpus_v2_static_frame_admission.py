"""C4 determination: typed static frames are admitted; the blocker is elsewhere.

The v2 candidate's first shadow measurement reported that supplying a stated
reference frame moved solved contexts to ``compiler_unsupported ::
requires_specialized_model``, and the standing hypothesis was that the
compiler reads the *presence* of a frame as demanding a specialized model.

With the C3 correction in place that hypothesis is measured false: a
correctly projected static world/support frame pair — typed axis bindings,
world origin, no translation, no rotation, no generalized coordinates — flows
through the compiler without tripping ``requires_specialized_model`` at all.
The horizontal-contact cohort's real blocker is ``underdetermined``: its
free-body system lacks the normal and friction force records that no v2
carrier may invent, exactly as the compiler reports.  So there is no blanket
frame gate to relax, and no C4 compiler package is needed for this family;
what it needs is a complete-profile engine package of its own.

These tests pin both halves of that determination.  Every fixture sentence
and number is independently authored for this suite.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from engine.mechanics.contracts import MechanicsProblemDraftV1
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1, PublicSplit
from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation
from evaluation.phase56_stage7.corpus_v2.records import (
    AxisSense,
    CorpusV2AugmentationV1,
    FrameAxisV2,
    FrameType,
    ReferenceFrameV2,
    SourceQuoteEvidenceV2,
)
from evaluation.phase56_stage7.lane_b_draft_projection import project_case_to_draft
from evaluation.phase56_stage7.lane_b_runner import LaneBTerminal, run_lane_b_case
from tests.support.phase56_stage7_corpus_fixtures import build_case

pytestmark = pytest.mark.slow

_HORIZONTAL_QUOTE = "수평 바닥"


def _case() -> PublicCorpusCaseV1:
    text = (
        f"실험 상자가 {_HORIZONTAL_QUOTE} 위에서 오른쪽으로 이동한다. "
        "실험 상자의 질량은 9 kg이고 오른쪽으로 수평 힘 45 N이 작용한다. "
        "바닥과 상자 사이의 운동마찰계수는 0.3이다. "
        "중력가속도는 9.81 m/s²로 사용한다. 실험 상자의 가속도 x성분을 구하여라."
    )

    def _fact(role, key, value, unit, quote, *, direction="not_applicable"):
        return {
            "role": role, "semantic_key": key, "raw_value": value,
            "raw_unit": unit, "evidence_quote": quote, "subject_role": "object",
            "segment_role": "motion_1", "event_role": None,
            "temporal_role": "timeless", "direction": direction,
            "relevance": "solver_input", "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        }

    gold = {
        "parse_status": "complete",
        "expected_system_type": "horizontal_friction_force",
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": [
            {"role": "object", "kind": "block", "label": "실험 상자"},
            {"role": "surface", "kind": "surface", "label": "수평 바닥"},
        ],
        "motion_segments": [
            {"role": "motion_1", "order": 1, "actor_roles": ["object"],
             "motion_model": "unknown", "relevance": "target",
             "start_event_role": "start", "end_event_role": "finish"}
        ],
        "events": [
            {"role": "start", "kind": "start", "subject_roles": ["object"],
             "segment_role": "motion_1", "evidence_quote": None},
            {"role": "finish", "kind": "finish", "subject_roles": ["object"],
             "segment_role": "motion_1", "evidence_quote": None},
        ],
        "explicit_facts": [
            _fact("m", "mass", "9", "kg", "실험 상자의 질량은 9 kg"),
            _fact(
                "f", "force", "45", "N", "오른쪽으로 수평 힘 45 N",
                direction="right",
            ),
            _fact("mu", "coefficient_of_friction", "0.3", "", "운동마찰계수는 0.3"),
        ],
        "relations": [
            {"role": "on_floor", "kind": "slides_on",
             "participant_roles": ["object", "surface"],
             "segment_role": "motion_1"}
        ],
        "assumption_proposals": [
            {"role": "g_const", "kind": "constant_gravity",
             "subject_role": "object", "segment_role": "motion_1",
             "supporting_quote": "중력가속도는 9.81 m/s²로 사용한다",
             "server_value_only": True}
        ],
        "queries": [
            {"role": "q1", "output_key": "acceleration",
             "subject_role": "object", "segment_role": "motion_1",
             "component": "x", "event_role": None}
        ],
        "answers": [],
        "expected_failure_codes": [],
    }
    record = build_case(
        index=771,
        split="public_dev",
        family="horizontal_friction_force",
        future_terminal="accepted",
        with_answer=False,
    )
    record.update(
        case_id="fx_public_dev_0771",
        split=PublicSplit.public_dev,
        family="horizontal_friction_force",
        problem_text=text,
        problem_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        gold=gold,
    )
    return PublicCorpusCaseV1(**record)


def _typed_static_frames(support_id: str) -> CorpusV2AugmentationV1:
    def _axis(name, sense, bound_frame, bound_axis):
        return FrameAxisV2(
            axis=name,
            sense=sense,
            bound_frame_id=bound_frame,
            bound_axis=bound_axis,
            bound_sign=1,
            evidence_refs=("v2_ev_horizontal",),
        )

    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(
                evidence_id="v2_ev_horizontal", quote=_HORIZONTAL_QUOTE
            ),
        ),
        reference_frames=(
            ReferenceFrameV2(
                frame_id="v2_world",
                frame_type=FrameType.world_cartesian,
                subject_id=support_id,
                axes=(
                    _axis("x", AxisSense.along_surface_forward, "v2_world", "x"),
                    _axis("y", AxisSense.up_the_page, "v2_world", "y"),
                ),
                evidence_refs=("v2_ev_horizontal",),
            ),
            ReferenceFrameV2(
                frame_id="v2_support",
                frame_type=FrameType.surface_tangent_normal,
                subject_id=support_id,
                parent_frame_id="v2_world",
                axes=(
                    _axis(
                        "tangent", AxisSense.along_surface_forward, "v2_world", "x"
                    ),
                    _axis("normal", AxisSense.away_from_surface, "v2_world", "y"),
                ),
                evidence_refs=("v2_ev_horizontal",),
            ),
        ),
    )


def _run_pair():
    projection = project_case_to_draft(_case())
    assert projection.draft is not None
    payload = projection.draft.model_dump(mode="json", warnings="none")
    baseline = run_lane_b_case(projection, execution_token="c4-probe-token")
    merged = project_augmentation(
        payload,
        _typed_static_frames("surface"),
        problem_text=projection.problem_text,
    )
    draft = MechanicsProblemDraftV1.model_validate(merged)
    shadowed = run_lane_b_case(
        replace(projection, draft=draft), execution_token="c4-probe-token"
    )
    return baseline, shadowed, merged


def test_the_cohorts_blocker_is_underdetermination_not_the_frame() -> None:
    baseline, shadowed, merged = _run_pair()

    assert baseline.terminal is LaneBTerminal.compiler_failure
    assert "underdetermined" in (baseline.compiler_codes or ())

    # Both frames arrived and the compiler consumed rather than refused them.
    assert len(merged["reference_frames"]) == 2
    assert shadowed.terminal is LaneBTerminal.compiler_failure
    assert "underdetermined" in (shadowed.compiler_codes or ())


def test_a_typed_static_frame_never_demands_a_specialized_model() -> None:
    _, shadowed, _ = _run_pair()

    assert shadowed.terminal is not LaneBTerminal.compiler_unsupported
    assert "requires_specialized_model" not in (shadowed.compiler_codes or ())


def test_the_frame_supplies_no_free_body_and_nothing_solves() -> None:
    # A frame states orientation, never forces.  With no normal or friction
    # record and no carrier allowed to invent one, the family must stay
    # unsolved — a solve here would mean something fabricated a force.
    _, shadowed, _ = _run_pair()

    assert shadowed.terminal is not LaneBTerminal.solved
    assert shadowed.answer_value_si is None
