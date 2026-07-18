from __future__ import annotations

from dataclasses import dataclass
import os
import threading
from typing import Any

from pydantic import ValidationError

from engine.textbook_parser.config import TextbookParserConfig
from engine.textbook_parser.contracts import (
    TextbookProblemParseV2,
    TextbookProblemParseWireV2,
)
from engine.textbook_parser.errors import (
    ErrorCode,
    ParserIncompleteError,
    ParserOutputMissingError,
    ParserRefusalError,
    ParserUnavailableError,
    RepairIssueV1,
    TextbookParserError,
)
from engine.textbook_parser.normalization import normalize_wire_parse
from engine.textbook_parser.prompt import load_prompt
from engine.textbook_parser.repair import format_repair_request
from engine.textbook_parser.telemetry import UsageSummary, estimate_cost


@dataclass(frozen=True)
class StructuredParseResponse:
    parsed: TextbookProblemParseV2
    usage: UsageSummary
    response_id: str | None
    usage_available: bool = True


class OpenAITextbookParserClient:
    """Dedicated official-SDK Responses/Structured Outputs client.

    The explanation LLM client is intentionally not reused. No raw response or prompt
    is returned to product code or written to telemetry/cache.
    """

    _semaphores: dict[int, threading.BoundedSemaphore] = {}
    _semaphore_lock = threading.Lock()

    def __init__(self, config: TextbookParserConfig, *, api_key: str | None = None) -> None:
        self.config = config
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise ParserUnavailableError("server-side OpenAI API key is not configured")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ParserUnavailableError("official OpenAI SDK is not installed") from exc
        self._client = OpenAI(
            api_key=self.api_key,
            timeout=config.timeout_seconds,
            max_retries=0,
        )
        with self._semaphore_lock:
            self._semaphore = self._semaphores.setdefault(
                config.max_inflight, threading.BoundedSemaphore(config.max_inflight)
            )

    def parse(
        self,
        problem_text: str,
        *,
        repair_error_codes: tuple[str, ...] = (),
        repair_issues: tuple[RepairIssueV1, ...] = (),
    ) -> StructuredParseResponse:
        if len(problem_text) > self.config.max_problem_chars:
            error = TextbookParserError("problem exceeds parser input character budget")
            error.code = ErrorCode.parser_budget_exceeded
            raise error
        instructions = load_prompt()
        input_payload: Any = problem_text
        if repair_issues:
            input_payload = format_repair_request(problem_text, repair_issues)
        elif repair_error_codes:
            input_payload = format_repair_request(
                problem_text,
                tuple(
                    RepairIssueV1(
                        phase="legacy_repair",
                        code=code,
                        path="",
                        reason_code=code,
                    )
                    for code in repair_error_codes
                ),
            )
        acquired = self._semaphore.acquire(timeout=self.config.timeout_seconds)
        if not acquired:
            error = ParserUnavailableError("parser concurrency budget is saturated")
            error.code = ErrorCode.parser_budget_exceeded
            raise error
        try:
            response = self._client.responses.parse(
                model=self.config.model,
                instructions=instructions,
                input=input_payload,
                text_format=TextbookProblemParseWireV2,
                reasoning={"effort": self.config.reasoning_effort},
                store=False,
                tools=[],
                max_output_tokens=self.config.max_output_tokens,
            )
        except ValidationError as exc:
            # Structured Outputs can be syntactically valid JSON while failing
            # the Pydantic graph contract. Preserve that typed signal so the
            # orchestrator performs its one and only schema-repair attempt.
            usage_summary = self._usage_from_object(
                getattr(exc, "response", None)
            )
            if usage_summary is not None:
                try:
                    setattr(exc, "usage_summary", usage_summary)
                except (AttributeError, TypeError):
                    pass
            raise
        except Exception as exc:
            self._raise_mapped(
                exc,
                usage_summary=self._usage_from_object(
                    getattr(exc, "response", None)
                ),
            )
            raise
        finally:
            self._semaphore.release()

        recovered_usage = self._usage_from_object(response)
        usage_summary = recovered_usage or UsageSummary()
        response_status = getattr(response, "status", None)
        incomplete_details = getattr(response, "incomplete_details", None)
        if response_status == "incomplete" or incomplete_details is not None:
            error = ParserIncompleteError("structured response was incomplete")
            error.response_status = response_status
            error.incomplete_reason = getattr(incomplete_details, "reason", None)
            error.request_id = getattr(response, "id", None)
            if recovered_usage is not None:
                error.usage_summary = recovered_usage
            raise error
        for item in getattr(response, "output", ()) or ():
            for content in getattr(item, "content", ()) or ():
                if getattr(content, "type", None) == "refusal" or getattr(content, "refusal", None):
                    error = ParserRefusalError(
                        "model refused the structured parse request"
                    )
                    if recovered_usage is not None:
                        error.usage_summary = recovered_usage
                    raise error
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            error = ParserOutputMissingError(
                "structured response did not contain output_parsed"
            )
            error.response_status = response_status
            error.request_id = getattr(response, "id", None)
            if recovered_usage is not None:
                error.usage_summary = recovered_usage
            raise error
        normalized = normalize_wire_parse(problem_text, parsed)
        return StructuredParseResponse(
            parsed=normalized,
            usage=usage_summary,
            response_id=getattr(response, "id", None),
            usage_available=recovered_usage is not None,
        )

    def _usage_from_object(self, response: Any) -> UsageSummary | None:
        usage = getattr(response, "usage", None) if response is not None else None
        if usage is None:
            return None
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        return estimate_cost(
            self.config.model,
            input_tokens=input_tokens,
            cached_input_tokens=int(getattr(input_details, "cached_tokens", 0) or 0),
            output_tokens=output_tokens,
            reasoning_tokens=int(getattr(output_details, "reasoning_tokens", 0) or 0),
        )

    @staticmethod
    def _raise_mapped(
        exc: Exception, *, usage_summary: UsageSummary | None = None
    ) -> None:
        def attach(error: TextbookParserError) -> TextbookParserError:
            error.request_id = (
                getattr(exc, "request_id", None)
                or getattr(getattr(exc, "response", None), "id", None)
            )
            error.response_status = status
            details = getattr(getattr(exc, "response", None), "incomplete_details", None)
            if getattr(details, "reason", None) is not None:
                error.incomplete_reason = getattr(details, "reason", None)
            if usage_summary is not None:
                error.usage_summary = usage_summary
            return error

        name = type(exc).__name__.lower()
        status = getattr(exc, "status_code", None)
        if "lengthfinishreason" in name or "length_finish" in name:
            error = ParserIncompleteError("structured response reached its output limit")
            error.code = ErrorCode.parser_length_finish
            error.incomplete_reason = "max_output_tokens"
            raise attach(error) from exc
        if "refusal" in name or "contentfilter" in name or "content_filter" in name:
            error = ParserRefusalError("model refused the structured parse request")
            raise attach(error) from exc
        if status == 401 or "authentication" in name:
            error = ParserUnavailableError("parser authentication failed")
            error.code = ErrorCode.parser_auth
            raise attach(error) from exc
        if status == 429:
            message = str(exc).lower()
            error = ParserUnavailableError("parser quota or rate limit rejected the request")
            error.code = ErrorCode.parser_quota if "quota" in message else ErrorCode.parser_rate_limited
            raise attach(error) from exc
        if "timeout" in name:
            error = ParserUnavailableError("parser request timed out")
            error.code = ErrorCode.parser_timeout
            raise attach(error) from exc
        error = TextbookParserError(
            f"parser request failed: {type(exc).__name__}"
        )
        if status is not None:
            error.code = ErrorCode.parser_api_status
        raise attach(error) from exc


__all__ = ["OpenAITextbookParserClient", "StructuredParseResponse"]
