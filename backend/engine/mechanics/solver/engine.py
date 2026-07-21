"""Public bounded mechanics solver orchestration."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from engine.mechanics.compiler.contracts import EquationGraph

from ._audit import (
    COMPLETENESS_AUDIT_VERSION,
    CompletenessAuditStatus,
    canonical_solution_signature,
)
from .backends import (
    COMPLETENESS_CERTIFICATE_VERSION,
    CompletenessProofKind,
    WorkerStatus,
)
from .contracts import (
    CandidateCoverage,
    CandidateSet,
    CandidateValue,
    DiagnosticSeverity,
    SolveBackendKind,
    SolvePhase,
    SolvePlan,
    SolverAttempt,
    SolverBudget,
    SolverDiagnosticCode,
    SolverDiagnosticEntry,
    SolverDiagnostics,
    SolverTimeout,
    candidate_generation_manifest,
    create_solver_candidate,
    diagnostic_entry_sort_key,
    solver_phase_limit_s,
)
from .isolation import (
    IsolatedBackendRun,
    IsolationStatus,
    run_isolated_backend,
    run_isolated_completeness_audit,
)
from .planner import plan_equation_graph


class SolverExecutionStatus(str, Enum):
    candidates_ready = "candidates_ready"
    incomplete = "incomplete"
    unsupported = "unsupported"
    backend_failure = "backend_failure"
    resource_limit = "resource_limit"
    timeout = "timeout"


class SolverExecutionError(ValueError):
    """Closed public failure raised only for an invalid plan object."""

    def __init__(self) -> None:
        super().__init__("invalid_plan")


class _WorkerRoot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    values: tuple[CandidateValue, ...] = Field(min_length=1, max_length=256)
    root_multiplicity: StrictInt = Field(ge=1, le=1024)


class _CompletenessCertificate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    certificate_version: Literal[COMPLETENESS_CERTIFICATE_VERSION]
    backend: SolveBackendKind
    graph_fingerprint: str
    plan_fingerprint: str
    proof_kind: CompletenessProofKind
    selected_equation_count: StrictInt = Field(ge=1, le=512)
    logical_unknown_count: StrictInt = Field(ge=1, le=256)
    solver_unknown_count: StrictInt = Field(ge=1, le=2048)
    solution_count: StrictInt = Field(ge=0, le=1024)
    total_multiplicity: StrictInt = Field(ge=0, le=1_048_576)
    coefficient_rank: StrictInt | None = Field(default=None, ge=0, le=2048)
    augmented_rank: StrictInt | None = Field(default=None, ge=0, le=2049)
    polynomial_degree: StrictInt | None = Field(default=None, ge=0, le=64)
    independent_solution_count: StrictInt | None = Field(default=None, ge=0, le=1024)
    independent_total_multiplicity: StrictInt | None = Field(
        default=None, ge=0, le=1_048_576
    )
    simple_solution_count: StrictInt | None = Field(default=None, ge=0, le=1024)
    numeric_start_count: StrictInt | None = Field(default=None, ge=1, le=1024)

    @model_validator(mode="after")
    def exact_proof_shape(self) -> "_CompletenessCertificate":
        optional = {
            "coefficient_rank": self.coefficient_rank,
            "augmented_rank": self.augmented_rank,
            "polynomial_degree": self.polynomial_degree,
            "independent_solution_count": self.independent_solution_count,
            "independent_total_multiplicity": self.independent_total_multiplicity,
            "simple_solution_count": self.simple_solution_count,
            "numeric_start_count": self.numeric_start_count,
        }
        required = {
            CompletenessProofKind.linear_rank: {
                "coefficient_rank", "augmented_rank",
            },
            CompletenessProofKind.univariate_polynomial_root_count: {
                "polynomial_degree", "independent_solution_count",
                "independent_total_multiplicity",
            },
            CompletenessProofKind.multivariate_polynomial_differential: {
                "independent_solution_count", "independent_total_multiplicity",
                "simple_solution_count",
            },
            CompletenessProofKind.bounded_numeric_starts: {
                "numeric_start_count",
            },
        }[self.proof_kind]
        if {name for name, value in optional.items() if value is not None} != required:
            raise ValueError("completeness proof fields must exactly match its kind")
        return self


class _WorkerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: WorkerStatus
    complete: StrictBool
    approximate: StrictBool
    roots: tuple[_WorkerRoot, ...] = Field(default_factory=tuple, max_length=1024)
    overflow: StrictBool
    certificate: _CompletenessCertificate | None = None

    @model_validator(mode="after")
    def closed_semantics(self) -> "_WorkerPayload":
        if self.status is WorkerStatus.success:
            if self.overflow:
                raise ValueError("successful worker payload cannot overflow")
            if self.complete != (self.certificate is not None):
                raise ValueError("complete success requires one exact certificate")
            if not self.complete and self.roots:
                raise ValueError("uncertified success cannot retain roots")
        else:
            if self.complete or self.certificate is not None:
                raise ValueError("failure payload cannot claim certified completion")
            if self.status in {WorkerStatus.unsupported, WorkerStatus.backend_failure}:
                if self.roots or self.overflow:
                    raise ValueError("closed failure payload cannot retain roots")
            elif self.status is WorkerStatus.resource_limit:
                if self.overflow != bool(self.roots):
                    raise ValueError("only overflow resource limit may retain a prefix")
        return self


class _SuccessfulCompletenessAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal[CompletenessAuditStatus.success]
    audit_version: Literal[COMPLETENESS_AUDIT_VERSION]
    backend: SolveBackendKind
    graph_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    proof_kind: CompletenessProofKind
    solver_unknown_count: StrictInt = Field(ge=1, le=2048)
    real_solution_count: StrictInt = Field(ge=0, le=1024)
    total_multiplicity: StrictInt = Field(ge=0, le=1_048_576)
    coefficient_rank: StrictInt | None = Field(default=None, ge=0, le=2048)
    augmented_rank: StrictInt | None = Field(default=None, ge=0, le=2049)
    polynomial_degree: StrictInt | None = Field(default=None, ge=0, le=64)
    canonical_signature: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def exact_proof_shape(self) -> "_SuccessfulCompletenessAudit":
        present = {
            name
            for name in (
                "coefficient_rank",
                "augmented_rank",
                "polynomial_degree",
                "canonical_signature",
            )
            if getattr(self, name) is not None
        }
        required = {
            CompletenessProofKind.linear_rank: {
                "coefficient_rank", "augmented_rank",
            },
            CompletenessProofKind.univariate_polynomial_root_count: {
                "polynomial_degree",
            },
            CompletenessProofKind.multivariate_polynomial_differential: {
                "canonical_signature",
            },
        }.get(self.proof_kind)
        if required is None or present != required:
            raise ValueError("audit fields must exactly match its symbolic proof kind")
        return self


class SolverRun(BaseModel):
    """Immutable handoff from candidate generation to independent verification."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    status: SolverExecutionStatus
    plan: SolvePlan
    candidate_set: CandidateSet
    diagnostics: SolverDiagnostics

    @model_validator(mode="after")
    def exact_bindings(self) -> "SolverRun":
        if (
            self.candidate_set.graph_fingerprint != self.plan.graph_fingerprint
            or self.candidate_set.plan_fingerprint != self.plan.plan_fingerprint
        ):
            raise ValueError("solver run candidate set must bind to its plan")
        return self


_SEVERITY = {
    SolverDiagnosticCode.backend_selected: DiagnosticSeverity.info,
    SolverDiagnosticCode.numeric_fallback_used: DiagnosticSeverity.warning,
    SolverDiagnosticCode.candidate_limit_reached: DiagnosticSeverity.error,
    SolverDiagnosticCode.generation_incomplete: DiagnosticSeverity.warning,
    SolverDiagnosticCode.backend_unsupported: DiagnosticSeverity.error,
    SolverDiagnosticCode.backend_failure: DiagnosticSeverity.error,
    SolverDiagnosticCode.resource_limit: DiagnosticSeverity.error,
    SolverDiagnosticCode.timeout: DiagnosticSeverity.error,
}


def _entry(
    code: SolverDiagnosticCode,
    phase: SolvePhase,
    backend: SolveBackendKind,
) -> SolverDiagnosticEntry:
    return SolverDiagnosticEntry(
        code=code,
        severity=_SEVERITY[code],
        phase=phase,
        backend=backend,
    )


def _validated_payload(
    isolated: IsolatedBackendRun,
    plan: SolvePlan,
    audit: IsolatedBackendRun | None = None,
) -> _WorkerPayload:
    try:
        if (
            isolated.status is not IsolationStatus.completed
            or not isolated.process_reaped
            or isolated.backend
            not in {plan.primary_backend, plan.permitted_numeric_fallback}
        ):
            raise ValueError("worker result did not come from a completed authorized process")
        payload = _WorkerPayload.model_validate(isolated.payload)
        if (
            (plan.event_ids or plan.initial_condition_ids)
            and payload.status is not WorkerStatus.unsupported
        ):
            raise ValueError("event or initial-condition plan must fail closed")
        expected_approximate = isolated.backend in {
            SolveBackendKind.numeric_root,
            SolveBackendKind.ode_ivp,
            SolveBackendKind.event_root,
            SolveBackendKind.constrained_optimization,
        }
        if payload.approximate is not expected_approximate:
            raise ValueError("worker approximation flag contradicts its backend")
        if payload.status is WorkerStatus.resource_limit and payload.overflow:
            if len(payload.roots) != plan.budget.max_candidates:
                raise ValueError("overflow must retain the exact candidate budget prefix")
        for root in payload.roots:
            ids = tuple(item.symbol_id for item in root.values)
            if ids != plan.unknown_symbol_ids:
                raise ValueError("worker roots must exactly cover planned unknowns")
        root_keys = tuple(
            tuple((item.symbol_id, item.value_si) for item in root.values)
            for root in payload.roots
        )
        if len(set(root_keys)) != len(root_keys):
            raise ValueError("worker roots must be distinct")
        numeric_order = tuple(
            tuple(
                component
                for item in root.values
                for component in (
                    item.value_si
                    if isinstance(item.value_si, tuple)
                    else (item.value_si,)
                )
            )
            for root in payload.roots
        )
        if numeric_order != tuple(sorted(numeric_order)):
            raise ValueError("worker roots must use canonical numeric order")
        if payload.complete:
            _validate_completeness_certificate(payload, isolated, plan)
            if isolated.backend in {
                SolveBackendKind.linear_symbolic,
                SolveBackendKind.polynomial_symbolic,
            }:
                _validate_independent_completeness_audit(
                    payload, isolated, plan, audit
                )
            # Numeric completion means only that every deterministic bounded
            # start was attempted.  It never becomes exhaustive/auto-selectable,
            # so an independent exhaustive solution-count audit is inapplicable.
        return payload
    except Exception:
        return _WorkerPayload(
            status=WorkerStatus.backend_failure,
            complete=False,
            approximate=False,
            roots=(),
            overflow=False,
            certificate=None,
        )


def _solver_unknown_count(plan: SolvePlan) -> int:
    by_id = {item.symbol.symbol_id: item.symbol for item in plan.graph.symbols}
    return sum(
        by_id[symbol_id].vector_length or 1
        for symbol_id in plan.unknown_symbol_ids
    )


def _validate_completeness_certificate(
    payload: _WorkerPayload,
    isolated: IsolatedBackendRun,
    plan: SolvePlan,
) -> None:
    certificate = payload.certificate
    if certificate is None:
        raise ValueError("certified completion requires a certificate")
    if (
        certificate.backend is not isolated.backend
        or certificate.graph_fingerprint != plan.graph_fingerprint
        or certificate.plan_fingerprint != plan.plan_fingerprint
        or certificate.selected_equation_count != len(plan.selected_equality_ids)
        or certificate.logical_unknown_count != len(plan.unknown_symbol_ids)
        or certificate.solver_unknown_count != _solver_unknown_count(plan)
    ):
        raise ValueError("certificate authority does not bind to the exact plan")
    if (
        certificate.solution_count != len(payload.roots)
        or certificate.total_multiplicity
        != sum(item.root_multiplicity for item in payload.roots)
    ):
        raise ValueError("certificate root count or multiplicity does not match payload")
    multiplicities = tuple(item.root_multiplicity for item in payload.roots)
    proof = certificate.proof_kind
    if proof is CompletenessProofKind.linear_rank:
        if isolated.backend is not SolveBackendKind.linear_symbolic:
            raise ValueError("linear proof requires the linear backend")
        rank = certificate.coefficient_rank
        augmented = certificate.augmented_rank
        unknowns = certificate.solver_unknown_count
        if rank is None or augmented is None:
            raise ValueError("linear ranks are required")
        if rank > unknowns or augmented > unknowns + 1:
            raise ValueError("linear ranks exceed the solver dimensions")
        if rank < augmented:
            expected_count = 0
        elif rank == augmented == unknowns:
            expected_count = 1
        else:
            raise ValueError("linear ranks do not certify finite completeness")
        if certificate.solution_count != expected_count or any(item != 1 for item in multiplicities):
            raise ValueError("linear rank proof contradicts emitted solutions")
    elif proof is CompletenessProofKind.univariate_polynomial_root_count:
        if (
            isolated.backend is not SolveBackendKind.polynomial_symbolic
            or certificate.solver_unknown_count != 1
            or certificate.independent_solution_count != certificate.solution_count
            or certificate.independent_total_multiplicity != certificate.total_multiplicity
            or certificate.polynomial_degree is None
            or plan.structure.polynomial_degree is None
            or certificate.polynomial_degree > plan.structure.polynomial_degree
            or certificate.total_multiplicity > certificate.polynomial_degree
        ):
            raise ValueError("univariate root-count proof is inconsistent")
    elif proof is CompletenessProofKind.multivariate_polynomial_differential:
        if (
            isolated.backend is not SolveBackendKind.polynomial_symbolic
            or certificate.solver_unknown_count <= 1
            or certificate.independent_solution_count != certificate.solution_count
            or certificate.independent_total_multiplicity != certificate.solution_count
            or certificate.simple_solution_count != certificate.solution_count
            or certificate.total_multiplicity != certificate.solution_count
            or any(item != 1 for item in multiplicities)
        ):
            raise ValueError("multivariate differential proof is inconsistent")
    elif proof is CompletenessProofKind.bounded_numeric_starts:
        if (
            isolated.backend is not SolveBackendKind.numeric_root
            or not payload.approximate
            or certificate.numeric_start_count != plan.budget.max_numeric_starts
            or certificate.solution_count > plan.budget.max_numeric_starts
            or certificate.total_multiplicity != certificate.solution_count
            or any(item != 1 for item in multiplicities)
        ):
            raise ValueError("bounded numeric certificate is inconsistent")
    else:
        raise ValueError("unsupported completeness proof kind")


def _validate_independent_completeness_audit(
    payload: _WorkerPayload,
    isolated: IsolatedBackendRun,
    plan: SolvePlan,
    audit_run: IsolatedBackendRun | None,
) -> None:
    if (
        audit_run is None
        or audit_run.status is not IsolationStatus.completed
        or not audit_run.process_reaped
        or audit_run.phase is not SolvePhase.verification
        or audit_run.backend is not isolated.backend
    ):
        raise ValueError("symbolic completion requires one reaped independent audit")
    audit = _SuccessfulCompletenessAudit.model_validate(audit_run.payload)
    certificate = payload.certificate
    if certificate is None:
        raise ValueError("symbolic audit requires the worker certificate")
    if (
        audit.backend is not isolated.backend
        or audit.graph_fingerprint != plan.graph_fingerprint
        or audit.plan_fingerprint != plan.plan_fingerprint
        or audit.solver_unknown_count != _solver_unknown_count(plan)
        or audit.proof_kind is not certificate.proof_kind
        or audit.real_solution_count != len(payload.roots)
        or audit.total_multiplicity
        != sum(root.root_multiplicity for root in payload.roots)
    ):
        raise ValueError("independent audit does not bind to emitted plan roots")

    if audit.proof_kind is CompletenessProofKind.linear_rank:
        if (
            audit.coefficient_rank != certificate.coefficient_rank
            or audit.augmented_rank != certificate.augmented_rank
        ):
            raise ValueError("independent linear ranks disagree")
    elif audit.proof_kind is CompletenessProofKind.univariate_polynomial_root_count:
        if audit.polynomial_degree != certificate.polynomial_degree:
            raise ValueError("independent polynomial degree disagrees")
    elif audit.proof_kind is CompletenessProofKind.multivariate_polynomial_differential:
        rows = tuple(
            tuple(
                component
                for value in root.values
                for component in (
                    value.value_si
                    if isinstance(value.value_si, tuple)
                    else (value.value_si,)
                )
            )
            for root in payload.roots
        )
        if audit.canonical_signature != canonical_solution_signature(rows):
            raise ValueError("independent multivariate solution signature disagrees")
    else:
        raise ValueError("numeric proof cannot authorize symbolic completeness")


def _candidate_set(
    plan: SolvePlan,
    backend: SolveBackendKind,
    payload: _WorkerPayload | None,
    *,
    incomplete: bool,
) -> CandidateSet:
    candidates = []
    if payload is not None and (
        payload.status is WorkerStatus.success
        or (payload.status is WorkerStatus.resource_limit and payload.overflow)
    ):
        for root_index, root in enumerate(payload.roots):
            query_value = next(
                item.value_si
                for item in root.values
                if item.symbol_id == plan.query_symbol_id
            )
            candidates.append(create_solver_candidate(
                generation_index=root_index,
                root_index=root_index,
                root_multiplicity=root.root_multiplicity,
                graph_fingerprint=plan.graph_fingerprint,
                plan_fingerprint=plan.plan_fingerprint,
                backend=backend,
                approximate=payload.approximate,
                equation_ids=plan.selected_equality_ids,
                values=root.values,
                query_symbol_id=plan.query_symbol_id,
                query_value_si=query_value,
            ))
    exact_candidates = tuple(candidates)
    if incomplete:
        coverage = CandidateCoverage.incomplete
        complete = False
    elif backend in {
        SolveBackendKind.numeric_root,
        SolveBackendKind.ode_ivp,
        SolveBackendKind.event_root,
        SolveBackendKind.constrained_optimization,
    }:
        coverage = CandidateCoverage.bounded_numeric
        complete = True
    else:
        coverage = CandidateCoverage.exhaustive_symbolic
        complete = True
    return CandidateSet(
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        coverage=coverage,
        generation_complete=complete,
        generated_count=len(exact_candidates),
        candidates=exact_candidates,
        manifest=candidate_generation_manifest(exact_candidates),
    )


def _finalize(
    plan: SolvePlan,
    final_run: IsolatedBackendRun,
    payload: _WorkerPayload | None,
    entries: list[SolverDiagnosticEntry],
    attempts: list[SolverAttempt],
) -> SolverRun:
    timeout: SolverTimeout | None = None
    incomplete = True
    if final_run.status is IsolationStatus.timeout:
        status = SolverExecutionStatus.timeout
        entries.extend((
            _entry(SolverDiagnosticCode.timeout, final_run.phase, final_run.backend),
            _entry(
                SolverDiagnosticCode.generation_incomplete,
                SolvePhase.candidate_generation,
                final_run.backend,
            ),
        ))
        timeout = SolverTimeout(
            phase=final_run.phase,
            backend=final_run.backend,
            limit_s=solver_phase_limit_s(
                final_run.phase, final_run.backend, plan.budget
            ),
            elapsed_s=final_run.elapsed_s,
        )
    elif payload is None:
        status = SolverExecutionStatus.backend_failure
        entries.extend((
            _entry(SolverDiagnosticCode.backend_failure, final_run.phase, final_run.backend),
            _entry(
                SolverDiagnosticCode.generation_incomplete,
                SolvePhase.candidate_generation,
                final_run.backend,
            ),
        ))
    elif payload.status is WorkerStatus.success and payload.complete:
        status = SolverExecutionStatus.candidates_ready
        incomplete = False
    elif payload.status is WorkerStatus.unsupported:
        status = SolverExecutionStatus.unsupported
        entries.extend((
            _entry(SolverDiagnosticCode.backend_unsupported, final_run.phase, final_run.backend),
            _entry(
                SolverDiagnosticCode.generation_incomplete,
                SolvePhase.candidate_generation,
                final_run.backend,
            ),
        ))
    elif payload.status is WorkerStatus.resource_limit:
        status = SolverExecutionStatus.resource_limit
        if payload.overflow:
            entries.append(_entry(
                SolverDiagnosticCode.candidate_limit_reached,
                SolvePhase.candidate_generation,
                final_run.backend,
            ))
        else:
            entries.extend((
                _entry(SolverDiagnosticCode.resource_limit, final_run.phase, final_run.backend),
                _entry(
                    SolverDiagnosticCode.generation_incomplete,
                    SolvePhase.candidate_generation,
                    final_run.backend,
                ),
            ))
    elif payload.status is WorkerStatus.backend_failure:
        status = SolverExecutionStatus.backend_failure
        entries.extend((
            _entry(SolverDiagnosticCode.backend_failure, final_run.phase, final_run.backend),
            _entry(
                SolverDiagnosticCode.generation_incomplete,
                SolvePhase.candidate_generation,
                final_run.backend,
            ),
        ))
    else:
        status = SolverExecutionStatus.incomplete
        entries.append(_entry(
            SolverDiagnosticCode.generation_incomplete,
            SolvePhase.candidate_generation,
            final_run.backend,
        ))

    candidate_set = _candidate_set(
        plan,
        final_run.backend,
        payload,
        incomplete=incomplete,
    )
    exact_entries = tuple(sorted(entries, key=diagnostic_entry_sort_key))
    diagnostics = SolverDiagnostics(
        entries=exact_entries,
        attempts=tuple(attempts),
        total_elapsed_s=sum(item.elapsed_s for item in attempts),
        timeout=timeout,
    )
    return SolverRun(
        status=status,
        plan=plan,
        candidate_set=candidate_set,
        diagnostics=diagnostics,
    )


def execute_solve_plan(plan: SolvePlan) -> SolverRun:
    """Execute a validated plan using only its authorized isolated backends."""

    try:
        exact_plan = SolvePlan.model_validate_json(plan.model_dump_json())
    except Exception:
        raise SolverExecutionError() from None
    entries = [
        _entry(
            SolverDiagnosticCode.backend_selected,
            SolvePhase.planning,
            exact_plan.primary_backend,
        )
    ]
    attempts: list[SolverAttempt] = []
    primary_run = run_isolated_backend(exact_plan, exact_plan.primary_backend)
    attempts.append(SolverAttempt(
        attempt_index=0,
        backend=primary_run.backend,
        phase=primary_run.phase,
        elapsed_s=primary_run.elapsed_s,
        completed=primary_run.status is IsolationStatus.completed,
    ))
    if primary_run.status is IsolationStatus.timeout:
        return _finalize(exact_plan, primary_run, None, entries, attempts)
    primary_audit: IsolatedBackendRun | None = None
    primary_final_run = primary_run
    raw_primary = primary_run.payload
    requests_symbolic_audit = (
        primary_run.backend in {
            SolveBackendKind.linear_symbolic,
            SolveBackendKind.polynomial_symbolic,
        }
        and isinstance(raw_primary, dict)
        and raw_primary.get("status") == WorkerStatus.success.value
        and raw_primary.get("complete") is True
    )
    if requests_symbolic_audit:
        primary_audit = run_isolated_completeness_audit(
            exact_plan, primary_run.backend
        )
        attempts.append(SolverAttempt(
            attempt_index=len(attempts),
            backend=primary_audit.backend,
            phase=primary_audit.phase,
            elapsed_s=primary_audit.elapsed_s,
            completed=primary_audit.status is IsolationStatus.completed,
        ))
        primary_final_run = primary_audit
        if primary_audit.status is IsolationStatus.timeout:
            return _finalize(
                exact_plan, primary_audit, None, entries, attempts
            )
    primary_payload = _validated_payload(
        primary_run, exact_plan, primary_audit
    )
    fallback = exact_plan.permitted_numeric_fallback
    fallback_needed = (
        fallback is not None
        and (
            primary_payload.status in {
                WorkerStatus.unsupported,
                WorkerStatus.backend_failure,
            }
            or (
                primary_payload.status is WorkerStatus.success
                and not primary_payload.complete
            )
        )
    )
    if not fallback_needed or fallback is None:
        return _finalize(
            exact_plan, primary_final_run, primary_payload, entries, attempts
        )

    entries.append(_entry(
        SolverDiagnosticCode.numeric_fallback_used,
        SolvePhase.planning,
        fallback,
    ))
    fallback_run = run_isolated_backend(exact_plan, fallback)
    attempts.append(SolverAttempt(
        attempt_index=len(attempts),
        backend=fallback_run.backend,
        phase=fallback_run.phase,
        elapsed_s=fallback_run.elapsed_s,
        completed=fallback_run.status is IsolationStatus.completed,
    ))
    fallback_payload = (
        None
        if fallback_run.status is IsolationStatus.timeout
        else _validated_payload(fallback_run, exact_plan)
    )
    return _finalize(
        exact_plan,
        fallback_run,
        fallback_payload,
        entries,
        attempts,
    )


def solve_equation_graph(
    graph: EquationGraph,
    budget: SolverBudget | None = None,
) -> SolverRun:
    """Plan and execute one immutable equation graph."""

    return execute_solve_plan(plan_equation_graph(graph, budget))


# Alternative descriptive spellings for integration call sites.
solve_plan = execute_solve_plan
solve_graph = solve_equation_graph


__all__ = [
    "SolverExecutionError",
    "SolverExecutionStatus",
    "SolverRun",
    "execute_solve_plan",
    "solve_equation_graph",
    "solve_graph",
    "solve_plan",
]
