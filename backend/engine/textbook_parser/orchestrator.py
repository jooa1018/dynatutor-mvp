from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Protocol

from pydantic import ValidationError

from engine.textbook_parser.cache import CacheEntry, ParserCache, build_cache_key
from engine.textbook_parser.config import TextbookParserConfig
from engine.textbook_parser.contracts import TextbookProblemParseV1
from engine.textbook_parser.errors import ErrorCode, TextbookParserError, ValidationIssue
from engine.textbook_parser.openai_client import (
    OpenAITextbookParserClient,
    StructuredParseResponse,
)
from engine.textbook_parser.prompt import PROMPT_VERSION
from engine.textbook_parser.telemetry import UsageSummary, aggregate_usage, text_hash
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
class ParseOutcome:
    status: ParseDecisionStatus
    validated: ValidatedParse | None
    model: str
    prompt_version: str
    usage: UsageSummary
    cache_hit: bool
    retry_count: int
    problem_hash: str
    parser_latency_ms: float
    validation_latency_ms: float
    failure_code: str | None = None

    def public_summary(self) -> dict[str, Any]:
        parse = self.validated.parse if self.validated is not None else None
        validation = self.validated.to_summary() if self.validated is not None else {}
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
            "schema": parse.schema if parse is not None else "dynatutor.textbook_parse",
            "version": parse.version if parse is not None else "1.0",
            "model": self.model,
            "prompt_version": self.prompt_version,
            "entities": [item.model_dump(mode="json") for item in parse.entities] if parse else [],
            "segments": [item.model_dump(mode="json") for item in parse.motion_segments] if parse else [],
            "events": [item.model_dump(mode="json") for item in parse.events] if parse else [],
            "explicit_facts": [item.model_dump(mode="json") for item in parse.explicit_facts] if parse else [],
            "relations": [item.model_dump(mode="json") for item in parse.relations] if parse else [],
            "assumption_proposals": [item.model_dump(mode="json") for item in parse.assumption_proposals] if parse else [],
            "accepted_assumptions": accepted_assumptions,
            "rejected_assumptions": rejected_assumptions,
            "assumption_evaluations": validation.get("assumption_evaluations", []),
            "queries": [item.model_dump(mode="json") for item in parse.queries] if parse else [],
            "interpretation_candidates": [item.model_dump(mode="json") for item in parse.interpretation_candidates] if parse else [],
            "ambiguities": [item.model_dump(mode="json") for item in parse.ambiguities] if parse else [],
            "figure_dependency": parse.figure_dependency.model_dump(mode="json") if parse else None,
            "warnings": [
                item for item in validation.get("issues", []) if item.get("severity") in {"warning", "error", "critical"}
            ],
            "usage_summary": self.usage.to_dict(),
            "parser_latency_ms": self.parser_latency_ms,
            "validation_latency_ms": self.validation_latency_ms,
            "total_latency_ms": round(
                self.parser_latency_ms
                if self.parser_latency_ms > 0
                else self.validation_latency_ms,
                3,
            ),
            "cache_hit": self.cache_hit,
            "retry_count": self.retry_count,
            "failure_code": self.failure_code,
        }


def validate_recorded_payload(problem_text: str, payload: dict[str, Any]) -> ValidatedParse:
    authority_issues = validate_payload_authority(payload)
    if authority_issues:
        raise ValueError(authority_issues[0].message)
    parse = TextbookProblemParseV1.model_validate(payload)
    return validate_parse(problem_text, parse)


def _failure_outcome(
    *, config: TextbookParserConfig, started: float, code: str
) -> ParseOutcome:
    status = (
        ParseDecisionStatus.parser_unavailable
        if code
        in {
            ErrorCode.parser_unavailable.value,
            ErrorCode.parser_timeout.value,
            ErrorCode.parser_rate_limited.value,
            ErrorCode.parser_quota.value,
            ErrorCode.parser_auth.value,
            ErrorCode.parser_budget_exceeded.value,
        }
        else ParseDecisionStatus.parser_error
    )
    return ParseOutcome(
        status=status,
        validated=None,
        model=config.model,
        prompt_version=PROMPT_VERSION,
        usage=UsageSummary(),
        cache_hit=False,
        retry_count=0,
        problem_hash=text_hash(""),
        parser_latency_ms=round((time.perf_counter() - started) * 1000, 3),
        validation_latency_ms=0.0,
        failure_code=code,
    )


def parse_textbook_problem(
    problem_text: str,
    *,
    config: TextbookParserConfig | None = None,
    client: StructuredParserClient | None = None,
    cache: ParserCache | None = None,
) -> ParseOutcome:
    config = config or TextbookParserConfig.from_env()
    started = time.perf_counter()
    if not problem_text.strip() or len(problem_text) > config.max_problem_chars:
        return _failure_outcome(
            config=config, started=started, code=ErrorCode.parser_budget_exceeded.value
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
            problem_hash=problem_digest,
            parser_latency_ms=0.0,
            validation_latency_ms=round((time.perf_counter() - validation_started) * 1000, 3),
        )

    parser_client = None
    attempt_usages: list[UsageSummary] = []
    try:
        parser_client = client or OpenAITextbookParserClient(config)
        structured = parser_client.parse(problem_text)
        attempt_usages.append(structured.usage)
    except TextbookParserError as exc:
        return _failure_outcome(config=config, started=started, code=exc.code.value)
    except (ValidationError, ValueError):
        if config.max_retries != 1 or parser_client is None:
            return _failure_outcome(config=config, started=started, code=ErrorCode.schema_error.value)
        try:
            structured = parser_client.parse(
                problem_text,
                repair_error_codes=(ErrorCode.schema_error.value,),
            )
            attempt_usages.append(structured.usage)
            schema_repair_count = 1
        except (TextbookParserError, ValidationError, ValueError):
            return _failure_outcome(config=config, started=started, code=ErrorCode.repair_failed.value)
    else:
        schema_repair_count = 0

    validation_started = time.perf_counter()
    validated = validate_parse(problem_text, structured.parsed)
    repair_codes = tuple(
        sorted(
            {
                issue.code.value
                for issue in validated.issues
                if issue.code.value in REPAIRABLE_CODES
            }
        )
    )
    retry_count = schema_repair_count
    if repair_codes and config.max_retries == 1 and schema_repair_count == 0:
        retry_count = 1
        try:
            structured = parser_client.parse(
                problem_text, repair_error_codes=repair_codes
            )
            attempt_usages.append(structured.usage)
            validated = validate_parse(problem_text, structured.parsed)
        except (TextbookParserError, ValidationError, ValueError):
            return ParseOutcome(
                status=ParseDecisionStatus.parser_error,
                validated=validated,
                model=config.model,
                prompt_version=PROMPT_VERSION,
                usage=aggregate_usage(config.model, *attempt_usages),
                cache_hit=False,
                retry_count=1,
                problem_hash=problem_digest,
                parser_latency_ms=round((time.perf_counter() - started) * 1000, 3),
                validation_latency_ms=round((time.perf_counter() - validation_started) * 1000, 3),
                failure_code=ErrorCode.repair_failed.value,
            )

    parser_elapsed = (time.perf_counter() - started) * 1000
    aggregate = aggregate_usage(config.model, *attempt_usages)
    outcome = ParseOutcome(
        status=validated.status,
        validated=validated,
        model=config.model,
        prompt_version=PROMPT_VERSION,
        usage=aggregate,
        cache_hit=False,
        retry_count=retry_count,
        problem_hash=problem_digest,
        parser_latency_ms=round(parser_elapsed, 3),
        validation_latency_ms=round((time.perf_counter() - validation_started) * 1000, 3),
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
    "ParseOutcome",
    "StructuredParserClient",
    "parse_textbook_problem",
    "validate_recorded_payload",
]
