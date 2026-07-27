"""Stable public imports and bounded mechanics-law extensions."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from engine.mechanics.contracts import QuantityRole, QuantityShape
from engine.mechanics.math_ast import Equality, Multiply, Subtract
from engine.mechanics.laws.base import (
    BoundQuantity,
    InitialConditionBinding,
    LawContext,
    LawEmission,
    LawRule,
)
from engine.mechanics.laws.core import CORE_LAW_CATALOG, apply_core_laws, core_law_catalog
from engine.mechanics.laws import core as _core


# The typed IR stores magnitude and axis sign separately.  The historical
# impulse--momentum emitter used bare symbol references, which made a source
# statement such as "leftward impulse 9 N*s" numerically positive.  Replace only
# that endpoint law with the coordinate-correct signed balance.  No text, case,
# family, solver, root, or expected answer participates.
_original_momentum_emissions: Callable[[LawContext], list[LawEmission]] = (
    _core._momentum_emissions
)


def _direct_impulse_momentum_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    for interval in context.motion_intervals:
        if interval.start_event_id is None or interval.end_event_id is None:
            continue
        for subject_id in interval.subject_ids:
            masses = tuple(
                item
                for item in _core._by_role(context, QuantityRole.mass)
                if item.subject_id == subject_id
                and item.shape is QuantityShape.scalar
            )
            starts = tuple(
                item
                for item in _core._by_role(context, QuantityRole.velocity)
                if item.subject_id == subject_id
                and item.interval_id == interval.interval_id
                and item.event_id == interval.start_event_id
            )
            ends = tuple(
                item
                for item in _core._by_role(context, QuantityRole.velocity)
                if item.subject_id == subject_id
                and item.interval_id == interval.interval_id
                and item.event_id == interval.end_event_id
            )
            impulses = tuple(
                item
                for item in _core._by_role(context, QuantityRole.impulse)
                if item.subject_id == subject_id
                and item.interval_id == interval.interval_id
                and (
                    item.event_id is None
                    or (
                        item.event_id == interval.end_event_id
                        and item.known_si_value is None
                    )
                )
            )
            if not (
                len(masses) == len(starts) == len(ends) == len(impulses) == 1
                and _core._shape_compatible(starts[0], ends[0], impulses[0])
                and _core._component_compatible(starts[0], ends[0])
                and _core._component_compatible(starts[0], impulses[0])
                and starts[0].frame_id
                == ends[0].frame_id
                == impulses[0].frame_id
                and starts[0].frame_id is not None
            ):
                continue
            change = Multiply(
                factors=(
                    masses[0].expression,
                    Subtract(
                        left=_core._signed(ends[0]),
                        right=_core._signed(starts[0]),
                        dimension=ends[0].dimension,
                    ),
                ),
                dimension=impulses[0].dimension,
            )
            emitted.append(
                _core._emit(
                    context,
                    "linear_impulse_momentum",
                    Equality(left=_core._signed(impulses[0]), right=change),
                    (impulses[0], masses[0], starts[0], ends[0]),
                )
            )
    return emitted


def _signed_momentum_emissions(context: LawContext) -> list[LawEmission]:
    baseline = [
        item
        for item in _original_momentum_emissions(context)
        if item.rule.law_id != "linear_impulse_momentum"
    ]
    return [*baseline, *_direct_impulse_momentum_emissions(context)]


_signed_momentum_emissions._stage7_signed_impulse_v1 = True  # type: ignore[attr-defined]
_core._momentum_emissions = _signed_momentum_emissions


# A typed at-rest state is the authority for its zero equation.  Preserve the
# state's own evidence on the emitted equation/application; otherwise the
# independent source-evidence verifier sees the constraint evidence but no
# evidence on the equation it licensed and correctly rejects the candidate.
_original_topology_emissions: Callable[[LawContext], list[LawEmission]] = (
    _core._topology_constraint_emissions
)


def _state_evidenced_topology_emissions(context: LawContext) -> list[LawEmission]:
    states = {
        item.state_condition_id: item
        for item in context.state_conditions
    }
    out: list[LawEmission] = []
    for emission in _original_topology_emissions(context):
        if emission.rule.law_id != "state_at_rest" or len(emission.constraint_ids) != 1:
            out.append(emission)
            continue
        state = states.get(emission.constraint_ids[0])
        if state is None or not state.evidence_refs:
            out.append(emission)
            continue
        out.append(
            replace(
                emission,
                source_evidence_ids=tuple(
                    sorted(
                        set(emission.source_evidence_ids)
                        | set(state.evidence_refs)
                    )
                ),
            )
        )
    return out


_state_evidenced_topology_emissions._stage7_state_evidence_v1 = True  # type: ignore[attr-defined]
_core._topology_constraint_emissions = _state_evidenced_topology_emissions


__all__ = [
    "BoundQuantity",
    "CORE_LAW_CATALOG",
    "InitialConditionBinding",
    "LawContext",
    "LawEmission",
    "LawRule",
    "apply_core_laws",
    "core_law_catalog",
]
