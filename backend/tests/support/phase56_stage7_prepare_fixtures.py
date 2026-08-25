"""Synthetic preparations, so a snapshot test does not need a public corpus.

A `ShadowRuntimeSnapshotV2` now requires a `PrepareBindingV1` — the projection
of Phase M's attestation that says which preparation the run was admitted on.
That is a deliberate fail-closed choice: an optional binding would let a
snapshot omit it and still load, score and be quoted, which is exactly the
property the attestation exists to remove.

The consequence is that every test which freezes a snapshot needs a binding,
and building one by hand at each site would mean a dozen hand-assembled digests
nobody checks.  So these helpers build a real attestation over real
`RuntimeContextInputV2` values and project it, which means the fixtures satisfy
the same cross-field contract the production path does.  A test that could only
be written with an inconsistent binding is a test describing something Phase M
cannot produce.

Everything here is synthetic.  No public archive is read.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from evaluation.phase56_stage7.corpus_v2.prepare_attestation import (
    PrepareAttestationV1,
    build_prepare_attestation,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (
    RuntimeContextInputV2,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (
    LedgerState,
    RefusalCode,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (
    PrepareBindingV1,
    prepare_binding_from_attestation,
    scoring_handle,
)

SYNTHETIC_ARCHIVE = "a" * 64
SYNTHETIC_MANIFEST = "b" * 64
SYNTHETIC_CANDIDATE = "c" * 64
SYNTHETIC_CODE_HEAD = "deadbeef"


def synthetic_handle(index: int, *, archive: str = SYNTHETIC_ARCHIVE) -> str:
    return scoring_handle(original_v1_archive_sha256=archive, context_index=index)


def prepared_context(
    index: int,
    *,
    refused: bool = False,
    archive: str = SYNTHETIC_ARCHIVE,
) -> RuntimeContextInputV2:
    """One context in a state Phase M can actually produce.

    `refused` picks between the only two preparable states.  A refused context
    carries nothing but its handle and its reason, because that is what the
    cross-field contract requires and what a laundering attempt cannot imitate.
    """

    if refused:
        return RuntimeContextInputV2(
            scoring_handle=synthetic_handle(index, archive=archive),
            context_index=index,
            prepared_state=LedgerState.projection_refused,
            refusal_code=RefusalCode.projection_refused_no_draft,
        )
    return RuntimeContextInputV2(
        scoring_handle=synthetic_handle(index, archive=archive),
        context_index=index,
        prepared_state=LedgerState.runtime_completed,
        draft_payload={"synthetic": index},
    )


def synthetic_attestation(
    contexts: Sequence[RuntimeContextInputV2],
    *,
    campaign_seal_name: str | None = None,
    exact_code_head: str = SYNTHETIC_CODE_HEAD,
    archive: str = SYNTHETIC_ARCHIVE,
    manifest: str = SYNTHETIC_MANIFEST,
    candidate: str = SYNTHETIC_CANDIDATE,
    runtime_input_digest: str = "d" * 64,
    runtime_input_file_sha256: str = "e" * 64,
) -> PrepareAttestationV1:
    return build_prepare_attestation(
        campaign_seal_name=campaign_seal_name,
        exact_code_head=exact_code_head,
        original_v1_archive_sha256=archive,
        augmentation_manifest_digest=manifest,
        augmentation_manifest_file_sha256="f" * 64,
        candidate_archive_digest=candidate,
        candidate_archive_file_sha256="0" * 64,
        runtime_input_digest=runtime_input_digest,
        runtime_input_file_sha256=runtime_input_file_sha256,
        contexts=contexts,
    )


def attestation_for_ledger(
    ledger: Iterable, *, archive: str = SYNTHETIC_ARCHIVE
) -> PrepareAttestationV1:
    """The attestation `binding_for_ledger` projects, for tests that need both.

    A process-level test has to put a real attestation file on disk beside the
    snapshot, and it must be the one the snapshot's binding came from — two
    independently built attestations would disagree and the test would be
    exercising the binding check rather than whatever it meant to.
    """

    contexts = tuple(
        prepared_context(
            index,
            refused=entry.state is not LedgerState.runtime_completed,
            archive=archive,
        )
        for index, entry in enumerate(ledger)
    )
    return synthetic_attestation(contexts, archive=archive)


def binding_for_ledger(ledger: Iterable, *, archive: str = SYNTHETIC_ARCHIVE):
    """A binding whose population has the same shape as a ledger's.

    Derived from the ledger the test already built — how many contexts, and
    which of them are refusals — rather than returned as a constant, so a test
    that changes its ledger gets a binding that changed with it.  Positions are
    taken from the ledger's own order; a test whose ledger is not in corpus
    order gets a shape-compatible binding rather than a position-identical one,
    which is all `freeze_runtime_snapshot` needs and all these tests assert
    about it.
    """

    return prepare_binding_from_attestation(
        attestation_for_ledger(ledger, archive=archive)
    )


__all__ = [
    "SYNTHETIC_ARCHIVE",
    "SYNTHETIC_CANDIDATE",
    "SYNTHETIC_CODE_HEAD",
    "SYNTHETIC_MANIFEST",
    "PrepareBindingV1",
    "attestation_for_ledger",
    "binding_for_ledger",
    "prepared_context",
    "synthetic_attestation",
    "synthetic_handle",
]
