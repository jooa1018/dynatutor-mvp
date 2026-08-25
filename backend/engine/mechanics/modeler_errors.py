"""Typed, content-free failures for the mechanics model boundary."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelerErrorCode(str, Enum):
    schema_error = "schema_error"
    authority_rejected = "authority_rejected"
    output_incomplete = "output_incomplete"
    output_missing = "output_missing"
    refusal = "refusal"
    authentication = "authentication"
    quota = "quota"
    rate_limited = "rate_limited"
    timeout = "timeout"
    concurrency_budget = "concurrency_budget"
    api_status = "api_status"
    unavailable = "unavailable"


@dataclass(frozen=True)
class ModelerRepairIssue:
    code: str
    path: str
    referenced_id: str | None = None
    reason_code: str | None = None
    error_type: str | None = None


class MechanicsModelerError(RuntimeError):
    code = ModelerErrorCode.unavailable
    repairable = False

    def __init__(
        self,
        message: str,
        *,
        usage: object | None = None,
        repair_issues: tuple[ModelerRepairIssue, ...] = (),
        response_status: int | str | None = None,
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.repair_issues = repair_issues
        self.response_status = response_status


class ModelerSchemaError(MechanicsModelerError):
    code = ModelerErrorCode.schema_error


class ModelerStructuralSchemaError(ModelerSchemaError):
    """A schema failure proven to affect only allowlisted graph structure."""

    repairable = True


class ModelerAuthorityError(MechanicsModelerError):
    code = ModelerErrorCode.authority_rejected


class ModelerIncompleteError(MechanicsModelerError):
    code = ModelerErrorCode.output_incomplete


class ModelerOutputMissingError(MechanicsModelerError):
    code = ModelerErrorCode.output_missing


class ModelerRefusalError(MechanicsModelerError):
    code = ModelerErrorCode.refusal


class ModelerUnavailableError(MechanicsModelerError):
    code = ModelerErrorCode.unavailable


__all__ = [
    "MechanicsModelerError",
    "ModelerAuthorityError",
    "ModelerErrorCode",
    "ModelerIncompleteError",
    "ModelerOutputMissingError",
    "ModelerRefusalError",
    "ModelerRepairIssue",
    "ModelerSchemaError",
    "ModelerStructuralSchemaError",
    "ModelerUnavailableError",
]
