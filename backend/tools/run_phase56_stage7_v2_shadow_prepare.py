"""Phase M — build the v2 candidate archive, the runtime input, and attest them.

This command reads the corpus and the manifest, migrates one against the other,
and publishes three artifacts as **one generation**: the candidate archive, the
gold-free bundle the runtime phase will be given, and a restricted attestation
of what it prepared.  It runs no pipeline and compares no answer.

Splitting it out is what lets Phase R be provably gold-free.  When one process
did all three jobs it held `PublicCorpusCaseV1` objects — which contain `gold` —
from the first line to the last, so the claim "the runtime never saw an expected
answer" could only ever be a claim about discipline.  Here the corpus is read
once, by a command that does not solve, and what leaves is a
`ShadowRuntimeInputV2`: a type with no field an expectation could be written
into.

Every context in the corpus gets an entry in the bundle, including the ones
whose v1 record cannot be projected.  A refused context that stayed in the file
is a context the next phase still has to account for; a refused context that was
dropped here would be one nobody could notice was missing.

**The attestation is the new half, and it exists because a complete list is not
the same as an honest one.**  Every completeness rule downstream was computed
from the bundle's own contents, so an edited bundle simply moved the rules'
answers with it: relabel a solvable context as `projection_refused` with a null
draft and the ledger still has its row, the refusal is still one the contract
anticipates, and the record set still agrees with the completed set — because
both are now empty.  The attestation states what this command actually produced
— the order, the handles, the prepared state of each context, which ones were
refused and under which code — and hashes it, so a later phase can re-derive the
same statement from the file it was handed and see the disagreement.

The forbidden-key scan runs on the raw payload *before* validation and before
any write, so a bundle naming a gold member never reaches disk at all.

Publication is a single commit point, not three renames.  An earlier fix staged
each artifact beside its final path and renamed all three at the end — which
kept a *refused* preparation off the final paths, but still left the success
path publishing through three consecutive renames.  Each rename was atomic; the
set was not.  An exception or a process kill between them left the final paths
holding artifacts from two different preparations, and nothing could undo the
renames that had already happened.  So the artifacts now live together in an
immutable generation directory under ``--publication-root``, staged in a
per-run private directory, validated in full — read-back hashes, attestation,
campaign seal, cross-artifact binding — and made authoritative by exactly one
``os.replace`` of the ``CURRENT.json`` pointer.  A reader resolving the
publication sees the previous complete generation or the new complete
generation, never a mixture.  On success this command prints
``STAGE7_V2_PREPARE_PUBLICATION_ID=<generation-id>`` so the orchestrator can
pin Phase V, Phase R and Phase G to exactly this generation.

Failure semantics, stated exactly.  A refusal before the generation is promoted
removes this run's staging directory and touches nothing else: the previous
``CURRENT.json`` and every existing generation are byte-unchanged.  A failure
between the promote and the pointer replace leaves the previous authority
standing and the new generation on disk as a complete but *unreferenced*
orphan — deliberately, because deleting it could delete a directory another
writer just committed to.  No fixed-name staging file exists anywhere in this
protocol, so two concurrent preparations cannot overwrite each other's staging.

Exit 0 when the generation was published and the pointer committed, 2 when the
preparation could not be built or published honestly — and in that case the
previous authority holds exactly what it held before.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.corpus_v2.campaign_seal import (  # noqa: E402
    campaign_seal_failures,
    resolve_campaign_seal,
)
from evaluation.phase56_stage7.corpus_v2.canonical import file_sha256  # noqa: E402
from evaluation.phase56_stage7.corpus_v2.prepare_attestation import (  # noqa: E402
    build_prepare_attestation,
    runtime_input_binding_failures,
)
from evaluation.phase56_stage7.corpus_v2.prepare_builder import (  # noqa: E402
    PrepareBuildRefused,
    build_prepared_campaign,
)
from evaluation.phase56_stage7.corpus_v2.publication import (  # noqa: E402
    CANDIDATE_ARCHIVE_NAME,
    PREPARE_ATTESTATION_NAME,
    RUNTIME_INPUT_NAME,
    GenerationTransaction,
    PublicationRefused,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (  # noqa: E402
    RuntimeInputRefused,
    load_runtime_input,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (  # noqa: E402
    LedgerState,
)

PREPARE_FAILURE_EXIT = 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-archive", type=Path, required=True)
    parser.add_argument(
        "--expected-corpus-sha256",
        type=str,
        default=None,
        help=(
            "optional exact SHA-256 for a separately named reproducible "
            "campaign archive. Omitted preserves the frozen Phase 56 public "
            "archive identity."
        ),
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--publication-root",
        type=Path,
        required=True,
        help=(
            "the directory that holds immutable generations and the CURRENT "
            "pointer. The three artifacts are published together inside one "
            "generation here; there is no flat-path publication mode."
        ),
    )
    parser.add_argument(
        "--exact-code-head",
        type=str,
        required=True,
        help=(
            "the commit every artifact in this preparation is evidence about. "
            "Required: an attestation that did not name one could be presented "
            "beside any code head at all."
        ),
    )
    parser.add_argument(
        "--campaign-seal",
        type=str,
        default=None,
        help=(
            "the named population contract this preparation must satisfy, e.g. "
            "phase56-stage7-v2-public-campaign-v1. Recorded in the attestation "
            "so a later phase enforces the seal the preparation claimed rather "
            "than whichever one it was asked to."
        ),
    )
    args = parser.parse_args()

    try:
        if args.expected_corpus_sha256 is None:
            prepared = build_prepared_campaign(
                corpus_archive=args.corpus_archive, manifest=args.manifest
            )
        else:
            prepared = build_prepared_campaign(
                corpus_archive=args.corpus_archive,
                manifest=args.manifest,
                expected_corpus_sha256=args.expected_corpus_sha256,
            )
    except (PrepareBuildRefused, RuntimeInputRefused) as exc:
        print(f"STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return PREPARE_FAILURE_EXIT

    contexts = prepared.runtime_input.contexts

    def _refuse(reason: str) -> int:
        print(f"STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:{reason}", file=sys.stderr)
        return PREPARE_FAILURE_EXIT

    # Nothing becomes authoritative until every gate below has passed.  The
    # gates need file hashes and file hashes need bytes on disk, so the three
    # artifacts are staged in this run's private generation directory, judged
    # there, and made visible by one pointer replace at the very end.  A
    # refused preparation leaves the previous authority holding exactly what
    # it held before this run started.
    try:
        transaction = GenerationTransaction(args.publication_root)
    except PublicationRefused as exc:
        return _refuse(str(exc))

    with transaction:
        try:
            candidate_file_sha = transaction.stage(
                CANDIDATE_ARCHIVE_NAME, prepared.candidate_body
            )
        except PublicationRefused:
            return _refuse("prepare_candidate_archive_write_mismatch")

        try:
            bundle_file_sha = transaction.stage(
                RUNTIME_INPUT_NAME, prepared.runtime_input_body
            )
        except PublicationRefused:
            return _refuse("prepare_runtime_input_write_mismatch")

        attestation = build_prepare_attestation(
            campaign_seal_name=args.campaign_seal,
            exact_code_head=args.exact_code_head,
            original_v1_archive_sha256=prepared.original_v1_archive_sha256,
            augmentation_manifest_digest=prepared.augmentation_manifest_digest,
            augmentation_manifest_file_sha256=(
                prepared.augmentation_manifest_file_sha256
            ),
            candidate_archive_digest=prepared.candidate_archive_digest,
            candidate_archive_file_sha256=candidate_file_sha,
            runtime_input_digest=prepared.runtime_input.digest,
            runtime_input_file_sha256=bundle_file_sha,
            contexts=contexts,
            unresolved_augmentation_count=prepared.unresolved_augmentation_count,
        )

        # A named seal is checked here as well as downstream.  Phase M is the
        # phase that can still refuse to produce the artifacts at all, and a
        # preparation whose population does not match the campaign it claims to
        # be is not a preparation anyone should be handed.
        if args.campaign_seal is not None:
            seal = resolve_campaign_seal(args.campaign_seal)
            if seal is None:
                return _refuse("campaign_seal_unknown")
            seal_failures = campaign_seal_failures(attestation, seal)
            if seal_failures:
                return _refuse(",".join(seal_failures))

        attestation_body = (
            json.dumps(
                attestation.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        try:
            attestation_file_sha = transaction.stage(
                PREPARE_ATTESTATION_NAME, attestation_body
            )
        except PublicationRefused:
            return _refuse("prepare_attestation_write_mismatch")

        # The generation is judged as a reader would see it — from the staged
        # bytes, not from the values still in memory — before any authority
        # moves.  This is the whole-generation validation: the runtime input
        # reloads, and every binding between it and the attestation holds.
        staged_bundle_body = transaction.staged_body(RUNTIME_INPUT_NAME)
        try:
            staged_bundle = load_runtime_input(staged_bundle_body)
        except RuntimeInputRefused as exc:
            return _refuse(f"prepare_publication_binding_mismatch:{exc}")
        binding = runtime_input_binding_failures(
            attestation,
            staged_bundle,
            runtime_input_file_sha256=file_sha256(staged_bundle_body),
            exact_code_head=args.exact_code_head,
        )
        if binding:
            return _refuse(
                "prepare_publication_binding_mismatch:" + ",".join(binding)
            )

        try:
            published = transaction.commit(attestation.attestation_digest)
        except PublicationRefused as exc:
            return _refuse(str(exc))

    print(
        "STAGE7_V2_PREPARE_ORIGINAL_V1_ARCHIVE_SHA256="
        f"{prepared.original_v1_archive_sha256}"
    )
    print(
        "STAGE7_V2_PREPARE_MANIFEST_DIGEST="
        f"{prepared.augmentation_manifest_digest}"
    )
    print(
        "STAGE7_V2_PREPARE_MANIFEST_FILE_SHA256="
        f"{prepared.augmentation_manifest_file_sha256}"
    )
    print(
        "STAGE7_V2_PREPARE_CANDIDATE_ARCHIVE_SHA256="
        f"{prepared.candidate_archive_digest}"
    )
    print(f"STAGE7_V2_PREPARE_CANDIDATE_FILE_SHA256={candidate_file_sha}")
    print(
        f"STAGE7_V2_PREPARE_RUNTIME_INPUT_DIGEST={prepared.runtime_input.digest}"
    )
    print(f"STAGE7_V2_PREPARE_RUNTIME_INPUT_FILE_SHA256={bundle_file_sha}")
    print(
        "STAGE7_V2_PREPARE_ATTESTATION_DIGEST="
        f"{attestation.attestation_digest}"
    )
    print(f"STAGE7_V2_PREPARE_ATTESTATION_FILE_SHA256={attestation_file_sha}")
    print(f"STAGE7_V2_PREPARE_EXPECTED_CONTEXTS={len(contexts)}")
    print(
        "STAGE7_V2_PREPARE_CONTEXT_INDEX_SET_DIGEST="
        f"{attestation.context_index_set_digest}"
    )
    print(
        "STAGE7_V2_PREPARE_EXPECTED_HANDLE_SET_DIGEST="
        f"{attestation.expected_handle_set_digest}"
    )
    print(
        "STAGE7_V2_PREPARE_PREPARED_STATE_MAP_DIGEST="
        f"{attestation.prepared_state_map_digest}"
    )
    print(
        "STAGE7_V2_PREPARE_REFUSAL_HANDLE_SET_DIGEST="
        f"{attestation.refusal_handle_set_digest}"
    )
    for name, count in attestation.prepared_state_counts:
        print(f"STAGE7_V2_PREPARE_STATE_{name}={count}")
    for name, count in attestation.prepared_refusal_counts:
        print(f"STAGE7_V2_PREPARE_REFUSAL_{name}={count}")
    print(
        "STAGE7_V2_PREPARE_PROJECTION_REFUSED="
        + str(
            sum(
                1
                for item in contexts
                if item.prepared_state is LedgerState.projection_refused
            )
        )
    )
    print(f"STAGE7_V2_PREPARE_CAMPAIGN_SEAL={args.campaign_seal or 'none'}")
    print(f"STAGE7_V2_PREPARE_EXACT_CODE_HEAD={args.exact_code_head}")
    # The machine-readable pin.  The orchestrator captures this once and hands
    # the same generation to Phase V, Phase R and Phase G, so one pipeline
    # cannot straddle two publications however the pointer moves meanwhile.
    print(f"STAGE7_V2_PREPARE_PUBLICATION_ID={published.generation_id}")
    print("STAGE7_V2_PREPARE_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
