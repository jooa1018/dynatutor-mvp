"""Stage 7 public corpus schema binding and normalised record parsing.

The corpus is an external artifact whose exact key spelling is not part of this
repository.  Rather than guessing a single key name, each normalised field
declares an ordered alias set that must resolve *unambiguously* and *identically*
for every record, and every resolved alias must also be declared by the
archive's own ``schema.json``.  Any drift, ambiguity, or undeclared key fails
closed instead of silently binding the wrong column.

Nothing here reaches the runtime domain: normalised records stay in the gold /
scoring domain and are consumed only by the scorer and the integrity checks.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from pydantic import Field, StringConstraints, ValidationError
from typing import Annotated

from evaluation.phase56_stage7.contracts import (
    FrozenStrictModel,
    Sha256,
    Stage7FailureKind,
)
from evaluation.phase56_stage7.gold_domain import PublicSplit


RECORD_BINDING_VERSION = "phase56-stage7-public-record-binding-v1"

_PRIVATE_KEY_MARKERS: tuple[str, ...] = (
    "private",
    "heldout",
    "held_out",
    "donotshare",
    "do_not_share",
)
_MAX_RECORDS_PER_SPLIT = 512
_MAX_JSONL_LINE_CHARS = 200_000


class CorpusRecordReason(str, Enum):
    """Closed, privacy-safe corpus-schema rejection catalogue."""

    invalid_json = "invalid_json"
    record_not_object = "record_not_object"
    blank_jsonl_line = "blank_jsonl_line"
    jsonl_line_too_long = "jsonl_line_too_long"
    record_limit_exceeded = "record_limit_exceeded"
    schema_declaration_unrecognized = "schema_declaration_unrecognized"
    undeclared_bound_field = "undeclared_bound_field"
    missing_required_field = "missing_required_field"
    ambiguous_field_binding = "ambiguous_field_binding"
    inconsistent_field_binding = "inconsistent_field_binding"
    invalid_field_type = "invalid_field_type"
    private_marker_in_public_record = "private_marker_in_public_record"
    private_manifest_not_keys_only = "private_manifest_not_keys_only"
    unknown_split_label = "unknown_split_label"


class CorpusRecordError(Exception):
    """Fail-closed schema rejection carrying no corpus content."""

    def __init__(
        self,
        reason: CorpusRecordReason,
        *,
        field: str | None = None,
        record_index: int | None = None,
        failure_kind: Stage7FailureKind = Stage7FailureKind.corpus_integrity_failure,
    ) -> None:
        detail = reason.value
        if field is not None:
            # ``field`` is always an evaluator-declared normalised field name,
            # never a corpus-supplied string.
            detail = f"{detail}[field:{field}]"
        if record_index is not None:
            detail = f"{detail}[record:{record_index}]"
        super().__init__(detail)
        self.reason = reason
        self.field = field
        self.record_index = record_index
        self.failure_kind = failure_kind

    @property
    def sanitized_reason(self) -> str:
        return str(self)


@dataclass(frozen=True, slots=True)
class FieldBinding:
    normalized_field: str
    aliases: tuple[str, ...]
    required: bool


PUBLIC_CASE_FIELD_BINDINGS: tuple[FieldBinding, ...] = (
    FieldBinding("case_id", ("case_id", "id", "caseId"), True),
    FieldBinding("split", ("split", "public_split", "subset"), True),
    FieldBinding("family", ("family", "corpus_family", "category"), True),
    FieldBinding("problem_text", ("problem_text", "problem", "question", "text"), True),
    FieldBinding(
        "problem_sha256",
        ("problem_sha256", "problem_hash", "text_sha256", "problem_text_sha256"),
        True,
    ),
    FieldBinding(
        "evidence_quotes",
        ("evidence_quotes", "evidence", "source_quotes", "quotes"),
        True,
    ),
    FieldBinding("facts", ("facts", "explicit_facts", "given_facts"), True),
    FieldBinding(
        "reference_answer",
        ("reference_answer", "answer", "expected_answer", "final_answer"),
        False,
    ),
    FieldBinding(
        "declared_terminal",
        ("expected_terminal", "terminal", "future_expected_terminal", "outcome"),
        False,
    ),
    FieldBinding("chapter", ("chapter", "section", "unit_chapter"), False),
)

_FACT_VALUE_ALIASES: tuple[str, ...] = ("value", "quantity", "magnitude", "number")
_FACT_UNIT_ALIASES: tuple[str, ...] = ("unit", "units", "unit_symbol")
_FACT_ROLE_ALIASES: tuple[str, ...] = (
    "semantic_role",
    "role",
    "key",
    "name",
    "semantic_key",
)
_ANSWER_VALUE_ALIASES: tuple[str, ...] = ("value", "magnitude", "number", "answer")
_ANSWER_UNIT_ALIASES: tuple[str, ...] = ("unit", "units", "unit_symbol")

BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=50_000)]
BoundedToken = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class CorpusFactV1(FrozenStrictModel):
    role: BoundedToken
    value: float | None = Field(default=None, allow_inf_nan=False)
    unit: Annotated[str, StringConstraints(min_length=1, max_length=48)] | None = None


class CorpusReferenceAnswerV1(FrozenStrictModel):
    value: float = Field(allow_inf_nan=False)
    unit: Annotated[str, StringConstraints(min_length=1, max_length=48)] | None = None


class PublicCorpusCaseV1(FrozenStrictModel):
    """Normalised, gold-domain-only view of one public corpus case."""

    binding_version: str = RECORD_BINDING_VERSION
    case_id: BoundedToken
    split: PublicSplit
    family: BoundedToken
    problem_text: BoundedText
    problem_sha256: Sha256
    evidence_quotes: tuple[BoundedText, ...] = Field(max_length=64)
    facts: tuple[CorpusFactV1, ...] = Field(default=(), max_length=128)
    reference_answer: CorpusReferenceAnswerV1 | None = None
    declared_terminal: BoundedToken | None = None
    chapter: BoundedToken | None = None


def _declared_schema_field_names(schema_document: Any) -> frozenset[str]:
    """Extract declared field names from the archive's own schema document."""

    if not isinstance(schema_document, Mapping):
        raise CorpusRecordError(CorpusRecordReason.schema_declaration_unrecognized)
    properties = schema_document.get("properties")
    if isinstance(properties, Mapping) and properties:
        return frozenset(str(key) for key in properties)
    fields = schema_document.get("fields")
    if isinstance(fields, (list, tuple)) and fields:
        names: set[str] = set()
        for entry in fields:
            if isinstance(entry, str):
                names.add(entry)
            elif isinstance(entry, Mapping) and isinstance(entry.get("name"), str):
                names.add(str(entry["name"]))
        if names:
            return frozenset(names)
    raise CorpusRecordError(CorpusRecordReason.schema_declaration_unrecognized)


def parse_schema_document(schema_bytes: bytes) -> frozenset[str]:
    try:
        document = json.loads(schema_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorpusRecordError(CorpusRecordReason.invalid_json) from exc
    return _declared_schema_field_names(document)


def _assert_no_private_markers(record: Mapping[str, Any], index: int) -> None:
    for key in record:
        folded = re.sub(r"[^a-z0-9]", "", str(key).casefold())
        if any(marker.replace("_", "") in folded for marker in _PRIVATE_KEY_MARKERS):
            raise CorpusRecordError(
                CorpusRecordReason.private_marker_in_public_record,
                record_index=index,
            )


def _resolve_alias(
    record: Mapping[str, Any], binding: FieldBinding, index: int
) -> str | None:
    present = [alias for alias in binding.aliases if alias in record]
    if len(present) > 1:
        raise CorpusRecordError(
            CorpusRecordReason.ambiguous_field_binding,
            field=binding.normalized_field,
            record_index=index,
        )
    if not present:
        if binding.required:
            raise CorpusRecordError(
                CorpusRecordReason.missing_required_field,
                field=binding.normalized_field,
                record_index=index,
            )
        return None
    return present[0]


def _require_str(value: Any, *, field: str, index: int) -> str:
    """Require a genuine string; stringifying ``None`` would fabricate a value."""

    if not isinstance(value, str):
        raise CorpusRecordError(
            CorpusRecordReason.invalid_field_type, field=field, record_index=index
        )
    return value


def _pick(mapping: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in mapping:
            return mapping[alias]
    return None


def _coerce_quotes(value: Any, index: int) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        quotes: list[str] = []
        for item in value:
            if isinstance(item, str):
                quotes.append(item)
            elif isinstance(item, Mapping):
                text = _pick(item, ("quote", "text", "span", "source_text"))
                if not isinstance(text, str):
                    raise CorpusRecordError(
                        CorpusRecordReason.invalid_field_type,
                        field="evidence_quotes",
                        record_index=index,
                    )
                quotes.append(text)
            else:
                raise CorpusRecordError(
                    CorpusRecordReason.invalid_field_type,
                    field="evidence_quotes",
                    record_index=index,
                )
        return tuple(quotes)
    raise CorpusRecordError(
        CorpusRecordReason.invalid_field_type,
        field="evidence_quotes",
        record_index=index,
    )


def _coerce_number(value: Any, *, field: str, index: int) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            # JSON accepts NaN/Infinity by default; a non-finite corpus number
            # must fail closed rather than silently degrade to "absent".
            raise CorpusRecordError(
                CorpusRecordReason.invalid_field_type, field=field, record_index=index
            )
        return number
    return None


def _coerce_facts(value: Any, index: int) -> tuple[CorpusFactV1, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise CorpusRecordError(
            CorpusRecordReason.invalid_field_type, field="facts", record_index=index
        )
    facts: list[CorpusFactV1] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise CorpusRecordError(
                CorpusRecordReason.invalid_field_type, field="facts", record_index=index
            )
        role = _pick(item, _FACT_ROLE_ALIASES)
        if not isinstance(role, str) or not role:
            raise CorpusRecordError(
                CorpusRecordReason.invalid_field_type, field="facts", record_index=index
            )
        unit = _pick(item, _FACT_UNIT_ALIASES)
        try:
            facts.append(
                CorpusFactV1(
                    role=role,
                    value=_coerce_number(
                        _pick(item, _FACT_VALUE_ALIASES), field="facts", index=index
                    ),
                    unit=unit if isinstance(unit, str) and unit else None,
                )
            )
        except ValidationError as exc:
            raise CorpusRecordError(
                CorpusRecordReason.invalid_field_type, field="facts", record_index=index
            ) from exc
    return tuple(facts)


def _coerce_reference_answer(value: Any, index: int) -> CorpusReferenceAnswerV1 | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = _coerce_number(value, field="reference_answer", index=index)
        if number is None:
            raise CorpusRecordError(
                CorpusRecordReason.invalid_field_type,
                field="reference_answer",
                record_index=index,
            )
        return CorpusReferenceAnswerV1(value=number)
    if isinstance(value, Mapping):
        number = _coerce_number(
            _pick(value, _ANSWER_VALUE_ALIASES), field="reference_answer", index=index
        )
        if number is None:
            # A structured answer without a finite numeric value describes a
            # non-numeric outcome; it is not a reference answer.
            return None
        unit = _pick(value, _ANSWER_UNIT_ALIASES)
        return CorpusReferenceAnswerV1(
            value=number, unit=unit if isinstance(unit, str) and unit else None
        )
    if isinstance(value, str):
        return None
    raise CorpusRecordError(
        CorpusRecordReason.invalid_field_type,
        field="reference_answer",
        record_index=index,
    )


def _coerce_split(value: Any, expected: PublicSplit, index: int) -> PublicSplit:
    if not isinstance(value, str):
        raise CorpusRecordError(
            CorpusRecordReason.invalid_field_type, field="split", record_index=index
        )
    normalized = value.strip().casefold().replace("-", "_")
    for split in PublicSplit:
        if normalized == split.value:
            if split is not expected:
                raise CorpusRecordError(
                    CorpusRecordReason.unknown_split_label, record_index=index
                )
            return split
    raise CorpusRecordError(CorpusRecordReason.unknown_split_label, record_index=index)


def parse_public_jsonl(
    payload: bytes,
    *,
    split: PublicSplit,
    declared_schema_fields: frozenset[str],
) -> tuple[PublicCorpusCaseV1, ...]:
    """Parse one authorised public split into normalised gold-domain cases."""

    text = payload.decode("utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) > _MAX_RECORDS_PER_SPLIT:
        raise CorpusRecordError(CorpusRecordReason.record_limit_exceeded)

    resolved_binding: dict[str, str | None] = {}
    cases: list[PublicCorpusCaseV1] = []

    for index, line in enumerate(lines):
        if len(line) > _MAX_JSONL_LINE_CHARS:
            raise CorpusRecordError(
                CorpusRecordReason.jsonl_line_too_long, record_index=index
            )
        if not line.strip():
            raise CorpusRecordError(
                CorpusRecordReason.blank_jsonl_line, record_index=index
            )
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CorpusRecordError(
                CorpusRecordReason.invalid_json, record_index=index
            ) from exc
        if not isinstance(record, Mapping):
            raise CorpusRecordError(
                CorpusRecordReason.record_not_object, record_index=index
            )
        _assert_no_private_markers(record, index)

        values: dict[str, Any] = {}
        for binding in PUBLIC_CASE_FIELD_BINDINGS:
            alias = _resolve_alias(record, binding, index)
            if alias is not None:
                # Optional fields legitimately appear on only some records, so
                # consistency is enforced across the records that carry them.
                previous = resolved_binding.get(binding.normalized_field)
                if previous is not None and previous != alias:
                    raise CorpusRecordError(
                        CorpusRecordReason.inconsistent_field_binding,
                        field=binding.normalized_field,
                        record_index=index,
                    )
                resolved_binding[binding.normalized_field] = alias
                if alias not in declared_schema_fields:
                    raise CorpusRecordError(
                        CorpusRecordReason.undeclared_bound_field,
                        field=binding.normalized_field,
                        record_index=index,
                    )
            values[binding.normalized_field] = (
                record[alias] if alias is not None else None
            )

        declared_terminal = values["declared_terminal"]
        chapter = values["chapter"]
        try:
            case = PublicCorpusCaseV1(
                case_id=_require_str(values["case_id"], field="case_id", index=index),
                split=_coerce_split(values["split"], split, index),
                family=_require_str(values["family"], field="family", index=index),
                problem_text=_require_str(
                    values["problem_text"], field="problem_text", index=index
                ),
                problem_sha256=_require_str(
                    values["problem_sha256"], field="problem_sha256", index=index
                )
                .strip()
                .casefold(),
                evidence_quotes=_coerce_quotes(values["evidence_quotes"], index),
                facts=_coerce_facts(values["facts"], index),
                reference_answer=_coerce_reference_answer(
                    values["reference_answer"], index
                ),
                declared_terminal=str(declared_terminal)
                if isinstance(declared_terminal, str) and declared_terminal
                else None,
                chapter=str(chapter) if isinstance(chapter, str) and chapter else None,
            )
        except ValidationError as exc:
            raise CorpusRecordError(
                CorpusRecordReason.invalid_field_type, record_index=index
            ) from exc
        cases.append(case)

    return tuple(cases)
