"""Source-only Phase 57 continuation manifest, generation two.

The Phase 56 supplemental nine-entry manifest is historical evidence and never
changes here.  Phase 57 generation two starts from those exact reviewed entries
and adds five three-case cohorts whose missing carriers are stated verbatim by
the committed public source records:

* horizontal driven kinetic contact;
* frictionless horizontal table-pulley support;
* incline kinetic motion sense;
* spring natural-length endpoint; and
* vertical-circle inside-contact limit.

Cohort discovery sees only :class:`SourceOnlyCaseV1`.  Complete public records
are consulted only after the 24 source positions are frozen, and then only to
compute their opaque fingerprints.  No answer, expected terminal, family,
case identifier, solver result, or gold tolerance participates in selection or
carrier authoring.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
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
    ContactSide,
    ContactSideV2,
    CorpusV2AugmentationV1,
    EndpointCondition,
    EndpointConditionV2,
    FrameAxisV2,
    FrameOriginKind,
    FrameType,
    MotionSense,
    MotionSenseV2,
    ReferenceFrameV2,
    SourceQuoteEvidenceV2,
)
from evaluation.phase56_stage7.corpus_v2.supplemental_campaign import (
    SourceOnlyCaseV1,
    SupplementalCohort,
    SupplementalManifestRefused,
    build_supplemental_manifest,
    source_only_case,
)


PHASE57_CONTINUATION_CAMPAIGN_ID = (
    "PHASE57_REPRODUCIBLE_PUBLIC_CONTINUATION_V2"
)
PHASE57_CONTINUATION_AUTHORING_PROVENANCE = (
    f"{PHASE57_CONTINUATION_CAMPAIGN_ID}:source-only-reviewed-v2"
)
EXPECTED_COHORT_SIZE = 3
EXPECTED_SELECTED_CONTEXTS = 24

_HORIZONTAL_FLOOR_QUOTE = "수평 바닥"
_RIGHTWARD_MOTION_QUOTE = "오른쪽으로 움직이고 있다"
_HORIZONTAL_TABLE_QUOTE = "마찰 없는 수평면"
_DOWNSLOPE_MOTION_QUOTE = "아래쪽으로 미끄러진다"
_NATURAL_LENGTH_QUOTE = "자연길이가 되는 순간"
_INSIDE_TRACK_QUOTE = "안쪽"
_CONTACT_LIMIT_QUOTE = "접촉을 막 유지하기 위한 최소 속력"


class Phase57ContinuationCohort(str, Enum):
    banked_frictionless_curve = "banked_frictionless_curve"
    flat_curve_maximum_speed = "flat_curve_maximum_speed"
    instant_center_two_point_speed = "instant_center_two_point_speed"
    horizontal_driven_kinetic_contact = "horizontal_driven_kinetic_contact"
    table_pulley_horizontal_support = "table_pulley_horizontal_support"
    incline_kinetic_motion = "incline_kinetic_motion"
    spring_natural_length_endpoint = "spring_natural_length_endpoint"
    vertical_circle_contact_limit = "vertical_circle_contact_limit"


class Phase57ContinuationManifestReason(str, Enum):
    cohort_cardinality_mismatch = "phase57_continuation_cohort_cardinality_mismatch"
    cohort_overlap = "phase57_continuation_cohort_overlap"
    selected_population_mismatch = "phase57_continuation_population_mismatch"
    source_quote_missing_or_ambiguous = (
        "phase57_continuation_source_quote_missing_or_ambiguous"
    )
    source_shape_changed = "phase57_continuation_source_shape_changed"


class Phase57ContinuationManifestRefused(ValueError):
    """A source-content-free refusal from generation-two construction."""

    def __init__(self, reason: Phase57ContinuationManifestReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Phase57ContinuationSelectionV2:
    by_cohort: tuple[tuple[Phase57ContinuationCohort, tuple[int, ...]], ...]

    @property
    def selected_positions(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                position
                for _, positions in self.by_cohort
                for position in positions
            )
        )

    def cohort_for_position(self, position: int) -> Phase57ContinuationCohort:
        matches = [
            cohort for cohort, positions in self.by_cohort if position in positions
        ]
        if len(matches) != 1:
            raise Phase57ContinuationManifestRefused(
                Phase57ContinuationManifestReason.cohort_overlap
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class Phase57ContinuationManifestBuildV2:
    manifest: AugmentationManifestV1
    selection: Phase57ContinuationSelectionV2
    selection_identity_digest: str


def _signature(case: SourceOnlyCaseV1) -> tuple[object, ...]:
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


_HORIZONTAL_DRIVEN_SIGNATURE = (
    ("block", "surface"),
    ("slides_on",),
    ("constant_gravity",),
    ("coefficient_of_friction", "force", "mass"),
    (("acceleration", "x"),),
    ("unknown",),
    ("start",),
    ("none", ()),
)

_TABLE_PULLEY_SIGNATURE = (
    ("block", "block", "pulley", "surface", "system"),
    ("connected_by_rope", "passes_over_pulley", "slides_on"),
    (
        "constant_gravity",
        "frictionless",
        "inextensible_rope",
        "massless_pulley",
        "massless_rope",
    ),
    ("mass_1", "mass_2"),
    (("acceleration", "magnitude"),),
    ("unknown",),
    ("start",),
    ("none", ()),
)

_INCLINE_KINETIC_SIGNATURE = (
    ("block", "incline"),
    ("slides_on",),
    ("constant_gravity",),
    ("angle", "coefficient_of_friction"),
    (("acceleration", "tangential"),),
    ("sliding_on_incline",),
    ("start",),
    ("none", ()),
)

_SPRING_NATURAL_LENGTH_SIGNATURE = (
    ("block", "spring", "surface"),
    ("attached_to_spring", "slides_on"),
    ("frictionless", "starts_from_rest"),
    ("displacement", "mass", "spring_constant"),
    (("final_velocity", "magnitude"),),
    ("energy_interval",),
    ("finish", "release"),
    ("none", ()),
)

_VERTICAL_CIRCLE_SIGNATURE = (
    ("particle", "surface"),
    ("contact_with",),
    ("constant_gravity",),
    ("radius",),
    (("minimum_speed", "magnitude"),),
    ("unknown",),
    ("highest_point",),
    ("none", ()),
)

_EXPANSION_SIGNATURES: tuple[
    tuple[Phase57ContinuationCohort, tuple[object, ...]], ...
] = (
    (
        Phase57ContinuationCohort.horizontal_driven_kinetic_contact,
        _HORIZONTAL_DRIVEN_SIGNATURE,
    ),
    (
        Phase57ContinuationCohort.table_pulley_horizontal_support,
        _TABLE_PULLEY_SIGNATURE,
    ),
    (
        Phase57ContinuationCohort.incline_kinetic_motion,
        _INCLINE_KINETIC_SIGNATURE,
    ),
    (
        Phase57ContinuationCohort.spring_natural_length_endpoint,
        _SPRING_NATURAL_LENGTH_SIGNATURE,
    ),
    (
        Phase57ContinuationCohort.vertical_circle_contact_limit,
        _VERTICAL_CIRCLE_SIGNATURE,
    ),
)

_BASELINE_COHORT_MAP: dict[SupplementalCohort, Phase57ContinuationCohort] = {
    SupplementalCohort.banked_frictionless_curve: (
        Phase57ContinuationCohort.banked_frictionless_curve
    ),
    SupplementalCohort.flat_curve_maximum_speed: (
        Phase57ContinuationCohort.flat_curve_maximum_speed
    ),
    SupplementalCohort.instant_center_two_point_speed: (
        Phase57ContinuationCohort.instant_center_two_point_speed
    ),
}


def _unique_quote(problem_text: str, quote: str) -> str:
    if problem_text.count(quote) != 1:
        raise Phase57ContinuationManifestRefused(
            Phase57ContinuationManifestReason.source_quote_missing_or_ambiguous
        )
    return quote


def _one(items: Sequence[object]) -> object:
    if len(items) != 1:
        raise Phase57ContinuationManifestRefused(
            Phase57ContinuationManifestReason.source_shape_changed
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


def _horizontal_support_frames(
    *, case: SourceOnlyCaseV1, evidence_id: str
) -> tuple[ReferenceFrameV2, ReferenceFrameV2]:
    surface = _one([item for item in case.entities if item.kind == "surface"])
    world_frame = "v2_frame_world_horizontal_support"
    support_frame = "v2_frame_horizontal_support"
    return (
        ReferenceFrameV2(
            frame_id=world_frame,
            frame_type=FrameType.world_cartesian,
            origin_kind=FrameOriginKind.world,
            subject_id=surface.role,
            axes=(
                _axis(
                    name="x",
                    sense=AxisSense.along_surface_forward,
                    bound_frame_id=world_frame,
                    bound_axis="x",
                    evidence_id=evidence_id,
                ),
                _axis(
                    name="y",
                    sense=AxisSense.up_the_page,
                    bound_frame_id=world_frame,
                    bound_axis="y",
                    evidence_id=evidence_id,
                ),
            ),
            evidence_refs=(evidence_id,),
        ),
        ReferenceFrameV2(
            frame_id=support_frame,
            frame_type=FrameType.surface_tangent_normal,
            origin_kind=FrameOriginKind.entity,
            subject_id=surface.role,
            parent_frame_id=world_frame,
            axes=(
                _axis(
                    name="tangent",
                    sense=AxisSense.along_surface_forward,
                    anchor_entity_id=surface.role,
                    bound_frame_id=world_frame,
                    bound_axis="x",
                    evidence_id=evidence_id,
                ),
                _axis(
                    name="normal",
                    sense=AxisSense.away_from_surface,
                    anchor_entity_id=surface.role,
                    bound_frame_id=world_frame,
                    bound_axis="y",
                    evidence_id=evidence_id,
                ),
            ),
            evidence_refs=(evidence_id,),
        ),
    )


def _horizontal_driven_augmentation(
    case: SourceOnlyCaseV1,
) -> CorpusV2AugmentationV1:
    horizontal_evidence = "v2_ev_horizontal_floor"
    motion_evidence = "v2_ev_rightward_motion"
    body = _one([item for item in case.entities if item.kind == "block"])
    segment = _one(list(case.motion_segments))
    frames = _horizontal_support_frames(case=case, evidence_id=horizontal_evidence)
    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(
                evidence_id=horizontal_evidence,
                quote=_unique_quote(case.problem_text, _HORIZONTAL_FLOOR_QUOTE),
            ),
            SourceQuoteEvidenceV2(
                evidence_id=motion_evidence,
                quote=_unique_quote(case.problem_text, _RIGHTWARD_MOTION_QUOTE),
            ),
        ),
        reference_frames=frames,
        motion_senses=(
            MotionSenseV2(
                sense_id="v2_motion_rightward_on_support",
                sense=MotionSense.along_axis_positive,
                frame_id=frames[1].frame_id,
                axis="tangent",
                sign=1,
                subject_id=body.role,
                interval_id=segment.role,
                evidence_refs=(motion_evidence,),
            ),
        ),
    )


def _table_pulley_augmentation(
    case: SourceOnlyCaseV1,
) -> CorpusV2AugmentationV1:
    evidence_id = "v2_ev_horizontal_table"
    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(
                evidence_id=evidence_id,
                quote=_unique_quote(case.problem_text, _HORIZONTAL_TABLE_QUOTE),
            ),
        ),
        reference_frames=_horizontal_support_frames(
            case=case, evidence_id=evidence_id
        ),
    )


def _incline_augmentation(case: SourceOnlyCaseV1) -> CorpusV2AugmentationV1:
    evidence_id = "v2_ev_downslope_motion"
    body = _one([item for item in case.entities if item.kind == "block"])
    incline = _one([item for item in case.entities if item.kind == "incline"])
    segment = _one(list(case.motion_segments))
    world_frame = "v2_frame_world_incline"
    slope_frame = "v2_frame_slope"
    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(
                evidence_id=evidence_id,
                quote=_unique_quote(case.problem_text, _DOWNSLOPE_MOTION_QUOTE),
            ),
        ),
        reference_frames=(
            ReferenceFrameV2(
                frame_id=world_frame,
                frame_type=FrameType.world_cartesian,
                origin_kind=FrameOriginKind.world,
                subject_id=incline.role,
                axes=(
                    _axis(
                        name="x",
                        sense=AxisSense.along_surface_forward,
                        bound_frame_id=world_frame,
                        bound_axis="x",
                        evidence_id=evidence_id,
                    ),
                    _axis(
                        name="y",
                        sense=AxisSense.up_the_page,
                        bound_frame_id=world_frame,
                        bound_axis="y",
                        evidence_id=evidence_id,
                    ),
                ),
                evidence_refs=(evidence_id,),
            ),
            ReferenceFrameV2(
                frame_id=slope_frame,
                frame_type=FrameType.incline_tangent_normal,
                origin_kind=FrameOriginKind.entity,
                subject_id=incline.role,
                parent_frame_id=world_frame,
                axes=(
                    _axis(
                        name="tangent",
                        sense=AxisSense.down_slope,
                        bound_frame_id=slope_frame,
                        bound_axis="tangent",
                        evidence_id=evidence_id,
                    ),
                    _axis(
                        name="normal",
                        sense=AxisSense.away_from_surface,
                        bound_frame_id=slope_frame,
                        bound_axis="normal",
                        evidence_id=evidence_id,
                    ),
                ),
                evidence_refs=(evidence_id,),
            ),
        ),
        motion_senses=(
            MotionSenseV2(
                sense_id="v2_motion_downslope",
                sense=MotionSense.along_axis_positive,
                frame_id=slope_frame,
                axis="tangent",
                sign=1,
                subject_id=body.role,
                interval_id=segment.role,
                evidence_refs=(evidence_id,),
            ),
        ),
    )


def _spring_augmentation(case: SourceOnlyCaseV1) -> CorpusV2AugmentationV1:
    evidence_id = "v2_ev_natural_length"
    spring = _one([item for item in case.entities if item.kind == "spring"])
    segment = _one(list(case.motion_segments))
    finish = _one([item for item in case.events if item.kind == "finish"])
    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(
                evidence_id=evidence_id,
                quote=_unique_quote(case.problem_text, _NATURAL_LENGTH_QUOTE),
            ),
        ),
        endpoint_conditions=(
            EndpointConditionV2(
                endpoint_id="v2_natural_length_endpoint",
                condition=EndpointCondition.reaches_natural_length,
                boundary_event_id=finish.role,
                subject_id=spring.role,
                interval_id=segment.role,
                evidence_refs=(evidence_id,),
            ),
        ),
    )


def _vertical_circle_augmentation(
    case: SourceOnlyCaseV1,
) -> CorpusV2AugmentationV1:
    inside_evidence = "v2_ev_inside_track"
    limit_evidence = "v2_ev_contact_limit"
    particle = _one([item for item in case.entities if item.kind == "particle"])
    track = _one([item for item in case.entities if item.kind == "surface"])
    contact = _one([item for item in case.relations if item.kind == "contact_with"])
    segment = _one(list(case.motion_segments))
    top = _one([item for item in case.events if item.kind == "highest_point"])
    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(
                evidence_id=inside_evidence,
                quote=_unique_quote(case.problem_text, _INSIDE_TRACK_QUOTE),
            ),
            SourceQuoteEvidenceV2(
                evidence_id=limit_evidence,
                quote=_unique_quote(case.problem_text, _CONTACT_LIMIT_QUOTE),
            ),
        ),
        contact_sides=(
            ContactSideV2(
                contact_id="v2_contact_inside_track",
                interaction_id=f"rel_{contact.role}",
                side=ContactSide.inside_track,
                subject_id=particle.role,
                evidence_refs=(inside_evidence,),
            ),
        ),
        constraint_authorities=(
            ConstraintAuthorityV2(
                constraint_id="v2_contact_maintained",
                authority=ConstraintAuthority.contact_maintained,
                participant_ids=(particle.role, track.role),
                subject_id=particle.role,
                interval_id=segment.role,
                evidence_refs=(limit_evidence,),
            ),
        ),
        endpoint_conditions=(
            EndpointConditionV2(
                endpoint_id="v2_contact_limit_boundary",
                condition=EndpointCondition.contact_limit,
                boundary_event_id=top.role,
                subject_id=particle.role,
                interval_id=segment.role,
                evidence_refs=(limit_evidence,),
            ),
        ),
    )


def _augmentation_for(
    cohort: Phase57ContinuationCohort,
    case: SourceOnlyCaseV1,
) -> CorpusV2AugmentationV1:
    if cohort is Phase57ContinuationCohort.horizontal_driven_kinetic_contact:
        return _horizontal_driven_augmentation(case)
    if cohort is Phase57ContinuationCohort.table_pulley_horizontal_support:
        return _table_pulley_augmentation(case)
    if cohort is Phase57ContinuationCohort.incline_kinetic_motion:
        return _incline_augmentation(case)
    if cohort is Phase57ContinuationCohort.spring_natural_length_endpoint:
        return _spring_augmentation(case)
    if cohort is Phase57ContinuationCohort.vertical_circle_contact_limit:
        return _vertical_circle_augmentation(case)
    raise Phase57ContinuationManifestRefused(
        Phase57ContinuationManifestReason.source_shape_changed
    )


def discover_phase57_continuation_cohorts(
    cases: Sequence[SourceOnlyCaseV1],
    *,
    baseline_positions: Sequence[int] = (),
) -> Phase57ContinuationSelectionV2:
    """Discover five expansion cohorts and combine them with the frozen nine."""

    baseline = tuple(sorted(baseline_positions))
    if len(baseline) != 9 or len(baseline) != len(set(baseline)):
        raise Phase57ContinuationManifestRefused(
            Phase57ContinuationManifestReason.source_shape_changed
        )

    selected: list[tuple[Phase57ContinuationCohort, tuple[int, ...]]] = []
    for cohort, expected_signature in _EXPANSION_SIGNATURES:
        positions = tuple(
            position
            for position, case in enumerate(cases)
            if _signature(case) == expected_signature
        )
        if len(positions) != EXPECTED_COHORT_SIZE:
            raise Phase57ContinuationManifestRefused(
                Phase57ContinuationManifestReason.cohort_cardinality_mismatch
            )
        selected.append((cohort, positions))

    expansion = [position for _, positions in selected for position in positions]
    if len(expansion) != len(set(expansion)) or set(expansion) & set(baseline):
        raise Phase57ContinuationManifestRefused(
            Phase57ContinuationManifestReason.cohort_overlap
        )
    if len(baseline) + len(expansion) != EXPECTED_SELECTED_CONTEXTS:
        raise Phase57ContinuationManifestRefused(
            Phase57ContinuationManifestReason.selected_population_mismatch
        )
    return Phase57ContinuationSelectionV2(by_cohort=tuple(selected))


def build_phase57_continuation_manifest(
    cases: Sequence[PublicCorpusCaseV1],
) -> Phase57ContinuationManifestBuildV2:
    """Build a 24-entry source-only manifest without changing Phase 56 bytes."""

    source_cases = tuple(source_only_case(case) for case in cases)
    try:
        baseline = build_supplemental_manifest(cases)
    except SupplementalManifestRefused as exc:
        raise Phase57ContinuationManifestRefused(
            Phase57ContinuationManifestReason.source_shape_changed
        ) from exc

    baseline_by_position = dict(
        zip(
            baseline.selection.selected_positions,
            baseline.manifest.entries,
            strict=True,
        )
    )
    expansion = discover_phase57_continuation_cohorts(
        source_cases,
        baseline_positions=baseline.selection.selected_positions,
    )

    combined_by_cohort: list[
        tuple[Phase57ContinuationCohort, tuple[int, ...]]
    ] = [
        (_BASELINE_COHORT_MAP[cohort], positions)
        for cohort, positions in baseline.selection.by_cohort
    ]
    combined_by_cohort.extend(expansion.by_cohort)
    selection = Phase57ContinuationSelectionV2(by_cohort=tuple(combined_by_cohort))
    if len(selection.selected_positions) != EXPECTED_SELECTED_CONTEXTS:
        raise Phase57ContinuationManifestRefused(
            Phase57ContinuationManifestReason.selected_population_mismatch
        )

    entries: list[AugmentationEntryV1] = []
    identities: list[dict[str, str]] = []
    for position in selection.selected_positions:
        cohort = selection.cohort_for_position(position)
        fingerprint = record_fingerprint(
            cases[position].model_dump(mode="json", warnings="none")
        )
        existing = baseline_by_position.get(position)
        if existing is not None:
            if existing.original_fingerprint != fingerprint:
                raise Phase57ContinuationManifestRefused(
                    Phase57ContinuationManifestReason.source_shape_changed
                )
            entry = existing
        else:
            entry = AugmentationEntryV1(
                original_fingerprint=fingerprint,
                review_status=ReviewStatus.reviewed,
                authoring_provenance=PHASE57_CONTINUATION_AUTHORING_PROVENANCE,
                augmentation=_augmentation_for(cohort, source_cases[position]),
            )
        entries.append(entry)
        identities.append(
            {"cohort": cohort.value, "original_fingerprint": fingerprint}
        )

    manifest = AugmentationManifestV1(entries=tuple(entries))
    assert_manifest_has_no_answer_authority(manifest.model_dump(mode="json"))
    material = json.dumps(
        identities,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return Phase57ContinuationManifestBuildV2(
        manifest=manifest,
        selection=selection,
        selection_identity_digest=hashlib.sha256(material).hexdigest(),
    )


def phase57_continuation_manifest_body(manifest: AugmentationManifestV1) -> str:
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
    "PHASE57_CONTINUATION_AUTHORING_PROVENANCE",
    "PHASE57_CONTINUATION_CAMPAIGN_ID",
    "Phase57ContinuationCohort",
    "Phase57ContinuationManifestBuildV2",
    "Phase57ContinuationManifestReason",
    "Phase57ContinuationManifestRefused",
    "Phase57ContinuationSelectionV2",
    "build_phase57_continuation_manifest",
    "discover_phase57_continuation_cohorts",
    "phase57_continuation_manifest_body",
]
