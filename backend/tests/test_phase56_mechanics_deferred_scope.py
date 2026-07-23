from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib

import pytest
from pydantic import ValidationError

import engine.mechanics.runtime.orchestrator as runtime_module
from engine.mechanics.compiler import (
    COURSE_SCOPE_DEFERRED_ISSUE_CODES,
    CompilerIssue,
    CompilerIssueCode,
    CompilerIssueSeverity,
    CompilerResult,
    CompilerStatus,
    has_course_scope_deferred_issue,
)
from engine.mechanics.contracts import MechanicsProblemIRV1
from engine.mechanics.modeler import ModelerTerminal
from engine.mechanics.modeler_config import MechanicsIRMode
from engine.mechanics.normalization import NormalizationResult, calculation_fingerprint
from engine.mechanics.runtime import (
    MechanicsRuntimeExecution,
    MechanicsRuntimeOrchestrator,
    MechanicsRuntimeSummary,
    RuntimeDelivery,
    RuntimeFailure,
    RuntimeTerminal,
)
from engine.mechanics.runtime.contracts import compiler_result_is_coherent
from engine.mechanics.validation import DraftValidationResult, ValidationTerminal
from test_phase56_mechanics_compiler import (
    ACCELERATION,
    FREQUENCY,
    LENGTH,
    MASS,
    STIFFNESS,
    TIME,
    VELOCITY,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
    _vibration_payload,
    compile_mechanics_ir,
)
from test_phase56_mechanics_runtime import (
    PROBLEM,
    _ModelerSpy,
    _accepted_outcome,
    _config,
    _graph,
)


EXPECTED_DEFERRED_CODES = frozenset(
    {
        CompilerIssueCode.free_linear_vibration_readout_deferred,
        CompilerIssueCode.translating_frame_relative_acceleration_deferred,
        CompilerIssueCode.rotating_frame_relative_acceleration_deferred,
        CompilerIssueCode.slot_pin_relative_motion_deferred,
    }
)


def _entity(entity_id: str, primitive: str, label: str | None = None) -> dict[str, object]:
    return {
        "entity_id": entity_id,
        "primitive": primitive,
        "label": label,
        "aliases": [],
        "component_of_entity_id": None,
        "evidence_refs": [],
        "model_confidence": None,
    }


def _point(point_id: str, owner_entity_id: str) -> dict[str, object]:
    return {
        "point_id": point_id,
        "role": "material",
        "owner_entity_id": owner_entity_id,
        "frame_id": None,
        "label": None,
        "evidence_refs": [],
    }


def _frame(
    frame_id: str,
    frame_type: str,
    axes: tuple[str, ...],
    *,
    origin: dict[str, object] | None = None,
    parent_frame_id: str | None = None,
    translating_with_entity_id: str | None = None,
    rotating_about_point_id: str | None = None,
) -> dict[str, object]:
    return {
        "frame_id": frame_id,
        "frame_type": frame_type,
        "origin": origin or {"kind": "world"},
        "axes": [
            {
                "axis": axis,
                "direction": {
                    "kind": "axis",
                    "frame_id": frame_id,
                    "axis": axis,
                    "sign": 1,
                },
            }
            for axis in axes
        ],
        "parent_frame_id": parent_frame_id,
        "translating_with_entity_id": translating_with_entity_id,
        "rotating_about_point_id": rotating_about_point_id,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }


def _interval(
    subject_ids: tuple[str, ...],
    frame_id: str | None,
) -> dict[str, object]:
    return {
        "interval_id": "motionInterval",
        "order": 1,
        "subject_ids": list(subject_ids),
        "frame_id": frame_id,
        "start_event_id": None,
        "end_event_id": None,
        "evidence_refs": [],
    }


def _query(
    *,
    role: str,
    subject_id: str,
    quantity_id: str,
    frame_id: str,
    component: str,
    output_unit: str,
    output_dimension,
    point_id: str | None = None,
) -> dict[str, object]:
    return {
        "query_id": "deferredQuery",
        "target": {
            "role": role,
            "subject_id": subject_id,
            "point_id": point_id,
            "frame_id": frame_id,
            "interval_id": "motionInterval",
            "event_id": None,
            "component": component,
            "direction": None,
            "target_quantity_id": quantity_id,
        },
        "output_unit": output_unit,
        "output_dimension": output_dimension.model_dump(mode="json"),
        "shape": "scalar",
        "evidence_refs": [],
    }


def _kinematic_payload() -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["points"] = []
    payload["events"] = []
    payload["geometry"] = []
    payload["interactions"] = []
    payload["constraints"] = []
    payload["state_conditions"] = []
    payload["principle_hints"] = []
    payload["assumptions"] = []
    payload["ambiguities"] = []
    payload["unsupported_features"] = []
    return payload


def _vibration_readout_payload(role: str = "frequency") -> dict[str, object]:
    payload = _vibration_payload()
    dimension = FREQUENCY if role == "frequency" else TIME
    symbol_id = "readoutOmega" if role == "frequency" else "readoutPeriod"
    quantity_id = "frequencyReadout" if role == "frequency" else "periodReadout"
    payload["symbols"].append(_symbol(symbol_id, quantity_id, dimension))
    payload["quantities"].append(
        _quantity(
            quantity_id,
            symbol_id,
            role,
            "bodyA",
            dimension,
            frame_id="vibrationFrame",
            interval_id="vibrationInterval",
        )
    )
    payload["queries"][0]["target"].update(
        {
            "role": role,
            "subject_id": "bodyA",
            "point_id": None,
            "frame_id": "vibrationFrame",
            "interval_id": "vibrationInterval",
            "event_id": None,
            "component": "unspecified",
            "direction": None,
            "target_quantity_id": quantity_id,
        }
    )
    payload["queries"][0]["output_unit"] = "1/s" if role == "frequency" else "s"
    payload["queries"][0]["output_dimension"] = dimension.model_dump(mode="json")
    return payload


def _natural_frequency_readout_payload() -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["symbols"] = [
        _symbol("omega", "frequencyQ", FREQUENCY),
        _symbol("mass", "massQ", MASS),
        _symbol("stiffness", "stiffnessQ", STIFFNESS),
    ]
    payload["quantities"] = [
        _quantity("frequencyQ", "omega", "frequency", "bodyA", FREQUENCY),
        _quantity("massQ", "mass", "mass", "bodyA", MASS, value=2.0, unit="kg"),
        _quantity(
            "stiffnessQ",
            "stiffness",
            "stiffness",
            "bodyA",
            STIFFNESS,
            value=8.0,
            unit="N/m",
        ),
    ]
    payload["assumptions"] = [
        {
            "assumption_id": "frequencyAuthority",
            "kind": "angular_natural_frequency",
            "subject_id": "bodyA",
            "interval_id": None,
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "Angular natural frequency is requested.",
            "evidence_refs": [],
        }
    ]
    payload["queries"][0]["target"].update(
        {
            "role": "frequency",
            "subject_id": "bodyA",
            "point_id": None,
            "frame_id": None,
            "interval_id": None,
            "event_id": None,
            "component": "unspecified",
            "direction": None,
            "target_quantity_id": "frequencyQ",
        }
    )
    payload["queries"][0]["output_unit"] = "1/s"
    payload["queries"][0]["output_dimension"] = FREQUENCY.model_dump(mode="json")
    return payload


def _natural_period_readout_payload() -> dict[str, object]:
    payload = _natural_frequency_readout_payload()
    payload["symbols"][0] = _symbol("period", "periodQ", TIME)
    payload["quantities"][0] = _quantity(
        "periodQ",
        "period",
        "period",
        "bodyA",
        TIME,
    )
    payload["queries"][0]["target"].update(
        role="period",
        target_quantity_id="periodQ",
    )
    payload["queries"][0]["output_unit"] = "s"
    payload["queries"][0]["output_dimension"] = TIME.model_dump(mode="json")
    return payload


def _add_natural_frequency_spring_topology(
    payload: dict[str, object],
) -> dict[str, object]:
    payload["entities"].append(_entity("springElement", "spring"))
    payload["geometry"] = [
        {
            "relation_id": "bodyAttachedToSpring",
            "kind": "attached",
            "participant_ids": ["bodyA", "springElement"],
            "expression": None,
            "quantity_ids": ["stiffnessQ"],
            "interval_id": None,
            "evidence_refs": [],
        }
    ]
    payload["interactions"] = [
        {
            "interaction_id": "naturalFrequencySpring",
            "kind": "spring",
            "participant_ids": ["bodyA", "springElement"],
            "point_ids": [],
            "frame_id": None,
            "interval_id": None,
            "event_id": None,
            "quantity_ids": ["stiffnessQ"],
            "evidence_refs": [],
        }
    ]
    return payload


def _natural_frequency_spring_topology_payload() -> dict[str, object]:
    return _add_natural_frequency_spring_topology(
        _natural_frequency_readout_payload()
    )


def _natural_period_spring_topology_payload() -> dict[str, object]:
    return _add_natural_frequency_spring_topology(
        _natural_period_readout_payload()
    )


def _translation_payload() -> dict[str, object]:
    payload = _kinematic_payload()
    payload["entities"] = [
        _entity("movingPointMass", "particle"),
        _entity("carrier", "rigid_body"),
    ]
    payload["reference_frames"] = [
        _frame("worldFrame", "cartesian_2d", ("x", "y")),
        _frame(
            "translatingFrame",
            "translating",
            ("x", "y"),
            parent_frame_id="worldFrame",
            translating_with_entity_id="carrier",
        ),
    ]
    payload["motion_intervals"] = [
        _interval(("movingPointMass", "carrier"), None)
    ]
    payload["symbols"] = [
        _symbol("aRelative", "relativeAcceleration", ACCELERATION),
        _symbol("aCarrier", "carrierAcceleration", ACCELERATION),
    ]
    payload["quantities"] = [
        _quantity(
            "relativeAcceleration",
            "aRelative",
            "acceleration",
            "movingPointMass",
            ACCELERATION,
            frame_id="translatingFrame",
            interval_id="motionInterval",
            component="x",
        ),
        _quantity(
            "carrierAcceleration",
            "aCarrier",
            "acceleration",
            "carrier",
            ACCELERATION,
            frame_id="worldFrame",
            interval_id="motionInterval",
            component="x",
        ),
    ]
    payload["queries"] = [
        _query(
            role="acceleration",
            subject_id="movingPointMass",
            quantity_id="relativeAcceleration",
            frame_id="translatingFrame",
            component="x",
            output_unit="m/s^2",
            output_dimension=ACCELERATION,
        )
    ]
    return payload


def _translation_absolute_output_payload() -> dict[str, object]:
    payload = _translation_payload()
    payload["symbols"] = [
        _symbol("aAbsoluteB", "absoluteAccelerationB", ACCELERATION),
        _symbol("aReferenceA", "referenceAccelerationA", ACCELERATION),
        _symbol("aRelativeB", "relativeAccelerationB", ACCELERATION),
    ]
    payload["quantities"] = [
        _quantity(
            "absoluteAccelerationB",
            "aAbsoluteB",
            "acceleration",
            "movingPointMass",
            ACCELERATION,
            frame_id="worldFrame",
            interval_id="motionInterval",
            component="x",
        ),
        _quantity(
            "referenceAccelerationA",
            "aReferenceA",
            "acceleration",
            "carrier",
            ACCELERATION,
            value=2.0,
            unit="m/s^2",
            frame_id="worldFrame",
            interval_id="motionInterval",
            component="x",
        ),
        _quantity(
            "relativeAccelerationB",
            "aRelativeB",
            "acceleration",
            "movingPointMass",
            ACCELERATION,
            value=3.0,
            unit="m/s^2",
            frame_id="translatingFrame",
            interval_id="motionInterval",
            component="x",
        ),
    ]
    payload["queries"] = [
        _query(
            role="acceleration",
            subject_id="movingPointMass",
            quantity_id="absoluteAccelerationB",
            frame_id="worldFrame",
            component="x",
            output_unit="m/s^2",
            output_dimension=ACCELERATION,
        )
    ]
    return payload


def _translation_absolute_unspecified_output_payload() -> dict[str, object]:
    payload = _translation_absolute_output_payload()
    for quantity in payload["quantities"]:
        quantity["component"] = "unspecified"
    payload["queries"][0]["target"]["component"] = "unspecified"
    return payload


def _coriolis_payload() -> dict[str, object]:
    payload = _kinematic_payload()
    payload["entities"] = [
        _entity("movingParticle", "particle"),
        _entity("carrier", "rigid_body"),
    ]
    payload["points"] = [_point("pivotPoint", "carrier")]
    payload["reference_frames"] = [
        _frame("worldFrame", "cartesian_2d", ("x", "y")),
        _frame(
            "rotatingFrame",
            "rotating",
            ("x", "y"),
            origin={"kind": "point", "point_id": "pivotPoint"},
            parent_frame_id="worldFrame",
            rotating_about_point_id="pivotPoint",
        ),
    ]
    payload["motion_intervals"] = [
        _interval(("movingParticle", "carrier"), "rotatingFrame")
    ]
    payload["symbols"] = [
        _symbol("aCoriolis", "coriolisAcceleration", ACCELERATION),
        _symbol("vRelative", "relativeVelocity", VELOCITY),
        _symbol("omegaCarrier", "carrierAngularVelocity", FREQUENCY),
    ]
    payload["quantities"] = [
        _quantity(
            "coriolisAcceleration",
            "aCoriolis",
            "acceleration",
            "movingParticle",
            ACCELERATION,
            frame_id="rotatingFrame",
            interval_id="motionInterval",
            component="x",
        ),
        _quantity(
            "relativeVelocity",
            "vRelative",
            "velocity",
            "movingParticle",
            VELOCITY,
            frame_id="rotatingFrame",
            interval_id="motionInterval",
            component="x",
        ),
        _quantity(
            "carrierAngularVelocity",
            "omegaCarrier",
            "angular_velocity",
            "carrier",
            FREQUENCY,
            frame_id="rotatingFrame",
            interval_id="motionInterval",
        ),
    ]
    payload["queries"] = [
        _query(
            role="acceleration",
            subject_id="movingParticle",
            quantity_id="coriolisAcceleration",
            frame_id="rotatingFrame",
            component="x",
            output_unit="m/s^2",
            output_dimension=ACCELERATION,
        )
    ]
    return payload


def _coriolis_magnitude_payload() -> dict[str, object]:
    payload = _coriolis_payload()
    payload["quantities"][0]["component"] = "magnitude"
    payload["queries"][0]["target"]["component"] = "magnitude"
    return payload


def _coriolis_unspecified_payload() -> dict[str, object]:
    payload = _coriolis_payload()
    payload["quantities"][0]["component"] = "unspecified"
    payload["queries"][0]["target"]["component"] = "unspecified"
    return payload


def _coriolis_magnitude_speed_carrier_payload() -> dict[str, object]:
    payload = _coriolis_magnitude_payload()
    payload["quantities"][1]["role"] = "speed"
    payload["quantities"][1]["component"] = "magnitude"
    return payload


def _coriolis_unspecified_speed_carrier_payload() -> dict[str, object]:
    payload = _coriolis_unspecified_payload()
    payload["quantities"][1]["role"] = "speed"
    payload["quantities"][1]["component"] = "unspecified"
    return payload


def _slot_pin_payload() -> dict[str, object]:
    payload = _kinematic_payload()
    payload["entities"] = [
        _entity("slotBody", "slot"),
        _entity("pinJoint", "joint"),
    ]
    payload["points"] = [_point("pinPoint", "pinJoint")]
    payload["reference_frames"] = [
        _frame("radialFrame", "radial_transverse", ("radial", "transverse"))
    ]
    payload["motion_intervals"] = [
        _interval(("slotBody", "pinJoint"), "radialFrame")
    ]
    payload["symbols"] = [_symbol("vPin", "pinVelocity", VELOCITY)]
    payload["quantities"] = [
        _quantity(
            "pinVelocity",
            "vPin",
            "velocity",
            "pinJoint",
            VELOCITY,
            frame_id="radialFrame",
            interval_id="motionInterval",
            point_id="pinPoint",
            component="radial",
        )
    ]
    payload["geometry"] = [
        {
            "relation_id": "pinLiesOnSlot",
            "kind": "lies_on",
            "participant_ids": ["pinPoint", "slotBody"],
            "expression": None,
            "quantity_ids": [],
            "interval_id": "motionInterval",
            "evidence_refs": [],
        }
    ]
    payload["queries"] = [
        _query(
            role="velocity",
            subject_id="pinJoint",
            quantity_id="pinVelocity",
            frame_id="radialFrame",
            point_id="pinPoint",
            component="radial",
            output_unit="m/s",
            output_dimension=VELOCITY,
        )
    ]
    return payload


def _slot_pin_speed_magnitude_payload() -> dict[str, object]:
    payload = _slot_pin_payload()
    payload["symbols"] = [
        _symbol("vMagnitude", "pinSpeed", VELOCITY),
        _symbol("radius", "slotRadius", LENGTH),
        _symbol("radialSpeed", "pinRadialSpeed", VELOCITY),
        _symbol("omega", "slotAngularVelocity", FREQUENCY),
    ]
    payload["quantities"] = [
        _quantity(
            "pinSpeed",
            "vMagnitude",
            "speed",
            "pinJoint",
            VELOCITY,
            frame_id="radialFrame",
            interval_id="motionInterval",
            point_id="pinPoint",
            component="magnitude",
        ),
        _quantity(
            "slotRadius",
            "radius",
            "radius",
            "pinJoint",
            LENGTH,
            value=0.4,
            unit="m",
            frame_id="radialFrame",
            interval_id="motionInterval",
            point_id="pinPoint",
            component="radial",
        ),
        _quantity(
            "pinRadialSpeed",
            "radialSpeed",
            "velocity",
            "pinJoint",
            VELOCITY,
            value=0.3,
            unit="m/s",
            frame_id="radialFrame",
            interval_id="motionInterval",
            point_id="pinPoint",
            component="radial",
        ),
        _quantity(
            "slotAngularVelocity",
            "omega",
            "angular_velocity",
            "slotBody",
            FREQUENCY,
            value=6.0,
            unit="rad/s",
            frame_id="radialFrame",
            interval_id="motionInterval",
        ),
    ]
    payload["queries"] = [
        _query(
            role="speed",
            subject_id="pinJoint",
            quantity_id="pinSpeed",
            frame_id="radialFrame",
            point_id="pinPoint",
            component="magnitude",
            output_unit="m/s",
            output_dimension=VELOCITY,
        )
    ]
    payload["geometry"][0]["quantity_ids"] = [
        "slotRadius",
        "pinRadialSpeed",
        "slotAngularVelocity",
    ]
    return payload


def _slot_pin_speed_unspecified_payload() -> dict[str, object]:
    payload = _slot_pin_speed_magnitude_payload()
    payload["quantities"][0]["component"] = "unspecified"
    payload["queries"][0]["target"]["component"] = "unspecified"
    return payload


def _slot_pin_velocity_magnitude_payload() -> dict[str, object]:
    payload = _slot_pin_speed_magnitude_payload()
    payload["quantities"][0]["role"] = "velocity"
    payload["queries"][0]["target"]["role"] = "velocity"
    return payload


EXACT_PAYLOADS = (
    (
        "free_vibration_frequency",
        _vibration_readout_payload,
        CompilerIssueCode.free_linear_vibration_readout_deferred,
    ),
    (
        "natural_frequency_minimal",
        _natural_frequency_readout_payload,
        CompilerIssueCode.free_linear_vibration_readout_deferred,
    ),
    (
        "natural_period_minimal",
        _natural_period_readout_payload,
        CompilerIssueCode.free_linear_vibration_readout_deferred,
    ),
    (
        "natural_frequency_spring_topology",
        _natural_frequency_spring_topology_payload,
        CompilerIssueCode.free_linear_vibration_readout_deferred,
    ),
    (
        "natural_period_spring_topology",
        _natural_period_spring_topology_payload,
        CompilerIssueCode.free_linear_vibration_readout_deferred,
    ),
    (
        "translating_acceleration",
        _translation_payload,
        CompilerIssueCode.translating_frame_relative_acceleration_deferred,
    ),
    (
        "translating_absolute_output",
        _translation_absolute_output_payload,
        CompilerIssueCode.translating_frame_relative_acceleration_deferred,
    ),
    (
        "translating_absolute_unspecified_output",
        _translation_absolute_unspecified_output_payload,
        CompilerIssueCode.translating_frame_relative_acceleration_deferred,
    ),
    (
        "rotating_coriolis",
        _coriolis_payload,
        CompilerIssueCode.rotating_frame_relative_acceleration_deferred,
    ),
    (
        "rotating_coriolis_magnitude",
        _coriolis_magnitude_payload,
        CompilerIssueCode.rotating_frame_relative_acceleration_deferred,
    ),
    (
        "rotating_coriolis_unspecified",
        _coriolis_unspecified_payload,
        CompilerIssueCode.rotating_frame_relative_acceleration_deferred,
    ),
    (
        "rotating_coriolis_magnitude_speed_carrier",
        _coriolis_magnitude_speed_carrier_payload,
        CompilerIssueCode.rotating_frame_relative_acceleration_deferred,
    ),
    (
        "rotating_coriolis_unspecified_speed_carrier",
        _coriolis_unspecified_speed_carrier_payload,
        CompilerIssueCode.rotating_frame_relative_acceleration_deferred,
    ),
    (
        "slot_pin",
        _slot_pin_payload,
        CompilerIssueCode.slot_pin_relative_motion_deferred,
    ),
    (
        "slot_pin_speed_magnitude",
        _slot_pin_speed_magnitude_payload,
        CompilerIssueCode.slot_pin_relative_motion_deferred,
    ),
    (
        "slot_pin_speed_unspecified",
        _slot_pin_speed_unspecified_payload,
        CompilerIssueCode.slot_pin_relative_motion_deferred,
    ),
    (
        "slot_pin_velocity_magnitude",
        _slot_pin_velocity_magnitude_payload,
        CompilerIssueCode.slot_pin_relative_motion_deferred,
    ),
)


def _compile(payload: dict[str, object]):
    return compile_mechanics_ir(_ir(payload))


@pytest.mark.parametrize("_,payload_factory,expected_code", EXACT_PAYLOADS)
def test_exact_typed_deferred_capabilities_return_one_stable_unsupported_issue(
    _: str,
    payload_factory,
    expected_code: CompilerIssueCode,
) -> None:
    result = _compile(payload_factory())
    assert result.status is CompilerStatus.unsupported
    assert result.graph is None
    assert tuple(item.code for item in result.issues) == (expected_code,)
    assert has_course_scope_deferred_issue(item.code for item in result.issues)


def test_deferred_issue_code_set_is_closed_and_exact() -> None:
    assert COURSE_SCOPE_DEFERRED_ISSUE_CODES == EXPECTED_DEFERRED_CODES
    assert not has_course_scope_deferred_issue(
        (CompilerIssueCode.requires_specialized_model,)
    )
    assert not has_course_scope_deferred_issue(
        (CompilerIssueCode.free_linear_vibration_readout_deferred.value,)
    )


@pytest.mark.parametrize("role", ("frequency", "period"))
def test_free_vibration_period_and_frequency_readouts_are_deferred(role: str) -> None:
    result = _compile(_vibration_readout_payload(role))
    assert tuple(item.code for item in result.issues) == (
        CompilerIssueCode.free_linear_vibration_readout_deferred,
    )


def test_existing_vibration_displacement_ode_remains_ready() -> None:
    result = _compile(_vibration_payload())
    assert result.status is CompilerStatus.ready
    assert result.graph is not None
    assert "linear_vibration" in {item.law_id for item in result.graph.equations}
    assert not has_course_scope_deferred_issue(item.code for item in result.issues)


@pytest.mark.parametrize("_,payload_factory,expected_code", EXACT_PAYLOADS)
def test_metadata_raw_text_digest_labels_and_unsupported_features_cannot_bypass_gate(
    _: str,
    payload_factory,
    expected_code: CompilerIssueCode,
) -> None:
    payload = payload_factory()
    payload["metadata"].update(
        system_type="single_particle_newton",
        subtype="not_deferred_claim",
        source_text_sha256=hashlib.sha256(
            b"raw words deliberately claim a different family"
        ).hexdigest(),
    )
    for index, entity in enumerate(payload["entities"]):
        entity["label"] = f"misleading label {index}"
        entity["aliases"] = ["not a routing key"]
    payload["unsupported_features"] = [
        {
            "feature_code": "misleadingFeatureLabel",
            "description": "Diagnostic-only feature text cannot alter typed scope.",
            "referenced_ids": [],
            "evidence_refs": [],
        }
    ]
    result = _compile(payload)
    assert tuple(item.code for item in result.issues) == (expected_code,)


@pytest.mark.parametrize(
    "claimed_family",
    (
        "spring_mass_vibration",
        "relative_acceleration_translation",
        "coriolis_relative_motion",
        "slot_pin_relative_motion",
    ),
)
def test_system_type_subtype_and_diagnostic_feature_cannot_select_deferred_family(
    claimed_family: str,
) -> None:
    payload = _single_unknown_payload([])
    payload["metadata"].update(
        system_type=claimed_family,
        subtype=claimed_family,
        source_text_sha256="a" * 64,
    )
    payload["unsupported_features"] = [
        {
            "feature_code": "deferredClaim",
            "description": claimed_family,
            "referenced_ids": [],
            "evidence_refs": [],
        }
    ]
    result = _compile(payload)
    assert not has_course_scope_deferred_issue(item.code for item in result.issues)


@pytest.mark.parametrize(
    "payload_factory,mutate",
    (
        (
            _vibration_readout_payload,
            lambda payload: payload["assumptions"].__setitem__(
                slice(None),
                [
                    item
                    for item in payload["assumptions"]
                    if item["kind"] != "free_vibration"
                ],
            ),
        ),
        (
            _translation_payload,
            lambda payload: payload["reference_frames"][1].update(
                translating_with_entity_id=None
            ),
        ),
        (
            _coriolis_payload,
            lambda payload: (
                payload["quantities"].pop(),
                payload["symbols"].pop(),
            ),
        ),
        (
            _slot_pin_payload,
            lambda payload: payload["geometry"][0].update(kind="topology_connects"),
        ),
    ),
)
def test_incomplete_near_misses_never_receive_a_false_exact_family_code(
    payload_factory,
    mutate,
) -> None:
    payload = payload_factory()
    mutate(payload)
    result = _compile(payload)
    assert not has_course_scope_deferred_issue(item.code for item in result.issues)


@pytest.mark.parametrize(
    "mutation",
    ("topology", "carrier", "component"),
)
def test_absolute_translation_near_misses_do_not_capture_arbitrary_acceleration(
    mutation: str,
) -> None:
    payload = _translation_absolute_output_payload()
    if mutation == "topology":
        payload["reference_frames"][1]["translating_with_entity_id"] = None
    elif mutation == "carrier":
        payload["quantities"] = [
            item
            for item in payload["quantities"]
            if item["quantity_id"] != "referenceAccelerationA"
        ]
        payload["symbols"] = [
            item for item in payload["symbols"] if item["symbol_id"] != "aReferenceA"
        ]
    else:
        next(
            item
            for item in payload["quantities"]
            if item["quantity_id"] == "relativeAccelerationB"
        )["component"] = "y"
    result = _compile(payload)
    assert CompilerIssueCode.translating_frame_relative_acceleration_deferred not in {
        item.code for item in result.issues
    }


def test_absolute_translation_unspecified_requires_a_translating_frame() -> None:
    payload = _translation_absolute_unspecified_output_payload()
    payload["reference_frames"][1]["translating_with_entity_id"] = None
    result = _compile(payload)
    assert CompilerIssueCode.translating_frame_relative_acceleration_deferred not in {
        item.code for item in result.issues
    }


@pytest.mark.parametrize("missing", ("relativeVelocity", "carrierAngularVelocity"))
def test_coriolis_magnitude_requires_both_typed_motion_carriers(missing: str) -> None:
    payload = _coriolis_magnitude_payload()
    symbol_id = next(
        item["symbol_id"]
        for item in payload["quantities"]
        if item["quantity_id"] == missing
    )
    payload["quantities"] = [
        item for item in payload["quantities"] if item["quantity_id"] != missing
    ]
    payload["symbols"] = [
        item for item in payload["symbols"] if item["symbol_id"] != symbol_id
    ]
    result = _compile(payload)
    assert CompilerIssueCode.rotating_frame_relative_acceleration_deferred not in {
        item.code for item in result.issues
    }


def test_nonrotating_rigid_body_acceleration_magnitude_is_not_coriolis_deferred() -> None:
    payload = _coriolis_magnitude_payload()
    payload["entities"][0]["primitive"] = "rigid_body"
    rotating_frame = payload["reference_frames"][1]
    rotating_frame["frame_type"] = "body_fixed"
    rotating_frame["rotating_about_point_id"] = None
    result = _compile(payload)
    assert CompilerIssueCode.rotating_frame_relative_acceleration_deferred not in {
        item.code for item in result.issues
    }


def test_polar_speed_magnitude_without_rotating_frame_is_not_coriolis_deferred() -> None:
    payload = _coriolis_magnitude_speed_carrier_payload()
    frame = payload["reference_frames"][1]
    frame["frame_type"] = "radial_transverse"
    frame["axes"] = _frame(
        "rotatingFrame",
        "radial_transverse",
        ("radial", "transverse"),
    )["axes"]
    frame["rotating_about_point_id"] = None
    result = _compile(payload)
    assert CompilerIssueCode.rotating_frame_relative_acceleration_deferred not in {
        item.code for item in result.issues
    }


def test_radial_polar_motion_and_an_unrelated_slot_are_not_slot_pin_deferred() -> None:
    payload = _slot_pin_payload()
    payload["entities"] = [
        _entity("polarParticle", "particle"),
        _entity("unrelatedSlot", "slot"),
    ]
    payload["points"][0]["owner_entity_id"] = "polarParticle"
    payload["motion_intervals"][0]["subject_ids"] = [
        "polarParticle",
        "unrelatedSlot",
    ]
    payload["quantities"][0]["subject_id"] = "polarParticle"
    payload["queries"][0]["target"]["subject_id"] = "polarParticle"
    payload["geometry"] = []
    result = _compile(payload)
    assert CompilerIssueCode.slot_pin_relative_motion_deferred not in {
        item.code for item in result.issues
    }
    assert not has_course_scope_deferred_issue(item.code for item in result.issues)


def test_slot_pin_speed_near_misses_and_polar_magnitude_remain_unblocked() -> None:
    no_lies_on = _slot_pin_speed_magnitude_payload()
    no_lies_on["geometry"] = []
    result = _compile(no_lies_on)
    assert CompilerIssueCode.slot_pin_relative_motion_deferred not in {
        item.code for item in result.issues
    }

    no_slot = _slot_pin_speed_magnitude_payload()
    no_slot["entities"] = [
        item for item in no_slot["entities"] if item["entity_id"] != "slotBody"
    ]
    no_slot["motion_intervals"][0]["subject_ids"] = ["pinJoint"]
    no_slot["geometry"] = []
    next(
        item
        for item in no_slot["quantities"]
        if item["quantity_id"] == "slotAngularVelocity"
    )["subject_id"] = "pinJoint"
    result = _compile(no_slot)
    assert CompilerIssueCode.slot_pin_relative_motion_deferred not in {
        item.code for item in result.issues
    }

    polar = deepcopy(no_slot)
    polar["entities"] = [_entity("polarParticle", "particle")]
    polar["points"][0]["owner_entity_id"] = "polarParticle"
    polar["motion_intervals"][0]["subject_ids"] = ["polarParticle"]
    for quantity in polar["quantities"]:
        quantity["subject_id"] = "polarParticle"
    polar["queries"][0]["target"]["subject_id"] = "polarParticle"
    result = _compile(polar)
    assert CompilerIssueCode.slot_pin_relative_motion_deferred not in {
        item.code for item in result.issues
    }
    assert not has_course_scope_deferred_issue(item.code for item in result.issues)

    velocity_unspecified = _slot_pin_velocity_magnitude_payload()
    velocity_unspecified["quantities"][0]["component"] = "unspecified"
    velocity_unspecified["queries"][0]["target"]["component"] = "unspecified"
    result = _compile(velocity_unspecified)
    assert CompilerIssueCode.slot_pin_relative_motion_deferred not in {
        item.code for item in result.issues
    }


def test_invalid_query_and_dangling_binding_precede_deferred_classification() -> None:
    query_mismatch = _translation_payload()
    query_mismatch["queries"][0]["target"]["component"] = "y"
    result = _compile(query_mismatch)
    assert result.status is CompilerStatus.invalid
    assert tuple(item.code for item in result.issues) == (
        CompilerIssueCode.unresolved_query,
    )

    dangling = _slot_pin_payload()
    dangling["entities"] = [
        item for item in dangling["entities"] if item["entity_id"] != "slotBody"
    ]
    result = _compile(dangling)
    assert result.status is CompilerStatus.invalid
    assert tuple(item.code for item in result.issues) == (
        CompilerIssueCode.invalid_binding,
    )


def _coherent_outcome(ir: MechanicsProblemIRV1):
    baseline = _accepted_outcome()
    fingerprint = calculation_fingerprint(ir)
    normalization = NormalizationResult(
        terminal=ValidationTerminal.accepted,
        validation=DraftValidationResult(ValidationTerminal.accepted, ()),
        ir=ir,
        calculation_fingerprint=fingerprint,
        correction_revision=ir.metadata.correction_revision,
    )
    return replace(
        baseline,
        terminal=ModelerTerminal.accepted,
        normalization=normalization,
        ir=ir,
        calculation_fingerprint=fingerprint,
    )


@pytest.mark.parametrize(
    "mode",
    (
        MechanicsIRMode.shadow,
        MechanicsIRMode.confirm,
        MechanicsIRMode.auto,
        MechanicsIRMode.required,
    ),
)
@pytest.mark.parametrize("_,payload_factory,expected_code", EXACT_PAYLOADS)
def test_runtime_deferred_matrix_never_solves_or_delivers_legacy_or_generic(
    monkeypatch,
    mode: MechanicsIRMode,
    _: str,
    payload_factory,
    expected_code: CompilerIssueCode,
) -> None:
    ir = _ir(payload_factory())
    compiler_result = compile_mechanics_ir(ir)
    assert compiler_result.status is CompilerStatus.unsupported
    assert compiler_result.graph is None
    assert tuple(item.code for item in compiler_result.issues) == (expected_code,)

    compiler_calls: list[tuple[object, object]] = []

    class CompilerSpy:
        def compile(self, compiled_ir, *, validated_ir_authorization):
            compiler_calls.append((compiled_ir, validated_ir_authorization))
            return compiler_result

    outcome = _coherent_outcome(ir)
    modeler = _ModelerSpy(outcome)
    solve_calls: list[object] = []
    monkeypatch.setattr(runtime_module, "MechanicsCompiler", CompilerSpy)
    monkeypatch.setattr(
        runtime_module,
        "solve_verified_equation_graph",
        lambda graph: solve_calls.append(graph),
    )
    execution = MechanicsRuntimeOrchestrator(
        _config(mode),
        modeler=modeler,
    ).evaluate(
        PROBLEM,
        confirmation_fingerprint=(
            outcome.calculation_fingerprint
            if mode is MechanicsIRMode.confirm
            else None
        ),
    )
    assert modeler.calls == [PROBLEM]
    assert len(compiler_calls) == 1
    assert compiler_calls[0][0] is ir
    assert solve_calls == []
    assert execution.terminal is RuntimeTerminal.compiler_rejected
    assert execution.delivery is RuntimeDelivery.none
    assert execution.generic_result is None
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert tuple(item.code for item in execution.compiler_result.issues) == (
        expected_code,
    )
    assert execution.summary.compiler_issue_codes == (
        expected_code,
    )


def test_runtime_off_is_the_only_legacy_rollback_and_never_models() -> None:
    outcome = _coherent_outcome(_ir(_translation_payload()))
    modeler = _ModelerSpy(outcome)
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.off),
        modeler=modeler,
    ).evaluate(PROBLEM)
    assert modeler.calls == []
    assert execution.terminal is RuntimeTerminal.off
    assert execution.delivery is RuntimeDelivery.legacy
    assert execution.generic_result is None


@pytest.mark.parametrize(
    "problem_text",
    (
        "This text falsely claims an ordinary inertial-frame problem.",
        "relative_acceleration_translation",
        "spring_mass_vibration coriolis slot pin",
    ),
)
def test_runtime_raw_problem_text_cannot_bypass_typed_deferred_classification(
    problem_text: str,
) -> None:
    outcome = _coherent_outcome(_ir(_translation_payload()))
    modeler = _ModelerSpy(outcome)
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.required),
        modeler=modeler,
    ).evaluate(problem_text)
    assert modeler.calls == [problem_text]
    assert execution.terminal is RuntimeTerminal.compiler_rejected
    assert execution.delivery is RuntimeDelivery.none
    assert execution.summary.compiler_issue_codes == (
        CompilerIssueCode.translating_frame_relative_acceleration_deferred,
    )


def test_runtime_contract_rejects_forged_shadow_legacy_fallback_for_deferred() -> None:
    ir = _ir(_translation_payload())
    outcome = _coherent_outcome(ir)
    compiler_result = compile_mechanics_ir(ir)
    assert tuple(item.code for item in compiler_result.issues) == (
        CompilerIssueCode.translating_frame_relative_acceleration_deferred,
    )
    with pytest.raises(ValueError, match="non-solving compiler rejection"):
        MechanicsRuntimeExecution(
            mode=MechanicsIRMode.shadow,
            terminal=RuntimeTerminal.compiler_rejected,
            delivery=RuntimeDelivery.legacy,
            modeler_outcome=outcome,
            compiler_result=compiler_result,
        )


def test_nondeferred_shadow_behavior_remains_legacy() -> None:
    payload = _translation_payload()
    payload["reference_frames"][1]["translating_with_entity_id"] = None
    outcome = _coherent_outcome(_ir(payload))
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.shadow),
        modeler=_ModelerSpy(outcome),
    ).evaluate(PROBLEM)
    assert execution.delivery is RuntimeDelivery.legacy
    assert execution.generic_result is None
    if execution.compiler_result is not None:
        assert not has_course_scope_deferred_issue(
            item.code for item in execution.compiler_result.issues
        )


def _deferred_compiler_issue() -> CompilerIssue:
    return CompilerIssue(
        code=CompilerIssueCode.slot_pin_relative_motion_deferred,
        severity=CompilerIssueSeverity.error,
        message="The exact course-scope capability is deferred.",
        path="queries.deferredQuery",
        referenced_id="deferredQuery",
    )


def test_compiler_result_contract_binds_deferred_to_one_unsupported_graphless_error() -> None:
    issue = _deferred_compiler_issue()
    graph = _graph(positive_only=True)
    valid = CompilerResult(
        status=CompilerStatus.unsupported,
        issues=(issue,),
    )
    assert valid.graph is None
    assert valid.compilable is False
    assert compiler_result_is_coherent(valid)

    for status in (CompilerStatus.ready, CompilerStatus.overdetermined):
        with pytest.raises(ValidationError, match="exact unsupported"):
            CompilerResult(status=status, graph=graph, issues=(issue,))
    with pytest.raises(ValidationError, match="exact unsupported"):
        CompilerResult(
            status=CompilerStatus.unsupported,
            graph=graph,
            issues=(issue,),
        )
    with pytest.raises(ValidationError, match="exact unsupported"):
        CompilerResult(
            status=CompilerStatus.unsupported,
            issues=(
                issue,
                CompilerIssue(
                    code=CompilerIssueCode.requires_specialized_model,
                    severity=CompilerIssueSeverity.error,
                    message="An unrelated issue cannot share deferred authority.",
                    path="queries.deferredQuery",
                ),
            ),
        )

    ordinary = CompilerResult(status=CompilerStatus.ready, graph=graph)
    assert ordinary.compilable
    assert compiler_result_is_coherent(ordinary)


def test_execution_and_summary_reject_nonrejection_or_mixed_deferred_projections() -> None:
    ir = _ir(_slot_pin_speed_magnitude_payload())
    outcome = _coherent_outcome(ir)
    compiler_result = compile_mechanics_ir(ir)
    assert compiler_result.status is CompilerStatus.unsupported

    valid = MechanicsRuntimeExecution(
        mode=MechanicsIRMode.required,
        terminal=RuntimeTerminal.compiler_rejected,
        delivery=RuntimeDelivery.none,
        modeler_outcome=outcome,
        compiler_result=compiler_result,
    )
    assert valid.summary.compiler_issue_codes == (
        CompilerIssueCode.slot_pin_relative_motion_deferred,
    )

    with pytest.raises(ValueError, match="non-solving compiler rejection"):
        MechanicsRuntimeExecution(
            mode=MechanicsIRMode.required,
            terminal=RuntimeTerminal.solved,
            delivery=RuntimeDelivery.none,
            modeler_outcome=outcome,
            compiler_result=compiler_result,
        )
    with pytest.raises(ValidationError, match=r"exact .*unsupported projection"):
        MechanicsRuntimeSummary(
            mode=MechanicsIRMode.required,
            terminal=RuntimeTerminal.solved,
            delivery=RuntimeDelivery.none,
            modeler_terminal=ModelerTerminal.accepted,
            compiler_status=CompilerStatus.unsupported,
            compiler_issue_codes=(
                CompilerIssueCode.slot_pin_relative_motion_deferred,
            ),
        )
    with pytest.raises(ValidationError, match="exact"):
        MechanicsRuntimeSummary(
            mode=MechanicsIRMode.required,
            terminal=RuntimeTerminal.compiler_rejected,
            delivery=RuntimeDelivery.none,
            modeler_terminal=ModelerTerminal.accepted,
            compiler_status=CompilerStatus.unsupported,
            compiler_issue_codes=(
                CompilerIssueCode.slot_pin_relative_motion_deferred,
                CompilerIssueCode.requires_specialized_model,
            ),
        )


@pytest.mark.parametrize(
    "mode",
    (
        MechanicsIRMode.shadow,
        MechanicsIRMode.confirm,
        MechanicsIRMode.auto,
        MechanicsIRMode.required,
    ),
)
def test_forged_ready_deferred_compiler_result_fails_closed_before_solver(
    monkeypatch,
    mode: MechanicsIRMode,
) -> None:
    ir = _ir(_translation_payload())
    outcome = _coherent_outcome(ir)
    forged = CompilerResult.model_construct(
        status=CompilerStatus.ready,
        graph=_graph(positive_only=True),
        issues=(_deferred_compiler_issue(),),
    )
    assert not compiler_result_is_coherent(forged)

    class CompilerSpy:
        def compile(self, compiled_ir, *, validated_ir_authorization):
            assert compiled_ir is ir
            return forged

    solve_calls: list[object] = []
    monkeypatch.setattr(runtime_module, "MechanicsCompiler", CompilerSpy)
    monkeypatch.setattr(
        runtime_module,
        "solve_verified_equation_graph",
        lambda graph: solve_calls.append(graph),
    )
    execution = MechanicsRuntimeOrchestrator(
        _config(mode),
        modeler=_ModelerSpy(outcome),
    ).evaluate(
        PROBLEM,
        confirmation_fingerprint=(
            outcome.calculation_fingerprint
            if mode is MechanicsIRMode.confirm
            else None
        ),
    )
    assert execution.terminal is RuntimeTerminal.failed
    assert execution.failure is RuntimeFailure.compiler_contract
    assert execution.delivery is RuntimeDelivery.none
    assert execution.compiler_result is None
    assert execution.solve_result is None
    assert execution.generic_result is None
    assert solve_calls == []


def test_ordinary_nondeferred_compiler_contract_failure_preserves_shadow_legacy(
    monkeypatch,
) -> None:
    payload = _translation_payload()
    payload["reference_frames"][1]["translating_with_entity_id"] = None
    ir = _ir(payload)
    outcome = _coherent_outcome(ir)
    forged = CompilerResult.model_construct(
        status=CompilerStatus.ready,
        graph=None,
        issues=(),
    )
    assert not compiler_result_is_coherent(forged)

    class CompilerSpy:
        def compile(self, compiled_ir, *, validated_ir_authorization):
            return forged

    monkeypatch.setattr(runtime_module, "MechanicsCompiler", CompilerSpy)
    execution = MechanicsRuntimeOrchestrator(
        _config(MechanicsIRMode.shadow),
        modeler=_ModelerSpy(outcome),
    ).evaluate(PROBLEM)
    assert execution.terminal is RuntimeTerminal.failed
    assert execution.failure is RuntimeFailure.compiler_contract
    assert execution.delivery is RuntimeDelivery.legacy
    assert execution.compiler_result is None
    assert execution.generic_result is None
