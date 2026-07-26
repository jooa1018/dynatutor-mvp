"""Profile feasibility: the ranking instrument is measured, not assumed.

The instrument's one job is to keep the next-package decision honest: a
profile's deep classes are reachable only through its own applied
transaction, an unbuilt profile's population reads
``profile_transaction_not_formable``, and every class of the closed
vocabulary is proven producible by a positive control — a zero without a
control would be a blind spot, not a measurement.

Fixtures are independently authored.  Nothing reads a case ID, family,
split, expected terminal, or expected answer inside the paths under test.
"""

from __future__ import annotations

import hashlib

import pytest

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_runner import LaneBResult, LaneBTerminal
from evaluation.phase56_stage7.profile_feasibility import (
    PROFILE_FEASIBILITY_VERSION,
    FeasibilityClass,
    classify_lane_result,
    measure_profile_feasibility,
)
from support.phase56_stage7_corpus_fixtures import build_case


def _result(terminal: LaneBTerminal, equation_count: int = 0) -> LaneBResult:
    return LaneBResult(
        execution_token="0" * 32,
        terminal=terminal,
        equation_count=equation_count,
    )


# --------------------------------------------------------------------------
# Positive controls: every class of the closed vocabulary is producible
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("terminal", "equation_count", "expected"),
    [
        (LaneBTerminal.needs_figure, 0, FeasibilityClass.validation_blocked),
        (
            LaneBTerminal.needs_confirmation,
            0,
            FeasibilityClass.validation_blocked,
        ),
        (
            LaneBTerminal.insufficient_information,
            0,
            FeasibilityClass.validation_blocked,
        ),
        (
            LaneBTerminal.validation_rejected,
            0,
            FeasibilityClass.validation_blocked,
        ),
        (
            LaneBTerminal.normalization_rejected,
            0,
            FeasibilityClass.normalization_blocked,
        ),
        (
            LaneBTerminal.authorization_failed,
            0,
            FeasibilityClass.authorization_blocked,
        ),
        (LaneBTerminal.compiler_failure, 0, FeasibilityClass.compiler_no_equation),
        (
            LaneBTerminal.compiler_failure,
            3,
            FeasibilityClass.compiler_underdetermined,
        ),
        (
            LaneBTerminal.compiler_unsupported,
            0,
            FeasibilityClass.precise_unsupported_reachable,
        ),
        (
            LaneBTerminal.verified_unsupported,
            0,
            FeasibilityClass.verified_deferred_reachable,
        ),
        (LaneBTerminal.solve_rejected, 2, FeasibilityClass.solver_rejected),
        (
            LaneBTerminal.verification_rejected,
            2,
            FeasibilityClass.verification_rejected,
        ),
        (LaneBTerminal.solved, 2, FeasibilityClass.verified_solve_reachable),
        (
            LaneBTerminal.projection_rejected,
            0,
            FeasibilityClass.profile_transaction_not_formable,
        ),
    ],
)
def test_every_class_is_producible_and_exact(terminal, equation_count, expected):
    assert classify_lane_result(_result(terminal, equation_count)) is expected


def test_the_class_vocabulary_is_closed():
    assert {item.value for item in FeasibilityClass} == {
        "profile_transaction_not_formable",
        "validation_blocked",
        "normalization_blocked",
        "authorization_blocked",
        "compiler_no_equation",
        "compiler_underdetermined",
        "solver_rejected",
        "verification_rejected",
        "verified_solve_reachable",
        "verified_deferred_reachable",
        "precise_unsupported_reachable",
    }


# --------------------------------------------------------------------------
# End to end: credit goes only through an applied transaction
# --------------------------------------------------------------------------

PROBLEM_TEXT = (
    "연습 상황: 돌을 지면 위에서 위로 던진다. 처음 속력은 9 m/s 이고 "
    "처음 높이는 2 m 이다. 공기 저항은 무시한다. 돌이 최고점에 "
    "도달할 때까지 걸리는 시간을 구하시오."
)


def _free_flight_case() -> PublicCorpusCaseV1:
    record = build_case(
        index=17,
        split="public_dev",
        family="single_particle_newton",
        future_terminal="accepted",
        with_answer=True,
    )
    record["split"] = PublicSplit.public_dev
    record["problem_text"] = PROBLEM_TEXT
    record["problem_hash"] = hashlib.sha256(
        PROBLEM_TEXT.encode("utf-8")
    ).hexdigest()
    gold = record["gold"]
    gold["entities"] = [
        {"role": "stone", "kind": "particle", "label": "돌"},
        {"role": "ground", "kind": "surface", "label": "지면"},
    ]
    gold["motion_segments"] = [
        {
            "role": "fall",
            "order": 1,
            "actor_roles": ["stone"],
            "motion_model": "projectile_free_flight",
            "relevance": "target",
            "start_event_role": "go",
            "end_event_role": "top",
        }
    ]
    gold["events"] = [
        {
            "role": "go",
            "kind": "release",
            "subject_roles": ["stone"],
            "segment_role": "fall",
            "evidence_quote": None,
        },
        {
            "role": "top",
            "kind": "comes_to_rest",
            "subject_roles": ["stone"],
            "segment_role": "fall",
            "evidence_quote": None,
        },
    ]
    gold["explicit_facts"] = [
        {
            "role": "v0",
            "semantic_key": "initial_velocity",
            "raw_value": "9",
            "raw_unit": "m/s",
            "evidence_quote": "처음 속력은 9 m/s",
            "subject_role": "stone",
            "segment_role": "fall",
            "event_role": "go",
            "temporal_role": "initial",
            "direction": "upward",
            "relevance": "solver_input",
            "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        },
        {
            "role": "h0",
            "semantic_key": "height",
            "raw_value": "2",
            "raw_unit": "m",
            "evidence_quote": "처음 높이는 2 m",
            "subject_role": "stone",
            "segment_role": "fall",
            "event_role": "go",
            "temporal_role": "initial",
            "direction": "upward",
            "relevance": "solver_input",
            "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        },
    ]
    gold["relations"] = []
    gold["assumption_proposals"] = [
        {
            "role": "air",
            "kind": "no_air_resistance",
            "subject_role": "stone",
            "segment_role": "fall",
            "supporting_quote": "공기 저항은 무시한다",
            "server_value_only": True,
        },
        {
            "role": "grav",
            "kind": "constant_gravity",
            "subject_role": "stone",
            "segment_role": "fall",
            "supporting_quote": None,
            "server_value_only": True,
        },
    ]
    gold["queries"] = [
        {
            "role": "q1",
            "output_key": "time",
            "subject_role": "stone",
            "segment_role": "fall",
            "component": "magnitude",
            "event_role": "top",
        }
    ]
    gold["answers"] = [
        {
            "query_role": "q1",
            "numeric": 0.9174,
            "unit": "s",
            "tolerance_abs": 0.01,
            "reference_expression": "v0/g",
        }
    ]
    return PublicCorpusCaseV1(**record)


def test_an_applied_transaction_reaches_a_deep_class_end_to_end():
    """The free-flight fixture credits `free_flight_gravity` with its real
    pipeline class, and every other applicable profile stays not-formable."""

    matrix = measure_profile_feasibility([_free_flight_case()])
    assert matrix.version == PROFILE_FEASIBILITY_VERSION
    assert matrix.context_count == 1
    rows = {row.profile_id: row for row in matrix.rows}
    assert "free_flight_gravity" in rows
    free_flight = dict(rows["free_flight_gravity"].class_counts)
    deep = {
        FeasibilityClass.compiler_no_equation.value,
        FeasibilityClass.compiler_underdetermined.value,
        FeasibilityClass.solver_rejected.value,
        FeasibilityClass.verified_solve_reachable.value,
    }
    assert sum(free_flight.get(name, 0) for name in deep) == 1
    assert (
        free_flight.get(
            FeasibilityClass.profile_transaction_not_formable.value, 0
        )
        == 0
    )
    for profile_id, row in rows.items():
        if profile_id == "free_flight_gravity":
            continue
        counts = dict(row.class_counts)
        assert counts == {
            FeasibilityClass.profile_transaction_not_formable.value: (
                row.applicable_contexts
            )
        }


def test_a_context_without_a_transaction_is_not_formable_everywhere():
    case = PublicCorpusCaseV1(
        **{
            **build_case(
                index=19,
                split="public_dev",
                family="single_particle_newton",
                future_terminal="accepted",
                with_answer=True,
            ),
            "split": PublicSplit.public_dev,
        }
    )
    matrix = measure_profile_feasibility([case])
    assert matrix.context_count == 1
    for row in matrix.rows:
        counts = dict(row.class_counts)
        assert counts == {
            FeasibilityClass.profile_transaction_not_formable.value: (
                row.applicable_contexts
            )
        }
        # The as-is terminal table still shows how far the context gets.
        assert sum(dict(row.as_is_terminal_counts).values()) == (
            row.applicable_contexts
        )


def test_the_matrix_is_deterministic_and_counts_only():
    cases = [_free_flight_case()]
    first = measure_profile_feasibility(cases)
    second = measure_profile_feasibility(cases)
    assert first == second
    payload = first.as_dict()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert isinstance(key, str)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        else:
            assert isinstance(node, (str, int))

    walk(payload)


def test_gold_metadata_contributes_nothing():
    """The same structure under other labels, with no answer, measures alike."""

    first = _free_flight_case()
    payload = _free_flight_case().model_dump(mode="python")
    payload["case_id"] = "fx_other_feasibility_identity"
    payload["family"] = "totally_different_family"
    payload["tags"] = ["other", "labels"]
    payload["gold"]["answers"] = []
    second = PublicCorpusCaseV1(**payload)
    assert measure_profile_feasibility([first]) == measure_profile_feasibility(
        [second]
    )


def test_the_production_path_does_not_import_the_instrument():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for base in ("engine", "app"):
        for path in (root / base).rglob("*.py"):
            if "profile_feasibility" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []
