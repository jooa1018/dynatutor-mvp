from __future__ import annotations

import hashlib
from collections import Counter
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from evaluation.phase56_stage7.contracts import (
    FrozenStrictModel,
    STAGE7_GOLD_CASE_SCHEMA,
    STAGE7_GOLD_CASE_VERSION,
    Sha256,
    Stage7ExpectedTerminal,
    Stage7FailureKind,
    Stage7HardSafetySignal,
    Stage7Metric,
    Stage7RuntimeTerminal,
)
from evaluation.phase56_stage7.runtime_domain import (
    RuntimeDomainInputV1,
    RuntimeDomainSnapshotV1,
)


CaseId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
]
Family = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    ),
]


class PublicSplit(str, Enum):
    public_dev = "public_dev"
    public_adversarial = "public_adversarial"


class GoldNumericAnswerV1(FrozenStrictModel):
    value: float = Field(allow_inf_nan=False)
    unit: Annotated[str, StringConstraints(min_length=1, max_length=48)]
    absolute_tolerance: float = Field(allow_inf_nan=False, ge=0.0, le=1.0e12)
    relative_tolerance: float = Field(allow_inf_nan=False, ge=0.0, le=1.0)
    direction: Annotated[str, StringConstraints(min_length=1, max_length=96)] | None = None


class GoldGraphProjectionV1(FrozenStrictModel):
    entity_roles: tuple[str, ...] = Field(default=(), max_length=256)
    segment_roles: tuple[str, ...] = Field(default=(), max_length=256)
    event_roles: tuple[str, ...] = Field(default=(), max_length=256)
    explicit_fact_roles: tuple[str, ...] = Field(default=(), max_length=1024)
    relation_roles: tuple[str, ...] = Field(default=(), max_length=1024)
    query_roles: tuple[str, ...] = Field(default=(), max_length=64)
    assumption_roles: tuple[str, ...] = Field(default=(), max_length=128)


class GoldDomainCaseV1(FrozenStrictModel):
    schema: Literal["dynatutor.phase56_stage7.gold_case"] = STAGE7_GOLD_CASE_SCHEMA
    version: Literal["1.0"] = STAGE7_GOLD_CASE_VERSION
    case_id: CaseId
    split: PublicSplit
    family: Family
    problem_sha256: Sha256
    expected_terminal: Stage7ExpectedTerminal
    expected_answer: GoldNumericAnswerV1 | None = None
    gold_graph: GoldGraphProjectionV1 = Field(default_factory=GoldGraphProjectionV1)
    expected_hard_safety_signals: tuple[Stage7HardSafetySignal, ...] = ()

    @model_validator(mode="after")
    def validate_expected_shape(self) -> "GoldDomainCaseV1":
        if self.expected_terminal is Stage7ExpectedTerminal.accepted:
            if self.expected_answer is None:
                raise ValueError("accepted gold case requires a finite expected answer")
        elif self.expected_answer is not None:
            raise ValueError("non-accepted gold case cannot carry an expected answer")
        if self.expected_hard_safety_signals:
            raise ValueError("gold contract expects zero hard-safety signals")
        return self


class FrozenRuntimeResultV1(FrozenStrictModel):
    """Scorer-only binding created after the runtime snapshot is immutable."""

    runtime_input_sha256: Sha256
    snapshot: RuntimeDomainSnapshotV1

    @classmethod
    def from_runtime(
        cls,
        runtime_input: RuntimeDomainInputV1,
        snapshot: RuntimeDomainSnapshotV1,
    ) -> "FrozenRuntimeResultV1":
        if snapshot.execution_token != runtime_input.execution_token:
            raise ValueError("runtime snapshot token does not match input token")
        if snapshot.input_cache_sha256 != runtime_input.cache_sha256():
            raise ValueError("runtime snapshot cache identity mismatch")
        runtime_input_sha256 = hashlib.sha256(runtime_input.cache_material()).hexdigest()
        return cls(runtime_input_sha256=runtime_input_sha256, snapshot=snapshot)


class Stage7CaseScoreV1(FrozenStrictModel):
    privacy_safe_case_sha256: Sha256
    expected_terminal: Stage7ExpectedTerminal
    actual_terminal: Stage7RuntimeTerminal
    terminal_match: bool
    answer_match: bool | None = None
    metric_values: dict[Stage7Metric, float] = Field(default_factory=dict)
    hard_safety_counts: dict[Stage7HardSafetySignal, int] = Field(default_factory=dict)
    failure_kind: Stage7FailureKind | None = None
    bounded_mismatch_signature: Annotated[
        str, StringConstraints(max_length=240)
    ] | None = None

    @model_validator(mode="after")
    def validate_hard_safety(self) -> "Stage7CaseScoreV1":
        if any(count < 0 for count in self.hard_safety_counts.values()):
            raise ValueError("hard-safety counts cannot be negative")
        if set(self.metric_values) - set(Stage7Metric):
            raise ValueError("unknown metric")
        for value in self.metric_values.values():
            if not 0.0 <= value <= 1.0:
                raise ValueError("metric values must be fractions")
        return self


def role_counter(values: tuple[str, ...]) -> Counter[str]:
    """Return a multiset projection; repeated equal facts remain distinct."""

    return Counter(values)
