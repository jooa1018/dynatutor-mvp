"""Stage 7: what a blocked law is really blocked on.

The law-prerequisite matrix reports how often a law's *declared* prerequisites
hold while its emission function stays silent.  These tests pin down the two
things that number cannot tell you: which typed structure the emitter blocks on
first, and whether supplying it changes anything.

The positive control is the load-bearing test here.  A counterfactual that never
unlocks anything would report "a frame does not help" for a trivial reason — it
does not work.  So one test builds a polar context complete in every respect but
its frame, shows the engine emits nothing, adds only the frame, and shows the
engine emits the polar laws.  Every zero the other tests assert is meaningful
only because that one passes.

Nothing here reads a case ID, family, split, problem text, quote, expected
terminal, or expected answer.
"""

from __future__ import annotations

import json

import pytest

from engine.mechanics.contracts import (
    AxisName,
    EntityPrimitive,
    GeometryRelationKind,
    InteractionKind,
    IREntity,
    IRGeometryRelation,
    IRInteraction,
    IRMotionInterval,
    IRPoint,
    PointRole,
    QuantityComponent,
    QuantityRole,
    QuantityShape,
    ReferenceFrameType,
)
from engine.mechanics.laws import apply_core_laws
from engine.mechanics.laws.base import BoundQuantity, LawContext
from engine.mechanics.laws.core import _RULES
from engine.mechanics.math_ast import DimensionVector, SymbolDefinition, SymbolRef

from evaluation.phase56_stage7.blocked_law_diagnosis import (
    BLOCKED_LAW_DIAGNOSIS_VERSION,
    CounterfactualOutcome,
    UnmetPrerequisite,
    _with_frame,
    counterfactual_outcome,
    diagnose_blocked_laws,
    first_unmet_prerequisite,
)
from evaluation.phase56_stage7.redaction import assert_privacy_safe_artifact

_LENGTH = DimensionVector(length=1)
_SPEED = DimensionVector(length=1, time=-1)
_ACCELERATION = DimensionVector(length=1, time=-2)
_RATE = DimensionVector(time=-1)
_RATE2 = DimensionVector(time=-2)


def _quantity(
    name: str,
    *,
    role: QuantityRole,
    subject_id: str,
    component: QuantityComponent,
    dimension: DimensionVector,
    frame_id: str | None,
    interval_id: str,
    known: float | None,
) -> BoundQuantity:
    return BoundQuantity(
        quantity_id=f"q_{name}",
        symbol_id=f"s_{name}",
        role=role,
        subject_id=subject_id,
        point_id=None,
        frame_id=frame_id,
        interval_id=interval_id,
        event_id=None,
        component=component,
        shape=QuantityShape.scalar,
        dimension=dimension,
        expression=SymbolRef(symbol_id=f"s_{name}", dimension=dimension),
        evidence_ids=(f"ev_{name}",),
        known_si_value=known,
    )


def _polar_context(*, frame_id: str | None) -> LawContext:
    """A polar problem stated completely, in a frame that may not exist yet.

    Everything ``_polar_kinematics_profile`` requires is here: one particle and
    one observer entity, one interval covering both, one radius relation, and
    the eleven typed component quantities with the five source-known values and
    six unknowns.  When ``frame_id`` is ``None`` the quantities name no frame and
    the context carries none, which is exactly the shape the real projection
    produces today.
    """

    particle_id = "ent_particle"
    coordinate_id = "ent_observer"
    interval_id = "seg_1"
    spec = (
        ("radius", QuantityRole.radius, coordinate_id, QuantityComponent.radial, _LENGTH, 2.0),
        ("rdot", QuantityRole.velocity, coordinate_id, QuantityComponent.radial, _SPEED, 3.0),
        ("rddot", QuantityRole.acceleration, coordinate_id, QuantityComponent.radial, _ACCELERATION, 1.0),
        ("omega", QuantityRole.angular_velocity, coordinate_id, QuantityComponent.transverse, _RATE, 4.0),
        ("alpha", QuantityRole.angular_acceleration, coordinate_id, QuantityComponent.transverse, _RATE2, 5.0),
        ("vr", QuantityRole.velocity, particle_id, QuantityComponent.radial, _SPEED, None),
        ("vt", QuantityRole.velocity, particle_id, QuantityComponent.transverse, _SPEED, None),
        ("speed", QuantityRole.speed, particle_id, QuantityComponent.magnitude, _SPEED, None),
        ("ar", QuantityRole.acceleration, particle_id, QuantityComponent.radial, _ACCELERATION, None),
        ("at", QuantityRole.acceleration, particle_id, QuantityComponent.transverse, _ACCELERATION, None),
        ("amag", QuantityRole.acceleration, particle_id, QuantityComponent.magnitude, _ACCELERATION, None),
    )
    quantities = tuple(
        _quantity(
            name,
            role=role,
            subject_id=subject,
            component=component,
            dimension=dimension,
            frame_id=frame_id,
            interval_id=interval_id,
            known=known,
        )
        for name, role, subject, component, dimension, known in spec
    )
    return LawContext(
        quantities=quantities,
        entities=(
            IREntity(
                entity_id=particle_id,
                primitive=EntityPrimitive.particle,
                evidence_refs=("ev_particle",),
            ),
            IREntity(
                entity_id=coordinate_id,
                primitive=EntityPrimitive.reference_frame,
                evidence_refs=("ev_observer",),
            ),
        ),
        points=(),
        reference_frames=(),
        motion_intervals=(
            IRMotionInterval(
                interval_id=interval_id,
                order=1,
                subject_ids=(particle_id, coordinate_id),
                frame_id=frame_id,
                evidence_refs=("ev_interval",),
            ),
        ),
        events=(),
        geometry=(
            IRGeometryRelation(
                relation_id="geo_radius",
                kind=GeometryRelationKind.radius,
                participant_ids=(particle_id, coordinate_id),
                quantity_ids=("q_radius",),
                interval_id=interval_id,
                evidence_refs=("ev_radius",),
            ),
        ),
        interactions=(),
        state_conditions=(),
        assumptions=(),
        approved_assumption_ids=frozenset(),
        symbols=tuple(
            SymbolDefinition(symbol_id=item.symbol_id, quantity_id=item.quantity_id, dimension=item.dimension)
            for item in quantities
        ),
        hinted_principles=(),
    )


def _emitted_law_ids(context: LawContext) -> frozenset[str]:
    return frozenset(item.rule.law_id for item in apply_core_laws(context))


# --------------------------------------------------------------------------
# Positive control — the counterfactual can unlock a law
# --------------------------------------------------------------------------


def test_a_polar_context_emits_nothing_while_its_frame_is_missing() -> None:
    assert _emitted_law_ids(_polar_context(frame_id=None)) == frozenset()


def test_adding_only_a_polar_frame_makes_the_engine_emit_the_polar_laws() -> None:
    """The load-bearing control: a frame alone, and the law fires.

    Nothing but the frame is added — the same augmentation the diagnosis
    applies.  Without this passing, every measured zero elsewhere would be
    indistinguishable from a broken counterfactual.
    """

    unframed = _polar_context(frame_id=None)
    framed = _with_frame(
        unframed,
        ReferenceFrameType.radial_transverse,
        (AxisName.radial, AxisName.transverse),
        scope_quantities=True,
    )
    emitted = _emitted_law_ids(framed)
    assert "polar_velocity_radial" in emitted
    assert "polar_velocity_transverse" in emitted
    assert "planar_acceleration_magnitude" in emitted
    assert "acceleration_magnitude_nonnegative" in emitted


def test_the_counterfactual_reports_the_unlock_it_measured() -> None:
    """A source that already types its components needs only the frame."""

    unframed = _polar_context(frame_id=None)
    outcome = counterfactual_outcome(unframed, _RULES["polar_velocity_radial"])
    assert outcome is CounterfactualOutcome.polar_frame_alone_unlocks


def test_a_source_grounded_frame_binding_is_never_overwritten() -> None:
    """Filling an absent frame is adding one; replacing a stated one is not."""

    stated = _polar_context(frame_id="frame_from_source")
    augmented = _with_frame(
        stated,
        ReferenceFrameType.radial_transverse,
        (AxisName.radial, AxisName.transverse),
        scope_quantities=True,
    )
    assert {item.frame_id for item in augmented.quantities} == {"frame_from_source"}


def test_a_cartesian_frame_does_not_unlock_a_polar_law() -> None:
    """The right frame type is what matters, not the presence of any frame."""

    unframed = _polar_context(frame_id=None)
    for frame_type, axes in (
        (ReferenceFrameType.cartesian_1d, (AxisName.x,)),
        (ReferenceFrameType.cartesian_2d, (AxisName.x, AxisName.y)),
    ):
        framed = _with_frame(unframed, frame_type, axes, scope_quantities=True)
        assert "polar_velocity_radial" not in _emitted_law_ids(framed)


def test_the_counterfactual_never_mutates_the_context_it_was_given() -> None:
    unframed = _polar_context(frame_id=None)
    before = _emitted_law_ids(unframed)
    counterfactual_outcome(unframed, _RULES["polar_velocity_radial"])
    assert unframed.reference_frames == ()
    assert _emitted_law_ids(unframed) == before


# --------------------------------------------------------------------------
# First unmet typed prerequisite
# --------------------------------------------------------------------------


def test_a_complete_polar_context_without_a_frame_reports_the_missing_frame() -> None:
    assert (
        first_unmet_prerequisite(_polar_context(frame_id=None), _RULES["polar_velocity_radial"])
        is UnmetPrerequisite.missing_frame
    )


def test_a_frame_of_the_wrong_type_is_not_reported_as_a_missing_frame() -> None:
    context = _with_frame(
        _polar_context(frame_id=None),
        ReferenceFrameType.body_fixed,
        (AxisName.x,),
        scope_quantities=True,
    )
    assert (
        first_unmet_prerequisite(context, _RULES["polar_velocity_radial"])
        is UnmetPrerequisite.wrong_frame_type
    )


def test_a_law_about_a_body_the_source_never_declares_is_not_applicable() -> None:
    """A rigid-body point law has nothing to say about a lone particle."""

    context = _polar_context(frame_id=None)
    assert (
        first_unmet_prerequisite(context, _RULES["rigid_point_velocity"])
        is UnmetPrerequisite.law_not_semantically_applicable
    )


def test_a_rigid_body_without_points_reports_the_missing_point_not_the_frame() -> None:
    base = _polar_context(frame_id=None)
    body = IREntity(
        entity_id="ent_body",
        primitive=EntityPrimitive.rigid_body,
        evidence_refs=("ev_body",),
    )
    context = _with_frame(
        LawContext(
            **{
                **{
                    field: getattr(base, field)
                    for field in base.__dataclass_fields__
                    if field != "entities"
                },
                "entities": (*base.entities, body),
            }
        ),
        ReferenceFrameType.cartesian_2d,
        (AxisName.x, AxisName.y),
        scope_quantities=True,
    )
    assert (
        first_unmet_prerequisite(context, _RULES["rigid_point_velocity"])
        is UnmetPrerequisite.missing_point
    )


def test_every_blocked_pair_receives_exactly_one_closed_classification() -> None:
    context = _polar_context(frame_id=None)
    for rule in _RULES.values():
        unmet = first_unmet_prerequisite(context, rule)
        assert isinstance(unmet, UnmetPrerequisite)
        assert unmet.value in {item.value for item in UnmetPrerequisite}


# --------------------------------------------------------------------------
# Report shape, determinism, and privacy
# --------------------------------------------------------------------------


def test_the_report_counts_every_blocked_context_once_per_law() -> None:
    report = diagnose_blocked_laws([_polar_context(frame_id=None)])
    assert report.version == BLOCKED_LAW_DIAGNOSIS_VERSION
    assert report.context_count == 1
    for law in report.laws:
        assert law.blocked_contexts == sum(
            count for _, count in law.counterfactual_counts
        )


def test_a_law_that_always_emits_is_not_reported_as_blocked() -> None:
    framed = _with_frame(
        _polar_context(frame_id=None),
        ReferenceFrameType.radial_transverse,
        (AxisName.radial, AxisName.transverse),
        scope_quantities=True,
    )
    report = diagnose_blocked_laws([framed])
    assert "polar_velocity_radial" not in {law.law_id for law in report.laws}


def test_the_report_is_deterministic_for_the_same_contexts() -> None:
    contexts = [_polar_context(frame_id=None)]
    assert diagnose_blocked_laws(contexts).as_dict() == diagnose_blocked_laws(contexts).as_dict()


def test_the_report_is_privacy_safe_and_carries_no_identity() -> None:
    payload = diagnose_blocked_laws([_polar_context(frame_id=None)]).as_dict()
    assert_privacy_safe_artifact(payload)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for marker in ("ent_particle", "ent_observer", "seg_1", "geo_radius", "ev_radius", "s_omega"):
        assert marker not in text


def test_the_diagnosis_returns_counts_and_codes_only() -> None:
    """No Draft, IR, expression, or context escapes into the report."""

    payload = diagnose_blocked_laws([_polar_context(frame_id=None)]).as_dict()
    for law in payload["laws"]:
        assert set(law) == {
            "law_id",
            "tier",
            "declared_satisfied",
            "emitted",
            "blocked_contexts",
            "unmet_counts",
            "counterfactual_counts",
        }
        for value in law["unmet_counts"].values():
            assert isinstance(value, int)
        for key in law["counterfactual_counts"]:
            assert key in {item.value for item in CounterfactualOutcome}


def test_no_production_module_imports_the_diagnosis() -> None:
    """The counterfactual is an evaluator instrument, not a runtime input."""

    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in (*(root / "engine").rglob("*.py"), *(root / "app").rglob("*.py")):
        if "blocked_law_diagnosis" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


@pytest.mark.parametrize(
    "law_id",
    ["polar_velocity_radial", "planar_acceleration_magnitude", "rigid_point_velocity"],
)
def test_a_diagnosed_law_is_a_real_catalogue_law(law_id: str) -> None:
    assert law_id in _RULES
