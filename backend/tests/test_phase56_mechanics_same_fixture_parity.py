from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerIssueCode, CompilerStatus
from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
)
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.migration import (
    DifferentialStatus,
    InvarianceVariantKind,
    LabelledIRProbeVariant,
    LegacyCandidateScalar,
    LegacyDifferentialReport,
    LegacyObservation,
    LegacyTerminal,
    MechanicsMigrationInvarianceComparison,
    MechanicsMigrationProbeExecution,
    MigrationProbeTerminal,
    build_generic_result_invariance_signature,
    build_legacy_differential_report,
    compare_mechanics_ir_invariance,
    execute_mechanics_ir_probe,
)
from engine.mechanics.normalization import NormalizationResult, normalize_draft
from engine.mechanics.solver.contracts import CandidateCoverage, SolveBackendKind
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import ValidationTerminal
from engine.mechanics.verification.contracts import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity, SolverResult
from engine.solvers.newton.single_particle import SingleParticleNewtonSolver


MASS = DimensionVector(mass=1)
FORCE = DimensionVector(mass=1, length=1, time=-2)
ACCELERATION = DimensionVector(length=1, time=-2)


@dataclass(frozen=True)
class SignedForceInput:
    magnitude_si: float
    direction_sign: int | None
    evidence_quote: str

    def __post_init__(self) -> None:
        if (
            type(self.magnitude_si) is not float
            or not math.isfinite(self.magnitude_si)
            or self.magnitude_si <= 0.0
        ):
            raise ValueError("force magnitude must be one positive finite float")
        if self.direction_sign not in {-1, 1, None}:
            raise ValueError("force direction must be -1, +1, or unresolved")


@dataclass(frozen=True)
class SingleParticleSource:
    problem_text: str
    mass_si: float
    forces: tuple[SignedForceInput, ...]

    def __post_init__(self) -> None:
        if (
            type(self.mass_si) is not float
            or not math.isfinite(self.mass_si)
            or self.mass_si <= 0.0
        ):
            raise ValueError("mass must be one positive finite float")
        if type(self.forces) is not tuple or not self.forces:
            raise ValueError("at least one exact force input is required")

    @property
    def net_force_si(self) -> float:
        if any(item.direction_sign is None for item in self.forces):
            raise ValueError("unresolved force directions have no authorized net force")
        return sum(
            item.magnitude_si * item.direction_sign
            for item in self.forces
            if item.direction_sign is not None
        )


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport
    invariance: MechanicsMigrationInvarianceComparison


BASELINE = SingleParticleSource(
    problem_text=(
        "A 2 kg particle has a 10 N force in the +x direction. "
        "Find its acceleration along +x."
    ),
    mass_si=2.0,
    forces=(
        SignedForceInput(
            magnitude_si=10.0,
            direction_sign=1,
            evidence_quote="a 10 N force in the +x direction",
        ),
    ),
)


SIGNED_BALANCE = SingleParticleSource(
    problem_text=(
        "A 2 kg particle has a 10 N force in the +x direction and "
        "a 4 N force in the -x direction. Find its acceleration along +x."
    ),
    mass_si=2.0,
    forces=(
        SignedForceInput(
            magnitude_si=10.0,
            direction_sign=1,
            evidence_quote="a 10 N force in the +x direction",
        ),
        SignedForceInput(
            magnitude_si=4.0,
            direction_sign=-1,
            evidence_quote="a 4 N force in the -x direction",
        ),
    ),
)


AMBIGUOUS_DIRECTION = SingleParticleSource(
    problem_text=(
        "A 2 kg particle has a 10 N force in the +x direction and "
        "a 4 N force of unspecified direction. Find its acceleration along +x."
    ),
    mass_si=2.0,
    forces=(
        SignedForceInput(
            magnitude_si=10.0,
            direction_sign=1,
            evidence_quote="a 10 N force in the +x direction",
        ),
        SignedForceInput(
            magnitude_si=4.0,
            direction_sign=None,
            evidence_quote="a 4 N force of unspecified direction",
        ),
    ),
)


def _text_evidence(
    source_text: str,
    *,
    evidence_id: str,
    quote: str,
    quantity_token: str,
) -> dict[str, object]:
    start = source_text.index(quote)
    quantity_start = start + quote.index(quantity_token)
    return {
        "kind": "text",
        "evidence_id": evidence_id,
        "quote": quote,
        "source_span": {"start": start, "end": start + len(quote)},
        "quantity_span": {
            "start": quantity_start,
            "end": quantity_start + len(quantity_token),
        },
        "occurrence_index": source_text[:start].count(quote),
    }


def _symbol(
    symbol_id: str,
    quantity_id: str,
    dimension: DimensionVector,
) -> dict[str, object]:
    return {
        "symbol_id": symbol_id,
        "quantity_id": quantity_id,
        "dimension": dimension.model_dump(mode="json"),
        "shape": "scalar",
        "vector_length": None,
    }


def _normalize_single_particle(
    source: SingleParticleSource,
    *,
    blocking_direction_ambiguity: bool = False,
) -> NormalizationResult:
    mass_raw = f"{source.mass_si:g}"
    mass_token = f"{mass_raw} kg"
    source_evidence = [
        _text_evidence(
            source.problem_text,
            evidence_id="massEvidence",
            quote=mass_token,
            quantity_token=mass_token,
        )
    ]
    symbols = [_symbol("mA", "massA", MASS)]
    quantities: list[dict[str, object]] = [
        {
            "quantity_id": "massA",
            "symbol_id": "mA",
            "role": "mass",
            "subject_id": "bodyA",
            "shape": "scalar",
            "dimension": MASS.model_dump(mode="json"),
            "provenance": "explicit_source",
            "evidence_refs": ["massEvidence"],
            "raw_value": mass_raw,
            "raw_unit": "kg",
        }
    ]
    interactions: list[dict[str, object]] = []
    for index, force in enumerate(source.forces, start=1):
        quantity_id = f"force{index}"
        symbol_id = f"f{index}"
        evidence_id = f"forceEvidence{index}"
        raw_value = f"{force.magnitude_si:g}"
        quantity_token = f"{raw_value} N"
        source_evidence.append(
            _text_evidence(
                source.problem_text,
                evidence_id=evidence_id,
                quote=force.evidence_quote,
                quantity_token=quantity_token,
            )
        )
        symbols.append(_symbol(symbol_id, quantity_id, FORCE))
        quantities.append(
            {
                "quantity_id": quantity_id,
                "symbol_id": symbol_id,
                "role": "force",
                "subject_id": "bodyA",
                "frame_id": "frame1",
                "interval_id": "interval1",
                "component": "x",
                "direction": (
                    None
                    if force.direction_sign is None
                    else {
                        "kind": "axis",
                        "frame_id": "frame1",
                        "axis": "x",
                        "sign": force.direction_sign,
                    }
                ),
                "shape": "scalar",
                "dimension": FORCE.model_dump(mode="json"),
                "provenance": "explicit_source",
                "evidence_refs": [evidence_id],
                "raw_value": raw_value,
                "raw_unit": "N",
            }
        )
        interactions.append(
            {
                "interaction_id": f"appliedForce{index}",
                "kind": "applied_force",
                "participant_ids": ["bodyA"],
                "point_ids": [],
                "frame_id": "frame1",
                "interval_id": "interval1",
                "event_id": None,
                "quantity_ids": [quantity_id],
                "evidence_refs": [evidence_id],
            }
        )
    symbols.append(_symbol("aA", "accelerationA", ACCELERATION))
    quantities.append(
        {
            "quantity_id": "accelerationA",
            "symbol_id": "aA",
            "role": "acceleration",
            "subject_id": "bodyA",
            "frame_id": "frame1",
            "interval_id": "interval1",
            "component": "x",
            "direction": {
                "kind": "axis",
                "frame_id": "frame1",
                "axis": "x",
                "sign": 1,
            },
            "shape": "scalar",
            "dimension": ACCELERATION.model_dump(mode="json"),
            "provenance": "inferred",
            "evidence_refs": [],
        }
    )
    payload = {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnosticOnly",
            "subtype": "ignoredLabel",
            "model_id": "sameFixtureTest",
            "model_hash": None,
            "prompt_hash": None,
            "source_text_sha256": hashlib.sha256(
                source.problem_text.encode("utf-8")
            ).hexdigest(),
            "model_confidence": 0.9,
        },
        "source_assets": [],
        "source_evidence": source_evidence,
        "entities": [
            {
                "entity_id": "bodyA",
                "primitive": "particle",
                "label": "particle",
                "aliases": [],
                "component_of_entity_id": None,
                "evidence_refs": [],
                "model_confidence": 0.9,
            }
        ],
        "points": [],
        "reference_frames": [
            {
                "frame_id": "frame1",
                "frame_type": "cartesian_1d",
                "origin": {"kind": "world"},
                "axes": [
                    {
                        "axis": "x",
                        "direction": {
                            "kind": "axis",
                            "frame_id": "frame1",
                            "axis": "x",
                            "sign": 1,
                        },
                    }
                ],
                "parent_frame_id": None,
                "translating_with_entity_id": None,
                "rotating_about_point_id": None,
                "generalized_coordinate_symbol_ids": [],
                "evidence_refs": [],
            }
        ],
        "motion_intervals": [
            {
                "interval_id": "interval1",
                "order": 1,
                "subject_ids": ["bodyA"],
                "frame_id": "frame1",
                "start_event_id": None,
                "end_event_id": None,
                "evidence_refs": [],
            }
        ],
        "events": [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": [],
        "interactions": interactions,
        "constraints": [],
        "state_conditions": [],
        "queries": [
            {
                "query_id": "queryA",
                "target": {
                    "role": "acceleration",
                    "subject_id": "bodyA",
                    "point_id": None,
                    "frame_id": "frame1",
                    "interval_id": "interval1",
                    "event_id": None,
                    "component": "x",
                    "direction": {
                        "kind": "axis",
                        "frame_id": "frame1",
                        "axis": "x",
                        "sign": 1,
                    },
                    "target_quantity_id": "accelerationA",
                },
                "output_unit": "m/s^2",
                "output_dimension": ACCELERATION.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": [],
            }
        ],
        "principle_hints": [],
        "assumptions": [],
        "ambiguities": (
            [
                {
                    "ambiguity_id": "forceDirectionAmbiguity",
                    "kind": "direction",
                    "referenced_ids": [
                        f"force{index}"
                        for index in range(1, len(source.forces) + 1)
                    ],
                    "description": "The sign of one force along the x axis is unresolved.",
                    "blocking": True,
                    "evidence_refs": [],
                }
            ]
            if blocking_direction_ambiguity
            else []
        ),
        "figure_dependency": {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        },
        "unsupported_features": [],
    }
    draft = MechanicsProblemDraftV1.model_validate(payload)
    return normalize_draft(source.problem_text, draft)


def _build_single_particle_ir(source: SingleParticleSource) -> MechanicsProblemIRV1:
    normalization = _normalize_single_particle(source)
    assert normalization.terminal is ValidationTerminal.accepted
    assert normalization.accepted
    assert type(normalization.ir) is MechanicsProblemIRV1
    return normalization.ir


def _observe_single_particle_legacy(
    source: SingleParticleSource,
) -> tuple[LegacyObservation, SolverResult]:
    net_force_si = source.net_force_si
    problem = CanonicalProblem(
        system_type="deliberately_wrong_label",
        knowns={
            "m": Quantity("m", source.mass_si, "kg"),
            "F": Quantity("F", net_force_si, "N"),
        },
        unknowns=["acceleration"],
        requested_outputs=["acceleration"],
    )
    assert problem.system_type == "deliberately_wrong_label"
    assert problem.raw_text == ""
    solver = SingleParticleNewtonSolver()
    result = solver.solve(problem)
    assert result.ok is True
    assert result.answer is not None
    assert result.verification.passed is True
    primary = tuple(item for item in result.answers if item.role == "primary")
    assert len(primary) == 1
    answer = result.answer
    item = primary[0]
    assert type(answer.numeric) is float
    assert type(item.numeric) is float
    assert answer.unit is not None and item.unit is not None
    assert item.symbol == "a"
    assert item.output_key == "acceleration"
    normalized_answer = normalize_quantity(
        str(answer.numeric), answer.unit, "scalar", ACCELERATION
    )
    normalized_item = normalize_quantity(
        str(item.numeric), item.unit, "scalar", ACCELERATION
    )
    assert type(normalized_answer.value) is float
    assert normalized_answer == normalized_item
    residual = net_force_si - source.mass_si * normalized_answer.value
    residual_passed = math.isclose(residual, 0.0, rel_tol=0.0, abs_tol=1.0e-12)
    assert residual_passed is True
    observation = LegacyObservation(
        case_id=(
            "singleParticleNewtonSignedBalance"
            if len(source.forces) > 1
            else "singleParticleNewtonMFToA"
        ),
        diagnostic_kernel_id="singleParticleNewtonDirectV1",
        terminal=LegacyTerminal.solved,
        query_symbol_id="aA",
        si_unit=normalized_answer.si_unit,
        selected_scalar_si=normalized_answer.value,
        complete_candidate_scalars_si=(
            LegacyCandidateScalar(
                value_si=normalized_answer.value,
                multiplicity=1,
            ),
        ),
        residual_passed=residual_passed,
    )
    return observation, result


def _diagnostic_variant(
    ir: MechanicsProblemIRV1,
    *,
    system_type: str | None,
    source_text: str,
) -> MechanicsProblemIRV1:
    payload = ir.model_dump(mode="python", warnings="none")
    payload["metadata"]["system_type"] = system_type
    payload["metadata"]["subtype"] = None
    payload["metadata"]["source_text_sha256"] = hashlib.sha256(
        source_text.encode("utf-8")
    ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


def _same_fixture_evidence(source: SingleParticleSource) -> SameFixtureEvidence:
    ir = _build_single_particle_ir(source)
    assert "raw_text" not in type(ir).model_fields

    # Generic authority is complete before the legacy implementation is called.
    execution = execute_mechanics_ir_probe(ir)
    assert execution.terminal is MigrationProbeTerminal.solved
    assert execution.solve_result is not None
    generic_signature = build_generic_result_invariance_signature(
        execution.solve_result
    )

    observation, _ = _observe_single_particle_legacy(source)
    report = build_legacy_differential_report(execution.solve_result, observation)
    assert build_generic_result_invariance_signature(
        execution.solve_result
    ) == generic_signature

    changed = _diagnostic_variant(
        ir,
        system_type="wrongDiagnosticLabel",
        source_text=(
            "Equivalent wording changes the diagnostic family label but not the "
            "accepted physical evidence."
        ),
    )
    removed = _diagnostic_variant(
        ir,
        system_type=None,
        source_text=(
            "Equivalent wording omits the diagnostic family label while retaining "
            "the accepted physical evidence."
        ),
    )
    assert changed.source_evidence == removed.source_evidence == ir.source_evidence
    invariance = compare_mechanics_ir_invariance(
        execution,
        (
            LabelledIRProbeVariant(
                label="changedLabel",
                kind=InvarianceVariantKind.system_type_changed,
                ir=changed,
            ),
            LabelledIRProbeVariant(
                label="removedLabel",
                kind=InvarianceVariantKind.system_type_removed,
                ir=removed,
            ),
        ),
    )
    return SameFixtureEvidence(
        registry_entry="single_particle_newton",
        ir=ir,
        execution=execution,
        observation=observation,
        report=report,
        invariance=invariance,
    )


@pytest.mark.parametrize(
    "source",
    (BASELINE, SIGNED_BALANCE),
    ids=("mass-force-to-acceleration", "signed-multiple-force-balance"),
)
def test_single_particle_newton_same_fixture_full_parity_and_invariance(
    source: SingleParticleSource,
) -> None:
    evidence = _same_fixture_evidence(source)
    execution = evidence.execution
    result = execution.solve_result
    compiler = execution.compiler_result
    assert evidence.registry_entry == "single_particle_newton"
    assert compiler is not None and compiler.graph is not None
    assert execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert execution.solve_terminal is MechanicsSolveTerminal.solved

    equations = tuple(
        item
        for item in compiler.graph.equations
        if item.law_id == "particle_newton_second"
    )
    assert len(equations) == 1
    assert set(equations[0].source_quantity_ids) == {
        "massA",
        "accelerationA",
        *(f"force{index}" for index in range(1, len(source.forces) + 1)),
    }
    assert result.plan.primary_backend is SolveBackendKind.linear_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert result.candidate_set.generation_complete is True
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    assert candidate.query_symbol_id == "aA"
    assert candidate.root_multiplicity == 1
    assert candidate.query_value_si == pytest.approx(
        evidence.observation.selected_scalar_si
    )
    assert len(result.verification_outcomes) == 1
    outcome = result.verification_outcomes[0]
    assert outcome.passed is True
    residual_checks = tuple(
        check
        for check in outcome.checks
        if check.kind is VerificationCheckKind.equation_residual
    )
    assert len(residual_checks) == 1
    assert residual_checks[0].status is VerificationCheckStatus.passed
    assert residual_checks[0].measured_error == pytest.approx(0.0)

    assert evidence.observation.residual_passed is True
    assert evidence.report.status is DifferentialStatus.full_parity
    assert evidence.report.discrepancies == ()
    assert evidence.report.observation_terminal is LegacyTerminal.solved
    assert evidence.report.generic_terminal is MechanicsSolveTerminal.solved
    assert evidence.invariance.all_invariant is True
    assert all(item.matches_baseline for item in evidence.invariance.variants)


def test_single_particle_newton_rejects_unbound_multiple_force_direction() -> None:
    declared = _normalize_single_particle(
        AMBIGUOUS_DIRECTION,
        blocking_direction_ambiguity=True,
    )
    assert declared.terminal is ValidationTerminal.needs_confirmation
    assert declared.ir is None

    # Defense in depth: even if an author omits the ambiguity record, an
    # accepted IR with an unbound scalar force cannot emit a Newton balance.
    ir = _build_single_particle_ir(AMBIGUOUS_DIRECTION)
    execution = execute_mechanics_ir_probe(ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.underdetermined
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert tuple(item.code for item in execution.compiler_result.issues) == (
        CompilerIssueCode.underdetermined,
    )
    assert execution.compiler_result.graph is not None
    assert not any(
        item.law_id == "particle_newton_second"
        for item in execution.compiler_result.graph.equations
    )
