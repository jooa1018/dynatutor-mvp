"""Source-only manifest builder for the distinct Stage 7 yield campaign.

This is not a reconstruction of the unavailable historical augmentation
manifest.  It builds the separately named
``STAGE7_V2_SUPPLEMENTAL_YIELD_CAMPAIGN_V1`` population described by the
current Phase 56 candidate contract.

Discovery and identity binding are deliberately separate operations.  Cohort
selection receives :class:`SourceOnlyCaseV1`, a closed view that cannot hold a
case id, split, expected terminal, failure code, answer, tolerance, family, or
solver result.  Only after all three structural predicates have selected
exactly three records each does the builder return to the original records and
hash each complete record as an opaque manifest identity.  The hash is never
an input to selection.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from enum import Enum
from typing import Sequence

from evaluation.phase56_stage7.corpus_records import (
    CorpusAssumptionV1,
    CorpusEntityV1,
    CorpusEventV1,
    CorpusFactV1,
    CorpusFigureDependencyV1,
    CorpusQueryV1,
    CorpusRelationV1,
    CorpusSegmentV1,
    PublicCorpusCaseV1,
)
from evaluation.phase56_stage7.corpus_v2.migration import (
    AugmentationEntryV1,
    AugmentationManifestV1,
    ReviewStatus,
    assert_manifest_has_no_answer_authority,
    record_fingerprint,
)
from evaluation.phase56_stage7.corpus_v2.records import (
    AxisSense,
    ConstraintAuthority,
    ConstraintAuthorityV2,
    CorpusV2AugmentationV1,
    FrameAxisV2,
    FrameOriginKind,
    FrameType,
    QueryObjective,
    QueryObjectiveV2,
    ReferenceFrameV2,
    SourceQuoteEvidenceV2,
)


SUPPLEMENTAL_CAMPAIGN_ID = "STAGE7_V2_SUPPLEMENTAL_YIELD_CAMPAIGN_V1"
SUPPLEMENTAL_AUTHORING_PROVENANCE = (
    f"{SUPPLEMENTAL_CAMPAIGN_ID}:source-only-reviewed-v1"
)
EXPECTED_COHORT_SIZE = 3
EXPECTED_SELECTED_CONTEXTS = 9

_HORIZONTAL_QUOTE = "수평 원형도로"
_MAXIMUM_QUOTE = "미끄러지지 않는 최대 속력의 크기"
_INSTANT_CENTER_QUOTE = "순간중심 방법으로"


class SupplementalCohort(str, Enum):
    banked_frictionless_curve = "banked_frictionless_curve"
    flat_curve_maximum_speed = "flat_curve_maximum_speed"
    instant_center_two_point_speed = "instant_center_two_point_speed"


class SupplementalManifestReason(str, Enum):
    source_population_mismatch = "supplemental_source_population_mismatch"
    cohort_cardinality_mismatch = "supplemental_cohort_cardinality_mismatch"
    cohort_overlap = "supplemental_cohort_overlap"
    selected_population_mismatch = "supplemental_selected_population_mismatch"
    source_quote_missing_or_ambiguous = (
        "supplemental_source_quote_missing_or_ambiguous"
    )
    source_shape_changed = "supplemental_source_shape_changed"


class SupplementalManifestRefused(ValueError):
    """A closed, source-content-free refusal from manifest construction."""

    def __init__(self, reason: SupplementalManifestReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class SourceOnlyCaseV1:
    """The complete information cohort discovery is allowed to inspect."""

    problem_text: str
    figure_dependency: CorpusFigureDependencyV1
    entities: tuple[CorpusEntityV1, ...]
    motion_segments: tuple[CorpusSegmentV1, ...]
    events: tuple[CorpusEventV1, ...]
    explicit_facts: tuple[CorpusFactV1, ...]
    relations: tuple[CorpusRelationV1, ...]
    assumption_proposals: tuple[CorpusAssumptionV1, ...]
    queries: tuple[CorpusQueryV1, ...]


SOURCE_ONLY_FIELDS: tuple[str, ...] = tuple(
    item.name for item in fields(SourceOnlyCaseV1)
)


@dataclass(frozen=True, slots=True)
class SupplementalSelectionV1:
    """Opaque archive positions selected solely from source structure."""

    by_cohort: tuple[tuple[SupplementalCohort, tuple[int, ...]], ...]

    @property
    def selected_positions(self) -> tuple[int, ...]:
        return tuple(
            sorted(position for _, positions in self.by_cohort for position in positions)
        )

    def cohort_for_position(self, position: int) -> SupplementalCohort:
        matches = [
            cohort
            for cohort, positions in self.by_cohort
            if position in positions
        ]
        if len(matches) != 1:
            raise SupplementalManifestRefused(
                SupplementalManifestReason.cohort_overlap
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class SupplementalManifestBuildV1:
    manifest: AugmentationManifestV1
    selection: SupplementalSelectionV1
    selection_identity_digest: str


def source_only_case(case: PublicCorpusCaseV1) -> SourceOnlyCaseV1:
    """Copy only source-grounded fields out of the gold-domain container."""

    source = case.gold
    return SourceOnlyCaseV1(
        problem_text=case.problem_text,
        figure_dependency=source.figure_dependency,
        entities=source.entities,
        motion_segments=source.motion_segments,
        events=source.events,
        explicit_facts=source.explicit_facts,
        relations=source.relations,
        assumption_proposals=source.assumption_proposals,
        queries=source.queries,
    )


def _signature(case: SourceOnlyCaseV1) -> tuple[object, ...]:
    """Canonical typed signature; no text and no evaluation authority."""

    return (
        tuple(sorted(entity.kind for entity in case.entities)),
        tuple(sorted(relation.kind for relation in case.relations)),
        tuple(sorted(item.kind for item in case.assumption_proposals)),
        tuple(sorted(fact.semantic_key for fact in case.explicit_facts)),
        tuple(sorted((query.output_key, query.component) for query in case.queries)),
        tuple(sorted(segment.motion_model for segment in case.motion_segments)),
        tuple(sorted(event.kind for event in case.events)),
        (
            case.figure_dependency.level,
            tuple(sorted(case.figure_dependency.missing_information)),
        ),
    )


_BANKED_SIGNATURE = (
    ("surface", "vehicle"),
    ("contact_with",),
    ("constant_gravity", "frictionless"),
    ("angle", "radius"),
    (("final_velocity", "magnitude"),),
    ("unknown",),
    ("start",),
    ("none", ()),
)

_FLAT_SIGNATURE = (
    ("surface", "vehicle"),
    ("contact_with",),
    ("constant_gravity",),
    ("coefficient_of_friction", "radius"),
    (("final_velocity", "magnitude"),),
    ("unknown",),
    ("start",),
    ("none", ()),
)

_INSTANT_CENTER_SIGNATURE = (
    ("point", "point", "point", "rigid_body"),
    ("point_on_body", "point_on_body"),
    (),
    ("radius", "radius", "velocity"),
    (("tangential_velocity", "magnitude"),),
    ("general_plane_motion",),
    ("other",),
    ("none", ()),
)

_SIGNATURES: tuple[tuple[SupplementalCohort, tuple[object, ...]], ...] = (
    (SupplementalCohort.banked_frictionless_curve, _BANKED_SIGNATURE),
    (SupplementalCohort.flat_curve_maximum_speed, _FLAT_SIGNATURE),
    (SupplementalCohort.instant_center_two_point_speed, _INSTANT_CENTER_SIGNATURE),
)


def discover_supplemental_cohorts(
    cases: Sequence[SourceOnlyCaseV1],
) -> SupplementalSelectionV1:
    """Select the frozen three cohorts from typed source structure only."""

    selected: list[tuple[SupplementalCohort, tuple[int, ...]]] = []
    for cohort, expected_signature in _SIGNATURES:
        positions = tuple(
            position
            for position, case in enumerate(cases)
            if _signature(case) == expected_signature
        )
        if len(positions) != EXPECTED_COHORT_SIZE:
            raise SupplementalManifestRefused(
                SupplementalManifestReason.cohort_cardinality_mismatch
            )
        selected.append((cohort, positions))

    flat = [position for _, positions in selected for position in positions]
    if len(flat) != len(set(flat)):
        raise SupplementalManifestRefused(SupplementalManifestReason.cohort_overlap)
    if len(flat) != EXPECTED_SELECTED_CONTEXTS:
        raise SupplementalManifestRefused(
            SupplementalManifestReason.selected_population_mismatch
        )
    return SupplementalSelectionV1(by_cohort=tuple(selected))


def _unique_quote(problem_text: str, quote: str) -> str:
    if problem_text.count(quote) != 1:
        raise SupplementalManifestRefused(
            SupplementalManifestReason.source_quote_missing_or_ambiguous
        )
    return quote


def _one(items: Sequence[object]) -> object:
    if len(items) != 1:
        raise SupplementalManifestRefused(
            SupplementalManifestReason.source_shape_changed
        )
    return items[0]


def _axis(
    *,
    name: str,
    sense: AxisSense,
    bound_frame_id: str,
    bound_axis: str,
    evidence_id: str,
    anchor_entity_id: str | None = None,
) -> FrameAxisV2:
    return FrameAxisV2(
        axis=name,
        sense=sense,
        anchor_entity_id=anchor_entity_id,
        bound_frame_id=bound_frame_id,
        bound_axis=bound_axis,
        bound_sign=1,
        evidence_refs=(evidence_id,),
    )


def _flat_curve_augmentation(case: SourceOnlyCaseV1) -> CorpusV2AugmentationV1:
    horizontal_evidence = "v2_ev_horizontal_road"
    maximum_evidence = "v2_ev_maximum_speed"
    world_frame = "v2_frame_world"
    support_frame = "v2_frame_horizontal_support"

    vehicle = _one([item for item in case.entities if item.kind == "vehicle"])
    surface = _one([item for item in case.entities if item.kind == "surface"])
    query = _one(list(case.queries))

    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(
                evidence_id=horizontal_evidence,
                quote=_unique_quote(case.problem_text, _HORIZONTAL_QUOTE),
            ),
            SourceQuoteEvidenceV2(
                evidence_id=maximum_evidence,
                quote=_unique_quote(case.problem_text, _MAXIMUM_QUOTE),
            ),
        ),
        reference_frames=(
            ReferenceFrameV2(
                frame_id=world_frame,
                frame_type=FrameType.world_cartesian,
                origin_kind=FrameOriginKind.world,
                subject_id=vehicle.role,
                axes=(
                    _axis(
                        name="x",
                        sense=AxisSense.along_surface_forward,
                        bound_frame_id=world_frame,
                        bound_axis="x",
                        evidence_id=horizontal_evidence,
                    ),
                    _axis(
                        name="y",
                        sense=AxisSense.up_the_page,
                        bound_frame_id=world_frame,
                        bound_axis="y",
                        evidence_id=horizontal_evidence,
                    ),
                ),
                evidence_refs=(horizontal_evidence,),
            ),
            ReferenceFrameV2(
                frame_id=support_frame,
                frame_type=FrameType.surface_tangent_normal,
                origin_kind=FrameOriginKind.entity,
                subject_id=surface.role,
                axes=(
                    _axis(
                        name="tangent",
                        sense=AxisSense.along_surface_forward,
                        anchor_entity_id=surface.role,
                        bound_frame_id=world_frame,
                        bound_axis="x",
                        evidence_id=horizontal_evidence,
                    ),
                    _axis(
                        name="normal",
                        sense=AxisSense.away_from_surface,
                        anchor_entity_id=surface.role,
                        bound_frame_id=world_frame,
                        bound_axis="y",
                        evidence_id=horizontal_evidence,
                    ),
                ),
                evidence_refs=(horizontal_evidence,),
            ),
        ),
        query_objectives=(
            QueryObjectiveV2(
                objective_id="v2_objective_maximum_speed",
                # The v1 Draft projection namespaces source query roles in the
                # same deterministic way it namespaces fact quantities.
                query_id=f"qry_{query.role}",
                objective=QueryObjective.maximum,
                evidence_refs=(maximum_evidence,),
            ),
        ),
    )


def _instant_center_augmentation(
    case: SourceOnlyCaseV1,
) -> CorpusV2AugmentationV1:
    evidence_id = "v2_ev_instant_center_method"
    body = _one([item for item in case.entities if item.kind == "rigid_body"])
    points = {item.role for item in case.entities if item.kind == "point"}
    attached_points = {
        participant
        for relation in case.relations
        for participant in relation.participant_roles
        if participant in points
    }
    centre_id = _one(sorted(points - attached_points))
    segment = _one(list(case.motion_segments))
    event = _one(list(case.events))

    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(
                evidence_id=evidence_id,
                quote=_unique_quote(case.problem_text, _INSTANT_CENTER_QUOTE),
            ),
        ),
        constraint_authorities=(
            ConstraintAuthorityV2(
                constraint_id="v2_constraint_instantaneous_center",
                authority=ConstraintAuthority.instantaneous_center,
                participant_ids=(body.role, centre_id),
                subject_id=body.role,
                event_id=event.role,
                evidence_refs=(evidence_id,),
            ),
        ),
    )


def _augmentation_for(
    cohort: SupplementalCohort, case: SourceOnlyCaseV1
) -> CorpusV2AugmentationV1:
    if cohort is SupplementalCohort.banked_frictionless_curve:
        # V1 already carries every source statement this cohort needs.  The
        # reviewed empty entry marks membership without inventing a carrier.
        return CorpusV2AugmentationV1()
    if cohort is SupplementalCohort.flat_curve_maximum_speed:
        return _flat_curve_augmentation(case)
    if cohort is SupplementalCohort.instant_center_two_point_speed:
        return _instant_center_augmentation(case)
    raise SupplementalManifestRefused(SupplementalManifestReason.source_shape_changed)


def build_supplemental_manifest(
    cases: Sequence[PublicCorpusCaseV1],
) -> SupplementalManifestBuildV1:
    """Build the nine-entry manifest, binding identities after discovery."""

    source_cases = tuple(source_only_case(case) for case in cases)
    if len(source_cases) != len(cases):
        raise SupplementalManifestRefused(
            SupplementalManifestReason.source_population_mismatch
        )
    selection = discover_supplemental_cohorts(source_cases)

    entries: list[AugmentationEntryV1] = []
    identities: list[dict[str, str]] = []
    for position in selection.selected_positions:
        # This is the first operation that sees the complete record.  Its
        # answer-bearing members are serialized only into a one-way identity
        # hash, after selection has already finished; none is inspected.
        record = cases[position].model_dump(mode="json", warnings="none")
        fingerprint = record_fingerprint(record)
        cohort = selection.cohort_for_position(position)
        entries.append(
            AugmentationEntryV1(
                original_fingerprint=fingerprint,
                review_status=ReviewStatus.reviewed,
                authoring_provenance=SUPPLEMENTAL_AUTHORING_PROVENANCE,
                augmentation=_augmentation_for(cohort, source_cases[position]),
            )
        )
        identities.append(
            {"cohort": cohort.value, "original_fingerprint": fingerprint}
        )

    manifest = AugmentationManifestV1(entries=tuple(entries))
    assert_manifest_has_no_answer_authority(manifest.model_dump(mode="json"))
    identity_material = json.dumps(
        identities,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return SupplementalManifestBuildV1(
        manifest=manifest,
        selection=selection,
        selection_identity_digest=hashlib.sha256(identity_material).hexdigest(),
    )


def supplemental_manifest_body(manifest: AugmentationManifestV1) -> str:
    """Canonical human-readable bytes for the out-of-tree manifest file."""

    assert_manifest_has_no_answer_authority(manifest.model_dump(mode="json"))
    return (
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


__all__ = [
    "EXPECTED_COHORT_SIZE",
    "EXPECTED_SELECTED_CONTEXTS",
    "SOURCE_ONLY_FIELDS",
    "SUPPLEMENTAL_CAMPAIGN_ID",
    "SourceOnlyCaseV1",
    "SupplementalCohort",
    "SupplementalManifestBuildV1",
    "SupplementalManifestReason",
    "SupplementalManifestRefused",
    "SupplementalSelectionV1",
    "build_supplemental_manifest",
    "discover_supplemental_cohorts",
    "source_only_case",
    "supplemental_manifest_body",
]
