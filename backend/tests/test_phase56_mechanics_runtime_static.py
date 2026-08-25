from __future__ import annotations

import ast
import inspect
from pathlib import Path

import engine.mechanics as mechanics
from engine.mechanics.runtime import (
    MechanicsRuntimeOrchestrator,
    MechanicsRuntimeSummary,
)
import engine.mechanics.runtime.contracts as contracts_module
import engine.mechanics.runtime.orchestrator as orchestrator_module


RUNTIME_DIR = Path(orchestrator_module.__file__).parent
ORCHESTRATOR_PATH = Path(orchestrator_module.__file__)
CONTRACTS_PATH = Path(contracts_module.__file__)


def _function(tree: ast.AST, class_name: str, function_name: str) -> ast.FunctionDef:
    owner = next(
        item
        for item in ast.walk(tree)
        if isinstance(item, ast.ClassDef) and item.name == class_name
    )
    return next(
        item
        for item in owner.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    )


def test_public_constructor_and_evaluate_signatures_expose_no_authority_injection() -> None:
    constructor = inspect.signature(MechanicsRuntimeOrchestrator)
    assert tuple(constructor.parameters) == ("config", "modeler")
    assert constructor.parameters["modeler"].kind is inspect.Parameter.KEYWORD_ONLY

    evaluate = inspect.signature(MechanicsRuntimeOrchestrator.evaluate)
    assert tuple(evaluate.parameters) == (
        "self",
        "problem_text",
        "confirmation_fingerprint",
    )
    assert (
        evaluate.parameters["confirmation_fingerprint"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    forbidden = {
        "ir",
        "seal",
        "graph",
        "backend",
        "equation",
        "solver",
        "legacy_result",
        "migration_report",
        "expected_answer",
        "system_type",
    }
    assert forbidden.isdisjoint(constructor.parameters)
    assert forbidden.isdisjoint(evaluate.parameters)


def test_evaluate_has_one_lexical_call_site_per_authority_stage_and_no_loops() -> None:
    tree = ast.parse(ORCHESTRATOR_PATH.read_text(encoding="utf-8"))
    evaluate = _function(tree, "MechanicsRuntimeOrchestrator", "evaluate")
    calls = tuple(item for item in ast.walk(evaluate) if isinstance(item, ast.Call))

    model_calls = tuple(
        item
        for item in calls
        if isinstance(item.func, ast.Attribute) and item.func.attr == "model"
    )
    authorize_calls = tuple(
        item
        for item in calls
        if isinstance(item.func, ast.Name)
        and item.func.id == "authorize_validated_mechanics_ir"
    )
    compile_calls = tuple(
        item
        for item in calls
        if isinstance(item.func, ast.Attribute) and item.func.attr == "compile"
    )
    solve_calls = tuple(
        item
        for item in calls
        if isinstance(item.func, ast.Name)
        and item.func.id == "solve_verified_equation_graph"
    )
    assert len(model_calls) == len(authorize_calls) == len(compile_calls) == len(solve_calls) == 1
    assert not any(isinstance(item, (ast.For, ast.AsyncFor, ast.While)) for item in ast.walk(evaluate))

    model_call = model_calls[0]
    assert len(model_call.args) == 1
    assert isinstance(model_call.args[0], ast.Name)
    assert model_call.args[0].id == "problem_text"
    assert model_call.keywords == []

    authorize_call = authorize_calls[0]
    assert len(authorize_call.args) == 1
    assert isinstance(authorize_call.args[0], ast.Name)
    assert authorize_call.args[0].id == "exact_ir"

    compile_call = compile_calls[0]
    assert len(compile_call.args) == 1
    assert isinstance(compile_call.args[0], ast.Name)
    assert compile_call.args[0].id == "exact_ir"
    assert [item.arg for item in compile_call.keywords] == [
        "validated_ir_authorization"
    ]
    assert isinstance(compile_call.keywords[0].value, ast.Name)
    assert compile_call.keywords[0].value.id == "authorization"

    solve_call = solve_calls[0]
    assert len(solve_call.args) == 1
    assert isinstance(solve_call.args[0], ast.Name)
    assert solve_call.args[0].id == "exact_graph"
    assert solve_call.keywords == []


def test_runtime_imports_exclude_product_legacy_migration_and_backend_modules() -> None:
    imported: set[str] = set()
    for path in RUNTIME_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
    forbidden_fragments = (
        ".services",
        ".migration",
        "legacy_kernels",
        "legacy_solver",
        ".routes",
        ".schemas",
        "solver.backends",
        "solver.engine",
        "verification.verifier",
    )
    assert not any(
        fragment in module
        for module in imported
        for fragment in forbidden_fragments
    )


def test_orchestrator_contains_no_forbidden_routing_or_answer_inputs() -> None:
    source = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    forbidden_tokens = (
        "system_type",
        "expected_answer",
        "corpus",
        "migration_report",
        "legacy_result",
        "legacy_solver",
        "backend=",
        "equations=",
    )
    assert all(token not in source for token in forbidden_tokens)
    assert "eval(" not in source
    assert "exec(" not in source


def test_summary_schema_is_an_exact_safe_allowlist() -> None:
    assert set(MechanicsRuntimeSummary.model_fields) == {
        "schema",
        "version",
        "mode",
        "terminal",
        "delivery",
        "modeler_terminal",
        "compiler_status",
        "compiler_issue_codes",
        "solve_terminal",
        "solve_diagnostic_codes",
        "failure",
        "current_calculation_fingerprint",
    }
    assert MechanicsRuntimeSummary.model_config["extra"] == "forbid"
    assert MechanicsRuntimeSummary.model_config["frozen"] is True
    assert MechanicsRuntimeSummary.model_config["strict"] is True


def test_root_runtime_exports_are_present_once_without_duplicate_public_names() -> None:
    expected = {
        "RUNTIME_CONTRACT_VERSION",
        "RUNTIME_SUMMARY_SCHEMA",
        "RUNTIME_SUMMARY_VERSION",
        "MechanicsRuntimeExecution",
        "MechanicsRuntimeOrchestrator",
        "MechanicsRuntimeSummary",
        "RuntimeDelivery",
        "RuntimeFailure",
        "RuntimeTerminal",
        "build_runtime_summary",
    }
    assert len(mechanics.__all__) == len(set(mechanics.__all__))
    assert expected <= set(mechanics.__all__)
    assert all(hasattr(mechanics, name) for name in expected)


def test_runtime_package_files_are_limited_to_the_fixed_three_modules() -> None:
    assert {item.name for item in RUNTIME_DIR.glob("*.py")} == {
        "__init__.py",
        "contracts.py",
        "orchestrator.py",
    }
    assert CONTRACTS_PATH.parent == ORCHESTRATOR_PATH.parent
