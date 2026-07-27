"""Stage 7 Lane B case-level gold scoring.

This module is the **gold / scoring domain**.  Nothing here may be imported by
the runtime, the compiler, the solver, or the verifier, and nothing here runs
until the runtime snapshot is complete and immutable: the scorer is handed the
frozen per-case runtime records and the gold cases, and it only *compares*.

Why case-level.  Counting terminals is not scoring.  The frozen Stage 7 target
is a *distribution over classes* — 81 supported, 12 deferred, 2 unsupported
other, 2 needs-figure, 2 needs-confirmation, 1 insufficient-information — so an
aggregate that happens to total correctly can still be wrong case by case: a
supported problem answered as deferred and a deferred problem silently solved
cancel out in a histogram and are both hard-safety failures.  Every case is
therefore matched to *its own* expected class and checked against the exact
requirements of that class.

Tolerance.  The corpus declares one absolute tolerance per answer, in the
answer's own unit.  That declaration is the frozen contract and the scorer
applies it exactly: expected value and tolerance are converted to SI through
the same registry and compared without an evaluator-invented floor.  Widening a
corpus tolerance because a result missed it would be the evaluator scoring its
own engine.

The expected class comes from `scope_adjusted_expected_terminal`, which reads
the corpus's own declared terminal plus the frozen deferred-family scope.  No
case ID, split, chapter, difficulty, tag, filename, or corpus order takes part,
and the value is never handed back to the runtime.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from engine.mechanics.compiler.contracts import (
    COURSE_SCOPE_DEFERRED_ISSUE_CODES,
)

from evaluation.phase56_stage7.contracts import Stage7ExpectedTerminal
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.corpus_semantics import (
    scope_adjusted_expected_terminal,
)
from evaluation.phase56_stage7.lane_b_runner import LaneBResult, LaneBTerminal


LANE_B_SCORING_VERSION = "phase56-stage7-lane-b-scoring-v1"

# The exact typed compiler codes that prove a *course-scope deferral*.  A
# deferred case must carry one of these; an unsupported-other case must not, so
# the two classes can never be satisfied by each other's evidence.
_DEFERRED_CODE_VALUES: frozenset[str] = frozenset(
    code.value for code in COURSE_SCOPE_DEFERRED_ISSUE_CODES
)

# Every verification check a solved candidate carries must have passed.  An
# `inconclusive` check is not a pass: it is the verifier declining to prove the
# property, which is exactly the state a scored solve may not be in.
_PASSED = "passed"

# The kinds every solved candidate must carry whatever its graph looks like.
#
# "Some check passed" is not verification.  Without a required-kind floor a
# single `("anything", "passed")` would drive both candidate coverage and
# residual verification to 100 %, so an engine that checked nothing but its own
# arithmetic would score identically to one that proved its units, its binding
# and its evidence.  These four are the ones no solved graph can be without:
# the residual of the equations actually used, the dimensional consistency of
# the unknowns, the binding of the answer to the question asked, and the source
# evidence the plan was allowed to rest on.
#
# Beyond this floor the obligation is the *graph's*, not a list's: the runtime
# records what its own plan and candidate required, and the scorer demands that
# whole set.  A graph with events must show its event ordering, one with
# constraints its constraints, one with a time unknown its non-negative time —
# without this scorer hard-coding physics it cannot see.
_REQUIRED_CHECK_KINDS: frozenset[str] = frozenset(
    {
        "equation_residual",
        "unit_consistency",
        "query_binding",
        "source_evidence",
    }
)

_SOLVED_TERMINAL = LaneBTerminal.solved.value
_VERIFIED_UNSUPPORTED_TERMINAL = LaneBTerminal.verified_unsupported.value
_NEEDS_FIGURE_TERMINAL = LaneBTerminal.needs_figure.value
_NEEDS_CONFIRMATION_TERMINAL = LaneBTerminal.needs_confirmation.value
_INSUFFICIENT_TERMINAL = LaneBTerminal.insufficient_information.value

_COMPILER_UNSUPPORTED_TERMINAL = LaneBTerminal.compiler_unsupported.value

# The runtime terminals each expected class may reach.  Deferred and
# unsupported-other overlap on purpose — the *evidence* separates them, not the
# terminal name — and the per-class checks below enforce that.
#
# `unsupported_other` accepts `compiler_unsupported` as well as
# `verified_unsupported`, because otherwise the class is unreachable by
# construction and no correct Stage 7 could ever satisfy it.  The only producer
# of `verified_unsupported` in the compiler path requires a course-scope
# deferred code — which is exactly the evidence that *disqualifies*
# unsupported-other — so an engine that correctly proves a problem out of scope
# at the compiler lands on `compiler_unsupported` and would score
# `terminal_mismatch` forever.  That is the same defect class as the removed
# `strict_lane_b_all_solved`: a gate a correct implementation cannot pass.
#
# This widens no judgement.  The added terminal still has to clear the blocked
# checks below — no numeric answer, no deferred evidence — and now also has to
# carry positive typed evidence that the compiler really refused on scope.
# Measured before landing: both unsupported-other cases currently stop at
# `compiler_failure :: underdetermined`, so this changes no count today; it
# removes a trap that would have fired the moment they were fixed.
_REQUIRED_TERMINALS: dict[Stage7ExpectedTerminal, frozenset[str]] = {
    Stage7ExpectedTerminal.accepted: frozenset({_SOLVED_TERMINAL}),
    Stage7ExpectedTerminal.deferred_unsupported: frozenset(
        {_VERIFIED_UNSUPPORTED_TERMINAL}
    ),
    Stage7ExpectedTerminal.unsupported_other: frozenset(
        {_VERIFIED_UNSUPPORTED_TERMINAL, _COMPILER_UNSUPPORTED_TERMINAL}
    ),
    Stage7ExpectedTerminal.needs_figure: frozenset({_NEEDS_FIGURE_TERMINAL}),
    Stage7ExpectedTerminal.needs_confirmation: frozenset({_NEEDS_CONFIRMATION_TERMINAL}),
    Stage7ExpectedTerminal.insufficient_information: frozenset({_INSUFFICIENT_TERMINAL}),
}


class ScoringFailureReason(str, Enum):
    """Closed, privacy-safe scorer rejection catalogue.

    A scorer that cannot score is a typed FAIL, never a silent partial pass and
    never a raw traceback in the artifact.
    """

    record_count_mismatch = "record_count_mismatch"
    unit_registry_unavailable = "unit_registry_unavailable"
    expected_terminal_underivable = "expected_terminal_underivable"
    gold_answer_shape_invalid = "gold_answer_shape_invalid"


class ScoringFailure(Exception):
    """Fail-closed scoring rejection carrying no corpus content."""

    def __init__(self, reason: ScoringFailureReason) -> None:
        super().__init__(reason.value)
        self.reason = reason

    @property
    def sanitized_reason(self) -> str:
        return self.reason.value


class SupportedDefect(str, Enum):
    """Why one supported case did not score as a clean verified solve.

    Closed vocabulary, counted only.  These names describe *evaluator
    judgements about the runtime record*; none of them can carry case content.
    """

    terminal_not_solved = "terminal_not_solved"
    answer_missing = "answer_missing"
    answer_not_finite = "answer_not_finite"
    query_symbol_unbound = "query_symbol_unbound"
    query_subject_unbound = "query_subject_unbound"
    output_unit_missing = "output_unit_missing"
    unit_dimension_mismatch = "unit_dimension_mismatch"
    unit_unconvertible = "unit_unconvertible"
    candidate_not_unique = "candidate_not_unique"
    verification_check_missing = "verification_check_missing"
    verification_check_not_passed = "verification_check_not_passed"
    verification_check_kind_missing = "verification_check_kind_missing"
    numeric_outside_tolerance = "numeric_outside_tolerance"


class BlockedDefect(str, Enum):
    """Why one non-supported case did not score as its expected safe terminal."""

    terminal_mismatch = "terminal_mismatch"
    deferred_evidence_missing = "deferred_evidence_missing"
    unsupported_other_used_deferred_evidence = (
        "unsupported_other_used_deferred_evidence"
    )
    numeric_answer_present = "numeric_answer_present"
    unsupported_reason_missing = "unsupported_reason_missing"


@dataclass(frozen=True, slots=True)
class SupportedAnswerScore:
    """Answer scoring restricted to the supported class.

    `unscored` is a first-class failure, not an abstention: a supported case
    whose solved output could not be compared has not been shown correct, and
    the strict gate treats it exactly as it treats a wrong one.
    """

    scored: int
    correct: int
    wrong: int
    unscored: int
    # The subset of `unscored` that actually produced a solved output nobody
    # could compare.  The rest of `unscored` is the yield gap — supported cases
    # the engine honestly declined — which is a capability shortfall, not a
    # safety signal.  Keeping the two apart is what lets safety and yield stay
    # independent verdicts.
    solved_but_unscored: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "scored": self.scored,
            "correct": self.correct,
            "wrong": self.wrong,
            "unscored": self.unscored,
            "solved_but_unscored": self.solved_but_unscored,
        }


@dataclass(frozen=True, slots=True)
class LaneBScorecard:
    """Case-level comparison of the frozen runtime against the frozen target."""

    version: str
    total_cases: int
    expected_counts: tuple[tuple[str, int], ...]
    actual_terminal_counts: tuple[tuple[str, int], ...]
    terminal_mapping_matches: int
    supported_expected: int
    supported_solved: int
    supported_correct: int
    supported_wrong: int
    supported_unscored: int
    supported_solved_unscored: int
    supported_defect_counts: tuple[tuple[str, int], ...]
    deferred_expected: int
    deferred_matched: int
    unsupported_other_expected: int
    unsupported_other_matched: int
    needs_figure_expected: int
    needs_figure_matched: int
    needs_confirmation_expected: int
    needs_confirmation_matched: int
    insufficient_information_expected: int
    insufficient_information_matched: int
    blocked_defect_counts: tuple[tuple[str, int], ...]
    # Every blocked class, not only the deferred one.  A `needs_figure`,
    # `needs_confirmation`, `insufficient_information` or `unsupported_other`
    # case that comes back `solved` is fabricating an answer to a problem the
    # contract says has none — the same hard-safety failure as a silently
    # solved deferred case, and it must not be invisible just because it lands
    # in a different class.
    blocked_silent_solves: int
    # A blocked case that reached its correct safe terminal and *still* carries
    # a numeric answer.  The terminal is right and the payload is not.
    blocked_numeric_answers: int
    unit_dimension_matches: int
    query_binding_matches: int
    direction_sign_matches: int
    candidate_coverage_matches: int
    residual_verification_matches: int
    deferred_silent_solves: int
    supported_downgraded_to_unsupported: int

    @property
    def terminal_mapping_accuracy(self) -> float:
        return _fraction(self.terminal_mapping_matches, self.total_cases)

    @property
    def answer_accuracy(self) -> float:
        return _fraction(self.supported_correct, self.supported_expected)

    @property
    def unit_dimension_accuracy(self) -> float:
        return _fraction(self.unit_dimension_matches, self.supported_expected)

    @property
    def query_binding_accuracy(self) -> float:
        return _fraction(self.query_binding_matches, self.supported_expected)

    @property
    def direction_sign_accuracy(self) -> float:
        return _fraction(self.direction_sign_matches, self.supported_expected)

    @property
    def candidate_coverage(self) -> float:
        return _fraction(self.candidate_coverage_matches, self.supported_expected)

    @property
    def residual_verification(self) -> float:
        return _fraction(self.residual_verification_matches, self.supported_expected)

    @property
    def answer_score(self) -> SupportedAnswerScore:
        return SupportedAnswerScore(
            scored=self.supported_correct + self.supported_wrong,
            correct=self.supported_correct,
            wrong=self.supported_wrong,
            unscored=self.supported_unscored,
            solved_but_unscored=self.supported_solved_unscored,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "total_cases": self.total_cases,
            "expected_counts": dict(self.expected_counts),
            "actual_terminal_counts": dict(self.actual_terminal_counts),
            "terminal_mapping_matches": self.terminal_mapping_matches,
            "terminal_mapping_accuracy": self.terminal_mapping_accuracy,
            "supported": {
                "expected": self.supported_expected,
                "solved": self.supported_solved,
                "correct": self.supported_correct,
                "wrong": self.supported_wrong,
                "unscored": self.supported_unscored,
                "solved_but_unscored": self.supported_solved_unscored,
                "defect_counts": dict(self.supported_defect_counts),
            },
            "deferred": {
                "expected": self.deferred_expected,
                "matched": self.deferred_matched,
            },
            "unsupported_other": {
                "expected": self.unsupported_other_expected,
                "matched": self.unsupported_other_matched,
            },
            "needs_figure": {
                "expected": self.needs_figure_expected,
                "matched": self.needs_figure_matched,
            },
            "needs_confirmation": {
                "expected": self.needs_confirmation_expected,
                "matched": self.needs_confirmation_matched,
            },
            "insufficient_information": {
                "expected": self.insufficient_information_expected,
                "matched": self.insufficient_information_matched,
            },
            "blocked_defect_counts": dict(self.blocked_defect_counts),
            "blocked_silent_solves": self.blocked_silent_solves,
            "blocked_numeric_answers": self.blocked_numeric_answers,
            "metrics": {
                "answer_accuracy": self.answer_accuracy,
                "unit_dimension_accuracy": self.unit_dimension_accuracy,
                "query_binding_accuracy": self.query_binding_accuracy,
                "direction_sign_accuracy": self.direction_sign_accuracy,
                "candidate_coverage": self.candidate_coverage,
                "residual_verification": self.residual_verification,
            },
            "deferred_silent_solves": self.deferred_silent_solves,
            "supported_downgraded_to_unsupported": (
                self.supported_downgraded_to_unsupported
            ),
        }


def _fraction(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _registry() -> Any:
    try:
        import pint
    except Exception as exc:  # pragma: no cover - dependency is pinned
        raise ScoringFailure(ScoringFailureReason.unit_registry_unavailable) from exc
    try:
        return pint.UnitRegistry()
    except Exception as exc:  # pragma: no cover - registry construction is total
        raise ScoringFailure(ScoringFailureReason.unit_registry_unavailable) from exc


@dataclass(frozen=True, slots=True)
class _SiAnswer:
    value: float
    tolerance: float
    dimensionality: Any


def _gold_answer_in_si(registry: Any, answer: Any) -> _SiAnswer | None:
    """Convert one gold answer and its declared tolerance into SI.

    The tolerance is converted as a true *delta*: the SI distance between the
    declared value and the declared value plus its tolerance.  Converting the
    tolerance as an absolute quantity instead would be correct only for purely
    multiplicative units — for an offset unit it adds the offset to the
    tolerance, so a `± 0.1 degC` declaration would arrive as `± 273.25 K` and
    accept essentially any answer.  That is the same defect class as the
    removed `1e-6` floor, an evaluator silently widening a corpus tolerance,
    reached through the unit path instead of the arithmetic one.

    No floor is applied and no relative slack is invented: a corpus that asks
    for 1e-6 gets 1e-6.
    """

    unit = answer.unit or ""
    try:
        quantity = registry.Quantity(answer.numeric, unit).to_base_units()
        shifted = registry.Quantity(
            answer.numeric + answer.tolerance_abs, unit
        ).to_base_units()
        tolerance = abs(float(shifted.magnitude) - float(quantity.magnitude))
    except Exception:
        return None
    return _SiAnswer(
        value=float(quantity.magnitude),
        tolerance=tolerance,
        dimensionality=quantity.dimensionality,
    )


# How many representable steps of rounding the comparison itself may introduce.
#
# Three roundings stand between the corpus's declaration and the number compared
# here: the SI conversion of the expected value, the SI conversion of the
# tolerance delta, and the subtraction.  Each can move its result by up to half
# an ULP at the operand scale, so a value that is *exactly* on the declared
# boundary can land a couple of ULP outside it and be scored wrong for arithmetic
# reasons alone.
#
# This forgives that, and only that.  An ULP is a property of binary64 — about
# 2.2e-16 relative — not of the corpus, so the allowance cannot widen a declared
# tolerance in any way a result could exploit: it is some eleven orders of
# magnitude below the tightest tolerance the corpus declares.  It is emphatically
# NOT a floor: there is no `1e-6`, no `max(tolerance, ...)`, and no magnitude-
# based slack.  A tolerance of 1e-6 still means 1e-6.
_TOLERANCE_BOUNDARY_ULPS = 4


def _within_declared_tolerance(
    value: float, expected_value: float, tolerance: float
) -> bool:
    """The declared tolerance, plus only the rounding this comparison caused."""

    difference = abs(value - expected_value)
    if difference <= tolerance:
        return True
    scale = max(abs(value), abs(expected_value), tolerance)
    if not math.isfinite(scale) or scale <= 0.0:
        return False
    admissible = tolerance
    for _ in range(_TOLERANCE_BOUNDARY_ULPS):
        admissible += math.ulp(scale)
    return difference <= admissible


def _runtime_dimensionality(registry: Any, unit: str | None) -> Any | None:
    if not unit:
        return None
    try:
        return registry.Quantity(1.0, unit).to_base_units().dimensionality
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class _SupportedOutcome:
    """The independent judgements one supported case earns.

    They are deliberately separate: a case can bind its query correctly and
    still answer outside tolerance, and each of those is its own frozen metric.
    """

    solved: bool = False
    correct: bool = False
    wrong: bool = False
    unit_ok: bool = False
    query_ok: bool = False
    coverage_ok: bool = False
    residual_ok: bool = False
    direction_ok: bool = False


def _score_supported(
    registry: Any,
    case: PublicCorpusCaseV1,
    record: LaneBResult,
    defects: Counter[str],
) -> _SupportedOutcome:
    """Score one supported case.

    `correct` and `wrong` are mutually exclusive; a supported case that is
    neither is *unscored*, which the strict gate rejects.
    """

    if record.terminal.value != _SOLVED_TERMINAL:
        defects[SupportedDefect.terminal_not_solved.value] += 1
        return _SupportedOutcome()

    # --- binding: the answer must be the answer to the question that was asked
    query_ok = True
    if record.answer_query_symbol_id is None:
        defects[SupportedDefect.query_symbol_unbound.value] += 1
        query_ok = False
    if record.query_subject_id is None:
        defects[SupportedDefect.query_subject_unbound.value] += 1
        query_ok = False

    # --- candidate coverage: exactly one candidate survived verification
    coverage_ok = record.verified_candidate_count == 1
    if not coverage_ok:
        defects[SupportedDefect.candidate_not_unique.value] += 1

    # --- residual verification: the checks this graph *owed*, all of them passed
    checks = record.verification_checks
    passed_kinds = {kind for kind, status in checks if status == _PASSED}
    obliged = _REQUIRED_CHECK_KINDS | set(record.required_check_kinds)
    all_passed = bool(checks) and all(status == _PASSED for _kind, status in checks)
    residual_ok = all_passed and obliged <= passed_kinds
    if not checks:
        defects[SupportedDefect.verification_check_missing.value] += 1
    elif not all_passed:
        defects[SupportedDefect.verification_check_not_passed.value] += 1
    elif not residual_ok:
        defects[SupportedDefect.verification_check_kind_missing.value] += 1

    partial = _SupportedOutcome(
        solved=True,
        query_ok=query_ok,
        coverage_ok=coverage_ok,
        residual_ok=residual_ok,
    )

    # --- numeric answer
    value = record.answer_value_si
    if value is None:
        defects[SupportedDefect.answer_missing.value] += 1
        return partial
    if value != value or value in (float("inf"), float("-inf")):
        defects[SupportedDefect.answer_not_finite.value] += 1
        return partial

    answers = case.gold.answers
    if len(answers) != 1:
        raise ScoringFailure(ScoringFailureReason.gold_answer_shape_invalid)
    expected = _gold_answer_in_si(registry, answers[0])
    if expected is None:
        defects[SupportedDefect.unit_unconvertible.value] += 1
        return partial

    # --- unit / dimension: the runtime's own declared output unit must carry
    # the same dimension as the gold answer.  A number that happens to match
    # numerically in the wrong dimension is not a correct answer.
    if not record.answer_unit:
        defects[SupportedDefect.output_unit_missing.value] += 1
        unit_ok = False
    else:
        actual_dimensionality = _runtime_dimensionality(registry, record.answer_unit)
        if actual_dimensionality is None:
            defects[SupportedDefect.unit_unconvertible.value] += 1
            unit_ok = False
        elif actual_dimensionality != expected.dimensionality:
            defects[SupportedDefect.unit_dimension_mismatch.value] += 1
            unit_ok = False
        else:
            unit_ok = True
    if not unit_ok:
        return _SupportedOutcome(
            solved=True,
            wrong=True,
            query_ok=query_ok,
            coverage_ok=coverage_ok,
            residual_ok=residual_ok,
        )

    # --- the corpus's own frozen tolerance, applied exactly
    within = _within_declared_tolerance(value, expected.value, expected.tolerance)
    if not within:
        defects[SupportedDefect.numeric_outside_tolerance.value] += 1
    # Direction/sign is proven by the *signed* comparison above together with an
    # explicitly bound component: an unsigned magnitude that happens to match is
    # not evidence that the direction was resolved.  It is a distinct judgement
    # from unit accuracy, which is why it is measured separately.
    direction_ok = within and record.answer_component is not None
    return _SupportedOutcome(
        solved=True,
        correct=within,
        wrong=not within,
        unit_ok=True,
        query_ok=query_ok,
        coverage_ok=coverage_ok,
        residual_ok=residual_ok,
        direction_ok=direction_ok,
    )


def _has_deferred_evidence(record: LaneBResult) -> bool:
    return any(code in _DEFERRED_CODE_VALUES for code in record.compiler_codes)


def _score_blocked(
    expected_terminal: Stage7ExpectedTerminal,
    record: LaneBResult,
    defects: Counter[str],
) -> bool:
    """Score one non-supported case against its exact expected safe terminal."""

    required = _REQUIRED_TERMINALS[expected_terminal]
    if record.terminal.value not in required:
        defects[BlockedDefect.terminal_mismatch.value] += 1
        return False
    # No blocked class may carry a numeric answer, whatever produced it.
    if record.answer_value_si is not None:
        defects[BlockedDefect.numeric_answer_present.value] += 1
        return False
    if expected_terminal is Stage7ExpectedTerminal.deferred_unsupported:
        if not _has_deferred_evidence(record):
            defects[BlockedDefect.deferred_evidence_missing.value] += 1
            return False
        return True
    if expected_terminal is Stage7ExpectedTerminal.unsupported_other:
        # An unsupported-other case must not borrow a deferred capability proof:
        # the two classes are distinguished by evidence, so sharing evidence
        # would make the distribution unfalsifiable.
        if _has_deferred_evidence(record):
            defects[
                BlockedDefect.unsupported_other_used_deferred_evidence.value
            ] += 1
            return False
        # Reaching the terminal is not the same as proving the refusal.  A case
        # that arrives at `compiler_unsupported` must say *why* with a typed
        # compiler code, or it is an undifferentiated failure wearing the right
        # terminal — the exact substitution this class exists to make visible.
        if record.terminal.value == _COMPILER_UNSUPPORTED_TERMINAL:
            if not record.compiler_codes:
                defects[BlockedDefect.unsupported_reason_missing.value] += 1
                return False
        return True
    return True


def score_lane_b_cases(
    cases: Sequence[PublicCorpusCaseV1],
    records: Sequence[LaneBResult],
) -> LaneBScorecard:
    """Compare the frozen runtime records against the frozen gold expectation.

    Both sequences are positional and must be the same length: `records[i]` is
    the runtime's own result for `cases[i]`.  The runtime produced them without
    reading `cases`; this function is the first and only place the two meet.
    """

    if len(cases) != len(records):
        raise ScoringFailure(ScoringFailureReason.record_count_mismatch)

    registry = _registry()
    expected_counts: Counter[str] = Counter()
    actual_terminals: Counter[str] = Counter()
    supported_defects: Counter[str] = Counter()
    blocked_defects: Counter[str] = Counter()

    terminal_matches = 0
    supported_expected = supported_solved = 0
    supported_correct = supported_wrong = supported_solved_unscored = 0
    unit_matches = query_matches = coverage_matches = residual_matches = 0
    direction_matches = 0
    deferred_expected = deferred_matched = 0
    other_expected = other_matched = 0
    figure_expected = figure_matched = 0
    confirmation_expected = confirmation_matched = 0
    insufficient_expected = insufficient_matched = 0
    deferred_silent_solves = 0
    blocked_silent_solves = blocked_numeric_answers = 0
    supported_downgraded = 0

    for index, (case, record) in enumerate(zip(cases, records)):
        try:
            expected_terminal = scope_adjusted_expected_terminal(
                case, case_index=index
            )
        except Exception as exc:
            raise ScoringFailure(
                ScoringFailureReason.expected_terminal_underivable
            ) from exc
        expected_counts[expected_terminal.value] += 1
        actual_terminals[record.terminal.value] += 1
        if record.terminal.value in _REQUIRED_TERMINALS[expected_terminal]:
            terminal_matches += 1

        if expected_terminal is Stage7ExpectedTerminal.accepted:
            supported_expected += 1
            outcome = _score_supported(registry, case, record, supported_defects)
            supported_solved += int(outcome.solved)
            supported_correct += int(outcome.correct)
            supported_wrong += int(outcome.wrong)
            if outcome.solved and not (outcome.correct or outcome.wrong):
                # Reached `solved` and produced an output, yet nothing could
                # compare it.  That is the hard-safety case: an unverifiable
                # claim, not an honest decline.
                supported_solved_unscored += 1
            unit_matches += int(outcome.unit_ok)
            query_matches += int(outcome.query_ok)
            coverage_matches += int(outcome.coverage_ok)
            residual_matches += int(outcome.residual_ok)
            direction_matches += int(outcome.direction_ok)
            if record.terminal.value == _VERIFIED_UNSUPPORTED_TERMINAL:
                # A supported problem answered as an unsupported capability is
                # the mirror image of a silent solve and is tracked as its own
                # signal, not folded into a generic terminal mismatch.
                supported_downgraded += 1
            continue

        matched = _score_blocked(expected_terminal, record, blocked_defects)
        # Silent solves are counted for *every* blocked class.  The deferred
        # one keeps its own counter because the frozen hard-safety catalog
        # names `deferred_silent_solve` specifically; the other four are
        # counted together so none of them can pass unmeasured.
        if record.terminal.value == _SOLVED_TERMINAL:
            if expected_terminal is Stage7ExpectedTerminal.deferred_unsupported:
                deferred_silent_solves += 1
            else:
                blocked_silent_solves += 1
        elif record.answer_value_si is not None:
            blocked_numeric_answers += 1
        if expected_terminal is Stage7ExpectedTerminal.deferred_unsupported:
            deferred_expected += 1
            deferred_matched += int(matched)
        elif expected_terminal is Stage7ExpectedTerminal.unsupported_other:
            other_expected += 1
            other_matched += int(matched)
        elif expected_terminal is Stage7ExpectedTerminal.needs_figure:
            figure_expected += 1
            figure_matched += int(matched)
        elif expected_terminal is Stage7ExpectedTerminal.needs_confirmation:
            confirmation_expected += 1
            confirmation_matched += int(matched)
        else:
            insufficient_expected += 1
            insufficient_matched += int(matched)

    supported_unscored = supported_expected - supported_correct - supported_wrong

    return LaneBScorecard(
        version=LANE_B_SCORING_VERSION,
        total_cases=len(cases),
        expected_counts=tuple(sorted(expected_counts.items())),
        actual_terminal_counts=tuple(sorted(actual_terminals.items())),
        terminal_mapping_matches=terminal_matches,
        supported_expected=supported_expected,
        supported_solved=supported_solved,
        supported_correct=supported_correct,
        supported_wrong=supported_wrong,
        supported_unscored=supported_unscored,
        supported_solved_unscored=supported_solved_unscored,
        supported_defect_counts=tuple(sorted(supported_defects.items())),
        deferred_expected=deferred_expected,
        deferred_matched=deferred_matched,
        unsupported_other_expected=other_expected,
        unsupported_other_matched=other_matched,
        needs_figure_expected=figure_expected,
        needs_figure_matched=figure_matched,
        needs_confirmation_expected=confirmation_expected,
        needs_confirmation_matched=confirmation_matched,
        insufficient_information_expected=insufficient_expected,
        insufficient_information_matched=insufficient_matched,
        blocked_defect_counts=tuple(sorted(blocked_defects.items())),
        blocked_silent_solves=blocked_silent_solves,
        blocked_numeric_answers=blocked_numeric_answers,
        unit_dimension_matches=unit_matches,
        query_binding_matches=query_matches,
        direction_sign_matches=direction_matches,
        candidate_coverage_matches=coverage_matches,
        residual_verification_matches=residual_matches,
        deferred_silent_solves=deferred_silent_solves,
        supported_downgraded_to_unsupported=supported_downgraded,
    )


__all__ = [
    "LANE_B_SCORING_VERSION",
    "BlockedDefect",
    "LaneBScorecard",
    "ScoringFailure",
    "ScoringFailureReason",
    "SupportedAnswerScore",
    "SupportedDefect",
    "score_lane_b_cases",
]
