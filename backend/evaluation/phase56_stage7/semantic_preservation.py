"""What survives the trip from the source contract to a law's prerequisite.

The standing claim was "the projection drops nothing", and it was measured by
counting relations, explicit facts and assumptions on both sides.  Equal counts
are not preservation.  Every one of the meanings this evaluator has had to
revoke survived that count and lost the thing that mattered: a launch angle
kept its number and lost what it was measured from, an initial velocity kept
its value and widened from an instant to an interval, a generic surface kept
its primitive and acquired an orientation nobody stated.  A count cannot see
any of that, because the record is still there.

So this module traces meaning instead of cardinality, along the whole path:

    public source contract
      -> projected MechanicsProblemDraftV1
      -> normalized MechanicsProblemIRV1
      -> the prerequisite a profile reads
      -> the prerequisite a law reads

Two questions are asked separately, because they have different answers and
very different remedies.

*Per source field*: did this field's meaning arrive, and in what condition?
`PreservationStatus` separates arriving unchanged from arriving rescaled, from
arriving with its scope altered, from arriving because a policy derived it, from
not arriving at all.  `ConsumptionStatus` then asks the second half — a field
that arrives intact and that no law ever reads is not preserved in any useful
sense, and saying so is the point.

*Per engine carrier*: is there any source field that could have stated this at
all?  `OMITTED_BECAUSE_V1_HAS_NO_CARRIER` is the answer for a meaning the
corpus contract has no place to put, and it is a fact about the contract rather
than about the evaluator.  A closure that wants such a meaning has to invent it,
which is exactly the failure mode the revoked packages share.

Reports are counts over closed vocabularies.  No record here has a field that
could hold a case identifier, a family, problem text, an evidence quote, an
expected answer, or a tolerance.

Nothing here participates in a runtime decision.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from enum import Enum
from typing import Annotated, Any, Callable, Iterable, Mapping, Sequence

from pydantic import Field, StringConstraints

from evaluation.phase56_stage7.contracts import FrozenStrictModel


SEMANTIC_PRESERVATION_VERSION = "phase56-stage7-semantic-preservation-v1"

_Token = Annotated[str, StringConstraints(min_length=1, max_length=120)]


class PreservationStatus(str, Enum):
    """What happened to one source field's meaning on the way down."""

    preserved_exact = "PRESERVED_EXACT"
    preserved_normalized = "PRESERVED_NORMALIZED"
    preserved_with_scope_change = "PRESERVED_WITH_SCOPE_CHANGE"
    derived_by_approved_policy = "DERIVED_BY_APPROVED_POLICY"
    omitted_because_v1_has_no_carrier = "OMITTED_BECAUSE_V1_HAS_NO_CARRIER"
    ambiguous_after_projection = "AMBIGUOUS_AFTER_PROJECTION"
    dropped_unsafely = "DROPPED_UNSAFELY"


class ConsumptionStatus(str, Enum):
    """Whether anything downstream actually reads it.

    A field can survive projection perfectly and still be dead: nothing in the
    catalogue asks for it.  That is a different gap from losing it, and mixing
    the two is how "the projection drops nothing" came to sound like an answer.
    """

    not_consumed = "NOT_CONSUMED"
    consumed_by_law = "CONSUMED_BY_LAW"
    consumed_by_terminal_detector = "CONSUMED_BY_TERMINAL_DETECTOR"


class SourceFieldCategory(str, Enum):
    """Every physics-relevant field the public v1 source contract states.

    Taken from the contract itself, not from a sample: these are the field
    names the corpus's own records carry.  `evidence_quote`, `label`,
    `relevance` and the answer block are deliberately absent — the first three
    are not physics and the fourth may not be read.
    """

    entity_kind = "entity.kind"
    entity_role = "entity.role"
    segment_actor_roles = "motion_segment.actor_roles"
    segment_motion_model = "motion_segment.motion_model"
    segment_order = "motion_segment.order"
    segment_start_event = "motion_segment.start_event_role"
    segment_end_event = "motion_segment.end_event_role"
    event_kind = "event.kind"
    event_subject_roles = "event.subject_roles"
    event_segment_role = "event.segment_role"
    fact_role = "explicit_fact.role"
    fact_semantic_key = "explicit_fact.semantic_key"
    fact_subject_role = "explicit_fact.subject_role"
    fact_segment_role = "explicit_fact.segment_role"
    fact_event_role = "explicit_fact.event_role"
    fact_temporal_role = "explicit_fact.temporal_role"
    fact_direction = "explicit_fact.direction"
    fact_raw_value = "explicit_fact.raw_value"
    fact_raw_unit = "explicit_fact.raw_unit"
    fact_occurrence_index = "explicit_fact.occurrence_index"
    relation_kind = "relation.kind"
    relation_participants = "relation.participant_roles"
    relation_segment_role = "relation.segment_role"
    assumption_kind = "assumption_proposal.kind"
    assumption_subject = "assumption_proposal.subject_role"
    assumption_segment = "assumption_proposal.segment_role"
    assumption_server_value = "assumption_proposal.server_value_only"
    query_output_key = "query.output_key"
    query_subject_role = "query.subject_role"
    query_segment_role = "query.segment_role"
    query_event_role = "query.event_role"
    query_component = "query.component"


class EngineCarrier(str, Enum):
    """Meanings the engine's own contract can hold and a law can read.

    The question this vocabulary answers is not "did the projection carry it"
    but "could the source have said it at all".
    """

    reference_frame = "reference_frame"
    frame_axis_direction = "frame_axis_direction"
    angle_reference_datum = "angle_reference_datum"
    motion_sense = "motion_sense"
    contact_side = "contact_side"
    endpoint_condition = "endpoint_condition"
    constraint_record = "constraint_record"
    interaction_participant = "interaction_participant"
    query_objective = "query_objective"
    quantity_frame_binding = "quantity_frame_binding"
    quantity_point_binding = "quantity_point_binding"
    state_condition = "state_condition"


# The source fields that can supply each engine carrier.  An empty tuple is the
# finding, not an omission in this table: it says the v1 corpus contract has no
# field whose meaning is that carrier, so nothing the projection does can
# produce one without inventing it.
CARRIER_SOURCE_FIELDS: dict[EngineCarrier, tuple[SourceFieldCategory, ...]] = {
    EngineCarrier.reference_frame: (),
    EngineCarrier.frame_axis_direction: (),
    EngineCarrier.angle_reference_datum: (),
    EngineCarrier.motion_sense: (),
    EngineCarrier.contact_side: (),
    # Partial, and the partiality is the finding: the event-kind vocabulary
    # states `comes_to_rest`, `highest_point` and `reaches_position`, so those
    # endpoints are sayable — while a spring at natural length, a specified
    # displacement, or a contact loss have no member and cannot be stated.
    EngineCarrier.endpoint_condition: (SourceFieldCategory.event_kind,),
    EngineCarrier.query_objective: (),
    EngineCarrier.quantity_frame_binding: (),
    # These four do have source fields, and are listed so the table is a
    # measurement rather than a list of complaints.
    EngineCarrier.constraint_record: (SourceFieldCategory.assumption_kind,),
    EngineCarrier.interaction_participant: (
        SourceFieldCategory.relation_participants,
    ),
    EngineCarrier.quantity_point_binding: (SourceFieldCategory.fact_subject_role,),
    EngineCarrier.state_condition: (
        SourceFieldCategory.assumption_kind,
        SourceFieldCategory.event_kind,
    ),
}


class PipelineStage(str, Enum):
    """Where a meaning was last seen, and therefore where it was lost."""

    source_contract = "source_contract"
    draft_projection = "draft_projection"
    ir_normalization = "ir_normalization"
    profile_prerequisite = "profile_prerequisite"
    law_prerequisite = "law_prerequisite"


class FieldPreservationV1(FrozenStrictModel):
    """One source field category, traced.  Counts only."""

    category: SourceFieldCategory
    status: PreservationStatus
    consumption: ConsumptionStatus
    occurrences: int = 0
    carried_to_draft: int = 0
    carried_to_ir: int = 0
    consumed: int = 0
    blocked: int = 0
    # How many contexts actually lost something here.  The status is merged by
    # severity, so one context in ninety-seven turns a category red; without
    # this count a reader cannot tell that case from a systematic loss.
    contexts_with_loss: int = 0
    first_failing_stage: PipelineStage | None = None


class CarrierOmissionV1(FrozenStrictModel):
    """One engine carrier, and whether the source contract can state it."""

    carrier: EngineCarrier
    source_fields: tuple[SourceFieldCategory, ...] = ()
    status: PreservationStatus
    contexts_requiring: int = 0
    contexts_supplying: int = 0

    @property
    def has_source_carrier(self) -> bool:
        return bool(self.source_fields)


class SemanticPreservationReportV1(FrozenStrictModel):
    """The whole audit, as counts over closed vocabularies."""

    version: str = SEMANTIC_PRESERVATION_VERSION
    context_count: int = 0
    fields: tuple[FieldPreservationV1, ...] = Field(default=(), max_length=128)
    carriers: tuple[CarrierOmissionV1, ...] = Field(default=(), max_length=64)
    status_counts: tuple[tuple[str, int], ...] = ()
    consumption_counts: tuple[tuple[str, int], ...] = ()
    first_failing_stage_counts: tuple[tuple[str, int], ...] = ()
    source_contract_omission_count: int = 0
    projection_loss_count: int = 0
    normalization_loss_count: int = 0
    law_consumption_gap_count: int = 0

    @property
    def digest(self) -> str:
        material = repr(self.model_dump(mode="json")).encode("utf-8")
        return hashlib.sha256(material).hexdigest()


# ---------------------------------------------------------------------------
# Extractors.  Each pair says where one meaning lives on each side.
# ---------------------------------------------------------------------------


def _values(items: Iterable[Any], attribute: str) -> list[str]:
    out: list[str] = []
    for item in items:
        value = getattr(item, attribute, None)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            out.extend(str(part) for part in value)
        else:
            out.append(str(getattr(value, "value", value)))
    return out


def _draft_values(payload: Mapping[str, Any], key: str, attribute: str) -> list[str]:
    out: list[str] = []
    for item in payload.get(key) or []:
        value = item.get(attribute)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            out.extend(str(part) for part in value)
        elif isinstance(value, Mapping):
            out.append("present")
        else:
            out.append(str(value))
    return out


def _query_target_values(payload: Mapping[str, Any], attribute: str) -> list[str]:
    out: list[str] = []
    for query in payload.get("queries") or []:
        value = query.get("target", {}).get(attribute)
        if value is not None:
            out.append(str(value))
    return out


# A direction the source explicitly declines to state is not a direction.  It is
# counted as absent on both sides so the trace does not report a loss where the
# source stated nothing to lose.
_ABSENT_DIRECTION_NAMES = frozenset({"not_applicable", "unspecified", "none"})


def _source_directions(gold: Any) -> list[str]:
    return [
        str(fact.direction)
        for fact in gold.explicit_facts
        if fact.direction is not None
        and str(fact.direction) not in _ABSENT_DIRECTION_NAMES
    ]


def _draft_directions(payload: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for quantity in payload.get("quantities") or []:
        binding = quantity.get("direction")
        if not binding:
            continue
        # `DirectionBinding` names the semantic direction in its own `direction`
        # field, beside the `kind` that says how it is expressed.  Reading a
        # `name` field here — which the contract does not have — reported all
        # 105 stated directions as dropped, which is exactly the false alarm
        # this audit exists to avoid producing.
        name = (
            binding.get("direction")
            if isinstance(binding, Mapping)
            else getattr(binding, "direction", None)
        )
        if name is None or str(name) in _ABSENT_DIRECTION_NAMES:
            continue
        out.append(str(getattr(name, "value", name)))
    return out


_SourceExtractor = Callable[[Any], list[str]]
_DraftExtractor = Callable[[Mapping[str, Any]], list[str]]


class CarrierShape(str, Enum):
    """How the Draft holds one source meaning, if it holds it at all.

    Without this distinction the classifier cannot tell "the Draft lost it"
    from "the Draft never had a field for it because another record carries the
    meaning".  Both look like a zero count, and calling the second one a drop
    is a false alarm — the audit reported one on `motion_segment.motion_model`
    before this existed.
    """

    # The Draft has its own record for it; counts on both sides are comparable.
    carried = "carried"
    # The meaning is read through a different record — a temporal role becomes
    # an interval or event binding, a motion model selects a profile — so a zero
    # count on its own field is correct rather than a loss.
    absorbed = "absorbed"
    # Nothing downstream holds or reads it.
    unheld = "unheld"


class _FieldSpec:
    """Where one meaning lives on the source side and on the Draft side."""

    __slots__ = (
        "category",
        "source",
        "draft",
        "scope_may_change",
        "consumption",
        "shape",
    )

    def __init__(
        self,
        category: SourceFieldCategory,
        source: _SourceExtractor,
        draft: _DraftExtractor,
        *,
        consumption: ConsumptionStatus,
        scope_may_change: bool = False,
        shape: CarrierShape = CarrierShape.carried,
    ) -> None:
        self.category = category
        self.source = source
        self.draft = draft
        self.consumption = consumption
        self.scope_may_change = scope_may_change
        self.shape = shape


def _field_specs() -> tuple[_FieldSpec, ...]:
    law = ConsumptionStatus.consumed_by_law
    detector = ConsumptionStatus.consumed_by_terminal_detector
    unused = ConsumptionStatus.not_consumed
    return (
        _FieldSpec(
            SourceFieldCategory.entity_kind,
            lambda gold: _values(gold.entities, "kind"),
            lambda payload: _draft_values(payload, "entities", "primitive"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.entity_role,
            lambda gold: _values(gold.entities, "role"),
            lambda payload: _draft_values(payload, "entities", "entity_id"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.segment_motion_model,
            lambda gold: _values(gold.motion_segments, "motion_model"),
            # The Draft has no motion-model field: the model selects a profile
            # rather than being carried as a record.
            lambda payload: [],
            consumption=law,
            shape=CarrierShape.absorbed,
        ),
        _FieldSpec(
            SourceFieldCategory.segment_order,
            lambda gold: _values(gold.motion_segments, "order"),
            lambda payload: _draft_values(payload, "motion_intervals", "order"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.segment_actor_roles,
            lambda gold: _values(gold.motion_segments, "actor_roles"),
            lambda payload: _draft_values(payload, "motion_intervals", "subject_ids"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.segment_start_event,
            lambda gold: _values(gold.motion_segments, "start_event_role"),
            lambda payload: _draft_values(
                payload, "motion_intervals", "start_event_id"
            ),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.segment_end_event,
            lambda gold: _values(gold.motion_segments, "end_event_role"),
            lambda payload: _draft_values(payload, "motion_intervals", "end_event_id"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.event_kind,
            lambda gold: _values(gold.events, "kind"),
            lambda payload: _draft_values(payload, "events", "kind"),
            consumption=detector,
            scope_may_change=True,
        ),
        _FieldSpec(
            SourceFieldCategory.event_subject_roles,
            lambda gold: _values(gold.events, "subject_roles"),
            lambda payload: _draft_values(payload, "events", "subject_ids"),
            consumption=detector,
        ),
        _FieldSpec(
            SourceFieldCategory.event_segment_role,
            lambda gold: _values(gold.events, "segment_role"),
            lambda payload: _draft_values(payload, "events", "occurs_in_interval_ids"),
            consumption=detector,
            scope_may_change=True,
            # An event's segment is carried by the interval's own
            # `start_event_id`/`end_event_id` — both traced above and both
            # 100/100 — not by `occurs_in_interval_ids`.  Reading only the
            # latter reported 104 of 132 bindings as dropped when every one of
            # them is present on the other side of the same edge.
            shape=CarrierShape.absorbed,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_role,
            lambda gold: _values(gold.explicit_facts, "role"),
            lambda payload: _draft_values(payload, "quantities", "quantity_id"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_semantic_key,
            lambda gold: _values(gold.explicit_facts, "semantic_key"),
            lambda payload: _draft_values(payload, "quantities", "role"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_subject_role,
            lambda gold: _values(gold.explicit_facts, "subject_role"),
            lambda payload: _draft_values(payload, "quantities", "subject_id"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_segment_role,
            lambda gold: [
                value
                for value in _values(gold.explicit_facts, "segment_role")
                if value
            ],
            lambda payload: _draft_values(payload, "quantities", "interval_id"),
            consumption=law,
            scope_may_change=True,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_event_role,
            lambda gold: [
                value for value in _values(gold.explicit_facts, "event_role") if value
            ],
            lambda payload: _draft_values(payload, "quantities", "event_id"),
            consumption=law,
            scope_may_change=True,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_temporal_role,
            lambda gold: _values(gold.explicit_facts, "temporal_role"),
            # Absorbed into the interval/event binding rather than carried; the
            # two scope fields above are where it is actually traced.
            lambda payload: [],
            consumption=law,
            scope_may_change=True,
            shape=CarrierShape.absorbed,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_direction,
            _source_directions,
            _draft_directions,
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_raw_value,
            lambda gold: [
                str(fact.raw_value)
                for fact in gold.explicit_facts
                if fact.raw_value is not None
            ],
            lambda payload: [
                str(quantity["raw_value"])
                for quantity in payload.get("quantities") or []
                if quantity.get("raw_value") is not None
            ],
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_raw_unit,
            lambda gold: [
                str(fact.raw_unit)
                for fact in gold.explicit_facts
                if fact.raw_unit is not None
            ],
            lambda payload: [
                str(quantity["raw_unit"])
                for quantity in payload.get("quantities") or []
                if quantity.get("raw_unit") is not None
            ],
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.fact_occurrence_index,
            lambda gold: [
                str(fact.occurrence_index)
                for fact in gold.explicit_facts
                if fact.occurrence_index is not None
            ],
            lambda payload: [],
            consumption=unused,
            shape=CarrierShape.unheld,
        ),
        _FieldSpec(
            SourceFieldCategory.relation_kind,
            lambda gold: _values(gold.relations, "kind"),
            lambda payload: _draft_values(payload, "geometry", "kind")
            + _draft_values(payload, "interactions", "kind"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.relation_participants,
            lambda gold: _values(gold.relations, "participant_roles"),
            lambda payload: _draft_values(payload, "geometry", "participant_ids")
            + _draft_values(payload, "interactions", "participant_ids"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.relation_segment_role,
            lambda gold: [
                value for value in _values(gold.relations, "segment_role") if value
            ],
            lambda payload: _draft_values(payload, "geometry", "interval_id")
            + _draft_values(payload, "interactions", "interval_id"),
            consumption=law,
            scope_may_change=True,
        ),
        _FieldSpec(
            SourceFieldCategory.assumption_kind,
            lambda gold: _values(gold.assumption_proposals, "kind"),
            lambda payload: _draft_values(payload, "assumptions", "kind"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.assumption_subject,
            lambda gold: _values(gold.assumption_proposals, "subject_role"),
            lambda payload: _draft_values(payload, "assumptions", "subject_id"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.assumption_segment,
            lambda gold: [
                value
                for value in _values(gold.assumption_proposals, "segment_role")
                if value
            ],
            lambda payload: _draft_values(payload, "assumptions", "interval_id"),
            consumption=law,
            scope_may_change=True,
        ),
        _FieldSpec(
            SourceFieldCategory.assumption_server_value,
            lambda gold: [
                str(item.server_value_only)
                for item in gold.assumption_proposals
                if item.server_value_only
            ],
            lambda payload: _draft_values(payload, "assumptions", "disposition"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.query_output_key,
            lambda gold: _values(gold.queries, "output_key"),
            lambda payload: _query_target_values(payload, "role"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.query_subject_role,
            lambda gold: _values(gold.queries, "subject_role"),
            lambda payload: _query_target_values(payload, "subject_id"),
            consumption=law,
        ),
        _FieldSpec(
            SourceFieldCategory.query_segment_role,
            lambda gold: [
                value for value in _values(gold.queries, "segment_role") if value
            ],
            lambda payload: _query_target_values(payload, "interval_id"),
            consumption=law,
            scope_may_change=True,
        ),
        _FieldSpec(
            SourceFieldCategory.query_event_role,
            lambda gold: [
                value for value in _values(gold.queries, "event_role") if value
            ],
            lambda payload: _query_target_values(payload, "event_id"),
            consumption=law,
            scope_may_change=True,
        ),
        _FieldSpec(
            SourceFieldCategory.query_component,
            lambda gold: _values(gold.queries, "component"),
            lambda payload: _query_target_values(payload, "component"),
            consumption=law,
        ),
    )


FIELD_SPECS = _field_specs()


def _classify(
    *,
    source_count: int,
    draft_count: int,
    ir_count: int,
    consumption: ConsumptionStatus,
    scope_may_change: bool,
    shape: CarrierShape,
) -> tuple[PreservationStatus, PipelineStage | None]:
    """One field's status from its counts along the pipeline."""

    if shape is CarrierShape.unheld:
        # Nothing holds it and nothing reads it.  A property of the contract,
        # not a projection defect, however many occurrences the source states.
        return (
            PreservationStatus.omitted_because_v1_has_no_carrier,
            PipelineStage.source_contract,
        )
    if shape is CarrierShape.absorbed:
        # The meaning is read through another record, so its own count is
        # expected to be zero and a zero here is not a loss.
        return PreservationStatus.preserved_with_scope_change, None
    if source_count == 0:
        # Nothing was stated, so nothing could be lost.  This is the honest
        # reading of a field the corpus simply does not use.
        if draft_count:
            return PreservationStatus.derived_by_approved_policy, None
        return PreservationStatus.preserved_exact, None
    if draft_count == 0:
        return (
            PreservationStatus.preserved_with_scope_change
            if scope_may_change
            else PreservationStatus.dropped_unsafely,
            PipelineStage.draft_projection,
        )
    if draft_count < source_count:
        return PreservationStatus.dropped_unsafely, PipelineStage.draft_projection
    if ir_count and ir_count < draft_count:
        return PreservationStatus.dropped_unsafely, PipelineStage.ir_normalization
    if draft_count > source_count:
        return PreservationStatus.derived_by_approved_policy, None
    if scope_may_change:
        return PreservationStatus.preserved_with_scope_change, None
    return PreservationStatus.preserved_normalized, None


def trace_context(
    gold: Any, draft: Any, ir: Any = None
) -> tuple[FieldPreservationV1, ...]:
    """Trace every source field of one context down the pipeline.

    A context whose projection was *rejected* carries no Draft, and tracing it
    would report every field as dropped.  That is a refusal, not a loss — the
    engine declined to model the problem — so the caller must not pass one.
    `trace_context(gold, None)` raises rather than quietly contributing a
    hundred false drops to the aggregate.
    """

    if draft is None:
        raise ValueError(
            "a rejected projection has no Draft to trace; count it separately"
        )
    payload: Mapping[str, Any] = (
        draft
        if isinstance(draft, Mapping)
        else draft.model_dump(mode="json", warnings="none")
    )
    ir_payload: Mapping[str, Any] = (
        {}
        if ir is None
        else ir
        if isinstance(ir, Mapping)
        else ir.model_dump(mode="json", warnings="none")
    )
    traced: list[FieldPreservationV1] = []
    for spec in FIELD_SPECS:
        source_values = spec.source(gold)
        draft_values = spec.draft(payload)
        ir_values = spec.draft(ir_payload) if ir_payload else []
        status, stage = _classify(
            source_count=len(source_values),
            draft_count=len(draft_values),
            ir_count=len(ir_values),
            consumption=spec.consumption,
            scope_may_change=spec.scope_may_change,
            shape=spec.shape,
        )
        traced.append(
            FieldPreservationV1(
                category=spec.category,
                status=status,
                consumption=spec.consumption,
                occurrences=len(source_values),
                carried_to_draft=len(draft_values),
                carried_to_ir=len(ir_values),
                consumed=(
                    len(draft_values)
                    if spec.consumption is not ConsumptionStatus.not_consumed
                    else 0
                ),
                blocked=max(0, len(source_values) - len(draft_values)),
                contexts_with_loss=(
                    1
                    if spec.shape is CarrierShape.carried
                    and len(draft_values) < len(source_values)
                    else 0
                ),
                first_failing_stage=stage,
            )
        )
    return tuple(traced)


def build_carrier_omissions(
    *,
    requiring: Mapping[EngineCarrier, int] | None = None,
    supplying: Mapping[EngineCarrier, int] | None = None,
) -> tuple[CarrierOmissionV1, ...]:
    """Per engine carrier, whether the source contract can state it at all."""

    requiring = requiring or {}
    supplying = supplying or {}
    omissions: list[CarrierOmissionV1] = []
    for carrier in EngineCarrier:
        fields = CARRIER_SOURCE_FIELDS.get(carrier, ())
        omissions.append(
            CarrierOmissionV1(
                carrier=carrier,
                source_fields=fields,
                status=(
                    PreservationStatus.preserved_normalized
                    if fields
                    else PreservationStatus.omitted_because_v1_has_no_carrier
                ),
                contexts_requiring=int(requiring.get(carrier, 0)),
                contexts_supplying=int(supplying.get(carrier, 0)),
            )
        )
    return tuple(omissions)


def build_semantic_preservation_report(
    traces: Iterable[Sequence[FieldPreservationV1]],
    *,
    carriers: Sequence[CarrierOmissionV1] | None = None,
) -> SemanticPreservationReportV1:
    """Aggregate per-context traces into the published report."""

    per_category: dict[SourceFieldCategory, FieldPreservationV1] = {}
    contexts = 0
    for trace in traces:
        contexts += 1
        for item in trace:
            existing = per_category.get(item.category)
            if existing is None:
                per_category[item.category] = item
                continue
            # Statuses are merged by severity: one context that dropped a field
            # unsafely is the finding, and averaging it away with ninety-nine
            # that did not would hide exactly the case worth reading.
            worse = max(
                (existing.status, item.status),
                key=lambda status: _STATUS_SEVERITY[status],
            )
            stage = existing.first_failing_stage or item.first_failing_stage
            per_category[item.category] = FieldPreservationV1(
                category=item.category,
                status=worse,
                consumption=item.consumption,
                occurrences=existing.occurrences + item.occurrences,
                carried_to_draft=existing.carried_to_draft + item.carried_to_draft,
                carried_to_ir=existing.carried_to_ir + item.carried_to_ir,
                consumed=existing.consumed + item.consumed,
                blocked=existing.blocked + item.blocked,
                contexts_with_loss=existing.contexts_with_loss
                + item.contexts_with_loss,
                first_failing_stage=stage,
            )

    fields = tuple(
        per_category[category]
        for category in SourceFieldCategory
        if category in per_category
    )
    statuses: Counter[str] = Counter(item.status.value for item in fields)
    consumptions: Counter[str] = Counter(item.consumption.value for item in fields)
    stages: Counter[str] = Counter(
        item.first_failing_stage.value
        for item in fields
        if item.first_failing_stage is not None
    )
    carrier_records = tuple(carriers or build_carrier_omissions())
    return SemanticPreservationReportV1(
        context_count=contexts,
        fields=fields,
        carriers=carrier_records,
        status_counts=tuple(sorted(statuses.items())),
        consumption_counts=tuple(sorted(consumptions.items())),
        first_failing_stage_counts=tuple(sorted(stages.items())),
        source_contract_omission_count=sum(
            1
            for carrier in carrier_records
            if carrier.status is PreservationStatus.omitted_because_v1_has_no_carrier
        ),
        projection_loss_count=sum(
            1
            for item in fields
            if item.first_failing_stage is PipelineStage.draft_projection
            and item.status is PreservationStatus.dropped_unsafely
        ),
        normalization_loss_count=sum(
            1
            for item in fields
            if item.first_failing_stage is PipelineStage.ir_normalization
        ),
        law_consumption_gap_count=sum(
            1
            for item in fields
            if item.consumption is ConsumptionStatus.not_consumed
            and item.occurrences > 0
        ),
    )


_STATUS_SEVERITY: dict[PreservationStatus, int] = {
    PreservationStatus.preserved_exact: 0,
    PreservationStatus.preserved_normalized: 1,
    PreservationStatus.preserved_with_scope_change: 2,
    PreservationStatus.derived_by_approved_policy: 3,
    PreservationStatus.omitted_because_v1_has_no_carrier: 4,
    PreservationStatus.ambiguous_after_projection: 5,
    PreservationStatus.dropped_unsafely: 6,
}


def report_as_dict(report: SemanticPreservationReportV1) -> dict[str, Any]:
    """The report as plain JSON for the out-of-repository artifact."""

    payload = report.model_dump(mode="json")
    payload["digest"] = report.digest
    return payload


__all__ = [
    "CARRIER_SOURCE_FIELDS",
    "FIELD_SPECS",
    "SEMANTIC_PRESERVATION_VERSION",
    "CarrierOmissionV1",
    "ConsumptionStatus",
    "EngineCarrier",
    "FieldPreservationV1",
    "PipelineStage",
    "PreservationStatus",
    "SemanticPreservationReportV1",
    "SourceFieldCategory",
    "build_carrier_omissions",
    "build_semantic_preservation_report",
    "report_as_dict",
    "trace_context",
]
