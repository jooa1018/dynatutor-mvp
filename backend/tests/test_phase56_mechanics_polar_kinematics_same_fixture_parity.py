from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.verification import MechanicsSolveTerminal, VerificationCheckKind, VerificationCheckStatus
from engine.models import CanonicalProblem, Quantity
from engine.solvers.advanced_motion import PolarKinematicsSolver
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
from test_phase56_mechanics_compiler import (
    ACCELERATION,
    ANGULAR_ACCELERATION,
    FREQUENCY,
    LENGTH,
    VELOCITY,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
    compile_mechanics_ir,
)


@dataclass(frozen=True)
class PolarCase:
    case_id: str
    radius: tuple[float, str]
    radial_rate: tuple[float, str]
    radial_acceleration: tuple[float, str]
    omega: tuple[float, str]
    alpha: tuple[float, str]
    query_quantity_id: str = "speedQ"

    @property
    def expected(self) -> dict[str, float]:
        r = _si(self.radius, LENGTH)
        rdot = _si(self.radial_rate, VELOCITY)
        rddot = _si(self.radial_acceleration, ACCELERATION)
        omega = _si(self.omega, FREQUENCY)
        alpha = _si(self.alpha, ANGULAR_ACCELERATION)
        vr = rdot
        vt = r * omega
        ar = rddot - r * omega * omega
        at = r * alpha + 2.0 * rdot * omega
        return {
            "vRadQ": vr,
            "vTransQ": vt,
            "speedQ": math.hypot(vr, vt),
            "aRadQ": ar,
            "aTransQ": at,
            "aMagQ": math.hypot(ar, at),
        }

    @property
    def expected_si(self) -> float:
        return self.expected[self.query_quantity_id]


def _si(raw: tuple[float, str], dimension) -> float:
    from engine.mechanics.units import normalize_quantity

    value = normalize_quantity(str(raw[0]), raw[1], "scalar", dimension).value
    assert isinstance(value, float)
    return value


BASE = PolarCase("base", (2.0, "m"), (0.5, "m/s"), (-0.2, "m/s^2"), (3.0, "rad/s"), (1.5, "rad/s^2"))
QUERY_VR = PolarCase(**{**BASE.__dict__, "case_id": "query-vr", "query_quantity_id": "vRadQ"})
QUERY_VT = PolarCase(**{**BASE.__dict__, "case_id": "query-vt", "query_quantity_id": "vTransQ"})
QUERY_AR = PolarCase(**{**BASE.__dict__, "case_id": "query-ar", "query_quantity_id": "aRadQ"})
QUERY_AT = PolarCase(**{**BASE.__dict__, "case_id": "query-at", "query_quantity_id": "aTransQ"})
QUERY_AMAG = PolarCase(**{**BASE.__dict__, "case_id": "query-amag", "query_quantity_id": "aMagQ"})
CONSTANT_RADIUS = PolarCase("constant-radius", (1.2, "m"), (0.0, "m/s"), (0.0, "m/s^2"), (4.0, "rad/s"), (0.0, "rad/s^2"), "aMagQ")
ZERO_OMEGA = PolarCase("zero-omega", (0.8, "m"), (-1.0, "m/s"), (2.0, "m/s^2"), (0.0, "rad/s"), (-3.0, "rad/s^2"), "aMagQ")
SIGNED = PolarCase("signed", (1.5, "m"), (-0.4, "m/s"), (-0.8, "m/s^2"), (-2.0, "rad/s"), (1.2, "rad/s^2"), "aMagQ")
MIXED_UNITS = PolarCase("mixed-units", (150.0, "cm"), (36.0, "km/h"), (-50.0, "cm/s^2"), (60.0, "rpm"), (2.0, "rad/s^2"), "aMagQ")
VALID_CASES = (BASE, QUERY_VR, QUERY_VT, QUERY_AR, QUERY_AT, QUERY_AMAG)
BOUNDARY_CASES = (CONSTANT_RADIUS, ZERO_OMEGA, SIGNED, MIXED_UNITS)


def _direction(axis: str) -> dict[str, object]:
    return {"kind": "axis", "frame_id": "polarFrame", "axis": axis, "sign": 1}


def _q(quantity_id: str, symbol_id: str, role: str, dimension, *, subject_id: str, component: str, value: tuple[float, str] | None) -> dict[str, object]:
    raw, unit = value if value is not None else (None, "1")
    item = _quantity(
        quantity_id, symbol_id, role, subject_id, dimension,
        value=raw, unit=unit, frame_id="polarFrame", interval_id="polarInterval",
        component=component,
        provenance="explicit_source" if value is not None else "inferred",
        evidence_refs=("polarEvidence",),
    )
    if component in {"radial", "transverse"}:
        item["direction"] = _direction(component)
    return item


def _payload(case: PolarCase) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["metadata"].update(
        system_type="diagnosticPolar", subtype="diagnostic", model_id="sameFixturePolar",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    quote = "typed radial transverse particle kinematics"
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "polarEvidence", "quote": quote,
        "source_span": {"start": 0, "end": len(quote)}, "quantity_span": None,
        "occurrence_index": 0,
    }]
    payload["entities"] = [
        {"entity_id": "particle", "primitive": "particle", "label": "particle", "aliases": [], "component_of_entity_id": None, "evidence_refs": ["polarEvidence"], "model_confidence": None},
        {"entity_id": "polarCoordinate", "primitive": "reference_frame", "label": "polar coordinate", "aliases": [], "component_of_entity_id": None, "evidence_refs": ["polarEvidence"], "model_confidence": None},
    ]
    payload["points"] = []
    payload["reference_frames"] = [{
        "frame_id": "polarFrame", "frame_type": "radial_transverse", "origin": {"kind": "world"},
        "axes": [
            {"axis": "radial", "direction": _direction("radial")},
            {"axis": "transverse", "direction": _direction("transverse")},
        ],
        "parent_frame_id": None, "translating_with_entity_id": None,
        "rotating_about_point_id": None, "generalized_coordinate_symbol_ids": [],
        "evidence_refs": ["polarEvidence"],
    }]
    payload["motion_intervals"] = [{
        "interval_id": "polarInterval", "order": 1,
        "subject_ids": ["particle", "polarCoordinate"], "frame_id": "polarFrame",
        "start_event_id": None, "end_event_id": None, "evidence_refs": ["polarEvidence"],
    }]
    payload["events"] = []
    quantities = [
        _q("radiusQ", "r", "radius", LENGTH, subject_id="polarCoordinate", component="radial", value=case.radius),
        _q("rDotQ", "rDot", "velocity", VELOCITY, subject_id="polarCoordinate", component="radial", value=case.radial_rate),
        _q("rDDotQ", "rDDot", "acceleration", ACCELERATION, subject_id="polarCoordinate", component="radial", value=case.radial_acceleration),
        _q("omegaQ", "omega", "angular_velocity", FREQUENCY, subject_id="polarCoordinate", component="transverse", value=case.omega),
        _q("alphaQ", "alpha", "angular_acceleration", ANGULAR_ACCELERATION, subject_id="polarCoordinate", component="transverse", value=case.alpha),
        _q("vRadQ", "vRad", "velocity", VELOCITY, subject_id="particle", component="radial", value=None),
        _q("vTransQ", "vTrans", "velocity", VELOCITY, subject_id="particle", component="transverse", value=None),
        _q("speedQ", "speed", "speed", VELOCITY, subject_id="particle", component="magnitude", value=None),
        _q("aRadQ", "aRad", "acceleration", ACCELERATION, subject_id="particle", component="radial", value=None),
        _q("aTransQ", "aTrans", "acceleration", ACCELERATION, subject_id="particle", component="transverse", value=None),
        _q("aMagQ", "aMag", "acceleration", ACCELERATION, subject_id="particle", component="magnitude", value=None),
    ]
    payload["quantities"] = quantities
    dimensions = {
        "radius": LENGTH, "velocity": VELOCITY, "speed": VELOCITY,
        "acceleration": ACCELERATION, "angular_velocity": FREQUENCY,
        "angular_acceleration": ANGULAR_ACCELERATION,
    }
    payload["symbols"] = [_symbol(item["symbol_id"], item["quantity_id"], dimensions[item["role"]]) for item in quantities]
    payload["geometry"] = [{
        "relation_id": "polarRadius", "kind": "radius",
        "participant_ids": ["particle", "polarCoordinate"], "expression": None,
        "quantity_ids": ["radiusQ"], "interval_id": "polarInterval",
        "evidence_refs": ["polarEvidence"],
    }]
    payload["interactions"] = []
    payload["constraints"] = []
    payload["state_conditions"] = []
    payload["assumptions"] = []
    target = next(item for item in quantities if item["quantity_id"] == case.query_quantity_id)
    output_dimension = VELOCITY if target["role"] in {"velocity", "speed"} else ACCELERATION
    output_unit = "m/s" if output_dimension == VELOCITY else "m/s^2"
    payload["queries"] = [{
        "query_id": "polarQuery",
        "target": {
            "role": target["role"], "subject_id": "particle", "point_id": None,
            "frame_id": "polarFrame", "interval_id": "polarInterval", "event_id": None,
            "component": target["component"], "direction": target["direction"],
            "target_quantity_id": target["quantity_id"],
        },
        "output_unit": output_unit, "output_dimension": output_dimension.model_dump(mode="json"),
        "shape": "scalar", "evidence_refs": ["polarEvidence"],
    }]
    payload["principle_hints"] = []
    payload["ambiguities"] = []
    payload["unsupported_features"] = []
    return payload


def _solve(case: PolarCase):
    compiled = compile_mechanics_ir(_ir(_payload(case)))
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    selected = next(item for item in result.verified_candidates if item.candidate.candidate_id == result.selected_candidate_id)
    values = {item.symbol.symbol_id: item.known_si_value for item in compiled.graph.symbols if item.known_si_value is not None}
    values.update({item.symbol_id: item.value_si for item in selected.candidate.values})
    assert isinstance(selected.candidate.query_value_si, float)
    return compiled.graph, result, selected.candidate.query_value_si, values


@pytest.mark.parametrize("case", VALID_CASES, ids=lambda item: item.case_id)
def test_polar_kinematics_components_magnitudes_units_and_residuals(case: PolarCase) -> None:
    graph, result, value, values = _solve(case)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    assert {item.law_id for item in graph.equations} == {
        "polar_velocity_radial", "polar_velocity_transverse", "planar_velocity_magnitude",
        "polar_acceleration_radial", "polar_acceleration_transverse", "planar_acceleration_magnitude",
        "translational_speed_nonnegative", "acceleration_magnitude_nonnegative",
    }
    assert result.plan.primary_backend is SolveBackendKind.polynomial_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    for symbol, quantity_id in (("vRad", "vRadQ"), ("vTrans", "vTransQ"), ("speed", "speedQ"), ("aRad", "aRadQ"), ("aTrans", "aTransQ"), ("aMag", "aMagQ")):
        assert values[symbol] == pytest.approx(case.expected[quantity_id], abs=1.0e-9)
    if case.query_quantity_id in {"speedQ", "aMagQ"}:
        roots = sorted(float(item.query_value_si) for item in result.candidate_set.candidates)
        assert len(roots) == 4  # independent speed and acceleration magnitude signs
        assert roots[:2] == pytest.approx([-value, -value])
        assert roots[2:] == pytest.approx([value, value])
        assert len(result.verified_candidates) == 1
        rejected = next(item for item in result.verification_outcomes if not item.passed)
        check = next(item for item in rejected.checks if item.kind is VerificationCheckKind.inequality)
        assert check.status is VerificationCheckStatus.failed


def test_polar_kinematics_metadata_id_and_order_invariance() -> None:
    baseline = compile_mechanics_ir(_ir(_payload(BASE)))
    assert baseline.graph is not None
    payload = _payload(BASE)
    payload["metadata"].update(system_type="wrongLabel", subtype="wrongSubtype", model_id="wrongModel")
    identifiers = _collect_fixture_identifiers(payload)
    mapping = {identifier: f"renamed{index}" for index, identifier in enumerate(sorted(identifiers), start=1)}
    _rename_fixture_identifiers(payload, mapping)
    for key in ("entities", "reference_frames", "motion_intervals", "symbols", "quantities", "geometry", "queries"):
        payload[key] = list(reversed(payload[key]))
    changed = compile_mechanics_ir(_ir(payload))
    assert changed.status is CompilerStatus.ready, changed.issues
    assert changed.graph is not None
    assert changed.graph.fingerprint == baseline.graph.fingerprint
    assert Counter(item.law_id for item in changed.graph.equations) == Counter(item.law_id for item in baseline.graph.equations)


def test_polar_kinematics_missing_derivative_topology_query_unit_and_radius_fail_closed() -> None:
    mutations = []
    for quantity_id in ("rDotQ", "rDDotQ", "alphaQ"):
        missing = _payload(BASE)
        missing["quantities"] = [item for item in missing["quantities"] if item["quantity_id"] != quantity_id]
        missing["symbols"] = [item for item in missing["symbols"] if item["quantity_id"] != quantity_id]
        mutations.append(missing)
    wrong_frame = _payload(BASE); wrong_frame["reference_frames"][0]["frame_type"] = "cartesian_2d"; mutations.append(wrong_frame)
    bad_radius = _payload(BASE); next(item for item in bad_radius["quantities"] if item["quantity_id"] == "radiusQ")["raw_value"] = "0"; mutations.append(bad_radius)
    extra_actor = _payload(BASE); extra_actor["entities"].append({"entity_id": "other", "primitive": "particle", "label": "other", "aliases": [], "component_of_entity_id": None, "evidence_refs": ["polarEvidence"], "model_confidence": None}); mutations.append(extra_actor)
    wrong_query = _payload(BASE); wrong_query["queries"][0]["target"]["subject_id"] = "polarCoordinate"; mutations.append(wrong_query)
    wrong_unit = _payload(BASE); wrong_unit["queries"][0]["output_unit"] = "N"; mutations.append(wrong_unit)
    for payload in mutations:
        assert compile_mechanics_ir(_ir(payload)).status is not CompilerStatus.ready


@pytest.mark.slow
@pytest.mark.parametrize("case", (BASE, QUERY_AMAG, CONSTANT_RADIUS, ZERO_OMEGA, SIGNED, MIXED_UNITS), ids=lambda item: item.case_id)
def test_polar_kinematics_same_fixture_legacy_parity(case: PolarCase) -> None:
    _, _, generic, _ = _solve(case)
    r = _si(case.radius, LENGTH); rdot = _si(case.radial_rate, VELOCITY)
    rddot = _si(case.radial_acceleration, ACCELERATION)
    omega = _si(case.omega, FREQUENCY); alpha = _si(case.alpha, ANGULAR_ACCELERATION)
    wants_acc = case.query_quantity_id in {"aRadQ", "aTransQ", "aMagQ"}
    legacy = PolarKinematicsSolver().solve(CanonicalProblem(
        system_type="polar_kinematics",
        knowns={
            "r": Quantity("r", r, "m"), "rdot": Quantity("rdot", rdot, "m/s"),
            "rddot": Quantity("rddot", rddot, "m/s^2"),
            "omega": Quantity("omega", omega, "rad/s"), "alpha": Quantity("alpha", alpha, "rad/s^2"),
        },
        unknowns=["acceleration" if wants_acc else "velocity"],
        requested_outputs=["acceleration" if wants_acc else "velocity"],
    ))
    assert legacy.ok is True, legacy.unsupported_reason
    assert legacy.answer is not None
    expected = case.expected["aMagQ" if wants_acc else "speedQ"]
    assert legacy.answer.numeric == pytest.approx(expected, abs=1.0e-5)
    if case.query_quantity_id in {"speedQ", "aMagQ"}:
        assert generic == pytest.approx(legacy.answer.numeric, abs=1.0e-5)
