"""Stage 7 public corpus semantic integrity and scope-adjusted terminal counts.

Every check here runs in the gold / scoring domain before any runtime execution.
The scope-adjusted terminal distribution is *derived* from the corpus plus the
frozen current-course scope and then compared with the frozen contract; it is
never produced by branching on an individual case ID or family route.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from evaluation.phase56_stage7.contracts import (
    Stage7ExpectedTerminal,
    Stage7FailureKind,
    stage7_evaluation_contract,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit


SEMANTIC_POLICY_VERSION = "phase56-stage7-corpus-semantics-v1"

_HANGUL_PATTERN = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")
_NUMBER_PATTERN = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")
_WHITESPACE_PATTERN = re.compile(r"\s+")

_VALUE_RELATIVE_TOLERANCE = 1.0e-9
_VALUE_ABSOLUTE_TOLERANCE = 1.0e-12

_MAX_PRIVATE_MANIFEST_STRING_CHARS = 256
_PRIVATE_MANIFEST_FORBIDDEN_KEYS = frozenset(
    {
        "problemtext",
        "problem",
        "text",
        "question",
        "answer",
        "answers",
        "referenceanswer",
        "expectedanswer",
        "finalanswer",
        "solution",
        "gold",
        "goldgraph",
        "evidence",
        "evidencequotes",
        "quotes",
        "facts",
        "explicitfacts",
    }
)

_TERMINAL_LABEL_ALIASES: dict[str, Stage7ExpectedTerminal] = {
    "accepted": Stage7ExpectedTerminal.accepted,
    "solved": Stage7ExpectedTerminal.accepted,
    "supported": Stage7ExpectedTerminal.accepted,
    "answerable": Stage7ExpectedTerminal.accepted,
    "unsupported": Stage7ExpectedTerminal.unsupported_other,
    "unsupportedother": Stage7ExpectedTerminal.unsupported_other,
    "verifiedunsupported": Stage7ExpectedTerminal.unsupported_other,
    "outofscope": Stage7ExpectedTerminal.unsupported_other,
    "deferred": Stage7ExpectedTerminal.deferred_unsupported,
    "deferredunsupported": Stage7ExpectedTerminal.deferred_unsupported,
    "needsfigure": Stage7ExpectedTerminal.needs_figure,
    "requiresfigure": Stage7ExpectedTerminal.needs_figure,
    "figurerequired": Stage7ExpectedTerminal.needs_figure,
    "needsconfirmation": Stage7ExpectedTerminal.needs_confirmation,
    "needsclarification": Stage7ExpectedTerminal.needs_confirmation,
    "ambiguous": Stage7ExpectedTerminal.needs_confirmation,
    "insufficientinformation": Stage7ExpectedTerminal.insufficient_information,
    "insufficientconditions": Stage7ExpectedTerminal.insufficient_information,
    "insufficient": Stage7ExpectedTerminal.insufficient_information,
}


class CorpusSemanticReason(str, Enum):
    """Closed, privacy-safe semantic rejection catalogue."""

    split_count_mismatch = "split_count_mismatch"
    total_count_mismatch = "total_count_mismatch"
    duplicate_case_id = "duplicate_case_id"
    duplicate_problem_text = "duplicate_problem_text"
    problem_hash_mismatch = "problem_hash_mismatch"
    splits_not_disjoint = "splits_not_disjoint"
    problem_text_not_korean = "problem_text_not_korean"
    evidence_quote_absent_from_problem = "evidence_quote_absent_from_problem"
    fact_value_absent_from_evidence = "fact_value_absent_from_evidence"
    non_finite_reference_answer = "non_finite_reference_answer"
    missing_reference_answer_for_accepted = "missing_reference_answer_for_accepted"
    unexpected_reference_answer_for_blocked = "unexpected_reference_answer_for_blocked"
    unknown_terminal_label = "unknown_terminal_label"
    unclassifiable_case = "unclassifiable_case"
    scope_terminal_count_mismatch = "scope_terminal_count_mismatch"
    manifest_declaration_unrecognized = "manifest_declaration_unrecognized"
    manifest_count_mismatch = "manifest_count_mismatch"
    manifest_hash_mismatch = "manifest_hash_mismatch"
    validation_report_unrecognized = "validation_report_unrecognized"
    validation_report_not_passing = "validation_report_not_passing"
    private_manifest_invalid_json = "private_manifest_invalid_json"
    private_manifest_carries_content = "private_manifest_carries_content"


class CorpusSemanticError(Exception):
    """Fail-closed semantic rejection carrying no corpus content."""

    def __init__(
        self,
        reason: CorpusSemanticReason,
        *,
        case_index: int | None = None,
        failure_kind: Stage7FailureKind = Stage7FailureKind.corpus_reference_issue,
    ) -> None:
        detail = reason.value
        if case_index is not None:
            detail = f"{detail}[case:{case_index}]"
        super().__init__(detail)
        self.reason = reason
        self.case_index = case_index
        self.failure_kind = failure_kind

    @property
    def sanitized_reason(self) -> str:
        return str(self)


@dataclass(frozen=True, slots=True)
class ScopeAdjustedDistribution:
    supported_accepted: int
    deferred_unsupported: int
    unsupported_other: int
    needs_figure: int
    needs_confirmation: int
    insufficient_information: int

    @property
    def total(self) -> int:
        return (
            self.supported_accepted
            + self.deferred_unsupported
            + self.unsupported_other
            + self.needs_figure
            + self.needs_confirmation
            + self.insufficient_information
        )


@dataclass(frozen=True, slots=True)
class CorpusSemanticEvidence:
    policy_version: str
    public_dev_count: int
    public_adversarial_count: int
    distribution: ScopeAdjustedDistribution
    deferred_family_counts: tuple[tuple[str, int], ...]


def _normalize_whitespace(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", unicodedata.normalize("NFC", value)).strip()


def _problem_hash_candidates(problem_text: str) -> frozenset[str]:
    variants = {
        problem_text,
        problem_text.strip(),
        unicodedata.normalize("NFC", problem_text),
        unicodedata.normalize("NFC", problem_text).strip(),
        _normalize_whitespace(problem_text),
    }
    return frozenset(
        hashlib.sha256(variant.encode("utf-8")).hexdigest() for variant in variants
    )


def _numbers_in(text: str) -> tuple[float, ...]:
    numbers: list[float] = []
    for match in _NUMBER_PATTERN.finditer(text):
        try:
            numbers.append(float(match.group().replace(",", "")))
        except ValueError:  # pragma: no cover - regex already constrains the token
            continue
    return tuple(numbers)


def _value_is_present(value: float, candidates: Iterable[float]) -> bool:
    return any(
        math.isclose(
            value,
            candidate,
            rel_tol=_VALUE_RELATIVE_TOLERANCE,
            abs_tol=_VALUE_ABSOLUTE_TOLERANCE,
        )
        for candidate in candidates
    )


def scope_adjusted_expected_terminal(
    case: PublicCorpusCaseV1, *, case_index: int
) -> Stage7ExpectedTerminal:
    """Map one case to its current-scope expected terminal.

    Current Phase 56 course scope takes precedence over any older terminal the
    corpus declares.  The only scope input is the frozen deferred-family set;
    no case ID, filename, split, or chapter participates.
    """

    contract = stage7_evaluation_contract()
    if case.family in contract.course_scope.deferred_families:
        return Stage7ExpectedTerminal.deferred_unsupported

    if case.declared_terminal is not None:
        key = re.sub(r"[^a-z0-9]", "", case.declared_terminal.casefold())
        terminal = _TERMINAL_LABEL_ALIASES.get(key)
        if terminal is None:
            raise CorpusSemanticError(
                CorpusSemanticReason.unknown_terminal_label, case_index=case_index
            )
        if terminal is Stage7ExpectedTerminal.deferred_unsupported:
            # A corpus-declared "deferred" outside the frozen four families is
            # not a current-scope deferral; it is a plain unsupported case.
            return Stage7ExpectedTerminal.unsupported_other
        return terminal

    if case.reference_answer is not None:
        return Stage7ExpectedTerminal.accepted
    raise CorpusSemanticError(
        CorpusSemanticReason.unclassifiable_case, case_index=case_index
    )


def _verify_case(case: PublicCorpusCaseV1, index: int) -> Stage7ExpectedTerminal:
    if not _HANGUL_PATTERN.search(case.problem_text):
        raise CorpusSemanticError(
            CorpusSemanticReason.problem_text_not_korean, case_index=index
        )
    if case.problem_sha256 not in _problem_hash_candidates(case.problem_text):
        raise CorpusSemanticError(
            CorpusSemanticReason.problem_hash_mismatch, case_index=index
        )

    normalized_problem = _normalize_whitespace(case.problem_text)
    for quote in case.evidence_quotes:
        if _normalize_whitespace(quote) not in normalized_problem:
            raise CorpusSemanticError(
                CorpusSemanticReason.evidence_quote_absent_from_problem,
                case_index=index,
            )

    quote_numbers: list[float] = []
    for quote in case.evidence_quotes:
        quote_numbers.extend(_numbers_in(quote))
    for fact in case.facts:
        if fact.value is None:
            continue
        if not math.isfinite(fact.value):
            raise CorpusSemanticError(
                CorpusSemanticReason.non_finite_reference_answer, case_index=index
            )
        if not _value_is_present(fact.value, quote_numbers):
            raise CorpusSemanticError(
                CorpusSemanticReason.fact_value_absent_from_evidence, case_index=index
            )

    terminal = scope_adjusted_expected_terminal(case, case_index=index)
    if terminal is Stage7ExpectedTerminal.accepted:
        if case.reference_answer is None:
            raise CorpusSemanticError(
                CorpusSemanticReason.missing_reference_answer_for_accepted,
                case_index=index,
            )
        if not math.isfinite(case.reference_answer.value):
            raise CorpusSemanticError(
                CorpusSemanticReason.non_finite_reference_answer, case_index=index
            )
    elif terminal is not Stage7ExpectedTerminal.deferred_unsupported:
        # A deferred case may still carry the corpus reference answer it was
        # authored with; current scope withdraws answer authority without
        # rewriting the corpus.  Every other blocked class must carry none.
        if case.reference_answer is not None:
            raise CorpusSemanticError(
                CorpusSemanticReason.unexpected_reference_answer_for_blocked,
                case_index=index,
            )
    return terminal


def verify_corpus_semantics(
    *,
    public_dev: tuple[PublicCorpusCaseV1, ...],
    public_adversarial: tuple[PublicCorpusCaseV1, ...],
) -> CorpusSemanticEvidence:
    """Verify semantic integrity and the derived scope-adjusted distribution."""

    contract = stage7_evaluation_contract()
    if len(public_dev) != contract.split_counts.public_dev:
        raise CorpusSemanticError(CorpusSemanticReason.split_count_mismatch)
    if len(public_adversarial) != contract.split_counts.public_adversarial:
        raise CorpusSemanticError(CorpusSemanticReason.split_count_mismatch)
    if len(public_dev) + len(public_adversarial) != contract.split_counts.total:
        raise CorpusSemanticError(CorpusSemanticReason.total_count_mismatch)

    dev_ids = {case.case_id for case in public_dev}
    adversarial_ids = {case.case_id for case in public_adversarial}
    if dev_ids & adversarial_ids:
        raise CorpusSemanticError(CorpusSemanticReason.splits_not_disjoint)

    all_cases = public_dev + public_adversarial
    if len({case.case_id for case in all_cases}) != len(all_cases):
        raise CorpusSemanticError(CorpusSemanticReason.duplicate_case_id)
    normalized_texts = [_normalize_whitespace(case.problem_text) for case in all_cases]
    if len(set(normalized_texts)) != len(normalized_texts):
        raise CorpusSemanticError(CorpusSemanticReason.duplicate_problem_text)

    terminals: Counter[Stage7ExpectedTerminal] = Counter()
    deferred_families: Counter[str] = Counter()
    for index, case in enumerate(all_cases):
        terminal = _verify_case(case, index)
        terminals[terminal] += 1
        if terminal is Stage7ExpectedTerminal.deferred_unsupported:
            deferred_families[case.family] += 1

    distribution = ScopeAdjustedDistribution(
        supported_accepted=terminals[Stage7ExpectedTerminal.accepted],
        deferred_unsupported=terminals[Stage7ExpectedTerminal.deferred_unsupported],
        unsupported_other=terminals[Stage7ExpectedTerminal.unsupported_other],
        needs_figure=terminals[Stage7ExpectedTerminal.needs_figure],
        needs_confirmation=terminals[Stage7ExpectedTerminal.needs_confirmation],
        insufficient_information=terminals[
            Stage7ExpectedTerminal.insufficient_information
        ],
    )
    expected = contract.expected_terminals
    if (
        distribution.supported_accepted != expected.supported_accepted
        or distribution.deferred_unsupported != expected.deferred_unsupported
        or distribution.unsupported_other != expected.unsupported_other
        or distribution.needs_figure != expected.needs_figure
        or distribution.needs_confirmation != expected.needs_confirmation
        or distribution.insufficient_information != expected.insufficient_information
        or distribution.total != expected.total
    ):
        raise CorpusSemanticError(CorpusSemanticReason.scope_terminal_count_mismatch)

    return CorpusSemanticEvidence(
        policy_version=SEMANTIC_POLICY_VERSION,
        public_dev_count=len(public_dev),
        public_adversarial_count=len(public_adversarial),
        distribution=distribution,
        deferred_family_counts=tuple(sorted(deferred_families.items())),
    )


def verify_manifest(
    manifest_bytes: bytes,
    *,
    entry_sha256_by_name: Mapping[str, str],
    split_counts: Mapping[str, int],
) -> None:
    """Cross-check a corpus-supplied manifest against observed evidence."""

    try:
        document = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorpusSemanticError(
            CorpusSemanticReason.manifest_declaration_unrecognized
        ) from exc
    if not isinstance(document, Mapping):
        raise CorpusSemanticError(CorpusSemanticReason.manifest_declaration_unrecognized)

    checked = 0
    for name, expected_sha in _declared_hashes(document).items():
        actual = entry_sha256_by_name.get(name)
        if actual is None:
            raise CorpusSemanticError(CorpusSemanticReason.manifest_hash_mismatch)
        if actual.casefold() != expected_sha.casefold():
            raise CorpusSemanticError(CorpusSemanticReason.manifest_hash_mismatch)
        checked += 1
    for name, expected_count in _declared_counts(document).items():
        actual_count = split_counts.get(name)
        if actual_count is None or actual_count != expected_count:
            raise CorpusSemanticError(CorpusSemanticReason.manifest_count_mismatch)
        checked += 1
    if checked == 0:
        raise CorpusSemanticError(CorpusSemanticReason.manifest_declaration_unrecognized)


def _declared_hashes(document: Mapping[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for container_key in ("files", "sha256", "hashes", "entries"):
        container = document.get(container_key)
        if isinstance(container, Mapping):
            for name, value in container.items():
                if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value):
                    hashes[str(name)] = value
                elif isinstance(value, Mapping):
                    nested = value.get("sha256") or value.get("hash")
                    if isinstance(nested, str) and re.fullmatch(
                        r"[0-9a-fA-F]{64}", nested
                    ):
                        hashes[str(name)] = nested
        elif isinstance(container, (list, tuple)):
            for item in container:
                if not isinstance(item, Mapping):
                    continue
                name = item.get("name") or item.get("path") or item.get("file")
                digest = item.get("sha256") or item.get("hash")
                if isinstance(name, str) and isinstance(digest, str):
                    if re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                        hashes[name] = digest
    return hashes


def _declared_counts(document: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for container_key in ("counts", "split_counts", "splits"):
        container = document.get(container_key)
        if isinstance(container, Mapping):
            for name, value in container.items():
                if isinstance(value, int) and not isinstance(value, bool):
                    counts[str(name)] = value
                elif isinstance(value, Mapping):
                    nested = value.get("count")
                    if isinstance(nested, int) and not isinstance(nested, bool):
                        counts[str(name)] = nested
    for split in PublicSplit:
        value = document.get(f"{split.value}_count")
        if isinstance(value, int) and not isinstance(value, bool):
            counts[split.value] = value
    return counts


def verify_validation_report(report_bytes: bytes) -> None:
    """Require a corpus-supplied validation report to declare a passing result."""

    try:
        document = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorpusSemanticError(
            CorpusSemanticReason.validation_report_unrecognized
        ) from exc
    if not isinstance(document, Mapping):
        raise CorpusSemanticError(CorpusSemanticReason.validation_report_unrecognized)

    for key in ("status", "result", "overall_status", "outcome"):
        value = document.get(key)
        if isinstance(value, str):
            if re.sub(r"[^a-z]", "", value.casefold()) in ("pass", "passed", "ok", "valid"):
                return
            raise CorpusSemanticError(
                CorpusSemanticReason.validation_report_not_passing
            )
    for key in ("passed", "ok", "valid", "is_valid"):
        value = document.get(key)
        if isinstance(value, bool):
            if value:
                return
            raise CorpusSemanticError(
                CorpusSemanticReason.validation_report_not_passing
            )
    errors = document.get("errors")
    if isinstance(errors, (list, tuple)):
        if errors:
            raise CorpusSemanticError(
                CorpusSemanticReason.validation_report_not_passing
            )
        return
    raise CorpusSemanticError(CorpusSemanticReason.validation_report_unrecognized)


def assert_private_manifest_is_keys_only(manifest_bytes: bytes) -> None:
    """Keys-only absence audit for an optional private-without-text manifest.

    The manifest is never parsed into evaluation state; only the absence of raw
    text, quotes, gold structure, and reference answers is confirmed, after
    which it is quarantined.
    """

    try:
        document = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorpusSemanticError(
            CorpusSemanticReason.private_manifest_invalid_json
        ) from exc

    def walk(node: Any, depth: int) -> None:
        if depth > 16:
            raise CorpusSemanticError(
                CorpusSemanticReason.private_manifest_carries_content
            )
        if isinstance(node, Mapping):
            for key, child in node.items():
                folded = re.sub(r"[^a-z0-9]", "", str(key).casefold())
                if folded in _PRIVATE_MANIFEST_FORBIDDEN_KEYS:
                    raise CorpusSemanticError(
                        CorpusSemanticReason.private_manifest_carries_content
                    )
                walk(child, depth + 1)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child, depth + 1)
        elif isinstance(node, str):
            if len(node) > _MAX_PRIVATE_MANIFEST_STRING_CHARS:
                raise CorpusSemanticError(
                    CorpusSemanticReason.private_manifest_carries_content
                )
            if _HANGUL_PATTERN.search(node):
                raise CorpusSemanticError(
                    CorpusSemanticReason.private_manifest_carries_content
                )

    walk(document, 0)
