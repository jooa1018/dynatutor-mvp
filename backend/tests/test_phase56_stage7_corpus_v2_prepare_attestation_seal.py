"""A complete ledger is not an honest one: the refusal-laundering attack matrix.

The ledger closed *silent omission*.  A context that failed used to be dropped
from the run — no runtime record, so absent from the snapshot; absent from the
snapshot, absent from the scored handle set; absent from the handle set,
uncountable as wrong, unscored, forbidden or regressed.  Giving every context a
row closed that: nothing can leave quietly any more.

This suite is about the attack that replaces it.  Every completeness rule reads
the runtime input, and the runtime input was an unsigned JSON document.  So
instead of *removing* a context you *relabel* it:

    {"scoring_handle": "<the real handle>", "context_index": 42,
     "prepared_state": "projection_refused",
     "refusal_code": "projection_refused_no_draft",
     "draft_payload": null}

Nothing is missing.  The handle is expected, present and unique; the row is a
refusal the contract *anticipates* rather than a blocking one; the record set
and the completed-row set still agree.  Do it to all ninety-seven measurable
contexts and the run reports a hundred-row ledger, a hundred permitted refusals,
zero records, zero wrong, zero unscored, zero regressed — and acceptance PASS.
The measurement was not incomplete.  It was excused.

Four structures close it, and the controls below are grouped by which one each
attack has to defeat:

* **cross-field validation** makes "refused, with a draft" and "completed,
  without one" unrepresentable, so the laundered row cannot even be spelled if
  it keeps the projection's outputs;
* **the attestation** states what Phase M actually prepared — order, handles,
  prepared state per context, which were refused and under which code — and
  hashes it, so a relabelled bundle disagrees with a document written before
  the relabelling;
* **Phase V** rebuilds the preparation from the corpus and the manifest, which
  is the only check a forger who rewrites *both* files consistently cannot
  satisfy; and
* **the frozen population seal** pins this campaign's exact 97/3 split and the
  identity of the three refusals, so a run that is internally coherent about
  some other population is still not this campaign's measurement.

Each control asserts the *name* of the gate it hits, not merely that something
failed.  A state-map attack that only ever surfaced as "the file hash changed"
would be no evidence that the state map is checked at all, and a control that
passes for the wrong reason is worse than no control.

Everything here is synthetic.  No public archive is read.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from evaluation.phase56_stage7.corpus_v2.campaign_seal import (
    STAGE7_PUBLIC_CAMPAIGN_SEAL_NAME,
    STAGE7_PUBLIC_CAMPAIGN_SEAL_V1,
    CampaignPopulationSealV1,
    CampaignSealFailure,
    campaign_seal_failures,
    resolve_campaign_seal,
)
from evaluation.phase56_stage7.corpus_v2.canonical import (
    canonical_digest,
    canonical_json_bytes,
    file_sha256,
)
from evaluation.phase56_stage7.corpus_v2.prepare_attestation import (
    CORPUS_V2_PREPARE_ATTESTATION_VERSION,
    PrepareAttestationRefused,
    PrepareBindingFailure,
    build_prepare_attestation,
    load_prepare_attestation,
    prepared_refusal_counts,
    prepared_state_counts,
    prepared_state_map_digest,
    refusal_handle_entries,
    refusal_handle_set_digest,
    runtime_input_binding_failures,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (
    PREPARABLE_STATES,
    PreparedStateConflict,
    RuntimeContextInputV2,
    RuntimeInputRefused,
    ShadowRuntimeInputV2,
    assert_bundle_has_no_gold,
    load_runtime_input,
)
from evaluation.phase56_stage7.corpus_v2.publication import (
    CURRENT_POINTER_NAME,
    GENERATIONS_DIRECTORY_NAME,
    resolve_published_generation,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (
    LedgerState,
    RefusalCode,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (
    RuntimeSnapshotRefused,
    load_full_runtime_snapshot,
    redact_runtime_snapshot,
)
from evaluation.phase56_stage7.typed_support_frames import (
    payload_states_horizontal_support,
    stated_support_orientation,
)
from tests.support.phase56_stage7_prepare_fixtures import (
    SYNTHETIC_ARCHIVE,
    SYNTHETIC_CANDIDATE,
    SYNTHETIC_CODE_HEAD,
    SYNTHETIC_MANIFEST,
    prepared_context,
    synthetic_attestation,
    synthetic_handle,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY_ROOT / "backend" / "tools"

RUNTIME_TOOL = TOOLS / "run_phase56_stage7_v2_shadow_runtime.py"
VERIFY_TOOL = TOOLS / "run_phase56_stage7_v2_shadow_verify_prepare.py"
SCORE_TOOL = TOOLS / "run_phase56_stage7_v2_shadow_score.py"
PREPARE_TOOL = TOOLS / "run_phase56_stage7_v2_shadow_prepare.py"

# How many contexts the synthetic campaign has, and how it splits.  Small
# enough to be readable, shaped like the real one: most measurable, a few
# refused for want of a Draft.
COMPLETED = 4
REFUSED = 2


# ==========================================================================
# Harness
# ==========================================================================
def _contexts(completed: int = COMPLETED, refused: int = REFUSED):
    """A preparation in the only two states Phase M can produce."""

    return tuple(
        prepared_context(index, refused=index >= completed)
        for index in range(completed + refused)
    )


def _bundle(contexts=None) -> ShadowRuntimeInputV2:
    return ShadowRuntimeInputV2(
        original_v1_archive_sha256=SYNTHETIC_ARCHIVE,
        augmentation_manifest_sha256=SYNTHETIC_MANIFEST,
        candidate_archive_sha256=SYNTHETIC_CANDIDATE,
        contexts=_contexts() if contexts is None else tuple(contexts),
    )


def _body(payload) -> str:
    """The on-disk spelling Phase M writes, so file hashes are comparable."""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _write_pair(
    tmp_path: Path,
    *,
    bundle: ShadowRuntimeInputV2 | None = None,
    raw_mutation=None,
    attestation_mutation=None,
    seal: str | None = None,
    code_head: str = SYNTHETIC_CODE_HEAD,
    reattest: bool = False,
) -> tuple[Path, Path]:
    """Write a runtime input and its attestation, optionally tampered with.

    `raw_mutation` edits the runtime input's raw JSON *after* the honest
    attestation was computed — the ordinary attack, where only the bundle
    moves.  `reattest` re-derives the attestation from the mutated bundle
    instead, which is the joint forgery: the two files then agree with each
    other completely and only an outside reference can tell.
    """

    bundle = bundle if bundle is not None else _bundle()
    payload = json.loads(canonical_json_bytes(bundle.model_dump(mode="json")))
    honest_contexts = bundle.contexts
    # The honest file hash, taken before the tampering, because that is what
    # Phase M would have attested.  Computing it from the mutated bytes would
    # hand the attacker a matching hash for free and quietly turn every control
    # below into a weaker one.
    honest_file_sha = file_sha256(_body(payload))

    if raw_mutation is not None:
        raw_mutation(payload)
    body = _body(payload)
    runtime_input = tmp_path / "runtime_input.json"
    runtime_input.write_text(body, encoding="utf-8")

    contexts = honest_contexts
    digest = bundle.digest
    file_sha = honest_file_sha
    if reattest:
        # Re-derive from what is actually on disk.  This is what an attacker
        # with the code in front of them would do.
        forged = ShadowRuntimeInputV2.model_validate_json(json.dumps(payload))
        contexts = forged.contexts
        digest = forged.digest
        file_sha = file_sha256(body)

    attestation = synthetic_attestation(
        contexts,
        campaign_seal_name=seal,
        exact_code_head=code_head,
        runtime_input_digest=digest,
        runtime_input_file_sha256=file_sha,
    )
    attestation_payload = attestation.model_dump(mode="json")
    if attestation_mutation is not None:
        attestation_mutation(attestation_payload)
    attestation_path = tmp_path / "attestation.json"
    attestation_path.write_text(_body(attestation_payload), encoding="utf-8")
    return runtime_input, attestation_path


def _runtime_process(
    tmp_path: Path,
    runtime_input: Path,
    attestation: Path,
    *,
    code_head: str | None = SYNTHETIC_CODE_HEAD,
):
    command = [
        sys.executable,
        str(RUNTIME_TOOL),
        "--runtime-input",
        str(runtime_input),
        "--prepare-attestation",
        str(attestation),
        "--runtime-snapshot",
        str(tmp_path / "snapshot.json"),
        "--redacted-view",
        str(tmp_path / "redacted.json"),
    ]
    if code_head is not None:
        command += ["--exact-code-head", code_head]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _assert_refused_before_running(tmp_path: Path, completed, *, gate: str) -> None:
    """The shape every runtime-side control asserts.

    Three separate claims, because two of them have been true while the third
    was not: the process exits 2, the *named* gate is the reason, and the
    pipeline was never entered.

    The last one is checked two ways.  No snapshot and no redacted view exist,
    so nothing was written; and `STAGE7_V2_RUNTIME_UNEXPECTED_EXCEPTION` never
    appears — the synthetic draft payloads are not valid
    `MechanicsProblemDraftV1` documents, so a run loop that had been entered
    would have raised on the first context and said so.
    """

    assert completed.returncode == 2, completed.stdout + completed.stderr
    output = completed.stdout + completed.stderr
    assert gate in output, output
    assert "STAGE7_V2_RUNTIME_UNEXPECTED_EXCEPTION" not in output, output
    assert not (tmp_path / "snapshot.json").exists()
    assert not (tmp_path / "redacted.json").exists()


# ==========================================================================
# The harness itself must be honest about the un-tampered case
# ==========================================================================
def test_an_untampered_pair_is_admitted_and_reaches_the_pipeline(tmp_path) -> None:
    """The control group.

    Without this every negative below could be passing because the harness is
    broken rather than because the gate works.  An honest pair gets past the
    binding check — and then fails on the synthetic drafts, which is exactly
    the marker the negatives assert is *absent*.
    """

    runtime_input, attestation = _write_pair(tmp_path)

    completed = _runtime_process(tmp_path, runtime_input, attestation)
    output = completed.stdout + completed.stderr

    assert "STAGE7_V2_RUNTIME_UNEXPECTED_EXCEPTION" in output, output
    for gate in (
        PrepareBindingFailure.prepared_state_map_mismatch.value,
        PrepareBindingFailure.runtime_input_file_sha_mismatch.value,
        PrepareBindingFailure.attestation_digest_mismatch.value,
    ):
        assert gate not in output, output


# ==========================================================================
# 3.1 Cross-field validation: the laundered row cannot be spelled
# ==========================================================================
def test_a5_a_completed_context_without_a_draft_is_refused() -> None:
    """Control A5."""

    with pytest.raises(Exception) as refusal:
        RuntimeContextInputV2(
            scoring_handle=synthetic_handle(0),
            context_index=0,
            prepared_state=LedgerState.runtime_completed,
        )

    assert PreparedStateConflict.runtime_completed_without_draft.value in str(
        refusal.value
    )


def test_a6_a_refused_context_carrying_a_draft_is_refused() -> None:
    """Control A6."""

    with pytest.raises(Exception) as refusal:
        RuntimeContextInputV2(
            scoring_handle=synthetic_handle(0),
            context_index=0,
            prepared_state=LedgerState.projection_refused,
            refusal_code=RefusalCode.projection_refused_no_draft,
            draft_payload={"anything": 1},
        )

    assert PreparedStateConflict.projection_refused_with_draft.value in str(
        refusal.value
    )


def test_a_completed_context_may_not_also_carry_a_refusal_code() -> None:
    with pytest.raises(Exception) as refusal:
        RuntimeContextInputV2(
            scoring_handle=synthetic_handle(0),
            context_index=0,
            prepared_state=LedgerState.runtime_completed,
            draft_payload={"x": 1},
            refusal_code=RefusalCode.projection_refused_no_draft,
        )

    assert PreparedStateConflict.runtime_completed_with_refusal_code.value in str(
        refusal.value
    )


def test_a_projection_refusal_must_use_the_projection_refusal_code() -> None:
    with pytest.raises(Exception) as refusal:
        RuntimeContextInputV2(
            scoring_handle=synthetic_handle(0),
            context_index=0,
            prepared_state=LedgerState.projection_refused,
            refusal_code=RefusalCode.migration_refused_unresolved_entry,
        )

    assert PreparedStateConflict.projection_refused_wrong_code.value in str(
        refusal.value
    )


@pytest.mark.parametrize(
    "field, value",
    [
        ("problem_text", "a sentence the projection would have carried"),
        ("projection_terminal", "projected"),
        ("sanitized_reason", "a_reason"),
        ("derived_authority_ids", ("typed_incline_slide_motion",)),
        ("known_symbol_ids", ("v_1",)),
        ("approvable_assumption_ids", ("rest_at_start",)),
        ("environment_scoped_quantity_ids", ("g",)),
        ("segment_internal_event_ids", ("e_1",)),
        ("unknown_symbol_ids", ("t",)),
        ("event_authority_gaps", (("e_1", "missing"),)),
    ],
)
def test_a_refusal_carrying_the_projections_own_outputs_is_refused(
    field, value
) -> None:
    """The laundering signature, field by field.

    Phase M leaves every one of these at its default for a context it could not
    project — there was no projection to take them from.  A refusal that has
    one is a runtime-completed context somebody relabelled and forgot to
    strip.
    """

    with pytest.raises(Exception) as refusal:
        RuntimeContextInputV2(
            scoring_handle=synthetic_handle(0),
            context_index=0,
            prepared_state=LedgerState.projection_refused,
            refusal_code=RefusalCode.projection_refused_no_draft,
            **{field: value},
        )

    assert (
        PreparedStateConflict.projection_refused_with_runtime_authority.value
        in str(refusal.value)
    )
    assert field in str(refusal.value)


@pytest.mark.parametrize(
    "state, code",
    [
        (
            LedgerState.migration_refused,
            RefusalCode.migration_refused_unresolved_entry,
        ),
        (
            LedgerState.migration_refused,
            RefusalCode.migration_refused_conflicting_entry,
        ),
        (
            LedgerState.runtime_failed,
            RefusalCode.runtime_failed_unexpected_exception,
        ),
        (
            LedgerState.snapshot_rejected,
            RefusalCode.snapshot_rejected_incomplete_record,
        ),
    ],
)
def test_a_state_no_preparation_can_produce_is_refused(state, code) -> None:
    """3.1 C and D, pinned as unreachability rather than assumed.

    `migration_refused` is not a gap in this schema, it is a fact about the
    migration contract: `build_candidate_archive` either resolves an entry,
    leaves the record unresolved with an empty augmentation — still a
    preparable context — or raises `MigrationError` and aborts the whole
    preparation.  No path turns a migration refusal into a runtime input row.
    `runtime_failed` and `snapshot_rejected` are decided by phases that have
    not run when this file is written.  Admitting any of them would be
    admitting a state no honest Phase M can produce.
    """

    with pytest.raises(Exception) as refusal:
        RuntimeContextInputV2(
            scoring_handle=synthetic_handle(0),
            context_index=0,
            prepared_state=state,
            refusal_code=code,
        )

    assert PreparedStateConflict.state_not_preparable.value in str(refusal.value)
    assert state not in PREPARABLE_STATES


def test_the_preparable_states_are_exactly_two() -> None:
    assert PREPARABLE_STATES == {
        LedgerState.runtime_completed,
        LedgerState.projection_refused,
    }


# ==========================================================================
# 3.2 The raw no-gold scan, at the boundary and before validation
# ==========================================================================
@pytest.mark.parametrize(
    "key",
    [
        "gold",
        "answer",
        "answers",
        "expected_answer",
        "expected_terminal",
        "expected_failure_codes",
        "tolerance",
        "reference_expression",
        "family",
        "case_id",
        "split",
        "solution",
        "solver_output",
    ],
)
def test_a4_a_gold_key_nested_deep_in_a_draft_payload_is_refused(key) -> None:
    """Control A4, at every name the contract forbids.

    `draft_payload` is an open mapping, so pydantic accepts a gold member
    nested inside one: the field's type is satisfied.  The scan is what
    refuses it, and it runs on the raw document before any model sees it.
    """

    payload = {
        "original_v1_archive_sha256": SYNTHETIC_ARCHIVE,
        "augmentation_manifest_sha256": SYNTHETIC_MANIFEST,
        "candidate_archive_sha256": SYNTHETIC_CANDIDATE,
        "contexts": [
            {
                "scoring_handle": synthetic_handle(0),
                "context_index": 0,
                "prepared_state": "runtime_completed",
                "draft_payload": {"a": {"b": {"c": {key: "leaked"}}}},
            }
        ],
    }

    with pytest.raises(RuntimeInputRefused) as refusal:
        load_runtime_input(json.dumps(payload))

    assert key in str(refusal.value)


@pytest.mark.parametrize(
    "spelling", ["expectedAnswer", "expected-answer", "Expected Answer", "GOLD"]
)
def test_a_spelling_variant_of_a_gold_member_is_refused(spelling) -> None:
    """The vocabulary is matched normalized, not casefolded.

    A casefolded comparison admitted `expectedAnswer`, which is the same field
    with a different keyboard.
    """

    with pytest.raises(RuntimeInputRefused):
        assert_bundle_has_no_gold({"draft_payload": {spelling: 1}})


def test_a4_the_runtime_command_refuses_a_nested_gold_key_before_running(
    tmp_path,
) -> None:
    """Control A4 at the process boundary, on direct invocation."""

    def mutate(payload):
        payload["contexts"][0]["draft_payload"]["nested"] = {
            "deeper": {"expected_answer": 42}
        }

    runtime_input, attestation = _write_pair(
        tmp_path, raw_mutation=mutate, reattest=True
    )

    completed = _runtime_process(tmp_path, runtime_input, attestation)

    _assert_refused_before_running(
        tmp_path, completed, gate="names a gold member: expected_answer"
    )


def test_the_scan_runs_before_validation_not_after() -> None:
    """Ordering, as a property rather than a comment.

    A bundle that carries a gold member *and* is structurally invalid must be
    refused for the gold member.  If validation ran first the refusal would
    name the schema error, and a bundle that happened to validate would have
    reached the model with the expectation still in it.
    """

    payload = {
        "original_v1_archive_sha256": SYNTHETIC_ARCHIVE,
        "augmentation_manifest_sha256": SYNTHETIC_MANIFEST,
        "candidate_archive_sha256": SYNTHETIC_CANDIDATE,
        "contexts": [
            {
                "scoring_handle": "not-a-handle",
                "context_index": -1,
                "prepared_state": "runtime_completed",
                "draft_payload": {"gold": 1},
            }
        ],
    }

    with pytest.raises(RuntimeInputRefused) as refusal:
        load_runtime_input(json.dumps(payload))

    assert "gold member" in str(refusal.value)


# ==========================================================================
# 3.3 The attestation, and its own integrity
# ==========================================================================
def test_the_attestation_digest_is_canonical_json_not_a_repr() -> None:
    """3.3's serialization requirement, checked against the shared helper."""

    attestation = synthetic_attestation(_contexts())

    assert attestation.attestation_digest == canonical_digest(
        attestation.digest_material()
    )
    assert attestation.digest_is_intact()
    assert attestation.version == CORPUS_V2_PREPARE_ATTESTATION_VERSION


def test_the_attestation_separates_canonical_digests_from_file_hashes() -> None:
    """A canonical digest and a file SHA-256 are different questions.

    Both are carried, under names that say which is which, and the two are
    different values for the same artifact — so a reader who quotes one has not
    silently quoted the other.
    """

    attestation = synthetic_attestation(
        _contexts(), runtime_input_digest="d" * 64, runtime_input_file_sha256="e" * 64
    )

    assert attestation.runtime_input_digest != attestation.runtime_input_file_sha256
    assert (
        attestation.candidate_archive_digest
        != attestation.candidate_archive_file_sha256
    )
    assert (
        attestation.augmentation_manifest_digest
        != attestation.augmentation_manifest_file_sha256
    )


def test_a8_a_mutated_attestation_count_fails_its_own_digest(tmp_path) -> None:
    """Control A8: one edited byte inside the attestation."""

    attestation = synthetic_attestation(_contexts())
    payload = attestation.model_dump(mode="json")
    payload["expected_context_count"] = payload["expected_context_count"] + 1

    with pytest.raises(PrepareAttestationRefused) as refusal:
        load_prepare_attestation(json.dumps(payload))

    assert "digest does not match" in str(refusal.value)


def test_a8_a_mutated_attestation_is_refused_by_the_runtime_command(
    tmp_path,
) -> None:
    """Control A8 at the process boundary."""

    runtime_input, attestation = _write_pair(
        tmp_path,
        attestation_mutation=lambda payload: payload.__setitem__(
            "prepared_state_map_digest", "0" * 64
        ),
    )

    completed = _runtime_process(tmp_path, runtime_input, attestation)

    _assert_refused_before_running(
        tmp_path, completed, gate="digest does not match its contents"
    )


def test_the_refusal_handle_set_covers_identity_and_not_only_count() -> None:
    """Why a count digest would not have been enough.

    Two preparations with the same number of refusals and different refused
    contexts must not hash the same, or the swap in A7 is invisible.
    """

    honest = _contexts()
    swapped = tuple(
        prepared_context(context.context_index, refused=context.context_index in {0, 4})
        for context in honest
    )

    assert prepared_state_counts(honest) == prepared_state_counts(swapped)
    assert prepared_refusal_counts(honest) == prepared_refusal_counts(swapped)
    assert refusal_handle_set_digest(honest) != refusal_handle_set_digest(swapped)
    assert prepared_state_map_digest(honest) != prepared_state_map_digest(swapped)


def test_the_refusal_handle_entries_are_sorted_and_carry_their_code() -> None:
    entries = refusal_handle_entries(_contexts())

    assert [entry.context_index for entry in entries] == sorted(
        entry.context_index for entry in entries
    )
    assert all(
        entry.refusal_code is RefusalCode.projection_refused_no_draft
        for entry in entries
    )
    assert len(entries) == REFUSED


# ==========================================================================
# 3.5 Phase R's binding check — the laundering controls
# ==========================================================================
def _launder(payload, indices) -> None:
    """Relabel measurable contexts as anticipated refusals, cleanly.

    Cleanly, because a sloppy relabelling is caught by the cross-field
    validator instead and the control would be exercising the wrong gate: the
    projection's outputs are stripped along with the draft, so what reaches the
    binding check is a bundle that is internally valid in every respect and
    only disagrees with what Phase M attested.
    """

    for context in payload["contexts"]:
        if context["context_index"] not in indices:
            continue
        context["prepared_state"] = "projection_refused"
        context["refusal_code"] = "projection_refused_no_draft"
        context["draft_payload"] = None
        for name in ("problem_text", "projection_terminal", "sanitized_reason"):
            context[name] = None
        for name in (
            "derived_authority_ids",
            "environment_scoped_quantity_ids",
            "segment_internal_event_ids",
            "approvable_assumption_ids",
            "known_symbol_ids",
            "unknown_symbol_ids",
            "event_authority_gaps",
        ):
            context[name] = []
        context.pop("augmentation", None)


def test_a1_one_laundered_context_fails_the_state_map(tmp_path) -> None:
    """Control A1: a single runtime-completed context excused into a refusal."""

    runtime_input, attestation = _write_pair(
        tmp_path, raw_mutation=lambda payload: _launder(payload, {0})
    )

    completed = _runtime_process(tmp_path, runtime_input, attestation)

    _assert_refused_before_running(
        tmp_path,
        completed,
        gate=PrepareBindingFailure.prepared_state_map_mismatch.value,
    )
    output = completed.stdout + completed.stderr
    assert PrepareBindingFailure.refusal_handle_set_mismatch.value in output
    assert PrepareBindingFailure.state_counts_mismatch.value in output


def test_a2_laundering_every_measurable_context_fails(tmp_path) -> None:
    """Control A2: the whole attack, at full scale.

    The bundle that reaches the gate is a perfectly complete, perfectly
    coherent account of a hundred-per-cent-refused corpus.  Every ledger rule
    would pass it.  What refuses it is that Phase M never prepared it.
    """

    runtime_input, attestation = _write_pair(
        tmp_path,
        raw_mutation=lambda payload: _launder(payload, set(range(COMPLETED))),
    )

    completed = _runtime_process(tmp_path, runtime_input, attestation)

    _assert_refused_before_running(
        tmp_path,
        completed,
        gate=PrepareBindingFailure.prepared_state_map_mismatch.value,
    )
    output = completed.stdout + completed.stderr
    assert PrepareBindingFailure.state_counts_mismatch.value in output
    assert PrepareBindingFailure.refusal_handle_set_mismatch.value in output


def test_a2_the_all_refused_bundle_would_otherwise_have_passed_completeness(
    tmp_path,
) -> None:
    """Why A2 needed a new structure rather than a stricter ledger.

    The laundered bundle is loadable, its handles are unique and complete, and
    every refusal in it is one the contract anticipates.  Nothing in the
    completeness vocabulary objects — which is precisely the finding.
    """

    payload = json.loads(canonical_json_bytes(_bundle().model_dump(mode="json")))
    _launder(payload, set(range(COMPLETED)))
    laundered = load_runtime_input(json.dumps(payload))

    assert len(laundered.contexts) == COMPLETED + REFUSED
    assert all(
        context.prepared_state is LedgerState.projection_refused
        for context in laundered.contexts
    )
    assert all(
        context.refusal_code in {RefusalCode.projection_refused_no_draft}
        for context in laundered.contexts
    )
    assert len(set(laundered.expected_handles)) == len(laundered.contexts)

    # And the attestation is the thing that objects.
    honest = synthetic_attestation(_contexts())
    failures = runtime_input_binding_failures(
        honest, laundered, runtime_input_file_sha256=honest.runtime_input_file_sha256
    )
    assert PrepareBindingFailure.prepared_state_map_mismatch.value in failures


def test_a3_a_single_edited_byte_fails_the_file_hash_and_not_the_state_map(
    tmp_path,
) -> None:
    """Control A3, and the reason the failure set is reported in full.

    Editing a problem text changes the bytes and the canonical digest and
    leaves the prepared-state map alone.  A1 changes the state map too.  The
    two controls are distinguishable only because every failure is named.
    """

    def mutate(payload):
        payload["contexts"][0]["problem_text"] = "an edited sentence"

    runtime_input, attestation = _write_pair(tmp_path, raw_mutation=mutate)

    completed = _runtime_process(tmp_path, runtime_input, attestation)

    _assert_refused_before_running(
        tmp_path,
        completed,
        gate=PrepareBindingFailure.runtime_input_file_sha_mismatch.value,
    )
    output = completed.stdout + completed.stderr
    assert PrepareBindingFailure.runtime_input_digest_mismatch.value in output
    assert PrepareBindingFailure.prepared_state_map_mismatch.value not in output


def test_a7_swapping_which_contexts_are_refused_fails(tmp_path) -> None:
    """Control A7: the counts are preserved and the identities are not.

    Refuse a measurable context, admit a refused one, and every count in the
    ledger is unchanged.  This is the attack a count-only seal cannot see.
    """

    swapped = tuple(
        prepared_context(index, refused=index in {0, 1})
        for index in range(COMPLETED + REFUSED)
    )
    honest = _contexts()
    assert prepared_state_counts(swapped) == prepared_state_counts(honest)

    payload = json.loads(
        canonical_json_bytes(_bundle(contexts=swapped).model_dump(mode="json"))
    )
    body = _body(payload)
    runtime_input = tmp_path / "runtime_input.json"
    runtime_input.write_text(body, encoding="utf-8")
    # The attestation describes the honest preparation; only the bundle moved.
    attestation = synthetic_attestation(
        honest,
        runtime_input_digest=ShadowRuntimeInputV2.model_validate_json(
            json.dumps(payload)
        ).digest,
        runtime_input_file_sha256=file_sha256(body),
    )
    attestation_path = tmp_path / "attestation.json"
    attestation_path.write_text(
        _body(attestation.model_dump(mode="json")), encoding="utf-8"
    )

    completed = _runtime_process(tmp_path, runtime_input, attestation_path)

    _assert_refused_before_running(
        tmp_path,
        completed,
        gate=PrepareBindingFailure.refusal_handle_set_mismatch.value,
    )
    output = completed.stdout + completed.stderr
    assert PrepareBindingFailure.prepared_state_map_mismatch.value in output
    # The counts really were preserved: this is not a count failure.
    assert PrepareBindingFailure.state_counts_mismatch.value not in output


def test_a11_a_different_exact_code_head_fails(tmp_path) -> None:
    """Control A11."""

    runtime_input, attestation = _write_pair(tmp_path, code_head="cafebabe")

    completed = _runtime_process(
        tmp_path, runtime_input, attestation, code_head=SYNTHETIC_CODE_HEAD
    )

    _assert_refused_before_running(
        tmp_path,
        completed,
        gate=PrepareBindingFailure.exact_code_head_mismatch.value,
    )


def test_the_runtime_command_requires_an_attestation(tmp_path) -> None:
    """There is no path that runs without one.

    A flag with a default would be a fail-open path: the binding check would
    simply not happen for a caller who omitted it.
    """

    runtime_input, _ = _write_pair(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(RUNTIME_TOOL),
            "--runtime-input",
            str(runtime_input),
            "--runtime-snapshot",
            str(tmp_path / "snapshot.json"),
            "--redacted-view",
            str(tmp_path / "redacted.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--prepare-attestation" in completed.stderr
    assert not (tmp_path / "snapshot.json").exists()


# ==========================================================================
# 3.4 Phase V — the joint forgery
# ==========================================================================
def test_a9_a_jointly_forged_pair_satisfies_phase_r_and_not_phase_v(
    tmp_path,
) -> None:
    """Control A9, the one that decides whether any of this holds.

    The runtime input is laundered and the attestation is re-derived from the
    laundered file, exactly as the code would compute it.  The two agree about
    every hash, every digest, every count.  Phase R's binding check — which is
    a comparison *between these two documents* — has nothing to object to.

    That is not a defect in Phase R; it is the boundary of what any
    artifact-to-artifact check can do, and it is why Phase V rebuilds from the
    corpus instead.
    """

    runtime_input, attestation = _write_pair(
        tmp_path,
        raw_mutation=lambda payload: _launder(payload, set(range(COMPLETED))),
        reattest=True,
    )

    forged_bundle = load_runtime_input(runtime_input.read_text(encoding="utf-8"))
    forged_attestation = load_prepare_attestation(
        attestation.read_text(encoding="utf-8")
    )

    # The pair is internally perfect.
    assert forged_attestation.digest_is_intact()
    assert (
        runtime_input_binding_failures(
            forged_attestation,
            forged_bundle,
            runtime_input_file_sha256=file_sha256(
                runtime_input.read_text(encoding="utf-8")
            ),
            exact_code_head=SYNTHETIC_CODE_HEAD,
        )
        == ()
    )
    assert dict(forged_attestation.prepared_state_counts)[
        LedgerState.runtime_completed.value
    ] == 0

    # And it describes a preparation the honest one does not.
    honest = synthetic_attestation(_contexts())
    assert (
        forged_attestation.prepared_state_map_digest
        != honest.prepared_state_map_digest
    )
    assert (
        forged_attestation.refusal_handle_set_digest
        != honest.refusal_handle_set_digest
    )


def test_a9_the_verifier_refuses_a_forged_pair_against_a_rebuild(tmp_path) -> None:
    """Control A9's other half: the rebuild is what sees it.

    Phase V's comparison is against values re-derived from the corpus, and the
    forged pair cannot move those.  Exercised here at the function level with
    the rebuild standing in for the corpus; the command-level equivalent runs
    against the real archive out of tree.
    """

    payload = json.loads(canonical_json_bytes(_bundle().model_dump(mode="json")))
    _launder(payload, set(range(COMPLETED)))
    forged = ShadowRuntimeInputV2.model_validate_json(json.dumps(payload))
    rebuilt = _contexts()

    assert prepared_state_map_digest(forged.contexts) != prepared_state_map_digest(
        rebuilt
    )
    assert refusal_handle_set_digest(forged.contexts) != refusal_handle_set_digest(
        rebuilt
    )
    assert prepared_state_counts(forged.contexts) != prepared_state_counts(rebuilt)


def _synthetic_campaign(tmp_path, monkeypatch):
    """A whole preparation over an independently authored corpus.

    `read_public_corpus_archive` pins the frozen public archive's SHA-256, and
    that pin is correct — no flag loosens it, because a flag that loosened it
    would be the fail-open path.  So this runs Phase V in-process with the
    expectation redirected at the synthetic archive's own hash, which exercises
    the real rebuild-and-compare against a corpus this repository owns.
    """

    import hashlib

    from evaluation.phase56_stage7.corpus_integrity import read_public_corpus_archive
    from evaluation.phase56_stage7.corpus_v2 import prepare_builder
    from tests.support.phase56_stage7_corpus_fixtures import (
        default_members,
        write_plain_archive,
    )

    archive = tmp_path / "corpus.zip"
    write_plain_archive(archive, default_members())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(
        prepare_builder,
        "read_public_corpus_archive",
        lambda path: read_public_corpus_archive(path, expected_sha256=digest),
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "phase56-stage7-corpus-v2-record-v1",
                "migration_version": "phase56-stage7-corpus-v2-migration-v1",
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    return archive, manifest


def _run_verifier(tmp_path, monkeypatch, archive, manifest, code_head) -> int:
    import runpy

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(VERIFY_TOOL),
            "--corpus-archive",
            str(archive),
            "--manifest",
            str(manifest),
            "--candidate-archive",
            str(tmp_path / "candidate.json"),
            "--runtime-input",
            str(tmp_path / "runtime_input.json"),
            "--prepare-attestation",
            str(tmp_path / "attestation.json"),
            "--verification-report",
            str(tmp_path / "verify.json"),
            "--exact-code-head",
            code_head,
        ],
    )
    module = runpy.run_path(str(VERIFY_TOOL), run_name="not_main")
    return module["main"]()


def test_a9_the_verifier_rebuild_refuses_a_jointly_forged_pair_end_to_end(
    tmp_path, monkeypatch, capsys
) -> None:
    """Control A9 as a whole command, over a real corpus rebuild.

    A complete preparation is produced, then laundered, then re-attested from
    the laundered file so the two artifacts agree perfectly with each other.
    Phase V opens the corpus again, rebuilds, and disagrees — which is the only
    check in the chain a joint forgery cannot satisfy.
    """

    from evaluation.phase56_stage7.corpus_v2 import prepare_builder

    archive, manifest = _synthetic_campaign(tmp_path, monkeypatch)
    honest = prepare_builder.build_prepared_campaign(
        corpus_archive=archive, manifest=manifest
    )
    (tmp_path / "candidate.json").write_text(honest.candidate_body, encoding="utf-8")

    # Launder every measurable context, then re-attest the laundered file.
    payload = json.loads(honest.runtime_input_body)
    _launder(payload, {c["context_index"] for c in payload["contexts"]})
    forged = ShadowRuntimeInputV2.model_validate_json(json.dumps(payload))
    forged_body = _body(forged.model_dump(mode="json"))
    (tmp_path / "runtime_input.json").write_text(forged_body, encoding="utf-8")

    forged_attestation = build_prepare_attestation(
        campaign_seal_name=None,
        exact_code_head=SYNTHETIC_CODE_HEAD,
        original_v1_archive_sha256=honest.original_v1_archive_sha256,
        augmentation_manifest_digest=honest.augmentation_manifest_digest,
        augmentation_manifest_file_sha256=honest.augmentation_manifest_file_sha256,
        candidate_archive_digest=honest.candidate_archive_digest,
        candidate_archive_file_sha256=honest.candidate_file_sha256,
        runtime_input_digest=forged.digest,
        runtime_input_file_sha256=file_sha256(forged_body),
        contexts=forged.contexts,
        unresolved_augmentation_count=forged.unresolved_augmentation_count,
    )
    (tmp_path / "attestation.json").write_text(
        _body(forged_attestation.model_dump(mode="json")), encoding="utf-8"
    )

    # The pair is internally flawless: Phase R's binding check finds nothing.
    assert (
        runtime_input_binding_failures(
            forged_attestation,
            forged,
            runtime_input_file_sha256=file_sha256(forged_body),
            exact_code_head=SYNTHETIC_CODE_HEAD,
        )
        == ()
    )

    status = _run_verifier(
        tmp_path, monkeypatch, archive, manifest, SYNTHETIC_CODE_HEAD
    )
    output = capsys.readouterr().out

    assert status == 2, output
    assert "replay_prepared_state_map_mismatch" in output
    assert "replay_refusal_handle_set_mismatch" in output
    assert "replay_runtime_input_bytes_mismatch" in output
    assert "STAGE7_V2_VERIFY_PREPARE_ACCEPTANCE=FAIL" in output


def test_an_honest_preparation_passes_the_verifier_end_to_end(
    tmp_path, monkeypatch, capsys
) -> None:
    """The control group for A9: an untampered preparation verifies."""

    from evaluation.phase56_stage7.corpus_v2 import prepare_builder

    archive, manifest = _synthetic_campaign(tmp_path, monkeypatch)
    honest = prepare_builder.build_prepared_campaign(
        corpus_archive=archive, manifest=manifest
    )
    (tmp_path / "candidate.json").write_text(honest.candidate_body, encoding="utf-8")
    (tmp_path / "runtime_input.json").write_text(
        honest.runtime_input_body, encoding="utf-8"
    )
    attestation = build_prepare_attestation(
        campaign_seal_name=None,
        exact_code_head=SYNTHETIC_CODE_HEAD,
        original_v1_archive_sha256=honest.original_v1_archive_sha256,
        augmentation_manifest_digest=honest.augmentation_manifest_digest,
        augmentation_manifest_file_sha256=honest.augmentation_manifest_file_sha256,
        candidate_archive_digest=honest.candidate_archive_digest,
        candidate_archive_file_sha256=honest.candidate_file_sha256,
        runtime_input_digest=honest.runtime_input.digest,
        runtime_input_file_sha256=honest.runtime_input_file_sha256,
        contexts=honest.runtime_input.contexts,
        unresolved_augmentation_count=honest.unresolved_augmentation_count,
    )
    (tmp_path / "attestation.json").write_text(
        _body(attestation.model_dump(mode="json")), encoding="utf-8"
    )

    status = _run_verifier(
        tmp_path, monkeypatch, archive, manifest, SYNTHETIC_CODE_HEAD
    )
    output = capsys.readouterr().out

    assert status == 0, output
    assert "STAGE7_V2_VERIFY_PREPARE_ACCEPTANCE=PASS" in output


def test_the_preparation_is_byte_identical_across_two_rebuilds(
    tmp_path, monkeypatch
) -> None:
    """Determinism at the artifact level, which the rebuild gate depends on."""

    from evaluation.phase56_stage7.corpus_v2 import prepare_builder

    archive, manifest = _synthetic_campaign(tmp_path, monkeypatch)
    first = prepare_builder.build_prepared_campaign(
        corpus_archive=archive, manifest=manifest
    )
    second = prepare_builder.build_prepared_campaign(
        corpus_archive=archive, manifest=manifest
    )

    assert first.candidate_body == second.candidate_body
    assert first.runtime_input_body == second.runtime_input_body
    assert first.candidate_file_sha256 == second.candidate_file_sha256
    assert first.runtime_input_file_sha256 == second.runtime_input_file_sha256
    assert prepared_state_map_digest(
        first.runtime_input.contexts
    ) == prepared_state_map_digest(second.runtime_input.contexts)


def test_the_population_digests_do_not_depend_on_the_manifest(
    tmp_path, monkeypatch
) -> None:
    """Why the seal's population values could be regenerated without it.

    A context's prepared state is decided by `project_case_to_draft`, which
    reads the v1 record and nothing else — so which contexts are refused, in
    which order, under which handles, is a property of the corpus alone.  The
    seal's two manifest hashes are a different matter and are checked
    separately.
    """

    from evaluation.phase56_stage7.corpus_v2 import prepare_builder

    archive, manifest = _synthetic_campaign(tmp_path, monkeypatch)
    baseline = prepare_builder.build_prepared_campaign(
        corpus_archive=archive, manifest=manifest
    )

    # A manifest with a different digest that resolves to the same archive: an
    # unresolved entry is never migrated, so only the manifest hash moves.
    fingerprint = json.loads(baseline.candidate_body)["records"][0][
        "original_fingerprint"
    ]
    other = tmp_path / "other_manifest.json"
    other.write_text(
        json.dumps(
            {
                "schema_version": "phase56-stage7-corpus-v2-record-v1",
                "migration_version": "phase56-stage7-corpus-v2-migration-v1",
                "entries": [
                    {
                        "original_fingerprint": fingerprint,
                        "review_status": "unresolved",
                        "authoring_provenance": "independence probe",
                        "unresolved_reason": "probe",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    probed = prepare_builder.build_prepared_campaign(
        corpus_archive=archive, manifest=other
    )

    assert (
        probed.augmentation_manifest_digest != baseline.augmentation_manifest_digest
    )
    for projection in (
        prepared_state_map_digest,
        refusal_handle_set_digest,
        prepared_state_counts,
        prepared_refusal_counts,
    ):
        assert projection(probed.runtime_input.contexts) == projection(
            baseline.runtime_input.contexts
        )


def test_the_verifier_never_imports_a_solver_a_runtime_or_a_scorer() -> None:
    """Phase V's import graph, by AST rather than by substring.

    It is allowed to open the corpus and the preparation projection — that is
    the whole job — and it may not hold anything that could execute the
    pipeline or compare an answer.  A docstring mentioning the word "solver"
    must not be able to fail this, which is why the check parses.
    """

    imported = _imported_names(VERIFY_TOOL)

    for forbidden in (
        "run_lane_b_case",
        "run_shadow_context",
        "shadow_runner",
        "lane_b_runner",
        "lane_b_scoring",
        "gold_scoring",
        "compare_answer_to_gold",
        "score_shadow_snapshot",
        "build_gold_index",
        "gold_domain",
        "solver",
        "verifier",
    ):
        assert forbidden not in imported, forbidden


def test_the_verifier_is_allowed_the_corpus_and_the_projection() -> None:
    """The other direction, so the test above cannot pass by the file being empty."""

    imported = _imported_names(VERIFY_TOOL)

    assert "prepare_builder" in imported
    assert "build_prepared_campaign" in imported


def test_the_verifier_writes_only_its_own_report() -> None:
    """A verifier that can repair what it verifies has verified nothing."""

    source = VERIFY_TOOL.read_text("utf-8")
    tree = ast.parse(source)
    written = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"write_text", "write_bytes", "replace", "unlink"}
    }
    # The verifier delegates its one output to the byte-exact atomic writer.
    # It has no direct filesystem mutation primitive with which it could repair
    # the inputs it verifies.
    assert written == set()
    assert source.count("write_utf8_atomic(") == 1


def test_the_orchestrator_runs_the_verifier_between_prepare_and_runtime() -> None:
    """The ordering that makes "zero runtime calls" true.

    A verifier that ran after the runtime would be an audit trail rather than a
    gate.
    """

    source = (TOOLS / "run_phase56_stage7_v2_shadow.py").read_text("utf-8")

    prepare = source.index("PHASE_M_PREPARE")
    verify = source.index("PHASE_V_VERIFY_PREPARE")
    runtime = source.index("PHASE_R_RUNTIME")
    score = source.index("PHASE_G_SCORE")

    assert prepare < verify < runtime < score
    assert VERIFY_TOOL.exists()


# ==========================================================================
# 3.6 / 3.7 Snapshot and Phase G binding
# ==========================================================================
def _frozen_snapshot():
    from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (
        ShadowLedgerEntryV2,
        ShadowRuntimeRecordV2,
        freeze_runtime_snapshot,
        prepare_binding_from_attestation,
    )

    attestation = synthetic_attestation(_contexts())
    ledger = [
        ShadowLedgerEntryV2(
            scoring_handle=synthetic_handle(index),
            state=LedgerState.runtime_completed,
        )
        for index in range(COMPLETED)
    ] + [
        ShadowLedgerEntryV2(
            scoring_handle=synthetic_handle(index),
            state=LedgerState.projection_refused,
            refusal_code=RefusalCode.projection_refused_no_draft,
        )
        for index in range(COMPLETED, COMPLETED + REFUSED)
    ]
    records = [
        ShadowRuntimeRecordV2(
            scoring_handle=synthetic_handle(index),
            cohort_digest="d" * 64,
            baseline_rung="law_emitted_graph_underdetermined",
            shadow_rung="solved_and_verified",
            shadow_solved=True,
            answer_value_si=3.0,
            answer_unit="m/s^2",
        )
        for index in range(COMPLETED)
    ]
    snapshot = freeze_runtime_snapshot(
        records,
        ledger=ledger,
        original_v1_archive_sha256=SYNTHETIC_ARCHIVE,
        augmentation_manifest_sha256=SYNTHETIC_MANIFEST,
        candidate_archive_sha256=SYNTHETIC_CANDIDATE,
        prepare_binding=prepare_binding_from_attestation(attestation),
        exact_code_head=SYNTHETIC_CODE_HEAD,
    )
    return snapshot, attestation


def test_the_snapshot_carries_the_prepare_binding_and_hashes_it() -> None:
    """3.6: the binding is in the digest material, not beside it."""

    snapshot, attestation = _frozen_snapshot()

    assert snapshot.prepare_binding.prepare_attestation_digest == (
        attestation.attestation_digest
    )
    assert snapshot.prepare_binding.prepared_state_map_digest == (
        attestation.prepared_state_map_digest
    )
    assert snapshot.digest_is_intact()
    assert "prepare_binding" in snapshot.digest_material().decode("utf-8")


def test_a10_editing_the_snapshots_prepare_binding_breaks_its_digest() -> None:
    """Control A10."""

    snapshot, _ = _frozen_snapshot()
    payload = json.loads(json.dumps(snapshot.model_dump(mode="json")))
    payload["prepare_binding"]["prepare_attestation_digest"] = "0" * 64

    with pytest.raises(RuntimeSnapshotRefused) as refusal:
        load_full_runtime_snapshot(json.dumps(payload))

    assert "digest does not match" in str(refusal.value)


def test_a_snapshot_with_no_prepare_binding_cannot_be_loaded() -> None:
    """The binding is required, so omitting it is not a way around it."""

    snapshot, _ = _frozen_snapshot()
    payload = json.loads(json.dumps(snapshot.model_dump(mode="json")))
    payload.pop("prepare_binding")

    with pytest.raises(RuntimeSnapshotRefused):
        load_full_runtime_snapshot(json.dumps(payload))


def test_a_snapshot_cannot_name_a_code_head_the_preparation_did_not() -> None:
    from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (
        ShadowLedgerEntryV2,
        freeze_runtime_snapshot,
        prepare_binding_from_attestation,
    )

    attestation = synthetic_attestation(_contexts(), exact_code_head="cafebabe")

    with pytest.raises(RuntimeSnapshotRefused) as refusal:
        freeze_runtime_snapshot(
            [],
            ledger=[
                ShadowLedgerEntryV2(
                    scoring_handle=synthetic_handle(index),
                    state=LedgerState.projection_refused,
                    refusal_code=RefusalCode.projection_refused_no_draft,
                )
                for index in range(COMPLETED + REFUSED)
            ],
            original_v1_archive_sha256=SYNTHETIC_ARCHIVE,
            augmentation_manifest_sha256=SYNTHETIC_MANIFEST,
            candidate_archive_sha256=SYNTHETIC_CANDIDATE,
            prepare_binding=prepare_binding_from_attestation(attestation),
            exact_code_head=SYNTHETIC_CODE_HEAD,
        )

    assert "prepare_exact_code_head_mismatch" in str(refusal.value)


def test_the_redacted_view_publishes_digests_and_never_a_handle_set() -> None:
    """3.6's privacy line, and the reason it is drawn where it is.

    A scoring handle is `sha256(archive_sha256 || context_index)`, the archive
    SHA-256 is published, and the corpus has a hundred contexts — so a digest
    over the refused handles is brute-forceable back to which positions were
    refused.  The whole-document digests invert to nothing and stay.
    """

    snapshot, attestation = _frozen_snapshot()
    view = redact_runtime_snapshot(snapshot)
    body = json.dumps(view.model_dump(mode="json"), ensure_ascii=False)

    assert view.prepare_attestation_digest == attestation.attestation_digest
    assert view.prepared_state_counts == tuple(attestation.prepared_state_counts)
    assert attestation.refusal_handle_set_digest not in body
    assert attestation.expected_handle_set_digest not in body
    assert "scoring_handle" not in body
    for handle in (synthetic_handle(index) for index in range(COMPLETED + REFUSED)):
        assert handle not in body


def test_the_score_command_requires_an_attestation(tmp_path) -> None:
    snapshot, _ = _frozen_snapshot()
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot.model_dump(mode="json")), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCORE_TOOL),
            "--corpus-archive",
            str(tmp_path / "nope.zip"),
            "--runtime-snapshot",
            str(path),
            "--shadow-report",
            str(tmp_path / "report.json"),
            "--scorecard",
            str(tmp_path / "scorecard.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--prepare-attestation" in completed.stderr


def test_a10_the_score_command_refuses_a_snapshot_bound_elsewhere(tmp_path) -> None:
    """Control A10 at the process boundary, before the corpus is opened.

    The snapshot is internally intact and describes a different preparation
    from the attestation it is presented with.  The refusal happens with a
    corpus path that does not exist, which proves the gold was never reached.
    """

    snapshot, _ = _frozen_snapshot()
    other = synthetic_attestation(
        tuple(
            prepared_context(index, refused=index in {0, 1})
            for index in range(COMPLETED + REFUSED)
        )
    )
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot.model_dump(mode="json")), encoding="utf-8"
    )
    attestation_path = tmp_path / "attestation.json"
    attestation_path.write_text(
        json.dumps(other.model_dump(mode="json")), encoding="utf-8"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCORE_TOOL),
            "--corpus-archive",
            str(tmp_path / "no-such-corpus.zip"),
            "--runtime-snapshot",
            str(snapshot_path),
            "--prepare-attestation",
            str(attestation_path),
            "--shadow-report",
            str(tmp_path / "report.json"),
            "--scorecard",
            str(tmp_path / "scorecard.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout + completed.stderr

    assert completed.returncode == 2, output
    assert PrepareBindingFailure.attestation_digest_mismatch.value in output
    assert PrepareBindingFailure.prepared_state_map_mismatch.value in output
    assert not (tmp_path / "report.json").exists()
    assert not (tmp_path / "scorecard.json").exists()


def test_the_scoring_phase_still_holds_no_pipeline() -> None:
    """The existing isolation contract, re-asserted after the new imports."""

    imported = _imported_names(SCORE_TOOL)

    for forbidden in (
        "run_lane_b_case",
        "run_shadow_context",
        "project_case_to_draft",
        "project_augmentation",
        "MechanicsProblemDraftV1",
        "build_candidate_archive",
        "shadow_runner",
        "projection",
        "lane_b_runner",
        "lane_b_draft_projection",
        "prepare_builder",
    ):
        assert forbidden not in imported, forbidden


def test_the_runtime_phase_still_cannot_reach_the_gold_domain() -> None:
    imported = _imported_names(RUNTIME_TOOL)

    for forbidden in (
        "gold_scoring",
        "compare_answer_to_gold",
        "corpus_preflight",
        "corpus_integrity",
        "read_public_corpus_archive",
        "load_public_cases",
        "PublicCorpusCaseV1",
        "gold_domain",
        "lane_b_scoring",
        "prepare_builder",
    ):
        assert forbidden not in imported, forbidden


# ==========================================================================
# 3.8 The frozen campaign population seal
# ==========================================================================
def test_the_public_campaign_seal_states_ninety_seven_and_three() -> None:
    seal = STAGE7_PUBLIC_CAMPAIGN_SEAL_V1

    assert seal.expected_context_count == 100
    assert dict(seal.prepared_state_counts) == {
        "runtime_completed": 97,
        "projection_refused": 3,
        "migration_refused": 0,
        "runtime_failed": 0,
        "snapshot_rejected": 0,
    }
    assert dict(seal.prepared_refusal_counts) == {
        "projection_refused_no_draft": 3,
        "migration_refused_unresolved_entry": 0,
        "migration_refused_conflicting_entry": 0,
        "runtime_failed_unexpected_exception": 0,
        "snapshot_rejected_incomplete_record": 0,
    }
    assert seal.original_v1_archive_sha256 == (
        "cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef"
    )
    assert resolve_campaign_seal(STAGE7_PUBLIC_CAMPAIGN_SEAL_NAME) is seal


# The population fields the real preparation derives from a hundred contexts.
# This suite does not build a hundred contexts, so it takes them from the seal
# and lets a test move exactly one — which is what isolates each gate.
_POPULATION_FIELDS = (
    "expected_context_count",
    "context_index_set_digest",
    "expected_handle_set_digest",
    "prepared_state_map_digest",
    "refusal_handle_set_digest",
    "prepared_state_counts",
    "prepared_refusal_counts",
)


def _sealed(**overrides):
    """An attestation shaped like the sealed campaign, with fields overridden.

    Overrides are split, because the two kinds are not interchangeable: the
    identity fields are inputs to `build_prepare_attestation`, and the
    population fields are things it *derives* from the contexts it is given.
    A test that wants to move a derived field has to state it afterwards.
    """

    seal = STAGE7_PUBLIC_CAMPAIGN_SEAL_V1
    population = {
        name: overrides.pop(name, getattr(seal, name)) for name in _POPULATION_FIELDS
    }
    fields = {
        "campaign_seal_name": seal.name,
        "exact_code_head": SYNTHETIC_CODE_HEAD,
        "original_v1_archive_sha256": seal.original_v1_archive_sha256,
        "augmentation_manifest_digest": seal.augmentation_manifest_digest,
        "augmentation_manifest_file_sha256": seal.augmentation_manifest_file_sha256,
        "candidate_archive_digest": SYNTHETIC_CANDIDATE,
        "candidate_archive_file_sha256": "0" * 64,
        "runtime_input_digest": "d" * 64,
        "runtime_input_file_sha256": "e" * 64,
        "contexts": (),
    }
    fields.update(overrides)
    return build_prepare_attestation(**fields).model_copy(update=population)


def test_an_attestation_matching_the_seal_passes_it() -> None:
    """The control group for every seal negative below."""

    assert campaign_seal_failures(_sealed(), STAGE7_PUBLIC_CAMPAIGN_SEAL_V1) == ()


@pytest.mark.parametrize(
    "overrides, gate",
    [
        pytest.param(
            {
                "prepared_state_counts": (
                    ("migration_refused", 0),
                    ("projection_refused", 4),
                    ("runtime_completed", 96),
                    ("runtime_failed", 0),
                    ("snapshot_rejected", 0),
                )
            },
            CampaignSealFailure.state_counts_mismatch.value,
            id="three_refusals_become_four",
        ),
        pytest.param(
            {
                "prepared_refusal_counts": (
                    ("migration_refused_conflicting_entry", 0),
                    ("migration_refused_unresolved_entry", 0),
                    ("projection_refused_no_draft", 4),
                    ("runtime_failed_unexpected_exception", 0),
                    ("snapshot_rejected_incomplete_record", 0),
                )
            },
            CampaignSealFailure.refusal_counts_mismatch.value,
            id="refusal_code_count_moves",
        ),
        pytest.param(
            {"refusal_handle_set_digest": "1" * 64},
            CampaignSealFailure.refusal_handle_set_mismatch.value,
            id="refused_handles_swapped_at_equal_count",
        ),
        pytest.param(
            {"context_index_set_digest": "2" * 64},
            CampaignSealFailure.context_index_set_mismatch.value,
            id="context_order_changed",
        ),
        pytest.param(
            {"expected_handle_set_digest": "3" * 64},
            CampaignSealFailure.expected_handle_set_mismatch.value,
            id="handle_set_changed",
        ),
        pytest.param(
            {"prepared_state_map_digest": "4" * 64},
            CampaignSealFailure.prepared_state_map_mismatch.value,
            id="state_map_changed",
        ),
        pytest.param(
            {"augmentation_manifest_digest": "5" * 64},
            CampaignSealFailure.manifest_digest_mismatch.value,
            id="exact_manifest_substituted",
        ),
        pytest.param(
            {"augmentation_manifest_file_sha256": "6" * 64},
            CampaignSealFailure.manifest_file_sha_mismatch.value,
            id="manifest_file_substituted",
        ),
        pytest.param(
            {"original_v1_archive_sha256": "7" * 64},
            CampaignSealFailure.corpus_archive_mismatch.value,
            id="corpus_hash_substituted",
        ),
        pytest.param(
            {"expected_context_count": 99},
            CampaignSealFailure.context_count_mismatch.value,
            id="a_context_left_the_campaign",
        ),
        pytest.param(
            {"campaign_seal_name": None},
            CampaignSealFailure.not_sealed.value,
            id="seal_dropped_from_the_attestation",
        ),
        pytest.param(
            {"campaign_seal_name": "some-other-campaign"},
            CampaignSealFailure.name_mismatch.value,
            id="a_different_campaign_claimed",
        ),
    ],
)
def test_the_seal_refuses_every_population_substitution(overrides, gate) -> None:
    """3.8's attack list, each at the gate it is supposed to hit."""

    failures = campaign_seal_failures(_sealed(**overrides), STAGE7_PUBLIC_CAMPAIGN_SEAL_V1)

    assert gate in failures, failures


def test_the_ninety_seven_three_split_is_not_hard_coded_into_the_ledger() -> None:
    """3.8's structural requirement.

    The seal is a separate versioned contract rather than counts baked into the
    ledger's enums, because the two change for different reasons: a new refusal
    code is a contract change, and a corpus revision is a new campaign that
    should get its own seal rather than quietly editing this one.
    """

    ledger_source = (
        REPOSITORY_ROOT
        / "backend"
        / "evaluation"
        / "phase56_stage7"
        / "corpus_v2"
        / "runtime_ledger.py"
    ).read_text("utf-8")

    assert "97" not in ledger_source
    assert STAGE7_PUBLIC_CAMPAIGN_SEAL_NAME not in ledger_source


def test_a_run_that_names_no_seal_still_cannot_claim_the_sealed_campaign() -> None:
    """Bypassing by omission is itself a named failure."""

    unsealed = _sealed(campaign_seal_name=None)

    assert CampaignSealFailure.not_sealed.value in campaign_seal_failures(
        unsealed, STAGE7_PUBLIC_CAMPAIGN_SEAL_V1
    )


# ==========================================================================
# A12 — the B30 typed-frame policy is still the only admission
# ==========================================================================
def test_a12_a_bare_numeric_angle_admits_no_support_orientation() -> None:
    """Control A12: the frame-less angle=0 branch stays gone.

    B15 revoked admission on a support-owned angle of zero, because a numeric
    zero fixes no reference: it says the surface is level relative to something
    the record never names.  B30 replaced it with a typed frame binding — the
    support's tangent *is* the world's x axis — and this pins that a
    restoration of the numeric branch fails.
    """

    payload = {
        "entities": [
            {"entity_id": "table", "primitive": "surface", "inclination_angle": 0.0}
        ],
        "quantities": [{"quantity_id": "theta", "value": 0.0, "unit": "rad"}],
        "reference_frames": [],
    }

    assert stated_support_orientation(payload, support_id="table") is None
    assert payload_states_horizontal_support(payload) is False


def test_a12_the_policy_sites_all_read_one_function() -> None:
    """The four sites B30 unified, by import graph rather than by comment."""

    for relative in (
        "backend/evaluation/phase56_stage7/complete_profile.py",
        "backend/evaluation/phase56_stage7/complete_profile_application.py",
    ):
        imported = _imported_names(REPOSITORY_ROOT / relative)
        assert "stated_support_orientation" in imported, relative


# ==========================================================================
# Deterministic serialization
# ==========================================================================
def test_the_canonical_helper_is_stable_against_key_order_and_ascii() -> None:
    """The one canonicalization, and what it does and does not depend on."""

    assert canonical_json_bytes({"b": 1, "a": 2}) == canonical_json_bytes(
        {"a": 2, "b": 1}
    )
    # Korean is carried as itself, not as escapes: the bytes must depend on the
    # content and not on the writer.
    assert "가".encode("utf-8") in canonical_json_bytes({"k": "가"})
    with pytest.raises(ValueError):
        canonical_json_bytes({"k": float("nan")})


def test_two_attestations_over_the_same_preparation_are_identical() -> None:
    """Determinism, which the byte-identical rebuild gate depends on."""

    first = synthetic_attestation(_contexts())
    second = synthetic_attestation(_contexts())

    assert first == second
    assert first.attestation_digest == second.attestation_digest


def test_the_attestation_carries_no_wall_clock_field() -> None:
    """A timestamp would make every rebuild differ from every other one.

    Checked as the exact field set rather than by hunting for substrings — the
    blunt version fails on `candidate_archive_digest`, which contains "date"
    and is not a date.  Pinning the whole set also means a timestamp added
    later fails here on the day it is added, under a name that says why.
    """

    payload = synthetic_attestation(_contexts()).model_dump(mode="json")

    assert set(payload) == {
        "version",
        "campaign_seal_name",
        "exact_code_head",
        "original_v1_archive_sha256",
        "augmentation_manifest_digest",
        "augmentation_manifest_file_sha256",
        "candidate_archive_digest",
        "candidate_archive_file_sha256",
        "runtime_input_digest",
        "runtime_input_file_sha256",
        "expected_context_count",
        "context_index_set_digest",
        "expected_handle_set_digest",
        "prepared_state_map_digest",
        "refusal_handle_set_digest",
        "prepared_state_counts",
        "prepared_refusal_counts",
        "unresolved_augmentation_count",
        "attestation_digest",
    }


# ==========================================================================
# Phase M single-commit generation publication
# ==========================================================================
#
# The seal is judged over the attestation, the attestation carries each
# artifact's file hash, and a file hash needs bytes on a filesystem.  Phase M
# used to resolve that by writing the candidate archive and the runtime input to
# their final paths first and checking the seal afterwards — so a preparation
# refused for being some other campaign still left two of its three artifacts
# exactly where Phase V, and a hand-run Phase R, look for them.  The first fix
# staged each artifact beside its destination and renamed all three after the
# gates — which kept a *refused* preparation off the final paths, but still
# published a *successful* one through three consecutive renames, and a crash
# between them could mix two preparations at the authoritative paths.  The
# publication is now one immutable generation directory plus a single CURRENT
# pointer replace; these controls are the earlier ones restated against that
# protocol, and `test_phase56_stage7_corpus_v2_publication_transaction.py`
# holds the crash/concurrency attack matrix the flat-path protocol could not
# even express.
#
# The two seal controls below are a matched pair over one synthetic campaign.
# The seal they are judged against is built from that campaign's own honest
# attestation, so the *only* thing that differs between them is the manifest
# pair — which is the shape of this project's live blocker: the population is
# reproducible from the corpus, and the exact manifest hashes are not.
SYNTHETIC_SEAL_NAME = "phase56-stage7-v2-synthetic-campaign-test"


def _prepared_campaign(tmp_path, monkeypatch):
    from evaluation.phase56_stage7.corpus_v2 import prepare_builder

    archive, manifest = _synthetic_campaign(tmp_path, monkeypatch)
    prepared = prepare_builder.build_prepared_campaign(
        corpus_archive=archive, manifest=manifest
    )
    return archive, manifest, prepared


def _honest_attestation(prepared, *, name: str | None):
    return build_prepare_attestation(
        campaign_seal_name=name,
        exact_code_head=SYNTHETIC_CODE_HEAD,
        original_v1_archive_sha256=prepared.original_v1_archive_sha256,
        augmentation_manifest_digest=prepared.augmentation_manifest_digest,
        augmentation_manifest_file_sha256=prepared.augmentation_manifest_file_sha256,
        candidate_archive_digest=prepared.candidate_archive_digest,
        candidate_archive_file_sha256=prepared.candidate_file_sha256,
        runtime_input_digest=prepared.runtime_input.digest,
        runtime_input_file_sha256=prepared.runtime_input_file_sha256,
        contexts=prepared.runtime_input.contexts,
        unresolved_augmentation_count=prepared.unresolved_augmentation_count,
    )


def _seal_from(attestation, **overrides) -> CampaignPopulationSealV1:
    """A seal this preparation satisfies, except where a test says otherwise.

    Derived from the preparation rather than hand-written, so the negative
    control fails on the one field it edited and not on nine others it never
    meant to touch.
    """

    values: dict = {
        "name": SYNTHETIC_SEAL_NAME,
        "original_v1_archive_sha256": attestation.original_v1_archive_sha256,
        "augmentation_manifest_digest": attestation.augmentation_manifest_digest,
        "augmentation_manifest_file_sha256": (
            attestation.augmentation_manifest_file_sha256
        ),
        "expected_context_count": attestation.expected_context_count,
        "context_index_set_digest": attestation.context_index_set_digest,
        "expected_handle_set_digest": attestation.expected_handle_set_digest,
        "prepared_state_map_digest": attestation.prepared_state_map_digest,
        "refusal_handle_set_digest": attestation.refusal_handle_set_digest,
        "prepared_state_counts": tuple(attestation.prepared_state_counts),
        "prepared_refusal_counts": tuple(attestation.prepared_refusal_counts),
    }
    values.update(overrides)
    return CampaignPopulationSealV1(**values)


def _publication_root(tmp_path) -> Path:
    return tmp_path / "publication"


def _run_prepare(tmp_path, monkeypatch, archive, manifest, *, seal=None) -> int:
    import runpy

    argv = [
        str(PREPARE_TOOL),
        "--corpus-archive",
        str(archive),
        "--manifest",
        str(manifest),
        "--publication-root",
        str(_publication_root(tmp_path)),
        "--exact-code-head",
        SYNTHETIC_CODE_HEAD,
    ]
    if seal is not None:
        argv += ["--campaign-seal", seal]
    monkeypatch.setattr(sys, "argv", argv)
    module = runpy.run_path(str(PREPARE_TOOL), run_name="not_main")
    return module["main"]()


def _generation_directories(tmp_path) -> list[Path]:
    generations = _publication_root(tmp_path) / GENERATIONS_DIRECTORY_NAME
    if not generations.exists():
        return []
    return sorted(generations.iterdir())


def _assert_nothing_published(tmp_path) -> None:
    """No pointer, no generation, no staging directory, no ``.partial``.

    The refused run's abort removes the one staging directory it owns, and a
    fixed-name staging file cannot be left behind because the protocol has
    none — each run stages under its own random token.
    """

    root = _publication_root(tmp_path)
    assert not (
        root / CURRENT_POINTER_NAME
    ).exists(), "a refused prepare committed the authority pointer"
    assert (
        _generation_directories(tmp_path) == []
    ), "a refused prepare left a generation or staging directory behind"
    if root.exists():
        assert list(root.rglob("*.partial")) == []


def test_a_failed_campaign_seal_publishes_no_prepare_artifact(
    tmp_path, monkeypatch, capsys
) -> None:
    """The negative control: refused for the manifest, and nothing published.

    The candidate archive and the runtime input are derived, staged and hashed
    before the seal can be judged at all — that ordering is forced, not chosen.
    What the protocol decides is where those bytes are while the judging
    happens: in this run's private staging directory, which no reader
    resolves, and which the refusal removes whole.
    """

    from evaluation.phase56_stage7.corpus_v2 import campaign_seal

    archive, manifest, prepared = _prepared_campaign(tmp_path, monkeypatch)
    seal = _seal_from(
        _honest_attestation(prepared, name=SYNTHETIC_SEAL_NAME),
        augmentation_manifest_digest="9" * 64,
        augmentation_manifest_file_sha256="8" * 64,
    )
    monkeypatch.setitem(campaign_seal.CAMPAIGN_SEALS, SYNTHETIC_SEAL_NAME, seal)

    status = _run_prepare(
        tmp_path, monkeypatch, archive, manifest, seal=SYNTHETIC_SEAL_NAME
    )
    captured = capsys.readouterr()

    assert status == 2, captured.out
    # The two gates the test edited, and only those.
    assert CampaignSealFailure.manifest_digest_mismatch.value in captured.err
    assert CampaignSealFailure.manifest_file_sha_mismatch.value in captured.err
    assert CampaignSealFailure.context_count_mismatch.value not in captured.err
    assert CampaignSealFailure.prepared_state_map_mismatch.value not in captured.err
    assert "STAGE7_V2_PREPARE_ACCEPTANCE=PASS" not in captured.out

    _assert_nothing_published(tmp_path)


def test_a_failed_campaign_seal_leaves_an_earlier_preparation_intact(
    tmp_path, monkeypatch, capsys
) -> None:
    """A refused run must not disturb what an honest one published.

    The refused run's staging lives one directory over from the committed
    generation, so "clean up after yourself" and "delete the generation
    somebody is about to score" are one path apart.  This pins which of the
    two happens: after the refusal, the pointer bytes, the generation's three
    artifacts and the generation *set* are all exactly as the honest run left
    them.
    """

    from evaluation.phase56_stage7.corpus_v2 import campaign_seal

    archive, manifest, prepared = _prepared_campaign(tmp_path, monkeypatch)
    honest_seal = _seal_from(_honest_attestation(prepared, name=SYNTHETIC_SEAL_NAME))
    monkeypatch.setitem(
        campaign_seal.CAMPAIGN_SEALS, SYNTHETIC_SEAL_NAME, honest_seal
    )
    assert (
        _run_prepare(tmp_path, monkeypatch, archive, manifest, seal=SYNTHETIC_SEAL_NAME)
        == 0
    )
    capsys.readouterr()

    root = _publication_root(tmp_path)
    pointer_before = (root / CURRENT_POINTER_NAME).read_bytes()
    published = resolve_published_generation(root)
    artifacts_before = {
        path: path.read_bytes()
        for path in (
            published.candidate_archive,
            published.runtime_input,
            published.prepare_attestation,
        )
    }
    generations_before = _generation_directories(tmp_path)

    refusing_seal = _seal_from(
        _honest_attestation(prepared, name=SYNTHETIC_SEAL_NAME),
        augmentation_manifest_digest="9" * 64,
    )
    monkeypatch.setitem(
        campaign_seal.CAMPAIGN_SEALS, SYNTHETIC_SEAL_NAME, refusing_seal
    )

    status = _run_prepare(
        tmp_path, monkeypatch, archive, manifest, seal=SYNTHETIC_SEAL_NAME
    )
    capsys.readouterr()

    assert status == 2
    assert (root / CURRENT_POINTER_NAME).read_bytes() == pointer_before
    for path, body in artifacts_before.items():
        assert path.read_bytes() == body
    assert _generation_directories(tmp_path) == generations_before
    assert list(root.rglob("*.partial")) == []
    assert resolve_published_generation(root).generation_id == (
        published.generation_id
    )


def test_a_sealed_preparation_publishes_all_three_artifacts(
    tmp_path, monkeypatch, capsys
) -> None:
    """The positive control, differing from the negative one by the manifest.

    Same corpus, same seal, same command — only the two manifest hashes agree.
    All three artifacts appear, and each one's hash is the hash the attestation
    states, recomputed from the published bytes rather than from the body the
    command intended to write.
    """

    from evaluation.phase56_stage7.corpus_v2 import campaign_seal

    archive, manifest, prepared = _prepared_campaign(tmp_path, monkeypatch)
    seal = _seal_from(_honest_attestation(prepared, name=SYNTHETIC_SEAL_NAME))
    monkeypatch.setitem(campaign_seal.CAMPAIGN_SEALS, SYNTHETIC_SEAL_NAME, seal)

    status = _run_prepare(
        tmp_path, monkeypatch, archive, manifest, seal=SYNTHETIC_SEAL_NAME
    )
    captured = capsys.readouterr()

    assert status == 0, captured.err
    assert "STAGE7_V2_PREPARE_ACCEPTANCE=PASS" in captured.out

    # The publication resolves: one pointer, one complete generation, and the
    # machine-readable id the orchestrator pins the rest of the pipeline to.
    root = _publication_root(tmp_path)
    published = resolve_published_generation(root)
    assert (
        f"STAGE7_V2_PREPARE_PUBLICATION_ID={published.generation_id}"
        in captured.out
    )
    assert [path.name for path in _generation_directories(tmp_path)] == [
        published.generation_id
    ]
    assert list(root.rglob("*.partial")) == []

    # Every check below re-reads the published bytes.  An artifact that is on
    # disk but is not the one the attestation describes is exactly the failure
    # a single-commit publication is supposed to make impossible.
    bundle_body = published.runtime_input.read_text(encoding="utf-8")
    attestation = load_prepare_attestation(
        published.prepare_attestation.read_text(encoding="utf-8")
    )
    assert attestation.attestation_digest == published.generation_id
    assert attestation.campaign_seal_name == SYNTHETIC_SEAL_NAME
    assert campaign_seal_failures(attestation, seal) == ()

    assert attestation.candidate_archive_file_sha256 == file_sha256(
        published.candidate_archive.read_text(encoding="utf-8")
    )
    assert attestation.runtime_input_file_sha256 == file_sha256(bundle_body)
    assert attestation.candidate_archive_digest == prepared.candidate_archive_digest
    assert attestation.runtime_input_digest == load_runtime_input(bundle_body).digest
    assert (
        runtime_input_binding_failures(
            attestation,
            load_runtime_input(bundle_body),
            runtime_input_file_sha256=file_sha256(bundle_body),
            exact_code_head=SYNTHETIC_CODE_HEAD,
        )
        == ()
    )


def test_a_refused_preparation_stops_the_pipeline_before_phase_v(tmp_path) -> None:
    """Why "nothing published" is also "no later phase ran".

    The orchestrator's guards are read off the AST rather than asserted in
    prose.  Phase M is invoked through `_run_prepare`, which returns its exit
    status *and* the publication id it printed; the next statement returns a
    non-zero status, and the one after that refuses to continue when the id is
    missing — so on a refused preparation nothing downstream is reachable, and
    on an accepted one nothing downstream can run unpinned.  Every later phase
    receives the captured id through one `pinned` argument list, which is how
    a pointer moved mid-pipeline cannot redirect Phase V, R or G.
    """

    tree = ast.parse((TOOLS / "run_phase56_stage7_v2_shadow.py").read_text("utf-8"))
    main = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    def _calls(statement, name):
        return [
            node
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]

    phases = [
        (index, statement)
        for index, statement in enumerate(main.body)
        if _calls(statement, "_run") or _calls(statement, "_run_prepare")
    ]
    assert phases, "no phase invocation found in the orchestrator"

    # Phase M is first, invoked through the capturing runner exactly once in
    # the whole function, and its status and publication id are bound together.
    prepare_index, prepare_statement = phases[0]
    prepare_calls = _calls(prepare_statement, "_run_prepare")
    assert len(prepare_calls) == 1
    assert ast.literal_eval(prepare_calls[0].args[0]) == "PHASE_M_PREPARE"
    assert sum(len(_calls(node, "_run_prepare")) for node in main.body) == 1
    assert isinstance(prepare_statement, ast.Assign)
    (target,) = prepare_statement.targets
    assert isinstance(target, ast.Tuple)
    assert [name.id for name in target.elts] == ["status", "publication_id"]

    status_guard = main.body[prepare_index + 1]
    assert isinstance(status_guard, ast.If)
    assert isinstance(status_guard.test, ast.Name)
    assert status_guard.test.id == "status"
    assert len(status_guard.body) == 1
    assert isinstance(status_guard.body[0], ast.Return)
    assert isinstance(status_guard.body[0].value, ast.Name)
    assert status_guard.body[0].value.id == "status"

    pin_guard = main.body[prepare_index + 2]
    assert isinstance(pin_guard, ast.If)
    assert isinstance(pin_guard.test, ast.Compare)
    assert isinstance(pin_guard.test.left, ast.Name)
    assert pin_guard.test.left.id == "publication_id"
    assert isinstance(pin_guard.test.ops[0], ast.Is)
    assert isinstance(pin_guard.body[-1], ast.Return)

    # The pin is spelled once, carries the captured id, and every later phase
    # sits after both guards.
    pinned = next(
        statement
        for statement in main.body
        if isinstance(statement, ast.Assign)
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "pinned"
    )
    pinned_names = {
        node.id for node in ast.walk(pinned.value) if isinstance(node, ast.Name)
    }
    pinned_literals = {
        node.value
        for node in ast.walk(pinned.value)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "publication_id" in pinned_names
    assert "--publication-id" in pinned_literals
    assert "--publication-root" in pinned_literals
    assert main.body.index(pinned) > prepare_index + 2
    assert all(index > main.body.index(pinned) for index, _ in phases[1:])
    for _, statement in phases[1:]:
        (call,) = _calls(statement, "_run")
        command_name = call.args[1]
        assert isinstance(command_name, ast.Name)
        construction = next(
            candidate
            for candidate in main.body
            if isinstance(candidate, ast.Assign)
            and isinstance(candidate.targets[0], ast.Name)
            and candidate.targets[0].id == command_name.id
        )
        starred = {
            node.value.id
            for node in ast.walk(construction.value)
            if isinstance(node, ast.Starred) and isinstance(node.value, ast.Name)
        }
        assert "pinned" in starred, command_name.id


# ==========================================================================
# Exit-code synchronization
# ==========================================================================
def test_every_new_command_exits_two_on_its_own_failure() -> None:
    """The shape this forbids is `print("...FAIL...")` then `return 0`."""

    verify = VERIFY_TOOL.read_text("utf-8")
    assert "VERIFY_FAILURE_EXIT = 2" in verify
    assert "return 0 if not failures else VERIFY_FAILURE_EXIT" in verify

    prepare = PREPARE_TOOL.read_text("utf-8")
    assert "PREPARE_FAILURE_EXIT = 2" in prepare

    runtime = RUNTIME_TOOL.read_text("utf-8")
    assert "return 0 if not failures else RUNTIME_FAILURE_EXIT" in runtime


def _imported_names(path: Path) -> set[str]:
    """Every name a module imports, from the AST.

    Parsed rather than grepped: a docstring that mentions `gold_scoring` — and
    the ones in this package do, at length — must not be able to fail an
    import-isolation check, and a substring probe cannot tell the two apart.
    """

    tree = ast.parse(path.read_text("utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            names.update((node.module or "").split("."))
            names.update(alias.name for alias in node.names)
    return names
