"""Stage 7 permanent offline workflow and gate-runner contract.

These tests keep the workflow read-only and offline by construction: a future
edit that adds a push, a finalizer dispatch, a secret read, a live credential,
or a raw-corpus commit fails here rather than in production.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from evaluation.phase56_stage7.contracts import stage7_evaluation_contract


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github/workflows/phase56-stage7-offline-evaluation.yml"
)
RUNNER_PATH = REPOSITORY_ROOT / "backend/tools/run_phase56_stage7_offline_gate.py"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_runner():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("stage7_gate_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Slotted dataclasses resolve their defining module through ``sys.modules``.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_workflow_exists_and_is_read_only(workflow_text: str) -> None:
    assert "permissions:\n  contents: read\n" in workflow_text
    assert "contents: write" not in workflow_text
    assert "pull-requests: write" not in workflow_text
    assert "id-token:" not in workflow_text


@pytest.mark.parametrize(
    "forbidden",
    (
        "git push",
        "git commit",
        "peter-evans/create-pull-request",
        "workflow_run:",
        "repository_dispatch",
        "gh workflow run",
        "gh pr ",
        "secrets.",
        "vercel",
        "deploy",
    ),
)
def test_workflow_never_pushes_dispatches_or_reads_secrets(
    workflow_text: str, forbidden: str
) -> None:
    assert forbidden not in workflow_text


def test_workflow_forces_empty_credentials_and_provider_base_urls(
    workflow_text: str,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "MECHANICS_MODELER_BASE_URL",
        "MECHANICS_FIGURE_BASE_URL",
    ):
        assert re.search(rf'^\s+{name}: ""$', workflow_text, re.MULTILINE), name


def test_workflow_runs_integrity_and_isolation_before_regression(
    workflow_text: str,
) -> None:
    gate_index = workflow_text.index("Stage 7 offline gate")
    focused_index = workflow_text.index("Stage 7 focused contracts")
    regression_index = workflow_text.index("Full backend regression")
    assert gate_index < focused_index < regression_index


def test_workflow_asserts_no_source_mutation_and_uploads_only_the_report(
    workflow_text: str,
) -> None:
    assert "Assert the gate mutated no source" in workflow_text
    assert "worktree-before.txt" in workflow_text
    assert "worktree-after.txt" in workflow_text
    upload = workflow_text[workflow_text.index("Upload redacted aggregate artifact") :]
    assert "stage7_offline_gate_report.json" in upload
    for leaky in (
        "public_dev.jsonl",
        "public_adversarial.jsonl",
        ".zip",
        "backend/tests/fixtures",
    ):
        assert leaky not in upload


def test_workflow_covers_frontend_lane_gates(workflow_text: str) -> None:
    for step in (
        "Frontend tests",
        "Frontend lint",
        "Frontend typecheck",
        "Frontend production build",
    ):
        assert step in workflow_text


def test_workflow_never_names_private_or_full_corpus_material(
    workflow_text: str,
) -> None:
    contract = stage7_evaluation_contract()
    for forbidden in contract.corpus.forbidden_commit_names:
        assert forbidden not in workflow_text


def test_gate_runner_declares_the_supplied_corpus_path_contract() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert 'PUBLIC_CORPUS_PATH_ENV = "STAGE7_PUBLIC_CORPUS_PATH"' in source
    # The runner reports NOT_RUN rather than claiming an unexecuted pass.
    assert '"disposition": "NOT_RUN"' in source


def test_gate_runner_emits_a_privacy_safe_report_without_a_corpus(
    gate_runner, monkeypatch
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "MECHANICS_MODELER_BASE_URL",
        "MECHANICS_FIGURE_BASE_URL",
        "STAGE7_PUBLIC_CORPUS_PATH",
    ):
        monkeypatch.setenv(name, "")

    report, passed = gate_runner.build_report()
    assert passed
    assert report["external_model_calls"] == 0
    assert report["private_heldout_accesses"] == 0
    assert report["measured_cost_usd"] == 0.0
    assert report["actual_model_quality"] == "NOT_RUN / N/A"
    assert report["public_corpus"]["disposition"] == "NOT_RUN"
    assert report["public_corpus"]["public_total"] == "NOT_RUN"
    assert all(
        gate["result"] in ("PASS", "NOT_RUN") for gate in report["gates"]
    )
    structural = {gate["name"] for gate in report["gates"]}
    assert {
        "runtime_domain_does_not_import_gold",
        "production_runtime_isolated_from_evaluator",
        "gold_domain_has_no_execution_authority",
        "corpus_modules_are_execution_free",
        "raw_corpus_is_not_committed",
        "stage7_contract_preflight",
        "public_corpus_integrity",
    } <= structural

    serialized = json.dumps(report, ensure_ascii=False)
    for forbidden in (
        "problem_text",
        "gold_graph",
        "expected_answer",
        "raw_provider_output",
        "image_base64",
    ):
        assert forbidden not in serialized


def test_gate_runner_refuses_to_run_with_live_credentials(
    gate_runner, monkeypatch
) -> None:
    from evaluation.phase56_stage7.network_guard import ExternalNetworkBlocked

    for name in ("ANTHROPIC_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-key-must-not-be-used")
    with pytest.raises(ExternalNetworkBlocked):
        gate_runner.build_report()


# --------------------------------------------------------------------------
# Strict acceptance mode
# --------------------------------------------------------------------------


def test_gate_runner_declares_the_strict_acceptance_flags() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "--require-public-corpus" in source
    assert "--require-full-stage7" in source


def test_strict_mode_refuses_an_absent_corpus(gate_runner) -> None:
    report = {
        "public_corpus": {"supplied": False, "disposition": "NOT_RUN"},
        "lane_b": {"executed": False, "disposition": "NOT_RUN"},
    }
    outcomes = gate_runner._strict_requirements(
        report, require_corpus=True, require_full=False
    )
    assert outcomes
    assert not all(outcome.passed for outcome in outcomes)
    failed = {outcome.name for outcome in outcomes if not outcome.passed}
    assert "strict_corpus_supplied" in failed


def test_strict_mode_refuses_a_lane_that_did_not_run(gate_runner) -> None:
    report = {
        "public_corpus": {"supplied": True, "disposition": "PASS"},
        "lane_b": {
            "executed": True,
            "total_cases": 100,
            "executed_cases": 98,
            "terminal_counts": {"solved": 98, "needs_figure": 2},
        },
    }
    outcomes = gate_runner._strict_requirements(
        report, require_corpus=False, require_full=True
    )
    failed = {outcome.name for outcome in outcomes if not outcome.passed}
    # Lane B is fully solved here, so only the lanes that never ran may fail.
    assert "strict_lane_b_all_solved" not in failed
    assert {
        "strict_lane_c_pass",
        "strict_lane_d_pass",
        "strict_lane_e_pass",
        "strict_compositional_12_pass",
        "strict_synthetic_38_pass",
        "strict_metamorphic_pass",
        "strict_hard_safety_pass",
    } <= failed


def test_strict_mode_refuses_unsolved_lane_b_cases(gate_runner) -> None:
    report = {
        "public_corpus": {"supplied": True, "disposition": "PASS"},
        "lane_b": {
            "executed": True,
            "total_cases": 100,
            "executed_cases": 98,
            "terminal_counts": {"compiler_failure": 82, "needs_figure": 2},
        },
    }
    outcomes = gate_runner._strict_requirements(
        report, require_corpus=False, require_full=True
    )
    failed = {outcome.name for outcome in outcomes if not outcome.passed}
    assert "strict_lane_b_all_solved" in failed


def test_strict_mode_requires_the_exact_corpus_sha_and_counts(gate_runner) -> None:
    from evaluation.phase56_stage7.contracts import stage7_evaluation_contract

    contract = stage7_evaluation_contract()
    report = {
        "public_corpus": {
            "supplied": True,
            "archive_sha256": contract.corpus.expected_zip_sha256,
            "public_dev": 84,
            "public_adversarial": 16,
            "public_total": 100,
        },
        "lane_b": {"executed": False},
    }
    outcomes = gate_runner._strict_requirements(
        report, require_corpus=True, require_full=False
    )
    assert all(outcome.passed for outcome in outcomes)

    wrong = {**report, "public_corpus": {**report["public_corpus"], "public_dev": 83}}
    outcomes = gate_runner._strict_requirements(
        wrong, require_corpus=True, require_full=False
    )
    assert not all(outcome.passed for outcome in outcomes)
