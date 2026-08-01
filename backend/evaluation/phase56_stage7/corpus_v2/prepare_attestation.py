"""What Phase M prepared, attested, so a later phase cannot be told otherwise.

The defect this module closes is a *laundering* one, and it is the second shape
of a defect already fixed once.  The first shape was silent omission: a context
that failed was dropped from the run and therefore uncountable.  The ledger
closed that by giving every context a row.  But the ledger's rows were built
from what the runtime input file said, and the runtime input file was an
ordinary JSON document nobody had signed.  So the attack moved:

    {"scoring_handle": "<real handle>", "context_index": 42,
     "prepared_state": "projection_refused",
     "refusal_code": "projection_refused_no_draft",
     "draft_payload": null}

Every completeness check still passes.  The handle is expected, present, and
unique; the row is a *permitted* refusal, not a blocking one; the record set and
the completed-row set still agree — both are now empty.  Run it over all 97
runtime-completed contexts and the measurement reports a hundred-row ledger, a
hundred anticipated refusals, zero wrong, zero unscored, zero regressed, and
acceptance PASS.  Nothing was omitted.  Everything was excused.

An attestation is the missing half.  Phase M does not merely produce contexts,
it *states what it produced* — how many, in which order, under which handles, in
which prepared state, with a draft or without one — and hashes that statement.
A later phase re-derives the same statement from the file it was handed and
compares.  Changing a context's state changes the state map digest; swapping
which contexts were refused changes the refusal handle-set digest while leaving
the counts alone; editing a byte changes the file SHA.  There is no edit that
leaves all of them intact, because they are computed over different projections
of the same preparation.

Two properties are worth being explicit about.

*Counts are not enough.*  `refusal_handle_set_digest` covers sorted
``(context_index, scoring_handle, refusal_code)`` triples rather than
``{"projection_refused": 3}``.  An attacker who refuses a solvable context and
un-refuses an unsolvable one keeps every count identical, and that is precisely
the swap this digest exists to see.

*A file that vouches for itself vouches for nothing.*  Everything here is
checkable against an attestation, and an attestation is checkable against its
own digest — but an attacker who rewrites both files consistently defeats the
whole set.  That attack is not closed here; it is closed by Phase V, which
rebuilds the preparation from the corpus and the manifest and compares against
these values rather than within them.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Iterable, Sequence

from pydantic import Field, StringConstraints

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256
from evaluation.phase56_stage7.corpus_v2.canonical import canonical_digest
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (
    LedgerState,
    RefusalCode,
)


CORPUS_V2_PREPARE_ATTESTATION_VERSION = (
    "phase56-stage7-corpus-v2-prepare-attestation-v1"
)

_Handle = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Token = Annotated[str, StringConstraints(min_length=1, max_length=120)]
_CodeHead = Annotated[str, StringConstraints(min_length=7, max_length=64)]


class PreparedStateEntryV1(FrozenStrictModel):
    """One context's prepared disposition, as Phase M decided it.

    `draft_payload_present` is carried as its own boolean rather than inferred
    from `prepared_state`.  The two are supposed to agree — that is what the
    runtime input's cross-field validation enforces — and an attestation that
    only recorded the state could not witness a disagreement between them.
    """

    context_index: int = Field(ge=0)
    scoring_handle: _Handle
    prepared_state: LedgerState
    refusal_code: RefusalCode | None = None
    draft_payload_present: bool


class RefusalHandleEntryV1(FrozenStrictModel):
    """Which context was refused, and under which code.  Not how many."""

    context_index: int = Field(ge=0)
    scoring_handle: _Handle
    refusal_code: RefusalCode


def prepared_state_entries(
    contexts: Iterable[Any],
) -> tuple[PreparedStateEntryV1, ...]:
    """The prepared-state map, in corpus order.

    Order is content here.  A preparation that emitted the same contexts in a
    different order is a different preparation — the scoring handle is derived
    from the context's *position*, so a reordering silently re-points every
    handle at a different case.
    """

    return tuple(
        PreparedStateEntryV1(
            context_index=context.context_index,
            scoring_handle=context.scoring_handle,
            prepared_state=context.prepared_state,
            refusal_code=context.refusal_code,
            draft_payload_present=context.draft_payload is not None,
        )
        for context in contexts
    )


def refusal_handle_entries(
    contexts: Iterable[Any],
) -> tuple[RefusalHandleEntryV1, ...]:
    """Every refused context, sorted, with the handle it was refused under."""

    entries = [
        RefusalHandleEntryV1(
            context_index=context.context_index,
            scoring_handle=context.scoring_handle,
            refusal_code=context.refusal_code,
        )
        for context in contexts
        if context.refusal_code is not None
    ]
    entries.sort(key=lambda item: (item.context_index, item.scoring_handle))
    return tuple(entries)


def prepared_state_map_digest(contexts: Iterable[Any]) -> str:
    return canonical_digest(
        [entry.model_dump(mode="json") for entry in prepared_state_entries(contexts)]
    )


def refusal_handle_set_digest(contexts: Iterable[Any]) -> str:
    return canonical_digest(
        [entry.model_dump(mode="json") for entry in refusal_handle_entries(contexts)]
    )


def expected_handle_set_digest(contexts: Iterable[Any]) -> str:
    """Over the handles *in order*, not over a set.

    Named for the set it identifies and computed over the sequence, because two
    preparations with the same handles in a different order are not the same
    preparation and a set digest would call them equal.
    """

    return canonical_digest([context.scoring_handle for context in contexts])


def context_index_set_digest(contexts: Iterable[Any]) -> str:
    return canonical_digest([context.context_index for context in contexts])


def prepared_state_counts(contexts: Iterable[Any]) -> tuple[tuple[str, int], ...]:
    """Every state's count, including the zeroes.

    Zeroes are carried for the same reason the ledger carries them: a published
    ``runtime_failed: 0`` is a measurement, and a missing key is only an
    absence.
    """

    counts = {state.value: 0 for state in LedgerState}
    for context in contexts:
        counts[context.prepared_state.value] += 1
    return tuple(sorted(counts.items()))


def prepared_refusal_counts(contexts: Iterable[Any]) -> tuple[tuple[str, int], ...]:
    counts = {code.value: 0 for code in RefusalCode}
    for context in contexts:
        if context.refusal_code is not None:
            counts[context.refusal_code.value] += 1
    return tuple(sorted(counts.items()))


class PrepareAttestationV1(FrozenStrictModel):
    """Phase M's signed statement about the preparation it produced.

    Every hash here is named for what it is over.  `*_digest` is a canonical
    digest over content; `*_file_sha256` is over the bytes of a file on disk.
    They are different numbers and a reader must never have to guess which one
    a field carries — the previous evidence set reported "the manifest hash"
    for both, and the two were only ever equal by accident.
    """

    version: str = CORPUS_V2_PREPARE_ATTESTATION_VERSION
    # Which named campaign this preparation is.  Phase V is told the name by
    # the operator and refuses an attestation that names a different one, so
    # the population seal cannot be dodged by preparing an unnamed campaign.
    campaign_seal_name: _Token | None = None
    exact_code_head: _CodeHead

    original_v1_archive_sha256: Sha256

    augmentation_manifest_digest: Sha256
    augmentation_manifest_file_sha256: Sha256

    candidate_archive_digest: Sha256
    candidate_archive_file_sha256: Sha256

    runtime_input_digest: Sha256
    runtime_input_file_sha256: Sha256

    expected_context_count: int = Field(ge=0)
    context_index_set_digest: Sha256
    expected_handle_set_digest: Sha256

    prepared_state_map_digest: Sha256
    refusal_handle_set_digest: Sha256

    prepared_state_counts: tuple[tuple[str, int], ...] = ()
    prepared_refusal_counts: tuple[tuple[str, int], ...] = ()
    unresolved_augmentation_count: int = Field(default=0, ge=0)

    attestation_digest: Sha256

    def digest_material(self) -> Any:
        return self.model_dump(mode="json", exclude={"attestation_digest"})

    def recomputed_digest(self) -> str:
        return canonical_digest(self.digest_material())

    def digest_is_intact(self) -> bool:
        return self.recomputed_digest() == self.attestation_digest


class PrepareAttestationRefused(RuntimeError):
    """An attestation that cannot be trusted is not used to admit a run."""


def build_prepare_attestation(
    *,
    campaign_seal_name: str | None,
    exact_code_head: str,
    original_v1_archive_sha256: str,
    augmentation_manifest_digest: str,
    augmentation_manifest_file_sha256: str,
    candidate_archive_digest: str,
    candidate_archive_file_sha256: str,
    runtime_input_digest: str,
    runtime_input_file_sha256: str,
    contexts: Sequence[Any],
    unresolved_augmentation_count: int = 0,
) -> PrepareAttestationV1:
    """Attest one preparation.  The digest is over the model's own dump.

    Built twice, as the snapshot is: once with a placeholder so the model's
    canonical serialization is what gets hashed, then again from that hash.
    Hashing a hand-assembled dict instead would let the attestation's own
    material and its published fields drift apart.
    """

    draft = {
        "campaign_seal_name": campaign_seal_name,
        "exact_code_head": exact_code_head,
        "original_v1_archive_sha256": original_v1_archive_sha256,
        "augmentation_manifest_digest": augmentation_manifest_digest,
        "augmentation_manifest_file_sha256": augmentation_manifest_file_sha256,
        "candidate_archive_digest": candidate_archive_digest,
        "candidate_archive_file_sha256": candidate_archive_file_sha256,
        "runtime_input_digest": runtime_input_digest,
        "runtime_input_file_sha256": runtime_input_file_sha256,
        "expected_context_count": len(contexts),
        "context_index_set_digest": context_index_set_digest(contexts),
        "expected_handle_set_digest": expected_handle_set_digest(contexts),
        "prepared_state_map_digest": prepared_state_map_digest(contexts),
        "refusal_handle_set_digest": refusal_handle_set_digest(contexts),
        "prepared_state_counts": prepared_state_counts(contexts),
        "prepared_refusal_counts": prepared_refusal_counts(contexts),
        "unresolved_augmentation_count": unresolved_augmentation_count,
    }
    provisional = PrepareAttestationV1(**draft, attestation_digest="0" * 64)
    return PrepareAttestationV1(
        **draft, attestation_digest=provisional.recomputed_digest()
    )


def load_prepare_attestation(body: str) -> PrepareAttestationV1:
    """Re-read an attestation from its own bytes, or refuse it.

    A refusal here is never a repair.  A truncated file, a schema that is not
    this one, or a digest that does not match its own contents all mean the same
    thing: nothing downstream may be admitted on this document's word.
    """

    try:
        attestation = PrepareAttestationV1.model_validate_json(body)
    except Exception as exc:  # noqa: BLE001 — re-raised as the typed refusal
        raise PrepareAttestationRefused(
            f"the prepare attestation could not be read as one: {type(exc).__name__}"
        ) from None
    if attestation.version != CORPUS_V2_PREPARE_ATTESTATION_VERSION:
        raise PrepareAttestationRefused(
            f"the prepare attestation is version {attestation.version}, "
            f"not {CORPUS_V2_PREPARE_ATTESTATION_VERSION}"
        )
    if not attestation.digest_is_intact():
        raise PrepareAttestationRefused(
            "the prepare attestation digest does not match its contents"
        )
    return attestation


class PrepareBindingFailure(str, Enum):
    """The machine-checkable names a mis-bound preparation fails under.

    Names rather than a boolean, and a *set* rather than the first one found,
    so a negative control can assert the gate it meant to hit instead of
    whichever gate happens to be checked first.  A state-map attack that only
    ever showed up as "the file hash changed" would not be evidence that the
    state map is checked at all.
    """

    attestation_digest_mismatch = "prepare_attestation_digest_mismatch"
    campaign_seal_name_mismatch = "prepare_campaign_seal_name_mismatch"
    exact_code_head_mismatch = "prepare_exact_code_head_mismatch"
    corpus_archive_mismatch = "prepare_corpus_archive_mismatch"
    manifest_digest_mismatch = "prepare_manifest_digest_mismatch"
    manifest_file_sha_mismatch = "prepare_manifest_file_sha_mismatch"
    candidate_archive_digest_mismatch = "prepare_candidate_archive_digest_mismatch"
    candidate_archive_file_sha_mismatch = (
        "prepare_candidate_archive_file_sha_mismatch"
    )
    runtime_input_digest_mismatch = "prepare_runtime_input_digest_mismatch"
    runtime_input_file_sha_mismatch = "prepare_runtime_input_file_sha_mismatch"
    context_count_mismatch = "prepare_context_count_mismatch"
    context_index_set_mismatch = "prepare_context_index_set_mismatch"
    expected_handle_set_mismatch = "prepare_expected_handle_set_mismatch"
    prepared_state_map_mismatch = "prepare_prepared_state_map_mismatch"
    refusal_handle_set_mismatch = "prepare_refusal_handle_set_mismatch"
    state_counts_mismatch = "prepare_state_counts_mismatch"
    refusal_counts_mismatch = "prepare_refusal_counts_mismatch"
    unresolved_augmentation_count_mismatch = (
        "prepare_unresolved_augmentation_count_mismatch"
    )


def runtime_input_binding_failures(
    attestation: PrepareAttestationV1,
    bundle: Any,
    *,
    runtime_input_file_sha256: str,
    exact_code_head: str | None = None,
) -> tuple[str, ...]:
    """Every way this runtime input is not the one that was attested.

    Re-derives the attested projections from the bundle rather than reading the
    bundle's own opinion of them, which is the whole point: a file that carried
    its own state-map digest would be attesting to itself.

    Deliberately *not* short-circuiting.  A single laundered context changes
    the state map and the file hash; a byte edit to a problem text changes the
    file hash and not the state map; a refusal swap changes the state map and
    the refusal set and neither count.  Reporting all of them is what lets each
    control name the gate it is actually exercising.
    """

    failures: list[str] = []
    if not attestation.digest_is_intact():
        failures.append(PrepareBindingFailure.attestation_digest_mismatch.value)
    if attestation.runtime_input_file_sha256 != runtime_input_file_sha256:
        failures.append(PrepareBindingFailure.runtime_input_file_sha_mismatch.value)
    if attestation.runtime_input_digest != bundle.digest:
        failures.append(PrepareBindingFailure.runtime_input_digest_mismatch.value)
    if attestation.original_v1_archive_sha256 != bundle.original_v1_archive_sha256:
        failures.append(PrepareBindingFailure.corpus_archive_mismatch.value)
    if attestation.augmentation_manifest_digest != bundle.augmentation_manifest_sha256:
        failures.append(PrepareBindingFailure.manifest_digest_mismatch.value)
    if attestation.candidate_archive_digest != bundle.candidate_archive_sha256:
        failures.append(
            PrepareBindingFailure.candidate_archive_digest_mismatch.value
        )
    contexts = bundle.contexts
    if attestation.expected_context_count != len(contexts):
        failures.append(PrepareBindingFailure.context_count_mismatch.value)
    if attestation.context_index_set_digest != context_index_set_digest(contexts):
        failures.append(PrepareBindingFailure.context_index_set_mismatch.value)
    if attestation.expected_handle_set_digest != expected_handle_set_digest(contexts):
        failures.append(PrepareBindingFailure.expected_handle_set_mismatch.value)
    if attestation.prepared_state_map_digest != prepared_state_map_digest(contexts):
        failures.append(PrepareBindingFailure.prepared_state_map_mismatch.value)
    if attestation.refusal_handle_set_digest != refusal_handle_set_digest(contexts):
        failures.append(PrepareBindingFailure.refusal_handle_set_mismatch.value)
    if tuple(attestation.prepared_state_counts) != prepared_state_counts(contexts):
        failures.append(PrepareBindingFailure.state_counts_mismatch.value)
    if tuple(attestation.prepared_refusal_counts) != prepared_refusal_counts(contexts):
        failures.append(PrepareBindingFailure.refusal_counts_mismatch.value)
    if attestation.unresolved_augmentation_count != (
        bundle.unresolved_augmentation_count
    ):
        failures.append(
            PrepareBindingFailure.unresolved_augmentation_count_mismatch.value
        )
    if exact_code_head is not None and attestation.exact_code_head != exact_code_head:
        failures.append(PrepareBindingFailure.exact_code_head_mismatch.value)
    return tuple(sorted(set(failures)))


__all__ = [
    "CORPUS_V2_PREPARE_ATTESTATION_VERSION",
    "PrepareAttestationRefused",
    "PrepareAttestationV1",
    "PrepareBindingFailure",
    "PreparedStateEntryV1",
    "RefusalHandleEntryV1",
    "build_prepare_attestation",
    "context_index_set_digest",
    "expected_handle_set_digest",
    "load_prepare_attestation",
    "prepared_refusal_counts",
    "prepared_state_counts",
    "prepared_state_entries",
    "prepared_state_map_digest",
    "refusal_handle_entries",
    "refusal_handle_set_digest",
    "runtime_input_binding_failures",
]
