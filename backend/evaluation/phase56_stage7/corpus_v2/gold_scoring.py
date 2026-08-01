"""Score a frozen v2 shadow runtime snapshot, in the gold domain.

This module is the **gold / scoring domain** of the shadow evaluation.  It runs
only after the runtime phase is complete and its snapshot is immutable: the
input is a `ShadowRuntimeSnapshotV2` whose digest has already been computed, and
this module recomputes that digest before reading a single gold member.  It
never compiles, never solves, never verifies, and never projects — a scorer that
could re-run the pipeline could re-run it having seen the answer.

The comparison itself is not written here.  It is `compare_answer_to_gold` from
the official strict scorer, unchanged, so a shadow "correct" means exactly what
an official one means.  There is deliberately no v2 comparator, no v2 tolerance
and no v2 unit policy to soften.

What this module adds is the accounting the first shadow runner did not have:
`correct`, `wrong` and `unscored` are three separate counts, and a solved
context that nobody could compare lands in the third rather than vanishing into
"wrong: 0".  A context whose expected class has no answer at all and which
solved anyway is a `forbidden_class_solve` — the shadow-side name for the
hard-safety failure the official gate calls a silent solve.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from evaluation.phase56_stage7.contracts import Stage7ExpectedTerminal
from evaluation.phase56_stage7.corpus_semantics import (
    scope_adjusted_expected_terminal,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (
    ShadowRuntimeRecordV2,
    ShadowRuntimeSnapshotV2,
    scoring_handle,
)
from evaluation.phase56_stage7.lane_b_scoring import (
    AnswerVerdict,
    compare_answer_to_gold,
    gold_scoring_registry,
)


CORPUS_V2_GOLD_SCORING_VERSION = "phase56-stage7-corpus-v2-gold-scoring-v1"


class GoldScoringRefused(RuntimeError):
    """The scorer declined to score something it could not score honestly."""


@dataclass(frozen=True, slots=True)
class ShadowGoldCaseV1:
    """What the scorer is allowed to know about one context's expectation.

    A deliberately small window on the gold: the expected class, and the answer
    when the class has one.  No case id, no family, no split, no problem text,
    no failure code — none of which a comparison needs, and all of which a
    comparison that had them could be steered by.
    """

    expected_terminal: Stage7ExpectedTerminal
    gold_answer: Any | None = None


class ContextVerdict(str, Enum):
    correct = "correct"
    wrong = "wrong"
    unscored = "unscored"
    not_solved = "not_solved"
    forbidden_class_solve = "forbidden_class_solve"


@dataclass(frozen=True, slots=True)
class ScoredContextV1:
    """One context's scored outcome, paired back to its runtime record."""

    scoring_handle: str
    cohort_digest: str
    augmented: bool
    newly_solved: bool
    regressed: bool
    shadow_solved: bool
    verdict: ContextVerdict
    defect: str | None = None

    @property
    def correct(self) -> bool:
        return self.verdict is ContextVerdict.correct

    @property
    def wrong(self) -> bool:
        return self.verdict is ContextVerdict.wrong

    @property
    def unscored(self) -> bool:
        return self.verdict in (
            ContextVerdict.unscored,
            ContextVerdict.forbidden_class_solve,
        )


def build_gold_index(
    cases: Sequence[Any],
    context_indices: Sequence[int] | None = None,
    *,
    original_v1_archive_sha256: str,
) -> dict[str, ShadowGoldCaseV1]:
    """Pair the gold to the frozen runtime records, by opaque handle.

    Called only after the snapshot is frozen.  `context_indices` defaults to
    *every* position in the corpus, and that default is the safe one: an index
    built over only the positions the runtime happened to record is an index
    that agrees with the snapshot about which contexts exist, so a context
    dropped from the snapshot is dropped from the pairing too and scores
    nothing rather than failing.  Building over the whole corpus makes the two
    sets independent, which is what lets `gold_pairing_failures` below compare
    them and find a disagreement.

    The expected class comes from `scope_adjusted_expected_terminal`, the same
    derivation the official strict scorer uses — a shadow run must not be able
    to disagree with the official gate about which class a case is in.
    """

    positions = (
        range(len(cases)) if context_indices is None else tuple(context_indices)
    )
    index: dict[str, ShadowGoldCaseV1] = {}
    for position in positions:
        case = cases[position]
        expected = scope_adjusted_expected_terminal(case, case_index=position)
        answers = case.gold.answers
        gold_answer = (
            answers[0]
            if expected is Stage7ExpectedTerminal.accepted and len(answers) == 1
            else None
        )
        index[
            scoring_handle(
                original_v1_archive_sha256=original_v1_archive_sha256,
                context_index=position,
            )
        ] = ShadowGoldCaseV1(expected_terminal=expected, gold_answer=gold_answer)
    return index


def _score_one(
    record: ShadowRuntimeRecordV2,
    gold: ShadowGoldCaseV1 | None,
    registry: Any,
) -> ScoredContextV1:
    def built(verdict: ContextVerdict, defect: str | None = None) -> ScoredContextV1:
        return ScoredContextV1(
            scoring_handle=record.scoring_handle,
            cohort_digest=record.cohort_digest,
            augmented=record.augmented,
            newly_solved=record.newly_solved,
            regressed=record.regressed,
            shadow_solved=record.shadow_solved,
            verdict=verdict,
            defect=defect,
        )

    if not record.shadow_solved:
        return built(ContextVerdict.not_solved)

    # A solved context with no gold binding is unscored.  It is never a pass:
    # the whole defect this module exists to close was a solve counted as
    # not-wrong because nothing had compared it.
    if gold is None:
        return built(ContextVerdict.unscored, "gold_case_unavailable")

    # A class the corpus says has no answer, solved anyway.  The same
    # hard-safety failure the official gate calls a silent solve, named on the
    # shadow side so it cannot be reported as a yield.
    if gold.expected_terminal is not Stage7ExpectedTerminal.accepted:
        return built(ContextVerdict.forbidden_class_solve, "solved_blocked_class")
    if gold.gold_answer is None:
        return built(ContextVerdict.unscored, "gold_answer_unavailable")

    # The answer must be the answer to the question that was asked.  An
    # unbound solve is not comparable evidence, whatever number it carries.
    if not record.query_binding_complete:
        return built(ContextVerdict.wrong, "query_binding_incomplete")

    comparison = compare_answer_to_gold(
        registry,
        gold.gold_answer,
        value_si=record.answer_value_si,
        unit=record.answer_unit,
    )
    defect = comparison.defect.value if comparison.defect is not None else None
    if comparison.verdict is AnswerVerdict.correct:
        return built(ContextVerdict.correct, defect)
    if comparison.verdict is AnswerVerdict.wrong:
        return built(ContextVerdict.wrong, defect)
    return built(ContextVerdict.unscored, defect)


def gold_pairing_failures(
    snapshot: ShadowRuntimeSnapshotV2,
    gold_by_handle: Mapping[str, ShadowGoldCaseV1],
) -> tuple[str, ...]:
    """Where the corpus and the snapshot disagree about which contexts exist.

    Two independently built sets: the gold index is derived from the corpus the
    scorer holds, and the ledger from the run the snapshot recorded.  They must
    be the same set.  When they are not, one of them lost a context, and which
    one is exactly the question a run that silently skipped something could not
    previously be asked.
    """

    failures: list[str] = []
    expected = set(snapshot.expected_handles)
    paired = set(gold_by_handle)
    if expected - paired:
        failures.append("shadow_expected_handle_missing")
    if paired - expected:
        failures.append("shadow_unknown_handle_present")
    if len(gold_by_handle) != snapshot.expected_context_count:
        failures.append("shadow_context_count_mismatch")
    return tuple(sorted(set(failures)))


def score_shadow_snapshot(
    snapshot: ShadowRuntimeSnapshotV2,
    gold_by_handle: Mapping[str, ShadowGoldCaseV1],
) -> tuple[ScoredContextV1, ...]:
    """Score a frozen snapshot.  Refuses one whose digest no longer matches.

    The digest check is the sequencing proof: a snapshot that was edited after
    it was frozen — by a scorer feeding a result back, or by anything else —
    cannot present the hash it was sealed with.

    The completeness check is the other half, and it is newer.  A snapshot can
    be perfectly self-consistent and still be a measurement of a subset nobody
    chose, because the contexts it dropped are missing from its own accounting
    as well.  So the ledger is re-checked here, against the scorer's own idea
    of what the corpus contains, before a single answer is compared.
    """

    if not snapshot.digest_is_intact():
        raise GoldScoringRefused(
            "runtime snapshot digest does not match its contents; "
            "the snapshot was not frozen before scoring"
        )
    incomplete = snapshot.completeness_failures()
    if incomplete:
        raise GoldScoringRefused(
            "the runtime snapshot does not account for every context: "
            + ",".join(incomplete)
        )
    registry = gold_scoring_registry()
    return tuple(
        _score_one(record, gold_by_handle.get(record.scoring_handle), registry)
        for record in snapshot.records
    )


@dataclass(frozen=True, slots=True)
class ShadowScoreTotals:
    """The counts a shadow report is built from.  Three, never two."""

    newly_solved: int = 0
    newly_solved_correct: int = 0
    newly_solved_wrong: int = 0
    newly_solved_unscored: int = 0
    all_shadow_correct: int = 0
    all_shadow_wrong: int = 0
    all_shadow_unscored: int = 0
    forbidden_class_solve: int = 0
    regressed: int = 0
    query_binding_mismatch: int = 0
    defect_counts: tuple[tuple[str, int], ...] = ()
    cohort_yield: tuple[tuple[str, int], ...] = ()


def totals(scored: tuple[ScoredContextV1, ...]) -> ShadowScoreTotals:
    defects: Counter[str] = Counter()
    yields: Counter[str] = Counter()
    for row in scored:
        if row.defect:
            defects[row.defect] += 1
        # A cohort's yield is a *correct* new solve.  Counting a new solve that
        # was never compared would be counting the gap as the gain.
        if row.newly_solved and row.correct:
            yields[row.cohort_digest] += 1
    return ShadowScoreTotals(
        newly_solved=sum(1 for row in scored if row.newly_solved),
        newly_solved_correct=sum(1 for row in scored if row.newly_solved and row.correct),
        newly_solved_wrong=sum(1 for row in scored if row.newly_solved and row.wrong),
        newly_solved_unscored=sum(
            1 for row in scored if row.newly_solved and row.unscored
        ),
        all_shadow_correct=sum(1 for row in scored if row.correct),
        all_shadow_wrong=sum(1 for row in scored if row.wrong),
        all_shadow_unscored=sum(1 for row in scored if row.unscored),
        forbidden_class_solve=sum(
            1 for row in scored if row.verdict is ContextVerdict.forbidden_class_solve
        ),
        regressed=sum(1 for row in scored if row.regressed),
        query_binding_mismatch=sum(
            1 for row in scored if row.defect == "query_binding_incomplete"
        ),
        defect_counts=tuple(sorted(defects.items())),
        cohort_yield=tuple(sorted(yields.items())),
    )


__all__ = [
    "CORPUS_V2_GOLD_SCORING_VERSION",
    "ContextVerdict",
    "GoldScoringRefused",
    "ScoredContextV1",
    "ShadowGoldCaseV1",
    "ShadowScoreTotals",
    "build_gold_index",
    "gold_pairing_failures",
    "score_shadow_snapshot",
    "totals",
]
