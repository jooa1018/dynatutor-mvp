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

**This module is the runtime phase and it cannot score.**  It takes no
comparator, reaches no expected answer, and returns a runtime record whose type
has no field an answer could be written into.  Scoring happens afterwards, in
`gold_scoring`, against the frozen snapshot these records are sealed into.  The
earlier shape of this function accepted an optional `compare_answer` callback
and the public runner never passed one, which is how a run that had compared
nothing came to be reported as `wrong: 0` — a number that meant "not scored"
while reading as "nothing was wrong".  Removing the hook removes the possibility
of that report, rather than documenting it.
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
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (
    ShadowRuntimeRecordV2,
    digest_of,
    scoring_handle,
)


CORPUS_V2_SHADOW_RUNNER_VERSION = "phase56-stage7-corpus-v2-shadow-runner-v2"


class ShadowRunRefused(RuntimeError):
    """The shadow run declined to measure something it could not measure honestly."""


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "value", value) if not isinstance(value, str) else value


def run_shadow_context(
    *,
    draft_payload: Mapping[str, Any],
    augmentation: CorpusV2AugmentationV1,
    run: Callable[[Mapping[str, Any]], Any],
    problem_text: str | None = None,
    original_v1_archive_sha256: str,
    context_index: int,
) -> ShadowRuntimeRecordV2:
    """One context, run twice, recorded as the move between two rungs.

    `run` is the caller's binding to the real pipeline; it receives a Draft
    payload and returns a lane result.  `problem_text` reaches the projection so
    an authored source quote can be aligned — or refused — against the source's
    own words; nothing else reads it.

    The returned record carries the runtime's own answer, unit and binding so a
    later gold pass can compare them.  It carries no expectation of any kind.
    """

    baseline_result = run(draft_payload)
    augmented_payload = project_augmentation(
        draft_payload, augmentation, problem_text=problem_text
    )
    shadow_result = run(augmented_payload)

    baseline_rung = progress_rung(baseline_result)
    shadow_rung = progress_rung(shadow_result)
    shadow_solved = shadow_rung is ProgressRung.solved_and_verified
    baseline_solved = baseline_rung is ProgressRung.solved_and_verified

    query_symbol = getattr(shadow_result, "answer_query_symbol_id", None)
    query_subject = getattr(shadow_result, "query_subject_id", None)
    component = _text(getattr(shadow_result, "answer_component", None))
    binding_complete = query_symbol is not None and query_subject is not None

    return ShadowRuntimeRecordV2(
        scoring_handle=scoring_handle(
            original_v1_archive_sha256=original_v1_archive_sha256,
            context_index=context_index,
        ),
        cohort_digest=structural_cohort(draft_payload).digest,
        augmented=not augmentation.is_empty,
        carriers_supplied=tuple(
            name for name, count in augmentation.carrier_counts() if count
        ),
        baseline_rung=baseline_rung.value,
        shadow_rung=shadow_rung.value,
        baseline_solved=baseline_solved,
        shadow_solved=shadow_solved,
        answer_value_si=getattr(shadow_result, "answer_value_si", None),
        answer_unit=getattr(shadow_result, "answer_unit", None),
        answer_component=component,
        # The binding is digested rather than published: the scorer needs to
        # know whether the answer was bound to the question that was asked, and
        # a reader of the aggregate has no business learning the symbol names.
        query_binding_digest=digest_of([query_symbol, query_subject, component]),
        query_binding_complete=binding_complete,
        candidate_count=int(getattr(shadow_result, "candidate_count", 0) or 0),
        verified_candidate_count=int(
            getattr(shadow_result, "verified_candidate_count", 0) or 0
        ),
        applied_law_digest=digest_of(
            sorted(str(item) for item in (getattr(shadow_result, "applied_law_ids", ()) or ()))
        ),
        provenance_digest=digest_of(
            sorted(str(name) for name, count in augmentation.carrier_counts() if count)
        ),
        runtime_error_category=_text(getattr(shadow_result, "stage_exception", None)),
    )


def assert_no_regression(results: Sequence[ShadowRuntimeRecordV2]) -> None:
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


def assert_no_unaugmented_movement(results: Sequence[ShadowRuntimeRecordV2]) -> None:
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


def rung_delta(result: ShadowRuntimeRecordV2) -> int:
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
