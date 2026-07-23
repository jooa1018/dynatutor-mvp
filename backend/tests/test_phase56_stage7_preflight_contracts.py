from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import socket

import pytest
from pydantic import ValidationError

from evaluation.phase56_stage7.contracts import (
    PUBLIC_CORPUS_ZIP_SHA256,
    STAGE7_ARTIFACT_SCHEMA,
    STAGE7_ARTIFACT_VERSION,
    STAGE7_CONTRACT_VERSION,
    STAGE7_EVALUATOR_VERSION,
    Stage7CourseScopePolicy,
    Stage7ExpectedTerminal,
    Stage7FailureKind,
    Stage7HardSafetySignal,
    Stage7Lane,
    Stage7Metric,
    Stage7RuntimeTerminal,
    expected_runtime_terminal,
    stage7_evaluation_contract,
)
from evaluation.phase56_stage7.gold_domain import (
    GoldDomainCaseV1,
    GoldNumericAnswerV1,
    PublicSplit,
    role_counter,
)
from evaluation.phase56_stage7.isolation import (
    assert_production_runtime_isolated,
    assert_public_fixtures_excluded_from_production_image,
    assert_runtime_domain_does_not_import_gold,
)
from evaluation.phase56_stage7.network_guard import (
    ExternalNetworkBlocked,
    assert_offline_environment,
    block_external_network,
)
from evaluation.phase56_stage7.preflight import (
    PreflightTerminal,
    fail_preflight,
    run_contract_preflight,
)
from evaluation.phase56_stage7.redaction import (
    Stage7AggregateArtifactV1,
    assert_privacy_safe_artifact,
    privacy_safe_case_hash,
)
from evaluation.phase56_stage7.runtime_domain import (
    RuntimeAnswerV1,
    RuntimeDomainInputV1,
    RuntimeDomainSnapshotV1,
    RuntimeEvaluationMode,
    RuntimeInputKind,
    RuntimeOptionsV1,
    RuntimeTypedInputV1,
    build_typed_runtime_input,
    canonical_runtime_json,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOKEN_A = "a" * 32
TOKEN_B = "b" * 32


def _options() -> RuntimeOptionsV1:
    return RuntimeOptionsV1(mechanics_mode=RuntimeEvaluationMode.required)


def _payload() -> dict[str, object]:
    return {
        "metadata": {"language": "ko", "correction_revision": 0},
        "entities": [{"entity_id": "bodyA", "primitive": "particle"}],
        "quantities": [{"quantity_id": "massQ", "semantic_role": "mass"}],
        "queries": [{"query_id": "queryA", "output_unit": "m/s"}],
    }


def _input(token: str = TOKEN_A) -> RuntimeDomainInputV1:
    return build_typed_runtime_input(
        execution_token=token,
        payload=_payload(),
        options=_options(),
    )


def _deterministic_echo(runtime_input: RuntimeDomainInputV1) -> RuntimeDomainSnapshotV1:
    digest = runtime_input.cache_sha256()
    return RuntimeDomainSnapshotV1(
        execution_token=runtime_input.execution_token,
        input_cache_sha256=digest,
        terminal=Stage7RuntimeTerminal.solved,
        answer=RuntimeAnswerV1(value=1.0, unit="m/s"),
        calculation_fingerprint=digest,
        equation_graph_fingerprint=digest,
        solve_plan_fingerprint=digest,
        candidate_set_fingerprint=digest,
        verification_fingerprint=digest,
        candidate_count=1,
        verified_candidate_count=1,
        runtime_call_count=1,
        compiler_call_count=1,
        solver_call_count=1,
        model_or_provider_call_count=0,
    )


def test_contract_versions_and_public_zip_hash_are_frozen() -> None:
    contract = stage7_evaluation_contract()
    assert contract.contract_version == STAGE7_CONTRACT_VERSION
    assert contract.evaluator_version == STAGE7_EVALUATOR_VERSION
    assert contract.corpus.expected_zip_sha256 == PUBLIC_CORPUS_ZIP_SHA256
    assert STAGE7_ARTIFACT_SCHEMA == "dynatutor.phase56_stage7.report"
    assert STAGE7_ARTIFACT_VERSION == "1.0"
    assert contract.actual_model_quality_disposition == "NOT_RUN / N/A"


def test_scope_counts_and_deferred_families_are_exact() -> None:
    contract = stage7_evaluation_contract()
    assert contract.split_counts.public_dev == 84
    assert contract.split_counts.public_adversarial == 16
    assert contract.expected_terminals.total == 100
    assert contract.expected_terminals.supported_accepted == 81
    assert contract.expected_terminals.deferred_unsupported == 12
    assert contract.course_scope.deferred_families == (
        "spring_mass_vibration",
        "relative_acceleration_translation",
        "coriolis_relative_motion",
        "slot_pin_relative_motion",
    )
    assert contract.course_scope.particle_on_incline_alias == (
        "typed_contact_and_friction_structure"
    )
    assert contract.course_scope.spring_energy_alias == "spring_energy_speed"


def test_course_scope_cannot_be_reordered_or_relaxed() -> None:
    with pytest.raises(ValidationError, match="frozen"):
        Stage7CourseScopePolicy(
            deferred_families=(
                "slot_pin_relative_motion",
                "coriolis_relative_motion",
                "relative_acceleration_translation",
                "spring_mass_vibration",
            )
        )


def test_expected_terminal_mapping_is_closed_and_scope_aware() -> None:
    assert expected_runtime_terminal(Stage7ExpectedTerminal.accepted) is (
        Stage7RuntimeTerminal.solved
    )
    assert expected_runtime_terminal(Stage7ExpectedTerminal.deferred_unsupported) is (
        Stage7RuntimeTerminal.verified_unsupported
    )
    assert expected_runtime_terminal(Stage7ExpectedTerminal.unsupported_other) is (
        Stage7RuntimeTerminal.verified_unsupported
    )
    assert expected_runtime_terminal(Stage7ExpectedTerminal.needs_figure) is (
        Stage7RuntimeTerminal.needs_figure
    )
    assert expected_runtime_terminal(Stage7ExpectedTerminal.needs_confirmation) is (
        Stage7RuntimeTerminal.needs_confirmation
    )
    assert expected_runtime_terminal(
        Stage7ExpectedTerminal.insufficient_information
    ) is Stage7RuntimeTerminal.insufficient_information


def test_catalogs_are_complete_and_frozen() -> None:
    contract = stage7_evaluation_contract()
    assert contract.metrics == tuple(Stage7Metric)
    assert contract.hard_safety_signals == tuple(Stage7HardSafetySignal)
    assert contract.failure_taxonomy == tuple(Stage7FailureKind)
    assert contract.lanes == tuple(Stage7Lane)
    assert len(contract.metrics) == 26
    assert len(contract.hard_safety_signals) == 23
    assert len(contract.failure_taxonomy) == 19
    assert len(contract.lanes) == 5


def test_contracts_are_frozen_strict_and_extra_forbid() -> None:
    contract = stage7_evaluation_contract()
    with pytest.raises(ValidationError, match="frozen"):
        contract.evaluator_version = "changed"
    with pytest.raises(ValidationError, match="extra"):
        type(contract)(unexpected="forbidden")
    with pytest.raises(ValidationError):
        type(contract)(version=1)


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "case_id",
        "caseId",
        "family",
        "expected_answer",
        "expected-answer",
        "gold_graph",
        "answer_tolerance",
        "reference_expression",
        "expected_terminal",
        "system_type",
        "selected_root",
        "final_answer",
        "filename",
    ),
)
def test_runtime_typed_payload_rejects_gold_and_routing_metadata(
    forbidden_key: str,
) -> None:
    payload = _payload()
    payload[forbidden_key] = "forbidden"
    with pytest.raises(ValidationError, match="forbidden metadata key"):
        build_typed_runtime_input(
            execution_token=TOKEN_A,
            payload=payload,
            options=_options(),
        )


def test_runtime_typed_payload_rejects_private_markers_at_any_depth() -> None:
    payload = _payload()
    payload["metadata"] = {
        "language": "ko",
        "note": {"value": "DO_NOT_SHARE_WITH_CODEX_private_heldout.jsonl"},
    }
    with pytest.raises(ValidationError, match="forbidden private input"):
        build_typed_runtime_input(
            execution_token=TOKEN_A,
            payload=payload,
            options=_options(),
        )


def test_runtime_input_requires_exactly_one_allowed_input_shape() -> None:
    with pytest.raises(ValidationError, match="text only"):
        RuntimeDomainInputV1(
            execution_token=TOKEN_A,
            input_kind=RuntimeInputKind.problem_text,
            typed_input=RuntimeTypedInputV1(
                payload_sha256=hashlib.sha256(
                    canonical_runtime_json(_payload())
                ).hexdigest(),
                payload=_payload(),
            ),
            options=_options(),
        )
    with pytest.raises(ValidationError, match="typed payload only"):
        RuntimeDomainInputV1(
            execution_token=TOKEN_A,
            input_kind=RuntimeInputKind.validated_typed_input,
            problem_text="질량 1 kg의 물체가 움직인다.",
            options=_options(),
        )


def test_runtime_cache_identity_excludes_only_opaque_execution_token() -> None:
    first = _input(TOKEN_A)
    second = _input(TOKEN_B)
    assert first.execution_token != second.execution_token
    assert first.cache_material() == second.cache_material()
    assert first.cache_sha256() == second.cache_sha256()
    dumped = first.model_dump(mode="json")
    assert set(dumped) == {
        "schema",
        "version",
        "execution_token",
        "input_kind",
        "problem_text",
        "typed_input",
        "images",
        "options",
    }
    serialized_cache = json.loads(first.cache_material())
    assert "execution_token" not in serialized_cache
    assert "case_id" not in first.cache_material().decode("utf-8")
    assert "family" not in first.cache_material().decode("utf-8")


def test_gold_metadata_mutations_cannot_change_runtime_result() -> None:
    runtime_input = _input()
    baseline = _deterministic_echo(runtime_input)
    case_a = GoldDomainCaseV1(
        case_id="public-a",
        split=PublicSplit.public_dev,
        family="constant_acceleration_1d",
        problem_sha256="1" * 64,
        expected_terminal=Stage7ExpectedTerminal.accepted,
        expected_answer=GoldNumericAnswerV1(
            value=1.0,
            unit="m/s",
            absolute_tolerance=1.0e-9,
            relative_tolerance=1.0e-9,
        ),
    )
    case_b = GoldDomainCaseV1(
        case_id="completely-different-id",
        split=PublicSplit.public_adversarial,
        family="unrelated_scoring_family",
        problem_sha256="2" * 64,
        expected_terminal=Stage7ExpectedTerminal.accepted,
        expected_answer=GoldNumericAnswerV1(
            value=999.0,
            unit="kg",
            absolute_tolerance=0.5,
            relative_tolerance=0.5,
        ),
    )
    assert case_a != case_b
    assert _deterministic_echo(runtime_input) == baseline
    assert runtime_input.cache_sha256() == baseline.input_cache_sha256


def test_runtime_snapshot_is_immutable_and_answer_shape_is_terminal_bound() -> None:
    snapshot = _deterministic_echo(_input())
    with pytest.raises(ValidationError, match="frozen"):
        snapshot.terminal = Stage7RuntimeTerminal.runtime_failure
    with pytest.raises(ValidationError, match="non-solved"):
        RuntimeDomainSnapshotV1(
            execution_token=TOKEN_A,
            input_cache_sha256="1" * 64,
            terminal=Stage7RuntimeTerminal.verified_unsupported,
            answer=RuntimeAnswerV1(value=1.0, unit="m/s"),
            candidate_count=0,
            verified_candidate_count=0,
            runtime_call_count=1,
            compiler_call_count=1,
            solver_call_count=0,
            model_or_provider_call_count=0,
        )


def test_role_counter_preserves_repeated_equal_fact_cardinality() -> None:
    counter = role_counter(("mass:body", "mass:body", "speed:body"))
    assert counter["mass:body"] == 2
    assert counter["speed:body"] == 1


def test_runtime_and_production_import_domains_are_physically_isolated() -> None:
    assert_runtime_domain_does_not_import_gold(REPOSITORY_ROOT)
    assert_production_runtime_isolated(REPOSITORY_ROOT)
    assert_public_fixtures_excluded_from_production_image(REPOSITORY_ROOT)


def test_contract_preflight_passes_without_any_execution_call() -> None:
    result = run_contract_preflight(REPOSITORY_ROOT)
    assert result.terminal is PreflightTerminal.passed
    assert result.ledger.zero_execution
    assert result.failure_kind is None


def test_preflight_failure_is_structured_zero_call_zero_cost() -> None:
    result = fail_preflight(" deliberately broken   contract ")
    assert result.terminal is PreflightTerminal.harness_contract_failure
    assert result.failure_kind is Stage7FailureKind.harness_failure
    assert result.sanitized_reason == "deliberately broken contract"
    assert result.ledger.zero_execution


def test_offline_environment_requires_empty_keys_and_provider_urls(monkeypatch) -> None:
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "MECHANICS_MODELER_BASE_URL",
        "MECHANICS_FIGURE_BASE_URL",
    ):
        monkeypatch.setenv(name, "")
    assert assert_offline_environment().passed
    monkeypatch.setenv("OPENAI_API_KEY", "not-empty")
    with pytest.raises(ExternalNetworkBlocked, match="empty model credentials"):
        assert_offline_environment()


def test_network_guard_fails_fast_and_restores_socket() -> None:
    original = socket.socket
    with block_external_network():
        with pytest.raises(ExternalNetworkBlocked, match="external network disabled"):
            socket.socket()
    assert socket.socket is original


@pytest.mark.parametrize(
    "payload",
    (
        {"problem_text": "raw corpus text"},
        {"goldGraph": {"answer": 1}},
        {"nested": {"expected-answer": 3}},
        {"value": "sk-secret-like-value"},
        {"value": "data:image/png;base64,AAAA"},
        {"value": "private_heldout"},
    ),
)
def test_artifact_redaction_rejects_raw_or_sensitive_content(payload) -> None:
    with pytest.raises(ValueError):
        assert_privacy_safe_artifact(payload)


def test_aggregate_artifact_emits_only_privacy_safe_aggregate_json() -> None:
    artifact = Stage7AggregateArtifactV1(
        exact_head_sha="1" * 64,
        corpus_zip_sha256=PUBLIC_CORPUS_ZIP_SHA256,
        public_split_sha256={"public_dev": "2" * 64},
        public_split_counts={"public_dev": 84},
        terminal_confusion={"accepted->accepted": 81},
        metric_aggregates={Stage7Metric.query_accuracy: 1.0},
        hard_safety_counts={Stage7HardSafetySignal.case_id_routing: 0},
        failure_counts={},
        privacy_safe_case_hashes=(
            privacy_safe_case_hash(case_id="public-a", problem_sha256="3" * 64),
        ),
    )
    payload = artifact.privacy_safe_json_bytes()
    decoded = json.loads(payload)
    assert decoded["actual_model_quality"] == "NOT_RUN / N/A"
    assert decoded["external_model_calls"] == 0
    assert decoded["private_heldout_accesses"] == 0
    for forbidden in (
        "problem_text",
        "gold_graph",
        "expected_answer",
        "raw_provider_output",
        "image_base64",
    ):
        assert forbidden not in payload.decode("utf-8")


def test_fixture_contract_commits_only_public_splits_schema_and_sanitized_metadata() -> None:
    contract = stage7_evaluation_contract()
    assert contract.corpus.committed_fixture_allowlist == (
        "public_dev.jsonl",
        "public_adversarial.jsonl",
        "schema.json",
        "sanitized_manifest.json",
        "README.md",
    )
    assert "public_all.jsonl" in contract.corpus.forbidden_commit_names
    assert "private_heldout_manifest_without_text.json" in (
        contract.corpus.forbidden_commit_names
    )
    assert contract.corpus.private_manifest_inspection == (
        "keys_only_absence_check_then_quarantine"
    )
