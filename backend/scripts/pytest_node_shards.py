"""Deterministic node-level pytest sharding for expensive marked suites.

The complete node inventory is collected from pytest under one frozen marker
expression.  Every collected node is assigned exactly once to a deterministic
matrix shard; no fixture value, corpus field, expected answer, or runtime result
participates in routing.  Node-level distribution prevents a single expensive
parameterized file from exceeding a per-shard CI budget while retaining the
original marker scope unchanged.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import ClassVar, Sequence

SHARD_MANIFEST_SCHEMA = "dynatutor.pytest_node_shards"
SHARD_MANIFEST_VERSION = "1.0"
_SUMMARY_RE = re.compile(r"^\d+/\d+ tests collected(?: \(.*\))? in .+$")
_FAILURE_NODE_RE = re.compile(r"^(?:FAILED|ERROR)\s+(?P<node>[^\s]+)")
_TIMEOUT_RE = re.compile(r"^\[run_with_timeout\].*(?:timed out|timeout|exit)", re.I)


@dataclass(frozen=True, slots=True)
class TestNode:
    __test__: ClassVar[bool] = False
    node_id: str

    @property
    def path(self) -> str:
        return self.node_id.split("::", 1)[0]


@dataclass(frozen=True, slots=True)
class NodeShard:
    index: int
    nodes: tuple[TestNode, ...]


def parse_node_collection_output(text: str, *, backend_root: Path) -> tuple[TestNode, ...]:
    """Parse ``pytest --collect-only -q`` node IDs and fail closed on drift."""

    root = backend_root.resolve()
    records: list[TestNode] = []
    seen: set[str] = set()
    saw_summary = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[run_with_timeout] "):
            continue
        if _SUMMARY_RE.fullmatch(line):
            saw_summary = True
            continue
        if "::" not in line:
            raise ValueError(f"unexpected node collection output: {line}")
        path = line.split("::", 1)[0]
        candidate = (root / path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"collected path escapes backend root: {path}") from exc
        if not candidate.is_file():
            raise ValueError(f"collected test file does not exist: {path}")
        if line in seen:
            raise ValueError(f"duplicate collected test node: {line}")
        seen.add(line)
        records.append(TestNode(line))
    if not records:
        raise ValueError("collection produced no test nodes")
    if not saw_summary:
        raise ValueError("collection summary is missing")
    return tuple(records)


def assign_node_shards(records: Sequence[TestNode], *, shard_count: int) -> tuple[NodeShard, ...]:
    """Assign each sorted node once by stable round-robin placement."""

    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    if not records:
        raise ValueError("records must not be empty")
    effective_count = min(shard_count, len(records))
    buckets: list[list[TestNode]] = [[] for _ in range(effective_count)]
    for index, record in enumerate(sorted(records, key=lambda item: item.node_id)):
        buckets[index % effective_count].append(record)
    shards = tuple(
        NodeShard(index=index, nodes=tuple(bucket))
        for index, bucket in enumerate(buckets)
    )
    flattened = [item.node_id for shard in shards for item in shard.nodes]
    expected = [item.node_id for item in records]
    if len(flattened) != len(set(flattened)):
        raise AssertionError("node shard assignment contains duplicates")
    if set(flattened) != set(expected):
        missing = sorted(set(expected) - set(flattened))
        extra = sorted(set(flattened) - set(expected))
        raise AssertionError(f"node shard assignment drift: missing={missing} extra={extra}")
    return shards


def manifest_payload(records: Sequence[TestNode], shards: Sequence[NodeShard], *, marker: str) -> dict[str, object]:
    paths = sorted({item.path for item in records})
    payload: dict[str, object] = {
        "schema": SHARD_MANIFEST_SCHEMA,
        "version": SHARD_MANIFEST_VERSION,
        "marker": marker,
        "collected_file_count": len(paths),
        "collected_test_count": len(records),
        "shard_count": len(shards),
        "shards": [
            {
                "index": shard.index,
                "test_count": len(shard.nodes),
                "nodes": [item.node_id for item in shard.nodes],
            }
            for shard in shards
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    payload["sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def sanitized_failure_summary(log_text: str, *, shard: NodeShard, shard_count: int, exit_status: int) -> str:
    lines = [
        f"shard={shard.index}/{shard_count}",
        f"node_count={len(shard.nodes)}",
        f"exit_status={exit_status}",
    ]
    for line in log_text.splitlines():
        match = _FAILURE_NODE_RE.match(line)
        if match is not None:
            lines.append(f"failed_node={match.group('node')}")
        elif _TIMEOUT_RE.match(line):
            lines.append(f"timeout={line}")
        if len(lines) >= 64:
            break
    return "\n".join(lines) + "\n"


def _run_capture(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
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
        "--collect-only",
        "-q",
        "--disable-warnings",
        "-o",
        "addopts=",
        "-m",
        marker,
    ]


def _execution_command(*, marker: str, timeout_seconds: int, backend_root: Path, nodes: Sequence[str]) -> list[str]:
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
        *nodes,
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker", required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--failure-summary", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    backend_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(backend_root) + (os.pathsep + existing if existing else "")
    env["DYNATUTOR_RUN_CWD"] = str(backend_root)

    status, output = _run_capture(
        _collection_command(marker=args.marker, timeout_seconds=args.timeout_seconds, backend_root=backend_root),
        cwd=backend_root,
        env=env,
    )
    sys.stdout.write(output)
    if status != 0:
        print("[pytest_node_shards] collection failed", file=sys.stderr)
        return status
    try:
        records = parse_node_collection_output(output, backend_root=backend_root)
        shards = assign_node_shards(records, shard_count=args.shard_count)
    except (ValueError, AssertionError) as exc:
        print(f"[pytest_node_shards] {exc}", file=sys.stderr)
        return 2
    if not 0 <= args.shard_index < len(shards):
        print(f"[pytest_node_shards] shard index {args.shard_index} is outside 0..{len(shards)-1}", file=sys.stderr)
        return 2

    manifest = manifest_payload(records, shards, marker=args.marker)
    if args.manifest_output is not None:
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PYTEST_NODE_SHARD_MANIFEST=" + json.dumps({
        "schema": SHARD_MANIFEST_SCHEMA,
        "version": SHARD_MANIFEST_VERSION,
        "sha256": manifest["sha256"],
        "collected_file_count": manifest["collected_file_count"],
        "collected_test_count": manifest["collected_test_count"],
        "shard_test_counts": [len(item.nodes) for item in shards],
    }, separators=(",", ":")))

    shard = shards[args.shard_index]
    print(f"[pytest_node_shards] shard {shard.index + 1}/{len(shards)}: {len(shard.nodes)} tests")
    for item in shard.nodes:
        print(f"[pytest_node_shards] selected {item.node_id}")
    if args.verify_only:
        return 0

    if args.failure_summary is not None:
        args.failure_summary.unlink(missing_ok=True)
    run_status, run_output = _run_capture(
        _execution_command(
            marker=args.marker,
            timeout_seconds=args.timeout_seconds,
            backend_root=backend_root,
            nodes=tuple(item.node_id for item in shard.nodes),
        ),
        cwd=backend_root,
        env=env,
    )
    if run_status == 0:
        sys.stdout.write(run_output)
        return 0
    print(f"[pytest_node_shards] shard {shard.index + 1}/{len(shards)} failed; compact tail follows", file=sys.stderr)
    tail = "\n".join(run_output.splitlines()[-300:])
    if tail:
        print(tail, file=sys.stderr)
    if args.failure_summary is not None:
        args.failure_summary.parent.mkdir(parents=True, exist_ok=True)
        args.failure_summary.write_text(
            sanitized_failure_summary(run_output, shard=shard, shard_count=len(shards), exit_status=run_status),
            encoding="utf-8",
        )
    return run_status


if __name__ == "__main__":
    raise SystemExit(main())
