from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


STAGE7_EVALUATOR_VERSION = "phase56-stage7-evaluator-v1"
STAGE7_CONTRACT_VERSION = "phase56-stage7-evaluation-contract-v1"
STAGE7_RUNTIME_INPUT_SCHEMA = "dynatutor.phase56_stage7.runtime_input"
STAGE7_RUNTIME_INPUT_VERSION = "1.0"
STAGE7_RUNTIME_SNAPSHOT_SCHEMA = "dynatutor.phase56_stage7.runtime_snapshot"
STAGE7_RUNTIME_SNAPSHOT_VERSION = "1.0"
STAGE7_GOLD_CASE_SCHEMA = "dynatutor.phase56_stage7.gold_case"
STAGE7_GOLD_CASE_VERSION = "1.0"
STAGE7_ARTIFACT_SCHEMA = "dynatutor.phase56_stage7.report"
STAGE7_ARTIFACT_VERSION = "1.0"

PUBLIC_CORPUS_ZIP_SHA256 = (
    "cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef"
)
PUBLIC_DEV_FILENAME = "public_dev.jsonl"
PUBLIC_ADVERSARIAL_FILENAME = "public_adversarial.jsonl"
PUBLIC_SCHEMA_FILENAME = "schema.json"
PRIVATE_MANIFEST_FILENAME = "private_heldout_manifest_without_text.json"
PUBLIC_FIXTURE_DIRECTORY = "backend/tests/fixtures/phase56_stage7_public"

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
VersionToken = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    ),
]


class FrozenStrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
        revalidate_instances="always",
    )


class Stage7Lane(str, Enum):
    corpus_and_evaluator_integrity = "lane_a_corpus_and_evaluator_integrity"
    deterministic_engine = "lane_b_gold_structure_to_ir_deterministic_engine"
    recorded_modeler = "lane_c_recorded_or_fake_modeler_contract"
    product_api = "lane_d_product_api_runtime"
    frontend = "lane_e_frontend_interaction"


class Stage7ExpectedTerminal(str, Enum):
    accepted = "accepted"
    deferred_unsupported = "deferred_unsupported"
    unsupported_other = "unsupported_other"
    needs_figure = "needs_figure"
    needs_confirmation = "needs_confirmation"
    insufficient_information = "insufficient_information"


class Stage7RuntimeTerminal(str, Enum):
    solved = "solved"
    verified_unsupported = "verified_unsupported"
    needs_figure = "needs_figure"
    needs_confirmation = "needs_confirmation"
    insufficient_information = "insufficient_information"
    runtime_failure = "runtime_failure"


_EXPECTED_TO_RUNTIME_TERMINAL: dict[Stage7ExpectedTerminal, Stage7RuntimeTerminal] = {
    Stage7ExpectedTerminal.accepted: Stage7RuntimeTerminal.solved,
    Stage7ExpectedTerminal.deferred_unsupported: Stage7RuntimeTerminal.verified_unsupported,
    Stage7ExpectedTerminal.unsupported_other: Stage7RuntimeTerminal.verified_unsupported,
    Stage7ExpectedTerminal.needs_figure: Stage7RuntimeTerminal.needs_figure,
    Stage7ExpectedTerminal.needs_confirmation: Stage7RuntimeTerminal.needs_confirmation,
    Stage7ExpectedTerminal.insufficient_information: Stage7RuntimeTerminal.insufficient_information,
}


def expected_runtime_terminal(
    expected: Stage7ExpectedTerminal,
) -> Stage7RuntimeTerminal:
    return _EXPECTED_TO_RUNTIME_TERMINAL[expected]


class Stage7FailureKind(str, Enum):
    harness_failure = "HARNESS_FAILURE"
    corpus_integrity_failure = "CORPUS_INTEGRITY_FAILURE"
    gold_isolation_failure = "GOLD_ISOLATION_FAILURE"
    evaluator_adapter_failure = "EVALUATOR_ADAPTER_FAILURE"
    corpus_reference_issue = "CORPUS_REFERENCE_ISSUE"
    modeling_contract_failure = "MODELING_CONTRACT_FAILURE"
    evidence_reconciliation_failure = "EVIDENCE_RECONCILIATION_FAILURE"
    normalization_failure = "NORMALIZATION_FAILURE"
    authorization_failure = "AUTHORIZATION_FAILURE"
    compiler_failure = "COMPILER_FAILURE"
    law_emission_failure = "LAW_EMISSION_FAILURE"
    solver_failure = "SOLVER_FAILURE"
    root_selection_failure = "ROOT_SELECTION_FAILURE"
    verification_failure = "VERIFICATION_FAILURE"
    projection_failure = "PROJECTION_FAILURE"
    api_failure = "API_FAILURE"
    frontend_failure = "FRONTEND_FAILURE"
    expected_terminal_mismatch = "EXPECTED_TERMINAL_MISMATCH"
    security_authority_failure = "SECURITY_AUTHORITY_FAILURE"


class Stage7Metric(str, Enum):
    entity_precision = "entity_precision"
    entity_recall = "entity_recall"
    segment_precision = "segment_precision"
    segment_recall = "segment_recall"
    event_precision = "event_precision"
    event_recall = "event_recall"
    explicit_fact_precision = "explicit_fact_precision"
    explicit_fact_recall = "explicit_fact_recall"
    relation_precision = "relation_precision"
    relation_recall = "relation_recall"
    query_accuracy = "query_accuracy"
    unit_accuracy = "unit_accuracy"
    entity_binding = "entity_binding"
    segment_binding = "segment_binding"
    event_binding = "event_binding"
    temporal_binding = "temporal_binding"
    direction_binding = "direction_binding"
    assumption_precision = "assumption_precision"
    route_terminal_accuracy = "route_terminal_accuracy"
    deterministic_answer_accuracy = "deterministic_answer_accuracy"
    candidate_coverage = "candidate_coverage"
    residual_verification = "residual_verification"
    safe_abstention = "safe_abstention"
    figure_dependency_accuracy = "figure_dependency_accuracy"
    conflict_accuracy = "conflict_accuracy"
    correction_replay_accuracy = "correction_replay_accuracy"


class Stage7HardSafetySignal(str, Enum):
    confident_wrong_solve = "confident_wrong_solve"
    invented_explicit_numeric_fact = "invented_explicit_numeric_fact"
    answer_authority_violation = "answer_authority_violation"
    model_selected_solver_authority = "model_selected_solver_authority"
    executable_model_equation = "executable_model_equation"
    selected_root_authority = "selected_root_authority"
    expected_answer_leakage = "expected_answer_leakage"
    gold_metadata_runtime_leakage = "gold_metadata_runtime_leakage"
    case_id_routing = "case_id_routing"
    family_routing = "family_routing"
    unsafe_legacy_fallback = "unsafe_legacy_fallback"
    deferred_silent_solve = "deferred_silent_solve"
    unresolved_conflict_solve = "unresolved_conflict_solve"
    correction_bypass = "correction_bypass"
    stale_revision_acceptance = "stale_revision_acceptance"
    direct_graph_patch = "direct_graph_patch"
    direct_answer_patch = "direct_answer_patch"
    raw_image_or_base64_logging = "raw_image_or_base64_logging"
    raw_provider_output_logging = "raw_provider_output_logging"
    prompt_injection_authority = "prompt_injection_authority"
    unbounded_repair_or_retry = "unbounded_repair_or_retry"
    candidate_root_early_discard = "candidate_root_early_discard"
    private_heldout_access = "private_heldout_access"


class Stage7ExpectedTerminalCounts(FrozenStrictModel):
    supported_accepted: Literal[81] = 81
    deferred_unsupported: Literal[12] = 12
    unsupported_other: Literal[2] = 2
    needs_figure: Literal[2] = 2
    needs_confirmation: Literal[2] = 2
    insufficient_information: Literal[1] = 1
    total: Literal[100] = 100

    @model_validator(mode="after")
    def validate_total(self) -> "Stage7ExpectedTerminalCounts":
        subtotal = (
            self.supported_accepted
            + self.deferred_unsupported
            + self.unsupported_other
            + self.needs_figure
            + self.needs_confirmation
            + self.insufficient_information
        )
        if subtotal != self.total:
            raise ValueError("scope-adjusted terminal counts must total 100")
        return self


class Stage7PublicSplitCounts(FrozenStrictModel):
    public_dev: Literal[84] = 84
    public_adversarial: Literal[16] = 16
    total: Literal[100] = 100
    public_dev_supported: Literal[72] = 72
    public_dev_deferred: Literal[12] = 12
    public_adversarial_supported: Literal[9] = 9

    @model_validator(mode="after")
    def validate_split(self) -> "Stage7PublicSplitCounts":
        if self.public_dev + self.public_adversarial != self.total:
            raise ValueError("public split counts must total 100")
        if self.public_dev_supported + self.public_dev_deferred != self.public_dev:
            raise ValueError("public_dev scope counts must total 84")
        return self


class Stage7CourseScopePolicy(FrozenStrictModel):
    policy_version: Literal["phase56-stage7-course-scope-v1"] = (
        "phase56-stage7-course-scope-v1"
    )
    accepted_generic_capability_count: Literal[25] = 25
    registry_inventory_count: Literal[29] = 29
    deferred_families: tuple[
        Literal[
            "spring_mass_vibration",
            "relative_acceleration_translation",
            "coriolis_relative_motion",
            "slot_pin_relative_motion",
        ],
        ...,
    ] = (
        "spring_mass_vibration",
        "relative_acceleration_translation",
        "coriolis_relative_motion",
        "slot_pin_relative_motion",
    )
    particle_on_incline_alias: Literal["typed_contact_and_friction_structure"] = (
        "typed_contact_and_friction_structure"
    )
    spring_energy_alias: Literal["spring_energy_speed"] = "spring_energy_speed"

    @model_validator(mode="after")
    def validate_scope(self) -> "Stage7CourseScopePolicy":
        if self.registry_inventory_count != (
            self.accepted_generic_capability_count + len(self.deferred_families)
        ):
            raise ValueError("Stage 7 scope must preserve 25 accepted plus 4 deferred")
        expected = (
            "spring_mass_vibration",
            "relative_acceleration_translation",
            "coriolis_relative_motion",
            "slot_pin_relative_motion",
        )
        if self.deferred_families != expected:
            raise ValueError("deferred families and order are frozen by current scope")
        return self


class Stage7CorpusInputContract(FrozenStrictModel):
    contract_version: Literal["phase56-stage7-public-corpus-input-v1"] = (
        "phase56-stage7-public-corpus-input-v1"
    )
    expected_zip_sha256: Literal[
        "cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef"
    ] = PUBLIC_CORPUS_ZIP_SHA256
    committed_fixture_allowlist: tuple[
        Literal[
            "public_dev.jsonl",
            "public_adversarial.jsonl",
            "schema.json",
            "sanitized_manifest.json",
            "README.md",
        ],
        ...,
    ] = (
        "public_dev.jsonl",
        "public_adversarial.jsonl",
        "schema.json",
        "sanitized_manifest.json",
        "README.md",
    )
    forbidden_commit_names: tuple[str, ...] = (
        "dynatutor_beer12_ko_corpus_v1_public.zip",
        "public_all.jsonl",
        "private_heldout_manifest_without_text.json",
        "DO_NOT_SHARE_WITH_CODEX_private_heldout.jsonl",
        "dynatutor_beer12_ko_corpus_v1_full.zip",
    )
    max_archive_member_bytes: Literal[2_000_000] = 2_000_000
    max_archive_total_bytes: Literal[10_000_000] = 10_000_000
    private_manifest_inspection: Literal[
        "keys_only_absence_check_then_quarantine"
    ] = "keys_only_absence_check_then_quarantine"


class Stage7QualityGates(FrozenStrictModel):
    deterministic_required_fraction: Literal[1.0] = 1.0
    diagnostic_metamorphic_required_fraction: Literal[1.0] = 1.0
    physics_change_detection_required_fraction: Literal[1.0] = 1.0
    synthetic_source_region_required_fraction: Literal[1.0] = 1.0
    maximum_hard_safety_violations: Literal[0] = 0
    maximum_external_model_calls: Literal[0] = 0
    maximum_private_accesses: Literal[0] = 0


class Stage7NetworkPolicy(FrozenStrictModel):
    policy_version: Literal["phase56-stage7-offline-network-v1"] = (
        "phase56-stage7-offline-network-v1"
    )
    external_network_allowed_during_evaluation: Literal[False] = False
    openai_api_key_required_value: Literal[""] = ""
    anthropic_api_key_required_value: Literal[""] = ""
    actual_model_calls_allowed: Literal[0] = 0
    repair_calls_allowed_for_fake_or_recorded_provider: Literal[1] = 1


class Stage7ReportRedactionPolicy(FrozenStrictModel):
    policy_version: Literal["phase56-stage7-report-redaction-v1"] = (
        "phase56-stage7-report-redaction-v1"
    )
    allowed_case_identifier: Literal["privacy_safe_sha256"] = "privacy_safe_sha256"
    bounded_mismatch_signature_max_chars: Literal[240] = 240
    forbidden_result_fields: tuple[str, ...] = (
        "problem_text",
        "gold_graph",
        "expected_answer",
        "answer_tolerance",
        "reference_expression",
        "raw_provider_output",
        "raw_image",
        "image_base64",
        "private_manifest",
        "prompt_content",
        "secret",
    )


class Stage7FixtureIsolationPolicy(FrozenStrictModel):
    policy_version: Literal["phase56-stage7-fixture-isolation-v1"] = (
        "phase56-stage7-fixture-isolation-v1"
    )
    evaluator_fixture_directory: Literal[
        "backend/tests/fixtures/phase56_stage7_public"
    ] = PUBLIC_FIXTURE_DIRECTORY
    production_import_roots: tuple[Literal["backend/app", "backend/engine"], ...] = (
        "backend/app",
        "backend/engine",
    )
    production_docker_copy_roots: tuple[Literal["app", "engine"], ...] = (
        "app",
        "engine",
    )
    evaluator_package_root: Literal["backend/evaluation/phase56_stage7"] = (
        "backend/evaluation/phase56_stage7"
    )


class Stage7EvaluationContractV1(FrozenStrictModel):
    schema: Literal["dynatutor.phase56_stage7.evaluation_contract"] = (
        "dynatutor.phase56_stage7.evaluation_contract"
    )
    version: Literal["1.0"] = "1.0"
    contract_version: Literal[
        "phase56-stage7-evaluation-contract-v1"
    ] = STAGE7_CONTRACT_VERSION
    evaluator_version: Literal[
        "phase56-stage7-evaluator-v1"
    ] = STAGE7_EVALUATOR_VERSION
    corpus: Stage7CorpusInputContract = Field(default_factory=Stage7CorpusInputContract)
    split_counts: Stage7PublicSplitCounts = Field(default_factory=Stage7PublicSplitCounts)
    expected_terminals: Stage7ExpectedTerminalCounts = Field(
        default_factory=Stage7ExpectedTerminalCounts
    )
    course_scope: Stage7CourseScopePolicy = Field(default_factory=Stage7CourseScopePolicy)
    quality_gates: Stage7QualityGates = Field(default_factory=Stage7QualityGates)
    network: Stage7NetworkPolicy = Field(default_factory=Stage7NetworkPolicy)
    redaction: Stage7ReportRedactionPolicy = Field(
        default_factory=Stage7ReportRedactionPolicy
    )
    fixture_isolation: Stage7FixtureIsolationPolicy = Field(
        default_factory=Stage7FixtureIsolationPolicy
    )
    metrics: tuple[Stage7Metric, ...] = tuple(Stage7Metric)
    hard_safety_signals: tuple[Stage7HardSafetySignal, ...] = tuple(
        Stage7HardSafetySignal
    )
    failure_taxonomy: tuple[Stage7FailureKind, ...] = tuple(Stage7FailureKind)
    lanes: tuple[Stage7Lane, ...] = tuple(Stage7Lane)
    actual_model_quality_disposition: Literal["NOT_RUN / N/A"] = "NOT_RUN / N/A"

    @model_validator(mode="after")
    def validate_closed_catalogs(self) -> "Stage7EvaluationContractV1":
        if self.metrics != tuple(Stage7Metric):
            raise ValueError("metric catalog is frozen in declaration order")
        if self.hard_safety_signals != tuple(Stage7HardSafetySignal):
            raise ValueError("hard-safety catalog is frozen in declaration order")
        if self.failure_taxonomy != tuple(Stage7FailureKind):
            raise ValueError("failure taxonomy is frozen in declaration order")
        if self.lanes != tuple(Stage7Lane):
            raise ValueError("evaluation lanes are frozen in declaration order")
        return self


def stage7_evaluation_contract() -> Stage7EvaluationContractV1:
    """Return the frozen, corpus-independent Stage 7 evaluator contract."""

    return Stage7EvaluationContractV1()
