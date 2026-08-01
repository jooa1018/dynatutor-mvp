"""Migration from v1 to the v2 candidate, driven by an explicit manifest.

Migration is not inference.  Nothing here reads problem text, matches a
keyword, or derives a carrier from what a case looks like — every addition
comes from a manifest entry a human authored while reading the source, and the
entry names the evidence it came from.  A case the author could not resolve has
no entry, stays unresolved, and is reported as unresolved.

Three invariants make a migrated archive trustworthy, and each is enforced
here rather than documented:

*The v1 record is not touched.*  A migrated record carries the original's
canonical bytes and their fingerprint, so a v2 archive can always be reduced
back to the exact v1 archive it came from.

*The manifest cannot see an answer.*  Expected answers, expected terminals,
expected failure codes, reference expressions, tolerances and solver output are
refused as manifest inputs by a structural scan, not by convention.  A carrier
chosen to make a number come out right is a carrier chosen by the answer.

*The result is deterministic.*  The same v1 archive and the same manifest
rebuild to the same bytes and the same hash, every time.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Annotated, Any, Iterable, Mapping, Sequence

from pydantic import Field, StringConstraints, model_validator

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256
from evaluation.phase56_stage7.corpus_v2.merge import (
    V2MergeConflict,
    V2MergeConflictReason,
    assert_fill_only_merge,
)
from evaluation.phase56_stage7.corpus_v2.records import (
    CORPUS_V2_SCHEMA_VERSION,
    CorpusV2AugmentationV1,
)
from evaluation.phase56_stage7.corpus_v2.validation import (
    V2ValidationError,
    V2ValidationReason,
    validate_augmentation,
)


CORPUS_V2_MIGRATION_VERSION = "phase56-stage7-corpus-v2-migration-v1"

# Field names a manifest entry may never contain, at any depth.  These are the
# fields that carry the answer, and an augmentation authored from one of them is
# an augmentation authored from the answer.
FORBIDDEN_MANIFEST_FIELDS: frozenset[str] = frozenset(
    {
        "answers",
        "answer",
        "expectedanswer",
        "numeric",
        "tolerance",
        "toleranceabs",
        "referenceexpression",
        "expectedterminal",
        "futureexpectedterminal",
        "phase55expectedterminal",
        "expectedfailurecodes",
        "signconvention",
        "solveroutput",
        "solution",
        "targetvalue",
    }
)


class MigrationReason(str, Enum):
    """Closed, privacy-safe migration rejection catalogue."""

    manifest_contains_answer_field = "manifest_contains_answer_field"
    manifest_fingerprint_mismatch = "manifest_fingerprint_mismatch"
    manifest_duplicate_fingerprint = "manifest_duplicate_fingerprint"
    manifest_entry_invalid = "manifest_entry_invalid"
    augmentation_rejected = "augmentation_rejected"
    # The augmentation validates on its own and still restates a field the v1
    # source already states, differently.  Additive migration cannot carry it.
    augmentation_conflicts_with_source = "augmentation_conflicts_with_source"
    original_record_mutated = "original_record_mutated"


class MigrationError(ValueError):
    def __init__(
        self,
        reason: MigrationReason,
        *,
        detail: V2ValidationReason | tuple[V2MergeConflictReason, ...] | None = None,
    ) -> None:
        super().__init__(reason.value)
        self.reason = reason
        self.detail = detail


class ReviewStatus(str, Enum):
    """How far an augmentation entry has been through review.

    `unresolved` is a first-class outcome and the honest one for a case whose
    source does not state what the carrier would need.  It is never migrated.
    """

    authored = "authored"
    reviewed = "reviewed"
    unresolved = "unresolved"


class AugmentationEntryV1(FrozenStrictModel):
    """One manifest entry: which v1 record, and what to add to it."""

    original_fingerprint: Sha256
    augmentation_version: Annotated[
        str, StringConstraints(min_length=1, max_length=64)
    ] = CORPUS_V2_SCHEMA_VERSION
    review_status: ReviewStatus = ReviewStatus.authored
    authoring_provenance: Annotated[
        str, StringConstraints(min_length=1, max_length=160)
    ]
    unresolved_reason: Annotated[
        str, StringConstraints(min_length=1, max_length=160)
    ] | None = None
    augmentation: CorpusV2AugmentationV1 = Field(
        default_factory=CorpusV2AugmentationV1
    )

    @model_validator(mode="after")
    def validate_entry(self) -> "AugmentationEntryV1":
        if self.review_status is ReviewStatus.unresolved:
            if not self.unresolved_reason:
                raise ValueError("an unresolved entry must say why")
            if not self.augmentation.is_empty:
                raise ValueError("an unresolved entry may not carry a carrier")
        return self

    @property
    def fingerprint(self) -> str:
        """A digest of this entry's additions, separate from the original's."""

        payload = json.dumps(
            self.augmentation.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        material = f"{self.original_fingerprint}\0{payload}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()


class AugmentationManifestV1(FrozenStrictModel):
    """Every entry, keyed by the fingerprint of the v1 record it augments."""

    schema_version: Annotated[str, StringConstraints(min_length=1, max_length=64)] = (
        CORPUS_V2_SCHEMA_VERSION
    )
    migration_version: Annotated[
        str, StringConstraints(min_length=1, max_length=64)
    ] = CORPUS_V2_MIGRATION_VERSION
    entries: tuple[AugmentationEntryV1, ...] = Field(default=(), max_length=512)

    @model_validator(mode="after")
    def validate_manifest(self) -> "AugmentationManifestV1":
        seen = [entry.original_fingerprint for entry in self.entries]
        if len(seen) != len(set(seen)):
            raise ValueError("a manifest may bind one original record once")
        return self

    def by_fingerprint(self) -> dict[str, AugmentationEntryV1]:
        return {entry.original_fingerprint: entry for entry in self.entries}

    @property
    def digest(self) -> str:
        material = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def assert_manifest_has_no_answer_authority(value: Any) -> None:
    """Refuse a manifest that names any answer-bearing field, at any depth."""

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                if isinstance(key, str) and _normalized_key(key) in (
                    FORBIDDEN_MANIFEST_FIELDS
                ):
                    raise MigrationError(
                        MigrationReason.manifest_contains_answer_field
                    )
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(value)


def canonical_record_bytes(record: Mapping[str, Any]) -> bytes:
    """One byte sequence per v1 record, stable across key order."""

    return json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def record_fingerprint(record: Mapping[str, Any]) -> str:
    """The v1 record's identity, used as the manifest key."""

    return hashlib.sha256(canonical_record_bytes(record)).hexdigest()


class MigratedRecordV1(FrozenStrictModel):
    """One v2 record: the original, untouched, plus what was added to it."""

    schema_version: Annotated[str, StringConstraints(min_length=1, max_length=64)] = (
        CORPUS_V2_SCHEMA_VERSION
    )
    original_fingerprint: Sha256
    augmentation_fingerprint: Sha256 | None = None
    augmentation: CorpusV2AugmentationV1 = Field(
        default_factory=CorpusV2AugmentationV1
    )
    review_status: ReviewStatus = ReviewStatus.unresolved

    @property
    def augmented(self) -> bool:
        return not self.augmentation.is_empty


def migrate_record(
    record: Mapping[str, Any],
    manifest: AugmentationManifestV1,
    *,
    known_entity_ids: Sequence[str] = (),
    known_interval_ids: Sequence[str] = (),
    known_event_ids: Sequence[str] = (),
    known_evidence_ids: Sequence[str] = (),
    known_interaction_ids: Sequence[str] = (),
    known_query_ids: Sequence[str] = (),
    authored_ids: Sequence[str] = (),
    draft_payload: Mapping[str, Any] | None = None,
) -> MigratedRecordV1:
    """Bind one v1 record to its manifest entry, or leave it unresolved.

    A record with no entry is not an error and is not upgraded: it comes back
    with an empty augmentation and `unresolved` status, which is what "the
    author could not state this from the source" looks like in the archive.

    `draft_payload`, when supplied, is the record's own projected v1 Draft, and
    the fill-only merge contract is checked against it here — at migration
    time, before any archive is built — so a conflicting entry never becomes a
    candidate record at all.
    """

    fingerprint = record_fingerprint(record)
    entry = manifest.by_fingerprint().get(fingerprint)
    if entry is None:
        return MigratedRecordV1(
            original_fingerprint=fingerprint, review_status=ReviewStatus.unresolved
        )
    if entry.review_status is ReviewStatus.unresolved:
        return MigratedRecordV1(
            original_fingerprint=fingerprint, review_status=ReviewStatus.unresolved
        )
    try:
        validate_augmentation(
            entry.augmentation,
            known_entity_ids=known_entity_ids,
            known_interval_ids=known_interval_ids,
            known_event_ids=known_event_ids,
            known_evidence_ids=known_evidence_ids,
            known_interaction_ids=known_interaction_ids,
            known_query_ids=known_query_ids,
            authored_ids=authored_ids,
        )
    except V2ValidationError as exc:
        raise MigrationError(
            MigrationReason.augmentation_rejected, detail=exc.reason
        ) from None
    if draft_payload is not None:
        try:
            assert_fill_only_merge(draft_payload, entry.augmentation)
        except V2MergeConflict as exc:
            raise MigrationError(
                MigrationReason.augmentation_conflicts_with_source,
                detail=exc.reasons,
            ) from None
    return MigratedRecordV1(
        original_fingerprint=fingerprint,
        augmentation_fingerprint=entry.fingerprint,
        augmentation=entry.augmentation,
        review_status=entry.review_status,
    )


def rollback_to_v1(
    migrated: MigratedRecordV1, originals: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any]:
    """Recover the exact v1 record a migrated record came from.

    Deterministic and total: the fingerprint is the key, so a rollback either
    returns the original bytes or fails loudly.  There is no partial unwind.
    """

    original = originals.get(migrated.original_fingerprint)
    if original is None:
        raise MigrationError(MigrationReason.manifest_fingerprint_mismatch)
    if record_fingerprint(original) != migrated.original_fingerprint:
        raise MigrationError(MigrationReason.original_record_mutated)
    return original


def build_candidate_archive(
    records: Iterable[Mapping[str, Any]],
    manifest: AugmentationManifestV1,
    *,
    context_ids: Mapping[str, Mapping[str, Sequence[str]]] | None = None,
    draft_payloads: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[MigratedRecordV1, ...]:
    """Migrate a whole archive, in the order the records arrive.

    `context_ids` supplies each record's own identifier sets, keyed by
    fingerprint, so the validator can refuse a carrier that references
    something the source does not contain.  `draft_payloads` supplies each
    record's projected v1 Draft, keyed the same way, so the fill-only merge
    contract is enforced during migration and a conflicting entry fails the
    build rather than surviving into a candidate archive.
    """

    assert_manifest_has_no_answer_authority(manifest.model_dump(mode="json"))
    context_ids = context_ids or {}
    draft_payloads = draft_payloads or {}
    migrated: list[MigratedRecordV1] = []
    for record in records:
        fingerprint = record_fingerprint(record)
        known = context_ids.get(fingerprint, {})
        migrated.append(
            migrate_record(
                record,
                manifest,
                known_entity_ids=known.get("entities", ()),
                known_interval_ids=known.get("intervals", ()),
                known_event_ids=known.get("events", ()),
                known_evidence_ids=known.get("evidence", ()),
                known_interaction_ids=known.get("interactions", ()),
                known_query_ids=known.get("queries", ()),
                authored_ids=known.get("authored", ()),
                draft_payload=draft_payloads.get(fingerprint),
            )
        )
    return tuple(migrated)


def archive_digest(migrated: Sequence[MigratedRecordV1]) -> str:
    """A deterministic digest of a whole candidate archive."""

    material = json.dumps(
        [item.model_dump(mode="json") for item in migrated],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


__all__ = [
    "CORPUS_V2_MIGRATION_VERSION",
    "FORBIDDEN_MANIFEST_FIELDS",
    "AugmentationEntryV1",
    "AugmentationManifestV1",
    "MigratedRecordV1",
    "MigrationError",
    "MigrationReason",
    "ReviewStatus",
    "archive_digest",
    "assert_manifest_has_no_answer_authority",
    "build_candidate_archive",
    "canonical_record_bytes",
    "migrate_record",
    "record_fingerprint",
    "rollback_to_v1",
]
