"""Mechanical constructors for solver-authored ExplanationTrace evidence.

This module never solves, validates, selects, rounds, or mutates a public
answer.  A solver supplies its already-resolved physics contract; these helpers
only copy canonical/delivered values into the immutable Phase 53 dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from engine.models import (
    CalculationCoordinateFrame,
    CanonicalProblem,
    EquationEvidence,
    OutputEvidenceLink,
    SemanticFactEvidence,
    SolverExplanationEvidence,
    SolverResult,
    SubstitutionEvidence,
)


@dataclass(frozen=True)
class OutputSpec:
    output_id: str
    response_index: int
    output_key: str
    candidate_key: str
    equation_ids: tuple[str, ...]
    substitution_ids: tuple[str, ...]
    candidate_id: str | None = None
    candidate_numeric: float | int | None = None
    delivery_candidate_key: str | None = None
    delivery_transform: str = "identity"
    decimal_places: int | None = None
    delivery_policy_id: str = ""


def known_fact(canonical: CanonicalProblem, key: str) -> SemanticFactEvidence:
    quantity = canonical.knowns[key]
    if quantity.value is None or isinstance(quantity.value, bool):
        raise ValueError(f"known quantity {key!r} is not a resolved scalar")
    value = float(quantity.value)
    if not math.isfinite(value):
        raise ValueError(f"known quantity {key!r} is not finite")
    return SemanticFactEvidence(
        fact_id=f"known:{key}",
        semantic_key=key,
        value=quantity.value,
        unit=quantity.unit,
        source="canonical_known",
        classification="explicit",
    )


def semantic_fact(canonical: CanonicalProblem, key: str) -> SemanticFactEvidence:
    value = getattr(canonical, key)
    if value is None:
        raise ValueError(f"semantic fact {key!r} is unavailable")
    return SemanticFactEvidence(
        fact_id=f"semantic:{key}",
        semantic_key=key,
        value=value,
        unit=None,
        source="canonical_semantic",
        classification="explicit",
    )


def flag_fact(canonical: CanonicalProblem, key: str) -> SemanticFactEvidence:
    value = (canonical.flags or {}).get(key)
    if not isinstance(value, bool):
        raise ValueError(f"flag {key!r} is unavailable")
    return SemanticFactEvidence(
        fact_id=f"flag:{key}",
        semantic_key=key,
        value=value,
        unit=None,
        source="canonical_flag",
        classification="explicit",
    )


def assumption_fact(
    key: str, value: str | float, *, unit: str | None = None
) -> SemanticFactEvidence:
    return SemanticFactEvidence(
        fact_id=f"assumption:{key}",
        semantic_key=key,
        value=value,
        unit=unit,
        source="solver_assumption",
        classification="assumed",
    )


def gravity_fact(canonical: CanonicalProblem) -> SemanticFactEvidence:
    quantity = canonical.knowns.get("g")
    if quantity is not None and quantity.value is not None:
        if quantity.provenance_hint == "domain_default":
            # Preserve the exact default payload so the strict builder, rather
            # than this copying helper, rejects forged values/units fail-closed.
            return assumption_fact(
                "gravity_acceleration", quantity.value, unit=quantity.unit
            )
        return known_fact(canonical, "g")
    return assumption_fact("gravity_acceleration", 9.81, unit="m/s^2")


def calculation_frame(
    frame_id: str,
    coordinate_system: str,
    axes: Iterable[str],
    positive_directions: Iterable[str],
    units: Iterable[str],
) -> CalculationCoordinateFrame:
    return CalculationCoordinateFrame(
        frame_id=frame_id,
        coordinate_system=coordinate_system,
        axes=tuple(axes),
        positive_directions=tuple(positive_directions),
        units=tuple(units),
        source="solver_calculation",
        status="resolved",
    )


def attach_evidence(
    result: SolverResult,
    *,
    solver_name: str,
    coordinate_frame: CalculationCoordinateFrame,
    explicit_facts: Iterable[SemanticFactEvidence],
    assumptions: Iterable[SemanticFactEvidence] = (),
    equations: Iterable[EquationEvidence],
    substitutions: Iterable[SubstitutionEvidence],
    outputs: Iterable[OutputSpec],
    warnings: Iterable[str] = (),
) -> SolverResult:
    """Attach declared evidence using the already-produced response values."""

    delivered = list(result.answers or [])
    if not delivered:
        if result.answer is None:
            raise ValueError("structured evidence requires a delivered answer")
        delivered = [result.answer]
    delivery_candidate_id = f"delivery:{solver_name}:solve-response"
    links: list[OutputEvidenceLink] = []
    for spec in outputs:
        item = delivered[spec.response_index]
        numeric = getattr(item, "numeric", None)
        if (
            numeric is None
            or isinstance(numeric, bool)
            or not isinstance(numeric, (int, float))
            or not math.isfinite(float(numeric))
        ):
            raise ValueError(f"output {spec.output_id!r} is not a finite scalar")
        actual_key = getattr(item, "output_key", None)
        if actual_key != spec.output_key:
            raise ValueError(
                f"output {spec.output_id!r} key changed: {actual_key!r}"
            )
        candidate_numeric = (
            numeric if spec.candidate_numeric is None else spec.candidate_numeric
        )
        links.append(
            OutputEvidenceLink(
                output_id=spec.output_id,
                output_key=spec.output_key,
                candidate_id=spec.candidate_id or delivery_candidate_id,
                candidate_key=spec.candidate_key,
                candidate_numeric=candidate_numeric,
                numeric=numeric,
                unit=getattr(item, "unit", None),
                symbol=getattr(item, "symbol", None),
                role=getattr(item, "role", "primary"),
                response_index=spec.response_index,
                equation_ids=spec.equation_ids,
                substitution_ids=spec.substitution_ids,
                delivery_candidate_id=delivery_candidate_id,
                delivery_candidate_key=(
                    spec.delivery_candidate_key or spec.candidate_key
                ),
                delivery_transform=spec.delivery_transform,
                decimal_places=spec.decimal_places,
                delivery_policy_id=spec.delivery_policy_id,
            )
        )
    result.explanation_evidence = SolverExplanationEvidence(
        coordinate_frame=coordinate_frame,
        explicit_facts=tuple(explicit_facts),
        assumptions=tuple(assumptions),
        equations=tuple(equations),
        substitutions=tuple(substitutions),
        outputs=tuple(links),
        warnings=tuple(warnings),
    )
    return result
