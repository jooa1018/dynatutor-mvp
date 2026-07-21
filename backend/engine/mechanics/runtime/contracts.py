"""Immutable contracts for the internal generic-mechanics rollout boundary.

The retained execution is intentionally not a serializable API model: it may
hold the exact, immutable objects produced by the modeler, compiler, and
verified graph pipeline.  ``MechanicsRuntimeSummary`` is the only safe
serializable projection and contains a closed diagnostic vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from engine.mechanics.compiler.contracts import (
    CompilerIssue,
    CompilerIssueCode,
    CompilerResult,
    CompilerStatus,
    EquationGraph,
)
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_VERSION,
    IR_SCHEMA_VERSION,
    MechanicsProblemIRV1,
)
from engine.mechanics.errors import (
    MechanicsIssueSeverity,
    MechanicsValidationIssue,
)
from engine.mechanics.modeler import (
    MECHANICS_MODELER_PROMPT_VERSION,
    MECHANICS_MODELER_VERSION,
    MechanicsModelerOutcome,
    ModelerAttemptDiagnostic,
    ModelerTelemetry,
    ModelerTerminal,
    modeler_prompt_hash,
)
from engine.mechanics.modeler_config import MechanicsIRMode
from engine.mechanics.normalization import (
    NORMALIZATION_POLICY_VERSION,
    VALIDATION_POLICY_VERSION,
    NormalizationResult,
    calculation_fingerprint,
)
from engine.mechanics.solver.contracts import SolverDiagnosticCode
from engine.mechanics.validation import DraftValidationResult, ValidationTerminal
from engine.mechanics.verification.contracts import (
    MechanicsSolveResult,
    MechanicsSolveTerminal,
)


RUNTIME_CONTRACT_VERSION = "mechanics-runtime-contract-v1"
RUNTIME_SUMMARY_SCHEMA = "dynatutor.mechanics_runtime_summary"
RUNTIME_SUMMARY_VERSION = "1.0"

_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}\Z")


class RuntimeTerminal(str, Enum):
    """Closed terminal state of one retained runtime evaluation."""

    off = "off"
    disabled = "disabled"
    confirmation_invalid = "confirmation_invalid"
    confirmation_needed = "confirmation_needed"
    modeler_rejected = "modeler_rejected"
    compiler_rejected = "compiler_rejected"
    solve_rejected = "solve_rejected"
    solved = "solved"
    failed = "failed"


class RuntimeDelivery(str, Enum):
    """The only three delivery decisions available to later product wiring."""

    none = "none"
    legacy = "legacy"
    generic = "generic"


class RuntimeFailure(str, Enum):
    """Sanitized failure stages; exception types and messages are never kept."""

    modeler_construction = "modeler_construction"
    modeler_execution = "modeler_execution"
    modeler_contract = "modeler_contract"
    authorization = "authorization"
    compiler_construction = "compiler_construction"
    compiler_execution = "compiler_execution"
    compiler_contract = "compiler_contract"
    solver_execution = "solver_execution"
    solver_contract = "solver_contract"


Fingerprint = Annotated[
    str,
    StringConstraints(
        strip_whitespace=False,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    ),
]


def is_exact_confirmation_fingerprint(value: object) -> bool:
    """Return whether ``value`` is already the exact accepted wire spelling."""

    return type(value) is str and _FINGERPRINT_RE.fullmatch(value) is not None


def _pydantic_round_trip_is_exact(value: object, expected_type: type[BaseModel]) -> bool:
    if type(value) is not expected_type:
        return False
    try:
        rebuilt = expected_type.model_validate(
            value.model_dump(mode="python", warnings="none")
        )
    except Exception:
        return False
    return rebuilt == value


def _normalization_is_coherent(value: object) -> bool:
    if type(value) is not NormalizationResult:
        return False
    if type(value.terminal) is not ValidationTerminal:
        return False
    if type(value.validation) is not DraftValidationResult:
        return False
    if type(value.validation.terminal) is not ValidationTerminal:
        return False
    if value.validation.terminal is not value.terminal:
        return False
    if type(value.validation.issues) is not tuple:
        return False
    if any(type(issue) is not MechanicsValidationIssue for issue in value.validation.issues):
        return False
    if value.terminal is ValidationTerminal.accepted and any(
        issue.severity in {MechanicsIssueSeverity.error, MechanicsIssueSeverity.critical}
        for issue in value.validation.issues
    ):
        return False
    if type(value.correction_revision) is not int:
        return False
    if value.accepted:
        if type(value.ir) is not MechanicsProblemIRV1:
            return False
        if not is_exact_confirmation_fingerprint(value.calculation_fingerprint):
            return False
        if not _pydantic_round_trip_is_exact(value.ir, MechanicsProblemIRV1):
            return False
        try:
            return calculation_fingerprint(value.ir) == value.calculation_fingerprint
        except Exception:
            return False
    return value.ir is None and value.calculation_fingerprint is None


_NORMALIZATION_TO_MODELER_TERMINAL = {
    ValidationTerminal.accepted: ModelerTerminal.accepted,
    ValidationTerminal.needs_figure: ModelerTerminal.needs_figure,
    ValidationTerminal.needs_confirmation: ModelerTerminal.needs_confirmation,
    ValidationTerminal.insufficient_information: ModelerTerminal.insufficient_information,
    ValidationTerminal.unsupported: ModelerTerminal.unsupported,
    ValidationTerminal.invalid: ModelerTerminal.invalid,
}


def _telemetry_is_coherent(
    telemetry: object,
    terminal: ModelerTerminal,
    diagnostics: object,
) -> bool:
    if type(telemetry) is not ModelerTelemetry or type(diagnostics) is not tuple:
        return False
    if any(type(item) is not ModelerAttemptDiagnostic for item in diagnostics):
        return False
    integer_fields = (
        telemetry.input_tokens,
        telemetry.cached_input_tokens,
        telemetry.output_tokens,
        telemetry.reasoning_tokens,
        telemetry.request_attempts,
        telemetry.retry_count,
        telemetry.usage_missing_attempts,
    )
    if any(type(item) is not int or item < 0 for item in integer_fields):
        return False
    numeric_fields = (
        telemetry.measured_cost_usd,
        telemetry.conservative_cost_usd,
        telemetry.model_latency_ms,
        telemetry.normalization_latency_ms,
    )
    if any(
        type(item) not in {int, float} or not math.isfinite(float(item)) or item < 0
        for item in numeric_fields
    ):
        return False
    if type(telemetry.measured_cost_known) is not bool:
        return False
    if telemetry.terminal_status != terminal.value:
        return False
    if telemetry.request_attempts != len(diagnostics):
        return False
    if telemetry.retry_count != max(len(diagnostics) - 1, 0):
        return False
    if telemetry.usage_missing_attempts > telemetry.request_attempts:
        return False
    return True


def modeler_outcome_is_coherent(value: object) -> bool:
    """Validate the exact modeler boundary without trusting dataclass annotations."""

    if type(value) is not MechanicsModelerOutcome:
        return False
    if type(value.terminal) is not ModelerTerminal:
        return False
    if (
        type(value.model) is not str
        or not value.model
        or value.model != value.model.strip()
        or len(value.model) > 128
    ):
        return False
    if (
        value.modeler_version != MECHANICS_MODELER_VERSION
        or value.prompt_version != MECHANICS_MODELER_PROMPT_VERSION
        or value.prompt_sha256 != modeler_prompt_hash()
        or value.draft_schema_version != DRAFT_SCHEMA_VERSION
        or value.ir_schema_version != IR_SCHEMA_VERSION
        or value.validation_policy_version != VALIDATION_POLICY_VERSION
        or value.normalization_policy_version != NORMALIZATION_POLICY_VERSION
    ):
        return False
    if not is_exact_confirmation_fingerprint(value.source_text_sha256):
        return False
    if not is_exact_confirmation_fingerprint(value.normalized_text_sha256):
        return False
    if type(value.image_content_sha256) is not tuple or any(
        not is_exact_confirmation_fingerprint(item)
        for item in value.image_content_sha256
    ):
        return False
    if type(value.cache_hit) is not bool:
        return False
    if value.failure_code is not None and (
        type(value.failure_code) is not str
        or not value.failure_code
        or len(value.failure_code) > 256
    ):
        return False
    if not _telemetry_is_coherent(
        value.telemetry,
        value.terminal,
        value.attempt_diagnostics,
    ):
        return False
    normalization = value.normalization
    if normalization is not None and not _normalization_is_coherent(normalization):
        return False
    if value.terminal is ModelerTerminal.accepted:
        if normalization is None or not normalization.accepted:
            return False
        if type(value.ir) is not MechanicsProblemIRV1:
            return False
        if value.ir is not normalization.ir:
            return False
        if not is_exact_confirmation_fingerprint(value.calculation_fingerprint):
            return False
        if value.calculation_fingerprint != normalization.calculation_fingerprint:
            return False
        return value.accepted
    if value.ir is not None or value.calculation_fingerprint is not None:
        return False
    if normalization is not None and normalization.accepted:
        return False
    if normalization is not None and value.terminal in {
        ModelerTerminal.needs_figure,
        ModelerTerminal.needs_confirmation,
        ModelerTerminal.insufficient_information,
        ModelerTerminal.unsupported,
        ModelerTerminal.invalid,
    }:
        if _NORMALIZATION_TO_MODELER_TERMINAL[normalization.terminal] is not value.terminal:
            return False
    return not value.accepted


def compiler_result_is_coherent(value: object) -> bool:
    """Validate a compiler result and its exact frozen graph/issue shapes."""

    if not _pydantic_round_trip_is_exact(value, CompilerResult):
        return False
    if type(value.status) is not CompilerStatus:
        return False
    if value.graph is not None and type(value.graph) is not EquationGraph:
        return False
    if value.status in {CompilerStatus.ready, CompilerStatus.overdetermined}:
        if value.graph is None or not value.compilable:
            return False
    if type(value.issues) is not tuple:
        return False
    if any(
        type(issue) is not CompilerIssue or type(issue.code) is not CompilerIssueCode
        for issue in value.issues
    ):
        return False
    return True


def solve_result_is_coherent(value: object, graph: EquationGraph) -> bool:
    """Validate one exact final result and bind it to the compiled graph."""

    if type(graph) is not EquationGraph:
        return False
    if not _pydantic_round_trip_is_exact(value, MechanicsSolveResult):
        return False
    if type(value.terminal) is not MechanicsSolveTerminal:
        return False
    if type(value.plan.graph) is not EquationGraph or value.plan.graph != graph:
        return False
    if type(value.diagnostics.entries) is not tuple:
        return False
    return all(
        type(entry.code) is SolverDiagnosticCode
        for entry in value.diagnostics.entries
    )


def _expected_delivery(
    mode: MechanicsIRMode,
    terminal: RuntimeTerminal,
) -> RuntimeDelivery:
    if mode in {MechanicsIRMode.off, MechanicsIRMode.shadow}:
        return RuntimeDelivery.legacy
    if terminal is RuntimeTerminal.solved:
        return RuntimeDelivery.generic
    return RuntimeDelivery.none


@dataclass(frozen=True)
class MechanicsRuntimeExecution:
    """One immutable evaluation retained for later solve/diagnose projection."""

    mode: MechanicsIRMode
    terminal: RuntimeTerminal
    delivery: RuntimeDelivery
    failure: RuntimeFailure | None = None
    modeler_outcome: MechanicsModelerOutcome | None = field(default=None, repr=False)
    compiler_result: CompilerResult | None = field(default=None, repr=False)
    solve_result: MechanicsSolveResult | None = field(default=None, repr=False)
    current_calculation_fingerprint: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.mode) is not MechanicsIRMode:
            raise ValueError("runtime mode must use the closed rollout enum")
        if type(self.terminal) is not RuntimeTerminal:
            raise ValueError("runtime terminal must use the closed terminal enum")
        if type(self.delivery) is not RuntimeDelivery:
            raise ValueError("runtime delivery must use the closed delivery enum")
        if self.failure is not None and type(self.failure) is not RuntimeFailure:
            raise ValueError("runtime failure must use the sanitized failure enum")
        if self.modeler_outcome is not None and not modeler_outcome_is_coherent(
            self.modeler_outcome
        ):
            raise ValueError("retained modeler outcome is not coherent")
        if self.compiler_result is not None and not compiler_result_is_coherent(
            self.compiler_result
        ):
            raise ValueError("retained compiler result is not coherent")
        if self.solve_result is not None:
            graph = (
                self.compiler_result.graph
                if self.compiler_result is not None
                else None
            )
            if graph is None or not solve_result_is_coherent(self.solve_result, graph):
                raise ValueError("retained solve result is not coherent")
        if self.current_calculation_fingerprint is not None and not (
            is_exact_confirmation_fingerprint(self.current_calculation_fingerprint)
        ):
            raise ValueError("current calculation fingerprint is malformed")
        if self.delivery is not _expected_delivery(self.mode, self.terminal):
            raise ValueError("runtime delivery contradicts rollout mode and terminal")
        self._validate_terminal_shape()

    def _validate_terminal_shape(self) -> None:
        no_objects = (
            self.modeler_outcome is None
            and self.compiler_result is None
            and self.solve_result is None
        )
        accepted_model = (
            self.modeler_outcome is not None
            and self.modeler_outcome.terminal is ModelerTerminal.accepted
        )
        compilable = (
            self.compiler_result is not None
            and self.compiler_result.compilable
            and self.compiler_result.graph is not None
        )

        if self.terminal is RuntimeTerminal.off:
            if self.mode is not MechanicsIRMode.off or not no_objects:
                raise ValueError("off execution has one empty shape")
        elif self.mode is MechanicsIRMode.off:
            raise ValueError("off rollout mode cannot retain an active terminal")

        if self.terminal is RuntimeTerminal.disabled:
            if self.mode is MechanicsIRMode.off or not no_objects:
                raise ValueError("disabled execution has one empty active-mode shape")
        elif self.terminal is RuntimeTerminal.confirmation_invalid:
            if self.mode is not MechanicsIRMode.confirm or not no_objects:
                raise ValueError("invalid confirmation must stop before modeling")
        elif self.terminal is RuntimeTerminal.confirmation_needed:
            if (
                self.mode is not MechanicsIRMode.confirm
                or not accepted_model
                or self.compiler_result is not None
                or self.solve_result is not None
            ):
                raise ValueError("confirmation-needed execution must stop after modeling")
        elif self.terminal is RuntimeTerminal.modeler_rejected:
            if (
                self.modeler_outcome is None
                or self.modeler_outcome.terminal is ModelerTerminal.accepted
                or self.compiler_result is not None
                or self.solve_result is not None
            ):
                raise ValueError("modeler-rejected execution has an invalid retained prefix")
        elif self.terminal is RuntimeTerminal.compiler_rejected:
            if (
                not accepted_model
                or self.compiler_result is None
                or self.compiler_result.compilable
                or self.solve_result is not None
            ):
                raise ValueError("compiler-rejected execution has an invalid retained prefix")
        elif self.terminal is RuntimeTerminal.solve_rejected:
            if (
                not accepted_model
                or not compilable
                or self.solve_result is None
                or self.solve_result.terminal is MechanicsSolveTerminal.solved
            ):
                raise ValueError("solve-rejected execution has an invalid retained prefix")
        elif self.terminal is RuntimeTerminal.solved:
            if (
                not accepted_model
                or not compilable
                or self.solve_result is None
                or self.solve_result.terminal is not MechanicsSolveTerminal.solved
            ):
                raise ValueError("solved execution requires one exact solved generic result")
        elif self.terminal is RuntimeTerminal.failed:
            self._validate_failure_prefix()

        needs_fingerprint = self.terminal is RuntimeTerminal.confirmation_needed
        if needs_fingerprint != (self.current_calculation_fingerprint is not None):
            raise ValueError("only confirmation-needed retains the current fingerprint")
        if needs_fingerprint and (
            self.modeler_outcome is None
            or self.current_calculation_fingerprint
            != self.modeler_outcome.calculation_fingerprint
        ):
            raise ValueError("confirmation fingerprint must bind to the retained outcome")
        if (self.terminal is RuntimeTerminal.failed) != (self.failure is not None):
            raise ValueError("failure terminal and sanitized failure must be bidirectional")

    def _validate_failure_prefix(self) -> None:
        before_model = {
            RuntimeFailure.modeler_construction,
            RuntimeFailure.modeler_execution,
            RuntimeFailure.modeler_contract,
        }
        after_model = {
            RuntimeFailure.authorization,
            RuntimeFailure.compiler_construction,
            RuntimeFailure.compiler_execution,
            RuntimeFailure.compiler_contract,
        }
        after_compile = {
            RuntimeFailure.solver_execution,
            RuntimeFailure.solver_contract,
        }
        if self.failure in before_model:
            valid = (
                self.modeler_outcome is None
                and self.compiler_result is None
                and self.solve_result is None
            )
        elif self.failure in after_model:
            valid = (
                self.modeler_outcome is not None
                and self.modeler_outcome.terminal is ModelerTerminal.accepted
                and self.compiler_result is None
                and self.solve_result is None
            )
        elif self.failure in after_compile:
            valid = (
                self.modeler_outcome is not None
                and self.modeler_outcome.terminal is ModelerTerminal.accepted
                and self.compiler_result is not None
                and self.compiler_result.compilable
                and self.solve_result is None
            )
        else:
            valid = False
        if not valid:
            raise ValueError("runtime failure retained an invalid completed-stage prefix")

    @property
    def generic_result(self) -> MechanicsSolveResult | None:
        """Project only an authorized solved generic result, without reevaluation."""

        if self.delivery is RuntimeDelivery.generic:
            return self.solve_result
        return None

    @property
    def summary(self) -> "MechanicsRuntimeSummary":
        return build_runtime_summary(self)

    def to_summary(self) -> "MechanicsRuntimeSummary":
        return build_runtime_summary(self)


class MechanicsRuntimeSummary(BaseModel):
    """Strict safe projection containing no calculation or routing authority."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        strict=True,
        str_strip_whitespace=False,
    )

    schema: Literal[RUNTIME_SUMMARY_SCHEMA] = RUNTIME_SUMMARY_SCHEMA
    version: Literal[RUNTIME_SUMMARY_VERSION] = RUNTIME_SUMMARY_VERSION
    mode: MechanicsIRMode
    terminal: RuntimeTerminal
    delivery: RuntimeDelivery
    modeler_terminal: ModelerTerminal | None = None
    compiler_status: CompilerStatus | None = None
    compiler_issue_codes: tuple[CompilerIssueCode, ...] = Field(
        default_factory=tuple,
        max_length=256,
    )
    solve_terminal: MechanicsSolveTerminal | None = None
    solve_diagnostic_codes: tuple[SolverDiagnosticCode, ...] = Field(
        default_factory=tuple,
        max_length=256,
    )
    failure: RuntimeFailure | None = None
    current_calculation_fingerprint: Fingerprint | None = None

    @model_validator(mode="after")
    def enforce_safe_projection_shape(self) -> "MechanicsRuntimeSummary":
        if self.delivery is not _expected_delivery(self.mode, self.terminal):
            raise ValueError("summary delivery contradicts rollout mode and terminal")
        if self.mode is MechanicsIRMode.off:
            if self.terminal is not RuntimeTerminal.off:
                raise ValueError("off summary requires the off terminal")
        elif self.terminal is RuntimeTerminal.off:
            raise ValueError("active summary cannot use the off terminal")
        if self.compiler_status is None and self.compiler_issue_codes:
            raise ValueError("compiler issue codes require a compiler status")
        if self.compiler_status is not None and self.modeler_terminal is not ModelerTerminal.accepted:
            raise ValueError("compiler summary requires an accepted modeler terminal")
        if self.solve_terminal is None and self.solve_diagnostic_codes:
            raise ValueError("solve diagnostic codes require a solve terminal")
        if self.solve_terminal is not None and self.compiler_status not in {
            CompilerStatus.ready,
            CompilerStatus.overdetermined,
        }:
            raise ValueError("solve summary requires a compilable compiler status")
        if self.terminal is RuntimeTerminal.confirmation_needed:
            if (
                self.mode is not MechanicsIRMode.confirm
                or self.modeler_terminal is not ModelerTerminal.accepted
                or self.compiler_status is not None
                or self.solve_terminal is not None
                or self.current_calculation_fingerprint is None
            ):
                raise ValueError("confirmation-needed summary has one exact shape")
        elif self.current_calculation_fingerprint is not None:
            raise ValueError("only confirmation-needed summary exposes a fingerprint")
        if (self.terminal is RuntimeTerminal.failed) != (self.failure is not None):
            raise ValueError("summary failure terminal and stage must be bidirectional")
        if self.terminal is RuntimeTerminal.solved and self.solve_terminal is not MechanicsSolveTerminal.solved:
            raise ValueError("solved summary requires a solved generic terminal")
        if self.delivery is RuntimeDelivery.generic and self.solve_terminal is not MechanicsSolveTerminal.solved:
            raise ValueError("generic delivery requires an exact solved result")
        self._validate_terminal_projection()
        return self

    def _validate_terminal_projection(self) -> None:
        no_model = self.modeler_terminal is None
        no_compiler = self.compiler_status is None and not self.compiler_issue_codes
        no_solve = self.solve_terminal is None and not self.solve_diagnostic_codes
        accepted_model = self.modeler_terminal is ModelerTerminal.accepted
        compilable = self.compiler_status in {
            CompilerStatus.ready,
            CompilerStatus.overdetermined,
        }

        if self.terminal in {
            RuntimeTerminal.off,
            RuntimeTerminal.disabled,
            RuntimeTerminal.confirmation_invalid,
        }:
            valid = no_model and no_compiler and no_solve
        elif self.terminal is RuntimeTerminal.confirmation_needed:
            valid = accepted_model and no_compiler and no_solve
        elif self.terminal is RuntimeTerminal.modeler_rejected:
            valid = (
                self.modeler_terminal is not None
                and not accepted_model
                and no_compiler
                and no_solve
            )
        elif self.terminal is RuntimeTerminal.compiler_rejected:
            valid = accepted_model and self.compiler_status is not None and not compilable and no_solve
        elif self.terminal is RuntimeTerminal.solve_rejected:
            valid = (
                accepted_model
                and compilable
                and self.solve_terminal is not None
                and self.solve_terminal is not MechanicsSolveTerminal.solved
            )
        elif self.terminal is RuntimeTerminal.solved:
            valid = accepted_model and compilable and self.solve_terminal is MechanicsSolveTerminal.solved
        elif self.terminal is RuntimeTerminal.failed:
            before_model = {
                RuntimeFailure.modeler_construction,
                RuntimeFailure.modeler_execution,
                RuntimeFailure.modeler_contract,
            }
            after_model = {
                RuntimeFailure.authorization,
                RuntimeFailure.compiler_construction,
                RuntimeFailure.compiler_execution,
                RuntimeFailure.compiler_contract,
            }
            after_compile = {
                RuntimeFailure.solver_execution,
                RuntimeFailure.solver_contract,
            }
            if self.failure in before_model:
                valid = no_model and no_compiler and no_solve
            elif self.failure in after_model:
                valid = accepted_model and no_compiler and no_solve
            elif self.failure in after_compile:
                valid = accepted_model and compilable and no_solve
            else:
                valid = False
        else:
            valid = False
        if not valid:
            raise ValueError("summary terminal contradicts its completed-stage projection")


def build_runtime_summary(execution: MechanicsRuntimeExecution) -> MechanicsRuntimeSummary:
    """Derive the bounded safe summary solely from one retained execution."""

    if type(execution) is not MechanicsRuntimeExecution:
        raise TypeError("runtime summary requires an exact retained execution")
    modeler = execution.modeler_outcome
    compiler = execution.compiler_result
    solve = execution.solve_result
    return MechanicsRuntimeSummary(
        mode=execution.mode,
        terminal=execution.terminal,
        delivery=execution.delivery,
        modeler_terminal=modeler.terminal if modeler is not None else None,
        compiler_status=compiler.status if compiler is not None else None,
        compiler_issue_codes=(
            tuple(issue.code for issue in compiler.issues)
            if compiler is not None
            else ()
        ),
        solve_terminal=solve.terminal if solve is not None else None,
        solve_diagnostic_codes=(
            tuple(entry.code for entry in solve.diagnostics.entries)
            if solve is not None
            else ()
        ),
        failure=execution.failure,
        current_calculation_fingerprint=execution.current_calculation_fingerprint,
    )


__all__ = [
    "RUNTIME_CONTRACT_VERSION",
    "RUNTIME_SUMMARY_SCHEMA",
    "RUNTIME_SUMMARY_VERSION",
    "MechanicsRuntimeExecution",
    "MechanicsRuntimeSummary",
    "RuntimeDelivery",
    "RuntimeFailure",
    "RuntimeTerminal",
    "build_runtime_summary",
    "compiler_result_is_coherent",
    "is_exact_confirmation_fingerprint",
    "modeler_outcome_is_coherent",
    "solve_result_is_coherent",
]
