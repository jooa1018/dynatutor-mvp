"""Closed typed-AST translation used only inside solver workers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

import sympy as sp

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
    validate_math_expression,
)

from .contracts import SolvePlan


class TranslationStatus(str, Enum):
    success = "success"
    unsupported = "unsupported"
    resource_limit = "resource_limit"


class TranslationFailureCode(str, Enum):
    invalid_ast = "invalid_ast"
    symbol_missing = "symbol_missing"
    shape_mismatch = "shape_mismatch"
    unsupported_node = "unsupported_node"
    resource_limit = "resource_limit"


@dataclass(frozen=True)
class UnknownBinding:
    symbol_id: str
    shape: SymbolShape
    expression: Any
    atoms: tuple[Any, ...]


@dataclass(frozen=True)
class TranslatedSystem:
    unknowns: tuple[UnknownBinding, ...]
    solver_atoms: tuple[Any, ...]
    equations: tuple[tuple[str, Any], ...]
    inequalities: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class TranslationResult:
    status: TranslationStatus
    system: TranslatedSystem | None = None
    code: TranslationFailureCode | None = None
    referenced_id: str | None = None


@dataclass(frozen=True)
class ExpressionTranslation:
    status: TranslationStatus
    expression: Any | None = None
    code: TranslationFailureCode | None = None
    referenced_id: str | None = None


class _ClosedTranslationFailure(Exception):
    def __init__(
        self,
        code: TranslationFailureCode,
        referenced_id: str | None = None,
    ) -> None:
        self.code = code
        self.referenced_id = referenced_id
        super().__init__(code.value)


def _validation_failure_code(issue_code: str) -> TranslationFailureCode:
    if issue_code == "resource_limit":
        return TranslationFailureCode.resource_limit
    if issue_code == "symbol_missing":
        return TranslationFailureCode.symbol_missing
    if issue_code == "shape_mismatch":
        return TranslationFailureCode.shape_mismatch
    return TranslationFailureCode.invalid_ast


def _exact_number(value: float) -> sp.Rational:
    numerator, denominator = Decimal(str(value)).as_integer_ratio()
    return sp.Rational(numerator, denominator)


class _TypedTranslator:
    def __init__(
        self,
        symbols: Mapping[str, SymbolDefinition],
        known_values: Mapping[str, float | tuple[float, ...] | tuple[tuple[float, ...], ...]],
    ) -> None:
        self.definitions = dict(symbols)
        self.values: dict[str, Any] = {}
        self.unknown_bindings: dict[str, UnknownBinding] = {}
        for symbol_id in sorted(self.definitions):
            definition = self.definitions[symbol_id]
            known = known_values.get(symbol_id)
            if definition.shape is SymbolShape.scalar:
                if known is None:
                    atom = sp.Symbol(f"mechanics_scalar_{symbol_id}", real=True)
                    self.values[symbol_id] = atom
                    self.unknown_bindings[symbol_id] = UnknownBinding(
                        symbol_id=symbol_id,
                        shape=definition.shape,
                        expression=atom,
                        atoms=(atom,),
                    )
                elif isinstance(known, tuple):
                    raise _ClosedTranslationFailure(
                        TranslationFailureCode.shape_mismatch, symbol_id
                    )
                else:
                    self.values[symbol_id] = _exact_number(float(known))
            else:
                length = definition.vector_length
                if length is None:
                    raise _ClosedTranslationFailure(
                        TranslationFailureCode.shape_mismatch, symbol_id
                    )
                if known is None:
                    atoms = tuple(
                        sp.Symbol(f"mechanics_vector_{symbol_id}_{index}", real=True)
                        for index in range(length)
                    )
                    vector = sp.ImmutableDenseMatrix(length, 1, atoms)
                    self.values[symbol_id] = vector
                    self.unknown_bindings[symbol_id] = UnknownBinding(
                        symbol_id=symbol_id,
                        shape=definition.shape,
                        expression=vector,
                        atoms=atoms,
                    )
                else:
                    if (
                        not isinstance(known, tuple)
                        or len(known) != length
                        or any(isinstance(item, tuple) for item in known)
                    ):
                        raise _ClosedTranslationFailure(
                            TranslationFailureCode.shape_mismatch, symbol_id
                        )
                    self.values[symbol_id] = sp.ImmutableDenseMatrix(
                        length,
                        1,
                        tuple(_exact_number(float(item)) for item in known),
                    )

    def translate(self, node: MathExpression, dependent_on: str | None = None) -> Any:
        if isinstance(node, SymbolRef):
            value = self.values.get(node.symbol_id)
            if value is None:
                raise _ClosedTranslationFailure(
                    TranslationFailureCode.symbol_missing, node.symbol_id
                )
            if dependent_on is not None and node.symbol_id != dependent_on:
                definition = self.definitions[node.symbol_id]
                if node.symbol_id in self.unknown_bindings:
                    independent = self.values.get(dependent_on)
                    if independent is None or isinstance(independent, sp.MatrixBase):
                        raise _ClosedTranslationFailure(
                            TranslationFailureCode.shape_mismatch, dependent_on
                        )
                    if definition.shape is SymbolShape.vector:
                        length = definition.vector_length or 0
                        return sp.ImmutableDenseMatrix(
                            length,
                            1,
                            tuple(
                                sp.Function(
                                    f"mechanics_state_{node.symbol_id}_{index}",
                                    real=True,
                                )(independent)
                                for index in range(length)
                            ),
                        )
                    return sp.Function(
                        f"mechanics_state_{node.symbol_id}", real=True
                    )(independent)
            return value
        if isinstance(node, LiteralNode):
            return _exact_number(node.value)
        if isinstance(node, VectorNode):
            values = tuple(self.translate(item, dependent_on) for item in node.items)
            if any(isinstance(item, sp.MatrixBase) for item in values):
                raise _ClosedTranslationFailure(TranslationFailureCode.shape_mismatch)
            return sp.ImmutableDenseMatrix(len(values), 1, values)
        if isinstance(node, Add):
            values = tuple(self.translate(item, dependent_on) for item in node.terms)
            result = values[0]
            for item in values[1:]:
                result = result + item
            return result
        if isinstance(node, Subtract):
            return self.translate(node.left, dependent_on) - self.translate(
                node.right, dependent_on
            )
        if isinstance(node, Multiply):
            values = tuple(self.translate(item, dependent_on) for item in node.factors)
            result = values[0]
            for item in values[1:]:
                result = result * item
            return result
        if isinstance(node, Divide):
            denominator = self.translate(node.denominator, dependent_on)
            if isinstance(denominator, sp.MatrixBase):
                raise _ClosedTranslationFailure(TranslationFailureCode.shape_mismatch)
            return self.translate(node.numerator, dependent_on) / denominator
        if isinstance(node, Power):
            base = self.translate(node.base, dependent_on)
            exponent = self.translate(node.exponent, dependent_on)
            if isinstance(base, sp.MatrixBase) or isinstance(exponent, sp.MatrixBase):
                raise _ClosedTranslationFailure(TranslationFailureCode.shape_mismatch)
            return sp.Pow(base, exponent, evaluate=False)
        if isinstance(node, Negate):
            return -self.translate(node.operand, dependent_on)
        if isinstance(node, Dot):
            left = self.translate(node.left, dependent_on)
            right = self.translate(node.right, dependent_on)
            if not isinstance(left, sp.MatrixBase) or not isinstance(right, sp.MatrixBase):
                raise _ClosedTranslationFailure(TranslationFailureCode.shape_mismatch)
            return left.dot(right)
        if isinstance(node, Cross):
            left = self.translate(node.left, dependent_on)
            right = self.translate(node.right, dependent_on)
            if (
                not isinstance(left, sp.MatrixBase)
                or not isinstance(right, sp.MatrixBase)
                or left.rows != 3
                or right.rows != 3
            ):
                raise _ClosedTranslationFailure(TranslationFailureCode.shape_mismatch)
            return left.cross(right)
        if isinstance(node, Sin):
            return sp.sin(self.translate(node.argument, dependent_on), evaluate=False)
        if isinstance(node, Cos):
            return sp.cos(self.translate(node.argument, dependent_on), evaluate=False)
        if isinstance(node, Tan):
            return sp.tan(self.translate(node.argument, dependent_on), evaluate=False)
        if isinstance(node, Sqrt):
            return sp.sqrt(self.translate(node.operand, dependent_on), evaluate=False)
        if isinstance(node, Derivative):
            independent = self.values.get(node.wrt_symbol_id)
            if independent is None or isinstance(independent, sp.MatrixBase):
                raise _ClosedTranslationFailure(
                    TranslationFailureCode.shape_mismatch, node.wrt_symbol_id
                )
            expression = self.translate(node.expression, node.wrt_symbol_id)
            return sp.Derivative(expression, (independent, node.order), evaluate=False)
        if isinstance(node, Integral):
            independent = self.values.get(node.wrt_symbol_id)
            if independent is None or isinstance(independent, sp.MatrixBase):
                raise _ClosedTranslationFailure(
                    TranslationFailureCode.shape_mismatch, node.wrt_symbol_id
                )
            expression = self.translate(node.expression, node.wrt_symbol_id)
            if (node.lower is None) != (node.upper is None):
                raise _ClosedTranslationFailure(TranslationFailureCode.invalid_ast)
            limits: tuple[Any, ...]
            if node.lower is None:
                limits = (independent,)
            else:
                limits = (
                    independent,
                    self.translate(node.lower),
                    self.translate(node.upper),
                )
            result: Any = expression
            for _ in range(node.order):
                result = sp.Integral(result, limits)
            return result
        if isinstance(node, Norm):
            operand = self.translate(node.operand, dependent_on)
            if not isinstance(operand, sp.MatrixBase):
                raise _ClosedTranslationFailure(TranslationFailureCode.shape_mismatch)
            return sp.sqrt(operand.dot(operand), evaluate=False)
        if isinstance(node, Equality):
            return sp.Eq(
                self.translate(node.left, dependent_on),
                self.translate(node.right, dependent_on),
                evaluate=False,
            )
        if isinstance(node, Inequality):
            left = self.translate(node.left, dependent_on)
            right = self.translate(node.right, dependent_on)
            constructors = {
                InequalityRelation.lt: sp.StrictLessThan,
                InequalityRelation.le: sp.LessThan,
                InequalityRelation.gt: sp.StrictGreaterThan,
                InequalityRelation.ge: sp.GreaterThan,
            }
            return constructors[node.relation](left, right, evaluate=False)
        if isinstance(node, Piecewise):
            branches = tuple(
                (
                    self.translate(branch.value, dependent_on),
                    self.translate(branch.condition, dependent_on),
                )
                for branch in node.branches
            )
            if node.otherwise is not None:
                branches = (*branches, (self.translate(node.otherwise, dependent_on), True))
            return sp.Piecewise(*branches, evaluate=False)
        raise _ClosedTranslationFailure(TranslationFailureCode.unsupported_node)


def translate_expression(
    expression: MathExpression,
    symbols: Mapping[str, SymbolDefinition],
    known_values: Mapping[
        str, float | tuple[float, ...] | tuple[tuple[float, ...], ...]
    ] | None = None,
) -> ExpressionTranslation:
    """Translate one intact typed expression to an internal symbolic object."""

    issues = validate_math_expression(expression, symbols)
    if issues:
        first = issues[0]
        status = (
            TranslationStatus.resource_limit
            if first.code == "resource_limit"
            else TranslationStatus.unsupported
        )
        code = _validation_failure_code(first.code)
        return ExpressionTranslation(status=status, code=code, referenced_id=first.referenced_id)
    try:
        translator = _TypedTranslator(symbols, known_values or {})
        return ExpressionTranslation(
            status=TranslationStatus.success,
            expression=translator.translate(expression),
        )
    except _ClosedTranslationFailure as failure:
        return ExpressionTranslation(
            status=(
                TranslationStatus.resource_limit
                if failure.code is TranslationFailureCode.resource_limit
                else TranslationStatus.unsupported
            ),
            code=failure.code,
            referenced_id=failure.referenced_id,
        )
    except Exception:
        return ExpressionTranslation(
            status=TranslationStatus.unsupported,
            code=TranslationFailureCode.invalid_ast,
        )


def translate_solve_plan(plan: SolvePlan) -> TranslationResult:
    """Translate the selected graph system without consulting descriptive data."""

    definitions = {
        item.symbol.symbol_id: item.symbol
        for item in plan.graph.symbols
    }
    known_values = {
        item.symbol.symbol_id: item.known_si_value
        for item in plan.graph.symbols
        if item.known_si_value is not None
    }
    selected = set(plan.selected_equality_ids)
    inequality_ids = set(plan.inequality_ids)
    expressions = tuple(
        item
        for item in plan.graph.equations
        if item.equation_id in selected or item.equation_id in inequality_ids
    )
    for item in expressions:
        issues = validate_math_expression(
            item.expression,
            definitions,
            path=f"equation.{item.equation_id}",
        )
        if issues:
            first = issues[0]
            status = (
                TranslationStatus.resource_limit
                if first.code == "resource_limit"
                else TranslationStatus.unsupported
            )
            return TranslationResult(
                status=status,
                code=_validation_failure_code(first.code),
                referenced_id=first.referenced_id or item.equation_id,
            )
    try:
        translator = _TypedTranslator(definitions, known_values)
        bindings = tuple(
            translator.unknown_bindings[symbol_id]
            for symbol_id in plan.unknown_symbol_ids
        )
        equations: list[tuple[str, Any]] = []
        inequalities: list[tuple[str, Any]] = []
        by_id = {item.equation_id: item for item in plan.graph.equations}
        for equation_id in plan.selected_equality_ids:
            relation = translator.translate(by_id[equation_id].expression)
            if not isinstance(relation, sp.Equality):
                raise _ClosedTranslationFailure(
                    TranslationFailureCode.invalid_ast, equation_id
                )
            equations.append((equation_id, relation.lhs - relation.rhs))
        for equation_id in plan.inequality_ids:
            relation = translator.translate(by_id[equation_id].expression)
            if isinstance(relation, sp.Equality) or not getattr(relation, "is_Relational", False):
                raise _ClosedTranslationFailure(
                    TranslationFailureCode.invalid_ast, equation_id
                )
            inequalities.append((equation_id, relation))
        return TranslationResult(
            status=TranslationStatus.success,
            system=TranslatedSystem(
                unknowns=bindings,
                solver_atoms=tuple(atom for binding in bindings for atom in binding.atoms),
                equations=tuple(equations),
                inequalities=tuple(inequalities),
            ),
        )
    except _ClosedTranslationFailure as failure:
        return TranslationResult(
            status=(
                TranslationStatus.resource_limit
                if failure.code is TranslationFailureCode.resource_limit
                else TranslationStatus.unsupported
            ),
            code=failure.code,
            referenced_id=failure.referenced_id,
        )
    except Exception:
        return TranslationResult(
            status=TranslationStatus.unsupported,
            code=TranslationFailureCode.invalid_ast,
        )


__all__ = [
    "ExpressionTranslation",
    "TranslatedSystem",
    "TranslationFailureCode",
    "TranslationResult",
    "TranslationStatus",
    "UnknownBinding",
    "translate_expression",
    "translate_solve_plan",
]
