"""What every projected context is structurally missing, counted.

The complete-profile census answers "how close is profile P to closing?".  This
module answers the question underneath it: *which typed structure is absent
from the source at all*, across every context, regardless of which profile
might want it.

The distinction matters because the two have different remedies.  A profile
that is one derivable prerequisite short is a planner gap — write the closed
derivation and it closes.  A context whose queried unknown belongs to an entity
no free-body law will ever write an equation for is not a planner gap: no
transaction can fix it without changing what the source says the entity *is*,
and changing that is fabricating structure.

Every field below is a count over a closed vocabulary.  The records have no
field that could hold a case ID, a family, a split, a chapter, a difficulty, a
tag, an expected system type, an expected terminal, an expected answer, a gold
graph, a filename, or any problem text — so the aggregate can be published in
the redacted artifact without a redaction step having to remove anything.

Nothing here participates in a runtime decision.  It is a measurement, never a
gate and never an input to projection, normalization, compilation, or solving.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Sequence

from pydantic import Field

from engine.mechanics.contracts import EntityPrimitive
from engine.mechanics.laws.core import free_body_primitive_names

from evaluation.phase56_stage7.contracts import FrozenStrictModel

STRUCTURAL_BLOCKER_CENSUS_VERSION = (
    "phase56-stage7-structural-blocker-census-v1"
)


def _counts(counter: Counter[str]) -> tuple[tuple[str, int], ...]:
    """A counter as a sorted, JSON-stable pair sequence."""

    return tuple(sorted(counter.items()))


class StructuralBlockerCensusV1(FrozenStrictModel):
    """Counts of the typed structure the sources do not state.

    `contexts_without_reference_frame` is the one that explains the rest: every
    emitter that pairs quantities by component needs a named axis of a named
    frame, and a source that states no frame leaves every one of them blocked
    at the same place.
    """

    version: str = STRUCTURAL_BLOCKER_CENSUS_VERSION
    context_count: int = 0
    contexts_without_reference_frame: int = 0
    contexts_without_interaction: int = 0
    contexts_with_events: int = 0
    contexts_without_bounded_interval: int = 0
    # The queried unknown's owner, by entity primitive.  A primitive outside the
    # free-body set can never carry a Newton equation, whatever else is supplied.
    query_subject_primitive_counts: tuple[tuple[str, int], ...] = ()
    contexts_with_non_free_body_query_subject: int = 0
    query_component_counts: tuple[tuple[str, int], ...] = ()
    contexts_with_magnitude_query: int = 0
    free_body_primitives: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def blocked_on_query_subject(self) -> int:
        return self.contexts_with_non_free_body_query_subject


def _payload(draft: Any) -> dict[str, Any]:
    return draft.model_dump(mode="json", warnings="none")


def build_structural_blocker_census(
    drafts: Iterable[Any],
) -> StructuralBlockerCensusV1:
    """Count what every projected Draft is missing.  Counts only."""

    free_body: frozenset[str] = frozenset(free_body_primitive_names())
    subjects: Counter[str] = Counter()
    components: Counter[str] = Counter()
    contexts = 0
    without_frame = 0
    without_interaction = 0
    with_events = 0
    without_bounded_interval = 0
    non_free_body_subject = 0
    magnitude_query = 0

    for draft in drafts:
        payload = _payload(draft)
        queries: Sequence[dict[str, Any]] = payload.get("queries") or []
        if not queries:
            # A Draft with no question is not a context this census describes.
            continue
        contexts += 1
        if not payload.get("reference_frames"):
            without_frame += 1
        if not payload.get("interactions"):
            without_interaction += 1
        if payload.get("events"):
            with_events += 1
        if not any(
            interval.get("start_event_id") and interval.get("end_event_id")
            for interval in payload.get("motion_intervals") or []
        ):
            without_bounded_interval += 1

        primitive_by_entity = {
            item["entity_id"]: item["primitive"]
            for item in payload.get("entities") or []
        }
        target = queries[0]["target"]
        primitive = primitive_by_entity.get(target["subject_id"], "unresolved")
        subjects[primitive] += 1
        if primitive not in free_body:
            non_free_body_subject += 1

        component = target.get("component") or "unspecified"
        components[component] += 1
        if component == "magnitude":
            magnitude_query += 1

    return StructuralBlockerCensusV1(
        context_count=contexts,
        contexts_without_reference_frame=without_frame,
        contexts_without_interaction=without_interaction,
        contexts_with_events=with_events,
        contexts_without_bounded_interval=without_bounded_interval,
        query_subject_primitive_counts=_counts(subjects),
        contexts_with_non_free_body_query_subject=non_free_body_subject,
        query_component_counts=_counts(components),
        contexts_with_magnitude_query=magnitude_query,
        free_body_primitives=tuple(sorted(free_body)),
    )


def census_as_dict(census: StructuralBlockerCensusV1) -> dict[str, Any]:
    """The census as plain JSON for the redacted aggregate artifact."""

    return {
        "version": census.version,
        "context_count": census.context_count,
        "contexts_without_reference_frame": census.contexts_without_reference_frame,
        "contexts_without_interaction": census.contexts_without_interaction,
        "contexts_with_events": census.contexts_with_events,
        "contexts_without_bounded_interval": census.contexts_without_bounded_interval,
        "contexts_with_non_free_body_query_subject": (
            census.contexts_with_non_free_body_query_subject
        ),
        "contexts_with_magnitude_query": census.contexts_with_magnitude_query,
        "free_body_primitives": list(census.free_body_primitives),
        "query_subject_primitive_counts": [
            {"primitive": key, "count": value}
            for key, value in census.query_subject_primitive_counts
        ],
        "query_component_counts": [
            {"component": key, "count": value}
            for key, value in census.query_component_counts
        ],
    }


# The primitives the corpus may name as an entity but no free-body law will ever
# write an equation for.  Kept here as a derived constant so a change to the
# engine's free-body set shows up as a change in this census rather than as a
# silent drift.
def non_free_body_primitives() -> tuple[str, ...]:
    free_body = frozenset(free_body_primitive_names())
    return tuple(
        sorted(item.value for item in EntityPrimitive if item.value not in free_body)
    )


__all__ = [
    "STRUCTURAL_BLOCKER_CENSUS_VERSION",
    "StructuralBlockerCensusV1",
    "build_structural_blocker_census",
    "census_as_dict",
    "non_free_body_primitives",
]
