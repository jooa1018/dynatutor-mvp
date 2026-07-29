from pathlib import Path

import pytest

from scripts.pytest_node_shards import (
    NodeShard,
    TestNode,
    assign_node_shards,
    manifest_payload,
    parse_node_collection_output,
    sanitized_failure_summary,
)


def _file(tmp_path: Path, name: str = "tests/test_a.py") -> None:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# test\n", encoding="utf-8")


def test_node_collection_parser_accepts_unique_existing_nodes_and_summary(tmp_path: Path) -> None:
    _file(tmp_path)
    parsed = parse_node_collection_output(
        "tests/test_a.py::test_one\n"
        "tests/test_a.py::test_param[x]\n"
        "2/10 tests collected (8 deselected) in 0.10s\n"
        "[run_with_timeout] command exited with code 0\n",
        backend_root=tmp_path,
    )
    assert parsed == (
        TestNode("tests/test_a.py::test_one"),
        TestNode("tests/test_a.py::test_param[x]"),
    )


@pytest.mark.parametrize(
    "text, expected",
    (
        ("tests/test_a.py::test_one\n", "summary"),
        ("tests/test_missing.py::test_one\n1/1 tests collected in 0.1s\n", "does not exist"),
        ("tests/test_a.py::test_one\ntests/test_a.py::test_one\n2/2 tests collected in 0.1s\n", "duplicate"),
        ("unexpected\n1/1 tests collected in 0.1s\n", "unexpected"),
    ),
)
def test_node_collection_parser_fails_closed(tmp_path: Path, text: str, expected: str) -> None:
    _file(tmp_path)
    with pytest.raises(ValueError, match=expected):
        parse_node_collection_output(text, backend_root=tmp_path)


def test_node_assignment_spreads_parameterized_file_across_shards() -> None:
    records = tuple(TestNode(f"tests/test_heavy.py::test_case[{index:02d}]") for index in range(12))
    first = assign_node_shards(records, shard_count=8)
    second = assign_node_shards(tuple(reversed(records)), shard_count=8)
    assert first == second
    counts = [len(item.nodes) for item in first]
    assert counts == [2, 2, 2, 2, 1, 1, 1, 1]
    flattened = [node.node_id for shard in first for node in shard.nodes]
    assert len(flattened) == len(set(flattened)) == 12
    assert set(flattened) == {item.node_id for item in records}


def test_node_manifest_proves_complete_disjoint_partition() -> None:
    records = tuple(TestNode(f"tests/test_{index % 2}.py::test_{index}") for index in range(9))
    shards = assign_node_shards(records, shard_count=4)
    manifest = manifest_payload(records, shards, marker="slow")
    assert manifest["collected_file_count"] == 2
    assert manifest["collected_test_count"] == 9
    assert sum(item["test_count"] for item in manifest["shards"]) == 9
    nodes = [node for shard in manifest["shards"] for node in shard["nodes"]]
    assert len(nodes) == len(set(nodes)) == 9
    assert len(manifest["sha256"]) == 64


def test_node_failure_summary_is_closed_and_redacted() -> None:
    shard = NodeShard(2, (TestNode("tests/test_a.py::test_x"),))
    summary = sanitized_failure_summary(
        "FAILED tests/test_a.py::test_x - assert secret == 7\n"
        "E sensitive fixture value\n"
        "[run_with_timeout] timed out after 420s\n",
        shard=shard,
        shard_count=8,
        exit_status=124,
    )
    assert "failed_node=tests/test_a.py::test_x" in summary
    assert "timeout=[run_with_timeout] timed out after 420s" in summary
    assert "secret" not in summary
    assert "sensitive" not in summary
