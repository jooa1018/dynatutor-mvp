from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
from typing import Callable

import pytest

from engine.equation_generators.energy_momentum import solve_energy_momentum_system
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
from engine.mechanics.math_ast import DimensionVector, Equality, SymbolRef
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
from engine.solvers.rolling.rolling_general_I import RollingEnergyGeneralSolver
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
from test_phase56_mechanics_incline_same_fixture_parity import (
    ACCELERATION,
    MASS,
    _axis_binding,
    _quantity,
    _symbol,
    _text_evidence,
)
from test_phase56_mechanics_pure_rolling_same_fixture_parity import (
    APPROVED_ASSUMPTION_IDS as PURE_APPROVED_ASSUMPTION_IDS,
    BASELINE as PURE_BASELINE,
    _build_ir as _build_pure_ir,
)


ROLLING_INTERVAL_ID = "rollingInterval"
WORLD_FRAME_ID = "worldFrame"
BODY_ID = "rollingBody"
SURFACE_ID = "rollingIncline"
WORLD_ID = "world"
CENTER_POINT_ID = "massCenter"
CONTACT_POINT_ID = "contactPoint"

LENGTH = DimensionVector(length=1)
SPEED = DimensionVector(length=1, time=-1)
ANGULAR_VELOCITY = DimensionVector(time=-1)
MOMENT_OF_INERTIA = DimensionVector(mass=1, length=2)
APPROVED_ASSUMPTION_IDS = ("noEnergyLoss",)


@dataclass(frozen=True)
class RawScalar:
    value: str
    unit: str


@dataclass(frozen=True)
class GeneralRollingSource:
    problem_text: str
    mass_si: float
    radius_si: float
    inertia_si: float
    gravity_si: float
    height_si: float
    initial_speed_si: float
    mass_raw: RawScalar
    radius_raw: RawScalar
    inertia_raw: RawScalar
    gravity_raw: RawScalar
    height_raw: RawScalar
    initial_speed_raw: RawScalar | None

    def __post_init__(self) -> None:
        for value, label in (
            (self.mass_si, "mass"),
            (self.radius_si, "radius"),
            (self.inertia_si, "inertia"),
            (self.gravity_si, "gravity"),
            (self.height_si, "height"),
            (self.initial_speed_si, "initial speed"),
        ):
            if type(value) is not float or not math.isfinite(value):
                raise ValueError(f"{label} must be one finite float")

    @property
    def beta(self) -> float:
        return self.inertia_si / (self.mass_si * self.radius_si**2)

    @property
    def expected_final_speed_si(self) -> float:
        return math.sqrt(
            self.initial_speed_si**2
            + 2.0
            * self.mass_si
            * self.gravity_si
            * self.height_si
            / (self.mass_si + self.inertia_si / self.radius_si**2)
        )

    @property
    def expected_initial_omega_si(self) -> float:
        return self.initial_speed_si / self.radius_si

    @property
    def expected_final_omega_si(self) -> float:
        return self.expected_final_speed_si / self.radius_si

    @property
    def starts_from_rest(self) -> bool:
        return self.initial_speed_raw is None


def _source(
    *,
    mass_si: float = 3.0,
    radius_si: float = 0.4,
    inertia_si: float = 0.18,
    gravity_si: float = 9.81,
    height_si: float = 1.2,
    initial_speed_si: float = 0.0,
    evidenced_rest: bool = True,
    raw_scalars: tuple[
        RawScalar,
        RawScalar,
        RawScalar,
        RawScalar,
        RawScalar,
        RawScalar,
    ]
    | None = None,
    paraphrase_prefix: str = "",
) -> GeneralRollingSource:
    if raw_scalars is None:
        raw_scalars = (
            RawScalar(f"{mass_si:g}", "kg"),
            RawScalar(f"{radius_si:g}", "m"),
            RawScalar(f"{inertia_si:g}", "kg*m^2"),
            RawScalar(f"{gravity_si:g}", "m/s^2"),
            RawScalar(f"{height_si:g}", "m"),
            RawScalar(f"{initial_speed_si:g}", "m/s"),
        )
    (
        mass_raw,
        radius_raw,
        inertia_raw,
        gravity_raw,
        height_raw,
        supplied_initial_raw,
    ) = raw_scalars
    if evidenced_rest:
        if initial_speed_si != 0.0:
            raise ValueError("an evidenced rest state requires zero initial speed")
        initial_speed_raw = None
        initial_sentence = "It starts from rest."
    else:
        initial_speed_raw = supplied_initial_raw
        initial_sentence = (
            "Its initial center-of-mass speed is "
            f"{initial_speed_raw.value} {initial_speed_raw.unit}."
        )
    problem_text = " ".join(
        (
            paraphrase_prefix,
            f"A rolling rigid body has mass {mass_raw.value} {mass_raw.unit}.",
            f"Its radius is {radius_raw.value} {radius_raw.unit}.",
            (
                "Its moment of inertia about the mass center throughout the "
                f"rolling interval is {inertia_raw.value} {inertia_raw.unit}."
            ),
            f"Take g = {gravity_raw.value} {gravity_raw.unit}.",
            (
                "It descends through a vertical height of "
                f"{height_raw.value} {height_raw.unit}."
            ),
            initial_sentence,
            "It rolls on one fixed surface without slipping throughout the motion.",
            "Use a fixed Cartesian x-y world frame.",
            "Mechanical energy is conserved and there are no dissipative losses.",
            "Find its final nonnegative center-of-mass speed.",
        )
    ).strip()
    return GeneralRollingSource(
        problem_text=problem_text,
        mass_si=float(mass_si),
        radius_si=float(radius_si),
        inertia_si=float(inertia_si),
        gravity_si=float(gravity_si),
        height_si=float(height_si),
        initial_speed_si=float(initial_speed_si),
        mass_raw=mass_raw,
        radius_raw=radius_raw,
        inertia_raw=inertia_raw,
        gravity_raw=gravity_raw,
        height_raw=height_raw,
        initial_speed_raw=initial_speed_raw,
    )


BASELINE = _source()
NONZERO_INITIAL_SPEED = _source(initial_speed_si=0.8, evidenced_rest=False)
ZERO_HEIGHT = _source(height_si=0.0)
UNIT_NORMALIZED = _source(
    initial_speed_si=1.0,
    evidenced_rest=False,
    raw_scalars=(
        RawScalar("3000", "g"),
        RawScalar("40", "cm"),
        RawScalar("0.18", "kg*m^2"),
        RawScalar("9.81", "m/s^2"),
        RawScalar("120", "cm"),
        RawScalar("3.6", "km/h"),
    ),
)
BETA_AGREEMENT = _source(inertia_si=0.24)
COMMON_MASS_INERTIA_SCALE = _source(mass_si=6.0, inertia_si=0.36)
RADIUS_INERTIA_SCALE = _source(radius_si=0.8, inertia_si=0.72)
GH_INVARIANT = _source(gravity_si=4.905, height_si=2.4)
NEAR_ZERO_INERTIA = _source(inertia_si=1.0e-8)
LARGER_INERTIA = _source(inertia_si=0.72)
POSITIVE_CASES = (
    BASELINE,
    NONZERO_INITIAL_SPEED,
    ZERO_HEIGHT,
    UNIT_NORMALIZED,
    BETA_AGREEMENT,
    COMMON_MASS_INERTIA_SCALE,
    RADIUS_INERTIA_SCALE,
    GH_INVARIANT,
    NEAR_ZERO_INERTIA,
    LARGER_INERTIA,
)


PayloadMutation = Callable[[dict[str, object]], None]


def _draft_payload(source: GeneralRollingSource) -> dict[str, object]:
    mass_quote = (
        f"A rolling rigid body has mass {source.mass_raw.value} "
        f"{source.mass_raw.unit}."
    )
    radius_quote = (
        f"Its radius is {source.radius_raw.value} {source.radius_raw.unit}."
    )
    inertia_quote = (
        "Its moment of inertia about the mass center throughout the rolling "
        f"interval is {source.inertia_raw.value} {source.inertia_raw.unit}."
    )
    gravity_quote = (
        f"Take g = {source.gravity_raw.value} {source.gravity_raw.unit}."
    )
    height_quote = (
        "It descends through a vertical height of "
        f"{source.height_raw.value} {source.height_raw.unit}."
    )
    if source.initial_speed_raw is None:
        initial_quote = "It starts from rest."
        initial_token = None
    else:
        initial_quote = (
            "Its initial center-of-mass speed is "
            f"{source.initial_speed_raw.value} {source.initial_speed_raw.unit}."
        )
        initial_token = (
            f"{source.initial_speed_raw.value} {source.initial_speed_raw.unit}"
        )
    rolling_quote = (
        "It rolls on one fixed surface without slipping throughout the motion."
    )
    orientation_quote = "Use a fixed Cartesian x-y world frame."
    energy_quote = (
        "Mechanical energy is conserved and there are no dissipative losses."
    )
    query_quote = "Find its final nonnegative center-of-mass speed."
    evidence_specs = (
        ("massEvidence", mass_quote, f"{source.mass_raw.value} {source.mass_raw.unit}"),
        (
            "radiusEvidence",
            radius_quote,
            f"{source.radius_raw.value} {source.radius_raw.unit}",
        ),
        (
            "inertiaEvidence",
            inertia_quote,
            f"{source.inertia_raw.value} {source.inertia_raw.unit}",
        ),
        (
            "gravityEvidence",
            gravity_quote,
            f"{source.gravity_raw.value} {source.gravity_raw.unit}",
        ),
        (
            "heightEvidence",
            height_quote,
            f"{source.height_raw.value} {source.height_raw.unit}",
        ),
        ("initialEvidence", initial_quote, initial_token),
        ("rollingEvidence", rolling_quote, None),
        ("orientationEvidence", orientation_quote, None),
        ("energyEvidence", energy_quote, None),
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
    symbols = [
        _symbol(symbol_id, quantity_id, dimension)
        for symbol_id, quantity_id, dimension in (
            ("m", "mass", MASS),
            ("R", "radius", LENGTH),
            ("I", "shapeInertia", MOMENT_OF_INERTIA),
            ("g", "gravity", ACCELERATION),
            ("h", "heightDrop", LENGTH),
            ("v0", "initialSpeed", SPEED),
            ("omega0", "initialAngularSpeed", ANGULAR_VELOCITY),
            ("vf", "finalSpeed", SPEED),
            ("omegaf", "finalAngularSpeed", ANGULAR_VELOCITY),
        )
    ]
    quantities = [
        _quantity(
            "mass",
            "m",
            "mass",
            BODY_ID,
            MASS,
            provenance="explicit_source",
            evidence_refs=("massEvidence",),
            raw_value=source.mass_raw.value,
            raw_unit=source.mass_raw.unit,
        ),
        _quantity(
            "radius",
            "R",
            "radius",
            BODY_ID,
            LENGTH,
            provenance="explicit_source",
            evidence_refs=("radiusEvidence", "rollingEvidence"),
            raw_value=source.radius_raw.value,
            raw_unit=source.radius_raw.unit,
        ),
        _quantity(
            "shapeInertia",
            "I",
            "moment_of_inertia",
            BODY_ID,
            MOMENT_OF_INERTIA,
            point_id=CENTER_POINT_ID,
            interval_id=ROLLING_INTERVAL_ID,
            provenance="explicit_source",
            evidence_refs=("inertiaEvidence", "rollingEvidence"),
            raw_value=source.inertia_raw.value,
            raw_unit=source.inertia_raw.unit,
        ),
        _quantity(
            "gravity",
            "g",
            "gravity",
            WORLD_ID,
            ACCELERATION,
            provenance="explicit_source",
            evidence_refs=("gravityEvidence",),
            raw_value=source.gravity_raw.value,
            raw_unit=source.gravity_raw.unit,
        ),
        _quantity(
            "heightDrop",
            "h",
            "height",
            BODY_ID,
            LENGTH,
            provenance="explicit_source",
            evidence_refs=("heightEvidence",),
            raw_value=source.height_raw.value,
            raw_unit=source.height_raw.unit,
        ),
        _quantity(
            "initialSpeed",
            "v0",
            "speed",
            BODY_ID,
            SPEED,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="magnitude",
            provenance="inferred" if source.starts_from_rest else "explicit_source",
            evidence_refs=("initialEvidence", "rollingEvidence"),
            raw_value=(
                None
                if source.initial_speed_raw is None
                else source.initial_speed_raw.value
            ),
            raw_unit=(
                None
                if source.initial_speed_raw is None
                else source.initial_speed_raw.unit
            ),
        ),
        _quantity(
            "initialAngularSpeed",
            "omega0",
            "angular_velocity",
            BODY_ID,
            ANGULAR_VELOCITY,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="clockwise",
            direction={"kind": "semantic", "direction": "clockwise"},
            provenance="inferred",
            evidence_refs=("initialEvidence", "radiusEvidence", "rollingEvidence"),
        ),
        _quantity(
            "finalSpeed",
            "vf",
            "speed",
            BODY_ID,
            SPEED,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="magnitude",
            provenance="inferred",
            evidence_refs=(
                "heightEvidence",
                "rollingEvidence",
                "energyEvidence",
                "queryEvidence",
            ),
        ),
        _quantity(
            "finalAngularSpeed",
            "omegaf",
            "angular_velocity",
            BODY_ID,
            ANGULAR_VELOCITY,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="clockwise",
            direction={"kind": "semantic", "direction": "clockwise"},
            provenance="inferred",
            evidence_refs=("radiusEvidence", "rollingEvidence", "queryEvidence"),
        ),
    ]
    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnosticGeneralRollingLabel",
            "subtype": "diagnosticInertiaEnergyLabel",
            "model_id": "sameFixtureGeneralRollingTest",
            "source_text_sha256": hashlib.sha256(
                source.problem_text.encode("utf-8")
            ).hexdigest(),
        },
        "source_assets": [],
        "source_evidence": evidence,
        "entities": [
            {
                "entity_id": BODY_ID,
                "primitive": "rigid_body",
                "evidence_refs": [
                    "massEvidence",
                    "radiusEvidence",
                    "inertiaEvidence",
                    "heightEvidence",
                    "initialEvidence",
                    "rollingEvidence",
                    "queryEvidence",
                ],
            },
            {
                "entity_id": SURFACE_ID,
                "primitive": "incline",
                "evidence_refs": ["rollingEvidence"],
            },
            {
                "entity_id": WORLD_ID,
                "primitive": "environment",
                "evidence_refs": ["gravityEvidence"],
            },
        ],
        "points": [
            {
                "point_id": CENTER_POINT_ID,
                "role": "mass_center",
                "owner_entity_id": BODY_ID,
                "frame_id": WORLD_FRAME_ID,
                "evidence_refs": [
                    "massEvidence",
                    "radiusEvidence",
                    "inertiaEvidence",
                    "initialEvidence",
                    "queryEvidence",
                ],
            },
            {
                "point_id": CONTACT_POINT_ID,
                "role": "contact",
                "owner_entity_id": BODY_ID,
                "frame_id": WORLD_FRAME_ID,
                "evidence_refs": ["radiusEvidence", "rollingEvidence"],
            },
        ],
        "reference_frames": [
            {
                "frame_id": WORLD_FRAME_ID,
                "frame_type": "cartesian_2d",
                "origin": {"kind": "world"},
                "axes": [
                    _axis_binding("x", frame_id=WORLD_FRAME_ID),
                    _axis_binding("y", frame_id=WORLD_FRAME_ID),
                ],
                "evidence_refs": ["orientationEvidence"],
            }
        ],
        "motion_intervals": [
            {
                "interval_id": ROLLING_INTERVAL_ID,
                "order": 1,
                "subject_ids": [BODY_ID, SURFACE_ID, WORLD_ID],
                "frame_id": WORLD_FRAME_ID,
                "evidence_refs": [
                    "heightEvidence",
                    "initialEvidence",
                    "inertiaEvidence",
                    "rollingEvidence",
                    "energyEvidence",
                    "orientationEvidence",
                ],
            }
        ],
        "events": [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": [
            {
                "relation_id": "bodyRadiusGeometry",
                "kind": "radius",
                "participant_ids": [BODY_ID, CENTER_POINT_ID, CONTACT_POINT_ID],
                "quantity_ids": ["radius"],
                "interval_id": ROLLING_INTERVAL_ID,
                "evidence_refs": ["radiusEvidence", "rollingEvidence"],
            },
            {
                "relation_id": "rollingContactGeometry",
                "kind": "lies_on",
                "participant_ids": [BODY_ID, SURFACE_ID, CONTACT_POINT_ID],
                "quantity_ids": [],
                "interval_id": ROLLING_INTERVAL_ID,
                "evidence_refs": ["rollingEvidence"],
            },
        ],
        "interactions": [
            {
                "interaction_id": "gravityInteraction",
                "kind": "gravity",
                "participant_ids": [BODY_ID, WORLD_ID],
                "frame_id": WORLD_FRAME_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": ["mass", "gravity", "heightDrop"],
                "evidence_refs": [
                    "massEvidence",
                    "gravityEvidence",
                    "heightEvidence",
                ],
            },
            {
                "interaction_id": "rollingContact",
                "kind": "contact",
                "participant_ids": [BODY_ID, SURFACE_ID],
                "point_ids": [CONTACT_POINT_ID],
                "frame_id": WORLD_FRAME_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": ["radius"],
                "evidence_refs": ["radiusEvidence", "rollingEvidence"],
            },
        ],
        "constraints": [],
        "state_conditions": [
            {
                "state_condition_id": "touchingState",
                "kind": "contact",
                "state": "touching",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": [],
                "evidence_refs": ["rollingEvidence"],
            },
            {
                "state_condition_id": "fixedInclineState",
                "kind": "motion",
                "state": "at_rest",
                "subject_id": SURFACE_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": [],
                "evidence_refs": ["rollingEvidence"],
            },
            {
                "state_condition_id": "initialState",
                "kind": "initial",
                "state": "at_rest" if source.starts_from_rest else "moving",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": ["initialSpeed"],
                "evidence_refs": ["initialEvidence", "rollingEvidence"],
            },
            {
                "state_condition_id": "finalRollingState",
                "kind": "final",
                "state": "rolling",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": ["finalSpeed", "finalAngularSpeed"],
                "evidence_refs": [
                    "heightEvidence",
                    "rollingEvidence",
                    "energyEvidence",
                    "queryEvidence",
                ],
            },
            {
                "state_condition_id": "pureRollingState",
                "kind": "rolling",
                "state": "no_slip",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "quantity_ids": [
                    "radius",
                    "initialSpeed",
                    "initialAngularSpeed",
                    "finalSpeed",
                    "finalAngularSpeed",
                ],
                "evidence_refs": ["radiusEvidence", "rollingEvidence"],
            },
        ],
        "queries": [
            {
                "query_id": "queryTarget",
                "target": {
                    "role": "speed",
                    "subject_id": BODY_ID,
                    "point_id": CENTER_POINT_ID,
                    "frame_id": WORLD_FRAME_ID,
                    "interval_id": ROLLING_INTERVAL_ID,
                    "component": "magnitude",
                    "target_quantity_id": "finalSpeed",
                },
                "output_unit": "m/s",
                "output_dimension": SPEED.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": ["queryEvidence"],
            }
        ],
        "principle_hints": [],
        "assumptions": [
            {
                "assumption_id": "noEnergyLoss",
                "kind": "no_energy_loss",
                "subject_id": BODY_ID,
                "interval_id": ROLLING_INTERVAL_ID,
                "disposition": "approved",
                "reason": (
                    "The source explicitly states that mechanical energy is "
                    "conserved without dissipative losses."
                ),
                "evidence_refs": ["energyEvidence"],
            }
        ],
        "ambiguities": [],
        "figure_dependency": {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        },
        "unsupported_features": [],
    }


def _normalize(
    source: GeneralRollingSource,
    *,
    mutation: PayloadMutation | None = None,
    approved_assumption_ids: tuple[str, ...] = APPROVED_ASSUMPTION_IDS,
) -> NormalizationResult:
    payload = _draft_payload(source)
    if mutation is not None:
        mutation(payload)
    draft = MechanicsProblemDraftV1.model_validate(payload)
    return normalize_draft(
        source.problem_text,
        draft,
        approved_assumption_ids=approved_assumption_ids,
    )


def _build_ir(source: GeneralRollingSource) -> MechanicsProblemIRV1:
    normalization = _normalize(source)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert normalization.accepted is True
    assert type(normalization.ir) is MechanicsProblemIRV1
    return normalization.ir


def _execute(
    ir: MechanicsProblemIRV1,
    *,
    approved_assumption_ids: tuple[str, ...] = APPROVED_ASSUMPTION_IDS,
) -> MechanicsMigrationProbeExecution:
    return execute_mechanics_ir_probe(
        ir,
        approved_assumption_ids=approved_assumption_ids,
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


@dataclass(frozen=True)
class GeneralRollingResiduals:
    initial_no_slip: float
    final_no_slip: float
    reduced_energy: float
    final_speed_si: float

    @property
    def passed(self) -> bool:
        return (
            all(
                abs(value) <= 1.0e-9
                for value in (
                    self.initial_no_slip,
                    self.final_no_slip,
                    self.reduced_energy,
                )
            )
            and self.final_speed_si >= -1.0e-12
        )


def _independent_residuals(
    source: GeneralRollingSource,
    values: dict[str, float],
) -> GeneralRollingResiduals:
    assert {"omega0", "omegaf", "vf"}.issubset(values)
    return GeneralRollingResiduals(
        initial_no_slip=(
            source.initial_speed_si - source.radius_si * values["omega0"]
        ),
        final_no_slip=(
            values["vf"] - source.radius_si * values["omegaf"]
        ),
        reduced_energy=(
            (source.mass_si + source.inertia_si / source.radius_si**2)
            * (values["vf"] ** 2 - source.initial_speed_si**2)
            - 2.0 * source.mass_si * source.gravity_si * source.height_si
        ),
        final_speed_si=values["vf"],
    )


def _legacy_problem(source: GeneralRollingSource) -> CanonicalProblem:
    knowns = {
        "m": Quantity("m", source.mass_si, "kg"),
        "R": Quantity("R", source.radius_si, "m"),
        "I": Quantity("I", source.inertia_si, "kg*m^2"),
        "g": Quantity("g", source.gravity_si, "m/s^2"),
        "h": Quantity("h", source.height_si, "m"),
    }
    if not source.starts_from_rest:
        knowns["v0"] = Quantity("v0", source.initial_speed_si, "m/s")
    return CanonicalProblem(
        raw_text=source.problem_text,
        system_type="rolling_energy_general",
        knowns=knowns,
        unknowns=["final_velocity"],
        requested_outputs=["final_velocity"],
        flags={
            "starts_from_rest": source.starts_from_rest,
            "no_slip": True,
            "no_energy_loss": True,
        },
    )


def _observe_legacy(
    source: GeneralRollingSource,
) -> tuple[LegacyObservation, SolverResult]:
    problem = _legacy_problem(source)
    generated = solve_energy_momentum_system(problem)
    assert generated.ok is True, generated.errors
    assert set(generated.solution) == {"v", "v0", "omega", "beta", "mode"}
    raw_v = generated.solution["v"]
    assert type(raw_v) is float and math.isfinite(raw_v) and raw_v >= 0.0
    assert generated.solution["mode"] == "I"
    assert generated.solution["v0"] == pytest.approx(
        source.initial_speed_si, rel=0.0, abs=1.0e-12
    )
    assert generated.solution["omega"] == pytest.approx(
        raw_v / source.radius_si, rel=0.0, abs=1.0e-12
    )
    assert generated.solution["beta"] == pytest.approx(
        source.beta, rel=0.0, abs=1.0e-12
    )

    result = RollingEnergyGeneralSolver().solve(problem)
    assert result.ok is True, result.unsupported_reason
    assert result.verification.passed is True
    assert result.answer is not None
    assert result.answer.symbolic is not None
    assert result.answer.numeric == pytest.approx(
        round(raw_v, 6), rel=0.0, abs=1.0e-12
    )
    speed_answer = next(item for item in result.answers if item.symbol == "v")
    assert speed_answer.numeric == pytest.approx(
        round(raw_v, 6), rel=0.0, abs=1.0e-12
    )
    omega_answer = next(item for item in result.answers if item.symbol == "omega")
    assert omega_answer.numeric == pytest.approx(
        round(raw_v / source.radius_si, 6), rel=0.0, abs=1.0e-12
    )

    normalized = normalize_quantity("%r" % raw_v, "m/s", "scalar", SPEED)
    assert type(normalized.value) is float
    observation = LegacyObservation(
        case_id=(
            "generalRolling"
            + hashlib.sha256(source.problem_text.encode("utf-8")).hexdigest()[:32]
        ),
        diagnostic_kernel_id="rollingEnergyGeneralDirectV1",
        terminal=LegacyTerminal.solved,
        query_symbol_id="vf",
        si_unit=render_canonical_si_unit(SPEED),
        selected_scalar_si=normalized.value,
        complete_candidate_scalars_si=(
            LegacyCandidateScalar(value_si=normalized.value, multiplicity=1),
        ),
        residual_passed=math.isclose(
            raw_v,
            source.expected_final_speed_si,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
    )
    return observation, result


@dataclass(frozen=True)
class SameFixtureEvidence:
    registry_entry: str
    ir: MechanicsProblemIRV1
    execution: MechanicsMigrationProbeExecution
    observation: LegacyObservation
    report: LegacyDifferentialReport
    residuals: GeneralRollingResiduals


def _same_fixture(source: GeneralRollingSource) -> SameFixtureEvidence:
    ir = _build_ir(source)
    assert "raw_text" not in type(ir).model_fields

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
    residuals = _independent_residuals(source, _candidate_values(execution))
    assert residuals.passed is True

    # Freeze every generic artifact before observing the same-fixture legacy
    # kernel; the differential harness is evidence only, never query authority.
    observation, _ = _observe_legacy(source)
    report = build_legacy_differential_report(execution.solve_result, observation)
    assert build_generic_result_invariance_signature(
        execution.solve_result
    ) == frozen_signature
    assert execution.compiler_result.graph.fingerprint == frozen_graph
    assert execution.solve_result.plan.plan_fingerprint == frozen_plan
    assert tuple(sorted(_candidate_values(execution).items())) == frozen_values
    assert _independent_residuals(source, _candidate_values(execution)) == residuals
    return SameFixtureEvidence(
        registry_entry="rolling_energy_general",
        ir=ir,
        execution=execution,
        observation=observation,
        report=report,
        residuals=residuals,
    )


def _forbid_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> SolverResult:
        raise AssertionError("a generic rolling-I case must not call legacy")

    monkeypatch.setattr(RollingEnergyGeneralSolver, "solve", forbidden)
    monkeypatch.setattr(
        "engine.equation_generators.energy_momentum.solve_energy_momentum_system",
        forbidden,
    )


def _compile(
    ir: MechanicsProblemIRV1,
    approved: tuple[str, ...] = APPROVED_ASSUMPTION_IDS,
):
    return MechanicsCompiler().compile(
        ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(ir),
        approved_assumption_ids=approved,
    )


def test_rolling_general_exact_profile_compiles_fast_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    result = _compile(_build_ir(BASELINE))
    assert result.status is CompilerStatus.ready, result.issues
    assert result.graph is not None
    assert Counter(item.law_id for item in result.graph.equations) == Counter(
        {
            "state_at_rest": 1,
            "rolling_no_slip": 2,
            "rolling_general_principal_energy": 1,
        }
    )
    assert "pure_rolling_shape_inertia" not in {
        item.law_id for item in result.graph.equations
    }


@pytest.mark.slow
@pytest.mark.parametrize(
    "source",
    POSITIVE_CASES,
    ids=(
        "arbitrary-explicit-inertia-baseline",
        "nonzero-initial-speed",
        "zero-height-drop",
        "mixed-source-unit-normalization",
        "beta-mass-radius-agreement",
        "common-mass-inertia-scaling",
        "radius-and-inertia-quadratic-scaling",
        "gravity-height-product-invariance",
        "near-zero-positive-inertia",
        "larger-inertia-monotonicity",
    ),
)
def test_rolling_general_same_fixture_full_parity(
    source: GeneralRollingSource,
) -> None:
    evidence = _same_fixture(source)
    compiler = evidence.execution.compiler_result
    result = evidence.execution.solve_result
    assert evidence.registry_entry == "rolling_energy_general"
    assert compiler is not None and compiler.graph is not None
    assert evidence.execution.compiler_status is CompilerStatus.ready
    assert result is not None
    assert evidence.execution.solve_terminal is MechanicsSolveTerminal.solved

    graph = compiler.graph
    expected_laws = Counter(
        {
            "rolling_no_slip": 2,
            "rolling_general_principal_energy": 1,
        }
    )
    if source.starts_from_rest:
        expected_laws["state_at_rest"] = 1
    assert Counter(item.law_id for item in graph.equations) == expected_laws
    assert not any(
        item.law_id == "pure_rolling_shape_inertia" for item in graph.equations
    )
    assert evidence.ir.constraints == ()
    assert tuple(item.assumption_id for item in evidence.ir.assumptions) == (
        "noEnergyLoss",
    )

    equations_by_law = {
        law_id: tuple(item for item in graph.equations if item.law_id == law_id)
        for law_id in expected_laws
    }
    no_slip_equations = equations_by_law["rolling_no_slip"]
    assert len(no_slip_equations) == 2
    assert {
        frozenset(item.source_quantity_ids) for item in no_slip_equations
    } == {
        frozenset(("radius", "initialSpeed", "initialAngularSpeed")),
        frozenset(("radius", "finalSpeed", "finalAngularSpeed")),
    }
    assert all(
        set(item.source_evidence_ids)
        == {
            "energyEvidence",
            "gravityEvidence",
            "heightEvidence",
            "initialEvidence",
            "massEvidence",
            "queryEvidence",
            "radiusEvidence",
            "rollingEvidence",
        }
        for item in no_slip_equations
    )
    assert all(
        set(item.constraint_ids)
        == {
            "bodyRadiusGeometry",
            "pureRollingState",
            "touchingState",
            "fixedInclineState",
        }
        for item in no_slip_equations
    )
    principal_energy = equations_by_law["rolling_general_principal_energy"]
    assert len(principal_energy) == 1
    assert principal_energy[0].assumption_ids == ("noEnergyLoss",)
    assert set(principal_energy[0].constraint_ids) == {
        "initialState",
        "finalRollingState",
        "pureRollingState",
        "touchingState",
        "fixedInclineState",
        "bodyRadiusGeometry",
        "rollingContactGeometry",
    }
    assert set(principal_energy[0].source_quantity_ids) == {
        "mass",
        "radius",
        "shapeInertia",
        "gravity",
        "heightDrop",
        "initialSpeed",
        "finalSpeed",
    }
    assert set(principal_energy[0].source_evidence_ids) == {
        "energyEvidence",
        "gravityEvidence",
        "heightEvidence",
        "inertiaEvidence",
        "initialEvidence",
        "massEvidence",
        "queryEvidence",
        "radiusEvidence",
        "rollingEvidence",
    }
    if source.starts_from_rest:
        rest_equation = equations_by_law["state_at_rest"]
        assert len(rest_equation) == 1
        assert rest_equation[0].assumption_ids == ()
        assert rest_equation[0].constraint_ids == ("initialState",)
        assert rest_equation[0].source_quantity_ids == ("initialSpeed",)
        assert set(rest_equation[0].source_evidence_ids) == {
            "energyEvidence",
            "heightEvidence",
            "initialEvidence",
            "queryEvidence",
            "radiusEvidence",
            "rollingEvidence",
        }

    assert result.plan.primary_backend in {
        SolveBackendKind.linear_symbolic,
        SolveBackendKind.nonlinear_symbolic,
    }
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert result.candidate_set.generation_complete is True
    assert len(result.candidate_set.candidates) == 1
    candidate = result.candidate_set.candidates[0]
    assert candidate.query_symbol_id == "vf"
    assert candidate.root_multiplicity == 1
    assert candidate.query_value_si >= 0.0
    assert candidate.query_value_si == pytest.approx(
        source.expected_final_speed_si, rel=0.0, abs=1.0e-9
    )
    assert candidate.query_value_si == pytest.approx(
        evidence.observation.selected_scalar_si, rel=0.0, abs=1.0e-9
    )
    values = _candidate_values(evidence.execution)
    assert values["omega0"] == pytest.approx(
        source.expected_initial_omega_si, abs=1.0e-9
    )
    assert values["vf"] == pytest.approx(
        source.expected_final_speed_si, abs=1.0e-9
    )
    assert values["omegaf"] == pytest.approx(
        source.expected_final_omega_si, abs=1.0e-9
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
    assert evidence.residuals.passed is True
    assert evidence.observation.residual_passed is True
    assert evidence.report.status is DifferentialStatus.full_parity
    assert evidence.report.discrepancies == ()
    assert evidence.report.observation_terminal is LegacyTerminal.solved
    assert evidence.report.generic_terminal is MechanicsSolveTerminal.solved

    inertia_quantity = next(
        item for item in evidence.ir.quantities if item.quantity_id == "shapeInertia"
    )
    assert inertia_quantity.provenance.value == "explicit_source"
    assert inertia_quantity.si_value == pytest.approx(source.inertia_si)
    assert inertia_quantity.point_id == CENTER_POINT_ID
    assert inertia_quantity.interval_id == ROLLING_INTERVAL_ID

    if source is ZERO_HEIGHT:
        assert values["vf"] == pytest.approx(0.0, abs=1.0e-12)
        assert values["omegaf"] == pytest.approx(0.0, abs=1.0e-12)
    if source is UNIT_NORMALIZED:
        known_by_id = {item.quantity_id: item for item in evidence.ir.quantities}
        assert known_by_id["mass"].si_value == pytest.approx(3.0)
        assert known_by_id["radius"].si_value == pytest.approx(0.4)
        assert known_by_id["shapeInertia"].si_value == pytest.approx(0.18)
        assert known_by_id["gravity"].si_value == pytest.approx(9.81)
        assert known_by_id["heightDrop"].si_value == pytest.approx(1.2)
        assert known_by_id["initialSpeed"].si_value == pytest.approx(1.0)
    if source in {
        COMMON_MASS_INERTIA_SCALE,
        RADIUS_INERTIA_SCALE,
        GH_INVARIANT,
    }:
        assert values["vf"] == pytest.approx(
            BASELINE.expected_final_speed_si, rel=0.0, abs=1.0e-9
        )
    if source is BETA_AGREEMENT:
        assert source.beta == pytest.approx(0.5, abs=1.0e-12)
    if source is NEAR_ZERO_INERTIA:
        point_mass_limit = math.sqrt(2.0 * source.gravity_si * source.height_si)
        assert values["vf"] == pytest.approx(point_mass_limit, abs=1.0e-7)
    if source is LARGER_INERTIA:
        assert values["vf"] < BASELINE.expected_final_speed_si


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


def _append_event(payload: dict[str, object]) -> None:
    events = payload["events"]
    assert isinstance(events, list)
    events.append(
        {
            "event_id": "decoyEvent",
            "kind": "other",
            "subject_ids": [BODY_ID],
            "interval_ids": [],
            "evidence_refs": ["rollingEvidence"],
        }
    )


def _append_decoy_quantity(payload: dict[str, object]) -> None:
    symbols = payload["symbols"]
    quantities = payload["quantities"]
    assert isinstance(symbols, list) and isinstance(quantities, list)
    symbols.append(_symbol("decoySpeedSymbol", "decoySpeed", SPEED))
    quantities.append(
        _quantity(
            "decoySpeed",
            "decoySpeedSymbol",
            "speed",
            BODY_ID,
            SPEED,
            point_id=CENTER_POINT_ID,
            frame_id=WORLD_FRAME_ID,
            interval_id=ROLLING_INTERVAL_ID,
            component="magnitude",
            evidence_refs=("queryEvidence",),
        )
    )


def _append_client_constraint(payload: dict[str, object]) -> None:
    constraints = payload["constraints"]
    assert isinstance(constraints, list)
    constraints.append(
        {
            "constraint_id": "clientEnergyContamination",
            "kind": "constitutive",
            "expression": Equality(
                left=SymbolRef(symbol_id="m", dimension=MASS),
                right=SymbolRef(symbol_id="m", dimension=MASS),
            ).model_dump(mode="json"),
            "subject_ids": [BODY_ID],
            "interval_id": ROLLING_INTERVAL_ID,
            "evidence_refs": ["massEvidence"],
        }
    )


def _append_principle_hint(payload: dict[str, object]) -> None:
    hints = payload["principle_hints"]
    assert isinstance(hints, list)
    hints.append(
        {
            "hint_id": "clientWorkEnergyHint",
            "principle": "work_energy",
            "scope_ids": [BODY_ID],
            "evidence_refs": ["energyEvidence"],
            "model_confidence": 1.0,
        }
    )


def _append_shape_assumption(payload: dict[str, object]) -> None:
    assumptions = payload["assumptions"]
    assert isinstance(assumptions, list)
    assumptions.append(
        {
            "assumption_id": "shapeAuthority",
            "kind": "solid_sphere",
            "subject_id": BODY_ID,
            "interval_id": ROLLING_INTERVAL_ID,
            "disposition": "approved",
            "reason": "Deliberate dual-authority conflict fixture.",
            "evidence_refs": ["inertiaEvidence"],
        }
    )


def _remove_inertia_authority(payload: dict[str, object]) -> None:
    payload["symbols"] = [
        item for item in payload["symbols"] if item["quantity_id"] != "shapeInertia"
    ]
    payload["quantities"] = [
        item
        for item in payload["quantities"]
        if item["quantity_id"] != "shapeInertia"
    ]


def _make_inertia_inferred(payload: dict[str, object]) -> None:
    inertia = _record(payload, "quantities", "quantity_id", "shapeInertia")
    inertia["provenance"] = "inferred"
    inertia.pop("raw_value", None)
    inertia.pop("raw_unit", None)


@dataclass(frozen=True)
class CompilerRejectCase:
    label: str
    mutation: PayloadMutation


COMPILER_REJECT_CASES = (
    CompilerRejectCase("source-inertia-missing", _remove_inertia_authority),
    CompilerRejectCase("source-inertia-is-inferred", _make_inertia_inferred),
    CompilerRejectCase(
        "incline-primitive-erased",
        _set_field("entities", "entity_id", SURFACE_ID, "primitive", "surface"),
    ),
    CompilerRejectCase(
        "point-roles-erased",
        _compose(
            _set_field("points", "point_id", CENTER_POINT_ID, "role", "material"),
            _set_field("points", "point_id", CONTACT_POINT_ID, "role", "material"),
        ),
    ),
    CompilerRejectCase(
        "world-frame-is-not-cartesian-2d",
        _set_field(
            "reference_frames",
            "frame_id",
            WORLD_FRAME_ID,
            "frame_type",
            "body_fixed",
        ),
    ),
    CompilerRejectCase("event-contamination", _append_event),
    CompilerRejectCase(
        "radius-and-contact-topology-deleted",
        _compose(
            _remove_record("geometry", "relation_id", "bodyRadiusGeometry"),
            _remove_record("geometry", "relation_id", "rollingContactGeometry"),
        ),
    ),
    CompilerRejectCase(
        "gravity-and-contact-interactions-incomplete",
        _compose(
            _remove_record("interactions", "interaction_id", "gravityInteraction"),
            _set_field(
                "interactions", "interaction_id", "rollingContact", "point_ids", []
            ),
        ),
    ),
    CompilerRejectCase(
        "touching-and-fixed-incline-states-contradict",
        _compose(
            _set_field(
                "state_conditions",
                "state_condition_id",
                "touchingState",
                "state",
                "separated",
            ),
            _set_field(
                "state_conditions",
                "state_condition_id",
                "fixedInclineState",
                "state",
                "moving",
            ),
        ),
    ),
    CompilerRejectCase(
        "initial-state-deleted",
        _remove_record("state_conditions", "state_condition_id", "initialState"),
    ),
    CompilerRejectCase(
        "final-state-deleted",
        _remove_record(
            "state_conditions", "state_condition_id", "finalRollingState"
        ),
    ),
    CompilerRejectCase(
        "no-slip-carrier-deleted",
        _remove_record("state_conditions", "state_condition_id", "pureRollingState"),
    ),
    CompilerRejectCase(
        "loss-evidence-erased",
        _set_field(
            "assumptions",
            "assumption_id",
            "noEnergyLoss",
            "evidence_refs",
            [],
        ),
    ),
    CompilerRejectCase(
        "loss-assumption-deleted",
        _remove_record("assumptions", "assumption_id", "noEnergyLoss"),
    ),
    CompilerRejectCase("extra-quantity-authority", _append_decoy_quantity),
    CompilerRejectCase("client-constraint-contamination", _append_client_constraint),
    CompilerRejectCase("principle-hint-contamination", _append_principle_hint),
    CompilerRejectCase(
        "source-inertia-scope-corrupted",
        _compose(
            _set_field(
                "quantities",
                "quantity_id",
                "shapeInertia",
                "point_id",
                CONTACT_POINT_ID,
            ),
            _set_field(
                "quantities",
                "quantity_id",
                "shapeInertia",
                "interval_id",
                None,
            ),
        ),
    ),
    CompilerRejectCase(
        "angular-direction-corrupted",
        _set_field(
            "quantities",
            "quantity_id",
            "initialAngularSpeed",
            "direction",
            {"kind": "semantic", "direction": "counterclockwise"},
        ),
    ),
)


@pytest.mark.parametrize("case", COMPILER_REJECT_CASES, ids=lambda case: case.label)
def test_rolling_general_exact_contract_mismatches_are_precisely_unsupported(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=case.mutation)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)

    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.compiler_result.graph is None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


@pytest.mark.parametrize(
    "quantity_id",
    ("mass", "radius", "shapeInertia", "gravity", "heightDrop"),
)
def test_rolling_general_source_quantity_evidence_deletion_is_invalid(
    quantity_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(
        BASELINE,
        mutation=_set_field(
            "quantities", "quantity_id", quantity_id, "evidence_refs", []
        ),
    )
    assert normalization.terminal is ValidationTerminal.invalid
    assert normalization.ir is None


def test_rolling_general_dual_shape_and_source_inertia_authority_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(
        BASELINE,
        mutation=_append_shape_assumption,
        approved_assumption_ids=("noEnergyLoss", "shapeAuthority"),
    )
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(
        normalization.ir,
        approved_assumption_ids=("noEnergyLoss", "shapeAuthority"),
    )
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.requires_specialized_model
        for issue in execution.compiler_result.issues
    )


def test_entry8_source_inertia_contamination_remains_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    payload = _build_pure_ir(PURE_BASELINE).model_dump(mode="python", warnings="none")
    inertia = next(
        item
        for item in payload["quantities"]
        if item["quantity_id"] == "shapeInertia"
    )
    inertia.update(
        {
            "provenance": "explicit_source",
            "raw_value": "0.072",
            "raw_unit": "kg*m^2",
            "si_value": 0.072,
            "si_unit": "kg*m^2",
        }
    )
    contaminated = MechanicsProblemIRV1.model_validate(payload)
    execution = _execute(
        contaminated,
        approved_assumption_ids=PURE_APPROVED_ASSUMPTION_IDS,
    )
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None


def test_rolling_general_rejected_loss_assumption_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(
        BASELINE,
        mutation=_set_field(
            "assumptions",
            "assumption_id",
            "noEnergyLoss",
            "disposition",
            "rejected",
        ),
        approved_assumption_ids=(),
    )
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir, approved_assumption_ids=())
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.unsupported
    assert execution.solve_result is None


def test_rolling_general_unapproved_loss_assumption_needs_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, approved_assumption_ids=())
    assert normalization.terminal is ValidationTerminal.needs_confirmation
    assert normalization.ir is None


INVALID_DOMAIN_CASES = (
    _source(mass_si=0.0),
    _source(mass_si=-1.0),
    _source(radius_si=0.0),
    _source(radius_si=-0.4),
    _source(inertia_si=0.0),
    _source(inertia_si=-0.18),
    _source(gravity_si=0.0),
    _source(gravity_si=-9.81),
    _source(height_si=-0.1),
    _source(initial_speed_si=-0.1, evidenced_rest=False),
)


@pytest.mark.parametrize(
    "source",
    INVALID_DOMAIN_CASES,
    ids=(
        "zero-mass",
        "negative-mass",
        "zero-radius",
        "negative-radius",
        "zero-inertia",
        "negative-inertia",
        "zero-gravity",
        "negative-gravity",
        "negative-height-drop",
        "negative-source-initial-speed",
    ),
)
def test_rolling_general_invalid_numeric_domain_fails_without_legacy(
    source: GeneralRollingSource,
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


@pytest.mark.parametrize(
    "mutation",
    (
        _set_field(
            "quantities", "quantity_id", "shapeInertia", "raw_unit", "kg"
        ),
        _compose(
            _set_field(
                "quantities",
                "quantity_id",
                "shapeInertia",
                "dimension",
                LENGTH.model_dump(mode="json"),
            ),
            _set_field(
                "symbols",
                "symbol_id",
                "I",
                "dimension",
                LENGTH.model_dump(mode="json"),
            ),
        ),
    ),
    ids=("wrong-inertia-unit", "wrong-inertia-dimension"),
)
def test_rolling_general_wrong_inertia_units_or_dimensions_are_invalid(
    mutation: PayloadMutation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=mutation)
    assert normalization.terminal is ValidationTerminal.invalid
    assert normalization.ir is None


def _query_quantity(
    payload: dict[str, object],
    quantity_id: str,
    *,
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
    query["shape"] = "scalar"


def _query_target(quantity_id: str, output_unit: str) -> PayloadMutation:
    def mutate(payload: dict[str, object]) -> None:
        _query_quantity(payload, quantity_id, output_unit=output_unit)

    return mutate


def _unbind_query(payload: dict[str, object]) -> None:
    query = _record(payload, "queries", "query_id", "queryTarget")
    target = query["target"]
    assert isinstance(target, dict)
    target["target_quantity_id"] = None


PARTICLE_ESCAPE_QUERY_CASES = (
    CompilerRejectCase(
        "final-speed-query",
        _set_field("entities", "entity_id", BODY_ID, "primitive", "particle"),
    ),
    CompilerRejectCase(
        "source-mass-query",
        _compose(
            _set_field("entities", "entity_id", BODY_ID, "primitive", "particle"),
            _query_target("mass", "kg"),
        ),
    ),
    CompilerRejectCase(
        "source-inertia-query",
        _compose(
            _set_field("entities", "entity_id", BODY_ID, "primitive", "particle"),
            _query_target("shapeInertia", "kg*m^2"),
        ),
    ),
)


@pytest.mark.parametrize(
    "case", PARTICLE_ESCAPE_QUERY_CASES, ids=lambda case: case.label
)
def test_rolling_general_particle_mismatch_cannot_escape_through_generic_query(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=case.mutation)
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


UNSUPPORTED_QUERY_CASES = (
    CompilerRejectCase("initial-speed-query", _query_target("initialSpeed", "m/s")),
    CompilerRejectCase(
        "initial-angular-speed-query",
        _query_target("initialAngularSpeed", "rad/s"),
    ),
    CompilerRejectCase(
        "final-angular-speed-query", _query_target("finalAngularSpeed", "rad/s")
    ),
    CompilerRejectCase(
        "source-inertia-query", _query_target("shapeInertia", "kg*m^2")
    ),
    CompilerRejectCase("source-radius-query", _query_target("radius", "m")),
    CompilerRejectCase("source-mass-query", _query_target("mass", "kg")),
)


@pytest.mark.parametrize("case", UNSUPPORTED_QUERY_CASES, ids=lambda case: case.label)
def test_rolling_general_internal_queries_are_unsupported(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=case.mutation)
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


def test_rolling_general_unbound_ambiguous_query_is_invalid_without_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=_unbind_query)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    execution = _execute(normalization.ir)
    assert execution.terminal is MigrationProbeTerminal.compiler_rejected
    assert execution.compiler_status is CompilerStatus.invalid
    assert execution.solve_result is None
    assert execution.compiler_result is not None
    assert any(
        issue.code is CompilerIssueCode.unresolved_query
        for issue in execution.compiler_result.issues
    )


QUERY_INDEPENDENT_DELETION_CASES = (
    CompilerRejectCase(
        "inertia-query-plus-radius-relation-deletion",
        _compose(
            _query_target("shapeInertia", "kg*m^2"),
            _remove_record("geometry", "relation_id", "bodyRadiusGeometry"),
        ),
    ),
    CompilerRejectCase(
        "mass-query-plus-loss-authority-deletion",
        _compose(
            _query_target("mass", "kg"),
            _remove_record("assumptions", "assumption_id", "noEnergyLoss"),
        ),
    ),
    CompilerRejectCase(
        "angular-query-plus-no-slip-deletion",
        _compose(
            _query_target("finalAngularSpeed", "rad/s"),
            _remove_record(
                "state_conditions", "state_condition_id", "pureRollingState"
            ),
        ),
    ),
)


@pytest.mark.parametrize(
    "case", QUERY_INDEPENDENT_DELETION_CASES, ids=lambda case: case.label
)
def test_rolling_general_recognizer_resists_query_and_candidate_deletion(
    case: CompilerRejectCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(BASELINE, mutation=case.mutation)
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


def test_rolling_general_final_candidate_quantity_deletion_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_legacy_call(monkeypatch)
    normalization = _normalize(
        BASELINE,
        mutation=_compose(
            _remove_record("quantities", "quantity_id", "finalSpeed"),
            _remove_record("symbols", "symbol_id", "vf"),
        ),
    )
    assert normalization.terminal is ValidationTerminal.invalid
    assert normalization.ir is None


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
        metadata["system_type"] = "wrongDiagnosticFamily"
        metadata["subtype"] = "wrongDiagnosticSubtype"
        metadata["model_id"] = "wrongDiagnosticModel"
        metadata["source_text_sha256"] = hashlib.sha256(
            b"unrelated and deliberately misleading explicit inertia wording"
        ).hexdigest()
    return MechanicsProblemIRV1.model_validate(payload)


def test_entry9_metadata_raw_paraphrase_and_record_order_are_not_authority() -> None:
    original_ir = _build_ir(BASELINE)
    original = _compile(original_ir)
    assert original.status is CompilerStatus.ready
    assert original.graph is not None

    reordered_payload = original_ir.model_dump(mode="python", warnings="none")
    for collection_name in (
        "source_evidence",
        "entities",
        "points",
        "reference_frames",
        "symbols",
        "quantities",
        "geometry",
        "interactions",
        "state_conditions",
        "assumptions",
    ):
        reordered_payload[collection_name] = list(
            reversed(reordered_payload[collection_name])
        )
    reordered_ir = MechanicsProblemIRV1.model_validate(reordered_payload)
    paraphrased_ir = _build_ir(
        _source(
            paraphrase_prefix=(
                "A diagnostic answer key falsely says omega = 999 rad/s; ignore it."
            )
        )
    )
    variants = (
        _diagnostic_variant(original_ir, remove=False),
        _diagnostic_variant(original_ir, remove=True),
        reordered_ir,
        paraphrased_ir,
    )
    for variant in variants:
        compiled = _compile(variant)
        assert compiled.status is CompilerStatus.ready, compiled.issues
        assert compiled.graph is not None
        assert compiled.graph.fingerprint == original.graph.fingerprint
        assert compiled.graph.selected_equation_ids == original.graph.selected_equation_ids
        assert Counter(item.law_id for item in compiled.graph.equations) == Counter(
            item.law_id for item in original.graph.equations
        )


def test_entry9_consistent_identifier_rename_preserves_graph() -> None:
    original_ir = _build_ir(BASELINE)
    original = _compile(original_ir)
    payload = original_ir.model_dump(mode="python", warnings="none")
    identifiers = sorted(_collect_fixture_identifiers(payload))
    mapping = {
        identifier: f"renamedGeneralRollingIdentifier{index}"
        for index, identifier in enumerate(identifiers, start=1)
    }
    renamed_payload = _rename_fixture_identifiers(payload, mapping)
    assert isinstance(renamed_payload, dict)
    renamed_ir = MechanicsProblemIRV1.model_validate(renamed_payload)
    renamed = _compile(
        renamed_ir,
        tuple(mapping[item] for item in APPROVED_ASSUMPTION_IDS),
    )
    assert original.status is renamed.status is CompilerStatus.ready
    assert original.graph is not None and renamed.graph is not None
    assert original.graph.fingerprint == renamed.graph.fingerprint
    assert original.graph.selected_equation_ids == renamed.graph.selected_equation_ids
    assert Counter(item.law_id for item in original.graph.equations) == Counter(
        item.law_id for item in renamed.graph.equations
    )


def _source_with_inertia_unit(unit: str) -> GeneralRollingSource:
    return _source(
        raw_scalars=(
            RawScalar("3", "kg"),
            RawScalar("0.4", "m"),
            RawScalar("0.18", unit),
            RawScalar("9.81", "m/s^2"),
            RawScalar("1.2", "m"),
            RawScalar("0", "m/s"),
        )
    )


@pytest.mark.parametrize(
    "alias_unit",
    ("kg*m2", "kg·m²"),
    ids=("ascii-inertia-alias", "unicode-inertia-alias"),
)
def test_entry9_inertia_unit_aliases_preserve_normalized_graph_semantics(
    alias_unit: str,
) -> None:
    baseline = _compile(_build_ir(BASELINE))
    alias = _compile(_build_ir(_source_with_inertia_unit(alias_unit)))
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


def _add_inertia_alias_evidence(payload: dict[str, object]) -> None:
    inertia = _record(payload, "quantities", "quantity_id", "shapeInertia")
    inertia["evidence_refs"] = [
        "energyEvidence",
        "inertiaEvidence",
        "rollingEvidence",
    ]


def test_entry9_equation_semantics_ignore_alias_but_fingerprint_tracks_provenance(
) -> None:
    baseline = _compile(_build_ir(BASELINE))
    normalization = _normalize(BASELINE, mutation=_add_inertia_alias_evidence)
    assert normalization.terminal is ValidationTerminal.accepted, normalization.issues
    assert type(normalization.ir) is MechanicsProblemIRV1
    provenance_variant = _compile(normalization.ir)
    assert baseline.status is provenance_variant.status is CompilerStatus.ready
    assert baseline.graph is not None and provenance_variant.graph is not None
    assert baseline.graph.fingerprint != provenance_variant.graph.fingerprint
    assert Counter(item.law_id for item in baseline.graph.equations) == Counter(
        item.law_id for item in provenance_variant.graph.equations
    )
    baseline_semantics = tuple(
        sorted(
            (item.law_id, repr(item.expression.model_dump(mode="json")))
            for item in baseline.graph.equations
        )
    )
    variant_semantics = tuple(
        sorted(
            (item.law_id, repr(item.expression.model_dump(mode="json")))
            for item in provenance_variant.graph.equations
        )
    )
    assert baseline_semantics == variant_semantics
