"""Official Responses Structured Outputs client for one-call mechanics modeling."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
import re
import threading
from typing import Any, Protocol

from pydantic import ValidationError

from engine.mechanics.contracts import (
    ANSWER_AUTHORITY_FORBIDDEN_FIELDS,
    MechanicsProblemDraftV1,
)
from engine.mechanics.modeler_config import MechanicsModelerConfig
from engine.mechanics.modeler_errors import (
    MechanicsModelerError,
    ModelerAuthorityError,
    ModelerErrorCode,
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
    ModelerInputError,
    _sanitized_input_error,
    _verify_modeler_input_raw,
)
from engine.mechanics.modeler_prompt import load_modeler_prompt
from engine.mechanics.modeler_repair import (
    format_repair_text,
    sanitize_repair_issues,
)
from engine.mechanics.modeler_telemetry import (
    ModelerUsage,
    UnpricedModelError,
    measured_usage,
    resolve_price_schedule,
)


@dataclass(frozen=True)
class StructuredModelerResponse:
    draft: MechanicsProblemDraftV1
    usage: ModelerUsage
    usage_available: bool


class MechanicsStructuredClient(Protocol):
    def model(
        self,
        problem_text: str,
        *,
        images: tuple[ModelerImageInput, ...] = (),
        repair_issues: tuple[ModelerRepairIssue, ...] = (),
    ) -> StructuredModelerResponse: ...


MECHANICS_RESPONSES_REQUEST_BUDGET_VERSION = "mechanics-responses-wire-budget-v2"
MECHANICS_RESPONSES_MESSAGE_OVERHEAD_TOKENS = 4_096


@dataclass(frozen=True)
class _BuiltModelerRequest:
    sdk_kwargs: dict[str, Any]
    wire_projection_json: str


def build_modeler_asset_manifest(
    images: tuple[ModelerImageInput, ...],
) -> tuple[str, ...]:
    sanitized_error: ModelerInputError | None = None
    try:
        result = _build_modeler_asset_manifest_raw(images)
    except Exception as caught:
        sanitized_error = _sanitized_input_error(caught)
    if sanitized_error is None:
        return result
    error = sanitized_error
    sanitized_error = None
    images = ()
    error.__cause__ = None
    error.__context__ = None
    error.__traceback__ = None
    error.__suppress_context__ = True
    raise error from None


def _build_modeler_asset_manifest_raw(
    images: tuple[ModelerImageInput, ...],
) -> tuple[str, ...]:
    manifest: list[str] = []
    for image in images:
        fields = [
            f"asset_id={image.asset_id}",
            f"sha256={image.content_sha256}",
            f"media_type={image.media_type}",
        ]
        if image.page_id is not None:
            fields.append(f"page_id={image.page_id}")
        if image.page_number is not None:
            fields.append(f"page_number={image.page_number}")
        if image.parent_asset_id is not None:
            fields.append(f"parent_asset_id={image.parent_asset_id}")
        manifest.append(";".join(fields))
    return tuple(manifest)


def build_modeler_user_text(
    problem_text: str,
    images: tuple[ModelerImageInput, ...],
    repair_issues: tuple[ModelerRepairIssue, ...] = (),
) -> str:
    sanitized_error: ModelerInputError | None = None
    try:
        result = _build_modeler_user_text_raw(
            problem_text, images, repair_issues
        )
    except Exception as caught:
        sanitized_error = _sanitized_input_error(caught)
    if sanitized_error is None:
        return result
    error = sanitized_error
    sanitized_error = None
    problem_text = ""
    images = ()
    repair_issues = ()
    error.__cause__ = None
    error.__context__ = None
    error.__traceback__ = None
    error.__suppress_context__ = True
    raise error from None


def _build_modeler_user_text_raw(
    problem_text: str,
    images: tuple[ModelerImageInput, ...],
    repair_issues: tuple[ModelerRepairIssue, ...] = (),
) -> str:
    manifest = _build_modeler_asset_manifest_raw(images)
    if repair_issues:
        return format_repair_text(
            problem_text,
            repair_issues,
            asset_manifest=manifest or ("<none>",),
        )
    lines = [
        "Create one complete MechanicsProblemDraftV1 from this untrusted source.",
        "Use exactly these source asset descriptors:",
        *(manifest or ("<none>",)),
        "ORIGINAL SOURCE TEXT:",
        problem_text,
    ]
    return "\n".join(lines)


def _build_modeler_request_raw(
    problem_text: str,
    images: tuple[ModelerImageInput, ...],
    repair_issues: tuple[ModelerRepairIssue, ...],
    *,
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
) -> _BuiltModelerRequest:
    try:
        problem_text.encode("utf-8")
    except UnicodeEncodeError:
        raise ModelerInputError("problem text is not valid UTF-8") from None
    user_text = _build_modeler_user_text_raw(
        problem_text, images, repair_issues
    )
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": user_text}
    ]
    for image in images:
        if not isinstance(image, ModelerImageInput) or not isinstance(
            image.data, bytes
        ):
            raise ModelerInputError("image input is invalid")
        encoded = base64.b64encode(image.data).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{image.media_type};base64,{encoded}",
                "detail": "high",
            }
        )
    request_input = [{"role": "user", "content": content}]
    instructions = load_modeler_prompt()
    sdk_kwargs: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": request_input,
        "text_format": MechanicsProblemDraftV1,
        "reasoning": {"effort": reasoning_effort},
        "store": False,
        "tools": [],
        "max_output_tokens": max_output_tokens,
    }
    wire_projection = {
        "endpoint": "/v1/responses",
        "method": "POST",
        "body": {
            "model": model,
            "instructions": instructions,
            "input": request_input,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "MechanicsProblemDraftV1",
                    "strict": True,
                    "schema": MechanicsProblemDraftV1.model_json_schema(),
                }
            },
            "reasoning": {"effort": reasoning_effort},
            "store": False,
            "tools": [],
            "max_output_tokens": max_output_tokens,
        },
    }
    wire_projection_json = json.dumps(
        wire_projection,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return _BuiltModelerRequest(sdk_kwargs, wire_projection_json)


def serialize_modeler_request_projection(
    problem_text: str,
    images: tuple[ModelerImageInput, ...],
    repair_issues: tuple[ModelerRepairIssue, ...] = (),
    *,
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
) -> str:
    sanitized_error: ModelerInputError | None = None
    try:
        result = _build_modeler_request_raw(
            problem_text,
            images,
            repair_issues,
            model=model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
        ).wire_projection_json
    except Exception as caught:
        sanitized_error = _sanitized_input_error(caught)
    if sanitized_error is None:
        return result
    error = sanitized_error
    sanitized_error = None
    problem_text = ""
    images = ()
    repair_issues = ()
    model = ""
    reasoning_effort = ""
    max_output_tokens = 0
    error.__cause__ = None
    error.__context__ = None
    error.__traceback__ = None
    error.__suppress_context__ = True
    raise error from None


def modeler_request_input_token_ceiling(
    problem_text: str,
    images: tuple[ModelerImageInput, ...],
    repair_issues: tuple[ModelerRepairIssue, ...],
    *,
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
    image_tokens_per_image_upper_bound: int,
) -> int:
    """Reserve the complete escaped wire projection plus image billing."""

    sanitized_error: ModelerInputError | None = None
    try:
        result = _modeler_request_input_token_ceiling_raw(
            problem_text,
            images,
            repair_issues,
            model=model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            image_tokens_per_image_upper_bound=(
                image_tokens_per_image_upper_bound
            ),
        )
    except Exception as caught:
        sanitized_error = _sanitized_input_error(caught)
    if sanitized_error is None:
        return result
    error = sanitized_error
    sanitized_error = None
    problem_text = ""
    images = ()
    repair_issues = ()
    model = ""
    reasoning_effort = ""
    max_output_tokens = 0
    image_tokens_per_image_upper_bound = 0
    error.__cause__ = None
    error.__context__ = None
    error.__traceback__ = None
    error.__suppress_context__ = True
    raise error from None


def _modeler_request_input_token_ceiling_raw(
    problem_text: str,
    images: tuple[ModelerImageInput, ...],
    repair_issues: tuple[ModelerRepairIssue, ...],
    *,
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
    image_tokens_per_image_upper_bound: int,
) -> int:
    projection = _build_modeler_request_raw(
        problem_text,
        images,
        repair_issues,
        model=model,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
    ).wire_projection_json
    return (
        len(projection.encode("utf-8"))
        + len(images) * image_tokens_per_image_upper_bound
        + MECHANICS_RESPONSES_MESSAGE_OVERHEAD_TOKENS
    )


class OpenAIMechanicsModelerClient:
    """Dedicated SDK boundary; raw request/response content never escapes it."""

    _semaphores: dict[int, threading.BoundedSemaphore] = {}
    _semaphore_lock = threading.Lock()

    def __init__(
        self,
        config: MechanicsModelerConfig,
        *,
        api_key: str | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        sanitized_error: MechanicsModelerError | None = None
        client: Any | None = None
        semaphore: threading.BoundedSemaphore | None = None
        try:
            client = (
                sdk_client
                if sdk_client is not None
                else self._construct_sdk_client_raw(config, api_key)
            )
            with self._semaphore_lock:
                semaphore = self._semaphores.setdefault(
                    config.max_inflight,
                    threading.BoundedSemaphore(config.max_inflight),
                )
        except MechanicsModelerError as caught:
            sanitized_error = self._sanitized_clone(caught)
        except Exception:
            sanitized_error = ModelerUnavailableError(
                "model SDK could not be initialized"
            )
        if sanitized_error is not None:
            error = sanitized_error
            sanitized_error = None
            api_key = None
            sdk_client = None
            client = None
            semaphore = None
            config = None  # type: ignore[assignment]
            self = None  # type: ignore[assignment]
            error.__cause__ = None
            error.__context__ = None
            error.__traceback__ = None
            error.__suppress_context__ = True
            raise error from None

        self.config = config
        self._client = client
        self._semaphore = semaphore

    @staticmethod
    def _construct_sdk_client_raw(
        config: MechanicsModelerConfig,
        api_key: str | None,
    ) -> Any:
        key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        if not key:
            raise ModelerUnavailableError(
                "server-side model credentials are not configured"
            )
        try:
            from openai import OpenAI
        except ImportError:
            raise ModelerUnavailableError(
                "official OpenAI SDK is not installed"
            ) from None
        return OpenAI(
            api_key=key,
            timeout=config.timeout_seconds,
            max_retries=0,
        )

    def model(
        self,
        problem_text: str,
        *,
        images: tuple[ModelerImageInput, ...] = (),
        repair_issues: tuple[ModelerRepairIssue, ...] = (),
    ) -> StructuredModelerResponse:
        sanitized_error: BaseException | None = None
        try:
            result = self._model_with_raw(
                problem_text,
                images=images,
                repair_issues=repair_issues,
            )
        except MechanicsModelerError as caught:
            sanitized_error = self._sanitized_clone(caught)
        except ModelerInputError as caught:
            sanitized_error = _sanitized_input_error(caught)
        except Exception:
            # Provider response wrappers can also fail while their attributes
            # are inspected.  Convert those failures only after the raw frame
            # unwinds, just like explicitly mapped SDK exceptions.
            sanitized_error = ModelerUnavailableError(
                "model service response could not be processed"
            )
        if sanitized_error is None:
            return result

        # Raise only after the raw-processing frame has unwound, and scrub this
        # wrapper's content-bearing locals before creating a traceback.
        error = sanitized_error
        sanitized_error = None
        problem_text = ""
        images = ()
        repair_issues = ()
        self = None  # type: ignore[assignment]
        error.__cause__ = None
        error.__context__ = None
        error.__traceback__ = None
        error.__suppress_context__ = True
        raise error from None

    def _model_with_raw(
        self,
        problem_text: str,
        *,
        images: tuple[ModelerImageInput, ...] = (),
        repair_issues: tuple[ModelerRepairIssue, ...] = (),
    ) -> StructuredModelerResponse:
        verified = _verify_modeler_input_raw(problem_text, images, self.config)
        selected_model = self.config.selected_model(has_images=bool(images))
        try:
            resolve_price_schedule(
                selected_model, self.config.model_price_schedule
            )
        except UnpricedModelError:
            raise ModelerUnavailableError(
                "selected model has no authorized price schedule"
            ) from None
        request = _build_modeler_request_raw(
            verified.problem_text,
            verified.images,
            repair_issues,
            model=selected_model,
            reasoning_effort=self.config.reasoning_effort,
            max_output_tokens=self.config.max_output_tokens,
        )
        acquired = self._semaphore.acquire(timeout=self.config.timeout_seconds)
        if not acquired:
            error = ModelerUnavailableError("modeler concurrency budget is saturated")
            error.code = ModelerErrorCode.concurrency_budget
            raise error
        try:
            try:
                response = self._client.responses.parse(**request.sdk_kwargs)
            except ValidationError as exc:
                usage = self._usage_from_object(
                    getattr(exc, "response", None), selected_model
                )
                self._raise_validation(exc, usage=usage)
                raise
            except MechanicsModelerError:
                raise
            except Exception as exc:
                self._raise_mapped(
                    exc,
                    usage=self._usage_from_object(
                        getattr(exc, "response", None), selected_model
                    ),
                )
                raise
        finally:
            self._semaphore.release()

        recovered_usage = self._usage_from_object(response, selected_model)
        usage = recovered_usage or ModelerUsage()
        status = getattr(response, "status", None)
        incomplete = getattr(response, "incomplete_details", None)
        if status in {"failed", "cancelled"}:
            error = ModelerUnavailableError(
                "model request did not complete",
                usage=recovered_usage,
                response_status=status,
            )
            error.code = ModelerErrorCode.api_status
            raise error
        if status == "incomplete" or incomplete is not None:
            reason = getattr(incomplete, "reason", None)
            if reason == "content_filter":
                raise ModelerRefusalError(
                    "model safety policy stopped mechanics modeling",
                    usage=recovered_usage,
                )
            safe_reason = (
                reason
                if reason in {"max_output_tokens"}
                else "incomplete"
            )
            raise ModelerIncompleteError(
                "structured model output was incomplete",
                usage=recovered_usage,
                repair_issues=(
                    ModelerRepairIssue(
                        code=ModelerErrorCode.output_incomplete.value,
                        path="draft",
                        reason_code=safe_reason,
                    ),
                ),
                response_status=status,
            )
        for item in getattr(response, "output", ()) or ():
            for output_content in getattr(item, "content", ()) or ():
                if (
                    getattr(output_content, "type", None) == "refusal"
                    or getattr(output_content, "refusal", None)
                ):
                    raise ModelerRefusalError(
                        "model refused mechanics modeling", usage=recovered_usage
                    )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ModelerOutputMissingError(
                "structured model output was missing",
                usage=recovered_usage,
                repair_issues=(
                    ModelerRepairIssue(
                        code=ModelerErrorCode.output_missing.value,
                        path="draft",
                        reason_code=ModelerErrorCode.output_missing.value,
                    ),
                ),
                response_status=status,
            )
        if not isinstance(parsed, MechanicsProblemDraftV1):
            try:
                parsed = MechanicsProblemDraftV1.model_validate(parsed)
            except ValidationError as exc:
                self._raise_validation(exc, usage=recovered_usage)
                raise
        return StructuredModelerResponse(
            draft=parsed,
            usage=usage,
            usage_available=recovered_usage is not None,
        )

    @staticmethod
    def _sanitized_clone(error: MechanicsModelerError) -> MechanicsModelerError:
        code = error.code if isinstance(error.code, ModelerErrorCode) else ModelerErrorCode.unavailable
        usage = error.usage if isinstance(error.usage, ModelerUsage) else None
        status = error.response_status
        if not (
            isinstance(status, int)
            and not isinstance(status, bool)
            and 100 <= status <= 599
        ) and status not in {"completed", "incomplete", "failed", "cancelled"}:
            status = None
        issues = sanitize_repair_issues(tuple(error.repair_issues))
        messages = {
            ModelerErrorCode.schema_error: "structured model output failed its contract",
            ModelerErrorCode.authority_rejected: "model output claimed forbidden authority",
            ModelerErrorCode.output_incomplete: "structured model output was incomplete",
            ModelerErrorCode.output_missing: "structured model output was missing",
            ModelerErrorCode.refusal: "model refused mechanics modeling",
            ModelerErrorCode.authentication: "model authentication failed",
            ModelerErrorCode.quota: "model quota rejected the request",
            ModelerErrorCode.rate_limited: "model rate limit rejected the request",
            ModelerErrorCode.timeout: "model request timed out",
            ModelerErrorCode.concurrency_budget: "model concurrency budget is saturated",
            ModelerErrorCode.api_status: "model API rejected the request",
            ModelerErrorCode.unavailable: "model service is unavailable",
        }
        kwargs = {"usage": usage, "response_status": status}
        if code is ModelerErrorCode.schema_error and error.repairable and issues:
            cloned: MechanicsModelerError = ModelerStructuralSchemaError(
                messages[code], repair_issues=issues, **kwargs
            )
        elif code is ModelerErrorCode.schema_error:
            cloned = ModelerSchemaError(messages[code], **kwargs)
        elif code is ModelerErrorCode.authority_rejected:
            cloned = ModelerAuthorityError(messages[code], **kwargs)
        elif code is ModelerErrorCode.output_incomplete:
            cloned = ModelerIncompleteError(messages[code], **kwargs)
        elif code is ModelerErrorCode.output_missing:
            cloned = ModelerOutputMissingError(messages[code], **kwargs)
        elif code is ModelerErrorCode.refusal:
            cloned = ModelerRefusalError(messages[code], **kwargs)
        else:
            cloned = ModelerUnavailableError(messages[code], **kwargs)
            cloned.code = code
        cloned.__cause__ = None
        cloned.__context__ = None
        cloned.__traceback__ = None
        cloned.__suppress_context__ = True
        return cloned

    def _usage_from_object(self, response: Any, model: str) -> ModelerUsage | None:
        try:
            usage = getattr(response, "usage", None) if response is not None else None
            if usage is None:
                return None
            input_details = getattr(usage, "input_tokens_details", None)
            output_details = getattr(usage, "output_tokens_details", None)
            return measured_usage(
                model,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                cached_input_tokens=int(
                    getattr(input_details, "cached_tokens", 0) or 0
                ),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                reasoning_tokens=int(
                    getattr(output_details, "reasoning_tokens", 0) or 0
                ),
                supplied_schedule=self.config.model_price_schedule,
            )
        except Exception:
            # Usage is optional telemetry.  A malformed provider wrapper must
            # neither escape nor retain its raw object graph.
            return None

    @staticmethod
    def _validation_is_authority_failure(exc: ValidationError) -> bool:
        forbidden = {name.lower() for name in ANSWER_AUTHORITY_FORBIDDEN_FIELDS}
        for detail in exc.errors(include_url=False, include_input=False):
            loc = {str(part).lower() for part in detail.get("loc", ())}
            if loc & forbidden:
                return True
            context_error = (detail.get("ctx") or {}).get("error")
            if context_error is not None:
                internal_message = str(context_error).lower()
                if "answer-authority" in internal_message:
                    return True
        return False

    @classmethod
    def _raise_validation(
        cls, exc: ValidationError, *, usage: ModelerUsage | None
    ) -> None:
        if cls._validation_is_authority_failure(exc):
            raise ModelerAuthorityError(
                "model output attempted to claim forbidden authority", usage=usage
            ) from exc
        details = exc.errors(include_url=False, include_input=False)
        issues: list[ModelerRepairIssue] = []
        for detail in details[:24]:
            loc = detail.get("loc", ())
            path = ".".join(str(part) for part in loc)
            if not re.fullmatch(r"[A-Za-z0-9_.\[\]-]{0,240}", path):
                path = ""
            error_type = str(detail.get("type", "schema_error"))
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", error_type):
                error_type = "schema_error"
            issues.append(
                ModelerRepairIssue(
                    code=ModelerErrorCode.schema_error.value,
                    path=path,
                    reason_code=ModelerErrorCode.schema_error.value,
                    error_type=error_type,
                )
            )
        safe_issues = sanitize_repair_issues(tuple(issues))
        error_type = (
            ModelerStructuralSchemaError
            if 0 < len(details) <= 24 and len(safe_issues) == len(details)
            else ModelerSchemaError
        )
        raise error_type(
            "model output failed the structured schema",
            usage=usage,
            repair_issues=safe_issues,
        ) from exc

    @staticmethod
    def _raise_mapped(
        exc: Exception, *, usage: ModelerUsage | None
    ) -> None:
        name = type(exc).__name__.lower()
        status = getattr(exc, "status_code", None)
        if "lengthfinishreason" in name or "length_finish" in name:
            raise ModelerIncompleteError(
                "structured model output reached its limit",
                usage=usage,
                repair_issues=(
                    ModelerRepairIssue(
                        code=ModelerErrorCode.output_incomplete.value,
                        path="draft",
                        reason_code="max_output_tokens",
                    ),
                ),
                response_status=status,
            ) from exc
        if "refusal" in name or "contentfilter" in name or "content_filter" in name:
            raise ModelerRefusalError(
                "model refused mechanics modeling", usage=usage
            ) from exc
        error = ModelerUnavailableError(
            "model request failed", usage=usage, response_status=status
        )
        if status == 401 or "authentication" in name:
            error.code = ModelerErrorCode.authentication
        elif status == 429:
            provider_code = getattr(exc, "code", None)
            error.code = (
                ModelerErrorCode.quota
                if provider_code == "insufficient_quota"
                else ModelerErrorCode.rate_limited
            )
        elif "timeout" in name:
            error.code = ModelerErrorCode.timeout
        elif status is not None:
            error.code = ModelerErrorCode.api_status
        else:
            error.code = ModelerErrorCode.unavailable
        raise error from exc


__all__ = [
    "MECHANICS_RESPONSES_MESSAGE_OVERHEAD_TOKENS",
    "MECHANICS_RESPONSES_REQUEST_BUDGET_VERSION",
    "MechanicsStructuredClient",
    "OpenAIMechanicsModelerClient",
    "StructuredModelerResponse",
    "build_modeler_asset_manifest",
    "build_modeler_user_text",
    "modeler_request_input_token_ceiling",
    "serialize_modeler_request_projection",
]
