from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Annotated, Iterable, Literal, Mapping, TypeAlias, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)


MATH_AST_VERSION = "mechanics-math-ast-v1"
MAX_AST_NODES = 256
MAX_AST_DEPTH = 24
MAX_VECTOR_LENGTH = 8
MAX_PIECEWISE_BRANCHES = 8
MAX_CALCULUS_ORDER = 4
MAX_ABSOLUTE_POWER = 12.0
MAX_TOTAL_AST_NODES = 4096
MAX_EXPRESSIONS = 128

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]*$",
    ),
]
FiniteFloat = Annotated[
    float,
    Field(allow_inf_nan=False, ge=-1.0e300, le=1.0e300),
]


class StrictMathModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        frozen=True,
        revalidate_instances="always",
    )


class DimensionVector(StrictMathModel):
    """Integer exponents of the seven SI base dimensions.

    Plane angle is dimensionless in Pint and therefore has no separate slot.
    """

    mass: int = Field(default=0, ge=-24, le=24)
    length: int = Field(default=0, ge=-24, le=24)
    time: int = Field(default=0, ge=-24, le=24)
    current: int = Field(default=0, ge=-24, le=24)
    temperature: int = Field(default=0, ge=-24, le=24)
    amount: int = Field(default=0, ge=-24, le=24)
    luminous_intensity: int = Field(default=0, ge=-24, le=24)

    @classmethod
    def dimensionless(cls) -> "DimensionVector":
        return cls()

    def plus(self, other: "DimensionVector") -> "DimensionVector" | None:
        values = {
            name: getattr(self, name) + getattr(other, name)
            for name in self.model_fields
        }
        try:
            return DimensionVector(**values)
        except ValueError:
            return None

    def minus(self, other: "DimensionVector") -> "DimensionVector" | None:
        values = {
            name: getattr(self, name) - getattr(other, name)
            for name in self.model_fields
        }
        try:
            return DimensionVector(**values)
        except ValueError:
            return None

    def scaled(self, factor: float) -> "DimensionVector" | None:
        values: dict[str, int] = {}
        for name in self.model_fields:
            value = getattr(self, name) * factor
            rounded = round(value)
            if not math.isclose(value, rounded, rel_tol=0.0, abs_tol=1.0e-10):
                return None
            values[name] = int(rounded)
        try:
            return DimensionVector(**values)
        except ValueError:
            return None


class SymbolShape(str, Enum):
    scalar = "scalar"
    vector = "vector"


class SymbolDefinition(StrictMathModel):
    symbol_id: Identifier
    quantity_id: Identifier | None = None
    dimension: DimensionVector
    shape: SymbolShape = SymbolShape.scalar
    vector_length: int | None = Field(default=None, ge=2, le=MAX_VECTOR_LENGTH)

    @model_validator(mode="after")
    def validate_shape(self) -> "SymbolDefinition":
        if self.shape == SymbolShape.vector and self.vector_length is None:
            raise ValueError("vector symbols require vector_length")
        if self.shape == SymbolShape.scalar and self.vector_length is not None:
            raise ValueError("scalar symbols cannot declare vector_length")
        return self


class MathNode(StrictMathModel):
    dimension: DimensionVector | None = None


class SymbolRef(MathNode):
    op: Literal["symbol"] = "symbol"
    symbol_id: Identifier


class LiteralNode(MathNode):
    op: Literal["literal"] = "literal"
    value: FiniteFloat


class VectorNode(MathNode):
    op: Literal["vector"] = "vector"
    items: tuple["MathExpression", ...] = Field(
        min_length=2, max_length=MAX_VECTOR_LENGTH
    )


class Add(MathNode):
    op: Literal["add"] = "add"
    terms: tuple["MathExpression", ...] = Field(min_length=2, max_length=32)


class Subtract(MathNode):
    op: Literal["subtract"] = "subtract"
    left: "MathExpression"
    right: "MathExpression"


class Multiply(MathNode):
    op: Literal["multiply"] = "multiply"
    factors: tuple["MathExpression", ...] = Field(min_length=2, max_length=32)


class Divide(MathNode):
    op: Literal["divide"] = "divide"
    numerator: "MathExpression"
    denominator: "MathExpression"


class Power(MathNode):
    op: Literal["power"] = "power"
    base: "MathExpression"
    exponent: "MathExpression"


class Negate(MathNode):
    op: Literal["negate"] = "negate"
    operand: "MathExpression"


class Dot(MathNode):
    op: Literal["dot"] = "dot"
    left: "MathExpression"
    right: "MathExpression"


class Cross(MathNode):
    op: Literal["cross"] = "cross"
    left: "MathExpression"
    right: "MathExpression"


class Sin(MathNode):
    op: Literal["sin"] = "sin"
    argument: "MathExpression"


class Cos(MathNode):
    op: Literal["cos"] = "cos"
    argument: "MathExpression"


class Tan(MathNode):
    op: Literal["tan"] = "tan"
    argument: "MathExpression"


class Sqrt(MathNode):
    op: Literal["sqrt"] = "sqrt"
    operand: "MathExpression"


class Derivative(MathNode):
    op: Literal["derivative"] = "derivative"
    expression: "MathExpression"
    wrt_symbol_id: Identifier
    order: int = Field(default=1, ge=1, le=MAX_CALCULUS_ORDER)


class Integral(MathNode):
    op: Literal["integral"] = "integral"
    expression: "MathExpression"
    wrt_symbol_id: Identifier
    lower: "MathExpression | None" = None
    upper: "MathExpression | None" = None
    order: int = Field(default=1, ge=1, le=MAX_CALCULUS_ORDER)


class Norm(MathNode):
    op: Literal["norm"] = "norm"
    operand: "MathExpression"


class Equality(MathNode):
    op: Literal["equality"] = "equality"
    left: "MathExpression"
    right: "MathExpression"


class InequalityRelation(str, Enum):
    lt = "lt"
    le = "le"
    gt = "gt"
    ge = "ge"


class Inequality(MathNode):
    op: Literal["inequality"] = "inequality"
    relation: InequalityRelation
    left: "MathExpression"
    right: "MathExpression"


class PiecewiseBranch(StrictMathModel):
    condition: "RelationExpression"
    value: "MathExpression"


class Piecewise(MathNode):
    op: Literal["piecewise"] = "piecewise"
    branches: tuple[PiecewiseBranch, ...] = Field(
        min_length=1, max_length=MAX_PIECEWISE_BRANCHES
    )
    otherwise: "MathExpression | None" = None


RelationExpression: TypeAlias = Annotated[
    Union[Equality, Inequality], Field(discriminator="op")
]
MathExpression: TypeAlias = Annotated[
    Union[
        SymbolRef,
        LiteralNode,
        VectorNode,
        Add,
        Subtract,
        Multiply,
        Divide,
        Power,
        Negate,
        Dot,
        Cross,
        Sin,
        Cos,
        Tan,
        Sqrt,
        Derivative,
        Integral,
        Norm,
        Piecewise,
        Equality,
        Inequality,
    ],
    Field(discriminator="op"),
]


_FORWARD_MODELS = (
    VectorNode,
    Add,
    Subtract,
    Multiply,
    Divide,
    Power,
    Negate,
    Dot,
    Cross,
    Sin,
    Cos,
    Tan,
    Sqrt,
    Derivative,
    Integral,
    Norm,
    Equality,
    Inequality,
    PiecewiseBranch,
    Piecewise,
)
for _model in _FORWARD_MODELS:
    _model.model_rebuild(
        _types_namespace={
            "MathExpression": MathExpression,
            "RelationExpression": RelationExpression,
        }
    )


@dataclass(frozen=True)
class AstValidationIssue:
    code: str
    message: str
    path: str
    referenced_id: str | None = None


@dataclass(frozen=True)
class _Inferred:
    dimension: DimensionVector
    shape: str


def _children(node: MathNode) -> tuple[MathNode, ...]:
    if isinstance(node, VectorNode):
        return tuple(node.items)
    if isinstance(node, Add):
        return tuple(node.terms)
    if isinstance(node, (Subtract, Dot, Cross, Equality, Inequality)):
        return (node.left, node.right)
    if isinstance(node, Multiply):
        return tuple(node.factors)
    if isinstance(node, Divide):
        return (node.numerator, node.denominator)
    if isinstance(node, Power):
        return (node.base, node.exponent)
    if isinstance(node, (Negate, Sqrt, Norm)):
        return (node.operand,)
    if isinstance(node, (Sin, Cos, Tan)):
        return (node.argument,)
    if isinstance(node, Derivative):
        return (node.expression,)
    if isinstance(node, Integral):
        bounds = tuple(item for item in (node.lower, node.upper) if item is not None)
        return (node.expression, *bounds)
    if isinstance(node, Piecewise):
        parts: list[MathNode] = []
        for branch in node.branches:
            parts.extend((branch.condition, branch.value))
        if node.otherwise is not None:
            parts.append(node.otherwise)
        return tuple(parts)
    return ()


def _shape_for_symbol(symbol: SymbolDefinition) -> str:
    if symbol.shape == SymbolShape.vector:
        return f"vector:{symbol.vector_length}"
    return "scalar"


def _is_numeric_shape(shape: str) -> bool:
    return shape == "scalar" or shape.startswith("vector:")


_EXPRESSION_ADAPTER = TypeAdapter(MathExpression)


def _validated_expression_copy(expression: object) -> MathExpression | None:
    """Return a deep schema-validated copy, including for already-built models."""

    try:
        payload = (
            expression.model_dump(mode="python", warnings="none")
            if isinstance(expression, BaseModel)
            else expression
        )
        return _EXPRESSION_ADAPTER.validate_python(payload)
    except Exception:
        return None


def _validated_symbol_table(
    symbols: Mapping[str, SymbolDefinition],
    issues: list[AstValidationIssue],
    path: str,
) -> dict[str, SymbolDefinition]:
    validated: dict[str, SymbolDefinition] = {}
    try:
        iterator = iter(symbols.items())
    except Exception:
        issues.append(AstValidationIssue("unsupported", "symbol table must be a mapping", path))
        return validated
    try:
        for index in range(513):
            try:
                key, value = next(iterator)
            except StopIteration:
                break
            if index >= 512:
                issues.append(AstValidationIssue("resource_limit", "symbol table exceeds 512 entries", path))
                break
            try:
                payload = (
                    value.model_dump(mode="python", warnings="none")
                    if isinstance(value, BaseModel)
                    else value
                )
                symbol = SymbolDefinition.model_validate(payload)
            except Exception:
                issues.append(AstValidationIssue("unsupported", "symbol definition is not schema-valid", f"{path}.{index}"))
                continue
            if key != symbol.symbol_id:
                issues.append(AstValidationIssue("unsupported", "symbol table key must equal symbol_id", f"{path}.{index}", symbol.symbol_id))
                continue
            validated[key] = symbol
    except Exception:
        issues.append(AstValidationIssue("unsupported", "symbol table iteration failed", path))
    return validated


def validate_math_expression(
    expression: MathExpression | object,
    symbols: Mapping[str, SymbolDefinition],
    *,
    path: str = "expression",
) -> tuple[AstValidationIssue, ...]:
    """Validate a typed expression without interpreting any source string."""

    issues: list[AstValidationIssue] = []
    if isinstance(expression, MathNode):
        _, preflight_issues = _bounded_node_count(
            expression,
            path=path,
            limit=MAX_AST_NODES,
        )
        if preflight_issues:
            return preflight_issues
    safe_expression = _validated_expression_copy(expression)
    if safe_expression is None:
        return (
            AstValidationIssue(
                "unsupported",
                "expression is not an intact schema-valid AST",
                path,
            ),
        )
    safe_symbols = _validated_symbol_table(symbols, issues, f"{path}.symbols")
    node_count = 0
    active: set[int] = set()

    def issue(code: str, message: str, node_path: str, ref: str | None = None) -> None:
        issues.append(AstValidationIssue(code, message, node_path, ref))

    def infer(node: MathNode, node_path: str, depth: int) -> _Inferred:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_AST_NODES:
            issue("resource_limit", "expression exceeds the AST node limit", node_path)
            return _Inferred(DimensionVector.dimensionless(), "invalid")
        if depth > MAX_AST_DEPTH:
            issue("resource_limit", "expression exceeds the AST depth limit", node_path)
            return _Inferred(DimensionVector.dimensionless(), "invalid")
        identity = id(node)
        if identity in active:
            issue("resource_limit", "cyclic AST object graph is not allowed", node_path)
            return _Inferred(DimensionVector.dimensionless(), "invalid")
        active.add(identity)
        try:
            if isinstance(node, SymbolRef):
                symbol = safe_symbols.get(node.symbol_id)
                if symbol is None:
                    issue("symbol_missing", "symbol reference is not in the symbol table", node_path, node.symbol_id)
                    result = _Inferred(node.dimension or DimensionVector.dimensionless(), "invalid")
                else:
                    result = _Inferred(symbol.dimension, _shape_for_symbol(symbol))
            elif isinstance(node, LiteralNode):
                if not math.isfinite(node.value):
                    issue("unsupported", "literal must be finite", node_path)
                result = _Inferred(node.dimension or DimensionVector.dimensionless(), "scalar")
            elif isinstance(node, VectorNode):
                inferred = [infer(item, f"{node_path}.items.{index}", depth + 1) for index, item in enumerate(node.items)]
                first = inferred[0]
                if any(item.shape != "scalar" for item in inferred):
                    issue("shape_mismatch", "vector elements must be scalar", node_path)
                if any(item.dimension != first.dimension for item in inferred[1:]):
                    issue("dimension_mismatch", "vector elements must share one dimension", node_path)
                result = _Inferred(first.dimension, f"vector:{len(node.items)}")
            elif isinstance(node, (Add, Multiply)):
                values = node.terms if isinstance(node, Add) else node.factors
                inferred = [infer(item, f"{node_path}.{('terms' if isinstance(node, Add) else 'factors')}.{index}", depth + 1) for index, item in enumerate(values)]
                if isinstance(node, Add):
                    first = inferred[0]
                    if any(not _is_numeric_shape(item.shape) for item in inferred):
                        issue("shape_mismatch", "addends must be numeric", node_path)
                    if any(item.dimension != first.dimension for item in inferred[1:]):
                        issue("dimension_mismatch", "addends must share one dimension", node_path)
                    if any(item.shape != first.shape for item in inferred[1:]):
                        issue("shape_mismatch", "addends must share one shape", node_path)
                    result = first if all(_is_numeric_shape(item.shape) for item in inferred) else _Inferred(first.dimension, "invalid")
                else:
                    numeric = all(_is_numeric_shape(item.shape) for item in inferred)
                    non_scalars = [item for item in inferred if item.shape.startswith("vector:")]
                    if not numeric or len(non_scalars) > 1:
                        issue("shape_mismatch", "multiply allows at most one vector operand", node_path)
                    dimension = DimensionVector.dimensionless()
                    for item in inferred:
                        combined = dimension.plus(item.dimension)
                        if combined is None:
                            issue("dimension_mismatch", "multiply exceeds dimension exponent bounds", node_path)
                            dimension = DimensionVector.dimensionless()
                            numeric = False
                            break
                        dimension = combined
                    shape = non_scalars[0].shape if len(non_scalars) == 1 else "scalar"
                    result = _Inferred(dimension, shape if numeric else "invalid")
            elif isinstance(node, Subtract):
                left = infer(node.left, f"{node_path}.left", depth + 1)
                right = infer(node.right, f"{node_path}.right", depth + 1)
                numeric = _is_numeric_shape(left.shape) and _is_numeric_shape(right.shape)
                if not numeric:
                    issue("shape_mismatch", "subtraction operands must be numeric", node_path)
                if left.dimension != right.dimension:
                    issue("dimension_mismatch", "subtraction operands must share one dimension", node_path)
                if left.shape != right.shape:
                    issue("shape_mismatch", "subtraction operands must share one shape", node_path)
                result = left if numeric else _Inferred(left.dimension, "invalid")
            elif isinstance(node, Divide):
                numerator = infer(node.numerator, f"{node_path}.numerator", depth + 1)
                denominator = infer(node.denominator, f"{node_path}.denominator", depth + 1)
                numeric = _is_numeric_shape(numerator.shape) and _is_numeric_shape(denominator.shape)
                if not numeric:
                    issue("shape_mismatch", "division operands must be numeric", node_path)
                if denominator.shape != "scalar":
                    issue("shape_mismatch", "division denominator must be scalar", node_path)
                dimension = numerator.dimension.minus(denominator.dimension)
                if dimension is None:
                    issue("dimension_mismatch", "division exceeds dimension exponent bounds", node_path)
                    dimension = DimensionVector.dimensionless()
                    numeric = False
                result = _Inferred(dimension, numerator.shape if numeric else "invalid")
            elif isinstance(node, Power):
                base = infer(node.base, f"{node_path}.base", depth + 1)
                exponent = infer(node.exponent, f"{node_path}.exponent", depth + 1)
                power_value: float | None = None
                if not isinstance(node.exponent, LiteralNode):
                    issue("unsupported", "power exponent must be a finite literal", node_path)
                else:
                    power_value = node.exponent.value
                if not _is_numeric_shape(exponent.shape) or exponent.shape != "scalar" or exponent.dimension != DimensionVector.dimensionless():
                    issue("dimension_mismatch", "power exponent must be dimensionless scalar", node_path)
                if not _is_numeric_shape(base.shape) or base.shape != "scalar":
                    issue("shape_mismatch", "power base must be scalar", node_path)
                if power_value is None or abs(power_value) > MAX_ABSOLUTE_POWER:
                    issue("resource_limit", "power exceeds the allowed absolute exponent", node_path)
                    powered = None
                else:
                    powered = base.dimension.scaled(power_value)
                if powered is None:
                    issue("dimension_mismatch", "power produces unsupported fractional dimensions", node_path)
                    powered = DimensionVector.dimensionless()
                result = _Inferred(powered, "scalar")
            elif isinstance(node, Negate):
                result = infer(node.operand, f"{node_path}.operand", depth + 1)
                if not _is_numeric_shape(result.shape):
                    issue("shape_mismatch", "negation operand must be numeric", node_path)
                    result = _Inferred(result.dimension, "invalid")
            elif isinstance(node, (Dot, Cross)):
                left = infer(node.left, f"{node_path}.left", depth + 1)
                right = infer(node.right, f"{node_path}.right", depth + 1)
                numeric = _is_numeric_shape(left.shape) and _is_numeric_shape(right.shape)
                if not numeric or not left.shape.startswith("vector:") or left.shape != right.shape:
                    issue("shape_mismatch", "dot/cross operands must be equal-length vectors", node_path)
                if isinstance(node, Cross) and left.shape != "vector:3":
                    issue("shape_mismatch", "cross product requires three-component vectors", node_path)
                dimension = left.dimension.plus(right.dimension)
                if dimension is None:
                    issue("dimension_mismatch", "dot/cross exceeds dimension exponent bounds", node_path)
                    dimension = DimensionVector.dimensionless()
                    numeric = False
                shape = left.shape if isinstance(node, Cross) else "scalar"
                result = _Inferred(dimension, shape if numeric else "invalid")
            elif isinstance(node, (Sin, Cos, Tan)):
                argument = infer(node.argument, f"{node_path}.argument", depth + 1)
                if not _is_numeric_shape(argument.shape) or argument.shape != "scalar" or argument.dimension != DimensionVector.dimensionless():
                    issue("dimension_mismatch", "trigonometric argument must be dimensionless scalar", node_path)
                result = _Inferred(DimensionVector.dimensionless(), "scalar")
            elif isinstance(node, Sqrt):
                operand = infer(node.operand, f"{node_path}.operand", depth + 1)
                if not _is_numeric_shape(operand.shape) or operand.shape != "scalar":
                    issue("shape_mismatch", "square root operand must be scalar", node_path)
                dimension = operand.dimension.scaled(0.5)
                if dimension is None:
                    issue("dimension_mismatch", "square root produces unsupported fractional dimensions", node_path)
                    dimension = DimensionVector.dimensionless()
                result = _Inferred(dimension, "scalar")
            elif isinstance(node, (Derivative, Integral)):
                value = infer(node.expression, f"{node_path}.expression", depth + 1)
                numeric = _is_numeric_shape(value.shape)
                if not numeric:
                    issue("shape_mismatch", "calculus expression must be numeric", node_path)
                wrt = safe_symbols.get(node.wrt_symbol_id)
                if wrt is None:
                    issue("symbol_missing", "calculus variable is not in the symbol table", node_path, node.wrt_symbol_id)
                    wrt_dimension = DimensionVector.dimensionless()
                else:
                    wrt_dimension = wrt.dimension
                    if wrt.shape != SymbolShape.scalar:
                        issue("shape_mismatch", "calculus variable must be scalar", node_path, node.wrt_symbol_id)
                scaled = wrt_dimension.scaled(node.order)
                if scaled is None:
                    issue("dimension_mismatch", "calculus order exceeds dimension exponent bounds", node_path)
                    scaled = DimensionVector.dimensionless()
                    numeric = False
                dimension = value.dimension.minus(scaled) if isinstance(node, Derivative) else value.dimension.plus(scaled)
                if dimension is None:
                    issue("dimension_mismatch", "calculus result exceeds dimension exponent bounds", node_path)
                    dimension = DimensionVector.dimensionless()
                    numeric = False
                if isinstance(node, Integral):
                    for bound_name, bound in (("lower", node.lower), ("upper", node.upper)):
                        if bound is not None:
                            inferred_bound = infer(bound, f"{node_path}.{bound_name}", depth + 1)
                            if not _is_numeric_shape(inferred_bound.shape) or inferred_bound.shape != "scalar" or inferred_bound.dimension != wrt_dimension:
                                issue("dimension_mismatch", "integral bounds must match the integration symbol", f"{node_path}.{bound_name}")
                    if (node.lower is None) != (node.upper is None):
                        issue("unsupported", "integral bounds must be both present or both absent", node_path)
                result = _Inferred(dimension, value.shape if numeric else "invalid")
            elif isinstance(node, Norm):
                operand = infer(node.operand, f"{node_path}.operand", depth + 1)
                if not _is_numeric_shape(operand.shape) or not operand.shape.startswith("vector:"):
                    issue("shape_mismatch", "norm operand must be a vector", node_path)
                result = _Inferred(operand.dimension, "scalar")
            elif isinstance(node, Piecewise):
                values: list[_Inferred] = []
                for index, branch in enumerate(node.branches):
                    condition = infer(branch.condition, f"{node_path}.branches.{index}.condition", depth + 1)
                    if condition.shape != "boolean":
                        issue("shape_mismatch", "piecewise condition must be a comparison", f"{node_path}.branches.{index}.condition")
                    values.append(infer(branch.value, f"{node_path}.branches.{index}.value", depth + 1))
                if node.otherwise is not None:
                    values.append(infer(node.otherwise, f"{node_path}.otherwise", depth + 1))
                first = values[0]
                numeric = all(_is_numeric_shape(item.shape) for item in values)
                if not numeric:
                    issue("shape_mismatch", "piecewise values must be numeric", node_path)
                if any(item.dimension != first.dimension for item in values[1:]):
                    issue("dimension_mismatch", "piecewise values must share one dimension", node_path)
                if any(item.shape != first.shape for item in values[1:]):
                    issue("shape_mismatch", "piecewise values must share one shape", node_path)
                result = first if numeric else _Inferred(first.dimension, "invalid")
            elif isinstance(node, (Equality, Inequality)):
                left = infer(node.left, f"{node_path}.left", depth + 1)
                right = infer(node.right, f"{node_path}.right", depth + 1)
                if not _is_numeric_shape(left.shape) or not _is_numeric_shape(right.shape):
                    issue("shape_mismatch", "comparison operands must be numeric", node_path)
                if left.dimension != right.dimension:
                    issue("dimension_mismatch", "comparison operands must share one dimension", node_path)
                if left.shape != right.shape:
                    issue("shape_mismatch", "comparison operands must share one shape", node_path)
                result = _Inferred(DimensionVector.dimensionless(), "boolean")
            else:
                issue("unsupported", "unknown AST node type", node_path)
                result = _Inferred(DimensionVector.dimensionless(), "invalid")

            if node.dimension is not None and node.dimension != result.dimension:
                issue("dimension_mismatch", "declared node dimension does not match inferred dimension", node_path)
            return result
        finally:
            active.remove(identity)

    try:
        infer(safe_expression, path, 1)
    except Exception:
        issue("unsupported", "AST validation could not safely inspect the expression", path)
    return tuple(issues)


def _bounded_node_count(
    expression: object,
    *,
    path: str,
    limit: int,
) -> tuple[int, tuple[AstValidationIssue, ...]]:
    issues: list[AstValidationIssue] = []
    if not isinstance(expression, MathNode):
        return 0, (AstValidationIssue("unsupported", "expression root is not a typed AST node", path),)
    count = 0
    active: set[int] = set()
    stack: list[tuple[object, str, int, bool]] = [(expression, path, 1, False)]
    while stack:
        node, node_path, depth, exiting = stack.pop()
        if not isinstance(node, MathNode):
            issues.append(AstValidationIssue("unsupported", "AST child is not a typed node", node_path))
            continue
        identity = id(node)
        if exiting:
            active.discard(identity)
            continue
        if identity in active:
            issues.append(AstValidationIssue("resource_limit", "cyclic AST object graph is not allowed", node_path))
            break
        count += 1
        if count > limit:
            issues.append(AstValidationIssue("resource_limit", "AST node budget exceeded", node_path))
            break
        if depth > MAX_AST_DEPTH:
            issues.append(AstValidationIssue("resource_limit", "AST depth budget exceeded", node_path))
            break
        active.add(identity)
        stack.append((node, node_path, depth, True))
        try:
            children = _children(node)
        except Exception:
            issues.append(AstValidationIssue("unsupported", "AST children could not be inspected", node_path))
            break
        for index, child in reversed(tuple(enumerate(children))):
            stack.append((child, f"{node_path}.child.{index}", depth + 1, False))
    return count, tuple(issues)


def validate_math_expressions(
    expressions: Mapping[str, MathExpression] | Iterable[tuple[str, MathExpression]],
    symbols: Mapping[str, SymbolDefinition],
) -> tuple[AstValidationIssue, ...]:
    """Apply per-expression gates and the aggregate expression/node budgets."""

    issues: list[AstValidationIssue] = []
    total_nodes = 0
    try:
        iterator = iter(expressions.items() if isinstance(expressions, Mapping) else expressions)
    except Exception:
        return (AstValidationIssue("unsupported", "expressions must be a bounded mapping or pair iterable", "expressions"),)
    try:
        for index in range(MAX_EXPRESSIONS + 1):
            try:
                item = next(iterator)
            except StopIteration:
                break
            if index >= MAX_EXPRESSIONS:
                issues.append(AstValidationIssue("resource_limit", "expression collection exceeds the expression limit", "expressions"))
                break
            if not isinstance(item, tuple) or len(item) != 2:
                issues.append(AstValidationIssue("unsupported", "each expression entry must be a path/expression pair", f"expressions.{index}"))
                continue
            raw_path, expression = item
            expression_path = raw_path if isinstance(raw_path, str) and 0 < len(raw_path) <= 256 else f"expressions.{index}"
            count, count_issues = _bounded_node_count(
                expression,
                path=expression_path,
                limit=MAX_TOTAL_AST_NODES - total_nodes,
            )
            total_nodes += count
            issues.extend(count_issues)
            issues.extend(validate_math_expression(expression, symbols, path=expression_path))
            if total_nodes > MAX_TOTAL_AST_NODES or any(
                item.code == "resource_limit" and "node budget" in item.message
                for item in count_issues
            ):
                issues.append(AstValidationIssue("resource_limit", "expression collection exceeds the total AST node limit", "expressions"))
                break
    except Exception:
        issues.append(AstValidationIssue("unsupported", "expression collection iteration failed", "expressions"))
    return tuple(issues)


def count_math_nodes(expression: MathExpression | object) -> int:
    count, issues = _bounded_node_count(
        expression,
        path="expression",
        limit=MAX_AST_NODES,
    )
    return MAX_AST_NODES + 1 if issues else count


__all__ = [
    "MATH_AST_VERSION",
    "MAX_ABSOLUTE_POWER",
    "MAX_AST_DEPTH",
    "MAX_AST_NODES",
    "MAX_CALCULUS_ORDER",
    "MAX_EXPRESSIONS",
    "MAX_PIECEWISE_BRANCHES",
    "MAX_TOTAL_AST_NODES",
    "MAX_VECTOR_LENGTH",
    "Add",
    "AstValidationIssue",
    "Cos",
    "Cross",
    "Derivative",
    "DimensionVector",
    "Divide",
    "Dot",
    "Equality",
    "Inequality",
    "InequalityRelation",
    "Integral",
    "LiteralNode",
    "MathExpression",
    "Multiply",
    "Negate",
    "Norm",
    "Piecewise",
    "PiecewiseBranch",
    "Power",
    "RelationExpression",
    "Sin",
    "Sqrt",
    "Subtract",
    "SymbolDefinition",
    "SymbolRef",
    "SymbolShape",
    "Tan",
    "VectorNode",
    "count_math_nodes",
    "validate_math_expression",
    "validate_math_expressions",
]
