"""Stage 7 public corpus schema binding and normalised record parsing.

Records are bound to the corpus's own frozen `dynatutor-ko-corpus-v1.0` schema.
The binding is cross-checked against the archive's `schema.json` on every run:
if the corpus ever renames or drops a required field, parsing fails closed
instead of silently binding the wrong column.

Nothing here reaches the runtime domain.  Normalised records stay in the gold /
scoring domain.  `reference_expression` is retained verbatim for provenance and
is **never** evaluated.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from evaluation.phase56_stage7.contracts import Sha256, Stage7FailureKind
from evaluation.phase56_stage7.gold_domain import PublicSplit


RECORD_BINDING_VERSION = "phase56-stage7-public-record-binding-v2"
CORPUS_SCHEMA_VERSION = "dynatutor-ko-corpus-v1.0"

_PRIVATE_SPLIT_LABEL = "private_heldout"
_MAX_RECORDS_PER_SPLIT = 512
_MAX_JSONL_LINE_CHARS = 200_000

REQUIRED_CASE_FIELDS: tuple[str, ...] = (
    "schema_version",
    "case_id",
    "split",
    "language",
    "problem_text",
    "problem_hash",
    "source_provenance",
    "gold",
    "difficulty",
    "tags",
)
REQUIRED_GOLD_FIELDS: tuple[str, ...] = (
    "parse_status",
    "expected_system_type",
    "phase55_expected_terminal",
    "future_expected_terminal",
    "figure_dependency",
    "entities",
    "motion_segments",
    "events",
    "explicit_facts",
    "relations",
    "assumption_proposals",
    "queries",
    "answers",
)


class CorpusRecordReason(str, Enum):
    """Closed, privacy-safe corpus-schema rejection catalogue."""

    invalid_json = "invalid_json"
    record_not_object = "record_not_object"
    blank_jsonl_line = "blank_jsonl_line"
    jsonl_line_too_long = "jsonl_line_too_long"
    record_limit_exceeded = "record_limit_exceeded"
    schema_declaration_unrecognized = "schema_declaration_unrecognized"
    schema_version_mismatch = "schema_version_mismatch"
    undeclared_bound_field = "undeclared_bound_field"
    missing_required_field = "missing_required_field"
    missing_required_gold_field = "missing_required_gold_field"
    invalid_field_type = "invalid_field_type"
    non_finite_number = "non_finite_number"
    private_split_in_public_file = "private_split_in_public_file"
    unknown_split_label = "unknown_split_label"
    split_file_mismatch = "split_file_mismatch"
    non_korean_language = "non_korean_language"


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
            # ``field`` is always an evaluator-declared name, never corpus text.
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


class CorpusModel(BaseModel):
    """Frozen gold-domain record model.

    Unlike the runtime contracts this is not ``strict``: the corpus stores some
    numeric answers as JSON integers, and rejecting an integral answer would be
    a harness defect rather than a corpus defect.  Unknown keys are still
    forbidden so a silent schema drift cannot pass unnoticed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


Role = Annotated[str, StringConstraints(min_length=1, max_length=128)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=512)]
ProblemText = Annotated[str, StringConstraints(min_length=10, max_length=50_000)]
# A dimensionless corpus quantity carries an empty unit string; that is a real
# unit value, not a missing field, so it is preserved rather than rejected.
UnitText = Annotated[str, StringConstraints(max_length=64)]


class CorpusEntityV1(CorpusModel):
    role: Role
    kind: ShortText
    label: ShortText | None = None


class CorpusSegmentV1(CorpusModel):
    role: Role
    order: int
    actor_roles: tuple[Role, ...] = ()
    motion_model: ShortText | None = None
    relevance: ShortText | None = None
    start_event_role: Role | None = None
    end_event_role: Role | None = None


class CorpusEventV1(CorpusModel):
    role: Role
    kind: ShortText
    subject_roles: tuple[Role, ...] = ()
    segment_role: Role | None = None
    evidence_quote: ShortText | None = None


class CorpusFactV1(CorpusModel):
    role: Role
    semantic_key: ShortText
    raw_value: ShortText
    raw_unit: UnitText | None = None
    evidence_quote: ShortText | None = None
    subject_role: Role | None = None
    segment_role: Role | None = None
    event_role: Role | None = None
    temporal_role: ShortText | None = None
    direction: ShortText | None = None
    relevance: ShortText | None = None
    occurrence_index: int = 0
    quantity_occurrence_index: int = 0

    @property
    def numeric_value(self) -> float | None:
        try:
            value = float(self.raw_value.replace(",", ""))
        except ValueError:
            return None
        return value if math.isfinite(value) else None


class CorpusRelationV1(CorpusModel):
    role: Role
    kind: ShortText
    participant_roles: tuple[Role, ...] = ()
    segment_role: Role | None = None


class CorpusAssumptionV1(CorpusModel):
    role: Role
    kind: ShortText
    subject_role: Role | None = None
    segment_role: Role | None = None
    supporting_quote: ShortText | None = None
    server_value_only: bool = False


class CorpusQueryV1(CorpusModel):
    role: Role
    output_key: ShortText
    subject_role: Role | None = None
    segment_role: Role | None = None
    component: ShortText | None = None
    event_role: Role | None = None


class CorpusAnswerV1(CorpusModel):
    query_role: Role
    numeric: float
    unit: ShortText | None = None
    tolerance_abs: float = 0.0
    reference_expression: ShortText | None = None
    sign_convention: ShortText | None = None


class CorpusFigureDependencyV1(CorpusModel):
    level: ShortText
    missing_information: tuple[ShortText, ...] = ()


class CorpusGoldV1(CorpusModel):
    parse_status: ShortText
    expected_system_type: ShortText | None = None
    phase55_expected_terminal: ShortText
    future_expected_terminal: ShortText
    figure_dependency: CorpusFigureDependencyV1
    entities: tuple[CorpusEntityV1, ...] = Field(default=(), max_length=256)
    motion_segments: tuple[CorpusSegmentV1, ...] = Field(default=(), max_length=256)
    events: tuple[CorpusEventV1, ...] = Field(default=(), max_length=256)
    explicit_facts: tuple[CorpusFactV1, ...] = Field(default=(), max_length=1024)
    relations: tuple[CorpusRelationV1, ...] = Field(default=(), max_length=1024)
    assumption_proposals: tuple[CorpusAssumptionV1, ...] = Field(
        default=(), max_length=256
    )
    queries: tuple[CorpusQueryV1, ...] = Field(default=(), max_length=64)
    answers: tuple[CorpusAnswerV1, ...] = Field(default=(), max_length=64)
    expected_failure_codes: tuple[ShortText, ...] = ()


class CorpusProvenanceV1(BaseModel):
    """Provenance is declared ``additionalProperties: true`` by the corpus."""

    model_config = ConfigDict(extra="allow", frozen=True)

    basis: ShortText
    title: ShortText
    edition: int
    chapter: int
    section: ShortText
    independently_authored: bool
    original_problem_text_copied: bool
    original_numbers_reused: bool
    original_figures_reused: bool


class PublicCorpusCaseV1(CorpusModel):
    """Normalised, gold-domain-only view of one public corpus case."""

    binding_version: str = RECORD_BINDING_VERSION
    schema_version: ShortText
    case_id: Role
    split: PublicSplit
    language: ShortText
    problem_text: ProblemText
    problem_hash: Sha256
    source_provenance: CorpusProvenanceV1
    gold: CorpusGoldV1
    family: Role | None = None
    difficulty: int = 1
    tags: tuple[ShortText, ...] = ()
    notes: tuple[ShortText, ...] = ()

    @property
    def chapter(self) -> int:
        return self.source_provenance.chapter

    @property
    def reference_answers(self) -> tuple[CorpusAnswerV1, ...]:
        return self.gold.answers


@dataclass(frozen=True, slots=True)
class DeclaredSchema:
    version: str
    case_fields: frozenset[str]
    gold_fields: frozenset[str]


def _object_property_names(node: Any) -> frozenset[str]:
    if isinstance(node, Mapping):
        properties = node.get("properties")
        if isinstance(properties, Mapping) and properties:
            return frozenset(str(key) for key in properties)
    return frozenset()


def parse_schema_document(schema_bytes: bytes) -> DeclaredSchema:
    """Read the archive's own schema declaration and confirm the binding fits."""

    try:
        document = json.loads(schema_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorpusRecordError(CorpusRecordReason.invalid_json) from exc
    if not isinstance(document, Mapping):
        raise CorpusRecordError(CorpusRecordReason.schema_declaration_unrecognized)

    case_fields = _object_property_names(document)
    if not case_fields:
        raise CorpusRecordError(CorpusRecordReason.schema_declaration_unrecognized)
    gold_fields = _object_property_names(document["properties"].get("gold"))
    if not gold_fields:
        raise CorpusRecordError(CorpusRecordReason.schema_declaration_unrecognized)

    declared_version = document["properties"].get("schema_version", {})
    version = (
        declared_version.get("const")
        if isinstance(declared_version, Mapping)
        else None
    )
    if version != CORPUS_SCHEMA_VERSION:
        raise CorpusRecordError(CorpusRecordReason.schema_version_mismatch)

    missing_case = set(REQUIRED_CASE_FIELDS) - case_fields
    if missing_case:
        raise CorpusRecordError(
            CorpusRecordReason.undeclared_bound_field,
            field=sorted(missing_case)[0],
        )
    missing_gold = set(REQUIRED_GOLD_FIELDS) - gold_fields
    if missing_gold:
        raise CorpusRecordError(
            CorpusRecordReason.undeclared_bound_field,
            field=sorted(missing_gold)[0],
        )
    return DeclaredSchema(
        version=version, case_fields=case_fields, gold_fields=gold_fields
    )


def _assert_finite_numbers(node: Any, index: int, depth: int = 0) -> None:
    """JSON accepts NaN/Infinity by default; a non-finite corpus number fails."""

    if depth > 32:
        raise CorpusRecordError(
            CorpusRecordReason.invalid_field_type, record_index=index
        )
    if isinstance(node, bool):
        return
    if isinstance(node, float) and not math.isfinite(node):
        raise CorpusRecordError(
            CorpusRecordReason.non_finite_number, record_index=index
        )
    if isinstance(node, Mapping):
        for child in node.values():
            _assert_finite_numbers(child, index, depth + 1)
    elif isinstance(node, (list, tuple)):
        for child in node:
            _assert_finite_numbers(child, index, depth + 1)


def _coerce_split(value: Any, expected: PublicSplit, index: int) -> PublicSplit:
    if not isinstance(value, str):
        raise CorpusRecordError(
            CorpusRecordReason.invalid_field_type, field="split", record_index=index
        )
    normalized = value.strip().casefold().replace("-", "_")
    if normalized == _PRIVATE_SPLIT_LABEL:
        raise CorpusRecordError(
            CorpusRecordReason.private_split_in_public_file, record_index=index
        )
    for split in PublicSplit:
        if normalized == split.value:
            if split is not expected:
                raise CorpusRecordError(
                    CorpusRecordReason.split_file_mismatch, record_index=index
                )
            return split
    raise CorpusRecordError(CorpusRecordReason.unknown_split_label, record_index=index)


def parse_public_jsonl(
    payload: bytes,
    *,
    split: PublicSplit,
    declared_schema: DeclaredSchema,
) -> tuple[PublicCorpusCaseV1, ...]:
    """Parse one authorised public split into normalised gold-domain cases."""

    lines = payload.decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) > _MAX_RECORDS_PER_SPLIT:
        raise CorpusRecordError(CorpusRecordReason.record_limit_exceeded)

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
        _assert_finite_numbers(record, index)

        for field in REQUIRED_CASE_FIELDS:
            if field not in record:
                raise CorpusRecordError(
                    CorpusRecordReason.missing_required_field,
                    field=field,
                    record_index=index,
                )
        gold = record["gold"]
        if not isinstance(gold, Mapping):
            raise CorpusRecordError(
                CorpusRecordReason.invalid_field_type, field="gold", record_index=index
            )
        for field in REQUIRED_GOLD_FIELDS:
            if field not in gold:
                raise CorpusRecordError(
                    CorpusRecordReason.missing_required_gold_field,
                    field=field,
                    record_index=index,
                )
        if record["schema_version"] != declared_schema.version:
            raise CorpusRecordError(
                CorpusRecordReason.schema_version_mismatch, record_index=index
            )
        if record["language"] != "ko":
            raise CorpusRecordError(
                CorpusRecordReason.non_korean_language, record_index=index
            )

        payload_fields = dict(record)
        payload_fields["split"] = _coerce_split(record["split"], split, index)
        try:
            cases.append(PublicCorpusCaseV1(**payload_fields))
        except ValidationError as exc:
            raise CorpusRecordError(
                CorpusRecordReason.invalid_field_type, record_index=index
            ) from exc
    return tuple(cases)


def normalized_problem_key(problem_text: str) -> str:
    return re.sub(r"\s+", " ", problem_text).strip()
