from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import inspect
from pathlib import Path

import pytest

import engine.mechanics.migration.harness as harness_module
from engine.mechanics.compiler import CompilerResult, CompilerStatus
from engine.mechanics.contracts import MechanicsProblemIRV1
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.migration import (
    DifferentialStatus,
    InvarianceVariantKind,
    LabelledIRProbeVariant,
    LegacyCandidateScalar,
    LegacyObservation,
    LegacyTerminal,
    MechanicsMigrationProbeExecution,
    MigrationProbeFailure,
    MigrationProbeStage,
    MigrationProbeTerminal,
    compare_mechanics_ir_invariance,
    execute_mechanics_ir_probe,
)
from engine.mechanics.verification.contracts import (
    MechanicsSolveResult,
    MechanicsSolveTerminal,
)
from test_phase56_mechanics_compiler import _problem_payload
from test_phase56_mechanics_legacy_parity import _empty_nonsolved_result, _graph


NON_SOLVED_TERMINALS = tuple(
    item for item in MechanicsSolveTerminal
    if item is not MechanicsSolveTerminal.solved
)
NON_COMPILABLE_STATUSES = tuple(
    item for item in CompilerStatus
    if item not in {CompilerStatus.ready, CompilerStatus.overdetermined}
)


def _single_particle_ir(*, force: float = 10.0) -> MechanicsProblemIRV1:
    payload = deepcopy(_problem_payload())
    payload["entities"] = payload["entities"][:1]
    payload["symbols"] = [
        item for item in payload["symbols"]
        if item["symbol_id"] in {"mA", "fA", "aA"}
    ]
    payload["quantities"] = [
        item for item in payload["quantities"]
        if item["quantity_id"] in {"massA", "forceA", "accelerationA"}
    ]
    payload["source_evidence"] = []
    for index, quantity in enumerate(payload["quantities"]):
        if quantity["quantity_id"] == "forceA":
            quantity["raw_value"] = str(force)
            quantity["si_value"] = force
        if quantity["si_value"] is None:
            continue
        evidence_id = f"quantityEvidence{index}"
        payload["source_evidence"].append(
            {
                "kind": "text",
                "evidence_id": evidence_id,
                "quote": "A stated physical quantity is supplied here.",
                "source_span": {"start": 0, "end": 44},
                "quantity_span": None,
                "occurrence_index": 0,
            }
        )
        quantity.update(
            provenance="explicit_source",
            evidence_refs=[evidence_id],
            correction_id=None,
        )
    payload["motion_intervals"][0]["subject_ids"] = ["bodyA"]
    payload["interactions"] = payload["interactions"][:1]
    payload["assumptions"] = []
    return MechanicsProblemIRV1.model_validate(payload)


def _diagnostic_variant(
    ir: MechanicsProblemIRV1,
    *,
    system_type: str | None,
    paraphrase: str,
) -> MechanicsProblemIRV1:
    payload = ir.model_dump(mode="python", warnings="none")
    payload["metadata"]["system_type"] = system_type
    payload["metadata"]["subtype"] = None
    evidence = [dict(item) for item in payload["source_evidence"]]
    for item in evidence:
        item["quote"] = paraphrase
        item["source_span"] = {"start": 0, "end": len(paraphrase)}
    payload["source_evidence"] = evidence
    return MechanicsProblemIRV1.model_validate(payload)


def _observation(*, selected: float = 5.0) -> LegacyObservation:
    return LegacyObservation(
        case_id="singleParticleCase",
        diagnostic_kernel_id="independentOracle",
        terminal=LegacyTerminal.solved,
        query_symbol_id="aA",
        si_unit="m*s^-2",
        selected_scalar_si=selected,
        complete_candidate_scalars_si=(
            LegacyCandidateScalar(value_si=5.0, multiplicity=1),
        ),
        residual_passed=True,
    )


@pytest.fixture(scope="module")
def ir() -> MechanicsProblemIRV1:
    return _single_particle_ir()


@pytest.fixture(scope="module")
def solved_execution(ir: MechanicsProblemIRV1) -> MechanicsMigrationProbeExecution:
    execution = execute_mechanics_ir_probe(ir)
    assert execution.terminal is MigrationProbeTerminal.solved
    assert execution.solve_result is not None
    return execution


@pytest.fixture(scope="module")
def nonsolved_results(solved_execution):
    ambiguity = solve_verified_equation_graph(_graph(positive_only=False))
    needs_confirmation = solve_verified_equation_graph(_graph(nonlinear=True))
    results = {
        MechanicsSolveTerminal.ambiguity: ambiguity,
        MechanicsSolveTerminal.needs_confirmation: needs_confirmation,
    }
    results.update(
        {
            terminal: _empty_nonsolved_result(
                solved_execution.solve_result, terminal
            )
            for terminal in NON_SOLVED_TERMINALS
            if terminal not in results
        }
    )
    assert set(results) == set(NON_SOLVED_TERMINALS)
    return results


def test_real_scalar_probe_builds_full_and_mismatch_diagnostics(ir) -> None:
    matching = execute_mechanics_ir_probe(ir, observation=_observation())
    assert matching.terminal is MigrationProbeTerminal.solved
    assert matching.differential_status is DifferentialStatus.full_parity
    assert matching.differential_report is not None
    assert matching.differential_report.discrepancies == ()

    mismatch = execute_mechanics_ir_probe(ir, observation=_observation(selected=6.0))
    assert mismatch.terminal is MigrationProbeTerminal.solved
    assert mismatch.differential_status is DifferentialStatus.mismatch
    assert mismatch.differential_report is not None
    assert mismatch.differential_report.discrepancies


def test_exact_single_call_order_and_graph_object_identity(
    monkeypatch, ir, solved_execution
) -> None:
    exact_compiler = solved_execution.compiler_result
    exact_solve = solved_execution.solve_result
    assert exact_compiler is not None and exact_compiler.graph is not None
    assert exact_solve is not None
    events: list[str] = []

    def fingerprint(value):
        events.append("fingerprint")
        assert value is ir
        return solved_execution.calculation_fingerprint

    def authorize(value):
        events.append("authorize")
        assert value is ir
        return harness_module.ValidatedIRAuthorization(
            ir_sha256=harness_module._full_ir_digest(ir)
        )

    class CompilerSpy:
        def __init__(self):
            events.append("construct")

        def compile(self, value, *, validated_ir_authorization):
            events.append("compile")
            assert value is ir
            assert validated_ir_authorization.ir_sha256 == harness_module._full_ir_digest(ir)
            return exact_compiler

    def solve(graph):
        events.append("solve")
        assert graph is exact_compiler.graph
        return exact_solve

    monkeypatch.setattr(harness_module, "calculation_fingerprint", fingerprint)
    monkeypatch.setattr(harness_module, "authorize_validated_mechanics_ir", authorize)
    monkeypatch.setattr(harness_module, "MechanicsCompiler", CompilerSpy)
    monkeypatch.setattr(harness_module, "solve_verified_equation_graph", solve)
    execution = execute_mechanics_ir_probe(ir)
    assert execution.terminal is MigrationProbeTerminal.solved
    assert events == ["fingerprint", "authorize", "construct", "compile", "solve"]
    assert execution.compiler_result is exact_compiler
    assert execution.solve_result is exact_solve


def test_diagnostic_variants_are_fully_invariant_and_physics_change_is_not(
    ir, solved_execution
) -> None:
    changed = _diagnostic_variant(
        ir,
        system_type="incorrectDiagnosticLabel",
        paraphrase="This wording describes the same supplied physical quantity.",
    )
    removed = _diagnostic_variant(
        ir,
        system_type=None,
        paraphrase="Equivalent wording preserves every physical datum in the input.",
    )
    physical = _single_particle_ir(force=12.0)
    result = compare_mechanics_ir_invariance(
        solved_execution,
        (
            LabelledIRProbeVariant(
                label="changedLabel",
                kind=InvarianceVariantKind.system_type_changed,
                ir=changed,
            ),
            LabelledIRProbeVariant(
                label="removedLabel",
                kind=InvarianceVariantKind.system_type_removed,
                ir=removed,
            ),
            LabelledIRProbeVariant(
                label="physicalChange",
                kind=InvarianceVariantKind.raw_text_paraphrase,
                ir=physical,
            ),
        ),
    )
    assert result.baseline is solved_execution
    assert [item.matches_baseline for item in result.variants] == [True, True, False], [
        (
            item.calculation_fingerprint_matches,
            item.compiler_result_matches,
            item.terminal_matches,
            item.failure_matches,
            item.solve_shape_matches,
            item.generic_signature_matches,
        )
        for item in result.variants
    ]
    assert all(item.generic_signature_matches is True for item in result.variants[:2])
    assert not result.variants[2].calculation_fingerprint_matches
    assert not result.variants[2].compiler_result_matches
    assert not result.all_invariant


@pytest.mark.parametrize("status", NON_COMPILABLE_STATUSES)
def test_every_noncompilable_status_retains_diagnostics_but_never_solves(
    monkeypatch, ir, solved_execution, status
) -> None:
    graph = (
        solved_execution.compiler_result.graph
        if status is CompilerStatus.underdetermined
        else None
    )
    result = CompilerResult(status=status, graph=graph)

    class CompilerStub:
        def compile(self, value, *, validated_ir_authorization):
            return result

    calls: list[object] = []
    monkeypatch.setattr(harness_module, "MechanicsCompiler", CompilerStub)
    monkeypatch.setattr(
        harness_module,
        "solve_verified_equation_graph",
        lambda graph: calls.append(graph),
    )
    execution = execute_mechanics_ir_probe(ir, observation=_observation())
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_result is result
    assert execution.compiler_has_graph is (graph is not None)
    assert execution.solve_result is None
    assert execution.differential_report is None
    assert calls == []


def test_overdetermined_graph_is_solved_with_exact_identity(
    monkeypatch, ir, solved_execution
) -> None:
    graph = solved_execution.compiler_result.graph
    solve_result = solved_execution.solve_result
    result = CompilerResult(status=CompilerStatus.overdetermined, graph=graph)

    class CompilerStub:
        def compile(self, value, *, validated_ir_authorization):
            return result

    seen: list[object] = []
    monkeypatch.setattr(harness_module, "MechanicsCompiler", CompilerStub)

    def solve(value):
        seen.append(value)
        return solve_result

    monkeypatch.setattr(harness_module, "solve_verified_equation_graph", solve)
    execution = execute_mechanics_ir_probe(ir)
    assert execution.terminal is MigrationProbeTerminal.solved
    assert seen == [result.graph] and seen[0] is result.graph


@pytest.mark.parametrize("terminal", NON_SOLVED_TERMINALS)
def test_every_nonsolved_terminal_keeps_only_not_comparable_report(
    monkeypatch, ir, nonsolved_results, terminal
) -> None:
    nonsolved = nonsolved_results[terminal]
    compiler_result = CompilerResult(
        status=CompilerStatus.ready,
        graph=nonsolved.plan.graph,
    )

    class CompilerStub:
        def compile(self, value, *, validated_ir_authorization):
            return compiler_result

    monkeypatch.setattr(harness_module, "MechanicsCompiler", CompilerStub)
    monkeypatch.setattr(
        harness_module, "solve_verified_equation_graph", lambda graph: nonsolved
    )
    execution = execute_mechanics_ir_probe(ir, observation=_observation())
    assert execution.terminal is MigrationProbeTerminal.solve_rejected
    assert execution.solve_result is nonsolved
    assert execution.differential_status is DifferentialStatus.not_comparable
    assert execution.differential_report is not None


@pytest.mark.parametrize(
    "stage,expected",
    (
        ("construction", MigrationProbeFailure.compiler_construction),
        ("compilation", MigrationProbeFailure.compiler_execution),
        ("solving", MigrationProbeFailure.solver_execution),
    ),
)
def test_stage_exceptions_fail_closed_without_exception_text(
    monkeypatch, ir, solved_execution, stage, expected
) -> None:
    sentinel = "PRIVATE_EXCEPTION_SENTINEL"
    if stage == "construction":
        class CompilerFailure:
            def __init__(self):
                raise RuntimeError(sentinel)

        monkeypatch.setattr(harness_module, "MechanicsCompiler", CompilerFailure)
    else:
        class CompilerStub:
            def compile(self, value, *, validated_ir_authorization):
                if stage == "compilation":
                    raise RuntimeError(sentinel)
                return solved_execution.compiler_result

        monkeypatch.setattr(harness_module, "MechanicsCompiler", CompilerStub)
        if stage == "solving":
            monkeypatch.setattr(
                harness_module,
                "solve_verified_equation_graph",
                lambda graph: (_ for _ in ()).throw(RuntimeError(sentinel)),
            )
    execution = execute_mechanics_ir_probe(ir)
    assert execution.terminal is MigrationProbeTerminal.failed
    assert execution.failure is expected
    assert sentinel not in repr(execution)


def test_forged_compiler_and_solve_shapes_fail_closed(
    monkeypatch, ir, solved_execution
) -> None:
    forged_ready = CompilerResult.model_construct(
        status=CompilerStatus.ready, graph=None, issues=()
    )

    class ForgedCompiler:
        def compile(self, value, *, validated_ir_authorization):
            return forged_ready

    monkeypatch.setattr(harness_module, "MechanicsCompiler", ForgedCompiler)
    execution = execute_mechanics_ir_probe(ir)
    assert execution.failure is MigrationProbeFailure.compiler_contract

    class SolveSubclass(MechanicsSolveResult):
        pass

    exact = solved_execution.solve_result
    subclass = SolveSubclass.model_validate(exact.model_dump(mode="python"))

    class ExactCompiler:
        def compile(self, value, *, validated_ir_authorization):
            return solved_execution.compiler_result

    monkeypatch.setattr(harness_module, "MechanicsCompiler", ExactCompiler)
    monkeypatch.setattr(
        harness_module, "solve_verified_equation_graph", lambda graph: subclass
    )
    execution = execute_mechanics_ir_probe(ir)
    assert execution.failure is MigrationProbeFailure.solver_contract


def test_exact_inputs_frozen_outputs_and_variant_bounds(ir, solved_execution) -> None:
    class IRSubclass(MechanicsProblemIRV1):
        pass

    subclass = IRSubclass.model_validate(ir.model_dump(mode="python"))
    with pytest.raises(TypeError, match="exact"):
        execute_mechanics_ir_probe(subclass)
    with pytest.raises(TypeError, match="tuple"):
        compare_mechanics_ir_invariance(solved_execution, [])
    duplicate = LabelledIRProbeVariant(
        label="duplicate",
        kind=InvarianceVariantKind.raw_text_paraphrase,
        ir=ir,
    )
    with pytest.raises(ValueError, match="unique"):
        compare_mechanics_ir_invariance(solved_execution, (duplicate, duplicate))
    with pytest.raises(ValueError, match="64"):
        compare_mechanics_ir_invariance(
            solved_execution,
            tuple(
                LabelledIRProbeVariant(
                    label=f"variant{index}",
                    kind=InvarianceVariantKind.raw_text_paraphrase,
                    ir=ir,
                )
                for index in range(65)
            ),
        )
    with pytest.raises(FrozenInstanceError):
        solved_execution.terminal = MigrationProbeTerminal.failed
    with pytest.raises(ValueError, match="bool"):
        replace(
            compare_mechanics_ir_invariance(solved_execution, (duplicate,)).variants[0],
            matches_baseline=1,
        )


def test_static_leaf_boundary_and_public_exports() -> None:
    path = Path(harness_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    forbidden = (
        ".runtime",
        ".services",
        ".routes",
        ".modeler",
        "engine.solvers",
        ".registry",
        ".parser",
        ".explanation",
        "solver.backends",
        "solver.engine",
        "verification.verifier",
    )
    assert not any(fragment in module for fragment in forbidden for module in imports)
    signature = inspect.signature(execute_mechanics_ir_probe)
    assert tuple(signature.parameters) == ("ir", "observation")
    assert signature.parameters["observation"].kind is inspect.Parameter.KEYWORD_ONLY
    assert len(harness_module.__all__) == len(set(harness_module.__all__))

    mechanics_dir = path.parents[1]
    for candidate in mechanics_dir.rglob("*.py"):
        if candidate.parent == path.parent:
            continue
        assert "engine.mechanics.migration.harness" not in candidate.read_text(
            encoding="utf-8"
        )
