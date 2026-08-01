"""Run the real pipeline over v2-augmented Drafts, twice, and compare.

A shadow evaluation is only evidence if the two runs differ in exactly one
thing.  So every context is run twice through the *same* deterministic
compiler, solver and verifier — once on its v1 Draft and once on the same Draft
with the augmentation attached — and the pair is reported as a rung-to-rung
move.  Nothing here selects a different law, relaxes a check, or reads an
answer to decide what to do.

The safety instrumentation is the v1 instrumentation, unchanged.  A shadow run
that produced a wrong answer would be exactly as much of a defect as an
official one, and is counted as one.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from evaluation.phase56_stage7.authority_census import (
    ProgressRung,
    progress_rung,
    rung_index,
    structural_cohort,
)
from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation
from evaluation.phase56_stage7.corpus_v2.records import CorpusV2AugmentationV1
from evaluation.phase56_stage7.corpus_v2.reporting import ShadowContextResultV1


CORPUS_V2_SHADOW_RUNNER_VERSION = "phase56-stage7-corpus-v2-shadow-runner-v1"


class ShadowRunRefused(RuntimeError):
    """The shadow run declined to measure something it could not measure honestly."""


def run_shadow_context(
    *,
    draft_payload: Mapping[str, Any],
    augmentation: CorpusV2AugmentationV1,
    run: Callable[[Mapping[str, Any]], Any],
    compare_answer: Callable[[Any], bool | None] | None = None,
) -> ShadowContextResultV1:
    """One context, run twice, reported as the move between two rungs.

    `run` is the caller's binding to the real pipeline; it receives a Draft
    payload and returns a lane result.  `compare_answer` is the caller's gold
    comparison and returns `True` for correct, `False` for wrong, and `None`
    when nothing could be compared — the third case is a first-class outcome,
    not a pass.
    """

    baseline_result = run(draft_payload)
    augmented_payload = project_augmentation(draft_payload, augmentation)
    shadow_result = run(augmented_payload)

    baseline_rung = progress_rung(baseline_result)
    shadow_rung = progress_rung(shadow_result)
    shadow_solved = shadow_rung is ProgressRung.solved_and_verified
    baseline_solved = baseline_rung is ProgressRung.solved_and_verified

    correct: bool | None = None
    if shadow_solved and compare_answer is not None:
        correct = compare_answer(shadow_result)

    return ShadowContextResultV1(
        cohort_digest=structural_cohort(draft_payload).digest,
        augmented=not augmentation.is_empty,
        carriers_supplied=tuple(
            name for name, count in augmentation.carrier_counts() if count
        ),
        baseline_rung=baseline_rung.value,
        shadow_rung=shadow_rung.value,
        baseline_solved=baseline_solved,
        shadow_solved=shadow_solved,
        shadow_correct=bool(correct),
        # A solved context nobody could compare is not correct and not wrong;
        # it is unscored, and it is counted as neither rather than as a pass.
        shadow_wrong=correct is False,
    )


def assert_no_regression(results: Sequence[ShadowContextResultV1]) -> None:
    """Refuse a shadow run in which a carrier took a solve away.

    A v2 carrier is additive by construction, so a context that solved on its
    v1 Draft and does not solve with the carrier attached means the projection
    changed something it had no business changing.
    """

    regressed = [row for row in results if row.regressed]
    if regressed:
        raise ShadowRunRefused(
            f"{len(regressed)} contexts solved before the carrier and not after"
        )


def assert_no_unaugmented_movement(results: Sequence[ShadowContextResultV1]) -> None:
    """Refuse a shadow run in which a context with no carrier moved anyway.

    An empty augmentation projects to an equal Draft, so an unaugmented context
    must land on exactly the rung it started on.  If one moves, the shadow
    pipeline is not the v1 pipeline and no comparison it produces means
    anything.
    """

    for row in results:
        if row.augmented:
            continue
        if row.baseline_rung != row.shadow_rung:
            raise ShadowRunRefused(
                "an unaugmented context changed rung; the shadow run is not "
                "measuring the carrier"
            )


def rung_delta(result: ShadowContextResultV1) -> int:
    """How far the carrier moved this context along the ladder."""

    return rung_index(ProgressRung(result.shadow_rung)) - rung_index(
        ProgressRung(result.baseline_rung)
    )


__all__ = [
    "CORPUS_V2_SHADOW_RUNNER_VERSION",
    "ShadowRunRefused",
    "assert_no_regression",
    "assert_no_unaugmented_movement",
    "run_shadow_context",
    "rung_delta",
]
