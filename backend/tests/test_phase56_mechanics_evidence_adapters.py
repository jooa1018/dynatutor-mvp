from __future__ import annotations

from dataclasses import asdict, replace
import inspect
import json
from pathlib import Path
import re

import pytest

from engine.mechanics.compiler import (
    ConstraintNode,
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
    LiteralNode,
    Power,
    SymbolDefinition,
    SymbolRef,
)
from engine.mechanics.solver import (
    CandidateSet,
    CandidateValue,
    SolvePlan,
    SolverBudget,
    SolverDiagnosticEntry,
    SolverDiagnostics,
    candidate_generation_manifest,
    make_solver_candidate,
    numeric_fallback_for_structure,
    primary_backend_for_structure,
)
from engine.mechanics.solver.contracts import (
    _graph_event_ids,
    _graph_evidence_ids,
    _graph_structure,
    _graph_unknown_ids,
)
from engine.mechanics.verification.adapters import (
    LegacyProjectionLimitation,
    LegacyProjectionStatus,
    build_evidence_adapter,
    build_legacy_evidence_projection,
    build_legacy_verification_report,
    build_solver_explanation_evidence,
    to_legacy_verification_checks,
)
from engine.mechanics.verification.verifier import verify_solver_candidates
from engine.verification.types import VerificationStatus


def _graph(
    *,
    expression: Equality | None = None,
    dimension: DimensionVector = DimensionVector(),
    shape: str = "scalar",
    vector_length: int | None = None,
    known_value: float | tuple[float, ...] = 2.0,
    role: str = "position",
) -> EquationGraph:
    x = SymbolNode(
        symbol=SymbolDefinition(
            symbol_id="x",
            quantity_id="quantity_x",
            dimension=dimension,
            shape=shape,
            vector_length=vector_length,
        ),
        quantity_id="quantity_x",
        quantity_role=role,
    )
    g = SymbolNode(
        symbol=SymbolDefinition(
            symbol_id="g",
            quantity_id="quantity_g",
            dimension=dimension,
            shape=shape,
            vector_length=vector_length,
        ),
        quantity_id="quantity_g",
        quantity_role="parameter",
        known_si_value=known_value,
    )
    equation = EquationNode(
        equation_id="eq_selected",
        expression=expression or Equality(
            left=SymbolRef(symbol_id="x"),
            right=SymbolRef(symbol_id="g"),
        ),
        expression_fingerprint="b" * 64,
        law_id="generic_law",
        scope=EquationScope(),
        source_evidence_ids=("source_one",),
        dimension=dimension,
        complexity_cost=4,
    )
    return EquationGraph(
        query_id="query_x",
        query_symbol_id="x",
        symbols=(g, x),
        equations=(equation,),
        constraints=(),
        applications=(LawApplication(
            application_id="application_main",
            law_id="generic_law",
            equation_ids=("eq_selected",),
            scope=EquationScope(),
            source_evidence_ids=("source_one",),
            complexity_cost=4,
        ),),
        incidence=(IncidenceEdge(equation_id="eq_selected", symbol_id="x"),),
        rank=RankAnalysis(
            equality_count=1,
            inequality_count=0,
            unknown_count=1,
            structural_rank=1,
            underdetermined=False,
            overdetermined=False,
            conflicting=False,
        ),
        selected_equation_ids=("eq_selected",),
        fingerprint="a" * 64,
    )


def _plan(graph: EquationGraph) -> SolvePlan:
    unknowns = _graph_unknown_ids(graph)
    structure = _graph_structure(graph, unknowns)
    return SolvePlan(
        graph=graph,
        query_id=graph.query_id,
        query_symbol_id=graph.query_symbol_id,
        selected_equality_ids=graph.selected_equation_ids,
        inequality_ids=tuple(sorted(
            item.equation_id
            for item in graph.equations
            if isinstance(item.expression, Inequality)
        )),
        constraint_ids=tuple(sorted(item.constraint_id for item in graph.constraints)),
        initial_condition_ids=(),
        event_ids=_graph_event_ids(graph),
        allowed_source_evidence_ids=_graph_evidence_ids(graph),
        unknown_symbol_ids=unknowns,
        known_symbol_ids=("g",),
        structure=structure,
        primary_backend=primary_backend_for_structure(structure),
        permitted_numeric_fallback=numeric_fallback_for_structure(structure),
        budget=SolverBudget(),
    )


def _candidate(
    plan: SolvePlan,
    value: float | tuple[float, ...],
    *,
    generation_index: int = 0,
    root_index: int = 0,
) -> object:
    return make_solver_candidate(
        generation_index=generation_index,
        root_index=root_index,
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        backend=plan.primary_backend,
        approximate=False,
        equation_ids=plan.selected_equality_ids,
        values=(CandidateValue(symbol_id="x", value_si=value),),
        query_symbol_id="x",
        query_value_si=value,
    )


def _result(
    graph: EquationGraph,
    *candidate_specs: tuple[float | tuple[float, ...], int, int],
):
    plan = _plan(graph)
    candidates = tuple(
        _candidate(plan, value, generation_index=generation_index, root_index=root_index)
        for value, generation_index, root_index in candidate_specs
    )
    candidate_set = CandidateSet(
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        coverage="exhaustive_symbolic",
        generation_complete=True,
        generated_count=len(candidates),
        candidates=candidates,
        manifest=candidate_generation_manifest(candidates),
    )
    diagnostics = SolverDiagnostics(
        entries=(SolverDiagnosticEntry(
            code="backend_selected",
            severity="info",
            phase="planning",
            backend=plan.primary_backend,
        ),),
        total_elapsed_s=0.01,
    )
    return verify_solver_candidates(plan, candidate_set, diagnostics)


def test_v2_adapter_binds_selected_candidate_checks_substitutions_and_si_unit() -> None:
    force = DimensionVector(mass=1, length=1, time=-2)
    result = _result(_graph(dimension=force), (2.0, 0, 0))
    adapter = build_evidence_adapter(result)
    assert adapter.result == result
    assert adapter.candidate_id == result.selected_candidate_id
    assert adapter.query_id == "query_x"
    assert adapter.equation_ids == ("eq_selected",)
    assert adapter.source_evidence_ids == ("source_one",)
    assert [(item.symbol_id, item.value_si) for item in adapter.substitutions] == [("x", 2.0)]
    assert adapter.output.query_symbol_id == "x"
    assert adapter.output.value_si == 2.0
    assert adapter.output.si_unit == "kg*m*s^-2"
    assert adapter.checks == result.verified_candidates[0].outcome.checks


def test_legacy_projection_serializes_exact_selected_links_without_text_authority() -> None:
    result = _result(_graph(dimension=DimensionVector(length=1)), (2.0, 0, 0))
    projection = build_legacy_evidence_projection(result)
    assert projection.status is LegacyProjectionStatus.projected
    assert projection.limitation is None
    assert projection.selected_generation_index == 0
    assert projection.selected_root_index == 0
    assert projection.selected_root_multiplicity == 1
    assert not projection.rejected_candidates
    assert projection.verification_report is not None
    assert projection.verification_report.passed
    assert projection.verification_report.dimension_summary == "m"
    assert projection.verification_report.checks == []
    assert projection.verification_report.errors == []
    assert projection.verification_report.structured_checks == [
        item.to_dict() for item in projection.verification_checks
    ]

    equation = projection.equations[0]
    assert equation.equation_id == "eq_selected"
    assert json.loads(equation.expression)["op"] == "equality"
    assert equation.output_ids == (projection.outputs[0].output_id,)
    substitution = projection.substitutions[0]
    assert substitution.equation_id == equation.equation_id
    assert json.loads(substitution.expression) == {"symbol_id": "x", "value_si": 2.0}
    output = projection.outputs[0]
    assert output.candidate_id == result.selected_candidate_id
    assert output.output_key == "query_x"
    assert output.symbol == "x"
    assert output.numeric == 2.0
    assert output.unit == "m"
    assert output.equation_ids == ("eq_selected",)
    assert output.substitution_ids == tuple(item.substitution_id for item in projection.substitutions)
    assert projection.explanation_evidence is not None
    assert projection.explanation_evidence.equations == projection.equations
    assert projection.explanation_evidence.substitutions == projection.substitutions
    assert projection.explanation_evidence.outputs == projection.outputs
    json.dumps({
        "equation": asdict(equation),
        "substitution": asdict(substitution),
        "output": asdict(output),
        "checks": [item.to_dict() for item in projection.verification_checks],
    }, sort_keys=True)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: replace(item, status=VerificationStatus.FAILED),
        lambda item: replace(item, status=VerificationStatus.INCONCLUSIVE),
        lambda item: replace(item, check_id="forged_check"),
        lambda item: replace(item, source_equation_ids=("outside_graph",)),
        lambda item: replace(
            item,
            metadata={**dict(item.metadata), "candidate_id": "forged_candidate"},
        ),
    ],
    ids=("failed", "status", "id", "outside-graph", "metadata"),
)
def test_legacy_report_rejects_every_noncanonical_public_check(mutate: object) -> None:
    result = _result(_graph(), (2.0, 0, 0))
    adapter = build_evidence_adapter(result)
    canonical = to_legacy_verification_checks(result)
    forged = (mutate(canonical[0]), *canonical[1:])
    with pytest.raises(ValueError, match="exactly match"):
        build_legacy_verification_report(adapter, forged)


def test_legacy_report_omitted_and_explicit_canonical_paths_are_identical() -> None:
    result = _result(_graph(), (2.0, 0, 0))
    adapter = build_evidence_adapter(result)
    canonical = to_legacy_verification_checks(result)
    implicit = build_legacy_verification_report(adapter)
    explicit = build_legacy_verification_report(adapter, canonical)
    assert implicit == explicit
    assert implicit.passed == all(
        item.passed
        for item in canonical
        if item.metadata["selected"] is True
    )


def test_application_only_source_is_preserved_per_equation_and_substitution() -> None:
    base = _graph()
    equation = base.equations[0].model_copy(update={"source_evidence_ids": ()})
    application = base.applications[0].model_copy(update={
        "source_evidence_ids": ("source_application",),
    })
    graph = base.model_copy(update={
        "equations": (equation,),
        "applications": (application,),
    })
    result = _result(graph, (2.0, 0, 0))
    projection = build_legacy_evidence_projection(result)
    assert projection.adapter.source_evidence_ids == ("source_application",)
    assert projection.equations[0].fact_ids == ("source_application",)
    assert {item.fact_ids for item in projection.substitutions} == {
        ("source_application",),
    }


def test_constraint_source_is_bound_only_to_its_connected_equation() -> None:
    base = _graph()
    selected = base.equations[0].model_copy(update={
        "source_evidence_ids": ("source_selected",),
    })
    inequality = EquationNode(
        equation_id="ineq_connected",
        expression=Inequality(
            relation="ge",
            left=SymbolRef(symbol_id="x"),
            right=LiteralNode(value=0.0),
        ),
        expression_fingerprint="c" * 64,
        law_id="domain_law",
        scope=EquationScope(),
        constraint_ids=("constraint_connected",),
        dimension=DimensionVector(),
        complexity_cost=3,
    )
    constraint = ConstraintNode(
        constraint_id="constraint_connected",
        constraint_kind="nonnegative",
        equation_id="ineq_connected",
        scope=EquationScope(),
        source_evidence_ids=("source_constraint",),
    )
    graph = base.model_copy(update={
        "equations": (selected, inequality),
        "constraints": (constraint,),
        "applications": (
            LawApplication(
                application_id="application_selected",
                law_id="generic_law",
                equation_ids=("eq_selected",),
                scope=EquationScope(),
                source_evidence_ids=("source_selected",),
                complexity_cost=4,
            ),
            LawApplication(
                application_id="application_constraint",
                law_id="domain_law",
                equation_ids=("ineq_connected",),
                scope=EquationScope(),
                constraint_ids=("constraint_connected",),
                complexity_cost=3,
            ),
        ),
        "rank": RankAnalysis(
            equality_count=1,
            inequality_count=1,
            unknown_count=1,
            structural_rank=1,
            underdetermined=False,
            overdetermined=False,
            conflicting=False,
        ),
    })
    result = _result(graph, (2.0, 0, 0))
    projection = build_legacy_evidence_projection(result)
    facts_by_equation = {
        item.equation_id: item.fact_ids
        for item in projection.equations
    }
    assert facts_by_equation == {
        "eq_selected": ("source_selected",),
        "ineq_connected": ("source_constraint",),
    }
    for substitution in projection.substitutions:
        assert substitution.fact_ids == facts_by_equation[substitution.equation_id]


def test_legacy_check_metadata_preserves_root_and_selected_rejected_separation() -> None:
    polynomial = Equality(
        left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
        right=LiteralNode(value=4.0),
    )
    result = _result(
        _graph(expression=polynomial, role="length"),
        (-2.0, 0, 0),
        (2.0, 1, 1),
    )
    assert result.terminal.value == "solved"
    projection = build_legacy_evidence_projection(result)
    assert len(projection.rejected_candidates) == 1
    rejected = projection.rejected_candidates[0]
    assert (rejected.generation_index, rejected.root_index, rejected.root_multiplicity) == (0, 0, 1)
    assert {item.reason.value for item in rejected.rejections} == {"positive_parameter_violation"}
    selected_checks = [
        item for item in projection.verification_checks if item.metadata["selected"]
    ]
    rejected_checks = [
        item for item in projection.verification_checks if not item.metadata["selected"]
    ]
    assert selected_checks and rejected_checks
    assert {item.metadata["root_index"] for item in selected_checks} == {1}
    assert {item.metadata["root_index"] for item in rejected_checks} == {0}
    assert any(item.metadata["rejection_reason"] == "positive_parameter_violation" for item in rejected_checks)


def test_vector_v2_evidence_is_valid_but_legacy_scalar_target_closes_atomically() -> None:
    graph = _graph(
        shape="vector",
        vector_length=2,
        known_value=(1.0, 2.0),
    )
    result = _result(graph, ((1.0, 2.0), 0, 0))
    adapter = build_evidence_adapter(result)
    assert adapter.output.value_si == (1.0, 2.0)
    projection = build_legacy_evidence_projection(result)
    assert projection.status is LegacyProjectionStatus.unsupported
    assert projection.limitation is LegacyProjectionLimitation.vector_output_not_representable
    assert not projection.verification_checks
    assert projection.verification_report is None
    assert not projection.equations
    assert not projection.substitutions
    assert not projection.outputs
    assert projection.explanation_evidence is None
    with pytest.raises(ValueError, match="vector_output_not_representable"):
        build_solver_explanation_evidence(adapter)


def test_non_solved_result_cannot_create_selected_answer_evidence() -> None:
    result = _result(_graph(), (2.0, 0, 0), (2.0, 1, 1))
    assert result.terminal.value == "ambiguity"
    with pytest.raises(ValueError, match="solved"):
        build_evidence_adapter(result)
    with pytest.raises(ValueError, match="solved"):
        to_legacy_verification_checks(result)


def test_individual_additive_adapters_match_the_closed_bundle() -> None:
    result = _result(_graph(), (2.0, 0, 0))
    adapter = build_evidence_adapter(result)
    checks = to_legacy_verification_checks(result)
    report = build_legacy_verification_report(adapter, checks)
    explanation = build_solver_explanation_evidence(adapter)
    bundle = build_legacy_evidence_projection(result)
    assert checks == bundle.verification_checks
    assert report.structured_checks == bundle.verification_report.structured_checks
    assert explanation == bundle.explanation_evidence


def test_adapter_source_has_no_expression_execution_or_answer_oracle_path() -> None:
    source = Path(
        inspect.getsourcefile(build_evidence_adapter) or ""
    ).read_text(encoding="utf-8")
    forbidden = (
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"\bcompile\s*\(",
        r"\bsympify\b",
        r"\bparse_expr\b",
        r"\blambdify\b",
        r"raw_text",
        r"expected_answer",
        r"legacy_solver",
    )
    assert not [pattern for pattern in forbidden if re.search(pattern, source, re.IGNORECASE)]
