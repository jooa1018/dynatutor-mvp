from __future__ import annotations

import hashlib
import json
import math
import re
from enum import Enum
from typing import Annotated, Any, Literal, Mapping

from pydantic import Field, StringConstraints, field_validator, model_validator

from evaluation.phase56_stage7.contracts import (
    FrozenStrictModel,
    STAGE7_RUNTIME_INPUT_SCHEMA,
    STAGE7_RUNTIME_INPUT_VERSION,
    STAGE7_RUNTIME_SNAPSHOT_SCHEMA,
    STAGE7_RUNTIME_SNAPSHOT_VERSION,
    Sha256,
    Stage7RuntimeTerminal,
)


OpaqueExecutionToken = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{32}$"),
]
ProblemText = Annotated[str, StringConstraints(min_length=1, max_length=50_000)]
BoundedDiagnostic = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]

# Normalization catches snake_case, camelCase, kebab-case, and spaced aliases.
_FORBIDDEN_NORMALIZED_KEYS = frozenset(
    {
        "caseid",
        "problemid",
        "split",
        "family",
        "corpusfamily",
        "expectedsystemtype",
        "systemtype",
        "expectedterminal",
        "gold",
        "goldgraph",
        "goldentities",
        "goldfacts",
        "goldrelations",
        "expectedanswer",
        "referenceanswer",
        "answertolerance",
        "tolerance",
        "chapter",
        "section",
        "tags",
        "difficulty",
        "failurelabel",
        "failurekind",
        "referenceexpression",
        "answer",
        "finalanswer",
        "selectedanswer",
        "solverresult",
        "selectedsolver",
        "selectedroot",
        "verificationresult",
        "grading",
        "filename",
        "filepath",
    }
)
_FORBIDDEN_VALUE_TOKENS = (
    "private_heldout",
    "do_not_share_with_codex",
    "dynatutor_beer12_ko_corpus_v1_full",
)
_MAX_TYPED_DEPTH = 32
_MAX_TYPED_NODES = 20_000
_MAX_STRING_LENGTH = 100_000
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_IMAGES = 4


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _validate_runtime_payload(value: Any) -> Any:
    node_count = 0

    def walk(node: Any, *, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > _MAX_TYPED_NODES:
            raise ValueError("typed runtime payload exceeds node limit")
        if depth > _MAX_TYPED_DEPTH:
            raise ValueError("typed runtime payload exceeds depth limit")
        if node is None or isinstance(node, (bool, int)):
            return
        if isinstance(node, float):
            if not math.isfinite(node):
                raise ValueError("typed runtime payload contains non-finite number")
            return
        if isinstance(node, str):
            if len(node) > _MAX_STRING_LENGTH:
                raise ValueError("typed runtime payload string exceeds length limit")
            folded = node.casefold()
            if any(token in folded for token in _FORBIDDEN_VALUE_TOKENS):
                raise ValueError("typed runtime payload references forbidden private input")
            return
        if isinstance(node, Mapping):
            for raw_key, child in node.items():
                if not isinstance(raw_key, str):
                    raise ValueError("typed runtime payload keys must be strings")
                normalized = _normalize_key(raw_key)
                if normalized in _FORBIDDEN_NORMALIZED_KEYS:
                    raise ValueError(
                        f"typed runtime payload contains forbidden metadata key: {raw_key}"
                    )
                walk(child, depth=depth + 1)
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child, depth=depth + 1)
            return
        raise ValueError("typed runtime payload must contain JSON-compatible values only")

    walk(value, depth=0)
    return value


def canonical_runtime_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class RuntimeInputKind(str, Enum):
    problem_text = "problem_text"
    validated_typed_input = "validated_typed_input"
    multimodal = "multimodal"


class RuntimeEvaluationMode(str, Enum):
    required = "required"
    auto = "auto"
    confirm = "confirm"
    text_compatibility = "text_compatibility"


class RuntimeOptionsV1(FrozenStrictModel):
    mechanics_mode: RuntimeEvaluationMode
    allow_fake_provider: bool = False
    allow_recorded_provider: bool = False
    maximum_repair_attempts: Annotated[int, Field(ge=0, le=1)] = 0

    @model_validator(mode="after")
    def validate_provider_options(self) -> "RuntimeOptionsV1":
        if self.allow_fake_provider and self.allow_recorded_provider:
            raise ValueError("fake and recorded provider modes are mutually exclusive")
        if not (self.allow_fake_provider or self.allow_recorded_provider):
            if self.maximum_repair_attempts != 0:
                raise ValueError("repair attempts require an offline fake/recorded provider")
        return self


class RuntimeImageInputV1(FrozenStrictModel):
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    content_sha256: Sha256
    image_bytes: bytes = Field(min_length=1, max_length=_MAX_IMAGE_BYTES)

    @model_validator(mode="after")
    def validate_digest(self) -> "RuntimeImageInputV1":
        actual = hashlib.sha256(self.image_bytes).hexdigest()
        if actual != self.content_sha256:
            raise ValueError("runtime image digest mismatch")
        return self


class RuntimeTypedInputV1(FrozenStrictModel):
    kind: Literal["mechanics_problem_draft_v1"] = "mechanics_problem_draft_v1"
    payload_sha256: Sha256
    payload: dict[str, Any]

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_runtime_payload(value)
        return value

    @model_validator(mode="after")
    def validate_payload_digest(self) -> "RuntimeTypedInputV1":
        actual = hashlib.sha256(canonical_runtime_json(self.payload)).hexdigest()
        if actual != self.payload_sha256:
            raise ValueError("typed runtime payload digest mismatch")
        return self


class RuntimeDomainInputV1(FrozenStrictModel):
    schema: Literal["dynatutor.phase56_stage7.runtime_input"] = (
        STAGE7_RUNTIME_INPUT_SCHEMA
    )
    version: Literal["1.0"] = STAGE7_RUNTIME_INPUT_VERSION
    execution_token: OpaqueExecutionToken
    input_kind: RuntimeInputKind
    problem_text: ProblemText | None = None
    typed_input: RuntimeTypedInputV1 | None = None
    images: tuple[RuntimeImageInputV1, ...] = Field(default=(), max_length=_MAX_IMAGES)
    options: RuntimeOptionsV1

    @model_validator(mode="after")
    def validate_input_shape(self) -> "RuntimeDomainInputV1":
        has_text = self.problem_text is not None
        has_typed = self.typed_input is not None
        has_images = bool(self.images)
        if self.input_kind is RuntimeInputKind.problem_text:
            if not has_text or has_typed or has_images:
                raise ValueError("problem_text input requires text only")
        elif self.input_kind is RuntimeInputKind.validated_typed_input:
            if has_text or not has_typed or has_images:
                raise ValueError("validated_typed_input requires one typed payload only")
        elif self.input_kind is RuntimeInputKind.multimodal:
            if not has_text or has_typed or not has_images:
                raise ValueError("multimodal input requires text and at least one image")
        return self

    def cache_material(self) -> bytes:
        """Return calculation cache material with the opaque token excluded.

        The token is transport correlation only.  It must not make case metadata,
        scorer metadata, or execution ordering part of runtime calculation identity.
        """

        payload = self.model_dump(mode="json", exclude={"execution_token"})
        return canonical_runtime_json(payload)

    def cache_sha256(self) -> str:
        return hashlib.sha256(self.cache_material()).hexdigest()


class RuntimeAnswerV1(FrozenStrictModel):
    value: float = Field(allow_inf_nan=False)
    unit: Annotated[str, StringConstraints(min_length=1, max_length=48)]
    direction: Annotated[str, StringConstraints(min_length=1, max_length=96)] | None = None


class RuntimeGraphProjectionV1(FrozenStrictModel):
    """Bounded semantic actual-output projection used only by the scorer.

    This projection contains runtime-produced semantics, never expected/gold data.
    Role tuples deliberately avoid model-chosen ID spelling and preserve multiset
    cardinality by retaining repeated tuple entries.
    """

    entity_roles: tuple[str, ...] = Field(default=(), max_length=256)
    segment_roles: tuple[str, ...] = Field(default=(), max_length=256)
    event_roles: tuple[str, ...] = Field(default=(), max_length=256)
    explicit_fact_roles: tuple[str, ...] = Field(default=(), max_length=1024)
    relation_roles: tuple[str, ...] = Field(default=(), max_length=1024)
    query_roles: tuple[str, ...] = Field(default=(), max_length=64)
    assumption_roles: tuple[str, ...] = Field(default=(), max_length=128)


class RuntimeDomainSnapshotV1(FrozenStrictModel):
    schema: Literal["dynatutor.phase56_stage7.runtime_snapshot"] = (
        STAGE7_RUNTIME_SNAPSHOT_SCHEMA
    )
    version: Literal["1.0"] = STAGE7_RUNTIME_SNAPSHOT_VERSION
    evaluator_version: Literal["phase56-stage7-evaluator-v1"] = (
        "phase56-stage7-evaluator-v1"
    )
    execution_token: OpaqueExecutionToken
    input_cache_sha256: Sha256
    terminal: Stage7RuntimeTerminal
    answer: RuntimeAnswerV1 | None = None
    graph_projection: RuntimeGraphProjectionV1 = Field(
        default_factory=RuntimeGraphProjectionV1
    )
    calculation_fingerprint: Sha256 | None = None
    equation_graph_fingerprint: Sha256 | None = None
    solve_plan_fingerprint: Sha256 | None = None
    candidate_set_fingerprint: Sha256 | None = None
    verification_fingerprint: Sha256 | None = None
    candidate_count: int = Field(ge=0, le=10_000)
    verified_candidate_count: int = Field(ge=0, le=10_000)
    diagnostics: tuple[BoundedDiagnostic, ...] = Field(default=(), max_length=128)
    runtime_call_count: int = Field(ge=0, le=10_000)
    compiler_call_count: int = Field(ge=0, le=10_000)
    solver_call_count: int = Field(ge=0, le=10_000)
    model_or_provider_call_count: int = Field(ge=0, le=2)

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> "RuntimeDomainSnapshotV1":
        if self.terminal is Stage7RuntimeTerminal.solved:
            if self.answer is None or self.verified_candidate_count != 1:
                raise ValueError("solved snapshot requires one verified answer")
        elif self.answer is not None:
            raise ValueError("non-solved snapshot cannot carry an answer")
        if self.verified_candidate_count > self.candidate_count:
            raise ValueError("verified candidate count exceeds candidate count")
        return self


def build_typed_runtime_input(
    *,
    execution_token: str,
    payload: dict[str, Any],
    options: RuntimeOptionsV1,
) -> RuntimeDomainInputV1:
    payload_sha256 = hashlib.sha256(canonical_runtime_json(payload)).hexdigest()
    return RuntimeDomainInputV1(
        execution_token=execution_token,
        input_kind=RuntimeInputKind.validated_typed_input,
        typed_input=RuntimeTypedInputV1(
            payload_sha256=payload_sha256,
            payload=payload,
        ),
        options=options,
    )
