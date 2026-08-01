"""The v2 shadow runtime snapshot: what the pipeline did, frozen before scoring.

This module is the **runtime domain** of the shadow evaluation.  It may not
import the gold domain, the scorer, or anything that can reach an expected
answer, and nothing here reads one.  A snapshot is produced by running the
pipeline and is then immutable; the scorer receives it and only *compares*.

Why the freeze is a contract and not a convention.  A shadow measurement that
scores while it runs cannot prove it did not steer: the same process held both
the answer and the next decision.  Sequencing the two — run everything, freeze,
hash, only then look at the gold — makes the claim checkable, because a scorer
handed an already-hashed snapshot has nothing left to influence.  The digest is
recomputed on construction, so a snapshot whose records were edited after the
fact fails to build at all.

The records here are privacy-safe by construction.  A context is identified by
an opaque scoring handle derived from the archive digest and the context's
position — enough to pair a runtime record with its gold case inside the
scorer, and nothing a reader of the published aggregate can invert into a case
identity.  The handle is stripped before any report is written.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Iterable, Sequence

from pydantic import Field, StringConstraints

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (
    LedgerState,
    ShadowLedgerEntryV2,
    ledger_completeness_failures,
    refusal_counts,
    state_counts,
)


CORPUS_V2_RUNTIME_SNAPSHOT_VERSION = "phase56-stage7-corpus-v2-runtime-snapshot-v3"
CORPUS_V2_REDACTED_VIEW_VERSION = "phase56-stage7-corpus-v2-redacted-runtime-view-v1"

# Stamped into the snapshot so a reader of a fragment still learns that this is
# runtime evidence about a candidate archive and not an official measurement.
RUNTIME_SCORE_CLASS = "EXPERIMENTAL_V2_SHADOW_RUNTIME"
# The redacted view's own class.  Deliberately not the one above: the two
# artifacts are different objects with different contents, and a reader who
# saw only one of them must not be able to mistake it for the other.
REDACTED_VIEW_CLASS = "EXPERIMENTAL_V2_SHADOW_RUNTIME_REDACTED_VIEW"

_Token = Annotated[str, StringConstraints(min_length=1, max_length=120)]
_Handle = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def scoring_handle(*, original_v1_archive_sha256: str, context_index: int) -> str:
    """An opaque pairing label for one context.

    Derived from the archive digest and the context's position, so it is
    deterministic for a given archive and reveals neither the case identity nor
    the corpus order to a reader of the artifact.  It is *pairing* only: no
    runtime decision is taken from it, and it never reaches a report.
    """

    material = f"{original_v1_archive_sha256}\0{context_index}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class ShadowRuntimeRecordV2(FrozenStrictModel):
    """One context's runtime outcome, with no gold member anywhere in it.

    Everything here is something the pipeline produced.  There is deliberately
    no expected answer, expected terminal, expected failure code, family, case
    id, split, or source text field — not redacted at write time, but absent
    from the type, so a scorer that wanted to feed one back has nowhere to put
    it.
    """

    scoring_handle: _Handle
    cohort_digest: Sha256
    augmented: bool = False
    carriers_supplied: tuple[_Token, ...] = ()
    baseline_rung: _Token
    shadow_rung: _Token
    baseline_solved: bool = False
    shadow_solved: bool = False
    # The runtime's own output, as the runtime declared it.  `answer_value_si`
    # is the pipeline's number in SI; comparing it to anything happens in the
    # gold domain, after this record is frozen.
    answer_value_si: float | None = None
    answer_unit: Annotated[str, StringConstraints(max_length=48)] | None = None
    answer_component: _Token | None = None
    query_binding_digest: Sha256 | None = None
    query_binding_complete: bool = False
    candidate_count: int = Field(default=0, ge=0, le=10_000)
    verified_candidate_count: int = Field(default=0, ge=0, le=10_000)
    applied_law_digest: Sha256 | None = None
    provenance_digest: Sha256 | None = None
    runtime_error_category: _Token | None = None

    @property
    def newly_solved(self) -> bool:
        return self.shadow_solved and not self.baseline_solved

    @property
    def regressed(self) -> bool:
        return self.baseline_solved and not self.shadow_solved


class ShadowRuntimeSnapshotV2(FrozenStrictModel):
    """Every runtime record for one shadow run, frozen and self-verifying.

    `runtime_snapshot_digest` is recomputed from the rest of the model when the
    snapshot is constructed.  A snapshot whose records were changed afterwards
    cannot be rebuilt with the same digest, and pydantic's frozen model refuses
    the in-place edit that would try.
    """

    version: str = CORPUS_V2_RUNTIME_SNAPSHOT_VERSION
    score_class: str = RUNTIME_SCORE_CLASS
    original_v1_archive_sha256: Sha256
    augmentation_manifest_sha256: Sha256
    candidate_archive_sha256: Sha256
    exact_code_head: Annotated[str, StringConstraints(max_length=64)] | None = None
    runtime_contract_version: str = CORPUS_V2_RUNTIME_SNAPSHOT_VERSION
    # How many contexts the corpus contains — fixed before anything runs, so a
    # context that failed cannot also leave the denominator.  `context_count`
    # below is how many produced a record, and the two are different numbers
    # whenever anything was refused.
    expected_context_count: int = Field(default=0, ge=0)
    context_count: int = Field(default=0, ge=0)
    augmented_context_count: int = Field(default=0, ge=0)
    unresolved_augmentation_count: int = Field(default=0, ge=0)
    migration_ambiguities: tuple[tuple[str, int], ...] = ()
    # One row per expected context, in a closed vocabulary.  This is the
    # structure that makes a silently dropped context impossible: a snapshot
    # whose ledger does not account for every expected handle cannot be frozen.
    ledger: tuple[ShadowLedgerEntryV2, ...] = Field(default=(), max_length=512)
    records: tuple[ShadowRuntimeRecordV2, ...] = Field(default=(), max_length=512)
    runtime_snapshot_digest: Sha256

    def digest_material(self) -> bytes:
        payload = self.model_dump(mode="json", exclude={"runtime_snapshot_digest"})
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def recomputed_digest(self) -> str:
        return hashlib.sha256(self.digest_material()).hexdigest()

    def digest_is_intact(self) -> bool:
        return self.recomputed_digest() == self.runtime_snapshot_digest

    def by_handle(self) -> dict[str, ShadowRuntimeRecordV2]:
        return {record.scoring_handle: record for record in self.records}

    @property
    def expected_handles(self) -> tuple[str, ...]:
        """Every context this run was supposed to account for.

        Read off the ledger rather than off the records, because the records
        are exactly what a dropped context is missing from.  A ledger that has
        itself lost a row fails `completeness_failures` on the count.
        """

        return tuple(entry.scoring_handle for entry in self.ledger)

    def completeness_failures(self) -> tuple[str, ...]:
        """Every way this snapshot fails to account for every context, by name.

        Checked on construction, and checkable again by anyone holding the
        file.  An independent reader gets the same answer from the same bytes,
        which is the point: the claim "nothing went missing" is verifiable
        without re-running the pipeline.
        """

        failures = list(
            ledger_completeness_failures(
                self.ledger,
                expected_handles=self.expected_handles,
                recorded_handles=[row.scoring_handle for row in self.records],
            )
        )
        if self.expected_context_count != len(self.ledger):
            failures.append("shadow_context_count_mismatch")
        if self.context_count != len(self.records):
            failures.append("shadow_context_count_mismatch")
        return tuple(sorted(set(failures)))

    @property
    def ledger_state_counts(self) -> tuple[tuple[str, int], ...]:
        return state_counts(self.ledger)

    @property
    def ledger_refusal_counts(self) -> tuple[tuple[str, int], ...]:
        return refusal_counts(self.ledger)


class RuntimeSnapshotRefused(RuntimeError):
    """A snapshot that cannot be trusted as a measurement is not returned."""


def freeze_runtime_snapshot(
    records: Iterable[ShadowRuntimeRecordV2],
    *,
    ledger: Sequence[ShadowLedgerEntryV2],
    original_v1_archive_sha256: str,
    augmentation_manifest_sha256: str,
    candidate_archive_sha256: str,
    exact_code_head: str | None = None,
    unresolved_augmentation_count: int = 0,
) -> ShadowRuntimeSnapshotV2:
    """Close the runtime phase.  Nothing may be measured after this returns.

    `ledger` is required and is the completeness contract: one row for every
    context the corpus contains.  A snapshot whose ledger does not account for
    every one of them — or which carries a record no ledger row admits, or a
    blocking refusal — is refused here rather than written, because a snapshot
    that can be scored is a snapshot somebody will quote.

    `migration_ambiguities` used to be a caller-supplied
    ``Counter[type(exc).__name__]``.  It is now derived from the ledger's closed
    refusal codes, so the snapshot cannot report a reason vocabulary that
    differs from the one its own rows are written in.
    """

    rows = tuple(records)
    entries = tuple(ledger)
    handles = [row.scoring_handle for row in rows]
    if len(handles) != len(set(handles)):
        raise RuntimeSnapshotRefused("two runtime records share one scoring handle")
    draft = {
        "original_v1_archive_sha256": original_v1_archive_sha256,
        "augmentation_manifest_sha256": augmentation_manifest_sha256,
        "candidate_archive_sha256": candidate_archive_sha256,
        "exact_code_head": exact_code_head,
        "expected_context_count": len(entries),
        "context_count": len(rows),
        "augmented_context_count": sum(1 for row in rows if row.augmented),
        "unresolved_augmentation_count": unresolved_augmentation_count,
        "migration_ambiguities": refusal_counts(entries),
        "ledger": entries,
        "records": rows,
    }
    # Build once with a placeholder digest so the model's own canonical dump is
    # what gets hashed, then build the real snapshot from that hash.  Hashing a
    # hand-assembled dict instead would let the two drift.
    provisional = ShadowRuntimeSnapshotV2(
        **draft,
        runtime_snapshot_digest="0" * 64,
    )
    snapshot = ShadowRuntimeSnapshotV2(
        **draft,
        runtime_snapshot_digest=provisional.recomputed_digest(),
    )
    failures = snapshot.completeness_failures()
    if failures:
        raise RuntimeSnapshotRefused(
            "the runtime snapshot does not account for every context: "
            + ",".join(failures)
        )
    return snapshot


def load_full_runtime_snapshot(body: str) -> ShadowRuntimeSnapshotV2:
    """Re-read a frozen snapshot from its own bytes, or refuse it.

    This is the function that makes the artifact independently re-scorable, and
    it is why the full snapshot has to exist as a file at all.  Before this,
    the only complete snapshot lived in the runner's memory: what reached disk
    was the redacted view with the pairing handles stripped, and Phase G read
    the in-memory object rather than the file.  Nobody holding the artifact
    could rebuild the measurement, and the sequencing claim rested on the two
    phases being polite to each other inside one process.

    Every refusal here is a refusal to score, never a repair: a truncated file,
    a schema that is not this one, a digest that does not match the contents,
    or a ledger that does not account for every context.
    """

    try:
        snapshot = ShadowRuntimeSnapshotV2.model_validate_json(body)
    except Exception as exc:  # noqa: BLE001 — re-raised as the typed refusal
        raise RuntimeSnapshotRefused(
            f"the runtime snapshot could not be read as one: {type(exc).__name__}"
        ) from None
    if snapshot.version != CORPUS_V2_RUNTIME_SNAPSHOT_VERSION:
        raise RuntimeSnapshotRefused(
            f"the runtime snapshot is version {snapshot.version}, "
            f"not {CORPUS_V2_RUNTIME_SNAPSHOT_VERSION}"
        )
    if snapshot.score_class != RUNTIME_SCORE_CLASS:
        raise RuntimeSnapshotRefused(
            "the runtime snapshot is not stamped as a full runtime snapshot"
        )
    if not snapshot.digest_is_intact():
        raise RuntimeSnapshotRefused(
            "the runtime snapshot digest does not match its contents"
        )
    failures = snapshot.completeness_failures()
    if failures:
        raise RuntimeSnapshotRefused(
            "the runtime snapshot does not account for every context: "
            + ",".join(failures)
        )
    return snapshot


class RedactedRuntimeRecordV2(FrozenStrictModel):
    """One runtime outcome with the pairing handle absent from the *type*.

    Not `ShadowRuntimeRecordV2` with a field removed at write time: a separate
    model, so the redacted view cannot be validated as a full snapshot and a
    caller that tried to score one has nowhere to read a handle from.  The
    fields kept are the ones a reader of the published aggregate can check the
    aggregate against; the handle is the one field that could re-identify a
    case, and it is not expressible here.
    """

    cohort_digest: Sha256
    augmented: bool = False
    carriers_supplied: tuple[_Token, ...] = ()
    baseline_rung: _Token
    shadow_rung: _Token
    baseline_solved: bool = False
    shadow_solved: bool = False
    answer_unit: Annotated[str, StringConstraints(max_length=48)] | None = None
    answer_component: _Token | None = None
    query_binding_complete: bool = False
    candidate_count: int = Field(default=0, ge=0, le=10_000)
    verified_candidate_count: int = Field(default=0, ge=0, le=10_000)
    applied_law_digest: Sha256 | None = None
    provenance_digest: Sha256 | None = None
    runtime_error_category: _Token | None = None


class PublicRedactedRuntimeViewV2(FrozenStrictModel):
    """The publishable view of a runtime snapshot.  Never a scoring input.

    It carries its own version and class, and it *references* the full
    snapshot's digest instead of presenting one of its own under that name —
    the two files have different bytes and therefore different file hashes, and
    a view that published a digest called "the runtime snapshot digest" while
    hashing different contents would be the most confusing artifact in the set.

    The ledger counts survive redaction because they are the completeness
    evidence and they identify nothing: knowing that three contexts were
    refused for want of a Draft tells a reader the measurement covered the
    corpus, and tells them nothing about which contexts those were.
    """

    version: str = CORPUS_V2_REDACTED_VIEW_VERSION
    score_class: str = REDACTED_VIEW_CLASS
    is_scoring_input: bool = False
    original_v1_archive_sha256: Sha256
    augmentation_manifest_sha256: Sha256
    candidate_archive_sha256: Sha256
    # Whose measurement this is a view of.  Named for what it is.
    full_runtime_snapshot_digest: Sha256
    exact_code_head: Annotated[str, StringConstraints(max_length=64)] | None = None
    runtime_contract_version: str = ""
    expected_context_count: int = Field(default=0, ge=0)
    context_count: int = Field(default=0, ge=0)
    augmented_context_count: int = Field(default=0, ge=0)
    unresolved_augmentation_count: int = Field(default=0, ge=0)
    ledger_state_counts: tuple[tuple[str, int], ...] = ()
    ledger_refusal_counts: tuple[tuple[str, int], ...] = ()
    records: tuple[RedactedRuntimeRecordV2, ...] = Field(default=(), max_length=512)


def redact_runtime_snapshot(
    snapshot: ShadowRuntimeSnapshotV2,
) -> PublicRedactedRuntimeViewV2:
    """Build the publishable view.  One direction only, and lossy on purpose.

    `answer_value_si` and `query_binding_digest` are dropped along with the
    handle: the first is the runtime's number, which belongs in the scored
    report next to what it was compared against rather than loose in a public
    file, and the second is a digest over symbol identifiers.
    """

    return PublicRedactedRuntimeViewV2(
        original_v1_archive_sha256=snapshot.original_v1_archive_sha256,
        augmentation_manifest_sha256=snapshot.augmentation_manifest_sha256,
        candidate_archive_sha256=snapshot.candidate_archive_sha256,
        full_runtime_snapshot_digest=snapshot.runtime_snapshot_digest,
        exact_code_head=snapshot.exact_code_head,
        runtime_contract_version=snapshot.runtime_contract_version,
        expected_context_count=snapshot.expected_context_count,
        context_count=snapshot.context_count,
        augmented_context_count=snapshot.augmented_context_count,
        unresolved_augmentation_count=snapshot.unresolved_augmentation_count,
        ledger_state_counts=snapshot.ledger_state_counts,
        ledger_refusal_counts=snapshot.ledger_refusal_counts,
        records=tuple(
            RedactedRuntimeRecordV2(
                cohort_digest=row.cohort_digest,
                augmented=row.augmented,
                carriers_supplied=row.carriers_supplied,
                baseline_rung=row.baseline_rung,
                shadow_rung=row.shadow_rung,
                baseline_solved=row.baseline_solved,
                shadow_solved=row.shadow_solved,
                answer_unit=row.answer_unit,
                answer_component=row.answer_component,
                query_binding_complete=row.query_binding_complete,
                candidate_count=row.candidate_count,
                verified_candidate_count=row.verified_candidate_count,
                applied_law_digest=row.applied_law_digest,
                provenance_digest=row.provenance_digest,
                runtime_error_category=row.runtime_error_category,
            )
            for row in snapshot.records
        ),
    )


def digest_of(values: Iterable[Any]) -> str:
    """A stable digest of an ordered collection of small runtime values."""

    material = json.dumps(
        list(values),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


__all__ = [
    "CORPUS_V2_REDACTED_VIEW_VERSION",
    "CORPUS_V2_RUNTIME_SNAPSHOT_VERSION",
    "REDACTED_VIEW_CLASS",
    "RUNTIME_SCORE_CLASS",
    "LedgerState",
    "PublicRedactedRuntimeViewV2",
    "RedactedRuntimeRecordV2",
    "RuntimeSnapshotRefused",
    "ShadowLedgerEntryV2",
    "ShadowRuntimeRecordV2",
    "ShadowRuntimeSnapshotV2",
    "digest_of",
    "freeze_runtime_snapshot",
    "load_full_runtime_snapshot",
    "redact_runtime_snapshot",
    "scoring_handle",
]
