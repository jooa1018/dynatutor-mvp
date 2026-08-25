"""Focused Stage-2 tests for the one-call generic mechanics modeler."""
from __future__ import annotations

import builtins
from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import inspect
import os
from pathlib import Path
import sqlite3
import stat
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
)
from engine.mechanics.modeler import (
    MechanicsModeler,
    MechanicsModelerOutcome,
    ModelerTelemetry,
    ModelerTerminal,
)
import engine.mechanics.modeler_cache as cache_module
from engine.mechanics.modeler_cache import (
    CacheSecurityError,
    DEFAULT_MECHANICS_CACHE_COMPATIBILITY_VERSIONS,
    MechanicsModelerCache,
    build_modeler_cache_key,
)
from engine.mechanics.modeler_client import (
    OpenAIMechanicsModelerClient,
    StructuredModelerResponse,
    build_modeler_user_text,
    modeler_request_input_token_ceiling,
    serialize_modeler_request_projection,
)
from engine.mechanics.modeler_config import (
    DEFAULT_MECHANICS_MODELER_MODEL,
    MechanicsIRMode,
    MechanicsModelerConfig,
)
from engine.mechanics.modeler_errors import (
    ModelerErrorCode,
    ModelerAuthorityError,
    ModelerIncompleteError,
    ModelerOutputMissingError,
    ModelerRefusalError,
    ModelerRepairIssue,
    ModelerSchemaError,
    ModelerStructuralSchemaError,
    ModelerUnavailableError,
)
from engine.mechanics.modeler_inputs import (
    ModelerImageInput,
    ModelerFigureDisabledError,
    ModelerInputBudgetError,
    ModelerInputError,
    verify_modeler_input,
)
from engine.mechanics.modeler_prompt import load_modeler_prompt
from engine.mechanics.modeler_repair import (
    is_repairable_structural_path,
    sanitize_repair_issues,
)
from engine.mechanics.modeler_telemetry import (
    ModelPriceSchedule,
    ModelerUsage,
    conservative_attempt_cost,
    resolve_price_schedule,
)
from engine.mechanics.errors import (
    MechanicsIssueCode,
    MechanicsIssueSeverity,
    MechanicsValidationIssue,
)
from engine.mechanics.normalization import NormalizationResult, normalize_draft
from engine.mechanics.validation import DraftValidationResult, ValidationTerminal


def _dimension(*, length: int = 0, time: int = 0) -> dict[str, int]:
    return {
        "mass": 0,
        "length": length,
        "time": time,
        "current": 0,
        "temperature": 0,
        "amount": 0,
        "luminous_intensity": 0,
    }


def _draft_payload() -> dict[str, object]:
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 999,
            "system_type": "diagnostic_only",
            "subtype": None,
            "model_id": None,
            "model_hash": None,
            "prompt_hash": None,
            "source_text_sha256": None,
            "model_confidence": 0.5,
        },
        "source_assets": [],
        "source_evidence": [],
        "entities": [
            {
                "entity_id": "body1",
                "primitive": "particle",
                "label": "body",
                "aliases": [],
                "component_of_entity_id": None,
                "evidence_refs": [],
                "model_confidence": 0.8,
            }
        ],
        "points": [],
        "reference_frames": [],
        "motion_intervals": [],
        "events": [],
        "symbols": [],
        "quantities": [],
        "geometry": [],
        "interactions": [],
        "constraints": [],
        "state_conditions": [],
        "queries": [
            {
                "query_id": "query1",
                "target": {
                    "role": "position",
                    "subject_id": "body1",
                    "point_id": None,
                    "frame_id": None,
                    "interval_id": None,
                    "event_id": None,
                    "component": "unspecified",
                    "direction": None,
                    "target_quantity_id": None,
                },
                "output_unit": "m",
                "output_dimension": _dimension(length=1),
                "shape": "scalar",
                "evidence_refs": [],
            }
        ],
        "principle_hints": [],
        "assumptions": [],
        "ambiguities": [],
        "figure_dependency": {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        },
        "unsupported_features": [],
    }


def _draft() -> MechanicsProblemDraftV1:
    return MechanicsProblemDraftV1.model_validate(_draft_payload())


def _duplicate_draft() -> MechanicsProblemDraftV1:
    payload = _draft_payload()
    payload["entities"] = [
        *payload["entities"],
        {
            "entity_id": "body1",
            "primitive": "particle",
            "label": "duplicate",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": [],
            "model_confidence": 0.2,
        },
    ]
    return MechanicsProblemDraftV1.model_validate(payload)


def _figure_required_draft() -> MechanicsProblemDraftV1:
    payload = _draft_payload()
    payload["figure_dependency"] = {
        "level": "required",
        "missing_information": ["geometry"],
        "evidence_refs": [],
    }
    return MechanicsProblemDraftV1.model_validate(payload)


def _unsupported_draft() -> MechanicsProblemDraftV1:
    payload = _draft_payload()
    payload["unsupported_features"] = [
        {
            "feature_code": "specialized_model",
            "description": "A specialized physical model is required.",
            "referenced_ids": ["body1"],
            "evidence_refs": [],
        }
    ]
    return MechanicsProblemDraftV1.model_validate(payload)


def _usage(input_tokens: int = 10, output_tokens: int = 20) -> ModelerUsage:
    return ModelerUsage(
        input_tokens=input_tokens,
        cached_input_tokens=1,
        output_tokens=output_tokens,
        reasoning_tokens=2,
        measured_cost_usd=0.0001,
        cost_known=True,
    )


def _response(
    draft: MechanicsProblemDraftV1,
    *,
    usage: ModelerUsage | None = None,
    usage_available: bool = True,
) -> StructuredModelerResponse:
    return StructuredModelerResponse(
        draft=draft,
        usage=usage or _usage(),
        usage_available=usage_available,
    )


class FakeModelClient:
    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, tuple[ModelerImageInput, ...], tuple[ModelerRepairIssue, ...]]] = []

    def model(
        self,
        problem_text: str,
        *,
        images: tuple[ModelerImageInput, ...] = (),
        repair_issues: tuple[ModelerRepairIssue, ...] = (),
    ) -> StructuredModelerResponse:
        self.calls.append((problem_text, images, repair_issues))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        assert isinstance(result, StructuredModelerResponse)
        return result


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, MechanicsProblemDraftV1] = {}

    def get(self, key: str):
        draft = self.values.get(key)
        return None if draft is None else SimpleNamespace(draft=draft)

    def put(self, key: str, draft: MechanicsProblemDraftV1) -> None:
        self.values[key] = draft


def _config(**changes: object) -> MechanicsModelerConfig:
    config = MechanicsModelerConfig(
        enabled=True,
        mode=MechanicsIRMode.auto,
        figure_enabled=True,
        cache_enabled=False,
    )
    return replace(config, **changes)


def _png(asset_id: str = "image1", suffix: bytes = b"") -> ModelerImageInput:
    data = b"\x89PNG\r\n\x1a\n" + suffix
    return ModelerImageInput(
        asset_id=asset_id,
        content_sha256=hashlib.sha256(data).hexdigest(),
        media_type="image/png",
        data=data,
    )


def _jpeg(asset_id: str = "image2") -> ModelerImageInput:
    data = b"\xff\xd8\xff\xe0fixture"
    return ModelerImageInput(
        asset_id=asset_id,
        content_sha256=hashlib.sha256(data).hexdigest(),
        media_type="image/jpeg",
        data=data,
    )


def test_config_defaults_are_rollout_safe_and_preserve_exact_snapshot() -> None:
    config = MechanicsModelerConfig.from_env()
    assert config.enabled is False
    assert config.mode is MechanicsIRMode.off
    assert config.store is False
    assert config.figure_enabled is False
    assert config.cache_enabled is False
    assert config.model == DEFAULT_MECHANICS_MODELER_MODEL == "gpt-5.4-mini-2026-03-17"
    assert config.max_total_cost_usd == 2.0
    assert config.figure_model is None
    assert config.selected_model(has_images=True) == config.model


def test_config_bounds_retry_mode_store_reasoning_and_figure_override(monkeypatch) -> None:
    monkeypatch.setenv("MECHANICS_IR_ENABLED", "true")
    monkeypatch.setenv("MECHANICS_IR_MODE", "shadow")
    monkeypatch.setenv("MECHANICS_MODELER_MAX_RETRIES", "99")
    monkeypatch.setenv("MECHANICS_MODELER_TIMEOUT_SECONDS", "999")
    monkeypatch.setenv("MECHANICS_MODELER_REASONING_EFFORT", "medium")
    monkeypatch.setenv("MECHANICS_FIGURE_ENABLED", "true")
    monkeypatch.setenv("MECHANICS_FIGURE_MODEL", "operator-figure-snapshot")
    config = MechanicsModelerConfig.from_env()
    assert config.mode is MechanicsIRMode.shadow
    assert config.max_retries == 1
    assert config.timeout_seconds == 60.0
    assert config.figure_enabled is True
    assert config.selected_model(has_images=False) == DEFAULT_MECHANICS_MODELER_MODEL
    assert config.selected_model(has_images=True) == "operator-figure-snapshot"
    monkeypatch.setenv("MECHANICS_MODELER_STORE", "true")
    with pytest.raises(ValueError, match="remain false"):
        MechanicsModelerConfig.from_env()
    monkeypatch.setenv("MECHANICS_MODELER_STORE", "false")
    monkeypatch.setenv("MECHANICS_MODELER_REASONING_EFFORT", "unbounded")
    with pytest.raises(ValueError, match="low"):
        MechanicsModelerConfig.from_env()


def test_live_modeler_cost_gate_is_immutably_capped_at_two_usd(monkeypatch) -> None:
    with pytest.raises(ValueError, match="cost budget"):
        _config(max_total_cost_usd=2.01)
    monkeypatch.setenv("MECHANICS_MODELER_MAX_COST_USD", "100")
    assert MechanicsModelerConfig.from_env().max_total_cost_usd == 2.0


def test_text_path_is_exactly_one_model_call_and_server_stamps_metadata() -> None:
    fake = FakeModelClient(_response(_draft()))
    outcome = MechanicsModeler(_config(), client=fake).model("Find the position.", correction_revision=7)
    assert len(fake.calls) == 1
    assert fake.calls[0][1] == ()
    assert fake.calls[0][2] == ()
    assert outcome.accepted
    assert outcome.terminal is ModelerTerminal.accepted
    assert outcome.ir is not None
    assert outcome.ir.metadata.correction_revision == 7
    assert outcome.ir.metadata.model_id == "mechanics_modeler"
    assert outcome.ir.metadata.source_text_sha256 == hashlib.sha256(b"Find the position.").hexdigest()
    with pytest.raises(FrozenInstanceError):
        outcome.terminal = ModelerTerminal.invalid
    with pytest.raises(FrozenInstanceError):
        outcome.telemetry.request_attempts = 9


def test_text_plus_multiple_images_is_one_combined_call() -> None:
    images = (_png(), _jpeg())
    fake = FakeModelClient(_response(_draft()))
    outcome = MechanicsModeler(_config(), client=fake).model("Use both figures.", images=images)
    assert len(fake.calls) == 1
    assert fake.calls[0][1] is images
    assert outcome.accepted
    assert outcome.image_content_sha256 == tuple(image.content_sha256 for image in images)
    assert tuple(asset.asset_id for asset in outcome.ir.source_assets) == ("image1", "image2")


def test_duplicate_graph_gets_one_fresh_full_repair_with_same_images() -> None:
    images = (_png(), _jpeg())
    fake = FakeModelClient(_response(_duplicate_draft(), usage=_usage(10, 20)), _response(_draft(), usage=_usage(30, 40)))
    outcome = MechanicsModeler(_config(), client=fake).model("Repair structure.", images=images)
    assert outcome.accepted
    assert len(fake.calls) == 2
    assert fake.calls[0][1] is images and fake.calls[1][1] is images
    assert fake.calls[0][2] == ()
    repair = fake.calls[1][2]
    assert repair and {issue.code for issue in repair} == {"duplicate_id"}
    assert all(set(vars(issue)) == {"code", "path", "referenced_id", "reason_code", "error_type"} for issue in repair)
    assert outcome.telemetry.input_tokens == 40
    assert outcome.telemetry.output_tokens == 60
    assert outcome.telemetry.request_attempts == 2
    assert outcome.telemetry.retry_count == 1


def test_repeated_structural_failure_stops_after_two_total_attempts() -> None:
    fake = FakeModelClient(_response(_duplicate_draft()), _response(_duplicate_draft()))
    outcome = MechanicsModeler(_config(), client=fake).model("Do not loop.")
    assert len(fake.calls) == 2
    assert outcome.terminal is ModelerTerminal.invalid
    assert outcome.ir is None and outcome.calculation_fingerprint is None


def test_schema_error_repair_is_allowlisted_and_sanitized() -> None:
    issue = ModelerRepairIssue(
        "schema_error",
        "entities.0.entity_id",
        reason_code="schema_error",
        error_type="missing",
    )
    untrusted = ModelerRepairIssue(
        "schema_error",
        "private_secret_field",
        referenced_id="not valid",
        reason_code="private reason",
        error_type="private details",
    )
    first = ModelerStructuralSchemaError(
        "private details", repair_issues=(issue, untrusted)
    )
    fake = FakeModelClient(first, _response(_draft()))
    outcome = MechanicsModeler(_config(), client=fake).model("Trusted original text.")
    assert outcome.accepted and len(fake.calls) == 2
    assert fake.calls[1][0] == "Trusted original text."
    assert fake.calls[1][2] == (issue,)
    assert "private details" not in repr(outcome.attempt_diagnostics)


def test_repair_path_allowlist_requires_a_safe_structural_leaf() -> None:
    assert is_repairable_structural_path("entities.0.entity_id")
    assert is_repairable_structural_path(
        "reference_frames.0.origin.point_id"
    )
    assert is_repairable_structural_path("queries.0.target.subject_id")
    assert is_repairable_structural_path(
        "motion_intervals.0.subject_ids.1"
    )
    assert is_repairable_structural_path("geometry.0.participant_ids.0")
    for path in (
        "entities",
        "entities.0",
        "reference_frames.0.origin",
        "reference_frames.0.axes",
        "reference_frames.0.generalized_coordinate_symbol_ids",
        "motion_intervals.0.subject_ids",
        "geometry.0.participant_ids",
        "interactions.0.point_ids",
        "events.0.interval_ids",
        "motion_intervals.0.subject_ids.01",
        "motion_intervals.0.subject_ids.512",
        "source_evidence.0.source_span",
        "quantities.0.quantity_id",
        "quantities.0.raw_value",
        "events.0.time_quantity_id",
        "queries.0.target.target_quantity_id",
        "assumptions.0.assumption_id",
        "figure_dependency.evidence_refs",
        "metadata.model_hash",
    ):
        assert not is_repairable_structural_path(path)


@pytest.mark.parametrize(
    "error_type",
    [
        None,
        "value_error",
        "extra_forbidden",
        "model_type",
        "json_invalid",
        "union_tag_invalid",
        "private.regex-safe-type",
    ],
)
def test_schema_repair_requires_a_strict_pydantic_error_type(error_type) -> None:
    issue = ModelerRepairIssue(
        "schema_error",
        "entities.0.entity_id",
        reason_code="schema_error",
        error_type=error_type,
    )
    assert sanitize_repair_issues((issue,)) == ()

    allowed = replace(issue, error_type="missing")
    assert sanitize_repair_issues((allowed,)) == (allowed,)


@pytest.mark.parametrize("code", ["authentication", "timeout", "quota"])
def test_unavailable_failures_never_loop(code: str) -> None:
    error = ModelerUnavailableError("private")
    error.code = ModelerErrorCode(code)
    fake = FakeModelClient(error, _response(_draft()))
    outcome = MechanicsModeler(_config(), client=fake).model("One attempt only.")
    assert len(fake.calls) == 1
    assert outcome.terminal is ModelerTerminal.unavailable


@pytest.mark.parametrize(
    ("error", "terminal"),
    [
        (ModelerIncompleteError("private"), ModelerTerminal.invalid),
        (ModelerOutputMissingError("private"), ModelerTerminal.invalid),
        (ModelerAuthorityError("private"), ModelerTerminal.refused),
        (ModelerRefusalError("private"), ModelerTerminal.refused),
    ],
)
def test_terminal_model_failures_never_repair(error, terminal) -> None:
    fake = FakeModelClient(error, _response(_draft()))
    outcome = MechanicsModeler(_config(), client=fake).model("One attempt only.")
    assert len(fake.calls) == 1
    assert outcome.terminal is terminal


@pytest.mark.parametrize(
    ("code", "path"),
    [
        (MechanicsIssueCode.evidence_quote_missing, "source_evidence.0.quote"),
        (MechanicsIssueCode.evidence_span_mismatch, "source_evidence.0.source_span"),
        (MechanicsIssueCode.evidence_occurrence_mismatch, "source_evidence.0.occurrence_index"),
        (MechanicsIssueCode.quantity_occurrence_reused, "quantities.0.evidence_refs"),
        (MechanicsIssueCode.figure_asset_missing, "source_evidence.0.asset_id"),
        (MechanicsIssueCode.figure_region_invalid, "source_evidence.0.region"),
        (MechanicsIssueCode.provenance_violation, "quantities.0.provenance"),
        (MechanicsIssueCode.raw_value_mismatch, "quantities.0.raw_value"),
        (MechanicsIssueCode.raw_unit_mismatch, "quantities.0.raw_unit"),
        (MechanicsIssueCode.assumption_not_approved, "assumptions.0"),
    ],
)
def test_sensitive_validation_failures_never_repair(code, path) -> None:
    issue = MechanicsValidationIssue(
        code,
        MechanicsIssueSeverity.error,
        "private validation detail",
        path,
    )
    validation = DraftValidationResult(ValidationTerminal.invalid, (issue,))

    def rejected(*args, **kwargs):
        return NormalizationResult(
            ValidationTerminal.invalid,
            validation,
            None,
            None,
            0,
        )

    fake = FakeModelClient(_response(_draft()), _response(_draft()))
    outcome = MechanicsModeler(
        _config(), client=fake, normalizer=rejected
    ).model("Sensitive failure.")
    assert len(fake.calls) == 1
    assert outcome.terminal is ModelerTerminal.invalid


def test_preflight_gates_make_zero_api_calls() -> None:
    fake = FakeModelClient(_response(_draft()))
    disabled = MechanicsModeler(
        replace(_config(), enabled=False, mode=MechanicsIRMode.off), client=fake
    ).model("No dispatch.")
    assert disabled.terminal is ModelerTerminal.disabled and fake.calls == []

    figures_off = MechanicsModeler(
        replace(_config(), figure_enabled=False), client=fake
    ).model("No image dispatch.", images=(_png(),))
    assert figures_off.terminal is ModelerTerminal.needs_figure and fake.calls == []

    image = _png()
    bad = replace(image, content_sha256="0" * 64)
    invalid = MechanicsModeler(_config(), client=fake).model("Bad hash.", images=(bad,))
    assert invalid.terminal is ModelerTerminal.invalid and fake.calls == []

    budget = MechanicsModeler(
        replace(_config(), max_total_cost_usd=0.001), client=fake
    ).model("Budget blocks before dispatch.")
    assert budget.terminal is ModelerTerminal.budget_exceeded and fake.calls == []

    nonbyte_image = replace(_png(), data="RAW_NONBYTE_IMAGE_PRIVATE")
    invalid_nonbyte = MechanicsModeler(_config(), client=fake).model(
        "RAW_NONBYTE_PROBLEM_PRIVATE", images=(nonbyte_image,)
    )
    assert invalid_nonbyte.terminal is ModelerTerminal.invalid
    assert invalid_nonbyte.image_content_sha256 == ()
    assert fake.calls == []

    disabled_nonbyte = MechanicsModeler(
        replace(_config(), enabled=False, mode=MechanicsIRMode.off), client=fake
    ).model("RAW_DISABLED_PROBLEM_PRIVATE", images=(nonbyte_image,))
    assert disabled_nonbyte.terminal is ModelerTerminal.disabled
    assert disabled_nonbyte.image_content_sha256 == ()
    assert fake.calls == []


def test_image_preflight_verifies_type_signature_count_and_byte_budgets() -> None:
    config = _config()
    with pytest.raises(ModelerInputError) as media_error:
        verify_modeler_input(
            "source", (replace(_png(), media_type="image/svg+xml"),), config
        )
    assert type(media_error.value) is ModelerInputError
    assert media_error.value.code == "input_invalid"
    assert str(media_error.value) == "modeler input is invalid"

    with pytest.raises(ModelerInputError) as signature_error:
        verify_modeler_input(
            "source", (replace(_png(), media_type="image/jpeg"),), config
        )
    assert type(signature_error.value) is ModelerInputError
    assert signature_error.value.code == "input_invalid"
    assert str(signature_error.value) == "modeler input is invalid"

    with pytest.raises(ModelerInputBudgetError) as count_error:
        verify_modeler_input("source", (_png(), _jpeg()), replace(config, max_images=1))
    assert count_error.value.code == "input_budget_exceeded"
    assert str(count_error.value) == "modeler input budget was exceeded"

    large_data = b"\x89PNG\r\n\x1a\n" + b"x" * 1_100
    large = ModelerImageInput(
        "large1", hashlib.sha256(large_data).hexdigest(), "image/png", large_data
    )
    with pytest.raises(ModelerInputBudgetError) as byte_error:
        verify_modeler_input(
            "source", (large,), replace(config, max_image_bytes=1_024)
        )
    assert byte_error.value.code == "input_budget_exceeded"
    assert str(byte_error.value) == "modeler input budget was exceeded"
    large2 = replace(large, asset_id="large2")
    with pytest.raises(ModelerInputBudgetError) as total_error:
        verify_modeler_input(
            "source",
            (large, large2),
            replace(config, max_image_bytes=2_000, max_total_image_bytes=2_100),
        )
    assert total_error.value.code == "input_budget_exceeded"
    assert str(total_error.value) == "modeler input budget was exceeded"


def test_request_budget_covers_exact_korean_schema_metadata_images_and_repair() -> None:
    config = _config()
    schedule = resolve_price_schedule(config.model)
    assert schedule.input_usd_per_million == 0.75
    assert schedule.cached_input_usd_per_million == 0.075
    assert schedule.output_usd_per_million == 4.50

    hostile_pattern = "\\\"\n\r\t\b\f한"
    problem_text = (
        hostile_pattern * (config.max_problem_chars // len(hostile_pattern))
        + "한" * (config.max_problem_chars % len(hostile_pattern))
    )
    images = tuple(
        replace(
            _png("a" + str(index) + "x" * 62, suffix=bytes([index])),
            page_id="p" + str(index) + "y" * 62,
            page_number=100_000,
            parent_asset_id="r" + str(index) + "z" * 62,
        )
        for index in range(config.max_images)
    )
    verified = verify_modeler_input(problem_text, images, config)
    assert verified.images is images

    initial_projection = serialize_modeler_request_projection(
        problem_text,
        images,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        max_output_tokens=config.max_output_tokens,
    )
    assert "\\\\" in initial_projection
    assert '\\"' in initial_projection
    assert "\\n" in initial_projection and "\\r" in initial_projection
    assert "\\ud55c" in initial_projection
    assert "MechanicsProblemDraftV1" in initial_projection
    assert "json_schema" in initial_projection
    assert "data:image/png;base64," in initial_projection
    initial_ceiling = modeler_request_input_token_ceiling(
        problem_text,
        images,
        (),
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        max_output_tokens=config.max_output_tokens,
        image_tokens_per_image_upper_bound=(
            schedule.image_tokens_per_image_upper_bound
        ),
    )
    assert initial_ceiling >= (
        len(initial_projection.encode("utf-8"))
        + len(images) * schedule.image_tokens_per_image_upper_bound
    )

    repair_issues = (
        ModelerRepairIssue(
            "duplicate_id",
            "entities.1.entity_id",
            referenced_id="body1",
            reason_code="duplicate_id",
        ),
    )
    repair_ceiling = modeler_request_input_token_ceiling(
        problem_text,
        images,
        repair_issues,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        max_output_tokens=config.max_output_tokens,
        image_tokens_per_image_upper_bound=(
            schedule.image_tokens_per_image_upper_bound
        ),
    )
    repair_projection = serialize_modeler_request_projection(
        problem_text,
        images,
        repair_issues,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        max_output_tokens=config.max_output_tokens,
    )
    assert repair_ceiling >= (
        len(repair_projection.encode("utf-8"))
        + len(images) * schedule.image_tokens_per_image_upper_bound
    )
    assert repair_ceiling > initial_ceiling
    assert conservative_attempt_cost(
        config.model,
        input_token_ceiling=repair_ceiling,
        max_output_tokens=config.max_output_tokens,
    ) > 0


def test_unpriced_model_override_refuses_before_dispatch_unless_schedule_matches() -> None:
    with pytest.raises(ValueError, match="conservative"):
        ModelPriceSchedule(
            model="operator-free-model",
            input_usd_per_million=0.0,
            cached_input_usd_per_million=0.0,
            output_usd_per_million=0.0,
            image_tokens_per_image_upper_bound=20_000,
        )

    fake = FakeModelClient(_response(_draft()))
    unpriced = MechanicsModeler(
        _config(model="operator-unpriced-model"), client=fake
    ).model("Do not dispatch without a price ceiling.")
    assert unpriced.terminal is ModelerTerminal.budget_exceeded
    assert unpriced.failure_code == "model_pricing_unavailable"
    assert fake.calls == []

    sdk_responses = FakeResponsesAPI(_sdk_response(parsed=_draft()))
    direct_client = OpenAIMechanicsModelerClient(
        _config(model="operator-unpriced-model"),
        sdk_client=SimpleNamespace(responses=sdk_responses),
    )
    with pytest.raises(ModelerUnavailableError):
        direct_client.model("Direct boundary also refuses before SDK dispatch.")
    assert sdk_responses.calls == []

    schedule = ModelPriceSchedule(
        model="operator-priced-model",
        input_usd_per_million=1.0,
        cached_input_usd_per_million=0.1,
        output_usd_per_million=5.0,
        image_tokens_per_image_upper_bound=20_000,
        pricing_version="operator-price-v1",
    )
    priced_fake = FakeModelClient(_response(_draft()))
    priced = MechanicsModeler(
        _config(
            model="operator-priced-model",
            model_price_schedule=schedule,
        ),
        client=priced_fake,
    ).model("Dispatch with an explicit bounded schedule.")
    assert priced.accepted
    assert len(priced_fake.calls) == 1


def test_repair_cost_is_reserved_before_second_call() -> None:
    problem_text = "One reservation fits but two do not."
    config = _config()
    verified = verify_modeler_input(problem_text, (), config)
    probe = MechanicsModeler(config, client=FakeModelClient())
    initial_cost = probe._reservation(
        config.model, verified, repair_issues=()
    )
    repair_issues = (
        ModelerRepairIssue(
            "duplicate_id",
            "entities.1.entity_id",
            referenced_id="body1",
            reason_code="duplicate_id",
        ),
    )
    repair_cost = probe._reservation(
        config.model, verified, repair_issues=repair_issues
    )
    budget = initial_cost + repair_cost / 2
    assert 0.001 <= budget <= 100.0

    fake = FakeModelClient(_response(_duplicate_draft()))
    outcome = MechanicsModeler(
        replace(config, max_total_cost_usd=budget), client=fake
    ).model(problem_text)
    assert len(fake.calls) == 1
    assert outcome.terminal is ModelerTerminal.budget_exceeded
    assert outcome.telemetry.request_attempts == 1
    assert outcome.telemetry.conservative_cost_usd == initial_cost


@pytest.mark.parametrize(
    ("draft", "terminal"),
    [
        (_figure_required_draft(), ModelerTerminal.needs_figure),
        (_unsupported_draft(), ModelerTerminal.unsupported),
        (_duplicate_draft(), ModelerTerminal.invalid),
    ],
)
def test_nonaccepted_terminals_never_expose_ir_or_fingerprint(draft, terminal) -> None:
    fake = FakeModelClient(_response(draft))
    outcome = MechanicsModeler(_config(max_retries=0), client=fake).model("Terminal mapping.")
    assert outcome.terminal is terminal
    assert outcome.ir is None
    assert outcome.calculation_fingerprint is None


def test_trusted_normalization_arguments_are_forwarded_by_identity() -> None:
    approved: list[str] = []
    corrections: dict[str, object] = {}
    assumptions: dict[str, object] = {}
    confirmed: set[str] = set()
    captured: dict[str, object] = {}

    def spy(problem_text, draft, **kwargs):
        captured.update(kwargs)
        return normalize_draft(problem_text, draft, **kwargs)

    outcome = MechanicsModeler(
        _config(), client=FakeModelClient(_response(_draft())), normalizer=spy
    ).model(
        "Forward exactly.",
        approved_assumption_ids=approved,
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
        confirmed_figure_evidence_ids=confirmed,
    )
    assert outcome.accepted
    assert captured["approved_assumption_ids"] is approved
    assert captured["authorized_corrections"] is corrections
    assert captured["authorized_assumptions"] is assumptions
    assert captured["confirmed_figure_evidence_ids"] is confirmed


def test_cache_hit_revalidates_with_current_trusted_arguments_and_zero_calls() -> None:
    cache = MemoryCache()
    fake = FakeModelClient(_response(_draft()))
    calls: list[object] = []

    def spy(problem_text, draft, **kwargs):
        calls.append(kwargs["approved_assumption_ids"])
        return normalize_draft(problem_text, draft, **kwargs)

    modeler = MechanicsModeler(
        _config(cache_enabled=True), client=fake, cache=cache, normalizer=spy
    )
    first_authority = ("first",)
    second_authority = ("second",)
    first = modeler.model("Cache source.", approved_assumption_ids=first_authority)
    second = modeler.model("Cache source.", approved_assumption_ids=second_authority)
    assert first.accepted and second.accepted and second.cache_hit
    assert len(fake.calls) == 1
    assert calls == [first_authority, second_authority]


def test_cache_key_binds_text_images_models_prompt_policy_revision_and_identity(monkeypatch) -> None:
    config = _config()
    image1, image2 = _png(), _jpeg()
    verified = verify_modeler_input("A  source", (image1, image2), config)

    def key(**changes):
        return build_modeler_cache_key(
            changes.pop("verified", verified),
            changes.pop("config", config),
            correction_revision=changes.pop("revision", 1),
            modeling_input_identity=changes.pop("identity", "input-v1"),
            compatibility_versions=changes.pop(
                "compatibility_versions",
                DEFAULT_MECHANICS_CACHE_COMPATIBILITY_VERSIONS,
            ),
        )

    baseline = key()
    assert key(revision=2) != baseline
    assert key(identity="input-v2") != baseline
    assert key(config=replace(config, model="operator-model")) != baseline
    assert key(verified=verify_modeler_input("A source", (image1, image2), config)) != baseline
    assert key(verified=verify_modeler_input("A  source", (image2, image1), config)) != baseline
    assert key(verified=verify_modeler_input("A  source", (_png(suffix=b"x"), image2), config)) != baseline
    original_prompt_hash = cache_module.modeler_prompt_hash
    monkeypatch.setattr(cache_module, "modeler_prompt_hash", lambda: "f" * 64)
    assert key() != baseline
    monkeypatch.setattr(cache_module, "modeler_prompt_hash", original_prompt_hash)
    original_normalization_policy = cache_module.NORMALIZATION_POLICY_VERSION
    monkeypatch.setattr(cache_module, "NORMALIZATION_POLICY_VERSION", "changed-policy")
    assert key() != baseline
    monkeypatch.setattr(
        cache_module,
        "NORMALIZATION_POLICY_VERSION",
        original_normalization_policy,
    )

    compatibility = DEFAULT_MECHANICS_CACHE_COMPATIBILITY_VERSIONS
    for dimension in (
        "evidence",
        "law",
        "compiler",
        "solver",
        "verification",
    ):
        changed = replace(
            compatibility,
            **{dimension: getattr(compatibility, dimension) + "-changed"},
        )
        assert key(compatibility_versions=changed) != baseline
    with pytest.raises(FrozenInstanceError):
        compatibility.evidence = "mutable"  # type: ignore[misc]

    cache_source = inspect.getsource(cache_module)
    assert "engine.mechanics.compiler" not in cache_source
    assert "engine.mechanics.solver" not in cache_source
    assert "engine.mechanics.verification" not in cache_source


def test_cache_path_type_bounds_and_existing_directory_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(CacheSecurityError, match="type"):
        MechanicsModelerCache(path=object())  # type: ignore[arg-type]
    with pytest.raises(CacheSecurityError, match="length"):
        MechanicsModelerCache(path="x" * 1_025)
    with pytest.raises(CacheSecurityError, match="name a file"):
        MechanicsModelerCache(path=tmp_path)


def test_default_cache_secures_private_directory_file_and_delete_journal(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(cache_module.tempfile, "gettempdir", lambda: str(tmp_path))
    cache = MechanicsModelerCache()
    cache.put("private-key", _draft())
    assert cache.path.exists()
    assert cache.path.parent.name == "dynatutor_mechanics_modeler_cache"
    with sqlite3.connect(cache.path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(journal_mode).lower() == "delete"
    assert not Path(str(cache.path) + "-wal").exists()
    assert not Path(str(cache.path) + "-shm").exists()
    if os.name == "posix":
        assert stat.S_IMODE(cache.path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(cache.path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission boundary")
def test_cache_rejects_nonprivate_custom_parent(tmp_path: Path) -> None:
    public_parent = tmp_path / "public-cache"
    public_parent.mkdir(mode=0o755)
    public_parent.chmod(0o755)
    with pytest.raises(CacheSecurityError, match="permissions"):
        MechanicsModelerCache(path=public_parent / "mechanics.sqlite3")

    private_target = tmp_path / "private-target"
    private_target.mkdir(mode=0o700)
    linked_parent = tmp_path / "linked-cache"
    linked_parent.symlink_to(private_target, target_is_directory=True)
    with pytest.raises(CacheSecurityError, match="symbolic link"):
        MechanicsModelerCache(path=linked_parent / "mechanics.sqlite3")


def test_sqlite_cache_corruption_is_deleted_and_treated_as_miss(tmp_path: Path) -> None:
    path = tmp_path / "mechanics.sqlite3"
    cache = MechanicsModelerCache(path=str(path), ttl_seconds=60, l1_entries=1, l2_entries=10)
    cache.put("key", _draft())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE mechanics_modeler_cache SET payload_json = ? WHERE cache_key = ?",
            ("{corrupt", "key"),
        )
    fresh = MechanicsModelerCache(path=str(path), ttl_seconds=60, l1_entries=1, l2_entries=10)
    assert fresh.get("key") is None
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT 1 FROM mechanics_modeler_cache WHERE cache_key = ?", ("key",)
        ).fetchone() is None


def test_cache_ttl_and_l1_capacity_are_bounded(tmp_path: Path) -> None:
    now = [100.0]
    cache = MechanicsModelerCache(
        path=str(tmp_path / "ttl.sqlite3"),
        ttl_seconds=60,
        l1_entries=1,
        l2_entries=10,
        clock=lambda: now[0],
    )
    cache.put("first", _draft())
    cache.put("second", _draft())
    assert len(cache._l1) == 1
    assert cache.get("first") is not None  # recovered through structured L2
    now[0] = 161.0
    assert cache.get("first") is None


class FakeResponsesAPI:
    def __init__(self, response=None, error: BaseException | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _sdk_response(
    *,
    parsed: MechanicsProblemDraftV1 | None = None,
    status: str = "completed",
    incomplete_reason: str | None = None,
    refusal: bool = False,
    usage: bool = True,
):
    output = []
    if refusal:
        output = [SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="blocked")])]
    usage_object = None
    if usage:
        usage_object = SimpleNamespace(
            input_tokens=11,
            output_tokens=22,
            input_tokens_details=SimpleNamespace(cached_tokens=3),
            output_tokens_details=SimpleNamespace(reasoning_tokens=4),
        )
    return SimpleNamespace(
        status=status,
        incomplete_details=(
            SimpleNamespace(reason=incomplete_reason)
            if incomplete_reason is not None
            else None
        ),
        output=output,
        output_parsed=parsed,
        usage=usage_object,
    )


def _capture_exception(target, *args, **kwargs) -> BaseException:
    captured: BaseException | None = None
    try:
        target(*args, **kwargs)
    except BaseException as caught:
        captured = caught
    target = None
    args = ()
    kwargs = {}
    if captured is None:
        raise AssertionError("call did not raise")
    return captured


def _assert_exception_graph_is_sanitized(
    caught: BaseException,
    *,
    forbidden_objects: tuple[object, ...] = (),
    forbidden_text: tuple[str, ...] = (),
    forbidden_bytes: tuple[bytes, ...] = (),
) -> None:
    forbidden_ids = {id(value) for value in forbidden_objects}
    visited: set[int] = set()

    def visit(value: object) -> None:
        identity = id(value)
        assert identity not in forbidden_ids
        if identity in visited:
            return
        visited.add(identity)
        if isinstance(value, str):
            assert not any(token in value for token in forbidden_text)
            return
        if isinstance(value, (bytes, bytearray, memoryview)):
            blob = bytes(value)
            assert not any(token in blob for token in forbidden_bytes)
            return
        if value is None or isinstance(value, (bool, int, float)):
            return
        if isinstance(value, dict):
            for key, item in value.items():
                visit(key)
                visit(item)
            return
        if isinstance(value, (tuple, list, set, frozenset)):
            for item in value:
                visit(item)
            return
        if isinstance(value, BaseException):
            visit(value.args)
            visit(vars(value))
            assert value.__cause__ is None
            assert value.__context__ is None
            traceback = value.__traceback__
            while traceback is not None:
                visit(dict(traceback.tb_frame.f_locals))
                traceback = traceback.tb_next
            return
        attributes = getattr(value, "__dict__", None)
        if isinstance(attributes, dict):
            visit(attributes)

    assert caught.__suppress_context__ is True
    visit(caught)


def test_public_input_boundaries_scrub_all_raw_frames_and_values() -> None:
    config = _config(max_problem_chars=500)
    lone_surrogate = "RAW_LONE_SURROGATE_\ud800_PRIVATE"
    lone_error = _capture_exception(
        verify_modeler_input, lone_surrogate, (), config
    )
    assert type(lone_error) is ModelerInputError
    _assert_exception_graph_is_sanitized(
        lone_error, forbidden_text=(lone_surrogate, "RAW_LONE_SURROGATE")
    )

    budget_text = "RAW_BUDGET_PRIVATE_" * 40
    budget_error = _capture_exception(
        verify_modeler_input, budget_text, (), config
    )
    assert isinstance(budget_error, ModelerInputBudgetError)
    _assert_exception_graph_is_sanitized(
        budget_error, forbidden_text=(budget_text, "RAW_BUDGET_PRIVATE")
    )

    image_sentinel = b"RAW_REAL_IMAGE_BYTES_PRIVATE"
    png_bytes = b"\x89PNG\r\n\x1a\n" + image_sentinel
    signature_image = ModelerImageInput(
        "privateImage",
        hashlib.sha256(png_bytes).hexdigest(),
        "image/jpeg",
        png_bytes,
    )
    asset_error = _capture_exception(
        signature_image.verified_asset, config
    )
    assert type(asset_error) is ModelerInputError
    _assert_exception_graph_is_sanitized(
        asset_error,
        forbidden_objects=(signature_image,),
        forbidden_bytes=(image_sentinel,),
    )

    verify_error = _capture_exception(
        verify_modeler_input,
        "Image signature source.",
        (signature_image,),
        config,
    )
    assert type(verify_error) is ModelerInputError
    _assert_exception_graph_is_sanitized(
        verify_error,
        forbidden_objects=(signature_image,),
        forbidden_bytes=(image_sentinel,),
    )

    valid_private_image = _png(suffix=image_sentinel)
    figure_error = _capture_exception(
        verify_modeler_input,
        "Figure disabled source.",
        (valid_private_image,),
        replace(config, figure_enabled=False),
    )
    assert isinstance(figure_error, ModelerFigureDisabledError)
    _assert_exception_graph_is_sanitized(
        figure_error,
        forbidden_objects=(valid_private_image,),
        forbidden_bytes=(image_sentinel,),
    )

    # Invalid typed data is deliberately deferred out of the generated
    # dataclass __init__ frame and into the sanitized verification boundary.
    nonbytes_image = ModelerImageInput(
        "nonbytesImage",
        "0" * 64,
        "image/png",
        bytearray(image_sentinel),  # type: ignore[arg-type]
    )
    type_error = _capture_exception(nonbytes_image.verified_asset, config)
    assert type(type_error) is ModelerInputError
    _assert_exception_graph_is_sanitized(
        type_error,
        forbidden_objects=(nonbytes_image,),
        forbidden_bytes=(image_sentinel,),
    )

    token_error = _capture_exception(
        modeler_request_input_token_ceiling,
        lone_surrogate,
        (),
        (),
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        max_output_tokens=config.max_output_tokens,
        image_tokens_per_image_upper_bound=16_384,
    )
    assert type(token_error) is ModelerInputError
    _assert_exception_graph_is_sanitized(
        token_error, forbidden_text=(lone_surrogate, "RAW_LONE_SURROGATE")
    )

    token_image_error = _capture_exception(
        modeler_request_input_token_ceiling,
        "Token image source.",
        (nonbytes_image,),
        (),
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        max_output_tokens=config.max_output_tokens,
        image_tokens_per_image_upper_bound=16_384,
    )
    assert type(token_image_error) is ModelerInputError
    _assert_exception_graph_is_sanitized(
        token_image_error,
        forbidden_objects=(nonbytes_image,),
        forbidden_bytes=(image_sentinel,),
    )


def test_sdk_import_and_constructor_failures_scrub_keys_and_raw_errors(
    monkeypatch,
) -> None:
    api_key_sentinel = "sk-RAW_API_KEY_PRIVATE"
    import_sentinel = "RAW_SDK_IMPORT_PRIVATE"
    original_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError(import_sentinel)
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(builtins, "__import__", failing_import)
        import_error = _capture_exception(
            OpenAIMechanicsModelerClient,
            _config(),
            api_key=api_key_sentinel,
        )
    assert isinstance(import_error, ModelerUnavailableError)
    _assert_exception_graph_is_sanitized(
        import_error,
        forbidden_text=(api_key_sentinel, import_sentinel),
    )

    constructor_sentinel = "RAW_SDK_CONSTRUCTOR_PRIVATE"

    class FailingOpenAI:
        def __init__(self, *, api_key, timeout, max_retries) -> None:
            raise RuntimeError(
                f"{constructor_sentinel}:{api_key}:{timeout}:{max_retries}"
            )

    with monkeypatch.context() as scoped:
        scoped.setitem(
            sys.modules, "openai", SimpleNamespace(OpenAI=FailingOpenAI)
        )
        constructor_error = _capture_exception(
            OpenAIMechanicsModelerClient,
            _config(),
            api_key=api_key_sentinel,
        )
    assert isinstance(constructor_error, ModelerUnavailableError)
    _assert_exception_graph_is_sanitized(
        constructor_error,
        forbidden_text=(api_key_sentinel, constructor_sentinel),
    )


def test_official_client_payload_is_one_message_with_text_and_all_images() -> None:
    response = _sdk_response(parsed=_draft())
    responses = FakeResponsesAPI(response)
    schedule = ModelPriceSchedule(
        model="operator-figure-model",
        input_usd_per_million=1.0,
        cached_input_usd_per_million=0.1,
        output_usd_per_million=5.0,
        image_tokens_per_image_upper_bound=20_000,
        pricing_version="operator-figure-price-v1",
    )
    client = OpenAIMechanicsModelerClient(
        _config(
            figure_model="operator-figure-model",
            model_price_schedule=schedule,
        ),
        sdk_client=SimpleNamespace(responses=responses),
    )
    images = (_png(), _jpeg())
    result = client.model("Combined source.", images=images)
    assert result.draft == _draft()
    assert len(responses.calls) == 1
    payload = responses.calls[0]
    assert payload["model"] == "operator-figure-model"
    assert payload["store"] is False and payload["tools"] == []
    assert payload["text_format"] is MechanicsProblemDraftV1
    assert len(payload["input"]) == 1
    message = payload["input"][0]
    assert message["role"] == "user"
    assert [item["type"] for item in message["content"]] == ["input_text", "input_image", "input_image"]
    assert message["content"][0]["text"] == build_modeler_user_text(
        "Combined source.", images
    )
    assert all(item["image_url"].startswith("data:image/") for item in message["content"][1:])
    assert result.usage.input_tokens == 11
    assert result.usage.cached_input_tokens == 3
    assert result.usage.output_tokens == 22
    assert result.usage.reasoning_tokens == 4


def test_official_client_text_only_uses_same_single_call_contract() -> None:
    responses = FakeResponsesAPI(_sdk_response(parsed=_draft()))
    client = OpenAIMechanicsModelerClient(
        _config(), sdk_client=SimpleNamespace(responses=responses)
    )
    client.model("Text only.")
    payload = responses.calls[0]
    assert payload["model"] == DEFAULT_MECHANICS_MODELER_MODEL
    assert len(payload["input"]) == 1
    assert [part["type"] for part in payload["input"][0]["content"]] == ["input_text"]


def test_official_client_maps_refusal_incomplete_missing_and_missing_usage() -> None:
    refusal_client = OpenAIMechanicsModelerClient(
        _config(), sdk_client=SimpleNamespace(responses=FakeResponsesAPI(_sdk_response(parsed=None, refusal=True)))
    )
    with pytest.raises(ModelerRefusalError):
        refusal_client.model("Refusal.")

    incomplete_client = OpenAIMechanicsModelerClient(
        _config(),
        sdk_client=SimpleNamespace(
            responses=FakeResponsesAPI(
                _sdk_response(parsed=None, status="incomplete", incomplete_reason="max_output_tokens")
            )
        ),
    )
    with pytest.raises(ModelerIncompleteError) as incomplete:
        incomplete_client.model("Incomplete.")
    assert not incomplete.value.repairable
    assert incomplete.value.repair_issues == ()

    missing_client = OpenAIMechanicsModelerClient(
        _config(),
        sdk_client=SimpleNamespace(
            responses=FakeResponsesAPI(_sdk_response(parsed=None, usage=False))
        ),
    )
    with pytest.raises(ModelerOutputMissingError) as missing:
        missing_client.model("Missing.")
    assert missing.value.code is ModelerErrorCode.output_missing
    assert missing.value.usage is None
    assert not missing.value.repairable
    assert missing.value.repair_issues == ()


def test_official_client_maps_schema_authority_and_api_failures_without_raw_details() -> None:
    with pytest.raises(ValidationError) as schema_validation:
        MechanicsProblemDraftV1.model_validate({"schema": DRAFT_SCHEMA_NAME})
    schema_client = OpenAIMechanicsModelerClient(
        _config(),
        sdk_client=SimpleNamespace(
            responses=FakeResponsesAPI(error=schema_validation.value)
        ),
    )
    with pytest.raises(ModelerSchemaError) as schema_error:
        schema_client.model("Schema failure.")
    assert not schema_error.value.repairable
    assert schema_error.value.repair_issues == ()
    assert "Schema failure" not in repr(schema_error.value.repair_issues)

    structural_payload = _draft_payload()
    del structural_payload["entities"][0]["entity_id"]
    with pytest.raises(ValidationError) as structural_validation:
        MechanicsProblemDraftV1.model_validate(structural_payload)
    structural_client = OpenAIMechanicsModelerClient(
        _config(),
        sdk_client=SimpleNamespace(
            responses=FakeResponsesAPI(error=structural_validation.value)
        ),
    )
    with pytest.raises(ModelerStructuralSchemaError) as structural_error:
        structural_client.model("Structural failure.")
    assert structural_error.value.repairable
    assert structural_error.value.repair_issues == (
        ModelerRepairIssue(
            "schema_error",
            "entities.0.entity_id",
            reason_code="schema_error",
            error_type="missing",
        ),
    )

    authority_payload = _draft_payload()
    authority_payload["expected" + "_answer"] = "private value"
    with pytest.raises(ValidationError) as authority_validation:
        MechanicsProblemDraftV1.model_validate(authority_payload)
    authority_client = OpenAIMechanicsModelerClient(
        _config(),
        sdk_client=SimpleNamespace(
            responses=FakeResponsesAPI(error=authority_validation.value)
        ),
    )
    with pytest.raises(ModelerAuthorityError) as authority_error:
        authority_client.model("Authority failure.")
    assert not authority_error.value.repairable

    class FakeProviderError(Exception):
        def __init__(self, status_code: int, code: str | None = None) -> None:
            super().__init__("raw provider detail must stay private")
            self.status_code = status_code
            self.code = code

    for provider_error, expected_code in (
        (FakeProviderError(401), ModelerErrorCode.authentication),
        (FakeProviderError(429, "insufficient_quota"), ModelerErrorCode.quota),
        (FakeProviderError(500), ModelerErrorCode.api_status),
    ):
        client = OpenAIMechanicsModelerClient(
            _config(),
            sdk_client=SimpleNamespace(
                responses=FakeResponsesAPI(error=provider_error)
            ),
        )
        with pytest.raises(ModelerUnavailableError) as mapped:
            client.model("API failure.")
        assert mapped.value.code is expected_code
        assert "raw provider detail" not in str(mapped.value)


def test_typed_client_errors_do_not_retain_raw_provider_or_validation_graphs() -> None:
    sentinels = (
        "RAW_API_KEY_sk-private-123",
        "UkFXX0JBU0U2NF9CTE9C",
        "RAW_FULL_DRAFT_PRIVATE",
        "RAW_PROVIDER_INTERNAL_DETAIL",
    )

    class ProviderLeakError(Exception):
        def __init__(self) -> None:
            super().__init__(sentinels[3])
            self.status_code = 429
            self.code = "insufficient_quota"
            self.api_key = sentinels[0]
            self.blob = sentinels[1]
            self.full_draft = {"private": sentinels[2]}
            self.response = _sdk_response()

    raw_provider = ProviderLeakError()
    provider_client = OpenAIMechanicsModelerClient(
        _config(),
        sdk_client=SimpleNamespace(
            responses=FakeResponsesAPI(error=raw_provider)
        ),
    )
    provider_caught = _capture_exception(
        provider_client.model, "Caller source must also be scrubbed."
    )
    assert isinstance(provider_caught, ModelerUnavailableError)
    assert provider_caught.code is ModelerErrorCode.quota
    assert provider_caught.response_status == 429
    assert provider_caught.usage is not None
    _assert_exception_graph_is_sanitized(
        provider_caught,
        forbidden_objects=(raw_provider,),
        forbidden_text=sentinels,
    )

    raw_payload = _draft_payload()
    raw_payload["entities"][0]["label"] = "|".join(sentinels[:3])
    del raw_payload["entities"][0]["entity_id"]
    with pytest.raises(ValidationError) as raw_validation_caught:
        MechanicsProblemDraftV1.model_validate(raw_payload)
    raw_validation = raw_validation_caught.value
    validation_client = OpenAIMechanicsModelerClient(
        _config(),
        sdk_client=SimpleNamespace(
            responses=FakeResponsesAPI(error=raw_validation)
        ),
    )
    validation_caught = _capture_exception(
        validation_client.model, "Raw validation source."
    )
    assert isinstance(validation_caught, ModelerStructuralSchemaError)
    _assert_exception_graph_is_sanitized(
        validation_caught,
        forbidden_objects=(raw_validation,),
        forbidden_text=sentinels,
    )


def test_missing_usage_keeps_conservative_reservation_and_safe_telemetry() -> None:
    fake = FakeModelClient(_response(_draft(), usage=ModelerUsage(), usage_available=False))
    outcome = MechanicsModeler(_config(), client=fake).model("Usage absent.")
    assert outcome.accepted
    assert outcome.telemetry.usage_missing_attempts == 1
    assert outcome.telemetry.conservative_cost_usd > 0
    assert outcome.telemetry.measured_cost_usd == 0
    unsafe_fragments = ("problem_text", "image_data", "response", "prompt_text", "output_text")
    outcome_names = {item.name for item in fields(MechanicsModelerOutcome)}
    telemetry_names = {item.name for item in fields(ModelerTelemetry)}
    assert not any(fragment in name for fragment in unsafe_fragments for name in outcome_names | telemetry_names)


def test_prompt_is_enum_generated_example_free_and_explicitly_non_authoritative() -> None:
    prompt = load_modeler_prompt()
    assert "EntityPrimitive" in prompt
    assert "Do not calculate" in prompt
    assert "untrusted data" in prompt
    assert "metadata.system_type" in prompt and "routing" in prompt
    assert "example" not in prompt.lower()


def test_modeler_modules_have_no_legacy_parser_or_answer_driven_runtime(monkeypatch) -> None:
    mechanics_dir = Path(inspect.getfile(MechanicsModeler)).parent
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in mechanics_dir.glob("modeler*.py")
    )
    forbidden = (
        "engine.textbook_parser",
        "case" + "_id",
        "expected" + "_answer",
        "corpus" + "_family",
        "sym" + "pify(",
        "ev" + "al(",
    )
    assert not any(token in source for token in forbidden)
    assert "if metadata.system_type" not in source
    assert ".system_type.value" not in source
    assert "responses.parse" in source
    assert '"store": False' in source and '"tools": []' in source
