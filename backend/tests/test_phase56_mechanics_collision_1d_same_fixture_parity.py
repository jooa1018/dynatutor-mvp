from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
from typing import Callable

import pytest

from engine.mechanics.compiler import (
    CompilerIssueCode,
    CompilerStatus,
    MechanicsCompiler,
    authorize_validated_mechanics_ir,
)
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
)
from engine.mechanics.math_ast import (
    Add,
    DimensionVector,
    Equality,
    Multiply,
    Negate,
    Subtract,
    SymbolRef,
)
from engine.mechanics.migration import (
    DifferentialStatus,
    LegacyCandidateScalar,
    LegacyObservation,
    LegacyTerminal,
    MechanicsMigrationProbeExecution,
    MigrationProbeTerminal,
    build_generic_result_invariance_signature,
    build_legacy_differential_report,
    execute_mechanics_ir_probe,
)
from engine.mechanics.normalization import NormalizationResult, normalize_draft
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.solver.contracts import (
    _graph_event_ids,
    _graph_plan_event_ids,
)
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import ValidationTerminal
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
    render_canonical_si_unit,
)
from engine.models import CanonicalProblem, Quantity, SolverResult
from engine.solvers.collision import Collision1DSolver
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
from test_phase56_mechanics_incline_same_fixture_parity import (
    DIMENSIONLESS,
    MASS,
    _quantity,
    _symbol,
    _text_evidence,
)


VELOCITY = DimensionVector(length=1, time=-1)

SYSTEM_ID = "impactSystem"
PARTICLE_A_ID = "particleA"
PARTICLE_B_ID = "particleB"
FRAME_ID = "impactFrame"
INTERVAL_ID = "impactInterval"
START_EVENT_ID = "impactStart"
END_EVENT_ID = "impactEnd"
ASSUMPTION_ID = "isolatedImpact"
APPROVED_ASSUMPTION_IDS = (ASSUMPTION_ID,)


@dataclass(frozen=True)
class RawScalar:
    value: str
    unit: str


@dataclass(frozen=True)
class CollisionSource:
    mass_a_si: float
    mass_b_si: float
    velocity_a_si: float
    velocity_b_si: float
    restitution_si: float
    query_particle: str = "A"
    mass_a_raw: RawScalar = RawScalar("2", "kg")
    mass_b_raw: RawScalar = RawScalar("3", "kg")
    speed_a_raw: RawScalar = RawScalar("4", "m/s")
    speed_b_raw: RawScalar = RawScalar("0", "m/s")
    restitution_raw: RawScalar = RawScalar("50", "%")
    paraphrase_prefix: str = ""

    def __post_init__(self) -> None:
        if self.query_particle not in {"A", "B"}:
            raise ValueError("query particle must be A or B")
        if any(
            type(item) is not float or not math.isfinite(item)
            for item in (
                self.mass_a_si,
                self.mass_b_si,
                self.velocity_a_si,
                self.velocity_b_si,
                self.restitution_si,
            )
        ):
            raise ValueError("collision source scalars must be finite floats")

    @property
    def expected_pair(self) -> tuple[float, float]:
        denominator = self.mass_a_si + self.mass_b_si
        a_after = (
            self.mass_a_si * self.velocity_a_si
            + self.mass_b_si * self.velocity_b_si
            - self.mass_b_si
            * self.restitution_si
            * (self.velocity_a_si - self.velocity_b_si)
        ) / denominator
        b_after = a_after + self.restitution_si * (
            self.velocity_a_si - self.velocity_b_si
        )
        return (a_after, b_after)

    @property
    def expected_query(self) -> float:
        return self.expected_pair[0 if self.query_particle == "A" else 1]

    @property
    def query_symbol_id(self) -> str:
        return "vAAfter" if self.query_particle == "A" else "vBAfter"

    @property
    def problem_text(self) -> str:
        direction_a = "+x" if self.velocity_a_si >= 0.0 else "-x"
        direction_b = "+x" if self.velocity_b_si >= 0.0 else "-x"
        return " ".join(
            item
            for item in (
                self.paraphrase_prefix,
                "Particles A and B form the impact system.",
                f"Particle A has mass {self.mass_a_raw.value} {self.mass_a_raw.unit}.",
                f"Particle B has mass {self.mass_b_raw.value} {self.mass_b_raw.unit}.",
                "Use a world-origin one-dimensional frame with positive x to the right.",
                f"Before impact A moves in {direction_a} with speed {self.speed_a_raw.value} {self.speed_a_raw.unit}.",
                f"Before impact B moves in {direction_b} with speed {self.speed_b_raw.value} {self.speed_b_raw.unit}.",
                "The two particles collide during the stated impact interval.",
                f"The coefficient of restitution is {self.restitution_raw.value} {self.restitution_raw.unit}.",
                "External impulse on the impact system is negligible during collision.",
                f"Find particle {self.query_particle}'s post-impact x velocity.",
            )
            if item
        )


def _source(
    *,
    mass_a: float = 2.0,
    mass_b: float = 3.0,
    velocity_a: float = 4.0,
    velocity_b: float = 0.0,
    restitution: float = 0.5,
    query_particle: str = "A",
    raw: tuple[RawScalar, RawScalar, RawScalar, RawScalar, RawScalar] | None = None,
    paraphrase_prefix: str = "",
) -> CollisionSource:
    if raw is None:
        raw = (
            RawScalar(repr(float(mass_a)), "kg"),
            RawScalar(repr(float(mass_b)), "kg"),
            RawScalar(repr(abs(float(velocity_a))), "m/s"),
            RawScalar(repr(abs(float(velocity_b))), "m/s"),
            RawScalar(repr(100.0 * float(restitution)), "%"),
        )
    return CollisionSource(
        mass_a_si=float(mass_a),
        mass_b_si=float(mass_b),
        velocity_a_si=float(velocity_a),
        velocity_b_si=float(velocity_b),
        restitution_si=float(restitution),
        query_particle=query_particle,
        mass_a_raw=raw[0],
        mass_b_raw=raw[1],
        speed_a_raw=raw[2],
        speed_b_raw=raw[3],
        restitution_raw=raw[4],
        paraphrase_prefix=paraphrase_prefix,
    )


BASELINE = _source()
QUERY_B = _source(query_particle="B")
PERFECTLY_INELASTIC = _source(restitution=0.0)
EQUAL_MASS_ELASTIC = _source(mass_b=2.0, restitution=1.0)
UNEQUAL_MOVING = _source(mass_a=5.0, mass_b=1.5, velocity_a=7.0, velocity_b=2.0, restitution=0.35)
EQUAL_PARTIAL = _source(mass_b=2.0, velocity_a=6.0, velocity_b=1.0, restitution=0.25)
HEAD_ON = _source(velocity_a=5.0, velocity_b=-3.0, restitution=0.8)
BOTH_NEGATIVE = _source(velocity_a=-1.0, velocity_b=-4.0, restitution=0.6)
MIXED_UNITS = _source(
    mass_a=2.0,
    mass_b=3.0,
    velocity_a=5.0,
    velocity_b=1.0,
    restitution=0.4,
    raw=(
        RawScalar("2000", "g"),
        RawScalar("3", "kg"),
        RawScalar("18", "km/h"),
        RawScalar("100", "cm/s"),
        RawScalar("40", "%"),
    ),
)
MASS_SCALED = _source(mass_a=20.0, mass_b=30.0)
GALILEAN_SHIFT = _source(velocity_a=14.0, velocity_b=10.0)
REFLECTED_SWAPPED = _source(
    mass_a=3.0,
    mass_b=2.0,
    velocity_a=0.0,
    velocity_b=-4.0,
    restitution=0.5,
    query_particle="B",
)

SLOW_CASES = (
    BASELINE,
    QUERY_B,
    PERFECTLY_INELASTIC,
    EQUAL_MASS_ELASTIC,
    UNEQUAL_MOVING,
    EQUAL_PARTIAL,
    HEAD_ON,
    BOTH_NEGATIVE,
    MIXED_UNITS,
    MASS_SCALED,
    GALILEAN_SHIFT,
    REFLECTED_SWAPPED,
)

PayloadMutation = Callable[[dict[str, object]], None]


def _axis_direction(sign: int = 1) -> dict[str, object]:
    return {
        "kind": "axis",
        "frame_id": FRAME_ID,
        "axis": "x",
        "sign": sign,
    }


def _draft_payload(source: CollisionSource) -> dict[str, object]:
    system_quote = "Particles A and B form the impact system."
    mass_a_quote = f"Particle A has mass {source.mass_a_raw.value} {source.mass_a_raw.unit}."
    mass_b_quote = f"Particle B has mass {source.mass_b_raw.value} {source.mass_b_raw.unit}."
    frame_quote = "Use a world-origin one-dimensional frame with positive x to the right."
    direction_a = "+x" if source.velocity_a_si >= 0.0 else "-x"
    direction_b = "+x" if source.velocity_b_si >= 0.0 else "-x"
    velocity_a_quote = f"Before impact A moves in {direction_a} with speed {source.speed_a_raw.value} {source.speed_a_raw.unit}."
    velocity_b_quote = f"Before impact B moves in {direction_b} with speed {source.speed_b_raw.value} {source.speed_b_raw.unit}."
    collision_quote = "The two particles collide during the stated impact interval."
    restitution_quote = f"The coefficient of restitution is {source.restitution_raw.value} {source.restitution_raw.unit}."
    isolation_quote = "External impulse on the impact system is negligible during collision."
    query_quote = f"Find particle {source.query_particle}'s post-impact x velocity."
    evidence_specs = (
        ("systemEvidence", system_quote, None),
        ("massAEvidence", mass_a_quote, f"{source.mass_a_raw.value} {source.mass_a_raw.unit}"),
        ("massBEvidence", mass_b_quote, f"{source.mass_b_raw.value} {source.mass_b_raw.unit}"),
        ("frameEvidence", frame_quote, None),
        ("velocityAEvidence", velocity_a_quote, f"{source.speed_a_raw.value} {source.speed_a_raw.unit}"),
        ("velocityBEvidence", velocity_b_quote, f"{source.speed_b_raw.value} {source.speed_b_raw.unit}"),
        ("collisionEvidence", collision_quote, None),
        ("restitutionEvidence", restitution_quote, f"{source.restitution_raw.value} {source.restitution_raw.unit}"),
        ("isolationEvidence", isolation_quote, None),
        ("queryEvidence", query_quote, None),
    )
    evidence = [
        _text_evidence(
            source.problem_text,
            evidence_id=evidence_id,
            quote=quote,
            quantity_token=quantity_token,
        )
        for evidence_id, quote, quantity_token in evidence_specs
    ]
    velocity_a_before = _quantity(
        "velocityABefore", "uA", "velocity", PARTICLE_A_ID, VELOCITY,
        frame_id=FRAME_ID, interval_id=INTERVAL_ID, component="x",
        direction=_axis_direction(1 if source.velocity_a_si >= 0.0 else -1),
        provenance="explicit_source", evidence_refs=("velocityAEvidence", "frameEvidence", "collisionEvidence"),
        raw_value=source.speed_a_raw.value, raw_unit=source.speed_a_raw.unit,
    )
    velocity_a_before["event_id"] = START_EVENT_ID
    velocity_b_before = _quantity(
        "velocityBBefore", "uB", "velocity", PARTICLE_B_ID, VELOCITY,
        frame_id=FRAME_ID, interval_id=INTERVAL_ID, component="x",
        direction=_axis_direction(1 if source.velocity_b_si >= 0.0 else -1),
        provenance="explicit_source", evidence_refs=("velocityBEvidence", "frameEvidence", "collisionEvidence"),
        raw_value=source.speed_b_raw.value, raw_unit=source.speed_b_raw.unit,
    )
    velocity_b_before["event_id"] = START_EVENT_ID
    after_quantities: list[dict[str, object]] = []
    for particle, suffix, symbol in (
        (PARTICLE_A_ID, "A", "vAAfter"),
        (PARTICLE_B_ID, "B", "vBAfter"),
    ):
        item = _quantity(
            f"velocity{suffix}After", symbol, "velocity", particle, VELOCITY,
            frame_id=FRAME_ID, interval_id=INTERVAL_ID, component="x",
            direction=_axis_direction(1), provenance="inferred",
            evidence_refs=("collisionEvidence", "queryEvidence"),
        )
        item["event_id"] = END_EVENT_ID
        after_quantities.append(item)
    quantities = [
        _quantity(
            "massA", "mA", "mass", PARTICLE_A_ID, MASS,
            provenance="explicit_source", evidence_refs=("massAEvidence", "systemEvidence"),
            raw_value=source.mass_a_raw.value, raw_unit=source.mass_a_raw.unit,
        ),
        _quantity(
            "massB", "mB", "mass", PARTICLE_B_ID, MASS,
            provenance="explicit_source", evidence_refs=("massBEvidence", "systemEvidence"),
            raw_value=source.mass_b_raw.value, raw_unit=source.mass_b_raw.unit,
        ),
        velocity_a_before,
        velocity_b_before,
        *after_quantities,
        _quantity(
            "restitution", "e", "coefficient_restitution", SYSTEM_ID,
            DIMENSIONLESS, frame_id=FRAME_ID, interval_id=INTERVAL_ID,
            provenance="explicit_source", evidence_refs=("restitutionEvidence", "collisionEvidence"),
            raw_value=source.restitution_raw.value, raw_unit=source.restitution_raw.unit,
        ),
    ]
    query_suffix = source.query_particle
    query_particle_id = PARTICLE_A_ID if query_suffix == "A" else PARTICLE_B_ID
    query_quantity_id = f"velocity{query_suffix}After"
    query_symbol_id = source.query_symbol_id
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnosticCollisionLabel",
            "subtype": "diagnosticImpactSubtype",
            "model_id": "sameFixtureCollisionTest",
            "source_text_sha256": hashlib.sha256(source.problem_text.encode("utf-8")).hexdigest(),
        },
        "source_assets": [],
        "source_evidence": evidence,
        "entities": [
            {"entity_id": SYSTEM_ID, "primitive": "system", "evidence_refs": ["systemEvidence", "collisionEvidence", "isolationEvidence"]},
            {"entity_id": PARTICLE_A_ID, "primitive": "particle", "component_of_entity_id": SYSTEM_ID, "evidence_refs": ["systemEvidence", "massAEvidence", "velocityAEvidence", "collisionEvidence"]},
            {"entity_id": PARTICLE_B_ID, "primitive": "particle", "component_of_entity_id": SYSTEM_ID, "evidence_refs": ["systemEvidence", "massBEvidence", "velocityBEvidence", "collisionEvidence"]},
        ],
        "reference_frames": [
            {"frame_id": FRAME_ID, "frame_type": "cartesian_1d", "origin": {"kind": "world"}, "axes": [{"axis": "x", "direction": _axis_direction(1)}], "evidence_refs": ["frameEvidence"]}
        ],
        "motion_intervals": [
            {"interval_id": INTERVAL_ID, "order": 1, "subject_ids": [SYSTEM_ID, PARTICLE_A_ID, PARTICLE_B_ID], "frame_id": FRAME_ID, "start_event_id": START_EVENT_ID, "end_event_id": END_EVENT_ID, "evidence_refs": ["collisionEvidence", "isolationEvidence"]}
        ],
        "events": [
            {"event_id": START_EVENT_ID, "kind": "collision_start", "subject_ids": [PARTICLE_A_ID, PARTICLE_B_ID], "interval_ids": [INTERVAL_ID], "evidence_refs": ["collisionEvidence", "velocityAEvidence", "velocityBEvidence"]},
            {"event_id": END_EVENT_ID, "kind": "collision_end", "subject_ids": [PARTICLE_A_ID, PARTICLE_B_ID], "interval_ids": [INTERVAL_ID], "evidence_refs": ["collisionEvidence", "queryEvidence"]},
        ],
        "points": [],
        "symbols": [
            _symbol("mA", "massA", MASS),
            _symbol("mB", "massB", MASS),
            _symbol("uA", "velocityABefore", VELOCITY),
            _symbol("uB", "velocityBBefore", VELOCITY),
            _symbol("vAAfter", "velocityAAfter", VELOCITY),
            _symbol("vBAfter", "velocityBAfter", VELOCITY),
            _symbol("e", "restitution", DIMENSIONLESS),
        ],
        "quantities": quantities,
        "geometry": [],
        "interactions": [
            {"interaction_id": "collisionInteraction", "kind": "collision", "participant_ids": [PARTICLE_A_ID, PARTICLE_B_ID], "point_ids": [], "frame_id": FRAME_ID, "interval_id": INTERVAL_ID, "quantity_ids": [item["quantity_id"] for item in quantities], "evidence_refs": ["collisionEvidence", "restitutionEvidence"]}
        ],
        "constraints": [],
        "state_conditions": [],
        "queries": [
            {"query_id": "queryAfterVelocity", "target": {"role": "velocity", "subject_id": query_particle_id, "frame_id": FRAME_ID, "interval_id": INTERVAL_ID, "event_id": END_EVENT_ID, "component": "x", "direction": _axis_direction(1), "target_quantity_id": query_quantity_id}, "output_unit": "m/s", "output_dimension": VELOCITY.model_dump(mode="json"), "shape": "scalar", "evidence_refs": ["queryEvidence"]}
        ],
        "principle_hints": [],
        "assumptions": [
            {"assumption_id": ASSUMPTION_ID, "kind": "external_impulse_negligible", "subject_id": SYSTEM_ID, "interval_id": INTERVAL_ID, "disposition": "approved", "reason": "The source explicitly states negligible external impulse on the complete impact system.", "evidence_refs": ["isolationEvidence"]}
        ],
        "ambiguities": [],
        "figure_dependency": {"level": "none", "missing_information": [], "evidence_refs": []},
        "unsupported_features": [],
    }


def _normalize(
    source: CollisionSource,
    *,
    mutation: PayloadMutation | None = None,
    approved_assumption_ids: tuple[str, ...] = APPROVED_ASSUMPTION_IDS,
) -> NormalizationResult:
    payload = _draft_payload(source)
    if mutation is not None:
        mutation(payload)
    return normalize_draft(
        source.problem_text,
        MechanicsProblemDraftV1.model_validate(payload),
        approved_assumption_ids=approved_assumption_ids,
    )


def _build_ir(source: CollisionSource = BASELINE) -> MechanicsProblemIRV1:
    result = _normalize(source)
    assert result.terminal is ValidationTerminal.accepted, result.issues
    assert type(result.ir) is MechanicsProblemIRV1
    return result.ir


def _compile(ir: MechanicsProblemIRV1, approved: tuple[str, ...] = APPROVED_ASSUMPTION_IDS):
    return MechanicsCompiler().compile(
        ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(ir),
        approved_assumption_ids=approved,
    )


def _execute(ir: MechanicsProblemIRV1, approved: tuple[str, ...] = APPROVED_ASSUMPTION_IDS) -> MechanicsMigrationProbeExecution:
    return execute_mechanics_ir_probe(ir, approved_assumption_ids=approved)


def _candidate_values(execution: MechanicsMigrationProbeExecution) -> dict[str, float]:
    result = execution.solve_result
    assert result is not None
    assert len(result.candidate_set.candidates) == 1
    return {
        item.symbol_id: float(item.value_si)
        for item in result.candidate_set.candidates[0].values
    }


def _forbid_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> SolverResult:
        raise AssertionError("generic collision tests must not call legacy")

    monkeypatch.setattr(Collision1DSolver, "solve", forbidden)


@pytest.mark.parametrize("source", (BASELINE, QUERY_B, PERFECTLY_INELASTIC, EQUAL_MASS_ELASTIC, HEAD_ON, BOTH_NEGATIVE))
def test_collision_1d_exact_typed_profile_compiles_without_legacy(
    source: CollisionSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    compiled = _compile(_build_ir(source))
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    assert Counter(item.law_id for item in compiled.graph.equations) == Counter(
        {"system_momentum_conservation": 1, "direct_restitution": 1}
    )
    assert compiled.graph.rank.unknown_count == 2
    assert compiled.graph.rank.structural_rank == 2
    assert len(compiled.graph.selected_equation_ids) == 2
    assert all(item.scope.entity_ids == (SYSTEM_ID, PARTICLE_A_ID, PARTICLE_B_ID) for item in compiled.graph.equations)
    assert all(item.scope.event_ids == (END_EVENT_ID, START_EVENT_ID) for item in compiled.graph.equations)
    momentum = next(item for item in compiled.graph.equations if item.law_id == "system_momentum_conservation")
    assert momentum.assumption_ids == (ASSUMPTION_ID,)
    assert "isolationEvidence" in momentum.source_evidence_ids
    structural_evidence = {
        "systemEvidence",
        "massAEvidence",
        "massBEvidence",
        "frameEvidence",
        "velocityAEvidence",
        "velocityBEvidence",
        "collisionEvidence",
        "restitutionEvidence",
        "queryEvidence",
    }
    assert structural_evidence <= set(momentum.source_evidence_ids)
    restitution = next(item for item in compiled.graph.equations if item.law_id == "direct_restitution")
    assert structural_evidence <= set(restitution.source_evidence_ids)


def test_collision_1d_plan_treats_boundaries_as_static_but_retains_graph_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    execution = _execute(_build_ir())
    assert execution.terminal is MigrationProbeTerminal.solved
    result = execution.solve_result
    assert result is not None
    assert result.terminal is MechanicsSolveTerminal.solved
    assert result.plan.event_ids == ()
    assert result.plan.structure.has_event_condition is True
    assert result.plan.primary_backend is SolveBackendKind.linear_symbolic
    assert all(item.scope.event_ids == (END_EVENT_ID, START_EVENT_ID) for item in result.plan.graph.equations)
    assert all(
        check.kind is not VerificationCheckKind.event_order
        for item in result.verified_candidates
        for check in item.outcome.checks
    )
    assert all(
        check.status is VerificationCheckStatus.passed
        for item in result.verified_candidates
        for check in item.outcome.checks
    )


def test_collision_1d_generic_solution_and_independent_residuals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    source = HEAD_ON
    execution = _execute(_build_ir(source))
    assert execution.terminal is MigrationProbeTerminal.solved
    values = _candidate_values(execution)
    expected_a, expected_b = source.expected_pair
    assert values["vAAfter"] == pytest.approx(expected_a, abs=1.0e-10)
    assert values["vBAfter"] == pytest.approx(expected_b, abs=1.0e-10)
    momentum = source.mass_a_si * source.velocity_a_si + source.mass_b_si * source.velocity_b_si - source.mass_a_si * values["vAAfter"] - source.mass_b_si * values["vBAfter"]
    restitution = values["vBAfter"] - values["vAAfter"] - source.restitution_si * (source.velocity_a_si - source.velocity_b_si)
    reduced_mass = source.mass_a_si * source.mass_b_si / (source.mass_a_si + source.mass_b_si)
    kinetic_loss = 0.5 * reduced_mass * (1.0 - source.restitution_si**2) * (source.velocity_a_si - source.velocity_b_si) ** 2
    assert momentum == pytest.approx(0.0, abs=1.0e-10)
    assert restitution == pytest.approx(0.0, abs=1.0e-10)
    assert kinetic_loss >= 0.0


@pytest.mark.parametrize(
    ("case_id", "mutation"),
    (
        ("system-primitive", lambda payload: payload["entities"][0].update(primitive="particle")),
        ("particle-parent", lambda payload: payload["entities"][1].update(component_of_entity_id=None)),
        ("frame-origin", lambda payload: payload["reference_frames"][0].update(origin={"kind": "entity", "entity_id": SYSTEM_ID})),
        ("axis-sign", lambda payload: payload["reference_frames"][0]["axes"][0]["direction"].update(sign=-1)),
        ("event-kind", lambda payload: payload["events"][1].update(kind="finish")),
        ("event-subject", lambda payload: payload["events"][0].update(subject_ids=[PARTICLE_A_ID])),
        ("event-time", lambda payload: payload["events"][0].update(time_quantity_id="velocityABefore")),
        ("interaction-points", lambda payload: payload["interactions"][0].update(point_ids=["ghostPoint"])),
        ("interaction-quantity", lambda payload: payload["interactions"][0]["quantity_ids"].pop()),
        ("mass-scope", lambda payload: payload["quantities"][0].update(frame_id=FRAME_ID)),
        ("before-provenance", lambda payload: payload["quantities"][2].update(provenance="inferred", raw_value=None, raw_unit=None)),
        ("after-provenance", lambda payload: payload["quantities"][4].update(provenance="explicit_source", raw_value="1", raw_unit="m/s")),
        ("coefficient-subject", lambda payload: payload["quantities"][6].update(subject_id=PARTICLE_A_ID)),
        ("assumption-subject", lambda payload: payload["assumptions"][0].update(subject_id=PARTICLE_A_ID)),
        ("query-event", lambda payload: payload["queries"][0]["target"].update(event_id=START_EVENT_ID)),
        ("query-output-unit", lambda payload: payload["queries"][0].update(output_unit="kg")),
        ("extra-geometry", lambda payload: payload["geometry"].append({"relation_id": "decoyRelation", "kind": "topology_connects", "participant_ids": [PARTICLE_A_ID, PARTICLE_B_ID], "quantity_ids": [], "interval_id": INTERVAL_ID, "evidence_refs": ["collisionEvidence"]})),
    ),
)
def test_collision_1d_structural_near_misses_fail_closed_without_legacy(
    case_id: str,
    mutation: PayloadMutation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del case_id
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=mutation)
    if normalization.terminal is not ValidationTerminal.accepted:
        assert normalization.ir is None
        return
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None


@pytest.mark.parametrize(
    "source",
    (
        _source(mass_a=0.0),
        _source(mass_b=-1.0),
        _source(restitution=-0.01),
        _source(restitution=1.01),
        _source(velocity_a=2.0, velocity_b=2.0),
    ),
)
def test_collision_1d_invalid_domains_reject_before_legacy(
    source: CollisionSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    compiled = _compile(normalization.ir)
    assert compiled.status is CompilerStatus.invalid
    assert compiled.graph is None
    assert compiled.issues[0].code is CompilerIssueCode.invalid_domain


def test_collision_1d_system_assumption_requires_external_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, approved_assumption_ids=())
    assert normalization.terminal is ValidationTerminal.needs_confirmation
    assert normalization.ir is None
    ir = _build_ir()
    compiled = _compile(ir, approved=())
    assert compiled.status is CompilerStatus.unsupported
    assert compiled.graph is None
    assert compiled.issues[0].code is CompilerIssueCode.requires_specialized_model


def test_collision_1d_metadata_and_text_do_not_author_physics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    baseline = _build_ir()
    payload = baseline.model_dump(mode="python", warnings="none")
    payload["metadata"] = payload["metadata"].model_copy(update={"system_type": "adversarialLabel", "subtype": "notCollision"}) if hasattr(payload["metadata"], "model_copy") else {**payload["metadata"], "system_type": "adversarialLabel", "subtype": "notCollision"}
    variant = MechanicsProblemIRV1.model_validate(payload)
    original = _compile(baseline)
    changed = _compile(variant)
    assert original.status is changed.status is CompilerStatus.ready
    assert original.graph is not None and changed.graph is not None
    assert original.graph.fingerprint == changed.graph.fingerprint


def test_collision_1d_identifier_rename_preserves_graph_and_solution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    original_ir = _build_ir()
    original = _compile(original_ir)
    payload = original_ir.model_dump(mode="python", warnings="none")
    identifiers = sorted(_collect_fixture_identifiers(payload))
    mapping = {identifier: f"renamedCollisionIdentifier{index}" for index, identifier in enumerate(identifiers, 1)}
    renamed_payload = _rename_fixture_identifiers(payload, mapping)
    assert isinstance(renamed_payload, dict)
    renamed_ir = MechanicsProblemIRV1.model_validate(renamed_payload)
    renamed = _compile(renamed_ir, approved=(mapping[ASSUMPTION_ID],))
    assert original.status is renamed.status is CompilerStatus.ready
    assert original.graph is not None and renamed.graph is not None
    assert original.graph.fingerprint == renamed.graph.fingerprint
    original_execution = _execute(original_ir)
    renamed_execution = _execute(renamed_ir, approved=(mapping[ASSUMPTION_ID],))
    assert original_execution.terminal is renamed_execution.terminal is MigrationProbeTerminal.solved
    assert original_execution.solve_result is not None
    assert renamed_execution.solve_result is not None
    assert (
        original_execution.solve_result.candidate_set.coverage
        is renamed_execution.solve_result.candidate_set.coverage
        is CandidateCoverage.exhaustive_symbolic
    )
    assert renamed_execution.solve_result.plan.query_symbol_id == mapping["vAAfter"]
    original_values = _candidate_values(original_execution)
    renamed_values = _candidate_values(renamed_execution)
    assert renamed_values[mapping["vAAfter"]] == pytest.approx(original_values["vAAfter"])
    assert renamed_values[mapping["vBAfter"]] == pytest.approx(original_values["vBAfter"])


def test_collision_1d_participant_list_reversal_preserves_solution_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    baseline = _execute(_build_ir())
    normalization = _normalize(
        BASELINE,
        mutation=lambda payload: payload["interactions"][0]["participant_ids"].reverse(),
    )
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    reversed_execution = _execute(normalization.ir)
    assert baseline.terminal is reversed_execution.terminal is MigrationProbeTerminal.solved
    assert _candidate_values(baseline) == pytest.approx(_candidate_values(reversed_execution))


def _replace_graph_equation(graph, law_id: str, expression: Equality):
    equations = tuple(
        item.model_copy(update={"expression": expression})
        if item.law_id == law_id
        else item
        for item in graph.equations
    )
    return graph.model_copy(update={"equations": equations})


def _crossed_momentum_graph(graph):
    equation = next(
        item for item in graph.equations
        if item.law_id == "system_momentum_conservation"
    )
    assert isinstance(equation.expression.left, Add)
    assert isinstance(equation.expression.right, Add)
    first, second = equation.expression.right.terms
    assert isinstance(first, Multiply) and isinstance(second, Multiply)
    crossed = Add(
        terms=(
            first.model_copy(update={"factors": (first.factors[0], second.factors[1])}),
            second.model_copy(update={"factors": (second.factors[0], first.factors[1])}),
        )
    )
    expression = equation.expression.model_copy(update={"right": crossed})
    return _replace_graph_equation(graph, equation.law_id, expression)


def _mixed_event_restitution_graph(graph):
    symbols = {item.symbol.symbol_id: item.symbol.dimension for item in graph.symbols}
    ref = lambda identifier: SymbolRef(symbol_id=identifier, dimension=symbols[identifier])
    expression = Equality(
        left=Subtract(left=ref("vAAfter"), right=ref("uA")),
        right=Negate(
            operand=Multiply(
                factors=(
                    ref("e"),
                    Subtract(left=ref("vBAfter"), right=ref("uB")),
                )
            )
        ),
    )
    return _replace_graph_equation(graph, "direct_restitution", expression)


def _narrow_scope_graph(graph):
    equations = []
    applications = []
    for item in graph.equations:
        scope = item.scope.model_copy(update={"entity_ids": (PARTICLE_A_ID, PARTICLE_B_ID)})
        equations.append(item.model_copy(update={"scope": scope}))
    for item in graph.applications:
        scope = item.scope.model_copy(update={"entity_ids": (PARTICLE_A_ID, PARTICLE_B_ID)})
        applications.append(item.model_copy(update={"scope": scope}))
    return graph.model_copy(update={"equations": tuple(equations), "applications": tuple(applications)})


def _application_evidence_spoof_graph(graph):
    first, *rest = graph.applications
    changed = first.model_copy(update={"source_evidence_ids": ("spoofEvidence",)})
    return graph.model_copy(update={"applications": (changed, *rest)})


def _application_cost_spoof_graph(graph):
    first, *rest = graph.applications
    changed = first.model_copy(update={"complexity_cost": first.complexity_cost + 1})
    return graph.model_copy(update={"applications": (changed, *rest)})


def _all_cost_spoof_graph(graph):
    equations = tuple(
        item.model_copy(update={"complexity_cost": item.complexity_cost + 1})
        for item in graph.equations
    )
    applications = tuple(
        item.model_copy(update={"complexity_cost": item.complexity_cost + 1})
        for item in graph.applications
    )
    return graph.model_copy(update={"equations": equations, "applications": applications})


def _equation_dimension_spoof_graph(graph):
    equations = tuple(
        item.model_copy(update={"dimension": DimensionVector()})
        if item.law_id == "direct_restitution"
        else item
        for item in graph.equations
    )
    return graph.model_copy(update={"equations": equations})


def _mass_domain_spoof_graph(graph):
    symbols = tuple(
        item.model_copy(update={"known_si_value": 0.0})
        if item.quantity_role == "mass" and item.subject_id == PARTICLE_A_ID
        else item
        for item in graph.symbols
    )
    return graph.model_copy(update={"symbols": symbols})


def _coefficient_domain_spoof_graph(graph):
    symbols = tuple(
        item.model_copy(update={"known_si_value": 1.5})
        if item.quantity_role == "coefficient_restitution"
        else item
        for item in graph.symbols
    )
    return graph.model_copy(update={"symbols": symbols})


def _incidence_spoof_graph(graph):
    return graph.model_copy(update={"incidence": graph.incidence[:-1]})


@pytest.mark.parametrize(
    "mutate",
    (
        _crossed_momentum_graph,
        _mixed_event_restitution_graph,
        _narrow_scope_graph,
        _application_evidence_spoof_graph,
        _application_cost_spoof_graph,
        _all_cost_spoof_graph,
        _equation_dimension_spoof_graph,
        _mass_domain_spoof_graph,
        _coefficient_domain_spoof_graph,
        _incidence_spoof_graph,
    ),
)
def test_static_collision_event_waiver_rejects_synthetic_graph_spoofs(
    mutate: Callable[[object], object],
) -> None:
    compiled = _compile(_build_ir())
    assert compiled.graph is not None
    graph = mutate(compiled.graph)
    assert _graph_event_ids(graph) == (END_EVENT_ID, START_EVENT_ID)
    assert _graph_plan_event_ids(graph) == (END_EVENT_ID, START_EVENT_ID)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: (
            payload.update(interactions=[], events=[]),
        ),
        lambda payload: (
            payload.update(interactions=[]),
            payload["quantities"].pop(),
            payload["symbols"].pop(),
        ),
        lambda payload: (
            payload.update(events=[]),
            payload["quantities"].pop(),
            payload["symbols"].pop(),
        ),
    ),
)
def test_collision_candidate_cannot_escape_by_deleting_paired_signals(
    mutation: PayloadMutation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=mutation)
    if normalization.terminal is not ValidationTerminal.accepted:
        assert normalization.ir is None
        return
    assert type(normalization.ir) is MechanicsProblemIRV1
    compiled = _compile(normalization.ir)
    assert compiled.graph is None
    assert compiled.status in {CompilerStatus.invalid, CompilerStatus.unsupported}


def _legacy_observation(source: CollisionSource) -> LegacyObservation:
    problem = CanonicalProblem(
        system_type="collision_1d",
        knowns={
            "m1": Quantity("m1", source.mass_a_si, "kg"),
            "m2": Quantity("m2", source.mass_b_si, "kg"),
            "v1": Quantity("v1", source.velocity_a_si, "m/s"),
            "v2": Quantity("v2", source.velocity_b_si, "m/s"),
            "e": Quantity("e", source.restitution_si, None),
        },
        unknowns=["v1_after", "v2_after"],
        requested_outputs=["v1_after", "v2_after"],
    )
    result = Collision1DSolver().solve(problem)
    assert result.ok is True, result.unsupported_reason
    expected_a, expected_b = source.expected_pair
    assert len(result.answers) == 2
    by_symbol = {item.symbol: item.numeric for item in result.answers}
    assert by_symbol["v1'"] == pytest.approx(round(expected_a, 6), abs=1.0e-12)
    assert by_symbol["v2'"] == pytest.approx(round(expected_b, 6), abs=1.0e-12)
    normalized = normalize_quantity(repr(source.expected_query), "m/s", "scalar", VELOCITY)
    assert type(normalized.value) is float
    return LegacyObservation(
        case_id="collision" + hashlib.sha256(source.problem_text.encode("utf-8")).hexdigest()[:32],
        diagnostic_kernel_id="collision1DDirectV1",
        terminal=LegacyTerminal.solved,
        query_symbol_id=source.query_symbol_id,
        si_unit=render_canonical_si_unit(VELOCITY),
        selected_scalar_si=normalized.value,
        complete_candidate_scalars_si=(LegacyCandidateScalar(value_si=normalized.value, multiplicity=1),),
        residual_passed=True,
    )


@pytest.mark.slow
@pytest.mark.parametrize("source", SLOW_CASES)
def test_collision_1d_same_fixture_full_parity(source: CollisionSource) -> None:
    ir = _build_ir(source)
    execution = _execute(ir)
    assert execution.terminal is MigrationProbeTerminal.solved
    assert execution.solve_result is not None
    frozen_signature = build_generic_result_invariance_signature(execution.solve_result)
    frozen_values = tuple(sorted(_candidate_values(execution).items()))
    expected_a, expected_b = source.expected_pair
    values = dict(frozen_values)
    assert values["vAAfter"] == pytest.approx(expected_a, abs=1.0e-9)
    assert values["vBAfter"] == pytest.approx(expected_b, abs=1.0e-9)
    assert execution.solve_result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    observation = _legacy_observation(source)
    report = build_legacy_differential_report(execution.solve_result, observation)
    assert report.status is DifferentialStatus.full_parity
    assert build_generic_result_invariance_signature(execution.solve_result) == frozen_signature
    assert tuple(sorted(_candidate_values(execution).items())) == frozen_values
