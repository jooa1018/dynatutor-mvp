"""The authority census, as a contract rather than a table.

The census makes three empirical claims — that contexts partition into typed
cohorts, that a cohort is short of a named carrier, and that the shortfall is
what blocks it.  Each claim has a different failure mode, so each has its own
tests here:

* a fingerprint that changed when an identifier changed would invent cohorts;
* a fingerprint that stayed equal when the physics changed would merge them;
* a "blocked on carrier X" read off a count could be neither.

Everything below is synthetic.  No test reads the public archive, and no
fixture carries a case identifier, a family, problem text, or an expected
answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import pytest

from evaluation.phase56_stage7.authority_census import (
    AUTHORITY_CENSUS_VERSION,
    ExpectedClass,
    ProgressRung,
    SourceCarrierCategory,
    available_carriers,
    build_authority_census,
    build_authority_context,
    census_as_dict,
    measure_carrier_counterfactual,
    missing_carriers,
    progress_rung,
    required_carriers,
    rung_index,
    structural_cohort,
)


# ---------------------------------------------------------------------------
# Synthetic contexts.  Plain dictionaries: the census reads a Draft payload, so
# a fixture only has to be shaped like one.
# ---------------------------------------------------------------------------


def _context(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "entities": [
            {"entity_id": "e1", "primitive": "particle"},
            {"entity_id": "e2", "primitive": "incline"},
        ],
        "reference_frames": [],
        "points": [],
        "motion_intervals": [
            {
                "interval_id": "i1",
                "order": 1,
                "start_event_id": "v1",
                "end_event_id": "v2",
            }
        ],
        "events": [
            {"event_id": "v1", "kind": "start"},
            {"event_id": "v2", "kind": "finish"},
        ],
        "geometry": [
            {
                "relation_id": "g1",
                "kind": "slides_on",
                "participant_ids": ["e1", "e2"],
            }
        ],
        "interactions": [],
        "constraints": [],
        "state_conditions": [],
        "assumptions": [],
        "quantities": [
            {
                "quantity_id": "q1",
                "role": "velocity",
                "subject_id": "e1",
                "component": "magnitude",
                "interval_id": "i1",
                "raw_value": 3.0,
            }
        ],
        "queries": [
            {
                "query_id": "y1",
                "shape": "scalar",
                "target": {
                    "role": "acceleration",
                    "subject_id": "e1",
                    "component": "magnitude",
                    "interval_id": "i1",
                },
            }
        ],
    }
    base.update(overrides)
    return base


@dataclass(frozen=True)
class _Result:
    """Just enough of a lane result for the ladder to read."""

    terminal: str
    equation_count: int = 0
    applied_law_ids: tuple[str, ...] = ()
    verified_candidate_count: int = 0
    compiler_status: str | None = None
    solve_terminal: str | None = None


def _rename(context: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """Rewrite every identifier through `mapping`, leaving structure alone."""

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: walk(value) for key, value in node.items()}
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, str):
            return mapping.get(node, node)
        return node

    return walk(context)


# ---------------------------------------------------------------------------
# Fingerprint invariance — the same physics must stay one cohort
# ---------------------------------------------------------------------------


def test_a_context_fingerprints_identically_to_itself() -> None:
    assert structural_cohort(_context()).digest == structural_cohort(_context()).digest


def test_renaming_every_identifier_does_not_move_the_cohort() -> None:
    original = _context()
    renamed = _rename(
        original,
        {
            "e1": "body_alpha",
            "e2": "ramp_beta",
            "i1": "phase_one",
            "v1": "t_zero",
            "v2": "t_end",
            "g1": "rel_77",
            "q1": "fact_42",
            "y1": "ask_1",
        },
    )

    assert structural_cohort(renamed).digest == structural_cohort(original).digest


def test_reordering_every_array_does_not_move_the_cohort() -> None:
    original = _context()
    reordered = dict(original)
    reordered["entities"] = list(reversed(original["entities"]))
    reordered["events"] = list(reversed(original["events"]))
    reordered["quantities"] = list(reversed(original["quantities"]))

    assert structural_cohort(reordered).digest == structural_cohort(original).digest


def test_swapping_a_symmetric_relations_participants_does_not_move_the_cohort() -> None:
    original = _context(
        entities=[
            {"entity_id": "e1", "primitive": "particle"},
            {"entity_id": "e2", "primitive": "rigid_body"},
        ],
        geometry=[
            {
                "relation_id": "g1",
                "kind": "topology_connects",
                "participant_ids": ["e1", "e2"],
            }
        ],
    )
    swapped = _context(
        entities=[
            {"entity_id": "e1", "primitive": "particle"},
            {"entity_id": "e2", "primitive": "rigid_body"},
        ],
        geometry=[
            {
                "relation_id": "g1",
                "kind": "topology_connects",
                "participant_ids": ["e2", "e1"],
            }
        ],
    )

    assert structural_cohort(swapped).digest == structural_cohort(original).digest


def test_swapping_a_directional_relations_participants_does_move_the_cohort() -> None:
    # `slides_on` is not symmetric: a block on a ramp is not a ramp on a block.
    original = _context()
    swapped = _context(
        geometry=[
            {
                "relation_id": "g1",
                "kind": "slides_on",
                "participant_ids": ["e2", "e1"],
            }
        ]
    )

    assert structural_cohort(swapped).digest != structural_cohort(original).digest


def test_a_different_numeric_value_does_not_move_the_cohort() -> None:
    original = _context()
    rescaled = _context(
        quantities=[dict(original["quantities"][0], raw_value=91.7, raw_unit="km/h")]
    )

    assert structural_cohort(rescaled).digest == structural_cohort(original).digest


def test_an_equivalent_unit_does_not_move_the_cohort() -> None:
    metres = _context(
        quantities=[dict(_context()["quantities"][0], raw_value=1.0, raw_unit="m/s")]
    )
    kilometres = _context(
        quantities=[dict(_context()["quantities"][0], raw_value=3.6, raw_unit="km/h")]
    )

    assert structural_cohort(metres).digest == structural_cohort(kilometres).digest


def test_a_field_the_census_does_not_read_does_not_move_the_cohort() -> None:
    # Labels, families and provenance are not physics and must not partition.
    original = _context()
    labelled = _rename(original, {})
    labelled["entities"] = [
        dict(item, label="블록", aliases=["A"]) for item in original["entities"]
    ]

    assert structural_cohort(labelled).digest == structural_cohort(original).digest


# ---------------------------------------------------------------------------
# Fingerprint sensitivity — different physics must be different cohorts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "mutated"),
    [
        (
            "query role",
            _context(
                queries=[
                    {
                        "query_id": "y1",
                        "shape": "scalar",
                        "target": {
                            "role": "force",
                            "subject_id": "e1",
                            "component": "magnitude",
                            "interval_id": "i1",
                        },
                    }
                ]
            ),
        ),
        (
            "query component",
            _context(
                queries=[
                    {
                        "query_id": "y1",
                        "shape": "scalar",
                        "target": {
                            "role": "acceleration",
                            "subject_id": "e1",
                            "component": "tangential",
                            "interval_id": "i1",
                        },
                    }
                ]
            ),
        ),
        (
            "query objective",
            _context(
                queries=[
                    {
                        "query_id": "y1",
                        "shape": "scalar",
                        "objective": "minimum",
                        "target": {
                            "role": "acceleration",
                            "subject_id": "e1",
                            "component": "magnitude",
                            "interval_id": "i1",
                        },
                    }
                ]
            ),
        ),
        (
            "event scope",
            _context(
                queries=[
                    {
                        "query_id": "y1",
                        "shape": "scalar",
                        "target": {
                            "role": "acceleration",
                            "subject_id": "e1",
                            "component": "magnitude",
                            "event_id": "v2",
                        },
                    }
                ]
            ),
        ),
        (
            "interval scope",
            _context(
                motion_intervals=[
                    {"interval_id": "i1", "order": 1, "start_event_id": "v1"}
                ]
            ),
        ),
        (
            "topology",
            _context(
                geometry=[
                    {
                        "relation_id": "g1",
                        "kind": "rolls_on",
                        "participant_ids": ["e1", "e2"],
                    }
                ]
            ),
        ),
        (
            "contact regime",
            _context(
                interactions=[
                    {
                        "interaction_id": "x1",
                        "kind": "contact",
                        "participant_ids": ["e1", "e2"],
                        "contact_side": "inward",
                    }
                ]
            ),
        ),
        (
            "quantity role",
            _context(
                quantities=[
                    dict(_context()["quantities"][0], role="force"),
                ]
            ),
        ),
        (
            "direction carrier",
            _context(
                quantities=[
                    dict(
                        _context()["quantities"][0],
                        direction={"kind": "semantic", "name": "downward"},
                    ),
                ]
            ),
        ),
        (
            "frame carrier",
            _context(
                reference_frames=[
                    {
                        "frame_id": "f1",
                        "frame_type": "tangential_normal",
                        "axes": [{"axis": "t"}],
                    }
                ]
            ),
        ),
        (
            "endpoint carrier",
            _context(
                state_conditions=[
                    {
                        "state_condition_id": "s1",
                        "kind": "boundary",
                        "state": "at_rest",
                        "subject_id": "e1",
                        "event_id": "v2",
                    }
                ]
            ),
        ),
        (
            "assumption carrier",
            _context(
                assumptions=[
                    {
                        "assumption_id": "a1",
                        "kind": "pure_rolling",
                        "subject_id": "e1",
                        "disposition": "accepted",
                    }
                ]
            ),
        ),
        (
            "entity primitive",
            _context(
                entities=[
                    {"entity_id": "e1", "primitive": "rigid_body"},
                    {"entity_id": "e2", "primitive": "incline"},
                ]
            ),
        ),
    ],
)
def test_a_physics_change_moves_the_cohort(description: str, mutated: Any) -> None:
    assert structural_cohort(mutated).digest != structural_cohort(_context()).digest, (
        f"{description} did not partition"
    )


def test_the_cohort_tokens_carry_no_identifier_label_or_value() -> None:
    tokens = structural_cohort(_context()).tokens
    joined = " ".join(tokens)

    for forbidden in ("e1", "e2", "i1", "v1", "v2", "g1", "q1", "y1", "3.0", "블록"):
        assert forbidden not in joined


def test_a_context_with_no_draft_at_all_is_counted_rather_than_dropped() -> None:
    # A rejected projection carries no Draft.  It is a real structural class.
    cohort = structural_cohort(None)

    assert cohort.digest
    assert "query=absent" in cohort.tokens
    assert required_carriers(None) == ()


# ---------------------------------------------------------------------------
# Carriers
# ---------------------------------------------------------------------------


def test_an_axis_component_query_with_no_frame_requires_a_reference_frame() -> None:
    context = _context(
        queries=[
            {
                "query_id": "y1",
                "shape": "scalar",
                "target": {
                    "role": "velocity",
                    "subject_id": "e1",
                    "component": "x",
                    "interval_id": "i1",
                },
            }
        ]
    )

    assert SourceCarrierCategory.reference_frame in required_carriers(context)
    assert SourceCarrierCategory.reference_frame in missing_carriers(context)


def test_a_stated_frame_satisfies_the_axis_component_query() -> None:
    context = _context(
        reference_frames=[
            {
                "frame_id": "f1",
                "frame_type": "cartesian_2d",
                "axes": [{"axis": "x", "direction": {"kind": "axis", "axis": "x"}}],
            }
        ],
        queries=[
            {
                "query_id": "y1",
                "shape": "scalar",
                "target": {
                    "role": "velocity",
                    "subject_id": "e1",
                    "component": "x",
                    "interval_id": "i1",
                },
            }
        ],
    )

    assert SourceCarrierCategory.reference_frame in available_carriers(context)
    assert SourceCarrierCategory.reference_frame not in missing_carriers(context)


def test_a_magnitude_query_does_not_require_a_frame() -> None:
    # The default fixture asks for a magnitude, which names no axis.
    assert SourceCarrierCategory.reference_frame not in required_carriers(_context())


def test_an_angle_with_neither_frame_nor_angle_relation_needs_a_datum() -> None:
    context = _context(
        quantities=[
            {
                "quantity_id": "q1",
                "role": "angle",
                "subject_id": "e2",
                "component": "magnitude",
                "raw_value": 30.0,
            }
        ]
    )

    assert SourceCarrierCategory.angle_reference_datum in missing_carriers(context)


def test_an_angle_relation_naming_two_participants_supplies_the_datum() -> None:
    context = _context(
        geometry=[
            {
                "relation_id": "g1",
                "kind": "angle",
                "participant_ids": ["e1", "e2"],
            }
        ],
        quantities=[
            {
                "quantity_id": "q1",
                "role": "angle",
                "subject_id": "e2",
                "component": "magnitude",
                "raw_value": 30.0,
            }
        ],
    )

    assert SourceCarrierCategory.angle_reference_datum not in required_carriers(context)


def test_a_world_direction_on_a_slope_needs_a_motion_sense() -> None:
    context = _context(
        quantities=[
            dict(
                _context()["quantities"][0],
                direction={"kind": "semantic", "name": "downward"},
            )
        ]
    )

    assert SourceCarrierCategory.motion_sense in missing_carriers(context)


def test_a_direction_bound_to_a_stated_frame_axis_is_a_motion_sense() -> None:
    context = _context(
        reference_frames=[
            {
                "frame_id": "f1",
                "frame_type": "tangential_normal",
                "axes": [{"axis": "t", "direction": {"kind": "axis", "axis": "t"}}],
            }
        ],
        quantities=[
            dict(
                _context()["quantities"][0],
                direction={
                    "kind": "axis",
                    "name": "positive",
                    "frame_id": "f1",
                    "axis": "t",
                    "sign": 1,
                },
            )
        ],
    )

    assert SourceCarrierCategory.motion_sense in available_carriers(context)
    assert SourceCarrierCategory.motion_sense not in missing_carriers(context)


def test_a_world_direction_with_no_contact_topology_is_not_a_motion_sense_gap() -> None:
    context = _context(
        geometry=[],
        quantities=[
            dict(
                _context()["quantities"][0],
                direction={"kind": "semantic", "name": "downward"},
            )
        ],
    )

    assert SourceCarrierCategory.motion_sense not in required_carriers(context)


def test_contact_with_no_stated_side_on_a_one_sided_topology_needs_the_side() -> None:
    context = _context(
        interactions=[
            {
                "interaction_id": "x1",
                "kind": "contact",
                "participant_ids": ["e1", "e2"],
            }
        ]
    )

    assert SourceCarrierCategory.contact_side in missing_carriers(context)


def test_a_stated_contact_side_satisfies_it() -> None:
    context = _context(
        interactions=[
            {
                "interaction_id": "x1",
                "kind": "contact",
                "participant_ids": ["e1", "e2"],
                "contact_side": "inward",
            }
        ]
    )

    assert SourceCarrierCategory.contact_side in available_carriers(context)
    assert SourceCarrierCategory.contact_side not in missing_carriers(context)


def test_a_query_at_an_undefined_endpoint_needs_the_endpoint_condition() -> None:
    context = _context(
        queries=[
            {
                "query_id": "y1",
                "shape": "scalar",
                "target": {
                    "role": "velocity",
                    "subject_id": "e1",
                    "component": "magnitude",
                    "event_id": "v2",
                },
            }
        ]
    )

    assert SourceCarrierCategory.endpoint_condition in missing_carriers(context)


def test_a_condition_stated_at_that_event_satisfies_the_endpoint() -> None:
    context = _context(
        state_conditions=[
            {
                "state_condition_id": "s1",
                "kind": "boundary",
                "state": "at_rest",
                "subject_id": "e1",
                "event_id": "v2",
            }
        ],
        queries=[
            {
                "query_id": "y1",
                "shape": "scalar",
                "target": {
                    "role": "velocity",
                    "subject_id": "e1",
                    "component": "magnitude",
                    "event_id": "v2",
                },
            }
        ],
    )

    assert SourceCarrierCategory.endpoint_condition not in missing_carriers(context)


def test_a_query_at_a_named_endpoint_does_not_need_the_carrier() -> None:
    # `comes_to_rest` says what holds there; `finish` only says when.
    context = _context(
        events=[
            {"event_id": "v1", "kind": "start"},
            {"event_id": "v2", "kind": "comes_to_rest"},
        ],
        queries=[
            {
                "query_id": "y1",
                "shape": "scalar",
                "target": {
                    "role": "velocity",
                    "subject_id": "e1",
                    "component": "magnitude",
                    "event_id": "v2",
                },
            }
        ],
    )

    assert SourceCarrierCategory.endpoint_condition not in required_carriers(context)


def test_a_rolling_topology_with_no_constraint_or_assumption_needs_authority() -> None:
    context = _context(
        geometry=[
            {
                "relation_id": "g1",
                "kind": "rolls_on",
                "participant_ids": ["e1", "e2"],
            }
        ]
    )

    assert SourceCarrierCategory.constraint_authority in missing_carriers(context)


def test_an_approved_assumption_states_the_rolling_constraint() -> None:
    context = _context(
        geometry=[
            {
                "relation_id": "g1",
                "kind": "rolls_on",
                "participant_ids": ["e1", "e2"],
            }
        ],
        assumptions=[
            {
                "assumption_id": "a1",
                "kind": "pure_rolling",
                "subject_id": "e1",
                "disposition": "accepted",
            }
        ],
    )

    assert SourceCarrierCategory.constraint_authority not in required_carriers(context)


def test_a_force_query_on_a_system_needs_the_interaction_named() -> None:
    context = _context(
        entities=[
            {"entity_id": "e1", "primitive": "system"},
            {"entity_id": "e2", "primitive": "incline"},
        ],
        queries=[
            {
                "query_id": "y1",
                "shape": "scalar",
                "target": {
                    "role": "force",
                    "subject_id": "e1",
                    "component": "magnitude",
                    "interval_id": "i1",
                },
            }
        ],
    )

    assert SourceCarrierCategory.interaction_target in missing_carriers(context)


def test_a_negative_value_beside_a_stated_direction_needs_an_encoding() -> None:
    context = _context(
        quantities=[
            dict(
                _context()["quantities"][0],
                raw_value=-4.0,
                direction={"kind": "semantic", "name": "upward"},
            )
        ]
    )

    assert SourceCarrierCategory.signed_scalar_encoding in missing_carriers(context)


def test_a_negative_value_with_no_direction_is_just_a_number() -> None:
    context = _context(
        quantities=[dict(_context()["quantities"][0], raw_value=-4.0)]
    )

    assert SourceCarrierCategory.signed_scalar_encoding not in required_carriers(context)


# ---------------------------------------------------------------------------
# The ladder: "the emitter fired" is not "the problem is solved"
# ---------------------------------------------------------------------------


def test_the_ladder_is_strictly_ordered() -> None:
    ladder = [
        ProgressRung.projection_rejected,
        ProgressRung.law_not_emitted,
        ProgressRung.law_emitted_graph_underdetermined,
        ProgressRung.graph_determined_solve_failed,
        ProgressRung.solved_unverified,
        ProgressRung.solved_and_verified,
    ]

    indices = [rung_index(rung) for rung in ladder]

    assert indices == sorted(indices)
    assert len(set(indices)) == len(indices)


def test_a_compiler_stop_with_no_equation_is_law_not_emitted() -> None:
    result = _Result(terminal="compiler_failure", equation_count=0)

    assert progress_rung(result) is ProgressRung.law_not_emitted


def test_a_compiler_stop_with_equations_is_not_reported_as_a_solve() -> None:
    result = _Result(
        terminal="compiler_failure",
        equation_count=3,
        applied_law_ids=("particle_newton_second",),
    )

    rung = progress_rung(result)

    assert rung is ProgressRung.law_emitted_graph_underdetermined
    assert rung is not ProgressRung.solved_and_verified
    assert rung_index(rung) < rung_index(ProgressRung.solved_and_verified)


def test_a_solve_without_a_verified_candidate_is_not_a_verified_solve() -> None:
    assert (
        progress_rung(_Result(terminal="solved", verified_candidate_count=0))
        is ProgressRung.solved_unverified
    )
    assert (
        progress_rung(_Result(terminal="solved", verified_candidate_count=1))
        is ProgressRung.solved_and_verified
    )


def test_a_neutral_terminal_is_not_a_pipeline_failure() -> None:
    for terminal in (
        "needs_figure",
        "needs_confirmation",
        "insufficient_information",
        "verified_unsupported",
        "compiler_unsupported",
    ):
        assert (
            progress_rung(_Result(terminal=terminal))
            is ProgressRung.blocked_neutral_terminal
        )


# ---------------------------------------------------------------------------
# The counterfactual instrument
# ---------------------------------------------------------------------------


def test_a_carrier_that_only_makes_an_emitter_fire_is_not_a_closure() -> None:
    counterfactual = measure_carrier_counterfactual(
        carrier=SourceCarrierCategory.reference_frame,
        baseline_result=_Result(terminal="compiler_failure"),
        augmented_result=_Result(
            terminal="compiler_failure",
            equation_count=2,
            applied_law_ids=("particle_newton_second",),
        ),
    )

    assert counterfactual.unblocked is True
    assert counterfactual.closes is False


def test_a_carrier_that_closes_the_problem_reports_both() -> None:
    counterfactual = measure_carrier_counterfactual(
        carrier=SourceCarrierCategory.contact_side,
        baseline_result=_Result(terminal="compiler_failure"),
        augmented_result=_Result(terminal="solved", verified_candidate_count=1),
    )

    assert counterfactual.unblocked is True
    assert counterfactual.closes is True


def test_a_carrier_that_changes_nothing_reports_no_unblock() -> None:
    counterfactual = measure_carrier_counterfactual(
        carrier=SourceCarrierCategory.endpoint_condition,
        baseline_result=_Result(terminal="compiler_failure"),
        augmented_result=_Result(terminal="compiler_failure"),
    )

    assert counterfactual.unblocked is False
    assert counterfactual.closes is False
    assert counterfactual.regressed is False


def test_a_carrier_that_moves_a_context_backwards_is_a_defect() -> None:
    counterfactual = measure_carrier_counterfactual(
        carrier=SourceCarrierCategory.motion_sense,
        baseline_result=_Result(terminal="solved", verified_candidate_count=1),
        augmented_result=_Result(terminal="compiler_failure"),
    )

    assert counterfactual.regressed is True
    assert counterfactual.unblocked is False


# ---------------------------------------------------------------------------
# The aggregate
# ---------------------------------------------------------------------------


def _row(**kwargs: Any):
    context = kwargs.pop("context", _context())
    result = kwargs.pop("result", _Result(terminal="compiler_failure"))
    return build_authority_context(context, result, **kwargs)


def test_a_solved_supported_context_is_neither_blocked_nor_a_candidate() -> None:
    row = _row(
        result=_Result(terminal="solved", verified_candidate_count=1),
        expected_class=ExpectedClass.supported,
    )

    assert row.solved is True
    assert row.authority_blocked is False
    assert row.closure_candidate is False


def test_an_unsolved_supported_context_short_of_a_carrier_is_blocked() -> None:
    row = _row(
        context=_context(
            interactions=[
                {
                    "interaction_id": "x1",
                    "kind": "contact",
                    "participant_ids": ["e1", "e2"],
                }
            ]
        ),
        expected_class=ExpectedClass.supported,
    )

    assert row.authority_blocked is True
    assert row.closure_candidate is False


def test_an_unsolved_supported_context_short_of_nothing_is_a_candidate() -> None:
    row = _row(expected_class=ExpectedClass.supported)

    assert row.missing_carriers == ()
    assert row.closure_candidate is True
    assert row.authority_blocked is False


def test_an_unsolved_deferred_context_is_neither() -> None:
    row = _row(expected_class=ExpectedClass.deferred)

    assert row.authority_blocked is False
    assert row.closure_candidate is False


def test_a_solved_context_short_of_a_carrier_is_a_negative_control() -> None:
    # The census publishes how often its own reading over-fires rather than
    # tuning the reading until the count is zero.
    row = _row(
        context=_context(
            interactions=[
                {
                    "interaction_id": "x1",
                    "kind": "contact",
                    "participant_ids": ["e1", "e2"],
                }
            ]
        ),
        result=_Result(terminal="solved", verified_candidate_count=1),
        expected_class=ExpectedClass.supported,
    )

    assert row.carrier_hypothesis_false_positive is True

    census = build_authority_census([row])

    assert census.carrier_hypothesis_false_positive_count == 1


def test_contexts_that_share_a_structure_share_a_cohort() -> None:
    rows = [
        _row(expected_class=ExpectedClass.supported),
        _row(
            context=_rename(_context(), {"e1": "other", "q1": "renamed"}),
            expected_class=ExpectedClass.supported,
        ),
    ]

    census = build_authority_census(rows)

    assert census.cohort_count == 1
    assert census.cohorts[0].population == 2


def test_the_aggregate_totals_agree_with_its_rows() -> None:
    rows = [
        _row(
            result=_Result(terminal="solved", verified_candidate_count=1),
            expected_class=ExpectedClass.supported,
        ),
        _row(expected_class=ExpectedClass.supported),
        _row(
            context=_context(
                geometry=[
                    {
                        "relation_id": "g1",
                        "kind": "rolls_on",
                        "participant_ids": ["e1", "e2"],
                    }
                ]
            ),
            expected_class=ExpectedClass.supported,
        ),
        _row(
            result=_Result(terminal="verified_unsupported"),
            expected_class=ExpectedClass.deferred,
        ),
    ]

    census = build_authority_census(rows)

    assert census.context_count == 4
    assert census.supported_expected == 3
    assert census.supported_solved == 1
    assert census.supported_unsolved == 2
    assert census.deferred == 1
    assert census.closure_candidate_count == 1
    assert census.authority_blocked_count == 1
    assert (
        census.closure_candidate_count + census.authority_blocked_count
        == census.supported_unsolved
    )
    assert sum(cohort.population for cohort in census.cohorts) == 4


def test_the_census_digest_is_deterministic_and_content_sensitive() -> None:
    first = build_authority_census([_row(expected_class=ExpectedClass.supported)])
    same = build_authority_census([_row(expected_class=ExpectedClass.supported)])
    different = build_authority_census([_row(expected_class=ExpectedClass.deferred)])

    assert first.digest == same.digest
    assert first.digest != different.digest


def test_row_order_does_not_change_the_census() -> None:
    supported = _row(expected_class=ExpectedClass.supported)
    deferred = _row(
        result=_Result(terminal="verified_unsupported"),
        expected_class=ExpectedClass.deferred,
    )

    assert (
        build_authority_census([supported, deferred]).digest
        == build_authority_census([deferred, supported]).digest
    )


def test_the_published_census_carries_no_case_material() -> None:
    from evaluation.phase56_stage7.redaction import assert_privacy_safe_artifact

    census = build_authority_census(
        [
            _row(expected_class=ExpectedClass.supported),
            _row(
                result=_Result(terminal="solved", verified_candidate_count=1),
                expected_class=ExpectedClass.supported,
            ),
        ]
    )
    payload = census_as_dict(census)

    assert_privacy_safe_artifact(payload)
    text = repr(payload)
    for forbidden in (
        "case_id",
        "problem_text",
        "expected_answer",
        "evidence_quote",
        "family",
        "tolerance",
        "블록",
    ):
        assert forbidden not in text
    assert payload["version"] == AUTHORITY_CENSUS_VERSION


def test_no_census_field_can_hold_a_free_text_source_string() -> None:
    from evaluation.phase56_stage7.authority_census import (
        AuthorityCensusV1,
        AuthorityContextV1,
    )

    forbidden_parts = (
        "problem",
        "problem_text",
        "raw_text",
        "quote",
        "evidence",
        "answer",
        "case_id",
        "family",
        "split",
        "label",
        "tolerance",
    )
    for model in (AuthorityCensusV1, AuthorityContextV1):
        for name in model.model_fields:
            for part in forbidden_parts:
                assert part not in name, f"{model.__name__}.{name} could hold {part}"


def test_an_empty_population_is_a_census_rather_than_an_error() -> None:
    census = build_authority_census([])

    assert census.context_count == 0
    assert census.cohort_count == 0
    assert census.closure_candidate_count == 0


# ---------------------------------------------------------------------------
# The gate wiring
# ---------------------------------------------------------------------------


def test_the_offline_gate_publishes_the_census_as_a_diagnostic_section() -> None:
    from pathlib import Path

    gate = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "tools"
        / "run_phase56_stage7_offline_gate.py"
    )
    source = gate.read_text(encoding="utf-8")

    assert '"authority_census": authority_census_section' in source
    # Diagnostic, never a gate: it must not appear in the strict gate list.
    assert "authority_census_pass" not in source
    # Runtime before gold, in the section itself.
    census_body = source.split("def _authority_census_section", 1)[1].split(
        "\ndef ", 1
    )[0]
    assert census_body.index("run_lane_b_case") < census_body.index(
        "scope_adjusted_expected_terminal"
    )


def test_the_census_section_reports_not_run_without_an_archive() -> None:
    import importlib.util
    import sys
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "tools"
        / "run_phase56_stage7_offline_gate.py"
    )
    spec = importlib.util.spec_from_file_location("stage7_offline_gate_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["stage7_offline_gate_probe"] = module
    try:
        spec.loader.exec_module(module)
        section = module._authority_census_section(None)
    finally:
        sys.modules.pop("stage7_offline_gate_probe", None)

    # A run without the archive must never report a measured census.
    assert section == {"executed": False, "disposition": "NOT_RUN"}
