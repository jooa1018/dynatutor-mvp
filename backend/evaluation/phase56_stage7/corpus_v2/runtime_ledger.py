"""One row per public context, so a context cannot leave the measurement quietly.

This module exists because of a specific defect.  The shadow runner used to walk
the corpus like this::

    if projection.draft is None:
        ambiguities["projection_refused"] += 1
        continue
    try:
        ...
    except Exception as exc:
        ambiguities[type(exc).__name__] += 1
        continue

Both ``continue`` statements drop the context out of the run *entirely*: it
leaves no runtime record, so it is absent from the snapshot; absent from the
snapshot, it is absent from the scored handle set; absent from the handle set,
the gold index is built without it; and absent from the gold index, it cannot be
counted wrong, unscored, forbidden or regressed.  A context that failed was
therefore indistinguishable from a context that never existed, and the remaining
contexts could carry an acceptance PASS on their own.  The aggregate said
nothing was wrong because nothing that could have been wrong was still being
looked at.

The ledger is the fix, and it is a *completeness* structure rather than a
diagnostic one.  Every context the corpus contains gets exactly one row, whether
it ran or not; the states are a closed set; and the reasons are a closed
vocabulary rather than ``type(exc).__name__``, so an exception class nobody
anticipated is a blocking failure by construction instead of a new label in a
counter that acceptance never reads.

The division that matters is not "did it run" but **is this refusal one the
contract anticipated**.  A projection that declines a context the v1 record
cannot express is expected, bounded, and part of the measurement.  An
unhandled exception is neither, and no run carrying one is an accepted
measurement — the number it would report is a number about a subset nobody
chose.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Iterable, Sequence

from pydantic import StringConstraints, model_validator

from evaluation.phase56_stage7.contracts import FrozenStrictModel


CORPUS_V2_RUNTIME_LEDGER_VERSION = "phase56-stage7-corpus-v2-runtime-ledger-v1"

_Handle = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class LedgerState(str, Enum):
    """What became of one context.  Closed, and exhaustive over the corpus."""

    runtime_completed = "runtime_completed"
    projection_refused = "projection_refused"
    migration_refused = "migration_refused"
    runtime_failed = "runtime_failed"
    snapshot_rejected = "snapshot_rejected"


class RefusalCode(str, Enum):
    """Why a context did not produce a runtime record.

    A closed vocabulary, deliberately.  The counter this replaces was keyed by
    ``type(exc).__name__``, which meant the set of reasons was whatever the
    interpreter happened to raise — so no acceptance rule could enumerate the
    ones that were allowed, and every unanticipated failure arrived as a new
    label that nothing checked.
    """

    # Anticipated.  The v1 record does not carry what a Draft would need, and
    # declining to build one is the honest outcome rather than a failure.
    projection_refused_no_draft = "projection_refused_no_draft"
    # Anticipated.  The manifest author could not state the carrier from the
    # source, or stated one the fill-only merge contract refuses.
    migration_refused_unresolved_entry = "migration_refused_unresolved_entry"
    migration_refused_conflicting_entry = "migration_refused_conflicting_entry"
    # Never anticipated.  Both of these fail acceptance wherever they appear.
    runtime_failed_unexpected_exception = "runtime_failed_unexpected_exception"
    snapshot_rejected_incomplete_record = "snapshot_rejected_incomplete_record"


# The refusals a measurement may contain and still be a measurement.  Each is a
# statement about what the *source* does not carry, bounded by the contract and
# countable in advance.
EXPECTED_REFUSALS: frozenset[RefusalCode] = frozenset(
    {
        RefusalCode.projection_refused_no_draft,
        RefusalCode.migration_refused_unresolved_entry,
        RefusalCode.migration_refused_conflicting_entry,
    }
)

# The refusals that mean the run itself is broken.  A run containing one of
# these has not measured the corpus, whatever its other counts say.
BLOCKING_REFUSALS: frozenset[RefusalCode] = frozenset(RefusalCode) - EXPECTED_REFUSALS

_STATE_REFUSALS: dict[LedgerState, frozenset[RefusalCode]] = {
    LedgerState.projection_refused: frozenset(
        {RefusalCode.projection_refused_no_draft}
    ),
    LedgerState.migration_refused: frozenset(
        {
            RefusalCode.migration_refused_unresolved_entry,
            RefusalCode.migration_refused_conflicting_entry,
        }
    ),
    LedgerState.runtime_failed: frozenset(
        {RefusalCode.runtime_failed_unexpected_exception}
    ),
    LedgerState.snapshot_rejected: frozenset(
        {RefusalCode.snapshot_rejected_incomplete_record}
    ),
}


class LedgerCompletenessFailure(str, Enum):
    """The machine-checkable names an incomplete ledger fails under.

    These are values on the artifact, not lines in a log.  A failure that only
    existed as printed text could be — and was — reported beside a process exit
    of zero.
    """

    expected_handle_missing = "shadow_expected_handle_missing"
    unknown_handle_present = "shadow_unknown_handle_present"
    duplicate_handle = "shadow_duplicate_handle"
    context_count_mismatch = "shadow_context_count_mismatch"
    unexpected_runtime_failure = "shadow_unexpected_runtime_failure"
    snapshot_incomplete = "shadow_snapshot_incomplete"


class ShadowLedgerEntryV2(FrozenStrictModel):
    """One context's disposition.  Exactly one, for every context there is."""

    scoring_handle: _Handle
    state: LedgerState
    refusal_code: RefusalCode | None = None

    @model_validator(mode="after")
    def validate_entry(self) -> "ShadowLedgerEntryV2":
        if self.state is LedgerState.runtime_completed:
            if self.refusal_code is not None:
                raise ValueError("a completed context was not refused")
            return self
        if self.refusal_code is None:
            raise ValueError("a refused context must say under which code")
        allowed = _STATE_REFUSALS[self.state]
        if self.refusal_code not in allowed:
            raise ValueError(
                f"{self.refusal_code.value} is not a reason for {self.state.value}"
            )
        return self

    @property
    def is_blocking(self) -> bool:
        return self.refusal_code in BLOCKING_REFUSALS


def ledger_completeness_failures(
    ledger: Sequence[ShadowLedgerEntryV2],
    *,
    expected_handles: Iterable[str],
    recorded_handles: Iterable[str],
) -> tuple[str, ...]:
    """Every way this ledger fails to account for every context, by name.

    Three sets have to agree and the checks are deliberately separate, because
    the defect being closed was precisely a case where two of them agreed with
    each other by both omitting the same context:

    * ``expected_handles`` — every context the corpus contains.  Fixed before
      anything runs, so a context cannot be dropped from the denominator.
    * the ledger — one row per context, whatever became of it.
    * ``recorded_handles`` — the contexts that produced a runtime record, which
      must be exactly the ``runtime_completed`` rows and nothing else.

    Returns names rather than raising so a caller can report all of them at
    once and set its exit status from the same values it prints.
    """

    failures: list[str] = []
    expected = list(expected_handles)
    expected_set = set(expected)
    handles = [entry.scoring_handle for entry in ledger]
    seen = set(handles)
    recorded = list(recorded_handles)
    recorded_set = set(recorded)

    if len(handles) != len(seen):
        failures.append(LedgerCompletenessFailure.duplicate_handle.value)
    if len(recorded) != len(recorded_set):
        failures.append(LedgerCompletenessFailure.duplicate_handle.value)
    if expected_set - seen:
        failures.append(LedgerCompletenessFailure.expected_handle_missing.value)
    if seen - expected_set:
        failures.append(LedgerCompletenessFailure.unknown_handle_present.value)
    if len(expected) != len(expected_set) or len(handles) != len(expected):
        failures.append(LedgerCompletenessFailure.context_count_mismatch.value)

    completed = {
        entry.scoring_handle
        for entry in ledger
        if entry.state is LedgerState.runtime_completed
    }
    # A record with no completed row, or a completed row with no record, is the
    # exact shape of the original defect: a context present in one accounting
    # and absent from the other.
    if completed != recorded_set:
        failures.append(LedgerCompletenessFailure.snapshot_incomplete.value)
    if recorded_set - expected_set:
        failures.append(LedgerCompletenessFailure.unknown_handle_present.value)
    if any(entry.is_blocking for entry in ledger):
        failures.append(LedgerCompletenessFailure.unexpected_runtime_failure.value)

    return tuple(sorted(set(failures)))


def refusal_counts(
    ledger: Sequence[ShadowLedgerEntryV2],
) -> tuple[tuple[str, int], ...]:
    """How many contexts each closed refusal code accounts for, sorted.

    Replaces the free-form ``Counter[type(exc).__name__]`` that used to be
    reported as "migration ambiguities".  Every key here is a member of a
    closed enum, so a reader can check the list against the contract instead of
    against whatever ran.
    """

    counts: dict[str, int] = {}
    for entry in ledger:
        if entry.refusal_code is None:
            continue
        counts[entry.refusal_code.value] = counts.get(entry.refusal_code.value, 0) + 1
    return tuple(sorted(counts.items()))


def state_counts(
    ledger: Sequence[ShadowLedgerEntryV2],
) -> tuple[tuple[str, int], ...]:
    """How many contexts are in each ledger state, sorted, including zeroes.

    Zeroes are carried deliberately.  A published count of
    ``runtime_failed: 0`` is a measurement; a missing key is only an absence,
    and the whole defect this module closes was an absence that read as a zero.
    """

    counts = {state.value: 0 for state in LedgerState}
    for entry in ledger:
        counts[entry.state.value] += 1
    return tuple(sorted(counts.items()))


__all__ = [
    "BLOCKING_REFUSALS",
    "CORPUS_V2_RUNTIME_LEDGER_VERSION",
    "EXPECTED_REFUSALS",
    "LedgerCompletenessFailure",
    "LedgerState",
    "RefusalCode",
    "ShadowLedgerEntryV2",
    "ledger_completeness_failures",
    "refusal_counts",
    "state_counts",
]
