"""Stage 7 corpus integrity preflight orchestration.

Corpus integrity runs strictly before execution.  Whatever fails, the result is
a structured ``HARNESS_CONTRACT_FAILURE`` with zero runtime, compiler, solver,
and provider calls and zero cost.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from evaluation.phase56_stage7.contracts import (
    PUBLIC_CORPUS_ZIP_SHA256,
    Stage7FailureKind,
)
from evaluation.phase56_stage7.corpus_integrity import (
    ArchiveEntryEvidence,
    CorpusIntegrityError,
    FORBIDDEN_ARCHIVE_MEMBERS,
    PRIVATE_MANIFEST_MEMBER,
    SafeArchiveInventory,
    read_public_corpus_archive,
)
from evaluation.phase56_stage7.corpus_records import (
    CorpusRecordError,
    PublicCorpusCaseV1,
    parse_public_jsonl,
    parse_schema_document,
)
from evaluation.phase56_stage7.corpus_semantics import (
    CorpusSemanticError,
    CorpusSemanticEvidence,
    assert_private_manifest_is_keys_only,
    verify_corpus_semantics,
    verify_manifest,
    verify_validation_report,
)
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.preflight import PreflightCallLedger, PreflightTerminal


CORPUS_PREFLIGHT_VERSION = "phase56-stage7-corpus-preflight-v1"

# Corpus integrity must be reachable without importing any executing subsystem.
_CORPUS_MODULE_NAMES: tuple[str, ...] = (
    "corpus_integrity.py",
    "corpus_records.py",
    "corpus_semantics.py",
    "corpus_preflight.py",
)
_FORBIDDEN_CORPUS_IMPORT_ROOTS: frozenset[str] = frozenset(
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
        "asyncio",
    }
)
_FORBIDDEN_EXTRACTION_CALLS: frozenset[str] = frozenset({"extract", "extractall"})


@dataclass(frozen=True, slots=True)
class Stage7CorpusPreflightResult:
    terminal: PreflightTerminal
    ledger: PreflightCallLedger
    version: str = CORPUS_PREFLIGHT_VERSION
    failure_kind: Stage7FailureKind | None = None
    sanitized_reason: str | None = None
    archive_sha256: str | None = None
    entry_evidence: tuple[ArchiveEntryEvidence, ...] = ()
    semantic_evidence: CorpusSemanticEvidence | None = None

    @property
    def passed(self) -> bool:
        return self.terminal is PreflightTerminal.passed


def _failure(
    reason: str, failure_kind: Stage7FailureKind
) -> Stage7CorpusPreflightResult:
    bounded = " ".join(reason.split())[:160] or "corpus integrity failure"
    return Stage7CorpusPreflightResult(
        terminal=PreflightTerminal.harness_contract_failure,
        ledger=PreflightCallLedger(),
        failure_kind=failure_kind,
        sanitized_reason=bounded,
    )


def load_public_cases(
    inventory: SafeArchiveInventory,
) -> tuple[tuple[PublicCorpusCaseV1, ...], tuple[PublicCorpusCaseV1, ...]]:
    declared_schema = parse_schema_document(inventory.members["schema.json"])
    public_dev = parse_public_jsonl(
        inventory.members["public_dev.jsonl"],
        split=PublicSplit.public_dev,
        declared_schema=declared_schema,
    )
    public_adversarial = parse_public_jsonl(
        inventory.members["public_adversarial.jsonl"],
        split=PublicSplit.public_adversarial,
        declared_schema=declared_schema,
    )
    return public_dev, public_adversarial


def run_corpus_integrity_preflight(
    archive_path: Path,
    *,
    expected_sha256: str = PUBLIC_CORPUS_ZIP_SHA256,
) -> Stage7CorpusPreflightResult:
    """Run the full archive + schema + semantic corpus gate with zero execution."""

    ledger = PreflightCallLedger()
    try:
        inventory = read_public_corpus_archive(
            archive_path, expected_sha256=expected_sha256
        )
        public_dev, public_adversarial = load_public_cases(inventory)
        semantic_evidence = verify_corpus_semantics(
            public_dev=public_dev, public_adversarial=public_adversarial
        )

        entry_sha_by_name = {
            entry.name: entry.sha256 for entry in inventory.entries
        }
        split_counts = {
            PublicSplit.public_dev.value: len(public_dev),
            PublicSplit.public_adversarial.value: len(public_adversarial),
            "public_dev.jsonl": len(public_dev),
            "public_adversarial.jsonl": len(public_adversarial),
        }
        manifest = inventory.members.get("manifest.json")
        if manifest is not None:
            verify_manifest(
                manifest,
                entry_sha256_by_name=entry_sha_by_name,
                split_counts=split_counts,
                forbidden_member_names=FORBIDDEN_ARCHIVE_MEMBERS,
            )
        report = inventory.members.get("validation_report.json")
        if report is not None:
            verify_validation_report(report)
        if inventory.private_manifest_bytes is not None:
            assert_private_manifest_is_keys_only(inventory.private_manifest_bytes)
    except CorpusIntegrityError as exc:
        return _failure(exc.sanitized_reason, exc.failure_kind)
    except CorpusRecordError as exc:
        return _failure(exc.sanitized_reason, exc.failure_kind)
    except CorpusSemanticError as exc:
        return _failure(exc.sanitized_reason, exc.failure_kind)
    except Exception as exc:  # fail closed; only the exception type is reported
        return _failure(type(exc).__name__, Stage7FailureKind.harness_failure)

    return Stage7CorpusPreflightResult(
        terminal=PreflightTerminal.passed,
        ledger=ledger,
        archive_sha256=inventory.archive_sha256,
        entry_evidence=inventory.entries,
        semantic_evidence=semantic_evidence,
    )


def assert_corpus_modules_are_execution_free(repository_root: Path) -> None:
    """Prove corpus integrity cannot reach runtime, provider, or network code.

    The check is structural: the corpus modules may not import an executing
    subsystem and may not call ZIP extraction, so no integrity path can start a
    solve or materialise an archive member on disk.
    """

    package_root = repository_root / "backend/evaluation/phase56_stage7"
    for module_name in _CORPUS_MODULE_NAMES:
        path = package_root / module_name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in _FORBIDDEN_CORPUS_IMPORT_ROOTS:
                        raise ValueError(
                            f"corpus integrity module imports executing subsystem: "
                            f"{module_name}:{root}"
                        )
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in _FORBIDDEN_CORPUS_IMPORT_ROOTS:
                    raise ValueError(
                        f"corpus integrity module imports executing subsystem: "
                        f"{module_name}:{root}"
                    )
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in _FORBIDDEN_EXTRACTION_CALLS:
                    raise ValueError(
                        f"corpus integrity module extracts archive members to disk: "
                        f"{module_name}"
                    )


def assert_raw_corpus_is_not_committed(repository_root: Path) -> None:
    """Reject any raw corpus archive or unauthorised split inside the worktree."""

    forbidden_names = (
        "dynatutor_beer12_ko_corpus_v1_public.zip",
        "dynatutor_beer12_ko_corpus_v1_full.zip",
        "DO_NOT_SHARE_WITH_CODEX_private_heldout.jsonl",
        "all_cases.jsonl",
        "public_all.jsonl",
        PRIVATE_MANIFEST_MEMBER,
    )
    for path in repository_root.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        if path.name in forbidden_names:
            raise ValueError(f"raw corpus material is committed: {path.name}")
