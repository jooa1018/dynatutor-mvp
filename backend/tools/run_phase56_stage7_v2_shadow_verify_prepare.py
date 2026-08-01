"""Phase V — rebuild the preparation from the corpus, and check the artifacts.

This command exists because an attestation cannot verify itself, and neither can
a set of files that only reference each other.

Phase R checks the runtime input against the attestation: the file hash, the
canonical digest, the handle set, the prepared-state map, the refusal set, the
counts.  Every one of those checks is a comparison between two documents Phase M
wrote.  An attacker who edits the runtime input — laundering ninety-seven
runtime-completed contexts into anticipated refusals — and then rewrites the
attestation to describe the laundered file, recomputing its digest as the code
would, produces a pair that agrees with itself perfectly.  Phase R sees two
documents in complete accord and admits the run.  The measurement it then
performs is of nothing at all, and it passes.

Phase V is the outside reference.  It does not read the artifacts' opinion of
themselves; it opens the two inputs that cannot be quietly forged — the public
corpus archive, whose SHA-256 is frozen and published, and the augmentation
manifest, whose digest is published — reruns the deterministic preparation, and
compares its own result against the bytes on disk.  A laundered runtime input
disagrees with the rebuild at the first context it changed, whatever the
attestation says about it.

What this command may not do is as important as what it does.  It runs no
solver, executes no pipeline, scores nothing, compares no answer, and writes
nothing except its own verification report.  It reads the corpus — that is the
point — but the corpus is the *source*, not the gold: Phase V never opens an
expected answer, and the import-graph test pins that as a property rather than a
promise.  It also never repairs anything: a mismatch is a refusal, and the
process exits 2 with Phase R not invoked.

Ordering matters.  Phase V runs **between** Phase M and Phase R, so a
preparation that fails verification never reaches the runtime at all — zero
runtime calls, zero pipeline invocations, zero scores.

Exit 0 when the artifacts on disk are exactly what the corpus and the manifest
rebuild to, 2 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from enum import Enum
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.corpus_v2.campaign_seal import (  # noqa: E402
    CampaignSealFailure,
    campaign_seal_failures,
    resolve_campaign_seal,
)
from evaluation.phase56_stage7.corpus_v2.canonical import (  # noqa: E402
    canonical_digest,
    file_sha256,
)
from evaluation.phase56_stage7.corpus_v2.prepare_attestation import (  # noqa: E402
    PrepareAttestationRefused,
    context_index_set_digest,
    expected_handle_set_digest,
    load_prepare_attestation,
    prepared_refusal_counts,
    prepared_state_counts,
    prepared_state_map_digest,
    refusal_handle_set_digest,
)
from evaluation.phase56_stage7.corpus_v2.prepare_builder import (  # noqa: E402
    PrepareBuildRefused,
    build_prepared_campaign,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (  # noqa: E402
    RuntimeInputRefused,
    assert_bundle_has_no_gold,
    load_runtime_input,
)

VERIFY_FAILURE_EXIT = 2

VERIFY_REPORT_VERSION = "phase56-stage7-corpus-v2-prepare-verification-v1"
VERIFY_REPORT_CLASS = "EXPERIMENTAL_V2_SHADOW_PREPARE_VERIFICATION"


class ReplayFailure(str, Enum):
    """The names a replayed preparation fails under.

    Every one of these is a disagreement between what the corpus and the
    manifest rebuild to and what is on disk.  None of them can be satisfied by
    editing the artifacts consistently, which is the entire reason this phase
    exists.
    """

    attestation_unreadable = "replay_attestation_unreadable"
    runtime_input_unreadable = "replay_runtime_input_unreadable"
    rebuild_refused = "replay_rebuild_refused"
    corpus_archive_mismatch = "replay_corpus_archive_mismatch"
    manifest_digest_mismatch = "replay_manifest_digest_mismatch"
    manifest_file_sha_mismatch = "replay_manifest_file_sha_mismatch"
    candidate_archive_bytes_mismatch = "replay_candidate_archive_bytes_mismatch"
    candidate_archive_digest_mismatch = "replay_candidate_archive_digest_mismatch"
    candidate_archive_file_sha_mismatch = "replay_candidate_archive_file_sha_mismatch"
    runtime_input_bytes_mismatch = "replay_runtime_input_bytes_mismatch"
    runtime_input_digest_mismatch = "replay_runtime_input_digest_mismatch"
    runtime_input_file_sha_mismatch = "replay_runtime_input_file_sha_mismatch"
    context_count_mismatch = "replay_context_count_mismatch"
    context_index_set_mismatch = "replay_context_index_set_mismatch"
    expected_handle_set_mismatch = "replay_expected_handle_set_mismatch"
    prepared_state_map_mismatch = "replay_prepared_state_map_mismatch"
    refusal_handle_set_mismatch = "replay_refusal_handle_set_mismatch"
    state_counts_mismatch = "replay_state_counts_mismatch"
    refusal_counts_mismatch = "replay_refusal_counts_mismatch"
    unresolved_augmentation_count_mismatch = (
        "replay_unresolved_augmentation_count_mismatch"
    )
    exact_code_head_mismatch = "replay_exact_code_head_mismatch"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--runtime-input", type=Path, required=True)
    parser.add_argument("--prepare-attestation", type=Path, required=True)
    parser.add_argument("--verification-report", type=Path, required=True)
    parser.add_argument(
        "--exact-code-head",
        type=str,
        required=True,
        help="the commit the attestation must name as its own.",
    )
    parser.add_argument(
        "--campaign-seal",
        type=str,
        default=None,
        help=(
            "the named population contract this preparation must satisfy. "
            "The operator states it; the attestation must agree, so a "
            "preparation cannot escape the seal by declining to name one."
        ),
    )
    args = parser.parse_args()

    failures: list[str] = []

    attestation = None
    try:
        attestation = load_prepare_attestation(
            args.prepare_attestation.read_text(encoding="utf-8")
        )
    except (PrepareAttestationRefused, OSError) as exc:
        print(f"STAGE7_V2_VERIFY_PREPARE_DETAIL={exc}", file=sys.stderr)
        failures.append(ReplayFailure.attestation_unreadable.value)

    # The runtime input is re-read through the same loader Phase R uses, so the
    # cross-field contract and the raw gold scan are exercised here too — a
    # bundle Phase R would refuse is refused one phase earlier, before the
    # runtime is ever started.
    bundle = None
    runtime_input_body = ""
    try:
        runtime_input_body = args.runtime_input.read_text(encoding="utf-8")
        assert_bundle_has_no_gold(json.loads(runtime_input_body))
        bundle = load_runtime_input(runtime_input_body)
    except (RuntimeInputRefused, OSError, ValueError) as exc:
        print(f"STAGE7_V2_VERIFY_PREPARE_DETAIL={exc}", file=sys.stderr)
        failures.append(ReplayFailure.runtime_input_unreadable.value)

    # --- the independent rebuild, from the corpus and the manifest only ------
    rebuilt = None
    try:
        rebuilt = build_prepared_campaign(
            corpus_archive=args.corpus_archive, manifest=args.manifest
        )
    except (PrepareBuildRefused, RuntimeInputRefused, OSError) as exc:
        print(f"STAGE7_V2_VERIFY_PREPARE_DETAIL={exc}", file=sys.stderr)
        failures.append(ReplayFailure.rebuild_refused.value)

    if rebuilt is None or attestation is None:
        # Nothing further is checkable, and a partial verdict is worse than
        # none: it would read as "these checks passed" rather than "these
        # checks never ran".
        return _finish(args, sorted(set(failures)), attestation, rebuilt)

    candidate_body = ""
    try:
        candidate_body = args.candidate_archive.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"STAGE7_V2_VERIFY_PREPARE_DETAIL={exc}", file=sys.stderr)

    # Bytes first, because that is the comparison the attestation cannot fake:
    # a rebuilt archive that differs from the file on disk is a different
    # preparation however consistently the hashes were rewritten.
    if candidate_body != rebuilt.candidate_body:
        failures.append(ReplayFailure.candidate_archive_bytes_mismatch.value)
    if runtime_input_body != rebuilt.runtime_input_body:
        failures.append(ReplayFailure.runtime_input_bytes_mismatch.value)

    if attestation.original_v1_archive_sha256 != rebuilt.original_v1_archive_sha256:
        failures.append(ReplayFailure.corpus_archive_mismatch.value)
    if attestation.augmentation_manifest_digest != (
        rebuilt.augmentation_manifest_digest
    ):
        failures.append(ReplayFailure.manifest_digest_mismatch.value)
    if attestation.augmentation_manifest_file_sha256 != (
        rebuilt.augmentation_manifest_file_sha256
    ):
        failures.append(ReplayFailure.manifest_file_sha_mismatch.value)
    if attestation.candidate_archive_digest != rebuilt.candidate_archive_digest:
        failures.append(ReplayFailure.candidate_archive_digest_mismatch.value)
    if attestation.candidate_archive_file_sha256 != file_sha256(candidate_body):
        failures.append(ReplayFailure.candidate_archive_file_sha_mismatch.value)
    if attestation.runtime_input_digest != rebuilt.runtime_input.digest:
        failures.append(ReplayFailure.runtime_input_digest_mismatch.value)
    if attestation.runtime_input_file_sha256 != file_sha256(runtime_input_body):
        failures.append(ReplayFailure.runtime_input_file_sha_mismatch.value)
    if attestation.exact_code_head != args.exact_code_head:
        failures.append(ReplayFailure.exact_code_head_mismatch.value)

    # Every population projection, re-derived from the rebuild rather than read
    # off either artifact.
    expected = rebuilt.runtime_input.contexts
    if attestation.expected_context_count != len(expected):
        failures.append(ReplayFailure.context_count_mismatch.value)
    if attestation.context_index_set_digest != context_index_set_digest(expected):
        failures.append(ReplayFailure.context_index_set_mismatch.value)
    if attestation.expected_handle_set_digest != expected_handle_set_digest(expected):
        failures.append(ReplayFailure.expected_handle_set_mismatch.value)
    if attestation.prepared_state_map_digest != prepared_state_map_digest(expected):
        failures.append(ReplayFailure.prepared_state_map_mismatch.value)
    if attestation.refusal_handle_set_digest != refusal_handle_set_digest(expected):
        failures.append(ReplayFailure.refusal_handle_set_mismatch.value)
    if tuple(attestation.prepared_state_counts) != prepared_state_counts(expected):
        failures.append(ReplayFailure.state_counts_mismatch.value)
    if tuple(attestation.prepared_refusal_counts) != prepared_refusal_counts(expected):
        failures.append(ReplayFailure.refusal_counts_mismatch.value)
    if attestation.unresolved_augmentation_count != (
        rebuilt.unresolved_augmentation_count
    ):
        failures.append(ReplayFailure.unresolved_augmentation_count_mismatch.value)

    # And the same projections again, this time from the bundle that is
    # actually on disk.  The rebuild says what the preparation *should* be; this
    # says what the file Phase R would be handed actually *is*.  A joint forgery
    # satisfies the second and fails the first.
    if bundle is not None:
        on_disk = bundle.contexts
        if prepared_state_map_digest(on_disk) != prepared_state_map_digest(expected):
            failures.append(ReplayFailure.prepared_state_map_mismatch.value)
        if refusal_handle_set_digest(on_disk) != refusal_handle_set_digest(expected):
            failures.append(ReplayFailure.refusal_handle_set_mismatch.value)
        if expected_handle_set_digest(on_disk) != expected_handle_set_digest(expected):
            failures.append(ReplayFailure.expected_handle_set_mismatch.value)
        if context_index_set_digest(on_disk) != context_index_set_digest(expected):
            failures.append(ReplayFailure.context_index_set_mismatch.value)
        if len(on_disk) != len(expected):
            failures.append(ReplayFailure.context_count_mismatch.value)

    if args.campaign_seal is not None:
        seal = resolve_campaign_seal(args.campaign_seal)
        if seal is None:
            failures.append(CampaignSealFailure.unknown_seal.value)
        else:
            failures.extend(campaign_seal_failures(attestation, seal))

    return _finish(args, sorted(set(failures)), attestation, rebuilt)


def _finish(args, failures, attestation, rebuilt) -> int:
    """Write the one artifact this phase produces, and exit on its verdict.

    The report carries the same values the exit status is derived from, so a
    reader of the file and a shell reading `$?` cannot be told different
    things.  No candidate archive, runtime input or attestation is rewritten
    here — a verifier that could repair what it verifies has verified nothing.
    """

    payload = {
        "version": VERIFY_REPORT_VERSION,
        "score_class": VERIFY_REPORT_CLASS,
        "is_official_score": False,
        "is_scoring_input": False,
        "campaign_seal_name": args.campaign_seal,
        "exact_code_head": args.exact_code_head,
        "acceptance": "PASS" if not failures else "FAIL",
        "replay_failures": list(failures),
        "attestation_digest": (
            attestation.attestation_digest if attestation is not None else None
        ),
        "rebuilt_candidate_archive_digest": (
            rebuilt.candidate_archive_digest if rebuilt is not None else None
        ),
        "rebuilt_candidate_archive_file_sha256": (
            rebuilt.candidate_file_sha256 if rebuilt is not None else None
        ),
        "rebuilt_runtime_input_digest": (
            rebuilt.runtime_input.digest if rebuilt is not None else None
        ),
        "rebuilt_runtime_input_file_sha256": (
            rebuilt.runtime_input_file_sha256 if rebuilt is not None else None
        ),
        "rebuilt_original_v1_archive_sha256": (
            rebuilt.original_v1_archive_sha256 if rebuilt is not None else None
        ),
        "rebuilt_augmentation_manifest_digest": (
            rebuilt.augmentation_manifest_digest if rebuilt is not None else None
        ),
        "rebuilt_augmentation_manifest_file_sha256": (
            rebuilt.augmentation_manifest_file_sha256 if rebuilt is not None else None
        ),
        "rebuilt_expected_context_count": (
            rebuilt.expected_context_count if rebuilt is not None else None
        ),
        "rebuilt_context_index_set_digest": (
            context_index_set_digest(rebuilt.runtime_input.contexts)
            if rebuilt is not None
            else None
        ),
        "rebuilt_expected_handle_set_digest": (
            expected_handle_set_digest(rebuilt.runtime_input.contexts)
            if rebuilt is not None
            else None
        ),
        "rebuilt_prepared_state_map_digest": (
            prepared_state_map_digest(rebuilt.runtime_input.contexts)
            if rebuilt is not None
            else None
        ),
        "rebuilt_refusal_handle_set_digest": (
            refusal_handle_set_digest(rebuilt.runtime_input.contexts)
            if rebuilt is not None
            else None
        ),
        "rebuilt_prepared_state_counts": (
            [list(item) for item in prepared_state_counts(rebuilt.runtime_input.contexts)]
            if rebuilt is not None
            else None
        ),
        "rebuilt_prepared_refusal_counts": (
            [
                list(item)
                for item in prepared_refusal_counts(rebuilt.runtime_input.contexts)
            ]
            if rebuilt is not None
            else None
        ),
    }
    payload["report_digest"] = canonical_digest(payload)
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    args.verification_report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.verification_report.with_name(
        args.verification_report.name + ".partial"
    )
    temporary.write_text(body, encoding="utf-8")
    temporary.replace(args.verification_report)

    print(f"STAGE7_V2_VERIFY_PREPARE_REPORT_DIGEST={payload['report_digest']}")
    print(
        "STAGE7_V2_VERIFY_PREPARE_REPORT_FILE_SHA256="
        f"{hashlib.sha256(body.encode('utf-8')).hexdigest()}"
    )
    if attestation is not None:
        print(
            "STAGE7_V2_VERIFY_PREPARE_ATTESTATION_DIGEST="
            f"{attestation.attestation_digest}"
        )
    if rebuilt is not None:
        print(
            "STAGE7_V2_VERIFY_PREPARE_REBUILT_RUNTIME_INPUT_DIGEST="
            f"{rebuilt.runtime_input.digest}"
        )
        print(
            "STAGE7_V2_VERIFY_PREPARE_REBUILT_PREPARED_STATE_MAP_DIGEST="
            f"{prepared_state_map_digest(rebuilt.runtime_input.contexts)}"
        )
        print(
            "STAGE7_V2_VERIFY_PREPARE_REBUILT_REFUSAL_HANDLE_SET_DIGEST="
            f"{refusal_handle_set_digest(rebuilt.runtime_input.contexts)}"
        )
        for name, count in prepared_state_counts(rebuilt.runtime_input.contexts):
            print(f"STAGE7_V2_VERIFY_PREPARE_REBUILT_STATE_{name}={count}")
    print(f"STAGE7_V2_VERIFY_PREPARE_CAMPAIGN_SEAL={args.campaign_seal or 'none'}")
    print(
        "STAGE7_V2_VERIFY_PREPARE_ACCEPTANCE="
        + ("PASS" if not failures else "FAIL:" + ",".join(failures))
    )
    return 0 if not failures else VERIFY_FAILURE_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
