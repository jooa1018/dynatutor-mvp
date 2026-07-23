from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable


FORBIDDEN_RUNTIME_IMPORT_FRAGMENTS = (
    "evaluation.phase56_stage7",
    "phase56_stage7_public",
    "public_dev.jsonl",
    "public_adversarial.jsonl",
    "private_heldout",
)
FORBIDDEN_RUNTIME_SOURCE_TOKENS = (
    "expected_answer",
    "gold_graph",
    "corpus_family",
)


def _python_files(root: Path) -> Iterable[Path]:
    yield from sorted(path for path in root.rglob("*.py") if path.is_file())


def assert_production_runtime_isolated(repository_root: Path) -> None:
    for relative_root in (Path("backend/app"), Path("backend/engine")):
        root = repository_root / relative_root
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                module: str | None = None
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                        if any(
                            fragment in module
                            for fragment in FORBIDDEN_RUNTIME_IMPORT_FRAGMENTS
                        ):
                            raise ValueError(
                                f"production runtime imports evaluator data: {path}:{module}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if any(
                        fragment in module
                        for fragment in FORBIDDEN_RUNTIME_IMPORT_FRAGMENTS
                    ):
                        raise ValueError(
                            f"production runtime imports evaluator data: {path}:{module}"
                        )


def assert_runtime_domain_does_not_import_gold(repository_root: Path) -> None:
    runtime_path = (
        repository_root
        / "backend/evaluation/phase56_stage7/runtime_domain.py"
    )
    source = runtime_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(runtime_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if "gold_domain" in node.module:
                raise ValueError("runtime domain must not import gold domain")
        if isinstance(node, ast.Import):
            if any("gold_domain" in alias.name for alias in node.names):
                raise ValueError("runtime domain must not import gold domain")


def assert_public_fixtures_excluded_from_production_image(repository_root: Path) -> None:
    dockerfile = (repository_root / "backend/Dockerfile").read_text(encoding="utf-8")
    normalized_lines = [
        " ".join(line.strip().split())
        for line in dockerfile.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    copy_lines = [line for line in normalized_lines if line.upper().startswith("COPY ")]
    if "COPY app ./app" not in copy_lines or "COPY engine ./engine" not in copy_lines:
        raise ValueError("production Dockerfile must explicitly copy app and engine")
    forbidden = ("tests", "fixtures", "evaluation", "public_dev", "public_adversarial")
    if any(any(token in line.casefold() for token in forbidden) for line in copy_lines):
        raise ValueError("production Dockerfile copies evaluator or fixture data")
