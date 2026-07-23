from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.verification import MechanicsSolveTerminal
from engine.models import CanonicalProblem, Quantity
from engine.solvers.advanced_motion import InstantCenterVelocitySolver
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
from test_phase56_mechanics_compiler import (
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
class InstantCenterCase:
    case_id: str
    radius: tuple[float, str]
    omega: tuple[float, str] | None
    target_speed: tuple[float, str] | None

    @property
    def query_quantity_id(self) -> str:
        return "omegaQ" if self.omega is None else "targetSpeedQ"

    @property
    def expected_si(self) -> float:
        r = _si(self.radius, LENGTH)
        if self.omega is None:
            assert self.target_speed is not None
            return _si(self.target_speed, VELOCITY) / r
        return _si(self.omega, FREQUENCY) * r


def _si(raw: tuple[float, str], dimension) -> float:
    from engine.mechanics.units import normalize_quantity
    value = normalize_quantity(str(raw[0]), raw[1], "scalar", dimension).value
    assert isinstance(value, float)
    return value


SOLVE_SPEED = InstantCenterCase("solve-speed", (0.5, "m"), (4.0, "rad/s"), None)
SOLVE_OMEGA = InstantCenterCase("solve-omega", (0.8, "m"), None, (3.2, "m/s"))
ZERO_OMEGA = InstantCenterCase("zero-omega", (1.2, "m"), (0.0, "rad/s"), None)
MIXED_SPEED = InstantCenterCase("mixed-speed", (50.0, "cm"), (60.0, "rpm"), None)
MIXED_OMEGA = InstantCenterCase("mixed-omega", (750.0, "mm"), None, (5.4, "km/h"))
VALID_CASES = (SOLVE_SPEED, SOLVE_OMEGA, ZERO_OMEGA, MIXED_SPEED, MIXED_OMEGA)


def _direction(axis: str) -> dict[str, object]:
    return {"kind": "axis", "frame_id": "rigidFrame", "axis": axis, "sign": 1}


def _q(quantity_id: str, symbol_id: str, role: str, dimension, *, point_id: str, value: tuple[float, str] | None) -> dict[str, object]:
    raw, unit = value if value is not None else (None, "1")
    return _quantity(
        quantity_id, symbol_id, role, "body", dimension,
        value=raw, unit=unit, frame_id="rigidFrame", interval_id="rigidInterval",
        point_id=point_id, component="magnitude",
        provenance="explicit_source" if value is not None else "inferred",
        evidence_refs=("instantEvidence",),
    )


def _payload(case: InstantCenterCase) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["metadata"].update(
        system_type="diagnosticInstantCenter", subtype="diagnosticVelocity",
        model_id="sameFixtureInstantCenter",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "instantEvidence",
        "quote": "typed instantaneous center and target point radius",
        "source_span": {"start": 0, "end": 49}, "quantity_span": None,
        "occurrence_index": 0,
    }]
    payload["entities"] = [{
        "entity_id": "body", "primitive": "rigid_body", "label": "body", "aliases": [],
        "component_of_entity_id": None, "evidence_refs": ["instantEvidence"], "model_confidence": None,
    }]
    payload["points"] = [
        {"point_id": "instantCenter", "role": "reference", "owner_entity_id": "body",
         "frame_id": "rigidFrame", "label": "IC", "evidence_refs": ["instantEvidence"]},
        {"point_id": "targetPoint", "role": "material", "owner_entity_id": "body",
         "frame_id": "rigidFrame", "label": "B", "evidence_refs": ["instantEvidence"]},
    ]
    payload["reference_frames"] = [{
        "frame_id": "rigidFrame", "frame_type": "cartesian_2d", "origin": {"kind": "world"},
        "axes": [
            {"axis": "x", "direction": _direction("x")},
            {"axis": "y", "direction": _direction("y")},
        ],
        "parent_frame_id": None, "translating_with_entity_id": None,
        "rotating_about_point_id": None, "generalized_coordinate_symbol_ids": [],
        "evidence_refs": ["instantEvidence"],
    }]
    payload["motion_intervals"] = [{
        "interval_id": "rigidInterval", "order": 1, "subject_ids": ["body"],
        "frame_id": "rigidFrame", "start_event_id": None, "end_event_id": None,
        "evidence_refs": ["instantEvidence"],
    }]
    payload["events"] = []
    quantities = [
        _q("radiusQ", "radius", "radius", LENGTH, point_id="targetPoint", value=case.radius),
        _q("omegaQ", "omega", "angular_velocity", FREQUENCY, point_id="instantCenter", value=case.omega),
        _q("centerSpeedQ", "centerSpeed", "speed", VELOCITY, point_id="instantCenter", value=(0.0, "m/s")),
        _q("targetSpeedQ", "targetSpeed", "speed", VELOCITY, point_id="targetPoint", value=case.target_speed),
    ]
    payload["quantities"] = quantities
    payload["symbols"] = [
        _symbol(item["symbol_id"], item["quantity_id"],
                LENGTH if item["role"] == "radius" else FREQUENCY if item["role"] == "angular_velocity" else VELOCITY)
        for item in quantities
    ]
    payload["geometry"] = [{
        "relation_id": "instantRadius", "kind": "radius",
        "participant_ids": ["body", "instantCenter", "targetPoint"],
        "expression": None, "quantity_ids": ["radiusQ"],
        "interval_id": "rigidInterval", "evidence_refs": ["instantEvidence"],
    }]
    payload["interactions"] = []
    payload["constraints"] = []
    payload["state_conditions"] = [{
        "state_condition_id": "centerAtRest", "kind": "motion", "state": "at_rest",
        "subject_id": "body", "interval_id": "rigidInterval", "event_id": None,
        "expression": None, "quantity_ids": ["centerSpeedQ"],
        "evidence_refs": ["instantEvidence"],
    }]
    payload["assumptions"] = [{
        "assumption_id": "instantCenterAuthority", "kind": "instantaneous_center",
        "subject_id": "body", "interval_id": "rigidInterval", "disposition": "approved",
        "proposed_role": None, "proposed_value": None, "proposed_unit": None,
        "reason": "The stated point is the instantaneous center for this instant.",
        "evidence_refs": ["instantEvidence"],
    }]
    target = next(item for item in quantities if item["quantity_id"] == case.query_quantity_id)
    target_dimension = FREQUENCY if target["role"] == "angular_velocity" else VELOCITY
    payload["queries"] = [{
        "query_id": "instantQuery",
        "target": {
            "role": target["role"], "subject_id": "body",
            "point_id": target["point_id"], "frame_id": "rigidFrame",
            "interval_id": "rigidInterval", "event_id": None,
            "component": "magnitude", "direction": None,
            "target_quantity_id": target["quantity_id"],
        },
        "output_unit": "rad/s" if target_dimension == FREQUENCY else "m/s",
        "output_dimension": target_dimension.model_dump(mode="json"),
        "shape": "scalar", "evidence_refs": ["instantEvidence"],
    }]
    payload["principle_hints"] = []
    payload["ambiguities"] = []
    payload["unsupported_features"] = []
    return payload


def _solve(case: InstantCenterCase):
    compiled = compile_mechanics_ir(_ir(_payload(case)))
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    selected = next(item for item in result.verified_candidates if item.candidate.candidate_id == result.selected_candidate_id)
    assert isinstance(selected.candidate.query_value_si, float)
    return compiled.graph, result, selected.candidate.query_value_si


@pytest.mark.parametrize("case", VALID_CASES, ids=lambda item: item.case_id)
def test_instant_center_solves_speed_or_angular_speed_with_units_and_residuals(case: InstantCenterCase) -> None:
    graph, result, value = _solve(case)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    assert {item.law_id for item in graph.equations} == {
        "rigid_instant_center_speed", "translational_speed_nonnegative", "angular_speed_nonnegative",
    }
    assert result.plan.primary_backend is SolveBackendKind.linear_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert len(result.verified_candidates) == 1


def test_instant_center_metadata_id_and_order_invariance() -> None:
    baseline = compile_mechanics_ir(_ir(_payload(SOLVE_SPEED)))
    assert baseline.graph is not None
    payload = _payload(SOLVE_SPEED)
    payload["metadata"].update(system_type="wrong", subtype="wrong", model_id="wrong")
    identifiers = _collect_fixture_identifiers(payload)
    mapping = {identifier: f"renamed{index}" for index, identifier in enumerate(sorted(identifiers), start=1)}
    _rename_fixture_identifiers(payload, mapping)
    for key in (
        "entities", "points", "reference_frames", "motion_intervals", "symbols", "quantities",
        "geometry", "state_conditions", "assumptions", "queries",
    ):
        payload[key] = list(reversed(payload[key]))
    changed = compile_mechanics_ir(_ir(payload))
    assert changed.status is CompilerStatus.ready, changed.issues
    assert changed.graph is not None
    assert changed.graph.fingerprint == baseline.graph.fingerprint
    assert Counter(item.law_id for item in changed.graph.equations) == Counter(item.law_id for item in baseline.graph.equations)


def test_instant_center_zero_radius_missing_authority_wrong_state_query_and_extra_actor_fail_closed() -> None:
    mutations = []
    zero_radius = _payload(SOLVE_SPEED)
    item = next(item for item in zero_radius["quantities"] if item["quantity_id"] == "radiusQ")
    item.update(raw_value="0.0", raw_unit="m", si_value=0.0, si_unit="m")
    mutations.append(zero_radius)
    no_authority = _payload(SOLVE_SPEED)
    no_authority["assumptions"] = []
    mutations.append(no_authority)
    wrong_state = _payload(SOLVE_SPEED)
    wrong_state["state_conditions"][0]["state"] = "moving"
    mutations.append(wrong_state)
    both_unknown = _payload(SOLVE_SPEED)
    omega = next(item for item in both_unknown["quantities"] if item["quantity_id"] == "omegaQ")
    omega.update(raw_value=None, raw_unit=None, si_value=None, si_unit=None, provenance="inferred")
    mutations.append(both_unknown)
    wrong_query = _payload(SOLVE_SPEED)
    wrong_query["queries"][0]["target"]["point_id"] = "instantCenter"
    mutations.append(wrong_query)
    extra_actor = _payload(SOLVE_SPEED)
    extra_actor["entities"].append({
        "entity_id": "other", "primitive": "particle", "label": "other", "aliases": [],
        "component_of_entity_id": None, "evidence_refs": ["instantEvidence"], "model_confidence": None,
    })
    mutations.append(extra_actor)
    for payload in mutations:
        assert compile_mechanics_ir(_ir(payload)).status is not CompilerStatus.ready


@pytest.mark.slow
@pytest.mark.parametrize("case", VALID_CASES, ids=lambda item: item.case_id)
def test_instant_center_same_fixture_legacy_parity(case: InstantCenterCase) -> None:
    _, _, generic = _solve(case)
    knowns = {"r": Quantity("r", _si(case.radius, LENGTH), "m")}
    if case.omega is not None:
        knowns["omega"] = Quantity("omega", _si(case.omega, FREQUENCY), "rad/s")
        unknown = "velocity"
    else:
        assert case.target_speed is not None
        knowns["v"] = Quantity("v", _si(case.target_speed, VELOCITY), "m/s")
        unknown = "angular_velocity"
    legacy = InstantCenterVelocitySolver().solve(CanonicalProblem(
        system_type="instant_center_velocity", knowns=knowns,
        unknowns=[unknown], requested_outputs=[unknown],
    ))
    assert legacy.ok is True, legacy.unsupported_reason
    assert legacy.answer is not None
    assert generic == pytest.approx(legacy.answer.numeric, abs=1.0e-5)
