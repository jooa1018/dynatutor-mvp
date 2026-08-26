"""Frozen contract for the distinct Phase 57 public continuation campaign."""

from __future__ import annotations

from typing import Literal

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256


PHASE57_PUBLIC_EVALUATION_VERSION = (
    "phase57-reproducible-public-evaluation-contract-v1"
)
PHASE57_CAMPAIGN_ID = "PHASE57_REPRODUCIBLE_PUBLIC_CONTINUATION_V1"
PHASE57_CAMPAIGN_SEAL_NAME = "phase57-reproducible-public-continuation-v1"
PHASE57_SOURCE_PHASE56_HEAD = "63a6e35614f9aa4dc3dbf8238e70f3b0a748fd17"

PHASE57_SOURCE_PUBLIC_ARCHIVE_SHA256 = (
    "cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef"
)
PHASE57_FIXTURE_SET_DIGEST = (
    "f3d143fb692711da840ec8aa0b35934d115ef40f2418053eda252892aa4cbeb0"
)
PHASE57_REPRODUCIBLE_ARCHIVE_SHA256 = (
    "e523fc39a3f44fd50542e622924c3154f76fa25362aaf5180884954892b3f958"
)
PHASE57_CONTINUATION_MANIFEST_DIGEST = (
    "32aa3ce51e3006e533913b2f822251d22dccba2a379a35008f19e7a7e1aef7cd"
)
PHASE57_CONTINUATION_MANIFEST_FILE_SHA256 = (
    "946cd6364669c123341d54999a87a468bc22f7260ea2b8500ddee267878bcd3a"
)
PHASE57_CONTINUATION_SELECTION_DIGEST = (
    "dcabc7f3a64ad448093d4d854e501da12d515c2876923bb8a456fccc192c4231"
)

PHASE56_HISTORICAL_STAGE7_STATUS = "STAGE_7_IN_PROGRESS / NOT_ACCEPTED"
PHASE56_HISTORICAL_STAGE8_STATUS = "STAGE_8_NOT_STARTED"


class Phase57AcceptanceThresholdsV1(FrozenStrictModel):
    """The public regression floor; improvements may exceed it, never weaken it."""

    expected_context_count: Literal[100] = 100
    expected_runtime_completed: Literal[97] = 97
    expected_projection_refused: Literal[3] = 3
    minimum_all_shadow_correct: Literal[50] = 50
    minimum_newly_solved_correct: Literal[6] = 6
    maximum_all_shadow_wrong: Literal[0] = 0
    maximum_all_shadow_unscored: Literal[0] = 0
    maximum_newly_solved_wrong: Literal[0] = 0
    maximum_newly_solved_unscored: Literal[0] = 0
    maximum_forbidden_class_solve: Literal[0] = 0
    maximum_regressed: Literal[0] = 0
    maximum_query_binding_mismatch: Literal[0] = 0


class Phase57QualityTargetsV1(FrozenStrictModel):
    """Completion target, deliberately separate from the regression floor."""

    expected_supported_count: Literal[81] = 81
    required_supported_correct: Literal[81] = 81
    maximum_supported_wrong: Literal[0] = 0
    maximum_forbidden_class_solve: Literal[0] = 0
    maximum_regressed: Literal[0] = 0


PHASE57_ACCEPTANCE_THRESHOLDS_V1 = Phase57AcceptanceThresholdsV1()
PHASE57_QUALITY_TARGETS_V1 = Phase57QualityTargetsV1()


class Phase57PublicEvaluationContractV1(FrozenStrictModel):
    """What a Phase 57 PASS does and, critically, does not claim."""

    version: Literal[
        "phase57-reproducible-public-evaluation-contract-v1"
    ] = PHASE57_PUBLIC_EVALUATION_VERSION
    campaign_id: Literal[
        "PHASE57_REPRODUCIBLE_PUBLIC_CONTINUATION_V1"
    ] = PHASE57_CAMPAIGN_ID
    campaign_seal_name: Literal[
        "phase57-reproducible-public-continuation-v1"
    ] = PHASE57_CAMPAIGN_SEAL_NAME
    source_phase56_head: Literal[
        "63a6e35614f9aa4dc3dbf8238e70f3b0a748fd17"
    ] = PHASE57_SOURCE_PHASE56_HEAD

    historical_phase56_stage7_status: Literal[
        "STAGE_7_IN_PROGRESS / NOT_ACCEPTED"
    ] = PHASE56_HISTORICAL_STAGE7_STATUS
    historical_phase56_stage8_status: Literal["STAGE_8_NOT_STARTED"] = (
        PHASE56_HISTORICAL_STAGE8_STATUS
    )
    historical_manifest_available: Literal[False] = False
    historical_substitution_allowed: Literal[False] = False
    historical_acceptance_claimed: Literal[False] = False
    hidden_generalization_claimed: Literal[False] = False
    public_regression_measurement: Literal[True] = True

    source_public_archive_sha256: Sha256 = PHASE57_SOURCE_PUBLIC_ARCHIVE_SHA256
    fixture_set_digest: Sha256 = PHASE57_FIXTURE_SET_DIGEST
    reproducible_archive_sha256: Sha256 = PHASE57_REPRODUCIBLE_ARCHIVE_SHA256
    continuation_manifest_digest: Sha256 = PHASE57_CONTINUATION_MANIFEST_DIGEST
    continuation_manifest_file_sha256: Sha256 = (
        PHASE57_CONTINUATION_MANIFEST_FILE_SHA256
    )
    continuation_selection_digest: Sha256 = PHASE57_CONTINUATION_SELECTION_DIGEST
    thresholds: Phase57AcceptanceThresholdsV1 = PHASE57_ACCEPTANCE_THRESHOLDS_V1
    quality_targets: Phase57QualityTargetsV1 = PHASE57_QUALITY_TARGETS_V1


def phase57_public_evaluation_contract() -> Phase57PublicEvaluationContractV1:
    """Return the immutable Phase 57 public continuation contract."""

    return Phase57PublicEvaluationContractV1()


__all__ = [
    "PHASE56_HISTORICAL_STAGE7_STATUS",
    "PHASE56_HISTORICAL_STAGE8_STATUS",
    "PHASE57_ACCEPTANCE_THRESHOLDS_V1",
    "PHASE57_CAMPAIGN_ID",
    "PHASE57_CAMPAIGN_SEAL_NAME",
    "PHASE57_CONTINUATION_MANIFEST_DIGEST",
    "PHASE57_CONTINUATION_MANIFEST_FILE_SHA256",
    "PHASE57_CONTINUATION_SELECTION_DIGEST",
    "PHASE57_FIXTURE_SET_DIGEST",
    "PHASE57_PUBLIC_EVALUATION_VERSION",
    "PHASE57_QUALITY_TARGETS_V1",
    "PHASE57_REPRODUCIBLE_ARCHIVE_SHA256",
    "PHASE57_SOURCE_PHASE56_HEAD",
    "PHASE57_SOURCE_PUBLIC_ARCHIVE_SHA256",
    "Phase57AcceptanceThresholdsV1",
    "Phase57PublicEvaluationContractV1",
    "Phase57QualityTargetsV1",
    "phase57_public_evaluation_contract",
]
