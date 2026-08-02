"""Phase M — build the v2 candidate archive, the runtime input, and attest them.

This command reads the corpus and the manifest, migrates one against the other,
and writes three files: the candidate archive, the gold-free bundle the runtime
phase will be given, and a restricted attestation of what it prepared.  It runs
no pipeline and compares no answer.

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
any write, so a bundle naming a gold member never reaches disk at all.  It used
to run after the file had been written.

Publication is all-or-nothing for the same reason.  The campaign seal is judged
over the attestation, the attestation carries each artifact's file hash, and a
file hash needs bytes on a filesystem — so the three artifacts are staged beside
their destinations, hashed from what was actually written, put to every gate,
and only then renamed into place.  Before, the candidate archive and the runtime
input went straight to their final paths and the seal was checked afterwards, so
a preparation refused for being some other campaign still left two of its three
artifacts sitting where the next phase looks for them.

Exit 0 when all three artifacts were published, 2 when they could not be built
honestly — and in that case the final paths hold whatever they held before.
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
)
from evaluation.phase56_stage7.corpus_v2.prepare_builder import (  # noqa: E402
    PrepareBuildRefused,
    build_prepared_campaign,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (  # noqa: E402
    RuntimeInputRefused,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (  # noqa: E402
    LedgerState,
)

PREPARE_FAILURE_EXIT = 2


def _stage(path: Path, body: str) -> tuple[Path, str] | None:
    """Write an artifact beside its final name without publishing it.

    Returns the staged path and the SHA-256 of the bytes that came back off the
    filesystem, or `None` when those are not the bytes we meant to write.  The
    hash is recomputed from the file rather than from `body` deliberately: a
    write that lost its tail would otherwise be attested as intact, and the
    attestation is the thing a later phase trusts.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(path.name + ".partial")
    staged.write_text(body, encoding="utf-8")
    written = file_sha256(staged.read_text(encoding="utf-8"))
    if written != file_sha256(body):
        return None
    return staged, written


def _publish(staged: list[tuple[Path, Path]]) -> None:
    """Move every staged artifact to its final path, after all gates passed.

    A rename is the last thing this command does, so the window in which the
    final paths could disagree with each other is one `replace` call wide and
    contains no decision that could still refuse the preparation.
    """

    for source, destination in staged:
        source.replace(destination)


def _discard(staged: list[tuple[Path, Path]]) -> None:
    """Remove the staged artifacts, leaving the final paths as they were found.

    Only the files this run created are touched.  A refused preparation must
    not take an earlier honest one down with it.
    """

    for source, _ in staged:
        source.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--runtime-input", type=Path, required=True)
    parser.add_argument("--prepare-attestation", type=Path, required=True)
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
        prepared = build_prepared_campaign(
            corpus_archive=args.corpus_archive, manifest=args.manifest
        )
    except (PrepareBuildRefused, RuntimeInputRefused) as exc:
        print(f"STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return PREPARE_FAILURE_EXIT

    contexts = prepared.runtime_input.contexts

    # Nothing reaches a final artifact path until every gate below has passed.
    # The gates need file hashes and file hashes need bytes on disk, so each
    # artifact is staged beside its destination and the three are published
    # together at the end.  A refused preparation leaves the final paths holding
    # exactly what they held before it ran.
    staged: list[tuple[Path, Path]] = []

    def _refuse(reason: str) -> int:
        _discard(staged)
        print(f"STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:{reason}", file=sys.stderr)
        return PREPARE_FAILURE_EXIT

    try:
        candidate = _stage(args.candidate_archive, prepared.candidate_body)
        if candidate is None:
            return _refuse("prepare_candidate_archive_write_mismatch")
        staged.append((candidate[0], args.candidate_archive))
        candidate_file_sha = candidate[1]

        bundle = _stage(args.runtime_input, prepared.runtime_input_body)
        if bundle is None:
            return _refuse("prepare_runtime_input_write_mismatch")
        staged.append((bundle[0], args.runtime_input))
        bundle_file_sha = bundle[1]

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
        attested = _stage(args.prepare_attestation, attestation_body)
        if attested is None:
            return _refuse("prepare_attestation_write_mismatch")
        staged.append((attested[0], args.prepare_attestation))
        attestation_file_sha = attested[1]

        _publish(staged)
    except BaseException:
        # An unanticipated failure must not publish half a preparation either.
        _discard(staged)
        raise

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
    print("STAGE7_V2_PREPARE_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
