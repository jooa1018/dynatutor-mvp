from __future__ import annotations

from decimal import Decimal
import math

import pytest
from pydantic import ValidationError

from engine.mechanics import (
    CandidateCoverage,
    CandidateSet,
    DiagnosticTimeoutInvarianceRecord,
    DiagnosticSeverity,
    DifferentialStatus,
    DiscrepancyCode,
    GenericResultInvarianceSignature,
    InvarianceField,
    InvarianceVariantKind,
    LabelledInvarianceVariant,
    LegacyCandidateScalar,
    LegacyDifferentialReport,
    LegacyObservation,
    LegacyTerminal,
    MechanicsSolveTerminal,
    MechanicsSolveResult,
    PARITY_ABSOLUTE_TOLERANCE,
    PARITY_RELATIVE_TOLERANCE,
    SolveBackendKind,
    SolvePhase,
    SolverAttempt,
    SolverDiagnosticCode,
    SolverDiagnosticEntry,
    SolverDiagnostics,
    SolverTimeout,
    build_generic_result_invariance_signature,
    build_legacy_differential_report,
    compare_generic_result_invariance,
    diagnostic_entry_sort_key,
    solve_verified_equation_graph,
)
from engine.mechanics.compiler.contracts import (
    EquationGraph,
    EquationNode,
    EquationScope,
    IncidenceEdge,
    LawApplication,
    RankAnalysis,
    SymbolNode,
)
from engine.mechanics.math_ast import (
    DimensionVector,
    Equality,
    Inequality,
    InequalityRelation,
    LiteralNode,
    Power,
    SymbolDefinition,
    SymbolRef,
)


DIMENSIONLESS = DimensionVector()


def _symbol(identifier: str) -> SymbolNode:
    return SymbolNode(
        symbol=SymbolDefinition(
            symbol_id=identifier,
            quantity_id=f"quantity_{identifier}",
            dimension=DIMENSIONLESS,
        ),
        quantity_id=f"quantity_{identifier}",
        quantity_role="position",
    )


def _graph(*, positive_only: bool = True, nonlinear: bool = False) -> EquationGraph:
    scope = EquationScope()
    equality = EquationNode(
        equation_id="eq_selected",
        expression=Equality(
            left=Power(
                base=SymbolRef(symbol_id="x"),
                exponent=LiteralNode(value=0.5 if nonlinear else 2),
            ),
            right=LiteralNode(value=2 if nonlinear else 4),
        ),
        expression_fingerprint="a" * 64,
        law_id="generic_law",
        scope=scope,
        source_evidence_ids=("source1",),
        dimension=DIMENSIONLESS,
        complexity_cost=5,
    )
    domain = EquationNode(
        equation_id="ineq_domain",
        expression=Inequality(
            relation=InequalityRelation.gt,
            left=SymbolRef(symbol_id="x"),
            right=LiteralNode(value=0),
        ),
        expression_fingerprint="b" * 64,
        law_id="generic_law",
        scope=scope,
        source_evidence_ids=("source1",),
        dimension=DIMENSIONLESS,
        complexity_cost=3,
    )
    equations = (equality, domain) if positive_only else (equality,)
    equation_ids = tuple(sorted(item.equation_id for item in equations))
    return EquationGraph(
        query_id="query_x",
        query_symbol_id="x",
        symbols=(_symbol("x"),),
        equations=equations,
        constraints=(),
        applications=(LawApplication(
            application_id="application_main",
            law_id="generic_law",
            equation_ids=equation_ids,
            scope=scope,
            source_evidence_ids=("source1",),
            complexity_cost=sum(item.complexity_cost for item in equations),
        ),),
        incidence=(IncidenceEdge(equation_id="eq_selected", symbol_id="x"),),
        rank=RankAnalysis(
            equality_count=1,
            inequality_count=1 if positive_only else 0,
            unknown_count=1,
            structural_rank=1,
            underdetermined=False,
            overdetermined=False,
            conflicting=False,
        ),
        selected_equation_ids=("eq_selected",),
        fingerprint="c" * 64,
    )


@pytest.fixture(scope="module")
def solved_result():
    result = solve_verified_equation_graph(_graph())
    assert result.terminal is MechanicsSolveTerminal.solved
    return result


@pytest.fixture(scope="module")
def ambiguous_result():
    result = solve_verified_equation_graph(_graph(positive_only=False))
    assert result.terminal is MechanicsSolveTerminal.ambiguity
    return result


@pytest.fixture(scope="module")
def nonlinear_result():
    result = solve_verified_equation_graph(_graph(nonlinear=True))
    assert result.plan.permitted_numeric_fallback is SolveBackendKind.numeric_root
    return result


def _result_with_diagnostics(
    result: MechanicsSolveResult,
    diagnostics: SolverDiagnostics,
    *,
    terminal: MechanicsSolveTerminal | None = None,
) -> MechanicsSolveResult:
    payload = result.model_dump(mode="python")
    payload["diagnostics"] = diagnostics.model_dump(mode="python")
    if terminal is not None:
        payload.update(
            terminal=terminal,
            verification_outcomes=(),
            verified_candidates=(),
            rejections=(),
            selected_candidate_id=None,
        )
    return MechanicsSolveResult.model_validate(payload)


def _verification_failure_result(
    solved_result: MechanicsSolveResult,
    *,
    code: SolverDiagnosticCode = SolverDiagnosticCode.backend_failure,
    referenced_id: str | None = None,
) -> MechanicsSolveResult:
    terminal = {
        SolverDiagnosticCode.backend_failure: MechanicsSolveTerminal.solver_error,
        SolverDiagnosticCode.backend_unsupported: MechanicsSolveTerminal.unsupported,
    }[code]
    failure = SolverDiagnosticEntry(
        code=code,
        severity=DiagnosticSeverity.error,
        phase="verification",
        backend=solved_result.plan.primary_backend,
        referenced_id=referenced_id,
    )
    entries = tuple(sorted(
        (*solved_result.diagnostics.entries, failure),
        key=diagnostic_entry_sort_key,
    ))
    diagnostics = SolverDiagnostics(
        entries=entries,
        attempts=solved_result.diagnostics.attempts,
        total_elapsed_s=solved_result.diagnostics.total_elapsed_s,
    )
    return _result_with_diagnostics(solved_result, diagnostics, terminal=terminal)


def _empty_nonsolved_result(
    solved_result: MechanicsSolveResult,
    terminal: MechanicsSolveTerminal,
) -> MechanicsSolveResult:
    candidate_set = CandidateSet(
        graph_fingerprint=solved_result.plan.graph_fingerprint,
        plan_fingerprint=solved_result.plan.plan_fingerprint,
        coverage=CandidateCoverage.incomplete,
        generation_complete=False,
        generated_count=0,
        candidates=(),
        manifest=(),
    )
    entries = [SolverDiagnosticEntry(
        code=SolverDiagnosticCode.backend_selected,
        severity=DiagnosticSeverity.info,
        phase=SolvePhase.planning,
        backend=solved_result.plan.primary_backend,
    ), SolverDiagnosticEntry(
        code=SolverDiagnosticCode.generation_incomplete,
        severity=DiagnosticSeverity.warning,
        phase=SolvePhase.candidate_generation,
        backend=solved_result.plan.primary_backend,
    )]
    attempts: tuple[SolverAttempt, ...] = ()
    timeout = None
    total_elapsed_s = 0.0
    failure_code = {
        MechanicsSolveTerminal.solver_error: SolverDiagnosticCode.backend_failure,
        MechanicsSolveTerminal.unsupported: SolverDiagnosticCode.backend_unsupported,
        MechanicsSolveTerminal.resource_limit: SolverDiagnosticCode.resource_limit,
    }.get(terminal)
    if failure_code is not None:
        entries.append(SolverDiagnosticEntry(
            code=failure_code,
            severity=DiagnosticSeverity.error,
            phase=SolvePhase.candidate_generation,
            backend=solved_result.plan.primary_backend,
        ))
    if terminal is MechanicsSolveTerminal.timeout:
        limit = solved_result.plan.budget.symbolic_time_limit_s
        entries.append(SolverDiagnosticEntry(
            code=SolverDiagnosticCode.timeout,
            severity=DiagnosticSeverity.error,
            phase=SolvePhase.symbolic,
            backend=solved_result.plan.primary_backend,
        ))
        attempts = (SolverAttempt(
            attempt_index=0,
            backend=solved_result.plan.primary_backend,
            phase=SolvePhase.symbolic,
            elapsed_s=limit,
            completed=False,
        ),)
        timeout = SolverTimeout(
            phase=SolvePhase.symbolic,
            backend=solved_result.plan.primary_backend,
            limit_s=limit,
            elapsed_s=limit,
        )
        total_elapsed_s = limit
    diagnostics = SolverDiagnostics(
        entries=tuple(sorted(entries, key=diagnostic_entry_sort_key)),
        attempts=attempts,
        total_elapsed_s=total_elapsed_s,
        timeout=timeout,
    )
    return MechanicsSolveResult(
        terminal=terminal,
        plan=solved_result.plan,
        candidate_set=candidate_set,
        diagnostics=diagnostics,
    )


def _observation(
    *,
    selected: float = 2.0,
    candidates: tuple[LegacyCandidateScalar, ...] | None = (
        LegacyCandidateScalar(value_si=-2.0, multiplicity=1),
        LegacyCandidateScalar(value_si=2.0, multiplicity=1),
    ),
    terminal: LegacyTerminal = LegacyTerminal.solved,
    unit: str = "1",
    residual: bool | None = True,
) -> LegacyObservation:
    return LegacyObservation(
        case_id="case1",
        diagnostic_kernel_id="kernel1",
        terminal=terminal,
        query_symbol_id="x",
        si_unit=unit,
        selected_scalar_si=selected if terminal is LegacyTerminal.solved else None,
        complete_candidate_scalars_si=candidates,
        residual_passed=residual,
    )


def test_real_public_pipeline_vertical_match_and_mismatch(solved_result) -> None:
    matching = build_legacy_differential_report(solved_result, _observation())
    assert matching.status is DifferentialStatus.full_parity
    assert matching.discrepancies == ()
    assert matching.graph_fingerprint == solved_result.plan.graph_fingerprint
    assert matching.plan_fingerprint == solved_result.plan.plan_fingerprint
    assert matching.generic_candidate_manifest == solved_result.candidate_set.manifest
    assert matching.generic_candidate_ids == tuple(
        item.candidate_id for item in solved_result.candidate_set.candidates
    )
    assert matching.generic_selected_candidate_id == solved_result.selected_candidate_id

    mismatching = build_legacy_differential_report(
        solved_result,
        _observation(
            selected=2.01,
            candidates=(
                LegacyCandidateScalar(value_si=-2.0, multiplicity=1),
                LegacyCandidateScalar(value_si=2.01, multiplicity=1),
            ),
        ),
    )
    assert mismatching.status is DifferentialStatus.mismatch
    assert DiscrepancyCode.selected_scalar_mismatch in mismatching.discrepancies
    assert DiscrepancyCode.candidate_multiset_mismatch in mismatching.discrepancies


def test_contracts_round_trip_through_python_and_json(solved_result) -> None:
    observation = _observation()
    report = build_legacy_differential_report(solved_result, observation)
    signature = build_generic_result_invariance_signature(solved_result)

    for model in (observation, report, signature):
        assert type(model).model_validate(model.model_dump()) == model
        assert type(model).model_validate_json(model.model_dump_json()) == model
        assert type(model).model_json_schema()["additionalProperties"] is False

    comparison = compare_generic_result_invariance(
        signature,
        (LabelledInvarianceVariant(
            label="same",
            kind=InvarianceVariantKind.unit_equivalent,
            signature=signature,
        ),),
    )
    for model in (report, signature, comparison):
        payload = model.model_dump()
        payload["selected_answer"] = 999.0
        with pytest.raises(ValidationError, match="Extra inputs"):
            type(model).model_validate(payload)


def test_terminal_report_shapes_reject_all_bidirectional_contradictions(solved_result) -> None:
    genuine = build_legacy_differential_report(solved_result, _observation())

    forged_payloads = []
    observation_not_comparable_full = genuine.model_dump(mode="python")
    observation_not_comparable_full["observation_terminal"] = LegacyTerminal.not_comparable
    forged_payloads.append(observation_not_comparable_full)

    solved_with_nonsolved_code = genuine.model_dump(mode="python")
    solved_with_nonsolved_code.update(
        status=DifferentialStatus.not_comparable,
        discrepancies=(DiscrepancyCode.generic_nonsolved_result,),
    )
    forged_payloads.append(solved_with_nonsolved_code)

    solved_observation_with_not_comparable_code = genuine.model_dump(mode="python")
    solved_observation_with_not_comparable_code.update(
        status=DifferentialStatus.not_comparable,
        discrepancies=(DiscrepancyCode.observation_not_comparable,),
    )
    forged_payloads.append(solved_observation_with_not_comparable_code)

    equal_terminals_with_mismatch = genuine.model_dump(mode="python")
    equal_terminals_with_mismatch.update(
        status=DifferentialStatus.mismatch,
        discrepancies=(DiscrepancyCode.terminal_mismatch,),
    )
    forged_payloads.append(equal_terminals_with_mismatch)

    ambiguity_claiming_full = genuine.model_dump(mode="python")
    ambiguity_claiming_full["observation_terminal"] = LegacyTerminal.ambiguity
    forged_payloads.append(ambiguity_claiming_full)

    for payload in forged_payloads:
        with pytest.raises(ValidationError, match="terminal discrepancy|solved terminals"):
            LegacyDifferentialReport.model_validate(payload)


def test_terminal_factory_reports_remain_valid_round_trips(
    solved_result,
    ambiguous_result,
) -> None:
    reports = (
        build_legacy_differential_report(solved_result, _observation()),
        build_legacy_differential_report(solved_result, _observation(candidates=None)),
        build_legacy_differential_report(ambiguous_result, _observation()),
        build_legacy_differential_report(
            solved_result,
            LegacyObservation(
                case_id="caseNotComparable",
                diagnostic_kernel_id="kernel1",
                terminal=LegacyTerminal.not_comparable,
            ),
        ),
        build_legacy_differential_report(
            solved_result,
            _observation(terminal=LegacyTerminal.ambiguity),
        ),
    )
    expected_statuses = (
        DifferentialStatus.full_parity,
        DifferentialStatus.selected_output_only_match,
        DifferentialStatus.not_comparable,
        DifferentialStatus.not_comparable,
        DifferentialStatus.mismatch,
    )
    for report, expected_status in zip(reports, expected_statuses):
        assert report.status is expected_status
        assert LegacyDifferentialReport.model_validate(report.model_dump()) == report
        assert LegacyDifferentialReport.model_validate_json(report.model_dump_json()) == report


def test_every_nonsolved_terminal_and_observation_branch_validates(
    solved_result,
    ambiguous_result,
    nonlinear_result,
) -> None:
    results = (
        ambiguous_result,
        nonlinear_result,
        _empty_nonsolved_result(
            solved_result,
            MechanicsSolveTerminal.insufficient_conditions,
        ),
        _empty_nonsolved_result(solved_result, MechanicsSolveTerminal.solver_error),
        _empty_nonsolved_result(solved_result, MechanicsSolveTerminal.timeout),
        _empty_nonsolved_result(solved_result, MechanicsSolveTerminal.resource_limit),
        _empty_nonsolved_result(solved_result, MechanicsSolveTerminal.unsupported),
    )
    assert {item.terminal for item in results} == {
        item for item in MechanicsSolveTerminal
        if item is not MechanicsSolveTerminal.solved
    }
    for result in results:
        matching_observation = LegacyObservation(
            case_id="caseMatchingTerminal",
            diagnostic_kernel_id="kernel1",
            terminal=LegacyTerminal(result.terminal.value),
            query_symbol_id="x",
            si_unit="1",
        )
        observations = (
            matching_observation,
            _observation(),
            LegacyObservation(
                case_id="caseNotComparable",
                diagnostic_kernel_id="kernel1",
                terminal=LegacyTerminal.not_comparable,
            ),
        )
        for observation in observations:
            report = build_legacy_differential_report(result, observation)
            assert report.status is DifferentialStatus.not_comparable
            assert DiscrepancyCode.generic_nonsolved_result in report.discrepancies
            assert (
                DiscrepancyCode.observation_not_comparable in report.discrepancies
            ) == (observation.terminal is LegacyTerminal.not_comparable)
            assert (
                DiscrepancyCode.terminal_mismatch in report.discrepancies
            ) == (
                observation.terminal is not LegacyTerminal.not_comparable
                and observation.terminal.value != result.terminal.value
            )
            assert (
                DiscrepancyCode.generic_nonsolved_promotion_forbidden
                in report.discrepancies
            ) == (observation.terminal is LegacyTerminal.solved)
            assert LegacyDifferentialReport.model_validate_json(
                report.model_dump_json()
            ) == report


@pytest.mark.parametrize("field", ["raw_text", "problem_text", "system_type", "subtype", "expected_answer"])
def test_observation_forbids_extra_and_authority_shaped_fields(field: str) -> None:
    payload = _observation().model_dump()
    payload[field] = "forged"
    with pytest.raises(ValidationError, match="Extra inputs"):
        LegacyObservation.model_validate(payload)


def test_strict_bools_ints_finite_numbers_and_bounds() -> None:
    with pytest.raises(ValidationError):
        LegacyCandidateScalar(value_si=True, multiplicity=1)
    with pytest.raises(ValidationError):
        LegacyCandidateScalar(value_si=1.0, multiplicity=True)
    with pytest.raises(ValidationError):
        _observation(residual=1)  # type: ignore[arg-type]
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValidationError):
            LegacyCandidateScalar(value_si=value, multiplicity=1)
    with pytest.raises(ValidationError):
        LegacyCandidateScalar(value_si=1.0, multiplicity=1025)
    with pytest.raises(ValidationError):
        LegacyObservation(
            case_id="x" * 65,
            diagnostic_kernel_id="kernel1",
            terminal=LegacyTerminal.not_comparable,
        )


def test_migration_numeric_fields_reject_coercion_but_accept_json_integers(solved_result) -> None:
    for value in ("2", Decimal("2"), True, math.nan, math.inf, -math.inf, 10**400):
        with pytest.raises(ValidationError):
            LegacyCandidateScalar(value_si=value, multiplicity=1)

    observation_payload = _observation().model_dump(mode="python")
    observation_payload["selected_scalar_si"] = "2"
    with pytest.raises(ValidationError):
        LegacyObservation.model_validate(observation_payload)

    signature = build_generic_result_invariance_signature(solved_result)
    candidate_payload = signature.candidate_records[0].model_dump(mode="python")
    for query_value in ("-2", ("-2",), (True,), (math.inf,)):
        candidate_payload["query_value_si"] = query_value
        with pytest.raises(ValidationError):
            type(signature.candidate_records[0]).model_validate(candidate_payload)

    with pytest.raises(ValidationError):
        DiagnosticTimeoutInvarianceRecord(
            phase="verification",
            backend=solved_result.plan.primary_backend,
            limit_s="5",
        )

    report_payload = build_legacy_differential_report(
        solved_result,
        _observation(),
    ).model_dump(mode="python")
    report_payload["absolute_tolerance"] = "1e-9"
    with pytest.raises(ValidationError):
        LegacyDifferentialReport.model_validate(report_payload)

    json_scalar = LegacyCandidateScalar.model_validate_json(
        '{"value_si":2,"multiplicity":1}'
    )
    assert json_scalar.value_si == 2.0
    json_observation = LegacyObservation.model_validate_json(
        '{"case_id":"case1","diagnostic_kernel_id":"kernel1",'
        '"terminal":"solved","query_symbol_id":"x","si_unit":"1",'
        '"selected_scalar_si":2,"complete_candidate_scalars_si":'
        '[{"value_si":2,"multiplicity":1}],"residual_passed":true}'
    )
    assert json_observation.selected_scalar_si == 2.0


def test_observation_enforces_solved_and_non_solved_shapes() -> None:
    with pytest.raises(ValidationError, match="solved observation"):
        LegacyObservation(
            case_id="case1",
            diagnostic_kernel_id="kernel1",
            terminal=LegacyTerminal.solved,
            query_symbol_id="x",
            si_unit="1",
        )
    with pytest.raises(ValidationError, match="solved observation"):
        LegacyObservation(
            case_id="case1",
            diagnostic_kernel_id="kernel1",
            terminal=LegacyTerminal.ambiguity,
            query_symbol_id="x",
            si_unit="1",
            selected_scalar_si=2.0,
        )
    not_comparable = LegacyObservation(
        case_id="case1",
        diagnostic_kernel_id="kernel1",
        terminal=LegacyTerminal.not_comparable,
    )
    assert not_comparable.complete_candidate_scalars_si is None
    with pytest.raises(ValidationError, match="query metadata"):
        LegacyObservation(
            case_id="case1",
            diagnostic_kernel_id="kernel1",
            terminal=LegacyTerminal.not_comparable,
            query_symbol_id="x",
        )
    for noncanonical_unit in ("m*kg", "m*m", "m^0", "m^1", "m^02", "m^-01"):
        with pytest.raises(ValidationError):
            _observation(unit=noncanonical_unit)


def test_fixed_tolerances_cannot_be_widened_and_edges_are_bounded(solved_result) -> None:
    inside = 2.0 + 1.9e-9
    outside = 2.0 + 2.1e-9
    inside_report = build_legacy_differential_report(
        solved_result,
        _observation(
            selected=inside,
            candidates=(
                LegacyCandidateScalar(value_si=-2.0, multiplicity=1),
                LegacyCandidateScalar(value_si=inside, multiplicity=1),
            ),
        ),
    )
    outside_report = build_legacy_differential_report(
        solved_result,
        _observation(
            selected=outside,
            candidates=(
                LegacyCandidateScalar(value_si=-2.0, multiplicity=1),
                LegacyCandidateScalar(value_si=outside, multiplicity=1),
            ),
        ),
    )
    assert inside_report.status is DifferentialStatus.full_parity
    assert outside_report.status is DifferentialStatus.mismatch
    assert inside_report.absolute_tolerance == PARITY_ABSOLUTE_TOLERANCE
    assert inside_report.relative_tolerance == PARITY_RELATIVE_TOLERANCE
    payload = inside_report.model_dump()
    payload["absolute_tolerance"] = 1.0
    with pytest.raises(ValidationError):
        LegacyDifferentialReport.model_validate(payload)


def test_candidate_order_is_ignored_but_multiplicity_is_exact(solved_result) -> None:
    reordered = _observation(
        candidates=(
            LegacyCandidateScalar(value_si=2.0, multiplicity=1),
            LegacyCandidateScalar(value_si=-2.0, multiplicity=1),
        ),
    )
    assert build_legacy_differential_report(solved_result, reordered).status is DifferentialStatus.full_parity

    multiplicity_mismatch = _observation(
        candidates=(
            LegacyCandidateScalar(value_si=-2.0, multiplicity=1),
            LegacyCandidateScalar(value_si=2.0, multiplicity=2),
        ),
    )
    report = build_legacy_differential_report(solved_result, multiplicity_mismatch)
    assert report.status is DifferentialStatus.mismatch
    assert DiscrepancyCode.candidate_multiset_mismatch in report.discrepancies


@pytest.mark.parametrize(
    ("observation", "code"),
    [
        (_observation(unit="m"), DiscrepancyCode.canonical_si_unit_mismatch),
        (
            _observation(terminal=LegacyTerminal.ambiguity),
            DiscrepancyCode.terminal_mismatch,
        ),
        (_observation(residual=False), DiscrepancyCode.residual_failed),
    ],
)
def test_wrong_unit_terminal_and_failed_residual_are_mismatches(
    solved_result,
    observation: LegacyObservation,
    code: DiscrepancyCode,
) -> None:
    report = build_legacy_differential_report(solved_result, observation)
    assert report.status is DifferentialStatus.mismatch
    assert code in report.discrepancies


def test_selected_only_match_is_insufficient_for_full_parity(solved_result) -> None:
    report = build_legacy_differential_report(
        solved_result,
        _observation(candidates=None),
    )
    assert report.status is DifferentialStatus.selected_output_only_match
    assert report.discrepancies == (
        DiscrepancyCode.exhaustive_candidates_not_exposed,
    )


def test_solved_observation_cannot_promote_ambiguous_generic_result(ambiguous_result) -> None:
    report = build_legacy_differential_report(ambiguous_result, _observation())
    assert report.status is DifferentialStatus.not_comparable
    assert report.generic_terminal is MechanicsSolveTerminal.ambiguity
    assert report.generic_selected_candidate_id is None
    assert DiscrepancyCode.generic_nonsolved_result in report.discrepancies
    assert DiscrepancyCode.generic_nonsolved_promotion_forbidden in report.discrepancies


def test_matching_ambiguity_and_validated_solver_error_are_not_comparable(
    ambiguous_result,
    solved_result,
) -> None:
    matching_ambiguity = _observation(terminal=LegacyTerminal.ambiguity)
    ambiguity_report = build_legacy_differential_report(
        ambiguous_result,
        matching_ambiguity,
    )
    assert ambiguity_report.status is DifferentialStatus.not_comparable
    assert ambiguity_report.discrepancies == (
        DiscrepancyCode.generic_nonsolved_result,
    )

    solver_error = _verification_failure_result(solved_result)
    error_observation = _observation(terminal=LegacyTerminal.solver_error)
    error_report = build_legacy_differential_report(solver_error, error_observation)
    assert error_report.status is DifferentialStatus.not_comparable
    assert error_report.generic_terminal is MechanicsSolveTerminal.solver_error
    assert DiscrepancyCode.generic_nonsolved_result in error_report.discrepancies


def test_not_exposed_candidates_are_distinct_from_an_empty_complete_set(solved_result) -> None:
    not_exposed = build_legacy_differential_report(solved_result, _observation(candidates=None))
    empty = _observation(candidates=())
    empty_report = build_legacy_differential_report(solved_result, empty)
    assert not_exposed.status is DifferentialStatus.selected_output_only_match
    assert empty_report.status is DifferentialStatus.mismatch
    assert DiscrepancyCode.candidate_multiset_mismatch in empty_report.discrepancies


def test_forged_observation_cannot_mutate_or_change_generic_result(solved_result) -> None:
    before = solved_result.model_dump_json()
    forged = _observation(
        selected=999.0,
        candidates=(LegacyCandidateScalar(value_si=999.0, multiplicity=1),),
    )
    report = build_legacy_differential_report(solved_result, forged)
    assert report.status is DifferentialStatus.mismatch
    assert solved_result.model_dump_json() == before
    assert solved_result.selected_candidate_id == solved_result.verified_candidates[0].candidate.candidate_id
    with pytest.raises(ValidationError):
        forged.selected_scalar_si = 2.0

    forged_shape = solved_result.model_copy(
        update={"selected_candidate_id": solved_result.candidate_set.candidates[0].candidate_id}
    )
    with pytest.raises(ValidationError):
        build_generic_result_invariance_signature(forged_shape)
    forged_observation = _observation().model_copy(update={"terminal": LegacyTerminal.ambiguity})
    with pytest.raises(ValidationError):
        build_legacy_differential_report(solved_result, forged_observation)


def test_report_binds_selection_and_outcomes_to_nested_generic_signature(solved_result) -> None:
    report = build_legacy_differential_report(solved_result, _observation())
    failed_id = solved_result.candidate_set.candidates[0].candidate_id

    changed_selection = report.model_dump(mode="python")
    changed_selection["generic_selected_candidate_id"] = failed_id
    with pytest.raises(ValidationError, match="signature"):
        LegacyDifferentialReport.model_validate(changed_selection)

    changed_verified = report.model_dump(mode="python")
    changed_verified["generic_verified_candidate_ids"] = (failed_id,)
    with pytest.raises(ValidationError, match="signature"):
        LegacyDifferentialReport.model_validate(changed_verified)

    changed_nested = report.model_dump(mode="python")
    changed_nested["generic_invariance_signature"]["verified_candidate_ids"] = (failed_id,)
    with pytest.raises(ValidationError):
        LegacyDifferentialReport.model_validate(changed_nested)

    changed_rejections = report.model_dump(mode="python")
    changed_rejections["generic_rejection_authoritative_sha256"] = ()
    with pytest.raises(ValidationError, match="signature"):
        LegacyDifferentialReport.model_validate(changed_rejections)


def test_invariance_signature_excludes_diagnostic_elapsed_telemetry(solved_result) -> None:
    baseline = build_generic_result_invariance_signature(solved_result)
    changed_attempts = tuple(
        item.model_copy(update={"elapsed_s": item.elapsed_s + 0.000001})
        for item in solved_result.diagnostics.attempts
    )
    changed_diagnostics = solved_result.diagnostics.model_copy(
        update={
            "attempts": changed_attempts,
            "total_elapsed_s": solved_result.diagnostics.total_elapsed_s + 0.001,
        }
    )
    timing_variant = solved_result.model_copy(update={"diagnostics": changed_diagnostics})
    variant = build_generic_result_invariance_signature(timing_variant)
    assert variant == baseline
    assert variant.signature_sha256 == baseline.signature_sha256


def test_timeout_invariance_excludes_elapsed_but_binds_limit_and_provenance(solved_result) -> None:
    timeout_entry = SolverDiagnosticEntry(
        code=SolverDiagnosticCode.timeout,
        severity=DiagnosticSeverity.error,
        phase=SolvePhase.verification,
        backend=solved_result.plan.primary_backend,
    )
    selected_entry = next(
        item for item in solved_result.diagnostics.entries
        if item.code is SolverDiagnosticCode.backend_selected
    )

    def timeout_result(elapsed: float) -> MechanicsSolveResult:
        timeout = SolverTimeout(
            phase=SolvePhase.verification,
            backend=solved_result.plan.primary_backend,
            limit_s=solved_result.plan.budget.verification_time_limit_s,
            elapsed_s=elapsed,
        )
        attempt = SolverAttempt(
            attempt_index=0,
            backend=solved_result.plan.primary_backend,
            phase=SolvePhase.verification,
            elapsed_s=elapsed,
            completed=False,
        )
        diagnostics = SolverDiagnostics(
            entries=tuple(sorted(
                (selected_entry, timeout_entry),
                key=diagnostic_entry_sort_key,
            )),
            attempts=(attempt,),
            total_elapsed_s=elapsed,
            timeout=timeout,
        )
        return _result_with_diagnostics(
            solved_result,
            diagnostics,
            terminal=MechanicsSolveTerminal.timeout,
        )

    baseline = build_generic_result_invariance_signature(timeout_result(5.0))
    elapsed_variant = build_generic_result_invariance_signature(timeout_result(5.1))
    assert baseline == elapsed_variant
    assert baseline.diagnostic_timeout.limit_s == 5.0

    timeout_payload = baseline.model_dump(mode="python")
    timeout_payload.pop("signature_sha256")
    timeout_payload["diagnostic_timeout"]["limit_s"] = 4.0
    changed_limit = GenericResultInvarianceSignature.model_validate(timeout_payload)
    comparison = compare_generic_result_invariance(
        baseline,
        (LabelledInvarianceVariant(
            label="limitChanged",
            kind=InvarianceVariantKind.unit_equivalent,
            signature=changed_limit,
        ),),
    )
    assert comparison.variants[0].differing_fields == (
        InvarianceField.diagnostic_timeout,
    )


def test_deterministic_diagnostic_changes_are_invariance_fields(solved_result) -> None:
    failure = _verification_failure_result(solved_result)
    unsupported = _verification_failure_result(
        solved_result,
        code=SolverDiagnosticCode.backend_unsupported,
    )
    failure_signature = build_generic_result_invariance_signature(failure)
    unsupported_signature = build_generic_result_invariance_signature(unsupported)
    failure_comparison = compare_generic_result_invariance(
        failure_signature,
        (LabelledInvarianceVariant(
            label="failureCode",
            kind=InvarianceVariantKind.system_type_changed,
            signature=unsupported_signature,
        ),),
    ).variants[0]
    assert InvarianceField.diagnostic_entries in failure_comparison.differing_fields
    assert InvarianceField.terminal in failure_comparison.differing_fields

    referenced = _verification_failure_result(
        solved_result,
        referenced_id="eq_selected",
    )
    referenced_signature = build_generic_result_invariance_signature(referenced)
    referenced_comparison = compare_generic_result_invariance(
        failure_signature,
        (LabelledInvarianceVariant(
            label="referenceChanged",
            kind=InvarianceVariantKind.raw_text_paraphrase,
            signature=referenced_signature,
        ),),
    ).variants[0]
    assert referenced_comparison.differing_fields == (
        InvarianceField.diagnostic_entries,
    )


def test_operational_fallback_diagnostics_change_invariance(nonlinear_result) -> None:
    empty_candidates = CandidateSet(
        graph_fingerprint=nonlinear_result.plan.graph_fingerprint,
        plan_fingerprint=nonlinear_result.plan.plan_fingerprint,
        coverage=CandidateCoverage.incomplete,
        generation_complete=False,
        generated_count=0,
        candidates=(),
        manifest=(),
    )
    selected_entry = SolverDiagnosticEntry(
        code=SolverDiagnosticCode.backend_selected,
        severity=DiagnosticSeverity.info,
        phase=SolvePhase.planning,
        backend=nonlinear_result.plan.primary_backend,
    )
    incomplete_entry = SolverDiagnosticEntry(
        code=SolverDiagnosticCode.generation_incomplete,
        severity=DiagnosticSeverity.warning,
        phase=SolvePhase.candidate_generation,
        backend=nonlinear_result.plan.primary_backend,
    )
    failure_entry = SolverDiagnosticEntry(
        code=SolverDiagnosticCode.backend_failure,
        severity=DiagnosticSeverity.error,
        phase=SolvePhase.candidate_generation,
        backend=nonlinear_result.plan.primary_backend,
    )
    baseline_diagnostics = SolverDiagnostics(
        entries=tuple(sorted(
            (selected_entry, incomplete_entry, failure_entry),
            key=diagnostic_entry_sort_key,
        )),
        total_elapsed_s=0.0,
    )
    baseline_result = MechanicsSolveResult(
        terminal=MechanicsSolveTerminal.solver_error,
        plan=nonlinear_result.plan,
        candidate_set=empty_candidates,
        diagnostics=baseline_diagnostics,
    )
    baseline = build_generic_result_invariance_signature(baseline_result)
    fallback_entry = SolverDiagnosticEntry(
        code=SolverDiagnosticCode.numeric_fallback_used,
        severity=DiagnosticSeverity.warning,
        phase=SolvePhase.numeric,
        backend=SolveBackendKind.numeric_root,
    )
    fallback_attempt = SolverAttempt(
        attempt_index=0,
        backend=SolveBackendKind.numeric_root,
        phase=SolvePhase.numeric,
        elapsed_s=0.001,
        completed=True,
    )
    diagnostics = SolverDiagnostics(
        entries=tuple(sorted(
            (*baseline_diagnostics.entries, fallback_entry),
            key=diagnostic_entry_sort_key,
        )),
        attempts=(fallback_attempt,),
        total_elapsed_s=0.001,
    )
    fallback_result = MechanicsSolveResult(
        terminal=MechanicsSolveTerminal.solver_error,
        plan=nonlinear_result.plan,
        candidate_set=empty_candidates,
        diagnostics=diagnostics,
    )
    fallback_signature = build_generic_result_invariance_signature(fallback_result)
    comparison = compare_generic_result_invariance(
        baseline,
        (LabelledInvarianceVariant(
            label="fallbackUsed",
            kind=InvarianceVariantKind.system_type_removed,
            signature=fallback_signature,
        ),),
    ).variants[0]
    assert comparison.differing_fields == (
        InvarianceField.diagnostic_entries,
        InvarianceField.diagnostic_attempts,
    )


def test_invariance_signature_binds_exact_candidate_verification_and_selection(solved_result) -> None:
    signature = build_generic_result_invariance_signature(solved_result)
    assert signature.candidate_coverage is solved_result.candidate_set.coverage
    assert signature.generation_complete is solved_result.candidate_set.generation_complete
    assert tuple(item.candidate_id for item in signature.candidate_records) == tuple(
        item.candidate_id for item in solved_result.candidate_set.candidates
    )
    assert tuple(item.query_value_si for item in signature.candidate_records) == (-2.0, 2.0)
    assert tuple(item.root_multiplicity for item in signature.candidate_records) == (1, 1)
    assert tuple(item.authoritative_sha256 for item in signature.candidate_records) == tuple(
        item.authoritative_sha256 for item in solved_result.candidate_set.manifest
    )
    assert tuple(item.candidate_id for item in signature.verification_outcomes) == tuple(
        item.candidate_id for item in solved_result.verification_outcomes
    )
    assert signature.rejection_authoritative_sha256
    assert signature.verified_candidate_ids == (solved_result.selected_candidate_id,)
    assert GenericResultInvarianceSignature.model_validate_json(signature.model_dump_json()) == signature


def test_labelled_invariance_reports_every_exact_differing_field(solved_result) -> None:
    baseline = build_generic_result_invariance_signature(solved_result)
    replacements = {
        InvarianceField.graph_fingerprint: "d" * 64,
        InvarianceField.plan_fingerprint: "e" * 64,
        InvarianceField.primary_backend: SolveBackendKind.linear_symbolic,
        InvarianceField.permitted_numeric_fallback: SolveBackendKind.numeric_root,
        InvarianceField.candidate_coverage: CandidateCoverage.bounded_numeric,
        InvarianceField.generation_complete: False,
        InvarianceField.candidate_records: (),
        InvarianceField.verification_outcomes: (),
        InvarianceField.rejection_authoritative_sha256: (),
        InvarianceField.verified_candidate_ids: (),
        InvarianceField.diagnostic_entries: (),
        InvarianceField.diagnostic_attempts: (),
        InvarianceField.diagnostic_timeout: DiagnosticTimeoutInvarianceRecord(
            phase="verification",
            backend=solved_result.plan.primary_backend,
            limit_s=5.0,
        ),
        InvarianceField.terminal: MechanicsSolveTerminal.ambiguity,
        InvarianceField.selected_candidate_id: None,
    }
    variants = tuple(
        LabelledInvarianceVariant.model_construct(
            label=f"variant{index}",
            kind=tuple(InvarianceVariantKind)[index % len(InvarianceVariantKind)],
            signature=baseline.model_copy(
                update={field.value: replacement, "signature_sha256": str(index % 10) * 64}
            ),
        )
        for index, (field, replacement) in enumerate(replacements.items())
    )
    comparison = compare_generic_result_invariance(baseline, variants)
    for field, item in zip(replacements, comparison.variants):
        assert item.matches_baseline is False
        assert item.differing_fields == (field,)

    same = LabelledInvarianceVariant(
        label="same",
        kind=InvarianceVariantKind.unit_equivalent,
        signature=baseline,
    )
    same_comparison = compare_generic_result_invariance(baseline, (same,)).variants[0]
    assert same_comparison.matches_baseline is True
    assert same_comparison.differing_fields == ()
