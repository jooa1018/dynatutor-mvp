"""Phase R — run the pipeline over every context, then freeze what happened.

This command's input is a `ShadowRuntimeInputV2` file and nothing else.  It
never opens the corpus archive, never constructs a `PublicCorpusCaseV1`, and
never imports the gold domain or the scorer: there is no expected answer,
expected terminal, expected failure code, family or case id anywhere in this
process, because none of them is reachable from what it was given.

Two artifacts come out, and they are deliberately different objects.

*The full restricted runtime snapshot* carries the pairing handles and the
runtime's own answers.  It is the only input Phase G accepts, it re-reads and
re-validates from its own bytes, and it recomputes its own digest — so anyone
holding it can re-score the run without this process, which is what "the
measurement is independently checkable" has to mean.  It stays out of the
repository.

*The public redacted view* is a separate model with a separate version, and it
is not a scoring input.  Until now only this file reached disk, under the name
of the snapshot, while Phase G scored the in-memory object it had been handed.
The stored artifact therefore could not be re-loaded, could not recompute its
own digest, and could not be re-scored by anyone — the evidence and the thing
that was actually measured were two different objects with one name.

**No context leaves this command silently.**  Every context in the bundle gets
exactly one ledger row.  A context that raises is recorded as `runtime_failed`
under a closed refusal code and fails acceptance; it is not swallowed by a
`continue` that would remove it from the snapshot, from the handle set, from
the gold pairing and from every count at once.

**And no context is excused into one either.**  Accounting for every context is
not the same as measuring it.  The bundle used to be an ordinary JSON document
whose word this command took: it read `prepared_state` and `refusal_code` off
each context and wrote them straight into the ledger, so relabelling a solvable
context as an anticipated `projection_refused` with a null draft produced a
perfectly complete ledger of a measurement that had not happened.  Do it to all
ninety-seven and the run reports a hundred rows, a hundred permitted refusals,
zero records, and acceptance PASS.

Three things close that here, in this order, all of them before a single
context is run:

1. the **raw** bundle is scanned for gold members at the trust boundary — on
   the bytes, before any model validates them, because `draft_payload` is an
   open mapping and a nested expectation satisfies its type;
2. the bundle is loaded through a schema whose cross-field contract makes
   "refused, with a draft" and "completed, without one" unrepresentable; and
3. the bundle is checked against Phase M's attestation — file hash, canonical
   digest, handle set, context order, prepared-state map, refusal handle set
   and both count vectors — with the projections re-derived from the bundle
   rather than read off it.

A failure at any of them exits 2 with the runtime callback never invoked and
neither artifact written.  What this command cannot detect is a runtime input
and an attestation forged *together*; that is Phase V's job, and Phase V runs
before this one.

The bundle and the attestation arrive one of two ways, mutually exclusive.
The authoritative pipeline contract is ``--publication-root`` with the
``--publication-id`` Phase M printed: the pinned generation is resolved once
and ``CURRENT.json`` is never re-read, so this phase cannot be redirected onto
a different publication by a writer that moved the pointer meanwhile.  The
explicit paths remain as the non-authoritative probe harness the attack matrix
drives forged files through; every gate above applies to them unchanged.

Exit 0 when every context is accounted for, 2 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from engine.mechanics.contracts import MechanicsProblemDraftV1  # noqa: E402

from evaluation.phase56_stage7.corpus_v2.artifact_io import (  # noqa: E402
    write_utf8_atomic,
)
from evaluation.phase56_stage7.corpus_v2.campaign_seal import (  # noqa: E402
    CampaignSealFailure,
    campaign_seal_failures,
    resolve_campaign_seal,
)
from evaluation.phase56_stage7.corpus_v2.canonical import file_sha256  # noqa: E402
from evaluation.phase56_stage7.corpus_v2.prepare_attestation import (  # noqa: E402
    PrepareAttestationRefused,
    load_prepare_attestation,
    runtime_input_binding_failures,
)
from evaluation.phase56_stage7.corpus_v2.publication import (  # noqa: E402
    PublicationRefused,
    resolve_published_generation,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (  # noqa: E402
    RuntimeInputRefused,
    assert_bundle_has_no_gold,
    load_runtime_input,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (  # noqa: E402
    LedgerState,
    RefusalCode,
    ShadowLedgerEntryV2,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (  # noqa: E402
    RuntimeSnapshotRefused,
    freeze_runtime_snapshot,
    prepare_binding_from_attestation,
    redact_runtime_snapshot,
)
from evaluation.phase56_stage7.corpus_v2.shadow_runner import (  # noqa: E402
    assert_no_regression,
    assert_no_unaugmented_movement,
    run_shadow_context,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (  # noqa: E402
    DraftProjectionTerminal,
)
from evaluation.phase56_stage7.lane_b_runner import (  # noqa: E402
    deterministic_token,
    run_lane_b_case,
)
from evaluation.phase56_stage7.redaction import (  # noqa: E402
    assert_privacy_safe_artifact,
)


RUNTIME_FAILURE_EXIT = 2


class _Projected:
    """The shape `run_lane_b_case` expects, around an already-built Draft."""

    __slots__ = (
        "terminal",
        "problem_text",
        "draft",
        "sanitized_reason",
        "environment_scoped_quantity_ids",
        "segment_internal_event_ids",
        "approvable_assumption_ids",
        "known_symbol_ids",
        "unknown_symbol_ids",
        "event_authority_gaps",
    )

    def __init__(self, context: Any, draft: Any) -> None:
        # The lane compares this against `DraftProjectionTerminal` by identity,
        # so it has to arrive as the enum member the bundle names — a bare
        # string is a different object and every context would be rejected as
        # unprojected.  The enum is a runtime-domain type; it says whether a
        # Draft was built, and carries no expectation about how a case ends.
        self.terminal = DraftProjectionTerminal(context.projection_terminal)
        self.problem_text = context.problem_text
        self.draft = draft
        self.sanitized_reason = context.sanitized_reason
        self.environment_scoped_quantity_ids = context.environment_scoped_quantity_ids
        self.segment_internal_event_ids = context.segment_internal_event_ids
        self.known_symbol_ids = context.known_symbol_ids
        self.unknown_symbol_ids = context.unknown_symbol_ids
        self.event_authority_gaps = context.event_authority_gaps
        # The approvable set is the v1 projection's own, extended by exactly
        # the ids the carriers *derive* — never by an id a manifest named,
        # because no manifest can name one.  The authority bundle then
        # re-checks the Draft's approved dispositions against this set, so a
        # carrier that wrote an authority nobody declared still fails closed.
        self.approvable_assumption_ids = (
            *context.approvable_assumption_ids,
            *context.derived_authority_ids,
        )

    @property
    def projected(self) -> bool:
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publication-root",
        type=Path,
        default=None,
        help=(
            "resolve the runtime input and the attestation from a published "
            "generation. The authoritative pipeline contract; excludes the "
            "direct paths below."
        ),
    )
    parser.add_argument(
        "--publication-id",
        type=str,
        default=None,
        help=(
            "the exact generation to run, as printed by Phase M. When given, "
            "CURRENT.json is never read."
        ),
    )
    parser.add_argument("--runtime-input", type=Path, default=None)
    parser.add_argument("--prepare-attestation", type=Path, default=None)
    parser.add_argument("--runtime-snapshot", type=Path, required=True)
    parser.add_argument("--redacted-view", type=Path, required=True)
    parser.add_argument("--exact-code-head", type=str, default=None)
    parser.add_argument(
        "--record-regressions",
        action="store_true",
        help=(
            "record a carrier that takes a solve away instead of aborting. "
            "A measurement run needs the evidence; a release must not have it, "
            "so the default stays fail-closed."
        ),
    )
    args = parser.parse_args()

    if args.publication_root is not None:
        if args.runtime_input is not None or args.prepare_attestation is not None:
            print(
                "STAGE7_V2_RUNTIME_ACCEPTANCE=FAIL:publication_input_contract: "
                "--publication-root excludes --runtime-input and "
                "--prepare-attestation",
                file=sys.stderr,
            )
            return RUNTIME_FAILURE_EXIT
        try:
            published = resolve_published_generation(
                args.publication_root, publication_id=args.publication_id
            )
        except PublicationRefused as exc:
            print(f"STAGE7_V2_RUNTIME_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
            return RUNTIME_FAILURE_EXIT
        args.runtime_input = published.runtime_input
        args.prepare_attestation = published.prepare_attestation
        print(f"STAGE7_V2_RUNTIME_PUBLICATION_ID={published.generation_id}")
    elif (
        args.publication_id is not None
        or args.runtime_input is None
        or args.prepare_attestation is None
    ):
        print(
            "STAGE7_V2_RUNTIME_ACCEPTANCE=FAIL:publication_input_contract: "
            "pass --publication-root [--publication-id], or both "
            "--runtime-input and --prepare-attestation",
            file=sys.stderr,
        )
        return RUNTIME_FAILURE_EXIT

    # --- the trust boundary -------------------------------------------------
    # Everything from here to the binding check runs before the pipeline is
    # touched.  A failure in this block means zero runtime calls and zero
    # artifacts, which is what the negative controls assert.
    try:
        runtime_input_body = args.runtime_input.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"STAGE7_V2_RUNTIME_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return RUNTIME_FAILURE_EXIT

    try:
        # On the raw document, before any model has seen it.  A gold member
        # nested inside `draft_payload` satisfies that field's type, so a scan
        # that ran after validation would be scanning something the schema had
        # already accepted.
        assert_bundle_has_no_gold(json.loads(runtime_input_body))
        bundle = load_runtime_input(runtime_input_body)
    except (RuntimeInputRefused, ValueError) as exc:
        print(f"STAGE7_V2_RUNTIME_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return RUNTIME_FAILURE_EXIT

    try:
        attestation = load_prepare_attestation(
            args.prepare_attestation.read_text(encoding="utf-8")
        )
    except (PrepareAttestationRefused, OSError) as exc:
        print(f"STAGE7_V2_RUNTIME_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return RUNTIME_FAILURE_EXIT

    binding_failures = list(
        runtime_input_binding_failures(
            attestation,
            bundle,
            runtime_input_file_sha256=file_sha256(runtime_input_body),
            exact_code_head=args.exact_code_head,
        )
    )
    # The seal is read off the attestation rather than off a flag, so a
    # preparation cannot escape its own population contract by having the
    # runtime invoked without one.
    if attestation.campaign_seal_name is not None:
        seal = resolve_campaign_seal(attestation.campaign_seal_name)
        if seal is None:
            binding_failures.append(CampaignSealFailure.unknown_seal.value)
        else:
            binding_failures.extend(campaign_seal_failures(attestation, seal))
    if binding_failures:
        print(
            "STAGE7_V2_RUNTIME_ACCEPTANCE=FAIL:"
            + ",".join(sorted(set(binding_failures))),
            file=sys.stderr,
        )
        return RUNTIME_FAILURE_EXIT

    # --- admitted.  Only now does anything run ------------------------------
    results = []
    ledger: list[ShadowLedgerEntryV2] = []
    failed_handles: list[str] = []
    for context in bundle.contexts:
        if context.draft_payload is None:
            # Carried through from Phase M, not re-derived: the refusal was
            # decided where the record was read, and this phase records it.
            ledger.append(
                ShadowLedgerEntryV2(
                    scoring_handle=context.scoring_handle,
                    state=context.prepared_state,
                    refusal_code=context.refusal_code,
                )
            )
            continue

        def _run(payload: dict[str, Any], _context=context):
            draft = MechanicsProblemDraftV1.model_validate(payload)
            return run_lane_b_case(
                _Projected(_context, draft),
                execution_token=deterministic_token(_context.context_index),
            )

        try:
            results.append(
                run_shadow_context(
                    draft_payload=context.draft_payload,
                    augmentation=context.augmentation,
                    run=_run,
                    problem_text=context.problem_text,
                    original_v1_archive_sha256=bundle.original_v1_archive_sha256,
                    context_index=context.context_index,
                )
            )
        except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
            # The old shape was `continue`, which deleted the context from the
            # run.  Here it stays in the ledger under a closed code, so the
            # snapshot still accounts for it and acceptance still fails.
            print(
                "STAGE7_V2_RUNTIME_UNEXPECTED_EXCEPTION="
                f"{type(exc).__name__}",
                file=sys.stderr,
            )
            failed_handles.append(context.scoring_handle)
            ledger.append(
                ShadowLedgerEntryV2(
                    scoring_handle=context.scoring_handle,
                    state=LedgerState.runtime_failed,
                    refusal_code=RefusalCode.runtime_failed_unexpected_exception,
                )
            )
            continue
        ledger.append(
            ShadowLedgerEntryV2(
                scoring_handle=context.scoring_handle,
                state=LedgerState.runtime_completed,
            )
        )

    assert_no_unaugmented_movement(results)
    if not args.record_regressions:
        assert_no_regression(results)

    try:
        snapshot = freeze_runtime_snapshot(
            results,
            ledger=ledger,
            original_v1_archive_sha256=bundle.original_v1_archive_sha256,
            augmentation_manifest_sha256=bundle.augmentation_manifest_sha256,
            candidate_archive_sha256=bundle.candidate_archive_sha256,
            # From the verified attestation, not from an argument: a binding
            # assembled out of command-line strings would attest to whatever
            # the caller typed.
            prepare_binding=prepare_binding_from_attestation(attestation),
            exact_code_head=args.exact_code_head,
            unresolved_augmentation_count=bundle.unresolved_augmentation_count,
        )
    except RuntimeSnapshotRefused as exc:
        print(f"STAGE7_V2_RUNTIME_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return RUNTIME_FAILURE_EXIT

    snapshot_body = (
        json.dumps(
            snapshot.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    snapshot_file_sha = write_utf8_atomic(args.runtime_snapshot, snapshot_body)

    view = redact_runtime_snapshot(snapshot)
    view_payload = view.model_dump(mode="json")
    assert_privacy_safe_artifact(view_payload)
    view_body = (
        json.dumps(view_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    view_file_sha = write_utf8_atomic(args.redacted_view, view_body)

    print(f"STAGE7_V2_RUNTIME_SNAPSHOT_DIGEST={snapshot.runtime_snapshot_digest}")
    print(f"STAGE7_V2_RUNTIME_SNAPSHOT_FILE_SHA256={snapshot_file_sha}")
    print(f"STAGE7_V2_RUNTIME_REDACTED_VIEW_FILE_SHA256={view_file_sha}")
    print(
        "STAGE7_V2_RUNTIME_PREPARE_ATTESTATION_DIGEST="
        f"{snapshot.prepare_binding.prepare_attestation_digest}"
    )
    print(
        "STAGE7_V2_RUNTIME_PREPARE_RUNTIME_INPUT_DIGEST="
        f"{snapshot.prepare_binding.runtime_input_digest}"
    )
    print(
        "STAGE7_V2_RUNTIME_PREPARE_STATE_MAP_DIGEST="
        f"{snapshot.prepare_binding.prepared_state_map_digest}"
    )
    print(
        "STAGE7_V2_RUNTIME_PREPARE_REFUSAL_HANDLE_SET_DIGEST="
        f"{snapshot.prepare_binding.refusal_handle_set_digest}"
    )
    print(
        "STAGE7_V2_RUNTIME_PREPARE_CAMPAIGN_SEAL="
        f"{snapshot.prepare_binding.campaign_seal_name or 'none'}"
    )
    print(f"STAGE7_V2_RUNTIME_EXACT_CODE_HEAD={snapshot.exact_code_head}")
    print(f"STAGE7_V2_RUNTIME_EXPECTED_CONTEXTS={snapshot.expected_context_count}")
    print(f"STAGE7_V2_RUNTIME_RECORDED_CONTEXTS={snapshot.context_count}")
    for name, count in snapshot.ledger_state_counts:
        print(f"STAGE7_V2_RUNTIME_LEDGER_{name}={count}")
    for name, count in snapshot.ledger_refusal_counts:
        print(f"STAGE7_V2_RUNTIME_REFUSAL_{name}={count}")

    failures = list(snapshot.completeness_failures())
    if failed_handles:
        failures.append("shadow_unexpected_runtime_failure")
    failures = sorted(set(failures))
    print(
        "STAGE7_V2_RUNTIME_ACCEPTANCE="
        + ("PASS" if not failures else "FAIL:" + ",".join(failures))
    )
    return 0 if not failures else RUNTIME_FAILURE_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
