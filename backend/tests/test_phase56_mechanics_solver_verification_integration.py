from __future__ import annotations

import pytest

from engine.mechanics import (
    LegacyProjectionStatus,
    MechanicsSolveTerminal,
    SolverDiagnosticCode,
    build_evidence_adapter,
    build_legacy_evidence_projection,
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


def _symbol(identifier: str, known: float | None = None) -> SymbolNode:
    quantity_id = f"quantity_{identifier}"
    return SymbolNode(
        symbol=SymbolDefinition(
            symbol_id=identifier,
            quantity_id=quantity_id,
            dimension=DIMENSIONLESS,
        ),
        quantity_id=quantity_id,
        quantity_role="parameter" if known is not None else "position",
        known_si_value=known,
    )


def _graph(*, positive_only: bool = False, event: bool = False) -> EquationGraph:
    scope = (
        EquationScope(event_id="event1", event_ids=("event1",))
        if event
        else EquationScope()
    )
    equality = EquationNode(
        equation_id="eq_selected",
        expression=Equality(
            left=Power(
                base=SymbolRef(symbol_id="x"),
                exponent=LiteralNode(value=2),
            ),
            right=LiteralNode(value=4),
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


def test_pipeline_verifies_all_roots_then_selects_the_unique_physical_root() -> None:
    result = solve_verified_equation_graph(_graph(positive_only=True))

    assert result.terminal is MechanicsSolveTerminal.solved
    assert len(result.candidate_set.candidates) == 2
    assert len(result.verification_outcomes) == 2
    assert [item.query_value_si for item in result.verified_candidates] == [2.0]
    assert result.selected_candidate_id == result.verified_candidates[0].candidate.candidate_id

    adapter = build_evidence_adapter(result)
    assert adapter.candidate_id == result.selected_candidate_id
    assert adapter.output.value_si == pytest.approx(2.0)
    assert adapter.output.si_unit == "1"
    assert adapter.source_evidence_ids == ("source1",)
    legacy = build_legacy_evidence_projection(result)
    assert legacy.status is LegacyProjectionStatus.projected
    assert legacy.adapter == adapter


def test_pipeline_preserves_ambiguity_and_forbids_answer_evidence() -> None:
    result = solve_verified_equation_graph(_graph())

    assert result.terminal is MechanicsSolveTerminal.ambiguity
    assert [item.query_value_si for item in result.verified_candidates] == [-2.0, 2.0]
    assert result.selected_candidate_id is None
    with pytest.raises(ValueError, match="solved"):
        build_evidence_adapter(result)
    with pytest.raises(ValueError, match="solved"):
        build_legacy_evidence_projection(result)


def test_pipeline_maps_unsupported_event_semantics_without_partial_answers() -> None:
    result = solve_verified_equation_graph(_graph(event=True))

    assert result.terminal is MechanicsSolveTerminal.unsupported
    assert result.candidate_set.candidates == ()
    assert result.verification_outcomes == ()
    assert result.verified_candidates == ()
    assert result.selected_candidate_id is None
    assert [item.code for item in result.diagnostics.entries].count(
        SolverDiagnosticCode.backend_unsupported
    ) == 1
