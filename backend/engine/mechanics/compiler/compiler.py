from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import itertools
import json
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
    IRConstraint,
    IRGeometryRelation,
    IRQuery,
    IRStateCondition,
    MechanicsProblemIRV1,
    Provenance,
    QuantityRole,
    QuantityShape,
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


def _structural_template_support_issue(
    ir: MechanicsProblemIRV1,
    relevant: set[str],
    approved_assumption_ids: frozenset[str],
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
        specialization_issue = _structural_specialization_issue(safe_ir, query)
        if specialization_issue is not None:
            return _failure(CompilerStatus.unsupported, specialization_issue)
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
        support_issue = _structural_template_support_issue(
            safe_ir, relevant, authority.approved_assumption_ids
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
        matching_rank = _maximum_matching(equality_ids, incidence_map)
        known_values = {
            item.symbol.symbol_id: item.known_si_value for item in component_symbols
        }
        denominator_issue = _denominator_domain_issue(
            component_equations,
            {item.symbol.symbol_id: item for item in component_symbols},
            known_values,
        )
        if denominator_issue is not None:
            return _failure(denominator_issue[0], denominator_issue[1])
        linear_rank, augmented_rank, linear_complete = _linear_analysis(
            component_equations, unknown_ids, known_values
        )
        nonlinear_supported = linear_complete or all(
            _supported_non_affine_equation(equation, set(unknown_ids), known_values)
            for equation in component_equations
            if isinstance(equation.expression, Equality)
        )
        effective_rank = linear_rank if linear_complete else matching_rank
        conflicts = (
            tuple(sorted(equality_ids))
            if linear_complete and augmented_rank > linear_rank
            else tuple()
        )
        underdetermined = effective_rank < len(unknown_ids)
        overdetermined = len(equality_ids) > effective_rank
        consistency_inconclusive = overdetermined and not linear_complete
        if nonlinear_supported and not (not linear_complete and overdetermined):
            selected, alternatives, branch_exhausted = _closed_sets(
                component_equations,
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
