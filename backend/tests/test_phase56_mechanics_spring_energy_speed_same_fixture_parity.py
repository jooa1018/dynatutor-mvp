from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.math_ast import Add, DimensionVector, Equality, Inequality, Multiply, Power
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity
from engine.solvers.energy_vibration import SpringEnergySpeedSolver
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
from test_phase56_mechanics_compiler import (
    ENERGY,
    LENGTH,
    MASS,
    STIFFNESS,
    VELOCITY,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
    compile_mechanics_ir,
)


@dataclass(frozen=True)
class SpringEnergyCase:
    case_id: str
    mass: tuple[float, str]
    stiffness: tuple[float, str]
    start_displacement: tuple[float, str]
    end_displacement: tuple[float, str]
    start_speed: tuple[float, str]
    displacement_sign: int = 1

    @property
    def expected_si(self) -> float:
        mass = _si(self.mass, MASS)
        stiffness = _si(self.stiffness, STIFFNESS)
        x0 = _si(self.start_displacement, LENGTH)
        x1 = _si(self.end_displacement, LENGTH)
        v0 = _si(self.start_speed, VELOCITY)
        radicand = v0 * v0 + stiffness * (x0 * x0 - x1 * x1) / mass
        return math.sqrt(radicand) if radicand >= 0.0 else math.nan


def _si(raw: tuple[float, str], dimension: DimensionVector) -> float:
    from engine.mechanics.units import normalize_quantity

    value = normalize_quantity(str(raw[0]), raw[1], "scalar", dimension).value
    assert isinstance(value, float)
    return value


BASE = SpringEnergyCase(
    "base", (2.0, "kg"), (200.0, "N/m"), (0.1, "m"), (0.0, "m"), (0.0, "m/s")
)
NEGATIVE_COMPRESSION = SpringEnergyCase(
    "negative-compression", (2.0, "kg"), (200.0, "N/m"), (0.1, "m"), (0.0, "m"), (0.0, "m/s"), -1
)
ZERO_DEFORMATION = SpringEnergyCase(
    "zero-deformation", (3.0, "kg"), (120.0, "N/m"), (0.0, "m"), (0.0, "m"), (2.0, "m/s")
)
NONZERO_INITIAL = SpringEnergyCase(
    "nonzero-initial", (4.0, "kg"), (180.0, "N/m"), (0.2, "m"), (0.05, "m"), (1.5, "m/s")
)
MIXED_UNITS = SpringEnergyCase(
    "mixed-units", (2000.0, "g"), (200.0, "N/m"), (10.0, "cm"), (2.0, "cm"), (360.0, "cm/s")
)
LEGACY_MIXED_UNITS = SpringEnergyCase(
    "legacy-mixed-units", (2000.0, "g"), (200.0, "N/m"), (10.0, "cm"), (0.0, "cm"), (0.0, "cm/s")
)
IMPOSSIBLE = SpringEnergyCase(
    "impossible", (2.0, "kg"), (200.0, "N/m"), (0.01, "m"), (0.2, "m"), (0.0, "m/s")
)
VALID_CASES = (BASE, NEGATIVE_COMPRESSION, ZERO_DEFORMATION, NONZERO_INITIAL, MIXED_UNITS)


def _direction(sign: int) -> dict[str, object]:
    return {
        "kind": "axis",
        "frame_id": "springFrame",
        "axis": "x",
        "sign": sign,
    }


def _q(
    quantity_id: str,
    symbol_id: str,
    role: str,
    subject_id: str,
    dimension: DimensionVector,
    *,
    value: tuple[float, str] | None = None,
    component: str = "unspecified",
    sign: int | None = None,
    scoped: bool = True,
) -> dict[str, object]:
    raw_value, unit = value if value is not None else (None, "1")
    item = _quantity(
        quantity_id,
        symbol_id,
        role,
        subject_id,
        dimension,
        value=raw_value,
        unit=unit,
        frame_id="springFrame" if scoped else None,
        interval_id="springInterval" if scoped else None,
        component=component,
        provenance="explicit_source" if value is not None else "inferred",
        evidence_refs=("springEvidence",),
    )
    if sign is not None:
        item["direction"] = _direction(sign)
    return item


def _payload(case: SpringEnergyCase) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["metadata"].update(
        system_type="diagnosticSpringEnergy",
        subtype="diagnosticSpeed",
        model_id="sameFixtureSpringEnergy",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    payload["source_evidence"] = [
        {
            "kind": "text",
            "evidence_id": "springEvidence",
            "quote": "typed spring energy interval",
            "source_span": {"start": 0, "end": 28},
            "quantity_span": None,
            "occurrence_index": 0,
        }
    ]
    payload["entities"] = [
        {
            "entity_id": "body",
            "primitive": "particle",
            "label": "body",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": ["springEvidence"],
            "model_confidence": None,
        },
        {
            "entity_id": "spring",
            "primitive": "spring",
            "label": "spring",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": ["springEvidence"],
            "model_confidence": None,
        },
    ]
    payload["points"] = []
    payload["reference_frames"] = [
        {
            "frame_id": "springFrame",
            "frame_type": "cartesian_1d",
            "origin": {"kind": "world"},
            "axes": [
                {"axis": "x", "direction": _direction(1)},
            ],
            "parent_frame_id": None,
            "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": ["springEvidence"],
        }
    ]
    payload["motion_intervals"] = [
        {
            "interval_id": "springInterval",
            "order": 1,
            "subject_ids": ["body", "spring"],
            "frame_id": "springFrame",
            "start_event_id": None,
            "end_event_id": None,
            "evidence_refs": ["springEvidence"],
        }
    ]
    payload["events"] = []
    quantities = [
        _q("massQ", "mass", "mass", "body", MASS, value=case.mass, scoped=False),
        _q("stiffnessQ", "stiffness", "stiffness", "spring", STIFFNESS, value=case.stiffness, scoped=False),
        _q("xStartQ", "xStart", "displacement", "spring", LENGTH, value=case.start_displacement, component="x", sign=case.displacement_sign),
        _q("xEndQ", "xEnd", "displacement", "spring", LENGTH, value=case.end_displacement, component="x", sign=1),
        _q("speedStartQ", "speedStart", "speed", "body", VELOCITY, value=case.start_speed, component="magnitude"),
        _q("speedEndQ", "speedEnd", "speed", "body", VELOCITY, component="magnitude"),
        _q("kineticStartQ", "kineticStart", "energy", "body", ENERGY, component="magnitude"),
        _q("kineticEndQ", "kineticEnd", "energy", "body", ENERGY, component="magnitude"),
        _q("springEnergyStartQ", "springEnergyStart", "energy", "spring", ENERGY, component="magnitude"),
        _q("springEnergyEndQ", "springEnergyEnd", "energy", "spring", ENERGY, component="magnitude"),
    ]
    payload["symbols"] = [
        _symbol(item["symbol_id"], item["quantity_id"], DimensionVector.model_validate(item["dimension"]))
        for item in quantities
    ]
    payload["quantities"] = quantities
    payload["geometry"] = [
        {
            "relation_id": "springAttachment",
            "kind": "attached",
            "participant_ids": ["body", "spring"],
            "expression": None,
            "quantity_ids": [],
            "interval_id": "springInterval",
            "evidence_refs": ["springEvidence"],
        }
    ]
    payload["interactions"] = [
        {
            "interaction_id": "springInteraction",
            "kind": "spring",
            "participant_ids": ["body", "spring"],
            "point_ids": [],
            "frame_id": "springFrame",
            "interval_id": "springInterval",
            "event_id": None,
            "quantity_ids": [
                "stiffnessQ",
                "xStartQ",
                "xEndQ",
                "springEnergyStartQ",
                "springEnergyEndQ",
            ],
            "evidence_refs": ["springEvidence"],
        }
    ]
    payload["constraints"] = []
    payload["state_conditions"] = [
        {
            "state_condition_id": "bodyInitial",
            "kind": "initial",
            "state": "active",
            "subject_id": "body",
            "interval_id": "springInterval",
            "event_id": None,
            "expression": None,
            "quantity_ids": ["speedStartQ", "kineticStartQ"],
            "evidence_refs": ["springEvidence"],
        },
        {
            "state_condition_id": "bodyFinal",
            "kind": "final",
            "state": "active",
            "subject_id": "body",
            "interval_id": "springInterval",
            "event_id": None,
            "expression": None,
            "quantity_ids": ["speedEndQ", "kineticEndQ"],
            "evidence_refs": ["springEvidence"],
        },
        {
            "state_condition_id": "springInitial",
            "kind": "initial",
            "state": "active",
            "subject_id": "spring",
            "interval_id": "springInterval",
            "event_id": None,
            "expression": None,
            "quantity_ids": ["xStartQ", "springEnergyStartQ"],
            "evidence_refs": ["springEvidence"],
        },
        {
            "state_condition_id": "springFinal",
            "kind": "final",
            "state": "active",
            "subject_id": "spring",
            "interval_id": "springInterval",
            "event_id": None,
            "expression": None,
            "quantity_ids": ["xEndQ", "springEnergyEndQ"],
            "evidence_refs": ["springEvidence"],
        },
    ]
    payload["assumptions"] = [
        {
            "assumption_id": "linearSpring",
            "kind": "linear_spring",
            "subject_id": "spring",
            "interval_id": "springInterval",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "The evidenced spring is linear over the interval.",
            "evidence_refs": ["springEvidence"],
        },
        {
            "assumption_id": "kineticEnergyAuthority",
            "kind": "kinetic_energy",
            "subject_id": "body",
            "interval_id": "springInterval",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "The particle translational kinetic energy is used.",
            "evidence_refs": ["springEvidence"],
        },
        {
            "assumption_id": "noEnergyLoss",
            "kind": "no_energy_loss",
            "subject_id": "body",
            "interval_id": "springInterval",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "No nonconservative energy transfer occurs.",
            "evidence_refs": ["springEvidence"],
        },
    ]
    payload["queries"] = [
        {
            "query_id": "springSpeedQuery",
            "target": {
                "role": "speed",
                "subject_id": "body",
                "point_id": None,
                "frame_id": "springFrame",
                "interval_id": "springInterval",
                "event_id": None,
                "component": "magnitude",
                "direction": None,
                "target_quantity_id": "speedEndQ",
            },
            "output_unit": "m/s",
            "output_dimension": VELOCITY.model_dump(mode="json"),
            "shape": "scalar",
            "evidence_refs": ["springEvidence"],
        }
    ]
    return payload


def _compile(case: SpringEnergyCase):
    return compile_mechanics_ir(_ir(_payload(case)))


def _solve(case: SpringEnergyCase):
    compiled = _compile(case)
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    selected = next(
        item
        for item in result.verified_candidates
        if item.candidate.candidate_id == result.selected_candidate_id
    )
    values = {item.symbol_id: item.value_si for item in selected.candidate.values}
    assert isinstance(selected.candidate.query_value_si, float)
    return compiled.graph, result, selected.candidate.query_value_si, values


@pytest.mark.parametrize("case", VALID_CASES, ids=lambda item: item.case_id)
def test_spring_energy_limits_signs_initial_state_and_units(case: SpringEnergyCase) -> None:
    graph, result, value, values = _solve(case)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    laws = [item.law_id for item in graph.equations]
    assert laws.count("spring_potential") == 2
    assert laws.count("kinetic_energy") == 2
    assert laws.count("mechanical_energy_conservation") == 1
    assert laws.count("translational_speed_nonnegative") == 1
    assert result.plan.primary_backend is SolveBackendKind.polynomial_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert values["kineticStart"] + values["springEnergyStart"] == pytest.approx(
        values["kineticEnd"] + values["springEnergyEnd"], abs=1.0e-9
    )


def test_spring_energy_preserves_both_speed_roots_then_verifies_nonnegative() -> None:
    _, result, value, _ = _solve(NONZERO_INITIAL)
    roots = sorted(float(item.query_value_si) for item in result.candidate_set.candidates)
    assert roots == pytest.approx([-NONZERO_INITIAL.expected_si, NONZERO_INITIAL.expected_si])
    assert len(result.verification_outcomes) == 2
    assert len(result.verified_candidates) == 1
    assert value == pytest.approx(NONZERO_INITIAL.expected_si)
    rejected = next(item for item in result.verification_outcomes if not item.passed)
    check = next(item for item in rejected.checks if item.kind is VerificationCheckKind.inequality)
    assert check.status is VerificationCheckStatus.failed


def test_impossible_final_deformation_fails_without_clamp() -> None:
    compiled = _compile(IMPOSSIBLE)
    assert compiled.status is CompilerStatus.ready and compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is not MechanicsSolveTerminal.solved
    assert result.selected_candidate_id is None
    assert result.verified_candidates == ()


@pytest.mark.parametrize("assumption_id", ("linearSpring", "kineticEnergyAuthority", "noEnergyLoss"))
def test_missing_energy_authority_fails_closed(assumption_id: str) -> None:
    payload = _payload(BASE)
    payload["assumptions"] = [
        item for item in payload["assumptions"] if item["assumption_id"] != assumption_id
    ]
    compiled = compile_mechanics_ir(_ir(payload))
    assert compiled.status is not CompilerStatus.ready


def test_invalid_mass_stiffness_query_unit_and_extra_interaction_fail_closed() -> None:
    for quantity_id in ("massQ", "stiffnessQ"):
        payload = _payload(BASE)
        item = next(item for item in payload["quantities"] if item["quantity_id"] == quantity_id)
        item["raw_value"] = "0.0"
        item["si_value"] = 0.0
        assert compile_mechanics_ir(_ir(payload)).status is CompilerStatus.invalid

    wrong_unit = _payload(BASE)
    wrong_unit["queries"][0]["output_unit"] = "kg"
    assert compile_mechanics_ir(_ir(wrong_unit)).status is CompilerStatus.invalid

    extra = _payload(BASE)
    extra["interactions"].append(
        {
            "interaction_id": "extraForce",
            "kind": "applied_force",
            "participant_ids": ["body"],
            "point_ids": [],
            "frame_id": "springFrame",
            "interval_id": "springInterval",
            "event_id": None,
            "quantity_ids": [],
            "evidence_refs": ["springEvidence"],
        }
    )
    assert compile_mechanics_ir(_ir(extra)).status is not CompilerStatus.ready


def test_wrong_state_query_binding_and_metadata_have_no_answer_authority() -> None:
    wrong_state = _payload(BASE)
    state = next(item for item in wrong_state["state_conditions"] if item["state_condition_id"] == "bodyFinal")
    state["quantity_ids"] = ["speedStartQ", "kineticEndQ"]
    assert compile_mechanics_ir(_ir(wrong_state)).status is not CompilerStatus.ready

    wrong_query = _payload(BASE)
    wrong_query["queries"][0]["target"]["target_quantity_id"] = "speedStartQ"
    assert compile_mechanics_ir(_ir(wrong_query)).status is not CompilerStatus.ready

    first = _compile(BASE)
    changed = _payload(BASE)
    changed["metadata"].update(
        system_type="flat_curve_friction",
        subtype="unrelated",
        model_id="different",
        source_text_sha256="f" * 64,
    )
    second = compile_mechanics_ir(_ir(changed))
    assert first.status is second.status is CompilerStatus.ready
    assert first.graph is not None and second.graph is not None
    assert first.graph.fingerprint == second.graph.fingerprint


def test_spring_energy_identifier_and_record_order_invariance() -> None:
    original_ir = _ir(_payload(BASE))
    original = compile_mechanics_ir(original_ir)
    assert original.status is CompilerStatus.ready, original.issues
    assert original.graph is not None

    reordered_payload = original_ir.model_dump(mode="python", warnings="none")
    for collection_name in (
        'source_evidence',
        'entities',
        'reference_frames',
        'motion_intervals',
        'symbols',
        'quantities',
        'geometry',
        'interactions',
        'state_conditions',
        'assumptions',
    ):
        reordered_payload[collection_name] = list(
            reversed(reordered_payload[collection_name])
        )
    reordered = compile_mechanics_ir(_ir(reordered_payload))

    identifiers = sorted(_collect_fixture_identifiers(reordered_payload))
    mapping = {
        identifier: f"renamedSpringEnergyIdentifier{index}"
        for index, identifier in enumerate(identifiers, start=1)
    }
    renamed_payload = _rename_fixture_identifiers(reordered_payload, mapping)
    assert isinstance(renamed_payload, dict)
    renamed = compile_mechanics_ir(_ir(renamed_payload))

    for compiled in (reordered, renamed):
        assert compiled.status is CompilerStatus.ready, compiled.issues
        assert compiled.graph is not None
        assert compiled.graph.fingerprint == original.graph.fingerprint
        assert compiled.graph.selected_equation_ids == original.graph.selected_equation_ids
        assert Counter(item.law_id for item in compiled.graph.equations) == Counter(
            item.law_id for item in original.graph.equations
        )


@pytest.mark.slow
@pytest.mark.parametrize("case", (BASE, NEGATIVE_COMPRESSION, LEGACY_MIXED_UNITS), ids=lambda item: item.case_id)
def test_spring_energy_speed_same_fixture_legacy_parity(case: SpringEnergyCase) -> None:
    _, _, generic, _ = _solve(case)
    mass = _si(case.mass, MASS)
    stiffness = _si(case.stiffness, STIFFNESS)
    displacement = _si(case.start_displacement, LENGTH)
    legacy = SpringEnergySpeedSolver().solve(
        CanonicalProblem(
            system_type="spring_energy",
            raw_text="",
            knowns={
                "m": Quantity("m", mass, "kg"),
                "k": Quantity("k", stiffness, "N/m"),
                "x": Quantity("x", displacement, "m"),
            },
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
        )
    )
    assert legacy.ok is True, legacy.unsupported_reason
    assert legacy.answer is not None
    assert legacy.answer.numeric == pytest.approx(generic, abs=1.0e-5)
