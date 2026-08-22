"""Phase G — open the gold, pair it to a frozen snapshot, and compare.

This command's runtime input is a *file*: the full restricted snapshot, re-read
from its own bytes, re-validated against its own schema, and re-checked against
its own digest before a single expected answer is looked at.  It receives no
Python object from Phase R, and it holds no compiler, solver, verifier or
projection — so it cannot re-run the pipeline having seen the answer, and that
is a property of what it imports rather than a promise about what it does.

Until this session the two phases were functions in one process and Phase G
scored the in-memory snapshot.  The file on disk was the redacted view, which
has no pairing handles, so nobody — including this command — could have
re-scored the run from the artifact.  The sequencing was real and entirely
unverifiable.

The comparison is `compare_answer_to_gold`, the official strict scorer's own,
reused rather than reimplemented.  There is no v2 comparator to soften.

**Acceptance decides the exit status, from the same values the artifact
carries.**  A run that reports FAIL exits 2.  The previous runner printed
`ACCEPTANCE=FAIL` and returned 0, so a shell or a CI step reading the exit
status was told the measurement had succeeded.

The attestation arrives one of two ways, mutually exclusive.  The
authoritative pipeline contract is ``--publication-root`` with the
``--publication-id`` Phase M printed: the pinned generation is resolved once
and ``CURRENT.json`` is never re-read, so the attestation this run scores
against is the same one Phase V verified and Phase R was admitted on, whatever
a later writer did to the pointer.  ``--prepare-attestation`` remains as the
non-authoritative probe harness; the binding gates apply to it unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.corpus_integrity import (  # noqa: E402
    read_public_corpus_archive,
)
from evaluation.phase56_stage7.corpus_preflight import load_public_cases  # noqa: E402
from evaluation.phase56_stage7.corpus_v2.gold_scoring import (  # noqa: E402
    GoldScoringRefused,
    build_gold_index,
    gold_pairing_failures,
    score_shadow_snapshot,
    totals,
)
from evaluation.phase56_stage7.corpus_v2.artifact_io import (  # noqa: E402
    write_utf8_atomic,
)
from evaluation.phase56_stage7.corpus_v2.campaign_seal import (  # noqa: E402
    CampaignSealFailure,
    campaign_seal_failures,
    resolve_campaign_seal,
)
from evaluation.phase56_stage7.corpus_v2.prepare_attestation import (  # noqa: E402
    PrepareAttestationRefused,
    PrepareBindingFailure,
    load_prepare_attestation,
)
from evaluation.phase56_stage7.corpus_v2.publication import (  # noqa: E402
    PublicationRefused,
    resolve_published_generation,
)
from evaluation.phase56_stage7.corpus_v2.reporting import (  # noqa: E402
    assert_scores_are_separated,
    build_scored_shadow_scorecard,
    scored_scorecard_as_dict,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (  # noqa: E402
    LedgerState,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (  # noqa: E402
    RuntimeSnapshotRefused,
    load_full_runtime_snapshot,
)
from evaluation.phase56_stage7.redaction import (  # noqa: E402
    assert_privacy_safe_artifact,
)


SCORE_FAILURE_EXIT = 2


def _binding_failures(snapshot, attestation, expected_code_head: str | None):
    """Every way this snapshot is not a measurement of that preparation.

    Phase G does not replay the projection — that is Phase V's job, done once,
    against the corpus, before anything ran.  What Phase G checks is the other
    half: that the snapshot it is about to score was produced from the
    preparation the attestation describes, rather than from some other one.

    Compared field by field rather than by hashing the binding as a unit, so a
    control that alters exactly one of them can name the field it altered.
    """

    binding = snapshot.prepare_binding
    failures: list[str] = []
    if not attestation.digest_is_intact():
        failures.append(PrepareBindingFailure.attestation_digest_mismatch.value)
    if binding.prepare_attestation_digest != attestation.attestation_digest:
        failures.append(PrepareBindingFailure.attestation_digest_mismatch.value)
    if binding.runtime_input_digest != attestation.runtime_input_digest:
        failures.append(PrepareBindingFailure.runtime_input_digest_mismatch.value)
    if binding.runtime_input_file_sha256 != attestation.runtime_input_file_sha256:
        failures.append(PrepareBindingFailure.runtime_input_file_sha_mismatch.value)
    if binding.context_index_set_digest != attestation.context_index_set_digest:
        failures.append(PrepareBindingFailure.context_index_set_mismatch.value)
    if binding.expected_handle_set_digest != attestation.expected_handle_set_digest:
        failures.append(PrepareBindingFailure.expected_handle_set_mismatch.value)
    if binding.prepared_state_map_digest != attestation.prepared_state_map_digest:
        failures.append(PrepareBindingFailure.prepared_state_map_mismatch.value)
    if binding.refusal_handle_set_digest != attestation.refusal_handle_set_digest:
        failures.append(PrepareBindingFailure.refusal_handle_set_mismatch.value)
    if tuple(binding.prepared_state_counts) != tuple(
        attestation.prepared_state_counts
    ):
        failures.append(PrepareBindingFailure.state_counts_mismatch.value)
    if tuple(binding.prepared_refusal_counts) != tuple(
        attestation.prepared_refusal_counts
    ):
        failures.append(PrepareBindingFailure.refusal_counts_mismatch.value)
    if binding.campaign_seal_name != attestation.campaign_seal_name:
        failures.append(PrepareBindingFailure.campaign_seal_name_mismatch.value)
    if snapshot.original_v1_archive_sha256 != (
        attestation.original_v1_archive_sha256
    ):
        failures.append(PrepareBindingFailure.corpus_archive_mismatch.value)
    if snapshot.augmentation_manifest_sha256 != (
        attestation.augmentation_manifest_digest
    ):
        failures.append(PrepareBindingFailure.manifest_digest_mismatch.value)
    if snapshot.candidate_archive_sha256 != attestation.candidate_archive_digest:
        failures.append(
            PrepareBindingFailure.candidate_archive_digest_mismatch.value
        )
    heads = {binding.exact_code_head, attestation.exact_code_head}
    if expected_code_head is not None:
        heads.add(expected_code_head)
    if snapshot.exact_code_head is not None:
        heads.add(snapshot.exact_code_head)
    if len(heads) != 1:
        failures.append(PrepareBindingFailure.exact_code_head_mismatch.value)

    # The population seal, read off the attestation the snapshot is bound to.
    if attestation.campaign_seal_name is not None:
        seal = resolve_campaign_seal(attestation.campaign_seal_name)
        if seal is None:
            failures.append(CampaignSealFailure.unknown_seal.value)
        else:
            failures.extend(campaign_seal_failures(attestation, seal))
    return tuple(sorted(set(failures)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-archive", type=Path, required=True)
    parser.add_argument("--runtime-snapshot", type=Path, required=True)
    parser.add_argument(
        "--publication-root",
        type=Path,
        default=None,
        help=(
            "resolve the attestation from a published generation. The "
            "authoritative pipeline contract; excludes --prepare-attestation."
        ),
    )
    parser.add_argument(
        "--publication-id",
        type=str,
        default=None,
        help=(
            "the exact generation to score against, as printed by Phase M. "
            "When given, CURRENT.json is never read."
        ),
    )
    parser.add_argument("--prepare-attestation", type=Path, default=None)
    parser.add_argument("--shadow-report", type=Path, required=True)
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument(
        "--expected-code-head",
        type=str,
        default=None,
        help=(
            "the commit this scoring run is evidence about. When given, the "
            "snapshot, the attestation and this value must name one head."
        ),
    )
    parser.add_argument(
        "--campaign-seal",
        type=str,
        default=None,
        help=(
            "the named population contract the attestation must claim. Refused "
            "when the attestation names a different one, or none at all."
        ),
    )
    args = parser.parse_args()

    if args.publication_root is not None:
        if args.prepare_attestation is not None:
            print(
                "STAGE7_V2_SHADOW_ACCEPTANCE=FAIL:publication_input_contract: "
                "--publication-root excludes --prepare-attestation",
                file=sys.stderr,
            )
            return SCORE_FAILURE_EXIT
        try:
            published = resolve_published_generation(
                args.publication_root, publication_id=args.publication_id
            )
        except PublicationRefused as exc:
            print(f"STAGE7_V2_SHADOW_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
            return SCORE_FAILURE_EXIT
        args.prepare_attestation = published.prepare_attestation
        print(f"STAGE7_V2_SHADOW_PUBLICATION_ID={published.generation_id}")
    elif args.publication_id is not None or args.prepare_attestation is None:
        print(
            "STAGE7_V2_SHADOW_ACCEPTANCE=FAIL:publication_input_contract: "
            "pass --publication-root [--publication-id], or "
            "--prepare-attestation",
            file=sys.stderr,
        )
        return SCORE_FAILURE_EXIT

    try:
        snapshot = load_full_runtime_snapshot(
            args.runtime_snapshot.read_text(encoding="utf-8")
        )
    except RuntimeSnapshotRefused as exc:
        print(f"STAGE7_V2_SHADOW_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return SCORE_FAILURE_EXIT

    try:
        attestation = load_prepare_attestation(
            args.prepare_attestation.read_text(encoding="utf-8")
        )
    except (PrepareAttestationRefused, OSError) as exc:
        print(f"STAGE7_V2_SHADOW_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return SCORE_FAILURE_EXIT

    binding_failures = list(
        _binding_failures(snapshot, attestation, args.expected_code_head)
    )
    if args.campaign_seal is not None and (
        attestation.campaign_seal_name != args.campaign_seal
    ):
        binding_failures.append(
            CampaignSealFailure.name_mismatch.value
            if attestation.campaign_seal_name is not None
            else CampaignSealFailure.not_sealed.value
        )
    if binding_failures:
        # Refused before the gold is opened.  A snapshot that is not bound to
        # an attested preparation is not scored at all, so no report exists to
        # be quoted from a run nobody can attribute.
        print(
            "STAGE7_V2_SHADOW_ACCEPTANCE=FAIL:"
            + ",".join(sorted(set(binding_failures))),
            file=sys.stderr,
        )
        return SCORE_FAILURE_EXIT

    # --- The gold opens here, and the pipeline is already closed and hashed --
    inventory = read_public_corpus_archive(args.corpus_archive)
    public_dev, public_adversarial = load_public_cases(inventory)
    cases = (*public_dev, *public_adversarial)

    if inventory.archive_sha256 != snapshot.original_v1_archive_sha256:
        print(
            "STAGE7_V2_SHADOW_ACCEPTANCE=FAIL:shadow_archive_mismatch",
            file=sys.stderr,
        )
        return SCORE_FAILURE_EXIT

    # Built over the whole corpus, not over the positions the snapshot happens
    # to carry, so the two sets are independent and a disagreement is visible.
    gold_by_handle = build_gold_index(
        cases, original_v1_archive_sha256=inventory.archive_sha256
    )
    pairing = gold_pairing_failures(snapshot, gold_by_handle)

    try:
        scored = score_shadow_snapshot(snapshot, gold_by_handle)
    except GoldScoringRefused as exc:
        print(f"STAGE7_V2_SHADOW_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return SCORE_FAILURE_EXIT
    score_totals = totals(scored)

    coverage: Counter[str] = Counter()
    for row in snapshot.records:
        for name in row.carriers_supplied:
            coverage[name] += 1

    scorecard = build_scored_shadow_scorecard(
        scored,
        score_totals,
        snapshot=snapshot,
        carrier_coverage=tuple(sorted(coverage.items())),
        completeness_failures=pairing,
    )
    payload = scored_scorecard_as_dict(scorecard)
    assert_privacy_safe_artifact(payload)
    assert_scores_are_separated({"observed_public_score": "41/81"}, payload)

    report_file_sha = write_utf8_atomic(
        args.shadow_report,
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    # The scorecard is the machine-readable disposition on its own: the same
    # acceptance values this process exits on, in a file a checker can read
    # without parsing stdout.
    scorecard_file_sha = write_utf8_atomic(
        args.scorecard,
        json.dumps(
            {
                "score_class": payload["score_class"],
                "is_official_score": False,
                "digest": scorecard.digest,
                "exact_code_head": scorecard.exact_code_head,
                "runtime_snapshot_sha256": scorecard.runtime_snapshot_sha256,
                "acceptance": "PASS" if not scorecard.acceptance_failures else "FAIL",
                "acceptance_failures": list(scorecard.acceptance_failures),
                "prepare_attestation_digest": (
                    snapshot.prepare_binding.prepare_attestation_digest
                ),
                "runtime_input_digest": (
                    snapshot.prepare_binding.runtime_input_digest
                ),
                "prepared_state_map_digest": (
                    snapshot.prepare_binding.prepared_state_map_digest
                ),
                "refusal_handle_set_digest": (
                    snapshot.prepare_binding.refusal_handle_set_digest
                ),
                "expected_handle_set_digest": (
                    snapshot.prepare_binding.expected_handle_set_digest
                ),
                "campaign_seal_name": snapshot.prepare_binding.campaign_seal_name,
                "expected_context_count": scorecard.expected_context_count,
                "context_count": scorecard.context_count,
                "ledger_state_counts": [
                    list(item) for item in scorecard.ledger_state_counts
                ],
                "ledger_refusal_counts": [
                    list(item) for item in scorecard.ledger_refusal_counts
                ],
                "newly_solved": scorecard.newly_solved,
                "newly_solved_correct": scorecard.newly_solved_correct,
                "newly_solved_wrong": scorecard.newly_solved_wrong,
                "newly_solved_unscored": scorecard.newly_solved_unscored,
                "all_shadow_correct": scorecard.all_shadow_correct,
                "all_shadow_wrong": scorecard.all_shadow_wrong,
                "all_shadow_unscored": scorecard.all_shadow_unscored,
                "forbidden_class_solve": scorecard.forbidden_class_solve,
                "regressed": scorecard.regressed,
                "query_binding_mismatch": scorecard.query_binding_mismatch,
                "cohort_yield": [list(item) for item in scorecard.cohort_yield],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
    )

    print(f"STAGE7_V2_SHADOW_SCORE_CLASS={payload['score_class']}")
    print("STAGE7_V2_SHADOW_IS_OFFICIAL_SCORE=false")
    print(f"STAGE7_V2_SHADOW_ORIGINAL_V1_ARCHIVE_SHA256={inventory.archive_sha256}")
    print(f"STAGE7_V2_SHADOW_MANIFEST_SHA256={scorecard.augmentation_manifest_sha256}")
    print(
        "STAGE7_V2_SHADOW_CANDIDATE_ARCHIVE_SHA256="
        f"{scorecard.candidate_archive_sha256}"
    )
    print(f"STAGE7_V2_SHADOW_RUNTIME_SNAPSHOT_SHA256={scorecard.runtime_snapshot_sha256}")
    print(f"STAGE7_V2_SHADOW_REPORT_FILE_SHA256={report_file_sha}")
    print(f"STAGE7_V2_SHADOW_SCORECARD_FILE_SHA256={scorecard_file_sha}")
    print(f"STAGE7_V2_SHADOW_DIGEST={scorecard.digest}")
    print(f"STAGE7_V2_SHADOW_EXPECTED_CONTEXTS={scorecard.expected_context_count}")
    print(f"STAGE7_V2_SHADOW_CONTEXTS={scorecard.context_count}")
    for name, count in scorecard.ledger_state_counts:
        print(f"STAGE7_V2_SHADOW_LEDGER_{name}={count}")
    for name, count in scorecard.ledger_refusal_counts:
        print(f"STAGE7_V2_SHADOW_REFUSAL_{name}={count}")
    print(f"STAGE7_V2_SHADOW_AUGMENTED={scorecard.augmented_context_count}")
    print(f"STAGE7_V2_SHADOW_UNRESOLVED={scorecard.unresolved_augmentation_count}")
    print(f"STAGE7_V2_SHADOW_NEWLY_SOLVED={scorecard.newly_solved}")
    print(f"STAGE7_V2_SHADOW_NEWLY_SOLVED_CORRECT={scorecard.newly_solved_correct}")
    print(f"STAGE7_V2_SHADOW_NEWLY_SOLVED_WRONG={scorecard.newly_solved_wrong}")
    print(f"STAGE7_V2_SHADOW_NEWLY_SOLVED_UNSCORED={scorecard.newly_solved_unscored}")
    print(f"STAGE7_V2_SHADOW_ALL_CORRECT={scorecard.all_shadow_correct}")
    print(f"STAGE7_V2_SHADOW_ALL_WRONG={scorecard.all_shadow_wrong}")
    print(f"STAGE7_V2_SHADOW_ALL_UNSCORED={scorecard.all_shadow_unscored}")
    print(f"STAGE7_V2_SHADOW_FORBIDDEN_CLASS_SOLVE={scorecard.forbidden_class_solve}")
    print(f"STAGE7_V2_SHADOW_REGRESSED={scorecard.regressed}")
    print(f"STAGE7_V2_SHADOW_QUERY_BINDING_MISMATCH={scorecard.query_binding_mismatch}")
    print(f"STAGE7_V2_SHADOW_COHORT_YIELD={scorecard.cohort_yield_count}")
    for name, count in scorecard.carrier_coverage:
        print(f"STAGE7_V2_SHADOW_CARRIER_{name}={count}")
    for name, count in scorecard.scoring_defect_counts:
        print(f"STAGE7_V2_SHADOW_DEFECT_{name}={count}")
    print(
        "STAGE7_V2_SHADOW_RUNTIME_SCOREABLE="
        + str(
            sum(
                count
                for name, count in scorecard.ledger_state_counts
                if name == LedgerState.runtime_completed.value
            )
        )
    )

    failures = scorecard.acceptance_failures
    print(
        "STAGE7_V2_SHADOW_ACCEPTANCE="
        + ("PASS" if not failures else "FAIL:" + ",".join(failures))
    )
    # One source of truth for the printed disposition and the exit status.
    return 0 if not failures else SCORE_FAILURE_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
