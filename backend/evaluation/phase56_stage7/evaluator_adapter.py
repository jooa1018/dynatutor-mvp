"""The single authorised crossing between the gold and runtime trust domains.

``runtime_domain`` may not import ``gold_domain``.  This adapter is the only
module allowed to see both, and it may move data in exactly one direction:
source-grounded, user-like input travels to the runtime domain, and nothing
else does.  Rebinding a runtime result to its gold case happens only after the
runtime snapshot is frozen.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import FrozenRuntimeResultV1
from evaluation.phase56_stage7.runtime_domain import (
    RuntimeDomainInputV1,
    RuntimeDomainSnapshotV1,
    RuntimeInputKind,
    RuntimeOptionsV1,
)


ADAPTER_VERSION = "phase56-stage7-evaluator-adapter-v1"

# Modules that may only score.  None of them may import an executing subsystem,
# so no scoring path can produce, correct, or select an answer.
GOLD_DOMAIN_MODULES: tuple[str, ...] = (
    "gold_domain.py",
    "corpus_integrity.py",
    "corpus_records.py",
    "corpus_semantics.py",
    "corpus_preflight.py",
    "redaction.py",
    "evaluator_adapter.py",
)
_FORBIDDEN_GOLD_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "app",
        "engine",
        "openai",
        "httpx",
        "requests",
        "urllib",
        "http",
        "subprocess",
        "socket",
    }
)


class GoldIsolationViolation(RuntimeError):
    """Raised when the gold domain would gain runtime or answer authority."""


@dataclass(frozen=True, slots=True)
class ExecutionTokenIssuer:
    """Issue opaque per-execution tokens with no case-identity derivation.

    The token is derived from a run nonce and a monotonic counter only.  Case
    ID, family, split, chapter, and expected answer never contribute, so the
    token cannot smuggle scorer metadata into the runtime domain.
    """

    run_nonce: str

    def issue(self, sequence: int) -> str:
        material = f"{ADAPTER_VERSION}\0{self.run_nonce}\0{sequence}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()[:32]


def to_runtime_input(
    case: PublicCorpusCaseV1,
    *,
    execution_token: str,
    options: RuntimeOptionsV1,
) -> RuntimeDomainInputV1:
    """Project one gold case down to user-like runtime input only.

    Only the problem text crosses.  Case ID, split, family, chapter, declared
    terminal, gold facts, evidence quotes, and the reference answer stay in the
    gold domain, so runtime cannot route on them or read an expected answer.
    """

    return RuntimeDomainInputV1(
        execution_token=execution_token,
        input_kind=RuntimeInputKind.problem_text,
        problem_text=case.problem_text,
        options=options,
    )


def rebind_after_freeze(
    *,
    snapshot: RuntimeDomainSnapshotV1,
    runtime_input: RuntimeDomainInputV1,
    cases_by_token: Mapping[str, PublicCorpusCaseV1],
) -> tuple[FrozenRuntimeResultV1, PublicCorpusCaseV1]:
    """Reconnect a frozen runtime snapshot to its gold case for scoring.

    ``FrozenRuntimeResultV1.from_runtime`` re-verifies the token and the cache
    identity, so a scorer cannot substitute a different execution, mutate the
    snapshot, or re-run the runtime with expected data.
    """

    frozen = FrozenRuntimeResultV1.from_runtime(runtime_input, snapshot)
    case = cases_by_token.get(snapshot.execution_token)
    if case is None:
        raise GoldIsolationViolation("no gold case is bound to this execution token")
    return frozen, case


def assert_gold_domain_has_no_execution_authority(repository_root: Path) -> None:
    """Prove no scoring module can import a runtime, provider, or network path."""

    package_root = repository_root / "backend/evaluation/phase56_stage7"
    for module_name in GOLD_DOMAIN_MODULES:
        path = package_root / module_name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            roots: list[str] = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]]
            for root in roots:
                if root in _FORBIDDEN_GOLD_IMPORT_ROOTS:
                    raise GoldIsolationViolation(
                        f"gold-domain module gains execution authority: "
                        f"{module_name}:{root}"
                    )


def assert_runtime_material_is_gold_free(
    runtime_input: RuntimeDomainInputV1, case: PublicCorpusCaseV1
) -> None:
    """Prove no gold token of this case appears in runtime or cache material.

    The check covers the full serialised runtime input as well as the cache
    material, which together are the only things a calculation, a cache key, or
    a provider prompt can be built from.
    """

    material = runtime_input.model_dump_json().encode("utf-8")
    cache_material = runtime_input.cache_material()
    gold_tokens: list[str] = [
        case.case_id,
        case.split.value,
        case.problem_hash,
        case.gold.parse_status,
        case.gold.future_expected_terminal,
        case.gold.phase55_expected_terminal,
    ]
    if case.family is not None:
        gold_tokens.append(case.family)
    if case.gold.expected_system_type is not None:
        gold_tokens.append(case.gold.expected_system_type)
    for answer in case.gold.answers:
        gold_tokens.append(repr(answer.numeric))
        if answer.unit is not None:
            gold_tokens.append(answer.unit)
        if answer.reference_expression is not None:
            gold_tokens.append(answer.reference_expression)

    for token in gold_tokens:
        if not token:
            continue
        encoded = token.encode("utf-8")
        # The problem text itself is authorised user input; a gold token that
        # legitimately occurs inside it is not a leak.
        if encoded in case.problem_text.encode("utf-8"):
            continue
        if encoded in material or encoded in cache_material:
            raise GoldIsolationViolation(
                "runtime material carries gold metadata for this case"
            )
