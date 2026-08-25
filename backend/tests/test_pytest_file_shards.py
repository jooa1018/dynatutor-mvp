from pathlib import Path

import pytest

from scripts.pytest_file_shards import (
    Shard,
    TestFileCount,
    assign_file_shards,
    manifest_payload,
    parse_collection_output,
    sanitized_failure_summary,
    split_excluded_records,
)


def _files(tmp_path: Path, names: tuple[str, ...]) -> None:
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test\n", encoding="utf-8")


def test_collection_parser_accepts_only_existing_unique_test_files(tmp_path: Path) -> None:
    names = ("tests/test_a.py", "tests/test_b.py")
    _files(tmp_path, names)
    parsed = parse_collection_output(
        "tests/test_a.py: 3\ntests/test_b.py: 7\n[run_with_timeout] exit=0\n",
        backend_root=tmp_path,
    )
    assert parsed == (
        TestFileCount("tests/test_a.py", 3),
        TestFileCount("tests/test_b.py", 7),
    )


@pytest.mark.parametrize(
    "text, expected",
    (
        ("tests/test_missing.py: 1\n", "does not exist"),
        ("tests/test_a.py: 1\ntests/test_a.py: 1\n", "duplicate"),
        ("not a pytest collection line\n", "unexpected"),
    ),
)
def test_collection_parser_fails_closed(
    tmp_path: Path, text: str, expected: str
) -> None:
    _files(tmp_path, ("tests/test_a.py",))
    with pytest.raises(ValueError, match=expected):
        parse_collection_output(text, backend_root=tmp_path)


def test_assignment_is_deterministic_complete_disjoint_and_balanced() -> None:
    records = tuple(
        TestFileCount(f"tests/test_{index}.py", count)
        for index, count in enumerate((50, 40, 30, 20, 10, 9, 8, 7, 6, 5))
    )
    first = assign_file_shards(records, shard_count=4)
    second = assign_file_shards(tuple(reversed(records)), shard_count=4)
    assert first == second
    flattened = [item.path for shard in first for item in shard.files]
    assert len(flattened) == len(set(flattened)) == len(records)
    assert set(flattened) == {item.path for item in records}
    assert sum(shard.test_count for shard in first) == sum(item.count for item in records)
    assert max(shard.test_count for shard in first) - min(
        shard.test_count for shard in first
    ) <= max(item.count for item in records)


def test_more_requested_shards_than_files_never_creates_empty_shards() -> None:
    records = (TestFileCount("tests/test_a.py", 1), TestFileCount("tests/test_b.py", 2))
    shards = assign_file_shards(records, shard_count=8)
    assert len(shards) == 2
    assert all(shard.files for shard in shards)


@pytest.mark.parametrize("shard_count", (0, -1))
def test_invalid_shard_count_is_rejected(shard_count: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        assign_file_shards((TestFileCount("tests/test_a.py", 1),), shard_count=shard_count)


def test_exclusion_split_is_complete_disjoint_and_glob_scoped() -> None:
    records = (
        TestFileCount("tests/test_phase56_stage6_a.py", 2),
        TestFileCount("tests/test_other.py", 3),
        TestFileCount("tests/test_phase56_stage6_b.py", 5),
    )
    selected, excluded = split_excluded_records(
        records, exclude_globs=("tests/test_phase56_stage6*.py",)
    )
    assert selected == (TestFileCount("tests/test_other.py", 3),)
    assert excluded == (
        TestFileCount("tests/test_phase56_stage6_a.py", 2),
        TestFileCount("tests/test_phase56_stage6_b.py", 5),
    )


def test_exclusion_cannot_remove_every_file() -> None:
    records = (TestFileCount("tests/test_a.py", 1),)
    with pytest.raises(ValueError, match="every"):
        split_excluded_records(records, exclude_globs=("tests/*.py",))


def test_manifest_records_exact_selected_excluded_partition_without_runtime_data() -> None:
    all_records = (
        TestFileCount("tests/test_a.py", 2),
        TestFileCount("tests/test_stage6.py", 4),
        TestFileCount("tests/test_b.py", 1),
    )
    selected, excluded = split_excluded_records(
        all_records, exclude_globs=("tests/test_stage6.py",)
    )
    shards = assign_file_shards(selected, shard_count=2)
    manifest = manifest_payload(
        all_records,
        selected,
        excluded,
        shards,
        marker="not slow",
        exclude_globs=("tests/test_stage6.py",),
    )
    assert manifest["collected_file_count"] == 3
    assert manifest["collected_test_count"] == 7
    assert manifest["selected_file_count"] == 2
    assert manifest["selected_test_count"] == 3
    assert manifest["excluded_file_count"] == 1
    assert manifest["excluded_test_count"] == 4
    assert manifest["excluded_files"] == ["tests/test_stage6.py"]
    assert sum(item["test_count"] for item in manifest["shards"]) == 3
    assert {path for item in manifest["shards"] for path in item["files"]} == {
        "tests/test_a.py",
        "tests/test_b.py",
    }
    assert len(manifest["sha256"]) == 64


def test_failure_summary_contains_only_closed_diagnostics() -> None:
    shard = Shard(1, (TestFileCount("tests/test_a.py", 4),))
    summary = sanitized_failure_summary(
        "FAILED tests/test_a.py::test_x - assert secret == 7\n"
        "E sensitive fixture value\n"
        "[run_with_timeout] command timed out after 420s\n",
        shard=shard,
        shard_count=4,
        exit_status=124,
    )
    assert "failed_node=tests/test_a.py::test_x" in summary
    assert "timeout=[run_with_timeout] command timed out after 420s" in summary
    assert "secret" not in summary
    assert "sensitive" not in summary
