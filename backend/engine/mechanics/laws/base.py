from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from engine.mechanics.contracts import (
    AssumptionDisposition,
    IREntity,
    IREvent,
    IRGeometryRelation,
    IRInteraction,
    IRMotionInterval,
    IRPoint,
    IRReferenceFrame,
    IRAssumption,
    IRStateCondition,
    QuantityComponent,
    QuantityRole,
    QuantityShape,
)
from engine.mechanics.math_ast import DimensionVector, MathExpression, SymbolDefinition


class LawRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    law_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$", max_length=64)
    category: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$", max_length=64)
    required_roles: tuple[QuantityRole, ...] = Field(default_factory=tuple, max_length=16)
    required_interactions: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    approved_assumption_kinds: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    generated_roles: tuple[QuantityRole, ...] = Field(default_factory=tuple, max_length=8)
    complexity_cost: int = Field(default=10, ge=0, le=10_000)
    verification_hooks: tuple[str, ...] = Field(default_factory=tuple, max_length=16)


@dataclass(frozen=True)
class BoundQuantity:
    quantity_id: str | None
    symbol_id: str | None
    role: QuantityRole
    subject_id: str
    point_id: str | None
    frame_id: str | None
    interval_id: str | None
    event_id: str | None
    component: QuantityComponent
    shape: QuantityShape
    dimension: DimensionVector
    expression: MathExpression
    evidence_ids: tuple[str, ...]
    known_si_value: object | None = None
    direction_sign: int = 1
    direction_bound: bool = False
    # Canonical direction identity with the scalar sign removed.  The sign is
    # applied by ``_signed``; the identity prevents a scalar x balance from
    # silently consuming a y/tangential/normal quantity.
    direction_key: str | None = None
    generated: bool = False

    @property
    def stable_key(self) -> tuple[object, ...]:
        return (
            self.role.value,
            self.subject_id,
            self.point_id or "",
            self.frame_id or "",
            self.interval_id or "",
            self.event_id or "",
            self.component.value,
            self.direction_key or "",
            self.shape.value,
            self.quantity_id or "",
            self.symbol_id or "",
        )


@dataclass(frozen=True)
class LawContext:
    quantities: tuple[BoundQuantity, ...]
    entities: tuple[IREntity, ...]
    points: tuple[IRPoint, ...]
    reference_frames: tuple[IRReferenceFrame, ...]
    motion_intervals: tuple[IRMotionInterval, ...]
    events: tuple[IREvent, ...]
    geometry: tuple[IRGeometryRelation, ...]
    interactions: tuple[IRInteraction, ...]
    state_conditions: tuple[IRStateCondition, ...]
    assumptions: tuple[IRAssumption, ...]
    approved_assumption_ids: frozenset[str]
    symbols: tuple[SymbolDefinition, ...]
    hinted_principles: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.approved_assumption_ids) is not frozenset:
            raise TypeError("approved assumption authority must be an exact immutable snapshot")

    def approved_assumptions(self, kind: str, subject_id: str, interval_id: str | None) -> tuple[str, ...]:
        return tuple(
            sorted(
                assumption.assumption_id
                for assumption in self.assumptions
                if assumption.disposition is AssumptionDisposition.approved
                and assumption.assumption_id in self.approved_assumption_ids
                and assumption.kind == kind
                and assumption.subject_id == subject_id
                and (assumption.interval_id is None or assumption.interval_id == interval_id)
            )
        )


@dataclass(frozen=True)
class InitialConditionBinding:
    target_symbol_id: str
    value_symbol_id: str
    wrt_symbol_id: str
    derivative_order: int
    subject_id: str
    point_id: str | None
    frame_id: str | None
    interval_id: str
    event_id: str
    source_quantity_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    source_state_condition_ids: tuple[str, ...]

    @property
    def stable_key(self) -> tuple[object, ...]:
        return (
            self.target_symbol_id,
            self.wrt_symbol_id,
            self.derivative_order,
            self.value_symbol_id,
            self.subject_id,
            self.point_id or "",
            self.frame_id or "",
            self.interval_id,
            self.event_id,
            self.source_quantity_ids,
            self.source_evidence_ids,
            self.source_state_condition_ids,
        )


@dataclass(frozen=True)
class LawEmission:
    rule: LawRule
    expression: MathExpression
    entity_ids: tuple[str, ...]
    point_ids: tuple[str, ...] = ()
    frame_id: str | None = None
    interval_id: str | None = None
    event_id: str | None = None
    event_ids: tuple[str, ...] = ()
    source_quantity_ids: tuple[str, ...] = ()
    source_evidence_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    constraint_ids: tuple[str, ...] = ()
    generated_unknown_symbol_ids: tuple[str, ...] = ()
    initial_conditions: tuple[InitialConditionBinding, ...] = ()
    hint_priority: bool = False

    @property
    def effective_cost(self) -> int:
        reduction = 1 if self.hint_priority else 0
        return max(0, self.rule.complexity_cost - reduction)


def emission_for(
    rule: LawRule,
    expression: MathExpression,
    quantities: tuple[BoundQuantity, ...],
    *,
    assumption_ids: tuple[str, ...] = (),
    constraint_ids: tuple[str, ...] = (),
    extra_entity_ids: tuple[str, ...] = (),
    initial_conditions: tuple[InitialConditionBinding, ...] = (),
    hint_priority: bool = False,
) -> LawEmission:
    entity_ids = tuple(sorted({q.subject_id for q in quantities} | set(extra_entity_ids)))
    point_ids = tuple(sorted({q.point_id for q in quantities if q.point_id is not None}))
    frame_ids = {q.frame_id for q in quantities if q.frame_id is not None}
    interval_ids = {q.interval_id for q in quantities if q.interval_id is not None}
    event_ids = {q.event_id for q in quantities if q.event_id is not None}
    if len(frame_ids) > 1:
        raise ValueError("law application cannot combine frames without an explicit transform")
    if len(interval_ids) > 1:
        raise ValueError("law application cannot combine motion intervals")
    source_ids = tuple(
        sorted(
            {q.quantity_id for q in quantities if q.quantity_id is not None}
            | {
                item
                for condition in initial_conditions
                for item in condition.source_quantity_ids
            }
        )
    )
    evidence_ids = tuple(
        sorted(
            {item for q in quantities for item in q.evidence_ids}
            | {
                item
                for condition in initial_conditions
                for item in condition.source_evidence_ids
            }
        )
    )
    generated_ids = tuple(sorted(q.symbol_id for q in quantities if q.generated and q.symbol_id is not None))
    return LawEmission(
        rule=rule,
        expression=expression,
        entity_ids=entity_ids,
        point_ids=point_ids,
        frame_id=next(iter(frame_ids)) if len(frame_ids) == 1 else None,
        interval_id=next(iter(interval_ids)) if len(interval_ids) == 1 else None,
        event_id=next(iter(event_ids)) if len(event_ids) == 1 else None,
        event_ids=tuple(sorted(event_ids)),
        source_quantity_ids=source_ids,
        source_evidence_ids=evidence_ids,
        assumption_ids=tuple(sorted(set(assumption_ids))),
        constraint_ids=tuple(sorted(set(constraint_ids))),
        generated_unknown_symbol_ids=generated_ids,
        initial_conditions=tuple(sorted(initial_conditions, key=lambda item: item.stable_key)),
        hint_priority=hint_priority,
    )


__all__ = [
    "BoundQuantity",
    "LawContext",
    "LawEmission",
    "LawRule",
    "InitialConditionBinding",
    "emission_for",
]
