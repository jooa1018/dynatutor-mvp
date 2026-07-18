from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Protocol

from pydantic import ValidationError

from engine.textbook_parser.cache import CacheEntry, ParserCache, build_cache_key
from engine.textbook_parser.config import TextbookParserConfig
from engine.textbook_parser.contracts import TextbookProblemParseV1
from engine.textbook_parser.errors import (
    ErrorCode,
    ParserBudgetError,
    TextbookParserError,
)
from engine.textbook_parser.openai_client import (
    OpenAITextbookParserClient,
    StructuredParseResponse,
)
from engine.textbook_parser.prompt import PROMPT_VERSION, load_prompt
from engine.textbook_parser.telemetry import (
    UsageSummary,
    aggregate_usage,
    conservative_attempt_cost_upper_bound,
    text_hash,
)
from engine.textbook_parser.validation import (
    ParseDecisionStatus,
    ValidatedParse,
    validate_parse,
)
from engine.textbook_parser.validators.safety import validate_payload_authority


REPAIRABLE_CODES = frozenset(
    {
        ErrorCode.schema_error.value,
        ErrorCode.invalid_reference.value,
        ErrorCode.evidence_quote_missing.value,
        ErrorCode.evidence_occurrence_missing.value,
    }
)


class StructuredParserClient(Protocol):
    def parse(
        self, problem_text: str, *, repair_error_codes: tuple[str, ...] = ()
    ) -> StructuredParseResponse: ...


@dataclass(frozen=True)
class ValidationErrorDetail:
    field_path: tuple[str | int, ...]
    error_type: str

    def to_dict(self) -> dict[str, object]:
        return {
            "field_path": list(self.field_path),
            "error_type": self.error_type,
        }


@dataclass(frozen=True)
class AttemptDiagnostic:
    attempt_number: int
    phase: str
    exception_category: str
    validation_errors: tuple[ValidationErrorDetail, ...] = ()
    usage_unavailable: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt_number": self.attempt_number,
            "phase": self.phase,
            "exception_category": self.exception_category,
            "validation_errors": [
                item.to_dict() for item in self.validation_errors
            ],
            "usage_unavailable": self.usage_unavailable,
        }


@dataclass(frozen=True)
class ParseOutcome:
    status: ParseDecisionStatus
    validated: ValidatedParse | None
    model: str
    prompt_version: str
    usage: UsageSummary
    cache_hit: bool
    retry_count: int
    request_attempt_count: int
    problem_hash: str
    parser_latency_ms: float
    validation_latency_ms: float
    conservative_cost_upper_bound_usd: float
    usage_unavailable: bool = False
    attempt_diagnostics: tuple[AttemptDiagnostic, ...] = ()
    repair_error_codes: tuple[str, ...] = ()
    failure_code: str | None = None

    def diagnostic_context(self) -> dict[str, object]:
        selected = None
        selected_candidate = None
        if self.validated is not None:
            selected = next(
                (
                    item
                    for item in self.validated.candidates
                    if item.candidate_id == self.validated.selected_candidate_id
                ),
                None,
            )
            if selected is None and self.validated.candidates:
                selected = self.validated.candidates[0]
            selected_candidate = self.validated.selected_candidate
            if selected_candidate is None and selected is not None:
                selected_candidate = next(
                    (
                        item
                        for item in self.validated.parse.interpretation_candidates
                        if item.candidate_id == selected.candidate_id
                    ),
                    None,
                )
        capability = selected.capability if selected is not None else None
        score = selected.score if selected is not None else None
        binding = capability.binding.to_dict() if capability is not None else {}
        return {
            "selected_system_type": (
                selected_candidate.system_type
                if selected_candidate is not None
                else None
            ),
            "selected_candidate_id_present": (
                self.validated is not None
                and self.validated.selected_candidate_id is not None
            ),
            "selected_solver": (
                capability.solver_id if capability is not None else None
            ),
            "missing_inputs": (
                list(capability.missing_inputs) if capability is not None else []
            ),
            "binding_completeness": binding.get("completeness"),
            "validation_veto_codes": (
                list(score.veto_codes) if score is not None else []
            ),
        }

    def public_summary(self) -> dict[str, Any]:
        parse = self.validated.parse if self.validated is not None else None
        validation = (
            self.validated.to_summary() if self.validated is not None else {}
        )
        evaluations = {
            item["assumption_id"]: item
            for item in validation.get("assumption_evaluations", [])
        }
        accepted_ids = set(validation.get("accepted_assumption_ids", []))
        accepted_assumptions = []
        rejected_assumptions = []
        if parse is not None:
            for proposal in parse.assumption_proposals:
                payload = proposal.model_dump(mode="json")
                payload["evaluation"] = evaluations.get(proposal.assumption_id)
                if proposal.assumption_id in accepted_ids:
                    accepted_assumptions.append(payload)
                else:
                    rejected_assumptions.append(payload)
        return {
            "status": self.status.value,
            "source": "gpt_structured_outputs",
            "schema": (
                parse.schema if parse is not None else "dynatutor.textbook_parse"
            ),
            "version": parse.version if parse is not None else "1.1",
            "model": self.model,
            "prompt_version": self.prompt_version,
            "entities": [
                item.model_dump(mode="json") for item in parse.entities
            ]
            if parse
            else [],
            "segments": [
                item.model_dump(mode="json") for item in parse.motion_segments
            ]
            if parse
            else [],
            "events": [
                item.model_dump(mode="json") for item in parse.events
            ]
            if parse
            else [],
            "explicit_facts": [
                item.model_dump(mode="json") for item in parse.explicit_facts
            ]
            if parse
            else [],
            "relations": [
                item.model_dump(mode="json") for item in parse.relations
            ]
            if parse
            else [],
            "assumption_proposals": [
                item.model_dump(mode="json") for item in parse.assumption_proposals
            ]
            if parse
            else [],
            "accepted_assumptions": accepted_assumptions,
            "rejected_assumptions": rejected_assumptions,
            "assumption_evaluations": validation.get(
                "assumption_evaluations", []
            ),
            "queries": [
                item.model_dump(mode="json") for item in parse.queries
            ]
            if parse
            else [],
            "interpretation_candidates": [
                item.model_dump(mode="json")
                for item in parse.interpretation_candidates
            ]
            if parse
            else [],
            "ambiguities": [
                item.model_dump(mode="json") for item in parse.ambiguities
            ]
            if parse
            else [],
            "figure_dependency": (
                parse.figure_dependency.model_dump(mode="json")
                if parse
                else None
            ),
            "warnings": [
                item
                for item in validation.get("issues", [])
                if item.get("severity") in {"warning", "error", "critical"}
            ],
            "usage_summary": self.usage.to_dict(),
            "usage_unavailable": self.usage_unavailable,
            "conservative_cost_upper_bound_usd": (
                self.conservative_cost_upper_bound_usd
            ),
            "parser_latency_ms": self.parser_latency_ms,
            "validation_latency_ms": self.validation_latency_ms,
            "total_latency_ms": round(
                self.parser_latency_ms + self.validation_latency_ms, 3
            ),
            "cache_hit": self.cache_hit,
            "request_attempt_count": self.request_attempt_count,
            "retry_count": self.retry_count,
            "repair_error_codes": list(self.repair_error_codes),
            "attempt_diagnostics": [
                item.to_dict() for item in self.attempt_diagnostics
            ],
            "failure_code": self.failure_code,
            **self.diagnostic_context(),
        }


def validate_recorded_payload(
    problem_text: str, payload: dict[str, Any]
) -> ValidatedParse:
    authority_issues = validate_payload_authority(payload)
    if authority_issues:
        raise ValueError(authority_issues[0].message)
    parse = TextbookProblemParseV1.model_validate(payload)
    return validate_parse(problem_text, parse)


def _exception_usage(exc: Exception) -> UsageSummary | None:
    usage = getattr(exc, "usage_summary", None)
    return usage if isinstance(usage, UsageSummary) else None


def _sanitized_exception(
    exc: Exception,
    *,
    attempt_number: int,
    phase: str,
    usage_unavailable: bool,
) -> AttemptDiagnostic:
    validation_errors: tuple[ValidationErrorDetail, ...] = ()
    if isinstance(exc, ValidationError):
        category = "pydantic_validation_error"
        validation_errors = tuple(
            ValidationErrorDetail(
                field_path=tuple(item.get("loc", ())),
                error_type=str(item.get("type", "validation_error")),
            )
            for item in exc.errors()
        )
    elif isinstance(exc, TextbookParserError):
        category = exc.code.value
    elif isinstance(exc, ValueError):
        category = "value_error"
    else:
        category = "unexpected_exception"
    return AttemptDiagnostic(
        attempt_number=attempt_number,
        phase=phase,
        exception_category=category,
        validation_errors=validation_errors,
        usage_unavailable=usage_unavailable,
    )


def _failure_status(code: str) -> ParseDecisionStatus:
    if code in {
        ErrorCode.parser_unavailable.value,
        ErrorCode.parser_timeout.value,
        ErrorCode.parser_rate_limited.value,
        ErrorCode.parser_quota.value,
        ErrorCode.parser_auth.value,
        ErrorCode.parser_budget_exceeded.value,
    }:
        return ParseDecisionStatus.parser_unavailable
    return ParseDecisionStatus.parser_error


def _failure_outcome(
    *,
    config: TextbookParserConfig,
    code: str,
    problem_digest: str,
    attempt_usages: list[UsageSummary],
    unknown_reservations: list[float],
    request_attempt_count: int,
    parser_latency_ms: float,
    validation_latency_ms: float,
    diagnostics: list[AttemptDiagnostic],
    repair_error_codes: tuple[str, ...] = (),
    validated: ValidatedParse | None = None,
) -> ParseOutcome:
    usage = aggregate_usage(config.model, *attempt_usages)
    return ParseOutcome(
        status=_failure_status(code),
        validated=validated,
        model=config.model,
        prompt_version=PROMPT_VERSION,
        usage=usage,
        cache_hit=False,
        retry_count=max(request_attempt_count - 1, 0),
        request_attempt_count=request_attempt_count,
        problem_hash=problem_digest,
        parser_latency_ms=round(parser_latency_ms, 3),
        validation_latency_ms=round(validation_latency_ms, 3),
        conservative_cost_upper_bound_usd=round(
            usage.estimated_cost_usd + sum(unknown_reservations), 9
        ),
        usage_unavailable=bool(unknown_reservations),
        attempt_diagnostics=tuple(diagnostics),
        repair_error_codes=repair_error_codes,
        failure_code=code,
    )


def parse_textbook_problem(
    problem_text: str,
    *,
    config: TextbookParserConfig | None = None,
    client: StructuredParserClient | None = None,
    cache: ParserCache | None = None,
    cost_budget_usd: float | None = None,
) -> ParseOutcome:
    config = config or TextbookParserConfig.from_env()
    if not problem_text.strip() or len(problem_text) > config.max_problem_chars:
        return _failure_outcome(
            config=config,
            code=ErrorCode.parser_budget_exceeded.value,
            problem_digest=text_hash(""),
            attempt_usages=[],
            unknown_reservations=[],
            request_attempt_count=0,
            parser_latency_ms=0.0,
            validation_latency_ms=0.0,
            diagnostics=[],
        )
    from engine.extraction.normalizer import normalize

    normalized = normalize(problem_text)
    problem_digest = text_hash(normalized)
    cache = cache or ParserCache(
        path=config.cache_path,
        ttl_seconds=config.cache_ttl_seconds,
        l1_entries=config.cache_l1_entries,
        l2_entries=config.cache_l2_entries,
    )
    cache_key = build_cache_key(problem_text, config.model)
    cached = cache.get(cache_key)
    if cached is not None:
        validation_started = time.perf_counter()
        validated = validate_parse(problem_text, cached.parse)
        return ParseOutcome(
            status=validated.status,
            validated=validated,
            model=cached.model,
            prompt_version=PROMPT_VERSION,
            usage=cached.usage,
            cache_hit=True,
            retry_count=0,
            request_attempt_count=0,
            problem_hash=problem_digest,
            parser_latency_ms=0.0,
            validation_latency_ms=round(
                (time.perf_counter() - validation_started) * 1000, 3
            ),
            conservative_cost_upper_bound_usd=0.0,
        )

    attempt_usages: list[UsageSummary] = []
    unknown_reservations: list[float] = []
    diagnostics: list[AttemptDiagnostic] = []
    request_attempt_count = 0
    parser_latency_ms = 0.0
    validation_latency_ms = 0.0
    try:
        parser_client = client or OpenAITextbookParserClient(config)
    except TextbookParserError as exc:
        return _failure_outcome(
            config=config,
            code=exc.code.value,
            problem_digest=problem_digest,
            attempt_usages=attempt_usages,
            unknown_reservations=unknown_reservations,
            request_attempt_count=request_attempt_count,
            parser_latency_ms=parser_latency_ms,
            validation_latency_ms=validation_latency_ms,
            diagnostics=diagnostics,
        )
    prompt_character_budget = len(load_prompt()) + len(problem_text)

    def request(
        *,
        repair_error_codes: tuple[str, ...] = (),
        phase: str,
    ) -> StructuredParseResponse:
        nonlocal request_attempt_count, parser_latency_ms
        repair_overhead = (
            512 + sum(len(item) for item in repair_error_codes)
            if repair_error_codes
            else 0
        )
        reservation = conservative_attempt_cost_upper_bound(
            config.model,
            input_character_budget=prompt_character_budget + repair_overhead,
            max_output_tokens=config.max_output_tokens,
        )
        current_upper_bound = (
            aggregate_usage(config.model, *attempt_usages).estimated_cost_usd
            + sum(unknown_reservations)
        )
        if (
            cost_budget_usd is not None
            and current_upper_bound + reservation > cost_budget_usd
        ):
            raise ParserBudgetError(
                "conservative request reservation exceeds parser cost budget"
            )

        request_attempt_count += 1
        request_started = time.perf_counter()
        try:
            response = parser_client.parse(
                problem_text, repair_error_codes=repair_error_codes
            )
        except (TextbookParserError, ValidationError, ValueError) as exc:
            recovered = _exception_usage(exc)
            if recovered is not None:
                attempt_usages.append(recovered)
            else:
                unknown_reservations.append(reservation)
            diagnostics.append(
                _sanitized_exception(
                    exc,
                    attempt_number=request_attempt_count,
                    phase=phase,
                    usage_unavailable=recovered is None,
                )
            )
            raise
        finally:
            parser_latency_ms += (
                time.perf_counter() - request_started
            ) * 1000
        if response.usage_available:
            attempt_usages.append(response.usage)
        else:
            unknown_reservations.append(reservation)
        return response

    try:
        structured = request(phase="initial_schema_parse")
    except TextbookParserError as exc:
        return _failure_outcome(
            config=config,
            code=exc.code.value,
            problem_digest=problem_digest,
            attempt_usages=attempt_usages,
            unknown_reservations=unknown_reservations,
            request_attempt_count=request_attempt_count,
            parser_latency_ms=parser_latency_ms,
            validation_latency_ms=validation_latency_ms,
            diagnostics=diagnostics,
        )
    except (ValidationError, ValueError):
        if config.max_retries != 1:
            return _failure_outcome(
                config=config,
                code=ErrorCode.schema_error.value,
                problem_digest=problem_digest,
                attempt_usages=attempt_usages,
                unknown_reservations=unknown_reservations,
                request_attempt_count=request_attempt_count,
                parser_latency_ms=parser_latency_ms,
                validation_latency_ms=validation_latency_ms,
                diagnostics=diagnostics,
                repair_error_codes=(ErrorCode.schema_error.value,),
            )
        try:
            structured = request(
                repair_error_codes=(ErrorCode.schema_error.value,),
                phase="schema_repair",
            )
        except ParserBudgetError as exc:
            return _failure_outcome(
                config=config,
                code=exc.code.value,
                problem_digest=problem_digest,
                attempt_usages=attempt_usages,
                unknown_reservations=unknown_reservations,
                request_attempt_count=request_attempt_count,
                parser_latency_ms=parser_latency_ms,
                validation_latency_ms=validation_latency_ms,
                diagnostics=diagnostics,
                repair_error_codes=(ErrorCode.schema_error.value,),
            )
        except (TextbookParserError, ValidationError, ValueError):
            return _failure_outcome(
                config=config,
                code=ErrorCode.repair_failed.value,
                problem_digest=problem_digest,
                attempt_usages=attempt_usages,
                unknown_reservations=unknown_reservations,
                request_attempt_count=request_attempt_count,
                parser_latency_ms=parser_latency_ms,
                validation_latency_ms=validation_latency_ms,
                diagnostics=diagnostics,
                repair_error_codes=(ErrorCode.schema_error.value,),
            )
        schema_repair_count = 1
    else:
        schema_repair_count = 0

    validation_started = time.perf_counter()
    validated = validate_parse(problem_text, structured.parsed)
    validation_latency_ms += (
        time.perf_counter() - validation_started
    ) * 1000
    repair_codes = tuple(
        sorted(
            {
                issue.code.value
                for issue in validated.issues
                if issue.code.value in REPAIRABLE_CODES
            }
        )
    )
    if repair_codes and config.max_retries == 1 and schema_repair_count == 0:
        try:
            structured = request(
                repair_error_codes=repair_codes,
                phase="validation_repair",
            )
            validation_started = time.perf_counter()
            validated = validate_parse(problem_text, structured.parsed)
            validation_latency_ms += (
                time.perf_counter() - validation_started
            ) * 1000
        except ParserBudgetError as exc:
            return _failure_outcome(
                config=config,
                code=exc.code.value,
                problem_digest=problem_digest,
                attempt_usages=attempt_usages,
                unknown_reservations=unknown_reservations,
                request_attempt_count=request_attempt_count,
                parser_latency_ms=parser_latency_ms,
                validation_latency_ms=validation_latency_ms,
                diagnostics=diagnostics,
                repair_error_codes=repair_codes,
                validated=validated,
            )
        except (TextbookParserError, ValidationError, ValueError):
            return _failure_outcome(
                config=config,
                code=ErrorCode.repair_failed.value,
                problem_digest=problem_digest,
                attempt_usages=attempt_usages,
                unknown_reservations=unknown_reservations,
                request_attempt_count=request_attempt_count,
                parser_latency_ms=parser_latency_ms,
                validation_latency_ms=validation_latency_ms,
                diagnostics=diagnostics,
                repair_error_codes=repair_codes,
                validated=validated,
            )

    aggregate = aggregate_usage(config.model, *attempt_usages)
    outcome = ParseOutcome(
        status=validated.status,
        validated=validated,
        model=config.model,
        prompt_version=PROMPT_VERSION,
        usage=aggregate,
        cache_hit=False,
        retry_count=max(request_attempt_count - 1, 0),
        request_attempt_count=request_attempt_count,
        problem_hash=problem_digest,
        parser_latency_ms=round(parser_latency_ms, 3),
        validation_latency_ms=round(validation_latency_ms, 3),
        conservative_cost_upper_bound_usd=round(
            aggregate.estimated_cost_usd + sum(unknown_reservations), 9
        ),
        usage_unavailable=bool(unknown_reservations),
        attempt_diagnostics=tuple(diagnostics),
        repair_error_codes=repair_codes,
    )
    cache.put(
        cache_key,
        CacheEntry(
            parse=structured.parsed,
            validation_summary=validated.to_summary(),
            model=config.model,
            usage=aggregate,
            created_at=time.time(),
        ),
    )
    return outcome


__all__ = [
    "AttemptDiagnostic",
    "ParseOutcome",
    "StructuredParserClient",
    "ValidationErrorDetail",
    "parse_textbook_problem",
    "validate_recorded_payload",
]
