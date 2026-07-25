"""Privacy-safe prerequisite matrix for the core mechanics law catalogue.

A law rule declares three prerequisites — the quantity roles it relates, the
interaction kinds it needs, and the approved assumption kinds that authorise it.
Its *emission function* enforces more than that: reference frames with declared
axes, points with typed roles, component and endpoint scope, interaction-owned
quantities, cardinality.  Those extra requirements are what actually decide
whether a source-grounded projection can reach a law, and they are invisible in
the rule alone.

This module measures the difference.  For each law it reports how many real
``LawContext`` values satisfy each *declared* tier, and how many of those go on
to emit anything.  A law with the declared tier satisfied and no emission has an
unmet structural prerequisite; that gap is the actionable signal.

Everything here is a count.  No case ID, family, split, problem text, quote,
expected terminal, expected answer, entity name, or numeric value participates,
and the matrix is built from the same catalogue the runtime uses rather than
from a transcribed copy of it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from engine.mechanics.contracts import AssumptionDisposition
from engine.mechanics.laws import apply_core_laws
from engine.mechanics.laws.base import LawContext, LawRule
from engine.mechanics.laws.core import core_law_catalog

LAW_PREREQUISITE_MATRIX_VERSION = "stage7-law-prerequisites-v1"


class LawTopologyTier(str, Enum):
    """How much typed topology a law needs beyond its declared prerequisites.

    Derived from the rule's own category and declared interactions, so the tier
    of a newly added law follows automatically rather than from a hand-kept list
    that could drift away from the catalogue.
    """

    # No interaction and no body model: quantities, intervals, events, states.
    particle_kinematics = "particle_kinematics"
    # No interaction, but a body's mass/energy/momentum bookkeeping.
    particle_dynamics = "particle_dynamics"
    # Needs a typed interaction, hence a free-body model and its unknowns.
    free_body = "free_body"
    # Needs a rigid body's own points and a frame with declared axes.
    rigid_body = "rigid_body"


_RIGID_CATEGORIES: frozenset[str] = frozenset({"rigid_body_kinematics"})
_KINEMATIC_CATEGORIES: frozenset[str] = frozenset({"kinematics", "constraint"})


def topology_tier(rule: LawRule) -> LawTopologyTier:
    """Return the closed topology tier a rule's own declaration implies."""

    if rule.required_interactions:
        return LawTopologyTier.free_body
    if rule.category in _RIGID_CATEGORIES:
        return LawTopologyTier.rigid_body
    if rule.category in _KINEMATIC_CATEGORIES:
        return LawTopologyTier.particle_kinematics
    return LawTopologyTier.particle_dynamics


@dataclass(frozen=True, slots=True)
class LawPrerequisite:
    """One law's declared prerequisites and its measured reachability."""

    law_id: str
    category: str
    tier: LawTopologyTier
    required_roles: tuple[str, ...]
    required_interactions: tuple[str, ...]
    required_assumption_kinds: tuple[str, ...]
    # Contexts in which every declared prerequisite is present.
    declared_satisfied: int
    # Of those, the contexts in which the law actually emitted an equation.
    emitted: int

    @property
    def structural_gap(self) -> int:
        """Contexts whose declared prerequisites are met but which emit nothing.

        A positive number means the emission function requires typed structure
        the declaration does not name.
        """

        return self.declared_satisfied - self.emitted

    def as_dict(self) -> dict[str, Any]:
        return {
            "law_id": self.law_id,
            "category": self.category,
            "tier": self.tier.value,
            "required_roles": list(self.required_roles),
            "required_interactions": list(self.required_interactions),
            "required_assumption_kinds": list(self.required_assumption_kinds),
            "declared_satisfied": self.declared_satisfied,
            "emitted": self.emitted,
            "structural_gap": self.structural_gap,
        }


@dataclass(frozen=True, slots=True)
class LawPrerequisiteMatrix:
    """Aggregate reachability of the whole catalogue over real contexts."""

    version: str
    context_count: int
    tier_counts: tuple[tuple[str, int], ...]
    laws: tuple[LawPrerequisite, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "context_count": self.context_count,
            "tier_counts": dict(self.tier_counts),
            "laws": [item.as_dict() for item in self.laws],
        }

    def by_tier(self, tier: LawTopologyTier) -> tuple[LawPrerequisite, ...]:
        return tuple(item for item in self.laws if item.tier is tier)

    def reachable(self) -> tuple[LawPrerequisite, ...]:
        """Laws that emitted at least once."""

        return tuple(item for item in self.laws if item.emitted)

    def blocked(self) -> tuple[LawPrerequisite, ...]:
        """Laws whose declared prerequisites are met but which never emit.

        Ordered by how many contexts they would unlock, so the largest unmet
        structural prerequisite is first.
        """

        return tuple(
            sorted(
                (item for item in self.laws if item.structural_gap > 0),
                key=lambda item: (-item.structural_gap, item.law_id),
            )
        )


def _declared_satisfied(context: LawContext, rule: LawRule) -> bool:
    """True when every prerequisite the rule itself declares is present."""

    roles = {quantity.role for quantity in context.quantities}
    if any(role not in roles for role in rule.required_roles):
        return False
    if rule.required_interactions:
        kinds = {interaction.kind.value for interaction in context.interactions}
        if any(kind not in kinds for kind in rule.required_interactions):
            return False
    if rule.approved_assumption_kinds:
        approved = {
            assumption.kind
            for assumption in context.assumptions
            if assumption.disposition is AssumptionDisposition.approved
            and assumption.assumption_id in context.approved_assumption_ids
        }
        if any(kind not in approved for kind in rule.approved_assumption_kinds):
            return False
    return True


def build_law_prerequisite_matrix(
    contexts: Iterable[LawContext],
) -> LawPrerequisiteMatrix:
    """Measure catalogue reachability over real law contexts.

    Each context is evaluated once against the real ``apply_core_laws``, so the
    emission column is the engine's own answer rather than a restatement of it.
    """

    catalog = core_law_catalog()
    declared: Counter[str] = Counter()
    emitted: Counter[str] = Counter()
    total = 0
    for context in contexts:
        total += 1
        for rule in catalog:
            if _declared_satisfied(context, rule):
                declared[rule.law_id] += 1
        for law_id in {item.rule.law_id for item in apply_core_laws(context)}:
            emitted[law_id] += 1

    laws = tuple(
        LawPrerequisite(
            law_id=rule.law_id,
            category=rule.category,
            tier=topology_tier(rule),
            required_roles=tuple(role.value for role in rule.required_roles),
            required_interactions=tuple(rule.required_interactions),
            required_assumption_kinds=tuple(rule.approved_assumption_kinds),
            declared_satisfied=declared[rule.law_id],
            # A law can only emit where its declared prerequisites hold, so the
            # gap below is never negative even though the two are counted
            # independently.
            emitted=min(emitted[rule.law_id], declared[rule.law_id]),
        )
        for rule in catalog
    )
    tier_counts = Counter(item.tier.value for item in laws)
    return LawPrerequisiteMatrix(
        version=LAW_PREREQUISITE_MATRIX_VERSION,
        context_count=total,
        tier_counts=tuple(sorted(tier_counts.items())),
        laws=laws,
    )


def law_context_for_projection(projection: object) -> LawContext | None:
    """Build the real law context one projected Draft reaches, or ``None``.

    The context is the compiler's own, assembled through the compiler's own
    steps, so the matrix measures what the runtime measures rather than a
    parallel reimplementation of it.  A case that never reaches the law stage —
    a figure dependency, a rejected projection, an unauthorised IR — yields
    ``None`` and simply does not appear in the counts.
    """

    from engine.mechanics.compiler import MechanicsCompiler
    from engine.mechanics.compiler import compiler as compiler_module
    from engine.mechanics.normalization import normalize_draft

    if not getattr(projection, "projected", False):
        return None
    normalization = normalize_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    ir = normalization.ir
    if not normalization.accepted or ir is None or not ir.queries:
        return None
    query = ir.queries[0]
    try:
        query_quantity, _ = compiler_module._query_quantity(ir, query)
        source_symbols, _ = compiler_module._validate_reciprocal_bindings(ir)
        records = compiler_module._primary_records(ir, query)
        _, edges = compiler_module._graph_edges(records)
        relevant, _ = compiler_module._relevant_ids(
            query, edges, MechanicsCompiler()._limits
        )
        context, _, _, _ = compiler_module._build_law_context(
            ir,
            query,
            query_quantity,
            relevant,
            source_symbols,
            frozenset(projection.approvable_assumption_ids),
        )
    except Exception:
        return None
    return context


__all__ = [
    "LAW_PREREQUISITE_MATRIX_VERSION",
    "LawPrerequisite",
    "LawPrerequisiteMatrix",
    "LawTopologyTier",
    "build_law_prerequisite_matrix",
    "law_context_for_projection",
    "topology_tier",
]
