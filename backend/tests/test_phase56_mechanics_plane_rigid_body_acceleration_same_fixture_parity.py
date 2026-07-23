from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity
from engine.solvers.rigid_body_2d.acceleration import PlaneRigidBodyAccelerationSolver
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
from test_phase56_mechanics_compiler import (
    ACCELERATION,
    ANGULAR_ACCELERATION,
    FREQUENCY,
    LENGTH,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
    compile_mechanics_ir,
)


@dataclass(frozen=True)
class RigidAccelerationCase:
    case_id: str
    a_ax: tuple[float, str]
    a_ay: tuple[float, str]
    omega: tuple[float, str]
    alpha: tuple[float, str]
    r_x: tuple[float, str]
    r_y: tuple[float, str]
    query_quantity_id: str = "aMagQ"

    @property
    def expected_components(self) -> tuple[float, float]:
        a_ax = _si(self.a_ax, ACCELERATION)
        a_ay = _si(self.a_ay, ACCELERATION)
        omega = _si(self.omega, FREQUENCY)
        alpha = _si(self.alpha, ANGULAR_ACCELERATION)
        r_x = _si(self.r_x, LENGTH)
        r_y = _si(self.r_y, LENGTH)
        return (
            a_ax - alpha * r_y - omega * omega * r_x,
            a_ay + alpha * r_x - omega * omega * r_y,
        )

    @property
    def expected_si(self) -> float:
        x, y = self.expected_components
        return {"aBxQ": x, "aByQ": y, "aMagQ": math.hypot(x, y)}[
            self.query_quantity_id
        ]


def _si(raw: tuple[float, str], dimension) -> float:
    from engine.mechanics.units import normalize_quantity

    value = normalize_quantity(str(raw[0]), raw[1], "scalar", dimension).value
    assert isinstance(value, float)
    return value


BASE = RigidAccelerationCase(
    "base", (1.0, "m/s^2"), (-2.0, "m/s^2"), (3.0, "rad/s"),
    (2.0, "rad/s^2"), (0.4, "m"), (0.3, "m")
)
QUERY_X = RigidAccelerationCase(**{**BASE.__dict__, "case_id": "query-x", "query_quantity_id": "aBxQ"})
QUERY_Y = RigidAccelerationCase(**{**BASE.__dict__, "case_id": "query-y", "query_quantity_id": "aByQ"})
FIXED_A = RigidAccelerationCase(
    "fixed-a", (0.0, "m/s^2"), (0.0, "m/s^2"), (4.0, "rad/s"),
    (1.5, "rad/s^2"), (0.6, "m"), (-0.2, "m")
)
ZERO_OMEGA = RigidAccelerationCase(
    "zero-omega", (2.0, "m/s^2"), (1.0, "m/s^2"), (0.0, "rad/s"),
    (-3.0, "rad/s^2"), (0.2, "m"), (0.5, "m")
)
ZERO_ALPHA = RigidAccelerationCase(
    "zero-alpha", (-1.0, "m/s^2"), (0.5, "m/s^2"), (-2.5, "rad/s"),
    (0.0, "rad/s^2"), (-0.3, "m"), (0.4, "m")
)
SIGNED = RigidAccelerationCase(
    "signed", (-2.0, "m/s^2"), (3.0, "m/s^2"), (-1.5, "rad/s"),
    (-4.0, "rad/s^2"), (0.7, "m"), (-0.25, "m")
)
MIXED_UNITS = RigidAccelerationCase(
    "mixed-units", (100.0, "cm/s^2"), (-0.2, "m/s^2"), (30.0, "rpm"),
    (1.0, "rad/s^2"), (40.0, "cm"), (-250.0, "mm")
)
VALID_CASES = (BASE, QUERY_X, QUERY_Y, FIXED_A, ZERO_OMEGA, ZERO_ALPHA, SIGNED, MIXED_UNITS)


def _direction(axis: str) -> dict[str, object]:
    return {"kind": "axis", "frame_id": "rigidFrame", "axis": axis, "sign": 1}


def _q(
    quantity_id: str,
    symbol_id: str,
    role: str,
    dimension,
    *,
    point_id: str,
    component: str,
    value: tuple[float, str] | None,
) -> dict[str, object]:
    raw, unit = value if value is not None else (None, "1")
    item = _quantity(
        quantity_id,
        symbol_id,
        role,
        "body",
        dimension,
        value=raw,
        unit=unit,
        frame_id="rigidFrame",
        interval_id="rigidInterval",
        point_id=point_id,
        component=component,
        provenance="explicit_source" if value is not None else "inferred",
        evidence_refs=("rigidEvidence",),
    )
    if component in {"x", "y"}:
        item["direction"] = _direction(component)
    return item


def _payload(case: RigidAccelerationCase) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["metadata"].update(
        system_type="diagnosticRigidAcceleration",
        subtype="diagnosticPlanar",
        model_id="sameFixtureRigidAcceleration",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    payload["source_evidence"] = [
        {
            "kind": "text",
            "evidence_id": "rigidEvidence",
            "quote": "typed planar rigid body acceleration geometry",
            "source_span": {"start": 0, "end": 45},
            "quantity_span": None,
            "occurrence_index": 0,
        }
    ]
    payload["entities"] = [
        {
            "entity_id": "body", "primitive": "rigid_body", "label": "body",
            "aliases": [], "component_of_entity_id": None,
            "evidence_refs": ["rigidEvidence"], "model_confidence": None,
        }
    ]
    payload["points"] = [
        {
            "point_id": "pointA", "role": "reference", "owner_entity_id": "body",
            "frame_id": "rigidFrame", "label": "A",
            "evidence_refs": ["rigidEvidence"],
        },
        {
            "point_id": "pointB", "role": "material", "owner_entity_id": "body",
            "frame_id": "rigidFrame", "label": "B",
            "evidence_refs": ["rigidEvidence"],
        },
    ]
    payload["reference_frames"] = [
        {
            "frame_id": "rigidFrame", "frame_type": "cartesian_2d",
            "origin": {"kind": "world"},
            "axes": [
                {"axis": "x", "direction": _direction("x")},
                {"axis": "y", "direction": _direction("y")},
            ],
            "parent_frame_id": None, "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": ["rigidEvidence"],
        }
    ]
    payload["motion_intervals"] = [
        {
            "interval_id": "rigidInterval", "order": 1,
            "subject_ids": ["body"], "frame_id": "rigidFrame",
            "start_event_id": None, "end_event_id": None,
            "evidence_refs": ["rigidEvidence"],
        }
    ]
    payload["events"] = []
    quantities = [
        _q("aAxQ", "aAx", "acceleration", ACCELERATION, point_id="pointA", component="x", value=case.a_ax),
        _q("aAyQ", "aAy", "acceleration", ACCELERATION, point_id="pointA", component="y", value=case.a_ay),
        _q("omegaQ", "omega", "angular_velocity", FREQUENCY, point_id="pointA", component="z", value=case.omega),
        _q("alphaQ", "alpha", "angular_acceleration", ANGULAR_ACCELERATION, point_id="pointA", component="z", value=case.alpha),
        _q("rXQ", "rX", "displacement", LENGTH, point_id="pointB", component="x", value=case.r_x),
        _q("rYQ", "rY", "displacement", LENGTH, point_id="pointB", component="y", value=case.r_y),
        _q("aBxQ", "aBx", "acceleration", ACCELERATION, point_id="pointB", component="x", value=None),
        _q("aByQ", "aBy", "acceleration", ACCELERATION, point_id="pointB", component="y", value=None),
        _q("aMagQ", "aMag", "acceleration", ACCELERATION, point_id="pointB", component="magnitude", value=None),
    ]
    payload["quantities"] = quantities
    payload["symbols"] = [
        _symbol(item["symbol_id"], item["quantity_id"], ACCELERATION if item["role"] == "acceleration" else FREQUENCY if item["role"] == "angular_velocity" else ANGULAR_ACCELERATION if item["role"] == "angular_acceleration" else LENGTH)
        for item in quantities
    ]
    payload["geometry"] = [
        {
            "relation_id": "rigidAttachment", "kind": "attached",
            "participant_ids": ["body", "pointA", "pointB"],
            "expression": None, "quantity_ids": ["rXQ", "rYQ"],
            "interval_id": "rigidInterval", "evidence_refs": ["rigidEvidence"],
        }
    ]
    payload["interactions"] = []
    payload["constraints"] = []
    payload["state_conditions"] = []
    payload["assumptions"] = []
    target = next(item for item in quantities if item["quantity_id"] == case.query_quantity_id)
    payload["queries"] = [
        {
            "query_id": "rigidQuery",
            "target": {
                "role": target["role"], "subject_id": "body",
                "point_id": "pointB", "frame_id": "rigidFrame",
                "interval_id": "rigidInterval", "event_id": None,
                "component": target["component"], "direction": target["direction"],
                "target_quantity_id": target["quantity_id"],
            },
            "output_unit": "m/s^2",
            "output_dimension": ACCELERATION.model_dump(mode="json"),
            "shape": "scalar", "evidence_refs": ["rigidEvidence"],
        }
    ]
    payload["principle_hints"] = []
    payload["ambiguities"] = []
    payload["unsupported_features"] = []
    return payload


def _solve(case: RigidAccelerationCase):
    compiled = compile_mechanics_ir(_ir(_payload(case)))
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    selected = next(
        item for item in result.verified_candidates
        if item.candidate.candidate_id == result.selected_candidate_id
    )
    values = {
        item.symbol.symbol_id: item.known_si_value
        for item in compiled.graph.symbols if item.known_si_value is not None
    }
    values.update({item.symbol_id: item.value_si for item in selected.candidate.values})
    assert isinstance(selected.candidate.query_value_si, float)
    return compiled.graph, result, selected.candidate.query_value_si, values


@pytest.mark.parametrize("case", VALID_CASES, ids=lambda item: item.case_id)
def test_plane_rigid_body_acceleration_components_magnitude_units_and_residuals(case: RigidAccelerationCase) -> None:
    graph, result, value, values = _solve(case)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    assert {item.law_id for item in graph.equations} == {
        "planar_rigid_acceleration_x",
        "planar_rigid_acceleration_y",
        "planar_acceleration_magnitude",
        "acceleration_magnitude_nonnegative",
    }
    assert result.plan.primary_backend is SolveBackendKind.polynomial_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    expected_x, expected_y = case.expected_components
    assert values["aBx"] == pytest.approx(expected_x, abs=1.0e-9)
    assert values["aBy"] == pytest.approx(expected_y, abs=1.0e-9)
    assert values["aMag"] == pytest.approx(math.hypot(expected_x, expected_y), abs=1.0e-9)


def test_plane_rigid_body_acceleration_magnitude_negative_root_is_rejected() -> None:
    _, result, value, _ = _solve(BASE)
    roots = sorted(float(item.query_value_si) for item in result.candidate_set.candidates)
    assert roots == pytest.approx([-value, value])
    assert len(result.verified_candidates) == 1
    rejected = next(item for item in result.verification_outcomes if not item.passed)
    check = next(item for item in rejected.checks if item.kind is VerificationCheckKind.inequality)
    assert check.status is VerificationCheckStatus.failed


def test_plane_rigid_body_acceleration_metadata_id_and_order_invariance() -> None:
    baseline = compile_mechanics_ir(_ir(_payload(BASE)))
    assert baseline.graph is not None
    payload = _payload(BASE)
    payload["metadata"].update(system_type="wrongLabel", subtype="wrongSubtype", model_id="wrongModel")
    identifiers = _collect_fixture_identifiers(payload)
    mapping = {identifier: f"renamed{index}" for index, identifier in enumerate(sorted(identifiers), start=1)}
    _rename_fixture_identifiers(payload, mapping)
    for key in (
        "entities", "points", "reference_frames", "motion_intervals", "symbols",
        "quantities", "geometry", "queries",
    ):
        payload[key] = list(reversed(payload[key]))
    changed = compile_mechanics_ir(_ir(payload))
    assert changed.status is CompilerStatus.ready, changed.issues
    assert changed.graph is not None
    assert changed.graph.fingerprint == baseline.graph.fingerprint
    assert Counter(item.law_id for item in changed.graph.equations) == Counter(item.law_id for item in baseline.graph.equations)


def test_plane_rigid_body_acceleration_malformed_topology_query_unit_and_extra_actor_fail_closed() -> None:
    mutations = []
    missing_relation = _payload(BASE)
    missing_relation["geometry"] = []
    mutations.append(missing_relation)

    wrong_frame = _payload(BASE)
    wrong_frame["reference_frames"][0]["frame_type"] = "cartesian_1d"
    wrong_frame["reference_frames"][0]["axes"] = [wrong_frame["reference_frames"][0]["axes"][0]]
    mutations.append(wrong_frame)

    missing_alpha = _payload(BASE)
    missing_alpha["quantities"] = [item for item in missing_alpha["quantities"] if item["quantity_id"] != "alphaQ"]
    missing_alpha["symbols"] = [item for item in missing_alpha["symbols"] if item["quantity_id"] != "alphaQ"]
    mutations.append(missing_alpha)

    extra_actor = _payload(BASE)
    extra_actor["entities"].append({
        "entity_id": "other", "primitive": "particle", "label": "other",
        "aliases": [], "component_of_entity_id": None,
        "evidence_refs": ["rigidEvidence"], "model_confidence": None,
    })
    mutations.append(extra_actor)

    wrong_query = _payload(BASE)
    wrong_query["queries"][0]["target"]["point_id"] = "pointA"
    mutations.append(wrong_query)

    wrong_unit = _payload(BASE)
    wrong_unit["queries"][0]["output_unit"] = "m/s"
    mutations.append(wrong_unit)

    for payload in mutations:
        assert compile_mechanics_ir(_ir(payload)).status is not CompilerStatus.ready


@pytest.mark.slow
@pytest.mark.parametrize("case", (BASE, FIXED_A, SIGNED, MIXED_UNITS), ids=lambda item: item.case_id)
def test_plane_rigid_body_acceleration_same_fixture_legacy_parity(case: RigidAccelerationCase) -> None:
    _, _, generic, _ = _solve(case)
    r_x = _si(case.r_x, LENGTH)
    r_y = _si(case.r_y, LENGTH)
    a_ax = _si(case.a_ax, ACCELERATION)
    a_ay = _si(case.a_ay, ACCELERATION)
    omega = _si(case.omega, FREQUENCY)
    alpha = _si(case.alpha, ANGULAR_ACCELERATION)
    legacy = PlaneRigidBodyAccelerationSolver().solve(
        CanonicalProblem(
            system_type="plane_rigid_body_acceleration",
            knowns={
                "aAx": Quantity("aAx", a_ax, "m/s^2"),
                "aAy": Quantity("aAy", a_ay, "m/s^2"),
                "rBAx": Quantity("rBAx", r_x, "m"),
                "rBAy": Quantity("rBAy", r_y, "m"),
                "omega": Quantity("omega", abs(omega), "rad/s"),
                "alpha": Quantity("alpha", abs(alpha), "rad/s^2"),
            },
            coordinate_data={
                "omega_sign": -1 if omega < 0 else 1,
                "alpha_sign": -1 if alpha < 0 else 1,
            },
            unknowns=["acceleration"],
            requested_outputs=["acceleration"],
        )
    )
    assert legacy.ok is True, legacy.unsupported_reason
    assert legacy.answer is not None
    expected_mag = math.hypot(*case.expected_components)
    assert legacy.answer.numeric == pytest.approx(expected_mag, abs=1.0e-5)
    if case.query_quantity_id == "aMagQ":
        assert generic == pytest.approx(legacy.answer.numeric, abs=1.0e-5)
