from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import itertools
import json
import math
import re
from typing import Collection, Iterable, Mapping

from pydantic import BaseModel

from engine.mechanics.compiler.contracts import (
    COMPILER_POLICY_VERSION,
    LAW_LIBRARY_VERSION,
    CompilerIssue,
    CompilerIssueCode,
    CompilerIssueSeverity,
    CompilerLimits,
    CompilerResult,
    CompilerStatus,
    ConstraintNode,
    EquationGraph,
    EquationNode,
    EquationScope,
    InitialConditionNode,
    IncidenceEdge,
    LawApplication,
    RankAnalysis,
    RankMethod,
    SymbolNode,
    ValidatedIRAuthorization,
)
from engine.mechanics.contracts import (
    IR_SCHEMA_NAME,
    IR_SCHEMA_VERSION,
    AssumptionDisposition,
    ConstraintKind,
    EntityPrimitive,
    GeometryRelationKind,
    IRConstraint,
    IREntityOrigin,
    IRFigureEvidence,
    IRFrameOrigin,
    IRGeometryRelation,
    IRPointOrigin,
    IRQuery,
    IRQuantity,
    IRSourceAsset,
    IRStateCondition,
    IRTextEvidence,
    IRWorldOrigin,
    InteractionKind,
    MechanicsProblemIRV1,
    Provenance,
    QuantityComponent,
    QuantityRole,
    QuantityShape,
    ReferenceFrameType,
)
from engine.mechanics.laws import (
    BoundQuantity,
    InitialConditionBinding,
    LawContext,
    LawEmission,
    LawRule,
    apply_core_laws,
)
from engine.mechanics.math_ast import (
    Add,
    Cos,
    Cross,
    Derivative,
    DimensionVector,
    Divide,
    Dot,
    Equality,
    Inequality,
    Integral,
    LiteralNode,
    MathExpression,
    MathNode,
    Multiply,
    Negate,
    Norm,
    Piecewise,
    Power,
    Sin,
    Sqrt,
    Subtract,
    SymbolDefinition,
    SymbolRef,
    SymbolShape,
    Tan,
    VectorNode,
    validate_math_expressions,
)
from engine.mechanics.normalization import NORMALIZATION_POLICY_VERSION, VALIDATION_POLICY_VERSION
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import AssumptionAuthorization, CorrectionAuthorization


_EXPLICIT_CONSTRAINT_RULE = LawRule(
    law_id="explicit_constraint",
    category="constraint",
    complexity_cost=1,
    verification_hooks=("constraint_residual",),
)
_EXPLICIT_GEOMETRY_RULE = LawRule(
    law_id="explicit_geometry",
    category="constraint",
    complexity_cost=1,
    verification_hooks=("geometry_residual",),
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validated_ir_digest(ir: MechanicsProblemIRV1) -> str:
    return _digest(ir.model_dump(mode="json", warnings="none"))


def authorize_validated_mechanics_ir(ir: object) -> ValidatedIRAuthorization:
    """Build the caller-retained seal immediately after trusted validation."""

    if type(ir) is not MechanicsProblemIRV1:
        raise TypeError("validated IR authorization requires an exact mechanics IR v1")
    safe_ir = MechanicsProblemIRV1.model_validate(
        ir.model_dump(mode="python", warnings="none")
    )
    if (
        safe_ir.schema != IR_SCHEMA_NAME
        or safe_ir.version != IR_SCHEMA_VERSION
        or safe_ir.validation_policy_version != VALIDATION_POLICY_VERSION
        or safe_ir.normalization_policy_version != NORMALIZATION_POLICY_VERSION
    ):
        raise ValueError("validated IR authorization requires the active validation policies")
    return ValidatedIRAuthorization(ir_sha256=_validated_ir_digest(safe_ir))


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _issue(
    code: CompilerIssueCode,
    message: str,
    path: str,
    referenced_id: str | None = None,
    *,
    warning: bool = False,
) -> CompilerIssue:
    return CompilerIssue(
        code=code,
        severity=CompilerIssueSeverity.warning if warning else CompilerIssueSeverity.error,
        message=message,
        path=path,
        referenced_id=referenced_id,
    )


def _failure(status: CompilerStatus, *issues: CompilerIssue) -> CompilerResult:
    return CompilerResult(status=status, issues=tuple(issues))


def _expression_symbol_ids(expression: MathExpression | MathNode) -> tuple[str, ...]:
    found: set[str] = set()
    stack: list[object] = [expression]
    seen: set[int] = set()
    nodes = 0
    while stack:
        value = stack.pop()
        if isinstance(value, BaseModel):
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            nodes += 1
            if nodes > 4096:
                break
            if isinstance(value, SymbolRef):
                found.add(value.symbol_id)
            if isinstance(value, (Derivative, Integral)):
                found.add(value.wrt_symbol_id)
            for field_name in type(value).model_fields:
                stack.append(getattr(value, field_name))
        elif isinstance(value, tuple):
            stack.extend(reversed(value))
    return tuple(sorted(found))


def _ordinary_expression_symbol_ids(expression: MathExpression | MathNode) -> tuple[str, ...]:
    found: set[str] = set()
    stack: list[object] = [expression]
    seen: set[int] = set()
    while stack:
        value = stack.pop()
        if isinstance(value, BaseModel):
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            if isinstance(value, SymbolRef):
                found.add(value.symbol_id)
            for field_name in type(value).model_fields:
                if field_name == "wrt_symbol_id":
                    continue
                stack.append(getattr(value, field_name))
        elif isinstance(value, tuple):
            stack.extend(reversed(value))
    return tuple(sorted(found))


def _id_values(value: object, known: set[str], *, root_field: str = "") -> tuple[tuple[str, str], ...]:
    found: list[tuple[str, str]] = []
    stack: list[tuple[object, str]] = [(value, root_field)]
    visited: set[int] = set()
    steps = 0
    while stack:
        current, field_path = stack.pop()
        steps += 1
        if steps > 20_000:
            break
        if isinstance(current, BaseModel):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
            for field_name in type(current).model_fields:
                child = getattr(current, field_name)
                child_path = field_name if not field_path else f"{field_path}.{field_name}"
                if isinstance(child, str) and (
                    field_name.endswith("_id") or field_name in {"symbol_id", "wrt_symbol_id"}
                ):
                    if child in known:
                        found.append((child_path, child))
                    continue
                if isinstance(child, tuple) and (
                    field_name.endswith("_ids") or field_name.endswith("_refs")
                ):
                    for item in child:
                        if isinstance(item, str) and item in known:
                            found.append((child_path, item))
                    continue
                stack.append((child, child_path))
        elif isinstance(current, tuple):
            for item in current:
                stack.append((item, field_path))
    return tuple(found)


def _primary_records(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    *,
    include_source_records: bool = False,
) -> tuple[tuple[str, str, BaseModel], ...]:
    collections: tuple[tuple[str, Iterable[BaseModel], str], ...] = (
        ("entity", ir.entities, "entity_id"),
        ("point", ir.points, "point_id"),
        ("frame", ir.reference_frames, "frame_id"),
        ("interval", ir.motion_intervals, "interval_id"),
        ("event", ir.events, "event_id"),
        ("symbol", ir.symbols, "symbol_id"),
        ("quantity", ir.quantities, "quantity_id"),
        ("geometry", ir.geometry, "relation_id"),
        ("interaction", ir.interactions, "interaction_id"),
        ("constraint", ir.constraints, "constraint_id"),
        ("state", ir.state_conditions, "state_condition_id"),
        ("assumption", ir.assumptions, "assumption_id"),
    )
    if include_source_records:
        collections = (
            ("asset", ir.source_assets, "asset_id"),
            ("evidence", ir.source_evidence, "evidence_id"),
            *collections,
        )
    records: list[tuple[str, str, BaseModel]] = []
    for kind, values, field_name in collections:
        for value in values:
            records.append((kind, getattr(value, field_name), value))
    records.append(("query", query.query_id, query))
    return tuple(records)


def _graph_edges(
    records: tuple[tuple[str, str, BaseModel], ...]
) -> tuple[dict[str, tuple[str, BaseModel]], dict[str, tuple[tuple[str, str], ...]]]:
    record_map = {record_id: (kind, value) for kind, record_id, value in records}
    known = set(record_map)
    edges: dict[str, list[tuple[str, str]]] = {record_id: [] for record_id in known}
    for _, record_id, value in records:
        for label, referenced_id in _id_values(value, known):
            if referenced_id == record_id:
                continue
            edges[record_id].append((f"out:{label}", referenced_id))
            edges[referenced_id].append((f"in:{label}", record_id))
    return record_map, {
        record_id: tuple(sorted(set(neighbors))) for record_id, neighbors in edges.items()
    }


def _local_projection(value: object) -> object:
    if isinstance(value, IRSourceAsset):
        # Source records retain their exact IDs on emitted provenance, but raw
        # text/image locators and content are not calculation authority.  Their
        # canonical aliases are therefore derived from explicit provenance
        # graph edges only, matching calculation_fingerprint's exclusion of
        # source-record content while preserving provenance topology.
        return {"node": "source_asset"}
    if isinstance(value, (IRTextEvidence, IRFigureEvidence)):
        return {"node": "source_evidence"}
    if isinstance(value, BaseModel):
        projected: dict[str, object] = {"node": type(value).__name__}
        for field_name in type(value).model_fields:
            if (
                field_name.endswith("_id")
                or field_name.endswith("_ids")
                or field_name.endswith("_refs")
                or field_name
                in {
                    "label",
                    "aliases",
                    "model_confidence",
                    "description",
                    "reason",
                    "raw_value",
                    "raw_unit",
                    "si_unit",
                }
            ):
                continue
            projected[field_name] = _local_projection(getattr(value, field_name))
        return projected
    if isinstance(value, tuple):
        return tuple(_local_projection(item) for item in value)
    if isinstance(value, float):
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


class _CanonicalIds:
    def __init__(
        self,
        records: tuple[tuple[str, str, BaseModel], ...],
        edges: Mapping[str, tuple[tuple[str, str], ...]],
    ) -> None:
        kinds = {record_id: kind for kind, record_id, _ in records}
        values = {record_id: value for _, record_id, value in records}
        colors = {
            record_id: _digest({"kind": kinds[record_id], "value": _local_projection(values[record_id])})
            for record_id in values
        }
        for _ in range(16):
            updated = {
                record_id: _digest(
                    {
                        "base": _local_projection(values[record_id]),
                        "neighbors": sorted(
                            (label, colors[neighbor])
                            for label, neighbor in edges.get(record_id, ())
                        ),
                    }
                )
                for record_id in values
            }
            if updated == colors:
                break
            colors = updated
        self._aliases = {
            record_id: f"{kinds[record_id][:3]}_{colors[record_id][:20]}"
            for record_id in values
        }

    def get(self, identifier: str | None) -> str | None:
        if identifier is None:
            return None
        return self._aliases.get(identifier, f"external_{_digest(identifier)[:20]}")


def _emission_canonical_records(
    records: tuple[tuple[str, str, BaseModel], ...],
    emissions: tuple[LawEmission, ...],
    query: IRQuery,
) -> tuple[tuple[str, str, BaseModel], ...]:
    record_map = {record_id: (kind, value) for kind, record_id, value in records}
    known = set(record_map)
    selected: set[str] = {query.query_id}
    for emission in emissions:
        selected.update(emission.entity_ids)
        selected.update(emission.point_ids)
        selected.update(emission.event_ids)
        selected.update(emission.source_quantity_ids)
        selected.update(emission.source_evidence_ids)
        selected.update(emission.assumption_ids)
        selected.update(emission.constraint_ids)
        selected.update(_expression_symbol_ids(emission.expression))
        for condition in emission.initial_conditions:
            selected.update(
                {
                    condition.target_symbol_id,
                    condition.value_symbol_id,
                    condition.wrt_symbol_id,
                    condition.subject_id,
                    condition.interval_id,
                    condition.event_id,
                    *condition.source_quantity_ids,
                    *condition.source_evidence_ids,
                    *condition.source_state_condition_ids,
                }
            )
            if condition.point_id is not None:
                selected.add(condition.point_id)
            if condition.frame_id is not None:
                selected.add(condition.frame_id)
        for identifier in (emission.frame_id, emission.interval_id, emission.event_id):
            if identifier is not None:
                selected.add(identifier)
    frontier = sorted(selected.intersection(known))
    while frontier:
        current = frontier.pop()
        _, value = record_map[current]
        for _, referenced_id in _id_values(value, known):
            if referenced_id not in selected:
                selected.add(referenced_id)
                frontier.append(referenced_id)
    return tuple(
        (kind, record_id, value)
        for kind, record_id, value in records
        if record_id in selected
    )


def _relevant_ids(
    query: IRQuery,
    edges: Mapping[str, tuple[tuple[str, str], ...]],
    limits: CompilerLimits,
) -> tuple[set[str] | None, CompilerIssue | None]:
    reached = {query.query_id}
    frontier = [query.query_id]
    rounds = 0
    while frontier:
        rounds += 1
        if rounds > limits.max_fixed_point_rounds:
            return None, _issue(
                CompilerIssueCode.resource_limit,
                "relevant-subgraph fixed point exceeded its round limit",
                "ir",
            )
        next_frontier: list[str] = []
        for current in sorted(frontier):
            for _, neighbor in edges.get(current, ()):
                if neighbor in reached:
                    continue
                reached.add(neighbor)
                next_frontier.append(neighbor)
                if len(reached) > limits.max_relevant_records:
                    return None, _issue(
                        CompilerIssueCode.resource_limit,
                        "relevant subgraph exceeds its record limit",
                        "ir",
                    )
        frontier = next_frontier
    return reached, None


def _query_matches(quantity, query: IRQuery) -> bool:
    target = query.target
    if quantity.role is not target.role or quantity.subject_id != target.subject_id:
        return False
    if quantity.shape is not query.shape or quantity.dimension != query.output_dimension:
        return False
    if quantity.component is not target.component:
        return False
    for field_name in ("point_id", "frame_id", "interval_id", "event_id"):
        target_value = getattr(target, field_name)
        if target_value is not None and getattr(quantity, field_name) != target_value:
            return False
    if target.direction is not None and quantity.direction != target.direction:
        return False
    return True


def _query_quantity(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
) -> tuple[object | None, CompilerIssue | None]:
    if query.target.target_quantity_id is not None:
        quantity = next(
            (item for item in ir.quantities if item.quantity_id == query.target.target_quantity_id),
            None,
        )
        if quantity is None or not _query_matches(quantity, query):
            return None, _issue(
                CompilerIssueCode.unresolved_query,
                "query target quantity is missing or does not match the declared target",
                f"queries.{query.query_id}.target",
                query.target.target_quantity_id,
            )
        return quantity, None
    matches = tuple(item for item in ir.quantities if _query_matches(item, query))
    if len(matches) > 1:
        return None, _issue(
            CompilerIssueCode.unresolved_query,
            "query target matches more than one quantity",
            f"queries.{query.query_id}.target",
            query.query_id,
        )
    return (matches[0] if matches else None), None


def _structural_specialization_issue(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
) -> CompilerIssue | None:
    if query.shape is QuantityShape.tensor:
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            "tensor queries require a specialized mechanics model",
            f"queries.{query.query_id}",
            query.query_id,
        )
    entity = next((item for item in ir.entities if item.entity_id == query.target.subject_id), None)
    frame = next((item for item in ir.reference_frames if item.frame_id == query.target.frame_id), None)
    angular_roles = {
        QuantityRole.angular_position,
        QuantityRole.angular_velocity,
        QuantityRole.angular_acceleration,
        QuantityRole.angular_momentum,
        QuantityRole.moment,
        QuantityRole.torque,
    }
    if (
        entity is not None
        and entity.primitive.value == "rigid_body"
        and query.target.role in angular_roles
        and frame is not None
        and frame.frame_type.value in {"cartesian_3d", "body_fixed", "rotating"}
    ):
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            "three-dimensional rigid rotation requires a specialized mechanics model",
            f"queries.{query.query_id}.target.frame_id",
            frame.frame_id,
        )
    if (
        frame is not None
        and frame.frame_type.value == "rotating"
        and query.target.role in {QuantityRole.velocity, QuantityRole.acceleration}
    ):
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            "relative motion in a rotating frame requires a specialized mechanics model",
            f"queries.{query.query_id}.target.frame_id",
            frame.frame_id,
        )
    return None


def _resolved_kinematic_component(quantity: IRQuantity) -> bool:
    if quantity.shape is QuantityShape.vector:
        return quantity.component is QuantityComponent.unspecified
    return quantity.shape is QuantityShape.scalar and quantity.component not in {
        QuantityComponent.magnitude,
        QuantityComponent.unspecified,
    }


def _scope_matches_query(
    quantity: IRQuantity,
    query_quantity: IRQuantity,
    *,
    subject_id: str,
    frame_id: str | None,
) -> bool:
    return (
        quantity.subject_id == subject_id
        and quantity.frame_id == frame_id
        and quantity.interval_id == query_quantity.interval_id
        and quantity.event_id == query_quantity.event_id
    )


def _free_linear_vibration_readout_issue(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    query_quantity: IRQuantity,
    relevant: set[str],
) -> CompilerIssue | None:
    expected_dimension = {
        QuantityRole.period: DimensionVector(time=1),
        QuantityRole.frequency: DimensionVector(time=-1),
    }.get(query_quantity.role)
    if (
        expected_dimension is None
        or query_quantity.quantity_id not in relevant
        or query_quantity.shape is not QuantityShape.scalar
        or query_quantity.dimension != expected_dimension
        or query_quantity.symbol_id is None
        or query_quantity.si_value is not None
        or query_quantity.event_id is not None
    ):
        return None

    subject_id = query_quantity.subject_id
    interval_id = query_quantity.interval_id
    approved = tuple(
        item
        for item in ir.assumptions
        if item.assumption_id in relevant
        and item.disposition is AssumptionDisposition.approved
        and item.subject_id == subject_id
        and item.interval_id in {None, interval_id}
    )
    masses = tuple(
        item
        for item in ir.quantities
        if item.quantity_id in relevant
        and item.role is QuantityRole.mass
        and item.subject_id == subject_id
        and item.frame_id in {None, query_quantity.frame_id}
        and item.interval_id in {None, interval_id}
        and item.event_id is None
        and item.shape is QuantityShape.scalar
        and item.dimension == DimensionVector(mass=1)
        and item.symbol_id is not None
        and isinstance(item.si_value, float)
        and math.isfinite(item.si_value)
        and item.si_value > 0.0
    )
    stiffnesses = tuple(
        item
        for item in ir.quantities
        if item.quantity_id in relevant
        and item.role is QuantityRole.stiffness
        and item.subject_id == subject_id
        and item.frame_id in {None, query_quantity.frame_id}
        and item.interval_id in {None, interval_id}
        and item.event_id is None
        and item.shape is QuantityShape.scalar
        and item.dimension == DimensionVector(mass=1, time=-2)
        and item.symbol_id is not None
        and isinstance(item.si_value, float)
        and math.isfinite(item.si_value)
        and item.si_value > 0.0
    )
    natural_frequency_authority = tuple(
        item for item in approved if item.kind == "angular_natural_frequency"
    )
    exact_minimal_readout = (
        query_quantity.role in {QuantityRole.frequency, QuantityRole.period}
        and len(natural_frequency_authority) == 1
        and len(masses) == 1
        and len(stiffnesses) == 1
    )
    if exact_minimal_readout:
        return _issue(
            CompilerIssueCode.free_linear_vibration_readout_deferred,
            "free linear undamped spring period/frequency readout is deferred",
            f"queries.{query.query_id}.target.role",
            query_quantity.quantity_id,
        )

    frame = next(
        (
            item
            for item in ir.reference_frames
            if item.frame_id == query_quantity.frame_id
            and item.frame_id in relevant
        ),
        None,
    )
    if frame is None or frame.frame_type is not ReferenceFrameType.cartesian_1d:
        return None

    regimes = {
        kind: tuple(item for item in approved if item.kind == kind)
        for kind in (
            "linear_vibration",
            "free_vibration",
            "undamped",
            "forced_vibration",
            "damped",
        )
    }
    if (
        len(regimes["linear_vibration"]) != 1
        or len(regimes["free_vibration"]) != 1
        or len(regimes["undamped"]) != 1
        or regimes["forced_vibration"]
        or regimes["damped"]
    ):
        return None

    displacements = tuple(
        item
        for item in ir.quantities
        if item.quantity_id in relevant
        and item.role is QuantityRole.displacement
        and item.subject_id == subject_id
        and item.frame_id == frame.frame_id
        and item.interval_id == interval_id
        and item.event_id is None
        and item.shape is QuantityShape.scalar
        and item.dimension == DimensionVector(length=1)
        and item.symbol_id is not None
    )
    if len(displacements) != 1 or len(masses) != 1 or len(stiffnesses) != 1:
        return None

    springs = tuple(
        item
        for item in ir.interactions
        if item.interaction_id in relevant
        and item.kind is InteractionKind.spring
        and subject_id in item.participant_ids
        and item.frame_id in {None, frame.frame_id}
        and item.interval_id in {None, interval_id}
        and item.event_id is None
        and {displacements[0].quantity_id, stiffnesses[0].quantity_id}.issubset(
            item.quantity_ids
        )
    )
    external_terms = tuple(
        item
        for item in ir.interactions
        if item.interaction_id in relevant
        and item.kind in {InteractionKind.damping, InteractionKind.applied_force}
        and subject_id in item.participant_ids
        and item.interval_id in {None, interval_id}
        and item.event_id is None
    )
    if len(springs) != 1 or external_terms:
        return None
    return _issue(
        CompilerIssueCode.free_linear_vibration_readout_deferred,
        "free linear undamped spring period/frequency readout is deferred",
        f"queries.{query.query_id}.target.role",
        query_quantity.quantity_id,
    )


def _translating_frame_relative_acceleration_issue(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    query_quantity: IRQuantity,
    relevant: set[str],
) -> CompilerIssue | None:
    scalar_unspecified_output = (
        query_quantity.shape is QuantityShape.scalar
        and query_quantity.component is QuantityComponent.unspecified
    )
    if (
        query_quantity.quantity_id not in relevant
        or query_quantity.role is not QuantityRole.acceleration
        or query_quantity.dimension != DimensionVector(length=1, time=-2)
        or query_quantity.symbol_id is None
        or query_quantity.si_value is not None
        or not (
            _resolved_kinematic_component(query_quantity)
            or scalar_unspecified_output
        )
    ):
        return None
    frames = {item.frame_id: item for item in ir.reference_frames}
    def exact_translating_frame(frame: object) -> bool:
        return (
            frame is not None
            and frame.frame_id in relevant
            and frame.frame_type is ReferenceFrameType.translating
            and frame.parent_frame_id is not None
            and frame.parent_frame_id in relevant
            and frame.parent_frame_id in frames
            and frame.translating_with_entity_id is not None
            and frame.translating_with_entity_id in relevant
            and frame.rotating_about_point_id is None
        )

    frame = frames.get(query_quantity.frame_id or "")
    if exact_translating_frame(frame) and _resolved_kinematic_component(
        query_quantity
    ):
        carrier_id = frame.translating_with_entity_id
        carriers = tuple(
            item
            for item in ir.quantities
            if item.quantity_id in relevant
            and item.quantity_id != query_quantity.quantity_id
            and item.role is QuantityRole.acceleration
            and item.dimension == query_quantity.dimension
            and item.shape is query_quantity.shape
            and item.component is query_quantity.component
            and item.symbol_id is not None
            and _scope_matches_query(
                item,
                query_quantity,
                subject_id=carrier_id,
                frame_id=frame.parent_frame_id,
            )
        )
        if len(carriers) == 1:
            return _issue(
                CompilerIssueCode.translating_frame_relative_acceleration_deferred,
                "translating-frame relative acceleration is deferred",
                f"queries.{query.query_id}.target.frame_id",
                frame.frame_id,
            )

    absolute_profiles: list[object] = []
    for moving_frame in ir.reference_frames:
        if (
            not exact_translating_frame(moving_frame)
            or moving_frame.parent_frame_id != query_quantity.frame_id
            or moving_frame.translating_with_entity_id
            == query_quantity.subject_id
        ):
            continue
        carrier_id = moving_frame.translating_with_entity_id
        relative_operands = tuple(
            item
            for item in ir.quantities
            if item.quantity_id in relevant
            and item.quantity_id != query_quantity.quantity_id
            and item.role is QuantityRole.acceleration
            and item.subject_id == query_quantity.subject_id
            and item.point_id == query_quantity.point_id
            and item.frame_id == moving_frame.frame_id
            and item.interval_id == query_quantity.interval_id
            and item.event_id == query_quantity.event_id
            and item.component is query_quantity.component
            and item.shape is query_quantity.shape
            and item.dimension == query_quantity.dimension
            and item.symbol_id is not None
            and item.si_value is not None
        )
        reference_carriers = tuple(
            item
            for item in ir.quantities
            if item.quantity_id in relevant
            and item.role is QuantityRole.acceleration
            and item.subject_id == carrier_id
            and item.frame_id == moving_frame.parent_frame_id
            and item.interval_id == query_quantity.interval_id
            and item.event_id == query_quantity.event_id
            and item.component is query_quantity.component
            and item.shape is query_quantity.shape
            and item.dimension == query_quantity.dimension
            and item.symbol_id is not None
            and item.si_value is not None
        )
        if len(relative_operands) == 1 and len(reference_carriers) == 1:
            absolute_profiles.append(moving_frame)
    if len(absolute_profiles) != 1:
        return None
    frame = absolute_profiles[0]
    return _issue(
        CompilerIssueCode.translating_frame_relative_acceleration_deferred,
        "translating-frame relative acceleration is deferred",
        f"queries.{query.query_id}.target.frame_id",
        frame.frame_id,
    )


def _origin_is_relevant(
    ir: MechanicsProblemIRV1,
    frame_id: str,
    parent_frame_id: str,
    relevant: set[str],
) -> bool:
    frame = next(item for item in ir.reference_frames if item.frame_id == frame_id)
    origin = frame.origin
    if type(origin) is IRWorldOrigin:
        return True
    if type(origin) is IRPointOrigin:
        return origin.point_id in relevant
    if type(origin) is IREntityOrigin:
        return origin.entity_id in relevant
    if type(origin) is IRFrameOrigin:
        return (
            origin.frame_id in relevant
            and origin.frame_id != frame_id
            and origin.frame_id == parent_frame_id
        )
    return False


def _rotating_frame_relative_acceleration_issue(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    query_quantity: IRQuantity,
    relevant: set[str],
) -> CompilerIssue | None:
    scalar_full_output = (
        query_quantity.shape is QuantityShape.scalar
        and query_quantity.component
        in {QuantityComponent.magnitude, QuantityComponent.unspecified}
    )
    if (
        query_quantity.quantity_id not in relevant
        or query_quantity.role is not QuantityRole.acceleration
        or query_quantity.dimension != DimensionVector(length=1, time=-2)
        or query_quantity.symbol_id is None
        or query_quantity.si_value is not None
        or not (
            _resolved_kinematic_component(query_quantity)
            or scalar_full_output
        )
    ):
        return None
    subject = next(
        (
            item
            for item in ir.entities
            if item.entity_id == query_quantity.subject_id
            and item.entity_id in relevant
        ),
        None,
    )
    if subject is None or subject.primitive not in {
        EntityPrimitive.particle,
        EntityPrimitive.body_component,
        EntityPrimitive.joint,
    }:
        return None
    frames = {item.frame_id: item for item in ir.reference_frames}
    frame = frames.get(query_quantity.frame_id or "")
    if (
        frame is None
        or frame.frame_id not in relevant
        or frame.frame_type is not ReferenceFrameType.rotating
        or frame.parent_frame_id is None
        or frame.parent_frame_id not in relevant
        or frame.parent_frame_id not in frames
        or frame.rotating_about_point_id is None
        or frame.rotating_about_point_id not in relevant
        or not _origin_is_relevant(
            ir,
            frame.frame_id,
            frame.parent_frame_id,
            relevant,
        )
    ):
        return None

    relative_velocities = tuple(
        item
        for item in ir.quantities
        if item.quantity_id in relevant
        and (
            item.role is QuantityRole.velocity
            or (
                scalar_full_output
                and item.role is QuantityRole.speed
                and item.shape is QuantityShape.scalar
                and item.component
                in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            )
        )
        and item.dimension == DimensionVector(length=1, time=-1)
        and item.shape is query_quantity.shape
        and item.symbol_id is not None
        and (
            _resolved_kinematic_component(item)
            or (
                scalar_full_output
                and item.shape is QuantityShape.scalar
                and item.component
                in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            )
        )
        and _scope_matches_query(
            item,
            query_quantity,
            subject_id=query_quantity.subject_id,
            frame_id=frame.frame_id,
        )
        and item.point_id == query_quantity.point_id
    )
    points = {item.point_id: item for item in ir.points}
    origin_point_id = getattr(frame.origin, "point_id", None)
    rotation_subject_ids = {query_quantity.subject_id}
    for point_id in (frame.rotating_about_point_id, origin_point_id):
        owner_id = getattr(points.get(point_id), "owner_entity_id", None)
        if owner_id is not None:
            rotation_subject_ids.add(owner_id)
    origin_entity_id = getattr(frame.origin, "entity_id", None)
    if origin_entity_id is not None:
        rotation_subject_ids.add(origin_entity_id)
    if frame.translating_with_entity_id is not None:
        rotation_subject_ids.add(frame.translating_with_entity_id)
    angular_velocities = tuple(
        item
        for item in ir.quantities
        if item.quantity_id in relevant
        and item.role is QuantityRole.angular_velocity
        and item.dimension == DimensionVector(time=-1)
        and item.shape in {QuantityShape.scalar, QuantityShape.vector}
        and item.symbol_id is not None
        and item.subject_id in rotation_subject_ids
        and item.frame_id in {frame.frame_id, frame.parent_frame_id}
        and item.interval_id == query_quantity.interval_id
        and item.event_id == query_quantity.event_id
        and item.point_id in {None, frame.rotating_about_point_id}
    )
    if len(relative_velocities) != 1 or len(angular_velocities) != 1:
        return None
    return _issue(
        CompilerIssueCode.rotating_frame_relative_acceleration_deferred,
        "rotating-frame Coriolis relative acceleration is deferred",
        f"queries.{query.query_id}.target.frame_id",
        frame.frame_id,
    )


def _slot_pin_relative_motion_issue(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    query_quantity: IRQuantity,
    relevant: set[str],
) -> CompilerIssue | None:
    component_query = (
        query_quantity.role in {QuantityRole.velocity, QuantityRole.acceleration}
        and query_quantity.component
        in {QuantityComponent.radial, QuantityComponent.transverse}
    )
    magnitude_query = (
        (
            query_quantity.role is QuantityRole.speed
            and query_quantity.component
            in {QuantityComponent.magnitude, QuantityComponent.unspecified}
        )
        or (
            query_quantity.role is QuantityRole.velocity
            and query_quantity.component is QuantityComponent.magnitude
        )
    )
    if (
        query_quantity.quantity_id not in relevant
        or not (component_query or magnitude_query)
        or query_quantity.shape is not QuantityShape.scalar
        or query_quantity.symbol_id is None
        or query_quantity.si_value is not None
    ):
        return None
    expected_dimension = (
        DimensionVector(length=1, time=-2)
        if query_quantity.role is QuantityRole.acceleration
        else DimensionVector(length=1, time=-1)
    )
    if query_quantity.dimension != expected_dimension:
        return None
    frame = next(
        (
            item
            for item in ir.reference_frames
            if item.frame_id == query_quantity.frame_id
            and item.frame_id in relevant
        ),
        None,
    )
    if frame is None or frame.frame_type is not ReferenceFrameType.radial_transverse:
        return None

    entities = {item.entity_id: item for item in ir.entities}
    points = {item.point_id: item for item in ir.points}
    query_point = points.get(query_quantity.point_id or "")
    query_owner_id = getattr(query_point, "owner_entity_id", None)
    pin_primitives = {
        EntityPrimitive.joint,
        EntityPrimitive.particle,
        EntityPrimitive.body_component,
    }
    pin_ids = {
        entity_id
        for entity_id in {query_quantity.subject_id, query_owner_id}
        if entity_id is not None
        and entity_id in relevant
        and entity_id in entities
        and entities[entity_id].primitive in pin_primitives
    }
    if len(pin_ids) != 1:
        return None
    pin_id = next(iter(pin_ids))
    owned_point_ids = {
        item.point_id
        for item in ir.points
        if item.point_id in relevant and item.owner_entity_id == pin_id
    }
    slot_ids = {
        item.entity_id
        for item in ir.entities
        if item.entity_id in relevant and item.primitive is EntityPrimitive.slot
    }
    relations = tuple(
        item
        for item in ir.geometry
        if item.relation_id in relevant
        and item.kind is GeometryRelationKind.lies_on
        and item.interval_id in {None, query_quantity.interval_id}
        and len(set(item.participant_ids).intersection(slot_ids)) == 1
        and bool(
            set(item.participant_ids).intersection({pin_id, *owned_point_ids})
        )
    )
    if len(relations) != 1:
        return None
    if magnitude_query:
        relation_slot_ids = set(relations[0].participant_ids).intersection(slot_ids)
        radius_carriers = tuple(
            item
            for item in ir.quantities
            if item.quantity_id in relevant
            and item.role is QuantityRole.radius
            and item.subject_id in {pin_id, *relation_slot_ids}
            and item.point_id in {None, query_quantity.point_id, *owned_point_ids}
            and item.frame_id in {None, frame.frame_id}
            and item.interval_id in {None, query_quantity.interval_id}
            and item.event_id in {None, query_quantity.event_id}
            and item.component
            in {
                QuantityComponent.magnitude,
                QuantityComponent.radial,
                QuantityComponent.unspecified,
            }
            and item.shape is QuantityShape.scalar
            and item.dimension == DimensionVector(length=1)
            and item.symbol_id is not None
            and isinstance(item.si_value, float)
            and math.isfinite(item.si_value)
            and item.si_value > 0.0
        )
        radial_speed_carriers = tuple(
            item
            for item in ir.quantities
            if item.quantity_id in relevant
            and item.role in {QuantityRole.speed, QuantityRole.velocity}
            and item.quantity_id != query_quantity.quantity_id
            and item.subject_id == pin_id
            and item.point_id == query_quantity.point_id
            and item.frame_id == frame.frame_id
            and item.interval_id == query_quantity.interval_id
            and item.event_id == query_quantity.event_id
            and item.component is QuantityComponent.radial
            and item.shape is QuantityShape.scalar
            and item.dimension == DimensionVector(length=1, time=-1)
            and item.symbol_id is not None
            and isinstance(item.si_value, float)
            and math.isfinite(item.si_value)
        )
        angular_velocity_carriers = tuple(
            item
            for item in ir.quantities
            if item.quantity_id in relevant
            and item.role is QuantityRole.angular_velocity
            and item.subject_id in {pin_id, *relation_slot_ids}
            and item.point_id in {None, query_quantity.point_id, *owned_point_ids}
            and item.frame_id == frame.frame_id
            and item.interval_id == query_quantity.interval_id
            and item.event_id == query_quantity.event_id
            and item.component
            in {
                QuantityComponent.clockwise,
                QuantityComponent.counterclockwise,
                QuantityComponent.unspecified,
            }
            and item.shape is QuantityShape.scalar
            and item.dimension == DimensionVector(time=-1)
            and item.symbol_id is not None
            and isinstance(item.si_value, float)
            and math.isfinite(item.si_value)
        )
        if (
            len(radius_carriers) != 1
            or len(radial_speed_carriers) != 1
            or len(angular_velocity_carriers) != 1
        ):
            return None
    return _issue(
        CompilerIssueCode.slot_pin_relative_motion_deferred,
        "slot-pin radial/transverse relative motion is deferred",
        f"geometry.{relations[0].relation_id}",
        relations[0].relation_id,
    )


def _course_scope_deferred_issue(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    query_quantity: object | None,
    relevant: set[str],
) -> CompilerIssue | None:
    if type(query_quantity) is not IRQuantity:
        return None
    exact_quantity = query_quantity
    return (
        _free_linear_vibration_readout_issue(
            ir,
            query,
            exact_quantity,
            relevant,
        )
        or _translating_frame_relative_acceleration_issue(
            ir,
            query,
            exact_quantity,
            relevant,
        )
        or _rotating_frame_relative_acceleration_issue(
            ir,
            query,
            exact_quantity,
            relevant,
        )
        or _slot_pin_relative_motion_issue(
            ir,
            query,
            exact_quantity,
            relevant,
        )
    )


def _incline_projection_domain_issue(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    relevant: set[str],
) -> CompilerIssue | None:
    """Constrain only angles bound to the fixed-incline projection template."""

    entities = {item.entity_id: item for item in ir.entities}
    frame = next(
        (
            item
            for item in ir.reference_frames
            if item.frame_id == query.target.frame_id
            and item.frame_id in relevant
            and item.frame_type.value == "tangential_normal"
        ),
        None,
    )
    incline_id = getattr(getattr(frame, "origin", None), "entity_id", None)
    if (
        query.target.role is not QuantityRole.acceleration
        or query.shape is not QuantityShape.scalar
        or entities.get(query.target.subject_id) is None
        or entities[query.target.subject_id].primitive.value != "particle"
        or incline_id not in relevant
        or entities.get(incline_id) is None
        or entities[incline_id].primitive.value != "incline"
    ):
        return None
    relations = tuple(
        item
        for item in ir.geometry
        if item.relation_id in relevant
        and item.kind.value == "angle"
        and incline_id in item.participant_ids
        and len(item.participant_ids) == 2
        and len(item.quantity_ids) == 1
        and item.interval_id is None
        and item.evidence_refs
    )
    if len(relations) != 1:
        return None
    environment_ids = tuple(
        item
        for item in relations[0].participant_ids
        if entities.get(item) is not None
        and entities[item].primitive.value == "environment"
    )
    angle = next(
        (
            item
            for item in ir.quantities
            if item.quantity_id == relations[0].quantity_ids[0]
            and item.role is QuantityRole.angle
            and item.subject_id == incline_id
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id is None
            and item.event_id is None
            and item.direction is None
            and item.shape is QuantityShape.scalar
            and item.dimension == DimensionVector.dimensionless()
            and isinstance(item.si_value, float)
            and item.evidence_refs
        ),
        None,
    )
    if len(environment_ids) != 1 or angle is None:
        return None
    if not 0.0 <= angle.si_value <= math.pi / 2.0:
        return _issue(
            CompilerIssueCode.invalid_domain,
            "incline projection angle must be in the inclusive domain [0, pi/2]",
            f"quantities.{angle.quantity_id}.si_value",
            angle.quantity_id,
        )
    gravity_interactions = tuple(
        item
        for item in ir.interactions
        if item.interaction_id in relevant
        and item.kind.value == "gravity"
        and set(item.participant_ids)
        == {query.target.subject_id, environment_ids[0]}
        and item.frame_id == query.target.frame_id
        and item.interval_id == query.target.interval_id
    )
    gravities = tuple(
        quantity
        for interaction in gravity_interactions
        for quantity in ir.quantities
        if quantity.quantity_id in interaction.quantity_ids
        and quantity.role is QuantityRole.gravity
        and quantity.subject_id == environment_ids[0]
        and isinstance(quantity.si_value, float)
    )
    if len(gravity_interactions) == 1 and len(gravities) == 1 and gravities[0].si_value <= 0.0:
        return _issue(
            CompilerIssueCode.invalid_domain,
            "incline projection requires a positive gravity magnitude",
            f"quantities.{gravities[0].quantity_id}.si_value",
            gravities[0].quantity_id,
        )
    return None


def _exact_axis_direction(
    value: object,
    *,
    frame_id: str,
    axis: str,
    sign: int,
) -> bool:
    direction = getattr(value, "direction", None)
    return (
        getattr(direction, "kind", None) == "axis"
        and getattr(direction, "frame_id", None) == frame_id
        and getattr(getattr(direction, "axis", None), "value", None) == axis
        and getattr(direction, "sign", None) == sign
    )


def _incline_friction_contract_issue(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    relevant: set[str],
) -> CompilerIssue | None:
    """Require an exact source-backed active-friction incline contract.

    This gate is deliberately local to a tangential acceleration query on an
    incline.  The generic contact templates remain available for every other
    topology, while this topology cannot use a model-authored friction force as
    its own regime or direction authority.
    """

    frame = next(
        (
            item
            for item in ir.reference_frames
            if item.frame_id == query.target.frame_id
            and item.frame_id in relevant
            and item.frame_type.value == "tangential_normal"
        ),
        None,
    )
    incline_id = getattr(getattr(frame, "origin", None), "entity_id", None)
    entities = {item.entity_id: item for item in ir.entities}
    if (
        query.target.role is not QuantityRole.acceleration
        or query.shape is not QuantityShape.scalar
        or query.target.component.value != "tangential"
        or frame is None
        or incline_id is None
        or entities.get(incline_id) is None
        or entities[incline_id].primitive.value != "incline"
    ):
        return None

    body_id = query.target.subject_id
    quantities = {item.quantity_id: item for item in ir.quantities}
    related_contacts = tuple(
        item
        for item in ir.interactions
        if item.interaction_id in relevant
        and item.kind.value == "contact"
        and ({body_id, incline_id} & set(item.participant_ids))
    )
    friction_states = tuple(
        item
        for item in ir.state_conditions
        if item.state_condition_id in relevant
        and item.kind.value == "friction"
        and item.subject_id == body_id
    )
    carries_coefficient = any(
        quantities.get(quantity_id) is not None
        and quantities[quantity_id].role is QuantityRole.coefficient_friction
        for contact in related_contacts
        for quantity_id in contact.quantity_ids
    )
    carries_active_state = any(item.state.value != "inactive" for item in friction_states)
    if not carries_coefficient and not carries_active_state:
        return None

    def failure(referenced_id: str | None = None) -> CompilerIssue:
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            "active incline friction requires one exact evidenced contact, regime, and motion-direction contract",
            f"queries.{query.query_id}",
            referenced_id or query.query_id,
        )

    if (
        entities.get(body_id) is None
        or entities[body_id].primitive.value != "particle"
        or not entities[body_id].evidence_refs
        or not entities[incline_id].evidence_refs
        or query.target.interval_id is None
        or query.target.event_id is not None
        or not frame.evidence_refs
    ):
        return failure(body_id)

    axis_signature = {
        (
            item.axis.value,
            getattr(item.direction, "kind", None),
            getattr(item.direction, "frame_id", None),
            getattr(getattr(item.direction, "axis", None), "value", None),
            getattr(item.direction, "sign", None),
        )
        for item in frame.axes
    }
    if len(frame.axes) != 2 or axis_signature != {
        ("tangent", "axis", frame.frame_id, "tangent", 1),
        ("normal", "axis", frame.frame_id, "normal", 1),
    }:
        return failure(frame.frame_id)

    query_intervals = tuple(
        item
        for item in ir.motion_intervals
        if item.interval_id in relevant
        and item.interval_id == query.target.interval_id
    )
    if len(query_intervals) != 1:
        return failure(query.target.interval_id)
    query_interval = query_intervals[0]
    if (
        query_interval.frame_id != frame.frame_id
        or not {body_id, incline_id}.issubset(query_interval.subject_ids)
        or not query_interval.evidence_refs
        or (
            query_interval.start_event_id is not None
            and query_interval.start_event_id == query_interval.end_event_id
        )
    ):
        return failure(query_interval.interval_id)
    events = {item.event_id: item for item in ir.events}
    for event_id in (
        query_interval.start_event_id,
        query_interval.end_event_id,
    ):
        if event_id is None:
            continue
        event = events.get(event_id)
        if (
            event is None
            or query_interval.interval_id not in event.interval_ids
            or not set(event.subject_ids).issubset(query_interval.subject_ids)
        ):
            return failure(event_id)

    scoped_contacts = tuple(
        item
        for item in related_contacts
        if item.frame_id == frame.frame_id
        and item.interval_id == query.target.interval_id
        and item.event_id == query.target.event_id
    )
    if len(scoped_contacts) != 1:
        return failure(scoped_contacts[0].interaction_id if scoped_contacts else None)
    contact = scoped_contacts[0]
    if (
        len(contact.participant_ids) != 2
        or set(contact.participant_ids) != {body_id, incline_id}
        or len(contact.point_ids) != 1
        or not contact.evidence_refs
        or len(contact.quantity_ids) != 4
        or len(set(contact.quantity_ids)) != 4
    ):
        return failure(contact.interaction_id)

    contact_point = next(
        (item for item in ir.points if item.point_id == contact.point_ids[0]),
        None,
    )
    if (
        contact_point is None
        or contact_point.role.value != "contact"
        or contact_point.owner_entity_id != body_id
        or contact_point.frame_id != frame.frame_id
        or not contact_point.evidence_refs
    ):
        return failure(contact.point_ids[0])

    linked = tuple(quantities.get(item) for item in contact.quantity_ids)
    if any(item is None for item in linked):
        return failure(contact.interaction_id)
    normal_forces = tuple(
        item
        for item in linked
        if item.role is QuantityRole.force and item.component.value == "normal"
    )
    normal_accelerations = tuple(
        item
        for item in linked
        if item.role is QuantityRole.acceleration and item.component.value == "normal"
    )
    tangent_forces = tuple(
        item
        for item in linked
        if item.role is QuantityRole.force and item.component.value == "tangential"
    )
    coefficients = tuple(
        item for item in linked if item.role is QuantityRole.coefficient_friction
    )
    if not all(
        len(items) == 1
        for items in (normal_forces, normal_accelerations, tangent_forces, coefficients)
    ):
        return failure(contact.interaction_id)
    normal, normal_acceleration, tangent, coefficient = (
        normal_forces[0],
        normal_accelerations[0],
        tangent_forces[0],
        coefficients[0],
    )
    if (
        any(item.shape is not QuantityShape.scalar for item in linked)
        or any(not item.evidence_refs for item in linked)
        or any(item.subject_id != body_id for item in linked)
        or normal.point_id != contact_point.point_id
        or tangent.point_id != contact_point.point_id
        or normal_acceleration.point_id is not None
        or normal.frame_id != frame.frame_id
        or normal_acceleration.frame_id != frame.frame_id
        or tangent.frame_id != frame.frame_id
        or normal.interval_id != query.target.interval_id
        or normal_acceleration.interval_id != query.target.interval_id
        or tangent.interval_id != query.target.interval_id
        or normal.event_id != query.target.event_id
        or normal_acceleration.event_id != query.target.event_id
        or tangent.event_id != query.target.event_id
        or not _exact_axis_direction(normal, frame_id=frame.frame_id, axis="normal", sign=1)
        or not _exact_axis_direction(
            normal_acceleration, frame_id=frame.frame_id, axis="normal", sign=1
        )
        or coefficient.dimension != DimensionVector.dimensionless()
        or coefficient.component.value not in {"magnitude", "unspecified"}
        or coefficient.direction is not None
        or coefficient.point_id is not None
        or coefficient.frame_id is not None
        or coefficient.interval_id is not None
        or coefficient.event_id is not None
        or not isinstance(coefficient.si_value, float)
        or not math.isfinite(coefficient.si_value)
        or coefficient.si_value < 0.0
    ):
        return failure(contact.interaction_id)

    def scoped_states(kind: str, subject_id: str) -> tuple[IRStateCondition, ...]:
        return tuple(
            item
            for item in ir.state_conditions
            if item.state_condition_id in relevant
            and item.kind.value == kind
            and item.subject_id == subject_id
            and item.interval_id == query.target.interval_id
            and item.event_id == query.target.event_id
        )

    contact_states = scoped_states("contact", body_id)
    fixed_states = scoped_states("motion", incline_id)
    exact_friction_states = scoped_states("friction", body_id)
    body_motion_states = scoped_states("motion", body_id)
    if (
        len(contact_states) != 1
        or contact_states[0].state.value != "touching"
        or contact_states[0].expression is not None
        or len(contact_states[0].quantity_ids) != 2
        or set(contact_states[0].quantity_ids)
        != {normal.quantity_id, normal_acceleration.quantity_id}
        or not contact_states[0].evidence_refs
        or len(fixed_states) != 1
        or fixed_states[0].state.value != "at_rest"
        or fixed_states[0].expression is not None
        or fixed_states[0].quantity_ids
        or not fixed_states[0].evidence_refs
        or len(exact_friction_states) != 1
        or exact_friction_states[0].state.value not in {"sticking", "sliding"}
        or exact_friction_states[0].expression is not None
        or len(exact_friction_states[0].quantity_ids) != 3
        or set(exact_friction_states[0].quantity_ids)
        != {tangent.quantity_id, normal.quantity_id, coefficient.quantity_id}
        or not exact_friction_states[0].evidence_refs
        or len(body_motion_states) != 1
        or body_motion_states[0].expression is not None
        or not body_motion_states[0].evidence_refs
    ):
        return failure(contact.interaction_id)

    regime = exact_friction_states[0].state.value
    body_motion = body_motion_states[0]
    if regime == "sticking":
        if (
            body_motion.state.value != "at_rest"
            or body_motion.quantity_ids
            or not _exact_axis_direction(
                tangent, frame_id=frame.frame_id, axis="tangent", sign=-1
            )
        ):
            return failure(exact_friction_states[0].state_condition_id)
        return None

    if body_motion.state.value != "moving" or len(body_motion.quantity_ids) != 1:
        return failure(body_motion.state_condition_id)
    carrier = quantities.get(body_motion.quantity_ids[0])
    if (
        carrier is None
        or carrier.role is not QuantityRole.velocity
        or carrier.shape is not QuantityShape.scalar
        or carrier.dimension != DimensionVector(length=1, time=-1)
        or carrier.subject_id != body_id
        or carrier.point_id is not None
        or carrier.frame_id != frame.frame_id
        or carrier.interval_id != query.target.interval_id
        or carrier.event_id != query.target.event_id
        or carrier.component.value != "tangential"
        or carrier.provenance is not Provenance.explicit_source
        or not carrier.evidence_refs
        or not isinstance(carrier.si_value, float)
        or not math.isfinite(carrier.si_value)
        or carrier.si_value <= 0.0
    ):
        return failure(body_motion.state_condition_id)
    carrier_sign = getattr(carrier.direction, "sign", None)
    if (
        carrier_sign not in {-1, 1}
        or not _exact_axis_direction(
            carrier,
            frame_id=frame.frame_id,
            axis="tangent",
            sign=carrier_sign,
        )
        or not _exact_axis_direction(
            tangent,
            frame_id=frame.frame_id,
            axis="tangent",
            sign=-carrier_sign,
        )
    ):
        return failure(carrier.quantity_id)
    return None


@dataclass(frozen=True)
class _FixedPulleyHorizontalContactProfile:
    friction_state_id: str


def _fixed_pulley_horizontal_contact_contract(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    relevant: set[str],
    approved_assumption_ids: frozenset[str],
) -> tuple[_FixedPulleyHorizontalContactProfile | None, CompilerIssue | None]:
    """Close the exact evidenced horizontal-contact fixed-pulley template."""

    entities = tuple(item for item in ir.entities if item.entity_id in relevant)
    primitive_ids = {
        primitive: tuple(
            item.entity_id for item in entities if item.primitive.value == primitive
        )
        for primitive in (
            "particle",
            "surface",
            "rope",
            "pulley",
            "environment",
        )
    }
    interactions = tuple(
        item for item in ir.interactions if item.interaction_id in relevant
    )
    contacts = tuple(
        item for item in interactions if item.kind.value == "contact"
    )
    rope_interactions = tuple(
        item for item in interactions if item.kind.value == "rope_tension"
    )
    wraps = tuple(
        item
        for item in ir.geometry
        if item.relation_id in relevant and item.kind.value == "wraps"
    )
    fixed_signal = any(
        item.state_condition_id in relevant
        and item.subject_id in primitive_ids["pulley"]
        and item.kind.value == "motion"
        and item.state.value == "at_rest"
        for item in ir.state_conditions
    ) or any(
        item.assumption_id in relevant
        and item.subject_id in primitive_ids["pulley"]
        and item.kind == "fixed_pulley"
        for item in ir.assumptions
    )
    candidate = (
        bool(primitive_ids["surface"])
        and bool(contacts)
        and bool(rope_interactions)
        and bool(primitive_ids["rope"])
        and (bool(primitive_ids["pulley"]) or bool(wraps) or fixed_signal)
        and bool(primitive_ids["particle"])
    )
    if not candidate:
        return None, None

    def failure(detail: str, referenced_id: str | None = None) -> CompilerIssue:
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            f"fixed-pulley horizontal-contact topology {detail}",
            f"queries.{query.query_id}",
            referenced_id or query.query_id,
        )

    expected_counts = {
        "particle": 2,
        "surface": 1,
        "rope": 1,
        "pulley": 1,
        "environment": 1,
    }
    if (
        {key: len(value) for key, value in primitive_ids.items()} != expected_counts
        or len(entities) != 6
        or any(
            not item.evidence_refs or item.component_of_entity_id is not None
            for item in entities
        )
    ):
        return None, failure(
            "requires exactly two particles, one surface, one rope, one pulley, and one environment"
        )
    particle_ids = set(primitive_ids["particle"])
    surface_id = primitive_ids["surface"][0]
    rope_id = primitive_ids["rope"][0]
    pulley_id = primitive_ids["pulley"][0]
    environment_id = primitive_ids["environment"][0]

    frames = tuple(
        item for item in ir.reference_frames if item.frame_id in relevant
    )
    if len(frames) != 1:
        return None, failure("requires one evidenced Cartesian frame")
    frame = frames[0]
    axis_signature = {
        (
            item.axis.value,
            getattr(item.direction, "kind", None),
            getattr(item.direction, "frame_id", None),
            getattr(getattr(item.direction, "axis", None), "value", None),
            getattr(item.direction, "sign", None),
        )
        for item in frame.axes
    }
    if (
        frame.frame_type.value != "cartesian_2d"
        or getattr(frame.origin, "kind", None) != "world"
        or frame.parent_frame_id is not None
        or frame.translating_with_entity_id is not None
        or frame.rotating_about_point_id is not None
        or frame.generalized_coordinate_symbol_ids
        or not frame.evidence_refs
        or len(frame.axes) != 2
        or axis_signature
        != {
            ("x", "axis", frame.frame_id, "x", 1),
            ("y", "axis", frame.frame_id, "y", 1),
        }
    ):
        return None, failure("requires exact evidenced world +x/+y axes", frame.frame_id)

    intervals = tuple(
        item for item in ir.motion_intervals if item.interval_id in relevant
    )
    if len(intervals) != 1:
        return None, failure("requires one evidenced motion interval")
    interval = intervals[0]
    expected_subjects = {item.entity_id for item in entities}
    if (
        interval.frame_id != frame.frame_id
        or interval.start_event_id is not None
        or interval.end_event_id is not None
        or len(interval.subject_ids) != len(expected_subjects)
        or set(interval.subject_ids) != expected_subjects
        or not interval.evidence_refs
        or any(item.event_id in relevant for item in ir.events)
    ):
        return None, failure(
            "requires one exact event-free interval containing the complete topology",
            interval.interval_id,
        )

    if len(contacts) != 1:
        return None, failure("requires one horizontal surface contact")
    contact = contacts[0]
    table_ids = set(contact.participant_ids) & particle_ids
    if (
        len(contact.participant_ids) != 2
        or len(set(contact.participant_ids)) != 2
        or surface_id not in contact.participant_ids
        or len(table_ids) != 1
        or len(contact.point_ids) != 1
        or contact.frame_id != frame.frame_id
        or contact.interval_id != interval.interval_id
        or contact.event_id is not None
        or not contact.evidence_refs
    ):
        return None, failure("requires one exact evidenced particle/surface contact", contact.interaction_id)
    table_id = next(iter(table_ids))
    hanging_id = next(iter(particle_ids - {table_id}))
    points = tuple(item for item in ir.points if item.point_id in relevant)
    if len(points) != 1:
        return None, failure("requires one evidenced contact point", contact.point_ids[0])
    contact_point = points[0]
    if (
        contact_point.point_id != contact.point_ids[0]
        or contact_point.role.value != "contact"
        or contact_point.owner_entity_id != table_id
        or contact_point.frame_id != frame.frame_id
        or not contact_point.evidence_refs
    ):
        return None, failure("has an invalid contact-point binding", contact_point.point_id)

    geometry = tuple(item for item in ir.geometry if item.relation_id in relevant)
    attached = tuple(item for item in geometry if item.kind.value == "attached")
    if (
        len(geometry) != 3
        or len(wraps) != 1
        or len(attached) != 2
        or any(
            item.expression is not None
            or item.quantity_ids
            or item.interval_id != interval.interval_id
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            for item in geometry
        )
        or len(wraps[0].participant_ids) != 2
        or set(wraps[0].participant_ids) != {rope_id, pulley_id}
        or {frozenset(item.participant_ids) for item in attached}
        != {frozenset((rope_id, item)) for item in particle_ids}
    ):
        return None, failure(
            "requires one wrap and two exact evidenced rope attachments", rope_id
        )

    states = tuple(
        item for item in ir.state_conditions if item.state_condition_id in relevant
    )
    state_base_valid = all(
        item.interval_id == interval.interval_id
        and item.event_id is None
        and item.expression is None
        and bool(item.evidence_refs)
        for item in states
    )
    rope_states = tuple(
        item
        for item in states
        if item.subject_id == rope_id and item.kind.value == "rope"
    )
    pulley_states = tuple(
        item
        for item in states
        if item.subject_id == pulley_id and item.kind.value == "motion"
    )
    touching_states = tuple(
        item
        for item in states
        if item.subject_id == table_id and item.kind.value == "contact"
    )
    surface_states = tuple(
        item
        for item in states
        if item.subject_id == surface_id and item.kind.value == "motion"
    )
    friction_states = tuple(
        item
        for item in states
        if item.subject_id == table_id and item.kind.value == "friction"
    )
    table_motion_states = tuple(
        item
        for item in states
        if item.subject_id == table_id and item.kind.value == "motion"
    )
    if (
        not state_base_valid
        or len(rope_states) != 1
        or rope_states[0].state.value != "taut"
        or rope_states[0].quantity_ids
        or len(pulley_states) != 1
        or pulley_states[0].state.value != "at_rest"
        or pulley_states[0].quantity_ids
        or len(touching_states) != 1
        or touching_states[0].state.value != "touching"
        or len(surface_states) != 1
        or surface_states[0].state.value != "at_rest"
        or surface_states[0].quantity_ids
        or len(friction_states) != 1
        or friction_states[0].state.value
        not in {"inactive", "sticking", "sliding"}
    ):
        return None, failure("requires exact evidenced rope, pulley, contact, and friction states")
    friction_state = friction_states[0]
    regime = friction_state.state.value
    expected_state_count = 5 if regime == "inactive" else 6
    if (
        len(states) != expected_state_count
        or (regime == "inactive" and table_motion_states)
        or (regime != "inactive" and len(table_motion_states) != 1)
    ):
        return None, failure("contains extra or missing regime state", friction_state.state_condition_id)

    scoped_assumptions = tuple(
        item for item in ir.assumptions if item.assumption_id in relevant
    )
    expected_assumptions = {
        ("massless_rope", rope_id),
        ("inextensible_rope", rope_id),
        ("ideal_massless_frictionless_pulley", pulley_id),
        ("fixed_pulley", pulley_id),
    }
    if (
        len(scoped_assumptions) != 4
        or {(item.kind, item.subject_id) for item in scoped_assumptions}
        != expected_assumptions
        or any(
            item.disposition is not AssumptionDisposition.approved
            or item.assumption_id not in approved_assumption_ids
            or item.interval_id != interval.interval_id
            or item.proposed_role is not None
            or item.proposed_value is not None
            or item.proposed_unit is not None
            or not item.evidence_refs
            for item in scoped_assumptions
        )
    ):
        return None, failure(
            "requires exact externally approved evidenced rope and pulley assumptions",
            rope_id,
        )

    gravity_interactions = tuple(
        item for item in interactions if item.kind.value == "gravity"
    )
    if (
        len(interactions) != 4
        or len(gravity_interactions) != 2
        or len(rope_interactions) != 1
        or {next(iter(set(item.participant_ids) & particle_ids), None) for item in gravity_interactions}
        != particle_ids
        or any(
            len(item.participant_ids) != 2
            or len(set(item.participant_ids)) != 2
            or environment_id not in item.participant_ids
            or item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.point_ids
            or len(item.quantity_ids) != 3
            or len(set(item.quantity_ids)) != 3
            or not item.evidence_refs
            for item in gravity_interactions
        )
    ):
        return None, failure(
            "requires exactly two gravity, one contact, and one rope-tension interaction"
        )
    rope_interaction = rope_interactions[0]
    if (
        len(rope_interaction.participant_ids) != 4
        or set(rope_interaction.participant_ids)
        != particle_ids | {rope_id, pulley_id}
        or rope_interaction.point_ids
        or rope_interaction.frame_id != frame.frame_id
        or rope_interaction.interval_id != interval.interval_id
        or rope_interaction.event_id is not None
        or len(rope_interaction.quantity_ids) != 2
        or len(set(rope_interaction.quantity_ids)) != 2
        or not rope_interaction.evidence_refs
    ):
        return None, failure("has an invalid rope-tension interaction", rope_interaction.interaction_id)

    quantity_by_id = {item.quantity_id: item for item in ir.quantities}
    masses: dict[str, object] = {}
    weights: dict[str, object] = {}
    gravity_items: list[object] = []
    for interaction in gravity_interactions:
        body_id = next(iter(set(interaction.participant_ids) & particle_ids))
        linked = tuple(quantity_by_id.get(item) for item in interaction.quantity_ids)
        local_mass = tuple(
            item
            for item in linked
            if item is not None
            and item.role is QuantityRole.mass
            and item.subject_id == body_id
        )
        local_gravity = tuple(
            item
            for item in linked
            if item is not None
            and item.role is QuantityRole.gravity
            and item.subject_id == environment_id
        )
        local_weight = tuple(
            item
            for item in linked
            if item is not None
            and item.role is QuantityRole.force
            and item.subject_id == body_id
        )
        if not all(len(items) == 1 for items in (local_mass, local_gravity, local_weight)):
            return None, failure("requires one mass, gravity, and weight per particle", interaction.interaction_id)
        masses[body_id] = local_mass[0]
        gravity_items.append(local_gravity[0])
        weights[body_id] = local_weight[0]
    if len({item.quantity_id for item in gravity_items}) != 1:
        return None, failure("requires one shared gravity magnitude", environment_id)
    gravity = gravity_items[0]

    tensions = tuple(
        quantity_by_id.get(item) for item in rope_interaction.quantity_ids
    )
    linked_contact = tuple(
        quantity_by_id.get(item) for item in contact.quantity_ids
    )
    if any(item is None for item in (*tensions, *linked_contact)):
        return None, failure("contains an unresolved interaction quantity")
    tension_table = tuple(
        item for item in tensions
        if item.role is QuantityRole.force and item.subject_id == table_id
    )
    tension_hanging = tuple(
        item for item in tensions
        if item.role is QuantityRole.force and item.subject_id == hanging_id
    )
    normal_forces = tuple(
        item for item in linked_contact
        if item.role is QuantityRole.force
        and item.subject_id == table_id
        and item.component.value == "y"
        and getattr(getattr(item, "direction", None), "sign", None) == 1
    )
    normal_accelerations = tuple(
        item for item in linked_contact
        if item.role is QuantityRole.acceleration
        and item.subject_id == table_id
        and item.component.value == "y"
    )
    friction_forces = tuple(
        item for item in linked_contact
        if item.role is QuantityRole.force
        and item.subject_id == table_id
        and item.component.value == "x"
    )
    coefficients = tuple(
        item for item in linked_contact
        if item.role is QuantityRole.coefficient_friction
        and item.subject_id == table_id
    )
    accelerations = tuple(
        item
        for item in ir.quantities
        if item.quantity_id in relevant
        and item.role is QuantityRole.acceleration
        and item.subject_id in particle_ids
    )
    table_x = tuple(
        item for item in accelerations
        if item.subject_id == table_id and item.component.value == "x"
    )
    table_y = tuple(
        item for item in accelerations
        if item.subject_id == table_id and item.component.value == "y"
    )
    hanging_y = tuple(
        item for item in accelerations
        if item.subject_id == hanging_id and item.component.value == "y"
    )
    if (
        len(tension_table) != 1
        or len(tension_hanging) != 1
        or len(normal_forces) != 1
        or len(normal_accelerations) != 1
        or len(accelerations) != 3
        or len(table_x) != 1
        or len(table_y) != 1
        or len(hanging_y) != 1
    ):
        return None, failure("requires exact table/hanging force and acceleration components")
    normal = normal_forces[0]
    normal_acceleration = normal_accelerations[0]
    table_acceleration = table_x[0]
    hanging_acceleration = hanging_y[0]

    def exact_known(item: object, *, positive: bool) -> bool:
        value = getattr(item, "si_value", None)
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.provenance is Provenance.explicit_source
            and bool(item.evidence_refs)
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id is None
            and item.event_id is None
            and item.direction is None
            and item.component.value in {"magnitude", "unspecified"}
            and type(value) is float
            and math.isfinite(value)
            and (value > 0.0 if positive else value >= 0.0)
        )

    known_positive = (*masses.values(), gravity)
    bad_domain = next(
        (
            item for item in known_positive
            if type(getattr(item, "si_value", None)) is float
            and getattr(item, "si_value") <= 0.0
        ),
        None,
    )
    if bad_domain is not None:
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "fixed-pulley horizontal-contact masses and gravity must be positive",
            f"quantities.{bad_domain.quantity_id}.si_value",
            bad_domain.quantity_id,
        )
    if any(not exact_known(item, positive=True) for item in known_positive):
        return None, failure("requires exact positive source-backed masses and gravity")

    def exact_unknown_component(
        item: object,
        *,
        subject_id: str,
        point_id: str | None,
        axis: str,
        sign: int | None,
    ) -> bool:
        observed_sign = getattr(getattr(item, "direction", None), "sign", None)
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.si_value is None
            and item.provenance in {Provenance.inferred, Provenance.unknown}
            and bool(item.evidence_refs)
            and item.subject_id == subject_id
            and item.point_id == point_id
            and item.frame_id == frame.frame_id
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.component.value == axis
            and observed_sign in {-1, 1}
            and (sign is None or observed_sign == sign)
            and _exact_axis_direction(
                item,
                frame_id=frame.frame_id,
                axis=axis,
                sign=observed_sign,
            )
        )

    query_quantity_id = query.target.target_quantity_id
    if (
        any(
            not exact_unknown_component(
                item,
                subject_id=body_id,
                point_id=None,
                axis="y",
                sign=-1,
            )
            for body_id, item in weights.items()
        )
        or not exact_unknown_component(
            tension_table[0], subject_id=table_id, point_id=None, axis="x", sign=1
        )
        or not exact_unknown_component(
            tension_hanging[0], subject_id=hanging_id, point_id=None, axis="y", sign=1
        )
        or not exact_unknown_component(
            normal, subject_id=table_id, point_id=contact_point.point_id, axis="y", sign=1
        )
        or not exact_unknown_component(
            normal_acceleration, subject_id=table_id, point_id=None, axis="y", sign=1
        )
        or not exact_unknown_component(
            table_acceleration,
            subject_id=table_id,
            point_id=None,
            axis="x",
            sign=None if query_quantity_id == table_acceleration.quantity_id else 1,
        )
        or not exact_unknown_component(
            hanging_acceleration,
            subject_id=hanging_id,
            point_id=None,
            axis="y",
            sign=None if query_quantity_id == hanging_acceleration.quantity_id else -1,
        )
    ):
        return None, failure("requires exact evidenced horizontal/vertical component directions")

    friction = friction_forces[0] if len(friction_forces) == 1 else None
    coefficient = coefficients[0] if len(coefficients) == 1 else None
    carrier = None
    if regime == "inactive":
        if (
            len(linked_contact) != 2
            or friction is not None
            or coefficient is not None
            or friction_state.quantity_ids
        ):
            return None, failure("inactive friction must not carry a force or coefficient")
    else:
        if (
            len(linked_contact) != 4
            or friction is None
            or coefficient is None
            or not exact_known(coefficient, positive=False)
            or coefficient.dimension != DimensionVector.dimensionless()
            or set(friction_state.quantity_ids)
            != {friction.quantity_id, normal.quantity_id, coefficient.quantity_id}
            or len(friction_state.quantity_ids) != 3
        ):
            return None, failure("active friction requires one exact force and coefficient", friction_state.state_condition_id)
        table_motion = table_motion_states[0]
        if regime == "sticking":
            if (
                table_motion.state.value != "at_rest"
                or table_motion.quantity_ids
                or not exact_unknown_component(
                    friction,
                    subject_id=table_id,
                    point_id=contact_point.point_id,
                    axis="x",
                    sign=-1,
                )
            ):
                return None, failure("sticking friction requires an evidenced at-rest table particle")
        else:
            if table_motion.state.value != "moving" or len(table_motion.quantity_ids) != 1:
                return None, failure("sliding friction requires one motion carrier", table_motion.state_condition_id)
            carrier = quantity_by_id.get(table_motion.quantity_ids[0])
            carrier_sign = getattr(getattr(carrier, "direction", None), "sign", None)
            if (
                carrier is None
                or carrier.role is not QuantityRole.velocity
                or carrier.shape is not QuantityShape.scalar
                or carrier.dimension != DimensionVector(length=1, time=-1)
                or carrier.symbol_id is None
                or carrier.subject_id != table_id
                or carrier.point_id is not None
                or carrier.frame_id != frame.frame_id
                or carrier.interval_id != interval.interval_id
                or carrier.event_id is not None
                or carrier.component.value != "x"
                or carrier.provenance is not Provenance.explicit_source
                or not carrier.evidence_refs
                or type(carrier.si_value) is not float
                or not math.isfinite(carrier.si_value)
                or carrier.si_value <= 0.0
                or carrier_sign != 1
                or not _exact_axis_direction(
                    carrier, frame_id=frame.frame_id, axis="x", sign=1
                )
                or not exact_unknown_component(
                    friction,
                    subject_id=table_id,
                    point_id=contact_point.point_id,
                    axis="x",
                    sign=-1,
                )
            ):
                return None, failure("sliding friction requires exact opposite motion and force directions")

    if (
        set(touching_states[0].quantity_ids)
        != {normal.quantity_id, normal_acceleration.quantity_id}
        or len(touching_states[0].quantity_ids) != 2
        or any(item.dimension != weights[table_id].dimension for item in (*weights.values(), *tensions, normal))
        or masses[table_id].dimension.plus(gravity.dimension) != weights[table_id].dimension
        or masses[hanging_id].dimension.plus(gravity.dimension) != weights[hanging_id].dimension
        or masses[table_id].dimension.plus(table_acceleration.dimension) != weights[table_id].dimension
        or masses[table_id].dimension.plus(normal_acceleration.dimension) != weights[table_id].dimension
        or masses[hanging_id].dimension.plus(hanging_acceleration.dimension) != weights[hanging_id].dimension
        or table_acceleration.dimension != gravity.dimension
        or normal_acceleration.dimension != gravity.dimension
        or hanging_acceleration.dimension != gravity.dimension
        or (friction is not None and friction.dimension != normal.dimension)
    ):
        return None, failure("has invalid state bindings or dimensions")

    expected_quantities = {
        item.quantity_id
        for item in (
            *masses.values(),
            gravity,
            *weights.values(),
            *tensions,
            table_acceleration,
            normal_acceleration,
            hanging_acceleration,
            normal,
            *(() if friction is None else (friction,)),
            *(() if coefficient is None else (coefficient,)),
            *(() if carrier is None else (carrier,)),
        )
    }
    relevant_quantities = {
        item.quantity_id for item in ir.quantities if item.quantity_id in relevant
    }
    allowed_queries = {
        tension_table[0].quantity_id,
        tension_hanging[0].quantity_id,
        table_acceleration.quantity_id,
        hanging_acceleration.quantity_id,
    }
    query_quantity = quantity_by_id.get(query_quantity_id or "")
    if (
        relevant_quantities != expected_quantities
        or query_quantity_id not in allowed_queries
        or query_quantity is None
        or query.target.subject_id != query_quantity.subject_id
        or query.target.point_id != query_quantity.point_id
        or query.target.frame_id != frame.frame_id
        or query.target.interval_id != interval.interval_id
        or query.target.event_id is not None
        or query.target.component is not query_quantity.component
        or query.target.direction != query_quantity.direction
        or query.shape is not QuantityShape.scalar
        or query.output_dimension != query_quantity.dimension
        or not query.evidence_refs
        or any(item.constraint_id in relevant for item in ir.constraints)
    ):
        return None, failure("contains extra quantities, client equations, or an inexact query binding")

    return _FixedPulleyHorizontalContactProfile(
        friction_state_id=friction_state.state_condition_id
    ), None


@dataclass(frozen=True)
class _FixedPulleyInclineContactProfile:
    friction_state_id: str


def _fixed_pulley_incline_contact_contract(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    relevant: set[str],
    approved_assumption_ids: frozenset[str],
) -> tuple[_FixedPulleyInclineContactProfile | None, CompilerIssue | None]:
    """Close the exact two-frame incline/hanging fixed-pulley template."""

    entities = tuple(item for item in ir.entities if item.entity_id in relevant)
    entity_by_id = {item.entity_id: item for item in entities}
    primitive_ids = {
        primitive: tuple(
            item.entity_id
            for item in entities
            if item.primitive.value == primitive
        )
        for primitive in (
            "particle",
            "incline",
            "rope",
            "pulley",
            "environment",
        )
    }
    interactions = tuple(
        item for item in ir.interactions if item.interaction_id in relevant
    )
    contacts = tuple(
        item for item in interactions if item.kind.value == "contact"
    )
    rope_interactions = tuple(
        item for item in interactions if item.kind.value == "rope_tension"
    )
    wraps = tuple(
        item
        for item in ir.geometry
        if item.relation_id in relevant and item.kind.value == "wraps"
    )
    angles = tuple(
        item
        for item in ir.geometry
        if item.relation_id in relevant and item.kind.value == "angle"
    )
    rope_force_query = (
        query.target.role is QuantityRole.force
        and query.target.target_quantity_id is not None
        and any(
            query.target.target_quantity_id in item.quantity_ids
            for item in rope_interactions
        )
    )
    # Activate from the distinctive primitive signature before consulting any
    # relation that the exact contract must require.  Otherwise deleting two
    # complementary topology records can erase the recognizer's own signal and
    # let the remaining gravity/contact fragment fall through to generic laws.
    candidate = all(
        primitive_ids[primitive]
        for primitive in (
            "particle",
            "incline",
            "rope",
            "pulley",
            "environment",
        )
    )
    if not candidate:
        return None, None

    def failure(detail: str, referenced_id: str | None = None) -> CompilerIssue:
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            f"fixed-pulley incline/hanging topology {detail}",
            f"queries.{query.query_id}",
            referenced_id or query.query_id,
        )

    query_entity = entity_by_id.get(query.target.subject_id)
    if query_entity is None:
        return None, None
    if query.shape is not QuantityShape.scalar:
        return None, failure(
            "allows only scalar local-body acceleration or rope-tension queries",
            query.query_id,
        )
    if query_entity.primitive.value != "particle":
        return None, failure(
            "keeps every non-particle topology quantity non-queryable",
            query.target.target_quantity_id or query.query_id,
        )
    if query.target.role not in {QuantityRole.acceleration, QuantityRole.force}:
        return None, failure(
            "allows only local-body acceleration or rope-tension queries",
            query.target.target_quantity_id or query.query_id,
        )
    if query.target.role is QuantityRole.force and not rope_force_query:
        return None, failure(
            "keeps internal contact and projection forces non-queryable",
            query.target.target_quantity_id or query.query_id,
        )

    expected_counts = {
        "particle": 2,
        "incline": 1,
        "rope": 1,
        "pulley": 1,
        "environment": 1,
    }
    if (
        {key: len(value) for key, value in primitive_ids.items()}
        != expected_counts
        or len(entities) != 6
        or any(
            not item.evidence_refs or item.component_of_entity_id is not None
            for item in entities
        )
    ):
        return None, failure(
            "requires exactly two particles, one incline, one rope, one pulley, and one environment"
        )
    particle_ids = set(primitive_ids["particle"])
    incline_id = primitive_ids["incline"][0]
    rope_id = primitive_ids["rope"][0]
    pulley_id = primitive_ids["pulley"][0]
    environment_id = primitive_ids["environment"][0]

    frames = tuple(
        item for item in ir.reference_frames if item.frame_id in relevant
    )
    if len(frames) != 2:
        return None, failure("requires exact parent-world and incline frames")
    world_frames = tuple(
        item for item in frames if item.frame_type.value == "cartesian_2d"
    )
    incline_frames = tuple(
        item for item in frames if item.frame_type.value == "tangential_normal"
    )
    if len(world_frames) != 1 or len(incline_frames) != 1:
        return None, failure("requires one Cartesian parent and one tangential/normal frame")
    world_frame = world_frames[0]
    incline_frame = incline_frames[0]

    def axis_signature(frame: object) -> set[tuple[object, ...]]:
        return {
            (
                item.axis.value,
                getattr(item.direction, "kind", None),
                getattr(item.direction, "frame_id", None),
                getattr(getattr(item.direction, "axis", None), "value", None),
                getattr(item.direction, "sign", None),
            )
            for item in getattr(frame, "axes", ())
        }

    if (
        getattr(world_frame.origin, "kind", None) != "world"
        or world_frame.parent_frame_id is not None
        or world_frame.translating_with_entity_id is not None
        or world_frame.rotating_about_point_id is not None
        or world_frame.generalized_coordinate_symbol_ids
        or not world_frame.evidence_refs
        or len(world_frame.axes) != 2
        or axis_signature(world_frame)
        != {
            ("x", "axis", world_frame.frame_id, "x", 1),
            ("y", "axis", world_frame.frame_id, "y", 1),
        }
        or getattr(incline_frame.origin, "kind", None) != "entity"
        or getattr(incline_frame.origin, "entity_id", None) != incline_id
        or incline_frame.parent_frame_id != world_frame.frame_id
        or incline_frame.translating_with_entity_id is not None
        or incline_frame.rotating_about_point_id is not None
        or incline_frame.generalized_coordinate_symbol_ids
        or not incline_frame.evidence_refs
        or len(incline_frame.axes) != 2
        or axis_signature(incline_frame)
        != {
            ("tangent", "axis", incline_frame.frame_id, "tangent", 1),
            ("normal", "axis", incline_frame.frame_id, "normal", 1),
        }
    ):
        return None, failure("requires exact evidenced +x/+y and +tangent/+normal axes")

    intervals = tuple(
        item for item in ir.motion_intervals if item.interval_id in relevant
    )
    if len(intervals) != 1:
        return None, failure("requires one evidenced motion interval")
    interval = intervals[0]
    if (
        interval.frame_id is not None
        or interval.start_event_id is not None
        or interval.end_event_id is not None
        or len(interval.subject_ids) != len(entity_by_id)
        or set(interval.subject_ids) != set(entity_by_id)
        or not interval.evidence_refs
        or any(item.event_id in relevant for item in ir.events)
    ):
        return None, failure(
            "requires one exact event-free unframed interval containing the complete topology",
            interval.interval_id,
        )

    if len(contacts) != 1:
        return None, failure("requires one incline contact")
    contact = contacts[0]
    incline_body_ids = set(contact.participant_ids) & particle_ids
    if (
        len(contact.participant_ids) != 2
        or len(set(contact.participant_ids)) != 2
        or incline_id not in contact.participant_ids
        or len(incline_body_ids) != 1
        or len(contact.point_ids) != 1
        or contact.frame_id != incline_frame.frame_id
        or contact.interval_id != interval.interval_id
        or contact.event_id is not None
        or not contact.evidence_refs
    ):
        return None, failure("requires one exact evidenced particle/incline contact", contact.interaction_id)
    incline_body_id = next(iter(incline_body_ids))
    hanging_body_id = next(iter(particle_ids - {incline_body_id}))
    points = tuple(item for item in ir.points if item.point_id in relevant)
    if len(points) != 1:
        return None, failure("requires one evidenced contact point")
    contact_point = points[0]
    if (
        contact_point.point_id != contact.point_ids[0]
        or contact_point.role.value != "contact"
        or contact_point.owner_entity_id != incline_body_id
        or contact_point.frame_id != incline_frame.frame_id
        or not contact_point.evidence_refs
    ):
        return None, failure("has an invalid contact-point binding", contact_point.point_id)

    geometry = tuple(item for item in ir.geometry if item.relation_id in relevant)
    attached = tuple(item for item in geometry if item.kind.value == "attached")
    if (
        len(geometry) != 4
        or len(wraps) != 1
        or len(angles) != 1
        or len(attached) != 2
        or any(
            item.expression is not None
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            for item in geometry
        )
        or len(wraps[0].participant_ids) != 2
        or set(wraps[0].participant_ids) != {rope_id, pulley_id}
        or len(wraps[0].quantity_ids) != 2
        or len(set(wraps[0].quantity_ids)) != 2
        or wraps[0].interval_id != interval.interval_id
        or {frozenset(item.participant_ids) for item in attached}
        != {frozenset((rope_id, item)) for item in particle_ids}
        or any(
            len(item.quantity_ids) != 4
            or len(set(item.quantity_ids)) != 4
            or item.interval_id != interval.interval_id
            for item in attached
        )
        or len(angles[0].participant_ids) != 2
        or set(angles[0].participant_ids) != {incline_id, environment_id}
        or len(angles[0].quantity_ids) != 1
        or angles[0].interval_id is not None
    ):
        return None, failure(
            "requires one angle, one wrap, and two exact evidenced rope attachments",
            rope_id,
        )

    states = tuple(
        item for item in ir.state_conditions if item.state_condition_id in relevant
    )
    if any(
        item.interval_id != interval.interval_id
        or item.event_id is not None
        or item.expression is not None
        or not item.evidence_refs
        or len(item.quantity_ids) != len(set(item.quantity_ids))
        for item in states
    ):
        return None, failure("contains an invalid topology or contact state")
    rope_states = tuple(
        item for item in states
        if item.subject_id == rope_id and item.kind.value == "rope"
    )
    pulley_states = tuple(
        item for item in states
        if item.subject_id == pulley_id and item.kind.value == "motion"
    )
    contact_states = tuple(
        item for item in states
        if item.subject_id == incline_body_id and item.kind.value == "contact"
    )
    incline_states = tuple(
        item for item in states
        if item.subject_id == incline_id and item.kind.value == "motion"
    )
    friction_states = tuple(
        item for item in states
        if item.subject_id == incline_body_id and item.kind.value == "friction"
    )
    body_motion_states = tuple(
        item for item in states
        if item.subject_id == incline_body_id and item.kind.value == "motion"
    )
    if (
        len(rope_states) != 1
        or rope_states[0].state.value != "taut"
        or rope_states[0].quantity_ids
        or len(pulley_states) != 1
        or pulley_states[0].state.value != "at_rest"
        or pulley_states[0].quantity_ids
        or len(contact_states) != 1
        or contact_states[0].state.value != "touching"
        or len(incline_states) != 1
        or incline_states[0].state.value != "at_rest"
        or incline_states[0].quantity_ids
        or len(friction_states) != 1
        or friction_states[0].state.value not in {"inactive", "sticking", "sliding"}
    ):
        return None, failure("requires exact evidenced rope, pulley, contact, and friction states")
    friction_state = friction_states[0]
    regime = friction_state.state.value
    if (
        len(states) != (5 if regime == "inactive" else 6)
        or (regime == "inactive" and body_motion_states)
        or (regime != "inactive" and len(body_motion_states) != 1)
    ):
        return None, failure("contains extra or missing regime state", friction_state.state_condition_id)

    scoped_assumptions = tuple(
        item for item in ir.assumptions if item.assumption_id in relevant
    )
    expected_assumptions = {
        ("massless_rope", rope_id),
        ("inextensible_rope", rope_id),
        ("ideal_massless_frictionless_pulley", pulley_id),
        ("fixed_pulley", pulley_id),
        *((
            ("acceleration_not_opposite_motion", incline_body_id),
        ) if regime == "sliding" else ()),
    }
    if (
        len(scoped_assumptions) != len(expected_assumptions)
        or {(item.kind, item.subject_id) for item in scoped_assumptions}
        != expected_assumptions
        or any(
            item.disposition is not AssumptionDisposition.approved
            or item.assumption_id not in approved_assumption_ids
            or item.interval_id != interval.interval_id
            or item.proposed_role is not None
            or item.proposed_value is not None
            or item.proposed_unit is not None
            or not item.evidence_refs
            for item in scoped_assumptions
        )
    ):
        return None, failure(
            "requires exact externally approved evidenced rope, pulley, and motion assumptions",
            rope_id,
        )

    if len(interactions) != 4 or len(rope_interactions) != 1:
        return None, failure("requires two gravity, one contact, and one rope interaction")
    gravity_interactions = tuple(
        item for item in interactions if item.kind.value == "gravity"
    )
    rope_interaction = rope_interactions[0]
    incline_gravity = tuple(
        item
        for item in gravity_interactions
        if set(item.participant_ids) == {incline_body_id, environment_id}
    )
    hanging_gravity = tuple(
        item
        for item in gravity_interactions
        if set(item.participant_ids) == {hanging_body_id, environment_id}
    )
    if (
        len(gravity_interactions) != 2
        or len(incline_gravity) != 1
        or len(hanging_gravity) != 1
        or incline_gravity[0].frame_id != incline_frame.frame_id
        or len(incline_gravity[0].quantity_ids) != 4
        or hanging_gravity[0].frame_id != world_frame.frame_id
        or len(hanging_gravity[0].quantity_ids) != 3
        or any(
            len(item.participant_ids) != 2
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.point_ids
            or len(item.quantity_ids) != len(set(item.quantity_ids))
            or not item.evidence_refs
            for item in gravity_interactions
        )
        or len(rope_interaction.participant_ids) != 4
        or set(rope_interaction.participant_ids)
        != particle_ids | {rope_id, pulley_id}
        or rope_interaction.point_ids
        or rope_interaction.frame_id is not None
        or rope_interaction.interval_id != interval.interval_id
        or rope_interaction.event_id is not None
        or len(rope_interaction.quantity_ids) != 6
        or len(set(rope_interaction.quantity_ids)) != 6
        or not rope_interaction.evidence_refs
    ):
        return None, failure("has incomplete or ambiguous interaction cardinality")

    quantities = {
        item.quantity_id: item
        for item in ir.quantities
        if item.quantity_id in relevant
    }

    def one_linked(interaction: object, role: QuantityRole, subject_id: str):
        linked_ids = set(getattr(interaction, "quantity_ids", ()))
        values = tuple(
            item
            for item in quantities.values()
            if item.quantity_id in linked_ids
            and item.role is role
            and item.subject_id == subject_id
        )
        return values[0] if len(values) == 1 else None

    mass_incline = one_linked(incline_gravity[0], QuantityRole.mass, incline_body_id)
    mass_hanging = one_linked(hanging_gravity[0], QuantityRole.mass, hanging_body_id)
    gravity_a = one_linked(incline_gravity[0], QuantityRole.gravity, environment_id)
    gravity_b = one_linked(hanging_gravity[0], QuantityRole.gravity, environment_id)
    angle = quantities.get(angles[0].quantity_ids[0])

    def exact_known(item: object, *, positive: bool) -> bool:
        value = getattr(item, "si_value", None)
        return (
            item is not None
            and item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.provenance is Provenance.explicit_source
            and bool(item.evidence_refs)
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id is None
            and item.event_id is None
            and item.direction is None
            and item.component.value in {"magnitude", "unspecified"}
            and type(value) is float
            and math.isfinite(value)
            and (value > 0.0 if positive else value >= 0.0)
        )

    known_positive = (mass_incline, mass_hanging, gravity_a)
    bad_positive = next(
        (
            item for item in known_positive
            if item is not None
            and type(getattr(item, "si_value", None)) is float
            and getattr(item, "si_value") <= 0.0
        ),
        None,
    )
    if bad_positive is not None:
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "incline/hanging masses and gravity must be positive",
            f"quantities.{bad_positive.quantity_id}.si_value",
            bad_positive.quantity_id,
        )
    if (
        any(item is None or not exact_known(item, positive=True) for item in known_positive)
        or gravity_b is not gravity_a
        or mass_incline.role is not QuantityRole.mass
        or mass_hanging.role is not QuantityRole.mass
        or gravity_a.role is not QuantityRole.gravity
    ):
        return None, failure("requires exact source-backed masses and one shared gravity magnitude")
    if (
        angle is None
        or angle.role is not QuantityRole.angle
        or angle.subject_id != incline_id
        or angle.shape is not QuantityShape.scalar
        or angle.symbol_id is None
        or angle.provenance is not Provenance.explicit_source
        or not angle.evidence_refs
        or angle.point_id is not None
        or angle.frame_id is not None
        or angle.interval_id is not None
        or angle.event_id is not None
        or angle.direction is not None
        or angle.component.value not in {"magnitude", "unspecified"}
        or type(angle.si_value) is not float
        or not math.isfinite(angle.si_value)
        or angle.dimension != DimensionVector.dimensionless()
    ):
        return None, failure("requires one exact source-backed incline angle", incline_id)
    if not 0.0 <= angle.si_value < math.pi / 2.0:
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "incline/hanging projection angle must be in [0, pi/2)",
            f"quantities.{angle.quantity_id}.si_value",
            angle.quantity_id,
        )

    def exact_unknown_axis(
        item: object,
        *,
        role: QuantityRole,
        subject_id: str,
        point_id: str | None,
        frame_id: str,
        component: str,
        sign: int | None,
    ) -> bool:
        observed_sign = getattr(getattr(item, "direction", None), "sign", None)
        return (
            item is not None
            and item.role is role
            and item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.si_value is None
            and item.provenance in {Provenance.inferred, Provenance.unknown}
            and bool(item.evidence_refs)
            and item.subject_id == subject_id
            and item.point_id == point_id
            and item.frame_id == frame_id
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.component.value == component
            and observed_sign in {-1, 1}
            and (sign is None or observed_sign == sign)
            and _exact_axis_direction(
                item,
                frame_id=frame_id,
                axis=("tangent" if component == "tangential" else component),
                sign=observed_sign,
            )
        )

    incline_linked = tuple(quantities.get(item) for item in incline_gravity[0].quantity_ids)
    hanging_linked = tuple(quantities.get(item) for item in hanging_gravity[0].quantity_ids)
    gravity_tangent = next(
        (
            item for item in incline_linked
            if item is not None
            and item.role is QuantityRole.force
            and item.component.value == "tangential"
        ),
        None,
    )
    gravity_normal = next(
        (
            item for item in incline_linked
            if item is not None
            and item.role is QuantityRole.force
            and item.component.value == "normal"
        ),
        None,
    )
    hanging_weight = next(
        (
            item for item in hanging_linked
            if item is not None and item.role is QuantityRole.force
        ),
        None,
    )
    rope_values = tuple(quantities.get(item) for item in rope_interaction.quantity_ids)
    incline_tensions = tuple(
        item for item in rope_values
        if item is not None and item.role is QuantityRole.force and item.subject_id == incline_body_id
    )
    hanging_tensions = tuple(
        item for item in rope_values
        if item is not None and item.role is QuantityRole.force and item.subject_id == hanging_body_id
    )
    rope_tension_magnitudes = tuple(
        item for item in rope_values
        if item is not None
        and item.role is QuantityRole.force
        and item.subject_id == rope_id
    )
    rope_acceleration_coordinates = tuple(
        item for item in rope_values
        if item is not None
        and item.role is QuantityRole.acceleration
        and item.subject_id == rope_id
    )
    contact_values = tuple(quantities.get(item) for item in contact.quantity_ids)
    normal_values = tuple(
        item for item in contact_values
        if item is not None and item.role is QuantityRole.force and item.component.value == "normal"
    )
    normal_accelerations = tuple(
        item for item in contact_values
        if item is not None and item.role is QuantityRole.acceleration and item.component.value == "normal"
    )
    friction_values = tuple(
        item for item in contact_values
        if item is not None and item.role is QuantityRole.force and item.component.value == "tangential"
    )
    coefficients = tuple(
        item for item in contact_values
        if item is not None and item.role is QuantityRole.coefficient_friction
    )
    accelerations = tuple(
        item for item in quantities.values()
        if item.role is QuantityRole.acceleration and item.subject_id in particle_ids
    )
    incline_tangent_accelerations = tuple(
        item for item in accelerations
        if item.subject_id == incline_body_id and item.component.value == "tangential"
    )
    incline_normal_accelerations = tuple(
        item for item in accelerations
        if item.subject_id == incline_body_id and item.component.value == "normal"
    )
    hanging_accelerations = tuple(
        item for item in accelerations
        if item.subject_id == hanging_body_id and item.component.value == "y"
    )
    if (
        any(item is None for item in (*incline_linked, *hanging_linked, *rope_values, *contact_values))
        or len(incline_tensions) != 1
        or len(hanging_tensions) != 1
        or len(rope_tension_magnitudes) != 1
        or len(rope_acceleration_coordinates) != 1
        or len(normal_values) != 1
        or len(normal_accelerations) != 1
        or len(accelerations) != 3
        or len(incline_tangent_accelerations) != 1
        or len(incline_normal_accelerations) != 1
        or len(hanging_accelerations) != 1
        or incline_normal_accelerations[0] is not normal_accelerations[0]
    ):
        return None, failure("requires exact incline/hanging force and acceleration components")
    tension_incline = incline_tensions[0]
    tension_hanging = hanging_tensions[0]
    rope_tension = rope_tension_magnitudes[0]
    rope_acceleration = rope_acceleration_coordinates[0]
    normal = normal_values[0]
    normal_acceleration = normal_accelerations[0]
    acceleration_incline = incline_tangent_accelerations[0]
    acceleration_hanging = hanging_accelerations[0]
    if (
        not exact_unknown_axis(
            gravity_tangent,
            role=QuantityRole.force,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component="tangential",
            sign=1,
        )
        or not exact_unknown_axis(
            gravity_normal,
            role=QuantityRole.force,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component="normal",
            sign=-1,
        )
        or not exact_unknown_axis(
            hanging_weight,
            role=QuantityRole.force,
            subject_id=hanging_body_id,
            point_id=None,
            frame_id=world_frame.frame_id,
            component="y",
            sign=1,
        )
        or not exact_unknown_axis(
            tension_incline,
            role=QuantityRole.force,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component="tangential",
            sign=-1,
        )
        or not exact_unknown_axis(
            tension_hanging,
            role=QuantityRole.force,
            subject_id=hanging_body_id,
            point_id=None,
            frame_id=world_frame.frame_id,
            component="y",
            sign=-1,
        )
        or not exact_unknown_axis(
            normal,
            role=QuantityRole.force,
            subject_id=incline_body_id,
            point_id=contact_point.point_id,
            frame_id=incline_frame.frame_id,
            component="normal",
            sign=1,
        )
        or not exact_unknown_axis(
            normal_acceleration,
            role=QuantityRole.acceleration,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component="normal",
            sign=1,
        )
        or not exact_unknown_axis(
            acceleration_incline,
            role=QuantityRole.acceleration,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component="tangential",
            sign=None,
        )
        or not exact_unknown_axis(
            acceleration_hanging,
            role=QuantityRole.acceleration,
            subject_id=hanging_body_id,
            point_id=None,
            frame_id=world_frame.frame_id,
            component="y",
            sign=None,
        )
        or acceleration_incline.direction.sign != -acceleration_hanging.direction.sign
    ):
        return None, failure("requires exact opposed branch-coordinate directions", rope_id)

    def exact_unknown_rope_coordinate(
        item: object,
        *,
        role: QuantityRole,
        dimension: DimensionVector,
    ) -> bool:
        return (
            item is not None
            and item.role is role
            and item.subject_id == rope_id
            and item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.si_value is None
            and item.provenance in {Provenance.inferred, Provenance.unknown}
            and bool(item.evidence_refs)
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.component.value in {"magnitude", "unspecified"}
            and item.direction is None
            and item.dimension == dimension
        )

    if (
        not exact_unknown_rope_coordinate(
            rope_tension,
            role=QuantityRole.force,
            dimension=tension_incline.dimension,
        )
        or not exact_unknown_rope_coordinate(
            rope_acceleration,
            role=QuantityRole.acceleration,
            dimension=acceleration_incline.dimension,
        )
        or set(rope_interaction.quantity_ids)
        != {
            tension_incline.quantity_id,
            tension_hanging.quantity_id,
            rope_tension.quantity_id,
            acceleration_incline.quantity_id,
            acceleration_hanging.quantity_id,
            rope_acceleration.quantity_id,
        }
        or set(wraps[0].quantity_ids)
        != {rope_tension.quantity_id, rope_acceleration.quantity_id}
        or {
            frozenset(item.quantity_ids)
            for item in attached
        }
        != {
            frozenset(
                (
                    tension_incline.quantity_id,
                    acceleration_incline.quantity_id,
                    rope_tension.quantity_id,
                    rope_acceleration.quantity_id,
                )
            ),
            frozenset(
                (
                    tension_hanging.quantity_id,
                    acceleration_hanging.quantity_id,
                    rope_tension.quantity_id,
                    rope_acceleration.quantity_id,
                )
            ),
        }
    ):
        return None, failure("requires exact unframed rope coordinates and attachment transforms", rope_id)

    friction = friction_values[0] if len(friction_values) == 1 else None
    coefficient = coefficients[0] if len(coefficients) == 1 else None
    carrier = None
    if regime == "inactive":
        if (
            len(contact_values) != 2
            or friction is not None
            or coefficient is not None
            or friction_state.quantity_ids
        ):
            return None, failure("has an invalid frictionless contact profile")
    else:
        if (
            len(contact_values) != 4
            or friction is None
            or coefficient is None
            or not exact_known(coefficient, positive=False)
            or coefficient.role is not QuantityRole.coefficient_friction
            or coefficient.subject_id != incline_body_id
            or coefficient.dimension != DimensionVector.dimensionless()
            or set(friction_state.quantity_ids)
            != {friction.quantity_id, normal.quantity_id, coefficient.quantity_id}
            or len(friction_state.quantity_ids) != 3
            or not exact_unknown_axis(
                friction,
                role=QuantityRole.force,
                subject_id=incline_body_id,
                point_id=contact_point.point_id,
                frame_id=incline_frame.frame_id,
                component="tangential",
                sign=None,
            )
        ):
            return None, failure("has an invalid active-friction contact profile")
        motion_state = body_motion_states[0]
        if regime == "sticking":
            hanging_drive = mass_hanging.si_value * gravity_a.si_value
            incline_drive = (
                mass_incline.si_value
                * gravity_a.si_value
                * math.sin(angle.si_value)
            )
            static_drive = hanging_drive - incline_drive
            static_drive_is_zero = math.isclose(
                static_drive,
                0.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-12 * max(1.0, abs(hanging_drive), abs(incline_drive)),
            )
            expected_friction_sign = (
                None
                if static_drive_is_zero
                else 1 if static_drive > 0.0 else -1
            )
            if (
                motion_state.state.value != "at_rest"
                or motion_state.quantity_ids
                or (
                    expected_friction_sign is not None
                    and friction.direction.sign != expected_friction_sign
                )
            ):
                return None, failure("requires an exact evidenced sticking state")
        else:
            if motion_state.state.value != "moving" or len(motion_state.quantity_ids) != 1:
                return None, failure("requires an exact evidenced sliding state")
            carrier = quantities.get(motion_state.quantity_ids[0])
            carrier_sign = getattr(getattr(carrier, "direction", None), "sign", None)
            if (
                carrier is None
                or carrier.role is not QuantityRole.velocity
                or carrier.shape is not QuantityShape.scalar
                or carrier.dimension != DimensionVector(length=1, time=-1)
                or carrier.symbol_id is None
                or carrier.subject_id != incline_body_id
                or carrier.point_id is not None
                or carrier.frame_id != incline_frame.frame_id
                or carrier.interval_id != interval.interval_id
                or carrier.event_id is not None
                or carrier.component.value != "tangential"
                or carrier.provenance is not Provenance.explicit_source
                or type(carrier.si_value) is not float
                or not math.isfinite(carrier.si_value)
                or carrier.si_value <= 0.0
                or not carrier.evidence_refs
                or carrier_sign not in {-1, 1}
                or not _exact_axis_direction(
                    carrier,
                    frame_id=incline_frame.frame_id,
                    axis="tangent",
                    sign=carrier_sign,
                )
                or friction.direction.sign != -carrier_sign
            ):
                return None, failure("requires friction opposite one positive typed velocity carrier")

    if (
        set(contact_states[0].quantity_ids)
        != {normal.quantity_id, normal_acceleration.quantity_id}
        or len(contact_states[0].quantity_ids) != 2
        or mass_incline.dimension.plus(gravity_a.dimension) != gravity_tangent.dimension
        or gravity_tangent.dimension != gravity_normal.dimension
        or gravity_tangent.dimension != hanging_weight.dimension
        or gravity_tangent.dimension != tension_incline.dimension
        or gravity_tangent.dimension != tension_hanging.dimension
        or gravity_tangent.dimension != normal.dimension
        or mass_incline.dimension.plus(acceleration_incline.dimension)
        != gravity_tangent.dimension
        or mass_incline.dimension.plus(normal_acceleration.dimension)
        != normal.dimension
        or mass_hanging.dimension.plus(acceleration_hanging.dimension)
        != hanging_weight.dimension
        or acceleration_incline.dimension != gravity_a.dimension
        or acceleration_hanging.dimension != gravity_a.dimension
        or normal_acceleration.dimension != gravity_a.dimension
        or (friction is not None and friction.dimension != normal.dimension)
    ):
        return None, failure("contains a dimensionally inconsistent force balance")

    expected_quantities = {
        item.quantity_id
        for item in (
            mass_incline,
            mass_hanging,
            gravity_a,
            angle,
            gravity_tangent,
            gravity_normal,
            hanging_weight,
            tension_incline,
            tension_hanging,
            normal,
            normal_acceleration,
            acceleration_incline,
            acceleration_hanging,
            rope_tension,
            rope_acceleration,
            *(() if friction is None else (friction,)),
            *(() if coefficient is None else (coefficient,)),
            *(() if carrier is None else (carrier,)),
        )
    }
    query_quantity = quantities.get(query.target.target_quantity_id or "")
    allowed_query_quantities = (
        tension_incline,
        tension_hanging,
        acceleration_incline,
        acceleration_hanging,
    )
    if (
        set(quantities) != expected_quantities
        or query_quantity not in allowed_query_quantities
        or query.target.role is not query_quantity.role
        or query.target.subject_id != query_quantity.subject_id
        or query.target.point_id != query_quantity.point_id
        or query.target.frame_id != query_quantity.frame_id
        or query.target.interval_id != interval.interval_id
        or query.target.event_id is not None
        or query.target.component is not query_quantity.component
        or query.target.direction != query_quantity.direction
        or not query.evidence_refs
        or any(item.constraint_id in relevant for item in ir.constraints)
        or any(
            item.subject_id == pulley_id and item.quantity_id in relevant
            for item in ir.quantities
        )
    ):
        return None, failure("contains extra client equations, quantities, or an inexact query binding")
    return _FixedPulleyInclineContactProfile(
        friction_state_id=friction_state.state_condition_id
    ), None


def _complete_inertial_pulley_profile(
    ir: MechanicsProblemIRV1,
    relevant: set[str],
    approved_assumption_ids: frozenset[str],
) -> bool:
    """Recognize only the closed typed inputs used by pulley Newton-Euler."""
    primitive = {
        item.entity_id: item.primitive.value
        for item in ir.entities
        if item.entity_id in relevant
    }
    interactions = tuple(
        item for item in ir.interactions
        if item.interaction_id in relevant and item.kind.value == "rope_tension"
    )
    if len(interactions) != 1 or not interactions[0].evidence_refs:
        return False
    interaction = interactions[0]
    rope_ids = tuple(item for item in interaction.participant_ids if primitive.get(item) == "rope")
    pulley_ids = tuple(item for item in interaction.participant_ids if primitive.get(item) == "pulley")
    moving_types = {"particle", "rigid_body", "body_component"}
    moving_ids = tuple(
        item for item in interaction.participant_ids if primitive.get(item) in moving_types
    )
    if (
        interaction.frame_id is None
        or interaction.interval_id is None
        or interaction.event_id is not None
        or interaction.point_ids
        or len(interaction.participant_ids) != len(set(interaction.participant_ids))
        or len(rope_ids) != 1
        or len(pulley_ids) != 1
        or len(moving_ids) != 2
        or set(interaction.participant_ids) != {*rope_ids, *pulley_ids, *moving_ids}
        or len(interaction.quantity_ids) != len(set(interaction.quantity_ids))
        or len(interaction.quantity_ids) != 2
    ):
        return False
    rope_id, pulley_id = rope_ids[0], pulley_ids[0]
    inextensible = any(
        item.assumption_id in relevant
        and item.assumption_id in approved_assumption_ids
        and item.disposition is AssumptionDisposition.approved
        and item.kind == "inextensible_rope"
        and item.subject_id == rope_id
        and item.interval_id in {None, interaction.interval_id}
        and bool(item.evidence_refs)
        for item in ir.assumptions
    )
    wraps = tuple(
        item for item in ir.geometry
        if item.relation_id in relevant and item.kind.value == "wraps"
    )
    if not inextensible or len(wraps) != 1:
        return False
    wrap = wraps[0]
    if (
        set(wrap.participant_ids) != {rope_id, pulley_id}
        or len(wrap.participant_ids) != 2
        or wrap.interval_id not in {None, interaction.interval_id}
        or wrap.expression is not None
        or not wrap.evidence_refs
    ):
        return False
    quantities = tuple(item for item in ir.quantities if item.quantity_id in relevant)
    pulley_quantities = {
        role: tuple(
            item for item in quantities
            if item.subject_id == pulley_id and item.role is role
        )
        for role in (
            QuantityRole.moment_of_inertia,
            QuantityRole.radius,
            QuantityRole.angular_acceleration,
        )
    }
    inertias = pulley_quantities[QuantityRole.moment_of_inertia]
    radii = pulley_quantities[QuantityRole.radius]
    angular = pulley_quantities[QuantityRole.angular_acceleration]

    def positive_authorized_known(item: object) -> bool:
        authority_ref = {
            Provenance.explicit_source: getattr(item, "evidence_refs", ()),
            Provenance.user_correction: getattr(item, "correction_id", None),
            Provenance.server_default: getattr(item, "assumption_policy_ref", None),
        }.get(getattr(item, "provenance", None))
        value = getattr(item, "si_value", None)
        return (
            bool(authority_ref)
            and item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and type(value) is float
            and math.isfinite(value)
            and value > 0.0
            and item.point_id is None
            and item.frame_id in {None, interaction.frame_id}
            and item.interval_id in {None, interaction.interval_id}
            and item.event_id is None
            and item.component.value in {"magnitude", "unspecified"}
            and item.direction is None
        )
    if (
        len(inertias) != 1
        or len(radii) != 1
        or len(angular) != 1
        or not positive_authorized_known(inertias[0])
        or not positive_authorized_known(radii[0])
        or tuple(wrap.quantity_ids) != (radii[0].quantity_id,)
        or angular[0].shape is not QuantityShape.scalar
        or angular[0].symbol_id is None
        or angular[0].frame_id != interaction.frame_id
        or angular[0].interval_id != interaction.interval_id
        or angular[0].event_id != interaction.event_id
        or angular[0].point_id is not None
        or angular[0].si_value is not None
        or angular[0].provenance not in {Provenance.inferred, Provenance.unknown}
    ):
        return False
    quantity_by_id = {item.quantity_id: item for item in quantities}
    forces = tuple(quantity_by_id.get(item) for item in interaction.quantity_ids)
    if not all(item is not None for item in forces):
        return False

    def exact_axis_component(item: object) -> bool:
        component = item.component.value
        sign = getattr(getattr(item, "direction", None), "sign", None)
        return (
            component in {"x", "y", "z"}
            and sign in {-1, 1}
            and _exact_axis_direction(
                item,
                frame_id=interaction.frame_id,
                axis=component,
                sign=sign,
            )
        )

    return (
        all(item.role is QuantityRole.force for item in forces)
        and {item.subject_id for item in forces} == set(moving_ids)
        and all(
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.si_value is None
            and item.provenance in {Provenance.inferred, Provenance.unknown}
            and item.point_id is None
            and item.frame_id == interaction.frame_id
            and item.interval_id == interaction.interval_id
            and item.event_id == interaction.event_id
            and exact_axis_component(item)
            for item in forces
        )
        and forces[0].component is forces[1].component
        and _direction_key(forces[0]) == _direction_key(forces[1])
        and forces[0].dimension == forces[1].dimension
        and angular[0].component is forces[0].component
        and exact_axis_component(angular[0])
        and _direction_key(angular[0]) == _direction_key(forces[0])
        and forces[0].dimension.plus(radii[0].dimension) == inertias[0].dimension.plus(angular[0].dimension)
    )


@dataclass(frozen=True)
class _MassivePulleyAtwoodProfile:
    fixed_axis_angular_quantity_ids: frozenset[str]


@dataclass(frozen=True)
class _Collision1DProfile:
    system_id: str
    participant_ids: frozenset[str]


def _collision_1d_candidate(ir: MechanicsProblemIRV1) -> bool:
    """Recognize redundant typed impact signals without consulting the query."""

    has_system_topology = (
        any(item.primitive is EntityPrimitive.system for item in ir.entities)
        or any(item.component_of_entity_id is not None for item in ir.entities)
        or len(ir.entities) >= 3
    )
    if not has_system_topology:
        # Preserve the deliberately broad, evidence-less Stage 0--4 collision
        # compiler fixture.  The product profile below is the system-scoped
        # contract and must not retroactively reinterpret that low-level test.
        return False
    collision_signals = (
        any(item.kind is InteractionKind.collision for item in ir.interactions),
        any(item.kind.value == "collision_start" for item in ir.events)
        or any(item.kind.value == "collision_end" for item in ir.events),
        any(
            item.role is QuantityRole.coefficient_restitution
            for item in ir.quantities
        ),
    )
    return any(collision_signals)


def _collision_1d_contract(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    approved_assumption_ids: Collection[str],
) -> tuple[_Collision1DProfile | None, CompilerIssue | None]:
    """Close one evidenced, system-scoped, direct one-dimensional impact."""

    if not _collision_1d_candidate(ir):
        return None, None

    def failure(detail: str, referenced_id: str | None = None) -> CompilerIssue:
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            f"one-dimensional collision topology {detail}",
            f"queries.{query.query_id}",
            referenced_id or query.query_id,
        )

    systems = tuple(
        item for item in ir.entities if item.primitive is EntityPrimitive.system
    )
    particles = tuple(
        item for item in ir.entities if item.primitive is EntityPrimitive.particle
    )
    if (
        len(ir.entities) != 3
        or len(systems) != 1
        or len(particles) != 2
        or systems[0].component_of_entity_id is not None
        or any(
            item.component_of_entity_id != systems[0].entity_id
            for item in particles
        )
        or any(not item.evidence_refs for item in ir.entities)
    ):
        return None, failure(
            "requires one evidenced system containing exactly two evidenced particles"
        )
    system_id = systems[0].entity_id
    participant_ids = frozenset(item.entity_id for item in particles)

    if len(ir.reference_frames) != 1:
        return None, failure(
            "requires exactly one evidenced world-origin positive-x Cartesian frame"
        )
    frame = ir.reference_frames[0]
    axis = frame.axes[0] if len(frame.axes) == 1 else None
    if (
        frame.frame_type is not ReferenceFrameType.cartesian_1d
        or not isinstance(frame.origin, IRWorldOrigin)
        or frame.parent_frame_id is not None
        or frame.translating_with_entity_id is not None
        or frame.rotating_about_point_id is not None
        or frame.generalized_coordinate_symbol_ids
        or axis is None
        or axis.axis.value != "x"
        or getattr(axis.direction, "kind", None) != "axis"
        or getattr(axis.direction, "frame_id", None) != frame.frame_id
        or getattr(getattr(axis.direction, "axis", None), "value", None) != "x"
        or getattr(axis.direction, "sign", None) != 1
        or not frame.evidence_refs
    ):
        return None, failure(
            "requires exactly one evidenced world-origin positive-x Cartesian frame",
            frame.frame_id,
        )

    if len(ir.motion_intervals) != 1:
        return None, failure("requires exactly one evidenced collision interval")
    interval = ir.motion_intervals[0]
    if (
        interval.order != 1
        or set(interval.subject_ids) != {system_id, *participant_ids}
        or len(interval.subject_ids) != 3
        or interval.frame_id != frame.frame_id
        or interval.start_event_id is None
        or interval.end_event_id is None
        or interval.start_event_id == interval.end_event_id
        or not interval.evidence_refs
    ):
        return None, failure(
            "requires one exact system-and-particles interval with distinct impact boundaries",
            interval.interval_id,
        )
    events = {item.event_id: item for item in ir.events}
    start = events.get(interval.start_event_id)
    end = events.get(interval.end_event_id)
    if (
        len(events) != 2
        or start is None
        or end is None
        or start.kind.value != "collision_start"
        or end.kind.value != "collision_end"
        or any(
            set(item.subject_ids) != set(participant_ids)
            or len(item.subject_ids) != 2
            or item.interval_ids != (interval.interval_id,)
            or item.time_quantity_id is not None
            or not item.evidence_refs
            for item in (start, end)
        )
    ):
        return None, failure(
            "requires exact evidenced start/end events naming both particles and no event time",
            interval.interval_id,
        )

    collisions = tuple(
        item for item in ir.interactions if item.kind is InteractionKind.collision
    )
    if len(ir.interactions) != 1 or len(collisions) != 1:
        return None, failure("requires exactly one evidenced collision interaction")
    collision = collisions[0]
    if (
        set(collision.participant_ids) != set(participant_ids)
        or len(collision.participant_ids) != 2
        or collision.point_ids
        or collision.frame_id != frame.frame_id
        or collision.interval_id != interval.interval_id
        or collision.event_id is not None
        or not collision.evidence_refs
    ):
        return None, failure(
            "requires one interval-scoped particle-only collision interaction",
            collision.interaction_id,
        )

    quantities = {item.quantity_id: item for item in ir.quantities}
    masses = tuple(
        item for item in quantities.values() if item.role is QuantityRole.mass
    )
    velocities = tuple(
        item for item in quantities.values() if item.role is QuantityRole.velocity
    )
    coefficients = tuple(
        item
        for item in quantities.values()
        if item.role is QuantityRole.coefficient_restitution
    )
    if (
        len(quantities) != 7
        or len(masses) != 2
        or len(velocities) != 4
        or len(coefficients) != 1
    ):
        return None, failure(
            "requires exactly two masses, four boundary velocities, and one restitution coefficient"
        )

    def exact_source_scalar(item: IRQuantity) -> bool:
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.provenance is Provenance.explicit_source
            and type(item.si_value) is float
            and math.isfinite(item.si_value)
            and bool(item.evidence_refs)
            and item.assumption_policy_ref is None
            and item.correction_id is None
        )

    mass_by_subject = {item.subject_id: item for item in masses}
    if (
        set(mass_by_subject) != set(participant_ids)
        or len(mass_by_subject) != 2
        or any(
            not exact_source_scalar(item)
            or item.point_id is not None
            or item.frame_id is not None
            or item.interval_id is not None
            or item.event_id is not None
            or item.component
            not in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            or item.direction is not None
            or item.dimension != DimensionVector(mass=1)
            for item in masses
        )
    ):
        return None, failure("requires one exact unscoped source mass per particle")
    nonpositive_mass = next((item for item in masses if item.si_value <= 0.0), None)
    if nonpositive_mass is not None:
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "one-dimensional collision masses must be positive",
            f"quantities.{nonpositive_mass.quantity_id}.si_value",
            nonpositive_mass.quantity_id,
        )

    def exact_velocity_scope(item: IRQuantity, event_id: str) -> bool:
        return (
            item.subject_id in participant_ids
            and item.point_id is None
            and item.frame_id == frame.frame_id
            and item.interval_id == interval.interval_id
            and item.event_id == event_id
            and item.component is QuantityComponent.x
            and item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.dimension == DimensionVector(length=1, time=-1)
            and bool(item.evidence_refs)
            and item.assumption_policy_ref is None
            and item.correction_id is None
            and _exact_axis_direction(
                item,
                frame_id=frame.frame_id,
                axis="x",
                sign=getattr(item.direction, "sign", 0),
            )
            and getattr(item.direction, "sign", None) in {-1, 1}
        )

    before = tuple(item for item in velocities if item.event_id == start.event_id)
    after = tuple(item for item in velocities if item.event_id == end.event_id)
    if (
        len(before) != 2
        or len(after) != 2
        or {item.subject_id for item in before} != set(participant_ids)
        or {item.subject_id for item in after} != set(participant_ids)
        or any(
            not exact_velocity_scope(item, start.event_id)
            or not exact_source_scalar(item)
            or item.si_value < 0.0
            for item in before
        )
        or any(
            not exact_velocity_scope(item, end.event_id)
            or item.provenance is not Provenance.inferred
            or item.si_value is not None
            or getattr(item.direction, "sign", None) != 1
            for item in after
        )
    ):
        return None, failure(
            "requires one source-backed signed pre-impact and one inferred algebraic post-impact x velocity per particle"
        )
    signed_before = tuple(
        item.si_value * getattr(item.direction, "sign", 1) for item in before
    )
    if signed_before[0] == signed_before[1]:
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "a collision-start event requires distinct pre-impact particle velocities",
            f"events.{start.event_id}",
            start.event_id,
        )

    coefficient = coefficients[0]
    if (
        not exact_source_scalar(coefficient)
        or coefficient.subject_id != system_id
        or coefficient.point_id is not None
        or coefficient.frame_id != frame.frame_id
        or coefficient.interval_id != interval.interval_id
        or coefficient.event_id is not None
        or coefficient.component
        not in {QuantityComponent.magnitude, QuantityComponent.unspecified}
        or coefficient.direction is not None
        or coefficient.dimension != DimensionVector()
    ):
        return None, failure(
            "requires one exact source-backed system restitution coefficient",
            coefficient.quantity_id,
        )
    if not 0.0 <= coefficient.si_value <= 1.0:
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "one-dimensional collision restitution must lie in the closed interval [0, 1]",
            f"quantities.{coefficient.quantity_id}.si_value",
            coefficient.quantity_id,
        )

    expected_quantity_ids = set(quantities)
    if (
        set(collision.quantity_ids) != expected_quantity_ids
        or len(collision.quantity_ids) != len(expected_quantity_ids)
    ):
        return None, failure(
            "requires the collision interaction to bind the exact seven-quantity inventory",
            collision.interaction_id,
        )

    assumptions = tuple(ir.assumptions)
    isolation = assumptions[0] if len(assumptions) == 1 else None
    if (
        isolation is None
        or isolation.kind != "external_impulse_negligible"
        or isolation.subject_id != system_id
        or isolation.interval_id != interval.interval_id
        or isolation.disposition is not AssumptionDisposition.approved
        or isolation.proposed_role is not None
        or isolation.proposed_value is not None
        or isolation.proposed_unit is not None
        or not isolation.evidence_refs
        or isolation.assumption_id not in set(approved_assumption_ids)
    ):
        return None, failure(
            "requires one externally approved, evidenced, system-scoped negligible-impulse assumption",
            system_id,
        )

    after_by_id = {item.quantity_id: item for item in after}
    query_quantity = after_by_id.get(query.target.target_quantity_id or "")
    try:
        normalized_query_unit = normalize_quantity(
            "1",
            query.output_unit,
            query.shape,
            query.output_dimension,
        )
    except Exception:
        normalized_query_unit = None
    figure_dependency = ir.figure_dependency
    if (
        query_quantity is None
        or normalized_query_unit is None
        or normalized_query_unit.dimension != query_quantity.dimension
        or query.shape is not QuantityShape.scalar
        or query.target.role is not QuantityRole.velocity
        or query.target.subject_id != query_quantity.subject_id
        or query.target.point_id is not None
        or query.target.frame_id != frame.frame_id
        or query.target.interval_id != interval.interval_id
        or query.target.event_id != end.event_id
        or query.target.component is not QuantityComponent.x
        or query.target.direction != query_quantity.direction
        or query.output_dimension != query_quantity.dimension
        or not query.evidence_refs
        or len(ir.queries) != 1
        or ir.points
        or ir.geometry
        or ir.constraints
        or ir.state_conditions
        or ir.principle_hints
        or ir.ambiguities
        or ir.unsupported_features
        or figure_dependency.level.value != "none"
        or figure_dependency.missing_information
        or figure_dependency.evidence_refs
        or {item.symbol_id for item in ir.symbols}
        != {
            item.symbol_id
            for item in quantities.values()
            if item.symbol_id is not None
        }
    ):
        return None, failure(
            "contains extra client authority, symbols, topology, or an inexact post-impact velocity query",
            query.query_id,
        )
    return (
        _Collision1DProfile(
            system_id=system_id,
            participant_ids=participant_ids,
        ),
        None,
    )


@dataclass(frozen=True)
class _VerticalCircleProfile:
    mode: str
    location: str
    carrier_kind: str
    at_unilateral_boundary: bool


def _vertical_circle_roundoff_equal(left: float, right: float) -> bool:
    """Treat only a small fixed number of product-rounding ULPs as equal."""

    if not math.isfinite(left) or not math.isfinite(right):
        return False
    if (left == 0.0) != (right == 0.0):
        return False
    return math.isclose(
        left,
        right,
        rel_tol=8.0 * math.ulp(1.0),
        abs_tol=0.0,
    )


def _vertical_circle_candidate(ir: MechanicsProblemIRV1) -> bool:
    """Recognize redundant typed circular-motion signals, never the query."""

    rotating_circle_frame = any(
        item.frame_type is ReferenceFrameType.tangential_normal
        and item.rotating_about_point_id is not None
        for item in ir.reference_frames
    )
    radius_geometry = any(
        item.kind is GeometryRelationKind.radius for item in ir.geometry
    )
    rope_activity = (
        any(item.kind is InteractionKind.rope_tension for item in ir.interactions)
        and any(
            item.kind.value == "rope" and item.state.value == "taut"
            for item in ir.state_conditions
        )
    )
    contact_activity = (
        any(item.kind is InteractionKind.contact for item in ir.interactions)
        and any(
            item.kind.value == "contact" and item.state.value == "touching"
            for item in ir.state_conditions
        )
    )
    carrier_activity = rope_activity or contact_activity
    normal_gravity = any(
        item.role is QuantityRole.gravity
        and item.component is QuantityComponent.normal
        for item in ir.quantities
    )
    tangential_speed = any(
        item.role is QuantityRole.speed
        and item.component is QuantityComponent.tangential
        for item in ir.quantities
    )
    inward_reaction = any(
        item.role is QuantityRole.force
        and item.component is QuantityComponent.normal
        for item in ir.quantities
    )
    active_boundary = any(
        item.kind.value == "boundary"
        and item.state.value == "active"
        and bool(item.quantity_ids)
        for item in ir.state_conditions
    )
    vertical_inventory = (
        normal_gravity
        and tangential_speed
        and (inward_reaction or active_boundary)
    )

    # The first branch is the intact circular signature.  The latter two keep
    # the specialized gate active when any one of frame, radius, or carrier
    # activity is damaged, while an incline (no radius/rotation) and a rolling
    # profile (no normal gravity/reaction) remain outside this recognizer.
    return (
        (rotating_circle_frame and radius_geometry)
        or (rotating_circle_frame and carrier_activity)
        or (radius_geometry and carrier_activity and vertical_inventory)
    )


def _vertical_circle_contract(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
) -> tuple[_VerticalCircleProfile | None, CompilerIssue | None]:
    """Close the supported local vertical-circle reaction/boundary profiles."""

    if not _vertical_circle_candidate(ir):
        return None, None

    def failure(detail: str, referenced_id: str | None = None) -> CompilerIssue:
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            f"vertical-circle topology {detail}",
            f"queries.{query.query_id}",
            referenced_id or query.query_id,
        )

    primitive_ids = {
        primitive: tuple(
            item.entity_id for item in ir.entities if item.primitive is primitive
        )
        for primitive in (
            EntityPrimitive.particle,
            EntityPrimitive.environment,
            EntityPrimitive.rope,
            EntityPrimitive.surface,
        )
    }
    carrier_ids = (
        *primitive_ids[EntityPrimitive.rope],
        *primitive_ids[EntityPrimitive.surface],
    )
    if (
        len(ir.entities) != 3
        or len(primitive_ids[EntityPrimitive.particle]) != 1
        or len(primitive_ids[EntityPrimitive.environment]) != 1
        or len(carrier_ids) != 1
        or any(
            not item.evidence_refs or item.component_of_entity_id is not None
            for item in ir.entities
        )
    ):
        return None, failure(
            "requires exactly one evidenced particle, environment, and rope or circular surface"
        )
    particle_id = primitive_ids[EntityPrimitive.particle][0]
    environment_id = primitive_ids[EntityPrimitive.environment][0]
    carrier_id = carrier_ids[0]
    carrier_kind = (
        "rope"
        if carrier_id in primitive_ids[EntityPrimitive.rope]
        else "contact"
    )
    fixed_center_owner_id = environment_id if carrier_kind == "rope" else carrier_id

    if len(ir.reference_frames) != 1:
        return None, failure(
            "requires exactly one evidenced inward-positive tangential-normal frame"
        )
    frame = ir.reference_frames[0]
    particle_points = tuple(
        item
        for item in ir.points
        if item.owner_entity_id == particle_id and item.role.value == "material"
    )
    center_points = tuple(
        item
        for item in ir.points
        if item.owner_entity_id == fixed_center_owner_id
        and item.role.value == "geometric"
    )
    if (
        len(ir.points) != 2
        or len(particle_points) != 1
        or len(center_points) != 1
    ):
        return None, failure(
            "requires one particle material point and one fixed-center geometric point"
        )
    particle_point_id = particle_points[0].point_id
    center_point_id = center_points[0].point_id
    axis_signature = {
        (
            item.axis.value,
            getattr(item.direction, "kind", None),
            getattr(item.direction, "frame_id", None),
            getattr(getattr(item.direction, "axis", None), "value", None),
            getattr(item.direction, "sign", None),
        )
        for item in frame.axes
    }
    if (
        frame.frame_type is not ReferenceFrameType.tangential_normal
        or getattr(frame.origin, "kind", None) != "point"
        or getattr(frame.origin, "point_id", None) != particle_point_id
        or frame.parent_frame_id is not None
        or frame.translating_with_entity_id is not None
        or frame.rotating_about_point_id != center_point_id
        or frame.generalized_coordinate_symbol_ids
        or len(frame.axes) != 2
        or axis_signature
        != {
            ("tangent", "axis", frame.frame_id, "tangent", 1),
            ("normal", "axis", frame.frame_id, "normal", 1),
        }
        or not frame.evidence_refs
        or any(
            item.frame_id != frame.frame_id or not item.evidence_refs
            for item in ir.points
        )
    ):
        return None, failure(
            "requires an exact particle-origin frame with positive tangent/inward-normal axes rotating about the fixed center",
            frame.frame_id,
        )

    if len(ir.motion_intervals) != 1:
        return None, failure("requires one evidenced event-free motion interval")
    interval = ir.motion_intervals[0]
    if (
        interval.frame_id != frame.frame_id
        or interval.start_event_id is not None
        or interval.end_event_id is not None
        or set(interval.subject_ids)
        != {particle_id, environment_id, carrier_id}
        or len(interval.subject_ids) != 3
        or not interval.evidence_refs
        or ir.events
    ):
        return None, failure(
            "requires one event-free interval containing the complete circular topology",
            interval.interval_id,
        )

    radius_relations = tuple(
        item for item in ir.geometry if item.kind is GeometryRelationKind.radius
    )
    carrier_geometry_kind = (
        GeometryRelationKind.attached
        if carrier_kind == "rope"
        else GeometryRelationKind.lies_on
    )
    carrier_relations = tuple(
        item for item in ir.geometry if item.kind is carrier_geometry_kind
    )
    expected_carrier_participants = (
        {particle_id, particle_point_id, carrier_id, center_point_id}
        if carrier_kind == "rope"
        else {particle_id, particle_point_id, carrier_id}
    )
    if (
        len(ir.geometry) != 2
        or len(radius_relations) != 1
        or len(carrier_relations) != 1
        or any(
            item.expression is not None
            or item.interval_id != interval.interval_id
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            or len(item.quantity_ids) != len(set(item.quantity_ids))
            for item in ir.geometry
        )
        or set(radius_relations[0].participant_ids)
        != {particle_point_id, center_point_id}
        or len(radius_relations[0].participant_ids) != 2
        or set(carrier_relations[0].participant_ids)
        != expected_carrier_participants
        or len(carrier_relations[0].participant_ids)
        != len(expected_carrier_participants)
        or carrier_relations[0].quantity_ids
    ):
        relation_name = "attachment" if carrier_kind == "rope" else "lies-on"
        return None, failure(
            f"requires exact center-to-particle radius and {relation_name} geometry",
            carrier_id,
        )

    gravity_interactions = tuple(
        item for item in ir.interactions if item.kind is InteractionKind.gravity
    )
    expected_carrier_interaction_kind = (
        InteractionKind.rope_tension
        if carrier_kind == "rope"
        else InteractionKind.contact
    )
    carrier_interactions = tuple(
        item
        for item in ir.interactions
        if item.kind is expected_carrier_interaction_kind
    )
    if (
        len(ir.interactions) != 2
        or len(gravity_interactions) != 1
        or len(carrier_interactions) != 1
    ):
        return None, failure(
            "requires exactly one gravity and one matching rope-tension or contact interaction"
        )
    gravity_interaction = gravity_interactions[0]
    carrier_interaction = carrier_interactions[0]
    if (
        set(gravity_interaction.participant_ids)
        != {particle_id, environment_id}
        or len(gravity_interaction.participant_ids) != 2
        or tuple(gravity_interaction.point_ids) != (particle_point_id,)
        or set(carrier_interaction.participant_ids) != {particle_id, carrier_id}
        or len(carrier_interaction.participant_ids) != 2
        or tuple(carrier_interaction.point_ids) != (particle_point_id,)
        or any(
            item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or not item.evidence_refs
            for item in ir.interactions
        )
    ):
        return None, failure(
            "has incomplete, ambiguous, or incorrectly scoped gravity/carrier interactions"
        )

    quantities = {item.quantity_id: item for item in ir.quantities}

    def by_role(role: QuantityRole) -> tuple[object, ...]:
        return tuple(item for item in quantities.values() if item.role is role)

    masses = by_role(QuantityRole.mass)
    radii = by_role(QuantityRole.radius)
    gravities = by_role(QuantityRole.gravity)
    speeds = by_role(QuantityRole.speed)
    reactions = by_role(QuantityRole.force)
    source_speeds = tuple(
        item
        for item in speeds
        if item.provenance is Provenance.explicit_source or item.si_value is not None
    )
    mode = "reaction" if source_speeds else "minimum_speed"
    expected_quantity_count = 5 if mode == "reaction" else 3
    if (
        len(radii) != 1
        or len(gravities) != 1
        or len(speeds) != 1
        or len(reactions) != (1 if mode == "reaction" else 0)
        or len(masses) != (1 if mode == "reaction" else 0)
        or len(quantities) != expected_quantity_count
    ):
        inventory = (
            "exact source m, R, g, v and inferred local reaction"
            if mode == "reaction"
            else "exact source R, g and inferred minimum speed"
        )
        return None, failure(f"requires {inventory}")
    radius = radii[0]
    gravity = gravities[0]
    speed = speeds[0]
    reaction = reactions[0] if reactions else None
    mass = masses[0] if masses else None

    def exact_source_scalar(item: object) -> bool:
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.provenance is Provenance.explicit_source
            and type(item.si_value) is float
            and math.isfinite(item.si_value)
            and bool(item.evidence_refs)
            and item.assumption_policy_ref is None
            and item.correction_id is None
        )

    if (
        not exact_source_scalar(radius)
        or radius.subject_id != particle_id
        or radius.point_id != particle_point_id
        or radius.frame_id is not None
        or radius.interval_id is not None
        or radius.event_id is not None
        or radius.component
        not in {QuantityComponent.magnitude, QuantityComponent.unspecified}
        or radius.direction is not None
        or radius.dimension != DimensionVector(length=1)
        or tuple(radius_relations[0].quantity_ids) != (radius.quantity_id,)
    ):
        return None, failure(
            "requires one exact source-backed particle-point trajectory radius",
            radius.quantity_id,
        )
    if (
        not exact_source_scalar(gravity)
        or gravity.subject_id != environment_id
        or gravity.point_id is not None
        or gravity.frame_id != frame.frame_id
        or gravity.interval_id != interval.interval_id
        or gravity.event_id is not None
        or gravity.component is not QuantityComponent.normal
        or gravity.dimension != DimensionVector(length=1, time=-2)
        or not _exact_axis_direction(
            gravity,
            frame_id=frame.frame_id,
            axis="normal",
            sign=getattr(gravity.direction, "sign", 0),
        )
        or getattr(gravity.direction, "sign", None) not in {-1, 1}
    ):
        return None, failure(
            "requires one exact local-normal source gravity direction",
            gravity.quantity_id,
        )
    location = "top" if gravity.direction.sign == 1 else "bottom"
    if (
        speed.subject_id != particle_id
        or speed.point_id != particle_point_id
        or speed.frame_id != frame.frame_id
        or speed.interval_id != interval.interval_id
        or speed.event_id is not None
        or speed.shape is not QuantityShape.scalar
        or speed.symbol_id is None
        or speed.component is not QuantityComponent.tangential
        or speed.dimension != DimensionVector(length=1, time=-1)
        or not speed.evidence_refs
        or speed.assumption_policy_ref is not None
        or speed.correction_id is not None
        or not _exact_axis_direction(
            speed,
            frame_id=frame.frame_id,
            axis="tangent",
            sign=1,
        )
    ):
        return None, failure(
            "requires one exact positive-tangent local speed binding",
            speed.quantity_id,
        )
    if reaction is not None:
        if (
            reaction.subject_id != particle_id
            or reaction.point_id != particle_point_id
            or reaction.frame_id != frame.frame_id
            or reaction.interval_id != interval.interval_id
            or reaction.event_id is not None
            or reaction.shape is not QuantityShape.scalar
            or reaction.symbol_id is None
            or reaction.component is not QuantityComponent.normal
            or reaction.dimension != DimensionVector(mass=1, length=1, time=-2)
            or reaction.provenance is not Provenance.inferred
            or reaction.si_value is not None
            or not reaction.evidence_refs
            or reaction.assumption_policy_ref is not None
            or reaction.correction_id is not None
            or not _exact_axis_direction(
                reaction,
                frame_id=frame.frame_id,
                axis="normal",
                sign=1,
            )
        ):
            return None, failure(
                "requires one inferred inward-positive unilateral local reaction",
                reaction.quantity_id,
            )

    if radius.si_value <= 0.0 or gravity.si_value <= 0.0:
        bad = radius if radius.si_value <= 0.0 else gravity
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "vertical-circle radius and gravity magnitude must be positive",
            f"quantities.{bad.quantity_id}.si_value",
            bad.quantity_id,
        )
    if mode == "reaction":
        assert mass is not None
        assert reaction is not None
        if (
            not exact_source_scalar(mass)
            or mass.subject_id != particle_id
            or mass.point_id is not None
            or mass.frame_id is not None
            or mass.interval_id is not None
            or mass.event_id is not None
            or mass.component
            not in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            or mass.direction is not None
            or mass.dimension != DimensionVector(mass=1)
        ):
            return None, failure(
                "requires one exact source-backed unscoped particle mass",
                mass.quantity_id,
            )
        if (
            not exact_source_scalar(speed)
            or speed.si_value < 0.0
        ):
            code = (
                CompilerIssueCode.invalid_domain
                if type(speed.si_value) is float and speed.si_value < 0.0
                else CompilerIssueCode.requires_specialized_model
            )
            return None, _issue(
                code,
                "vertical-circle local speed must be finite, source-backed, and nonnegative",
                f"quantities.{speed.quantity_id}.si_value",
                speed.quantity_id,
            )
        if mass.si_value <= 0.0:
            return None, _issue(
                CompilerIssueCode.invalid_domain,
                "vertical-circle particle mass must be positive",
                f"quantities.{mass.quantity_id}.si_value",
                mass.quantity_id,
            )
        expected_gravity_quantity_ids = {mass.quantity_id, gravity.quantity_id}
        speed_squared = speed.si_value * speed.si_value
        if (
            not math.isfinite(speed_squared)
            or (speed.si_value > 0.0 and speed_squared == 0.0)
        ):
            return None, _issue(
                CompilerIssueCode.invalid_domain,
                "vertical-circle derived speed-squared must be finite and representable",
                f"quantities.{speed.quantity_id}.si_value",
                speed.quantity_id,
            )
        normal_acceleration = speed_squared / radius.si_value
        reaction_acceleration = (
            normal_acceleration - gravity.si_value
            if location == "top"
            else normal_acceleration + gravity.si_value
        )
        if (
            not math.isfinite(normal_acceleration)
            or not math.isfinite(reaction_acceleration)
            or (speed_squared > 0.0 and normal_acceleration == 0.0)
        ):
            return None, _issue(
                CompilerIssueCode.invalid_domain,
                "vertical-circle derived normal and reaction accelerations must be finite",
                f"quantities.{speed.quantity_id}.si_value",
                speed.quantity_id,
            )
        if location == "top":
            gravity_radius = gravity.si_value * radius.si_value
            if not math.isfinite(gravity_radius) or gravity_radius <= 0.0:
                return None, _issue(
                    CompilerIssueCode.invalid_domain,
                    "top vertical-circle gravity-radius product must be finite and representably positive",
                    f"quantities.{gravity.quantity_id}.si_value",
                    gravity.quantity_id,
                )
            at_unilateral_boundary = _vertical_circle_roundoff_equal(
                speed_squared, gravity_radius
            )
            if speed_squared < gravity_radius and not at_unilateral_boundary:
                return None, failure(
                    "rejects the top contact-loss/slack-rope regime because the required unilateral reaction would be negative",
                    speed.quantity_id,
                )
            if reaction_acceleration == 0.0 and not at_unilateral_boundary:
                return None, _issue(
                    CompilerIssueCode.invalid_domain,
                    "top vertical-circle reaction acceleration rounded to zero away from the unilateral boundary",
                    f"quantities.{speed.quantity_id}.si_value",
                    speed.quantity_id,
                )
        else:
            at_unilateral_boundary = False
        reaction_value = mass.si_value * reaction_acceleration
        if (
            not at_unilateral_boundary
            and (
                not math.isfinite(reaction_value)
                or reaction_acceleration <= 0.0
                or reaction_value <= 0.0
            )
        ):
            return None, _issue(
                CompilerIssueCode.invalid_domain,
                "vertical-circle derived non-boundary local reaction must be finite, representable, and positive",
                f"quantities.{mass.quantity_id}.si_value",
                mass.quantity_id,
            )
    else:
        if (
            speed.provenance is not Provenance.inferred
            or speed.si_value is not None
        ):
            return None, failure(
                "requires one inferred principal minimum-speed output",
                speed.quantity_id,
            )
        if location != "top":
            return None, failure(
                "supports the minimum-speed boundary only at the top",
                gravity.quantity_id,
            )
        gravity_radius = gravity.si_value * radius.si_value
        if not math.isfinite(gravity_radius) or gravity_radius <= 0.0:
            return None, _issue(
                CompilerIssueCode.invalid_domain,
                "minimum-speed gravity-radius product must be finite and representably positive",
                f"quantities.{gravity.quantity_id}.si_value",
                gravity.quantity_id,
            )
        expected_gravity_quantity_ids = {gravity.quantity_id}
        at_unilateral_boundary = True

    if (
        set(gravity_interaction.quantity_ids) != expected_gravity_quantity_ids
        or len(gravity_interaction.quantity_ids)
        != len(expected_gravity_quantity_ids)
        or tuple(carrier_interaction.quantity_ids)
        != (() if reaction is None else (reaction.quantity_id,))
    ):
        return None, failure(
            "contains inexact gravity or carrier-interaction quantity bindings"
        )

    active_kind = "rope" if carrier_kind == "rope" else "contact"
    active_value = "taut" if carrier_kind == "rope" else "touching"
    active_subject_id = carrier_id if carrier_kind == "rope" else particle_id
    active_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == active_kind
        and item.state.value == active_value
        and item.subject_id == active_subject_id
    )
    fixed_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == "motion"
        and item.state.value == "at_rest"
        and item.subject_id == fixed_center_owner_id
    )
    boundary_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == "boundary"
        and item.state.value == "active"
        and item.subject_id == particle_id
    )
    expected_state_count = 2 if mode == "reaction" else 3
    expected_active_quantity_ids = (
        {reaction.quantity_id}
        if carrier_kind == "contact" and reaction is not None
        else set()
    )
    if (
        len(ir.state_conditions) != expected_state_count
        or len(active_states) != 1
        or len(fixed_states) != 1
        or len(boundary_states) != (0 if mode == "reaction" else 1)
        or set(active_states[0].quantity_ids) != expected_active_quantity_ids
        or len(active_states[0].quantity_ids)
        != len(expected_active_quantity_ids)
        or fixed_states[0].quantity_ids
        or (
            mode == "minimum_speed"
            and (
                set(boundary_states[0].quantity_ids)
                != {speed.quantity_id}
                or len(boundary_states[0].quantity_ids) != 1
            )
        )
        or any(
            item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.expression is not None
            or not item.evidence_refs
            for item in ir.state_conditions
        )
    ):
        return None, failure(
            "requires exact evidenced taut/touching, fixed-center, and optional active-boundary states",
            particle_id,
        )

    expected_quantity_ids = {
        radius.quantity_id,
        gravity.quantity_id,
        speed.quantity_id,
        *(() if reaction is None else (reaction.quantity_id,)),
        *(() if mass is None else (mass.quantity_id,)),
    }
    query_quantity = quantities.get(query.target.target_quantity_id or "")
    expected_query_quantity = reaction if reaction is not None else speed
    figure_dependency = ir.figure_dependency
    if (
        set(quantities) != expected_quantity_ids
        or query_quantity is not expected_query_quantity
        or query.shape is not QuantityShape.scalar
        or query.target.role is not expected_query_quantity.role
        or query.target.subject_id != particle_id
        or query.target.point_id != particle_point_id
        or query.target.frame_id != frame.frame_id
        or query.target.interval_id != interval.interval_id
        or query.target.event_id is not None
        or query.target.component is not expected_query_quantity.component
        or query.target.direction != expected_query_quantity.direction
        or query.output_dimension != expected_query_quantity.dimension
        or not query.evidence_refs
        or len(ir.queries) != 1
        or ir.constraints
        or ir.assumptions
        or ir.principle_hints
        or ir.ambiguities
        or ir.unsupported_features
        or figure_dependency.level.value != "none"
        or figure_dependency.missing_information
        or figure_dependency.evidence_refs
        or {item.symbol_id for item in ir.symbols}
        != {
            item.symbol_id
            for item in quantities.values()
            if item.symbol_id is not None
        }
    ):
        return None, failure(
            "contains extra client authority, quantities, symbols, or an inexact local query",
            query.query_id,
        )
    return (
        _VerticalCircleProfile(
            mode=mode,
            location=location,
            carrier_kind=carrier_kind,
            at_unilateral_boundary=at_unilateral_boundary,
        ),
        None,
    )


_PURE_ROLLING_SHAPE_BETA: Mapping[str, Fraction] = {
    "solid_sphere": Fraction(2, 5),
    "hollow_sphere": Fraction(2, 3),
    "solid_cylinder": Fraction(1, 2),
    "disk": Fraction(1, 2),
    "hoop": Fraction(1, 1),
    "ring": Fraction(1, 1),
}


@dataclass(frozen=True)
class _RollingEnergyProfile:
    fixed_axis_angular_quantity_ids: frozenset[str]


def _rolling_energy_candidate(ir: MechanicsProblemIRV1) -> bool:
    """Use redundant physical signals, never the query or diagnostics."""

    primitives = {item.primitive for item in ir.entities}
    has_cartesian_2d_frame = any(
        item.frame_type is ReferenceFrameType.cartesian_2d
        for item in ir.reference_frames
    )
    intact_rigid_candidate = (
        EntityPrimitive.rigid_body in primitives
        and has_cartesian_2d_frame
        and (
            EntityPrimitive.incline in primitives
            or EntityPrimitive.environment in primitives
            or any(item.state.value == "no_slip" for item in ir.state_conditions)
            or any(item.kind in _PURE_ROLLING_SHAPE_BETA for item in ir.assumptions)
        )
    )
    if intact_rigid_candidate:
        return True

    role_counts = {
        role: sum(item.role is role for item in ir.quantities)
        for role in (
            QuantityRole.radius,
            QuantityRole.moment_of_inertia,
            QuantityRole.speed,
            QuantityRole.angular_velocity,
        )
    }
    rolling_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == "rolling" and item.state.value == "no_slip"
    )
    initial_states = tuple(
        item for item in ir.state_conditions if item.kind.value == "initial"
    )
    final_rolling_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == "final" and item.state.value == "rolling"
    )
    geometry_kinds = {item.kind for item in ir.geometry}
    damaged_rolling_signature = (
        has_cartesian_2d_frame
        and EntityPrimitive.incline in primitives
        and EntityPrimitive.environment in primitives
        and bool(rolling_states)
        and bool(initial_states)
        and bool(final_rolling_states)
        and GeometryRelationKind.radius in geometry_kinds
        and GeometryRelationKind.lies_on in geometry_kinds
        and role_counts[QuantityRole.radius] == 1
        and role_counts[QuantityRole.moment_of_inertia] == 1
        and role_counts[QuantityRole.speed] == 2
        and role_counts[QuantityRole.angular_velocity] == 2
    )
    return damaged_rolling_signature


def _rolling_energy_contract(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    approved_assumption_ids: frozenset[str],
) -> tuple[_RollingEnergyProfile | None, CompilerIssue | None]:
    """Close either supported lossless rolling-energy profile."""

    if not _rolling_energy_candidate(ir):
        return None, None

    source_inertia_claimed = any(
        item.role is QuantityRole.moment_of_inertia
        and (
            item.provenance is Provenance.explicit_source
            or item.si_value is not None
        )
        for item in ir.quantities
    )
    shape_claimed = any(
        item.kind in _PURE_ROLLING_SHAPE_BETA for item in ir.assumptions
    )
    rolling_mode = "general" if source_inertia_claimed else "pure"

    def failure(detail: str, referenced_id: str | None = None) -> CompilerIssue:
        profile_name = (
            "general rolling energy"
            if rolling_mode == "general"
            else "pure-rolling energy"
        )
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            f"{profile_name} topology {detail}",
            f"queries.{query.query_id}",
            referenced_id or query.query_id,
        )

    if source_inertia_claimed and shape_claimed:
        return None, failure(
            "rejects simultaneous source inertia and shape-derived inertia authority"
        )

    primitive_ids = {
        primitive: tuple(
            item.entity_id for item in ir.entities if item.primitive is primitive
        )
        for primitive in (
            EntityPrimitive.rigid_body,
            EntityPrimitive.incline,
            EntityPrimitive.environment,
        )
    }
    if (
        {key.value: len(value) for key, value in primitive_ids.items()}
        != {"rigid_body": 1, "incline": 1, "environment": 1}
        or len(ir.entities) != 3
        or any(
            not item.evidence_refs or item.component_of_entity_id is not None
            for item in ir.entities
        )
    ):
        return None, failure(
            "requires exactly one evidenced rigid body, incline, and environment"
        )
    body_id = primitive_ids[EntityPrimitive.rigid_body][0]
    incline_id = primitive_ids[EntityPrimitive.incline][0]
    environment_id = primitive_ids[EntityPrimitive.environment][0]

    if len(ir.reference_frames) != 1:
        return None, failure("requires one evidenced two-dimensional world frame")
    frame = ir.reference_frames[0]
    axis_signature = {
        (
            item.axis.value,
            getattr(item.direction, "kind", None),
            getattr(item.direction, "frame_id", None),
            getattr(getattr(item.direction, "axis", None), "value", None),
            getattr(item.direction, "sign", None),
        )
        for item in frame.axes
    }
    if (
        frame.frame_type is not ReferenceFrameType.cartesian_2d
        or getattr(frame.origin, "kind", None) != "world"
        or frame.parent_frame_id is not None
        or frame.translating_with_entity_id is not None
        or frame.rotating_about_point_id is not None
        or frame.generalized_coordinate_symbol_ids
        or not frame.evidence_refs
        or len(frame.axes) != 2
        or axis_signature
        != {
            ("x", "axis", frame.frame_id, "x", 1),
            ("y", "axis", frame.frame_id, "y", 1),
        }
    ):
        return None, failure(
            "requires exact positive x/y axes in one Cartesian world frame",
            frame.frame_id,
        )

    if len(ir.motion_intervals) != 1:
        return None, failure("requires one evidenced event-free motion interval")
    interval = ir.motion_intervals[0]
    if (
        interval.frame_id != frame.frame_id
        or interval.start_event_id is not None
        or interval.end_event_id is not None
        or set(interval.subject_ids) != {body_id, incline_id, environment_id}
        or len(interval.subject_ids) != 3
        or not interval.evidence_refs
        or ir.events
    ):
        return None, failure(
            "requires one event-free interval containing the complete topology",
            interval.interval_id,
        )

    centers = tuple(
        item
        for item in ir.points
        if item.owner_entity_id == body_id and item.role.value == "mass_center"
    )
    contacts = tuple(
        item
        for item in ir.points
        if item.owner_entity_id == body_id and item.role.value == "contact"
    )
    if (
        len(ir.points) != 2
        or len(centers) != 1
        or len(contacts) != 1
        or any(item.frame_id != frame.frame_id or not item.evidence_refs for item in ir.points)
    ):
        return None, failure(
            "requires one evidenced body-owned mass center and contact point",
            body_id,
        )
    center_id = centers[0].point_id
    contact_id = contacts[0].point_id

    radii_relations = tuple(
        item for item in ir.geometry if item.kind is GeometryRelationKind.radius
    )
    lies_on_relations = tuple(
        item for item in ir.geometry if item.kind is GeometryRelationKind.lies_on
    )
    if (
        len(ir.geometry) != 2
        or len(radii_relations) != 1
        or len(lies_on_relations) != 1
        or any(
            item.expression is not None
            or item.interval_id != interval.interval_id
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            or len(item.quantity_ids) != len(set(item.quantity_ids))
            for item in ir.geometry
        )
        or set(radii_relations[0].participant_ids)
        != {body_id, center_id, contact_id}
        or len(radii_relations[0].participant_ids) != 3
        or set(lies_on_relations[0].participant_ids)
        != {body_id, incline_id, contact_id}
        or len(lies_on_relations[0].participant_ids) != 3
        or lies_on_relations[0].quantity_ids
    ):
        return None, failure(
            "requires exact center-contact radius and body-contact-incline relations",
            body_id,
        )

    gravity_interactions = tuple(
        item for item in ir.interactions if item.kind is InteractionKind.gravity
    )
    contact_interactions = tuple(
        item for item in ir.interactions if item.kind is InteractionKind.contact
    )
    if (
        len(ir.interactions) != 2
        or len(gravity_interactions) != 1
        or len(contact_interactions) != 1
    ):
        return None, failure(
            "requires exactly one gravity and one contact interaction"
        )
    gravity_interaction = gravity_interactions[0]
    contact_interaction = contact_interactions[0]
    if (
        set(gravity_interaction.participant_ids) != {body_id, environment_id}
        or len(gravity_interaction.participant_ids) != 2
        or gravity_interaction.point_ids
        or set(contact_interaction.participant_ids) != {body_id, incline_id}
        or len(contact_interaction.participant_ids) != 2
        or tuple(contact_interaction.point_ids) != (contact_id,)
        or any(
            item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or not item.evidence_refs
            for item in ir.interactions
        )
    ):
        return None, failure(
            "has incomplete or ambiguous gravity/contact topology"
        )

    shape_assumptions = tuple(
        item for item in ir.assumptions if item.kind in _PURE_ROLLING_SHAPE_BETA
    )
    loss_assumptions = tuple(
        item for item in ir.assumptions if item.kind == "no_energy_loss"
    )
    expected_assumptions = (
        (*shape_assumptions, *loss_assumptions)
        if rolling_mode == "pure"
        else loss_assumptions
    )
    assumption_inventory_ok = (
        len(ir.assumptions) == 2
        and len(shape_assumptions) == 1
        and len(loss_assumptions) == 1
        if rolling_mode == "pure"
        else len(ir.assumptions) == 1
        and not shape_assumptions
        and len(loss_assumptions) == 1
    )
    if not assumption_inventory_ok or any(
        item.subject_id != body_id
        or item.interval_id != interval.interval_id
        or item.disposition is not AssumptionDisposition.approved
        or item.assumption_id not in approved_assumption_ids
        or item.proposed_role is not None
        or item.proposed_value is not None
        or item.proposed_unit is not None
        or not item.evidence_refs
        for item in expected_assumptions
    ):
        detail = (
            "requires exact externally approved closed-table shape and no-energy-loss assumptions"
            if rolling_mode == "pure"
            else "requires exactly one externally approved evidenced no-energy-loss assumption and no shape assumption"
        )
        return None, failure(detail, body_id)

    quantities = {item.quantity_id: item for item in ir.quantities}

    def by_role(role: QuantityRole) -> tuple[object, ...]:
        return tuple(item for item in quantities.values() if item.role is role)

    masses = by_role(QuantityRole.mass)
    radii = by_role(QuantityRole.radius)
    gravities = by_role(QuantityRole.gravity)
    heights = by_role(QuantityRole.height)
    inertias = by_role(QuantityRole.moment_of_inertia)
    speeds = by_role(QuantityRole.speed)
    angular_speeds = by_role(QuantityRole.angular_velocity)
    if (
        len(masses) != 1
        or len(radii) != 1
        or len(gravities) != 1
        or len(heights) != 1
        or len(inertias) != 1
        or len(speeds) != 2
        or len(angular_speeds) != 2
        or len(quantities) != 9
    ):
        return None, failure(
            "requires exact m, R, g, h, I, initial/final speed, and initial/final angular-speed inventory"
        )
    mass, radius, gravity, height, inertia = (
        masses[0], radii[0], gravities[0], heights[0], inertias[0]
    )

    known = (mass, radius, gravity, height)
    if any(
        item.shape is not QuantityShape.scalar
        or item.symbol_id is None
        or item.provenance is not Provenance.explicit_source
        or not item.evidence_refs
        or item.point_id is not None
        or item.frame_id is not None
        or item.interval_id is not None
        or item.event_id is not None
        or item.component not in {QuantityComponent.magnitude, QuantityComponent.unspecified}
        or item.direction is not None
        or type(item.si_value) is not float
        or not math.isfinite(item.si_value)
        for item in known
    ):
        return None, failure(
            "requires exact source-backed unscoped scalar m, R, g, and h"
        )
    invalid_positive = next(
        (item for item in (mass, radius, gravity) if item.si_value <= 0.0),
        None,
    )
    if invalid_positive is not None or height.si_value < 0.0:
        bad = invalid_positive or height
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "pure-rolling mass, radius, and gravity must be positive and height drop must be nonnegative",
            f"quantities.{bad.quantity_id}.si_value",
            bad.quantity_id,
        )
    if (
        mass.subject_id != body_id
        or radius.subject_id != body_id
        or gravity.subject_id != environment_id
        or height.subject_id != body_id
        or mass.dimension != DimensionVector(mass=1)
        or radius.dimension != DimensionVector(length=1)
        or gravity.dimension != DimensionVector(length=1, time=-2)
        or height.dimension != DimensionVector(length=1)
        or tuple(radii_relations[0].quantity_ids) != (radius.quantity_id,)
        or set(gravity_interaction.quantity_ids)
        != {mass.quantity_id, gravity.quantity_id, height.quantity_id}
        or len(gravity_interaction.quantity_ids) != 3
        or tuple(contact_interaction.quantity_ids) != (radius.quantity_id,)
    ):
        return None, failure("contains an inexact or dimensionally invalid source binding")

    inertia_binding_ok = (
        inertia.subject_id == body_id
        and inertia.point_id == center_id
        and inertia.frame_id is None
        and inertia.interval_id == interval.interval_id
        and inertia.event_id is None
        and inertia.shape is QuantityShape.scalar
        and inertia.dimension == DimensionVector(mass=1, length=2)
        and inertia.symbol_id is not None
        and bool(inertia.evidence_refs)
        and inertia.component
        in {QuantityComponent.magnitude, QuantityComponent.unspecified}
        and inertia.direction is None
    )
    if not inertia_binding_ok:
        return None, failure(
            "requires one exact scalar inertia at the body mass center",
            inertia.quantity_id,
        )
    if rolling_mode == "pure":
        if (
            inertia.si_value is not None
            or inertia.provenance not in {Provenance.inferred, Provenance.unknown}
        ):
            return None, failure(
                "requires one inferred inertia at the mass center; explicit source I belongs to the general rolling solver",
                inertia.quantity_id,
            )
    else:
        if (
            inertia.provenance is not Provenance.explicit_source
            or type(inertia.si_value) is not float
            or not math.isfinite(inertia.si_value)
        ):
            return None, failure(
                "requires one finite evidenced explicit-source inertia at the mass center",
                inertia.quantity_id,
            )
        if inertia.si_value <= 0.0:
            return None, _issue(
                CompilerIssueCode.invalid_domain,
                "general rolling moment of inertia must be positive",
                f"quantities.{inertia.quantity_id}.si_value",
                inertia.quantity_id,
            )

    initial_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == "initial" and item.subject_id == body_id
    )
    final_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == "final" and item.subject_id == body_id
    )
    no_slip_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == "rolling"
        and item.state.value == "no_slip"
        and item.subject_id == body_id
    )
    touching_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == "contact"
        and item.state.value == "touching"
        and item.subject_id == body_id
    )
    fixed_incline_states = tuple(
        item
        for item in ir.state_conditions
        if item.kind.value == "motion"
        and item.state.value == "at_rest"
        and item.subject_id == incline_id
    )
    if (
        len(ir.state_conditions) != 5
        or len(initial_states) != 1
        or len(final_states) != 1
        or len(no_slip_states) != 1
        or len(touching_states) != 1
        or touching_states[0].quantity_ids
        or len(fixed_incline_states) != 1
        or fixed_incline_states[0].quantity_ids
        or final_states[0].state.value != "rolling"
        or any(
            item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.expression is not None
            or not item.evidence_refs
            for item in ir.state_conditions
        )
    ):
        return None, failure(
            "requires exact initial/final/no-slip, touching-body, and fixed-incline state topology",
            body_id,
        )

    initial_speed_id = next(iter(initial_states[0].quantity_ids), None)
    initial_speed = quantities.get(initial_speed_id or "")
    final_speed = next(
        (
            quantities.get(item)
            for item in final_states[0].quantity_ids
            if quantities.get(item) in speeds
        ),
        None,
    )
    if (
        len(initial_states[0].quantity_ids) != 1
        or len(final_states[0].quantity_ids) != 2
        or initial_speed not in speeds
        or final_speed not in speeds
        or initial_speed is final_speed
    ):
        return None, failure("requires distinct state-bound initial and final speeds")

    def exact_speed(item: object) -> bool:
        return (
            item.subject_id == body_id
            and item.point_id == center_id
            and item.frame_id == frame.frame_id
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.shape is QuantityShape.scalar
            and item.dimension == DimensionVector(length=1, time=-1)
            and item.symbol_id is not None
            and item.component is QuantityComponent.magnitude
            and item.direction is None
            and bool(item.evidence_refs)
        )

    if not exact_speed(initial_speed) or not exact_speed(final_speed):
        return None, failure("requires exact center-of-mass scalar speed bindings")
    starts_from_rest = initial_states[0].state.value == "at_rest"
    if starts_from_rest:
        initial_ok = (
            initial_speed.si_value is None
            and initial_speed.provenance in {Provenance.inferred, Provenance.unknown}
        )
    else:
        initial_ok = (
            initial_states[0].state.value == "moving"
            and initial_speed.provenance is Provenance.explicit_source
            and type(initial_speed.si_value) is float
            and math.isfinite(initial_speed.si_value)
            and initial_speed.si_value >= 0.0
        )
    if not initial_ok:
        code = (
            CompilerIssueCode.invalid_domain
            if type(initial_speed.si_value) is float and initial_speed.si_value < 0.0
            else CompilerIssueCode.requires_specialized_model
        )
        return None, _issue(
            code,
            "pure rolling requires a nonnegative source initial speed or one evidenced at-rest state",
            f"quantities.{initial_speed.quantity_id}",
            initial_speed.quantity_id,
        )
    if (
        final_speed.si_value is not None
        or final_speed.provenance not in {Provenance.inferred, Provenance.unknown}
    ):
        return None, failure("requires one inferred final center-of-mass speed")

    final_angular_id = next(
        (
            item
            for item in final_states[0].quantity_ids
            if item != final_speed.quantity_id
        ),
        None,
    )
    final_angular = quantities.get(final_angular_id or "")
    initial_angular = next(
        (item for item in angular_speeds if item is not final_angular),
        None,
    )

    def exact_angular_speed(item: object) -> bool:
        direction = getattr(item, "direction", None)
        return (
            item is not None
            and item.subject_id == body_id
            and item.point_id == center_id
            and item.frame_id == frame.frame_id
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.shape is QuantityShape.scalar
            and item.dimension == DimensionVector(time=-1)
            and item.symbol_id is not None
            and item.si_value is None
            and item.provenance in {Provenance.inferred, Provenance.unknown}
            and item.component is QuantityComponent.clockwise
            and getattr(direction, "kind", None) == "semantic"
            and getattr(getattr(direction, "direction", None), "value", None)
            == "clockwise"
            and bool(item.evidence_refs)
        )

    if (
        final_angular not in angular_speeds
        or initial_angular not in angular_speeds
        or not exact_angular_speed(initial_angular)
        or not exact_angular_speed(final_angular)
        or set(no_slip_states[0].quantity_ids)
        != {
            radius.quantity_id,
            initial_speed.quantity_id,
            final_speed.quantity_id,
            initial_angular.quantity_id,
            final_angular.quantity_id,
        }
        or len(no_slip_states[0].quantity_ids) != 5
    ):
        return None, failure(
            "requires two inferred clockwise angular speeds and exact two-state no-slip carriers"
        )

    expected_quantity_ids = {
        mass.quantity_id,
        radius.quantity_id,
        gravity.quantity_id,
        height.quantity_id,
        inertia.quantity_id,
        initial_speed.quantity_id,
        final_speed.quantity_id,
        initial_angular.quantity_id,
        final_angular.quantity_id,
    }
    query_quantity = quantities.get(query.target.target_quantity_id or "")
    figure_dependency = ir.figure_dependency
    if (
        set(quantities) != expected_quantity_ids
        or query_quantity is not final_speed
        or query.shape is not QuantityShape.scalar
        or query.target.role is not QuantityRole.speed
        or query.target.subject_id != body_id
        or query.target.point_id != center_id
        or query.target.frame_id != frame.frame_id
        or query.target.interval_id != interval.interval_id
        or query.target.event_id is not None
        or query.target.component is not QuantityComponent.magnitude
        or query.target.direction is not None
        or query.output_dimension != final_speed.dimension
        or not query.evidence_refs
        or len(ir.queries) != 1
        or ir.constraints
        or ir.principle_hints
        or ir.ambiguities
        or ir.unsupported_features
        or figure_dependency.level.value != "none"
        or figure_dependency.missing_information
        or figure_dependency.evidence_refs
        or {item.symbol_id for item in ir.symbols}
        != {
            item.symbol_id
            for item in quantities.values()
            if item.symbol_id is not None
        }
    ):
        return None, failure(
            "contains extra client authority, quantities, symbols, or a non-final-speed query",
            query.query_id,
        )
    return (
        _RollingEnergyProfile(
            fixed_axis_angular_quantity_ids=frozenset(
                (initial_angular.quantity_id, final_angular.quantity_id)
            )
        ),
        None,
    )


def _massive_pulley_atwood_candidate(ir: MechanicsProblemIRV1) -> bool:
    primitive_ids = {
        primitive: tuple(
            item.entity_id
            for item in ir.entities
            if item.primitive.value == primitive
        )
        for primitive in ("particle", "rope", "pulley", "environment")
    }
    return (
        all(primitive_ids[primitive] for primitive in primitive_ids)
        and any(
            item.frame_type.value == "cartesian_3d"
            for item in ir.reference_frames
        )
    )


def _massive_pulley_atwood_contract(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    approved_assumption_ids: frozenset[str],
) -> tuple[_MassivePulleyAtwoodProfile | None, CompilerIssue | None]:
    """Close one exact fixed-axis, inertial-pulley Atwood topology."""

    # Activate independently of the query and of relations/interactions that
    # the closed profile must require.  This prevents complementary topology
    # deletions from erasing the recognizer's own signal.
    if not _massive_pulley_atwood_candidate(ir):
        return None, None

    def failure(detail: str, referenced_id: str | None = None) -> CompilerIssue:
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            f"massive-pulley Atwood topology {detail}",
            f"queries.{query.query_id}",
            referenced_id or query.query_id,
        )

    entities = ir.entities
    primitive_ids = {
        primitive: tuple(
            item.entity_id
            for item in entities
            if item.primitive.value == primitive
        )
        for primitive in ("particle", "rope", "pulley", "environment")
    }
    if (
        {key: len(value) for key, value in primitive_ids.items()}
        != {"particle": 2, "rope": 1, "pulley": 1, "environment": 1}
        or len(entities) != 5
        or any(
            not item.evidence_refs or item.component_of_entity_id is not None
            for item in entities
        )
    ):
        return None, failure(
            "requires exactly two evidenced particles, one rope, one pulley, and one environment"
        )
    particle_ids = set(primitive_ids["particle"])
    rope_id = primitive_ids["rope"][0]
    pulley_id = primitive_ids["pulley"][0]
    environment_id = primitive_ids["environment"][0]

    frames = ir.reference_frames
    if len(frames) != 1:
        return None, failure("requires one evidenced three-dimensional world frame")
    frame = frames[0]
    axis_signature = {
        (
            item.axis.value,
            getattr(item.direction, "kind", None),
            getattr(item.direction, "frame_id", None),
            getattr(getattr(item.direction, "axis", None), "value", None),
            getattr(item.direction, "sign", None),
        )
        for item in frame.axes
    }
    if (
        frame.frame_type.value != "cartesian_3d"
        or getattr(frame.origin, "kind", None) != "world"
        or frame.parent_frame_id is not None
        or frame.translating_with_entity_id is not None
        or frame.rotating_about_point_id is not None
        or frame.generalized_coordinate_symbol_ids
        or not frame.evidence_refs
        or len(frame.axes) != 3
        or axis_signature
        != {
            ("x", "axis", frame.frame_id, "x", 1),
            ("y", "axis", frame.frame_id, "y", 1),
            ("z", "axis", frame.frame_id, "z", 1),
        }
    ):
        return None, failure(
            "requires exact positive x/y/z axes in one Cartesian world frame",
            frame.frame_id,
        )

    intervals = ir.motion_intervals
    if len(intervals) != 1:
        return None, failure("requires one evidenced event-free motion interval")
    interval = intervals[0]
    if (
        interval.frame_id != frame.frame_id
        or interval.start_event_id is not None
        or interval.end_event_id is not None
        or len(interval.subject_ids) != len(entities)
        or set(interval.subject_ids) != {item.entity_id for item in entities}
        or not interval.evidence_refs
        or ir.events
    ):
        return None, failure(
            "requires one event-free interval containing the complete topology",
            interval.interval_id,
        )

    points = ir.points
    if (
        len(points) != 2
        or any(
            item.role.value != "contact"
            or item.owner_entity_id != pulley_id
            or item.frame_id != frame.frame_id
            or not item.evidence_refs
            for item in points
        )
    ):
        return None, failure(
            "requires exactly two evidenced pulley-owned rim contact points",
            pulley_id,
        )
    point_ids = {item.point_id for item in points}

    geometry = ir.geometry
    radii_relations = tuple(
        item for item in geometry if item.kind.value == "radius"
    )
    tangent_relations = tuple(
        item for item in geometry if item.kind.value == "tangent"
    )
    wraps = tuple(item for item in geometry if item.kind.value == "wraps")
    attachments = tuple(
        item for item in geometry if item.kind.value == "attached"
    )
    if (
        len(geometry) != 7
        or len(radii_relations) != 2
        or len(tangent_relations) != 2
        or len(wraps) != 1
        or len(attachments) != 2
        or any(
            item.expression is not None
            or item.interval_id != interval.interval_id
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            or len(item.quantity_ids) != len(set(item.quantity_ids))
            for item in geometry
        )
        or {
            frozenset(item.participant_ids) for item in radii_relations
        }
        != {
            frozenset((pulley_id, point_id)) for point_id in point_ids
        }
        or any(len(item.quantity_ids) != 1 for item in radii_relations)
        or {
            frozenset(item.participant_ids) for item in tangent_relations
        }
        != {
            frozenset((rope_id, pulley_id, point_id))
            for point_id in point_ids
        }
        or any(len(item.quantity_ids) != 2 for item in tangent_relations)
        or set(wraps[0].participant_ids) != {rope_id, pulley_id, *point_ids}
        or len(wraps[0].participant_ids) != 4
    ):
        return None, failure(
            "requires two radius and two tangent relations, one four-party wrap, and two attachments",
            pulley_id,
        )

    interactions = ir.interactions
    gravity_interactions = tuple(
        item for item in interactions if item.kind.value == "gravity"
    )
    rope_interactions = tuple(
        item for item in interactions if item.kind.value == "rope_tension"
    )
    if (
        len(interactions) != 3
        or len(gravity_interactions) != 2
        or len(rope_interactions) != 1
    ):
        return None, failure(
            "requires exactly two gravity interactions and one rope-tension interaction"
        )
    rope_interaction = rope_interactions[0]
    if (
        len(rope_interaction.participant_ids) != 4
        or set(rope_interaction.participant_ids)
        != particle_ids | {rope_id, pulley_id}
        or set(rope_interaction.point_ids) != point_ids
        or len(rope_interaction.point_ids) != 2
        or rope_interaction.frame_id != frame.frame_id
        or rope_interaction.interval_id != interval.interval_id
        or rope_interaction.event_id is not None
        or len(rope_interaction.quantity_ids) != 4
        or len(set(rope_interaction.quantity_ids)) != 4
        or not rope_interaction.evidence_refs
        or {
            next(iter(set(item.participant_ids) & particle_ids), None)
            for item in gravity_interactions
        }
        != particle_ids
        or any(
            len(item.participant_ids) != 2
            or len(set(item.participant_ids)) != 2
            or environment_id not in item.participant_ids
            or item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.point_ids
            or len(item.quantity_ids) != 3
            or len(set(item.quantity_ids)) != 3
            or not item.evidence_refs
            for item in gravity_interactions
        )
    ):
        return None, failure(
            "has incomplete or ambiguous force-interaction cardinality",
            rope_interaction.interaction_id,
        )

    states = ir.state_conditions
    taut_states = tuple(
        item
        for item in states
        if item.subject_id == rope_id and item.kind.value == "rope"
    )
    no_slip_states = tuple(
        item
        for item in states
        if item.subject_id == pulley_id and item.kind.value == "rolling"
    )
    if (
        len(states) != 2
        or len(taut_states) != 1
        or taut_states[0].state.value != "taut"
        or taut_states[0].quantity_ids
        or len(no_slip_states) != 1
        or no_slip_states[0].state.value != "no_slip"
        or any(
            item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.expression is not None
            or not item.evidence_refs
            for item in states
        )
    ):
        return None, failure(
            "requires exact evidenced taut-rope and pulley no-slip states without pulley at-rest",
            pulley_id,
        )

    scoped_assumptions = ir.assumptions
    expected_assumptions = {
        ("massless_rope", rope_id),
        ("inextensible_rope", rope_id),
        ("fixed_pulley", pulley_id),
        ("frictionless_axle", pulley_id),
    }
    if (
        len(scoped_assumptions) != 4
        or {(item.kind, item.subject_id) for item in scoped_assumptions}
        != expected_assumptions
        or any(
            item.disposition is not AssumptionDisposition.approved
            or item.assumption_id not in approved_assumption_ids
            or item.interval_id != interval.interval_id
            or item.proposed_role is not None
            or item.proposed_value is not None
            or item.proposed_unit is not None
            or not item.evidence_refs
            for item in scoped_assumptions
        )
    ):
        return None, failure(
            "requires exact approved massless/inextensible/fixed-center/frictionless-axle authority",
            pulley_id,
        )

    quantities = {item.quantity_id: item for item in ir.quantities}
    masses: dict[str, object] = {}
    weights: dict[str, object] = {}
    gravities: list[object] = []
    for interaction in gravity_interactions:
        body_id = next(iter(set(interaction.participant_ids) & particle_ids))
        linked = tuple(quantities.get(item) for item in interaction.quantity_ids)
        local_masses = tuple(
            item
            for item in linked
            if item is not None
            and item.role is QuantityRole.mass
            and item.subject_id == body_id
        )
        local_gravities = tuple(
            item
            for item in linked
            if item is not None
            and item.role is QuantityRole.gravity
            and item.subject_id == environment_id
        )
        local_weights = tuple(
            item
            for item in linked
            if item is not None
            and item.role is QuantityRole.force
            and item.subject_id == body_id
        )
        if not all(
            len(items) == 1
            for items in (local_masses, local_gravities, local_weights)
        ):
            return None, failure(
                "requires one mass, gravity magnitude, and weight per body",
                interaction.interaction_id,
            )
        masses[body_id] = local_masses[0]
        gravities.append(local_gravities[0])
        weights[body_id] = local_weights[0]
    if len({item.quantity_id for item in gravities}) != 1:
        return None, failure("requires one shared gravity magnitude", environment_id)
    gravity = gravities[0]

    inertias = tuple(
        item
        for item in quantities.values()
        if item.role is QuantityRole.moment_of_inertia
        and item.subject_id == pulley_id
    )
    radii = tuple(
        item
        for item in quantities.values()
        if item.role is QuantityRole.radius and item.subject_id == pulley_id
    )
    angular = tuple(
        item
        for item in quantities.values()
        if item.role is QuantityRole.angular_acceleration
        and item.subject_id == pulley_id
    )
    rope_accelerations = tuple(
        item
        for item in quantities.values()
        if item.role is QuantityRole.acceleration
        and item.subject_id == rope_id
        and item.frame_id is None
    )
    if (
        len(inertias) != 1
        or len(radii) != 2
        or len(angular) != 1
        or len(rope_accelerations) != 1
    ):
        return None, failure(
            "requires one inertia, two rim radii, one angular acceleration, and one unframed rope acceleration",
            pulley_id,
        )
    inertia = inertias[0]
    alpha = angular[0]
    rope_acceleration = rope_accelerations[0]

    known = (*masses.values(), gravity, inertia, *radii)
    bad_domain = next(
        (
            item
            for item in known
            if type(item.si_value) is not float
            or not math.isfinite(item.si_value)
            or item.si_value <= 0.0
        ),
        None,
    )
    if bad_domain is not None:
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "massive-pulley Atwood masses, gravity, inertia, and radii must be finite and positive",
            f"quantities.{bad_domain.quantity_id}.si_value",
            bad_domain.quantity_id,
        )
    if radii[0].si_value != radii[1].si_value:
        return None, _issue(
            CompilerIssueCode.invalid_domain,
            "massive-pulley Atwood rim radii must identify one common positive radius",
            "geometry",
            pulley_id,
        )

    def exact_known_unscoped(item: object, *, subject_id: str) -> bool:
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.subject_id == subject_id
            and item.provenance is Provenance.explicit_source
            and bool(item.evidence_refs)
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id is None
            and item.event_id is None
            and item.component
            in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            and item.direction is None
        )

    if (
        any(
            not exact_known_unscoped(item, subject_id=body_id)
            for body_id, item in masses.items()
        )
        or not exact_known_unscoped(gravity, subject_id=environment_id)
        or not exact_known_unscoped(inertia, subject_id=pulley_id)
    ):
        return None, failure(
            "requires exact source-backed unscoped masses, gravity, and inertia"
        )

    radius_by_sign: dict[int, object] = {}
    point_by_sign: dict[int, str] = {}
    for radius in radii:
        sign = getattr(getattr(radius, "direction", None), "sign", None)
        if (
            radius.shape is not QuantityShape.scalar
            or radius.symbol_id is None
            or radius.provenance is not Provenance.explicit_source
            or not radius.evidence_refs
            or radius.point_id not in point_ids
            or radius.frame_id != frame.frame_id
            or radius.interval_id != interval.interval_id
            or radius.event_id is not None
            or radius.component is not QuantityComponent.x
            or sign not in {-1, 1}
            or not _exact_axis_direction(
                radius,
                frame_id=frame.frame_id,
                axis="x",
                sign=sign,
            )
        ):
            return None, failure(
                "requires source-backed left/right point radii on the x axis",
                radius.quantity_id,
            )
        radius_by_sign[sign] = radius
        point_by_sign[sign] = radius.point_id
    if set(radius_by_sign) != {-1, 1} or set(point_by_sign.values()) != point_ids:
        return None, failure("requires one negative-x and one positive-x rim radius")
    for relation in radii_relations:
        point_id = next(iter(set(relation.participant_ids) & point_ids))
        radius = next(
            item for item in radii if item.point_id == point_id
        )
        if tuple(relation.quantity_ids) != (radius.quantity_id,):
            return None, failure(
                "requires each radius relation to bind its own rim radius",
                relation.relation_id,
            )

    def exact_unknown_axis(
        item: object,
        *,
        subject_id: str,
        point_id: str | None,
        component: QuantityComponent,
        sign: int,
    ) -> bool:
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.si_value is None
            and item.provenance in {Provenance.inferred, Provenance.unknown}
            and bool(item.evidence_refs)
            and item.subject_id == subject_id
            and item.point_id == point_id
            and item.frame_id == frame.frame_id
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.component is component
            and _exact_axis_direction(
                item,
                frame_id=frame.frame_id,
                axis=component.value,
                sign=sign,
            )
        )

    if any(
        not exact_unknown_axis(
            item,
            subject_id=body_id,
            point_id=None,
            component=QuantityComponent.y,
            sign=1,
        )
        for body_id, item in weights.items()
    ):
        return None, failure("requires both weights on the positive y axis")

    rope_linked = tuple(
        quantities.get(item) for item in rope_interaction.quantity_ids
    )
    if any(item is None for item in rope_linked):
        return None, failure("contains an unresolved rope-tension quantity")
    local_tensions = tuple(
        item
        for item in rope_linked
        if item.role is QuantityRole.force and item.subject_id in particle_ids
    )
    rim_tensions = tuple(
        item
        for item in rope_linked
        if item.role is QuantityRole.force
        and item.subject_id == pulley_id
        and item.point_id in point_ids
    )
    if (
        len(local_tensions) != 2
        or {item.subject_id for item in local_tensions} != particle_ids
        or len(rim_tensions) != 2
        or {item.point_id for item in rim_tensions} != point_ids
        or any(
            not exact_unknown_axis(
                item,
                subject_id=item.subject_id,
                point_id=None,
                component=QuantityComponent.y,
                sign=-1,
            )
            for item in local_tensions
        )
        or any(
            not exact_unknown_axis(
                item,
                subject_id=pulley_id,
                point_id=item.point_id,
                component=QuantityComponent.y,
                sign=1,
            )
            for item in rim_tensions
        )
    ):
        return None, failure(
            "requires separate upward body tensions and downward left/right rim tensions",
            rope_interaction.interaction_id,
        )

    body_accelerations = tuple(
        item
        for item in quantities.values()
        if item.role is QuantityRole.acceleration
        and item.subject_id in particle_ids
    )
    if (
        len(body_accelerations) != 2
        or {item.subject_id for item in body_accelerations} != particle_ids
        or any(
            item.shape is not QuantityShape.scalar
            or item.symbol_id is None
            or item.si_value is not None
            or item.provenance not in {Provenance.inferred, Provenance.unknown}
            or not item.evidence_refs
            or item.point_id is not None
            or item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.component is not QuantityComponent.y
            for item in body_accelerations
        )
        or rope_acceleration.shape is not QuantityShape.scalar
        or rope_acceleration.symbol_id is None
        or rope_acceleration.si_value is not None
        or rope_acceleration.provenance not in {Provenance.inferred, Provenance.unknown}
        or not rope_acceleration.evidence_refs
        or rope_acceleration.point_id is not None
        or rope_acceleration.interval_id != interval.interval_id
        or rope_acceleration.event_id is not None
        or rope_acceleration.component is not QuantityComponent.unspecified
        or rope_acceleration.direction is not None
        or alpha.shape is not QuantityShape.scalar
        or alpha.symbol_id is None
        or alpha.si_value is not None
        or alpha.provenance not in {Provenance.inferred, Provenance.unknown}
        or not alpha.evidence_refs
        or alpha.point_id is not None
        or alpha.frame_id != frame.frame_id
        or alpha.interval_id != interval.interval_id
        or alpha.event_id is not None
        or alpha.component is not QuantityComponent.z
        or not _exact_axis_direction(
            alpha,
            frame_id=frame.frame_id,
            axis="z",
            sign=1,
        )
    ):
        return None, failure(
            "requires exact local body accelerations, one unframed rope coordinate, and positive-z angular acceleration",
            pulley_id,
        )

    local_tension_by_body = {item.subject_id: item for item in local_tensions}
    rim_tension_by_point = {item.point_id: item for item in rim_tensions}
    acceleration_by_body = {
        item.subject_id: item for item in body_accelerations
    }
    attached_bodies: set[str] = set()
    attached_points: set[str] = set()
    for attachment in attachments:
        body_matches = set(attachment.participant_ids) & particle_ids
        point_matches = set(attachment.participant_ids) & point_ids
        if len(body_matches) != 1 or len(point_matches) != 1:
            return None, failure(
                "requires each attachment to identify one body and one rim point",
                attachment.relation_id,
            )
        body_id = next(iter(body_matches))
        point_id = next(iter(point_matches))
        sign = next(
            key for key, value in point_by_sign.items() if value == point_id
        )
        local_acceleration = acceleration_by_body[body_id]
        if (
            set(attachment.participant_ids)
            != {rope_id, pulley_id, body_id, point_id}
            or set(attachment.quantity_ids)
            != {
                local_tension_by_body[body_id].quantity_id,
                rim_tension_by_point[point_id].quantity_id,
                local_acceleration.quantity_id,
                rope_acceleration.quantity_id,
            }
            or len(attachment.quantity_ids) != 4
            or not _exact_axis_direction(
                local_acceleration,
                frame_id=frame.frame_id,
                axis="y",
                sign=sign,
            )
        ):
            return None, failure(
                "requires exact side-specific tension and acceleration attachment transfers",
                attachment.relation_id,
            )
        attached_bodies.add(body_id)
        attached_points.add(point_id)
    if attached_bodies != particle_ids or attached_points != point_ids:
        return None, failure("requires one distinct attachment on each rope side")

    for relation in tangent_relations:
        point_id = next(iter(set(relation.participant_ids) & point_ids))
        radius = next(item for item in radii if item.point_id == point_id)
        rim_tension = rim_tension_by_point[point_id]
        if set(relation.quantity_ids) != {
            radius.quantity_id,
            rim_tension.quantity_id,
        }:
            return None, failure(
                "requires each tangent relation to bind its signed radius and segment tension",
                relation.relation_id,
            )

    expected_wrap_quantities = {
        *(item.quantity_id for item in radii),
        *(item.quantity_id for item in rim_tensions),
        rope_acceleration.quantity_id,
        alpha.quantity_id,
    }
    if (
        set(wraps[0].quantity_ids) != expected_wrap_quantities
        or len(wraps[0].quantity_ids) != 6
        or set(no_slip_states[0].quantity_ids)
        != {
            *(item.quantity_id for item in radii),
            alpha.quantity_id,
        }
        or len(no_slip_states[0].quantity_ids) != 3
    ):
        return None, failure(
            "requires exact wrap and no-slip quantity carriers",
            wraps[0].relation_id,
        )

    force_dimension = next(iter(weights.values())).dimension
    acceleration_dimension = body_accelerations[0].dimension
    if (
        any(item.dimension != force_dimension for item in (*weights.values(), *local_tensions, *rim_tensions))
        or any(item.dimension != acceleration_dimension for item in (*body_accelerations, rope_acceleration))
        or any(item.dimension != radii[0].dimension for item in radii)
        or any(item.dimension.plus(gravity.dimension) != force_dimension for item in masses.values())
        or any(item.dimension.plus(acceleration_dimension) != force_dimension for item in masses.values())
        or radii[0].dimension.plus(alpha.dimension) != acceleration_dimension
        or radii[0].dimension.plus(force_dimension)
        != inertia.dimension.plus(alpha.dimension)
    ):
        return None, failure("contains a dimensionally inconsistent fixed-axis balance")

    expected_quantities = {
        *(item.quantity_id for item in masses.values()),
        gravity.quantity_id,
        *(item.quantity_id for item in weights.values()),
        *(item.quantity_id for item in local_tensions),
        *(item.quantity_id for item in rim_tensions),
        *(item.quantity_id for item in body_accelerations),
        rope_acceleration.quantity_id,
        inertia.quantity_id,
        *(item.quantity_id for item in radii),
        alpha.quantity_id,
    }
    query_quantity = quantities.get(query.target.target_quantity_id or "")
    allowed_query_quantities = (
        *local_tensions,
        *body_accelerations,
        alpha,
    )
    if (
        set(quantities) != expected_quantities
        or query_quantity not in allowed_query_quantities
        or query.shape is not QuantityShape.scalar
        or query.target.role is not query_quantity.role
        or query.target.subject_id != query_quantity.subject_id
        or query.target.point_id != query_quantity.point_id
        or query.target.frame_id != query_quantity.frame_id
        or query.target.interval_id != interval.interval_id
        or query.target.event_id is not None
        or query.target.component is not query_quantity.component
        or query.target.direction != query_quantity.direction
        or query.output_dimension != query_quantity.dimension
        or not query.evidence_refs
        or ir.constraints
        or {item.symbol_id for item in ir.symbols}
        != {
            item.symbol_id
            for item in quantities.values()
            if item.symbol_id is not None
        }
    ):
        return None, failure(
            "contains extra client equations, quantities, or a nonlocal query target",
            query.query_id,
        )
    return (
        _MassivePulleyAtwoodProfile(
            fixed_axis_angular_quantity_ids=frozenset((alpha.quantity_id,))
        ),
        None,
    )


def _fixed_pulley_particle_contract_issue(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    relevant: set[str],
    approved_assumption_ids: frozenset[str],
) -> CompilerIssue | None:
    """Close the exact evidenced two-particle fixed-pulley template.

    Activation is structural: diagnostic metadata and source wording are never
    consulted.  Other rope topologies remain on their existing generic paths.
    """

    if (
        query.target.role not in {QuantityRole.acceleration, QuantityRole.force}
        or query.shape is not QuantityShape.scalar
    ):
        return None
    entities = tuple(item for item in ir.entities if item.entity_id in relevant)
    entity_by_id = {item.entity_id: item for item in entities}
    if (
        entity_by_id.get(query.target.subject_id) is None
        or entity_by_id[query.target.subject_id].primitive.value != "particle"
    ):
        return None
    interactions = tuple(
        item for item in ir.interactions if item.interaction_id in relevant
    )
    rope_interactions = tuple(
        item for item in interactions if item.kind.value == "rope_tension"
    )
    rope_force_query = (
        query.target.role is QuantityRole.force
        and query.target.target_quantity_id is not None
        and any(
            query.target.target_quantity_id in item.quantity_ids
            for item in rope_interactions
        )
    )
    if query.target.role is QuantityRole.force and not rope_force_query:
        return None
    primitive_ids = {
        primitive: tuple(
            item.entity_id for item in entities if item.primitive.value == primitive
        )
        for primitive in ("particle", "rope", "pulley", "environment")
    }
    wraps = tuple(
        item
        for item in ir.geometry
        if item.relation_id in relevant and item.kind.value == "wraps"
    )
    fixed_signal = any(
        item.state_condition_id in relevant
        and item.subject_id in primitive_ids["pulley"]
        and item.state.value == "at_rest"
        for item in ir.state_conditions
    ) or any(
        item.assumption_id in relevant
        and item.subject_id in primitive_ids["pulley"]
        and item.kind == "fixed_pulley"
        for item in ir.assumptions
    )
    hanging_gravity_topology_signal = (
        bool(primitive_ids["environment"])
        or any(item.kind.value == "gravity" for item in interactions)
        or any(
            item.relation_id in relevant and item.kind.value == "attached"
            for item in ir.geometry
        )
        or any(
            item.state_condition_id in relevant
            and item.kind.value == "rope"
            and item.state.value == "taut"
            for item in ir.state_conditions
        )
    )
    candidate = (
        hanging_gravity_topology_signal
        and bool(rope_interactions)
        and bool(primitive_ids["rope"])
        and (len(primitive_ids["pulley"]) == 1 or bool(wraps) or fixed_signal)
        and (len(primitive_ids["particle"]) >= 2 or fixed_signal)
    )
    if candidate and _complete_inertial_pulley_profile(
        ir,
        relevant,
        approved_assumption_ids,
    ):
        return None
    if not candidate:
        return None

    def failure(detail: str, referenced_id: str | None = None) -> CompilerIssue:
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            f"fixed-pulley particle topology {detail}",
            f"queries.{query.query_id}",
            referenced_id or query.query_id,
        )

    if (
        {key: len(value) for key, value in primitive_ids.items()}
        != {"particle": 2, "rope": 1, "pulley": 1, "environment": 1}
        or len(entities) != 5
        or any(
            not item.evidence_refs or item.component_of_entity_id is not None
            for item in entities
        )
    ):
        return failure(
            "requires exactly two evidenced particles, one rope, one pulley, and one environment"
        )
    body_ids = set(primitive_ids["particle"])
    rope_id = primitive_ids["rope"][0]
    pulley_id = primitive_ids["pulley"][0]
    environment_id = primitive_ids["environment"][0]

    frames = tuple(
        item for item in ir.reference_frames if item.frame_id in relevant
    )
    if len(frames) != 1:
        return failure("requires one evidenced one-dimensional frame", query.target.frame_id)
    frame = frames[0]
    axis = frame.axes[0] if len(frame.axes) == 1 else None
    axis_name = getattr(getattr(axis, "axis", None), "value", None)
    if (
        frame.frame_id != query.target.frame_id
        or frame.frame_type.value != "cartesian_1d"
        or getattr(frame.origin, "kind", None) != "world"
        or frame.parent_frame_id is not None
        or frame.translating_with_entity_id is not None
        or frame.rotating_about_point_id is not None
        or frame.generalized_coordinate_symbol_ids
        or not frame.evidence_refs
        or axis_name not in {"x", "y", "z"}
        or getattr(getattr(axis, "direction", None), "kind", None) != "axis"
        or getattr(axis.direction, "frame_id", None) != frame.frame_id
        or getattr(getattr(axis.direction, "axis", None), "value", None) != axis_name
        or getattr(axis.direction, "sign", None) != 1
    ):
        return failure("requires one exact evidenced Cartesian axis", frame.frame_id)

    intervals = tuple(
        item for item in ir.motion_intervals if item.interval_id in relevant
    )
    if len(intervals) != 1:
        return failure("requires one evidenced motion interval", query.target.interval_id)
    interval = intervals[0]
    expected_subjects = set(entity_by_id)
    if (
        interval.interval_id != query.target.interval_id
        or interval.frame_id != frame.frame_id
        or interval.start_event_id is not None
        or interval.end_event_id is not None
        or len(interval.subject_ids) != len(expected_subjects)
        or set(interval.subject_ids) != expected_subjects
        or not interval.evidence_refs
        or any(item.event_id in relevant for item in ir.events)
        or any(item.point_id in relevant for item in ir.points)
    ):
        return failure(
            "requires one exact event-free interval containing the complete topology",
            interval.interval_id,
        )

    geometry = tuple(item for item in ir.geometry if item.relation_id in relevant)
    attached = tuple(item for item in geometry if item.kind.value == "attached")
    if (
        len(geometry) != 3
        or len(wraps) != 1
        or len(attached) != 2
        or any(
            item.expression is not None
            or item.quantity_ids
            or item.interval_id != interval.interval_id
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            for item in geometry
        )
        or len(wraps[0].participant_ids) != 2
        or set(wraps[0].participant_ids) != {rope_id, pulley_id}
        or {
            frozenset(item.participant_ids) for item in attached
        }
        != {frozenset((rope_id, body_id)) for body_id in body_ids}
    ):
        return failure("requires one wrap and two exact evidenced rope attachments", rope_id)

    states = tuple(
        item for item in ir.state_conditions if item.state_condition_id in relevant
    )
    taut = tuple(
        item
        for item in states
        if item.kind.value == "rope" and item.subject_id == rope_id
    )
    fixed = tuple(
        item
        for item in states
        if item.kind.value == "motion" and item.subject_id == pulley_id
    )
    if (
        len(states) != 2
        or len(taut) != 1
        or taut[0].state.value != "taut"
        or len(fixed) != 1
        or fixed[0].state.value != "at_rest"
        or any(
            item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.expression is not None
            or item.quantity_ids
            or not item.evidence_refs
            for item in states
        )
    ):
        return failure("requires evidenced taut-rope and fixed-pulley states", pulley_id)

    scoped_assumptions = tuple(
        item
        for item in ir.assumptions
        if item.assumption_id in relevant and item.subject_id in {rope_id, pulley_id}
    )
    expected_assumptions = {
        ("massless_rope", rope_id),
        ("inextensible_rope", rope_id),
        ("ideal_massless_frictionless_pulley", pulley_id),
        ("fixed_pulley", pulley_id),
    }
    if (
        len(scoped_assumptions) != 4
        or {(item.kind, item.subject_id) for item in scoped_assumptions}
        != expected_assumptions
        or any(
            item.disposition is not AssumptionDisposition.approved
            or item.assumption_id not in approved_assumption_ids
            or item.interval_id != interval.interval_id
            or item.proposed_role is not None
            or item.proposed_value is not None
            or item.proposed_unit is not None
            or not item.evidence_refs
            for item in scoped_assumptions
        )
    ):
        return failure(
            "requires exact externally approved evidenced rope and pulley assumptions",
            rope_id,
        )

    if len(interactions) != 3 or len(rope_interactions) != 1:
        return failure("requires exactly two gravity interactions and one rope-tension interaction")
    gravity_interactions = tuple(
        item for item in interactions if item.kind.value == "gravity"
    )
    rope_interaction = rope_interactions[0]
    if (
        len(gravity_interactions) != 2
        or {next(iter(set(item.participant_ids) & body_ids), None) for item in gravity_interactions}
        != body_ids
        or any(
            len(item.participant_ids) != 2
            or len(set(item.participant_ids)) != 2
            or environment_id not in item.participant_ids
            or item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.point_ids
            or len(item.quantity_ids) != 3
            or len(set(item.quantity_ids)) != 3
            or not item.evidence_refs
            for item in gravity_interactions
        )
        or len(rope_interaction.participant_ids) != 4
        or set(rope_interaction.participant_ids) != body_ids | {rope_id, pulley_id}
        or rope_interaction.point_ids
        or rope_interaction.frame_id != frame.frame_id
        or rope_interaction.interval_id != interval.interval_id
        or rope_interaction.event_id is not None
        or len(rope_interaction.quantity_ids) != 2
        or len(set(rope_interaction.quantity_ids)) != 2
        or not rope_interaction.evidence_refs
    ):
        return failure(
            "has incomplete or ambiguous interaction cardinality",
            rope_interaction.interaction_id,
        )

    quantity_by_id = {item.quantity_id: item for item in ir.quantities}
    masses: list[object] = []
    gravities: list[object] = []
    weights: list[object] = []
    for interaction in gravity_interactions:
        linked = tuple(quantity_by_id.get(item) for item in interaction.quantity_ids)
        body_id = next(iter(set(interaction.participant_ids) & body_ids))
        local_masses = tuple(
            item for item in linked
            if item is not None and item.role is QuantityRole.mass and item.subject_id == body_id
        )
        local_gravities = tuple(
            item for item in linked
            if item is not None
            and item.role is QuantityRole.gravity
            and item.subject_id == environment_id
        )
        local_weights = tuple(
            item for item in linked
            if item is not None and item.role is QuantityRole.force and item.subject_id == body_id
        )
        if not all(len(items) == 1 for items in (local_masses, local_gravities, local_weights)):
            return failure(
                "requires one mass, gravity magnitude, and weight per body",
                interaction.interaction_id,
            )
        masses.append(local_masses[0])
        gravities.append(local_gravities[0])
        weights.append(local_weights[0])

    tensions = tuple(
        quantity_by_id.get(item) for item in rope_interaction.quantity_ids
    )
    accelerations = tuple(
        item
        for item in ir.quantities
        if item.quantity_id in relevant
        and item.role is QuantityRole.acceleration
        and item.subject_id in body_ids
    )
    if (
        any(item is None for item in tensions)
        or any(item.role is not QuantityRole.force for item in tensions)
        or {item.subject_id for item in tensions} != body_ids
        or len(accelerations) != 2
        or {item.subject_id for item in accelerations} != body_ids
    ):
        return failure(
            "requires exactly two body tensions and two body accelerations",
            rope_interaction.interaction_id,
        )

    known = (*masses, *gravities)
    derived = (*weights, *tensions, *accelerations)
    if any(
        item.shape is not QuantityShape.scalar
        or item.symbol_id is None
        or item.provenance is not Provenance.explicit_source
        or not item.evidence_refs
        or item.point_id is not None
        or item.frame_id is not None
        or item.interval_id is not None
        or item.event_id is not None
        or item.direction is not None
        or item.component.value not in {"magnitude", "unspecified"}
        or not isinstance(item.si_value, float)
        or not math.isfinite(item.si_value)
        or item.si_value <= 0.0
        for item in known
    ):
        bad = next(
            (
                item
                for item in known
                if not isinstance(item.si_value, float)
                or not math.isfinite(item.si_value)
                or item.si_value <= 0.0
            ),
            None,
        )
        if bad is not None:
            return _issue(
                CompilerIssueCode.invalid_domain,
                "fixed-pulley particle masses and gravity magnitudes must be finite and positive",
                f"quantities.{bad.quantity_id}.si_value",
                bad.quantity_id,
            )
        return failure("requires exact source-backed unscoped masses and gravity magnitudes")
    if len({item.si_value for item in gravities}) != 1:
        return failure(
            "requires one shared or numerically equivalent gravity magnitude",
            environment_id,
        )

    def exact_component(item: object, *, sign: int | None) -> bool:
        observed_sign = getattr(getattr(item, "direction", None), "sign", None)
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.si_value is None
            and item.provenance in {Provenance.inferred, Provenance.unknown}
            and bool(item.evidence_refs)
            and item.point_id is None
            and item.frame_id == frame.frame_id
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.component.value == axis_name
            and observed_sign in {-1, 1}
            and (sign is None or observed_sign == sign)
            and _exact_axis_direction(
                item,
                frame_id=frame.frame_id,
                axis=axis_name,
                sign=observed_sign,
            )
        )

    if (
        any(not exact_component(item, sign=-1) for item in weights)
        or any(not exact_component(item, sign=1) for item in tensions)
        or any(
            not exact_component(
                item,
                sign=(
                    None
                    if query.target.role is QuantityRole.acceleration
                    and item.quantity_id == query.target.target_quantity_id
                    else 1
                ),
            )
            for item in accelerations
        )
        or any(
            item.dimension.plus(gravities[0].dimension) != weights[0].dimension
            for item in masses
        )
        or any(item.dimension != weights[0].dimension for item in (*weights, *tensions))
        or any(item.dimension != gravities[0].dimension for item in accelerations)
    ):
        return failure(
            "requires exact weight, tension, and acceleration component directions",
            frame.frame_id,
        )

    relevant_quantity_ids = {
        item.quantity_id for item in ir.quantities if item.quantity_id in relevant
    }
    expected_quantity_ids = {
        item.quantity_id for item in (*masses, *gravities, *derived)
    }
    query_quantity = quantity_by_id.get(query.target.target_quantity_id or "")
    allowed_query_quantities = (
        tensions
        if query.target.role is QuantityRole.force
        else accelerations
    )
    if (
        relevant_quantity_ids != expected_quantity_ids
        or query_quantity not in allowed_query_quantities
        or query.target.subject_id != query_quantity.subject_id
        or query.target.frame_id != frame.frame_id
        or query.target.interval_id != interval.interval_id
        or query.target.event_id is not None
        or query.target.component.value != axis_name
        or query.target.direction != query_quantity.direction
        or not query.evidence_refs
        or any(item.constraint_id in relevant for item in ir.constraints)
        or any(
            item.subject_id == pulley_id
            and item.quantity_id in relevant
            for item in ir.quantities
        )
    ):
        return failure(
            "contains extra client equations, quantities, or an inexact query binding",
            query.query_id,
        )
    return None


def _structural_template_support_issue(
    ir: MechanicsProblemIRV1,
    relevant: set[str],
    approved_assumption_ids: frozenset[str],
    accepted_friction_state_ids: frozenset[str] = frozenset(),
    accepted_fixed_axis_angular_quantity_ids: frozenset[str] = frozenset(),
) -> CompilerIssue | None:
    """Fail precisely when the IR cannot select a server-owned template."""

    primitive = {item.entity_id: item.primitive.value for item in ir.entities}
    frames = {item.frame_id: item for item in ir.reference_frames}
    for quantity in ir.quantities:
        if quantity.quantity_id not in relevant:
            continue
        frame = frames.get(quantity.frame_id)
        if quantity.shape is QuantityShape.tensor:
            return _issue(
                CompilerIssueCode.requires_specialized_model,
                "tensor quantity requires a specialized mechanics model",
                f"quantities.{quantity.quantity_id}",
                quantity.quantity_id,
            )
        if frame is not None and frame.frame_type.value == "rotating" and quantity.role in {QuantityRole.velocity, QuantityRole.acceleration}:
            return _issue(
                CompilerIssueCode.requires_specialized_model,
                "rotating-frame transport terms require a specialized mechanics model",
                f"quantities.{quantity.quantity_id}.frame_id",
                frame.frame_id,
            )
        if (
            frame is not None
            and frame.frame_type.value in {"cartesian_3d", "body_fixed"}
            and primitive.get(quantity.subject_id) in {"rigid_body", "pulley"}
            and quantity.role in {
                QuantityRole.angular_position,
                QuantityRole.angular_velocity,
                QuantityRole.angular_acceleration,
                QuantityRole.angular_momentum,
                QuantityRole.moment,
                QuantityRole.torque,
            }
            and quantity.quantity_id
            not in accepted_fixed_axis_angular_quantity_ids
        ):
            return _issue(
                CompilerIssueCode.requires_specialized_model,
                "three-dimensional rigid rotation requires tensor/Euler specialization",
                f"quantities.{quantity.quantity_id}.frame_id",
                frame.frame_id,
            )
    masses_by_subject: dict[str, list[object]] = {}
    for quantity in ir.quantities:
        if quantity.quantity_id in relevant and quantity.role is QuantityRole.mass:
            masses_by_subject.setdefault(quantity.subject_id, []).append(quantity)
    for subject_id, masses in masses_by_subject.items():
        scoped = {(item.interval_id, item.event_id) for item in masses}
        values = {item.si_value for item in masses if isinstance(item.si_value, float)}
        if len(masses) > 1 and len(scoped) > 1 and (len(values) > 1 or any(item.si_value is None for item in masses)):
            return _issue(
                CompilerIssueCode.requires_specialized_model,
                "time-varying mass requires a specialized mechanics model",
                "quantities",
                subject_id,
            )
    approved = tuple(
        item
        for item in ir.assumptions
        if item.disposition is AssumptionDisposition.approved
        and item.assumption_id in approved_assumption_ids
        and item.assumption_id in relevant
    )
    for assumption in approved:
        if assumption.kind != "force_depends_on_position":
            continue
        return _issue(
            CompilerIssueCode.requires_specialized_model,
            "general variable-force work requires a server-owned typed constitutive dependence that this IR cannot represent",
            f"assumptions.{assumption.assumption_id}",
            assumption.assumption_id,
        )

    for state in ir.state_conditions:
        if state.state_condition_id not in relevant or state.kind.value != "friction":
            continue
        if state.state_condition_id in accepted_friction_state_ids:
            continue
        contacts = tuple(
            item
            for item in ir.interactions
            if item.interaction_id in relevant
            and item.kind.value == "contact"
            and state.subject_id in item.participant_ids
            and item.interval_id == state.interval_id
            and item.event_id == state.event_id
        )
        linked = tuple(
            item
            for item in ir.quantities
            if len(contacts) == 1 and item.quantity_id in contacts[0].quantity_ids
        )
        tangent = tuple(item for item in linked if item.role is QuantityRole.force and item.component.value == "tangential")
        normal = tuple(item for item in linked if item.role is QuantityRole.force and item.component.value == "normal")
        coefficients = tuple(item for item in linked if item.role is QuantityRole.coefficient_friction)
        if state.state.value == "inactive":
            normal_accelerations = tuple(
                item
                for item in linked
                if item.role is QuantityRole.acceleration
                and item.component.value == "normal"
            )
            incline_ids = tuple(
                item
                for item in (contacts[0].participant_ids if len(contacts) == 1 else ())
                if primitive.get(item) == "incline"
            )
            touching = tuple(
                item
                for item in ir.state_conditions
                if len(normal) == len(normal_accelerations) == 1
                and item.state_condition_id in relevant
                and item.kind.value == "contact"
                and item.state.value == "touching"
                and item.subject_id == state.subject_id
                and item.interval_id == state.interval_id
                and item.event_id == state.event_id
                and set(item.quantity_ids)
                == {normal[0].quantity_id, normal_accelerations[0].quantity_id}
                and len(item.quantity_ids) == 2
                and item.evidence_refs
            )
            fixed = tuple(
                item
                for item in ir.state_conditions
                if len(incline_ids) == 1
                and item.state_condition_id in relevant
                and item.kind.value == "motion"
                and item.state.value == "at_rest"
                and item.subject_id == incline_ids[0]
                and item.interval_id == state.interval_id
                and item.event_id == state.event_id
                and not item.quantity_ids
                and item.evidence_refs
            )
            if (
                len(contacts) != 1
                or not contacts[0].evidence_refs
                or len(incline_ids) != 1
                or tangent
                or coefficients
                or len(normal) != 1
                or len(normal_accelerations) != 1
                or len(touching) != 1
                or len(fixed) != 1
                or state.quantity_ids
                or not state.evidence_refs
            ):
                return _issue(
                    CompilerIssueCode.requires_specialized_model,
                    "frictionless incline contact needs evidenced inactive friction, touching normal contact, and a fixed surface",
                    f"state_conditions.{state.state_condition_id}",
                    state.state_condition_id,
                )
            continue
        if (
            state.state.value not in {"sticking", "sliding"}
            or len(contacts) != 1
            or len(tangent) != 1
            or len(normal) != 1
            or len(coefficients) != 1
            or (state.state.value == "sliding" and tangent[0].direction is None)
        ):
            return _issue(
                CompilerIssueCode.requires_specialized_model,
                "contact friction needs one valid contact, normal/tangent pair, and an exact sticking/sliding direction regime",
                f"state_conditions.{state.state_condition_id}",
                state.state_condition_id,
            )

    for interaction in ir.interactions:
        if interaction.interaction_id not in relevant or interaction.kind.value != "collision":
            continue
        interval = next(
            (item for item in ir.motion_intervals if item.interval_id == interaction.interval_id),
            None,
        )
        start = next(
            (item for item in ir.events if interval is not None and item.event_id == interval.start_event_id),
            None,
        )
        end = next(
            (item for item in ir.events if interval is not None and item.event_id == interval.end_event_id),
            None,
        )
        participants = set(interaction.participant_ids)
        velocities = tuple(
            item
            for item in ir.quantities
            if item.quantity_id in interaction.quantity_ids
            and item.role is QuantityRole.velocity
            and item.subject_id in participants
        )
        pairs = {
            (item.subject_id, item.event_id, item.frame_id, item.component.value)
            for item in velocities
        }
        expected_pairs = {
            (subject_id, event_id)
            for subject_id in participants
            for event_id in (
                getattr(start, "event_id", None),
                getattr(end, "event_id", None),
            )
        }
        observed_pairs = {(subject_id, event_id) for subject_id, event_id, _, _ in pairs}
        scopes = {(frame_id, component) for _, _, frame_id, component in pairs}
        duplicate_collision = sum(
            item.kind.value == "collision"
            and set(item.participant_ids) == participants
            and item.interval_id == interaction.interval_id
            for item in ir.interactions
        ) != 1
        if (
            len(participants) != 2
            or interval is None
            or start is None
            or end is None
            or start.kind.value != "collision_start"
            or end.kind.value != "collision_end"
            or set(start.subject_ids) != participants
            or set(end.subject_ids) != participants
            or observed_pairs != expected_pairs
            or len(pairs) != 4
            or len(scopes) != 1
            or next(iter(scopes), (None, "unspecified"))[0] != interaction.frame_id
            or next(iter(scopes), (None, "unspecified"))[1] in {"unspecified", "magnitude"}
            or duplicate_collision
        ):
            return _issue(
                CompilerIssueCode.requires_specialized_model,
                "collision needs one paired interaction and reciprocal start/end line-component quantities",
                f"interactions.{interaction.interaction_id}",
                interaction.interaction_id,
            )

    for assumption in approved:
        if assumption.kind != "linear_vibration":
            continue
        regimes = {
            kind: tuple(
                item
                for item in approved
                if item.kind == kind
                and item.subject_id == assumption.subject_id
                and item.interval_id in {None, assumption.interval_id}
            )
            for kind in ("damped", "undamped", "forced_vibration", "free_vibration")
        }
        interval = next(
            (item for item in ir.motion_intervals if item.interval_id == assumption.interval_id),
            None,
        )
        states = tuple(
            item
            for item in ir.state_conditions
            if item.subject_id == assumption.subject_id
            and item.interval_id == assumption.interval_id
            and item.event_id == getattr(interval, "start_event_id", None)
            and item.kind.value == "initial"
            and item.evidence_refs
        )
        state_quantity_ids = {quantity_id for state in states for quantity_id in state.quantity_ids}
        displacements = tuple(
            item
            for item in ir.quantities
            if item.subject_id == assumption.subject_id
            and item.interval_id == assumption.interval_id
            and item.event_id is None
            and item.role in {
                QuantityRole.displacement,
                QuantityRole.generalized_coordinate,
            }
            and item.shape is QuantityShape.scalar
            and item.symbol_id is not None
        )
        displacement = displacements[0] if len(displacements) == 1 else None
        initial_position_role = (
            displacement.role if displacement is not None else QuantityRole.displacement
        )
        initial_velocity_role = (
            QuantityRole.generalized_speed
            if displacement is not None
            and displacement.role is QuantityRole.generalized_coordinate
            else QuantityRole.velocity
        )
        initial_values = tuple(
            item
            for item in ir.quantities
            if item.quantity_id in state_quantity_ids
            and item.si_value is not None
            and item.evidence_refs
            and item.symbol_id is not None
            and item.subject_id == assumption.subject_id
            and item.interval_id == assumption.interval_id
            and item.event_id == getattr(interval, "start_event_id", None)
            and item.role in {initial_position_role, initial_velocity_role}
            and displacement is not None
            and item.point_id == displacement.point_id
            and item.frame_id == displacement.frame_id
            and item.component is displacement.component
        )
        times = tuple(
            item
            for item in ir.quantities
            if displacement is not None
            and item.role is QuantityRole.time
            and item.subject_id == assumption.subject_id
            and item.point_id is None
            and item.frame_id == displacement.frame_id
            and item.interval_id == assumption.interval_id
            and item.event_id is None
            and item.shape is QuantityShape.scalar
            and item.symbol_id is not None
        )
        linked_forces = tuple(
            quantity
            for interaction in ir.interactions
            if interaction.kind.value == "applied_force"
            and interaction.interval_id == assumption.interval_id
            and assumption.subject_id in interaction.participant_ids
            for quantity in ir.quantities
            if quantity.quantity_id in interaction.quantity_ids
            and quantity.role is QuantityRole.force
        )
        forced_ok = (
            bool(regimes["forced_vibration"])
            and len(linked_forces) == 1
            and linked_forces[0].si_value is not None
        ) or (bool(regimes["free_vibration"]) and not linked_forces)
        if (
            bool(regimes["damped"]) == bool(regimes["undamped"])
            or bool(regimes["forced_vibration"]) == bool(regimes["free_vibration"])
            or interval is None
            or interval.start_event_id is None
            or len(states) != 1
            or displacement is None
            or len(times) != 1
            or len(initial_values) != 2
            or {item.role for item in initial_values}
            != {initial_position_role, initial_velocity_role}
            or any(
                not set(item.evidence_refs).issubset(set(states[0].evidence_refs))
                for item in initial_values
            )
            or not forced_ok
        ):
            return _issue(
                CompilerIssueCode.requires_specialized_model,
                "linear vibration needs one typed time variable, exact damping/forcing authority, and two source-backed initial bindings",
                f"assumptions.{assumption.assumption_id}",
                assumption.assumption_id,
            )

    for relation in ir.geometry:
        if relation.relation_id not in relevant or relation.kind.value != "wraps":
            continue
        ropes = tuple(item for item in relation.participant_ids if primitive.get(item) == "rope")
        pulleys = tuple(item for item in relation.participant_ids if primitive.get(item) == "pulley")
        interactions = tuple(
            item
            for item in ir.interactions
            if item.interaction_id in relevant
            and item.kind.value == "rope_tension"
            and set((*ropes, *pulleys)).issubset(item.participant_ids)
            and relation.interval_id in {None, item.interval_id}
        )
        if len(ropes) != 1 or len(pulleys) != 1 or not relation.evidence_refs or len(interactions) != 1:
            return _issue(
                CompilerIssueCode.requires_specialized_model,
                "wrapped rope topology does not identify exactly one evidenced rope/pulley application",
                f"geometry.{relation.relation_id}",
                relation.relation_id,
            )
        interaction = interactions[0]
        bodies = tuple(
            item
            for item in interaction.participant_ids
            if primitive.get(item) in {"particle", "rigid_body", "body_component"}
        )
        pulley_motion = any(
            item.subject_id == pulleys[0]
            and item.interval_id == interaction.interval_id
            and item.role in {QuantityRole.displacement, QuantityRole.velocity, QuantityRole.acceleration}
            for item in ir.quantities
        )
        fixed = any(
            item.kind == "fixed_pulley"
            and item.subject_id == pulleys[0]
            and item.interval_id in {None, interaction.interval_id}
            for item in approved
        ) or any(
            state.subject_id == pulleys[0]
            and state.state.value == "at_rest"
            and state.interval_id == interaction.interval_id
            and state.evidence_refs
            for state in ir.state_conditions
        )
        if not ((fixed and len(bodies) == 2 and not pulley_motion) or (not fixed and len(bodies) == 1 and pulley_motion)):
            return _issue(
                CompilerIssueCode.requires_specialized_model,
                "wrapped topology cannot determine fixed/moving pulley coefficients",
                f"geometry.{relation.relation_id}",
                relation.relation_id,
            )
    return None


def _shape_for_quantity(shape: QuantityShape) -> SymbolShape | None:
    if shape is QuantityShape.scalar:
        return SymbolShape.scalar
    if shape is QuantityShape.vector:
        return SymbolShape.vector
    return None


def _literal_expression(quantity) -> MathExpression | None:
    value = quantity.si_value
    if value is None:
        return None
    if quantity.shape is QuantityShape.scalar and isinstance(value, float):
        return LiteralNode(value=value, dimension=quantity.dimension)
    if quantity.shape is QuantityShape.vector and isinstance(value, tuple):
        return VectorNode(
            items=tuple(LiteralNode(value=item, dimension=quantity.dimension) for item in value),
            dimension=quantity.dimension,
        )
    return None


def _direction_sign(quantity) -> int:
    direction = quantity.direction
    sign = getattr(direction, "sign", 1) if direction is not None else 1
    return sign if sign in {-1, 1} else 1


def _canonical_direction_key(direction) -> str | None:
    if direction is None:
        return None
    payload = direction.model_dump(mode="json", warnings="none")
    # Axis sign is carried separately and applied exactly once by the law
    # emitter.  Every other part of the direction is part of compatibility.
    payload.pop("sign", None)
    return _canonical_json(payload)


def _direction_key(quantity) -> str | None:
    return _canonical_direction_key(quantity.direction)


_EXTERNAL_AUTHORITY_LIMIT = 256
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class _AuthoritySnapshot:
    approved_assumption_ids: frozenset[str]
    corrections: Mapping[str, CorrectionAuthorization]
    assumptions: Mapping[str, AssumptionAuthorization]


def _bounded_identifier(value: object) -> bool:
    return type(value) is str and _IDENTIFIER_PATTERN.fullmatch(value) is not None


def _snapshot_authority_inputs(
    approved_assumption_ids: Collection[str] | None,
    authorized_corrections: Mapping[str, CorrectionAuthorization] | None,
    authorized_assumptions: Mapping[str, AssumptionAuthorization] | None,
) -> tuple[_AuthoritySnapshot | None, CompilerIssue | None]:
    approved: set[str] = set()
    values: object = () if approved_assumption_ids is None else approved_assumption_ids
    if isinstance(values, (str, bytes)):
        return None, _issue(
            CompilerIssueCode.invalid_binding,
            "approved assumption authority must be a bounded collection of exact IDs",
            "approved_assumption_ids",
        )
    try:
        iterator = iter(values)
        for index in range(_EXTERNAL_AUTHORITY_LIMIT + 1):
            try:
                value = next(iterator)
            except StopIteration:
                break
            if index >= _EXTERNAL_AUTHORITY_LIMIT or not _bounded_identifier(value):
                return None, _issue(
                    CompilerIssueCode.invalid_binding,
                    "approved assumption authority exceeds its bound or contains an invalid ID",
                    f"approved_assumption_ids.{index}",
                )
            approved.add(value)
    except Exception:
        return None, _issue(
            CompilerIssueCode.invalid_binding,
            "approved assumption authority could not be snapshotted safely",
            "approved_assumption_ids",
        )

    def snapshot_map(
        source: object,
        record_type: type[CorrectionAuthorization] | type[AssumptionAuthorization],
        id_field: str,
        path: str,
    ) -> tuple[dict[str, object] | None, CompilerIssue | None]:
        if source is None:
            source = {}
        if not isinstance(source, Mapping):
            return None, _issue(
                CompilerIssueCode.invalid_binding,
                "external authority must be a bounded mapping of exact immutable records",
                path,
            )
        snapshot: dict[str, object] = {}
        try:
            iterator = iter(source.items())
            for index in range(_EXTERNAL_AUTHORITY_LIMIT + 1):
                try:
                    key, record = next(iterator)
                except StopIteration:
                    break
                if index >= _EXTERNAL_AUTHORITY_LIMIT:
                    return None, _issue(
                        CompilerIssueCode.invalid_binding,
                        "external authority mapping exceeds its bound",
                        path,
                    )
                item_path = f"{path}.{index}"
                if (
                    not _bounded_identifier(key)
                    or type(record) is not record_type
                    or getattr(record, id_field, None) != key
                    or not _bounded_identifier(getattr(record, "subject_id", None))
                    or type(getattr(record, "role", None)) is not str
                    or not 1 <= len(record.role) <= 64
                    or type(getattr(record, "raw_value", None)) is not str
                    or not 1 <= len(record.raw_value) <= 80
                    or type(getattr(record, "raw_unit", None)) is not str
                    or len(record.raw_unit) > 48
                    or (
                        record.interval_id is not None
                        and not _bounded_identifier(record.interval_id)
                    )
                    or (
                        record_type is CorrectionAuthorization
                        and record.event_id is not None
                        and not _bounded_identifier(record.event_id)
                    )
                ):
                    return None, _issue(
                        CompilerIssueCode.invalid_binding,
                        "external authority key and exact immutable record must agree",
                        item_path,
                        key if _bounded_identifier(key) else None,
                    )
                if record_type is CorrectionAuthorization:
                    copied = CorrectionAuthorization(
                        correction_id=record.correction_id,
                        subject_id=record.subject_id,
                        role=record.role,
                        raw_value=record.raw_value,
                        raw_unit=record.raw_unit,
                        interval_id=record.interval_id,
                        event_id=record.event_id,
                    )
                else:
                    copied = AssumptionAuthorization(
                        assumption_id=record.assumption_id,
                        subject_id=record.subject_id,
                        role=record.role,
                        raw_value=record.raw_value,
                        raw_unit=record.raw_unit,
                        interval_id=record.interval_id,
                    )
                snapshot[key] = copied
        except Exception:
            return None, _issue(
                CompilerIssueCode.invalid_binding,
                "external authority mapping could not be snapshotted safely",
                path,
            )
        return snapshot, None

    corrections, issue = snapshot_map(
        authorized_corrections,
        CorrectionAuthorization,
        "correction_id",
        "authorized_corrections",
    )
    if issue is not None or corrections is None:
        return None, issue
    assumptions, issue = snapshot_map(
        authorized_assumptions,
        AssumptionAuthorization,
        "assumption_id",
        "authorized_assumptions",
    )
    if issue is not None or assumptions is None:
        return None, issue
    return (
        _AuthoritySnapshot(
            approved_assumption_ids=frozenset(approved),
            corrections=dict(corrections),
            assumptions=dict(assumptions),
        ),
        None,
    )


def _authorization_matches_quantity(
    quantity: object,
    authorization: CorrectionAuthorization | AssumptionAuthorization | None,
    *,
    correction: bool,
) -> bool:
    expected_type = CorrectionAuthorization if correction else AssumptionAuthorization
    if type(authorization) is not expected_type:
        return False
    if correction:
        event_matches = authorization.event_id == quantity.event_id
    else:
        event_matches = quantity.event_id is None
    return (
        authorization.subject_id == quantity.subject_id
        and authorization.role == quantity.role.value
        and authorization.raw_value == quantity.raw_value
        and authorization.raw_unit == quantity.raw_unit
        and authorization.interval_id == quantity.interval_id
        and event_matches
    )


def _known_value_authority_issue(
    ir: MechanicsProblemIRV1,
    relevant: set[str],
    authority: _AuthoritySnapshot,
) -> CompilerIssue | None:
    """Reject a normalized value unless its retained authority closes.

    The compiler deliberately rechecks this boundary because an immutable IR
    instance can still be forged with ``model_copy`` after Stage 1.  A value
    that fails this check remains neither a known nor an equation source: the
    entire compilation fails closed before law selection.
    """

    evidence_ids = {item.evidence_id for item in ir.source_evidence}
    assumptions = {item.assumption_id: item for item in ir.assumptions}
    for quantity in sorted(ir.quantities, key=lambda item: item.quantity_id):
        if quantity.quantity_id not in relevant or quantity.si_value is None:
            continue
        try:
            normalized = normalize_quantity(
                quantity.raw_value,
                quantity.raw_unit,
                quantity.shape,
                quantity.dimension,
            )
        except Exception:
            return _issue(
                CompilerIssueCode.invalid_binding,
                "known value could not be reconstructed by the trusted SI normalizer",
                f"quantities.{quantity.quantity_id}.si_value",
                quantity.quantity_id,
            )
        if normalized.value != quantity.si_value or normalized.si_unit != quantity.si_unit:
            return _issue(
                CompilerIssueCode.invalid_binding,
                "stored normalized value or SI unit differs from trusted re-normalization",
                f"quantities.{quantity.quantity_id}.si_value",
                quantity.quantity_id,
            )
        valid = False
        if quantity.provenance is Provenance.explicit_source:
            valid = bool(quantity.evidence_refs) and set(quantity.evidence_refs).issubset(evidence_ids)
        elif quantity.provenance is Provenance.user_correction:
            authorization = authority.corrections.get(quantity.correction_id or "")
            valid = (
                bool(quantity.correction_id)
                and _authorization_matches_quantity(
                    quantity,
                    authorization,
                    correction=True,
                )
            )
        elif quantity.provenance is Provenance.server_default:
            assumption = assumptions.get(quantity.assumption_policy_ref or "")
            authorization = authority.assumptions.get(quantity.assumption_policy_ref or "")
            valid = (
                assumption is not None
                and quantity.assumption_policy_ref in authority.approved_assumption_ids
                and assumption.disposition is AssumptionDisposition.approved
                and assumption.subject_id == quantity.subject_id
                and assumption.interval_id == quantity.interval_id
                and assumption.proposed_role is quantity.role
                and assumption.proposed_value == quantity.raw_value
                and assumption.proposed_unit == quantity.raw_unit
                and _authorization_matches_quantity(
                    quantity,
                    authorization,
                    correction=False,
                )
            )
        elif quantity.provenance in {Provenance.inferred, Provenance.unknown}:
            valid = False
        if not valid:
            return _issue(
                CompilerIssueCode.invalid_binding,
                "normalized value lacks closed trusted source, correction, or approved server authority",
                f"quantities.{quantity.quantity_id}.si_value",
                quantity.quantity_id,
            )
    return None


_STRICTLY_POSITIVE_ROLES = frozenset(
    {
        QuantityRole.mass,
        QuantityRole.radius,
        QuantityRole.length,
        QuantityRole.area,
        QuantityRole.volume,
        QuantityRole.density,
        QuantityRole.moment_of_inertia,
        QuantityRole.stiffness,
        QuantityRole.period,
    }
)
_NONNEGATIVE_ROLES = frozenset(
    {
        QuantityRole.time,
        QuantityRole.duration,
        QuantityRole.speed,
        QuantityRole.frequency,
        QuantityRole.damping,
        QuantityRole.coefficient_friction,
    }
)


def _known_role_domain_issue(
    ir: MechanicsProblemIRV1,
    relevant: set[str],
) -> CompilerIssue | None:
    for quantity in sorted(ir.quantities, key=lambda item: item.quantity_id):
        if quantity.quantity_id not in relevant or quantity.si_value is None:
            continue
        role = quantity.role
        if role not in _STRICTLY_POSITIVE_ROLES | _NONNEGATIVE_ROLES | {
            QuantityRole.coefficient_restitution
        }:
            continue
        value = quantity.si_value
        valid = isinstance(value, float)
        if valid and role in _STRICTLY_POSITIVE_ROLES:
            valid = value > 0.0
        elif valid and role in _NONNEGATIVE_ROLES:
            valid = value >= 0.0
        elif valid and role is QuantityRole.coefficient_restitution:
            valid = 0.0 <= value <= 1.0
        if not valid:
            return _issue(
                CompilerIssueCode.invalid_domain,
                "known quantity violates the certified physical role domain",
                f"quantities.{quantity.quantity_id}.si_value",
                quantity.quantity_id,
            )
    return None


def _validate_reciprocal_bindings(
    ir: MechanicsProblemIRV1,
) -> tuple[dict[str, SymbolDefinition], CompilerIssue | None]:
    symbols = {symbol.symbol_id: symbol for symbol in ir.symbols}
    quantities = {quantity.quantity_id: quantity for quantity in ir.quantities}
    if len(symbols) != len(ir.symbols) or len(quantities) != len(ir.quantities):
        return symbols, _issue(
            CompilerIssueCode.invalid_binding,
            "duplicate symbol or quantity identity is not allowed",
            "ir",
        )
    for quantity in ir.quantities:
        if quantity.symbol_id is None:
            continue
        symbol = symbols.get(quantity.symbol_id)
        expected_shape = _shape_for_quantity(quantity.shape)
        if (
            symbol is None
            or symbol.quantity_id != quantity.quantity_id
            or symbol.dimension != quantity.dimension
            or symbol.shape is not expected_shape
            or (
                quantity.shape is QuantityShape.vector
                and isinstance(quantity.si_value, tuple)
                and symbol.vector_length != len(quantity.si_value)
            )
        ):
            return symbols, _issue(
                CompilerIssueCode.invalid_binding,
                "quantity and symbol bindings must be reciprocal with equal shape and dimension",
                f"quantities.{quantity.quantity_id}",
                quantity.quantity_id,
            )
    for symbol in ir.symbols:
        if symbol.quantity_id is None:
            continue
        quantity = quantities.get(symbol.quantity_id)
        if quantity is None or quantity.symbol_id != symbol.symbol_id:
            return symbols, _issue(
                CompilerIssueCode.invalid_binding,
                "symbol quantity binding is not reciprocal",
                f"symbols.{symbol.symbol_id}",
                symbol.symbol_id,
            )
    return symbols, None


def _structural_reference_issue(ir: MechanicsProblemIRV1, query: IRQuery) -> CompilerIssue | None:
    entity_ids = {item.entity_id for item in ir.entities}
    point_ids = {item.point_id for item in ir.points}
    frame_ids = {item.frame_id for item in ir.reference_frames}
    interval_ids = {item.interval_id for item in ir.motion_intervals}
    event_ids = {item.event_id for item in ir.events}
    quantity_ids = {item.quantity_id for item in ir.quantities}
    symbol_ids = {item.symbol_id for item in ir.symbols}
    assumption_ids = {item.assumption_id for item in ir.assumptions}
    evidence_ids = {item.evidence_id for item in ir.source_evidence}
    collections = (
        ("source_evidence", tuple(item.evidence_id for item in ir.source_evidence)),
        ("entities", tuple(item.entity_id for item in ir.entities)),
        ("points", tuple(item.point_id for item in ir.points)),
        ("reference_frames", tuple(item.frame_id for item in ir.reference_frames)),
        ("motion_intervals", tuple(item.interval_id for item in ir.motion_intervals)),
        ("events", tuple(item.event_id for item in ir.events)),
        ("symbols", tuple(item.symbol_id for item in ir.symbols)),
        ("quantities", tuple(item.quantity_id for item in ir.quantities)),
        ("geometry", tuple(item.relation_id for item in ir.geometry)),
        ("interactions", tuple(item.interaction_id for item in ir.interactions)),
        ("constraints", tuple(item.constraint_id for item in ir.constraints)),
        ("state_conditions", tuple(item.state_condition_id for item in ir.state_conditions)),
        ("assumptions", tuple(item.assumption_id for item in ir.assumptions)),
        ("queries", tuple(item.query_id for item in ir.queries)),
    )
    for path, identifiers in collections:
        if len(set(identifiers)) != len(identifiers):
            return _issue(CompilerIssueCode.invalid_binding, "duplicate record identity is not allowed", path)
    definition_ids = tuple(identifier for _, identifiers in collections for identifier in identifiers)
    if len(set(definition_ids)) != len(definition_ids):
        return _issue(
            CompilerIssueCode.invalid_binding,
            "record identities must be unique across mechanics namespaces",
            "ir",
        )

    def missing(value: str | None, allowed: set[str]) -> bool:
        return value is not None and value not in allowed

    def unresolved_refs(values: Iterable[str], allowed: set[str]) -> str | None:
        return next((item for item in values if item not in allowed), None)

    def bad_evidence(owner: object) -> str | None:
        return unresolved_refs(getattr(owner, "evidence_refs", ()), evidence_ids)

    intervals = {item.interval_id: item for item in ir.motion_intervals}
    events = {item.event_id: item for item in ir.events}
    points = {item.point_id: item for item in ir.points}
    frames_by_id = {item.frame_id: item for item in ir.reference_frames}
    quantities = {item.quantity_id: item for item in ir.quantities}
    quantity_by_symbol = {
        item.symbol_id: item for item in ir.quantities if item.symbol_id is not None
    }

    def expression_scope_issue(
        expression: MathExpression | None,
        *,
        path: str,
        subject_ids: set[str],
        interval_id: str | None,
        event_id: str | None,
    ) -> CompilerIssue | None:
        if expression is None:
            return None
        bound = tuple(
            quantity_by_symbol[item]
            for item in _expression_symbol_ids(expression)
            if item in quantity_by_symbol
        )
        if any(
            item.subject_id not in subject_ids and item.point_id not in subject_ids
            for item in bound
        ):
            return _issue(CompilerIssueCode.invalid_binding, "relation expression quantity is outside its subject scope", path)
        frames_in_expression = {item.frame_id for item in bound if item.frame_id is not None}
        intervals_in_expression = {item.interval_id for item in bound if item.interval_id is not None}
        events_in_expression = {item.event_id for item in bound if item.event_id is not None}
        if len(frames_in_expression) > 1:
            return _issue(CompilerIssueCode.invalid_binding, "relation expression mixes reference frames without a transform", path)
        if len(intervals_in_expression) > 1 or (interval_id is not None and intervals_in_expression - {interval_id}):
            return _issue(CompilerIssueCode.invalid_binding, "relation expression mixes motion intervals", path)
        if event_id is not None and events_in_expression - {event_id}:
            return _issue(CompilerIssueCode.invalid_binding, "relation expression event does not match its declared event", path)
        if len(events_in_expression) > 1:
            event_intervals = {
                linked_interval
                for linked_event in events_in_expression
                for linked_interval in events[linked_event].interval_ids
            }
            if len(event_intervals) != 1 or (interval_id is not None and event_intervals != {interval_id}):
                return _issue(CompilerIssueCode.invalid_binding, "relation expression combines events outside one reciprocal interval", path)
        return None

    for entity in ir.entities:
        if missing(entity.component_of_entity_id, entity_ids):
            return _issue(CompilerIssueCode.invalid_binding, "entity component owner does not resolve", f"entities.{entity.entity_id}.component_of_entity_id", entity.component_of_entity_id)
        bad = bad_evidence(entity)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "entity evidence does not resolve", f"entities.{entity.entity_id}.evidence_refs", bad)
    for point in ir.points:
        if missing(point.owner_entity_id, entity_ids) or missing(point.frame_id, frame_ids):
            return _issue(CompilerIssueCode.invalid_binding, "point owner or frame does not resolve", f"points.{point.point_id}", point.point_id)
        bad = bad_evidence(point)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "point evidence does not resolve", f"points.{point.point_id}.evidence_refs", bad)
    for frame in ir.reference_frames:
        if missing(frame.parent_frame_id, frame_ids) or frame.parent_frame_id == frame.frame_id:
            return _issue(CompilerIssueCode.invalid_binding, "frame parent does not resolve safely", f"reference_frames.{frame.frame_id}.parent_frame_id", frame.parent_frame_id)
        if missing(frame.translating_with_entity_id, entity_ids) or missing(frame.rotating_about_point_id, point_ids):
            return _issue(CompilerIssueCode.invalid_binding, "frame motion binding does not resolve", f"reference_frames.{frame.frame_id}", frame.frame_id)
        origin = frame.origin
        if missing(getattr(origin, "point_id", None), point_ids) or missing(getattr(origin, "entity_id", None), entity_ids) or missing(getattr(origin, "frame_id", None), frame_ids):
            return _issue(CompilerIssueCode.invalid_binding, "frame origin does not resolve", f"reference_frames.{frame.frame_id}.origin", frame.frame_id)
        if unresolved_refs(frame.generalized_coordinate_symbol_ids, symbol_ids):
            bad = unresolved_refs(frame.generalized_coordinate_symbol_ids, symbol_ids)
            return _issue(CompilerIssueCode.invalid_binding, "frame generalized coordinate does not resolve", f"reference_frames.{frame.frame_id}.generalized_coordinate_symbol_ids", bad)
        for axis in frame.axes:
            direction = axis.direction
            if missing(getattr(direction, "frame_id", None), frame_ids) or missing(getattr(direction, "symbol_id", None), symbol_ids):
                return _issue(CompilerIssueCode.invalid_binding, "frame axis direction does not resolve", f"reference_frames.{frame.frame_id}.axes", frame.frame_id)
        bad = bad_evidence(frame)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "frame evidence does not resolve", f"reference_frames.{frame.frame_id}.evidence_refs", bad)

    for interval in ir.motion_intervals:
        bad_subject = unresolved_refs(interval.subject_ids, entity_ids)
        if bad_subject or missing(interval.frame_id, frame_ids):
            return _issue(CompilerIssueCode.invalid_binding, "motion interval subject or frame does not resolve", f"motion_intervals.{interval.interval_id}", bad_subject or interval.frame_id)
        for field_name in ("start_event_id", "end_event_id"):
            event_id = getattr(interval, field_name)
            if event_id is None:
                continue
            event = events.get(event_id)
            if event is None or interval.interval_id not in event.interval_ids or not set(event.subject_ids).issubset(interval.subject_ids):
                return _issue(CompilerIssueCode.invalid_binding, "interval endpoint and event membership must be reciprocal", f"motion_intervals.{interval.interval_id}.{field_name}", event_id)
        bad = bad_evidence(interval)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "interval evidence does not resolve", f"motion_intervals.{interval.interval_id}.evidence_refs", bad)
    for event in ir.events:
        bad_subject = unresolved_refs(event.subject_ids, entity_ids)
        bad_interval = unresolved_refs(event.interval_ids, interval_ids)
        if bad_subject or bad_interval or missing(event.time_quantity_id, quantity_ids):
            return _issue(CompilerIssueCode.invalid_binding, "event subject, interval, or time quantity does not resolve", f"events.{event.event_id}", bad_subject or bad_interval or event.time_quantity_id)
        for interval_id in event.interval_ids:
            interval = intervals[interval_id]
            if event.event_id not in {interval.start_event_id, interval.end_event_id} or not set(event.subject_ids).issubset(interval.subject_ids):
                return _issue(CompilerIssueCode.invalid_binding, "event and interval membership must be reciprocal", f"events.{event.event_id}.interval_ids", interval_id)
        if event.time_quantity_id is not None:
            time_quantity = quantities[event.time_quantity_id]
            if time_quantity.role is not QuantityRole.time or time_quantity.event_id not in {None, event.event_id}:
                return _issue(CompilerIssueCode.invalid_binding, "event time binding is not a time quantity in the same event", f"events.{event.event_id}.time_quantity_id", event.time_quantity_id)
        bad = bad_evidence(event)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "event evidence does not resolve", f"events.{event.event_id}.evidence_refs", bad)

    target = query.target
    if target.subject_id not in entity_ids:
        return _issue(
            CompilerIssueCode.invalid_binding,
            "query subject does not resolve to an entity",
            f"queries.{query.query_id}.target.subject_id",
            target.subject_id,
        )
    for field_name, value, allowed in (
        ("point_id", target.point_id, point_ids),
        ("frame_id", target.frame_id, frame_ids),
        ("interval_id", target.interval_id, interval_ids),
        ("event_id", target.event_id, event_ids),
    ):
        if missing(value, allowed):
            return _issue(
                CompilerIssueCode.invalid_binding,
                "query scope reference does not resolve",
                f"queries.{query.query_id}.target.{field_name}",
                value,
            )
    if target.point_id is not None and points[target.point_id].owner_entity_id not in {None, target.subject_id}:
        return _issue(CompilerIssueCode.invalid_binding, "query point is not owned by the query subject", f"queries.{query.query_id}.target.point_id", target.point_id)
    if target.interval_id is not None and target.subject_id not in intervals[target.interval_id].subject_ids:
        return _issue(CompilerIssueCode.invalid_binding, "query subject is outside the query interval", f"queries.{query.query_id}.target.interval_id", target.interval_id)
    if target.event_id is not None:
        event = events[target.event_id]
        if target.subject_id not in event.subject_ids or (target.interval_id is not None and target.interval_id not in event.interval_ids):
            return _issue(CompilerIssueCode.invalid_binding, "query event is outside reciprocal subject/interval scope", f"queries.{query.query_id}.target.event_id", target.event_id)
    direction = target.direction
    if direction is not None and (missing(getattr(direction, "frame_id", None), frame_ids) or missing(getattr(direction, "symbol_id", None), symbol_ids)):
        return _issue(CompilerIssueCode.invalid_binding, "query direction binding does not resolve", f"queries.{query.query_id}.target.direction", query.query_id)
    if direction is not None and getattr(direction, "axis", None) is not None:
        direction_frame = frames_by_id.get(getattr(direction, "frame_id", None))
        if direction_frame is None or getattr(direction, "axis") not in {item.axis for item in direction_frame.axes}:
            return _issue(CompilerIssueCode.invalid_binding, "query axis direction is not declared by its frame", f"queries.{query.query_id}.target.direction", query.query_id)
    bad = unresolved_refs(query.evidence_refs, evidence_ids)
    if bad:
        return _issue(CompilerIssueCode.invalid_binding, "query evidence does not resolve", f"queries.{query.query_id}.evidence_refs", bad)
    for quantity in ir.quantities:
        if quantity.subject_id not in entity_ids:
            return _issue(
                CompilerIssueCode.invalid_binding,
                "quantity subject does not resolve to an entity",
                f"quantities.{quantity.quantity_id}.subject_id",
                quantity.subject_id,
            )
        for field_name, value, allowed in (
            ("point_id", quantity.point_id, point_ids),
            ("frame_id", quantity.frame_id, frame_ids),
            ("interval_id", quantity.interval_id, interval_ids),
            ("event_id", quantity.event_id, event_ids),
            ("assumption_policy_ref", quantity.assumption_policy_ref, assumption_ids),
        ):
            if missing(value, allowed):
                return _issue(
                    CompilerIssueCode.invalid_binding,
                    "quantity scope or authority reference does not resolve",
                    f"quantities.{quantity.quantity_id}.{field_name}",
                    value,
                )
        if quantity.point_id is not None:
            point = points[quantity.point_id]
            if point.owner_entity_id not in {None, quantity.subject_id} or (
                point.frame_id is not None and quantity.frame_id not in {None, point.frame_id}
            ):
                return _issue(CompilerIssueCode.invalid_binding, "quantity point ownership or frame is inconsistent", f"quantities.{quantity.quantity_id}.point_id", quantity.point_id)
        if quantity.interval_id is not None:
            interval = intervals[quantity.interval_id]
            if quantity.subject_id not in interval.subject_ids or (
                interval.frame_id is not None and quantity.frame_id not in {None, interval.frame_id}
            ):
                return _issue(CompilerIssueCode.invalid_binding, "quantity is outside its interval subject or frame scope", f"quantities.{quantity.quantity_id}.interval_id", quantity.interval_id)
        if quantity.event_id is not None:
            event = events[quantity.event_id]
            if quantity.subject_id not in event.subject_ids or (
                quantity.interval_id is not None and quantity.interval_id not in event.interval_ids
            ):
                return _issue(CompilerIssueCode.invalid_binding, "quantity event binding is outside reciprocal subject/interval scope", f"quantities.{quantity.quantity_id}.event_id", quantity.event_id)
        direction = quantity.direction
        if direction is not None and (missing(getattr(direction, "frame_id", None), frame_ids) or missing(getattr(direction, "symbol_id", None), symbol_ids)):
            return _issue(CompilerIssueCode.invalid_binding, "quantity direction binding does not resolve", f"quantities.{quantity.quantity_id}.direction", quantity.quantity_id)
        if direction is not None and getattr(direction, "axis", None) is not None:
            direction_frame = frames_by_id.get(getattr(direction, "frame_id", None))
            if direction_frame is None or getattr(direction, "axis") not in {item.axis for item in direction_frame.axes}:
                return _issue(CompilerIssueCode.invalid_binding, "quantity axis direction is not declared by its frame", f"quantities.{quantity.quantity_id}.direction", quantity.quantity_id)
        bad = bad_evidence(quantity)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "quantity evidence does not resolve", f"quantities.{quantity.quantity_id}.evidence_refs", bad)
    for interaction in ir.interactions:
        if any(item not in entity_ids for item in interaction.participant_ids):
            return _issue(
                CompilerIssueCode.invalid_binding,
                "interaction participant does not resolve to an entity",
                f"interactions.{interaction.interaction_id}.participant_ids",
                next(item for item in interaction.participant_ids if item not in entity_ids),
            )
        if any(item not in point_ids for item in interaction.point_ids):
            return _issue(
                CompilerIssueCode.invalid_binding,
                "interaction point does not resolve",
                f"interactions.{interaction.interaction_id}.point_ids",
                next(item for item in interaction.point_ids if item not in point_ids),
            )
        for field_name, value, allowed in (
            ("frame_id", interaction.frame_id, frame_ids),
            ("interval_id", interaction.interval_id, interval_ids),
            ("event_id", interaction.event_id, event_ids),
        ):
            if missing(value, allowed):
                return _issue(CompilerIssueCode.invalid_binding, "interaction scope reference does not resolve", f"interactions.{interaction.interaction_id}.{field_name}", value)
        bad_quantity = unresolved_refs(interaction.quantity_ids, quantity_ids)
        if bad_quantity:
            return _issue(CompilerIssueCode.invalid_binding, "interaction quantity does not resolve", f"interactions.{interaction.interaction_id}.quantity_ids", bad_quantity)
        if interaction.interval_id is not None:
            interval = intervals[interaction.interval_id]
            if not set(interaction.participant_ids).issubset(interval.subject_ids) or (
                interaction.frame_id is not None and interval.frame_id not in {None, interaction.frame_id}
            ):
                return _issue(CompilerIssueCode.invalid_binding, "interaction participants or frame are outside its interval", f"interactions.{interaction.interaction_id}.interval_id", interaction.interval_id)
        if interaction.event_id is not None:
            event = events[interaction.event_id]
            if not set(interaction.participant_ids).issubset(event.subject_ids) or (
                interaction.interval_id is not None and interaction.interval_id not in event.interval_ids
            ):
                return _issue(CompilerIssueCode.invalid_binding, "interaction event is outside reciprocal participant/interval scope", f"interactions.{interaction.interaction_id}.event_id", interaction.event_id)
        for quantity_id in interaction.quantity_ids:
            quantity = quantities[quantity_id]
            if quantity.frame_id not in {None, interaction.frame_id} and interaction.frame_id is not None:
                return _issue(CompilerIssueCode.invalid_binding, "interaction quantity frame is inconsistent", f"interactions.{interaction.interaction_id}.quantity_ids", quantity_id)
            if quantity.interval_id not in {None, interaction.interval_id} and interaction.interval_id is not None:
                return _issue(CompilerIssueCode.invalid_binding, "interaction quantity interval is inconsistent", f"interactions.{interaction.interaction_id}.quantity_ids", quantity_id)
            if quantity.event_id not in {None, interaction.event_id} and interaction.event_id is not None:
                return _issue(CompilerIssueCode.invalid_binding, "interaction quantity event is inconsistent", f"interactions.{interaction.interaction_id}.quantity_ids", quantity_id)
        bad = bad_evidence(interaction)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "interaction evidence does not resolve", f"interactions.{interaction.interaction_id}.evidence_refs", bad)

    for relation in ir.geometry:
        allowed_participants = entity_ids | point_ids
        bad_participant = unresolved_refs(relation.participant_ids, allowed_participants)
        bad_quantity = unresolved_refs(relation.quantity_ids, quantity_ids)
        if bad_participant or bad_quantity or missing(relation.interval_id, interval_ids):
            return _issue(CompilerIssueCode.invalid_binding, "geometry participant, quantity, or interval does not resolve", f"geometry.{relation.relation_id}", bad_participant or bad_quantity or relation.interval_id)
        bad = bad_evidence(relation)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "geometry evidence does not resolve", f"geometry.{relation.relation_id}.evidence_refs", bad)
        for quantity_id in relation.quantity_ids:
            quantity = quantities[quantity_id]
            if (
                quantity.subject_id not in relation.participant_ids
                and quantity.point_id not in relation.participant_ids
            ) or (
                relation.interval_id is not None
                and quantity.interval_id not in {None, relation.interval_id}
            ):
                return _issue(CompilerIssueCode.invalid_binding, "geometry quantity is outside participant/interval scope", f"geometry.{relation.relation_id}.quantity_ids", quantity_id)
        scoped_expression_issue = expression_scope_issue(
            relation.expression,
            path=f"geometry.{relation.relation_id}.expression",
            subject_ids=set(relation.participant_ids),
            interval_id=relation.interval_id,
            event_id=None,
        )
        if scoped_expression_issue is not None:
            return scoped_expression_issue
    for constraint in ir.constraints:
        bad_subject = unresolved_refs(constraint.subject_ids, entity_ids | point_ids)
        if bad_subject or missing(constraint.interval_id, interval_ids) or missing(constraint.event_id, event_ids):
            return _issue(CompilerIssueCode.invalid_binding, "constraint subject, interval, or event does not resolve", f"constraints.{constraint.constraint_id}", bad_subject or constraint.interval_id or constraint.event_id)
        if constraint.event_id is not None and constraint.interval_id is not None and constraint.interval_id not in events[constraint.event_id].interval_ids:
            return _issue(CompilerIssueCode.invalid_binding, "constraint event and interval are not reciprocal", f"constraints.{constraint.constraint_id}.event_id", constraint.event_id)
        bad = bad_evidence(constraint)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "constraint evidence does not resolve", f"constraints.{constraint.constraint_id}.evidence_refs", bad)
        scoped_expression_issue = expression_scope_issue(
            constraint.expression,
            path=f"constraints.{constraint.constraint_id}.expression",
            subject_ids=set(constraint.subject_ids),
            interval_id=constraint.interval_id,
            event_id=constraint.event_id,
        )
        if scoped_expression_issue is not None:
            return scoped_expression_issue
    for state in ir.state_conditions:
        bad_quantity = unresolved_refs(state.quantity_ids, quantity_ids)
        if state.subject_id not in entity_ids or bad_quantity or missing(state.interval_id, interval_ids) or missing(state.event_id, event_ids):
            return _issue(CompilerIssueCode.invalid_binding, "state subject, quantity, interval, or event does not resolve", f"state_conditions.{state.state_condition_id}", bad_quantity or state.subject_id)
        if state.event_id is not None:
            event = events[state.event_id]
            if state.subject_id not in event.subject_ids or (state.interval_id is not None and state.interval_id not in event.interval_ids):
                return _issue(CompilerIssueCode.invalid_binding, "state event is outside reciprocal subject/interval scope", f"state_conditions.{state.state_condition_id}.event_id", state.event_id)
        for quantity_id in state.quantity_ids:
            quantity = quantities[quantity_id]
            if quantity.subject_id != state.subject_id or quantity.interval_id not in {None, state.interval_id} or quantity.event_id not in {None, state.event_id}:
                return _issue(CompilerIssueCode.invalid_binding, "state quantity is outside the state scope", f"state_conditions.{state.state_condition_id}.quantity_ids", quantity_id)
        bad = bad_evidence(state)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "state evidence does not resolve", f"state_conditions.{state.state_condition_id}.evidence_refs", bad)
        scoped_expression_issue = expression_scope_issue(
            state.expression,
            path=f"state_conditions.{state.state_condition_id}.expression",
            subject_ids={state.subject_id},
            interval_id=state.interval_id,
            event_id=state.event_id,
        )
        if scoped_expression_issue is not None:
            return scoped_expression_issue
    for assumption in ir.assumptions:
        if assumption.subject_id not in entity_ids or missing(assumption.interval_id, interval_ids):
            return _issue(CompilerIssueCode.invalid_binding, "assumption subject or interval does not resolve", f"assumptions.{assumption.assumption_id}", assumption.subject_id)
        bad = bad_evidence(assumption)
        if bad:
            return _issue(CompilerIssueCode.invalid_binding, "assumption evidence does not resolve", f"assumptions.{assumption.assumption_id}.evidence_refs", bad)
    return None


def _query_symbol_definition(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    *,
    quantity_id: str | None = None,
    vector_length: int | None = None,
) -> SymbolDefinition:
    target = query.target
    entity = next((item for item in ir.entities if item.entity_id == target.subject_id), None)
    point = next((item for item in ir.points if item.point_id == target.point_id), None)
    frame = next((item for item in ir.reference_frames if item.frame_id == target.frame_id), None)
    interval = next((item for item in ir.motion_intervals if item.interval_id == target.interval_id), None)
    event = next((item for item in ir.events if item.event_id == target.event_id), None)
    semantic_target = {
        "role": target.role.value,
        "subject_primitive": entity.primitive.value if entity is not None else None,
        "point_role": point.role.value if point is not None else None,
        "frame_type": frame.frame_type.value if frame is not None else None,
        "frame_axes": tuple(item.axis.value for item in frame.axes) if frame is not None else tuple(),
        "interval_order": interval.order if interval is not None else None,
        "event_kind": event.kind.value if event is not None else None,
        "component": target.component.value,
        "shape": query.shape.value,
        "dimension": query.output_dimension.model_dump(mode="json"),
    }
    symbol_id = f"gen_{_digest(semantic_target)[:28]}"
    symbol_shape = _shape_for_quantity(query.shape)
    if symbol_shape is None:
        raise ValueError("query tensor shape requires specialized compilation")
    if symbol_shape is SymbolShape.vector and vector_length is None:
        raise ValueError("query vector length is not explicitly bound")
    return SymbolDefinition(
        symbol_id=symbol_id,
        quantity_id=quantity_id,
        dimension=query.output_dimension,
        shape=symbol_shape,
        vector_length=vector_length,
    )


def _build_law_context(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    query_quantity,
    relevant: set[str],
    source_symbols: Mapping[str, SymbolDefinition],
    approved_assumption_ids: frozenset[str],
) -> tuple[LawContext | None, dict[str, SymbolNode], str | None, CompilerIssue | None]:
    symbol_nodes: dict[str, SymbolNode] = {}
    bindings: list[BoundQuantity] = []
    quantity_by_id = {quantity.quantity_id: quantity for quantity in ir.quantities}
    for symbol in ir.symbols:
        if symbol.symbol_id not in relevant:
            continue
        quantity = quantity_by_id.get(symbol.quantity_id) if symbol.quantity_id is not None else None
        symbol_nodes[symbol.symbol_id] = SymbolNode(
            symbol=symbol,
            quantity_id=symbol.quantity_id,
            quantity_role=quantity.role.value if quantity is not None else None,
            subject_id=quantity.subject_id if quantity is not None else None,
            point_id=quantity.point_id if quantity is not None else None,
            frame_id=quantity.frame_id if quantity is not None else None,
            interval_id=quantity.interval_id if quantity is not None else None,
            event_id=quantity.event_id if quantity is not None else None,
            known_si_value=quantity.si_value if quantity is not None else None,
            generated=False,
        )
    for quantity in ir.quantities:
        if quantity.quantity_id not in relevant:
            continue
        if (
            query_quantity is not None
            and quantity.quantity_id == query_quantity.quantity_id
            and quantity.symbol_id is None
        ):
            continue
        expression: MathExpression | None
        if quantity.symbol_id is not None:
            expression = SymbolRef(symbol_id=quantity.symbol_id, dimension=quantity.dimension)
        else:
            expression = _literal_expression(quantity)
        if expression is None:
            return None, symbol_nodes, None, _issue(
                CompilerIssueCode.invalid_binding,
                "an unknown relevant quantity requires a reciprocal symbol binding",
                f"quantities.{quantity.quantity_id}",
                quantity.quantity_id,
            )
        bindings.append(
            BoundQuantity(
                quantity_id=quantity.quantity_id,
                symbol_id=quantity.symbol_id,
                role=quantity.role,
                subject_id=quantity.subject_id,
                point_id=quantity.point_id,
                frame_id=quantity.frame_id,
                interval_id=quantity.interval_id,
                event_id=quantity.event_id,
                component=quantity.component,
                shape=quantity.shape,
                dimension=quantity.dimension,
                expression=expression,
                evidence_ids=tuple(quantity.evidence_refs),
                known_si_value=quantity.si_value,
                direction_sign=_direction_sign(quantity),
                direction_bound=quantity.direction is not None,
                direction_key=_direction_key(quantity),
            )
        )
    query_symbol_id: str | None = None
    if query_quantity is not None and query_quantity.symbol_id is not None:
        query_symbol_id = query_quantity.symbol_id
    else:
        vector_length = None
        if query.shape is QuantityShape.vector:
            if query_quantity is not None and isinstance(query_quantity.si_value, tuple):
                vector_length = len(query_quantity.si_value)
            if vector_length is None and query.target.direction is not None:
                components = getattr(query.target.direction, "components", None)
                if isinstance(components, tuple):
                    vector_length = len(components)
            if vector_length is None and query.target.frame_id is not None:
                frame = next(
                    (item for item in ir.reference_frames if item.frame_id == query.target.frame_id),
                    None,
                )
                if frame is not None:
                    vector_length = len(frame.axes)
        try:
            query_symbol = _query_symbol_definition(
                ir,
                query,
                vector_length=vector_length,
            )
        except ValueError:
            return None, symbol_nodes, None, _issue(
                CompilerIssueCode.requires_specialized_model,
                "query shape requires a specialized compiler",
                f"queries.{query.query_id}",
                query.query_id,
            )
        query_symbol_id = query_symbol.symbol_id
        if query_symbol_id in symbol_nodes:
            return None, symbol_nodes, None, _issue(
                CompilerIssueCode.invalid_binding,
                "generated query symbol identity collides with an existing symbol",
                f"queries.{query.query_id}",
                query_symbol_id,
            )
        known_value = query_quantity.si_value if query_quantity is not None else None
        symbol_nodes[query_symbol_id] = SymbolNode(
            symbol=query_symbol,
            quantity_id=None,
            quantity_role=query.target.role.value,
            subject_id=query.target.subject_id,
            point_id=query.target.point_id,
            frame_id=query.target.frame_id,
            interval_id=query.target.interval_id,
            event_id=query.target.event_id,
            known_si_value=known_value,
            generated=True,
        )
        bindings.append(
            BoundQuantity(
                quantity_id=query_quantity.quantity_id if query_quantity is not None else None,
                symbol_id=query_symbol_id,
                role=query.target.role,
                subject_id=query.target.subject_id,
                point_id=query.target.point_id,
                frame_id=query.target.frame_id,
                interval_id=query.target.interval_id,
                event_id=query.target.event_id,
                component=query.target.component,
                shape=query.shape,
                dimension=query.output_dimension,
                expression=SymbolRef(symbol_id=query_symbol_id, dimension=query.output_dimension),
                evidence_ids=tuple(query_quantity.evidence_refs) if query_quantity is not None else tuple(query.evidence_refs),
                known_si_value=known_value,
                direction_sign=(
                    _direction_sign(query_quantity)
                    if query_quantity is not None
                    else getattr(query.target.direction, "sign", 1)
                ),
                direction_bound=query.target.direction is not None,
                direction_key=(
                    _direction_key(query_quantity)
                    if query_quantity is not None
                    else _canonical_direction_key(query.target.direction)
                ),
                generated=known_value is None,
            )
        )
    context = LawContext(
        quantities=tuple(sorted(bindings, key=lambda item: item.stable_key)),
        entities=tuple(sorted((item for item in ir.entities if item.entity_id in relevant), key=lambda item: item.entity_id)),
        points=tuple(sorted((item for item in ir.points if item.point_id in relevant), key=lambda item: item.point_id)),
        reference_frames=tuple(sorted((item for item in ir.reference_frames if item.frame_id in relevant), key=lambda item: item.frame_id)),
        motion_intervals=tuple(sorted((item for item in ir.motion_intervals if item.interval_id in relevant), key=lambda item: item.interval_id)),
        events=tuple(sorted((item for item in ir.events if item.event_id in relevant), key=lambda item: item.event_id)),
        geometry=tuple(sorted((item for item in ir.geometry if item.relation_id in relevant), key=lambda item: item.relation_id)),
        interactions=tuple(sorted((item for item in ir.interactions if item.interaction_id in relevant), key=lambda item: item.interaction_id)),
        state_conditions=tuple(sorted((item for item in ir.state_conditions if item.state_condition_id in relevant), key=lambda item: item.state_condition_id)),
        assumptions=tuple(sorted((item for item in ir.assumptions if item.assumption_id in relevant), key=lambda item: item.assumption_id)),
        approved_assumption_ids=frozenset(approved_assumption_ids),
        symbols=tuple(sorted(source_symbols.values(), key=lambda item: item.symbol_id)),
        hinted_principles=(),
    )
    return context, symbol_nodes, query_symbol_id, None


def _scope_for_explicit(
    ir: MechanicsProblemIRV1,
    value: IRConstraint | IRGeometryRelation | IRStateCondition,
    expression: MathExpression,
    quantity_by_symbol: Mapping[str, object],
) -> tuple[tuple[str, ...], tuple[str, ...], str | None, str | None]:
    point_ids = {item.point_id for item in ir.points}
    owner_by_point = {item.point_id: item.owner_entity_id for item in ir.points}
    if isinstance(value, IRConstraint):
        declared = tuple(value.subject_ids)
    elif isinstance(value, IRGeometryRelation):
        declared = tuple(value.participant_ids)
    else:
        declared = (value.subject_id,)
    entities = {item for item in declared if item not in point_ids}
    points = {item for item in declared if item in point_ids}
    for symbol_id in _expression_symbol_ids(expression):
        quantity = quantity_by_symbol.get(symbol_id)
        if quantity is None:
            continue
        if quantity.subject_id in point_ids:
            points.add(quantity.subject_id)
        else:
            entities.add(quantity.subject_id)
        if quantity.point_id is not None:
            points.add(quantity.point_id)
            owner = owner_by_point.get(quantity.point_id)
            if owner is not None:
                entities.add(owner)
    return (
        _sorted_unique(entities),
        _sorted_unique(points),
        getattr(value, "interval_id", None),
        getattr(value, "event_id", None),
    )


def _explicit_expression_template(
    expression: MathExpression,
    quantity_by_symbol: Mapping[str, object],
) -> bool:
    def visit(node: MathExpression) -> tuple[bool, bool]:
        if isinstance(node, SymbolRef):
            quantity = quantity_by_symbol.get(node.symbol_id)
            return quantity is not None, quantity is not None and quantity.si_value is None
        if isinstance(node, LiteralNode):
            dimensionless = node.dimension is None or node.dimension == DimensionVector.dimensionless()
            allowed = node.value == 0.0 or (dimensionless and abs(node.value) == 1.0)
            return allowed, False
        if isinstance(node, (Equality, Inequality)):
            left_ok, left_unknown = visit(node.left)
            right_ok, right_unknown = visit(node.right)
            return left_ok and right_ok, left_unknown or right_unknown
        if isinstance(node, Add):
            values = tuple(visit(item) for item in node.terms)
            return all(item[0] for item in values), any(item[1] for item in values)
        if isinstance(node, Subtract):
            left_ok, left_unknown = visit(node.left)
            right_ok, right_unknown = visit(node.right)
            return left_ok and right_ok, left_unknown or right_unknown
        if isinstance(node, Negate):
            return visit(node.operand)
        if isinstance(node, Multiply):
            values = tuple(visit(item) for item in node.factors)
            return all(item[0] for item in values) and sum(item[1] for item in values) <= 1, any(item[1] for item in values)
        if isinstance(node, Divide):
            numerator_ok, numerator_unknown = visit(node.numerator)
            denominator_ok, denominator_unknown = visit(node.denominator)
            return numerator_ok and denominator_ok and not denominator_unknown, numerator_unknown
        return False, False

    allowed, _ = visit(expression)
    return allowed


def _explicit_scope_and_template(
    ir: MechanicsProblemIRV1,
    value: IRConstraint | IRGeometryRelation,
    expression: MathExpression,
    query: IRQuery,
    quantity_by_symbol: Mapping[str, object],
) -> tuple[str | None, tuple[str, ...]] | None:
    evidence_ids = set(item.evidence_id for item in ir.source_evidence)
    if not value.evidence_refs or not set(value.evidence_refs).issubset(evidence_ids):
        return None
    if not _explicit_expression_template(expression, quantity_by_symbol):
        return None
    refs = set(_expression_symbol_ids(expression))
    if not refs or not refs.issubset(quantity_by_symbol):
        return None
    quantities = tuple(quantity_by_symbol[item] for item in sorted(refs))
    unknown_symbols = {item.symbol_id for item in quantities if item.si_value is None}
    query_quantity = next(
        (item for item in ir.quantities if item.quantity_id == query.target.target_quantity_id),
        None,
    )
    query_source_symbol = query_quantity.symbol_id if query_quantity is not None else None
    if isinstance(expression, Equality) and len(unknown_symbols) < 2:
        return None
    if isinstance(expression, Equality) and query_source_symbol in unknown_symbols and unknown_symbols == {query_source_symbol}:
        return None
    if isinstance(value, IRConstraint):
        if value.kind not in {
            ConstraintKind.kinematic,
            ConstraintKind.geometric,
            ConstraintKind.boundary,
            ConstraintKind.rolling,
            ConstraintKind.rope,
        }:
            return None
        subject_ids = set(value.subject_ids)
        point_owner = {item.point_id: item.owner_entity_id for item in ir.points}
        if not subject_ids or any(
            (
                item.subject_id not in subject_ids
                and (item.point_id is None or item.point_id not in subject_ids)
            )
            or (
                item.point_id is not None
                and point_owner.get(item.point_id) not in {None, item.subject_id}
            )
            for item in quantities
        ):
            return None
        roles = {item.role for item in quantities}
        linear_motion_roles = {
            QuantityRole.position,
            QuantityRole.displacement,
            QuantityRole.distance,
            QuantityRole.height,
            QuantityRole.time,
            QuantityRole.duration,
            QuantityRole.velocity,
            QuantityRole.speed,
            QuantityRole.acceleration,
            QuantityRole.angle,
            QuantityRole.angular_position,
            QuantityRole.angular_velocity,
            QuantityRole.angular_acceleration,
            QuantityRole.radius,
            QuantityRole.length,
            QuantityRole.count,
            QuantityRole.generalized_coordinate,
            QuantityRole.generalized_speed,
        }
        if not roles.issubset(linear_motion_roles):
            return None
        if value.kind in {ConstraintKind.kinematic, ConstraintKind.rope, ConstraintKind.rolling} and value.interval_id is None:
            return None
        primitives = {
            item.primitive.value for item in ir.entities if item.entity_id in subject_ids
        }
        if value.kind is ConstraintKind.rope and "rope" not in primitives:
            return None
        if value.kind is ConstraintKind.rolling and not primitives.intersection({"rigid_body", "pulley", "gear", "rack"}):
            return None
        interval_id = value.interval_id
        event_id = value.event_id
    else:
        if value.expression is None or not value.quantity_ids:
            return None
        if value.kind.value not in {"distance", "angle", "radius", "ratio", "parallel", "perpendicular"}:
            return None
        quantity_ids = {item.quantity_id for item in quantities}
        if not quantity_ids.issubset(set(value.quantity_ids)):
            return None
        participant_ids = set(value.participant_ids)
        if any(
            item.subject_id not in participant_ids
            and (item.point_id is None or item.point_id not in participant_ids)
            for item in quantities
        ):
            return None
        interval_id = value.interval_id
        event_id = None
    quantity_intervals = {item.interval_id for item in quantities if item.si_value is None and item.interval_id is not None}
    if len(quantity_intervals) > 1 or (interval_id is not None and quantity_intervals - {interval_id}):
        return None
    frames = {item.frame_id for item in quantities if item.frame_id is not None}
    if interval_id is not None:
        interval_frame = next(
            (item.frame_id for item in ir.motion_intervals if item.interval_id == interval_id),
            None,
        )
        if interval_frame is not None:
            frames.add(interval_frame)
    if len(frames) > 1:
        return None
    event_ids = {item.event_id for item in quantities if item.event_id is not None}
    if event_id is not None:
        event_ids.add(event_id)
    return (next(iter(frames)) if frames else None, tuple(sorted(event_ids)))


def _explicit_emissions(
    ir: MechanicsProblemIRV1,
    query: IRQuery,
    relevant: set[str],
    source_symbols: Mapping[str, SymbolDefinition],
) -> tuple[
    tuple[LawEmission, ...],
    tuple[tuple[str, str, tuple[str, ...]], ...],
    tuple[CompilerIssue, ...],
]:
    symbol_to_quantity = {
        symbol_id: symbol.quantity_id
        for symbol_id, symbol in source_symbols.items()
        if symbol.quantity_id is not None
    }
    emissions: list[LawEmission] = []
    descriptors: list[tuple[str, str, tuple[str, ...]]] = []
    authority_issues: list[CompilerIssue] = []
    quantity_by_symbol = {
        item.symbol_id: item for item in ir.quantities if item.symbol_id is not None
    }

    def add(
        identifier: str,
        kind: str,
        expression: MathExpression,
        evidence_ids: tuple[str, ...],
        entities: tuple[str, ...],
        points: tuple[str, ...],
        interval_id: str | None,
        event_id: str | None,
        frame_id: str | None,
        event_ids: tuple[str, ...],
        rule: LawRule,
        *,
        include_descriptor: bool = True,
    ) -> None:
        symbol_ids = _expression_symbol_ids(expression)
        quantity_ids = _sorted_unique(
            symbol_to_quantity[item]
            for item in symbol_ids
            if item in symbol_to_quantity
        )
        emissions.append(
            LawEmission(
                rule=rule,
                expression=expression,
                entity_ids=_sorted_unique(entities),
                point_ids=_sorted_unique(points),
                frame_id=frame_id,
                interval_id=interval_id,
                event_id=event_id,
                event_ids=_sorted_unique(event_ids),
                source_quantity_ids=quantity_ids,
                source_evidence_ids=_sorted_unique(evidence_ids),
                constraint_ids=(identifier,),
            )
        )
        if include_descriptor:
            descriptors.append((identifier, kind, _sorted_unique(evidence_ids)))

    for constraint in sorted(ir.constraints, key=lambda item: item.constraint_id):
        if constraint.constraint_id not in relevant:
            continue
        if not isinstance(constraint.expression, Inequality):
            authority_issues.append(
                _issue(
                    CompilerIssueCode.constraint_not_authoritative,
                    "model relation equality is diagnostic only; no server law template consumed it",
                    f"constraints.{constraint.constraint_id}",
                    constraint.constraint_id,
                    warning=True,
                )
            )
            continue
        entities, points, interval_id, event_id = _scope_for_explicit(
            ir, constraint, constraint.expression, quantity_by_symbol
        )
        authority = _explicit_scope_and_template(
            ir, constraint, constraint.expression, query, quantity_by_symbol
        )
        if authority is None:
            authority_issues.append(
                _issue(
                    CompilerIssueCode.constraint_not_authoritative,
                    "explicit relation is not an approved source-evidenced mechanics template",
                    f"constraints.{constraint.constraint_id}",
                    constraint.constraint_id,
                    warning=True,
                )
            )
            continue
        frame_id, event_ids = authority
        add(
            constraint.constraint_id,
            constraint.kind.value,
            constraint.expression,
            tuple(constraint.evidence_refs),
            entities,
            points,
            interval_id,
            event_id,
            frame_id,
            event_ids,
            _EXPLICIT_CONSTRAINT_RULE,
        )
    for relation in sorted(ir.geometry, key=lambda item: item.relation_id):
        if relation.relation_id not in relevant or relation.expression is None:
            continue
        if not isinstance(relation.expression, Inequality):
            authority_issues.append(
                _issue(
                    CompilerIssueCode.constraint_not_authoritative,
                    "model geometry equality is diagnostic only; no server geometry template consumed it",
                    f"geometry.{relation.relation_id}",
                    relation.relation_id,
                    warning=True,
                )
            )
            continue
        entities, points, interval_id, event_id = _scope_for_explicit(
            ir, relation, relation.expression, quantity_by_symbol
        )
        authority = _explicit_scope_and_template(
            ir, relation, relation.expression, query, quantity_by_symbol
        )
        if authority is None:
            authority_issues.append(
                _issue(
                    CompilerIssueCode.constraint_not_authoritative,
                    "explicit geometry is not an approved source-evidenced mechanics template",
                    f"geometry.{relation.relation_id}",
                    relation.relation_id,
                    warning=True,
                )
            )
            continue
        frame_id, event_ids = authority
        add(
            relation.relation_id,
            relation.kind.value,
            relation.expression,
            tuple(relation.evidence_refs),
            entities,
            points,
            interval_id,
            event_id,
            frame_id,
            event_ids,
            _EXPLICIT_GEOMETRY_RULE,
        )
    for state in sorted(ir.state_conditions, key=lambda item: item.state_condition_id):
        if state.state_condition_id not in relevant or state.expression is None:
            continue
        authority_issues.append(
            _issue(
                CompilerIssueCode.constraint_not_authoritative,
                "state expression is ignored; only server state templates can emit equations",
                f"state_conditions.{state.state_condition_id}",
                state.state_condition_id,
                warning=True,
            )
        )
    return tuple(emissions), tuple(descriptors), tuple(authority_issues[:128])


def _expression_projection(expression: MathExpression, aliases: _CanonicalIds) -> object:
    if isinstance(expression, SymbolRef):
        return {
            "op": expression.op,
            "symbol": aliases.get(expression.symbol_id),
            "dimension": expression.dimension.model_dump(mode="json") if expression.dimension else None,
        }
    if isinstance(expression, LiteralNode):
        return {
            "op": expression.op,
            "value": expression.value,
            "dimension": expression.dimension.model_dump(mode="json") if expression.dimension else None,
        }
    payload: dict[str, object] = {"op": expression.op}
    if expression.dimension is not None:
        payload["dimension"] = expression.dimension.model_dump(mode="json")
    for field_name in type(expression).model_fields:
        if field_name in {"op", "dimension"}:
            continue
        value = getattr(expression, field_name)
        if field_name == "wrt_symbol_id":
            payload[field_name] = aliases.get(value)
        elif isinstance(value, MathNode):
            payload[field_name] = _expression_projection(value, aliases)
        elif isinstance(value, tuple):
            payload[field_name] = tuple(
                _expression_projection(item, aliases)
                if isinstance(item, MathNode)
                else _nested_expression_projection(item, aliases)
                for item in value
            )
        elif isinstance(value, BaseModel):
            payload[field_name] = _nested_expression_projection(value, aliases)
        else:
            payload[field_name] = value.value if hasattr(value, "value") else value
    if isinstance(expression, Equality):
        sides = sorted((payload["left"], payload["right"]), key=_canonical_json)
        payload["left"], payload["right"] = sides
    elif isinstance(expression, Add):
        payload["terms"] = tuple(sorted(payload["terms"], key=_canonical_json))
    elif isinstance(expression, Multiply):
        payload["factors"] = tuple(sorted(payload["factors"], key=_canonical_json))
    return payload


def _nested_expression_projection(value: object, aliases: _CanonicalIds) -> object:
    if isinstance(value, MathNode):
        return _expression_projection(value, aliases)
    if isinstance(value, BaseModel):
        return {
            field_name: (
                aliases.get(getattr(value, field_name))
                if field_name in {"symbol_id", "wrt_symbol_id"}
                else _nested_expression_projection(getattr(value, field_name), aliases)
            )
            for field_name in type(value).model_fields
        }
    if isinstance(value, tuple):
        return tuple(_nested_expression_projection(item, aliases) for item in value)
    return value.value if hasattr(value, "value") else value


def _scope_projection(emission: LawEmission, aliases: _CanonicalIds) -> object:
    return {
        "entities": sorted(aliases.get(item) for item in emission.entity_ids),
        "points": sorted(aliases.get(item) for item in emission.point_ids),
        "frame": aliases.get(emission.frame_id),
        "interval": aliases.get(emission.interval_id),
        "event": aliases.get(emission.event_id),
        "events": sorted(aliases.get(item) for item in emission.event_ids),
    }


def _initial_condition_projection(
    condition: InitialConditionBinding,
    aliases: _CanonicalIds,
) -> object:
    return {
        "target": aliases.get(condition.target_symbol_id),
        "value": aliases.get(condition.value_symbol_id),
        "wrt": aliases.get(condition.wrt_symbol_id),
        "order": condition.derivative_order,
        "subject": aliases.get(condition.subject_id),
        "point": aliases.get(condition.point_id),
        "frame": aliases.get(condition.frame_id),
        "interval": aliases.get(condition.interval_id),
        "event": aliases.get(condition.event_id),
        "quantities": sorted(aliases.get(item) for item in condition.source_quantity_ids),
        "evidence": sorted(aliases.get(item) for item in condition.source_evidence_ids),
        "states": sorted(aliases.get(item) for item in condition.source_state_condition_ids),
    }


def _raw_expression_key(expression: MathExpression) -> str:
    payload = expression.model_dump(mode="json", warnings="none")
    if isinstance(expression, Equality):
        left = _canonical_json(payload["left"])
        right = _canonical_json(payload["right"])
        if right < left:
            payload["left"], payload["right"] = payload["right"], payload["left"]
    return _canonical_json(payload)


def _deduplicated_emissions(emissions: Iterable[LawEmission]) -> tuple[LawEmission, ...]:
    selected: dict[tuple[str, str], LawEmission] = {}
    for emission in emissions:
        key = (_raw_expression_key(emission.expression), _canonical_json({
            "entities": emission.entity_ids,
            "points": emission.point_ids,
            "frame": emission.frame_id,
            "interval": emission.interval_id,
            "event": emission.event_id,
            "events": emission.event_ids,
            "explicit_ids": emission.constraint_ids,
            "initial_conditions": tuple(
                item.stable_key for item in emission.initial_conditions
            ),
        }))
        current = selected.get(key)
        if current is None or (
            emission.effective_cost,
            emission.rule.law_id,
            emission.source_quantity_ids,
        ) < (
            current.effective_cost,
            current.rule.law_id,
            current.source_quantity_ids,
        ):
            selected[key] = emission
    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (
                item.effective_cost,
                item.rule.law_id,
                item.entity_ids,
                item.source_quantity_ids,
                tuple(condition.stable_key for condition in item.initial_conditions),
                _raw_expression_key(item.expression),
            ),
        )
    )


def _initial_condition_emission_issue(
    ir: MechanicsProblemIRV1,
    emissions: tuple[LawEmission, ...],
    symbol_nodes: Mapping[str, SymbolNode],
) -> CompilerIssue | None:
    evidence_ids = {item.evidence_id for item in ir.source_evidence}
    quantities = {item.quantity_id: item for item in ir.quantities}
    states = {item.state_condition_id: item for item in ir.state_conditions}
    for emission_index, emission in enumerate(emissions):
        expression_symbol_ids = set(_expression_symbol_ids(emission.expression))
        for condition_index, condition in enumerate(emission.initial_conditions):
            path = f"laws.{emission_index}.initial_conditions.{condition_index}"
            target = symbol_nodes.get(condition.target_symbol_id)
            value = symbol_nodes.get(condition.value_symbol_id)
            wrt = symbol_nodes.get(condition.wrt_symbol_id)
            if target is None or value is None or wrt is None:
                return _issue(
                    CompilerIssueCode.invalid_binding,
                    "initial-condition symbols must be compiler-known exact bindings",
                    path,
                )
            if (
                type(condition.derivative_order) is not int
                or condition.derivative_order not in {0, 1}
                or condition.target_symbol_id not in expression_symbol_ids
                or condition.wrt_symbol_id not in expression_symbol_ids
            ):
                return _issue(
                    CompilerIssueCode.invalid_binding,
                    "initial condition is not bound to its emitting typed equation",
                    path,
                )
            expected_dimension = (
                target.symbol.dimension
                if condition.derivative_order == 0
                else target.symbol.dimension.minus(wrt.symbol.dimension)
            )
            if (
                value.known_si_value is None
                or wrt.quantity_role != QuantityRole.time.value
                or wrt.symbol.shape is not SymbolShape.scalar
                or wrt.symbol.dimension != DimensionVector(time=1)
                or expected_dimension is None
                or value.symbol.dimension != expected_dimension
                or value.symbol.shape is not target.symbol.shape
                or value.symbol.vector_length != target.symbol.vector_length
            ):
                return _issue(
                    CompilerIssueCode.dimension_mismatch,
                    "initial-condition value does not match the target derivative type",
                    path,
                )
            if (
                target.subject_id != condition.subject_id
                or target.point_id != condition.point_id
                or target.frame_id != condition.frame_id
                or target.interval_id != condition.interval_id
                or target.event_id is not None
                or value.subject_id != condition.subject_id
                or value.point_id != condition.point_id
                or value.frame_id != condition.frame_id
                or value.interval_id != condition.interval_id
                or value.event_id != condition.event_id
                or wrt.subject_id != condition.subject_id
                or wrt.point_id is not None
                or wrt.frame_id != condition.frame_id
                or wrt.interval_id != condition.interval_id
                or wrt.event_id is not None
            ):
                return _issue(
                    CompilerIssueCode.invalid_binding,
                    "initial-condition symbol topology must match exactly",
                    path,
                )
            source_quantity = (
                quantities.get(value.quantity_id) if value.quantity_id is not None else None
            )
            if (
                source_quantity is None
                or source_quantity.symbol_id != condition.value_symbol_id
                or condition.source_quantity_ids != (source_quantity.quantity_id,)
                or source_quantity.quantity_id not in emission.source_quantity_ids
            ):
                return _issue(
                    CompilerIssueCode.invalid_binding,
                    "initial-condition quantity provenance is dangling or substituted",
                    path,
                )
            expected_evidence_ids = tuple(sorted(set(source_quantity.evidence_refs)))
            if (
                not expected_evidence_ids
                or condition.source_evidence_ids != expected_evidence_ids
                or not set(expected_evidence_ids).issubset(evidence_ids)
                or not set(expected_evidence_ids).issubset(emission.source_evidence_ids)
            ):
                return _issue(
                    CompilerIssueCode.invalid_binding,
                    "initial-condition evidence provenance is dangling or substituted",
                    path,
                )
            if (
                not condition.source_state_condition_ids
                or tuple(sorted(set(condition.source_state_condition_ids)))
                != condition.source_state_condition_ids
                or not set(condition.source_state_condition_ids).issubset(
                    emission.constraint_ids
                )
            ):
                return _issue(
                    CompilerIssueCode.invalid_binding,
                    "initial-condition state provenance is not owned by its equation",
                    path,
                )
            for state_id in condition.source_state_condition_ids:
                state = states.get(state_id)
                if (
                    state is None
                    or state.kind.value != "initial"
                    or state.subject_id != condition.subject_id
                    or state.interval_id != condition.interval_id
                    or state.event_id != condition.event_id
                    or source_quantity.quantity_id not in state.quantity_ids
                    or not set(expected_evidence_ids).issubset(state.evidence_refs)
                    or not set(state.evidence_refs).issubset(evidence_ids)
                ):
                    return _issue(
                        CompilerIssueCode.invalid_binding,
                        "initial-condition state binding is missing or topologically inconsistent",
                        path,
                        state_id,
                    )
    return None


def _node_dimension(node: MathExpression, symbols: Mapping[str, SymbolDefinition]) -> DimensionVector | None:
    if node.dimension is not None and not isinstance(node, (Equality, Inequality)):
        return node.dimension
    if isinstance(node, SymbolRef):
        symbol = symbols.get(node.symbol_id)
        return symbol.dimension if symbol is not None else None
    if isinstance(node, LiteralNode):
        return node.dimension or DimensionVector.dimensionless()
    if isinstance(node, VectorNode):
        return _node_dimension(node.items[0], symbols)
    if isinstance(node, (Add, Subtract)):
        child = node.terms[0] if isinstance(node, Add) else node.left
        return _node_dimension(child, symbols)
    if isinstance(node, Multiply):
        dimension = DimensionVector.dimensionless()
        for factor in node.factors:
            item = _node_dimension(factor, symbols)
            if item is None:
                return None
            dimension = dimension.plus(item)
            if dimension is None:
                return None
        return dimension
    if isinstance(node, Divide):
        left = _node_dimension(node.numerator, symbols)
        right = _node_dimension(node.denominator, symbols)
        return left.minus(right) if left is not None and right is not None else None
    if isinstance(node, Power):
        base = _node_dimension(node.base, symbols)
        return base.scaled(node.exponent.value) if base is not None and isinstance(node.exponent, LiteralNode) else None
    if isinstance(node, Negate):
        return _node_dimension(node.operand, symbols)
    if isinstance(node, (Dot, Cross)):
        left = _node_dimension(node.left, symbols)
        right = _node_dimension(node.right, symbols)
        return left.plus(right) if left is not None and right is not None else None
    if isinstance(node, (Sin, Cos, Tan)):
        return DimensionVector.dimensionless()
    if isinstance(node, Sqrt):
        value = _node_dimension(node.operand, symbols)
        return value.scaled(0.5) if value is not None else None
    if isinstance(node, (Derivative, Integral)):
        value = _node_dimension(node.expression, symbols)
        wrt = symbols.get(node.wrt_symbol_id)
        if value is None or wrt is None:
            return None
        scaled = wrt.dimension.scaled(node.order)
        if scaled is None:
            return None
        return value.minus(scaled) if isinstance(node, Derivative) else value.plus(scaled)
    if isinstance(node, Norm):
        return _node_dimension(node.operand, symbols)
    if isinstance(node, Piecewise):
        return _node_dimension(node.branches[0].value, symbols)
    if isinstance(node, (Equality, Inequality)):
        return _node_dimension(node.left, symbols)
    return None


@dataclass(frozen=True)
class _Finalized:
    equations: tuple[EquationNode, ...]
    applications: tuple[LawApplication, ...]
    descriptor_equations: Mapping[str, str]
    initial_conditions: tuple[InitialConditionNode, ...]
    initial_condition_equations: Mapping[str, str]


def _finalize_emissions(
    emissions: tuple[LawEmission, ...],
    aliases: _CanonicalIds,
    symbols: Mapping[str, SymbolDefinition],
) -> tuple[_Finalized | None, CompilerIssue | None]:
    semantic_groups: dict[str, list[tuple[LawEmission, object]]] = {}
    for emission in emissions:
        expression_projection = _expression_projection(emission.expression, aliases)
        semantic = {
            "expression": expression_projection,
            "scope": _scope_projection(emission, aliases),
            "evidence": sorted(
                aliases.get(item) for item in emission.source_evidence_ids
            ),
            "initial_conditions": tuple(
                _initial_condition_projection(item, aliases)
                for item in emission.initial_conditions
            ),
        }
        group_key = _digest(semantic)
        semantic_groups.setdefault(group_key, []).append((emission, semantic))
    equations: list[EquationNode] = []
    applications: list[LawApplication] = []
    descriptor_equations: dict[str, str] = {}
    claimed: dict[str, str] = {}
    claimed_applications: dict[str, str] = {}
    initial_conditions: dict[str, InitialConditionNode] = {}
    initial_condition_equations: dict[str, str] = {}
    for group_key in sorted(semantic_groups):
        members = sorted(
            semantic_groups[group_key],
            key=lambda item: (
                _raw_expression_key(item[0].expression),
                item[0].rule.law_id,
                item[0].source_quantity_ids,
            ),
        )
        for index, (emission, semantic) in enumerate(members):
            suffix = f"_{index}" if len(members) > 1 else ""
            equation_id = f"eq_{group_key[:24]}{suffix}"
            claim = _canonical_json(semantic)
            previous = claimed.get(equation_id)
            if previous is not None and previous != claim:
                return None, _issue(
                    CompilerIssueCode.invalid_ir,
                    "stable equation identity collision detected",
                    "equations",
                    equation_id,
                )
            claimed[equation_id] = claim
            dimension = _node_dimension(emission.expression, symbols)
            if dimension is None:
                return None, _issue(
                    CompilerIssueCode.dimension_mismatch,
                    "equation dimension could not be derived safely",
                    f"equations.{equation_id}",
                    equation_id,
                )
            expression_fingerprint = _digest(_expression_projection(emission.expression, aliases))
            scope = EquationScope(
                entity_ids=_sorted_unique(emission.entity_ids),
                point_ids=_sorted_unique(emission.point_ids),
                frame_id=emission.frame_id,
                interval_id=emission.interval_id,
                event_id=emission.event_id,
                event_ids=_sorted_unique((*emission.event_ids, *((emission.event_id,) if emission.event_id else ()))),
            )
            equation = EquationNode(
                equation_id=equation_id,
                expression=emission.expression,
                expression_fingerprint=expression_fingerprint,
                law_id=emission.rule.law_id,
                scope=scope,
                source_quantity_ids=_sorted_unique(emission.source_quantity_ids),
                source_evidence_ids=_sorted_unique(emission.source_evidence_ids),
                assumption_ids=_sorted_unique(emission.assumption_ids),
                constraint_ids=_sorted_unique(emission.constraint_ids),
                generated_unknown_symbol_ids=_sorted_unique(emission.generated_unknown_symbol_ids),
                dimension=dimension,
                complexity_cost=emission.effective_cost,
            )
            app_payload = {
                "law": emission.rule.law_id,
                "equation": equation_id,
                "scope": semantic["scope"],
                "sources": sorted(aliases.get(item) for item in emission.source_quantity_ids),
                "evidence": sorted(
                    aliases.get(item) for item in emission.source_evidence_ids
                ),
                "assumptions": sorted(aliases.get(item) for item in emission.assumption_ids),
                "constraints": sorted(aliases.get(item) for item in emission.constraint_ids),
            }
            application_id = f"app_{_digest(app_payload)[:24]}"
            application_claim = _canonical_json(app_payload)
            previous_application = claimed_applications.get(application_id)
            if previous_application is not None and previous_application != application_claim:
                return None, _issue(
                    CompilerIssueCode.invalid_ir,
                    "stable law-application identity collision detected",
                    "applications",
                    application_id,
                )
            claimed_applications[application_id] = application_claim
            application = LawApplication(
                application_id=application_id,
                law_id=emission.rule.law_id,
                equation_ids=(equation_id,),
                scope=scope,
                source_quantity_ids=equation.source_quantity_ids,
                source_evidence_ids=equation.source_evidence_ids,
                assumption_ids=equation.assumption_ids,
                constraint_ids=equation.constraint_ids,
                generated_unknown_symbol_ids=equation.generated_unknown_symbol_ids,
                complexity_cost=equation.complexity_cost,
            )
            equations.append(equation)
            applications.append(application)
            for condition in emission.initial_conditions:
                condition_semantic = _initial_condition_projection(condition, aliases)
                condition_id = (
                    f"ic{condition.derivative_order}_{_digest(condition_semantic)[:24]}"
                )
                condition_node = InitialConditionNode(
                    condition_id=condition_id,
                    target_symbol_id=condition.target_symbol_id,
                    value_symbol_id=condition.value_symbol_id,
                    wrt_symbol_id=condition.wrt_symbol_id,
                    derivative_order=condition.derivative_order,
                    scope=EquationScope(
                        entity_ids=(condition.subject_id,),
                        point_ids=((condition.point_id,) if condition.point_id is not None else ()),
                        frame_id=condition.frame_id,
                        interval_id=condition.interval_id,
                        event_id=condition.event_id,
                        event_ids=(condition.event_id,),
                    ),
                    source_quantity_ids=_sorted_unique(condition.source_quantity_ids),
                    source_evidence_ids=_sorted_unique(condition.source_evidence_ids),
                    source_state_condition_ids=_sorted_unique(
                        condition.source_state_condition_ids
                    ),
                )
                previous_condition = initial_conditions.get(condition_id)
                if (
                    previous_condition is not None
                    and previous_condition != condition_node
                ):
                    return None, _issue(
                        CompilerIssueCode.invalid_ir,
                        "stable initial-condition identity collision detected",
                        "initial_conditions",
                        condition_id,
                    )
                initial_conditions[condition_id] = condition_node
                initial_condition_equations[condition_id] = equation_id
            for identifier in emission.constraint_ids:
                descriptor_equations[identifier] = equation_id
    return (
        _Finalized(
            equations=tuple(sorted(equations, key=lambda item: item.equation_id)),
            applications=tuple(sorted(applications, key=lambda item: item.application_id)),
            descriptor_equations=descriptor_equations,
            initial_conditions=tuple(
                initial_conditions[item] for item in sorted(initial_conditions)
            ),
            initial_condition_equations=initial_condition_equations,
        ),
        None,
    )


def _exact_known_dot(
    expression: Dot,
    known_values: Mapping[str, object],
) -> Fraction | None:
    """Evaluate only a dot product of two normalized, known vector symbols."""

    if not (
        isinstance(expression.left, SymbolRef)
        and isinstance(expression.right, SymbolRef)
    ):
        return None
    left = known_values.get(expression.left.symbol_id)
    right = known_values.get(expression.right.symbol_id)
    if not (
        isinstance(left, tuple)
        and isinstance(right, tuple)
        and left
        and len(left) == len(right)
        and all(isinstance(item, float) for item in (*left, *right))
    ):
        return None
    return sum(
        (
            Fraction(str(left_item)) * Fraction(str(right_item))
            for left_item, right_item in zip(left, right, strict=True)
        ),
        Fraction(0),
    )


def _affine_expression(
    expression: MathExpression,
    unknown_ids: set[str],
    known_values: Mapping[str, object],
) -> tuple[dict[str, Fraction], Fraction] | None:
    if isinstance(expression, SymbolRef):
        if expression.symbol_id in unknown_ids:
            return {expression.symbol_id: Fraction(1)}, Fraction(0)
        value = known_values.get(expression.symbol_id)
        if isinstance(value, float):
            return {}, Fraction(str(value))
        return None
    if isinstance(expression, LiteralNode):
        return {}, Fraction(str(expression.value))
    if isinstance(expression, Dot):
        value = _exact_known_dot(expression, known_values)
        return ({}, value) if value is not None else None
    if isinstance(expression, (Sin, Cos, Tan)):
        value = _exact_scalar_value(expression, known_values)
        return ({}, value) if value is not None else None
    if isinstance(expression, Negate):
        value = _affine_expression(expression.operand, unknown_ids, known_values)
        if value is None:
            return None
        return ({key: -item for key, item in value[0].items()}, -value[1])
    if isinstance(expression, Add):
        result: tuple[dict[str, Fraction], Fraction] = ({}, Fraction(0))
        for term in expression.terms:
            value = _affine_expression(term, unknown_ids, known_values)
            if value is None:
                return None
            coefficients = dict(result[0])
            for key, item in value[0].items():
                coefficients[key] = coefficients.get(key, Fraction(0)) + item
            result = (coefficients, result[1] + value[1])
        return result
    if isinstance(expression, Subtract):
        left = _affine_expression(expression.left, unknown_ids, known_values)
        right = _affine_expression(expression.right, unknown_ids, known_values)
        if left is None or right is None:
            return None
        coefficients = dict(left[0])
        for key, item in right[0].items():
            coefficients[key] = coefficients.get(key, Fraction(0)) - item
        return coefficients, left[1] - right[1]
    if isinstance(expression, Multiply):
        values = tuple(
            _affine_expression(item, unknown_ids, known_values)
            for item in expression.factors
        )
        if any(item is None for item in values):
            return None
        affine_values = tuple(item for item in values if item is not None)
        variable_values = tuple(item for item in affine_values if item[0])
        if len(variable_values) > 1:
            return None
        scalar = Fraction(1)
        for item in affine_values:
            if not item[0]:
                scalar *= item[1]
        if not variable_values:
            return {}, scalar
        variable = variable_values[0]
        return ({key: item * scalar for key, item in variable[0].items()}, variable[1] * scalar)
    if isinstance(expression, Divide):
        numerator = _affine_expression(expression.numerator, unknown_ids, known_values)
        denominator = _affine_expression(expression.denominator, unknown_ids, known_values)
        if numerator is None or denominator is None or denominator[0] or denominator[1] == 0:
            return None
        return (
            {key: item / denominator[1] for key, item in numerator[0].items()},
            numerator[1] / denominator[1],
        )
    if isinstance(expression, Power) and isinstance(expression.exponent, LiteralNode):
        if expression.exponent.value == 1.0:
            return _affine_expression(expression.base, unknown_ids, known_values)
        if expression.exponent.value == 0.0:
            return {}, Fraction(1)
    return None


def _matrix_rank(rows: list[list[Fraction]]) -> int:
    if not rows:
        return 0
    matrix = [list(row) for row in rows]
    column_count = len(matrix[0])
    pivot_row = 0
    for column in range(column_count):
        pivot = next(
            (index for index in range(pivot_row, len(matrix)) if matrix[index][column] != 0),
            None,
        )
        if pivot is None:
            continue
        matrix[pivot_row], matrix[pivot] = matrix[pivot], matrix[pivot_row]
        divisor = matrix[pivot_row][column]
        matrix[pivot_row] = [item / divisor for item in matrix[pivot_row]]
        for index in range(len(matrix)):
            if index == pivot_row or matrix[index][column] == 0:
                continue
            factor = matrix[index][column]
            matrix[index] = [
                item - factor * pivot_item
                for item, pivot_item in zip(matrix[index], matrix[pivot_row])
            ]
        pivot_row += 1
        if pivot_row == len(matrix):
            break
    return pivot_row


def _polynomial_degree(
    expression: MathExpression,
    unknown_ids: set[str],
    known_values: Mapping[str, object],
) -> int | None:
    """Return a certified scalar polynomial degree, capped at two."""

    if isinstance(expression, SymbolRef):
        if expression.symbol_id in unknown_ids:
            return 1
        return 0 if isinstance(known_values.get(expression.symbol_id), float) else None
    if isinstance(expression, LiteralNode):
        return 0
    if isinstance(expression, Dot):
        return 0 if _exact_known_dot(expression, known_values) is not None else None
    if isinstance(expression, (Sin, Cos, Tan)):
        return 0 if _exact_scalar_value(expression, known_values) is not None else None
    if isinstance(expression, Negate):
        return _polynomial_degree(expression.operand, unknown_ids, known_values)
    if isinstance(expression, Add):
        degrees = tuple(_polynomial_degree(item, unknown_ids, known_values) for item in expression.terms)
        return None if any(item is None for item in degrees) else max(item for item in degrees if item is not None)
    if isinstance(expression, Subtract):
        left = _polynomial_degree(expression.left, unknown_ids, known_values)
        right = _polynomial_degree(expression.right, unknown_ids, known_values)
        return None if left is None or right is None else max(left, right)
    if isinstance(expression, Multiply):
        degrees = tuple(_polynomial_degree(item, unknown_ids, known_values) for item in expression.factors)
        if any(item is None for item in degrees):
            return None
        degree = sum(item for item in degrees if item is not None)
        return degree if degree <= 2 else None
    if isinstance(expression, Divide):
        numerator = _polynomial_degree(expression.numerator, unknown_ids, known_values)
        denominator = _polynomial_degree(expression.denominator, unknown_ids, known_values)
        return numerator if numerator is not None and denominator == 0 else None
    if isinstance(expression, Power) and isinstance(expression.exponent, LiteralNode):
        exponent = expression.exponent.value
        if exponent not in {0.0, 1.0, 2.0}:
            return None
        base = _polynomial_degree(expression.base, unknown_ids, known_values)
        if base is None:
            return None
        degree = base * int(exponent)
        return degree if degree <= 2 else None
    if isinstance(expression, Sqrt):
        # Only a principal root whose complete radicand is already an exact,
        # nonnegative known scalar may participate as a linear coefficient.
        # An unknown beneath sqrt remains on the nonlinear fail-closed path.
        radicand = _exact_scalar_value(expression.operand, known_values)
        return 0 if radicand is not None and radicand >= 0 else None
    return None


def _exact_scalar_value(
    expression: MathExpression,
    known_values: Mapping[str, object],
) -> Fraction | None:
    if isinstance(expression, SymbolRef):
        value = known_values.get(expression.symbol_id)
        return Fraction(str(value)) if isinstance(value, float) else None
    if isinstance(expression, LiteralNode):
        return Fraction(str(expression.value))
    if isinstance(expression, Dot):
        return _exact_known_dot(expression, known_values)
    if isinstance(expression, (Sin, Cos, Tan)):
        argument = _exact_scalar_value(expression.argument, known_values)
        if argument is None:
            return None
        numeric = float(argument)
        if isinstance(expression, Sin):
            result = math.sin(numeric)
        elif isinstance(expression, Cos):
            result = math.cos(numeric)
        else:
            result = math.tan(numeric)
        if not math.isfinite(result):
            return None
        for canonical in (-1.0, 0.0, 1.0):
            if abs(result - canonical) <= 1.0e-15:
                result = canonical
                break
        return Fraction(str(result))
    if isinstance(expression, Negate):
        value = _exact_scalar_value(expression.operand, known_values)
        return -value if value is not None else None
    if isinstance(expression, Add):
        values = tuple(_exact_scalar_value(item, known_values) for item in expression.terms)
        return None if any(item is None for item in values) else sum(
            (item for item in values if item is not None), Fraction(0)
        )
    if isinstance(expression, Subtract):
        left = _exact_scalar_value(expression.left, known_values)
        right = _exact_scalar_value(expression.right, known_values)
        return None if left is None or right is None else left - right
    if isinstance(expression, Multiply):
        value = Fraction(1)
        for factor in expression.factors:
            item = _exact_scalar_value(factor, known_values)
            if item is None:
                return None
            value *= item
        return value
    if isinstance(expression, Divide):
        numerator = _exact_scalar_value(expression.numerator, known_values)
        denominator = _exact_scalar_value(expression.denominator, known_values)
        if numerator is None or denominator is None or denominator == 0:
            return None
        return numerator / denominator
    if isinstance(expression, Power) and isinstance(expression.exponent, LiteralNode):
        base = _exact_scalar_value(expression.base, known_values)
        exponent = expression.exponent.value
        if base is None or not float(exponent).is_integer() or abs(exponent) > 12:
            return None
        integer = int(exponent)
        if base == 0 and integer <= 0:
            return None
        return base ** integer
    return None


def _certified_nonzero_expression(
    expression: MathExpression,
    symbols: Mapping[str, SymbolNode],
    known_values: Mapping[str, object],
) -> bool:
    exact = _exact_scalar_value(expression, known_values)
    if exact is not None:
        return exact != 0
    if isinstance(expression, SymbolRef):
        node = symbols.get(expression.symbol_id)
        return (
            node is not None
            and node.quantity_role in {item.value for item in _STRICTLY_POSITIVE_ROLES}
        )
    if isinstance(expression, Negate):
        return _certified_nonzero_expression(expression.operand, symbols, known_values)
    if isinstance(expression, Multiply):
        return all(
            _certified_nonzero_expression(item, symbols, known_values)
            for item in expression.factors
        )
    if isinstance(expression, Power) and isinstance(expression.exponent, LiteralNode):
        return (
            expression.exponent.value > 0.0
            and _certified_nonzero_expression(expression.base, symbols, known_values)
        )
    return False


def _denominator_domain_issue(
    equations: Iterable[EquationNode],
    symbols: Mapping[str, SymbolNode],
    known_values: Mapping[str, object],
) -> tuple[CompilerStatus, CompilerIssue] | None:
    for equation in equations:
        stack: list[object] = [equation.expression]
        visited = 0
        while stack:
            node = stack.pop()
            if not isinstance(node, BaseModel):
                continue
            visited += 1
            if visited > 4096:
                return (
                    CompilerStatus.resource_limit,
                    _issue(
                        CompilerIssueCode.resource_limit,
                        "denominator inspection exceeded its bounded AST budget",
                        f"equations.{equation.equation_id}",
                        equation.equation_id,
                    ),
                )
            if isinstance(node, Divide):
                exact = _exact_scalar_value(node.denominator, known_values)
                if exact == 0:
                    return (
                        CompilerStatus.invalid,
                        _issue(
                            CompilerIssueCode.invalid_domain,
                            "equation contains a literal or exactly known zero denominator",
                            f"equations.{equation.equation_id}",
                            equation.equation_id,
                        ),
                    )
                if exact is None and not _certified_nonzero_expression(
                    node.denominator, symbols, known_values
                ):
                    return (
                        CompilerStatus.unsupported,
                        _issue(
                            CompilerIssueCode.domain_unproven,
                            "unknown denominator lacks a certified nonzero physical domain",
                            f"equations.{equation.equation_id}",
                            equation.equation_id,
                        ),
                    )
            for field_name in type(node).model_fields:
                value = getattr(node, field_name)
                if isinstance(value, MathNode):
                    stack.append(value)
                elif isinstance(value, tuple):
                    stack.extend(item for item in value if isinstance(item, MathNode))
    return None


def _supported_non_affine_equation(
    equation: EquationNode,
    unknown_ids: set[str],
    known_values: Mapping[str, object],
) -> bool:
    if not isinstance(equation.expression, Equality):
        return True
    left = _polynomial_degree(equation.expression.left, unknown_ids, known_values)
    right = _polynomial_degree(equation.expression.right, unknown_ids, known_values)
    if left is not None and right is not None and max(left, right) <= 2:
        return True
    calculus_laws = {
        "particle_position_derivative",
        "particle_velocity_derivative",
        "angular_position_derivative",
        "angular_velocity_derivative",
        "particle_chain_acceleration",
        "linear_vibration",
    }
    if equation.law_id not in calculus_laws:
        return False
    nodes = (equation.expression.left, equation.expression.right)
    stack: list[MathExpression] = list(nodes)
    visited = 0
    while stack:
        node = stack.pop()
        visited += 1
        if visited > 256:
            return False
        if isinstance(node, Derivative):
            return True
        if isinstance(node, BaseModel):
            for field_name in type(node).model_fields:
                value = getattr(node, field_name)
                if isinstance(value, MathNode):
                    stack.append(value)
                elif isinstance(value, tuple):
                    stack.extend(item for item in value if isinstance(item, MathNode))
    return False


def _linear_analysis(
    equations: Iterable[EquationNode],
    unknown_ids: tuple[str, ...],
    known_values: Mapping[str, object],
) -> tuple[int, int, bool]:
    rows: list[list[Fraction]] = []
    unknown_set = set(unknown_ids)
    for equation in equations:
        if not isinstance(equation.expression, Equality):
            continue
        left = _affine_expression(equation.expression.left, unknown_set, known_values)
        right = _affine_expression(equation.expression.right, unknown_set, known_values)
        if left is None or right is None:
            return 0, 0, False
        coefficients = {
            key: left[0].get(key, Fraction(0)) - right[0].get(key, Fraction(0))
            for key in unknown_ids
        }
        constant = left[1] - right[1]
        rows.append([*(coefficients[key] for key in unknown_ids), -constant])
    coefficient_rows = [row[:-1] for row in rows]
    return _matrix_rank(coefficient_rows), _matrix_rank(rows), True


def _query_component(
    equations: tuple[EquationNode, ...],
    query_symbol_id: str,
) -> tuple[EquationNode, ...]:
    active_symbols = {query_symbol_id}
    active_equations: set[str] = set()
    refs = {equation.equation_id: set(_expression_symbol_ids(equation.expression)) for equation in equations}
    changed = True
    while changed:
        changed = False
        for equation in equations:
            if equation.equation_id in active_equations:
                continue
            if refs[equation.equation_id].intersection(active_symbols):
                active_equations.add(equation.equation_id)
                before = len(active_symbols)
                active_symbols.update(refs[equation.equation_id])
                changed = changed or len(active_symbols) != before
                changed = True
    return tuple(equation for equation in equations if equation.equation_id in active_equations)


def _maximum_matching(
    equation_ids: Iterable[str],
    incidence: Mapping[str, tuple[str, ...]],
) -> int:
    matched: dict[str, str] = {}

    def augment(equation_id: str, visited: set[str]) -> bool:
        for symbol_id in incidence.get(equation_id, ()):
            if symbol_id in visited:
                continue
            visited.add(symbol_id)
            owner = matched.get(symbol_id)
            if owner is None or augment(owner, visited):
                matched[symbol_id] = equation_id
                return True
        return False

    rank = 0
    for equation_id in sorted(equation_ids):
        if augment(equation_id, set()):
            rank += 1
    return rank


def _closed_sets(
    equations: tuple[EquationNode, ...],
    unknown_ids: tuple[str, ...],
    incidence: Mapping[str, tuple[str, ...]],
    known_values: Mapping[str, object],
    limits: CompilerLimits,
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...], bool]:
    if not unknown_ids:
        return tuple(), tuple(), False
    equalities = tuple(
        sorted(
            (equation for equation in equations if isinstance(equation.expression, Equality)),
            key=lambda item: (item.complexity_cost, item.equation_id),
        )
    )
    if len(equalities) < len(unknown_ids):
        return tuple(), tuple(), False
    found: list[tuple[str, ...]] = []
    exhausted = False
    branches = 0
    for group in itertools.combinations(equalities, len(unknown_ids)):
        branches += 1
        if branches > limits.max_branches:
            exhausted = True
            break
        ids = tuple(sorted(item.equation_id for item in group))
        linear_rank, augmented_rank, linear_complete = _linear_analysis(
            group, unknown_ids, known_values
        )
        independently_closing = (
            linear_rank == len(unknown_ids) and augmented_rank == linear_rank
            if linear_complete
            else _maximum_matching(ids, incidence) == len(unknown_ids)
        )
        if independently_closing:
            found.append(ids)
            if len(found) >= limits.max_alternative_sets + 1:
                break
    if not found:
        return tuple(), tuple(), exhausted
    return found[0], tuple(found[1 : limits.max_alternative_sets + 1]), exhausted


def _graph_fingerprint(
    query: IRQuery,
    query_symbol_id: str,
    symbols: tuple[SymbolNode, ...],
    equations: tuple[EquationNode, ...],
    constraints: tuple[ConstraintNode, ...],
    initial_conditions: tuple[InitialConditionNode, ...],
    selected: tuple[str, ...],
    alternatives: tuple[tuple[str, ...], ...],
    aliases: _CanonicalIds,
) -> str:
    equation_by_id = {item.equation_id: item for item in equations}
    payload = {
        "policy": COMPILER_POLICY_VERSION,
        "laws": LAW_LIBRARY_VERSION,
        "query": aliases.get(query.query_id),
        "query_symbol": aliases.get(query_symbol_id),
        "symbols": sorted(
            (
                {
                    "id": aliases.get(item.symbol.symbol_id),
                    "role": item.quantity_role,
                    "subject": aliases.get(item.subject_id),
                    "point": aliases.get(item.point_id),
                    "frame": aliases.get(item.frame_id),
                    "interval": aliases.get(item.interval_id),
                    "event": aliases.get(item.event_id),
                    "dimension": item.symbol.dimension.model_dump(mode="json"),
                    "shape": item.symbol.shape.value,
                    "length": item.symbol.vector_length,
                    "known": item.known_si_value,
                    "generated": item.generated,
                }
                for item in symbols
            ),
            key=_canonical_json,
        ),
        "equations": sorted(
            (
                {
                    "id": item.equation_id,
                    "expression": _expression_projection(item.expression, aliases),
                    "law": item.law_id,
                    "dimension": item.dimension.model_dump(mode="json"),
                    "scope": _scope_projection(
                        LawEmission(
                            rule=_EXPLICIT_CONSTRAINT_RULE,
                            expression=item.expression,
                            entity_ids=item.scope.entity_ids,
                            point_ids=item.scope.point_ids,
                            frame_id=item.scope.frame_id,
                            interval_id=item.scope.interval_id,
                            event_id=item.scope.event_id,
                            event_ids=item.scope.event_ids,
                        ),
                        aliases,
                    ),
                    "sources": sorted(aliases.get(source) for source in item.source_quantity_ids),
                    "evidence": sorted(
                        aliases.get(source) for source in item.source_evidence_ids
                    ),
                    "assumptions": sorted(aliases.get(source) for source in item.assumption_ids),
                    "constraints": sorted(aliases.get(source) for source in item.constraint_ids),
                    "cost": item.complexity_cost,
                }
                for item in equations
            ),
            key=_canonical_json,
        ),
        "constraints": sorted(
            (
                {
                    "id": aliases.get(item.constraint_id),
                    "kind": item.constraint_kind,
                    "equation": equation_by_id[item.equation_id].expression_fingerprint,
                }
                for item in constraints
            ),
            key=_canonical_json,
        ),
        "initial_conditions": sorted(
            (
                {
                    "target": aliases.get(item.target_symbol_id),
                    "value": aliases.get(item.value_symbol_id),
                    "wrt": aliases.get(item.wrt_symbol_id),
                    "order": item.derivative_order,
                    "subject": sorted(aliases.get(value) for value in item.scope.entity_ids),
                    "points": sorted(aliases.get(value) for value in item.scope.point_ids),
                    "frame": aliases.get(item.scope.frame_id),
                    "interval": aliases.get(item.scope.interval_id),
                    "event": aliases.get(item.scope.event_id),
                    "quantities": sorted(
                        aliases.get(value) for value in item.source_quantity_ids
                    ),
                    "evidence": sorted(
                        aliases.get(value) for value in item.source_evidence_ids
                    ),
                    "states": sorted(
                        aliases.get(value)
                        for value in item.source_state_condition_ids
                    ),
                }
                for item in initial_conditions
            ),
            key=_canonical_json,
        ),
        "selected": sorted(equation_by_id[item].expression_fingerprint for item in selected),
        "alternatives": sorted(
            sorted(equation_by_id[item].expression_fingerprint for item in group)
            for group in alternatives
        ),
    }
    return _digest(payload)


class MechanicsCompiler:
    def __init__(self, limits: CompilerLimits | None = None) -> None:
        self._limits = limits or CompilerLimits()

    @property
    def limits(self) -> CompilerLimits:
        return self._limits

    def compile(
        self,
        ir: object,
        *,
        validated_ir_authorization: ValidatedIRAuthorization | None = None,
        query_id: str | None = None,
        approved_assumption_ids: Collection[str] | None = None,
        authorized_corrections: Mapping[str, CorrectionAuthorization] | None = None,
        authorized_assumptions: Mapping[str, AssumptionAuthorization] | None = None,
    ) -> CompilerResult:
        if type(ir) is not MechanicsProblemIRV1:
            return _failure(
                CompilerStatus.invalid,
                _issue(
                    CompilerIssueCode.invalid_ir,
                    "compiler requires an exact immutable mechanics IR v1 instance",
                    "ir",
                ),
            )
        try:
            payload = ir.model_dump(mode="python", warnings="none")
            safe_ir = MechanicsProblemIRV1.model_validate(payload)
        except Exception:
            return _failure(
                CompilerStatus.invalid,
                _issue(
                    CompilerIssueCode.invalid_ir,
                    "IR could not be reconstructed through the immutable schema",
                    "ir",
                ),
            )
        if (
            safe_ir.schema != IR_SCHEMA_NAME
            or safe_ir.version != IR_SCHEMA_VERSION
            or safe_ir.validation_policy_version != VALIDATION_POLICY_VERSION
            or safe_ir.normalization_policy_version != NORMALIZATION_POLICY_VERSION
        ):
            return _failure(
                CompilerStatus.invalid,
                _issue(
                    CompilerIssueCode.policy_mismatch,
                    "IR schema or validation policy is not supported by this compiler",
                    "ir",
                ),
            )
        if type(validated_ir_authorization) is not ValidatedIRAuthorization:
            return _failure(
                CompilerStatus.invalid,
                _issue(
                    CompilerIssueCode.invalid_binding,
                    "compiler requires the exact caller-retained validated-IR authorization",
                    "validated_ir_authorization",
                ),
            )
        try:
            safe_validated_ir_authorization = ValidatedIRAuthorization.model_validate(
                validated_ir_authorization.model_dump(mode="python", warnings="none")
            )
            expected_validated_ir_authorization = ValidatedIRAuthorization(
                ir_sha256=_validated_ir_digest(safe_ir)
            )
        except Exception:
            return _failure(
                CompilerStatus.invalid,
                _issue(
                    CompilerIssueCode.invalid_binding,
                    "validated-IR authorization could not be reconstructed safely",
                    "validated_ir_authorization",
                ),
            )
        if safe_validated_ir_authorization != expected_validated_ir_authorization:
            return _failure(
                CompilerStatus.invalid,
                _issue(
                    CompilerIssueCode.invalid_binding,
                    "validated-IR authorization does not match the full reconstructed IR payload",
                    "validated_ir_authorization",
                ),
            )
        authority, authority_input_issue = _snapshot_authority_inputs(
            approved_assumption_ids,
            authorized_corrections,
            authorized_assumptions,
        )
        if authority_input_issue is not None or authority is None:
            return _failure(
                CompilerStatus.invalid,
                authority_input_issue
                or _issue(
                    CompilerIssueCode.invalid_binding,
                    "external authority inputs could not be snapshotted",
                    "authority",
                ),
            )
        blocking = tuple(item for item in safe_ir.ambiguities if item.blocking)
        if blocking:
            return CompilerResult(
                status=CompilerStatus.blocked,
                issues=tuple(
                    _issue(
                        CompilerIssueCode.blocking_ambiguity,
                        "blocking ambiguity must be resolved before compilation",
                        f"ambiguities.{item.ambiguity_id}",
                        item.ambiguity_id,
                    )
                    for item in blocking
                ),
            )
        if query_id is None:
            if len(safe_ir.queries) != 1:
                return _failure(
                    CompilerStatus.invalid,
                    _issue(
                        CompilerIssueCode.unresolved_query,
                        "query identity is required when the IR does not contain exactly one query",
                        "queries",
                    ),
                )
            query = safe_ir.queries[0]
        else:
            query = next((item for item in safe_ir.queries if item.query_id == query_id), None)
            if query is None:
                return _failure(
                    CompilerStatus.invalid,
                    _issue(
                        CompilerIssueCode.unresolved_query,
                        "requested query identity does not exist",
                        "queries",
                        query_id,
                    ),
                )
        reference_issue = _structural_reference_issue(safe_ir, query)
        if reference_issue is not None:
            return _failure(CompilerStatus.invalid, reference_issue)
        query_quantity, query_issue = _query_quantity(safe_ir, query)
        if query_issue is not None:
            return _failure(CompilerStatus.invalid, query_issue)
        source_symbols, binding_issue = _validate_reciprocal_bindings(safe_ir)
        if binding_issue is not None:
            return _failure(CompilerStatus.invalid, binding_issue)
        records = _primary_records(safe_ir, query)
        _, edges = _graph_edges(records)
        relevant, relevant_issue = _relevant_ids(query, edges, self._limits)
        if relevant_issue is not None or relevant is None:
            return _failure(CompilerStatus.resource_limit, relevant_issue or _issue(CompilerIssueCode.resource_limit, "relevant subgraph failed", "ir"))
        authority_issue = _known_value_authority_issue(safe_ir, relevant, authority)
        if authority_issue is not None:
            return _failure(CompilerStatus.invalid, authority_issue)
        domain_issue = _known_role_domain_issue(safe_ir, relevant)
        if domain_issue is not None:
            return _failure(CompilerStatus.invalid, domain_issue)
        deferred_issue = _course_scope_deferred_issue(
            safe_ir,
            query,
            query_quantity,
            relevant,
        )
        if deferred_issue is not None:
            return _failure(CompilerStatus.unsupported, deferred_issue)
        collision_1d_profile, collision_1d_issue = _collision_1d_contract(
            safe_ir,
            query,
            authority.approved_assumption_ids,
        )
        if collision_1d_issue is not None:
            status = (
                CompilerStatus.invalid
                if collision_1d_issue.code is CompilerIssueCode.invalid_domain
                else CompilerStatus.unsupported
            )
            return _failure(status, collision_1d_issue)
        vertical_circle_profile, vertical_circle_issue = (
            _vertical_circle_contract(
                safe_ir,
                query,
            )
        )
        if vertical_circle_issue is not None:
            status = (
                CompilerStatus.invalid
                if vertical_circle_issue.code is CompilerIssueCode.invalid_domain
                else CompilerStatus.unsupported
            )
            return _failure(status, vertical_circle_issue)
        massive_pulley_profile, massive_pulley_issue = (
            _massive_pulley_atwood_contract(
                safe_ir,
                query,
                authority.approved_assumption_ids,
            )
        )
        if massive_pulley_issue is not None:
            status = (
                CompilerStatus.invalid
                if massive_pulley_issue.code is CompilerIssueCode.invalid_domain
                else CompilerStatus.unsupported
            )
            return _failure(status, massive_pulley_issue)
        rolling_energy_profile, rolling_energy_issue = (
            _rolling_energy_contract(
                safe_ir,
                query,
                authority.approved_assumption_ids,
            )
        )
        if rolling_energy_issue is not None:
            status = (
                CompilerStatus.invalid
                if rolling_energy_issue.code is CompilerIssueCode.invalid_domain
                else CompilerStatus.unsupported
            )
            return _failure(status, rolling_energy_issue)
        specialization_issue = _structural_specialization_issue(safe_ir, query)
        if specialization_issue is not None:
            return _failure(CompilerStatus.unsupported, specialization_issue)
        incline_domain_issue = _incline_projection_domain_issue(safe_ir, query, relevant)
        if incline_domain_issue is not None:
            return _failure(CompilerStatus.invalid, incline_domain_issue)
        incline_pulley_profile, incline_pulley_issue = (
            _fixed_pulley_incline_contact_contract(
                safe_ir,
                query,
                relevant,
                authority.approved_assumption_ids,
            )
        )
        if incline_pulley_issue is not None:
            status = (
                CompilerStatus.invalid
                if incline_pulley_issue.code is CompilerIssueCode.invalid_domain
                else CompilerStatus.unsupported
            )
            return _failure(status, incline_pulley_issue)
        if incline_pulley_profile is None:
            incline_friction_issue = _incline_friction_contract_issue(
                safe_ir, query, relevant
            )
            if incline_friction_issue is not None:
                return _failure(CompilerStatus.unsupported, incline_friction_issue)
        horizontal_profile, horizontal_issue = (
            _fixed_pulley_horizontal_contact_contract(
                safe_ir,
                query,
                relevant,
                authority.approved_assumption_ids,
            )
        )
        if horizontal_issue is not None:
            status = (
                CompilerStatus.invalid
                if horizontal_issue.code is CompilerIssueCode.invalid_domain
                else CompilerStatus.unsupported
            )
            return _failure(status, horizontal_issue)
        if (
            horizontal_profile is None
            and incline_pulley_profile is None
            and massive_pulley_profile is None
        ):
            fixed_pulley_issue = _fixed_pulley_particle_contract_issue(
                safe_ir,
                query,
                relevant,
                authority.approved_assumption_ids,
            )
            if fixed_pulley_issue is not None:
                status = (
                    CompilerStatus.invalid
                    if fixed_pulley_issue.code is CompilerIssueCode.invalid_domain
                    else CompilerStatus.unsupported
                )
                return _failure(status, fixed_pulley_issue)
        support_issue = _structural_template_support_issue(
            safe_ir,
            relevant,
            authority.approved_assumption_ids,
            accepted_friction_state_ids=(
                frozenset(
                    item.friction_state_id
                    for item in (horizontal_profile, incline_pulley_profile)
                    if item is not None
                )
            ),
            accepted_fixed_axis_angular_quantity_ids=(
                frozenset().union(
                    *(
                        item.fixed_axis_angular_quantity_ids
                        for item in (massive_pulley_profile, rolling_energy_profile)
                        if item is not None
                    )
                )
            ),
        )
        if support_issue is not None:
            return _failure(CompilerStatus.unsupported, support_issue)
        context, symbol_nodes, query_symbol_id, context_issue = _build_law_context(
            safe_ir,
            query,
            query_quantity,
            relevant,
            source_symbols,
            authority.approved_assumption_ids,
        )
        if context_issue is not None or context is None or query_symbol_id is None:
            status = CompilerStatus.unsupported if context_issue and context_issue.code is CompilerIssueCode.requires_specialized_model else CompilerStatus.invalid
            return _failure(status, context_issue or _issue(CompilerIssueCode.invalid_ir, "law context could not be built", "ir"))
        if len(symbol_nodes) > self._limits.max_symbols:
            return _failure(
                CompilerStatus.resource_limit,
                _issue(CompilerIssueCode.resource_limit, "equation graph exceeds the symbol limit", "symbols"),
            )
        symbol_table = {item.symbol.symbol_id: item.symbol for item in symbol_nodes.values()}
        explicit_expressions: list[tuple[str, MathExpression]] = []
        explicit_expressions.extend(
            (f"constraints.{item.constraint_id}", item.expression)
            for item in safe_ir.constraints
            if item.constraint_id in relevant
        )
        explicit_expressions.extend(
            (f"geometry.{item.relation_id}", item.expression)
            for item in safe_ir.geometry
            if item.relation_id in relevant and item.expression is not None
        )
        explicit_expressions.extend(
            (f"state_conditions.{item.state_condition_id}", item.expression)
            for item in safe_ir.state_conditions
            if item.state_condition_id in relevant and item.expression is not None
        )
        source_ast_issues = validate_math_expressions(explicit_expressions, source_symbols)
        if source_ast_issues:
            first = source_ast_issues[0]
            code = CompilerIssueCode.dimension_mismatch if first.code == "dimension_mismatch" else CompilerIssueCode.invalid_expression
            status = CompilerStatus.resource_limit if first.code == "resource_limit" else CompilerStatus.invalid
            return _failure(
                status,
                _issue(
                    code,
                    "source relation failed the safe AST and dimension gate",
                    first.path,
                    first.referenced_id,
                ),
            )
        try:
            law_emissions = apply_core_laws(context)
        except Exception:
            return _failure(
                CompilerStatus.invalid,
                _issue(
                    CompilerIssueCode.invalid_expression,
                    "law application could not construct a safe typed expression",
                    "laws",
                ),
            )
        explicit_emissions, descriptors, authority_issues = _explicit_emissions(
            safe_ir, query, relevant, source_symbols
        )
        if len(descriptors) > self._limits.max_constraints:
            return _failure(
                CompilerStatus.resource_limit,
                _issue(CompilerIssueCode.resource_limit, "equation graph exceeds the constraint limit", "constraints"),
            )
        emissions = _deduplicated_emissions((*law_emissions, *explicit_emissions))
        if len(emissions) > self._limits.max_equations or len(emissions) > self._limits.max_applications:
            return _failure(
                CompilerStatus.resource_limit,
                _issue(CompilerIssueCode.resource_limit, "law application exceeds graph budgets", "laws"),
            )
        ast_issues = validate_math_expressions(
            ((f"equations.{index}", item.expression) for index, item in enumerate(emissions)),
            symbol_table,
        )
        if ast_issues:
            first = ast_issues[0]
            code = CompilerIssueCode.dimension_mismatch if first.code == "dimension_mismatch" else CompilerIssueCode.invalid_expression
            status = CompilerStatus.resource_limit if first.code == "resource_limit" else CompilerStatus.invalid
            return _failure(
                status,
                _issue(
                    code,
                    "generated equation failed the safe AST and dimension gate",
                    first.path,
                    first.referenced_id,
                ),
            )
        initial_condition_issue = _initial_condition_emission_issue(
            safe_ir, emissions, symbol_nodes
        )
        if initial_condition_issue is not None:
            return _failure(CompilerStatus.invalid, initial_condition_issue)
        canonical_records = _emission_canonical_records(
            _primary_records(safe_ir, query, include_source_records=True),
            emissions,
            query,
        )
        _, canonical_edges = _graph_edges(canonical_records)
        aliases = _CanonicalIds(canonical_records, canonical_edges)
        finalized, final_issue = _finalize_emissions(emissions, aliases, symbol_table)
        if final_issue is not None or finalized is None:
            return _failure(CompilerStatus.invalid, final_issue or _issue(CompilerIssueCode.invalid_ir, "equation finalization failed", "equations"))
        component_equations = _query_component(finalized.equations, query_symbol_id)
        component_equation_ids = {item.equation_id for item in component_equations}
        component_initial_conditions = tuple(
            item
            for item in finalized.initial_conditions
            if finalized.initial_condition_equations.get(item.condition_id)
            in component_equation_ids
        )
        if len(component_initial_conditions) > self._limits.max_initial_conditions:
            return _failure(
                CompilerStatus.resource_limit,
                _issue(
                    CompilerIssueCode.resource_limit,
                    "equation graph exceeds the initial-condition limit",
                    "initial_conditions",
                ),
            )
        referenced_symbols = {
            symbol_id
            for equation in component_equations
            for symbol_id in _expression_symbol_ids(equation.expression)
        }
        referenced_symbols.update(
            symbol_id
            for condition in component_initial_conditions
            for symbol_id in (
                condition.target_symbol_id,
                condition.value_symbol_id,
                condition.wrt_symbol_id,
            )
        )
        referenced_symbols.add(query_symbol_id)
        component_symbols = tuple(
            sorted(
                (item for symbol_id, item in symbol_nodes.items() if symbol_id in referenced_symbols),
                key=lambda item: item.symbol.symbol_id,
            )
        )
        ordinary_symbols = {
            symbol_id
            for equation in component_equations
            for symbol_id in _ordinary_expression_symbol_ids(equation.expression)
        }
        unknown_ids = tuple(
            sorted(
                item.symbol.symbol_id
                for item in component_symbols
                if item.known_si_value is None
                and (
                    item.symbol.symbol_id == query_symbol_id
                    or item.quantity_role != QuantityRole.time.value
                    or item.symbol.symbol_id in ordinary_symbols
                )
            )
        )
        if len(unknown_ids) > self._limits.max_unknowns:
            return _failure(
                CompilerStatus.resource_limit,
                _issue(CompilerIssueCode.resource_limit, "equation graph exceeds the unknown limit", "symbols"),
            )
        unknown_set = set(unknown_ids)
        incidence_map = {
            equation.equation_id: tuple(
                sorted(set(_expression_symbol_ids(equation.expression)).intersection(unknown_set))
            )
            for equation in component_equations
            if isinstance(equation.expression, Equality)
        }
        incidence_edges = tuple(
            IncidenceEdge(equation_id=equation_id, symbol_id=symbol_id)
            for equation_id in sorted(incidence_map)
            for symbol_id in incidence_map[equation_id]
        )
        equality_ids = tuple(
            item.equation_id for item in component_equations if isinstance(item.expression, Equality)
        )
        known_values = {
            item.symbol.symbol_id: item.known_si_value for item in component_symbols
        }

        # Equalities containing no unknowns are deterministic consistency
        # checks, not additional solve rows.  Keeping them in the graph retains
        # provenance and independent verification while excluding them from the
        # closure rank avoids falsely classifying a nonlinear endpoint system as
        # overdetermined merely because source-grounded relations (for example
        # a_y=-g or delta_y=h_f-h_0) are also present.
        known_only_conflicts: list[str] = []
        known_only_inconclusive = False
        solving_equality_ids: list[str] = []
        for equation in component_equations:
            if not isinstance(equation.expression, Equality):
                continue
            if incidence_map.get(equation.equation_id):
                solving_equality_ids.append(equation.equation_id)
                continue
            left = _exact_scalar_value(equation.expression.left, known_values)
            right = _exact_scalar_value(equation.expression.right, known_values)
            if left is None or right is None:
                known_only_inconclusive = True
            elif left != right:
                known_only_conflicts.append(equation.equation_id)
        solving_equality_ids_tuple = tuple(solving_equality_ids)
        solving_equations = tuple(
            item
            for item in component_equations
            if not isinstance(item.expression, Equality)
            or item.equation_id in set(solving_equality_ids_tuple)
        )
        matching_rank = _maximum_matching(solving_equality_ids_tuple, incidence_map)
        denominator_issue = _denominator_domain_issue(
            component_equations,
            {item.symbol.symbol_id: item for item in component_symbols},
            known_values,
        )
        if denominator_issue is not None:
            return _failure(denominator_issue[0], denominator_issue[1])
        linear_rank, augmented_rank, linear_complete = _linear_analysis(
            solving_equations, unknown_ids, known_values
        )
        nonlinear_supported = linear_complete or all(
            _supported_non_affine_equation(equation, set(unknown_ids), known_values)
            for equation in solving_equations
            if isinstance(equation.expression, Equality)
        )
        effective_rank = linear_rank if linear_complete else matching_rank
        conflicts = (
            tuple(sorted(known_only_conflicts))
            if known_only_conflicts
            else (
                tuple(sorted(solving_equality_ids_tuple))
                if linear_complete and augmented_rank > linear_rank
                else tuple()
            )
        )
        underdetermined = effective_rank < len(unknown_ids)
        overdetermined = len(solving_equality_ids_tuple) > effective_rank
        consistency_inconclusive = known_only_inconclusive or (
            overdetermined and not linear_complete
        )
        if (
            nonlinear_supported
            and not (not linear_complete and overdetermined)
            and not conflicts
        ):
            selected, alternatives, branch_exhausted = _closed_sets(
                solving_equations,
                unknown_ids,
                incidence_map,
                known_values,
                self._limits,
            )
        else:
            selected, alternatives, branch_exhausted = tuple(), tuple(), False
        rank = RankAnalysis(
            method=(
                RankMethod.numeric_linear_coefficients
                if linear_complete
                else RankMethod.structural_maximum_matching
            ),
            equality_count=len(equality_ids),
            inequality_count=sum(isinstance(item.expression, Inequality) for item in component_equations),
            unknown_count=len(unknown_ids),
            structural_rank=effective_rank,
            underdetermined=underdetermined,
            overdetermined=overdetermined,
            conflicting=bool(conflicts),
        )
        component_applications = tuple(
            item
            for item in finalized.applications
            if any(equation_id in component_equation_ids for equation_id in item.equation_ids)
        )
        descriptor_map = {identifier: (kind, evidence) for identifier, kind, evidence in descriptors}
        descriptor_map.update(
            {
                item.relation_id: (f"geometry_{item.kind.value}", tuple(item.evidence_refs))
                for item in safe_ir.geometry
                if item.relation_id in finalized.descriptor_equations
            }
        )
        descriptor_map.update(
            {
                item.state_condition_id: (f"state_{item.kind.value}", tuple(item.evidence_refs))
                for item in safe_ir.state_conditions
                if item.state_condition_id in finalized.descriptor_equations
            }
        )
        constraints = tuple(
            sorted(
                (
                    ConstraintNode(
                        constraint_id=identifier,
                        constraint_kind=descriptor_map[identifier][0],
                        equation_id=equation_id,
                        scope=next(item.scope for item in component_equations if item.equation_id == equation_id),
                        source_evidence_ids=descriptor_map[identifier][1],
                    )
                    for identifier, equation_id in finalized.descriptor_equations.items()
                    if equation_id in component_equation_ids and identifier in descriptor_map
                ),
                key=lambda item: item.constraint_id,
            )
        )
        fingerprint = _graph_fingerprint(
            query,
            query_symbol_id,
            component_symbols,
            component_equations,
            constraints,
            component_initial_conditions,
            selected,
            alternatives,
            aliases,
        )
        graph = EquationGraph(
            query_id=query.query_id,
            query_symbol_id=query_symbol_id,
            symbols=component_symbols,
            equations=component_equations,
            constraints=constraints,
            initial_conditions=component_initial_conditions,
            applications=component_applications,
            incidence=incidence_edges,
            rank=rank,
            selected_equation_ids=selected,
            alternative_closed_sets=alternatives,
            fingerprint=fingerprint,
        )
        issues: list[CompilerIssue] = list(authority_issues)
        issues.extend(
            _issue(
                CompilerIssueCode.unsupported_feature,
                "model feature label retained as a non-routing diagnostic",
                f"unsupported_features.{index}",
                feature.feature_code,
                warning=True,
            )
            for index, feature in enumerate(safe_ir.unsupported_features)
        )
        if not linear_complete and (not nonlinear_supported or overdetermined):
            issues.append(
                _issue(
                    CompilerIssueCode.consistency_inconclusive,
                    "non-affine equation component is outside the certified quadratic/calculus class or lacks an exact consistency proof",
                    "equations",
                )
            )
            status = CompilerStatus.unsupported
        elif conflicts:
            issues.append(
                _issue(
                    CompilerIssueCode.duplicate_conflict,
                    "affine equation rows are mutually inconsistent",
                    "equations",
                    conflicts[0],
                )
            )
            status = CompilerStatus.conflicting
        elif branch_exhausted:
            issues.append(
                _issue(
                    CompilerIssueCode.resource_limit,
                    "closed-set search reached its branch limit",
                    "equations",
                )
            )
            status = CompilerStatus.resource_limit
        elif underdetermined:
            issues.append(
                _issue(
                    CompilerIssueCode.underdetermined,
                    "equation graph does not structurally determine every relevant unknown",
                    "equations",
                )
            )
            status = CompilerStatus.underdetermined
        elif consistency_inconclusive:
            issues.append(
                _issue(
                    CompilerIssueCode.consistency_inconclusive,
                    "redundant non-affine equations cannot be certified consistent",
                    "equations",
                )
            )
            status = CompilerStatus.unsupported
        elif overdetermined:
            issues.append(
                _issue(
                    CompilerIssueCode.overdetermined,
                    "equation graph has more equalities than its structural rank",
                    "equations",
                    warning=True,
                )
            )
            status = CompilerStatus.overdetermined
        else:
            status = CompilerStatus.ready
        if not linear_complete and nonlinear_supported and not overdetermined and status is CompilerStatus.ready:
            issues.append(
                _issue(
                    CompilerIssueCode.nonlinear_verification_deferred,
                    "candidate and residual verification for the certified nonlinear/calculus component is deferred to the solver stage",
                    "equations",
                    warning=True,
                )
            )
        return CompilerResult(status=status, graph=graph, issues=tuple(issues))


def compile_mechanics_ir(
    ir: object,
    *,
    validated_ir_authorization: ValidatedIRAuthorization | None = None,
    query_id: str | None = None,
    limits: CompilerLimits | None = None,
    approved_assumption_ids: Collection[str] | None = None,
    authorized_corrections: Mapping[str, CorrectionAuthorization] | None = None,
    authorized_assumptions: Mapping[str, AssumptionAuthorization] | None = None,
) -> CompilerResult:
    return MechanicsCompiler(limits).compile(
        ir,
        validated_ir_authorization=validated_ir_authorization,
        query_id=query_id,
        approved_assumption_ids=approved_assumption_ids,
        authorized_corrections=authorized_corrections,
        authorized_assumptions=authorized_assumptions,
    )


__all__ = [
    "MechanicsCompiler",
    "authorize_validated_mechanics_ir",
    "compile_mechanics_ir",
]
