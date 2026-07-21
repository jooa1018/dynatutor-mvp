"""Strict offline IR-to-graph probes for legacy-migration evidence.

This leaf module owns no product or legacy execution authority.  It accepts an
already validated immutable IR, runs only the generic graph pipeline, and
retains the exact frozen results for diagnostic comparison.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from itertools import islice
import json
import re

from pydantic import BaseModel

from engine.mechanics.compiler import (
    CompilerIssue,
    CompilerIssueCode,
    CompilerResult,
    CompilerStatus,
    EquationGraph,
    MechanicsCompiler,
    ValidatedIRAuthorization,
    authorize_validated_mechanics_ir,
)
from engine.mechanics.contracts import MechanicsProblemIRV1
from engine.mechanics.migration.contracts import (
    DifferentialStatus,
    InvarianceVariantComparison,
    InvarianceVariantKind,
    LabelledInvarianceVariant,
    LegacyDifferentialReport,
    LegacyObservation,
)
from engine.mechanics.migration.parity import (
    build_generic_result_invariance_signature,
    build_legacy_differential_report,
    compare_generic_result_invariance,
)
from engine.mechanics.normalization import calculation_fingerprint
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.validation import AssumptionAuthorization, CorrectionAuthorization
from engine.mechanics.verification.contracts import (
    MechanicsSolveResult,
    MechanicsSolveTerminal,
)


_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_MAX_VARIANTS = 64
_MAX_AUTHORITY_ITEMS = 256
_COMPILABLE_STATUSES = frozenset(
    {CompilerStatus.ready, CompilerStatus.overdetermined}
)


class MigrationProbeTerminal(str, Enum):
    compiler_rejected = "compiler_rejected"
    solve_rejected = "solve_rejected"
    solved = "solved"
    failed = "failed"


class MigrationProbeStage(str, Enum):
    calculation_fingerprint = "calculation_fingerprint"
    authorization = "authorization"
    compiler_construction = "compiler_construction"
    compilation = "compilation"
    solving = "solving"
    differential_report = "differential_report"


class MigrationProbeFailure(str, Enum):
    calculation_fingerprint = "calculation_fingerprint"
    authorization = "authorization"
    compiler_construction = "compiler_construction"
    compiler_execution = "compiler_execution"
    compiler_contract = "compiler_contract"
    solver_execution = "solver_execution"
    solver_contract = "solver_contract"
    differential_report_contract = "differential_report_contract"


def _exact_fingerprint(value: object) -> bool:
    return type(value) is str and _FINGERPRINT.fullmatch(value) is not None


def _same_runtime_shape(original: object, rebuilt: object) -> bool:
    """Compare values and their concrete nested runtime types."""

    if type(original) is not type(rebuilt):
        return False
    if isinstance(rebuilt, BaseModel):
        return all(
            _same_runtime_shape(getattr(original, name), getattr(rebuilt, name))
            for name in type(rebuilt).model_fields
        )
    if isinstance(rebuilt, Enum):
        return original is rebuilt
    if isinstance(rebuilt, tuple):
        return len(original) == len(rebuilt) and all(
            _same_runtime_shape(left, right)
            for left, right in zip(original, rebuilt)
        )
    if isinstance(rebuilt, list):
        return len(original) == len(rebuilt) and all(
            _same_runtime_shape(left, right)
            for left, right in zip(original, rebuilt)
        )
    if isinstance(rebuilt, dict):
        return original.keys() == rebuilt.keys() and all(
            _same_runtime_shape(original[key], rebuilt[key]) for key in rebuilt
        )
    return original == rebuilt


def _exact_model(value: object, expected_type: type[BaseModel]) -> bool:
    if type(value) is not expected_type:
        return False
    try:
        rebuilt = expected_type.model_validate(
            value.model_dump(mode="python", warnings="none")
        )
    except Exception:
        return False
    return rebuilt == value and _same_runtime_shape(value, rebuilt)


def _validated_exact_ir(value: object) -> MechanicsProblemIRV1:
    if type(value) is not MechanicsProblemIRV1:
        raise TypeError("migration probes require an exact MechanicsProblemIRV1")
    if not _exact_model(value, MechanicsProblemIRV1):
        raise ValueError("migration probe IR is not an exact validated immutable model")
    return value


def _validated_exact_observation(value: object) -> LegacyObservation:
    if type(value) is not LegacyObservation:
        raise TypeError("migration probes require an exact LegacyObservation")
    if not _exact_model(value, LegacyObservation):
        raise ValueError("migration observation is not an exact validated model")
    return value


def _full_ir_digest(ir: MechanicsProblemIRV1) -> str:
    payload = json.dumps(
        ir.model_dump(mode="json", warnings="none"),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _authorization_is_coherent(
    value: object,
    ir: MechanicsProblemIRV1,
) -> bool:
    if not _exact_model(value, ValidatedIRAuthorization):
        return False
    try:
        expected = ValidatedIRAuthorization(ir_sha256=_full_ir_digest(ir))
    except Exception:
        return False
    return value == expected


def _compiler_result_is_coherent(value: object) -> bool:
    """Match the accepted compiler boundary while preserving partial graphs."""

    if not _exact_model(value, CompilerResult):
        return False
    if type(value.status) is not CompilerStatus:
        return False
    if value.graph is not None and type(value.graph) is not EquationGraph:
        return False
    if type(value.issues) is not tuple or any(
        type(issue) is not CompilerIssue
        or type(issue.code) is not CompilerIssueCode
        for issue in value.issues
    ):
        return False
    if value.status in _COMPILABLE_STATUSES:
        return value.graph is not None and value.compilable
    return not value.compilable


def _solve_result_is_coherent(
    value: object,
    graph: EquationGraph,
) -> bool:
    if type(graph) is not EquationGraph or not _exact_model(
        value, MechanicsSolveResult
    ):
        return False
    if type(value.terminal) is not MechanicsSolveTerminal:
        return False
    return (
        type(value.plan.graph) is EquationGraph
        and value.plan.graph == graph
        and value.plan.graph_fingerprint == graph.fingerprint
    )


def _report_is_coherent(
    value: object,
    solve_result: MechanicsSolveResult,
) -> bool:
    if not _exact_model(value, LegacyDifferentialReport):
        return False
    try:
        signature = build_generic_result_invariance_signature(solve_result)
    except Exception:
        return False
    if value.generic_invariance_signature != signature:
        return False
    if solve_result.terminal is not MechanicsSolveTerminal.solved:
        return value.status is DifferentialStatus.not_comparable
    return True


@dataclass(frozen=True)
class MechanicsMigrationProbeExecution:
    """Immutable retained prefix of one offline generic execution."""

    terminal: MigrationProbeTerminal
    stage: MigrationProbeStage
    calculation_fingerprint: str | None = None
    compiler_status: CompilerStatus | None = None
    compiler_has_graph: bool | None = None
    solve_terminal: MechanicsSolveTerminal | None = None
    differential_status: DifferentialStatus | None = None
    failure: MigrationProbeFailure | None = None
    _compiler_result: CompilerResult | None = field(
        default=None, repr=False, compare=False
    )
    _solve_result: MechanicsSolveResult | None = field(
        default=None, repr=False, compare=False
    )
    _differential_report: LegacyDifferentialReport | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.terminal) is not MigrationProbeTerminal:
            raise ValueError("probe terminal must use the closed enum")
        if type(self.stage) is not MigrationProbeStage:
            raise ValueError("probe stage must use the closed enum")
        if self.failure is not None and type(self.failure) is not MigrationProbeFailure:
            raise ValueError("probe failure must use the closed enum")
        if self.calculation_fingerprint is not None and not _exact_fingerprint(
            self.calculation_fingerprint
        ):
            raise ValueError("probe calculation fingerprint is malformed")
        if self.compiler_status is not None and type(self.compiler_status) is not CompilerStatus:
            raise ValueError("probe compiler status must use the closed enum")
        if self.compiler_has_graph is not None and type(self.compiler_has_graph) is not bool:
            raise ValueError("probe graph-presence metadata must be an exact bool")
        if self.solve_terminal is not None and type(self.solve_terminal) is not MechanicsSolveTerminal:
            raise ValueError("probe solve terminal must use the closed enum")
        if self.differential_status is not None and type(self.differential_status) is not DifferentialStatus:
            raise ValueError("probe differential status must use the closed enum")
        if self._compiler_result is not None and not _compiler_result_is_coherent(
            self._compiler_result
        ):
            raise ValueError("retained compiler result is not coherent")
        graph = (
            None if self._compiler_result is None else self._compiler_result.graph
        )
        if self._solve_result is not None and (
            graph is None or not _solve_result_is_coherent(self._solve_result, graph)
        ):
            raise ValueError("retained solve result is not coherent")
        if self._differential_report is not None and (
            self._solve_result is None
            or not _report_is_coherent(
                self._differential_report, self._solve_result
            )
        ):
            raise ValueError("retained differential report is not coherent")
        self._bind_metadata()
        self._bind_terminal_shape()

    def _bind_metadata(self) -> None:
        compiler = self._compiler_result
        solve = self._solve_result
        report = self._differential_report
        if (compiler is None) != (self.compiler_status is None):
            raise ValueError("compiler metadata must exactly follow the retained result")
        if compiler is not None and (
            self.compiler_status is not compiler.status
            or self.compiler_has_graph != (compiler.graph is not None)
        ):
            raise ValueError("compiler metadata contradicts the retained result")
        if compiler is None and self.compiler_has_graph is not None:
            raise ValueError("graph metadata requires a retained compiler result")
        if (solve is None) != (self.solve_terminal is None):
            raise ValueError("solve metadata must exactly follow the retained result")
        if solve is not None and self.solve_terminal is not solve.terminal:
            raise ValueError("solve metadata contradicts the retained result")
        if (report is None) != (self.differential_status is None):
            raise ValueError("differential metadata must exactly follow the report")
        if report is not None and self.differential_status is not report.status:
            raise ValueError("differential metadata contradicts the retained report")

    def _bind_terminal_shape(self) -> None:
        compiler = self._compiler_result
        solve = self._solve_result
        report = self._differential_report
        failed = self.terminal is MigrationProbeTerminal.failed
        if failed != (self.failure is not None):
            raise ValueError("failure terminal and failure stage must be bidirectional")
        if self.failure is MigrationProbeFailure.calculation_fingerprint:
            valid = (
                self.stage is MigrationProbeStage.calculation_fingerprint
                and self.calculation_fingerprint is None
                and compiler is None and solve is None and report is None
            )
        elif self.failure in {
            MigrationProbeFailure.authorization,
            MigrationProbeFailure.compiler_construction,
            MigrationProbeFailure.compiler_execution,
            MigrationProbeFailure.compiler_contract,
        }:
            expected_stage = {
                MigrationProbeFailure.authorization: MigrationProbeStage.authorization,
                MigrationProbeFailure.compiler_construction: MigrationProbeStage.compiler_construction,
                MigrationProbeFailure.compiler_execution: MigrationProbeStage.compilation,
                MigrationProbeFailure.compiler_contract: MigrationProbeStage.compilation,
            }[self.failure]
            valid = (
                self.stage is expected_stage
                and self.calculation_fingerprint is not None
                and compiler is None and solve is None and report is None
            )
        elif self.failure in {
            MigrationProbeFailure.solver_execution,
            MigrationProbeFailure.solver_contract,
        }:
            valid = (
                self.stage is MigrationProbeStage.solving
                and self.calculation_fingerprint is not None
                and compiler is not None and compiler.compilable
                and solve is None and report is None
            )
        elif self.failure is MigrationProbeFailure.differential_report_contract:
            valid = (
                self.stage is MigrationProbeStage.differential_report
                and self.calculation_fingerprint is not None
                and compiler is not None and compiler.compilable
                and solve is not None and report is None
            )
        elif failed:
            valid = False
        elif self.terminal is MigrationProbeTerminal.compiler_rejected:
            valid = (
                self.stage is MigrationProbeStage.compilation
                and self.calculation_fingerprint is not None
                and compiler is not None and not compiler.compilable
                and solve is None and report is None
            )
        elif self.terminal is MigrationProbeTerminal.solve_rejected:
            valid = (
                self.stage in {
                    MigrationProbeStage.solving,
                    MigrationProbeStage.differential_report,
                }
                and self.calculation_fingerprint is not None
                and compiler is not None and compiler.compilable
                and solve is not None
                and solve.terminal is not MechanicsSolveTerminal.solved
                and (report is None) == (self.stage is MigrationProbeStage.solving)
            )
        elif self.terminal is MigrationProbeTerminal.solved:
            valid = (
                self.stage in {
                    MigrationProbeStage.solving,
                    MigrationProbeStage.differential_report,
                }
                and self.calculation_fingerprint is not None
                and compiler is not None and compiler.compilable
                and solve is not None
                and solve.terminal is MechanicsSolveTerminal.solved
                and (report is None) == (self.stage is MigrationProbeStage.solving)
            )
        else:
            valid = False
        if not valid:
            raise ValueError("probe terminal retained an invalid completed-stage shape")

    @property
    def compiler_result(self) -> CompilerResult | None:
        return self._compiler_result

    @property
    def solve_result(self) -> MechanicsSolveResult | None:
        return self._solve_result

    @property
    def differential_report(self) -> LegacyDifferentialReport | None:
        return self._differential_report


@dataclass(frozen=True)
class LabelledIRProbeVariant:
    label: str
    kind: InvarianceVariantKind
    ir: MechanicsProblemIRV1 = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.label) is not str or _IDENTIFIER.fullmatch(self.label) is None:
            raise ValueError("probe variant label must be an exact bounded identifier")
        if type(self.kind) is not InvarianceVariantKind:
            raise ValueError("probe variant kind must use the accepted closed enum")
        _validated_exact_ir(self.ir)


@dataclass(frozen=True)
class MigrationProbeVariantComparison:
    label: str
    kind: InvarianceVariantKind
    calculation_fingerprint_matches: bool
    compiler_result_matches: bool
    terminal_matches: bool
    failure_matches: bool
    solve_shape_matches: bool
    generic_signature_matches: bool | None
    matches_baseline: bool
    variant_calculation_fingerprint: str | None
    variant_terminal: MigrationProbeTerminal
    variant_failure: MigrationProbeFailure | None
    generic_comparison: InvarianceVariantComparison | None = None
    _execution: MechanicsMigrationProbeExecution = field(
        repr=False, compare=False, default=None
    )

    def __post_init__(self) -> None:
        if type(self.label) is not str or _IDENTIFIER.fullmatch(self.label) is None:
            raise ValueError("variant comparison label is malformed")
        if type(self.kind) is not InvarianceVariantKind:
            raise ValueError("variant comparison kind is malformed")
        for value in (
            self.calculation_fingerprint_matches,
            self.compiler_result_matches,
            self.terminal_matches,
            self.failure_matches,
            self.solve_shape_matches,
            self.matches_baseline,
        ):
            if type(value) is not bool:
                raise ValueError("variant comparison flags require exact bools")
        if self.generic_signature_matches is not None and type(
            self.generic_signature_matches
        ) is not bool:
            raise ValueError("generic signature match requires an exact bool")
        if self.variant_calculation_fingerprint is not None and not _exact_fingerprint(
            self.variant_calculation_fingerprint
        ):
            raise ValueError("variant calculation fingerprint is malformed")
        if type(self.variant_terminal) is not MigrationProbeTerminal:
            raise ValueError("variant terminal is malformed")
        if self.variant_failure is not None and type(self.variant_failure) is not MigrationProbeFailure:
            raise ValueError("variant failure is malformed")
        if self.generic_comparison is not None:
            if not _exact_model(self.generic_comparison, InvarianceVariantComparison):
                raise ValueError("generic comparison is malformed")
            if (
                self.generic_comparison.label != self.label
                or self.generic_comparison.kind is not self.kind
                or self.generic_comparison.matches_baseline
                != self.generic_signature_matches
            ):
                raise ValueError("generic comparison metadata is contradictory")
        elif self.generic_signature_matches is not None:
            raise ValueError("generic signature metadata requires a comparison")
        if type(self._execution) is not MechanicsMigrationProbeExecution:
            raise ValueError("variant comparison requires one exact retained execution")
        self._execution.__post_init__()

    @property
    def execution(self) -> MechanicsMigrationProbeExecution:
        return self._execution


@dataclass(frozen=True)
class MechanicsMigrationInvarianceComparison:
    baseline_calculation_fingerprint: str | None
    variants: tuple[MigrationProbeVariantComparison, ...]
    all_invariant: bool
    _baseline: MechanicsMigrationProbeExecution = field(
        repr=False, compare=False, default=None
    )

    def __post_init__(self) -> None:
        if self.baseline_calculation_fingerprint is not None and not _exact_fingerprint(
            self.baseline_calculation_fingerprint
        ):
            raise ValueError("baseline calculation fingerprint is malformed")
        if type(self.variants) is not tuple or len(self.variants) > _MAX_VARIANTS:
            raise ValueError("invariance comparison accepts at most 64 variants")
        if any(type(item) is not MigrationProbeVariantComparison for item in self.variants):
            raise ValueError("invariance comparisons require exact variant records")
        labels = tuple(item.label for item in self.variants)
        if len(set(labels)) != len(labels):
            raise ValueError("invariance comparison labels must be unique")
        if type(self.all_invariant) is not bool:
            raise ValueError("aggregate invariance requires an exact bool")
        if self.all_invariant != all(item.matches_baseline for item in self.variants):
            raise ValueError("aggregate invariance must exactly follow variant records")
        if type(self._baseline) is not MechanicsMigrationProbeExecution:
            raise ValueError("comparison requires one exact baseline execution")
        self._baseline.__post_init__()
        if self.baseline_calculation_fingerprint != self._baseline.calculation_fingerprint:
            raise ValueError("baseline metadata contradicts the retained execution")
        for item in self.variants:
            _validate_comparison_record(self._baseline, item)

    @property
    def baseline(self) -> MechanicsMigrationProbeExecution:
        return self._baseline


def _failed_execution(
    failure: MigrationProbeFailure,
    stage: MigrationProbeStage,
    fingerprint: str | None,
    *,
    compiler_result: CompilerResult | None = None,
    solve_result: MechanicsSolveResult | None = None,
) -> MechanicsMigrationProbeExecution:
    return MechanicsMigrationProbeExecution(
        terminal=MigrationProbeTerminal.failed,
        stage=stage,
        calculation_fingerprint=fingerprint,
        compiler_status=(None if compiler_result is None else compiler_result.status),
        compiler_has_graph=(None if compiler_result is None else compiler_result.graph is not None),
        solve_terminal=(None if solve_result is None else solve_result.terminal),
        failure=failure,
        _compiler_result=compiler_result,
        _solve_result=solve_result,
    )


def execute_mechanics_ir_probe(
    ir: MechanicsProblemIRV1,
    *,
    observation: LegacyObservation | None = None,
    approved_assumption_ids: Collection[str] = (),
    authorized_corrections: Mapping[str, CorrectionAuthorization] | None = None,
    authorized_assumptions: Mapping[str, AssumptionAuthorization] | None = None,
) -> MechanicsMigrationProbeExecution:
    """Run one exact accepted IR through the offline generic probe."""

    exact_ir = _validated_exact_ir(ir)
    exact_observation = (
        None if observation is None else _validated_exact_observation(observation)
    )
    try:
        fingerprint = calculation_fingerprint(exact_ir)
    except Exception:
        return _failed_execution(
            MigrationProbeFailure.calculation_fingerprint,
            MigrationProbeStage.calculation_fingerprint,
            None,
        )
    if not _exact_fingerprint(fingerprint):
        return _failed_execution(
            MigrationProbeFailure.calculation_fingerprint,
            MigrationProbeStage.calculation_fingerprint,
            None,
        )
    try:
        authorization = authorize_validated_mechanics_ir(exact_ir)
    except Exception:
        return _failed_execution(
            MigrationProbeFailure.authorization,
            MigrationProbeStage.authorization,
            fingerprint,
        )
    if not _authorization_is_coherent(authorization, exact_ir):
        return _failed_execution(
            MigrationProbeFailure.authorization,
            MigrationProbeStage.authorization,
            fingerprint,
        )
    try:
        compiler = MechanicsCompiler()
    except Exception:
        return _failed_execution(
            MigrationProbeFailure.compiler_construction,
            MigrationProbeStage.compiler_construction,
            fingerprint,
        )
    try:
        compile_kwargs: dict[str, object] = {
            "validated_ir_authorization": authorization,
        }
        if type(approved_assumption_ids) is not tuple or approved_assumption_ids:
            compile_kwargs["approved_assumption_ids"] = approved_assumption_ids
        if authorized_corrections is not None:
            compile_kwargs["authorized_corrections"] = authorized_corrections
        if authorized_assumptions is not None:
            compile_kwargs["authorized_assumptions"] = authorized_assumptions
        compiler_result = compiler.compile(exact_ir, **compile_kwargs)
    except Exception:
        return _failed_execution(
            MigrationProbeFailure.compiler_execution,
            MigrationProbeStage.compilation,
            fingerprint,
        )
    if not _compiler_result_is_coherent(compiler_result):
        return _failed_execution(
            MigrationProbeFailure.compiler_contract,
            MigrationProbeStage.compilation,
            fingerprint,
        )
    if not compiler_result.compilable:
        return MechanicsMigrationProbeExecution(
            terminal=MigrationProbeTerminal.compiler_rejected,
            stage=MigrationProbeStage.compilation,
            calculation_fingerprint=fingerprint,
            compiler_status=compiler_result.status,
            compiler_has_graph=compiler_result.graph is not None,
            _compiler_result=compiler_result,
        )
    exact_graph = compiler_result.graph
    if exact_graph is None:
        return _failed_execution(
            MigrationProbeFailure.compiler_contract,
            MigrationProbeStage.compilation,
            fingerprint,
        )
    try:
        solve_result = solve_verified_equation_graph(exact_graph)
    except Exception:
        return _failed_execution(
            MigrationProbeFailure.solver_execution,
            MigrationProbeStage.solving,
            fingerprint,
            compiler_result=compiler_result,
        )
    if not _solve_result_is_coherent(solve_result, exact_graph):
        return _failed_execution(
            MigrationProbeFailure.solver_contract,
            MigrationProbeStage.solving,
            fingerprint,
            compiler_result=compiler_result,
        )
    report = None
    if exact_observation is not None:
        try:
            report = build_legacy_differential_report(
                solve_result, exact_observation
            )
        except Exception:
            return _failed_execution(
                MigrationProbeFailure.differential_report_contract,
                MigrationProbeStage.differential_report,
                fingerprint,
                compiler_result=compiler_result,
                solve_result=solve_result,
            )
        if not _report_is_coherent(report, solve_result):
            return _failed_execution(
                MigrationProbeFailure.differential_report_contract,
                MigrationProbeStage.differential_report,
                fingerprint,
                compiler_result=compiler_result,
                solve_result=solve_result,
            )
    terminal = (
        MigrationProbeTerminal.solved
        if solve_result.terminal is MechanicsSolveTerminal.solved
        else MigrationProbeTerminal.solve_rejected
    )
    return MechanicsMigrationProbeExecution(
        terminal=terminal,
        stage=(
            MigrationProbeStage.solving
            if report is None
            else MigrationProbeStage.differential_report
        ),
        calculation_fingerprint=fingerprint,
        compiler_status=compiler_result.status,
        compiler_has_graph=True,
        solve_terminal=solve_result.terminal,
        differential_status=None if report is None else report.status,
        _compiler_result=compiler_result,
        _solve_result=solve_result,
        _differential_report=report,
    )


def _comparison_values(
    baseline: MechanicsMigrationProbeExecution,
    variant: MechanicsMigrationProbeExecution,
    *,
    label: str,
    kind: InvarianceVariantKind,
) -> MigrationProbeVariantComparison:
    baseline_solve = baseline.solve_result
    variant_solve = variant.solve_result
    solve_shape_matches = (baseline_solve is None) == (variant_solve is None)
    generic_comparison = None
    generic_matches = None
    if baseline_solve is not None and variant_solve is not None:
        try:
            baseline_signature = build_generic_result_invariance_signature(
                baseline_solve
            )
            variant_signature = build_generic_result_invariance_signature(
                variant_solve
            )
            accepted = compare_generic_result_invariance(
                baseline_signature,
                (
                    LabelledInvarianceVariant(
                        label=label,
                        kind=kind,
                        signature=variant_signature,
                    ),
                ),
            )
            generic_comparison = accepted.variants[0]
            generic_matches = generic_comparison.matches_baseline
        except Exception as exc:
            raise ValueError("generic invariance comparison failed closed") from exc
    fingerprint_matches = (
        baseline.calculation_fingerprint is not None
        and baseline.calculation_fingerprint == variant.calculation_fingerprint
    )
    compiler_matches = baseline.compiler_result == variant.compiler_result
    terminal_matches = baseline.terminal is variant.terminal
    failure_matches = baseline.failure is variant.failure
    matches = all(
        (
            fingerprint_matches,
            compiler_matches,
            terminal_matches,
            failure_matches,
            solve_shape_matches,
            generic_matches is not False,
        )
    )
    return MigrationProbeVariantComparison(
        label=label,
        kind=kind,
        calculation_fingerprint_matches=fingerprint_matches,
        compiler_result_matches=compiler_matches,
        terminal_matches=terminal_matches,
        failure_matches=failure_matches,
        solve_shape_matches=solve_shape_matches,
        generic_signature_matches=generic_matches,
        matches_baseline=matches,
        variant_calculation_fingerprint=variant.calculation_fingerprint,
        variant_terminal=variant.terminal,
        variant_failure=variant.failure,
        generic_comparison=generic_comparison,
        _execution=variant,
    )


def _validate_comparison_record(
    baseline: MechanicsMigrationProbeExecution,
    record: MigrationProbeVariantComparison,
) -> None:
    expected = _comparison_values(
        baseline,
        record.execution,
        label=record.label,
        kind=record.kind,
    )
    public_fields = (
        "label",
        "kind",
        "calculation_fingerprint_matches",
        "compiler_result_matches",
        "terminal_matches",
        "failure_matches",
        "solve_shape_matches",
        "generic_signature_matches",
        "matches_baseline",
        "variant_calculation_fingerprint",
        "variant_terminal",
        "variant_failure",
        "generic_comparison",
    )
    if any(getattr(record, name) != getattr(expected, name) for name in public_fields):
        raise ValueError("variant comparison does not match retained executions")


def _snapshot_approved_assumption_ids(
    value: Collection[str],
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray, Mapping)) or not isinstance(
        value, Collection
    ):
        raise TypeError("approved assumption authority must be a bounded collection")
    try:
        expected_length = len(value)
    except Exception:
        raise TypeError(
            "approved assumption authority must expose a stable length"
        ) from None
    if expected_length > _MAX_AUTHORITY_ITEMS:
        raise ValueError("approved assumption authority exceeds 256 items")
    try:
        snapshot = tuple(islice(iter(value), _MAX_AUTHORITY_ITEMS + 1))
        final_length = len(value)
    except Exception:
        raise ValueError(
            "approved assumption authority changed while being snapshotted"
        ) from None
    if len(snapshot) > _MAX_AUTHORITY_ITEMS:
        raise ValueError("approved assumption authority exceeds 256 items")
    if final_length != expected_length or len(snapshot) != expected_length:
        raise ValueError(
            "approved assumption authority changed while being snapshotted"
        )
    if any(
        type(item) is not str or _IDENTIFIER.fullmatch(item) is None
        for item in snapshot
    ):
        raise ValueError("approved assumption authority contains an invalid ID")
    return snapshot


def _snapshot_authority_mapping(
    value: Mapping[str, object] | None,
    *,
    record_type: type[CorrectionAuthorization] | type[AssumptionAuthorization],
    id_field: str,
    label: str,
) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} authority must be a bounded mapping")
    try:
        expected_length = len(value)
    except Exception:
        raise TypeError(f"{label} authority must expose a stable length") from None
    if expected_length > _MAX_AUTHORITY_ITEMS:
        raise ValueError(f"{label} authority exceeds 256 items")
    try:
        items = tuple(islice(iter(value.items()), _MAX_AUTHORITY_ITEMS + 1))
        final_length = len(value)
    except Exception:
        raise ValueError(f"{label} authority changed while being snapshotted") from None
    if len(items) > _MAX_AUTHORITY_ITEMS:
        raise ValueError(f"{label} authority exceeds 256 items")
    if final_length != expected_length or len(items) != expected_length:
        raise ValueError(f"{label} authority changed while being snapshotted")
    snapshot: dict[str, object] = {}
    for key, record in items:
        if (
            type(key) is not str
            or _IDENTIFIER.fullmatch(key) is None
            or type(record) is not record_type
            or getattr(record, id_field, None) != key
            or key in snapshot
        ):
            raise ValueError(f"{label} authority contains an invalid record")
        snapshot[key] = record
    return snapshot


def compare_mechanics_ir_invariance(
    baseline: MechanicsMigrationProbeExecution,
    variants: tuple[LabelledIRProbeVariant, ...],
    *,
    approved_assumption_ids: Collection[str] = (),
    authorized_corrections: Mapping[str, CorrectionAuthorization] | None = None,
    authorized_assumptions: Mapping[str, AssumptionAuthorization] | None = None,
) -> MechanicsMigrationInvarianceComparison:
    """Execute and compare bounded diagnostic-only IR variants."""

    if type(baseline) is not MechanicsMigrationProbeExecution:
        raise TypeError("invariance comparison requires an exact baseline execution")
    baseline.__post_init__()
    if type(variants) is not tuple:
        raise TypeError("invariance variants must be supplied as an exact tuple")
    if len(variants) > _MAX_VARIANTS:
        raise ValueError("invariance comparison accepts at most 64 variants")
    if any(type(item) is not LabelledIRProbeVariant for item in variants):
        raise TypeError("invariance comparison requires exact labelled variants")
    labels = tuple(item.label for item in variants)
    if len(set(labels)) != len(labels):
        raise ValueError("invariance variant labels must be unique")
    approved_snapshot = _snapshot_approved_assumption_ids(
        approved_assumption_ids
    )
    correction_snapshot = _snapshot_authority_mapping(
        authorized_corrections,
        record_type=CorrectionAuthorization,
        id_field="correction_id",
        label="correction",
    )
    assumption_snapshot = _snapshot_authority_mapping(
        authorized_assumptions,
        record_type=AssumptionAuthorization,
        id_field="assumption_id",
        label="assumption",
    )
    records = tuple(
        _comparison_values(
            baseline,
            execute_mechanics_ir_probe(
                item.ir,
                approved_assumption_ids=approved_snapshot,
                authorized_corrections=correction_snapshot,
                authorized_assumptions=assumption_snapshot,
            ),
            label=item.label,
            kind=item.kind,
        )
        for item in variants
    )
    return MechanicsMigrationInvarianceComparison(
        baseline_calculation_fingerprint=baseline.calculation_fingerprint,
        variants=records,
        all_invariant=all(item.matches_baseline for item in records),
        _baseline=baseline,
    )


__all__ = [
    "LabelledIRProbeVariant",
    "MechanicsMigrationInvarianceComparison",
    "MechanicsMigrationProbeExecution",
    "MigrationProbeFailure",
    "MigrationProbeStage",
    "MigrationProbeTerminal",
    "MigrationProbeVariantComparison",
    "compare_mechanics_ir_invariance",
    "execute_mechanics_ir_probe",
]
