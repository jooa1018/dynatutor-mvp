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

Exit 0 when all three artifacts were written, 2 when they could not be built
honestly.
"""

from __future__ import annotations

import argparse
import hashlib
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


def _write_atomic(path: Path, body: str) -> str:
    """Write a file that is either wholly there or not there at all.

    A half-written artifact is worse than a missing one: it has a name, a size
    and a hash, and nothing about it says it is a fragment.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(body, encoding="utf-8")
    temporary.replace(path)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


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

    # Everything is derived and scanned before anything is written, so a
    # preparation that fails leaves no partial evidence behind.
    candidate_file_sha = _write_atomic(
        args.candidate_archive, prepared.candidate_body
    )
    bundle_file_sha = _write_atomic(
        args.runtime_input, prepared.runtime_input_body
    )

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

    # A named seal is checked here as well as downstream.  Phase M is the phase
    # that can still refuse to produce the artifacts at all, and a preparation
    # whose population does not match the campaign it claims to be is not a
    # preparation anyone should be handed.
    if args.campaign_seal is not None:
        seal = resolve_campaign_seal(args.campaign_seal)
        if seal is None:
            print(
                "STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:campaign_seal_unknown",
                file=sys.stderr,
            )
            return PREPARE_FAILURE_EXIT
        seal_failures = campaign_seal_failures(attestation, seal)
        if seal_failures:
            print(
                "STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:" + ",".join(seal_failures),
                file=sys.stderr,
            )
            return PREPARE_FAILURE_EXIT

    attestation_body = (
        json.dumps(
            attestation.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    attestation_file_sha = _write_atomic(args.prepare_attestation, attestation_body)

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
    # Recomputed from the bytes that were written rather than from the bytes
    # that were meant to be: an atomic write that lost its tail would otherwise
    # be attested as intact.
    if file_sha256(args.runtime_input.read_text(encoding="utf-8")) != bundle_file_sha:
        print(
            "STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:prepare_runtime_input_write_mismatch",
            file=sys.stderr,
        )
        return PREPARE_FAILURE_EXIT
    print("STAGE7_V2_PREPARE_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
