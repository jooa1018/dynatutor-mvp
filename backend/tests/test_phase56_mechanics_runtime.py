from __future__ import annotations

from dataclasses import replace

import pytest

import engine.mechanics.runtime.orchestrator as runtime_module
from engine.mechanics.compiler import authorize_validated_mechanics_ir
from engine.mechanics.compiler.contracts import (
    CompilerResult,
    CompilerStatus,
    EquationGraph,
    EquationNode,
    EquationScope,
    IncidenceEdge,
    LawApplication,
    RankAnalysis,
    SymbolNode,
)
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
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
from engine.mechanics.modeler import MechanicsModeler, ModelerTerminal
from engine.mechanics.modeler_client import StructuredModelerResponse
from engine.mechanics.modeler_config import MechanicsIRMode, MechanicsModelerConfig
from engine.mechanics.modeler_telemetry import ModelerUsage
from engine.mechanics.normalization import NormalizationResult
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.runtime import (
    MechanicsRuntimeOrchestrator,
    RuntimeDelivery,
    RuntimeFailure,
    RuntimeTerminal,
)
from engine.mechanics.validation import DraftValidationResult, ValidationTerminal
from engine.mechanics.verification.contracts import MechanicsSolveTerminal


PROBLEM = "Find the position."
DIMENSIONLESS = DimensionVector()


def _dimension(*, length: int = 0, time: int = 0) -> dict[str, int]:
    return {
        "mass": 0,
        "length": length,
        "time": time,
        "current": 0,
        "temperature": 0,
        "amount": 0,
        "luminous_intensity": 0,
    }


def _draft(*, velocity: bool = False) -> MechanicsProblemDraftV1:
    role = "velocity" if velocity else "position"
    unit = "m/s" if velocity else "m"
    dimension = _dimension(length=1, time=-1 if velocity else 0)
    return MechanicsProblemDraftV1.model_validate(
        {
            "schema": DRAFT_SCHEMA_NAME,
            "version": DRAFT_SCHEMA_VERSION,
            "metadata": {
                "language": "en",
                "correction_revision": 0,
                "system_type": "diagnostic_only",
                "subtype": None,
                "model_id": None,
                "model_hash": None,
                "prompt_hash": None,
                "source_text_sha256": None,
                "model_confidence": 0.5,
            },
            "source_assets": [],
            "source_evidence": [],
            "entities": [
                {
                    "entity_id": "body1",
                    "primitive": "particle",
                    "label": "body",
                    "aliases": [],
                    "component_of_entity_id": None,
                    "evidence_refs": [],
                    "model_confidence": 0.8,
                }
            ],
            "points": [],
            "reference_frames": [],
            "motion_intervals": [],
            "events": [],
            "symbols": [],
            "quantities": [],
            "geometry": [],
            "interactions": [],
            "constraints": [],
            "state_conditions": [],
            "queries": [
                {
                    "query_id": "query1",
                    "target": {
                        "role": role,
                        "subject_id": "body1",
                        "point_id": None,
                        "frame_id": None,
                        "interval_id": None,
                        "event_id": None,
                        "component": "unspecified",
                        "direction": None,
                        "target_quantity_id": None,
                    },
                    "output_unit": unit,
                    "output_dimension": dimension,
                    "shape": "scalar",
                    "evidence_refs": [],
                }
            ],
            "principle_hints": [],
            "assumptions": [],
            "ambiguities": [],
            "figure_dependency": {
                "level": "none",
                "missing_information": [],
                "evidence_refs": [],
            },
            "unsupported_features": [],
        }
    )


class _Client:
    def __init__(self, draft: MechanicsProblemDraftV1) -> None:
        self.draft = draft
        self.calls: list[str] = []

    def model(self, problem_text: str, **_: object) -> StructuredModelerResponse:
        self.calls.append(problem_text)
        return StructuredModelerResponse(
            draft=self.draft,
            usage=ModelerUsage(
                input_tokens=1,
                output_tokens=1,
                measured_cost_usd=0.0,
                cost_known=True,
            ),
            usage_available=True,
        )


def _config(mode: MechanicsIRMode, *, enabled: bool = True) -> MechanicsModelerConfig:
    return MechanicsModelerConfig(
        enabled=enabled,
        mode=mode,
        max_retries=0,
        cache_enabled=False,
    )


def _accepted_outcome(*, velocity: bool = False):
    client = _Client(_draft(velocity=velocity))
    outcome = MechanicsModeler(
        _config(MechanicsIRMode.auto),
        client=client,
    ).model(PROBLEM)
    assert outcome.terminal is ModelerTerminal.accepted
    return outcome


def _nonaccepted_outcome(terminal: ModelerTerminal):
    outcome = _accepted_outcome()
    validation_terminal = {
        ModelerTerminal.needs_figure: ValidationTerminal.needs_figure,
        ModelerTerminal.needs_confirmation: ValidationTerminal.needs_confirmation,
        ModelerTerminal.insufficient_information: ValidationTerminal.insufficient_information,
        ModelerTerminal.unsupported: ValidationTerminal.unsupported,
        ModelerTerminal.invalid: ValidationTerminal.invalid,
    }.get(terminal)
    normalization = (
        NormalizationResult(
            terminal=validation_terminal,
            validation=DraftValidationResult(validation_terminal, ()),
            ir=None,
            calculation_fingerprint=None,
            correction_revision=0,
        )
        if validation_terminal is not None
        else None
    )
    return replace(
        outcome,
        terminal=terminal,
        normalization=normalization,
        ir=None,
        calculation_fingerprint=None,
        telemetry=replace(outcome.telemetry, terminal_status=terminal.value),
        failure_code="safe_failure" if validation_terminal is None else None,
    )


class _ModelerSpy:
    def __init__(self, outcome=None, error: Exception | None = None) -> None:
        self.outcome = outcome
        self.error = error
        self.calls: list[object] = []

    def model(self, problem_text: object):
        self.calls.append(problem_text)
        if self.error is not None:
            raise self.error
        return self.outcome


def _symbol(identifier: str) -> SymbolNode:
    quantity_id = f"quantity_{identifier}"
    return SymbolNode(
        symbol=SymbolDefinition(
            symbol_id=identifier,
            quantity_id=quantity_id,
            dimension=DIMENSIONLESS,
        ),
        quantity_id=quantity_id,
        quantity_role="position",
    )


def _graph(*, positive_only: bool, event: bool = False) -> EquationGraph:
    scope = (
        EquationScope(event_id="event1", event_ids=("event1",))
        if event
        else EquationScope()
    )
    equality = EquationNode(
        equation_id="eq_selected",
        expression=Equality(
            left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2)),
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
        applications=(
            LawApplication(
                application_id="application_main",
                law_id="generic_law",
                equation_ids=equation_ids,
                scope=scope,
                source_evidence_ids=("source1",),
                complexity_cost=sum(item.complexity_cost for item in equations),
            ),
        ),
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


def _install_success_path(
    monkeypatch,
    outcome,
    *,
    compiler_result=None,
    solve_result=None,
):
    if compiler_result is None:
        graph = _graph(positive_only=True)
        compiler_result = CompilerResult(status=CompilerStatus.ready, graph=graph)
    exact_graph = compiler_result.graph
    assert exact_graph is not None
    result = solve_result or solve_verified_equation_graph(exact_graph)
    seal_holder: dict[str, object] = {}
    calls: list[tuple[str, object]] = []

    def authorize(ir):
        calls.append(("authorize", ir))
        seal = authorize_validated_mechanics_ir(ir)
        seal_holder["seal"] = seal
        return seal

    class CompilerSpy:
        def __init__(self) -> None:
            calls.append(("compiler_construct", self))

        def compile(self, ir, *, validated_ir_authorization):
            calls.append(("compile_ir", ir))
            calls.append(("compile_seal", validated_ir_authorization))
            return compiler_result

    def solve(graph_arg):
        calls.append(("solve", graph_arg))
        return result

    monkeypatch.setattr(runtime_module, "authorize_validated_mechanics_ir", authorize)
    monkeypatch.setattr(runtime_module, "MechanicsCompiler", CompilerSpy)
    monkeypatch.setattr(runtime_module, "solve_verified_equation_graph", solve)
    return calls, seal_holder, compiler_result, result


def test_off_never_constructs_or_calls_a_modeler_and_ignores_confirmation(monkeypatch) -> None:
    class ForbiddenModeler:
        def __init__(self, *_: object, **__: object) -> None:
            raise AssertionError("off constructed a modeler")

    monkeypatch.setattr(runtime_module, "MechanicsModeler", ForbiddenModeler)
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.off)
    ).evaluate(PROBLEM, confirmation_fingerprint=object())
    assert execution.terminal is RuntimeTerminal.off
    assert execution.delivery is RuntimeDelivery.legacy


@pytest.mark.parametrize("mode", tuple(MechanicsIRMode))
def test_disabled_mode_matrix_never_calls_modeler(mode: MechanicsIRMode) -> None:
    spy = _ModelerSpy(error=AssertionError("disabled model call"))
    execution = MechanicsRuntimeOrchestrator(
        _config(mode, enabled=False), modeler=spy
    ).evaluate(PROBLEM)
    assert spy.calls == []
    if mode is MechanicsIRMode.off:
        assert (execution.terminal, execution.delivery) == (
            RuntimeTerminal.off,
            RuntimeDelivery.legacy,
        )
    else:
        assert execution.terminal is RuntimeTerminal.disabled
        assert execution.delivery is (
            RuntimeDelivery.legacy
            if mode is MechanicsIRMode.shadow
            else RuntimeDelivery.none
        )


@pytest.mark.parametrize(
    "fingerprint",
    ("a" * 63, "a" * 65, "A" * 64, " " + "a" * 64, 7, b"a" * 64),
)
def test_confirm_malformed_fingerprint_stops_before_modeling(fingerprint) -> None:
    spy = _ModelerSpy(_accepted_outcome())
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.confirm), modeler=spy
    ).evaluate(PROBLEM, confirmation_fingerprint=fingerprint)
    assert execution.terminal is RuntimeTerminal.confirmation_invalid
    assert execution.delivery is RuntimeDelivery.none
    assert spy.calls == []


@pytest.mark.parametrize("supplied", (None, "0" * 64))
def test_confirm_missing_or_stale_models_once_then_stops_before_authority(
    monkeypatch, supplied
) -> None:
    outcome = _accepted_outcome()
    spy = _ModelerSpy(outcome)
    calls: list[object] = []

    def forbidden_authorize(ir):
        calls.append(ir)
        raise AssertionError("confirmation gate called authorization")

    monkeypatch.setattr(runtime_module, "authorize_validated_mechanics_ir", forbidden_authorize)
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.confirm), modeler=spy
    ).evaluate(PROBLEM, confirmation_fingerprint=supplied)
    assert execution.terminal is RuntimeTerminal.confirmation_needed
    assert execution.current_calculation_fingerprint == outcome.calculation_fingerprint
    assert execution.summary.current_calculation_fingerprint == outcome.calculation_fingerprint
    assert spy.calls == [PROBLEM]
    assert calls == []


def test_confirm_binds_to_the_current_outcome_not_a_previous_fingerprint() -> None:
    previous = _accepted_outcome(velocity=False)
    current = _accepted_outcome(velocity=True)
    assert previous.calculation_fingerprint != current.calculation_fingerprint
    spy = _ModelerSpy(current)
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.confirm), modeler=spy
    ).evaluate(PROBLEM, confirmation_fingerprint=previous.calculation_fingerprint)
    assert execution.terminal is RuntimeTerminal.confirmation_needed
    assert execution.current_calculation_fingerprint == current.calculation_fingerprint
    assert spy.calls == [PROBLEM]


def test_confirm_missing_models_once_with_cache_disabled() -> None:
    config = _config(MechanicsIRMode.confirm)
    client = _Client(_draft())
    modeler = MechanicsModeler(config, client=client)
    execution = MechanicsRuntimeOrchestrator(config, modeler=modeler).evaluate(PROBLEM)
    assert config.cache_enabled is False
    assert client.calls == [PROBLEM]
    assert execution.terminal is RuntimeTerminal.confirmation_needed


@pytest.mark.parametrize(
    "mode,expected_delivery",
    (
        (MechanicsIRMode.shadow, RuntimeDelivery.legacy),
        (MechanicsIRMode.auto, RuntimeDelivery.generic),
        (MechanicsIRMode.required, RuntimeDelivery.generic),
    ),
)
def test_exact_success_uses_one_call_each_in_identity_order_and_projects_without_calls(
    monkeypatch,
    mode: MechanicsIRMode,
    expected_delivery: RuntimeDelivery,
) -> None:
    outcome = _accepted_outcome()
    modeler = _ModelerSpy(outcome)
    calls, seals, compiler_result, solve_result = _install_success_path(
        monkeypatch, outcome
    )
    execution = MechanicsRuntimeOrchestrator(
        _config(mode), modeler=modeler
    ).evaluate(PROBLEM, confirmation_fingerprint=object())

    assert modeler.calls == [PROBLEM]
    assert [name for name, _ in calls] == [
        "authorize",
        "compiler_construct",
        "compile_ir",
        "compile_seal",
        "solve",
    ]
    assert calls[0][1] is outcome.ir
    assert calls[2][1] is outcome.ir
    assert calls[3][1] is seals["seal"]
    assert calls[4][1] is compiler_result.graph
    assert execution.solve_result is solve_result
    assert execution.terminal is RuntimeTerminal.solved
    assert execution.delivery is expected_delivery
    assert execution.generic_result is (
        solve_result if expected_delivery is RuntimeDelivery.generic else None
    )

    counts = (len(modeler.calls), len(calls))
    assert execution.summary == execution.summary == execution.to_summary()
    assert (len(modeler.calls), len(calls)) == counts


def test_confirm_exact_fingerprint_continues_without_legacy_delivery(monkeypatch) -> None:
    outcome = _accepted_outcome()
    modeler = _ModelerSpy(outcome)
    _install_success_path(monkeypatch, outcome)
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.confirm), modeler=modeler
    ).evaluate(PROBLEM, confirmation_fingerprint=outcome.calculation_fingerprint)
    assert execution.terminal is RuntimeTerminal.solved
    assert execution.delivery is RuntimeDelivery.generic
    assert execution.summary.current_calculation_fingerprint is None


@pytest.mark.parametrize(
    "terminal",
    tuple(item for item in ModelerTerminal if item is not ModelerTerminal.accepted),
)
@pytest.mark.parametrize(
    "mode,delivery",
    (
        (MechanicsIRMode.shadow, RuntimeDelivery.legacy),
        (MechanicsIRMode.confirm, RuntimeDelivery.none),
        (MechanicsIRMode.auto, RuntimeDelivery.none),
        (MechanicsIRMode.required, RuntimeDelivery.none),
    ),
)
def test_every_nonaccepted_modeler_terminal_obeys_mode_delivery(
    terminal: ModelerTerminal,
    mode: MechanicsIRMode,
    delivery: RuntimeDelivery,
) -> None:
    spy = _ModelerSpy(_nonaccepted_outcome(terminal))
    execution = MechanicsRuntimeOrchestrator(
        _config(mode), modeler=spy
    ).evaluate(PROBLEM)
    assert execution.terminal is RuntimeTerminal.modeler_rejected
    assert execution.delivery is delivery
    assert execution.modeler_outcome.terminal is terminal
    assert spy.calls == [PROBLEM]


@pytest.mark.parametrize(
    "status",
    (
        CompilerStatus.blocked,
        CompilerStatus.invalid,
        CompilerStatus.unsupported,
        CompilerStatus.underdetermined,
        CompilerStatus.conflicting,
        CompilerStatus.resource_limit,
    ),
)
def test_every_noncompilable_compiler_status_stops_before_solve(monkeypatch, status) -> None:
    outcome = _accepted_outcome()
    result = CompilerResult(status=status)
    solve_calls: list[object] = []

    class CompilerSpy:
        def compile(self, ir, *, validated_ir_authorization):
            return result

    monkeypatch.setattr(runtime_module, "MechanicsCompiler", CompilerSpy)
    monkeypatch.setattr(
        runtime_module,
        "solve_verified_equation_graph",
        lambda graph: solve_calls.append(graph),
    )
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.required), modeler=_ModelerSpy(outcome)
    ).evaluate(PROBLEM)
    assert execution.terminal is RuntimeTerminal.compiler_rejected
    assert execution.compiler_result is result
    assert solve_calls == []


@pytest.mark.parametrize(
    "mode,delivery",
    (
        (MechanicsIRMode.shadow, RuntimeDelivery.legacy),
        (MechanicsIRMode.confirm, RuntimeDelivery.none),
        (MechanicsIRMode.auto, RuntimeDelivery.none),
        (MechanicsIRMode.required, RuntimeDelivery.none),
    ),
)
def test_nonsolved_result_is_retained_but_never_delivered(monkeypatch, mode, delivery) -> None:
    outcome = _accepted_outcome()
    graph = _graph(positive_only=False)
    compiler_result = CompilerResult(status=CompilerStatus.ready, graph=graph)
    assert compiler_result.graph is not None
    result = solve_verified_equation_graph(compiler_result.graph)
    assert result.terminal is MechanicsSolveTerminal.ambiguity
    _install_success_path(
        monkeypatch,
        outcome,
        compiler_result=compiler_result,
        solve_result=result,
    )
    execution = MechanicsRuntimeOrchestrator(
        _config(mode), modeler=_ModelerSpy(outcome)
    ).evaluate(
        PROBLEM,
        confirmation_fingerprint=(
            outcome.calculation_fingerprint
            if mode is MechanicsIRMode.confirm
            else None
        ),
    )
    assert execution.terminal is RuntimeTerminal.solve_rejected
    assert execution.delivery is delivery
    assert execution.generic_result is None
    assert execution.solve_result.terminal is MechanicsSolveTerminal.ambiguity


@pytest.mark.parametrize(
    "mode,delivery",
    (
        (MechanicsIRMode.shadow, RuntimeDelivery.legacy),
        (MechanicsIRMode.confirm, RuntimeDelivery.none),
        (MechanicsIRMode.auto, RuntimeDelivery.none),
        (MechanicsIRMode.required, RuntimeDelivery.none),
    ),
)
def test_unexpected_model_exception_is_sanitized_and_mode_closed(mode, delivery) -> None:
    sentinel = "SECRET_PROVIDER_EXCEPTION"
    execution = MechanicsRuntimeOrchestrator(
        _config(mode), modeler=_ModelerSpy(error=RuntimeError(sentinel))
    ).evaluate(
        PROBLEM,
        confirmation_fingerprint="a" * 64 if mode is MechanicsIRMode.confirm else None,
    )
    assert execution.terminal is RuntimeTerminal.failed
    assert execution.failure is RuntimeFailure.modeler_execution
    assert execution.delivery is delivery
    assert sentinel not in repr(execution)
    assert sentinel not in execution.summary.model_dump_json()


@pytest.mark.parametrize(
    "stage,expected_failure",
    (
        ("modeler_construction", RuntimeFailure.modeler_construction),
        ("modeler_execution", RuntimeFailure.modeler_execution),
        ("modeler_contract", RuntimeFailure.modeler_contract),
        ("authorization", RuntimeFailure.authorization),
        ("compiler_construction", RuntimeFailure.compiler_construction),
        ("compiler_execution", RuntimeFailure.compiler_execution),
        ("compiler_contract", RuntimeFailure.compiler_contract),
        ("solver_execution", RuntimeFailure.solver_execution),
        ("solver_contract", RuntimeFailure.solver_contract),
    ),
)
@pytest.mark.parametrize(
    "mode,delivery",
    (
        (MechanicsIRMode.shadow, RuntimeDelivery.legacy),
        (MechanicsIRMode.required, RuntimeDelivery.none),
    ),
)
def test_every_unexpected_or_invalid_stage_is_sanitized_with_mode_delivery(
    monkeypatch,
    stage: str,
    expected_failure: RuntimeFailure,
    mode: MechanicsIRMode,
    delivery: RuntimeDelivery,
) -> None:
    sentinel = f"SECRET_{stage}"
    outcome = _accepted_outcome()
    modeler = _ModelerSpy(outcome)
    compiler_result = CompilerResult(
        status=CompilerStatus.ready,
        graph=_graph(positive_only=True),
    )

    if stage == "modeler_construction":
        modeler = None

        class ConstructionFailure:
            def __init__(self, *_: object, **__: object) -> None:
                raise RuntimeError(sentinel)

        monkeypatch.setattr(runtime_module, "MechanicsModeler", ConstructionFailure)
    elif stage == "modeler_execution":
        modeler = _ModelerSpy(error=RuntimeError(sentinel))
    elif stage == "modeler_contract":
        modeler = _ModelerSpy(object())
    elif stage == "authorization":
        monkeypatch.setattr(
            runtime_module,
            "authorize_validated_mechanics_ir",
            lambda ir: (_ for _ in ()).throw(RuntimeError(sentinel)),
        )
    elif stage == "compiler_construction":
        class CompilerConstructionFailure:
            def __init__(self) -> None:
                raise RuntimeError(sentinel)

        monkeypatch.setattr(
            runtime_module,
            "MechanicsCompiler",
            CompilerConstructionFailure,
        )
    elif stage in {"compiler_execution", "compiler_contract"}:
        class CompilerStage:
            def compile(self, ir, *, validated_ir_authorization):
                if stage == "compiler_execution":
                    raise RuntimeError(sentinel)
                return object()

        monkeypatch.setattr(runtime_module, "MechanicsCompiler", CompilerStage)
    elif stage in {"solver_execution", "solver_contract"}:
        class CompilerSuccess:
            def compile(self, ir, *, validated_ir_authorization):
                return compiler_result

        def solver_stage(graph):
            if stage == "solver_execution":
                raise RuntimeError(sentinel)
            return object()

        monkeypatch.setattr(runtime_module, "MechanicsCompiler", CompilerSuccess)
        monkeypatch.setattr(runtime_module, "solve_verified_equation_graph", solver_stage)

    execution = MechanicsRuntimeOrchestrator(
        _config(mode), modeler=modeler
    ).evaluate(PROBLEM)
    assert execution.terminal is RuntimeTerminal.failed
    assert execution.failure is expected_failure
    assert execution.delivery is delivery
    rendered = repr(execution) + execution.summary.model_dump_json()
    assert sentinel not in rendered


def test_invalid_authorization_shape_stops_before_compiler_construction(monkeypatch) -> None:
    outcome = _accepted_outcome()
    compiler_calls: list[object] = []

    class ForbiddenCompiler:
        def __init__(self) -> None:
            compiler_calls.append(self)

    monkeypatch.setattr(runtime_module, "authorize_validated_mechanics_ir", lambda ir: object())
    monkeypatch.setattr(runtime_module, "MechanicsCompiler", ForbiddenCompiler)
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.required), modeler=_ModelerSpy(outcome)
    ).evaluate(PROBLEM)
    assert execution.terminal is RuntimeTerminal.failed
    assert execution.failure is RuntimeFailure.authorization
    assert compiler_calls == []
