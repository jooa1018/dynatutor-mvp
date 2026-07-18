from __future__ import annotations

from dataclasses import dataclass
import os
import threading
from typing import Any

from pydantic import ValidationError

from engine.textbook_parser.config import TextbookParserConfig
from engine.textbook_parser.contracts import TextbookProblemParseV1
from engine.textbook_parser.errors import (
    ErrorCode,
    ParserRefusalError,
    ParserUnavailableError,
    TextbookParserError,
)
from engine.textbook_parser.prompt import load_prompt
from engine.textbook_parser.telemetry import UsageSummary, estimate_cost


@dataclass(frozen=True)
class StructuredParseResponse:
    parsed: TextbookProblemParseV1
    usage: UsageSummary
    response_id: str | None


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
    ) -> StructuredParseResponse:
        if len(problem_text) > self.config.max_problem_chars:
            error = TextbookParserError("problem exceeds parser input character budget")
            error.code = ErrorCode.parser_budget_exceeded
            raise error
        instructions = load_prompt()
        input_payload: Any = problem_text
        if repair_error_codes:
            input_payload = [
                {
                    "role": "user",
                    "content": (
                        "Re-parse the original problem. Correct only these validator codes: "
                        + ", ".join(repair_error_codes)
                        + "\n\nORIGINAL PROBLEM:\n"
                        + problem_text
                    ),
                }
            ]
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
                text_format=TextbookProblemParseV1,
                reasoning={"effort": self.config.reasoning_effort},
                store=False,
                tools=[],
                max_output_tokens=self.config.max_output_tokens,
            )
        except ValidationError:
            # Structured Outputs can be syntactically valid JSON while failing
            # the Pydantic graph contract. Preserve that typed signal so the
            # orchestrator performs its one and only schema-repair attempt.
            raise
        except Exception as exc:
            self._raise_mapped(exc)
            raise
        finally:
            self._semaphore.release()

        for item in getattr(response, "output", ()) or ():
            for content in getattr(item, "content", ()) or ():
                if getattr(content, "type", None) == "refusal" or getattr(content, "refusal", None):
                    raise ParserRefusalError("model refused the structured parse request")
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise TextbookParserError("structured response did not contain output_parsed")
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        usage_summary = estimate_cost(
            self.config.model,
            input_tokens=input_tokens,
            cached_input_tokens=int(getattr(input_details, "cached_tokens", 0) or 0),
            output_tokens=output_tokens,
            reasoning_tokens=int(getattr(output_details, "reasoning_tokens", 0) or 0),
        )
        return StructuredParseResponse(
            parsed=parsed,
            usage=usage_summary,
            response_id=getattr(response, "id", None),
        )

    @staticmethod
    def _raise_mapped(exc: Exception) -> None:
        name = type(exc).__name__.lower()
        status = getattr(exc, "status_code", None)
        if status == 401 or "authentication" in name:
            error = ParserUnavailableError("parser authentication failed")
            error.code = ErrorCode.parser_auth
            raise error from exc
        if status == 429:
            message = str(exc).lower()
            error = ParserUnavailableError("parser quota or rate limit rejected the request")
            error.code = ErrorCode.parser_quota if "quota" in message else ErrorCode.parser_rate_limited
            raise error from exc
        if "timeout" in name:
            error = ParserUnavailableError("parser request timed out")
            error.code = ErrorCode.parser_timeout
            raise error from exc
        raise TextbookParserError(f"parser request failed: {type(exc).__name__}") from exc


__all__ = ["OpenAITextbookParserClient", "StructuredParseResponse"]
