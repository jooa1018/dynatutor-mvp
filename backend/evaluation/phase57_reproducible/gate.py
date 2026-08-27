"""Strict aggregate gates for the Phase 57 public continuation measurement."""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Annotated, Any, Literal, Mapping

from pydantic import Field, StringConstraints, model_validator

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256
from evaluation.phase57_reproducible.contracts import (
    PHASE56_HISTORICAL_STAGE7_STATUS,
    PHASE56_HISTORICAL_STAGE8_STATUS,
    PHASE57_CAMPAIGN_ID,
    PHASE57_CAMPAIGN_SEAL_NAME,
    PHASE57_CONTINUATION_MANIFEST_DIGEST,
    PHASE57_FIXTURE_SET_DIGEST,
    PHASE57_PUBLIC_EVALUATION_VERSION,
    PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
    phase57_public_evaluation_contract,
)


PHASE57_GATE_REPORT_VERSION = "phase57-reproducible-public-gate-report-v1"
PHASE57_RUNNER_STATUS_VERSION = "phase57-reproducible-public-runner-status-v1"

GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class Phase57GateFailure(str, Enum):
    scorecard_unreadable = "scorecard_unreadable"
    scorecard_claims_official = "scorecard_claims_official"
    scorecard_acceptance_failed = "scorecard_acceptance_failed"
    code_head_mismatch = "code_head_mismatch"
    campaign_seal_mismatch = "campaign_seal_mismatch"
    archive_identity_mismatch = "archive_identity_mismatch"
    manifest_identity_mismatch = "manifest_identity_mismatch"
    expected_context_count_mismatch = "expected_context_count_mismatch"
    context_count_mismatch = "context_count_mismatch"
    ledger_state_counts_malformed = "ledger_state_counts_malformed"
    ledger_state_counts_mismatch = "ledger_state_counts_mismatch"
    all_correct_below_floor = "all_correct_below_floor"
    newly_solved_correct_below_floor = "newly_solved_correct_below_floor"
    all_wrong_nonzero = "all_wrong_nonzero"
    all_unscored_nonzero = "all_unscored_nonzero"
    newly_solved_wrong_nonzero = "newly_solved_wrong_nonzero"
    newly_solved_unscored_nonzero = "newly_solved_unscored_nonzero"
    forbidden_class_solve_nonzero = "forbidden_class_solve_nonzero"
    regression_nonzero = "regression_nonzero"
    query_binding_mismatch_nonzero = "query_binding_mismatch_nonzero"


class Phase57GateReportV1(FrozenStrictModel):
    """Privacy-minimal aggregate result for one exact-head Phase 57 run."""

    version: Literal[
        "phase57-reproducible-public-gate-report-v1"
    ] = PHASE57_GATE_REPORT_VERSION
    contract_version: Literal[
        "phase57-reproducible-public-evaluation-contract-v1"
    ] = PHASE57_PUBLIC_EVALUATION_VERSION
    campaign_id: Literal[
        "PHASE57_REPRODUCIBLE_PUBLIC_CONTINUATION_V1"
    ] = PHASE57_CAMPAIGN_ID
    campaign_seal_name: Literal[
        "phase57-reproducible-public-continuation-v1"
    ] = PHASE57_CAMPAIGN_SEAL_NAME
    exact_code_head: GitSha

    historical_phase56_stage7_status: Literal[
        "STAGE_7_IN_PROGRESS / NOT_ACCEPTED"
    ] = PHASE56_HISTORICAL_STAGE7_STATUS
    historical_phase56_stage8_status: Literal[
        "STAGE_8_NOT_STARTED"
    ] = PHASE56_HISTORICAL_STAGE8_STATUS
    historical_acceptance_claimed: Literal[False] = False
    historical_substitution_used: Literal[False] = False
    hidden_generalization_claimed: Literal[False] = False
    public_regression_measurement: Literal[True] = True
    production_release_claimed: Literal[False] = False
    external_model_calls: Literal[0] = 0
    private_heldout_text_accesses: Literal[0] = 0

    fixture_set_digest: Sha256 = PHASE57_FIXTURE_SET_DIGEST
    corpus_archive_sha256: Sha256 = PHASE57_REPRODUCIBLE_ARCHIVE_SHA256
    manifest_digest: Sha256 = PHASE57_CONTINUATION_MANIFEST_DIGEST
    source_shadow_report_raw_sha256: Sha256
    source_scorecard_digest: Sha256

    expected_context_count: int = Field(ge=0)
    context_count: int = Field(ge=0)
    runtime_completed: int = Field(ge=0)
    projection_refused: int = Field(ge=0)
    all_shadow_correct: int = Field(ge=0)
    all_shadow_wrong: int = Field(ge=0)
    all_shadow_unscored: int = Field(ge=0)
    newly_solved_correct: int = Field(ge=0)
    newly_solved_wrong: int = Field(ge=0)
    newly_solved_unscored: int = Field(ge=0)
    forbidden_class_solve: int = Field(ge=0)
    regressed: int = Field(ge=0)
    query_binding_mismatch: int = Field(ge=0)

    regression_acceptance: Literal["PASS", "FAIL"]
    regression_failures: tuple[str, ...] = ()
    quality_status: Literal["ACCEPTED", "IN_PROGRESS"]
    supported_correct_target: Literal[81] = 81
    quality_failures: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _dispositions_match_failures(self) -> "Phase57GateReportV1":
        if (self.regression_acceptance == "PASS") != (not self.regression_failures):
            raise ValueError("regression_disposition_inconsistent")
        if (self.quality_status == "ACCEPTED") != (not self.quality_failures):
            raise ValueError("quality_disposition_inconsistent")
        return self

    @property
    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class Phase57RunnerStatusV1(FrozenStrictModel):
    """Small status companion uploaded with the aggregate report."""

    version: Literal[
        "phase57-reproducible-public-runner-status-v1"
    ] = PHASE57_RUNNER_STATUS_VERSION
    campaign_seal_name: Literal[
        "phase57-reproducible-public-continuation-v1"
    ] = PHASE57_CAMPAIGN_SEAL_NAME
    exact_code_head: GitSha
    historical_phase56_stage7_status: Literal[
        "STAGE_7_IN_PROGRESS / NOT_ACCEPTED"
    ] = PHASE56_HISTORICAL_STAGE7_STATUS
    historical_phase56_stage8_status: Literal[
        "STAGE_8_NOT_STARTED"
    ] = PHASE56_HISTORICAL_STAGE8_STATUS
    historical_acceptance_claimed: Literal[False] = False
    historical_substitution_used: Literal[False] = False
    hidden_generalization_claimed: Literal[False] = False
    public_regression_measurement: Literal[True] = True
    production_release_claimed: Literal[False] = False
    regression_acceptance: Literal["PASS", "FAIL"]
    quality_status: Literal["ACCEPTED", "IN_PROGRESS", "NOT_RUN"]
    inner_exit: int | None = Field(default=None, ge=0)
    sanitized_reason: str | None = Field(default=None, max_length=96)

    @model_validator(mode="after")
    def _status_is_coherent(self) -> "Phase57RunnerStatusV1":
        if self.regression_acceptance == "PASS":
            if self.inner_exit != 0 or self.sanitized_reason is not None:
                raise ValueError("runner_pass_state_inconsistent")
            if self.quality_status == "NOT_RUN":
                raise ValueError("runner_pass_quality_not_run")
        return self


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(key)
    return value


def _state_counts(payload: Mapping[str, Any]) -> dict[str, int]:
    raw = payload.get("ledger_state_counts")
    if not isinstance(raw, list):
        raise ValueError(Phase57GateFailure.ledger_state_counts_malformed.value)

    output: dict[str, int] = {}
    for item in raw:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or isinstance(item[1], bool)
            or not isinstance(item[1], int)
            or item[1] < 0
            or item[0] in output
        ):
            raise ValueError(
                Phase57GateFailure.ledger_state_counts_malformed.value
            )
        output[item[0]] = item[1]
    return output


def evaluate_phase57_shadow_report(
    payload: Mapping[str, Any],
    *,
    exact_code_head: str,
    source_shadow_report_raw_sha256: str,
) -> Phase57GateReportV1:
    """Evaluate one gold-scored shadow report against two separate gates.

    The regression gate controls CI. The quality gate remains ``IN_PROGRESS``
    until all 81 supported public contexts are correct. A green regression run
    therefore cannot be cited as Phase 57 completion.
    """

    contract = phase57_public_evaluation_contract()
    failures: list[str] = []
    try:
        state_counts = _state_counts(payload)
        expected_context_count = _integer(payload, "expected_context_count")
        context_count = _integer(payload, "context_count")
        all_correct = _integer(payload, "all_shadow_correct")
        all_wrong = _integer(payload, "all_shadow_wrong")
        all_unscored = _integer(payload, "all_shadow_unscored")
        newly_correct = _integer(payload, "newly_solved_correct")
        newly_wrong = _integer(payload, "newly_solved_wrong")
        newly_unscored = _integer(payload, "newly_solved_unscored")
        forbidden = _integer(payload, "forbidden_class_solve")
        regressed = _integer(payload, "regressed")
        query_mismatch = _integer(payload, "query_binding_mismatch")
        scorecard_digest = payload.get("digest")
        if not isinstance(scorecard_digest, str) or not _HEX_64.fullmatch(
            scorecard_digest
        ):
            raise ValueError("digest")
        if not isinstance(source_shadow_report_raw_sha256, str) or not (
            _HEX_64.fullmatch(source_shadow_report_raw_sha256)
        ):
            raise ValueError("source_shadow_report_raw_sha256")
    except (TypeError, ValueError) as exc:
        reason = str(exc)
        if reason == Phase57GateFailure.ledger_state_counts_malformed.value:
            raise ValueError(reason) from None
        raise ValueError(Phase57GateFailure.scorecard_unreadable.value) from None

    thresholds = contract.thresholds
    acceptance_failures = payload.get("acceptance_failures")
    if payload.get("is_official_score") is not False:
        failures.append(Phase57GateFailure.scorecard_claims_official.value)
    if not isinstance(acceptance_failures, list) or acceptance_failures:
        failures.append(Phase57GateFailure.scorecard_acceptance_failed.value)
    if payload.get("exact_code_head") != exact_code_head:
        failures.append(Phase57GateFailure.code_head_mismatch.value)
    if payload.get("campaign_seal_name") != PHASE57_CAMPAIGN_SEAL_NAME:
        failures.append(Phase57GateFailure.campaign_seal_mismatch.value)
    if payload.get("original_v1_archive_sha256") != (
        PHASE57_REPRODUCIBLE_ARCHIVE_SHA256
    ):
        failures.append(Phase57GateFailure.archive_identity_mismatch.value)
    if payload.get("augmentation_manifest_sha256") != (
        PHASE57_CONTINUATION_MANIFEST_DIGEST
    ):
        failures.append(Phase57GateFailure.manifest_identity_mismatch.value)
    if expected_context_count != thresholds.expected_context_count:
        failures.append(Phase57GateFailure.expected_context_count_mismatch.value)

    runtime_completed = state_counts.get("runtime_completed", 0)
    projection_refused = state_counts.get("projection_refused", 0)
    expected_states = {
        "migration_refused": 0,
        "projection_refused": thresholds.expected_projection_refused,
        "runtime_completed": thresholds.expected_runtime_completed,
        "runtime_failed": 0,
        "snapshot_rejected": 0,
    }
    if state_counts != expected_states:
        failures.append(Phase57GateFailure.ledger_state_counts_mismatch.value)

    # ``expected_context_count`` is the fixed corpus population. ``context_count``
    # is the number of runtime records that were actually produced. Refused
    # contexts remain accounted for by the ledger and must not be counted as
    # records. Binding these values prevents either silent drops or denominator
    # inflation.
    if context_count != runtime_completed:
        failures.append(Phase57GateFailure.context_count_mismatch.value)

    if all_correct < thresholds.minimum_all_shadow_correct:
        failures.append(Phase57GateFailure.all_correct_below_floor.value)
    if newly_correct < thresholds.minimum_newly_solved_correct:
        failures.append(Phase57GateFailure.newly_solved_correct_below_floor.value)
    if all_wrong > thresholds.maximum_all_shadow_wrong:
        failures.append(Phase57GateFailure.all_wrong_nonzero.value)
    if all_unscored > thresholds.maximum_all_shadow_unscored:
        failures.append(Phase57GateFailure.all_unscored_nonzero.value)
    if newly_wrong > thresholds.maximum_newly_solved_wrong:
        failures.append(Phase57GateFailure.newly_solved_wrong_nonzero.value)
    if newly_unscored > thresholds.maximum_newly_solved_unscored:
        failures.append(Phase57GateFailure.newly_solved_unscored_nonzero.value)
    if forbidden > thresholds.maximum_forbidden_class_solve:
        failures.append(Phase57GateFailure.forbidden_class_solve_nonzero.value)
    if regressed > thresholds.maximum_regressed:
        failures.append(Phase57GateFailure.regression_nonzero.value)
    if query_mismatch > thresholds.maximum_query_binding_mismatch:
        failures.append(Phase57GateFailure.query_binding_mismatch_nonzero.value)

    regression_failures = tuple(sorted(set(failures)))
    quality = contract.quality_targets
    quality_failures: list[str] = [
        f"regression:{failure}" for failure in regression_failures
    ]
    if all_correct < quality.required_supported_correct:
        quality_failures.append(
            f"supported_correct:{all_correct}<{quality.required_supported_correct}"
        )
    if all_wrong > quality.maximum_supported_wrong:
        quality_failures.append(
            f"supported_wrong:{all_wrong}>{quality.maximum_supported_wrong}"
        )
    if forbidden > quality.maximum_forbidden_class_solve:
        quality_failures.append(
            "forbidden_class_solve:"
            f"{forbidden}>{quality.maximum_forbidden_class_solve}"
        )
    if regressed > quality.maximum_regressed:
        quality_failures.append(f"regressed:{regressed}>{quality.maximum_regressed}")
    canonical_quality_failures = tuple(sorted(set(quality_failures)))

    return Phase57GateReportV1(
        exact_code_head=exact_code_head,
        source_shadow_report_raw_sha256=source_shadow_report_raw_sha256,
        source_scorecard_digest=scorecard_digest,
        expected_context_count=expected_context_count,
        context_count=context_count,
        runtime_completed=runtime_completed,
        projection_refused=projection_refused,
        all_shadow_correct=all_correct,
        all_shadow_wrong=all_wrong,
        all_shadow_unscored=all_unscored,
        newly_solved_correct=newly_correct,
        newly_solved_wrong=newly_wrong,
        newly_solved_unscored=newly_unscored,
        forbidden_class_solve=forbidden,
        regressed=regressed,
        query_binding_mismatch=query_mismatch,
        regression_acceptance="PASS" if not regression_failures else "FAIL",
        regression_failures=regression_failures,
        quality_status=(
            "ACCEPTED" if not canonical_quality_failures else "IN_PROGRESS"
        ),
        quality_failures=canonical_quality_failures,
    )


def phase57_gate_report_as_dict(report: Phase57GateReportV1) -> dict[str, Any]:
    payload = report.model_dump(mode="json")
    payload["digest"] = report.digest
    return payload


def phase57_runner_status_as_dict(
    status: Phase57RunnerStatusV1,
) -> dict[str, Any]:
    return status.model_dump(mode="json")


__all__ = [
    "PHASE57_GATE_REPORT_VERSION",
    "PHASE57_RUNNER_STATUS_VERSION",
    "GitSha",
    "Phase57GateFailure",
    "Phase57GateReportV1",
    "Phase57RunnerStatusV1",
    "evaluate_phase57_shadow_report",
    "phase57_gate_report_as_dict",
    "phase57_runner_status_as_dict",
]
