"""Standalone generated tests for Phase-56 mechanics normalization."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal
import inspect
import math

import pytest
from pydantic import BaseModel, ValidationError

import engine.mechanics.normalization as normalization_module
import engine.mechanics.units as units_module
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    IR_SCHEMA_NAME,
    IR_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
)
from engine.mechanics.errors import MechanicsIssueCode
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.normalization import (
    NORMALIZATION_POLICY_VERSION,
    VALIDATION_POLICY_VERSION,
    calculation_fingerprint,
    normalize_draft,
)
from engine.mechanics.units import (
    UnitDimensionError,
    UnitNonFiniteError,
    UnitParseError,
    normalize_quantity,
    parse_scalar,
    parse_vector,
)
from engine.mechanics.validation import (
    AssumptionAuthorization,
    CorrectionAuthorization,
    DraftValidationResult,
    ValidationTerminal,
)
from tools._pint_shim import UnitRegistry as ShimUnitRegistry


def _dimension(**values: int) -> dict[str, int]:
    return DimensionVector(**values).model_dump(mode="json")


def _draft_payload(
    *,
    raw_value: str | None = "1",
    raw_unit: str | None = "kg",
    role: str = "mass",
    dimension: dict[str, int] | None = None,
    shape: str = "scalar",
    provenance: str = "user_correction",
    subject_id: str = "e1",
    correction_id: str | None = "corr1",
    correction_revision: int = 0,
) -> dict[str, object]:
    dimension = _dimension(mass=1) if dimension is None else dimension
    output_unit = {"mass": "kg", "length": "m", "velocity": "m/s"}.get(role, raw_unit or "1")
    quantity: dict[str, object] = {
        "quantity_id": "q1",
        "symbol_id": "sym1" if shape == "vector" else None,
        "role": role,
        "subject_id": subject_id,
        "point_id": None,
        "frame_id": None,
        "interval_id": None,
        "event_id": None,
        "component": "unspecified",
        "direction": None,
        "shape": shape,
        "dimension": dimension,
        "provenance": provenance,
        "evidence_refs": [],
        "assumption_policy_ref": "assumption1" if provenance == "server_default" else None,
        "correction_id": correction_id if provenance == "user_correction" else None,
        "model_confidence": 0.8,
        "raw_value": raw_value,
        "raw_unit": raw_unit,
    }
    symbols: list[dict[str, object]] = []
    if shape == "vector":
        component_count = len(raw_value.split(",")) if raw_value is not None else 2
        symbols.append({
            "symbol_id": "sym1", "quantity_id": "q1", "dimension": dimension,
            "shape": "vector", "vector_length": component_count,
        })
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en", "correction_revision": correction_revision,
            "system_type": "diagnostic", "subtype": "generated", "model_id": "fixture",
            "model_hash": "1" * 64, "prompt_hash": "2" * 64,
            "source_text_sha256": "3" * 64, "model_confidence": 0.5,
        },
        "source_assets": [],
        "source_evidence": [],
        "entities": [{
            "entity_id": "e1", "primitive": "particle", "label": "body",
            "aliases": ["object"], "component_of_entity_id": None,
            "evidence_refs": [], "model_confidence": 0.7,
        }],
        "points": [],
        "reference_frames": [],
        "motion_intervals": [],
        "events": [],
        "symbols": symbols,
        "quantities": [quantity],
        "geometry": [],
        "interactions": [],
        "constraints": [],
        "state_conditions": [],
        "queries": [{
            "query_id": "query1",
            "target": {
                "role": role, "subject_id": subject_id, "point_id": None,
                "frame_id": None, "interval_id": None, "event_id": None,
                "component": "unspecified", "direction": None,
                "target_quantity_id": "q1",
            },
            "output_unit": output_unit, "output_dimension": dimension,
            "shape": shape, "evidence_refs": [],
        }],
        "principle_hints": [],
        "assumptions": [],
        "ambiguities": [],
        "figure_dependency": {"level": "none", "missing_information": [], "evidence_refs": []},
        "unsupported_features": [],
    }


def _draft(**options: object) -> MechanicsProblemDraftV1:
    return MechanicsProblemDraftV1.model_validate(_draft_payload(**options))


def _corrections(draft: MechanicsProblemDraftV1) -> dict[str, CorrectionAuthorization]:
    result: dict[str, CorrectionAuthorization] = {}
    for quantity in draft.quantities:
        if quantity.provenance.value != "user_correction":
            continue
        assert quantity.correction_id and quantity.raw_value is not None and quantity.raw_unit is not None
        result[quantity.correction_id] = CorrectionAuthorization(
            correction_id=quantity.correction_id,
            subject_id=quantity.subject_id,
            role=quantity.role.value,
            raw_value=quantity.raw_value,
            raw_unit=quantity.raw_unit,
            interval_id=quantity.interval_id,
            event_id=quantity.event_id,
        )
    return result


def _run(
    draft: MechanicsProblemDraftV1,
    problem_text: str = "",
    *,
    approved_assumption_ids: tuple[str, ...] = (),
    authorized_assumptions: dict[str, AssumptionAuthorization] | None = None,
):
    return normalize_draft(
        problem_text,
        draft,
        approved_assumption_ids=approved_assumption_ids,
        authorized_corrections=_corrections(draft),
        authorized_assumptions=authorized_assumptions,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("−2", Decimal("-2")),
        (".5", Decimal("0.5")),
        ("1 / 2", Decimal("0.5")),
        ("1 e +2", Decimal("100")),
        ("1E−2", Decimal("0.01")),
        ("2 × 10^3", Decimal("2000")),
        ("2 x 10 ^ +3", Decimal("2000")),
        ("2 × 10³", Decimal("2000")),
        ("2×10⁻³", Decimal("0.002")),
    ],
)
def test_scalar_parser_has_exact_phase55_positive_grammar(raw: str, expected: Decimal) -> None:
    assert parse_scalar(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["1.", "1./2", "1x10-2", "1\n/2", "1 2", "1 + 2", "nan", "inf", "1kg"],
)
def test_scalar_parser_rejects_non_phase55_or_nonfinite_text(raw: str) -> None:
    with pytest.raises(UnitParseError):
        parse_scalar(raw)


def test_scalar_parser_rejects_zero_denominator_and_float_range_loss() -> None:
    with pytest.raises(UnitParseError):
        parse_scalar(True)
    with pytest.raises(UnitParseError):
        parse_scalar("1" * 81)
    with pytest.raises(UnitParseError):
        parse_scalar("1 / 0")
    with pytest.raises(UnitNonFiniteError):
        parse_scalar("1e999")
    with pytest.raises(UnitNonFiniteError):
        parse_scalar("1e-9999999")
    with pytest.raises(UnitNonFiniteError):
        parse_scalar("1e-400")


def test_vector_parser_is_complete_comma_only_and_bounded() -> None:
    assert parse_vector("1 / 2, 1 e +2,−3") == (Decimal("0.5"), Decimal("100"), Decimal("-3"))
    for raw in ("1 2", "1,2,3,4", "1,,2", "1;2", "1,\n2"):
        with pytest.raises(UnitParseError):
            parse_vector(raw)


def test_representative_scalar_conversions_cover_mass_speed_and_dimensionless() -> None:
    assert normalize_quantity("1000", "g", "scalar", DimensionVector(mass=1)).value == 1.0
    speed = normalize_quantity("36", "km/h", "scalar", DimensionVector(length=1, time=-1))
    assert speed.value == 10.0 and speed.si_unit == "m*s^-1"
    percent = normalize_quantity("50", "%", "scalar", DimensionVector())
    assert percent.value == 0.5 and percent.si_unit == ""


@pytest.mark.parametrize(
    ("unit", "dimension", "si_unit"),
    [
        ("m·s^-1", DimensionVector(length=1, time=-1), "m*s^-1"),
        ("m*s^-1", DimensionVector(length=1, time=-1), "m*s^-1"),
        ("m·s^-2", DimensionVector(length=1, time=-2), "m*s^-2"),
        ("m*s^-2", DimensionVector(length=1, time=-2), "m*s^-2"),
        ("kg*m2", DimensionVector(mass=1, length=2), "kg*m^2"),
        ("kg·m2", DimensionVector(mass=1, length=2), "kg*m^2"),
        ("kg·m²", DimensionVector(mass=1, length=2), "kg*m^2"),
    ],
)
def test_all_authoritative_missing_aliases_are_finite(unit: str, dimension: DimensionVector, si_unit: str) -> None:
    normalized = normalize_quantity("2", unit, "scalar", dimension)
    assert normalized.value == 2.0
    assert normalized.si_unit == si_unit


def test_angles_rpm_and_frequency_keep_semantic_si_units() -> None:
    angle = normalize_quantity("180", "°", "scalar", DimensionVector())
    assert angle.si_unit == "rad" and math.isclose(angle.value, math.pi)
    rpm = normalize_quantity("60", "rpm", "scalar", DimensionVector(time=-1))
    assert rpm.si_unit == "rad/s" and math.isclose(rpm.value, 2.0 * math.pi)
    angular_acceleration = normalize_quantity("2", "rad/s^2", "scalar", DimensionVector(time=-2))
    assert angular_acceleration.si_unit == "rad/s^2"
    frequency = normalize_quantity("2", "Hz", "scalar", DimensionVector(time=-1))
    assert frequency.si_unit == "s^-1"


@pytest.mark.parametrize(
    ("unit", "dimension", "si_unit"),
    [
        ("kg", DimensionVector(mass=1), "kg"),
        ("m", DimensionVector(length=1), "m"),
        ("s", DimensionVector(time=1), "s"),
        ("A", DimensionVector(current=1), "A"),
        ("K", DimensionVector(temperature=1), "K"),
        ("mol", DimensionVector(amount=1), "mol"),
        ("cd", DimensionVector(luminous_intensity=1), "cd"),
    ],
)
def test_selected_runtime_registry_supports_all_seven_si_bases(
    unit: str, dimension: DimensionVector, si_unit: str
) -> None:
    normalized = normalize_quantity("3", unit, "scalar", dimension)
    assert normalized.value == 3.0
    assert normalized.dimension == dimension
    assert normalized.si_unit == si_unit


_DUAL_REGISTRY_CASES = (
    # All seven SI bases exercise the dimension comparison and target builder.
    ("3", "kg", DimensionVector(mass=1), 3.0, "kg"),
    ("3", "m", DimensionVector(length=1), 3.0, "m"),
    ("3", "s", DimensionVector(time=1), 3.0, "s"),
    ("3", "A", DimensionVector(current=1), 3.0, "A"),
    ("3", "K", DimensionVector(temperature=1), 3.0, "K"),
    ("3", "mol", DimensionVector(amount=1), 3.0, "mol"),
    ("3", "cd", DimensionVector(luminous_intensity=1), 3.0, "cd"),
    # Representative M/L/T aliases retained from physics_core.units.
    ("1000", "g", DimensionVector(mass=1), 1.0, "kg"),
    ("100", "cm", DimensionVector(length=1), 1.0, "m"),
    ("2", "min", DimensionVector(time=1), 120.0, "s"),
    ("36", "km/h", DimensionVector(length=1, time=-1), 10.0, "m*s^-1"),
    ("100", "cm/s^2", DimensionVector(length=1, time=-2), 1.0, "m*s^-2"),
    ("2", "N", DimensionVector(mass=1, length=1, time=-2), 2.0, "kg*m*s^-2"),
    ("2", "J", DimensionVector(mass=1, length=2, time=-2), 2.0, "kg*m^2*s^-2"),
    ("2", "N/m", DimensionVector(mass=1, time=-2), 2.0, "kg*s^-2"),
    ("2", "kg*m^2", DimensionVector(mass=1, length=2), 2.0, "kg*m^2"),
)


def _assert_registry_backend(monkeypatch: pytest.MonkeyPatch, registry: object) -> None:
    monkeypatch.setattr(units_module, "_UREG", registry)
    for raw, unit, dimension, expected_value, expected_unit in _DUAL_REGISTRY_CASES:
        normalized = units_module.normalize_quantity(raw, unit, "scalar", dimension)
        assert math.isclose(normalized.value, expected_value)
        assert normalized.dimension == dimension
        assert normalized.si_unit == expected_unit


def test_explicit_pint_shim_registry_covers_seven_bases_and_legacy_mlt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_registry_backend(monkeypatch, ShimUnitRegistry())


def test_explicit_real_pint_registry_covers_seven_bases_and_legacy_mlt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        import pint
    except ModuleNotFoundError as exc:
        if exc.name != "pint":
            raise
        pytest.skip("the real-Pint half of the dual-backend contract requires Pint")
    _assert_registry_backend(monkeypatch, pint.UnitRegistry())


def test_whitelist_dimension_and_tensor_rejections_are_typed() -> None:
    with pytest.raises(UnitParseError):
        normalize_quantity("1", "m;__import__('os')", "scalar", DimensionVector(length=1))
    with pytest.raises(UnitDimensionError):
        normalize_quantity("1", "kg", "scalar", DimensionVector(length=1))
    with pytest.raises(UnitParseError):
        normalize_quantity("1", "m", "tensor", DimensionVector(length=1))
    with pytest.raises(UnitParseError):
        normalize_quantity("1", "m" * 49, "scalar", DimensionVector(length=1))


def test_normalize_draft_accepts_scalar_stamps_policies_preserves_input_and_freezes_quantity() -> None:
    draft = _draft()
    before = draft.model_dump(mode="python")
    result = _run(draft)
    assert result.accepted and result.terminal is ValidationTerminal.accepted
    assert result.ir is not None and result.calculation_fingerprint is not None
    assert result.ir.schema == IR_SCHEMA_NAME and result.ir.version == IR_SCHEMA_VERSION
    assert result.ir.validation_policy_version == "mechanics-validation-v1" == VALIDATION_POLICY_VERSION
    assert result.ir.normalization_policy_version == NORMALIZATION_POLICY_VERSION
    assert result.ir.quantities[0].si_value == 1.0 and result.ir.quantities[0].si_unit == "kg"
    assert draft.model_dump(mode="python") == before
    with pytest.raises((ValidationError, FrozenInstanceError, TypeError)):
        result.ir.quantities[0].si_value = 2.0


def _assert_reachable_ir_is_immutable(value: object, path: str = "ir") -> None:
    if isinstance(value, BaseModel):
        assert value.model_config.get("frozen") is True, path
        for field_name in type(value).model_fields:
            _assert_reachable_ir_is_immutable(
                getattr(value, field_name), f"{path}.{field_name}"
            )
        return
    if isinstance(value, tuple):
        for index, item in enumerate(value):
            _assert_reachable_ir_is_immutable(item, f"{path}.{index}")
        return
    assert not isinstance(value, (list, dict, set)), path


def test_accepted_ir_is_recursively_immutable_and_fingerprint_cannot_become_stale() -> None:
    draft = _draft()
    result = _run(draft)
    assert result.accepted and result.ir is not None
    assert result.calculation_fingerprint is not None
    ir = result.ir
    original_fingerprint = result.calculation_fingerprint

    _assert_reachable_ir_is_immutable(ir)
    assert isinstance(ir.entities, tuple)
    assert isinstance(ir.entities[0].aliases, tuple)
    assert isinstance(ir.queries, tuple)
    assert isinstance(ir.quantities[0].evidence_refs, tuple)

    with pytest.raises(AttributeError):
        ir.quantities.clear()  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        ir.entities[0].aliases.append("mutated")  # type: ignore[attr-defined]
    with pytest.raises(ValidationError, match="frozen"):
        ir.queries[0].output_unit = "s"
    with pytest.raises(ValidationError, match="frozen"):
        ir.queries[0].target.subject_id = "other"
    with pytest.raises(ValidationError, match="frozen"):
        ir.metadata.correction_revision = 99
    with pytest.raises(ValidationError, match="frozen"):
        ir.quantities[0].evidence_refs += ("evidence1",)

    assert calculation_fingerprint(ir) == original_fingerprint
    assert result.calculation_fingerprint == original_fingerprint

    # Accepted-IR immutability does not turn DraftV1 into a frozen authoring API.
    draft.entities[0].aliases.append("new-authoring-alias")
    draft.queries[0].output_unit = "g"
    assert draft.entities[0].aliases[-1] == "new-authoring-alias"
    assert draft.queries[0].output_unit == "g"


def test_normalize_draft_accepts_vector_and_rawless_symbolic_quantity() -> None:
    vector = _draft(
        raw_value="1,2", raw_unit="m*s^-1", role="velocity",
        dimension=_dimension(length=1, time=-1), shape="vector",
    )
    vector_result = _run(vector)
    assert vector_result.accepted and vector_result.ir.quantities[0].si_value == (1.0, 2.0)

    vector_3d = _draft(
        raw_value="1, 2, 3", raw_unit="m*s^-1", role="velocity",
        dimension=_dimension(length=1, time=-1), shape="vector",
    )
    vector_3d_result = _run(vector_3d)
    assert vector_3d_result.accepted
    assert vector_3d_result.ir.quantities[0].si_value == (1.0, 2.0, 3.0)

    symbolic = _draft(raw_value=None, raw_unit=None, provenance="inferred", correction_id=None)
    symbolic_result = _run(symbolic)
    assert symbolic_result.accepted
    assert symbolic_result.ir.quantities[0].si_value is None
    assert symbolic_result.ir.quantities[0].si_unit is None


def test_trusted_arguments_forward_by_identity_and_defaults_are_not_mutable(monkeypatch: pytest.MonkeyPatch) -> None:
    draft = _draft()
    approved = ("assumption1",)
    corrections: dict[str, CorrectionAuthorization] = {}
    assumptions: dict[str, AssumptionAuthorization] = {}
    figures = ("figure1",)
    captured: dict[str, object] = {}

    def fake_validate(problem_text: str, supplied_draft: object, **kwargs: object) -> DraftValidationResult:
        captured.update({"problem_text": problem_text, "draft": supplied_draft, **kwargs})
        return DraftValidationResult(ValidationTerminal.invalid, ())

    monkeypatch.setattr(normalization_module, "validate_draft", fake_validate)
    result = normalize_draft(
        "trusted", draft, approved_assumption_ids=approved,
        authorized_corrections=corrections, authorized_assumptions=assumptions,
        confirmed_figure_evidence_ids=figures,
    )
    assert result.ir is None and result.calculation_fingerprint is None
    assert captured["problem_text"] == "trusted" and captured["draft"] is draft
    assert captured["approved_assumption_ids"] is approved
    assert captured["authorized_corrections"] is corrections
    assert captured["authorized_assumptions"] is assumptions
    assert captured["confirmed_figure_evidence_ids"] is figures
    for parameter in inspect.signature(normalize_draft).parameters.values():
        assert not isinstance(parameter.default, (dict, list, set))


@pytest.mark.parametrize(
    "terminal_case",
    ["invalid", "needs_confirmation", "needs_figure", "unsupported", "insufficient_information"],
)
def test_every_nonaccepted_validation_terminal_has_no_ir_or_fingerprint(terminal_case: str) -> None:
    payload = _draft_payload()
    if terminal_case == "invalid":
        payload["queries"][0]["target"]["subject_id"] = "missing"
    elif terminal_case == "needs_confirmation":
        payload["ambiguities"] = [{
            "ambiguity_id": "ambiguity1", "kind": "interpretation",
            "referenced_ids": ["e1"], "description": "generated ambiguity",
            "blocking": True, "evidence_refs": [],
        }]
    elif terminal_case == "needs_figure":
        payload["figure_dependency"] = {
            "level": "required", "missing_information": ["generated figure fact"], "evidence_refs": [],
        }
    elif terminal_case == "unsupported":
        payload["unsupported_features"] = [{
            "feature_code": "feature1", "description": "generated unsupported feature",
            "referenced_ids": ["e1"], "evidence_refs": [],
        }]
    else:
        payload["queries"] = []
    result = _run(MechanicsProblemDraftV1.model_validate(payload))
    assert result.terminal.value == terminal_case
    assert result.ir is None and result.calculation_fingerprint is None


def _assert_atomic_failure(result: object, code: MechanicsIssueCode, forbidden_raw: str | None = None) -> None:
    assert result.terminal is ValidationTerminal.invalid
    assert result.ir is None and result.calculation_fingerprint is None
    assert result.issues[-1].code is code
    if forbidden_raw is not None:
        assert forbidden_raw not in result.issues[-1].message


def test_unit_parse_dimension_nonfinite_and_model_failures_are_atomic(monkeypatch: pytest.MonkeyPatch) -> None:
    unsafe_payload = _draft_payload(raw_unit="unsafe-unit")
    unsafe = MechanicsProblemDraftV1.model_validate(unsafe_payload)
    monkeypatch.setattr(
        normalization_module, "validate_draft",
        lambda *args, **kwargs: DraftValidationResult(ValidationTerminal.accepted, ()),
    )
    parsed = normalize_draft("", unsafe)
    _assert_atomic_failure(parsed, MechanicsIssueCode.unit_parse_error, "unsafe-unit")
    assert parsed.issues[-1].path == "quantities.0" and parsed.issues[-1].referenced_id == "q1"
    monkeypatch.undo()

    mismatch = _draft(role="length", dimension=_dimension(length=1), raw_unit="kg")
    dimension_result = _run(mismatch)
    _assert_atomic_failure(dimension_result, MechanicsIssueCode.unit_dimension_mismatch, "kg")
    assert dimension_result.issues[-1].path == "quantities.0"

    overflow = _draft(raw_value="1e999")
    nonfinite_result = _run(overflow)
    _assert_atomic_failure(nonfinite_result, MechanicsIssueCode.non_finite_value, "1e999")

    valid = _draft()
    monkeypatch.setattr(normalization_module, "MechanicsProblemIRV1", lambda **kwargs: (_ for _ in ()).throw(ValueError("boom")))
    model_result = _run(valid)
    _assert_atomic_failure(model_result, MechanicsIssueCode.schema_error)
    assert model_result.issues[-1].path == "normalization"


def _accepted_fingerprint(draft: MechanicsProblemDraftV1, problem_text: str = "", **kwargs: object) -> tuple[str, object]:
    result = _run(draft, problem_text, **kwargs)
    assert result.accepted and result.ir is not None and result.calculation_fingerprint is not None
    assert calculation_fingerprint(result.ir) == result.calculation_fingerprint
    return result.calculation_fingerprint, result


def test_fingerprint_changes_for_si_value_binding_and_provenance() -> None:
    one, _ = _accepted_fingerprint(_draft(raw_value="1"))
    two, _ = _accepted_fingerprint(_draft(raw_value="2"))
    assert one != two

    bound_payload = _draft_payload()
    bound_payload["entities"].append({
        "entity_id": "e2", "primitive": "particle", "label": None, "aliases": [],
        "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None,
    })
    rebound_payload = deepcopy(bound_payload)
    rebound_payload["quantities"][0]["subject_id"] = "e2"
    rebound_payload["queries"][0]["target"]["subject_id"] = "e2"
    bound, _ = _accepted_fingerprint(MechanicsProblemDraftV1.model_validate(bound_payload))
    rebound, _ = _accepted_fingerprint(MechanicsProblemDraftV1.model_validate(rebound_payload))
    assert bound != rebound

    inferred, _ = _accepted_fingerprint(_draft(raw_value=None, raw_unit=None, provenance="inferred", correction_id=None))
    unknown, _ = _accepted_fingerprint(_draft(raw_value=None, raw_unit=None, provenance="unknown", correction_id=None))
    assert inferred != unknown


def test_fingerprint_ignores_unreferenced_top_level_assumption_variations() -> None:
    payload = _draft_payload()
    payload["assumptions"] = [{
        "assumption_id": "diagnostic1", "kind": "generated_diagnostic",
        "subject_id": "e1", "interval_id": None, "disposition": "rejected",
        "proposed_role": "mass", "proposed_value": "9", "proposed_unit": "kg",
        "reason": "generated diagnostic only", "evidence_refs": [],
    }]
    baseline, result = _accepted_fingerprint(
        MechanicsProblemDraftV1.model_validate(payload)
    )
    assert result.ir is not None
    ir = result.ir
    diagnostic = ir.assumptions[0]

    renamed = diagnostic.model_copy(update={"assumption_id": "diagnostic2"})
    rekinded = diagnostic.model_copy(update={"kind": "other_diagnostic"})
    added = diagnostic.model_copy(update={"assumption_id": "diagnostic3"})
    variants = (
        ir.model_copy(update={"assumptions": ()}),
        ir.model_copy(update={"assumptions": (renamed,)}),
        ir.model_copy(update={"assumptions": (rekinded,)}),
        ir.model_copy(update={"assumptions": (diagnostic, added)}),
    )
    assert all(calculation_fingerprint(variant) == baseline for variant in variants)


def test_server_default_assumption_identity_and_provenance_are_retained() -> None:
    def server_default(assumption_id: str) -> tuple[str, object]:
        payload = _draft_payload(provenance="server_default", correction_id=None)
        payload["quantities"][0]["assumption_policy_ref"] = assumption_id
        payload["assumptions"] = [{
            "assumption_id": assumption_id, "kind": "generated_default",
            "subject_id": "e1", "interval_id": None, "disposition": "approved",
            "proposed_role": "mass", "proposed_value": "1", "proposed_unit": "kg",
            "reason": "generated policy", "evidence_refs": [],
        }]
        authorization = AssumptionAuthorization(
            assumption_id=assumption_id, subject_id="e1", role="mass",
            raw_value="1", raw_unit="kg", interval_id=None,
        )
        return _accepted_fingerprint(
            MechanicsProblemDraftV1.model_validate(payload),
            approved_assumption_ids=(assumption_id,),
            authorized_assumptions={assumption_id: authorization},
        )

    first, first_result = server_default("assumption1")
    second, second_result = server_default("assumption2")
    assert first != second
    assert first_result.ir.quantities[0].assumption_policy_ref == "assumption1"
    assert second_result.ir.quantities[0].assumption_policy_ref == "assumption2"
    assert first_result.ir.assumptions[0].assumption_id == "assumption1"
    assert second_result.ir.assumptions[0].assumption_id == "assumption2"

    # Top-level assumption records are excluded diagnostics: swapping them does
    # not change either fingerprint.  After that control, coherently relinking
    # the quantity and record reproduces the other fingerprint, so the quantity
    # reference is the calculation-authority difference.
    first_ir, second_ir = first_result.ir, second_result.ir
    assert calculation_fingerprint(
        first_ir.model_copy(update={"assumptions": second_ir.assumptions})
    ) == first
    relinked_quantity = first_ir.quantities[0].model_copy(
        update={"assumption_policy_ref": "assumption2"}
    )
    assert calculation_fingerprint(
        first_ir.model_copy(update={
            "quantities": (relinked_quantity,),
            "assumptions": second_ir.assumptions,
        })
    ) == second


def _diagnostic_draft(*, alternate: bool) -> tuple[str, MechanicsProblemDraftV1]:
    text = "alternate diagnostic" if alternate else "generated diagnostic"
    payload = _draft_payload(correction_revision=9 if alternate else 1)
    payload["metadata"].update({
        "system_type": "other" if alternate else "diagnostic",
        "subtype": "alternate" if alternate else "generated",
        "model_id": "alternate" if alternate else "fixture",
        "model_hash": ("a" if alternate else "1") * 64,
        "prompt_hash": ("b" if alternate else "2") * 64,
        "source_text_sha256": ("c" if alternate else "3") * 64,
        "model_confidence": 0.1 if alternate else 0.9,
    })
    payload["entities"][0]["label"] = "alternate label" if alternate else "generated label"
    payload["entities"][0]["aliases"] = ["alternate alias"] if alternate else ["generated alias"]
    payload["source_assets"] = [{
        "asset_id": "asset1", "kind": "image",
        "content_sha256": ("d" if alternate else "4") * 64,
        "media_type": "image/jpeg" if alternate else "image/png",
        "page_id": None, "page_number": None, "parent_asset_id": None,
    }]
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "evidence1", "quote": text,
        "source_span": {"start": 0, "end": len(text)}, "quantity_span": None,
        "occurrence_index": 0,
    }]
    payload["assumptions"] = [{
        "assumption_id": "diagnostic_assumption", "kind": "generated_diagnostic",
        "subject_id": "e1", "interval_id": None, "disposition": "rejected",
        "proposed_role": "mass", "proposed_value": "9" if alternate else "8",
        "proposed_unit": "g" if alternate else "kg",
        "reason": "alternate reason" if alternate else "generated reason", "evidence_refs": [],
    }]
    payload["principle_hints"] = [] if alternate else [{
        "hint_id": "hint1", "principle": "newton_second_law", "scope_ids": ["e1"],
        "evidence_refs": [], "model_confidence": 0.2,
    }]
    payload["figure_dependency"] = {
        "level": "helpful" if alternate else "none",
        "missing_information": ["alternate figure diagnostic"] if alternate else [],
        "evidence_refs": [],
    }
    return text, MechanicsProblemDraftV1.model_validate(payload)


def test_fingerprint_ignores_diagnostics_revision_raw_representation_and_evidence() -> None:
    text_a, draft_a = _diagnostic_draft(alternate=False)
    text_b, draft_b = _diagnostic_draft(alternate=True)
    first, first_result = _accepted_fingerprint(draft_a, text_a)
    second, second_result = _accepted_fingerprint(draft_b, text_b)
    assert first == second
    assert first_result.correction_revision == 1
    assert second_result.correction_revision == 9

    kilograms, _ = _accepted_fingerprint(_draft(raw_value="1", raw_unit="kg"))
    grams, _ = _accepted_fingerprint(_draft(raw_value="1000", raw_unit="g"))
    assert kilograms == grams


def test_fingerprint_is_top_level_and_set_like_order_invariant() -> None:
    payload = _draft_payload()
    payload["entities"].append({
        "entity_id": "e2", "primitive": "particle", "label": "second", "aliases": [],
        "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None,
    })
    payload["interactions"] = [
        {"interaction_id": "i1", "kind": "contact", "participant_ids": ["e1", "e2"], "point_ids": [], "frame_id": None, "interval_id": None, "event_id": None, "quantity_ids": [], "evidence_refs": []},
        {"interaction_id": "i2", "kind": "gravity", "participant_ids": ["e1"], "point_ids": [], "frame_id": None, "interval_id": None, "event_id": None, "quantity_ids": ["q1"], "evidence_refs": []},
    ]
    reordered = deepcopy(payload)
    reordered["entities"].reverse()
    reordered["interactions"].reverse()
    reordered["interactions"][1]["participant_ids"].reverse()
    first, _ = _accepted_fingerprint(MechanicsProblemDraftV1.model_validate(payload))
    second, _ = _accepted_fingerprint(MechanicsProblemDraftV1.model_validate(reordered))
    assert first == second


def test_fingerprint_preserves_vector_component_and_frame_axis_order() -> None:
    vector_a = _draft(
        raw_value="1,2", raw_unit="m/s", role="velocity",
        dimension=_dimension(length=1, time=-1), shape="vector",
    )
    vector_b = _draft(
        raw_value="2,1", raw_unit="m/s", role="velocity",
        dimension=_dimension(length=1, time=-1), shape="vector",
    )
    assert _accepted_fingerprint(vector_a)[0] != _accepted_fingerprint(vector_b)[0]

    payload = _draft_payload()
    payload["reference_frames"] = [{
        "frame_id": "frame1", "frame_type": "cartesian_2d", "origin": {"kind": "world"},
        "axes": [
            {"axis": "x", "direction": {"kind": "axis", "frame_id": "frame1", "axis": "x", "sign": 1}},
            {"axis": "y", "direction": {"kind": "axis", "frame_id": "frame1", "axis": "y", "sign": 1}},
        ],
        "parent_frame_id": None, "translating_with_entity_id": None,
        "rotating_about_point_id": None, "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }]
    swapped = deepcopy(payload)
    swapped["reference_frames"][0]["axes"].reverse()
    assert _accepted_fingerprint(MechanicsProblemDraftV1.model_validate(payload))[0] != _accepted_fingerprint(MechanicsProblemDraftV1.model_validate(swapped))[0]
