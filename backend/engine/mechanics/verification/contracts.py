"""Immutable verification and final-result contracts for mechanics Stage 4."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StringConstraints, model_validator

from engine.mechanics.math_ast import DimensionVector

from engine.mechanics.solver.contracts import (
    CandidateRejection,
    CandidateRejectionReason,
    CandidateSet,
    FiniteFloat,
    FrozenModel,
    Identifier,
    SIValue,
    SolvePlan,
    SolverCandidate,
    SolverDiagnosticCode,
    SolverDiagnostics,
    SolveBackendKind,
    SolvePhase,
    diagnostic_entry_sort_key,
    solver_phase_limit_s,
)


VERIFICATION_CONTRACT_VERSION = "mechanics-verification-contract-v1"
VERIFICATION_POLICY_VERSION = "mechanics-verification-policy-v1"
EVIDENCE_ADAPTER_VERSION = "mechanics-evidence-adapter-v2"
OutputUnit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


def render_canonical_si_unit(dimension: DimensionVector) -> str:
    """Render a dimension vector in fixed SI base order without unit parsing."""

    bases = (
        ("kg", dimension.mass),
        ("m", dimension.length),
        ("s", dimension.time),
        ("A", dimension.current),
        ("K", dimension.temperature),
        ("mol", dimension.amount),
        ("cd", dimension.luminous_intensity),
    )
    rendered = "*".join(
        name if exponent == 1 else f"{name}^{exponent}"
        for name, exponent in bases
        if exponent
    ) or "1"
    if len(rendered) > 64:
        raise ValueError("canonical SI unit exceeds the evidence output bound")
    return rendered


def _is_sorted_unique(values: tuple[str, ...]) -> bool:
    return values == tuple(sorted(set(values)))


class VerificationCheckKind(str, Enum):
    equation_residual = "equation_residual"
    independent_equation_set = "independent_equation_set"
    unit_consistency = "unit_consistency"
    query_binding = "query_binding"
    inequality = "inequality"
    constraint = "constraint"
    event_order = "event_order"
    nonnegative_time = "nonnegative_time"
    positive_parameter = "positive_parameter"
    physical_regime = "physical_regime"
    conserved_quantity = "conserved_quantity"
    source_evidence = "source_evidence"
    initial_boundary_condition = "initial_boundary_condition"
    numerical_integration_residual = "numerical_integration_residual"


class VerificationCheckStatus(str, Enum):
    passed = "passed"
    failed = "failed"
    inconclusive = "inconclusive"


_FAILED_REASON_BY_KIND = {
    VerificationCheckKind.equation_residual: CandidateRejectionReason.equation_residual,
    VerificationCheckKind.independent_equation_set: CandidateRejectionReason.independent_equation_mismatch,
    VerificationCheckKind.unit_consistency: CandidateRejectionReason.unit_mismatch,
    VerificationCheckKind.query_binding: CandidateRejectionReason.query_unbound,
    VerificationCheckKind.inequality: CandidateRejectionReason.inequality_violation,
    VerificationCheckKind.constraint: CandidateRejectionReason.constraint_violation,
    VerificationCheckKind.event_order: CandidateRejectionReason.event_order_violation,
    VerificationCheckKind.nonnegative_time: CandidateRejectionReason.nonnegative_time_violation,
    VerificationCheckKind.positive_parameter: CandidateRejectionReason.positive_parameter_violation,
    VerificationCheckKind.physical_regime: CandidateRejectionReason.physical_regime_violation,
    VerificationCheckKind.conserved_quantity: CandidateRejectionReason.conservation_violation,
    VerificationCheckKind.source_evidence: CandidateRejectionReason.source_evidence_mismatch,
    VerificationCheckKind.initial_boundary_condition: CandidateRejectionReason.initial_boundary_violation,
    VerificationCheckKind.numerical_integration_residual: CandidateRejectionReason.numerical_integration_residual,
}


class VerificationCheck(FrozenModel):
    check_id: Identifier
    kind: VerificationCheckKind
    status: VerificationCheckStatus
    equation_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    constraint_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    event_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    symbol_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    initial_condition_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    source_evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    measured_error: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0e300)
    tolerance: FiniteFloat | None = Field(default=None, gt=0.0, le=1.0e12)

    @model_validator(mode="after")
    def validate_check(self) -> "VerificationCheck":
        provenance = (
            self.equation_ids,
            self.constraint_ids,
            self.event_ids,
            self.symbol_ids,
            self.initial_condition_ids,
            self.source_evidence_ids,
        )
        if not all(_is_sorted_unique(values) for values in provenance):
            raise ValueError("verification provenance must be sorted and unique")
        if (self.measured_error is None) != (self.tolerance is None):
            raise ValueError("measured error and tolerance must be supplied together")
        if self.measured_error is not None:
            comparison_passed = self.measured_error <= self.tolerance
            if self.status is VerificationCheckStatus.passed and not comparison_passed:
                raise ValueError("a passing check cannot exceed its tolerance")
            if self.status is VerificationCheckStatus.failed and comparison_passed:
                raise ValueError("a failed check must exceed its tolerance")
        return self


def _rejection_key(item: CandidateRejection) -> tuple[object, ...]:
    return (
        item.check_id,
        item.reason.value,
        item.equation_ids,
        item.constraint_ids,
        item.event_ids,
        item.symbol_ids,
        item.initial_condition_ids,
        item.source_evidence_ids,
    )


class VerificationOutcome(FrozenModel):
    contract_version: Literal[VERIFICATION_CONTRACT_VERSION] = VERIFICATION_CONTRACT_VERSION
    policy_version: Literal[VERIFICATION_POLICY_VERSION] = VERIFICATION_POLICY_VERSION
    candidate_id: Identifier
    graph_fingerprint: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    plan_fingerprint: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    passed: StrictBool
    checks: tuple[VerificationCheck, ...] = Field(min_length=1, max_length=512)
    rejections: tuple[CandidateRejection, ...] = Field(default_factory=tuple, max_length=512)

    @model_validator(mode="after")
    def validate_outcome(self) -> "VerificationOutcome":
        check_ids = tuple(item.check_id for item in self.checks)
        if check_ids != tuple(sorted(set(check_ids))):
            raise ValueError("verification checks must have unique IDs in canonical ascending order")
        if any(item.candidate_id != self.candidate_id for item in self.rejections):
            raise ValueError("every rejection must reference this candidate")
        checks = {item.check_id: item for item in self.checks}
        if any(
            item.check_id not in checks
            or checks[item.check_id].status is VerificationCheckStatus.passed
            for item in self.rejections
        ):
            raise ValueError("every rejection must name a failed or inconclusive check")
        for rejection in self.rejections:
            check = checks[rejection.check_id]
            if (
                not set(rejection.equation_ids) <= set(check.equation_ids)
                or not set(rejection.constraint_ids) <= set(check.constraint_ids)
                or not set(rejection.event_ids) <= set(check.event_ids)
                or not set(rejection.symbol_ids) <= set(check.symbol_ids)
                or not set(rejection.initial_condition_ids) <= set(check.initial_condition_ids)
                or not set(rejection.source_evidence_ids) <= set(check.source_evidence_ids)
            ):
                raise ValueError("rejection provenance must be contained in its named check")
            expected_reason = (
                CandidateRejectionReason.verification_inconclusive
                if check.status is VerificationCheckStatus.inconclusive
                else _FAILED_REASON_BY_KIND[check.kind]
            )
            if rejection.reason is not expected_reason:
                raise ValueError("rejection reason must exactly match check kind and status policy")
        rejection_keys = tuple(_rejection_key(item) for item in self.rejections)
        if rejection_keys != tuple(sorted(set(rejection_keys))):
            raise ValueError("verification rejections must be unique and canonically ordered")
        rejected_checks = {item.check_id for item in self.rejections}
        nonpassing_checks = {
            item.check_id
            for item in self.checks
            if item.status is not VerificationCheckStatus.passed
        }
        if rejected_checks != nonpassing_checks:
            raise ValueError("every and only non-passing check must have a rejection")
        all_passed = all(item.status is VerificationCheckStatus.passed for item in self.checks)
        if self.passed != (all_passed and not self.rejections):
            raise ValueError("outcome passes iff every check passes and no rejection exists")
        return self


class VerifiedCandidate(FrozenModel):
    candidate: SolverCandidate
    outcome: VerificationOutcome
    query_symbol_id: Identifier
    query_value_si: SIValue

    @model_validator(mode="after")
    def bind_passing_candidate(self) -> "VerifiedCandidate":
        if not self.outcome.passed:
            raise ValueError("verified candidate requires a passing outcome")
        if self.outcome.candidate_id != self.candidate.candidate_id:
            raise ValueError("verification outcome and candidate IDs must agree")
        if self.outcome.graph_fingerprint != self.candidate.graph_fingerprint or self.outcome.plan_fingerprint != self.candidate.plan_fingerprint:
            raise ValueError("verification outcome and candidate fingerprints must agree")
        if self.query_symbol_id != self.candidate.query_symbol_id or self.query_value_si != self.candidate.query_value_si:
            raise ValueError("verified query binding must exactly match the candidate")
        return self


class MechanicsSolveTerminal(str, Enum):
    solved = "solved"
    needs_confirmation = "needs_confirmation"
    ambiguity = "ambiguity"
    insufficient_conditions = "insufficient_conditions"
    solver_error = "solver_error"
    timeout = "timeout"
    resource_limit = "resource_limit"
    unsupported = "unsupported"


_TERMINAL_CODE = {
    SolverDiagnosticCode.timeout: MechanicsSolveTerminal.timeout,
    SolverDiagnosticCode.resource_limit: MechanicsSolveTerminal.resource_limit,
    SolverDiagnosticCode.candidate_limit_reached: MechanicsSolveTerminal.resource_limit,
    SolverDiagnosticCode.backend_failure: MechanicsSolveTerminal.solver_error,
    SolverDiagnosticCode.backend_unsupported: MechanicsSolveTerminal.unsupported,
}


class _CheckProvenance(FrozenModel):
    equation_ids: tuple[str, ...] = ()
    constraint_ids: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()
    symbol_ids: tuple[str, ...] = ()
    initial_condition_ids: tuple[str, ...] = ()
    source_evidence_ids: tuple[str, ...] = ()


def _matches_physical_token(value: str) -> bool:
    lowered = value.lower()
    return any(
        token in lowered
        for token in ("contact", "friction", "rope", "tension", "slack", "rolling")
    )


def _is_conservation_law(value: str) -> bool:
    lowered = value.lower().replace("-", "_")
    return (
        lowered == "system_momentum_conservation"
        or "conservation" in lowered
        or "work_energy" in lowered
        or ("work" in lowered and "energy" in lowered)
    )


def _expected_check_provenance(
    plan: SolvePlan,
    candidate: SolverCandidate,
) -> dict[VerificationCheckKind, _CheckProvenance]:
    graph = plan.graph
    expected: dict[VerificationCheckKind, _CheckProvenance] = {
        VerificationCheckKind.unit_consistency: _CheckProvenance(
            symbol_ids=plan.unknown_symbol_ids,
        ),
        VerificationCheckKind.equation_residual: _CheckProvenance(
            equation_ids=candidate.equation_ids,
        ),
        VerificationCheckKind.query_binding: _CheckProvenance(
            symbol_ids=(plan.query_symbol_id,),
        ),
    }
    if plan.allowed_source_evidence_ids:
        expected[VerificationCheckKind.source_evidence] = _CheckProvenance(
            source_evidence_ids=plan.allowed_source_evidence_ids,
        )
    if plan.inequality_ids:
        expected[VerificationCheckKind.inequality] = _CheckProvenance(
            equation_ids=plan.inequality_ids,
        )
    if plan.constraint_ids:
        expected[VerificationCheckKind.constraint] = _CheckProvenance(
            constraint_ids=plan.constraint_ids,
        )
    if plan.event_ids:
        expected[VerificationCheckKind.event_order] = _CheckProvenance(
            event_ids=plan.event_ids,
        )
    if plan.initial_condition_ids:
        conditions = tuple(
            item
            for item in graph.initial_conditions
            if item.condition_id in set(plan.initial_condition_ids)
        )
        expected[VerificationCheckKind.initial_boundary_condition] = _CheckProvenance(
            event_ids=tuple(sorted({
                identifier
                for item in conditions
                for identifier in (*item.scope.event_ids, item.scope.event_id)
                if identifier is not None
            })),
            symbol_ids=tuple(sorted({
                identifier
                for item in conditions
                for identifier in (
                    item.target_symbol_id,
                    item.value_symbol_id,
                    item.wrt_symbol_id,
                )
            })),
            initial_condition_ids=plan.initial_condition_ids,
            source_evidence_ids=tuple(sorted({
                identifier
                for item in conditions
                for identifier in item.source_evidence_ids
            })),
        )
    alternative_equation_ids = tuple(sorted({
        identifier
        for closed_set in graph.alternative_closed_sets
        for identifier in closed_set
    }))
    if alternative_equation_ids:
        expected[VerificationCheckKind.independent_equation_set] = _CheckProvenance(
            equation_ids=alternative_equation_ids,
        )
    if candidate.backend is SolveBackendKind.ode_ivp:
        expected[VerificationCheckKind.numerical_integration_residual] = _CheckProvenance(
            equation_ids=candidate.equation_ids,
        )

    nonnegative_ids = tuple(sorted(
        item.symbol.symbol_id
        for item in graph.symbols
        if (item.quantity_role or "").lower() in {"time", "duration"}
    ))
    if nonnegative_ids:
        expected[VerificationCheckKind.nonnegative_time] = _CheckProvenance(
            symbol_ids=nonnegative_ids,
        )
    positive_ids = tuple(sorted(
        item.symbol.symbol_id
        for item in graph.symbols
        if (item.quantity_role or "").lower() in {"mass", "radius", "length"}
    ))
    if positive_ids:
        expected[VerificationCheckKind.positive_parameter] = _CheckProvenance(
            symbol_ids=positive_ids,
        )

    physical_equations: set[str] = set()
    physical_constraints: set[str] = set()
    for equation in graph.equations:
        if _matches_physical_token(equation.law_id):
            physical_equations.add(equation.equation_id)
            physical_constraints.update(equation.constraint_ids)
    for constraint in graph.constraints:
        if _matches_physical_token(constraint.constraint_kind):
            physical_constraints.add(constraint.constraint_id)
            physical_equations.add(constraint.equation_id)
    for application in graph.applications:
        if _matches_physical_token(application.law_id):
            physical_equations.update(application.equation_ids)
            physical_constraints.update(application.constraint_ids)
    if physical_equations or physical_constraints:
        expected[VerificationCheckKind.physical_regime] = _CheckProvenance(
            equation_ids=tuple(sorted(physical_equations)),
            constraint_ids=tuple(sorted(physical_constraints)),
        )

    conservation_equations = tuple(sorted({
        equation_id
        for application in graph.applications
        if _is_conservation_law(application.law_id)
        for equation_id in application.equation_ids
    }))
    if conservation_equations:
        expected[VerificationCheckKind.conserved_quantity] = _CheckProvenance(
            equation_ids=conservation_equations,
        )
    return expected


def _actual_check_provenance(check: VerificationCheck) -> _CheckProvenance:
    return _CheckProvenance(
        equation_ids=check.equation_ids,
        constraint_ids=check.constraint_ids,
        event_ids=check.event_ids,
        symbol_ids=check.symbol_ids,
        initial_condition_ids=check.initial_condition_ids,
        source_evidence_ids=check.source_evidence_ids,
    )


class MechanicsSolveResult(FrozenModel):
    terminal: MechanicsSolveTerminal
    plan: SolvePlan
    candidate_set: CandidateSet
    verification_outcomes: tuple[VerificationOutcome, ...] = Field(default_factory=tuple, max_length=1024)
    verified_candidates: tuple[VerifiedCandidate, ...] = Field(default_factory=tuple, max_length=1024)
    rejections: tuple[CandidateRejection, ...] = Field(default_factory=tuple, max_length=1024)
    selected_candidate_id: Identifier | None = None
    diagnostics: SolverDiagnostics

    @model_validator(mode="after")
    def enforce_terminal_invariants(self) -> "MechanicsSolveResult":
        if self.candidate_set.graph_fingerprint != self.plan.graph_fingerprint or self.candidate_set.plan_fingerprint != self.plan.plan_fingerprint:
            raise ValueError("candidate set must bind to the result plan")
        if len(self.candidate_set.candidates) > self.plan.budget.max_candidates:
            raise ValueError("candidate set exceeds the plan budget")

        candidates = {item.candidate_id: item for item in self.candidate_set.candidates}
        candidate_ids = tuple(candidates)
        outcome_ids = tuple(item.candidate_id for item in self.verification_outcomes)
        verified_ids = tuple(item.candidate.candidate_id for item in self.verified_candidates)
        if len(set(outcome_ids)) != len(outcome_ids) or len(set(verified_ids)) != len(verified_ids):
            raise ValueError("candidate verification references must be unique")
        if outcome_ids != tuple(item for item in candidate_ids if item in set(outcome_ids)):
            raise ValueError("verification outcomes must follow retained candidate order")
        if verified_ids != tuple(item for item in candidate_ids if item in set(verified_ids)):
            raise ValueError("verified candidates must follow retained candidate order")
        referenced_ids = set(outcome_ids) | set(verified_ids) | {item.candidate_id for item in self.rejections}
        if not referenced_ids <= set(candidates):
            raise ValueError("every referenced candidate must remain in CandidateSet")
        if any(
            item.graph_fingerprint != self.plan.graph_fingerprint
            or item.plan_fingerprint != self.plan.plan_fingerprint
            for item in self.verification_outcomes
        ):
            raise ValueError("every verification outcome must bind to the result graph and plan")

        permitted_backends = {self.plan.primary_backend}
        if self.plan.permitted_numeric_fallback is not None:
            permitted_backends.add(self.plan.permitted_numeric_fallback)
        for candidate in self.candidate_set.candidates:
            if candidate.query_symbol_id != self.plan.query_symbol_id:
                raise ValueError("candidate query symbol must exactly match the plan")
            if tuple(item.symbol_id for item in candidate.values) != self.plan.unknown_symbol_ids:
                raise ValueError("candidate values must exactly cover the plan unknown symbols")
            if candidate.equation_ids != self.plan.selected_equality_ids:
                raise ValueError("candidate equations must exactly match the selected equality set")
            if candidate.backend not in permitted_backends:
                raise ValueError("candidate backend is not authorized by the plan")

        graph_equation_ids = {item.equation_id for item in self.plan.graph.equations}
        graph_constraint_ids = set(self.plan.constraint_ids)
        graph_event_ids = set(self.plan.event_ids)
        graph_symbol_ids = {item.symbol.symbol_id for item in self.plan.graph.symbols}
        graph_initial_condition_ids = set(self.plan.initial_condition_ids)
        graph_evidence_ids = set(self.plan.allowed_source_evidence_ids)
        for outcome in self.verification_outcomes:
            candidate = candidates[outcome.candidate_id]
            expected_provenance = _expected_check_provenance(self.plan, candidate)
            kinds = tuple(item.kind for item in outcome.checks)
            if len(set(kinds)) != len(kinds):
                raise ValueError("each candidate must have unique verification check kinds")
            for check in outcome.checks:
                if not set(check.equation_ids) <= graph_equation_ids:
                    raise ValueError("verification check references an equation outside the embedded graph")
                if not set(check.constraint_ids) <= graph_constraint_ids:
                    raise ValueError("verification check references a constraint outside the embedded graph")
                if not set(check.event_ids) <= graph_event_ids:
                    raise ValueError("verification check references an event outside the plan scope")
                if not set(check.symbol_ids) <= graph_symbol_ids:
                    raise ValueError("verification check references a symbol outside the embedded graph")
                if not set(check.initial_condition_ids) <= graph_initial_condition_ids:
                    raise ValueError("verification check references an initial condition outside the plan scope")
                if not set(check.source_evidence_ids) <= graph_evidence_ids:
                    raise ValueError("verification check references evidence outside graph provenance")
                if check.kind not in expected_provenance:
                    raise ValueError("verification check kind is not applicable to this graph and candidate")
                if _actual_check_provenance(check) != expected_provenance[check.kind]:
                    raise ValueError("verification check provenance must exactly match graph-derived policy")

        outcomes = {item.candidate_id: item for item in self.verification_outcomes}
        for verified in self.verified_candidates:
            candidate = candidates[verified.candidate.candidate_id]
            if verified.candidate != candidate or outcomes.get(candidate.candidate_id) != verified.outcome:
                raise ValueError("verified candidates must exactly match retained candidates and outcomes")
            if candidate.graph_fingerprint != self.plan.graph_fingerprint or candidate.plan_fingerprint != self.plan.plan_fingerprint:
                raise ValueError("verified candidate fingerprint mismatch")
        passing_outcomes = {item.candidate_id for item in self.verification_outcomes if item.passed}
        if passing_outcomes != set(verified_ids):
            raise ValueError("every and only passing outcome must have a verified candidate")

        aggregate_rejections = tuple(
            rejection
            for outcome in self.verification_outcomes
            for rejection in outcome.rejections
        )
        if self.rejections != aggregate_rejections:
            raise ValueError("top-level rejections must exactly aggregate canonical outcome rejections")
        if set(verified_ids) & {item.candidate_id for item in self.rejections}:
            raise ValueError("a verified candidate cannot be rejected")

        complete_verdicts = {
            MechanicsSolveTerminal.solved,
            MechanicsSolveTerminal.ambiguity,
            MechanicsSolveTerminal.needs_confirmation,
            MechanicsSolveTerminal.insufficient_conditions,
        }
        if self.terminal in complete_verdicts and outcome_ids != candidate_ids:
            raise ValueError("answer verdicts require outcomes in exact retained candidate order")
        if self.terminal in complete_verdicts:
            for candidate_id, outcome in outcomes.items():
                candidate = candidates[candidate_id]
                kinds = tuple(item.kind for item in outcome.checks)
                if len(set(kinds)) != len(kinds):
                    raise ValueError("each candidate must have unique verification check kinds")
                required_kinds = set(_expected_check_provenance(self.plan, candidate))
                if not required_kinds <= set(kinds):
                    raise ValueError("answer verdict is missing graph-required verification check kinds")
        if self.terminal is MechanicsSolveTerminal.solved:
            if (
                not self.candidate_set.auto_selectable
                or len(self.verified_candidates) != 1
                or self.selected_candidate_id != verified_ids[0]
            ):
                raise ValueError("solved requires auto-selectable coverage and exactly one selected verified candidate")
        elif self.selected_candidate_id is not None:
            raise ValueError("only a solved result may select a candidate")
        if self.terminal is MechanicsSolveTerminal.ambiguity and (
            not self.candidate_set.auto_selectable or len(self.verified_candidates) < 2
        ):
            raise ValueError("ambiguity requires auto-selectable coverage and at least two verified candidates")
        if self.terminal is MechanicsSolveTerminal.needs_confirmation and (
            self.candidate_set.auto_selectable or not self.verified_candidates
        ):
            raise ValueError("needs-confirmation requires non-auto coverage and at least one verified candidate")
        if self.terminal is MechanicsSolveTerminal.insufficient_conditions and self.verified_candidates:
            raise ValueError("insufficient conditions requires zero verified candidates")

        failure_terminals = {
            MechanicsSolveTerminal.timeout,
            MechanicsSolveTerminal.resource_limit,
            MechanicsSolveTerminal.solver_error,
            MechanicsSolveTerminal.unsupported,
        }
        if self.terminal in failure_terminals and (
            self.verified_candidates or passing_outcomes
        ):
            raise ValueError("failure terminals forbid verified or passing partial answers")

        authorized_backends = permitted_backends
        if any(item.backend not in authorized_backends for item in self.diagnostics.entries):
            raise ValueError("diagnostic entry backend is not authorized by the plan")
        if any(item.backend not in authorized_backends for item in self.diagnostics.attempts):
            raise ValueError("solver attempt backend is not authorized by the plan")
        if self.diagnostics.timeout is not None and self.diagnostics.timeout.backend not in authorized_backends:
            raise ValueError("timeout backend is not authorized by the plan")
        for attempt in self.diagnostics.attempts:
            exact_limit = solver_phase_limit_s(
                attempt.phase,
                attempt.backend,
                self.plan.budget,
            )
            timeout = self.diagnostics.timeout
            is_timeout_attempt = (
                timeout is not None
                and attempt.phase is timeout.phase
                and attempt.backend is timeout.backend
                and not attempt.completed
            )
            if is_timeout_attempt and attempt.elapsed_s > exact_limit + self.plan.budget.timeout_termination_grace_s:
                raise ValueError("timeout attempt elapsed time exceeds the bounded termination grace")
            if not is_timeout_attempt and attempt.elapsed_s > exact_limit:
                raise ValueError("solver attempt elapsed time exceeds its exact plan limit")
        numeric_backends = {
            SolveBackendKind.numeric_root,
            SolveBackendKind.ode_ivp,
            SolveBackendKind.event_root,
            SolveBackendKind.constrained_optimization,
        }
        numeric_attempt_count = sum(
            item.phase is SolvePhase.numeric or item.backend in numeric_backends
            for item in self.diagnostics.attempts
        )
        if numeric_attempt_count > self.plan.budget.max_numeric_starts:
            raise ValueError("numeric solver attempt count exceeds the exact plan budget")
        if self.diagnostics.timeout is not None:
            exact_timeout_limit = solver_phase_limit_s(
                self.diagnostics.timeout.phase,
                self.diagnostics.timeout.backend,
                self.plan.budget,
            )
            if self.diagnostics.timeout.limit_s != exact_timeout_limit:
                raise ValueError("timeout limit must exactly match the plan phase/backend budget")
        selected_entries = tuple(
            item for item in self.diagnostics.entries
            if item.code is SolverDiagnosticCode.backend_selected
        )
        if len(selected_entries) != 1 or selected_entries[0].backend is not self.plan.primary_backend:
            raise ValueError("diagnostics must select the exact primary backend once")

        fallback_entries = tuple(
            item for item in self.diagnostics.entries
            if item.code is SolverDiagnosticCode.numeric_fallback_used
        )
        fallback = self.plan.permitted_numeric_fallback
        operational_fallback = fallback is not None and (
            any(item.backend is fallback for item in self.candidate_set.candidates)
            or any(item.backend is fallback for item in self.diagnostics.attempts)
            or (self.diagnostics.timeout is not None and self.diagnostics.timeout.backend is fallback)
            or any(
                item.backend is fallback
                and item.code not in {SolverDiagnosticCode.backend_selected, SolverDiagnosticCode.numeric_fallback_used}
                for item in self.diagnostics.entries
            )
        )
        if operational_fallback:
            if len(fallback_entries) != 1 or fallback_entries[0].backend is not fallback:
                raise ValueError("actual numeric fallback must have one exact diagnostic")
        elif fallback_entries:
            raise ValueError("numeric fallback diagnostic requires actual permitted fallback use")

        terminal_codes = tuple(item.code for item in self.diagnostics.entries if item.code in _TERMINAL_CODE)
        mapped_terminals = {_TERMINAL_CODE[item] for item in terminal_codes}
        if len(mapped_terminals) > 1 or len(terminal_codes) > 1:
            raise ValueError("contradictory or duplicate terminal diagnostic codes are forbidden")
        if self.terminal in failure_terminals:
            if mapped_terminals != {self.terminal}:
                raise ValueError("failure terminal requires matching closed diagnostic code")
        elif mapped_terminals:
            raise ValueError("terminal failure diagnostic requires its matching failure result")
        if (self.terminal is MechanicsSolveTerminal.timeout) != (self.diagnostics.timeout is not None):
            raise ValueError("timeout details, code, and terminal are bidirectional")

        incomplete_entries = tuple(
            item for item in self.diagnostics.entries
            if item.code is SolverDiagnosticCode.generation_incomplete
        )
        limit_entries = tuple(
            item for item in self.diagnostics.entries
            if item.code is SolverDiagnosticCode.candidate_limit_reached
        )
        if len(incomplete_entries) > 1 or len(limit_entries) > 1 or (incomplete_entries and limit_entries):
            raise ValueError("candidate generation must have one unambiguous incomplete marker")
        incomplete_marked = bool(incomplete_entries or limit_entries)
        if (self.candidate_set.coverage.value == "incomplete") != incomplete_marked:
            raise ValueError("incomplete candidate coverage and diagnostics must agree")
        if limit_entries:
            if self.terminal is not MechanicsSolveTerminal.resource_limit:
                raise ValueError("candidate limit closes as resource_limit")
            if len(self.candidate_set.candidates) != self.plan.budget.max_candidates:
                raise ValueError("candidate limit requires the exact retained budget boundary")
        if incomplete_entries and self.terminal not in failure_terminals:
            expected_terminal = (
                MechanicsSolveTerminal.needs_confirmation
                if self.verified_candidates
                else MechanicsSolveTerminal.insufficient_conditions
            )
            if self.terminal is not expected_terminal:
                raise ValueError("incomplete generation has one fail-closed answer terminal rule")
        if self.terminal in failure_terminals:
            terminal_entry = next(
                item
                for item in self.diagnostics.entries
                if item.code in _TERMINAL_CODE
            )
            if (
                terminal_entry.phase is not SolvePhase.verification
                and self.candidate_set.coverage.value != "incomplete"
            ):
                raise ValueError("pre-verification failure cannot claim complete candidate generation")
        if self.terminal is MechanicsSolveTerminal.solved and incomplete_marked:
            raise ValueError("solved cannot coexist with incomplete or limited generation")
        return self


class EvidenceSubstitution(FrozenModel):
    symbol_id: Identifier
    value_si: SIValue


class EvidenceOutput(FrozenModel):
    query_symbol_id: Identifier
    value_si: SIValue
    si_unit: OutputUnit


class EvidenceAdapterV2(FrozenModel):
    """Data-only bridge bound directly to one concrete solved result."""

    adapter_version: Literal[EVIDENCE_ADAPTER_VERSION] = EVIDENCE_ADAPTER_VERSION
    result: MechanicsSolveResult
    graph_fingerprint: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    plan_fingerprint: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    candidate_id: Identifier
    query_id: Identifier
    equation_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=512)
    source_evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    substitutions: tuple[EvidenceSubstitution, ...] = Field(min_length=1, max_length=256)
    output: EvidenceOutput
    checks: tuple[VerificationCheck, ...] = Field(min_length=1, max_length=512)

    @property
    def plan(self) -> SolvePlan:
        return self.result.plan

    @property
    def verified_candidate(self) -> VerifiedCandidate:
        return self.result.verified_candidates[0]

    @model_validator(mode="after")
    def validate_evidence(self) -> "EvidenceAdapterV2":
        expected_graph_fingerprint = self.result.plan.graph_fingerprint
        expected_plan_fingerprint = self.result.plan.plan_fingerprint
        if "graph_fingerprint" in self.model_fields_set:
            if self.graph_fingerprint is None or self.graph_fingerprint != expected_graph_fingerprint:
                raise ValueError("evidence graph fingerprint must exactly match its solved result")
        else:
            object.__setattr__(self, "graph_fingerprint", expected_graph_fingerprint)
        if "plan_fingerprint" in self.model_fields_set:
            if self.plan_fingerprint is None or self.plan_fingerprint != expected_plan_fingerprint:
                raise ValueError("evidence plan fingerprint must exactly match its solved result")
        else:
            object.__setattr__(self, "plan_fingerprint", expected_plan_fingerprint)

        if not _is_sorted_unique(self.equation_ids) or not _is_sorted_unique(self.source_evidence_ids):
            raise ValueError("evidence provenance IDs must be sorted and unique")
        symbols = tuple(item.symbol_id for item in self.substitutions)
        if not _is_sorted_unique(symbols):
            raise ValueError("evidence substitutions must be sorted and unique")
        if self.result.terminal is not MechanicsSolveTerminal.solved or self.result.selected_candidate_id is None:
            raise ValueError("evidence adapter requires one concrete solved selection")
        matching_verified = tuple(
            item for item in self.result.verified_candidates
            if item.candidate.candidate_id == self.result.selected_candidate_id
        )
        matching_outcomes = tuple(
            item for item in self.result.verification_outcomes
            if item.candidate_id == self.result.selected_candidate_id
        )
        if len(matching_verified) != 1 or len(matching_outcomes) != 1 or matching_verified[0].outcome != matching_outcomes[0]:
            raise ValueError("evidence adapter requires exactly one matching verified outcome")
        verified = matching_verified[0]
        candidate = verified.candidate
        outcome = verified.outcome
        if self.candidate_id != candidate.candidate_id or self.query_id != self.result.plan.query_id:
            raise ValueError("evidence candidate and query IDs must match the selected result")
        substitutions = tuple((item.symbol_id, item.value_si) for item in self.substitutions)
        candidate_values = tuple((item.symbol_id, item.value_si) for item in candidate.values)
        if substitutions != candidate_values:
            raise ValueError("evidence substitutions must exactly match selected candidate values")
        values = dict(substitutions)
        if values.get(self.output.query_symbol_id) != self.output.value_si:
            raise ValueError("evidence output must exactly match its query substitution")
        if self.output.query_symbol_id != verified.query_symbol_id or self.output.value_si != verified.query_value_si:
            raise ValueError("evidence output must exactly match the verified query value")
        query_symbols = tuple(
            item
            for item in self.result.plan.graph.symbols
            if item.symbol.symbol_id == self.result.plan.query_symbol_id
        )
        if len(query_symbols) != 1:
            raise ValueError("evidence query symbol must resolve exactly once in the embedded graph")
        exact_si_unit = render_canonical_si_unit(query_symbols[0].symbol.dimension)
        if self.output.si_unit != exact_si_unit:
            raise ValueError("evidence SI unit must exactly match the graph-derived query dimension")
        if self.checks != outcome.checks or any(item.status is not VerificationCheckStatus.passed for item in self.checks):
            raise ValueError("evidence checks must be the exact passing selected outcome")

        expected_equations = tuple(sorted({
            *candidate.equation_ids,
            *(identifier for check in self.checks for identifier in check.equation_ids),
        }))
        if self.equation_ids != expected_equations:
            raise ValueError("evidence equations must exactly union candidate and passing-check use")
        graph = self.result.plan.graph
        equation_by_id = {item.equation_id: item for item in graph.equations}
        constraint_by_id = {item.constraint_id: item for item in graph.constraints}
        referenced_constraints = {
            identifier
            for check in self.checks
            for identifier in check.constraint_ids
        }
        referenced_constraints.update(
            identifier
            for equation_id in expected_equations
            for identifier in equation_by_id[equation_id].constraint_ids
        )
        expected_sources = {
            identifier
            for check in self.checks
            for identifier in check.source_evidence_ids
        }
        expected_sources.update(
            identifier
            for equation_id in expected_equations
            for identifier in equation_by_id[equation_id].source_evidence_ids
        )
        expected_sources.update(
            identifier
            for constraint_id in referenced_constraints
            for identifier in constraint_by_id[constraint_id].source_evidence_ids
        )
        expected_sources.update(
            identifier
            for condition in graph.initial_conditions
            if condition.condition_id in self.result.plan.initial_condition_ids
            for identifier in condition.source_evidence_ids
        )
        expected_sources.update(
            identifier
            for application in graph.applications
            if set(application.equation_ids) & set(expected_equations)
            for identifier in application.source_evidence_ids
        )
        if self.source_evidence_ids != tuple(sorted(expected_sources)):
            raise ValueError("evidence sources must exactly match passing checks and graph provenance")
        return self


__all__ = [
    "EVIDENCE_ADAPTER_VERSION", "VERIFICATION_CONTRACT_VERSION", "VERIFICATION_POLICY_VERSION", "EvidenceAdapterV2",
    "EvidenceOutput", "EvidenceSubstitution", "MechanicsSolveResult", "MechanicsSolveTerminal",
    "VerificationCheck", "VerificationCheckKind", "VerificationCheckStatus",
    "VerificationOutcome", "VerifiedCandidate", "render_canonical_si_unit",
]
