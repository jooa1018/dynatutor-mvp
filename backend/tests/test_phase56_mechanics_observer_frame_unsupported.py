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
) -> dict[str, object]:
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
