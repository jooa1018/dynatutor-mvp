"""The exact population this Stage 7 public campaign measures, frozen by name.

Generic completeness is necessary and it is not sufficient.  Every structural
rule in this evaluation is of the form "the three accountings agree with each
other", and an attacker who moves all three at once satisfies all of them.  The
laundering attack is exactly that: relabel every runtime-completed context as an
anticipated `projection_refused`, and the ledger, the record set and the handle
set agree perfectly about a measurement of nothing.

A seal is the outside reference those rules do not have.  It does not ask
whether the run is internally consistent; it asks whether it is *this campaign*
— the one whose numbers have been reported, reviewed and quoted.  A hundred
contexts, ninety-seven of which the v1 projection can express and three of which
it declines for want of a Draft, against one named corpus and one named
manifest.  A run that is coherent about some other population is not this
campaign's measurement, whatever else is true of it.

Counts alone would not do it.  `refusal_handle_set_digest` covers *which*
contexts were refused; a swap that refuses a solvable context and admits an
unsolvable one leaves 97/3 standing and changes this digest.  Order alone would
not do it either: the scoring handle is derived from a context's position, so a
reordering re-points every handle at a different case while preserving every
count, and `context_index_set_digest` and `expected_handle_set_digest` are
computed over sequences rather than sets for that reason.

**Provenance of these values, stated exactly.**  The population digests below —
context index set, expected handle set, prepared-state map, refusal handle set,
and the state and refusal counts — were regenerated from the approved public
corpus by two independent rebuilds that agreed, and they are *manifest-
independent* by construction: a context's prepared state is decided by
`project_case_to_draft`, which reads the v1 record and nothing else.  That was
confirmed empirically by rebuilding against two manifests with different
digests and getting the same four values.  The two manifest hashes are a
different matter and are recorded here from the authoritative checkpoint's own
evidence rather than from a rebuild, because the exact manifest is a restricted
out-of-tree artifact.  A seal check that cannot see that manifest fails on those
two fields, which is the correct outcome: it is what "this is not that campaign"
looks like, and it must not be silently softened into a pass.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from pydantic import Field, StringConstraints

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256


CORPUS_V2_CAMPAIGN_SEAL_VERSION = "phase56-stage7-corpus-v2-campaign-seal-v1"

STAGE7_PUBLIC_CAMPAIGN_SEAL_NAME = "phase56-stage7-v2-public-campaign-v1"
STAGE7_SUPPLEMENTAL_CAMPAIGN_SEAL_NAME = (
    "phase56-stage7-v2-supplemental-yield-campaign-v1"
)

_Token = Annotated[str, StringConstraints(min_length=1, max_length=120)]


class CampaignSealFailure(str, Enum):
    """The machine-checkable names a population-seal violation fails under."""

    unknown_seal = "campaign_seal_unknown"
    not_sealed = "campaign_seal_absent_from_attestation"
    name_mismatch = "campaign_seal_name_mismatch"
    corpus_archive_mismatch = "campaign_seal_corpus_archive_mismatch"
    manifest_digest_mismatch = "campaign_seal_manifest_digest_mismatch"
    manifest_file_sha_mismatch = "campaign_seal_manifest_file_sha_mismatch"
    context_count_mismatch = "campaign_seal_context_count_mismatch"
    context_index_set_mismatch = "campaign_seal_context_index_set_mismatch"
    expected_handle_set_mismatch = "campaign_seal_expected_handle_set_mismatch"
    prepared_state_map_mismatch = "campaign_seal_prepared_state_map_mismatch"
    refusal_handle_set_mismatch = "campaign_seal_refusal_handle_set_mismatch"
    state_counts_mismatch = "campaign_seal_state_counts_mismatch"
    refusal_counts_mismatch = "campaign_seal_refusal_counts_mismatch"


class CampaignPopulationSealV1(FrozenStrictModel):
    """One named campaign's population, as an acceptance contract.

    Deliberately a separate versioned object rather than constants hard-coded
    into the ledger's enums.  The ledger describes what *any* run may contain;
    this describes what *this* run must contain, and the two change for
    completely different reasons — a new refusal code is a contract change,
    while a corpus revision is a new campaign that should get its own seal
    rather than quietly editing this one.
    """

    version: str = CORPUS_V2_CAMPAIGN_SEAL_VERSION
    name: _Token
    original_v1_archive_sha256: Sha256
    augmentation_manifest_digest: Sha256
    augmentation_manifest_file_sha256: Sha256
    expected_context_count: int = Field(ge=0)
    context_index_set_digest: Sha256
    expected_handle_set_digest: Sha256
    prepared_state_map_digest: Sha256
    refusal_handle_set_digest: Sha256
    prepared_state_counts: tuple[tuple[str, int], ...]
    prepared_refusal_counts: tuple[tuple[str, int], ...]


STAGE7_PUBLIC_CAMPAIGN_SEAL_V1 = CampaignPopulationSealV1(
    name=STAGE7_PUBLIC_CAMPAIGN_SEAL_NAME,
    # The approved public corpus, dynatutor_beer12_ko_corpus_v1_public4.zip.
    original_v1_archive_sha256=(
        "cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef"
    ),
    # Recorded from the authoritative checkpoint's evidence.  Not regenerated
    # here: the manifest is a restricted out-of-tree artifact.
    augmentation_manifest_digest=(
        "c72229789cd417c70eb2533212508b259a9f8df903415f1f6aac710464929328"
    ),
    augmentation_manifest_file_sha256=(
        "95aca08407e9508364468fe7be3a373ad0fe6d3e028bb5d0aa79052717542579"
    ),
    expected_context_count=100,
    # Regenerated from the approved corpus by two independent rebuilds.
    context_index_set_digest=(
        "9dd50adbd73bc58bb391efca85d1436fcc4c19cb0bc2495ec0eeb4c1e42f6952"
    ),
    expected_handle_set_digest=(
        "571e7c40a8999bc04b820ac8d26f5278a76039a06f254da1cef72398711205fd"
    ),
    prepared_state_map_digest=(
        "d66a27bc98baed7d8c1f8c3210e9b3319b6d00fdd06143b8d515649d93df5c84"
    ),
    refusal_handle_set_digest=(
        "84efd8804e234c4f280b8e8dda665e70011732b53af6c5443d95f2a1d4966cc5"
    ),
    prepared_state_counts=(
        ("migration_refused", 0),
        ("projection_refused", 3),
        ("runtime_completed", 97),
        ("runtime_failed", 0),
        ("snapshot_rejected", 0),
    ),
    prepared_refusal_counts=(
        ("migration_refused_conflicting_entry", 0),
        ("migration_refused_unresolved_entry", 0),
        ("projection_refused_no_draft", 3),
        ("runtime_failed_unexpected_exception", 0),
        ("snapshot_rejected_incomplete_record", 0),
    ),
)

# A distinct, newly authored measurement.  It intentionally shares the
# approved public archive and its manifest-independent 97/3 prepared
# population with the historical campaign, but binds a new source-only
# nine-entry manifest.  Passing this seal says nothing about the unavailable
# historical manifest and cannot satisfy the historical Stage 7 acceptance
# claim.
STAGE7_SUPPLEMENTAL_CAMPAIGN_SEAL_V1 = CampaignPopulationSealV1(
    name=STAGE7_SUPPLEMENTAL_CAMPAIGN_SEAL_NAME,
    original_v1_archive_sha256=(
        "cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef"
    ),
    augmentation_manifest_digest=(
        "32aa3ce51e3006e533913b2f822251d22dccba2a379a35008f19e7a7e1aef7cd"
    ),
    augmentation_manifest_file_sha256=(
        "946cd6364669c123341d54999a87a468bc22f7260ea2b8500ddee267878bcd3a"
    ),
    expected_context_count=100,
    context_index_set_digest=(
        "9dd50adbd73bc58bb391efca85d1436fcc4c19cb0bc2495ec0eeb4c1e42f6952"
    ),
    expected_handle_set_digest=(
        "571e7c40a8999bc04b820ac8d26f5278a76039a06f254da1cef72398711205fd"
    ),
    prepared_state_map_digest=(
        "d66a27bc98baed7d8c1f8c3210e9b3319b6d00fdd06143b8d515649d93df5c84"
    ),
    refusal_handle_set_digest=(
        "84efd8804e234c4f280b8e8dda665e70011732b53af6c5443d95f2a1d4966cc5"
    ),
    prepared_state_counts=(
        ("migration_refused", 0),
        ("projection_refused", 3),
        ("runtime_completed", 97),
        ("runtime_failed", 0),
        ("snapshot_rejected", 0),
    ),
    prepared_refusal_counts=(
        ("migration_refused_conflicting_entry", 0),
        ("migration_refused_unresolved_entry", 0),
        ("projection_refused_no_draft", 3),
        ("runtime_failed_unexpected_exception", 0),
        ("snapshot_rejected_incomplete_record", 0),
    ),
)

CAMPAIGN_SEALS: dict[str, CampaignPopulationSealV1] = {
    STAGE7_PUBLIC_CAMPAIGN_SEAL_V1.name: STAGE7_PUBLIC_CAMPAIGN_SEAL_V1,
    STAGE7_SUPPLEMENTAL_CAMPAIGN_SEAL_V1.name: (
        STAGE7_SUPPLEMENTAL_CAMPAIGN_SEAL_V1
    ),
}


def resolve_campaign_seal(name: str) -> CampaignPopulationSealV1 | None:
    return CAMPAIGN_SEALS.get(name)


def campaign_seal_failures(
    attestation: Any, seal: CampaignPopulationSealV1
) -> tuple[str, ...]:
    """Every way this attestation is not this campaign, by name.

    All of them, not the first: a control that raises the refusal count from 3
    to 4 and a control that swaps which contexts were refused are different
    attacks, and each has to be able to assert the gate it exercised.
    """

    failures: list[str] = []
    if attestation.campaign_seal_name is None:
        failures.append(CampaignSealFailure.not_sealed.value)
    elif attestation.campaign_seal_name != seal.name:
        failures.append(CampaignSealFailure.name_mismatch.value)
    if attestation.original_v1_archive_sha256 != seal.original_v1_archive_sha256:
        failures.append(CampaignSealFailure.corpus_archive_mismatch.value)
    if attestation.augmentation_manifest_digest != seal.augmentation_manifest_digest:
        failures.append(CampaignSealFailure.manifest_digest_mismatch.value)
    if attestation.augmentation_manifest_file_sha256 != (
        seal.augmentation_manifest_file_sha256
    ):
        failures.append(CampaignSealFailure.manifest_file_sha_mismatch.value)
    if attestation.expected_context_count != seal.expected_context_count:
        failures.append(CampaignSealFailure.context_count_mismatch.value)
    if attestation.context_index_set_digest != seal.context_index_set_digest:
        failures.append(CampaignSealFailure.context_index_set_mismatch.value)
    if attestation.expected_handle_set_digest != seal.expected_handle_set_digest:
        failures.append(CampaignSealFailure.expected_handle_set_mismatch.value)
    if attestation.prepared_state_map_digest != seal.prepared_state_map_digest:
        failures.append(CampaignSealFailure.prepared_state_map_mismatch.value)
    if attestation.refusal_handle_set_digest != seal.refusal_handle_set_digest:
        failures.append(CampaignSealFailure.refusal_handle_set_mismatch.value)
    if tuple(attestation.prepared_state_counts) != seal.prepared_state_counts:
        failures.append(CampaignSealFailure.state_counts_mismatch.value)
    if tuple(attestation.prepared_refusal_counts) != seal.prepared_refusal_counts:
        failures.append(CampaignSealFailure.refusal_counts_mismatch.value)
    return tuple(sorted(set(failures)))


__all__ = [
    "CAMPAIGN_SEALS",
    "CORPUS_V2_CAMPAIGN_SEAL_VERSION",
    "STAGE7_PUBLIC_CAMPAIGN_SEAL_NAME",
    "STAGE7_PUBLIC_CAMPAIGN_SEAL_V1",
    "STAGE7_SUPPLEMENTAL_CAMPAIGN_SEAL_NAME",
    "STAGE7_SUPPLEMENTAL_CAMPAIGN_SEAL_V1",
    "CampaignPopulationSealV1",
    "CampaignSealFailure",
    "campaign_seal_failures",
    "resolve_campaign_seal",
]
