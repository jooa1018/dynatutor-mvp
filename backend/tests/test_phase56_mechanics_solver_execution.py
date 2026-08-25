from __future__ import annotations

import ast
from pathlib import Path

import pytest
import sympy as sp

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
    Add,
    DimensionVector,
    Equality,
    Integral,
    LiteralNode,
    Power,
    Sin,
    Sqrt,
    Subtract,
    SymbolDefinition,
    SymbolRef,
    VectorNode,
)
from engine.mechanics.solver.contracts import (
    CandidateCoverage,
    SolveBackendKind,
    SolvePhase,
    SolverBudget,
    SolverDiagnosticCode,
)
from engine.mechanics.solver._audit import audit_solve_plan
from engine.mechanics.solver.backends import _numeric_expression_value, run_backend
from engine.mechanics.solver.engine import (
    SolverExecutionStatus,
    _validated_payload,
    execute_solve_plan,
)
from engine.mechanics.solver.isolation import (
    MAX_WORKER_RESPONSE_BYTES,
    IsolatedBackendRun,
    IsolationStatus,
    _decode_worker_payload,
    _encode_worker_payload,
    run_isolated_backend,
    run_isolated_completeness_audit,
)
import engine.mechanics.solver.isolation as solver_isolation
from engine.mechanics.solver.planner import plan_equation_graph
from engine.mechanics.solver.translation import (
    TranslationStatus,
    translate_expression,
    translate_solve_plan,
)


DIMENSIONLESS = DimensionVector()
SCOPE = EquationScope()


def _symbol(symbol_id: str, known: float | None = None) -> SymbolNode:
    quantity_id = f"quantity_{symbol_id}"
    return SymbolNode(
        symbol=SymbolDefinition(
            symbol_id=symbol_id,
            quantity_id=quantity_id,
            dimension=DIMENSIONLESS,
        ),
        quantity_id=quantity_id,
        quantity_role="parameter" if known is not None else "position",
        known_si_value=known,
    )


def _graph(
    expressions: tuple[Equality, ...],
    *,
    unknown_ids: tuple[str, ...] = ("x",),
    known: tuple[tuple[str, float], ...] = (),
    scope: EquationScope = SCOPE,
) -> EquationGraph:
    equations = tuple(
        EquationNode(
            equation_id=f"eq{index}",
            expression=expression,
            expression_fingerprint=f"{index + 100:064x}",
            law_id="law1",
            scope=scope,
            dimension=DIMENSIONLESS,
            complexity_cost=5,
        )
        for index, expression in enumerate(expressions, 1)
    )
    symbols = tuple(sorted(
        (*(_symbol(item) for item in unknown_ids), *(_symbol(item, value) for item, value in known)),
        key=lambda item: item.symbol.symbol_id,
    ))
    equation_ids = tuple(item.equation_id for item in equations)
    return EquationGraph(
        query_id="query1",
        query_symbol_id="x",
        symbols=symbols,
        equations=equations,
        constraints=(),
        applications=(LawApplication(
            application_id="application1",
            law_id="law1",
            equation_ids=equation_ids,
            scope=scope,
            complexity_cost=5 * len(equations),
        ),),
        incidence=tuple(
            IncidenceEdge(equation_id=equation_id, symbol_id=symbol_id)
            for equation_id in equation_ids
            for symbol_id in unknown_ids
        ),
        rank=RankAnalysis(
            equality_count=len(equations),
            inequality_count=0,
            unknown_count=len(unknown_ids),
            structural_rank=len(unknown_ids),
            underdetermined=False,
            overdetermined=len(equations) > len(unknown_ids),
            conflicting=False,
        ),
        selected_equation_ids=equation_ids,
        fingerprint="d" * 64,
    )


def _run(graph: EquationGraph, budget: SolverBudget | None = None):
    return execute_solve_plan(plan_equation_graph(graph, budget))


def test_typed_translation_closes_unknown_symbol_and_shape_mismatch() -> None:
    x = SymbolDefinition(symbol_id="x", dimension=DIMENSIONLESS)
    missing = translate_expression(SymbolRef(symbol_id="missing"), {"x": x})
    malformed = translate_expression(
        Add(
            terms=(
                VectorNode(items=(LiteralNode(value=1.0), LiteralNode(value=2.0))),
                LiteralNode(value=1.0),
            )
        ),
        {"x": x},
    )
    assert missing.status is TranslationStatus.unsupported
    assert malformed.status is TranslationStatus.unsupported


def test_translator_builds_selected_system_from_typed_nodes_only() -> None:
    graph = _graph(
        (Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="two")),),
        known=(("two", 2.0),),
    )
    translated = translate_solve_plan(plan_equation_graph(graph))
    assert translated.status is TranslationStatus.success
    assert translated.system is not None
    assert tuple(item.symbol_id for item in translated.system.unknowns) == ("x",)
    assert tuple(item for item, _ in translated.system.equations) == ("eq1",)


def test_linear_unique_solution_and_repeat_semantics_are_deterministic() -> None:
    graph = _graph(
        (Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="two")),),
        known=(("two", 2.0),),
    )
    first = _run(graph)
    repeated = _run(graph)
    assert first.status is SolverExecutionStatus.candidates_ready
    assert first.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert first.candidate_set.auto_selectable
    assert len(first.candidate_set.candidates) == 1
    assert first.candidate_set.candidates[0].query_value_si == pytest.approx(2.0)
    assert first.plan.plan_fingerprint == repeated.plan.plan_fingerprint
    assert first.candidate_set == repeated.candidate_set


def test_polynomial_retains_both_real_roots_in_canonical_order() -> None:
    graph = _graph((Equality(
        left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
        right=LiteralNode(value=4.0),
    ),))
    run = _run(graph)
    assert run.status is SolverExecutionStatus.candidates_ready
    assert [item.query_value_si for item in run.candidate_set.candidates] == [-2.0, 2.0]
    assert [item.generation_index for item in run.candidate_set.candidates] == [0, 1]
    assert [item.root_index for item in run.candidate_set.candidates] == [0, 1]
    assert run.candidate_set.manifest[0].candidate_id == run.candidate_set.candidates[0].candidate_id


def test_polynomial_no_real_root_is_exhaustive_empty() -> None:
    graph = _graph((Equality(
        left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
        right=LiteralNode(value=-1.0),
    ),))
    run = _run(graph)
    assert run.status is SolverExecutionStatus.candidates_ready
    assert run.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert run.candidate_set.generation_complete
    assert run.candidate_set.candidates == ()


def test_univariate_polynomial_certificate_preserves_repeated_root_multiplicity() -> None:
    graph = _graph((Equality(
        left=Power(
            base=Subtract(
                left=SymbolRef(symbol_id="x"),
                right=LiteralNode(value=1.0),
            ),
            exponent=LiteralNode(value=2.0),
        ),
        right=LiteralNode(value=0.0),
    ),))
    run = _run(graph)
    assert run.status is SolverExecutionStatus.candidates_ready
    assert len(run.candidate_set.candidates) == 1
    assert run.candidate_set.candidates[0].query_value_si == 1.0
    assert run.candidate_set.candidates[0].root_multiplicity == 2


def test_multivariable_linear_system_covers_every_unknown() -> None:
    graph = _graph(
        (
            Equality(
                left=Add(terms=(SymbolRef(symbol_id="x"), SymbolRef(symbol_id="y"))),
                right=LiteralNode(value=3.0),
            ),
            Equality(
                left=Subtract(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="y")),
                right=LiteralNode(value=1.0),
            ),
        ),
        unknown_ids=("x", "y"),
    )
    run = _run(graph)
    values = run.candidate_set.candidates[0].values
    assert tuple(item.symbol_id for item in values) == ("x", "y")
    assert tuple(item.value_si for item in values) == pytest.approx((2.0, 1.0))


def test_finite_nonlinear_without_differential_proof_uses_bounded_fallback() -> None:
    graph = _graph((Equality(
        left=Sqrt(operand=SymbolRef(symbol_id="x")),
        right=LiteralNode(value=2.0),
    ),))
    run = _run(graph)
    assert run.plan.primary_backend is SolveBackendKind.nonlinear_symbolic
    assert run.status is SolverExecutionStatus.candidates_ready
    assert run.candidate_set.coverage is CandidateCoverage.bounded_numeric
    assert not run.candidate_set.auto_selectable
    assert [item.query_value_si for item in run.candidate_set.candidates] == pytest.approx([4.0])


def test_numeric_safe_evaluator_is_real_only_at_every_intermediate() -> None:
    x = sp.Symbol("x", real=True)
    square_of_sqrt = sp.Pow(
        sp.Pow(x, sp.Rational(1, 2), evaluate=False),
        sp.Integer(2),
        evaluate=False,
    )
    negative_fractional = sp.Pow(
        x, sp.Rational(1, 3), evaluate=False
    )
    reciprocal = sp.Pow(x, sp.Integer(-1), evaluate=False)

    for expression, bindings in (
        (square_of_sqrt, {x: -1.0}),
        (negative_fractional, {x: -8.0}),
        (reciprocal, {x: 0.0}),
    ):
        assert _numeric_expression_value(
            expression, bindings, max_nodes=32, max_depth=8
        ) is None

    assert _numeric_expression_value(
        square_of_sqrt, {x: 4.0}, max_nodes=32, max_depth=8
    ) == pytest.approx(4.0)
    assert _numeric_expression_value(
        negative_fractional, {x: 8.0}, max_nodes=32, max_depth=8
    ) == pytest.approx(2.0)
    assert _numeric_expression_value(
        reciprocal, {x: 2.0}, max_nodes=32, max_depth=8
    ) == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    (
        (
            Power(
                base=Sqrt(operand=SymbolRef(symbol_id="x")),
                exponent=LiteralNode(value=2.0),
            ),
            LiteralNode(value=-1.0),
            (),
        ),
        (
            Power(
                base=Power(
                    base=SymbolRef(symbol_id="x"),
                    exponent=LiteralNode(value=0.5),
                ),
                exponent=LiteralNode(value=2.0),
            ),
            LiteralNode(value=-1.0),
            (),
        ),
        (
            Power(
                base=Sqrt(operand=SymbolRef(symbol_id="x")),
                exponent=LiteralNode(value=2.0),
            ),
            LiteralNode(value=4.0),
            (4.0,),
        ),
        (
            Power(
                base=Power(
                    base=SymbolRef(symbol_id="x"),
                    exponent=LiteralNode(value=-1.0),
                ),
                exponent=LiteralNode(value=-1.0),
            ),
            LiteralNode(value=1.0),
            (1.0,),
        ),
    ),
)
def test_public_numeric_backend_preserves_real_domains(
    left, right, expected: tuple[float, ...]
) -> None:
    run = _run(_graph((Equality(left=left, right=right),)))
    assert run.status is SolverExecutionStatus.candidates_ready
    assert run.candidate_set.coverage is CandidateCoverage.bounded_numeric
    assert not run.candidate_set.auto_selectable
    assert tuple(
        item.query_value_si for item in run.candidate_set.candidates
    ) == pytest.approx(expected)


def test_public_numeric_backend_never_emits_the_zero_division_point() -> None:
    reciprocal_of_reciprocal = Power(
        base=Power(
            base=SymbolRef(symbol_id="x"),
            exponent=LiteralNode(value=-1.0),
        ),
        exponent=LiteralNode(value=-1.0),
    )
    run = _run(_graph((Equality(
        left=reciprocal_of_reciprocal,
        right=LiteralNode(value=0.0),
    ),)))
    assert run.status is SolverExecutionStatus.candidates_ready
    assert run.candidate_set.coverage is CandidateCoverage.bounded_numeric
    assert not run.candidate_set.auto_selectable
    assert run.candidate_set.candidates
    assert all(
        item.query_value_si != 0.0
        for item in run.candidate_set.candidates
    )


def test_infinite_nonlinear_symbolic_set_uses_bounded_numeric_fallback() -> None:
    graph = _graph((Equality(
        left=Sin(argument=SymbolRef(symbol_id="x")),
        right=LiteralNode(value=0.0),
    ),))
    run = _run(graph, SolverBudget(max_numeric_starts=8, max_numeric_iterations=100))
    assert run.plan.permitted_numeric_fallback is SolveBackendKind.numeric_root
    assert run.status is SolverExecutionStatus.candidates_ready
    assert run.candidate_set.coverage is CandidateCoverage.bounded_numeric
    assert not run.candidate_set.auto_selectable
    assert all(item.backend is SolveBackendKind.numeric_root for item in run.candidate_set.candidates)
    assert any(
        item.code is SolverDiagnosticCode.numeric_fallback_used
        for item in run.diagnostics.entries
    )


def test_candidate_limit_retains_exact_prefix_and_closes_incomplete() -> None:
    graph = _graph((Equality(
        left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
        right=LiteralNode(value=1.0),
    ),))
    run = _run(graph, SolverBudget(max_candidates=1))
    assert run.status is SolverExecutionStatus.resource_limit
    assert run.candidate_set.coverage is CandidateCoverage.incomplete
    assert len(run.candidate_set.candidates) == 1
    assert any(
        item.code is SolverDiagnosticCode.candidate_limit_reached
        for item in run.diagnostics.entries
    )


def test_advanced_integral_fails_closed_after_authorized_fallback() -> None:
    graph = _graph((Equality(
        left=Integral(expression=SymbolRef(symbol_id="x"), wrt_symbol_id="x"),
        right=LiteralNode(value=1.0),
    ),))
    run = _run(graph)
    assert run.status is SolverExecutionStatus.unsupported
    assert run.candidate_set.coverage is CandidateCoverage.incomplete
    assert run.candidate_set.candidates == ()
    codes = {item.code for item in run.diagnostics.entries}
    assert SolverDiagnosticCode.numeric_fallback_used in codes
    assert SolverDiagnosticCode.backend_unsupported in codes
    assert SolverDiagnosticCode.generation_incomplete in codes


def test_event_scoped_graph_is_not_claimed_exhaustive() -> None:
    event_scope = EquationScope(event_id="event1", event_ids=("event1",))
    graph = _graph(
        (Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="two")),),
        known=(("two", 2.0),),
        scope=event_scope,
    )
    run = _run(graph)
    assert run.plan.event_ids == ("event1",)
    assert run.status is SolverExecutionStatus.unsupported
    assert run.candidate_set.coverage is CandidateCoverage.incomplete
    assert run.candidate_set.candidates == ()


def test_simple_multivariate_polynomial_requires_two_agreeing_paths() -> None:
    graph = _graph(
        (
            Equality(
                left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
                right=LiteralNode(value=1.0),
            ),
            Equality(
                left=SymbolRef(symbol_id="y"),
                right=SymbolRef(symbol_id="x"),
            ),
        ),
        unknown_ids=("x", "y"),
    )
    run = _run(graph)
    assert run.status is SolverExecutionStatus.candidates_ready
    assert run.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert [item.query_value_si for item in run.candidate_set.candidates] == [-1.0, 1.0]
    assert all(item.root_multiplicity == 1 for item in run.candidate_set.candidates)


def test_singular_multivariate_polynomial_never_invents_simple_multiplicity() -> None:
    graph = _graph(
        (
            Equality(
                left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
                right=LiteralNode(value=0.0),
            ),
            Equality(left=SymbolRef(symbol_id="y"), right=LiteralNode(value=0.0)),
        ),
        unknown_ids=("x", "y"),
    )
    run = _run(graph)
    assert run.status is SolverExecutionStatus.unsupported
    assert run.candidate_set.coverage is CandidateCoverage.incomplete
    assert run.candidate_set.candidates == ()


def _isolated_payload(plan, payload: dict[str, object]) -> IsolatedBackendRun:
    return IsolatedBackendRun(
        status=IsolationStatus.completed,
        payload=payload,
        elapsed_s=0.1,
        phase="symbolic",
        backend=plan.primary_backend,
        process_reaped=True,
    )


def _isolated_audit(
    plan,
    payload: dict[str, object] | None = None,
) -> IsolatedBackendRun:
    return IsolatedBackendRun(
        status=IsolationStatus.completed,
        payload=(
            audit_solve_plan(plan, plan.primary_backend)
            if payload is None
            else payload
        ),
        elapsed_s=0.1,
        phase=SolvePhase.verification,
        backend=plan.primary_backend,
        process_reaped=True,
    )


def test_parent_requires_independent_authority_and_exact_certificate() -> None:
    graph = _graph((Equality(
        left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
        right=LiteralNode(value=4.0),
    ),))
    plan = plan_equation_graph(graph)
    exact = run_backend(plan, plan.primary_backend)
    audit = _isolated_audit(plan)
    assert _validated_payload(_isolated_payload(plan, exact), plan).status.value == "backend_failure"
    assert _validated_payload(_isolated_payload(plan, exact), plan, audit).complete

    missing = {**exact, "certificate": None}
    assert _validated_payload(
        _isolated_payload(plan, missing), plan, audit
    ).status.value == "backend_failure"

    mismatched = {
        **exact,
        "certificate": {**exact["certificate"], "graph_fingerprint": "f" * 64},
    }
    assert _validated_payload(
        _isolated_payload(plan, mismatched), plan, audit
    ).status.value == "backend_failure"

    assert audit.payload is not None
    tampered_audit = {
        **audit.payload,
        "graph_fingerprint": "f" * 64,
    }
    assert _validated_payload(
        _isolated_payload(plan, exact),
        plan,
        _isolated_audit(plan, tampered_audit),
    ).status.value == "backend_failure"


def test_parent_detects_x_squared_root_omission_and_multiplicity_mismatch() -> None:
    graph = _graph((Equality(
        left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
        right=LiteralNode(value=4.0),
    ),))
    plan = plan_equation_graph(graph)
    exact = run_backend(plan, plan.primary_backend)
    audit = _isolated_audit(plan)
    assert len(exact["roots"]) == 2

    omitted_certificate = {
        **exact["certificate"],
        "solution_count": 1,
        "total_multiplicity": 1,
        "independent_solution_count": 1,
        "independent_total_multiplicity": 1,
    }
    omitted = {
        **exact,
        "roots": exact["roots"][:1],
        "certificate": omitted_certificate,
    }
    closed = _validated_payload(_isolated_payload(plan, omitted), plan, audit)
    assert closed.status.value == "backend_failure" and closed.roots == ()

    assert _validated_payload(
        _isolated_payload(plan, exact), plan, audit
    ).complete

    changed_root = {
        **exact["roots"][0],
        "root_multiplicity": exact["roots"][0]["root_multiplicity"] + 1,
    }
    mismatched = {**exact, "roots": [changed_root, *exact["roots"][1:]]}
    closed = _validated_payload(_isolated_payload(plan, mismatched), plan, audit)
    assert closed.status.value == "backend_failure" and closed.roots == ()


def test_failure_payload_cannot_smuggle_retained_candidates() -> None:
    graph = _graph((Equality(
        left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
        right=LiteralNode(value=4.0),
    ),))
    plan = plan_equation_graph(graph)
    exact = run_backend(plan, plan.primary_backend)
    forged = {
        "status": "unsupported",
        "complete": False,
        "approximate": False,
        "roots": exact["roots"][:1],
        "overflow": False,
        "certificate": None,
    }
    closed = _validated_payload(_isolated_payload(plan, forged), plan)
    assert closed.status.value == "backend_failure"
    assert closed.roots == ()


def test_bytes_ipc_decoder_closes_malformed_non_dict_and_oversized_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for encoded in (
        b"{",
        b"[]",
        b"\xff",
        b'{"status":NaN}',
        b'{"status":"success","status":"backend_failure"}',
    ):
        assert _decode_worker_payload(encoded)["status"] == "backend_failure"
    original_cap = solver_isolation.MAX_WORKER_RESPONSE_BYTES
    monkeypatch.setattr(solver_isolation, "MAX_WORKER_RESPONSE_BYTES", 8)
    assert _decode_worker_payload(b"x" * 9)["status"] == "backend_failure"
    monkeypatch.setattr(
        solver_isolation, "MAX_WORKER_RESPONSE_BYTES", original_cap
    )
    encoded = _encode_worker_payload({
        "status": "backend_failure",
        "complete": False,
        "approximate": False,
        "roots": [],
        "overflow": False,
        "certificate": None,
    })
    assert isinstance(encoded, bytes)
    assert _decode_worker_payload(encoded)["status"] == "backend_failure"

    graph = _graph(
        (Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="two")),),
        known=(("two", 2.0),),
    )
    plan = plan_equation_graph(graph)
    schema_closed = _validated_payload(
        _isolated_payload(plan, _decode_worker_payload(b"{}")), plan
    )
    assert schema_closed.status.value == "backend_failure"


def test_encoder_stops_streaming_before_materializing_an_over_cap_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    continued_after_oversize = False

    class _ObservedEncoder:
        def iterencode(self, _: object):
            nonlocal continued_after_oversize
            yield '{"status":'
            yield '"' + "x" * 64 + '"'
            continued_after_oversize = True
            yield "}"

    monkeypatch.setattr(
        solver_isolation.json,
        "JSONEncoder",
        lambda **_: _ObservedEncoder(),
    )
    monkeypatch.setattr(solver_isolation, "MAX_WORKER_RESPONSE_BYTES", 16)
    encoded = _encode_worker_payload({"status": "x"})
    assert encoded == solver_isolation._CLOSED_FAILURE_BYTES
    assert not continued_after_oversize


def test_encoder_rejects_cycles_before_json_and_allows_shared_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle: list[object] = []
    cycle.extend([cycle] * 1024)

    def fail_encoder(**_: object) -> object:
        raise AssertionError("cyclic payload must close before JSON encoding")

    monkeypatch.setattr(solver_isolation.json, "JSONEncoder", fail_encoder)
    assert _encode_worker_payload({"roots": cycle}) == solver_isolation._CLOSED_FAILURE_BYTES

    monkeypatch.undo()
    shared = [0.0] * 16
    encoded = _encode_worker_payload({"left": shared, "right": shared})
    assert _decode_worker_payload(encoded) == {"left": shared, "right": shared}


def test_response_cap_proves_the_closed_contract_maximum_shape() -> None:
    maximum_value = {
        "symbol_id": "x" * 64,
        "value_si": [-1.0e300] * 16,
    }
    encoded_value = solver_isolation.json.dumps(
        maximum_value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    maximum_root = {
        "values": [maximum_value] * 256,
        "root_multiplicity": 1024,
    }
    encoded_root = solver_isolation.json.dumps(
        maximum_root,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    assert len(encoded_value) <= solver_isolation._MAX_VALUE_JSON_BYTES
    assert len(encoded_root) <= solver_isolation._MAX_ROOT_JSON_BYTES
    assert (
        solver_isolation._MAX_SCHEMA_RESPONSE_BYTES
        <= MAX_WORKER_RESPONSE_BYTES
    )


def test_large_candidate_and_value_shape_fits_bounded_bytes_ipc() -> None:
    # Shared Python containers keep construction bounded; JSON still emits and
    # decodes the complete 1024 x 256 schema shape exactly once.
    maximum_identifier = "x" * 64
    scalar_value = {"symbol_id": maximum_identifier, "value_si": 0.0}
    vector_value = {
        "symbol_id": maximum_identifier,
        "value_si": [0.0] * 16,
    }
    values = [scalar_value] * 255 + [vector_value]
    root = {"values": values, "root_multiplicity": 1024}
    payload = {
        "status": "resource_limit",
        "complete": False,
        "approximate": False,
        "roots": [root] * 1024,
        "overflow": True,
        "certificate": None,
    }
    encoded = _encode_worker_payload(payload)
    assert 8 * 1024 * 1024 < len(encoded) <= MAX_WORKER_RESPONSE_BYTES
    decoded = _decode_worker_payload(encoded)
    assert decoded["status"] == "resource_limit"
    assert len(decoded["roots"]) == 1024
    assert len(decoded["roots"][-1]["values"]) == 256
    assert len(decoded["roots"][-1]["values"][-1]["value_si"]) == 16


def test_tiny_symbolic_budget_hard_times_out_and_reaps_worker() -> None:
    graph = _graph(
        (Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="two")),),
        known=(("two", 2.0),),
    )
    budget = SolverBudget(
        symbolic_time_limit_s=1.0e-6,
        timeout_termination_grace_s=0.25,
    )
    plan = plan_equation_graph(graph, budget)
    isolated = run_isolated_backend(plan, plan.primary_backend)
    assert isolated.status is IsolationStatus.timeout
    assert isolated.process_reaped
    run = _run(graph, budget)
    assert run.status is SolverExecutionStatus.timeout
    assert run.diagnostics.timeout is not None
    assert run.diagnostics.timeout.limit_s == budget.symbolic_time_limit_s
    assert run.diagnostics.attempts[-1].completed is False
    assert run.diagnostics.attempts[-1].elapsed_s == run.diagnostics.timeout.elapsed_s
    assert run.candidate_set.coverage is CandidateCoverage.incomplete


def test_tiny_independent_completeness_budget_reaps_and_closes_public_run() -> None:
    graph = _graph(
        (Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="two")),),
        known=(("two", 2.0),),
    )
    budget = SolverBudget(
        symbolic_time_limit_s=5.0,
        verification_time_limit_s=1.0e-6,
        timeout_termination_grace_s=0.25,
    )
    plan = plan_equation_graph(graph, budget)
    isolated = run_isolated_completeness_audit(plan, plan.primary_backend)
    assert isolated.status is IsolationStatus.timeout
    assert isolated.process_reaped

    run = execute_solve_plan(plan)
    assert run.status is SolverExecutionStatus.timeout
    assert run.candidate_set.coverage is CandidateCoverage.incomplete
    assert run.candidate_set.candidates == ()
    assert len(run.diagnostics.attempts) == 2
    assert run.diagnostics.attempts[0].completed
    assert run.diagnostics.attempts[1].phase is SolvePhase.verification
    assert not run.diagnostics.attempts[1].completed
    assert run.diagnostics.timeout is not None
    assert run.diagnostics.timeout.phase is SolvePhase.verification
    assert run.diagnostics.timeout.limit_s == budget.verification_time_limit_s


def test_solver_sources_have_no_dynamic_language_or_string_math_calls() -> None:
    solver_dir = Path(__file__).parents[1] / "engine" / "mechanics" / "solver"
    files = tuple(
        solver_dir / name
        for name in (
            "planner.py",
            "translation.py",
            "backends.py",
            "_audit.py",
            "isolation.py",
            "engine.py",
        )
    )
    forbidden_calls = {"eval", "exec", "compile", "sympify", "parse_expr"}
    forbidden_attributes = {"sympify", "parse_expr", "lambdify", "send", "recv"}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls, (path.name, node.func.id)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_attributes, (path.name, node.func.attr)
