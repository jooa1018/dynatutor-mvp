"""A read-only adversary against the B28A attestation and population seal.

This command tries the attacks rather than reading the code and being
satisfied.  Where an attack can be executed in-process against the real types
it is executed; where it is a property of the import graph it is checked by
parsing rather than by grepping, because every module in this package discusses
`gold_scoring` at length in its docstring and a substring probe cannot tell a
sentence from an import.

It reads.  It does not write to the repository, dispatch a workflow, push,
mutate a pull request, or touch a secret — a checker that could change what it
is checking is not a check.  Nothing here opens the public corpus either, so it
runs anywhere.

Exit 0 when no blocking finding survives, 1 otherwise.  Non-blocking findings
are printed with their reasoning and do not fail the run.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.corpus_v2.campaign_seal import (  # noqa: E402
    STAGE7_PUBLIC_CAMPAIGN_SEAL_V1,
    CampaignSealFailure,
    campaign_seal_failures,
)
from evaluation.phase56_stage7.corpus_v2.canonical import (  # noqa: E402
    canonical_digest,
    file_sha256,
)
from evaluation.phase56_stage7.corpus_v2.prepare_attestation import (  # noqa: E402
    PrepareAttestationRefused,
    PrepareBindingFailure,
    build_prepare_attestation,
    load_prepare_attestation,
    prepared_state_counts,
    prepared_state_map_digest,
    refusal_handle_set_digest,
    runtime_input_binding_failures,
)
from evaluation.phase56_stage7.corpus_v2.reporting import (  # noqa: E402
    OFFICIAL_SCORE_CLASS,
    SCORED_SCORE_CLASS,
    assert_scores_are_separated,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (  # noqa: E402
    PREPARABLE_STATES,
    RuntimeContextInputV2,
    RuntimeInputRefused,
    ShadowRuntimeInputV2,
    load_runtime_input,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (  # noqa: E402
    LedgerState,
    RefusalCode,
    ShadowLedgerEntryV2,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (  # noqa: E402
    RuntimeSnapshotRefused,
    ShadowRuntimeRecordV2,
    freeze_runtime_snapshot,
    load_full_runtime_snapshot,
    prepare_binding_from_attestation,
    redact_runtime_snapshot,
    scoring_handle,
)
from evaluation.phase56_stage7.typed_support_frames import (  # noqa: E402
    payload_states_horizontal_support,
    stated_support_orientation,
)

TOOLS = REPOSITORY_ROOT / "backend" / "tools"
CORPUS_V2 = REPOSITORY_ROOT / "backend" / "evaluation" / "phase56_stage7" / "corpus_v2"

ARCHIVE = "a" * 64
MANIFEST = "b" * 64
CANDIDATE = "c" * 64
CODE_HEAD = "deadbeef"

CHECKER_FAILURE_EXIT = 1


@dataclass(frozen=True)
class Finding:
    name: str
    blocking: bool
    detail: str


def _handle(index: int) -> str:
    return scoring_handle(original_v1_archive_sha256=ARCHIVE, context_index=index)


def _context(index: int, *, refused: bool):
    if refused:
        return RuntimeContextInputV2(
            scoring_handle=_handle(index),
            context_index=index,
            prepared_state=LedgerState.projection_refused,
            refusal_code=RefusalCode.projection_refused_no_draft,
        )
    return RuntimeContextInputV2(
        scoring_handle=_handle(index),
        context_index=index,
        prepared_state=LedgerState.runtime_completed,
        draft_payload={"probe": index},
    )


def _campaign(completed: int = 6, refused: int = 3):
    return tuple(
        _context(index, refused=index >= completed)
        for index in range(completed + refused)
    )


def _bundle(contexts):
    return ShadowRuntimeInputV2(
        original_v1_archive_sha256=ARCHIVE,
        augmentation_manifest_sha256=MANIFEST,
        candidate_archive_sha256=CANDIDATE,
        contexts=tuple(contexts),
    )


def _attest(contexts, *, seal=None, code_head=CODE_HEAD, bundle=None):
    target = bundle if bundle is not None else _bundle(contexts)
    return build_prepare_attestation(
        campaign_seal_name=seal,
        exact_code_head=code_head,
        original_v1_archive_sha256=ARCHIVE,
        augmentation_manifest_digest=MANIFEST,
        augmentation_manifest_file_sha256="f" * 64,
        candidate_archive_digest=CANDIDATE,
        candidate_archive_file_sha256="0" * 64,
        runtime_input_digest=target.digest,
        runtime_input_file_sha256="e" * 64,
        contexts=contexts,
        unresolved_augmentation_count=target.unresolved_augmentation_count,
    )


def _imported_names(path: Path) -> set[str]:
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


# ==========================================================================
# The attacks
# ==========================================================================
def check_all_refusal_laundering() -> list[Finding]:
    """Every measurable context relabelled as an anticipated refusal."""

    honest = _campaign()
    laundered = tuple(_context(item.context_index, refused=True) for item in honest)
    failures = runtime_input_binding_failures(
        _attest(honest),
        _bundle(laundered),
        runtime_input_file_sha256="e" * 64,
    )
    if PrepareBindingFailure.prepared_state_map_mismatch.value not in failures:
        return [
            Finding(
                "all_refusal_laundering_admitted",
                True,
                "a fully laundered bundle did not fail the prepared-state map",
            )
        ]
    return []


def check_single_refusal_laundering() -> list[Finding]:
    honest = _campaign()
    laundered = (
        _context(0, refused=True),
        *honest[1:],
    )
    failures = runtime_input_binding_failures(
        _attest(honest), _bundle(laundered), runtime_input_file_sha256="e" * 64
    )
    if PrepareBindingFailure.prepared_state_map_mismatch.value not in failures:
        return [
            Finding(
                "single_refusal_laundering_admitted",
                True,
                "one laundered context did not fail the prepared-state map",
            )
        ]
    return []


def check_joint_forgery_needs_an_outside_reference() -> list[Finding]:
    """The pair agrees with itself; only a rebuild disagrees.

    Two findings would be wrong here.  It is *expected* that the binding check
    passes — that is the boundary of an artifact-to-artifact comparison.  What
    must hold is that the rebuild's projections differ, and that Phase V is the
    thing that computes them.
    """

    findings: list[Finding] = []
    honest = _campaign()
    laundered = tuple(_context(item.context_index, refused=True) for item in honest)
    forged_bundle = _bundle(laundered)
    forged = build_prepare_attestation(
        campaign_seal_name=None,
        exact_code_head=CODE_HEAD,
        original_v1_archive_sha256=ARCHIVE,
        augmentation_manifest_digest=MANIFEST,
        augmentation_manifest_file_sha256="f" * 64,
        candidate_archive_digest=CANDIDATE,
        candidate_archive_file_sha256="0" * 64,
        runtime_input_digest=forged_bundle.digest,
        runtime_input_file_sha256="e" * 64,
        contexts=laundered,
        unresolved_augmentation_count=forged_bundle.unresolved_augmentation_count,
    )
    if (
        runtime_input_binding_failures(
            forged, forged_bundle, runtime_input_file_sha256="e" * 64
        )
        != ()
    ):
        findings.append(
            Finding(
                "joint_forgery_model_unsound",
                False,
                "the forged pair did not agree with itself; the checker's own "
                "model of the attack may be stale",
            )
        )
    if prepared_state_map_digest(laundered) == prepared_state_map_digest(honest):
        findings.append(
            Finding(
                "joint_forgery_invisible_to_rebuild",
                True,
                "a rebuild of the honest preparation cannot distinguish the "
                "forged population",
            )
        )
    source = (TOOLS / "run_phase56_stage7_v2_shadow_verify_prepare.py").read_text(
        "utf-8"
    )
    if "build_prepared_campaign" not in source:
        findings.append(
            Finding(
                "verifier_does_not_rebuild",
                True,
                "Phase V does not rebuild the preparation from the corpus",
            )
        )
    return findings


def check_refusal_handle_swap_at_equal_counts() -> list[Finding]:
    honest = _campaign()
    swapped = tuple(
        _context(item.context_index, refused=item.context_index in {0, 1, 2})
        for item in honest
    )
    if prepared_state_counts(swapped) != prepared_state_counts(honest):
        return [
            Finding(
                "handle_swap_probe_invalid",
                False,
                "the checker's swap changed the counts, so it does not "
                "exercise the identity path",
            )
        ]
    failures = runtime_input_binding_failures(
        _attest(honest), _bundle(swapped), runtime_input_file_sha256="e" * 64
    )
    if PrepareBindingFailure.refusal_handle_set_mismatch.value not in failures:
        return [
            Finding(
                "refusal_identity_swap_admitted",
                True,
                "swapping which contexts were refused, at equal counts, was "
                "not detected",
            )
        ]
    return []


def check_nested_gold_key() -> list[Finding]:
    payload = {
        "original_v1_archive_sha256": ARCHIVE,
        "augmentation_manifest_sha256": MANIFEST,
        "candidate_archive_sha256": CANDIDATE,
        "contexts": [
            {
                "scoring_handle": _handle(0),
                "context_index": 0,
                "prepared_state": "runtime_completed",
                "draft_payload": {"a": {"b": {"expected_answer": 1}}},
            }
        ],
    }
    try:
        load_runtime_input(json.dumps(payload))
    except RuntimeInputRefused:
        return []
    return [
        Finding(
            "nested_gold_key_admitted",
            True,
            "a gold member nested inside draft_payload reached the runtime",
        )
    ]


def check_cross_field_validation() -> list[Finding]:
    """Both laundered spellings, and the states no preparation can produce."""

    findings: list[Finding] = []
    attempts = [
        (
            "runtime_completed_without_draft",
            dict(prepared_state=LedgerState.runtime_completed),
        ),
        (
            "projection_refused_with_draft",
            dict(
                prepared_state=LedgerState.projection_refused,
                refusal_code=RefusalCode.projection_refused_no_draft,
                draft_payload={"x": 1},
            ),
        ),
        (
            "projection_refused_with_runtime_authority",
            dict(
                prepared_state=LedgerState.projection_refused,
                refusal_code=RefusalCode.projection_refused_no_draft,
                problem_text="carried over from a projection that happened",
            ),
        ),
        (
            "migration_refused_admitted",
            dict(
                prepared_state=LedgerState.migration_refused,
                refusal_code=RefusalCode.migration_refused_unresolved_entry,
            ),
        ),
        (
            "runtime_failed_admitted",
            dict(
                prepared_state=LedgerState.runtime_failed,
                refusal_code=RefusalCode.runtime_failed_unexpected_exception,
            ),
        ),
    ]
    for name, kwargs in attempts:
        try:
            RuntimeContextInputV2(
                scoring_handle=_handle(0), context_index=0, **kwargs
            )
        except Exception:
            continue
        findings.append(
            Finding(name, True, f"the runtime input schema admitted {name}")
        )
    if PREPARABLE_STATES != {
        LedgerState.runtime_completed,
        LedgerState.projection_refused,
    }:
        findings.append(
            Finding(
                "preparable_states_widened",
                True,
                f"preparable states are {sorted(s.value for s in PREPARABLE_STATES)}",
            )
        )
    return findings


def check_runtime_input_mutation() -> list[Finding]:
    honest = _campaign()
    failures = runtime_input_binding_failures(
        _attest(honest),
        _bundle(honest),
        runtime_input_file_sha256="1" * 64,
    )
    if PrepareBindingFailure.runtime_input_file_sha_mismatch.value not in failures:
        return [
            Finding(
                "runtime_input_file_hash_unchecked",
                True,
                "a runtime input whose bytes changed was not detected",
            )
        ]
    return []


def check_attestation_mutation() -> list[Finding]:
    payload = _attest(_campaign()).model_dump(mode="json")
    payload["prepared_state_counts"] = [["runtime_completed", 999]]
    try:
        load_prepare_attestation(json.dumps(payload))
    except PrepareAttestationRefused:
        return []
    return [
        Finding(
            "attestation_mutation_admitted",
            True,
            "an edited attestation passed its own integrity check",
        )
    ]


def _snapshot():
    contexts = _campaign()
    attestation = _attest(contexts)
    ledger = [
        ShadowLedgerEntryV2(
            scoring_handle=item.scoring_handle,
            state=item.prepared_state,
            refusal_code=item.refusal_code,
        )
        for item in contexts
    ]
    records = [
        ShadowRuntimeRecordV2(
            scoring_handle=item.scoring_handle,
            cohort_digest="d" * 64,
            baseline_rung="law_emitted_graph_underdetermined",
            shadow_rung="solved_and_verified",
            shadow_solved=True,
            answer_value_si=1.0,
            answer_unit="m/s",
        )
        for item in contexts
        if item.prepared_state is LedgerState.runtime_completed
    ]
    return (
        freeze_runtime_snapshot(
            records,
            ledger=ledger,
            original_v1_archive_sha256=ARCHIVE,
            augmentation_manifest_sha256=MANIFEST,
            candidate_archive_sha256=CANDIDATE,
            prepare_binding=prepare_binding_from_attestation(attestation),
            exact_code_head=CODE_HEAD,
        ),
        attestation,
    )


def check_snapshot_binding_mutation() -> list[Finding]:
    findings: list[Finding] = []
    snapshot, _ = _snapshot()
    payload = json.loads(json.dumps(snapshot.model_dump(mode="json")))
    payload["prepare_binding"]["prepare_attestation_digest"] = "9" * 64
    try:
        load_full_runtime_snapshot(json.dumps(payload))
        findings.append(
            Finding(
                "snapshot_binding_mutation_admitted",
                True,
                "a snapshot whose prepare binding was edited still loaded",
            )
        )
    except RuntimeSnapshotRefused:
        pass

    stripped = json.loads(json.dumps(snapshot.model_dump(mode="json")))
    stripped.pop("prepare_binding")
    try:
        load_full_runtime_snapshot(json.dumps(stripped))
        findings.append(
            Finding(
                "snapshot_without_binding_admitted",
                True,
                "a snapshot with no prepare binding loaded, so the binding is "
                "effectively optional",
            )
        )
    except RuntimeSnapshotRefused:
        pass
    return findings


def check_exact_head_mismatch() -> list[Finding]:
    honest = _campaign()
    failures = runtime_input_binding_failures(
        _attest(honest, code_head="cafebabe"),
        _bundle(honest),
        runtime_input_file_sha256="e" * 64,
        exact_code_head=CODE_HEAD,
    )
    if PrepareBindingFailure.exact_code_head_mismatch.value not in failures:
        return [
            Finding(
                "exact_code_head_unchecked",
                True,
                "an attestation naming a different commit was admitted",
            )
        ]
    return []


def check_empty_record_measurement() -> list[Finding]:
    """A hundred allowed refusals and no records must not be this campaign."""

    laundered = tuple(_context(index, refused=True) for index in range(100))
    attestation = build_prepare_attestation(
        campaign_seal_name=STAGE7_PUBLIC_CAMPAIGN_SEAL_V1.name,
        exact_code_head=CODE_HEAD,
        original_v1_archive_sha256=(
            STAGE7_PUBLIC_CAMPAIGN_SEAL_V1.original_v1_archive_sha256
        ),
        augmentation_manifest_digest=(
            STAGE7_PUBLIC_CAMPAIGN_SEAL_V1.augmentation_manifest_digest
        ),
        augmentation_manifest_file_sha256=(
            STAGE7_PUBLIC_CAMPAIGN_SEAL_V1.augmentation_manifest_file_sha256
        ),
        candidate_archive_digest=CANDIDATE,
        candidate_archive_file_sha256="0" * 64,
        runtime_input_digest="d" * 64,
        runtime_input_file_sha256="e" * 64,
        contexts=laundered,
    )
    failures = campaign_seal_failures(attestation, STAGE7_PUBLIC_CAMPAIGN_SEAL_V1)
    if CampaignSealFailure.state_counts_mismatch.value not in failures:
        return [
            Finding(
                "empty_measurement_passes_seal",
                True,
                "a zero-record, all-refused population satisfied the campaign seal",
            )
        ]
    return []


def check_handle_completeness_still_holds() -> list[Finding]:
    """The older ledger controls, re-run: nothing was traded away for the new ones."""

    findings: list[Finding] = []
    snapshot, _ = _snapshot()

    missing = json.loads(json.dumps(snapshot.model_dump(mode="json")))
    missing["records"] = missing["records"][:-1]
    try:
        load_full_runtime_snapshot(json.dumps(missing))
        findings.append(
            Finding(
                "record_removal_admitted",
                True,
                "a snapshot missing a record still loaded",
            )
        )
    except RuntimeSnapshotRefused:
        pass

    duplicate = _campaign()
    try:
        load_runtime_input(
            json.dumps(
                {
                    "original_v1_archive_sha256": ARCHIVE,
                    "augmentation_manifest_sha256": MANIFEST,
                    "candidate_archive_sha256": CANDIDATE,
                    "contexts": [
                        duplicate[0].model_dump(mode="json"),
                        duplicate[0].model_dump(mode="json"),
                    ],
                }
            )
        )
        findings.append(
            Finding(
                "duplicate_handle_admitted",
                True,
                "two contexts sharing one scoring handle were admitted",
            )
        )
    except RuntimeInputRefused:
        pass
    return findings


def check_score_class_separation() -> list[Finding]:
    findings: list[Finding] = []
    shadow = {
        "score_class": SCORED_SCORE_CLASS,
        "is_official_score": False,
        "newly_solved_correct": 9,
    }
    try:
        assert_scores_are_separated({"observed_public_score": "41/81"}, shadow)
    except ValueError as exc:
        findings.append(
            Finding("score_separation_broken", True, f"honest pair refused: {exc}")
        )
    for name, official, mixed in (
        (
            "official_field_in_shadow_report",
            {"observed_public_score": "41/81"},
            {**shadow, "observed_public_score": "50/81"},
        ),
        (
            "shadow_field_in_official_report",
            {"observed_public_score": "41/81", "newly_solved_correct": 9},
            shadow,
        ),
        (
            "shadow_report_claims_official",
            {"observed_public_score": "41/81"},
            {**shadow, "is_official_score": True},
        ),
    ):
        try:
            assert_scores_are_separated(official, mixed)
        except ValueError:
            continue
        findings.append(
            Finding(name, True, "the two score classes could be merged")
        )
    if OFFICIAL_SCORE_CLASS == SCORED_SCORE_CLASS:
        findings.append(
            Finding(
                "score_classes_identical",
                True,
                "the official and shadow classes are the same string",
            )
        )
    return findings


def check_no_summed_official_and_shadow() -> list[Finding]:
    """41 and 9 must not be addable: there is no field to add them into."""

    from evaluation.phase56_stage7.corpus_v2.reporting import ShadowScorecardV2

    official_names = {
        "observed_public_score",
        "supported_correct",
        "authority_accepted_score",
        "lane_b",
    }
    present = official_names & set(ShadowScorecardV2.model_fields)
    if present:
        return [
            Finding(
                "shadow_scorecard_has_official_field",
                True,
                f"a shadow number could be written into {sorted(present)}",
            )
        ]
    return []


def check_import_isolation() -> list[Finding]:
    findings: list[Finding] = []
    matrix = {
        "run_phase56_stage7_v2_shadow_runtime.py": (
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
        ),
        "run_phase56_stage7_v2_shadow_score.py": (
            "run_lane_b_case",
            "run_shadow_context",
            "project_case_to_draft",
            "project_augmentation",
            "MechanicsProblemDraftV1",
            "shadow_runner",
            "projection",
            "lane_b_runner",
            "lane_b_draft_projection",
            "prepare_builder",
            "complete_profile",
        ),
        "run_phase56_stage7_v2_shadow_verify_prepare.py": (
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
        ),
    }
    for name, forbidden in matrix.items():
        imported = _imported_names(TOOLS / name)
        for item in forbidden:
            if item in imported:
                findings.append(
                    Finding(
                        f"import_isolation_{name}_{item}",
                        True,
                        f"{name} imports {item}",
                    )
                )
    return findings


def check_thresholds_not_softened() -> list[Finding]:
    """Every acceptance path still exits 2, and the failure lists still exist."""

    findings: list[Finding] = []
    expectations = {
        "run_phase56_stage7_v2_shadow_prepare.py": ("PREPARE_FAILURE_EXIT = 2",),
        "run_phase56_stage7_v2_shadow_verify_prepare.py": (
            "VERIFY_FAILURE_EXIT = 2",
            "return 0 if not failures else VERIFY_FAILURE_EXIT",
        ),
        "run_phase56_stage7_v2_shadow_runtime.py": (
            "RUNTIME_FAILURE_EXIT = 2",
            "return 0 if not failures else RUNTIME_FAILURE_EXIT",
        ),
        "run_phase56_stage7_v2_shadow_score.py": (
            "SCORE_FAILURE_EXIT = 2",
            "return 0 if not failures else SCORE_FAILURE_EXIT",
        ),
    }
    for name, needles in expectations.items():
        source = (TOOLS / name).read_text("utf-8")
        for needle in needles:
            if needle not in source:
                findings.append(
                    Finding(
                        f"exit_contract_{name}",
                        True,
                        f"{name} no longer contains: {needle}",
                    )
                )

    from evaluation.phase56_stage7.corpus_v2.reporting import ShadowScorecardV2

    card = ShadowScorecardV2(
        candidate_archive_sha256=CANDIDATE,
        augmentation_manifest_sha256=MANIFEST,
        original_v1_archive_sha256=ARCHIVE,
        runtime_snapshot_sha256="d" * 64,
        newly_solved_wrong=1,
        newly_solved_unscored=1,
        all_shadow_wrong=1,
        forbidden_class_solve=1,
        regressed=1,
        query_binding_mismatch=1,
    )
    for expected in (
        "newly_solved_wrong",
        "newly_solved_unscored",
        "all_shadow_wrong",
        "forbidden_class_solve",
        "regressed",
        "query_binding_mismatch",
    ):
        if expected not in card.acceptance_failures:
            findings.append(
                Finding(
                    f"acceptance_gate_removed_{expected}",
                    True,
                    f"{expected} no longer fails acceptance",
                )
            )
    return findings


def check_campaign_seal_cannot_be_bypassed() -> list[Finding]:
    findings: list[Finding] = []
    unsealed = _attest(_campaign(), seal=None)
    if CampaignSealFailure.not_sealed.value not in campaign_seal_failures(
        unsealed, STAGE7_PUBLIC_CAMPAIGN_SEAL_V1
    ):
        findings.append(
            Finding(
                "unsealed_attestation_passes_seal",
                True,
                "an attestation naming no campaign satisfied the seal",
            )
        )
    # And each phase must consult the seal it finds on the attestation rather
    # than only one it was handed on the command line.
    for name in (
        "run_phase56_stage7_v2_shadow_runtime.py",
        "run_phase56_stage7_v2_shadow_score.py",
        "run_phase56_stage7_v2_shadow_verify_prepare.py",
    ):
        source = (TOOLS / name).read_text("utf-8")
        if "campaign_seal_failures" not in source:
            findings.append(
                Finding(
                    f"seal_not_enforced_in_{name}",
                    True,
                    f"{name} never calls campaign_seal_failures",
                )
            )
    return findings


def check_corpus_and_manifest_substitution() -> list[Finding]:
    findings: list[Finding] = []
    for field, gate in (
        ("original_v1_archive_sha256", CampaignSealFailure.corpus_archive_mismatch),
        (
            "augmentation_manifest_digest",
            CampaignSealFailure.manifest_digest_mismatch,
        ),
        (
            "augmentation_manifest_file_sha256",
            CampaignSealFailure.manifest_file_sha_mismatch,
        ),
    ):
        seal = STAGE7_PUBLIC_CAMPAIGN_SEAL_V1
        substituted = build_prepare_attestation(
            campaign_seal_name=seal.name,
            exact_code_head=CODE_HEAD,
            original_v1_archive_sha256=seal.original_v1_archive_sha256,
            augmentation_manifest_digest=seal.augmentation_manifest_digest,
            augmentation_manifest_file_sha256=(
                seal.augmentation_manifest_file_sha256
            ),
            candidate_archive_digest=CANDIDATE,
            candidate_archive_file_sha256="0" * 64,
            runtime_input_digest="d" * 64,
            runtime_input_file_sha256="e" * 64,
            contexts=(),
        ).model_copy(update={field: "8" * 64})
        if gate.value not in campaign_seal_failures(substituted, seal):
            findings.append(
                Finding(
                    f"substitution_undetected_{field}",
                    True,
                    f"substituting {field} did not fail the seal",
                )
            )
    return findings


def check_b30_angle_only_policy_stays_revoked() -> list[Finding]:
    payload = {
        "entities": [
            {"entity_id": "table", "primitive": "surface", "inclination_angle": 0.0}
        ],
        "quantities": [{"quantity_id": "theta", "value": 0.0, "unit": "rad"}],
        "reference_frames": [],
    }
    findings: list[Finding] = []
    if stated_support_orientation(payload, support_id="table") is not None:
        findings.append(
            Finding(
                "b30_angle_only_admission_restored",
                True,
                "a bare numeric angle again states a support orientation",
            )
        )
    if payload_states_horizontal_support(payload):
        findings.append(
            Finding(
                "b30_planner_angle_only_admission_restored",
                True,
                "the planner admits a frame-less payload",
            )
        )
    return findings


def check_redacted_view_publishes_no_handle_material() -> list[Finding]:
    snapshot, attestation = _snapshot()
    view = redact_runtime_snapshot(snapshot)
    body = json.dumps(view.model_dump(mode="json"), ensure_ascii=False)
    findings: list[Finding] = []
    if attestation.refusal_handle_set_digest in body:
        findings.append(
            Finding(
                "redacted_view_publishes_refusal_handle_digest",
                True,
                "the refusal handle-set digest is brute-forceable back to "
                "which corpus positions were refused",
            )
        )
    for index in range(9):
        if _handle(index) in body:
            findings.append(
                Finding(
                    "redacted_view_publishes_a_handle",
                    True,
                    "a scoring handle reached the publishable view",
                )
            )
            break
    return findings


def check_canonical_digests_are_not_reprs() -> list[Finding]:
    """No digest may be computed over `repr`, anywhere in the package."""

    findings: list[Finding] = []
    for path in sorted(CORPUS_V2.glob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "repr"
            ):
                findings.append(
                    Finding(
                        f"repr_digest_material_{path.name}",
                        True,
                        f"{path.name}:{node.lineno} builds digest material with repr()",
                    )
                )
    probe = {"b": 1, "a": [2, 3]}
    if canonical_digest(probe) != canonical_digest({"a": [2, 3], "b": 1}):
        findings.append(
            Finding(
                "canonicalization_order_dependent",
                True,
                "the shared canonical digest depends on key order",
            )
        )
    return findings


def check_direct_phase_invocation_requires_an_attestation() -> list[Finding]:
    """Neither Phase R nor Phase G has a path that runs without one."""

    findings: list[Finding] = []
    for name in (
        "run_phase56_stage7_v2_shadow_runtime.py",
        "run_phase56_stage7_v2_shadow_score.py",
    ):
        tree = ast.parse((TOOLS / name).read_text("utf-8"))
        required = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            if node.args[0].value != "--prepare-attestation":
                continue
            required = any(
                keyword.arg == "required"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
        if not required:
            findings.append(
                Finding(
                    f"attestation_optional_in_{name}",
                    True,
                    f"{name} does not require --prepare-attestation",
                )
            )
    return findings


def check_docs_agree_with_the_machine_artifacts() -> list[Finding]:
    """Whatever the documentation quotes must be what the code carries."""

    findings: list[Finding] = []
    seal = STAGE7_PUBLIC_CAMPAIGN_SEAL_V1
    docs = REPOSITORY_ROOT / "docs" / "PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md"
    if not docs.exists():
        return [Finding("candidate_doc_missing", False, str(docs))]
    body = docs.read_text("utf-8")
    if seal.original_v1_archive_sha256 not in body:
        findings.append(
            Finding(
                "docs_omit_corpus_sha",
                False,
                "the candidate document does not quote the sealed corpus SHA-256",
            )
        )
    # Every one of these tokens *should* appear in the document — under a
    # negation.  "`50/81` is not a figure this measurement produces" and
    # "`STAGE_7_ACCEPTED` ... and `V1_TARGET_REPLACED` are **not** declared"
    # are sentences that have to be there; the finding is for the same token
    # asserted rather than refused.
    #
    # This is a documentation-consistency heuristic and it is written as one.
    # The scope is a symmetric window rather than a sentence, because the two
    # forms above put the negation on either side of the token and one of them
    # wraps a markdown list across lines — a backwards-only window flagged
    # exactly the sentence it was meant to approve of, and a line-scoped one
    # flagged the wrapped list.
    negations = ("not", "never", "cannot", "no v2 number", "still is")
    for forbidden in (
        "50/81",
        "STAGE_7_ACCEPTED",
        "STAGE_8_READY_TO_START",
        "PUBLIC_CORPUS_V2_OFFICIAL",
        "V1_TARGET_REPLACED",
    ):
        for window in _windows_around(body, forbidden):
            if not any(word in window.casefold() for word in negations):
                findings.append(
                    Finding(
                        "docs_state_a_forbidden_conclusion",
                        True,
                        f"the candidate document asserts {forbidden!r} with no "
                        f"negation nearby, in: {' '.join(window.split())[:200]}",
                    )
                )
    return findings


def _windows_around(body: str, token: str, radius: int = 240) -> list[str]:
    """Every span of the document around a mention of a token."""

    windows: list[str] = []
    start = body.find(token)
    while start != -1:
        windows.append(
            body[max(0, start - radius) : start + len(token) + radius]
        )
        start = body.find(token, start + len(token))
    return windows


def check_repository_is_untouched() -> list[Finding]:
    """This checker must not have changed anything it looked at."""

    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return [Finding("git_status_unavailable", False, completed.stderr.strip())]
    if completed.stdout.strip():
        return [
            Finding(
                "working_tree_dirty",
                False,
                "uncommitted changes are present; this is reported rather than "
                "blocking because a checker run mid-session is legitimate:\n"
                + completed.stdout.strip(),
            )
        ]
    return []


CHECKS = (
    ("all_refusal_laundering", check_all_refusal_laundering),
    ("single_refusal_laundering", check_single_refusal_laundering),
    ("input_attestation_joint_forgery", check_joint_forgery_needs_an_outside_reference),
    ("refusal_handle_swap_at_equal_counts", check_refusal_handle_swap_at_equal_counts),
    ("nested_gold_key", check_nested_gold_key),
    ("cross_field_validation", check_cross_field_validation),
    ("runtime_input_mutation", check_runtime_input_mutation),
    ("attestation_mutation", check_attestation_mutation),
    ("snapshot_binding_mutation", check_snapshot_binding_mutation),
    ("exact_head_mismatch", check_exact_head_mismatch),
    ("empty_record_measurement", check_empty_record_measurement),
    ("handle_completeness", check_handle_completeness_still_holds),
    ("score_class_separation", check_score_class_separation),
    ("official_and_shadow_not_summable", check_no_summed_official_and_shadow),
    ("import_isolation", check_import_isolation),
    ("thresholds_not_softened", check_thresholds_not_softened),
    ("campaign_seal_bypass", check_campaign_seal_cannot_be_bypassed),
    ("corpus_manifest_substitution", check_corpus_and_manifest_substitution),
    ("b30_angle_only_policy", check_b30_angle_only_policy_stays_revoked),
    ("redacted_view_handle_material", check_redacted_view_publishes_no_handle_material),
    ("canonical_digests_not_reprs", check_canonical_digests_are_not_reprs),
    ("direct_invocation_requires_attestation", check_direct_phase_invocation_requires_an_attestation),
    ("docs_agree_with_artifacts", check_docs_agree_with_the_machine_artifacts),
    ("repository_untouched", check_repository_is_untouched),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    findings: list[Finding] = []
    for name, check in CHECKS:
        produced = check()
        status = "CLEAN" if not produced else "FINDING"
        print(f"B28A_CHECK_{name}={status}")
        findings.extend(produced)

    blocking = [item for item in findings if item.blocking]
    for item in findings:
        label = "BLOCKING" if item.blocking else "NON_BLOCKING"
        print(f"B28A_FINDING[{label}] {item.name}: {item.detail}")

    print(f"B28A_CHECKER_CHECKS={len(CHECKS)}")
    print(f"B28A_CHECKER_BLOCKING_FINDINGS={len(blocking)}")
    print(f"B28A_CHECKER_NON_BLOCKING_FINDINGS={len(findings) - len(blocking)}")

    if args.report is not None:
        payload = {
            "version": "phase56-stage7-b28a-readonly-checker-v1",
            "checks": [name for name, _ in CHECKS],
            "blocking_findings": [
                {"name": item.name, "detail": item.detail}
                for item in findings
                if item.blocking
            ],
            "non_blocking_findings": [
                {"name": item.name, "detail": item.detail}
                for item in findings
                if not item.blocking
            ],
        }
        payload["report_digest"] = canonical_digest(payload)
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(body, encoding="utf-8")
        print(f"B28A_CHECKER_REPORT_FILE_SHA256={file_sha256(body)}")

    print(
        "B28A_CHECKER_ACCEPTANCE=" + ("PASS" if not blocking else "FAIL")
    )
    return 0 if not blocking else CHECKER_FAILURE_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
