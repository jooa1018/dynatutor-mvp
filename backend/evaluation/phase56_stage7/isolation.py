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
# The tokens above name *gold* members.  A production module that reads one has
# reached into the evaluator's answer key, whatever it then does with it.
#
# The guard below distinguishes reading a gold member from *naming* one, because
# the two look identical to a substring scan and only one is a leak.  A leak is
# an identifier — `draft.expected_answer`, `expected_answer = ...`, a parameter
# of that name — or a string used as a subscript key — `payload["gold_graph"]`.
# A bare string constant in a collection literal is neither: that is how the
# runtime's own denylists (`ANSWER_AUTHORITY_FORBIDDEN_FIELDS`,
# `_FORBIDDEN_ENVELOPE_FIELDS`) spell the fields they exist to *reject*.  A
# substring scan would flag the defence as the vulnerability, so this guard
# reads the syntax instead of the text, and needs no allowlist to do it.
_SUBSCRIPT_READ_CONTEXTS = (ast.Load, ast.Store, ast.Del)


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


def _gold_token_use(node: ast.AST) -> str | None:
    """The forbidden token this node *reads*, or None.

    Identifier positions and subscript keys only.  Every other appearance of the
    same characters — a set element, a docstring, a comment — is a name, not a
    use, and naming a forbidden field is what a denylist is.
    """

    if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_RUNTIME_SOURCE_TOKENS:
        return node.attr
    if isinstance(node, ast.Name) and node.id in FORBIDDEN_RUNTIME_SOURCE_TOKENS:
        return node.id
    if isinstance(node, ast.arg) and node.arg in FORBIDDEN_RUNTIME_SOURCE_TOKENS:
        return node.arg
    if isinstance(node, ast.keyword) and node.arg in FORBIDDEN_RUNTIME_SOURCE_TOKENS:
        return node.arg
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if node.name in FORBIDDEN_RUNTIME_SOURCE_TOKENS:
            return node.name
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, _SUBSCRIPT_READ_CONTEXTS):
        key = node.slice
        if isinstance(key, ast.Constant) and key.value in FORBIDDEN_RUNTIME_SOURCE_TOKENS:
            return str(key.value)
    return None


def assert_runtime_source_does_not_read_gold_members(repository_root: Path) -> None:
    """No production module may read a gold member by name.

    The import guard above stops the evaluator package from being imported; this
    stops the same data arriving through an untyped payload that happens to
    carry the gold keys.
    """

    for relative_root in (Path("backend/app"), Path("backend/engine")):
        root = repository_root / relative_root
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                token = _gold_token_use(node)
                if token is not None:
                    raise ValueError(
                        f"production runtime reads a gold member: {path}:{token}"
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
