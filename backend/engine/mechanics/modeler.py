"""One-call mechanics modeler orchestration with one bounded full repair."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import time
from typing import Callable, Collection, Mapping

from engine.mechanics.contracts import (
    DRAFT_SCHEMA_VERSION,
    IR_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
)
from engine.mechanics.modeler_cache import (
    DEFAULT_MECHANICS_CACHE_COMPATIBILITY_VERSIONS,
    MECHANICS_MODELER_VERSION,
    MechanicsCacheCompatibilityVersions,
    MechanicsModelerCache,
    build_modeler_cache_key,
)
from engine.mechanics.modeler_client import (
    MechanicsStructuredClient,
    OpenAIMechanicsModelerClient,
    modeler_request_input_token_ceiling,
)
from engine.mechanics.modeler_config import MechanicsModelerConfig
from engine.mechanics.modeler_errors import (
    MechanicsModelerError,
    ModelerErrorCode,
    ModelerRepairIssue,
)
from engine.mechanics.modeler_inputs import (
    ModelerFigureDisabledError,
    ModelerImageInput,
    ModelerInputBudgetError,
    ModelerInputError,
    VerifiedModelerInput,
    normalized_text,
    verify_modeler_input,
)
from engine.mechanics.modeler_prompt import (
    MECHANICS_MODELER_PROMPT_VERSION,
    modeler_prompt_hash,
)
from engine.mechanics.modeler_repair import (
    repair_issues_from_validation,
    sanitize_repair_issues,
)
from engine.mechanics.modeler_telemetry import (
    ModelerUsage,
    UnpricedModelError,
    aggregate_usage,
    conservative_attempt_cost,
    resolve_price_schedule,
)
from engine.mechanics.normalization import (
    NORMALIZATION_POLICY_VERSION,
    VALIDATION_POLICY_VERSION,
    NormalizationResult,
    normalize_draft,
)
from engine.mechanics.validation import (
    AssumptionAuthorization,
    CorrectionAuthorization,
    ValidationTerminal,
)


class ModelerTerminal(str, Enum):
    accepted = "accepted"
    needs_figure = "needs_figure"
    needs_confirmation = "needs_confirmation"
    insufficient_information = "insufficient_information"
    unsupported = "unsupported"
    invalid = "invalid"
    disabled = "disabled"
    budget_exceeded = "budget_exceeded"
    refused = "refused"
    unavailable = "unavailable"


_VALIDATION_TERMINALS = {
    ValidationTerminal.accepted: ModelerTerminal.accepted,
    ValidationTerminal.needs_figure: ModelerTerminal.needs_figure,
    ValidationTerminal.needs_confirmation: ModelerTerminal.needs_confirmation,
    ValidationTerminal.insufficient_information: ModelerTerminal.insufficient_information,
    ValidationTerminal.unsupported: ModelerTerminal.unsupported,
    ValidationTerminal.invalid: ModelerTerminal.invalid,
}


@dataclass(frozen=True)
class ModelerAttemptDiagnostic:
    attempt_number: int
    phase: str
    result_code: str
    usage_available: bool
    model_latency_ms: float
    response_status: int | str | None = None
    repair_issues: tuple[ModelerRepairIssue, ...] = ()


@dataclass(frozen=True)
class ModelerTelemetry:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    request_attempts: int
    retry_count: int
    measured_cost_usd: float
    measured_cost_known: bool
    conservative_cost_usd: float
    model_latency_ms: float
    normalization_latency_ms: float
    usage_missing_attempts: int
    terminal_status: str


@dataclass(frozen=True)
class MechanicsModelerOutcome:
    terminal: ModelerTerminal
    normalization: NormalizationResult | None
    ir: MechanicsProblemIRV1 | None
    calculation_fingerprint: str | None
    model: str
    modeler_version: str
    prompt_version: str
    prompt_sha256: str
    draft_schema_version: str
    ir_schema_version: str
    validation_policy_version: str
    normalization_policy_version: str
    source_text_sha256: str
    normalized_text_sha256: str
    image_content_sha256: tuple[str, ...]
    cache_hit: bool
    telemetry: ModelerTelemetry
    attempt_diagnostics: tuple[ModelerAttemptDiagnostic, ...]
    failure_code: str | None = None

    @property
    def accepted(self) -> bool:
        return (
            self.terminal is ModelerTerminal.accepted
            and self.normalization is not None
            and self.normalization.accepted
            and self.ir is not None
            and self.calculation_fingerprint is not None
        )

    @property
    def normalization_result(self) -> NormalizationResult | None:
        return self.normalization


Normalizer = Callable[..., NormalizationResult]


class MechanicsModeler:
    """Model once, validate/normalize deterministically, repair at most once."""

    def __init__(
        self,
        config: MechanicsModelerConfig,
        *,
        client: MechanicsStructuredClient | None = None,
        cache: MechanicsModelerCache | None = None,
        normalizer: Normalizer = normalize_draft,
        perf_counter: Callable[[], float] = time.perf_counter,
        cache_compatibility_versions: MechanicsCacheCompatibilityVersions = (
            DEFAULT_MECHANICS_CACHE_COMPATIBILITY_VERSIONS
        ),
    ) -> None:
        self.config = config
        self._client = client
        self._normalizer = normalizer
        self._perf_counter = perf_counter
        self._cache_compatibility_versions = cache_compatibility_versions
        if cache is not None:
            self._cache = cache
        elif config.cache_enabled:
            self._cache = MechanicsModelerCache(
                path=config.cache_path,
                ttl_seconds=config.cache_ttl_seconds,
                l1_entries=config.cache_l1_entries,
                l2_entries=config.cache_l2_entries,
            )
        else:
            self._cache = None

    def model(
        self,
        problem_text: str,
        *,
        images: tuple[ModelerImageInput, ...] = (),
        approved_assumption_ids: Collection[str] = (),
        authorized_corrections: Mapping[str, CorrectionAuthorization] | None = None,
        authorized_assumptions: Mapping[str, AssumptionAuthorization] | None = None,
        confirmed_figure_evidence_ids: Collection[str] = (),
        correction_revision: int = 0,
        modeling_input_identity: str | None = None,
        cost_budget_usd: float | None = None,
    ) -> MechanicsModelerOutcome:
        if not isinstance(images, tuple):
            return self._preflight_failure(
                problem_text,
                (),
                ModelerTerminal.invalid,
                "images_must_be_tuple",
            )
        selected_model = self.config.selected_model(has_images=bool(images))
        if not self.config.active:
            return self._empty_outcome(
                terminal=ModelerTerminal.disabled,
                model=selected_model,
                problem_text=problem_text,
                image_hashes=self._safe_image_hashes(images),
                failure_code="modeler_disabled",
            )
        if not isinstance(correction_revision, int) or isinstance(correction_revision, bool) or not 0 <= correction_revision <= 1_000_000:
            return self._preflight_failure(
                problem_text, images, ModelerTerminal.invalid, "correction_revision_invalid"
            )
        if modeling_input_identity is not None and (
            not isinstance(modeling_input_identity, str)
            or not modeling_input_identity
            or len(modeling_input_identity) > 256
        ):
            return self._preflight_failure(
                problem_text, images, ModelerTerminal.invalid, "modeling_input_identity_invalid"
            )
        try:
            verified = verify_modeler_input(problem_text, images, self.config)
        except ModelerFigureDisabledError as exc:
            return self._preflight_failure(
                problem_text, images, ModelerTerminal.needs_figure, exc.code
            )
        except ModelerInputBudgetError as exc:
            return self._preflight_failure(
                problem_text, images, ModelerTerminal.budget_exceeded, exc.code
            )
        except ModelerInputError as exc:
            return self._preflight_failure(
                problem_text, images, ModelerTerminal.invalid, exc.code
            )

        cache_key = build_modeler_cache_key(
            verified,
            self.config,
            correction_revision=correction_revision,
            modeling_input_identity=modeling_input_identity,
            compatibility_versions=self._cache_compatibility_versions,
        )
        if self._cache is not None and self.config.cache_enabled:
            try:
                cached = self._cache.get(cache_key)
            except Exception:
                cached = None
            if cached is not None:
                draft = self._stamp_trusted_metadata(
                    cached.draft,
                    verified,
                    selected_model,
                    correction_revision,
                )
                started = self._perf_counter()
                normalization = self._normalize(
                    problem_text,
                    draft,
                    approved_assumption_ids=approved_assumption_ids,
                    authorized_corrections=authorized_corrections,
                    authorized_assumptions=authorized_assumptions,
                    confirmed_figure_evidence_ids=confirmed_figure_evidence_ids,
                )
                normalization_ms = (self._perf_counter() - started) * 1000.0
                if normalization is None:
                    return self._outcome(
                        terminal=ModelerTerminal.invalid,
                        verified=verified,
                        model=selected_model,
                        normalization=None,
                        cache_hit=True,
                        usages=(),
                        reservations=(),
                        normalization_latency_ms=normalization_ms,
                        diagnostics=(),
                        failure_code="normalization_failed",
                    )
                return self._outcome(
                    terminal=_VALIDATION_TERMINALS[normalization.terminal],
                    verified=verified,
                    model=selected_model,
                    normalization=normalization,
                    cache_hit=True,
                    usages=(),
                    reservations=(),
                    normalization_latency_ms=normalization_ms,
                    diagnostics=(),
                )

        budget = self.config.max_total_cost_usd
        if cost_budget_usd is not None:
            if not isinstance(cost_budget_usd, (int, float)) or isinstance(cost_budget_usd, bool):
                return self._outcome(
                    terminal=ModelerTerminal.budget_exceeded,
                    verified=verified,
                    model=selected_model,
                    normalization=None,
                    cache_hit=False,
                    usages=(),
                    reservations=(),
                    normalization_latency_ms=0.0,
                    diagnostics=(),
                    failure_code="cost_budget_invalid",
                )
            if not math.isfinite(float(cost_budget_usd)):
                return self._outcome(
                    terminal=ModelerTerminal.budget_exceeded,
                    verified=verified,
                    model=selected_model,
                    normalization=None,
                    cache_hit=False,
                    usages=(),
                    reservations=(),
                    normalization_latency_ms=0.0,
                    diagnostics=(),
                    failure_code="cost_budget_invalid",
                )
            budget = min(budget, max(float(cost_budget_usd), 0.0))

        try:
            self._reservation(selected_model, verified, repair_issues=())
        except UnpricedModelError:
            return self._outcome(
                terminal=ModelerTerminal.budget_exceeded,
                verified=verified,
                model=selected_model,
                normalization=None,
                cache_hit=False,
                usages=(),
                reservations=(),
                normalization_latency_ms=0.0,
                diagnostics=(),
                failure_code="model_pricing_unavailable",
            )

        client = self._client
        if client is None:
            try:
                client = OpenAIMechanicsModelerClient(self.config)
            except MechanicsModelerError as exc:
                return self._outcome(
                    terminal=ModelerTerminal.unavailable,
                    verified=verified,
                    model=selected_model,
                    normalization=None,
                    cache_hit=False,
                    usages=(),
                    reservations=(),
                    normalization_latency_ms=0.0,
                    diagnostics=(),
                    failure_code=exc.code.value,
                )
            self._client = client

        usages: list[ModelerUsage] = []
        reservations: list[float] = []
        diagnostics: list[ModelerAttemptDiagnostic] = []
        normalization_latency_ms = 0.0
        last_normalization: NormalizationResult | None = None
        repair_issues: tuple[ModelerRepairIssue, ...] = ()
        first_cause: str | None = None

        for attempt_number in range(1, self.config.max_retries + 2):
            phase = "initial" if attempt_number == 1 else "repair"
            try:
                reservation = self._reservation(
                    selected_model, verified, repair_issues=repair_issues
                )
            except UnpricedModelError:
                return self._outcome(
                    terminal=ModelerTerminal.budget_exceeded,
                    verified=verified,
                    model=selected_model,
                    normalization=last_normalization,
                    cache_hit=False,
                    usages=tuple(usages),
                    reservations=tuple(reservations),
                    normalization_latency_ms=normalization_latency_ms,
                    diagnostics=tuple(diagnostics),
                    failure_code="model_pricing_unavailable",
                )
            if sum(reservations) + reservation > budget:
                return self._outcome(
                    terminal=ModelerTerminal.budget_exceeded,
                    verified=verified,
                    model=selected_model,
                    normalization=last_normalization,
                    cache_hit=False,
                    usages=tuple(usages),
                    reservations=tuple(reservations),
                    normalization_latency_ms=normalization_latency_ms,
                    diagnostics=tuple(diagnostics),
                    failure_code="cost_budget_exceeded",
                )
            reservations.append(reservation)
            call_started = self._perf_counter()
            try:
                response = client.model(
                    problem_text,
                    images=images,
                    repair_issues=repair_issues,
                )
            except MechanicsModelerError as exc:
                latency_ms = (self._perf_counter() - call_started) * 1000.0
                usage_available = isinstance(exc.usage, ModelerUsage)
                if usage_available:
                    usages.append(exc.usage)
                else:
                    usages.append(ModelerUsage())
                safe_issues = sanitize_repair_issues(tuple(exc.repair_issues))
                diagnostics.append(
                    ModelerAttemptDiagnostic(
                        attempt_number=attempt_number,
                        phase=phase,
                        result_code=exc.code.value,
                        usage_available=usage_available,
                        model_latency_ms=latency_ms,
                        response_status=self._safe_status(exc.response_status),
                        repair_issues=safe_issues,
                    )
                )
                cause = f"client:{exc.code.value}"
                can_repair = (
                    attempt_number == 1
                    and self.config.max_retries == 1
                    and exc.repairable
                    and bool(safe_issues)
                    and cause != first_cause
                )
                if can_repair:
                    first_cause = cause
                    repair_issues = safe_issues
                    continue
                terminal = (
                    ModelerTerminal.refused
                    if exc.code in {
                        ModelerErrorCode.refusal,
                        ModelerErrorCode.authority_rejected,
                    }
                    else ModelerTerminal.invalid
                    if exc.code in {
                        ModelerErrorCode.schema_error,
                        ModelerErrorCode.output_incomplete,
                        ModelerErrorCode.output_missing,
                    }
                    else ModelerTerminal.unavailable
                )
                return self._outcome(
                    terminal=terminal,
                    verified=verified,
                    model=selected_model,
                    normalization=last_normalization,
                    cache_hit=False,
                    usages=tuple(usages),
                    reservations=tuple(reservations),
                    normalization_latency_ms=normalization_latency_ms,
                    diagnostics=tuple(diagnostics),
                    failure_code=exc.code.value,
                )
            except Exception:
                latency_ms = (self._perf_counter() - call_started) * 1000.0
                usages.append(ModelerUsage())
                diagnostics.append(
                    ModelerAttemptDiagnostic(
                        attempt_number=attempt_number,
                        phase=phase,
                        result_code="client_unexpected",
                        usage_available=False,
                        model_latency_ms=latency_ms,
                    )
                )
                return self._outcome(
                    terminal=ModelerTerminal.unavailable,
                    verified=verified,
                    model=selected_model,
                    normalization=last_normalization,
                    cache_hit=False,
                    usages=tuple(usages),
                    reservations=tuple(reservations),
                    normalization_latency_ms=normalization_latency_ms,
                    diagnostics=tuple(diagnostics),
                    failure_code="client_unexpected",
                )

            latency_ms = (self._perf_counter() - call_started) * 1000.0
            usages.append(response.usage)
            try:
                draft = self._stamp_trusted_metadata(
                    response.draft,
                    verified,
                    selected_model,
                    correction_revision,
                )
            except Exception:
                diagnostics.append(
                    ModelerAttemptDiagnostic(
                        attempt_number,
                        phase,
                        "structured_draft_invalid",
                        response.usage_available,
                        latency_ms,
                    )
                )
                return self._outcome(
                    terminal=ModelerTerminal.invalid,
                    verified=verified,
                    model=selected_model,
                    normalization=None,
                    cache_hit=False,
                    usages=tuple(usages),
                    reservations=tuple(reservations),
                    normalization_latency_ms=normalization_latency_ms,
                    diagnostics=tuple(diagnostics),
                    failure_code="structured_draft_invalid",
                )
            normalization_started = self._perf_counter()
            last_normalization = self._normalize(
                problem_text,
                draft,
                approved_assumption_ids=approved_assumption_ids,
                authorized_corrections=authorized_corrections,
                authorized_assumptions=authorized_assumptions,
                confirmed_figure_evidence_ids=confirmed_figure_evidence_ids,
            )
            normalization_latency_ms += (
                self._perf_counter() - normalization_started
            ) * 1000.0
            if last_normalization is None:
                diagnostics.append(
                    ModelerAttemptDiagnostic(
                        attempt_number,
                        phase,
                        "normalization_failed",
                        response.usage_available,
                        latency_ms,
                    )
                )
                return self._outcome(
                    terminal=ModelerTerminal.invalid,
                    verified=verified,
                    model=selected_model,
                    normalization=None,
                    cache_hit=False,
                    usages=tuple(usages),
                    reservations=tuple(reservations),
                    normalization_latency_ms=normalization_latency_ms,
                    diagnostics=tuple(diagnostics),
                    failure_code="normalization_failed",
                )
            candidate_repair = (
                repair_issues_from_validation(last_normalization.issues)
                if last_normalization.terminal is ValidationTerminal.invalid
                else ()
            )
            diagnostics.append(
                ModelerAttemptDiagnostic(
                    attempt_number=attempt_number,
                    phase=phase,
                    result_code=last_normalization.terminal.value,
                    usage_available=response.usage_available,
                    model_latency_ms=latency_ms,
                    repair_issues=candidate_repair,
                )
            )
            cause = "validation:" + ",".join(
                sorted({item.code for item in candidate_repair})
            )
            if (
                attempt_number == 1
                and self.config.max_retries == 1
                and candidate_repair
                and cause != first_cause
            ):
                first_cause = cause
                repair_issues = candidate_repair
                continue

            if (
                self._cache is not None
                and self.config.cache_enabled
                and last_normalization.terminal is not ValidationTerminal.invalid
            ):
                try:
                    self._cache.put(cache_key, draft)
                except Exception:
                    pass
            return self._outcome(
                terminal=_VALIDATION_TERMINALS[last_normalization.terminal],
                verified=verified,
                model=selected_model,
                normalization=last_normalization,
                cache_hit=False,
                usages=tuple(usages),
                reservations=tuple(reservations),
                normalization_latency_ms=normalization_latency_ms,
                diagnostics=tuple(diagnostics),
            )

        # The bounded range always returns, but fail closed if altered later.
        return self._outcome(
            terminal=ModelerTerminal.invalid,
            verified=verified,
            model=selected_model,
            normalization=last_normalization,
            cache_hit=False,
            usages=tuple(usages),
            reservations=tuple(reservations),
            normalization_latency_ms=normalization_latency_ms,
            diagnostics=tuple(diagnostics),
            failure_code="repair_budget_exhausted",
        )

    def _normalize(
        self,
        problem_text: str,
        draft: MechanicsProblemDraftV1,
        *,
        approved_assumption_ids: Collection[str],
        authorized_corrections: Mapping[str, CorrectionAuthorization] | None,
        authorized_assumptions: Mapping[str, AssumptionAuthorization] | None,
        confirmed_figure_evidence_ids: Collection[str],
    ) -> NormalizationResult | None:
        try:
            result = self._normalizer(
                problem_text,
                draft,
                approved_assumption_ids=approved_assumption_ids,
                authorized_corrections=authorized_corrections,
                authorized_assumptions=authorized_assumptions,
                confirmed_figure_evidence_ids=confirmed_figure_evidence_ids,
            )
        except Exception:
            return None
        if result.terminal is ValidationTerminal.accepted and not result.accepted:
            return None
        return result

    @staticmethod
    def _stamp_trusted_metadata(
        draft: MechanicsProblemDraftV1,
        verified: VerifiedModelerInput,
        selected_model: str,
        correction_revision: int,
    ) -> MechanicsProblemDraftV1:
        metadata = draft.metadata.model_copy(
            update={
                "correction_revision": correction_revision,
                "model_id": "mechanics_modeler",
                "model_hash": hashlib.sha256(selected_model.encode("utf-8")).hexdigest(),
                "prompt_hash": modeler_prompt_hash(),
                "source_text_sha256": verified.source_text_sha256,
            }
        )
        stamped = draft.model_copy(
            update={"metadata": metadata, "source_assets": list(verified.assets)}
        )
        return MechanicsProblemDraftV1.model_validate(
            stamped.model_dump(mode="python")
        )

    def _reservation(
        self,
        model: str,
        verified: VerifiedModelerInput,
        *,
        repair_issues: tuple[ModelerRepairIssue, ...],
    ) -> float:
        schedule = resolve_price_schedule(
            model, self.config.model_price_schedule
        )
        input_ceiling = modeler_request_input_token_ceiling(
            verified.problem_text,
            verified.images,
            repair_issues,
            model=model,
            reasoning_effort=self.config.reasoning_effort,
            max_output_tokens=self.config.max_output_tokens,
            image_tokens_per_image_upper_bound=(
                schedule.image_tokens_per_image_upper_bound
            ),
        )
        return conservative_attempt_cost(
            model,
            input_token_ceiling=input_ceiling,
            max_output_tokens=self.config.max_output_tokens,
            supplied_schedule=self.config.model_price_schedule,
        )

    @staticmethod
    def _safe_status(value: object) -> int | str | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value if 100 <= value <= 599 else None
        if value in {"completed", "incomplete", "failed", "cancelled"}:
            return str(value)
        return None

    def _outcome(
        self,
        *,
        terminal: ModelerTerminal,
        verified: VerifiedModelerInput,
        model: str,
        normalization: NormalizationResult | None,
        cache_hit: bool,
        usages: tuple[ModelerUsage, ...],
        reservations: tuple[float, ...],
        normalization_latency_ms: float,
        diagnostics: tuple[ModelerAttemptDiagnostic, ...],
        failure_code: str | None = None,
    ) -> MechanicsModelerOutcome:
        total_usage = aggregate_usage(
            model,
            usages,
            supplied_schedule=self.config.model_price_schedule,
        )
        request_attempts = len(diagnostics)
        accepted = normalization is not None and normalization.accepted
        ir = normalization.ir if accepted else None
        fingerprint = normalization.calculation_fingerprint if accepted else None
        telemetry = ModelerTelemetry(
            input_tokens=total_usage.input_tokens,
            cached_input_tokens=total_usage.cached_input_tokens,
            output_tokens=total_usage.output_tokens,
            reasoning_tokens=total_usage.reasoning_tokens,
            request_attempts=request_attempts,
            retry_count=max(request_attempts - 1, 0),
            measured_cost_usd=total_usage.measured_cost_usd,
            measured_cost_known=total_usage.cost_known,
            conservative_cost_usd=round(sum(reservations), 9),
            model_latency_ms=round(
                sum(item.model_latency_ms for item in diagnostics), 3
            ),
            normalization_latency_ms=round(normalization_latency_ms, 3),
            usage_missing_attempts=sum(
                not item.usage_available for item in diagnostics
            ),
            terminal_status=terminal.value,
        )
        return MechanicsModelerOutcome(
            terminal=terminal,
            normalization=normalization,
            ir=ir,
            calculation_fingerprint=fingerprint,
            model=model,
            modeler_version=MECHANICS_MODELER_VERSION,
            prompt_version=MECHANICS_MODELER_PROMPT_VERSION,
            prompt_sha256=modeler_prompt_hash(),
            draft_schema_version=DRAFT_SCHEMA_VERSION,
            ir_schema_version=IR_SCHEMA_VERSION,
            validation_policy_version=VALIDATION_POLICY_VERSION,
            normalization_policy_version=NORMALIZATION_POLICY_VERSION,
            source_text_sha256=verified.source_text_sha256,
            normalized_text_sha256=verified.normalized_text_sha256,
            image_content_sha256=tuple(
                image.content_sha256 for image in verified.images
            ),
            cache_hit=cache_hit,
            telemetry=telemetry,
            attempt_diagnostics=diagnostics,
            failure_code=failure_code,
        )

    def _empty_outcome(
        self,
        *,
        terminal: ModelerTerminal,
        model: str,
        problem_text: object,
        image_hashes: tuple[str, ...],
        failure_code: str,
    ) -> MechanicsModelerOutcome:
        text = problem_text if isinstance(problem_text, str) else ""
        exact = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        normalized = hashlib.sha256(
            normalized_text(text).encode("utf-8", errors="replace")
        ).hexdigest()
        telemetry = ModelerTelemetry(
            0, 0, 0, 0, 0, 0, 0.0, False, 0.0, 0.0, 0.0, 0, terminal.value
        )
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
            source_text_sha256=exact,
            normalized_text_sha256=normalized,
            image_content_sha256=image_hashes,
            cache_hit=False,
            telemetry=telemetry,
            attempt_diagnostics=(),
            failure_code=failure_code,
        )

    def _preflight_failure(
        self,
        problem_text: object,
        images: tuple[ModelerImageInput, ...],
        terminal: ModelerTerminal,
        failure_code: str,
    ) -> MechanicsModelerOutcome:
        return self._empty_outcome(
            terminal=terminal,
            model=self.config.selected_model(has_images=bool(images)),
            problem_text=problem_text,
            image_hashes=self._safe_image_hashes(images),
            failure_code=failure_code,
        )

    @staticmethod
    def _safe_image_hashes(images: tuple[object, ...]) -> tuple[str, ...]:
        return tuple(
            hashlib.sha256(image.data).hexdigest()
            for image in images
            if isinstance(image, ModelerImageInput)
            and isinstance(image.data, bytes)
        )


__all__ = [
    "MechanicsModeler",
    "MechanicsModelerOutcome",
    "ModelerAttemptDiagnostic",
    "ModelerTelemetry",
    "ModelerTerminal",
]
