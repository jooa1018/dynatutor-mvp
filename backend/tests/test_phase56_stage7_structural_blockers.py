"""The structural blocker census is a measurement, and must stay one.

These fixtures are independently authored Draft payloads.  They pin what the
census counts, that it counts nothing it should not, and — the part that
matters for Stage 7 — that the free-body primitive set the census reads is the
engine's own, so a change to the engine cannot silently make a blocked context
look unblocked.
"""

from __future__ import annotations

import json

import pytest

from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
)
from engine.mechanics.laws.core import free_body_primitive_names
from engine.mechanics.math_ast import DimensionVector

from evaluation.phase56_stage7.lane_b_structural_blockers import (
    STRUCTURAL_BLOCKER_CENSUS_VERSION,
    build_structural_blocker_census,
    census_as_dict,
    non_free_body_primitives,
)

ACCELERATION = DimensionVector(length=1, time=-2)


def _entity(entity_id: str, primitive: str) -> dict:
    return {
        "entity_id": entity_id,
        "primitive": primitive,
        "label": entity_id,
        "aliases": [],
        "component_of_entity_id": None,
        "evidence_refs": [],
        "model_confidence": None,
    }


def _draft(
    *,
    subject_primitive: str = "particle",
    component: str = "magnitude",
    frames: bool = False,
    interactions: bool = False,
    events: bool = False,
    bounded_interval: bool = False,
) -> MechanicsProblemDraftV1:
    """One minimal Draft with exactly the structure a control needs."""

    event_records = (
        [
            {
                "event_id": "ev_start",
                "kind": "start",
                "subject_ids": ["body"],
                "interval_ids": ["seg"],
                "time_quantity_id": None,
                "evidence_refs": [],
            },
            {
                "event_id": "ev_finish",
                "kind": "finish",
                "subject_ids": ["body"],
                "interval_ids": ["seg"],
                "time_quantity_id": None,
                "evidence_refs": [],
            },
        ]
        if events
        else []
    )
    payload = {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "ko",
            "correction_revision": 0,
            "system_type": None,
            "subtype": None,
            "model_id": None,
            "model_hash": None,
            "prompt_hash": None,
            "source_text_sha256": None,
            "model_confidence": None,
        },
        "source_assets": [],
        "source_evidence": [],
        "entities": [_entity("body", subject_primitive)],
        "points": [],
        "reference_frames": (
            [
                {
                    "frame_id": "frm",
                    "frame_type": "cartesian_2d",
                    "origin": {"kind": "world"},
                    "axes": [
                        {
                            "axis": name,
                            "direction": {
                                "kind": "axis",
                                "frame_id": "frm",
                                "axis": name,
                                "sign": 1,
                            },
                        }
                        for name in ("x", "y")
                    ],
                    "parent_frame_id": None,
                    "translating_with_entity_id": None,
                    "rotating_about_point_id": None,
                    "generalized_coordinate_symbol_ids": [],
                    "evidence_refs": [],
                }
            ]
            if frames
            else []
        ),
        "motion_intervals": [
            {
                "interval_id": "seg",
                "order": 1,
                "subject_ids": ["body"],
                "frame_id": None,
                "start_event_id": "ev_start" if bounded_interval and events else None,
                "end_event_id": "ev_finish" if bounded_interval and events else None,
                "evidence_refs": [],
            }
        ],
        "events": event_records,
        "symbols": [
            {
                "symbol_id": "sym_a",
                "quantity_id": "qty_a",
                "dimension": ACCELERATION.model_dump(mode="json"),
                "shape": "scalar",
                "vector_length": None,
            }
        ],
        "quantities": [
            {
                "quantity_id": "qty_a",
                "symbol_id": "sym_a",
                "role": "acceleration",
                "subject_id": "body",
                "point_id": None,
                "frame_id": None,
                "interval_id": "seg",
                "event_id": None,
                "component": component,
                "direction": None,
                "shape": "scalar",
                "dimension": ACCELERATION.model_dump(mode="json"),
                "provenance": "unknown",
                "evidence_refs": [],
                "assumption_policy_ref": None,
                "correction_id": None,
                "model_confidence": None,
                "raw_value": None,
                "raw_unit": None,
            }
        ],
        "geometry": [],
        "interactions": (
            [
                {
                    "interaction_id": "int_c",
                    "kind": "contact",
                    "participant_ids": ["body"],
                    "point_ids": [],
                    "frame_id": None,
                    "interval_id": "seg",
                    "event_id": None,
                    "quantity_ids": [],
                    "evidence_refs": [],
                }
            ]
            if interactions
            else []
        ),
        "constraints": [],
        "state_conditions": [],
        "queries": [
            {
                "query_id": "q1",
                "target": {
                    "role": "acceleration",
                    "subject_id": "body",
                    "point_id": None,
                    "frame_id": None,
                    "interval_id": "seg",
                    "event_id": None,
                    "component": component,
                    "direction": None,
                    "target_quantity_id": "qty_a",
                },
                "output_unit": "m/s^2",
                "output_dimension": ACCELERATION.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": [],
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
    return MechanicsProblemDraftV1.model_validate(payload)


# --------------------------------------------------------------------------
# What the census counts
# --------------------------------------------------------------------------


def test_an_empty_input_is_an_empty_census():
    census = build_structural_blocker_census([])
    assert census.context_count == 0
    assert census.contexts_with_non_free_body_query_subject == 0
    assert census.query_subject_primitive_counts == ()


def test_a_draft_missing_every_structure_is_counted_in_every_column():
    census = build_structural_blocker_census([_draft()])
    assert census.context_count == 1
    assert census.contexts_without_reference_frame == 1
    assert census.contexts_without_interaction == 1
    assert census.contexts_with_events == 0
    assert census.contexts_without_bounded_interval == 1
    assert census.contexts_with_magnitude_query == 1


def test_supplied_structure_is_not_counted_as_missing():
    census = build_structural_blocker_census(
        [
            _draft(
                frames=True,
                interactions=True,
                events=True,
                bounded_interval=True,
                component="x",
            )
        ]
    )
    assert census.contexts_without_reference_frame == 0
    assert census.contexts_without_interaction == 0
    assert census.contexts_with_events == 1
    assert census.contexts_without_bounded_interval == 0
    assert census.contexts_with_magnitude_query == 0
    assert census.query_component_counts == (("x", 1),)


@pytest.mark.parametrize("primitive", ["particle", "rigid_body", "mass_center"])
def test_a_free_body_query_subject_is_not_a_blocker(primitive):
    census = build_structural_blocker_census([_draft(subject_primitive=primitive)])
    assert census.contexts_with_non_free_body_query_subject == 0
    assert census.query_subject_primitive_counts == ((primitive, 1),)


@pytest.mark.parametrize("primitive", ["system", "point", "joint"])
def test_a_non_free_body_query_subject_is_a_blocker(primitive):
    """No free-body law writes an equation for these, whatever else is supplied.

    This is the blocker no closure transaction can remove: making the equation
    reachable would mean restating what the source says the entity *is*.
    """

    census = build_structural_blocker_census([_draft(subject_primitive=primitive)])
    assert census.contexts_with_non_free_body_query_subject == 1
    assert census.query_subject_primitive_counts == ((primitive, 1),)


def test_counts_accumulate_across_contexts():
    census = build_structural_blocker_census(
        [
            _draft(subject_primitive="particle"),
            _draft(subject_primitive="system"),
            _draft(subject_primitive="system"),
        ]
    )
    assert census.context_count == 3
    assert census.contexts_with_non_free_body_query_subject == 2
    assert dict(census.query_subject_primitive_counts) == {"particle": 1, "system": 2}


# --------------------------------------------------------------------------
# The set it reads is the engine's own
# --------------------------------------------------------------------------


def test_the_census_reads_the_engines_free_body_set_and_does_not_restate_it():
    census = build_structural_blocker_census([_draft()])
    assert census.free_body_primitives == tuple(sorted(free_body_primitive_names()))


def test_the_non_free_body_primitives_are_the_exact_complement():
    free_body = set(free_body_primitive_names())
    assert free_body.isdisjoint(non_free_body_primitives())
    assert "system" in non_free_body_primitives()
    assert "particle" not in non_free_body_primitives()


# --------------------------------------------------------------------------
# Privacy: the record has no field that could carry corpus content
# --------------------------------------------------------------------------


def test_the_census_record_carries_only_counts_and_closed_vocabulary():
    census = build_structural_blocker_census(
        [_draft(subject_primitive="system"), _draft(component="x")]
    )
    payload = census_as_dict(census)
    text = json.dumps(payload, ensure_ascii=False)

    # Every leaf is a count, a version string, or a closed-vocabulary name.
    closed = set(free_body_primitive_names()) | set(non_free_body_primitives())
    closed |= {
        "magnitude", "x", "y", "z", "radial", "transverse", "tangential",
        "normal", "clockwise", "counterclockwise", "unspecified", "unresolved",
    }
    for row in payload["query_subject_primitive_counts"]:
        assert row["primitive"] in closed
        assert isinstance(row["count"], int)
    for row in payload["query_component_counts"]:
        assert row["component"] in closed
        assert isinstance(row["count"], int)
    assert payload["version"] == STRUCTURAL_BLOCKER_CENSUS_VERSION

    forbidden_keys = {
        "case_id", "family", "split", "chapter", "difficulty", "tags",
        "problem_text", "expected_answer", "expected_terminal", "answer",
        "gold", "filename", "quote",
    }
    assert forbidden_keys.isdisjoint(payload)
    for token in ("case_id", "family", "problem_text", "answer", "gold"):
        assert token not in text


def test_the_census_does_not_mutate_the_drafts_it_reads():
    drafts = [_draft(subject_primitive="system"), _draft(component="x")]
    before = [item.model_dump_json(warnings="none") for item in drafts]
    build_structural_blocker_census(drafts)
    after = [item.model_dump_json(warnings="none") for item in drafts]
    assert before == after


def test_a_draft_without_a_question_is_not_a_context():
    """A Draft with no query has no queried unknown to be blocked on."""

    payload = json.loads(_draft().model_dump_json(warnings="none"))
    payload["queries"] = []
    census = build_structural_blocker_census(
        [MechanicsProblemDraftV1.model_validate(payload)]
    )
    assert census.context_count == 0
