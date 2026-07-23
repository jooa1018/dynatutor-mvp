from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from engine.mechanics.compiler.contracts import (
    CompilerLimits,
    EquationGraph,
    EquationNode,
    InitialConditionNode,
    LawApplication,
    RankAnalysis,
    SymbolNode,
)
from engine.mechanics.math_ast import (
    Derivative,
    DimensionVector,
    Integral,
    LiteralNode,
    MathExpression,
    RelationExpression,
    SymbolDefinition,
    SymbolRef,
)


_RELATION_ADAPTER = TypeAdapter(RelationExpression)
_MATH_EXPRESSION_ADAPTER = TypeAdapter(MathExpression)


def _symbol_node_payload(
    known_si_value: object = None,
    *,
    generated: object = False,
) -> dict[str, object]:
    return {
        "symbol": {
            "symbol_id": "x",
            "quantity_id": "quantity1",
            "dimension": {},
            "shape": "scalar",
            "vector_length": None,
        },
        "quantity_id": "quantity1",
        "known_si_value": known_si_value,
        "generated": generated,
    }


def _rank_payload() -> dict[str, object]:
    return {
        "equality_count": 0,
        "inequality_count": 0,
        "unknown_count": 0,
        "structural_rank": 0,
        "underdetermined": False,
        "overdetermined": False,
        "conflicting": False,
        "physical_consistency_claimed": False,
    }


def _initial_condition_payload(derivative_order: object) -> dict[str, object]:
    return {
        "condition_id": "condition1",
        "target_symbol_id": "target1",
        "value_symbol_id": "value1",
        "wrt_symbol_id": "time1",
        "derivative_order": derivative_order,
        "scope": {"event_id": "event1", "event_ids": ["event1"]},
        "source_quantity_ids": ["quantity1"],
        "source_evidence_ids": ["evidence1"],
        "source_state_condition_ids": ["state1"],
    }


def _equation_graph_payload(known_si_value: object = 1) -> dict[str, object]:
    return {
        "query_id": "query1",
        "query_symbol_id": "x",
        "symbols": [_symbol_node_payload(known_si_value)],
        "equations": [],
        "constraints": [],
        "applications": [],
        "incidence": [],
        "rank": _rank_payload(),
        "fingerprint": "f" * 64,
    }


@pytest.mark.parametrize("value", [True, False])
def test_literal_node_rejects_boolean_from_python_and_json(value: bool) -> None:
    payload = {"op": "literal", "value": value}

    with pytest.raises(ValidationError):
        LiteralNode.model_validate(payload)
    with pytest.raises(ValidationError):
        LiteralNode.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("value", [0, 1, -2.5, 1.0e300])
def test_literal_node_preserves_finite_python_and_json_numbers(value: int | float) -> None:
    payload = {"op": "literal", "value": value}

    from_python = LiteralNode.model_validate(payload)
    from_json = LiteralNode.model_validate_json(json.dumps(payload))

    assert from_python.value == float(value)
    assert from_json.value == float(value)
    assert type(from_python.value) is float
    assert type(from_json.value) is float


@pytest.mark.parametrize("value", [True, False])
def test_public_relation_expression_rejects_nested_boolean_literal(value: bool) -> None:
    payload = {
        "op": "equality",
        "left": {"op": "literal", "value": value},
        "right": {"op": "literal", "value": 0},
    }

    with pytest.raises(ValidationError):
        _RELATION_ADAPTER.validate_python(payload)
    with pytest.raises(ValidationError):
        _RELATION_ADAPTER.validate_json(json.dumps(payload))


@pytest.mark.parametrize("field_name", tuple(DimensionVector.model_fields))
@pytest.mark.parametrize("invalid", [True, "1", 1.0])
def test_dimension_exponents_reject_coercive_integer_inputs(
    field_name: str,
    invalid: object,
) -> None:
    with pytest.raises(ValidationError):
        DimensionVector.model_validate({field_name: invalid})


@pytest.mark.parametrize("invalid", [True, "3", 3.0])
def test_vector_length_rejects_coercive_integer_inputs(invalid: object) -> None:
    payload = {
        "symbol_id": "vector1",
        "dimension": {},
        "shape": "vector",
        "vector_length": invalid,
    }

    with pytest.raises(ValidationError):
        SymbolDefinition.model_validate(payload)


@pytest.mark.parametrize("model,op", [(Derivative, "derivative"), (Integral, "integral")])
@pytest.mark.parametrize("invalid", [True, "2", 2.0])
def test_calculus_order_rejects_coercive_integer_inputs(
    model: type[Derivative] | type[Integral],
    op: str,
    invalid: object,
) -> None:
    payload = {
        "op": op,
        "expression": {"op": "symbol", "symbol_id": "x"},
        "wrt_symbol_id": "t",
        "order": invalid,
    }

    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_math_integer_fields_preserve_exact_int_json_roundtrips() -> None:
    models = (
        DimensionVector(mass=1, length=-2, time=3),
        SymbolDefinition(
            symbol_id="vector1",
            dimension=DimensionVector(length=1),
            shape="vector",
            vector_length=3,
        ),
        Derivative(expression=SymbolRef(symbol_id="x"), wrt_symbol_id="t", order=2),
        Integral(expression=SymbolRef(symbol_id="x"), wrt_symbol_id="t", order=3),
    )

    for model in models:
        assert type(model).model_validate_json(model.model_dump_json()) == model


@pytest.mark.parametrize(
    "known_si_value",
    [True, False, [1, True], [False, 2.5], [[1, 2], [3, True]]],
)
def test_symbol_node_rejects_boolean_si_components(known_si_value: object) -> None:
    payload = _symbol_node_payload(known_si_value)

    with pytest.raises(ValidationError):
        SymbolNode.model_validate(payload)
    with pytest.raises(ValidationError):
        SymbolNode.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("known_si_value", [True, [1, False], [[True]]])
def test_equation_graph_rejects_nested_boolean_si_authority(
    known_si_value: object,
) -> None:
    payload = _equation_graph_payload(known_si_value)

    with pytest.raises(ValidationError):
        EquationGraph.model_validate(payload)
    with pytest.raises(ValidationError):
        EquationGraph.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    ("known_si_value", "expected"),
    [
        (1, 1.0),
        (-2.5, -2.5),
        ([1, 2.5, -3], (1.0, 2.5, -3.0)),
        ([[1, 2.5], [-3, 4]], ((1.0, 2.5), (-3.0, 4.0))),
    ],
)
def test_symbol_node_accepts_finite_int_and_float_si_components(
    known_si_value: object,
    expected: object,
) -> None:
    payload = _symbol_node_payload(known_si_value)

    from_python = SymbolNode.model_validate(payload)
    from_json = SymbolNode.model_validate_json(json.dumps(payload))

    assert from_python.known_si_value == expected
    assert from_json.known_si_value == expected
    assert SymbolNode.model_validate_json(from_python.model_dump_json()) == from_python


@pytest.mark.parametrize(
    "known_si_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        [1, float("nan")],
        [[1, 2], [3, float("inf")]],
    ],
)
def test_symbol_node_rejects_non_finite_si_components(known_si_value: object) -> None:
    with pytest.raises(ValidationError):
        SymbolNode.model_validate(_symbol_node_payload(known_si_value))


@pytest.mark.parametrize(
    "known_si_value",
    [[], [1, 2, 3, 4], [[]], [[1, 2, 3, 4]], [[1], [2], [3], [4]]],
)
def test_symbol_node_enforces_ir_si_value_shape_bounds(known_si_value: object) -> None:
    with pytest.raises(ValidationError):
        SymbolNode.model_validate(_symbol_node_payload(known_si_value))


@pytest.mark.parametrize(
    "known_si_value",
    [((1.0,), (2.0, 3.0)), [[1], [2, 3]], [[1, 2], [3]]],
)
def test_symbol_node_and_equation_graph_reject_ragged_tensors(
    known_si_value: object,
) -> None:
    symbol_payload = _symbol_node_payload(known_si_value)
    graph_payload = _equation_graph_payload(known_si_value)

    with pytest.raises(ValidationError):
        SymbolNode.model_validate(symbol_payload)
    with pytest.raises(ValidationError):
        SymbolNode.model_validate_json(json.dumps(symbol_payload))
    with pytest.raises(ValidationError):
        EquationGraph.model_validate(graph_payload)
    with pytest.raises(ValidationError):
        EquationGraph.model_validate_json(json.dumps(graph_payload))


@pytest.mark.parametrize(
    ("known_si_value", "expected"),
    [
        ([[1]], ((1.0,),)),
        ([[1, 2], [3.0, 4]], ((1.0, 2.0), (3.0, 4.0))),
        (
            [[1, 2, 3], [4.0, 5, 6], [7, 8, 9.0]],
            ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0)),
        ),
    ],
)
def test_rectangular_tensors_preserve_symbol_and_graph_json_roundtrips(
    known_si_value: object,
    expected: tuple[tuple[float, ...], ...],
) -> None:
    symbol = SymbolNode.model_validate(_symbol_node_payload(known_si_value))
    symbol_from_json = SymbolNode.model_validate_json(
        json.dumps(_symbol_node_payload(known_si_value))
    )
    graph = EquationGraph.model_validate(_equation_graph_payload(known_si_value))

    assert symbol.known_si_value == expected
    assert symbol_from_json == symbol
    assert SymbolNode.model_validate_json(symbol.model_dump_json()) == symbol
    assert graph.symbols[0].known_si_value == expected
    assert EquationGraph.model_validate_json(graph.model_dump_json()) == graph


@pytest.mark.parametrize("field_name", tuple(CompilerLimits.model_fields))
@pytest.mark.parametrize("invalid_kind", ["bool", "string", "float"])
def test_compiler_limits_reject_coercive_integer_inputs(
    field_name: str,
    invalid_kind: str,
) -> None:
    canonical = CompilerLimits().model_dump(mode="python")
    exact_value = canonical[field_name]
    canonical[field_name] = {
        "bool": True,
        "string": str(exact_value),
        "float": float(exact_value),
    }[invalid_kind]

    with pytest.raises(ValidationError):
        CompilerLimits.model_validate(canonical)


@pytest.mark.parametrize(
    "field_name",
    ["equality_count", "inequality_count", "unknown_count", "structural_rank"],
)
@pytest.mark.parametrize("invalid", [True, "0", 0.0])
def test_rank_counts_reject_coercive_integer_inputs(
    field_name: str,
    invalid: object,
) -> None:
    payload = _rank_payload()
    payload[field_name] = invalid

    with pytest.raises(ValidationError):
        RankAnalysis.model_validate(payload)


@pytest.mark.parametrize("field_name", ["underdetermined", "overdetermined", "conflicting"])
@pytest.mark.parametrize("invalid", [0, 1, "false", "true"])
def test_rank_flags_reject_non_boolean_inputs(field_name: str, invalid: object) -> None:
    payload = _rank_payload()
    payload[field_name] = invalid

    with pytest.raises(ValidationError):
        RankAnalysis.model_validate(payload)


@pytest.mark.parametrize("invalid", [0, "false", True])
def test_physical_consistency_claim_remains_strictly_false(invalid: object) -> None:
    payload = _rank_payload()
    payload["physical_consistency_claimed"] = invalid

    with pytest.raises(ValidationError):
        RankAnalysis.model_validate(payload)


@pytest.mark.parametrize("invalid", [0, 1, "false", "true"])
def test_generated_flag_rejects_non_boolean_inputs(invalid: object) -> None:
    with pytest.raises(ValidationError):
        SymbolNode.model_validate(_symbol_node_payload(generated=invalid))


@pytest.mark.parametrize("invalid", [True, "1", 1.0])
def test_initial_condition_order_rejects_coercive_integer_inputs(invalid: object) -> None:
    with pytest.raises(ValidationError):
        InitialConditionNode.model_validate(_initial_condition_payload(invalid))


@pytest.mark.parametrize("invalid", [True, "4", 4.0])
def test_complexity_costs_reject_coercive_integer_inputs(invalid: object) -> None:
    equation_payload = {
        "equation_id": "equation1",
        "expression": {
            "op": "equality",
            "left": {"op": "literal", "value": 0},
            "right": {"op": "literal", "value": 0.0},
        },
        "expression_fingerprint": "a" * 64,
        "law_id": "law1",
        "scope": {},
        "dimension": {},
        "complexity_cost": invalid,
    }
    application_payload = {
        "application_id": "application1",
        "law_id": "law1",
        "equation_ids": ["equation1"],
        "scope": {},
        "complexity_cost": invalid,
    }

    with pytest.raises(ValidationError):
        EquationNode.model_validate(equation_payload)
    with pytest.raises(ValidationError):
        LawApplication.model_validate(application_payload)


def test_canonical_equation_graph_preserves_json_roundtrip_and_schemas() -> None:
    graph = EquationGraph.model_validate(_equation_graph_payload())

    assert EquationGraph.model_validate_json(graph.model_dump_json()) == graph
    assert InitialConditionNode.model_validate_json(
        InitialConditionNode.model_validate(_initial_condition_payload(1)).model_dump_json()
    ).derivative_order == 1
    assert SymbolNode.model_validate_json(
        SymbolNode.model_validate(_symbol_node_payload(1, generated=True)).model_dump_json()
    ).generated is True
    assert EquationGraph.model_json_schema()["type"] == "object"
    assert _MATH_EXPRESSION_ADAPTER.json_schema()["oneOf"]
