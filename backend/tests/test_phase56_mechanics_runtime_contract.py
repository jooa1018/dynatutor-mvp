from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json

import pytest
from pydantic import ValidationError

from engine.mechanics.compiler.contracts import CompilerResult, CompilerStatus
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_VERSION,
    IR_SCHEMA_VERSION,
    MechanicsProblemIRV1,
)
from engine.mechanics.modeler import (
    MechanicsModelerOutcome,
    ModelerTelemetry,
    ModelerTerminal,
)
from engine.mechanics.modeler_config import MechanicsIRMode
from engine.mechanics.modeler_cache import MECHANICS_MODELER_VERSION
from engine.mechanics.modeler_prompt import (
    MECHANICS_MODELER_PROMPT_VERSION,
    modeler_prompt_hash,
)
from engine.mechanics.normalization import (
    NORMALIZATION_POLICY_VERSION,
    VALIDATION_POLICY_VERSION,
)
from engine.mechanics.runtime import (
    RUNTIME_SUMMARY_SCHEMA,
    RUNTIME_SUMMARY_VERSION,
    MechanicsRuntimeExecution,
    MechanicsRuntimeSummary,
    RuntimeDelivery,
    RuntimeFailure,
    RuntimeTerminal,
    build_runtime_summary,
)
from engine.mechanics.runtime.contracts import (
    compiler_result_is_coherent,
    is_exact_confirmation_fingerprint,
    modeler_outcome_is_coherent,
)


SAFE_SUMMARY_FIELDS = {
    "schema",
    "version",
    "mode",
    "terminal",
    "delivery",
    "modeler_terminal",
    "compiler_status",
    "compiler_issue_codes",
    "solve_terminal",
    "solve_diagnostic_codes",
    "failure",
    "current_calculation_fingerprint",
}


def _empty_outcome(
    terminal: ModelerTerminal = ModelerTerminal.disabled,
    *,
    model: str = "safe-model",
) -> MechanicsModelerOutcome:
    return MechanicsModelerOutcome(
        terminal=terminal,
        normalization=None,
        ir=None,
        calculation_fingerprint=None,
        model=model,
        modeler_version=MECHANICS_MODELER_VERSION,
        prompt_version=MECHANICS_MODELER_PROMPT_VERSION,
        prompt_sha256=modeler_prompt_hash(),
        draft_schema_version=DRAFT_SCHEMA_VERSION,
        ir_schema_version=IR_SCHEMA_VERSION,
        validation_policy_version=VALIDATION_POLICY_VERSION,
        normalization_policy_version=NORMALIZATION_POLICY_VERSION,
        source_text_sha256="b" * 64,
        normalized_text_sha256="c" * 64,
        image_content_sha256=(),
        cache_hit=False,
        telemetry=ModelerTelemetry(
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            request_attempts=0,
            retry_count=0,
            measured_cost_usd=0.0,
            measured_cost_known=False,
            conservative_cost_usd=0.0,
            model_latency_ms=0.0,
            normalization_latency_ms=0.0,
            usage_missing_attempts=0,
            terminal_status=terminal.value,
        ),
        attempt_diagnostics=(),
        failure_code="safe_failure",
    )


def test_runtime_enums_are_closed_string_enums() -> None:
    assert {item.value for item in RuntimeTerminal} == {
        "off",
        "disabled",
        "confirmation_invalid",
        "confirmation_needed",
        "modeler_rejected",
        "compiler_rejected",
        "solve_rejected",
        "solved",
        "failed",
    }
    assert {item.value for item in RuntimeDelivery} == {"none", "legacy", "generic"}
    assert len(RuntimeFailure) == 9


@pytest.mark.parametrize(
    "value,expected",
    (
        ("a" * 64, True),
        ("0" * 64, True),
        ("A" * 64, False),
        ("a" * 63, False),
        ("a" * 65, False),
        (" " + "a" * 64, False),
        ("a" * 64 + "\n", False),
        (None, False),
        (7, False),
    ),
)
def test_confirmation_fingerprint_is_exact_without_coercion(value, expected) -> None:
    assert is_exact_confirmation_fingerprint(value) is expected


def test_execution_is_frozen_and_rejects_delivery_or_terminal_contradictions() -> None:
    execution = MechanicsRuntimeExecution(
        mode=MechanicsIRMode.off,
        terminal=RuntimeTerminal.off,
        delivery=RuntimeDelivery.legacy,
    )
    with pytest.raises(FrozenInstanceError):
        execution.delivery = RuntimeDelivery.none
    with pytest.raises(ValueError, match="delivery"):
        MechanicsRuntimeExecution(
            mode=MechanicsIRMode.shadow,
            terminal=RuntimeTerminal.disabled,
            delivery=RuntimeDelivery.none,
        )
    with pytest.raises(ValueError, match="off"):
        MechanicsRuntimeExecution(
            mode=MechanicsIRMode.auto,
            terminal=RuntimeTerminal.off,
            delivery=RuntimeDelivery.none,
        )
    with pytest.raises(ValueError, match="solved"):
        MechanicsRuntimeExecution(
            mode=MechanicsIRMode.required,
            terminal=RuntimeTerminal.solved,
            delivery=RuntimeDelivery.generic,
        )


def test_failure_terminal_and_sanitized_stage_are_strict_and_bidirectional() -> None:
    execution = MechanicsRuntimeExecution(
        mode=MechanicsIRMode.shadow,
        terminal=RuntimeTerminal.failed,
        delivery=RuntimeDelivery.legacy,
        failure=RuntimeFailure.modeler_execution,
    )
    assert execution.failure is RuntimeFailure.modeler_execution
    with pytest.raises(ValueError, match="failure"):
        MechanicsRuntimeExecution(
            mode=MechanicsIRMode.auto,
            terminal=RuntimeTerminal.failed,
            delivery=RuntimeDelivery.none,
        )
    with pytest.raises(ValueError, match="failure"):
        MechanicsRuntimeExecution(
            mode=MechanicsIRMode.auto,
            terminal=RuntimeTerminal.disabled,
            delivery=RuntimeDelivery.none,
            failure=RuntimeFailure.modeler_execution,
        )


def test_modeler_exact_type_and_nonaccepted_shape_are_enforced() -> None:
    outcome = _empty_outcome()
    assert modeler_outcome_is_coherent(outcome)

    class OutcomeSubclass(MechanicsModelerOutcome):
        pass

    subclass = OutcomeSubclass(**outcome.__dict__)
    assert not modeler_outcome_is_coherent(subclass)

    forged_ir = MechanicsProblemIRV1.model_construct()
    forged = replace(outcome, ir=forged_ir)
    assert not modeler_outcome_is_coherent(forged)


def test_compiler_exact_revalidation_rejects_forged_ready_without_graph() -> None:
    forged = CompilerResult.model_construct(
        status=CompilerStatus.ready,
        graph=None,
        issues=(),
    )
    assert not compiler_result_is_coherent(forged)


def test_summary_is_strict_frozen_extra_forbid_and_has_only_allowlisted_fields() -> None:
    summary = build_runtime_summary(
        MechanicsRuntimeExecution(
            mode=MechanicsIRMode.off,
            terminal=RuntimeTerminal.off,
            delivery=RuntimeDelivery.legacy,
        )
    )
    assert summary.schema == RUNTIME_SUMMARY_SCHEMA
    assert summary.version == RUNTIME_SUMMARY_VERSION
    assert set(summary.model_dump()) == SAFE_SUMMARY_FIELDS
    with pytest.raises(ValidationError, match="frozen"):
        summary.delivery = RuntimeDelivery.none
    with pytest.raises(ValidationError, match="extra"):
        MechanicsRuntimeSummary(
            mode=MechanicsIRMode.off,
            terminal=RuntimeTerminal.off,
            delivery=RuntimeDelivery.legacy,
            raw_text="forbidden",
        )
    with pytest.raises(ValidationError):
        MechanicsRuntimeSummary(
            mode="off",
            terminal=RuntimeTerminal.off,
            delivery=RuntimeDelivery.legacy,
        )


def test_summary_rejects_forged_confirmation_and_generic_shapes() -> None:
    with pytest.raises(ValidationError, match="confirmation"):
        MechanicsRuntimeSummary(
            mode=MechanicsIRMode.confirm,
            terminal=RuntimeTerminal.confirmation_needed,
            delivery=RuntimeDelivery.none,
            modeler_terminal=ModelerTerminal.accepted,
        )
    with pytest.raises(ValidationError, match="fingerprint"):
        MechanicsRuntimeSummary(
            mode=MechanicsIRMode.auto,
            terminal=RuntimeTerminal.disabled,
            delivery=RuntimeDelivery.none,
            current_calculation_fingerprint="a" * 64,
        )
    with pytest.raises(ValidationError, match="generic"):
        MechanicsRuntimeSummary(
            mode=MechanicsIRMode.required,
            terminal=RuntimeTerminal.disabled,
            delivery=RuntimeDelivery.generic,
        )


def test_retained_objects_and_sentinels_never_enter_summary_dump_json_or_repr() -> None:
    sentinel = "RAW_IR_EQUATION_EXPECTED_ANSWER_EXCEPTION_REF_LEGACY_ROUTE_SENTINEL"
    outcome = _empty_outcome(ModelerTerminal.unavailable, model=sentinel)
    execution = MechanicsRuntimeExecution(
        mode=MechanicsIRMode.shadow,
        terminal=RuntimeTerminal.modeler_rejected,
        delivery=RuntimeDelivery.legacy,
        modeler_outcome=outcome,
    )
    summary = execution.summary
    serialized = json.dumps(summary.model_dump(mode="json"), sort_keys=True)
    rendered = "\n".join((repr(execution), repr(summary), summary.model_dump_json()))
    assert sentinel not in serialized
    assert sentinel not in rendered
    for forbidden in (
        "normalization",
        "equation",
        "symbol",
        "backend",
        "candidate",
        "value_si",
        "source_text_sha256",
        "expected_answer",
        "legacy_route",
        "artifact",
    ):
        assert forbidden not in serialized
        assert forbidden not in repr(summary)


def test_summary_builder_rejects_nonexact_execution() -> None:
    class ExecutionSubclass(MechanicsRuntimeExecution):
        pass

    execution = ExecutionSubclass(
        mode=MechanicsIRMode.off,
        terminal=RuntimeTerminal.off,
        delivery=RuntimeDelivery.legacy,
    )
    with pytest.raises(TypeError, match="exact"):
        build_runtime_summary(execution)
