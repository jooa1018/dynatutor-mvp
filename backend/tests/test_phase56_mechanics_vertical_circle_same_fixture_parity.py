from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
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
from engine.mechanics.math_ast import DimensionVector, Equality, LiteralNode
from engine.mechanics.migration import (
    DifferentialStatus,
    LegacyCandidateScalar,
    LegacyDifferentialReport,
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
from engine.mechanics.units import normalize_quantity
from engine.mechanics.validation import ValidationTerminal
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
    render_canonical_si_unit,
)
from engine.models import CanonicalProblem, Quantity, SolverResult
from engine.solvers.vertical_circle import VerticalCircleSolver
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
from test_phase56_mechanics_incline_same_fixture_parity import (
    ACCELERATION,
    FORCE,
    MASS,
    _axis_binding,
    _quantity,
    _symbol,
    _text_evidence,
)


LENGTH = DimensionVector(length=1)
SPEED = DimensionVector(length=1, time=-1)

INTERVAL_ID = "circleInterval"
FRAME_ID = "circleFrame"
PARTICLE_ID = "circleParticle"
CARRIER_ID = "circleCarrier"
WORLD_ID = "world"
PARTICLE_POINT_ID = "particlePoint"
CENTER_POINT_ID = "centerPoint"


@dataclass(frozen=True)
class RawScalar:
    value: str
    unit: str


@dataclass(frozen=True)
class VerticalCircleSource:
    problem_text: str
    carrier: str
    position: str
    mode: str
    mass_si: float | None
    radius_si: float
    gravity_si: float
    speed_si: float | None
    mass_raw: RawScalar | None
    radius_raw: RawScalar
    gravity_raw: RawScalar
    speed_raw: RawScalar | None

    def __post_init__(self) -> None:
        if self.carrier not in {"rope", "contact"}:
            raise ValueError("carrier must be rope or contact")
        if self.position not in {"top", "bottom"}:
            raise ValueError("position must be top or bottom")
        if self.mode not in {"reaction", "minimum_speed"}:
            raise ValueError("mode must be reaction or minimum_speed")
        if self.mode == "minimum_speed":
            if self.position != "top" or self.mass_si is not None:
                raise ValueError("minimum-speed fixtures are top and omit mass")
            if self.speed_si is not None or self.speed_raw is not None:
                raise ValueError("minimum-speed fixtures have no source speed")
        else:
            if self.mass_si is None or self.mass_raw is None:
                raise ValueError("reaction fixtures require source mass")
            if self.speed_si is None or self.speed_raw is None:
                raise ValueError("reaction fixtures require source speed")

    @property
    def gravity_sign(self) -> int:
        return 1 if self.position == "top" else -1

    @property
    def expected_si(self) -> float:
        if self.mode == "minimum_speed":
            return math.sqrt(self.gravity_si * self.radius_si)
        assert self.mass_si is not None and self.speed_si is not None
        return self.mass_si * (
            self.speed_si**2 / self.radius_si
            - self.gravity_sign * self.gravity_si
        )

    @property
    def query_symbol_id(self) -> str:
        return "vMin" if self.mode == "minimum_speed" else "C"

    @property
    def query_dimension(self) -> DimensionVector:
        return SPEED if self.mode == "minimum_speed" else FORCE


def _source(
    *,
    carrier: str = "rope",
    position: str = "top",
    mode: str = "reaction",
    mass_si: float = 2.0,
    radius_si: float = 1.25,
    gravity_si: float = 9.81,
    speed_si: float = 5.0,
    raw_scalars: tuple[RawScalar, RawScalar, RawScalar, RawScalar] | None = None,
    paraphrase_prefix: str = "",
) -> VerticalCircleSource:
    if raw_scalars is None:
        raw_scalars = (
            RawScalar(repr(float(mass_si)), "kg"),
            RawScalar(repr(float(radius_si)), "m"),
            RawScalar(repr(float(gravity_si)), "m/s^2"),
            RawScalar(repr(float(speed_si)), "m/s"),
        )
    mass_raw, radius_raw, gravity_raw, speed_raw = raw_scalars
    carrier_sentence = (
        "A taut rope connects the particle to the fixed circle center."
        if carrier == "rope"
        else "The particle remains in contact with a fixed circular surface."
    )
    location_sentence = (
        f"The particle is at the {position} of the vertical circle."
    )
    orientation_sentence = (
        "Use a local tangential-normal frame at the particle, with positive "
        "normal directed inward toward the fixed circle center."
    )
    radius_sentence = (
        f"The circular-path radius is {radius_raw.value} {radius_raw.unit}."
    )
    gravity_sentence = (
        f"Take g = {gravity_raw.value} {gravity_raw.unit}."
    )
    if mode == "minimum_speed":
        mass_sentence = ""
        motion_sentence = (
            "At the limiting active-carrier condition the inward carrier "
            "reaction is zero."
        )
        query_sentence = (
            "Find the unique nonnegative minimum tangential speed."
        )
        bound_mass_si: float | None = None
        bound_mass_raw: RawScalar | None = None
        bound_speed_si: float | None = None
        bound_speed_raw: RawScalar | None = None
    else:
        mass_sentence = (
            f"The particle mass is {mass_raw.value} {mass_raw.unit}."
        )
        motion_sentence = (
            f"Its tangential speed there is {speed_raw.value} {speed_raw.unit}."
        )
        query_sentence = (
            "Find the inward rope tension."
            if carrier == "rope"
            else "Find the inward contact normal force."
        )
        bound_mass_si = float(mass_si)
        bound_mass_raw = mass_raw
        bound_speed_si = float(speed_si)
        bound_speed_raw = speed_raw
    problem_text = " ".join(
        part
        for part in (
            paraphrase_prefix,
            mass_sentence,
            radius_sentence,
            gravity_sentence,
            carrier_sentence,
            location_sentence,
            orientation_sentence,
            motion_sentence,
            query_sentence,
        )
        if part
    ).strip()
    return VerticalCircleSource(
        problem_text=problem_text,
        carrier=carrier,
        position=position,
        mode=mode,
        mass_si=bound_mass_si,
        radius_si=float(radius_si),
        gravity_si=float(gravity_si),
        speed_si=bound_speed_si,
        mass_raw=bound_mass_raw,
        radius_raw=radius_raw,
        gravity_raw=gravity_raw,
        speed_raw=bound_speed_raw,
    )


TOP_ROPE = _source()
BOTTOM_ROPE = _source(position="bottom")
TOP_CONTACT = _source(carrier="contact")
BOTTOM_CONTACT = _source(carrier="contact", position="bottom")
TOP_THRESHOLD_ROPE = _source(speed_si=math.sqrt(9.81 * 1.25))
TOP_THRESHOLD_CONTACT = _source(
    carrier="contact", speed_si=math.sqrt(9.81 * 1.25)
)
TOP_MINIMUM_ROPE = _source(mode="minimum_speed")
TOP_MINIMUM_CONTACT = _source(carrier="contact", mode="minimum_speed")
MIXED_UNITS = _source(
    carrier="contact",
    raw_scalars=(
        RawScalar("2000", "g"),
        RawScalar("125", "cm"),
        RawScalar("9.81", "m/s^2"),
        RawScalar("18", "km/h"),
    ),
)
MASS_SCALED = _source(carrier="contact", position="bottom", mass_si=4.0)
CENTRIPETAL_INVARIANT = _source(speed_si=10.0, radius_si=5.0)
GRAVITY_RADIUS_INVARIANT = _source(
    carrier="contact",
    mode="minimum_speed",
    gravity_si=4.905,
    radius_si=2.5,
)

SLOW_CASES = (
    TOP_ROPE,
    BOTTOM_ROPE,
    TOP_CONTACT,
    BOTTOM_CONTACT,
    TOP_THRESHOLD_ROPE,
    TOP_THRESHOLD_CONTACT,
    TOP_MINIMUM_ROPE,
    TOP_MINIMUM_CONTACT,
    MIXED_UNITS,
    MASS_SCALED,
    CENTRIPETAL_INVARIANT,
    GRAVITY_RADIUS_INVARIANT,
)


PayloadMutation = Callable[[dict[str, object]], None]


def _axis_direction(axis: str, sign: int = 1) -> dict[str, object]:
    return {
        "kind": "axis",
        "frame_id": FRAME_ID,
        "axis": axis,
        "sign": sign,
    }


def _draft_payload(source: VerticalCircleSource) -> dict[str, object]:
    mass_quote = (
        None
        if source.mass_raw is None
        else f"The particle mass is {source.mass_raw.value} {source.mass_raw.unit}."
    )
    radius_quote = (
        f"The circular-path radius is {source.radius_raw.value} "
        f"{source.radius_raw.unit}."
    )
    gravity_quote = (
        f"Take g = {source.gravity_raw.value} {source.gravity_raw.unit}."
    )
    carrier_quote = (
        "A taut rope connects the particle to the fixed circle center."
        if source.carrier == "rope"
        else "The particle remains in contact with a fixed circular surface."
    )
    location_quote = (
        f"The particle is at the {source.position} of the vertical circle."
    )
    orientation_quote = (
        "Use a local tangential-normal frame at the particle, with positive "
        "normal directed inward toward the fixed circle center."
    )
    if source.mode == "minimum_speed":
        motion_quote = (
            "At the limiting active-carrier condition the inward carrier "
            "reaction is zero."
        )
        query_quote = "Find the unique nonnegative minimum tangential speed."
        speed_token = None
    else:
        assert source.speed_raw is not None
        motion_quote = (
            f"Its tangential speed there is {source.speed_raw.value} "
            f"{source.speed_raw.unit}."
        )
        query_quote = (
            "Find the inward rope tension."
            if source.carrier == "rope"
            else "Find the inward contact normal force."
        )
        speed_token = f"{source.speed_raw.value} {source.speed_raw.unit}"

    evidence_specs: list[tuple[str, str, str | None]] = [
        (
            "radiusEvidence",
            radius_quote,
            f"{source.radius_raw.value} {source.radius_raw.unit}",
        ),
        (
            "gravityEvidence",
            gravity_quote,
            f"{source.gravity_raw.value} {source.gravity_raw.unit}",
        ),
        ("carrierEvidence", carrier_quote, None),
        ("locationEvidence", location_quote, None),
        ("orientationEvidence", orientation_quote, None),
        ("motionEvidence", motion_quote, speed_token),
        ("queryEvidence", query_quote, None),
    ]
    if mass_quote is not None and source.mass_raw is not None:
        evidence_specs.insert(
            0,
            (
                "massEvidence",
                mass_quote,
                f"{source.mass_raw.value} {source.mass_raw.unit}",
            ),
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

    query_quantity_id = (
        "minimumSpeed" if source.mode == "minimum_speed" else "carrierReaction"
    )
    query_symbol_id = source.query_symbol_id
    symbols: list[dict[str, object]] = [
        _symbol("R", "radius", LENGTH),
        _symbol("g", "gravity", ACCELERATION),
    ]
    if source.mode == "minimum_speed":
        symbols.append(_symbol("vMin", "minimumSpeed", SPEED))
    else:
        symbols.extend(
            (
                _symbol("C", "carrierReaction", FORCE),
                _symbol("m", "mass", MASS),
                _symbol("v", "speed", SPEED),
            )
        )

    quantities: list[dict[str, object]] = [
        _quantity(
            "radius",
            "R",
            "radius",
            PARTICLE_ID,
            LENGTH,
            point_id=PARTICLE_POINT_ID,
            provenance="explicit_source",
            evidence_refs=("radiusEvidence", "carrierEvidence"),
            raw_value=source.radius_raw.value,
            raw_unit=source.radius_raw.unit,
        ),
        _quantity(
            "gravity",
            "g",
            "gravity",
            WORLD_ID,
            ACCELERATION,
            frame_id=FRAME_ID,
            interval_id=INTERVAL_ID,
            component="normal",
            direction=_axis_direction("normal", source.gravity_sign),
            provenance="explicit_source",
            evidence_refs=(
                "gravityEvidence",
                "locationEvidence",
                "orientationEvidence",
            ),
            raw_value=source.gravity_raw.value,
            raw_unit=source.gravity_raw.unit,
        ),
    ]
    if source.mode == "minimum_speed":
        quantities.append(
            _quantity(
                "minimumSpeed",
                "vMin",
                "speed",
                PARTICLE_ID,
                SPEED,
                point_id=PARTICLE_POINT_ID,
                frame_id=FRAME_ID,
                interval_id=INTERVAL_ID,
                component="tangential",
                direction=_axis_direction("tangent", 1),
                evidence_refs=(
                    "carrierEvidence",
                    "locationEvidence",
                    "orientationEvidence",
                    "motionEvidence",
                    "queryEvidence",
                ),
            )
        )
    else:
        assert source.mass_raw is not None and source.speed_raw is not None
        quantities.extend(
            (
                _quantity(
                    "carrierReaction",
                    "C",
                    "force",
                    PARTICLE_ID,
                    FORCE,
                    point_id=PARTICLE_POINT_ID,
                    frame_id=FRAME_ID,
                    interval_id=INTERVAL_ID,
                    component="normal",
                    direction=_axis_direction("normal", 1),
                    evidence_refs=(
                        "carrierEvidence",
                        "locationEvidence",
                        "orientationEvidence",
                        "motionEvidence",
                        "queryEvidence",
                    ),
                ),
                _quantity(
                    "mass",
                    "m",
                    "mass",
                    PARTICLE_ID,
                    MASS,
                    provenance="explicit_source",
                    evidence_refs=("massEvidence",),
                    raw_value=source.mass_raw.value,
                    raw_unit=source.mass_raw.unit,
                ),
                _quantity(
                    "speed",
                    "v",
                    "speed",
                    PARTICLE_ID,
                    SPEED,
                    point_id=PARTICLE_POINT_ID,
                    frame_id=FRAME_ID,
                    interval_id=INTERVAL_ID,
                    component="tangential",
                    direction=_axis_direction("tangent", 1),
                    provenance="explicit_source",
                    evidence_refs=(
                        "motionEvidence",
                        "locationEvidence",
                        "orientationEvidence",
                    ),
                    raw_value=source.speed_raw.value,
                    raw_unit=source.speed_raw.unit,
                ),
            )
        )

    carrier_primitive = "rope" if source.carrier == "rope" else "surface"
    center_owner = WORLD_ID if source.carrier == "rope" else CARRIER_ID
    carrier_interaction_kind = (
        "rope_tension" if source.carrier == "rope" else "contact"
    )
    carrier_state_kind = "rope" if source.carrier == "rope" else "contact"
    carrier_state_value = "taut" if source.carrier == "rope" else "touching"
    fixed_subject = WORLD_ID if source.carrier == "rope" else CARRIER_ID
    topology_kind = "attached" if source.carrier == "rope" else "lies_on"
    topology_participants = (
        [PARTICLE_ID, PARTICLE_POINT_ID, CARRIER_ID, CENTER_POINT_ID]
        if source.carrier == "rope"
        else [PARTICLE_ID, PARTICLE_POINT_ID, CARRIER_ID]
    )
    state_conditions: list[dict[str, object]] = [
        {
            "state_condition_id": "carrierActiveState",
            "kind": carrier_state_kind,
            "state": carrier_state_value,
            "subject_id": (
                CARRIER_ID if source.carrier == "rope" else PARTICLE_ID
            ),
            "interval_id": INTERVAL_ID,
            "quantity_ids": (
                []
                if source.mode == "minimum_speed" or source.carrier == "rope"
                else ["carrierReaction"]
            ),
            "evidence_refs": ["carrierEvidence", "motionEvidence"],
        },
        {
            "state_condition_id": "fixedCarrierState",
            "kind": "motion",
            "state": "at_rest",
            "subject_id": fixed_subject,
            "interval_id": INTERVAL_ID,
            "quantity_ids": [],
            "evidence_refs": ["carrierEvidence", "orientationEvidence"],
        },
    ]
    if source.mode == "minimum_speed":
        state_conditions.append(
            {
                "state_condition_id": "minimumBoundaryState",
                "kind": "boundary",
                "state": "active",
                "subject_id": PARTICLE_ID,
                "interval_id": INTERVAL_ID,
                "quantity_ids": ["minimumSpeed"],
                "evidence_refs": [
                    "carrierEvidence",
                    "locationEvidence",
                    "motionEvidence",
                    "queryEvidence",
                ],
            }
        )

    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnosticVerticalCircleLabel",
            "subtype": "diagnosticTopBottomLabel",
            "model_id": "sameFixtureVerticalCircleTest",
            "source_text_sha256": hashlib.sha256(
                source.problem_text.encode("utf-8")
            ).hexdigest(),
        },
        "source_assets": [],
        "source_evidence": evidence,
        "entities": [
            {
                "entity_id": PARTICLE_ID,
                "primitive": "particle",
                "evidence_refs": [
                    evidence_id for evidence_id, _, _ in evidence_specs
                ],
            },
            {
                "entity_id": CARRIER_ID,
                "primitive": carrier_primitive,
                "evidence_refs": ["radiusEvidence", "carrierEvidence"],
            },
            {
                "entity_id": WORLD_ID,
                "primitive": "environment",
                "evidence_refs": [
                    "gravityEvidence",
                    "carrierEvidence",
                    "orientationEvidence",
                ],
            },
        ],
        "points": [
            {
                "point_id": PARTICLE_POINT_ID,
                "role": "material",
                "owner_entity_id": PARTICLE_ID,
                "frame_id": FRAME_ID,
                "evidence_refs": [
                    "carrierEvidence",
                    "locationEvidence",
                    "orientationEvidence",
                ],
            },
            {
                "point_id": CENTER_POINT_ID,
                "role": "geometric",
                "owner_entity_id": center_owner,
                "frame_id": FRAME_ID,
                "evidence_refs": [
                    "radiusEvidence",
                    "carrierEvidence",
                    "orientationEvidence",
                ],
            },
        ],
        "reference_frames": [
            {
                "frame_id": FRAME_ID,
                "frame_type": "tangential_normal",
                "origin": {"kind": "point", "point_id": PARTICLE_POINT_ID},
                "axes": [
                    _axis_binding("tangent", frame_id=FRAME_ID),
                    _axis_binding("normal", frame_id=FRAME_ID),
                ],
                "rotating_about_point_id": CENTER_POINT_ID,
                "evidence_refs": [
                    "locationEvidence",
                    "orientationEvidence",
                ],
            }
        ],
        "motion_intervals": [
            {
                "interval_id": INTERVAL_ID,
                "order": 1,
                "subject_ids": [PARTICLE_ID, CARRIER_ID, WORLD_ID],
                "frame_id": FRAME_ID,
                "evidence_refs": [
                    "carrierEvidence",
                    "locationEvidence",
                    "orientationEvidence",
                    "motionEvidence",
                ],
            }
        ],
        "events": [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": [
            {
                "relation_id": "circleRadiusGeometry",
                "kind": "radius",
                "participant_ids": [PARTICLE_POINT_ID, CENTER_POINT_ID],
                "quantity_ids": ["radius"],
                "interval_id": INTERVAL_ID,
                "evidence_refs": [
                    "radiusEvidence",
                    "carrierEvidence",
                    "orientationEvidence",
                ],
            },
            {
                "relation_id": "carrierTopologyGeometry",
                "kind": topology_kind,
                "participant_ids": topology_participants,
                "quantity_ids": [],
                "interval_id": INTERVAL_ID,
                "evidence_refs": ["carrierEvidence", "orientationEvidence"],
            },
        ],
        "interactions": [
            {
                "interaction_id": "gravityInteraction",
                "kind": "gravity",
                "participant_ids": [PARTICLE_ID, WORLD_ID],
                "point_ids": [PARTICLE_POINT_ID],
                "frame_id": FRAME_ID,
                "interval_id": INTERVAL_ID,
                "quantity_ids": (
                    ["gravity"]
                    if source.mode == "minimum_speed"
                    else ["mass", "gravity"]
                ),
                "evidence_refs": [
                    "gravityEvidence",
                    "locationEvidence",
                    "orientationEvidence",
                ],
            },
            {
                "interaction_id": "carrierInteraction",
                "kind": carrier_interaction_kind,
                "participant_ids": [PARTICLE_ID, CARRIER_ID],
                "point_ids": [PARTICLE_POINT_ID],
                "frame_id": FRAME_ID,
                "interval_id": INTERVAL_ID,
                "quantity_ids": (
                    []
                    if source.mode == "minimum_speed"
                    else ["carrierReaction"]
                ),
                "evidence_refs": [
                    "carrierEvidence",
                    "locationEvidence",
                    "orientationEvidence",
                    "queryEvidence",
                ],
            },
        ],
        "constraints": [],
        "state_conditions": state_conditions,
        "queries": [
            {
                "query_id": "queryTarget",
                "target": {
                    "role": "speed" if source.mode == "minimum_speed" else "force",
                    "subject_id": PARTICLE_ID,
                    "point_id": PARTICLE_POINT_ID,
                    "frame_id": FRAME_ID,
                    "interval_id": INTERVAL_ID,
                    "component": (
                        "tangential"
                        if source.mode == "minimum_speed"
                        else "normal"
                    ),
                    "direction": _axis_direction(
                        "tangent" if source.mode == "minimum_speed" else "normal",
                        1,
                    ),
                    "target_quantity_id": query_quantity_id,
                },
                "output_unit": "m/s" if source.mode == "minimum_speed" else "N",
                "output_dimension": source.query_dimension.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": ["queryEvidence"],
            }
        ],
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


def _normalize(
    source: VerticalCircleSource,
    *,
    mutation: PayloadMutation | None = None,
) -> NormalizationResult:
    payload = _draft_payload(source)
    if mutation is not None:
        mutation(payload)
    draft = MechanicsProblemDraftV1.model_validate(payload)
    return normalize_draft(source.problem_text, draft)


def _build_ir(source: VerticalCircleSource) -> MechanicsProblemIRV1:
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert normalization.accepted is True
    assert type(normalization.ir) is MechanicsProblemIRV1
    return normalization.ir


def _execute(ir: MechanicsProblemIRV1) -> MechanicsMigrationProbeExecution:
    return execute_mechanics_ir_probe(ir)


def _compile(ir: MechanicsProblemIRV1):
    return MechanicsCompiler().compile(
        ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(ir),
    )


def _candidate_values(execution: MechanicsMigrationProbeExecution) -> dict[str, float]:
    result = execution.solve_result
    assert result is not None
    assert len(result.candidate_set.candidates) == 1
    values = {
        item.symbol_id: item.value_si
        for item in result.candidate_set.candidates[0].values
    }
    assert all(type(value) is float for value in values.values())
    return {key: value for key, value in values.items() if type(value) is float}


def _count_ast_ops(value: object, op: str) -> int:
    if isinstance(value, dict):
        return (1 if value.get("op") == op else 0) + sum(
            _count_ast_ops(item, op) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return sum(_count_ast_ops(item, op) for item in value)
    return 0


def _legacy_problem(source: VerticalCircleSource) -> CanonicalProblem:
    knowns = {
        "R": Quantity("R", source.radius_si, "m"),
        "g": Quantity("g", source.gravity_si, "m/s^2"),
    }
    if source.mode == "reaction":
        assert source.mass_si is not None and source.speed_si is not None
        knowns.update(
            {
                "m": Quantity("m", source.mass_si, "kg"),
                "v": Quantity("v", source.speed_si, "m/s"),
            }
        )
        requested = "tension" if source.carrier == "rope" else "normal_force"
    else:
        requested = "minimum_speed"
    return CanonicalProblem(
        system_type="vertical_circle",
        subtype=source.position,
        knowns=knowns,
        unknowns=[requested],
        requested_outputs=[requested],
    )


def _observe_legacy(
    source: VerticalCircleSource,
) -> tuple[LegacyObservation, SolverResult]:
    # The raw scalar is independently computed before the direct legacy call.
    raw_scalar = source.expected_si
    assert type(raw_scalar) is float and math.isfinite(raw_scalar)
    assert raw_scalar >= -1.0e-10
    raw_scalar = max(0.0, raw_scalar)

    problem = _legacy_problem(source)
    assert problem.raw_text == ""
    result = VerticalCircleSolver().solve(problem)
    assert result.ok is True, result.unsupported_reason
    assert result.verification.passed is True
    assert result.answer is not None
    assert result.answer.numeric == pytest.approx(
        round(raw_scalar, 5), rel=0.0, abs=1.0e-12
    )
    assert len(result.answers) >= 1
    primary = result.answers[0]
    assert primary.numeric == pytest.approx(
        round(raw_scalar, 5), rel=0.0, abs=1.0e-12
    )
    if source.mode == "reaction":
        # Contact parity is numeric only: the legacy adapter labels both
        # carrier forces as tension/T and therefore provides no normal-force
        # semantic-label authority.
        assert primary.symbol == "T"
        assert primary.output_key == "tension"
    else:
        assert primary.symbol == "v_min"

    normalized = normalize_quantity(
        repr(raw_scalar),
        "m/s" if source.mode == "minimum_speed" else "N",
        "scalar",
        source.query_dimension,
    )
    assert type(normalized.value) is float
    observation = LegacyObservation(
        case_id=(
            "verticalCircle"
            + hashlib.sha256(source.problem_text.encode("utf-8")).hexdigest()[:32]
        ),
        diagnostic_kernel_id="verticalCircleDirectV1",
        terminal=LegacyTerminal.solved,
        query_symbol_id=source.query_symbol_id,
        si_unit=render_canonical_si_unit(source.query_dimension),
        selected_scalar_si=normalized.value,
        complete_candidate_scalars_si=(
            LegacyCandidateScalar(value_si=normalized.value, multiplicity=1),
        ),
        residual_passed=True,
    )
    return observation, result


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport


def _same_fixture(source: VerticalCircleSource) -> SameFixtureEvidence:
    ir = _build_ir(source)
    assert "raw_text" not in type(ir).model_fields

    # Generic authority is executed and frozen before the diagnostic legacy call.
    execution = _execute(ir)
    assert execution.terminal is MigrationProbeTerminal.solved, (
        None
        if execution.compiler_result is None
        else execution.compiler_result.issues
    )
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is not None
    assert execution.solve_result is not None
    frozen_signature = build_generic_result_invariance_signature(
        execution.solve_result
    )
    frozen_graph = execution.compiler_result.graph.fingerprint
    frozen_plan = execution.solve_result.plan.plan_fingerprint
    frozen_values = tuple(sorted(_candidate_values(execution).items()))

    observation, _ = _observe_legacy(source)
    report = build_legacy_differential_report(execution.solve_result, observation)
    assert build_generic_result_invariance_signature(
        execution.solve_result
    ) == frozen_signature
    assert execution.compiler_result.graph.fingerprint == frozen_graph
    assert execution.solve_result.plan.plan_fingerprint == frozen_plan
    assert tuple(sorted(_candidate_values(execution).items())) == frozen_values
    return SameFixtureEvidence(
        registry_entry="vertical_circle",
        ir=ir,
        execution=execution,
        observation=observation,
        report=report,
    )


def _forbid_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> SolverResult:
        raise AssertionError("generic vertical-circle tests must not call legacy")

    monkeypatch.setattr(VerticalCircleSolver, "solve", forbidden)


FAST_PROFILES = (
    TOP_ROPE,
    BOTTOM_ROPE,
    TOP_CONTACT,
    BOTTOM_CONTACT,
    TOP_MINIMUM_ROPE,
    TOP_MINIMUM_CONTACT,
)


@pytest.mark.parametrize(
    "source",
    FAST_PROFILES,
    ids=(
        "top-rope-reaction",
        "bottom-rope-reaction",
        "top-contact-reaction",
        "bottom-contact-reaction",
        "top-rope-minimum-speed",
        "top-contact-minimum-speed",
    ),
)
def test_vertical_circle_exact_typed_profiles_compile_without_legacy(
    source: VerticalCircleSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    ir = _build_ir(source)
    result = _compile(ir)
    assert result.status is CompilerStatus.ready, result.issues
    assert result.graph is not None
    assert len(ir.entities) == 3
    assert len(ir.points) == 2
    assert len(ir.reference_frames) == 1
    assert len(ir.motion_intervals) == 1
    assert len(ir.geometry) == 2
    assert len(ir.interactions) == 2
    assert ir.constraints == ()
    assert ir.assumptions == ()
    assert len(ir.queries) == 1
    expected_quantity_ids = (
        {"radius", "gravity", "minimumSpeed"}
        if source.mode == "minimum_speed"
        else {"radius", "gravity", "carrierReaction", "mass", "speed"}
    )
    assert {item.quantity_id for item in ir.quantities} == expected_quantity_ids
    expected_laws = (
        Counter({"vertical_circle_top_minimum_speed": 1})
        if source.mode == "minimum_speed"
        else Counter({"vertical_circle_local_reaction": 1})
    )
    assert Counter(item.law_id for item in result.graph.equations) == expected_laws
    assert not any(
        law_id.startswith("rolling_") or law_id == "pure_rolling_shape_inertia"
        for law_id in (item.law_id for item in result.graph.equations)
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    "source",
    SLOW_CASES,
    ids=(
        "top-rope-reaction",
        "bottom-rope-reaction",
        "top-contact-normal",
        "bottom-contact-normal",
        "top-rope-threshold-zero",
        "top-contact-threshold-zero",
        "top-rope-minimum-speed",
        "top-contact-minimum-speed",
        "mixed-unit-reaction",
        "mass-scaled-reaction",
        "v-squared-over-radius-invariance",
        "g-times-radius-minimum-invariance",
    ),
)
def test_vertical_circle_same_fixture_full_parity(
    source: VerticalCircleSource,
) -> None:
    evidence = _same_fixture(source)
    compiler = evidence.execution.compiler_result
    result = evidence.execution.solve_result
    assert evidence.registry_entry == "vertical_circle"
    assert compiler is not None and compiler.graph is not None
    assert evidence.execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert evidence.execution.solve_terminal is MechanicsSolveTerminal.solved
    assert result.plan.primary_backend in {
        SolveBackendKind.linear_symbolic,
        SolveBackendKind.nonlinear_symbolic,
    }
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert result.candidate_set.generation_complete is True
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    assert candidate.query_symbol_id == source.query_symbol_id
    assert candidate.root_multiplicity == 1
    assert candidate.query_value_si >= 0.0
    assert candidate.query_value_si == pytest.approx(
        source.expected_si, rel=0.0, abs=1.0e-9
    )
    assert candidate.query_value_si == pytest.approx(
        evidence.observation.selected_scalar_si, rel=0.0, abs=1.0e-9
    )
    assert len(result.verification_outcomes) == 1
    outcome = result.verification_outcomes[0]
    assert outcome.passed is True
    assert {
        VerificationCheckKind.equation_residual,
        VerificationCheckKind.unit_consistency,
        VerificationCheckKind.query_binding,
        VerificationCheckKind.source_evidence,
    }.issubset({check.kind for check in outcome.checks})
    residual_checks = tuple(
        check
        for check in outcome.checks
        if check.kind is VerificationCheckKind.equation_residual
    )
    assert len(residual_checks) == 1
    assert residual_checks[0].status is VerificationCheckStatus.passed
    assert residual_checks[0].measured_error == pytest.approx(0.0, abs=1.0e-9)
    assert evidence.observation.residual_passed is True
    assert evidence.report.status is DifferentialStatus.full_parity
    assert evidence.report.discrepancies == ()
    assert evidence.report.observation_terminal is LegacyTerminal.solved
    assert evidence.report.generic_terminal is MechanicsSolveTerminal.solved

    graph = compiler.graph
    by_law = {item.law_id: item for item in graph.equations}
    if source.mode == "minimum_speed":
        assert set(by_law) == {"vertical_circle_top_minimum_speed"}
        min_equation = by_law["vertical_circle_top_minimum_speed"]
        assert set(min_equation.source_quantity_ids) == {
            "radius",
            "gravity",
            "minimumSpeed",
        }
        assert "mass" not in min_equation.source_quantity_ids
        assert isinstance(min_equation.expression, Equality)
        expression_json = min_equation.expression.model_dump(mode="json")
        assert _count_ast_ops(expression_json, "sqrt") == 1
        assert "+/-" not in repr(expression_json)
        assert "plus_minus" not in repr(expression_json)
    else:
        assert set(by_law) == {"vertical_circle_local_reaction"}
        reaction_equation = by_law["vertical_circle_local_reaction"]
        assert set(reaction_equation.source_quantity_ids) == {
            "mass",
            "radius",
            "gravity",
            "speed",
            "carrierReaction",
        }
        assert isinstance(reaction_equation.expression, Equality)
        assert "sqrt" not in repr(
            reaction_equation.expression.model_dump(mode="json")
        )

    if source is MIXED_UNITS:
        quantities = {item.quantity_id: item for item in evidence.ir.quantities}
        assert quantities["mass"].si_value == pytest.approx(2.0)
        assert quantities["radius"].si_value == pytest.approx(1.25)
        assert quantities["gravity"].si_value == pytest.approx(9.81)
        assert quantities["speed"].si_value == pytest.approx(5.0)
    if source in {TOP_THRESHOLD_ROPE, TOP_THRESHOLD_CONTACT}:
        assert candidate.query_value_si == 0.0
    if source is MASS_SCALED:
        assert source.expected_si == pytest.approx(
            2.0 * BOTTOM_CONTACT.expected_si, abs=1.0e-12
        )
    if source is BOTTOM_ROPE:
        assert source.expected_si - TOP_ROPE.expected_si == pytest.approx(
            2.0 * 2.0 * 9.81, abs=1.0e-12
        )
    if source is BOTTOM_CONTACT:
        assert source.expected_si - TOP_CONTACT.expected_si == pytest.approx(
            2.0 * 2.0 * 9.81, abs=1.0e-12
        )
    if source is CENTRIPETAL_INVARIANT:
        assert source.speed_si is not None and TOP_ROPE.speed_si is not None
        assert source.speed_si**2 / source.radius_si == pytest.approx(
            TOP_ROPE.speed_si**2 / TOP_ROPE.radius_si,
            abs=1.0e-12,
        )
        assert source.expected_si == pytest.approx(TOP_ROPE.expected_si)
    if source is GRAVITY_RADIUS_INVARIANT:
        assert source.gravity_si * source.radius_si == pytest.approx(
            TOP_MINIMUM_CONTACT.gravity_si * TOP_MINIMUM_CONTACT.radius_si
        )
        assert source.expected_si == pytest.approx(TOP_MINIMUM_CONTACT.expected_si)


def _record(
    payload: dict[str, object],
    collection_name: str,
    id_field: str,
    record_id: str,
) -> dict[str, object]:
    collection = payload[collection_name]
    assert isinstance(collection, list)
    return next(item for item in collection if item[id_field] == record_id)


def _remove_record(
    collection_name: str,
    id_field: str,
    record_id: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        collection = payload[collection_name]
        assert isinstance(collection, list)
        payload[collection_name] = [
            item for item in collection if item[id_field] != record_id
        ]

    return mutate


def _set_field(
    collection_name: str,
    id_field: str,
    record_id: str,
    field_name: str,
    value: object,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _record(payload, collection_name, id_field, record_id)[field_name] = value

    return mutate


def _compose(*mutations: PayloadMutation) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        for mutation in mutations:
            mutation(payload)

    return mutate


@dataclass(frozen=True)
class CompilerRejectCase:
    label: str
    source: VerticalCircleSource
    mutation: PayloadMutation
    expected_status: CompilerStatus = CompilerStatus.unsupported


def _append_duplicate_center(payload: dict[str, object]) -> None:
    points = payload["points"]
    assert isinstance(points, list)
    center = deepcopy(_record(payload, "points", "point_id", CENTER_POINT_ID))
    center["point_id"] = "duplicateCenterPoint"
    points.append(center)


def _append_extra_entity(payload: dict[str, object]) -> None:
    entities = payload["entities"]
    assert isinstance(entities, list)
    entities.append(
        {
            "entity_id": "decoyParticle",
            "primitive": "particle",
            "evidence_refs": ["carrierEvidence"],
        }
    )


def _append_extra_quantity(payload: dict[str, object]) -> None:
    symbols = payload["symbols"]
    quantities = payload["quantities"]
    assert isinstance(symbols, list) and isinstance(quantities, list)
    symbols.append(_symbol("decoy", "decoyQuantity", LENGTH))
    quantities.append(
        _quantity(
            "decoyQuantity",
            "decoy",
            "length",
            PARTICLE_ID,
            LENGTH,
            evidence_refs=("radiusEvidence",),
        )
    )


def _append_client_constraint(payload: dict[str, object]) -> None:
    constraints = payload["constraints"]
    assert isinstance(constraints, list)
    constraints.append(
        {
            "constraint_id": "clientReactionEquation",
            "kind": "dynamic",
            "expression": Equality(
                left=LiteralNode(value=0.0, dimension=FORCE),
                right=LiteralNode(value=0.0, dimension=FORCE),
            ).model_dump(mode="json"),
            "subject_ids": [PARTICLE_ID],
            "interval_id": INTERVAL_ID,
            "evidence_refs": ["queryEvidence"],
        }
    )


def _remove_center(payload: dict[str, object]) -> None:
    _remove_record("points", "point_id", CENTER_POINT_ID)(payload)
    frame = _record(payload, "reference_frames", "frame_id", FRAME_ID)
    frame["rotating_about_point_id"] = None
    radius = _record(payload, "geometry", "relation_id", "circleRadiusGeometry")
    radius["participant_ids"] = [PARTICLE_POINT_ID]
    topology = _record(
        payload, "geometry", "relation_id", "carrierTopologyGeometry"
    )
    topology["participant_ids"] = [
        item for item in topology["participant_ids"] if item != CENTER_POINT_ID
    ]


def _remove_circle_frame(payload: dict[str, object]) -> None:
    payload["reference_frames"] = []
    for point in payload["points"]:
        point["frame_id"] = None
    interval = _record(payload, "motion_intervals", "interval_id", INTERVAL_ID)
    interval["frame_id"] = None
    for quantity in payload["quantities"]:
        quantity["frame_id"] = None
        quantity["direction"] = None
    for interaction in payload["interactions"]:
        interaction["frame_id"] = None
    query = _record(payload, "queries", "query_id", "queryTarget")
    target = query["target"]
    assert isinstance(target, dict)
    target["frame_id"] = None
    target["direction"] = None


def _remove_radius(payload: dict[str, object]) -> None:
    _remove_record("quantities", "quantity_id", "radius")(payload)
    _remove_record("symbols", "symbol_id", "R")(payload)
    radius_geometry = _record(
        payload, "geometry", "relation_id", "circleRadiusGeometry"
    )
    radius_geometry["quantity_ids"] = []


def _query_quantity(
    payload: dict[str, object],
    quantity_id: str,
    output_unit: str,
) -> None:
    quantity = _record(payload, "quantities", "quantity_id", quantity_id)
    query = _record(payload, "queries", "query_id", "queryTarget")
    query["target"] = {
        "role": quantity["role"],
        "subject_id": quantity["subject_id"],
        "point_id": quantity.get("point_id"),
        "frame_id": quantity.get("frame_id"),
        "interval_id": quantity.get("interval_id"),
        "component": quantity.get("component", "unspecified"),
        "direction": quantity.get("direction"),
        "target_quantity_id": quantity_id,
    }
    query["output_unit"] = output_unit
    query["output_dimension"] = quantity["dimension"]


def _query_target(quantity_id: str, output_unit: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _query_quantity(payload, quantity_id, output_unit)

    return mutate


def _unbind_query(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryTarget")
    target = query["target"]
    assert isinstance(target, dict)
    target["target_quantity_id"] = None


def _delete_query(payload: dict[str, object]) -> None:
    payload["queries"] = []


def _set_reaction_direction(
    payload: dict[str, object],
    sign: int,
) -> None:
    direction = _axis_direction("normal", sign)
    reaction = _record(
        payload, "quantities", "quantity_id", "carrierReaction"
    )
    reaction["direction"] = direction
    query = _record(payload, "queries", "query_id", "queryTarget")
    target = query["target"]
    assert isinstance(target, dict)
    target["direction"] = direction


def _grounded_source_output(
    source: VerticalCircleSource,
    quantity_id: str,
    *,
    value: str,
    unit: str,
    quote: str,
) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        evidence = payload["source_evidence"]
        assert isinstance(evidence, list)
        evidence.append(
            _text_evidence(
                source.problem_text,
                evidence_id="maliciousOutputEvidence",
                quote=quote,
                quantity_token=f"{value} {unit}",
            )
        )
        quantity = _record(payload, "quantities", "quantity_id", quantity_id)
        quantity.update(
            {
                "provenance": "explicit_source",
                "raw_value": value,
                "raw_unit": unit,
            }
        )
        evidence_refs = quantity["evidence_refs"]
        assert isinstance(evidence_refs, list)
        evidence_refs.append("maliciousOutputEvidence")

    return mutate


SOURCE_PROVIDED_REACTION = _source(
    paraphrase_prefix="A source-provided carrier reaction is 20.38 N."
)
SOURCE_PROVIDED_MINIMUM = _source(
    mode="minimum_speed",
    paraphrase_prefix="A source-provided minimum speed is 3.5 m/s.",
)


PROFILE_MISMATCH_CASES = (
    CompilerRejectCase(
        "duplicate-center",
        TOP_ROPE,
        _append_duplicate_center,
    ),
    CompilerRejectCase(
        "corrupt-center-role",
        TOP_ROPE,
        _set_field("points", "point_id", CENTER_POINT_ID, "role", "contact"),
    ),
    CompilerRejectCase("missing-center", TOP_ROPE, _remove_center),
    CompilerRejectCase(
        "corrupt-frame-type",
        TOP_ROPE,
        _set_field(
            "reference_frames", "frame_id", FRAME_ID, "frame_type", "cartesian_2d"
        ),
    ),
    CompilerRejectCase("missing-frame", TOP_ROPE, _remove_circle_frame),
    CompilerRejectCase("missing-radius", TOP_ROPE, _remove_radius),
    CompilerRejectCase(
        "corrupt-radius-kind",
        TOP_ROPE,
        _set_field(
            "geometry",
            "relation_id",
            "circleRadiusGeometry",
            "kind",
            "distance",
        ),
    ),
    CompilerRejectCase(
        "missing-carrier-interaction",
        TOP_ROPE,
        _remove_record(
            "interactions", "interaction_id", "carrierInteraction"
        ),
    ),
    CompilerRejectCase(
        "corrupt-carrier-interaction",
        TOP_ROPE,
        _set_field(
            "interactions",
            "interaction_id",
            "carrierInteraction",
            "kind",
            "applied_force",
        ),
    ),
    CompilerRejectCase(
        "missing-carrier-state",
        TOP_ROPE,
        _remove_record(
            "state_conditions", "state_condition_id", "carrierActiveState"
        ),
    ),
    CompilerRejectCase(
        "rope-taut-state-scoped-to-particle",
        TOP_ROPE,
        _set_field(
            "state_conditions",
            "state_condition_id",
            "carrierActiveState",
            "subject_id",
            PARTICLE_ID,
        ),
    ),
    CompilerRejectCase(
        "rope-fixed-state-scoped-to-rope",
        TOP_ROPE,
        _set_field(
            "state_conditions",
            "state_condition_id",
            "fixedCarrierState",
            "subject_id",
            CARRIER_ID,
        ),
    ),
    CompilerRejectCase(
        "rope-center-owned-by-rope",
        TOP_ROPE,
        _set_field(
            "points",
            "point_id",
            CENTER_POINT_ID,
            "owner_entity_id",
            CARRIER_ID,
        ),
    ),
    CompilerRejectCase(
        "contact-center-owned-by-world",
        TOP_CONTACT,
        _set_field(
            "points",
            "point_id",
            CENTER_POINT_ID,
            "owner_entity_id",
            WORLD_ID,
        ),
    ),
    CompilerRejectCase(
        "contact-fixed-state-scoped-to-world",
        TOP_CONTACT,
        _set_field(
            "state_conditions",
            "state_condition_id",
            "fixedCarrierState",
            "subject_id",
            WORLD_ID,
        ),
    ),
    CompilerRejectCase(
        "slack-rope",
        TOP_ROPE,
        _set_field(
            "state_conditions",
            "state_condition_id",
            "carrierActiveState",
            "state",
            "slack",
        ),
    ),
    CompilerRejectCase(
        "separated-contact",
        TOP_CONTACT,
        _set_field(
            "state_conditions",
            "state_condition_id",
            "carrierActiveState",
            "state",
            "separated",
        ),
    ),
    CompilerRejectCase(
        "missing-gravity-direction",
        TOP_ROPE,
        _set_field(
            "quantities", "quantity_id", "gravity", "direction", None
        ),
    ),
    CompilerRejectCase(
        "wrong-reaction-direction",
        TOP_ROPE,
        lambda payload: _set_reaction_direction(payload, -1),
    ),
    CompilerRejectCase("extra-entity", TOP_ROPE, _append_extra_entity),
    CompilerRejectCase("extra-quantity", TOP_ROPE, _append_extra_quantity),
    CompilerRejectCase(
        "client-equation-constraint", TOP_ROPE, _append_client_constraint
    ),
    CompilerRejectCase(
        "source-provided-reaction",
        SOURCE_PROVIDED_REACTION,
        _grounded_source_output(
            SOURCE_PROVIDED_REACTION,
            "carrierReaction",
            value="20.38",
            unit="N",
            quote="A source-provided carrier reaction is 20.38 N.",
        ),
    ),
    CompilerRejectCase(
        "source-provided-minimum-speed",
        SOURCE_PROVIDED_MINIMUM,
        _grounded_source_output(
            SOURCE_PROVIDED_MINIMUM,
            "minimumSpeed",
            value="3.5",
            unit="m/s",
            quote="A source-provided minimum speed is 3.5 m/s.",
        ),
    ),
    CompilerRejectCase(
        "bottom-minimum-speed",
        _source(mode="minimum_speed"),
        _set_field(
            "quantities",
            "quantity_id",
            "gravity",
            "direction",
            _axis_direction("normal", -1),
        ),
    ),
    CompilerRejectCase(
        "wrong-carrier-primitive",
        TOP_ROPE,
        _set_field(
            "entities", "entity_id", CARRIER_ID, "primitive", "surface"
        ),
    ),
    CompilerRejectCase(
        "source-mass-query",
        TOP_ROPE,
        _query_target("mass", "kg"),
    ),
    CompilerRejectCase(
        "source-radius-query",
        TOP_ROPE,
        _query_target("radius", "m"),
    ),
    CompilerRejectCase(
        "source-speed-query",
        TOP_ROPE,
        _query_target("speed", "m/s"),
    ),
)


@pytest.mark.parametrize("case", PROFILE_MISMATCH_CASES, ids=lambda case: case.label)
def test_vertical_circle_exact_contract_mismatches_are_specialized_unsupported(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(case.source, mutation=case.mutation)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is case.expected_status
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


INVALID_DOMAIN_CASES = (
    _source(mass_si=0.0),
    _source(mass_si=-2.0),
    _source(radius_si=0.0),
    _source(radius_si=-1.25),
    _source(gravity_si=0.0),
    _source(gravity_si=-9.81),
    _source(speed_si=-1.0),
)


@pytest.mark.parametrize(
    "source",
    INVALID_DOMAIN_CASES,
    ids=(
        "zero-mass",
        "negative-mass",
        "zero-radius",
        "negative-radius",
        "zero-gravity",
        "negative-gravity",
        "negative-speed",
    ),
)
def test_vertical_circle_invalid_physical_domains_fail_without_legacy(
    source: VerticalCircleSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.invalid
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.invalid_domain
        for issue in execution.compiler_result.issues
    )


@pytest.mark.parametrize("carrier", ("rope", "contact"))
def test_vertical_circle_top_subthreshold_active_carrier_is_unsupported(
    carrier: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(_source(carrier=carrier, speed_si=1.0))
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


@pytest.mark.parametrize("carrier", ("rope", "contact"))
def test_vertical_circle_near_but_materially_subthreshold_is_unsupported(
    carrier: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threshold = math.sqrt(9.81 * 1.25)
    source = _source(
        carrier=carrier,
        speed_si=threshold * (1.0 - 1.0e-12),
    )
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def test_vertical_circle_zero_speed_is_not_equal_to_positive_subnormal_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(
        mass_si=1.0,
        gravity_si=1.0e-200,
        radius_si=5.0e-124,
        speed_si=0.0,
    )
    assert source.gravity_si * source.radius_si == 5.0e-324
    assert source.gravity_si * source.radius_si > 0.0
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def test_vertical_circle_unequal_positive_subnormals_are_not_one_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minimum_subnormal = 5.0e-324
    source = _source(
        mass_si=1.0,
        gravity_si=1.0e-200,
        radius_si=1.0e-123,
        speed_si=math.sqrt(minimum_subnormal),
    )
    assert source.speed_si is not None
    assert source.speed_si * source.speed_si == minimum_subnormal
    assert source.gravity_si * source.radius_si == 1.0e-323
    assert source.gravity_si * source.radius_si == 2.0 * minimum_subnormal
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def test_vertical_circle_equal_positive_subnormal_boundary_emits_exact_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minimum_subnormal = 5.0e-324
    source = _source(
        mass_si=1.0,
        gravity_si=1.0e-200,
        radius_si=5.0e-124,
        speed_si=math.sqrt(minimum_subnormal),
    )
    assert source.speed_si is not None
    assert source.speed_si * source.speed_si == minimum_subnormal
    assert source.gravity_si * source.radius_si == minimum_subnormal
    _forbid_legacy_call(monkeypatch)
    compiled = _compile(_build_ir(source))
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    assert len(compiled.graph.equations) == 1
    equation = compiled.graph.equations[0]
    assert equation.law_id == "vertical_circle_local_reaction"
    assert isinstance(equation.expression, Equality)
    assert equation.expression.right == LiteralNode(
        value=0.0,
        dimension=FORCE,
    )


DERIVED_OVERFLOW_CASES = (
    (
        "minimum-gravity-radius-product-overflow",
        _source(
            mode="minimum_speed",
            gravity_si=1.0e200,
            radius_si=1.0e200,
        ),
    ),
    (
        "reaction-speed-squared-overflow",
        _source(
            mass_si=1.0,
            gravity_si=1.0,
            radius_si=1.0,
            speed_si=1.0e200,
        ),
    ),
    (
        "reaction-speed-squared-over-radius-overflow",
        _source(
            mass_si=1.0,
            gravity_si=1.0,
            radius_si=1.0e-100,
            speed_si=1.0e150,
        ),
    ),
    (
        "reaction-final-force-overflow",
        _source(
            position="bottom",
            mass_si=1.0e250,
            gravity_si=1.0,
            radius_si=1.0,
            speed_si=1.0e50,
        ),
    ),
    (
        "reaction-final-force-underflow",
        _source(
            position="bottom",
            mass_si=1.0e-200,
            gravity_si=1.0e-200,
            radius_si=1.0,
            speed_si=1.0e-100,
        ),
    ),
    (
        "minimum-gravity-radius-product-underflow",
        _source(
            mode="minimum_speed",
            gravity_si=1.0e-200,
            radius_si=1.0e-200,
        ),
    ),
    (
        "reaction-speed-squared-underflow-before-radius-division",
        _source(
            mass_si=1.0,
            gravity_si=1.0e-200,
            radius_si=1.0e-200,
            speed_si=2.0e-200,
        ),
    ),
)


@pytest.mark.parametrize(
    ("_label", "source"),
    DERIVED_OVERFLOW_CASES,
    ids=tuple(item[0] for item in DERIVED_OVERFLOW_CASES),
)
def test_vertical_circle_finite_sources_with_unsafe_derived_values_are_invalid(
    _label: str,
    source: VerticalCircleSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    assert all(
        type(item.si_value) is float and math.isfinite(item.si_value)
        for item in normalization.ir.quantities
        if item.si_value is not None
    )
    if _label == "minimum-gravity-radius-product-underflow":
        assert source.gravity_si * source.radius_si == 0.0
        assert Decimal(repr(source.gravity_si)) * Decimal(
            repr(source.radius_si)
        ) > Decimal(0)
    if _label == "reaction-speed-squared-underflow-before-radius-division":
        assert source.speed_si is not None
        assert source.speed_si * source.speed_si == 0.0
        exact_acceleration = (
            Decimal(repr(source.speed_si)) ** 2
            / Decimal(repr(source.radius_si))
            - Decimal(repr(source.gravity_si))
        )
        assert exact_acceleration == Decimal("3E-200")
    if _label == "reaction-final-force-underflow":
        assert source.mass_si is not None and source.speed_si is not None
        floating_force = source.mass_si * (
            source.speed_si**2 / source.radius_si + source.gravity_si
        )
        assert floating_force == 0.0
        exact_force = Decimal(repr(source.mass_si)) * (
            Decimal(repr(source.speed_si)) ** 2
            / Decimal(repr(source.radius_si))
            + Decimal(repr(source.gravity_si))
        )
        assert exact_force == Decimal("2E-400")
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.invalid
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.invalid_domain
        for issue in execution.compiler_result.issues
    )


def test_vertical_circle_unbound_query_is_invalid_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(TOP_ROPE, mutation=_unbind_query)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def test_vertical_circle_missing_query_is_invalid_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    payload = _build_ir(TOP_ROPE).model_dump(mode="python", warnings="none")
    payload["queries"] = []
    queryless_ir = MechanicsProblemIRV1.model_validate(payload)
    execution = _execute(queryless_ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.invalid
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.unresolved_query
        for issue in execution.compiler_result.issues
    )


QUERY_INDEPENDENT_FALLBACK_CASES = (
    CompilerRejectCase(
        "mass-query-plus-radius-anchor-deletion",
        TOP_ROPE,
        _compose(
            _query_target("mass", "kg"),
            _remove_record(
                "geometry", "relation_id", "circleRadiusGeometry"
            ),
        ),
    ),
    CompilerRejectCase(
        "mass-query-plus-complete-circle-frame-removal",
        TOP_ROPE,
        _compose(
            _query_target("mass", "kg"),
            _remove_circle_frame,
        ),
    ),
    CompilerRejectCase(
        "gravity-query-plus-particle-primitive-corruption",
        TOP_ROPE,
        _compose(
            _query_target("gravity", "m/s^2"),
            _set_field(
                "entities", "entity_id", PARTICLE_ID, "primitive", "rigid_body"
            ),
        ),
    ),
    CompilerRejectCase(
        "radius-query-plus-carrier-interaction-deletion",
        TOP_MINIMUM_CONTACT,
        _compose(
            _query_target("radius", "m"),
            _remove_record(
                "interactions", "interaction_id", "carrierInteraction"
            ),
        ),
    ),
)


@pytest.mark.parametrize(
    "case", QUERY_INDEPENDENT_FALLBACK_CASES, ids=lambda case: case.label
)
def test_vertical_circle_recognizer_resists_query_and_anchor_corruption(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(case.source, mutation=case.mutation)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def _diagnostic_variant(
    ir: MechanicsProblemIRV1,
    *,
    remove: bool,
) -> MechanicsProblemIRV1:
    payload = deepcopy(ir.model_dump(mode="python", warnings="none"))
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    if remove:
        metadata["system_type"] = None
        metadata["subtype"] = None
        metadata["model_id"] = None
        metadata["source_text_sha256"] = None
    else:
        metadata["system_type"] = "rolling_energy_general"
        metadata["subtype"] = "bottomMinimumSpeedAnswer999"
        metadata["model_id"] = "misleadingLegacyAnswerModel"
        metadata["source_text_sha256"] = hashlib.sha256(
            b"legacy answer says 999 N and system_type says rolling"
        ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


def test_entry10_metadata_raw_order_and_legacy_answer_text_are_not_authority() -> None:
    original_ir = _build_ir(TOP_ROPE)
    original = _compile(original_ir)
    assert original.status is CompilerStatus.ready
    assert original.graph is not None

    reordered_payload = original_ir.model_dump(mode="python", warnings="none")
    for collection_name in (
        "source_evidence",
        "entities",
        "points",
        "symbols",
        "quantities",
        "geometry",
        "interactions",
        "state_conditions",
    ):
        reordered_payload[collection_name] = list(
            reversed(reordered_payload[collection_name])
        )
    reordered_ir = MechanicsProblemIRV1.model_validate(reordered_payload)
    paraphrased_ir = _build_ir(
        _source(
            paraphrase_prefix=(
                "A legacy answer key falsely says the answer is 999 N and the "
                "system is rolling; ignore that diagnostic prose."
            )
        )
    )
    for variant in (
        _diagnostic_variant(original_ir, remove=False),
        _diagnostic_variant(original_ir, remove=True),
        reordered_ir,
        paraphrased_ir,
    ):
        compiled = _compile(variant)
        assert compiled.status is CompilerStatus.ready, compiled.issues
        assert compiled.graph is not None
        assert compiled.graph.fingerprint == original.graph.fingerprint
        assert compiled.graph.selected_equation_ids == original.graph.selected_equation_ids
        assert Counter(item.law_id for item in compiled.graph.equations) == Counter(
            item.law_id for item in original.graph.equations
        )


def test_entry10_consistent_identifier_rename_preserves_graph() -> None:
    original_ir = _build_ir(TOP_MINIMUM_CONTACT)
    original = _compile(original_ir)
    payload = original_ir.model_dump(mode="python", warnings="none")
    identifiers = sorted(_collect_fixture_identifiers(payload))
    mapping = {
        identifier: f"renamedVerticalCircleIdentifier{index}"
        for index, identifier in enumerate(identifiers, start=1)
    }
    renamed_payload = _rename_fixture_identifiers(payload, mapping)
    assert isinstance(renamed_payload, dict)
    renamed_ir = MechanicsProblemIRV1.model_validate(renamed_payload)
    renamed = _compile(renamed_ir)
    assert original.status is renamed.status is CompilerStatus.ready
    assert original.graph is not None and renamed.graph is not None
    assert original.graph.fingerprint == renamed.graph.fingerprint
    assert original.graph.selected_equation_ids == renamed.graph.selected_equation_ids
    assert Counter(item.law_id for item in original.graph.equations) == Counter(
        item.law_id for item in renamed.graph.equations
    )


def test_entry10_unit_aliases_preserve_normalized_graph_semantics() -> None:
    baseline = _compile(_build_ir(TOP_ROPE))
    alias = _compile(
        _build_ir(
            _source(
                raw_scalars=(
                    RawScalar("2", "kg"),
                    RawScalar("1.25", "m"),
                    RawScalar("9.81", "m/s2"),
                    RawScalar("5", "m/s"),
                )
            )
        )
    )
    assert baseline.status is alias.status is CompilerStatus.ready
    assert baseline.graph is not None and alias.graph is not None
    assert baseline.graph.fingerprint == alias.graph.fingerprint
    assert baseline.graph.selected_equation_ids == alias.graph.selected_equation_ids
    baseline_semantics = tuple(
        sorted(
            (item.law_id, repr(item.expression.model_dump(mode="json")))
            for item in baseline.graph.equations
        )
    )
    alias_semantics = tuple(
        sorted(
            (item.law_id, repr(item.expression.model_dump(mode="json")))
            for item in alias.graph.equations
        )
    )
    assert baseline_semantics == alias_semantics


def test_entry10_forbidden_legacy_answer_field_is_rejected_before_normalization() -> None:
    payload = _draft_payload(TOP_ROPE)
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["expected_answer"] = 999
    with pytest.raises(ValueError, match="answer-authority fields are forbidden"):
        MechanicsProblemDraftV1.model_validate(payload)


def _add_rolling_decoy(payload: dict[str, object]) -> None:
    states = payload["state_conditions"]
    assert isinstance(states, list)
    states.append(
        {
            "state_condition_id": "rollingDecoyState",
            "kind": "rolling",
            "state": "no_slip",
            "subject_id": PARTICLE_ID,
            "interval_id": INTERVAL_ID,
            "quantity_ids": ["radius", "speed"],
            "evidence_refs": ["carrierEvidence"],
        }
    )


def test_vertical_circle_rolling_decoy_cannot_enter_entry8_or_entry9(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(TOP_ROPE, mutation=_add_rolling_decoy)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_result.graph is None
