"""Stage 7 Lane B: full-pipeline privacy-safe failure matrix and strict gate.

The matrix aggregates one real execution of

    projection → validate → normalize → authorize → compile → solve → verify

into closed terminals, a closed failure taxonomy, and identity-stripped
diagnostic paths.  It never records a case ID, family, split, problem text,
expected terminal, expected answer, source quote, or full equation, and it
never compares against a gold expectation — that belongs to the gold domain
after the runtime snapshot is frozen.
"""

from __future__ import annotations

import json

import pytest

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_failure_matrix import (
    PIPELINE_MATRIX_VERSION,
    build_pipeline_failure_matrix,
)
from evaluation.phase56_stage7.lane_b_runner import canonical_diagnostic_path
from evaluation.phase56_stage7.redaction import assert_privacy_safe_artifact
from support.phase56_stage7_corpus_fixtures import build_case


def _cases(count: int = 6, *, figure_level: str = "none"):
    out = []
    for index in range(count):
        record = build_case(
            index=index,
            split="public_dev",
            family="single_particle_newton",
            future_terminal="accepted",
            with_answer=True,
            figure_level=figure_level,
        )
        record["split"] = PublicSplit.public_dev
        out.append(PublicCorpusCaseV1(**record))
    return out


# --------------------------------------------------------------------------
# Identity stripping
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, expected",
    [
        ("quantities.qty_mu.interval_id", "quantities.*.interval_id"),
        ("events.instant.interval_ids", "events.*.interval_ids"),
        ("motion_intervals.segment_2.start_event_id", "motion_intervals.*.start_event_id"),
        ("geometry.geo_over_pulley", "geometry.*"),
        ("interactions.rel_collision", "interactions.*"),
        ("queries.qry_q1.target", "queries.*.target"),
        ("quantities.7.raw_value", "quantities.N.raw_value"),
        ("equations", "equations"),
        (None, ""),
    ],
)
def test_diagnostic_paths_keep_the_field_and_drop_the_identity(path, expected) -> None:
    assert canonical_diagnostic_path(path) == expected


def test_a_corpus_role_never_survives_into_a_diagnostic_path() -> None:
    for role in ("mu", "theta", "collision", "over_pulley", "instant", "segment_2"):
        assert role not in canonical_diagnostic_path(
            f"quantities.qty_{role}.interval_id"
        )


# --------------------------------------------------------------------------
# Matrix shape and privacy
# --------------------------------------------------------------------------


def test_matrix_counts_every_case_exactly_once() -> None:
    matrix = build_pipeline_failure_matrix(_cases(6))
    assert matrix.version == PIPELINE_MATRIX_VERSION
    assert matrix.total_cases == 6
    assert sum(dict(matrix.terminal_counts).values()) == 6
    assert sum(dict(matrix.taxonomy_counts).values()) == 6


def test_every_terminal_maps_to_a_closed_taxonomy_bucket() -> None:
    matrix = build_pipeline_failure_matrix(_cases(4))
    assert "UNCLASSIFIED" not in dict(matrix.taxonomy_counts)


def test_a_figure_dependent_case_is_a_neutral_terminal_not_an_execution() -> None:
    matrix = build_pipeline_failure_matrix(_cases(3, figure_level="required"))
    assert matrix.executed_cases == 0
    assert dict(matrix.terminal_counts) == {"needs_figure": 3}
    assert dict(matrix.taxonomy_counts) == {"BLOCKED_NEEDS_FIGURE": 3}


def test_matrix_reports_the_preserved_structural_counts() -> None:
    matrix = build_pipeline_failure_matrix(_cases(4))
    structures = dict(matrix.structure_counts)
    assert structures["projected"] == 4
    assert structures["known_symbols"] > 0
    assert structures["unknown_symbols"] == 4


def test_matrix_artifact_is_privacy_safe_and_serialisable() -> None:
    payload = build_pipeline_failure_matrix(_cases(5)).as_dict()
    assert_privacy_safe_artifact(payload)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    # No corpus identity, gold expectation, or problem sentence may appear.
    for marker in ("fx_public_dev", "single_particle_newton", "연습 상황", "public_dev"):
        assert marker not in text


def test_matrix_never_records_a_reference_answer() -> None:
    cases = _cases(4)
    payload = build_pipeline_failure_matrix(cases).as_dict()
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for case in cases:
        for answer in case.gold.answers:
            assert str(answer.numeric) not in text
            assert answer.reference_expression not in text


def test_the_matrix_is_deterministic_for_the_same_input() -> None:
    first = build_pipeline_failure_matrix(_cases(5)).as_dict()
    second = build_pipeline_failure_matrix(_cases(5)).as_dict()
    assert first == second


def test_gold_metadata_does_not_change_the_matrix() -> None:
    baseline = build_pipeline_failure_matrix(_cases(4)).as_dict()
    tampered = [
        case.model_copy(update={"family": "coriolis_relative_motion", "difficulty": 5})
        for case in _cases(4)
    ]
    assert build_pipeline_failure_matrix(tampered).as_dict() == baseline
