"""Independent, typed numeric evaluation for the mechanics verifier.

The evaluator accepts only the frozen mechanics math AST and an exact symbol
table.  It deliberately has no string-to-expression path and does not depend
on a symbolic backend's residual or success claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Mapping, TypeAlias

from engine.mechanics.math_ast import (
    Add,
    Cos,
    Cross,
    Derivative,
    Divide,
    Dot,
    Equality,
    Inequality,
    InequalityRelation,
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
    SymbolRef,
    Tan,
    VectorNode,
)
from engine.mechanics.solver.contracts import SIValue


NumericValue: TypeAlias = float | tuple[float, ...]
EvaluatedValue: TypeAlias = NumericValue | bool


class EvaluationStatus(str, Enum):
    ok = "ok"
    error = "error"
    inconclusive = "inconclusive"


class EvaluationErrorCode(str, Enum):
    missing_symbol = "missing_symbol"
    shape_mismatch = "shape_mismatch"
    nonfinite_value = "nonfinite_value"
    domain_error = "domain_error"
    unsupported_calculus = "unsupported_calculus"
    unsupported_trajectory = "unsupported_trajectory"
    unsupported_expression = "unsupported_expression"
    resource_limit = "resource_limit"
    no_piecewise_branch = "no_piecewise_branch"


@dataclass(frozen=True)
class EvaluationResult:
    status: EvaluationStatus
    value: EvaluatedValue | None = None
    error: EvaluationErrorCode | None = None
    referenced_symbol_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status is EvaluationStatus.ok:
            if self.value is None or self.error is not None:
                raise ValueError("successful evaluation requires one value and no error")
        elif self.value is not None or self.error is None:
            raise ValueError("closed evaluation requires one error and no value")
        if self.referenced_symbol_ids != tuple(sorted(set(self.referenced_symbol_ids))):
            raise ValueError("evaluation symbol provenance must be sorted and unique")


@dataclass(frozen=True)
class RelationResult:
    status: EvaluationStatus
    satisfied: bool | None
    measured_error: float | None
    tolerance: float | None
    error: EvaluationErrorCode | None = None
    referenced_symbol_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status is EvaluationStatus.ok:
            if (
                self.satisfied is None
                or self.measured_error is None
                or self.tolerance is None
                or self.error is not None
            ):
                raise ValueError("successful relation evaluation requires a bounded measurement")
            if not (
                math.isfinite(self.measured_error)
                and 0.0 <= self.measured_error <= 1.0
                and math.isfinite(self.tolerance)
                and self.tolerance > 0.0
            ):
                raise ValueError("relation measurements must be finite and bounded")
        elif any(
            value is not None
            for value in (self.satisfied, self.measured_error, self.tolerance)
        ) or self.error is None:
            raise ValueError("closed relation evaluation requires only one error code")


def _closed(
    error: EvaluationErrorCode,
    symbols: set[str] | tuple[str, ...] = (),
    *,
    inconclusive: bool = False,
) -> EvaluationResult:
    return EvaluationResult(
        status=(
            EvaluationStatus.inconclusive
            if inconclusive
            else EvaluationStatus.error
        ),
        error=error,
        referenced_symbol_ids=tuple(sorted(set(symbols))),
    )


def _is_scalar(value: object) -> bool:
    return isinstance(value, float) and math.isfinite(value)


def _is_vector(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and bool(value)
        and all(_is_scalar(item) for item in value)
    )


def _validated_numeric(value: object) -> NumericValue | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        converted = float(value)
        return converted if math.isfinite(converted) else None
    if isinstance(value, tuple) and value:
        converted_items: list[float] = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                return None
            converted = float(item)
            if not math.isfinite(converted):
                return None
            converted_items.append(converted)
        return tuple(converted_items)
    return None


def _magnitude(value: NumericValue) -> float:
    if isinstance(value, float):
        return abs(value)
    return math.sqrt(sum(item * item for item in value))


def _same_shape(left: NumericValue, right: NumericValue) -> bool:
    return (
        isinstance(left, float)
        and isinstance(right, float)
        or isinstance(left, tuple)
        and isinstance(right, tuple)
        and len(left) == len(right)
    )


def _subtract_values(
    left: NumericValue,
    right: NumericValue,
) -> NumericValue | None:
    if isinstance(left, float) and isinstance(right, float):
        return left - right
    if isinstance(left, tuple) and isinstance(right, tuple) and len(left) == len(right):
        return tuple(a - b for a, b in zip(left, right))
    return None


def _bounded_ratio(numerator: float, denominator: float) -> float:
    if not (math.isfinite(numerator) and math.isfinite(denominator)) or denominator <= 0.0:
        return 1.0
    return min(1.0, max(0.0, numerator / denominator))


class _Evaluator:
    def __init__(
        self,
        values: Mapping[str, SIValue],
        *,
        absolute_tolerance: float,
        relative_tolerance: float,
        constraint_tolerance: float,
        max_nodes: int,
        max_depth: int,
    ) -> None:
        self._values = values
        self._absolute_tolerance = absolute_tolerance
        self._relative_tolerance = relative_tolerance
        self._constraint_tolerance = constraint_tolerance
        self._max_nodes = max_nodes
        self._max_depth = max_depth
        self._nodes = 0
        self._active: set[int] = set()

    def visit(self, node: MathExpression | MathNode, depth: int = 1) -> EvaluationResult:
        self._nodes += 1
        if self._nodes > self._max_nodes or depth > self._max_depth:
            return _closed(EvaluationErrorCode.resource_limit)
        identity = id(node)
        if identity in self._active:
            return _closed(EvaluationErrorCode.resource_limit)
        self._active.add(identity)
        try:
            return self._visit_node(node, depth)
        except (ArithmeticError, OverflowError, TypeError, ValueError):
            return _closed(EvaluationErrorCode.domain_error)
        finally:
            self._active.discard(identity)

    def _children(
        self,
        nodes: tuple[MathExpression, ...],
        depth: int,
    ) -> tuple[tuple[EvaluationResult, ...] | None, EvaluationResult | None]:
        results: list[EvaluationResult] = []
        for node in nodes:
            result = self.visit(node, depth + 1)
            if result.status is not EvaluationStatus.ok:
                return None, result
            results.append(result)
        return tuple(results), None

    @staticmethod
    def _symbols(results: tuple[EvaluationResult, ...]) -> tuple[str, ...]:
        return tuple(sorted({
            identifier
            for result in results
            for identifier in result.referenced_symbol_ids
        }))

    def _visit_node(self, node: MathExpression | MathNode, depth: int) -> EvaluationResult:
        if isinstance(node, SymbolRef):
            if node.symbol_id not in self._values:
                return _closed(EvaluationErrorCode.missing_symbol, {node.symbol_id})
            numeric = _validated_numeric(self._values[node.symbol_id])
            if numeric is None:
                return _closed(EvaluationErrorCode.nonfinite_value, {node.symbol_id})
            return EvaluationResult(
                EvaluationStatus.ok,
                value=numeric,
                referenced_symbol_ids=(node.symbol_id,),
            )

        if isinstance(node, LiteralNode):
            numeric = _validated_numeric(node.value)
            if not isinstance(numeric, float):
                return _closed(EvaluationErrorCode.nonfinite_value)
            return EvaluationResult(EvaluationStatus.ok, value=numeric)

        if isinstance(node, VectorNode):
            results, failure = self._children(tuple(node.items), depth)
            if failure is not None:
                return failure
            assert results is not None
            if any(not isinstance(item.value, float) for item in results):
                return _closed(EvaluationErrorCode.shape_mismatch, self._symbols(results))
            value = tuple(item.value for item in results)
            return EvaluationResult(
                EvaluationStatus.ok,
                value=value,
                referenced_symbol_ids=self._symbols(results),
            )

        if isinstance(node, Add):
            results, failure = self._children(tuple(node.terms), depth)
            if failure is not None:
                return failure
            assert results is not None
            values = tuple(item.value for item in results)
            symbols = self._symbols(results)
            if all(isinstance(item, float) for item in values):
                value: NumericValue = sum(values)
            elif all(isinstance(item, tuple) for item in values):
                lengths = {len(item) for item in values}
                if len(lengths) != 1:
                    return _closed(EvaluationErrorCode.shape_mismatch, symbols)
                value = tuple(sum(parts) for parts in zip(*values))
            else:
                return _closed(EvaluationErrorCode.shape_mismatch, symbols)
            return self._finite_result(value, symbols)

        if isinstance(node, Subtract):
            return self._binary_additive(node.left, node.right, depth, subtract=True)

        if isinstance(node, Multiply):
            results, failure = self._children(tuple(node.factors), depth)
            if failure is not None:
                return failure
            assert results is not None
            symbols = self._symbols(results)
            values = tuple(item.value for item in results)
            if any(isinstance(item, bool) for item in values):
                return _closed(EvaluationErrorCode.shape_mismatch, symbols)
            vectors = tuple(item for item in values if isinstance(item, tuple))
            scalars = tuple(item for item in values if isinstance(item, float))
            if len(vectors) > 1 or len(vectors) + len(scalars) != len(values):
                return _closed(EvaluationErrorCode.shape_mismatch, symbols)
            factor = math.prod(scalars)
            value = (
                tuple(factor * item for item in vectors[0])
                if vectors
                else factor
            )
            return self._finite_result(value, symbols)

        if isinstance(node, Divide):
            results, failure = self._children((node.numerator, node.denominator), depth)
            if failure is not None:
                return failure
            assert results is not None
            numerator, denominator = (item.value for item in results)
            symbols = self._symbols(results)
            if not isinstance(denominator, float) or isinstance(numerator, bool):
                return _closed(EvaluationErrorCode.shape_mismatch, symbols)
            if abs(denominator) <= self._absolute_tolerance:
                return _closed(EvaluationErrorCode.domain_error, symbols)
            value = (
                numerator / denominator
                if isinstance(numerator, float)
                else tuple(item / denominator for item in numerator)
                if isinstance(numerator, tuple)
                else None
            )
            if value is None:
                return _closed(EvaluationErrorCode.shape_mismatch, symbols)
            return self._finite_result(value, symbols)

        if isinstance(node, Power):
            results, failure = self._children((node.base, node.exponent), depth)
            if failure is not None:
                return failure
            assert results is not None
            base, exponent = (item.value for item in results)
            symbols = self._symbols(results)
            if not isinstance(base, float) or not isinstance(exponent, float):
                return _closed(EvaluationErrorCode.shape_mismatch, symbols)
            if base == 0.0 and exponent < 0.0:
                return _closed(EvaluationErrorCode.domain_error, symbols)
            if base < 0.0 and not exponent.is_integer():
                return _closed(EvaluationErrorCode.domain_error, symbols)
            return self._finite_result(math.pow(base, exponent), symbols)

        if isinstance(node, Negate):
            result = self.visit(node.operand, depth + 1)
            if result.status is not EvaluationStatus.ok:
                return result
            value = result.value
            if isinstance(value, float):
                negated: NumericValue = -value
            elif isinstance(value, tuple):
                negated = tuple(-item for item in value)
            else:
                return _closed(EvaluationErrorCode.shape_mismatch, result.referenced_symbol_ids)
            return self._finite_result(negated, result.referenced_symbol_ids)

        if isinstance(node, (Dot, Cross)):
            results, failure = self._children((node.left, node.right), depth)
            if failure is not None:
                return failure
            assert results is not None
            left, right = (item.value for item in results)
            symbols = self._symbols(results)
            if (
                not isinstance(left, tuple)
                or not isinstance(right, tuple)
                or len(left) != len(right)
                or not left
            ):
                return _closed(EvaluationErrorCode.shape_mismatch, symbols)
            if isinstance(node, Dot):
                value = sum(a * b for a, b in zip(left, right))
            elif len(left) == 3:
                value = (
                    left[1] * right[2] - left[2] * right[1],
                    left[2] * right[0] - left[0] * right[2],
                    left[0] * right[1] - left[1] * right[0],
                )
            else:
                return _closed(EvaluationErrorCode.shape_mismatch, symbols)
            return self._finite_result(value, symbols)

        if isinstance(node, (Sin, Cos, Tan)):
            result = self.visit(node.argument, depth + 1)
            if result.status is not EvaluationStatus.ok:
                return result
            if not isinstance(result.value, float):
                return _closed(EvaluationErrorCode.shape_mismatch, result.referenced_symbol_ids)
            if isinstance(node, Tan) and abs(math.cos(result.value)) <= self._absolute_tolerance:
                return _closed(EvaluationErrorCode.domain_error, result.referenced_symbol_ids)
            function = math.sin if isinstance(node, Sin) else math.cos if isinstance(node, Cos) else math.tan
            return self._finite_result(function(result.value), result.referenced_symbol_ids)

        if isinstance(node, Sqrt):
            result = self.visit(node.operand, depth + 1)
            if result.status is not EvaluationStatus.ok:
                return result
            if not isinstance(result.value, float):
                return _closed(EvaluationErrorCode.shape_mismatch, result.referenced_symbol_ids)
            if result.value < 0.0:
                return _closed(EvaluationErrorCode.domain_error, result.referenced_symbol_ids)
            return self._finite_result(math.sqrt(result.value), result.referenced_symbol_ids)

        if isinstance(node, Norm):
            result = self.visit(node.operand, depth + 1)
            if result.status is not EvaluationStatus.ok:
                return result
            if not isinstance(result.value, tuple):
                return _closed(EvaluationErrorCode.shape_mismatch, result.referenced_symbol_ids)
            return self._finite_result(_magnitude(result.value), result.referenced_symbol_ids)

        if isinstance(node, Derivative):
            return _closed(
                EvaluationErrorCode.unsupported_trajectory,
                {node.wrt_symbol_id},
                inconclusive=True,
            )

        if isinstance(node, Integral):
            return _closed(
                EvaluationErrorCode.unsupported_calculus,
                {node.wrt_symbol_id},
                inconclusive=True,
            )

        if isinstance(node, Piecewise):
            referenced: set[str] = set()
            for branch in node.branches:
                condition = self.visit(branch.condition, depth + 1)
                referenced.update(condition.referenced_symbol_ids)
                if condition.status is not EvaluationStatus.ok:
                    return condition
                if not isinstance(condition.value, bool):
                    return _closed(EvaluationErrorCode.shape_mismatch, referenced)
                if condition.value:
                    value = self.visit(branch.value, depth + 1)
                    return self._merge_symbols(value, referenced)
            if node.otherwise is None:
                return _closed(EvaluationErrorCode.no_piecewise_branch, referenced)
            value = self.visit(node.otherwise, depth + 1)
            return self._merge_symbols(value, referenced)

        if isinstance(node, (Equality, Inequality)):
            relation = self.relation(node, depth=depth)
            if relation.status is not EvaluationStatus.ok:
                return EvaluationResult(
                    status=relation.status,
                    error=relation.error,
                    referenced_symbol_ids=relation.referenced_symbol_ids,
                )
            return EvaluationResult(
                EvaluationStatus.ok,
                value=relation.satisfied,
                referenced_symbol_ids=relation.referenced_symbol_ids,
            )

        return _closed(EvaluationErrorCode.unsupported_expression)

    def _binary_additive(
        self,
        left_node: MathExpression,
        right_node: MathExpression,
        depth: int,
        *,
        subtract: bool,
    ) -> EvaluationResult:
        results, failure = self._children((left_node, right_node), depth)
        if failure is not None:
            return failure
        assert results is not None
        left, right = (item.value for item in results)
        symbols = self._symbols(results)
        if isinstance(left, bool) or isinstance(right, bool):
            return _closed(EvaluationErrorCode.shape_mismatch, symbols)
        assert isinstance(left, (float, tuple)) and isinstance(right, (float, tuple))
        value = _subtract_values(left, right) if subtract else None
        if value is None:
            return _closed(EvaluationErrorCode.shape_mismatch, symbols)
        return self._finite_result(value, symbols)

    @staticmethod
    def _finite_result(
        value: NumericValue,
        symbols: set[str] | tuple[str, ...],
    ) -> EvaluationResult:
        if not (_is_scalar(value) or _is_vector(value)):
            return _closed(EvaluationErrorCode.nonfinite_value, symbols)
        return EvaluationResult(
            EvaluationStatus.ok,
            value=value,
            referenced_symbol_ids=tuple(sorted(set(symbols))),
        )

    @staticmethod
    def _merge_symbols(result: EvaluationResult, extra: set[str]) -> EvaluationResult:
        symbols = tuple(sorted({*extra, *result.referenced_symbol_ids}))
        return EvaluationResult(
            status=result.status,
            value=result.value,
            error=result.error,
            referenced_symbol_ids=symbols,
        )

    def relation(
        self,
        relation: Equality | Inequality,
        *,
        depth: int = 1,
    ) -> RelationResult:
        results, failure = self._children((relation.left, relation.right), depth)
        if failure is not None:
            return RelationResult(
                status=failure.status,
                satisfied=None,
                measured_error=None,
                tolerance=None,
                error=failure.error,
                referenced_symbol_ids=failure.referenced_symbol_ids,
            )
        assert results is not None
        left, right = (item.value for item in results)
        symbols = self._symbols(results)
        if (
            isinstance(left, bool)
            or isinstance(right, bool)
            or not isinstance(left, (float, tuple))
            or not isinstance(right, (float, tuple))
            or not _same_shape(left, right)
        ):
            return RelationResult(
                EvaluationStatus.error,
                None,
                None,
                None,
                EvaluationErrorCode.shape_mismatch,
                symbols,
            )
        difference = _subtract_values(left, right)
        assert difference is not None
        scale = max(1.0, _magnitude(left), _magnitude(right))
        residual = _bounded_ratio(_magnitude(difference), scale)
        equality_tolerance = min(
            1.0,
            max(
                self._relative_tolerance,
                self._absolute_tolerance / scale,
            ),
        )
        if isinstance(relation, Equality):
            return RelationResult(
                EvaluationStatus.ok,
                residual <= equality_tolerance,
                residual,
                equality_tolerance,
                referenced_symbol_ids=symbols,
            )
        if not isinstance(left, float) or not isinstance(right, float):
            return RelationResult(
                EvaluationStatus.error,
                None,
                None,
                None,
                EvaluationErrorCode.shape_mismatch,
                symbols,
            )
        tolerance = min(1.0, self._constraint_tolerance / scale)
        signed = (left - right) / scale
        if relation.relation is InequalityRelation.le:
            satisfied = signed <= tolerance
            violation = max(0.0, signed)
        elif relation.relation is InequalityRelation.lt:
            satisfied = signed < -tolerance
            violation = 0.0 if satisfied else min(1.0, tolerance + max(0.0, signed) + 1.0e-15)
        elif relation.relation is InequalityRelation.ge:
            satisfied = signed >= -tolerance
            violation = max(0.0, -signed)
        else:
            satisfied = signed > tolerance
            violation = 0.0 if satisfied else min(1.0, tolerance + max(0.0, -signed) + 1.0e-15)
        # Strict comparisons can fail at equality even though their ordinary
        # distance is zero.  The bounded metric therefore records the required
        # positive margin, while the boolean remains the authoritative verdict.
        measured = min(1.0, violation)
        if not satisfied and measured <= tolerance:
            measured = min(1.0, math.nextafter(tolerance, math.inf))
        return RelationResult(
            EvaluationStatus.ok,
            satisfied,
            measured,
            tolerance,
            referenced_symbol_ids=symbols,
        )


def evaluate_expression(
    expression: MathExpression | MathNode,
    values: Mapping[str, SIValue],
    *,
    absolute_tolerance: float = 1.0e-10,
    relative_tolerance: float = 1.0e-9,
    constraint_tolerance: float = 1.0e-9,
    max_nodes: int = 4096,
    max_depth: int = 24,
) -> EvaluationResult:
    """Traverse one typed expression and return a closed deterministic result."""

    if (
        not all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            and float(item) > 0.0
            for item in (
                absolute_tolerance,
                relative_tolerance,
                constraint_tolerance,
            )
        )
        or isinstance(max_nodes, bool)
        or isinstance(max_depth, bool)
        or not isinstance(max_nodes, int)
        or not isinstance(max_depth, int)
        or max_nodes < 1
        or max_depth < 1
    ):
        return _closed(EvaluationErrorCode.resource_limit)
    return _Evaluator(
        values,
        absolute_tolerance=float(absolute_tolerance),
        relative_tolerance=float(relative_tolerance),
        constraint_tolerance=float(constraint_tolerance),
        max_nodes=max_nodes,
        max_depth=max_depth,
    ).visit(expression)


def evaluate_relation(
    relation: Equality | Inequality,
    values: Mapping[str, SIValue],
    *,
    absolute_tolerance: float = 1.0e-10,
    relative_tolerance: float = 1.0e-9,
    constraint_tolerance: float = 1.0e-9,
    max_nodes: int = 4096,
    max_depth: int = 24,
) -> RelationResult:
    """Evaluate a typed relation with bounded normalized error evidence."""

    evaluator = _Evaluator(
        values,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        constraint_tolerance=constraint_tolerance,
        max_nodes=max_nodes,
        max_depth=max_depth,
    )
    return evaluator.relation(relation)


__all__ = [
    "EvaluatedValue",
    "EvaluationErrorCode",
    "EvaluationResult",
    "EvaluationStatus",
    "NumericValue",
    "RelationResult",
    "evaluate_expression",
    "evaluate_relation",
]
