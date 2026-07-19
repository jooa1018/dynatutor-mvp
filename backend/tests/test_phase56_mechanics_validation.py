from __future__ import annotations

from copy import deepcopy

import pytest

import engine.mechanics.validation as validation_module
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
)
from engine.mechanics.errors import MechanicsIssueCode
from engine.mechanics.validation import (
    AssumptionAuthorization,
    CorrectionAuthorization,
    ValidationTerminal,
    validate_draft,
)


_HASH = "0" * 64
_SOURCE_TEXT = "The mass is 2 kg."


def _payload() -> dict[str, object]:
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {"language": "en", "correction_revision": 0},
        "source_assets": [],
        "source_evidence": [],
        "entities": [
            {
                "entity_id": "body",
                "primitive": "particle",
                "label": "body",
                "aliases": [],
                "evidence_refs": [],
            }
        ],
        "points": [],
        "reference_frames": [],
        "motion_intervals": [],
        "events": [],
        "symbols": [],
        "quantities": [],
        "geometry": [],
        "interactions": [],
        "constraints": [],
        "state_conditions": [],
        "queries": [_query()],
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


def _draft(payload: dict[str, object] | None = None) -> MechanicsProblemDraftV1:
    return MechanicsProblemDraftV1.model_validate(_payload() if payload is None else payload)


def _query() -> dict[str, object]:
    return {
        "query_id": "query1",
        "target": {"role": "length", "subject_id": "body"},
        "output_unit": "m",
        "output_dimension": {"length": 1},
        "shape": "scalar",
        "evidence_refs": [],
    }


def _text_evidence(
    evidence_id: str = "evidence1",
    *,
    quote: str = "2 kg",
    source_start: int = 12,
    source_end: int = 16,
    occurrence_index: int = 0,
    quantity_span: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "kind": "text",
        "evidence_id": evidence_id,
        "quote": quote,
        "source_span": {"start": source_start, "end": source_end},
        "quantity_span": quantity_span
        if quantity_span is not None
        else {"start": source_start, "end": source_end},
        "occurrence_index": occurrence_index,
    }


def _quantity(
    quantity_id: str = "quantity1",
    *,
    provenance: str = "inferred",
    raw_value: str | None = None,
    raw_unit: str | None = None,
    evidence_refs: list[str] | None = None,
    correction_id: str | None = None,
    assumption_policy_ref: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "quantity_id": quantity_id,
        "role": "mass",
        "subject_id": "body",
        "shape": "scalar",
        "dimension": {"mass": 1},
        "provenance": provenance,
        "evidence_refs": [] if evidence_refs is None else evidence_refs,
    }
    if raw_value is not None:
        payload["raw_value"] = raw_value
    if raw_unit is not None:
        payload["raw_unit"] = raw_unit
    if correction_id is not None:
        payload["correction_id"] = correction_id
    if assumption_policy_ref is not None:
        payload["assumption_policy_ref"] = assumption_policy_ref
    return payload


def _assumption(
    assumption_id: str = "assumption1", *, disposition: str = "approved"
) -> dict[str, object]:
    return {
        "assumption_id": assumption_id,
        "kind": "idealization",
        "subject_id": "body",
        "disposition": disposition,
        "reason": "The model records this assumption explicitly.",
        "evidence_refs": [],
    }


def _codes(result: object) -> set[MechanicsIssueCode]:
    return {issue.code for issue in result.issues}  # type: ignore[union-attr]


def _explicit_result(
    problem_text: str,
    raw_value: str,
    raw_unit: str,
    *,
    quantity_text: str | None = None,
) -> object:
    selected = problem_text if quantity_text is None else quantity_text
    start = problem_text.index(selected)
    payload = _payload()
    payload["source_evidence"] = [
        _text_evidence(
            quote=problem_text,
            source_start=0,
            source_end=len(problem_text),
            quantity_span={"start": start, "end": start + len(selected)},
        )
    ]
    payload["quantities"] = [
        _quantity(
            provenance="explicit_source",
            raw_value=raw_value,
            raw_unit=raw_unit,
            evidence_refs=["evidence1"],
        )
    ]
    return validate_draft(problem_text, _draft(payload))


def _figure_payload(*, confidence: float = 0.0) -> dict[str, object]:
    payload = _payload()
    payload["source_assets"] = [
        {
            "asset_id": "page1",
            "kind": "page",
            "content_sha256": _HASH,
            "media_type": "application/pdf",
        },
        {
            "asset_id": "figure1",
            "kind": "image",
            "content_sha256": _HASH,
            "media_type": "image/png",
            "parent_asset_id": "page1",
        },
    ]
    payload["source_evidence"] = [
        {
            "kind": "figure",
            "evidence_id": "figure_evidence",
            "asset_id": "figure1",
            "page_id": "page1",
            "region": {
                "bbox": {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
            },
            "recognized_label": "2 kg",
            "confidence": confidence,
        }
    ]
    payload["quantities"] = [
        _quantity(
            provenance="explicit_source",
            raw_value="2",
            raw_unit="kg",
            evidence_refs=["figure_evidence"],
        )
    ]
    return payload


def test_minimal_well_bound_draft_is_accepted_and_system_type_is_non_authoritative() -> None:
    draft = _draft()
    result = validate_draft(_SOURCE_TEXT, draft)

    assert result.terminal is ValidationTerminal.accepted
    assert result.accepted is True
    assert result.blocked is False

    changed = draft.model_copy(
        update={"metadata": draft.metadata.model_copy(update={"system_type": "case_label"})}
    )
    assert validate_draft(_SOURCE_TEXT, changed) == result


@pytest.mark.parametrize(
    ("collection", "item"),
    [
        (
            "source_assets",
            {
                "asset_id": "asset1",
                "kind": "document",
                "content_sha256": _HASH,
                "media_type": "application/pdf",
            },
        ),
        ("source_evidence", _text_evidence()),
        (
            "entities",
            {
                "entity_id": "entity1",
                "primitive": "particle",
                "evidence_refs": [],
            },
        ),
        ("points", {"point_id": "point1", "role": "geometric", "evidence_refs": []}),
        (
            "reference_frames",
            {
                "frame_id": "frame1",
                "frame_type": "cartesian_1d",
                "origin": {"kind": "world"},
                "axes": [
                    {
                        "axis": "x",
                        "direction": {"kind": "semantic", "direction": "positive"},
                    }
                ],
                "evidence_refs": [],
            },
        ),
        (
            "motion_intervals",
            {"interval_id": "interval1", "order": 1, "subject_ids": ["body"], "evidence_refs": []},
        ),
        ("events", {"event_id": "event1", "kind": "start", "evidence_refs": []}),
        ("symbols", {"symbol_id": "symbol1", "dimension": {}}),
        ("quantities", _quantity()),
        (
            "geometry",
            {
                "relation_id": "geometry1",
                "kind": "distance",
                "participant_ids": ["body"],
                "evidence_refs": [],
            },
        ),
        (
            "interactions",
            {
                "interaction_id": "interaction1",
                "kind": "contact",
                "participant_ids": ["body"],
                "evidence_refs": [],
            },
        ),
        (
            "constraints",
            {
                "constraint_id": "constraint1",
                "kind": "kinematic",
                "expression": {
                    "op": "equality",
                    "left": {"op": "literal", "value": 1.0},
                    "right": {"op": "literal", "value": 1.0},
                },
                "evidence_refs": [],
            },
        ),
        (
            "state_conditions",
            {
                "state_condition_id": "state1",
                "kind": "initial",
                "state": "active",
                "subject_id": "body",
                "evidence_refs": [],
            },
        ),
        ("queries", _query()),
        (
            "principle_hints",
            {"hint_id": "hint1", "principle": "kinematics", "evidence_refs": []},
        ),
        ("assumptions", _assumption()),
        (
            "ambiguities",
            {
                "ambiguity_id": "ambiguity1",
                "kind": "other",
                "description": "A modelling choice remains visible.",
                "blocking": False,
                "evidence_refs": [],
            },
        ),
        (
            "unsupported_features",
            {
                "feature_code": "feature1",
                "description": "This is a separately recorded unsupported feature.",
                "evidence_refs": [],
            },
        ),
    ],
    ids=(
        "asset",
        "evidence",
        "entity",
        "point",
        "frame",
        "interval",
        "event",
        "symbol",
        "quantity",
        "geometry",
        "interaction",
        "constraint",
        "state",
        "query",
        "hint",
        "assumption",
        "ambiguity",
        "unsupported",
    ),
)
def test_duplicate_ids_are_rejected_in_every_namespace(
    collection: str, item: dict[str, object]
) -> None:
    payload = _payload()
    payload[collection] = [deepcopy(item), deepcopy(item)]

    result = validate_draft(_SOURCE_TEXT, _draft(payload))

    assert result.terminal is ValidationTerminal.invalid
    assert MechanicsIssueCode.duplicate_id in _codes(result)


@pytest.mark.parametrize(
    "category",
    [
        "asset",
        "evidence",
        "entity",
        "point",
        "frame",
        "interval",
        "event",
        "symbol",
        "quantity",
        "geometry",
        "interaction",
        "constraint",
        "state",
        "query",
        "hint",
        "assumption",
        "ambiguity",
        "unsupported",
    ],
)
def test_graph_reference_closure_covers_every_graph_category(category: str) -> None:
    payload = _payload()
    if category == "asset":
        payload["source_assets"] = [
            {
                "asset_id": "asset1",
                "kind": "document",
                "content_sha256": _HASH,
                "media_type": "application/pdf",
                "parent_asset_id": "missing",
            }
        ]
    elif category == "evidence":
        payload["source_evidence"] = [
            {
                "kind": "figure",
                "evidence_id": "evidence1",
                "asset_id": "missing",
                "region": {"bbox": {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}},
                "confidence": 0.9,
            }
        ]
    elif category == "entity":
        payload["entities"] = [
            {
                "entity_id": "body",
                "primitive": "particle",
                "component_of_entity_id": "missing",
                "evidence_refs": [],
            }
        ]
    elif category == "point":
        payload["points"] = [
            {"point_id": "point1", "role": "geometric", "owner_entity_id": "missing", "evidence_refs": []}
        ]
    elif category == "frame":
        payload["reference_frames"] = [
            {
                "frame_id": "frame1",
                "frame_type": "cartesian_1d",
                "origin": {"kind": "world"},
                "axes": [{"axis": "x", "direction": {"kind": "axis", "frame_id": "missing", "axis": "x"}}],
                "evidence_refs": [],
            }
        ]
    elif category == "interval":
        payload["motion_intervals"] = [
            {"interval_id": "interval1", "order": 1, "subject_ids": ["body"], "start_event_id": "missing", "evidence_refs": []}
        ]
    elif category == "event":
        payload["events"] = [
            {"event_id": "event1", "kind": "start", "time_quantity_id": "missing", "evidence_refs": []}
        ]
    elif category == "symbol":
        payload["quantities"] = [_quantity() | {"symbol_id": "missing"}]
    elif category == "quantity":
        payload["symbols"] = [{"symbol_id": "symbol1", "quantity_id": "missing", "dimension": {}}]
    elif category == "geometry":
        payload["geometry"] = [
            {"relation_id": "geometry1", "kind": "distance", "participant_ids": ["missing"], "evidence_refs": []}
        ]
    elif category == "interaction":
        payload["interactions"] = [
            {"interaction_id": "interaction1", "kind": "contact", "participant_ids": ["missing"], "evidence_refs": []}
        ]
    elif category == "constraint":
        payload["constraints"] = [
            {
                "constraint_id": "constraint1",
                "kind": "kinematic",
                "subject_ids": ["missing"],
                "expression": {"op": "equality", "left": {"op": "literal", "value": 1.0}, "right": {"op": "literal", "value": 1.0}},
                "evidence_refs": [],
            }
        ]
    elif category == "state":
        payload["state_conditions"] = [
            {"state_condition_id": "state1", "kind": "initial", "state": "active", "subject_id": "missing", "evidence_refs": []}
        ]
    elif category == "query":
        payload["queries"] = [
            _query() | {"target": {"role": "length", "subject_id": "body", "target_quantity_id": "missing"}}
        ]
    elif category == "hint":
        payload["principle_hints"] = [
            {"hint_id": "hint1", "principle": "kinematics", "scope_ids": ["missing"], "evidence_refs": []}
        ]
    elif category == "assumption":
        payload["assumptions"] = [_assumption() | {"subject_id": "missing"}]
    elif category == "ambiguity":
        payload["ambiguities"] = [
            {"ambiguity_id": "ambiguity1", "kind": "other", "referenced_ids": ["missing"], "description": "A reference is unresolved.", "blocking": False, "evidence_refs": []}
        ]
    elif category == "unsupported":
        payload["unsupported_features"] = [
            {"feature_code": "feature1", "description": "A reference is unresolved in an unsupported feature.", "referenced_ids": ["missing"], "evidence_refs": []}
        ]
    else:  # pragma: no cover - keeps this parameterized test exhaustive.
        raise AssertionError(category)

    result = validate_draft(_SOURCE_TEXT, _draft(payload))

    assert result.terminal is ValidationTerminal.invalid
    assert _codes(result) & {
        MechanicsIssueCode.invalid_reference,
        MechanicsIssueCode.figure_asset_missing,
    }


@pytest.mark.parametrize(
    ("problem_text", "evidence", "expected_code"),
    [
        (
            _SOURCE_TEXT,
            _text_evidence(quote="3 kg"),
            MechanicsIssueCode.evidence_quote_missing,
        ),
        (
            _SOURCE_TEXT,
            _text_evidence(source_start=0, source_end=4),
            MechanicsIssueCode.evidence_span_mismatch,
        ),
        (
            "2 kg then 2 kg",
            _text_evidence(source_start=10, source_end=14, occurrence_index=0),
            MechanicsIssueCode.evidence_occurrence_mismatch,
        ),
        (
            _SOURCE_TEXT,
            _text_evidence(quantity_span={"start": 0, "end": 4}),
            MechanicsIssueCode.quantity_span_mismatch,
        ),
    ],
)
def test_text_evidence_quote_span_occurrence_and_quantity_span_are_exact(
    problem_text: str,
    evidence: dict[str, object],
    expected_code: MechanicsIssueCode,
) -> None:
    payload = _payload()
    payload["source_evidence"] = [evidence]

    result = validate_draft(problem_text, _draft(payload))

    assert result.terminal is ValidationTerminal.invalid
    assert expected_code in _codes(result)


def test_text_evidence_and_quantity_occurrences_cannot_be_reused() -> None:
    payload = _payload()
    payload["source_evidence"] = [_text_evidence("evidence1"), _text_evidence("evidence2")]
    evidence_reuse = validate_draft(_SOURCE_TEXT, _draft(payload))

    assert MechanicsIssueCode.quantity_occurrence_reused in _codes(evidence_reuse)

    payload = _payload()
    payload["source_evidence"] = [_text_evidence()]
    payload["quantities"] = [
        _quantity("mass1", provenance="explicit_source", raw_value="2", raw_unit="kg", evidence_refs=["evidence1"]),
        _quantity("mass2", provenance="explicit_source", raw_value="2", raw_unit="kg", evidence_refs=["evidence1"]),
    ]
    quantity_reuse = validate_draft(_SOURCE_TEXT, _draft(payload))

    assert quantity_reuse.terminal is ValidationTerminal.invalid
    assert MechanicsIssueCode.quantity_occurrence_reused in _codes(quantity_reuse)


def test_explicit_source_requires_one_matching_value_unit_evidence_pair() -> None:
    payload = _payload()
    payload["source_evidence"] = [_text_evidence()]
    payload["quantities"] = [
        _quantity(provenance="explicit_source", raw_value="2", raw_unit="kg", evidence_refs=["evidence1"])
    ]
    assert validate_draft(_SOURCE_TEXT, _draft(payload)).terminal is ValidationTerminal.accepted

    value_mismatch = deepcopy(payload)
    value_mismatch["quantities"] = [
        _quantity(provenance="explicit_source", raw_value="3", raw_unit="kg", evidence_refs=["evidence1"])
    ]
    assert MechanicsIssueCode.raw_value_mismatch in _codes(validate_draft(_SOURCE_TEXT, _draft(value_mismatch)))

    unit_mismatch = deepcopy(payload)
    unit_mismatch["quantities"] = [
        _quantity(provenance="explicit_source", raw_value="2", raw_unit="m", evidence_refs=["evidence1"])
    ]
    assert MechanicsIssueCode.raw_unit_mismatch in _codes(validate_draft(_SOURCE_TEXT, _draft(unit_mismatch)))


def test_figure_asset_page_and_recognized_label_are_checked() -> None:
    payload = _payload()
    payload["source_assets"] = [
        {"asset_id": "page1", "kind": "page", "content_sha256": _HASH, "media_type": "application/pdf"},
        {"asset_id": "page2", "kind": "page", "content_sha256": _HASH, "media_type": "application/pdf"},
        {"asset_id": "figure1", "kind": "image", "content_sha256": _HASH, "media_type": "image/png", "page_id": "page1"},
    ]
    payload["source_evidence"] = [
        {
            "kind": "figure",
            "evidence_id": "figure_evidence",
            "asset_id": "figure1",
            "page_id": "page1",
            "region": {"bbox": {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}},
            "recognized_label": "2 kg",
            "confidence": 0.9,
        }
    ]
    payload["quantities"] = [
        _quantity(provenance="explicit_source", raw_value="2", raw_unit="kg", evidence_refs=["figure_evidence"])
    ]
    unconfirmed = validate_draft(_SOURCE_TEXT, _draft(payload))
    assert unconfirmed.terminal is ValidationTerminal.needs_confirmation
    assert MechanicsIssueCode.figure_evidence_unconfirmed in _codes(unconfirmed)
    assert validate_draft(
        _SOURCE_TEXT,
        _draft(payload),
        confirmed_figure_evidence_ids={"figure_evidence"},
    ).terminal is ValidationTerminal.accepted

    label_conflict = deepcopy(payload)
    label_conflict["quantities"] = [
        _quantity(provenance="explicit_source", raw_value="3", raw_unit="kg", evidence_refs=["figure_evidence"])
    ]
    assert MechanicsIssueCode.raw_value_mismatch in _codes(validate_draft(_SOURCE_TEXT, _draft(label_conflict)))

    page_conflict = deepcopy(payload)
    page_conflict["source_evidence"] = [
        deepcopy(payload["source_evidence"][0]) | {"page_id": "page2"}  # type: ignore[index]
    ]
    assert MechanicsIssueCode.figure_page_mismatch in _codes(validate_draft(_SOURCE_TEXT, _draft(page_conflict)))

    missing_asset = deepcopy(payload)
    missing_asset["source_evidence"] = [
        deepcopy(payload["source_evidence"][0]) | {"asset_id": "missing"}  # type: ignore[index]
    ]
    assert MechanicsIssueCode.figure_asset_missing in _codes(validate_draft(_SOURCE_TEXT, _draft(missing_asset)))


@pytest.mark.parametrize(
    "kind",
    ["explicit_source", "user_correction", "server_default", "inferred", "unknown"],
)
def test_provenance_rules_fail_closed_for_every_kind(kind: str) -> None:
    payload = _payload()
    if kind == "explicit_source":
        quantity = _quantity(provenance=kind)
    elif kind == "user_correction":
        quantity = _quantity(provenance=kind, raw_value="2", raw_unit="kg")
    elif kind == "server_default":
        quantity = _quantity(
            provenance=kind,
            raw_value="2",
            raw_unit="kg",
            assumption_policy_ref="policy1",
        )
        payload["assumptions"] = [_assumption("policy1", disposition="proposed")]
    else:
        quantity = _quantity(provenance=kind, raw_value="2", raw_unit="kg")
    payload["quantities"] = [quantity]

    result = validate_draft(_SOURCE_TEXT, _draft(payload))

    assert result.terminal is ValidationTerminal.invalid
    assert MechanicsIssueCode.provenance_violation in _codes(result)


def test_server_default_requires_trusted_authorization_and_user_approval_unblocks_assumptions() -> None:
    payload = _payload()
    payload["assumptions"] = [_assumption("policy1", disposition="approved")]
    payload["quantities"] = [
        _quantity(
            provenance="server_default",
            raw_value="2",
            raw_unit="kg",
            assumption_policy_ref="policy1",
        )
    ]
    draft = _draft(payload)
    assert validate_draft(_SOURCE_TEXT, draft).terminal is ValidationTerminal.invalid
    assert validate_draft(
        _SOURCE_TEXT,
        draft,
        approved_assumption_ids={"policy1"},
        authorized_assumptions={
            "policy1": AssumptionAuthorization(
                assumption_id="policy1",
                subject_id="body",
                role="mass",
                raw_value="2",
                raw_unit="kg",
            )
        },
    ).terminal is ValidationTerminal.accepted

    payload = _payload()
    payload["assumptions"] = [_assumption("visible1", disposition="visible")]
    draft = _draft(payload)
    assert validate_draft(_SOURCE_TEXT, draft).terminal is ValidationTerminal.needs_confirmation
    assert validate_draft(_SOURCE_TEXT, draft, approved_assumption_ids={"visible1"}).terminal is ValidationTerminal.accepted


def test_all_math_expressions_use_one_aggregate_gate_and_map_ast_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload()
    deep_expression: dict[str, object] = {"op": "literal", "value": 1.0}
    for _ in range(25):
        deep_expression = {"op": "negate", "operand": deep_expression}
    payload["geometry"] = [
        {
            "relation_id": "geometry1",
            "kind": "distance",
            "participant_ids": ["body"],
            "expression": {
                "op": "equality",
                "left": {"op": "symbol", "symbol_id": "missing"},
                "right": {"op": "literal", "value": 1.0},
            },
            "evidence_refs": [],
        }
    ]
    payload["constraints"] = [
        {
            "constraint_id": "constraint1",
            "kind": "kinematic",
            "expression": {
                "op": "equality",
                "left": {"op": "literal", "value": 1.0, "dimension": {"length": 1}},
                "right": {"op": "literal", "value": 1.0},
            },
            "evidence_refs": [],
        }
    ]
    payload["state_conditions"] = [
        {
            "state_condition_id": "state1",
            "kind": "initial",
            "state": "active",
            "subject_id": "body",
            "expression": {
                "op": "equality",
                "left": deep_expression,
                "right": {"op": "literal", "value": 1.0},
            },
            "evidence_refs": [],
        }
    ]
    calls = 0
    original = validation_module.validate_math_expressions

    def counted(expressions: object, symbols: object) -> object:
        nonlocal calls
        calls += 1
        return original(expressions, symbols)  # type: ignore[arg-type]

    monkeypatch.setattr(validation_module, "validate_math_expressions", counted)
    result = validate_draft(_SOURCE_TEXT, _draft(payload))

    assert calls == 1
    assert {
        MechanicsIssueCode.ast_symbol_missing,
        MechanicsIssueCode.ast_dimension_mismatch,
        MechanicsIssueCode.ast_resource_limit,
    } <= _codes(result)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("figure", ValidationTerminal.needs_figure),
        ("unsupported", ValidationTerminal.unsupported),
        ("confirmation", ValidationTerminal.needs_confirmation),
        ("ambiguity", ValidationTerminal.needs_confirmation),
        ("insufficient", ValidationTerminal.insufficient_information),
        ("invalid_precedence", ValidationTerminal.invalid),
    ],
)
def test_terminal_precedence(case: str, expected: ValidationTerminal) -> None:
    payload = _payload()
    if case == "figure":
        payload["figure_dependency"] = {"level": "required", "missing_information": ["diagram"], "evidence_refs": []}
    elif case == "unsupported":
        payload["unsupported_features"] = [
            {"feature_code": "feature1", "description": "The modelling feature is outside this implementation.", "evidence_refs": []}
        ]
    elif case == "confirmation":
        payload["assumptions"] = [_assumption("proposed1", disposition="proposed")]
    elif case == "ambiguity":
        payload["ambiguities"] = [
            {"ambiguity_id": "ambiguity1", "kind": "other", "description": "The model needs a user choice.", "blocking": False, "evidence_refs": []}
        ]
    elif case == "insufficient":
        payload["queries"] = []
    elif case == "invalid_precedence":
        payload["figure_dependency"] = {"level": "required", "missing_information": ["diagram"], "evidence_refs": []}
        payload["entities"] = [
            {"entity_id": "body", "primitive": "particle", "evidence_refs": ["missing"]}
        ]
    else:  # pragma: no cover
        raise AssertionError(case)

    assert validate_draft(_SOURCE_TEXT, _draft(payload)).terminal is expected


def test_problem_text_paraphrase_fails_when_evidence_no_longer_matches() -> None:
    payload = _payload()
    payload["source_evidence"] = [_text_evidence()]
    payload["quantities"] = [
        _quantity(provenance="explicit_source", raw_value="2", raw_unit="kg", evidence_refs=["evidence1"])
    ]
    draft = _draft(payload)

    assert validate_draft(_SOURCE_TEXT, draft).terminal is ValidationTerminal.accepted
    paraphrased = "The object has two kilograms of mass."
    assert validate_draft(paraphrased, draft).terminal is ValidationTerminal.invalid


def test_server_default_needs_both_trusted_inputs_and_exact_binding() -> None:
    payload = _payload()
    payload["assumptions"] = [_assumption("policy1", disposition="approved")]
    payload["quantities"] = [
        _quantity(
            provenance="server_default",
            raw_value="2",
            raw_unit="kg",
            assumption_policy_ref="policy1",
        )
    ]
    draft = _draft(payload)
    authorization = AssumptionAuthorization("policy1", "body", "mass", "2", "kg")
    auth_map = {"policy1": authorization}

    assert validate_draft(_SOURCE_TEXT, draft).terminal is ValidationTerminal.invalid
    assert validate_draft(
        _SOURCE_TEXT, draft, approved_assumption_ids={"policy1"}
    ).terminal is ValidationTerminal.invalid
    assert validate_draft(
        _SOURCE_TEXT, draft, authorized_assumptions=auth_map
    ).terminal is ValidationTerminal.invalid
    assert validate_draft(
        _SOURCE_TEXT,
        draft,
        approved_assumption_ids={"policy1"},
        authorized_assumptions=auth_map,
    ).terminal is ValidationTerminal.accepted

    rejected = deepcopy(payload)
    rejected["assumptions"] = [_assumption("policy1", disposition="rejected")]
    assert validate_draft(
        _SOURCE_TEXT,
        _draft(rejected),
        approved_assumption_ids={"policy1"},
        authorized_assumptions=auth_map,
    ).terminal is ValidationTerminal.invalid

    key_mismatch = {"other": authorization}
    result = validate_draft(
        _SOURCE_TEXT,
        draft,
        approved_assumption_ids={"policy1"},
        authorized_assumptions=key_mismatch,
    )
    assert result.terminal is ValidationTerminal.invalid
    assert MechanicsIssueCode.schema_error in _codes(result)

    for changed in (
        {"subject_id": "other"},
        {"role": "length"},
        {"raw_value": "3"},
        {"raw_unit": "g"},
        {"interval_id": "interval1"},
    ):
        mismatched = AssumptionAuthorization(
            assumption_id="policy1",
            subject_id=changed.get("subject_id", "body"),
            role=changed.get("role", "mass"),
            raw_value=changed.get("raw_value", "2"),
            raw_unit=changed.get("raw_unit", "kg"),
            interval_id=changed.get("interval_id"),
        )
        assert validate_draft(
            _SOURCE_TEXT,
            draft,
            approved_assumption_ids={"policy1"},
            authorized_assumptions={"policy1": mismatched},
        ).terminal is ValidationTerminal.invalid


def test_correction_id_is_not_authority_and_full_binding_is_exact() -> None:
    payload = _payload()
    payload["quantities"] = [
        _quantity(
            provenance="user_correction",
            raw_value="2",
            raw_unit="kg",
            correction_id="correction1",
        )
    ]
    draft = _draft(payload)
    exact = CorrectionAuthorization("correction1", "body", "mass", "2", "kg")
    assert validate_draft(_SOURCE_TEXT, draft).terminal is ValidationTerminal.invalid
    assert validate_draft(
        _SOURCE_TEXT,
        draft,
        authorized_corrections={"correction1": exact},
    ).terminal is ValidationTerminal.accepted

    for changed in (
        {"correction_id": "other"},
        {"subject_id": "other"},
        {"role": "length"},
        {"raw_value": "3"},
        {"raw_unit": "g"},
        {"interval_id": "interval1"},
        {"event_id": "event1"},
    ):
        mismatched = CorrectionAuthorization(
            correction_id=changed.get("correction_id", "correction1"),
            subject_id=changed.get("subject_id", "body"),
            role=changed.get("role", "mass"),
            raw_value=changed.get("raw_value", "2"),
            raw_unit=changed.get("raw_unit", "kg"),
            interval_id=changed.get("interval_id"),
            event_id=changed.get("event_id"),
        )
        assert validate_draft(
            _SOURCE_TEXT,
            draft,
            authorized_corrections={"correction1": mismatched},
        ).terminal is ValidationTerminal.invalid


@pytest.mark.parametrize(
    ("problem_text", "raw_value", "raw_unit", "quantity_text"),
    [
        ("banana kg", "banana", "kg", "banana kg"),
        ("1 0 kg", "1 0", "kg", "1 0 kg"),
        ("10 kg", "1", "kg", "10 kg"),
        ("2 cm", "2", "m", "2 cm"),
        ("2 m/s", "2", "m", "2 m/s"),
        ("2 bananas kg", "2", "kg", "2 bananas kg"),
    ],
)
def test_scalar_raw_and_evidence_grammar_fail_closed(
    problem_text: str,
    raw_value: str,
    raw_unit: str,
    quantity_text: str,
) -> None:
    assert _explicit_result(
        problem_text, raw_value, raw_unit, quantity_text=quantity_text
    ).terminal is ValidationTerminal.invalid  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("problem_text", "raw_value", "raw_unit"),
    [
        ("2 m", "2", "m"),
        ("1 / 2 kg", "1 / 2", "kg"),
        ("1 × 10² m", "1 × 10²", "m"),
        ("3 m/s²", "3", "m/s²"),
    ],
)
def test_phase55_numeric_grammar_remains_valid(
    problem_text: str, raw_value: str, raw_unit: str
) -> None:
    assert _explicit_result(problem_text, raw_value, raw_unit).terminal is ValidationTerminal.accepted  # type: ignore[union-attr]


def test_physical_text_identity_catches_nested_records_but_allows_distinct_tokens() -> None:
    payload = _payload()
    payload["source_evidence"] = [
        _text_evidence(
            "outer",
            quote="mass 2 kg",
            source_start=0,
            source_end=9,
            quantity_span={"start": 5, "end": 9},
        ),
        _text_evidence(
            "inner",
            quote="2 kg",
            source_start=5,
            source_end=9,
            quantity_span={"start": 5, "end": 9},
        ),
    ]
    duplicate = validate_draft("mass 2 kg", _draft(payload))
    assert duplicate.terminal is ValidationTerminal.invalid
    assert MechanicsIssueCode.quantity_occurrence_reused in _codes(duplicate)

    payload = _payload()
    payload["source_evidence"] = [
        _text_evidence(
            "x_component",
            quote="1 m, 2 m",
            source_start=0,
            source_end=8,
            quantity_span={"start": 0, "end": 3},
        ),
        _text_evidence(
            "y_component",
            quote="1 m, 2 m",
            source_start=0,
            source_end=8,
            quantity_span={"start": 5, "end": 8},
        ),
    ]
    assert validate_draft("1 m, 2 m", _draft(payload)).terminal is ValidationTerminal.accepted


def test_multiple_valid_quantity_bindings_require_confirmation() -> None:
    payload = _payload()
    payload["source_evidence"] = [
        _text_evidence("first", source_start=0, source_end=4, occurrence_index=0),
        _text_evidence("second", source_start=9, source_end=13, occurrence_index=1),
    ]
    payload["quantities"] = [
        _quantity(
            provenance="explicit_source",
            raw_value="2",
            raw_unit="kg",
            evidence_refs=["first", "second"],
        )
    ]
    result = validate_draft("2 kg and 2 kg", _draft(payload))
    assert result.terminal is ValidationTerminal.needs_confirmation
    assert MechanicsIssueCode.numeric_sequence_unconfirmed in _codes(result)


def test_figure_sources_require_valid_kind_ancestry_confirmation_and_unique_region() -> None:
    valid = _figure_payload(confidence=0.0)
    assert validate_draft(_SOURCE_TEXT, _draft(valid)).terminal is ValidationTerminal.needs_confirmation
    assert validate_draft(
        _SOURCE_TEXT,
        _draft(valid),
        confirmed_figure_evidence_ids={"figure_evidence"},
    ).terminal is ValidationTerminal.accepted

    wrong_pair = deepcopy(valid)
    wrong_pair["source_evidence"][0]["recognized_label"] = "3 kg"  # type: ignore[index]
    assert validate_draft(
        _SOURCE_TEXT,
        _draft(wrong_pair),
        confirmed_figure_evidence_ids={"figure_evidence"},
    ).terminal is ValidationTerminal.invalid

    dangling = deepcopy(valid)
    dangling["source_evidence"][0]["page_id"] = "missing_page"  # type: ignore[index]
    assert validate_draft(_SOURCE_TEXT, _draft(dangling)).terminal is ValidationTerminal.invalid

    unrelated = deepcopy(valid)
    unrelated["source_assets"][1].pop("parent_asset_id")  # type: ignore[index,union-attr]
    assert validate_draft(
        _SOURCE_TEXT,
        _draft(unrelated),
        confirmed_figure_evidence_ids={"figure_evidence"},
    ).terminal is ValidationTerminal.invalid

    document = deepcopy(valid)
    document["source_assets"][1] = {  # type: ignore[index]
        "asset_id": "figure1",
        "kind": "document",
        "content_sha256": _HASH,
        "media_type": "application/pdf",
    }
    document["source_evidence"][0]["page_id"] = None  # type: ignore[index]
    result = validate_draft(_SOURCE_TEXT, _draft(document))
    assert MechanicsIssueCode.figure_asset_invalid in _codes(result)

    duplicated = deepcopy(valid)
    second = deepcopy(duplicated["source_evidence"][0])  # type: ignore[index]
    second["evidence_id"] = "figure_evidence2"
    duplicated["source_evidence"].append(second)  # type: ignore[union-attr]
    result = validate_draft(_SOURCE_TEXT, _draft(duplicated))
    assert MechanicsIssueCode.quantity_occurrence_reused in _codes(result)


def test_tensor_is_not_auto_accepted_and_vector_requires_exact_symbol_reciprocity() -> None:
    payload = _payload()
    payload["source_evidence"] = [
        _text_evidence(
            quote="1 m, 2 m",
            source_start=0,
            source_end=8,
            quantity_span={"start": 0, "end": 8},
        )
    ]
    vector = _quantity(
        provenance="explicit_source",
        raw_value="1, 2",
        raw_unit="m",
        evidence_refs=["evidence1"],
    )
    vector.update(
        {"shape": "vector", "dimension": {"length": 1}, "symbol_id": "vector_symbol"}
    )
    payload["quantities"] = [vector]
    payload["symbols"] = [
        {
            "symbol_id": "vector_symbol",
            "quantity_id": "quantity1",
            "dimension": {"length": 1},
            "shape": "vector",
            "vector_length": 2,
        }
    ]
    assert validate_draft("1 m, 2 m", _draft(payload)).terminal is ValidationTerminal.accepted

    wrong_length = deepcopy(payload)
    wrong_length["symbols"][0]["vector_length"] = 3  # type: ignore[index]
    assert validate_draft(
        "1 m, 2 m", _draft(wrong_length)
    ).terminal is ValidationTerminal.needs_confirmation

    tensor = deepcopy(payload)
    tensor["symbols"] = []
    tensor["quantities"][0]["shape"] = "tensor"  # type: ignore[index]
    tensor["quantities"][0].pop("symbol_id")  # type: ignore[index,union-attr]
    result = validate_draft("1 m, 2 m", _draft(tensor))
    assert result.terminal is ValidationTerminal.needs_confirmation
    assert MechanicsIssueCode.numeric_sequence_unconfirmed in _codes(result)


def test_post_mutation_bounds_are_revalidated_before_scanning_or_normalizing() -> None:
    payload = _payload()
    payload["source_evidence"] = [_text_evidence()]
    payload["quantities"] = [
        _quantity(
            provenance="explicit_source",
            raw_value="2",
            raw_unit="kg",
            evidence_refs=["evidence1"],
        )
    ]
    draft = _draft(payload)

    oversized_quote = draft.model_copy(
        update={
            "source_evidence": [
                draft.source_evidence[0].model_copy(update={"quote": "q" * 1001})
            ]
        }
    )
    oversized_value = draft.model_copy(
        update={
            "quantities": [
                draft.quantities[0].model_copy(update={"raw_value": "1" * 81})
            ]
        }
    )
    oversized_unit = draft.model_copy(
        update={
            "quantities": [
                draft.quantities[0].model_copy(update={"raw_unit": "m" * 49})
            ]
        }
    )
    bad_occurrence = draft.model_copy(
        update={
            "source_evidence": [
                draft.source_evidence[0].model_copy(update={"occurrence_index": 1000})
            ]
        }
    )
    for changed in (oversized_quote, oversized_value, oversized_unit, bad_occurrence):
        result = validate_draft(_SOURCE_TEXT, changed)
        assert result.terminal is ValidationTerminal.invalid
        assert MechanicsIssueCode.schema_error in _codes(result)

    assert validate_draft("x" * 200_001, _draft()).terminal is ValidationTerminal.invalid

    figure_draft = _draft(_figure_payload())
    oversized_label = figure_draft.model_copy(
        update={
            "source_evidence": [
                figure_draft.source_evidence[0].model_copy(
                    update={"recognized_label": "1" * 201}
                )
            ]
        }
    )
    result = validate_draft(_SOURCE_TEXT, oversized_label)
    assert result.terminal is ValidationTerminal.invalid
    assert MechanicsIssueCode.schema_error in _codes(result)


def test_quote_scan_budget_is_enforced() -> None:
    problem_text = "a" * 200_000
    payload = _payload()
    payload["source_evidence"] = [
        _text_evidence(
            f"evidence{index}",
            quote="a" * index,
            source_start=0,
            source_end=index,
            quantity_span=None,
        )
        | {"quantity_span": None}
        for index in range(1, 102)
    ]
    result = validate_draft(problem_text, _draft(payload))
    assert result.terminal is ValidationTerminal.invalid
    assert MechanicsIssueCode.schema_error in _codes(result)


def _authorized_raw_case(
    provenance: str,
    *,
    raw_value: str,
    shape: str = "scalar",
    vector_length: int = 2,
) -> tuple[MechanicsProblemDraftV1, dict[str, object]]:
    payload = _payload()
    correction_id = "correction1" if provenance == "user_correction" else None
    policy_id = "policy1" if provenance == "server_default" else None
    quantity = _quantity(
        provenance=provenance,
        raw_value=raw_value,
        raw_unit="m" if shape == "vector" else "kg",
        correction_id=correction_id,
        assumption_policy_ref=policy_id,
    )
    if shape == "vector":
        quantity.update(
            {
                "role": "length",
                "shape": "vector",
                "dimension": {"length": 1},
                "symbol_id": "vector_symbol",
            }
        )
        payload["symbols"] = [
            {
                "symbol_id": "vector_symbol",
                "quantity_id": "quantity1",
                "dimension": {"length": 1},
                "shape": "vector",
                "vector_length": vector_length,
            }
        ]
    elif shape == "tensor":
        quantity["shape"] = "tensor"
    payload["quantities"] = [quantity]

    role = "length" if shape == "vector" else "mass"
    raw_unit = "m" if shape == "vector" else "kg"
    if provenance == "user_correction":
        options: dict[str, object] = {
            "authorized_corrections": {
                "correction1": CorrectionAuthorization(
                    "correction1", "body", role, raw_value, raw_unit
                )
            }
        }
    else:
        payload["assumptions"] = [_assumption("policy1", disposition="approved")]
        options = {
            "approved_assumption_ids": {"policy1"},
            "authorized_assumptions": {
                "policy1": AssumptionAuthorization(
                    "policy1", "body", role, raw_value, raw_unit
                )
            },
        }
    return _draft(payload), options


def test_model_marked_approved_assumption_still_needs_external_approval() -> None:
    payload = _payload()
    payload["assumptions"] = [_assumption("policy1", disposition="approved")]
    draft = _draft(payload)

    result = validate_draft(_SOURCE_TEXT, draft)
    assert result.terminal is ValidationTerminal.needs_confirmation
    assert MechanicsIssueCode.assumption_not_approved in _codes(result)
    assert validate_draft(
        _SOURCE_TEXT,
        draft,
        approved_assumption_ids={"policy1"},
    ).terminal is ValidationTerminal.accepted


@pytest.mark.parametrize("provenance", ["user_correction", "server_default"])
@pytest.mark.parametrize("raw_value", ["banana", "1 0"])
def test_exact_authorization_cannot_bypass_malformed_scalar_grammar(
    provenance: str,
    raw_value: str,
) -> None:
    draft, options = _authorized_raw_case(
        provenance,
        raw_value=raw_value,
    )
    result = validate_draft(_SOURCE_TEXT, draft, **options)
    assert result.terminal is ValidationTerminal.invalid
    assert MechanicsIssueCode.provenance_violation in _codes(result)


@pytest.mark.parametrize("provenance", ["user_correction", "server_default"])
def test_trusted_vector_correction_and_default_accept_only_safe_sequence(
    provenance: str,
) -> None:
    draft, options = _authorized_raw_case(
        provenance,
        raw_value="1, 2",
        shape="vector",
    )
    assert validate_draft(
        _SOURCE_TEXT,
        draft,
        **options,
    ).terminal is ValidationTerminal.accepted


@pytest.mark.parametrize("provenance", ["user_correction", "server_default"])
@pytest.mark.parametrize(
    "raw_value",
    ["banana", "1 2", "prefix 1, 2", "1, 2 suffix", "1, 2, 3"],
)
def test_vector_authority_rejects_unsafe_sequence_and_component_mismatch(
    provenance: str,
    raw_value: str,
) -> None:
    draft, options = _authorized_raw_case(
        provenance,
        raw_value=raw_value,
        shape="vector",
    )
    result = validate_draft(_SOURCE_TEXT, draft, **options)
    assert result.terminal is not ValidationTerminal.accepted
    assert MechanicsIssueCode.numeric_sequence_unconfirmed in _codes(result)


@pytest.mark.parametrize("provenance", ["user_correction", "server_default"])
def test_tensor_authorization_remains_confirmation_only(
    provenance: str,
) -> None:
    draft, options = _authorized_raw_case(
        provenance,
        raw_value="banana",
        shape="tensor",
    )
    result = validate_draft(_SOURCE_TEXT, draft, **options)
    assert result.terminal is ValidationTerminal.needs_confirmation
    assert MechanicsIssueCode.numeric_sequence_unconfirmed in _codes(result)
