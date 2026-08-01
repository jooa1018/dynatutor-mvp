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


CORPUS_V2_RUNTIME_SNAPSHOT_VERSION = "phase56-stage7-corpus-v2-runtime-snapshot-v2"

# Stamped into the snapshot so a reader of a fragment still learns that this is
# runtime evidence about a candidate archive and not an official measurement.
RUNTIME_SCORE_CLASS = "EXPERIMENTAL_V2_SHADOW_RUNTIME"

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
    context_count: int = Field(default=0, ge=0)
    augmented_context_count: int = Field(default=0, ge=0)
    unresolved_augmentation_count: int = Field(default=0, ge=0)
    migration_ambiguities: tuple[tuple[str, int], ...] = ()
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


class RuntimeSnapshotRefused(RuntimeError):
    """A snapshot that cannot be trusted as a measurement is not returned."""


def freeze_runtime_snapshot(
    records: Iterable[ShadowRuntimeRecordV2],
    *,
    original_v1_archive_sha256: str,
    augmentation_manifest_sha256: str,
    candidate_archive_sha256: str,
    exact_code_head: str | None = None,
    unresolved_augmentation_count: int = 0,
    migration_ambiguities: Sequence[tuple[str, int]] = (),
) -> ShadowRuntimeSnapshotV2:
    """Close the runtime phase.  Nothing may be measured after this returns."""

    rows = tuple(records)
    handles = [row.scoring_handle for row in rows]
    if len(handles) != len(set(handles)):
        raise RuntimeSnapshotRefused("two runtime records share one scoring handle")
    draft = {
        "original_v1_archive_sha256": original_v1_archive_sha256,
        "augmentation_manifest_sha256": augmentation_manifest_sha256,
        "candidate_archive_sha256": candidate_archive_sha256,
        "exact_code_head": exact_code_head,
        "context_count": len(rows),
        "augmented_context_count": sum(1 for row in rows if row.augmented),
        "unresolved_augmentation_count": unresolved_augmentation_count,
        "migration_ambiguities": tuple(migration_ambiguities),
        "records": rows,
    }
    # Build once with a placeholder digest so the model's own canonical dump is
    # what gets hashed, then build the real snapshot from that hash.  Hashing a
    # hand-assembled dict instead would let the two drift.
    provisional = ShadowRuntimeSnapshotV2(
        **draft,
        runtime_snapshot_digest="0" * 64,
    )
    return ShadowRuntimeSnapshotV2(
        **draft,
        runtime_snapshot_digest=provisional.recomputed_digest(),
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
    "CORPUS_V2_RUNTIME_SNAPSHOT_VERSION",
    "RUNTIME_SCORE_CLASS",
    "RuntimeSnapshotRefused",
    "ShadowRuntimeRecordV2",
    "ShadowRuntimeSnapshotV2",
    "digest_of",
    "freeze_runtime_snapshot",
    "scoring_handle",
]
