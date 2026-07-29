"""CI source identity and deterministic sharding contracts.

These checks pin the orchestration defect fixed during the B7 closure: PR jobs
must test the PR head itself, and a bounded job must never run four 420-second
shards sequentially under one 20-minute budget.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / ".github/workflows/backend-tests.yml"
STAGE6 = ROOT / ".github/workflows/phase56-stage6-multimodal.yml"
STAGE7 = ROOT / ".github/workflows/phase56-stage7-offline-evaluation.yml"
PHASE55 = ROOT / ".github/workflows/phase55-textbook-parser.yml"
FAST_WRAPPER = ROOT / "scripts/check_backend_fast.sh"
SHARDER = ROOT / "backend/scripts/pytest_file_shards.py"
SLOW_WRAPPER = ROOT / "scripts/check_backend_slow.sh"
NODE_SHARDER = ROOT / "backend/scripts/pytest_node_shards.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_permanent_workflow_checks_out_and_verifies_the_exact_source_sha() -> None:
    for path in (RELEASE, STAGE6, STAGE7, PHASE55):
        text = _text(path)
        assert "github.event.pull_request.head.sha" in text, path
        assert "ref: ${{ env.EXACT_HEAD_SHA }}" in text, path
        assert "git rev-parse HEAD" in text, path
        assert "refs/remotes/pull/" not in text, path


def test_release_fast_suite_is_four_parallel_jobs_with_a_partition_gate() -> None:
    text = _text(RELEASE)
    assert "shard_index: [0, 1, 2, 3]" in text
    assert "name: backend fast shard ${{ matrix.shard_index }}" in text
    assert "DYNATUTOR_BACKEND_FAST_SHARD_INDEX: ${{ matrix.shard_index }}" in text
    assert "backend_fast_audit:" in text
    assert "backend-fast-manifest-${{ github.run_id }}" in text
    assert "- backend_fast_audit" in text
    assert "cancel-in-progress: false" in text



def test_release_slow_suite_is_eight_parallel_node_shards_with_a_partition_gate() -> None:
    text = _text(RELEASE)
    assert "name: backend slow shard ${{ matrix.shard_index }}" in text
    assert "shard_index: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]" in text
    assert "DYNATUTOR_BACKEND_SLOW_SHARD_INDEX: ${{ matrix.shard_index }}" in text
    assert "backend_slow_audit:" in text
    assert "backend-slow-manifest-${{ github.run_id }}" in text
    assert "- backend_slow_audit" in text
    wrapper = _text(SLOW_WRAPPER)
    assert 'SLOW_MARKER_EXPRESSION="slow and not benchmark and not audit and not frontend"' in wrapper
    assert 'DYNATUTOR_BACKEND_SLOW_SHARD_COUNT:-16' in wrapper
    assert "pytest_node_shards.py" in wrapper
    assert NODE_SHARDER.is_file()

def test_stage6_focused_and_default_regression_are_a_complete_disjoint_partition() -> None:
    text = _text(STAGE6)
    assert "shard_index: [0, 1, 2, 3, 4, 5, 6, 7]" in text
    assert 'DYNATUTOR_BACKEND_FAST_SHARD_COUNT: "8"' in text
    assert "DYNATUTOR_BACKEND_FAST_EXCLUDE_GLOB: tests/test_phase56_stage6*.py" in text
    assert "stage6-focused-manifest" in text
    assert "partition_audit:" in text
    assert "excluded == actual" in text
    assert "focused['test_count'] == baseline['excluded_test_count']" in text
    assert "needs: [focused, backend_regression, partition_audit, frontend]" in text
    assert "cancel-in-progress: false" in text


def test_stage7_runs_the_entire_b7_file_in_an_explicit_slow_job() -> None:
    text = _text(STAGE7)
    assert "b7-slow-contracts:" in text
    assert "tests/test_phase56_stage7_b7_polar_kinematics_state.py" in text
    assert '-m "slow and not benchmark and not audit and not frontend"' in text
    assert "needs: [offline-evaluation, b7-slow-contracts, frontend]" in text


def test_fast_wrapper_never_changes_the_frozen_marker_or_hides_a_file_by_default() -> None:
    text = _text(FAST_WRAPPER)
    assert 'FAST_MARKER_EXPRESSION="not benchmark and not audit and not frontend and not slow"' in text
    assert 'EXCLUDE_GLOB="${DYNATUTOR_BACKEND_FAST_EXCLUDE_GLOB:-}"' in text
    assert "--exclude-glob" in text
    assert "for (( index = 0; index < SHARD_COUNT; index++ ))" in text
    assert SHARDER.is_file()
