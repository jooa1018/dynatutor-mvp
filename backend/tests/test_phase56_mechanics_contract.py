from __future__ import annotations

from collections.abc import Callable
import math

import pytest
from pydantic import TypeAdapter, ValidationError

from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    EntityPrimitive,
    FORBIDDEN_SCAN_MAX_DEPTH,
    FORBIDDEN_SCAN_MAX_HITS,
    FORBIDDEN_SCAN_MAX_KEY_LENGTH,
    FORBIDDEN_SCAN_MAX_NODES,
    ForbiddenFieldScanError,
    IR_SCHEMA_NAME,
    IR_SCHEMA_VERSION,
    IRQuantity,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
    find_forbidden_fields,
)
from engine.mechanics.math_ast import (
    MAX_AST_DEPTH,
    MAX_EXPRESSIONS,
    MAX_TOTAL_AST_NODES,
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
    Multiply,
    Negate,
    Norm,
    Power,
    Piecewise,
    PiecewiseBranch,
    Sin,
    Sqrt,
    SymbolDefinition,
    SymbolRef,
    SymbolShape,
    Subtract,
    Tan,
    VectorNode,
    validate_math_expression,
    validate_math_expressions,
)


def _minimal_draft_payload() -> dict[str, object]:
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {"language": "en", "correction_revision": 0},
        "source_assets": [],
        "source_evidence": [],
        "entities": [
            {
                "entity_id": "environment",
                "primitive": "environment",
                "label": "environment",
                "aliases": [],
                "evidence_refs": [],
            }
        ],
        "points": [],
        "reference_frames": [],
        "motion_intervals": [],
        "events": [],
        "quantities": [],
        "symbols": [],
        "geometry": [],
        "interactions": [],
        "constraints": [],
        "state_conditions": [],
        "queries": [],
        "principle_hints": [],
        "assumptions": [],
        "ambiguities": [],
        "figure_dependency": {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        },
        "unsupported_features": [],
    }


def _scalar_literal(
    dimension: DimensionVector | None = None,
    value: float = 1.0,
) -> LiteralNode:
    return LiteralNode(value=value, dimension=dimension)


def _comparison() -> Equality:
    return Equality(left=_scalar_literal(), right=_scalar_literal())


def _three_vector() -> VectorNode:
    return VectorNode(items=(_scalar_literal(), _scalar_literal(), _scalar_literal()))


def _complete_ir_quantity_payload() -> dict[str, object]:
    return {
        "quantity_id": "length",
        "role": "length",
        "subject_id": "body",
        "shape": "scalar",
        "dimension": {"length": 1},
        "provenance": "explicit_source",
        "raw_value": "2",
        "raw_unit": "m",
        "si_value": 2.0,
        "si_unit": "m",
    }


def test_draft_is_strict_and_allows_only_generic_entity_primitives() -> None:
    payload = _minimal_draft_payload()
    payload["unknown_top_level"] = True
    with pytest.raises(ValidationError):
        MechanicsProblemDraftV1.model_validate(payload)

    payload = _minimal_draft_payload()
    payload["entities"][0]["primitive"] = "pulley_atwood_problem"  # type: ignore[index]
    with pytest.raises(ValidationError):
        MechanicsProblemDraftV1.model_validate(payload)

    assert {item.value for item in EntityPrimitive} == {
        "particle",
        "rigid_body",
        "body_component",
        "point",
        "mass_center",
        "system",
        "surface",
        "incline",
        "rope",
        "pulley",
        "spring",
        "damper",
        "joint",
        "slot",
        "gear",
        "rack",
        "reference_frame",
        "field",
        "environment",
    }


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "answer",
        "expected_answer",
        "final_solver_result",
        "selected_equation_set",
        "verification_passed",
    ],
)
def test_draft_rejects_nested_answer_authority_fields(forbidden_key: str) -> None:
    payload = _minimal_draft_payload()
    payload["entities"][0][forbidden_key] = 42  # type: ignore[index]
    with pytest.raises(ValidationError, match="answer-authority"):
        MechanicsProblemDraftV1.model_validate(payload)


def test_ir_quantity_rejects_each_individually_missing_pair_member() -> None:
    complete = _complete_ir_quantity_payload()
    for missing in ("raw_value", "raw_unit", "si_value", "si_unit"):
        payload = dict(complete)
        payload.pop(missing)
        with pytest.raises(ValidationError):
            IRQuantity.model_validate(payload)

    assert IRQuantity.model_validate(complete).si_value == 2.0
    absent = {key: value for key, value in complete.items() if key not in {
        "raw_value", "raw_unit", "si_value", "si_unit"
    }}
    assert IRQuantity.model_validate(absent).si_value is None


@pytest.mark.parametrize(
    "present_pair",
    [("raw_value", "raw_unit"), ("si_value", "si_unit")],
    ids=("raw-only", "si-only"),
)
def test_ir_quantity_rejects_a_complete_pair_without_the_other(
    present_pair: tuple[str, str],
) -> None:
    payload = _complete_ir_quantity_payload()
    for field in {"raw_value", "raw_unit", "si_value", "si_unit"} - set(present_pair):
        payload.pop(field)

    with pytest.raises(ValidationError):
        IRQuantity.model_validate(payload)


def test_ir_quantity_normalizes_bounded_scalar_vector_and_tensor_si_values() -> None:
    scalar = IRQuantity.model_validate(_complete_ir_quantity_payload())
    assert scalar.si_value == 2.0

    scalar_integer_payload = _complete_ir_quantity_payload()
    scalar_integer_payload["si_value"] = 2
    assert IRQuantity.model_validate(scalar_integer_payload).si_value == 2.0

    vector_payload = _complete_ir_quantity_payload()
    vector_payload.update({"shape": "vector", "si_value": [3, 4, 5]})
    vector = IRQuantity.model_validate(vector_payload)
    assert vector.si_value == (3.0, 4.0, 5.0)
    assert isinstance(vector.si_value, tuple)

    tensor_payload = _complete_ir_quantity_payload()
    tensor_payload.update(
        {"shape": "tensor", "si_value": [[1, 2], [3, 4]]}
    )
    tensor = IRQuantity.model_validate(tensor_payload)
    assert tensor.si_value == ((1.0, 2.0), (3.0, 4.0))
    assert isinstance(tensor.si_value, tuple)
    assert isinstance(tensor.si_value[0], tuple)


@pytest.mark.parametrize(
    "shape,si_value",
    [
        ("scalar", [1]),
        ("vector", 1),
        ("vector", [[1, 2]]),
        ("tensor", 1),
        ("tensor", [1, 2]),
        ("tensor", [[1, 2], [3]]),
        ("vector", []),
        ("tensor", []),
        ("tensor", [[]]),
        ("vector", [1, 2, 3, 4]),
        ("tensor", [[1, 2, 3, 4]]),
        ("tensor", [[1], [2], [3], [4]]),
        ("scalar", math.nan),
        ("scalar", math.inf),
        ("scalar", -math.inf),
        ("scalar", 1.0e301),
        ("scalar", -1.0e301),
        ("scalar", True),
        ("vector", [True]),
        ("tensor", [[True]]),
        ("vector", [math.inf]),
        ("tensor", [[math.nan]]),
    ],
)
def test_ir_quantity_rejects_invalid_si_value_shapes_and_elements(
    shape: str, si_value: object
) -> None:
    payload = _complete_ir_quantity_payload()
    payload.update({"shape": shape, "si_value": si_value})
    with pytest.raises(ValidationError):
        IRQuantity.model_validate(payload)


def test_ir_quantity_is_frozen_after_validation() -> None:
    quantity = IRQuantity.model_validate(_complete_ir_quantity_payload())
    for field_name, value in (
        ("si_value", 3.0),
        ("shape", "vector"),
        ("raw_value", "3"),
    ):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(quantity, field_name, value)


def test_answer_authority_scan_is_bounded_and_allows_safe_payloads() -> None:
    payload = _minimal_draft_payload()
    assert find_forbidden_fields(payload) == ()
    assert (
        MechanicsProblemDraftV1.model_validate(payload).version
        == DRAFT_SCHEMA_VERSION
    )

    assert find_forbidden_fields({"k" * FORBIDDEN_SCAN_MAX_KEY_LENGTH: None}) == ()
    with pytest.raises(ForbiddenFieldScanError, match="key length limit"):
        find_forbidden_fields({"k" * (FORBIDDEN_SCAN_MAX_KEY_LENGTH + 1): None})
    with pytest.raises(ForbiddenFieldScanError, match="keys must be strings"):
        find_forbidden_fields({1: None})

    nested_list: list[object] = []
    cursor = nested_list
    for _ in range(FORBIDDEN_SCAN_MAX_DEPTH):
        child: list[object] = []
        cursor.append(child)
        cursor = child
    assert find_forbidden_fields(nested_list) == ()
    cursor.append([])
    with pytest.raises(ForbiddenFieldScanError, match="depth limit"):
        find_forbidden_fields(nested_list)

    cyclic_list: list[object] = []
    cyclic_list.append(cyclic_list)
    with pytest.raises(ForbiddenFieldScanError, match="cyclic"):
        find_forbidden_fields(cyclic_list)

    at_node_limit = {
        f"node_{index}": None for index in range(FORBIDDEN_SCAN_MAX_NODES - 1)
    }
    assert find_forbidden_fields(at_node_limit) == ()
    over_node_limit = {
        f"node_{index}": None for index in range(FORBIDDEN_SCAN_MAX_NODES)
    }
    with pytest.raises(ForbiddenFieldScanError, match="node limit"):
        find_forbidden_fields(over_node_limit)

    with pytest.raises(ForbiddenFieldScanError, match="hit limit"):
        find_forbidden_fields(
            [{"answer": index} for index in range(FORBIDDEN_SCAN_MAX_HITS + 1)]
        )


def test_answer_authority_scan_fails_closed_when_draft_payload_is_cyclic() -> None:
    payload = _minimal_draft_payload()
    cyclic_metadata = payload["metadata"]
    cyclic_metadata["loop"] = cyclic_metadata  # type: ignore[index]
    with pytest.raises(ValidationError, match="scan failed closed"):
        MechanicsProblemDraftV1.model_validate(payload)


def test_math_ast_discriminator_rejects_arbitrary_calls_and_code_strings() -> None:
    adapter = TypeAdapter(MathExpression)
    for payload in (
        {"op": "call", "function": "system", "arguments": []},
        {"op": "attribute", "object": "os", "name": "system"},
        {"op": "literal", "value": "__import__('os')"},
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)


def test_math_ast_literal_must_be_finite() -> None:
    with pytest.raises(ValidationError):
        LiteralNode(value=math.inf)
    with pytest.raises(ValidationError):
        LiteralNode(value=math.nan)


def test_math_ast_requires_symbols_and_checks_declared_dimension() -> None:
    length = DimensionVector(length=1)
    expression = Add(
        terms=[
            SymbolRef(symbol_id="x"),
            LiteralNode(value=1.0, dimension=DimensionVector.dimensionless()),
        ],
        dimension=length,
    )
    symbols = {
        "x": SymbolDefinition(symbol_id="x", dimension=length),
    }
    issues = validate_math_expression(expression, symbols)
    assert {item.code for item in issues} >= {"dimension_mismatch"}

    missing = validate_math_expression(SymbolRef(symbol_id="missing"), symbols)
    assert {item.code for item in missing} == {"symbol_missing"}


def test_math_ast_depth_and_power_limits_are_fail_closed() -> None:
    expression: MathExpression = LiteralNode(value=1.0)
    for _ in range(MAX_AST_DEPTH + 1):
        expression = Negate(operand=expression)
    depth_issues = validate_math_expression(expression, {})
    assert "resource_limit" in {item.code for item in depth_issues}

    power = Power(
        base=LiteralNode(value=2.0),
        exponent=LiteralNode(value=13.0),
    )
    power_issues = validate_math_expression(power, {})
    assert "resource_limit" in {item.code for item in power_issues}


def test_math_expression_collection_propagates_individual_issues() -> None:
    deep: MathExpression = _scalar_literal()
    for _ in range(MAX_AST_DEPTH + 1):
        deep = Negate(operand=deep)
    length = DimensionVector(length=1)
    issues = validate_math_expressions(
        {
            "expressions.depth": deep,
            "expressions.missing": SymbolRef(symbol_id="missing"),
            "expressions.dimension": Add(
                terms=(
                    SymbolRef(symbol_id="x"),
                    _scalar_literal(),
                )
            ),
        },
        {"x": SymbolDefinition(symbol_id="x", dimension=length)},
    )
    codes = {item.code for item in issues}

    assert {"resource_limit", "symbol_missing", "dimension_mismatch"} <= codes
    assert any(
        item.code == "resource_limit" and item.path.startswith("expressions.depth")
        for item in issues
    )
    assert any(
        item.code == "symbol_missing" and item.path == "expressions.missing"
        for item in issues
    )
    assert any(
        item.code == "dimension_mismatch" and item.path == "expressions.dimension"
        for item in issues
    )


def test_boolean_and_invalid_shapes_cannot_be_nested_as_numeric_operands() -> None:
    relation = Equality(left=LiteralNode(value=1.0), right=LiteralNode(value=1.0))
    time_symbol = SymbolDefinition(
        symbol_id="t",
        dimension=DimensionVector(time=1),
    )
    expressions = (
        Add(terms=[relation, relation]),
        Equality(left=relation, right=relation),
        Negate(operand=relation),
        Divide(numerator=relation, denominator=LiteralNode(value=1.0)),
        Derivative(expression=relation, wrt_symbol_id="t"),
    )
    for expression in expressions:
        issues = validate_math_expression(expression, {"t": time_symbol})
        assert "shape_mismatch" in {item.code for item in issues}

    missing_symbol_add = Add(
        terms=[SymbolRef(symbol_id="missing"), LiteralNode(value=1.0)]
    )
    missing_issues = validate_math_expression(missing_symbol_add, {})
    assert {"symbol_missing", "shape_mismatch"} <= {
        item.code for item in missing_issues
    }


@pytest.mark.parametrize(
    ("slot", "build", "expected_parent_code"),
    (
        pytest.param(
            "subtract",
            lambda bad: Subtract(left=bad, right=_scalar_literal()),
            "shape_mismatch",
            id="subtract",
        ),
        pytest.param(
            "multiply",
            lambda bad: Multiply(factors=(bad, _scalar_literal())),
            "shape_mismatch",
            id="multiply",
        ),
        pytest.param(
            "power-base",
            lambda bad: Power(base=bad, exponent=_scalar_literal()),
            "shape_mismatch",
            id="power-base",
        ),
        pytest.param(
            "power-exponent",
            lambda bad: Power(base=_scalar_literal(), exponent=bad),
            "dimension_mismatch",
            id="power-exponent",
        ),
        pytest.param(
            "dot",
            lambda bad: Dot(left=bad, right=_three_vector()),
            "shape_mismatch",
            id="dot",
        ),
        pytest.param(
            "cross",
            lambda bad: Cross(left=bad, right=_three_vector()),
            "shape_mismatch",
            id="cross",
        ),
        pytest.param(
            "sin",
            lambda bad: Sin(argument=bad),
            "dimension_mismatch",
            id="sin",
        ),
        pytest.param(
            "cos",
            lambda bad: Cos(argument=bad),
            "dimension_mismatch",
            id="cos",
        ),
        pytest.param(
            "tan",
            lambda bad: Tan(argument=bad),
            "dimension_mismatch",
            id="tan",
        ),
        pytest.param(
            "sqrt",
            lambda bad: Sqrt(operand=bad),
            "shape_mismatch",
            id="sqrt",
        ),
        pytest.param(
            "integral-expression",
            lambda bad: Integral(expression=bad, wrt_symbol_id="t"),
            "shape_mismatch",
            id="integral-expression",
        ),
        pytest.param(
            "integral-lower-bound",
            lambda bad: Integral(
                expression=_scalar_literal(),
                wrt_symbol_id="t",
                lower=bad,
                upper=SymbolRef(symbol_id="t"),
            ),
            "dimension_mismatch",
            id="integral-lower-bound",
        ),
        pytest.param(
            "norm",
            lambda bad: Norm(operand=bad),
            "shape_mismatch",
            id="norm",
        ),
        pytest.param(
            "nested-inequality",
            lambda bad: Inequality(relation="lt", left=bad, right=_scalar_literal()),
            "shape_mismatch",
            id="nested-inequality",
        ),
        pytest.param(
            "piecewise-value",
            lambda bad: Piecewise(
                branches=(PiecewiseBranch(condition=_comparison(), value=bad),)
            ),
            "shape_mismatch",
            id="piecewise-value",
        ),
    ),
)
@pytest.mark.parametrize(
    ("intruder", "expected_leaf_code"),
    (
        pytest.param(_comparison(), None, id="boolean"),
        pytest.param(
            SymbolRef(symbol_id="missing"),
            "symbol_missing",
            id="missing-symbol",
        ),
    ),
)
def test_numeric_slots_reject_boolean_and_missing_symbol_intrusion(
    slot: str,
    build: Callable[[MathExpression], MathExpression],
    expected_parent_code: str,
    intruder: MathExpression,
    expected_leaf_code: str | None,
) -> None:
    expression = build(intruder)
    symbols = {"t": SymbolDefinition(symbol_id="t", dimension=DimensionVector(time=1))}
    codes = {item.code for item in validate_math_expression(expression, symbols)}

    assert expected_parent_code in codes, slot
    if expected_leaf_code is not None:
        assert expected_leaf_code in codes, slot


def test_math_models_are_frozen_and_safe_validation_rechecks_bypasses() -> None:
    literal = LiteralNode(value=1.0)
    with pytest.raises(ValidationError):
        literal.value = 2.0  # type: ignore[misc]

    expression = Add(terms=[LiteralNode(value=1.0), LiteralNode(value=2.0)])
    assert isinstance(expression.terms, tuple)
    with pytest.raises(AttributeError):
        expression.terms.append(LiteralNode(value=3.0))  # type: ignore[attr-defined]

    object.__setattr__(literal, "value", "not-a-number")
    bypass_issues = validate_math_expression(literal, {})
    assert "unsupported" in {item.code for item in bypass_issues}


def test_math_ast_preflight_classifies_cycles_and_malformed_children() -> None:
    cyclic = Negate(operand=LiteralNode(value=1.0))
    object.__setattr__(cyclic, "operand", cyclic)
    cycle_issues = validate_math_expression(cyclic, {})
    assert cycle_issues
    assert {item.code for item in cycle_issues} == {"resource_limit"}
    assert all("cyclic" in item.message for item in cycle_issues)

    malformed = Negate(operand=LiteralNode(value=1.0))
    object.__setattr__(malformed, "operand", object())
    malformed_issues = validate_math_expression(malformed, {})
    assert malformed_issues
    assert {item.code for item in malformed_issues} == {"unsupported"}
    assert all("child" in item.message for item in malformed_issues)


def test_math_expression_collection_enforces_count_and_total_node_limits() -> None:
    too_many = {
        f"expressions.{index}": LiteralNode(value=float(index))
        for index in range(MAX_EXPRESSIONS + 1)
    }
    count_issues = validate_math_expressions(too_many, {})
    assert any(
        item.code == "resource_limit" and "expression limit" in item.message
        for item in count_issues
    )

    terms_per_expression = 32
    expression_count = MAX_TOTAL_AST_NODES // (terms_per_expression + 1) + 1
    assert expression_count <= MAX_EXPRESSIONS
    large = {
        f"expressions.{index}": Add(
            terms=[LiteralNode(value=float(term)) for term in range(terms_per_expression)]
        )
        for index in range(expression_count)
    }
    total_issues = validate_math_expressions(large, {})
    assert any(
        item.code == "resource_limit" and "total AST node limit" in item.message
        for item in total_issues
    )


def test_dimension_arithmetic_limits_return_dimension_issues_not_invalid_models(
) -> None:
    maximum = DimensionVector(length=24)
    minimum = DimensionVector(length=-24)
    length = DimensionVector(length=1)
    assert maximum.plus(length) is None
    assert minimum.minus(length) is None
    assert maximum.scaled(2.0) is None
    assert length.scaled(0.5) is None

    symbols = {
        "x": SymbolDefinition(symbol_id="x", dimension=length),
        "u": SymbolDefinition(
            symbol_id="u",
            dimension=maximum,
            shape=SymbolShape.vector,
            vector_length=3,
        ),
        "v": SymbolDefinition(
            symbol_id="v",
            dimension=maximum,
            shape=SymbolShape.vector,
            vector_length=3,
        ),
    }
    overflow_expressions = {
        "multiply": Multiply(
            factors=(_scalar_literal(maximum), _scalar_literal(length))
        ),
        "divide": Divide(
            numerator=_scalar_literal(minimum),
            denominator=_scalar_literal(length),
        ),
        "power": Power(
            base=_scalar_literal(maximum),
            exponent=_scalar_literal(value=2.0),
        ),
        "sqrt": Sqrt(operand=_scalar_literal(length)),
        "derivative": Derivative(
            expression=_scalar_literal(minimum),
            wrt_symbol_id="x",
        ),
        "integral": Integral(
            expression=_scalar_literal(maximum),
            wrt_symbol_id="x",
        ),
        "dot": Dot(left=SymbolRef(symbol_id="u"), right=SymbolRef(symbol_id="v")),
        "cross": Cross(left=SymbolRef(symbol_id="u"), right=SymbolRef(symbol_id="v")),
    }
    for name, expression in overflow_expressions.items():
        issues = validate_math_expression(expression, symbols)
        assert "dimension_mismatch" in {item.code for item in issues}, name


def test_math_ast_draft_and_ir_json_schemas_generate() -> None:
    assert TypeAdapter(MathExpression).json_schema()
    assert MechanicsProblemDraftV1.model_json_schema()
    ir_schema = MechanicsProblemIRV1.model_json_schema()
    assert ir_schema
    assert ir_schema["properties"]["entities"]["type"] == "array"
    assert "items" in ir_schema["properties"]["entities"]

    ir_payload = _minimal_draft_payload()
    ir_payload.update({
        "schema": IR_SCHEMA_NAME,
        "version": IR_SCHEMA_VERSION,
        "validation_policy_version": "mechanics-validation-v1",
        "normalization_policy_version": "mechanics-normalization-v1",
    })
    ir = MechanicsProblemIRV1.model_validate(ir_payload)
    assert isinstance(ir.entities, tuple)
    assert isinstance(ir.entities[0].aliases, tuple)
    assert isinstance(ir.queries, tuple)
    schema = IRQuantity.model_json_schema()
    assert schema

    def walk_schema(value: object) -> list[dict[str, object]]:
        if isinstance(value, dict):
            return [value] + [
                item
                for child in value.values()
                for item in walk_schema(child)
            ]
        if isinstance(value, list):
            return [item for child in value for item in walk_schema(child)]
        return []

    nodes = walk_schema(schema)
    assert any("tensor" in node.get("enum", []) for node in nodes)

    definitions = schema.get("$defs", {})

    def resolve_local_ref(node: object) -> dict[str, object]:
        if not isinstance(node, dict):
            return {}
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            definition = definitions.get(reference.rsplit("/", maxsplit=1)[-1])
            if isinstance(definition, dict):
                return definition
        return node

    def is_bounded_array(node: object) -> bool:
        resolved = resolve_local_ref(node)
        return (
            resolved.get("type") == "array"
            and resolved.get("minItems") == 1
            and resolved.get("maxItems") == 3
        )

    assert any(
        is_bounded_array(node)
        and is_bounded_array(resolve_local_ref(node).get("items"))
        for node in nodes
    )
