"""Stage 7 Lane B: which contract can express the two corpus structures.

Lane B evaluates the deterministic engine, so the question is not "how do we
force a parse through the Phase 55 graph contract" but "which typed contract
represents the corpus naturally".  This suite answers that with executable
evidence and pins both halves of the answer.

Blocker A — segment-internal query event: a query bound to a motion interval
*and* to an event that is not that interval's start or end boundary.

Blocker B — relation-scoped timeless environment fact: a timeless contact
property whose subject is an environment entity that is deliberately not a
subject of the motion interval, linked to the moving actor by a single
interval-scoped relation.

Result: `MechanicsProblemDraftV1` expresses both natively and
`validate_draft` accepts them, so the evaluator projects corpus structure
straight to a Draft.  The Phase 55 parse contract cannot express either shape;
that is recorded here as a product-parser expressiveness limitation rather than
hidden, and no Phase 55 contract is relaxed to work around it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
)
from engine.mechanics.validation import validate_draft
from engine.textbook_parser.contracts import (
    SCHEMA_NAME as PARSE_SCHEMA_NAME,
    SCHEMA_VERSION as PARSE_SCHEMA_VERSION,
    TextbookProblemParseV1,
)


PROBLEM_TEXT = (
    "물체가 수평면 위에서 미끄러진다. 경사각은 30 deg 이고 마찰계수는 0.2 이다. "
    "어느 순간의 속도를 구하시오."
)
_ANGLE_QUOTE = "경사각은 30 deg"
_MU_QUOTE = "마찰계수는 0.2"


def _span(needle: str) -> dict[str, int]:
    start = PROBLEM_TEXT.index(needle)
    return {"start": start, "end": start + len(needle)}


def draft_payload() -> dict[str, object]:
    """A Draft carrying blocker A and blocker B at the same time."""

    return {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {"language": "ko", "correction_revision": 0},
        "source_assets": [],
        "source_evidence": [
            {
                "evidence_id": "ev_angle",
                "kind": "text",
                "quote": _ANGLE_QUOTE,
                "occurrence_index": 0,
                "source_span": _span(_ANGLE_QUOTE),
                "quantity_span": _span("30 deg"),
            },
            {
                "evidence_id": "ev_mu",
                "kind": "text",
                "quote": _MU_QUOTE,
                "occurrence_index": 0,
                "source_span": _span(_MU_QUOTE),
                "quantity_span": _span("0.2"),
            },
        ],
        "entities": [
            {
                "entity_id": "body",
                "primitive": "particle",
                "label": "물체",
                "aliases": [],
                "evidence_refs": [],
            },
            {
                "entity_id": "incline",
                "primitive": "surface",
                "label": "경사면",
                "aliases": [],
                "evidence_refs": [],
            },
        ],
        "points": [],
        "reference_frames": [],
        "motion_intervals": [
            {
                "interval_id": "seg1",
                "order": 1,
                "subject_ids": ["body"],
                "start_event_id": "e_start",
                "end_event_id": "e_end",
                "evidence_refs": [],
            }
        ],
        # Blocker A: ``e_mid`` belongs to the interval without being a boundary.
        "events": [
            {
                "event_id": "e_start",
                "kind": "start",
                "subject_ids": ["body"],
                "interval_ids": ["seg1"],
                "evidence_refs": [],
            },
            {
                "event_id": "e_end",
                "kind": "other",
                "subject_ids": ["body"],
                "interval_ids": ["seg1"],
                "evidence_refs": [],
            },
            {
                "event_id": "e_mid",
                "kind": "other",
                "subject_ids": ["body"],
                "interval_ids": ["seg1"],
                "evidence_refs": [],
            },
        ],
        # Blocker B: ``incline`` is not an interval subject, yet carries timeless
        # contact properties scoped to that interval.
        "quantities": [
            {
                "quantity_id": "q_angle",
                "role": "angle",
                "subject_id": "incline",
                "interval_id": "seg1",
                "shape": "scalar",
                "dimension": {},
                "provenance": "explicit_source",
                "raw_value": "30",
                "raw_unit": "deg",
                "evidence_refs": ["ev_angle"],
            },
            {
                "quantity_id": "q_mu",
                "role": "coefficient_friction",
                "subject_id": "incline",
                "interval_id": "seg1",
                "shape": "scalar",
                "dimension": {},
                "provenance": "explicit_source",
                "raw_value": "0.2",
                "raw_unit": "",
                "evidence_refs": ["ev_mu"],
            },
        ],
        "symbols": [],
        "geometry": [],
        "interactions": [
            {
                "interaction_id": "contact1",
                "kind": "contact",
                "participant_ids": ["body", "incline"],
                "interval_id": "seg1",
                "evidence_refs": [],
            }
        ],
        "constraints": [],
        "state_conditions": [],
        "queries": [
            {
                "query_id": "q1",
                "output_unit": "m/s",
                "output_dimension": {"length": 1, "time": -1},
                "shape": "scalar",
                "target": {
                    "role": "velocity",
                    "subject_id": "body",
                    "interval_id": "seg1",
                    "event_id": "e_mid",
                    "component": "magnitude",
                },
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


# --------------------------------------------------------------------------
# Positive: the Draft contract expresses both structures and validates
# --------------------------------------------------------------------------


def test_draft_expresses_both_blockers_and_validation_accepts() -> None:
    draft = MechanicsProblemDraftV1.model_validate(draft_payload())
    result = validate_draft(PROBLEM_TEXT, draft)
    assert result.accepted, [
        (getattr(issue.code, "value", issue.code), issue.path) for issue in result.issues
    ]
    assert result.issues == () or all(
        getattr(issue.code, "value", issue.code) != "query_binding_invalid"
        for issue in result.issues
    )


def test_blocker_a_event_is_genuinely_not_a_boundary() -> None:
    draft = MechanicsProblemDraftV1.model_validate(draft_payload())
    interval = draft.motion_intervals[0]
    assert interval.start_event_id == "e_start"
    assert interval.end_event_id == "e_end"
    mid = next(event for event in draft.events if event.event_id == "e_mid")
    assert interval.interval_id in mid.interval_ids
    assert mid.event_id not in (interval.start_event_id, interval.end_event_id)
    target = draft.queries[0].target
    assert target.interval_id == interval.interval_id
    assert target.event_id == "e_mid"


def test_blocker_b_subject_is_genuinely_not_an_interval_subject() -> None:
    draft = MechanicsProblemDraftV1.model_validate(draft_payload())
    interval = draft.motion_intervals[0]
    assert "incline" not in interval.subject_ids
    scoped = [item for item in draft.quantities if item.subject_id == "incline"]
    assert {item.role.value for item in scoped} == {"angle", "coefficient_friction"}
    assert all(item.interval_id == interval.interval_id for item in scoped)
    interaction = draft.interactions[0]
    assert set(interaction.participant_ids) == {"body", "incline"}
    assert interaction.interval_id == interval.interval_id


# --------------------------------------------------------------------------
# Negative: nothing was weakened — dangling references still fail closed
# --------------------------------------------------------------------------


def test_query_event_reference_to_a_missing_event_still_fails() -> None:
    payload = draft_payload()
    payload["queries"][0]["target"]["event_id"] = "e_does_not_exist"
    draft = MechanicsProblemDraftV1.model_validate(payload)
    result = validate_draft(PROBLEM_TEXT, draft)
    assert not result.accepted


def test_quantity_interval_reference_to_a_missing_interval_still_fails() -> None:
    payload = draft_payload()
    payload["quantities"][0]["interval_id"] = "seg_does_not_exist"
    draft = MechanicsProblemDraftV1.model_validate(payload)
    result = validate_draft(PROBLEM_TEXT, draft)
    assert not result.accepted


def test_quantity_subject_reference_to_a_missing_entity_still_fails() -> None:
    payload = draft_payload()
    payload["quantities"][0]["subject_id"] = "ghost_entity"
    draft = MechanicsProblemDraftV1.model_validate(payload)
    result = validate_draft(PROBLEM_TEXT, draft)
    assert not result.accepted


# --------------------------------------------------------------------------
# Adversarial: answer authority and ungrounded numbers still fail closed
# --------------------------------------------------------------------------


def test_answer_authority_in_the_draft_still_fails_closed() -> None:
    payload = draft_payload()
    payload["queries"][0]["expected_answer"] = 3.0
    with pytest.raises(ValidationError, match="answer-authority"):
        MechanicsProblemDraftV1.model_validate(payload)


def test_environment_scoped_quantity_must_still_be_source_grounded() -> None:
    """Blocker B does not buy an exemption from evidence grounding."""

    payload = draft_payload()
    payload["quantities"][0]["raw_value"] = "45"
    draft = MechanicsProblemDraftV1.model_validate(payload)
    result = validate_draft(PROBLEM_TEXT, draft)
    assert not result.accepted
    codes = {getattr(issue.code, "value", issue.code) for issue in result.issues}
    assert "invented_explicit_number" in codes


# --------------------------------------------------------------------------
# Recorded product-parser limitation (not hidden, not worked around)
# --------------------------------------------------------------------------


def _parse_payload() -> dict[str, object]:
    return {
        "schema": PARSE_SCHEMA_NAME,
        "version": PARSE_SCHEMA_VERSION,
        "language": "ko",
        "parse_status": "complete",
        "entities": [
            {"entity_id": "body", "kind": "particle", "label": "물체", "aliases": []},
            {"entity_id": "incline", "kind": "incline", "label": "경사면", "aliases": []},
        ],
        "motion_segments": [
            {
                "segment_id": "seg1",
                "order": 1,
                "actor_ids": ["body"],
                "motion_model_candidates": ["sliding_on_incline"],
                "start_event_id": "e_start",
                "end_event_id": "e_end",
                "relevance": "target",
            }
        ],
        "events": [
            {
                "event_id": "e_start",
                "kind": "start",
                "subject_ids": ["body"],
                "segment_id": "seg1",
            },
            {
                "event_id": "e_end",
                "kind": "finish",
                "subject_ids": ["body"],
                "segment_id": "seg1",
            },
            {
                "event_id": "e_mid",
                "kind": "other",
                "subject_ids": ["body"],
                "segment_id": "seg1",
            },
        ],
        "explicit_facts": [],
        "relations": [
            {
                "relation_id": "contact1",
                "kind": "slides_on",
                "entity_ids": ["body", "incline"],
                "segment_id": "seg1",
            }
        ],
        "queries": [
            {
                "query_id": "q1",
                "output_key": "final_velocity",
                "subject_id": "body",
                "segment_id": "seg1",
                "component": "magnitude",
            }
        ],
        "assumption_proposals": [],
        "interpretation_candidates": [],
        "ambiguities": [],
        "figure_dependency": {"level": "none", "missing_information": []},
        "unsupported_features": [],
    }


def test_recorded_parser_limitation_segment_internal_query_event() -> None:
    """Phase 55 cannot express blocker A; the corpus contains 25 such cases.

    This pins the current product-parser limitation so it stays visible.  It is
    not a Lane B workaround: Lane B projects to a Draft instead.
    """

    payload = _parse_payload()
    payload["queries"][0]["event_id"] = "e_mid"
    with pytest.raises(ValidationError, match="query segment and event bindings"):
        TextbookProblemParseV1.model_validate(payload)


def test_recorded_parser_limitation_relation_scoped_environment_fact() -> None:
    """Phase 55 cannot express blocker B; the corpus contains 15 such cases."""

    payload = _parse_payload()
    payload["explicit_facts"] = [
        {
            "fact_id": "f_angle",
            "kind": "scalar",
            "semantic_key": "angle",
            "raw_value": "30",
            "raw_unit": "deg",
            "subject_id": "incline",
            "segment_id": "seg1",
            "temporal_role": "timeless",
            "direction": "not_applicable",
            "evidence_quote": _ANGLE_QUOTE,
            "relevance": "solver_input",
            "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        }
    ]
    with pytest.raises(ValidationError, match="fact subject must be an actor"):
        TextbookProblemParseV1.model_validate(payload)


def test_recorded_parser_limitation_baseline_parse_is_otherwise_valid() -> None:
    """The baseline differs from the two limitation cases only in those shapes."""

    TextbookProblemParseV1.model_validate(_parse_payload())
