"""A declared observer frame is precisely unsupported, not underdetermined.

When a source declares an entity that *is* a reference frame, it is stating that
the question is posed relative to a moving observer.  Every law profile in the
catalogue rejects a frame that translates with an entity or rotates about a
point, so no reusable law can relate a kinematic quantity across that observer.

Reporting "underdetermined" there claims a missing equation when what is missing
is a whole model.  The precise terminal is the honest one, and it is decided
from the typed IR alone: the entity primitive and the query's own role.  No
family, case ID, expected system type, expected terminal, or answer is read.
"""

from __future__ import annotations

import pytest

from engine.mechanics.compiler.contracts import CompilerIssueCode, CompilerStatus

from test_phase56_mechanics_compiler import (
    ACCELERATION,
    LENGTH,
    MASS,
    VELOCITY,
    compile_mechanics_ir,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
)


def _observer_payload(
    *,
    query_role: str = "velocity",
    with_observer: bool = True,
    modelled: bool = True,
    at_rest: bool = False,
) -> dict[str, object]:
    """A one-unknown kinematic problem beside a declared observer entity.

    ``modelled`` decides whether the typed model refers to the observer again —
    here by carrying the observer's own velocity, which is how a source states
    that the observer moves.  ``at_rest`` instead states that it does not.
    """

    payload = _single_unknown_payload([])
    payload["entities"] = [
        payload["entities"][0],
        *(
            [
                {
                    "entity_id": "observerFrame",
                    "primitive": "reference_frame",
                    "label": "observer",
                    "aliases": [],
                    "component_of_entity_id": None,
                    "evidence_refs": [],
                    "model_confidence": None,
                }
            ]
            if with_observer
            else []
        ),
    ]
    dimension = {"velocity": VELOCITY, "acceleration": ACCELERATION, "mass": MASS}.get(
        query_role, LENGTH
    )
    payload["symbols"] = [_symbol("target", "targetQ", dimension)]
    payload["quantities"] = [
        _quantity("targetQ", "target", query_role, "bodyA", dimension)
    ]
    if with_observer and (modelled or at_rest):
        payload["symbols"].append(_symbol("observerV", "observerQ", VELOCITY))
        payload["quantities"].append(
            _quantity(
                "observerQ",
                "observerV",
                "velocity",
                "observerFrame",
                VELOCITY,
                value=0.0 if at_rest else 4.0,
                unit="m/s",
                evidence_refs=("observerEvidence",),
            )
        )
        payload["source_evidence"] = [
            {
                "kind": "text",
                "evidence_id": "observerEvidence",
                "quote": "The observer's own motion is stated by the source.",
                "source_span": {"start": 0, "end": 49},
                "quantity_span": None,
                "occurrence_index": 0,
            }
        ]
    if with_observer and at_rest:
        payload["state_conditions"] = [
            {
                "state_condition_id": "observerRest",
                "kind": "motion",
                "state": "at_rest",
                "subject_id": "observerFrame",
                "interval_id": None,
                "event_id": None,
                "expression": None,
                "quantity_ids": ["observerQ"],
                "evidence_refs": ["observerEvidence"],
            }
        ]
    payload["queries"][0]["target"].update(
        {"role": query_role, "target_quantity_id": "targetQ"}
    )
    payload["queries"][0]["output_dimension"] = dimension.model_dump(mode="json")
    payload["queries"][0]["output_unit"] = {
        "velocity": "m/s",
        "acceleration": "m/s^2",
        "mass": "kg",
    }.get(query_role, "m")
    return payload


def _codes(result) -> set[str]:
    return {item.code.value for item in result.issues}


# --------------------------------------------------------------------------
# The precise terminal
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query_role",
    ["position", "displacement", "velocity", "speed", "acceleration"],
)
def test_a_kinematic_query_under_an_observer_frame_is_precisely_unsupported(
    query_role,
) -> None:
    result = compile_mechanics_ir(_ir(_observer_payload(query_role=query_role)))
    assert result.status is CompilerStatus.unsupported
    assert CompilerIssueCode.requires_specialized_model.value in _codes(result)


def test_the_same_problem_without_an_observer_is_not_deferred_for_this_reason() -> None:
    result = compile_mechanics_ir(
        _ir(_observer_payload(query_role="velocity", with_observer=False))
    )
    assert result.status is not CompilerStatus.unsupported


def test_a_frame_bound_query_stays_supported_beside_an_observer_entity() -> None:
    # The polar and plane-rigid families declare a coordinate observer *and* a
    # typed frame the laws work in.  Those are supported, and deferring them
    # would trade a solvable problem for a refusal.
    from test_phase56_mechanics_polar_kinematics_same_fixture_parity import (
        BASE,
        _payload,
    )

    payload = _payload(BASE)
    assert any(
        item["primitive"] == "reference_frame" for item in payload["entities"]
    )
    assert payload["queries"][0]["target"]["frame_id"] is not None
    result = compile_mechanics_ir(_ir(payload))
    assert CompilerIssueCode.requires_specialized_model.value not in _codes(result)


# --------------------------------------------------------------------------
# Negative controls: two observer declarations that mean nothing relative
# --------------------------------------------------------------------------


def test_an_observer_the_model_never_refers_to_again_is_not_deferred() -> None:
    # A source can name something without relating it to anything.  Claiming a
    # specialized model on the strength of a dangling declaration would refuse a
    # problem the catalogue may well close, and would permanently close the door
    # on ever solving it.
    result = compile_mechanics_ir(_ir(_observer_payload(modelled=False)))
    assert CompilerIssueCode.requires_specialized_model.value not in _codes(result)


def test_an_observer_the_source_states_is_at_rest_is_not_deferred() -> None:
    # An observer that does not move describes the same motion the ground frame
    # does, so no specialized model is needed to relate anything across it.
    result = compile_mechanics_ir(_ir(_observer_payload(at_rest=True)))
    assert CompilerIssueCode.requires_specialized_model.value not in _codes(result)


def test_a_resting_observer_is_still_part_of_the_model() -> None:
    # The exemption must come from the declared rest, not from the observer
    # having dropped out of the model: the same wiring without the rest defers.
    from engine.mechanics.compiler.compiler import _entity_is_modelled

    ir = _ir(_observer_payload(at_rest=True))
    assert _entity_is_modelled(ir, "observerFrame")
    moving = compile_mechanics_ir(_ir(_observer_payload(modelled=True)))
    assert CompilerIssueCode.requires_specialized_model.value in _codes(moving)


def test_a_dangling_observer_is_not_reported_as_modelled() -> None:
    from engine.mechanics.compiler.compiler import _entity_is_modelled

    assert not _entity_is_modelled(_ir(_observer_payload(modelled=False)), "observerFrame")


def test_being_modelled_is_decided_by_the_whole_typed_record_not_a_field_list() -> None:
    # The scan walks each typed record's own fields, so an entity referenced
    # through a nested origin — a field no hand-kept list would have to name —
    # still counts as modelled.
    from engine.mechanics.compiler.compiler import _entity_is_modelled

    payload = _observer_payload(modelled=False)
    payload["reference_frames"] = [
        {
            "frame_id": "observerBound",
            "frame_type": "cartesian_1d",
            "origin": {"kind": "entity", "entity_id": "observerFrame"},
            "axes": [
                {
                    "axis": "x",
                    "direction": {
                        "kind": "axis",
                        "frame_id": "observerBound",
                        "axis": "x",
                        "sign": 1,
                    },
                }
            ],
            "parent_frame_id": None,
            "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": [],
        }
    ]
    assert _entity_is_modelled(_ir(payload), "observerFrame")


def test_a_non_kinematic_query_is_not_deferred_by_an_observer_frame() -> None:
    # An observer changes how motion is described; it does not change a mass.
    result = compile_mechanics_ir(_ir(_observer_payload(query_role="mass")))
    assert CompilerIssueCode.requires_specialized_model.value not in _codes(result)


def test_the_issue_names_the_observer_and_the_query_role_only() -> None:
    result = compile_mechanics_ir(_ir(_observer_payload()))
    issue = next(
        item
        for item in result.issues
        if item.code is CompilerIssueCode.requires_specialized_model
    )
    assert issue.referenced_id == "observerFrame"
    assert issue.path.endswith(".target.role")
    assert "underdetermined" not in issue.message


def test_the_deferral_replaces_underdetermined_rather_than_joining_it() -> None:
    result = compile_mechanics_ir(_ir(_observer_payload()))
    assert CompilerIssueCode.underdetermined.value not in _codes(result)


def test_the_decision_is_deterministic() -> None:
    first = compile_mechanics_ir(_ir(_observer_payload()))
    second = compile_mechanics_ir(_ir(_observer_payload()))
    assert first.status is second.status
    assert _codes(first) == _codes(second)


def test_every_law_profile_rejects_a_frame_that_moves_with_a_body() -> None:
    # The deferral is honest only because no catalogue law accepts such a
    # frame.  This is the source-level guarantee that makes it so.
    from pathlib import Path

    source = Path("engine/mechanics/laws/core.py").read_text(encoding="utf-8")
    assert "translating_with_entity_id is not None" in source
    assert "or frame.translating_with_entity_id is not None" in source
