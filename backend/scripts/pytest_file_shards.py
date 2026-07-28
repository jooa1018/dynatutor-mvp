"""Deterministic file-level pytest sharding for bounded GitHub Actions jobs.

The selected pytest marker expression is never changed by the sharder.  It
collects the complete file inventory, applies only explicitly declared file
exclusions, validates that selected and excluded files form a complete disjoint
partition, then deterministically assigns every selected file to one shard.

No case identity, physics fixture, assertion value, corpus material, or answer
metadata participates in routing.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fnmatch import fnmatchcase
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import ClassVar, Iterable, Sequence

SHARD_MANIFEST_SCHEMA = "dynatutor.pytest_file_shards"
SHARD_MANIFEST_VERSION = "1.1"
_COLLECTION_RE = re.compile(r"^(?P<path>.+\.py):\s+(?P<count>[1-9][0-9]*)$")
_FAILURE_NODE_RE = re.compile(r"^(?:FAILED|ERROR)\s+(?P<node>[^\s]+)")
_TIMEOUT_RE = re.compile(r"^\[run_with_timeout\].*(?:timed out|timeout|exit)", re.I)


@dataclass(frozen=True, slots=True)
class TestFileCount:
    __test__: ClassVar[bool] = False
    path: str
    count: int


@dataclass(frozen=True, slots=True)
class Shard:
    index: int
    files: tuple[TestFileCount, ...]

    @property
    def test_count(self) -> int:
        return sum(item.count for item in self.files)


def parse_collection_output(text: str, *, backend_root: Path) -> tuple[TestFileCount, ...]:
    """Parse the stable ``pytest -qq --collect-only`` file-count format."""

    records: list[TestFileCount] = []
    seen: set[str] = set()
    root = backend_root.resolve()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[run_with_timeout] "):
            continue
        match = _COLLECTION_RE.fullmatch(line)
        if match is None:
            raise ValueError(f"unexpected collection output: {line}")
        path = match.group("path")
        count = int(match.group("count"))
        candidate = (root / path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"collected path escapes backend root: {path}") from exc
        if not candidate.is_file():
            raise ValueError(f"collected test file does not exist: {path}")
        if path in seen:
            raise ValueError(f"duplicate collected test file: {path}")
        seen.add(path)
        records.append(TestFileCount(path=path, count=count))
    if not records:
        raise ValueError("collection produced no test files")
    return tuple(records)


def split_excluded_records(
    records: Sequence[TestFileCount], *, exclude_globs: Sequence[str]
) -> tuple[tuple[TestFileCount, ...], tuple[TestFileCount, ...]]:
    """Return selected/excluded records and prove complete disjoint coverage."""

    selected: list[TestFileCount] = []
    excluded: list[TestFileCount] = []
    normalized = tuple(item for item in exclude_globs if item)
    for record in records:
        destination = excluded if any(
            fnmatchcase(record.path, pattern) for pattern in normalized
        ) else selected
        destination.append(record)
    if not selected:
        raise ValueError("file exclusions removed every collected test file")
    selected_paths = {item.path for item in selected}
    excluded_paths = {item.path for item in excluded}
    all_paths = {item.path for item in records}
    if selected_paths & excluded_paths:
        raise AssertionError("selected and excluded inventories overlap")
    if selected_paths | excluded_paths != all_paths:
        raise AssertionError("selected and excluded inventories are incomplete")
    if len(selected_paths) + len(excluded_paths) != len(records):
        raise AssertionError("selected/excluded inventory contains duplicates")
    return tuple(selected), tuple(excluded)


def assign_file_shards(
    records: Sequence[TestFileCount], *, shard_count: int
) -> tuple[Shard, ...]:
    """Assign every selected file once using deterministic least-loaded placement."""

    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    if not records:
        raise ValueError("records must not be empty")
    effective_count = min(shard_count, len(records))
    loads = [0] * effective_count
    buckets: list[list[TestFileCount]] = [[] for _ in range(effective_count)]
    for record in sorted(records, key=lambda item: (-item.count, item.path)):
        index = min(range(effective_count), key=lambda item: (loads[item], item))
        buckets[index].append(record)
        loads[index] += record.count

    shards = tuple(
        Shard(index=index, files=tuple(sorted(bucket, key=lambda item: item.path)))
        for index, bucket in enumerate(buckets)
    )
    flattened = [item.path for shard in shards for item in shard.files]
    expected = [item.path for item in records]
    if len(flattened) != len(set(flattened)):
        raise AssertionError("shard assignment contains duplicate files")
    if set(flattened) != set(expected):
        missing = sorted(set(expected) - set(flattened))
        extra = sorted(set(flattened) - set(expected))
        raise AssertionError(f"shard assignment drift: missing={missing} extra={extra}")
    if sum(shard.test_count for shard in shards) != sum(item.count for item in records):
        raise AssertionError("shard assignment changed the selected test count")
    return shards


def manifest_payload(
    all_records: Sequence[TestFileCount],
    selected_records: Sequence[TestFileCount],
    excluded_records: Sequence[TestFileCount],
    shards: Sequence[Shard],
    *,
    marker: str,
    exclude_globs: Sequence[str],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": SHARD_MANIFEST_SCHEMA,
        "version": SHARD_MANIFEST_VERSION,
        "marker": marker,
        "exclude_globs": list(exclude_globs),
        "collected_file_count": len(all_records),
        "collected_test_count": sum(item.count for item in all_records),
        "selected_file_count": len(selected_records),
        "selected_test_count": sum(item.count for item in selected_records),
        "excluded_file_count": len(excluded_records),
        "excluded_test_count": sum(item.count for item in excluded_records),
        "excluded_files": [item.path for item in excluded_records],
        "shard_count": len(shards),
        "shards": [
            {
                "index": shard.index,
                "file_count": len(shard.files),
                "test_count": shard.test_count,
                "files": [item.path for item in shard.files],
            }
            for shard in shards
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload["sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def sanitized_failure_summary(
    log_text: str,
    *,
    shard: Shard,
    shard_count: int,
    exit_status: int,
) -> str:
    """Return node identities and closed timeout diagnostics only."""

    nodes: list[str] = []
    timeouts: list[str] = []
    for raw_line in log_text.splitlines():
        match = _FAILURE_NODE_RE.match(raw_line)
        if match is not None and len(nodes) < 50:
            nodes.append(match.group("node"))
        elif _TIMEOUT_RE.match(raw_line) and len(timeouts) < 10:
            timeouts.append(raw_line.strip())
    lines = [
        f"shard_index={shard.index}",
        f"shard_count={shard_count}",
        f"selected_file_count={len(shard.files)}",
        f"selected_test_count={shard.test_count}",
        f"exit_status={exit_status}",
    ]
    lines.extend(f"failed_node={item}" for item in nodes)
    lines.extend(f"timeout={item}" for item in timeouts)
    return "\n".join(lines) + "\n"


def _run_capture(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.returncode, completed.stdout


def _collection_command(*, marker: str, timeout_seconds: int, backend_root: Path) -> list[str]:
    return [
        sys.executable,
        str(backend_root.parent / "scripts" / "run_with_timeout.py"),
        str(timeout_seconds),
        "--",
        sys.executable,
        "-m",
        "pytest",
        "-qq",
        "--disable-warnings",
        "--collect-only",
        "-o",
        "addopts=",
        "-m",
        marker,
    ]


def _execution_command(
    *, marker: str, timeout_seconds: int, backend_root: Path, files: Iterable[str]
) -> list[str]:
    return [
        sys.executable,
        str(backend_root.parent / "scripts" / "run_with_timeout.py"),
        str(timeout_seconds),
        "--",
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-o",
        "addopts=",
        "-m",
        marker,
        *files,
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker", required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument("--exclude-glob", action="append", default=[])
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--failure-summary", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)

    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    backend_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(backend_root) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    env["DYNATUTOR_RUN_CWD"] = str(backend_root)

    collect_status, collection_output = _run_capture(
        _collection_command(
            marker=args.marker,
            timeout_seconds=args.timeout_seconds,
            backend_root=backend_root,
        ),
        cwd=backend_root,
        env=env,
    )
    sys.stdout.write(collection_output)
    if collect_status != 0:
        print("[pytest_shards] collection failed", file=sys.stderr)
        return collect_status
    try:
        all_records = parse_collection_output(collection_output, backend_root=backend_root)
        selected_records, excluded_records = split_excluded_records(
            all_records, exclude_globs=args.exclude_glob
        )
        shards = assign_file_shards(selected_records, shard_count=args.shard_count)
    except (ValueError, AssertionError) as exc:
        print(f"[pytest_shards] {exc}", file=sys.stderr)
        return 2
    if not 0 <= args.shard_index < len(shards):
        print(
            f"[pytest_shards] shard index {args.shard_index} is outside 0..{len(shards)-1}",
            file=sys.stderr,
        )
        return 2

    manifest = manifest_payload(
        all_records,
        selected_records,
        excluded_records,
        shards,
        marker=args.marker,
        exclude_globs=args.exclude_glob,
    )
    if args.manifest_output is not None:
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    compact = {
        "schema": SHARD_MANIFEST_SCHEMA,
        "version": SHARD_MANIFEST_VERSION,
        "sha256": manifest["sha256"],
        "collected_file_count": manifest["collected_file_count"],
        "collected_test_count": manifest["collected_test_count"],
        "selected_file_count": manifest["selected_file_count"],
        "selected_test_count": manifest["selected_test_count"],
        "excluded_file_count": manifest["excluded_file_count"],
        "excluded_test_count": manifest["excluded_test_count"],
        "shard_test_counts": [item.test_count for item in shards],
    }
    print("PYTEST_SHARD_MANIFEST=" + json.dumps(compact, separators=(",", ":")))

    shard = shards[args.shard_index]
    print(
        f"[pytest_shards] shard {shard.index + 1}/{len(shards)}: "
        f"{len(shard.files)} files, {shard.test_count} tests"
    )
    for item in shard.files:
        print(f"[pytest_shards] selected {item.path}: {item.count}")
    if args.verify_only:
        return 0

    failure_summary = args.failure_summary
    if failure_summary is not None:
        failure_summary.unlink(missing_ok=True)
    run_status, run_output = _run_capture(
        _execution_command(
            marker=args.marker,
            timeout_seconds=args.timeout_seconds,
            backend_root=backend_root,
            files=(item.path for item in shard.files),
        ),
        cwd=backend_root,
        env=env,
    )
    if run_status == 0:
        sys.stdout.write(run_output)
        return 0

    print(
        f"[pytest_shards] shard {shard.index + 1}/{len(shards)} failed; compact tail follows",
        file=sys.stderr,
    )
    tail = "\n".join(run_output.splitlines()[-300:])
    if tail:
        print(tail, file=sys.stderr)
    if failure_summary is not None:
        failure_summary.parent.mkdir(parents=True, exist_ok=True)
        failure_summary.write_text(
            sanitized_failure_summary(
                run_output,
                shard=shard,
                shard_count=len(shards),
                exit_status=run_status,
            ),
            encoding="utf-8",
        )
    return run_status


if __name__ == "__main__":
    raise SystemExit(main())
