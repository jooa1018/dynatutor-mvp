"""Profile-isolated feasibility: independent runs, honest zeros, no first-wins.

The instrument under test measures every applicable (profile, context) pair
by planning and applying the **selected profile alone** against the pristine
projected Draft and running the full lane from there.  These controls pin
what the previous instrument could not state: an unimplemented profile is
``profile_not_implemented`` — not measured, never a "verified yield 0" — a
second applicable profile in a context is measured independently of the
closure's first-wins winner, declaration order changes nothing anywhere,
and ``compiler_unsupported_reachable`` exists only on the exact typed
compiler issue codes of the closed precise-unsupported whitelist.

Positive controls are real end-to-end paths (projection → authority →
selected transaction → event derivation → validation → normalization → IR
authorization → compiler → solver → independent verification) for every
status class an implemented profile can reach at this head:
``verified_solve_reachable`` (the evidenced-extremum shape, solved and
verified — see ``test_phase56_stage7_extremum_boundary_solve.py``),
``verified_deferred_reachable``, ``compiler_no_equation``,
``profile_transaction_rejected``, ``profile_plan_not_formable``, and the
``profile_not_implemented`` distinction.  The classes no implemented
profile can currently reach — ``verification_rejected`` and
``solver_rejected`` (the extremum waiver closed the one shape that used to
stop at the solver's door, and no implemented profile produces another
solver-reaching graph), ``compiler_underdetermined`` (every current law
chain emits whole or not at all, so a pruned component is closed or
empty), and ``compiler_unsupported_reachable`` (no implemented profile's
shape coexists with a specialized-model refusal) — are covered at the
classifier level only and are documented as such; hand-constructed
LaneBResult objects are used **only** to unit-cover the decision tree,
never to claim a pipeline path exists.

Fixtures are independently authored.  Nothing reads a case ID, family,
split, expected terminal, or expected answer in any path under test.
"""

from __future__ import annotations

import hashlib
import random

import pytest

from evaluation.phase56_stage7 import complete_profile as complete_profile_module
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    ApplicationOutcome,
    IMPLEMENTED_PROFILE_IDS,
    ProfileApplication,
    close_projected_draft,
    profile_has_transaction,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_authority import (
    build_lane_b_authority_bundle,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBResult,
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case_with_selected_profile,
)
from evaluation.phase56_stage7.profile_feasibility import (
    NOT_MEASURED_STATUSES,
    PRECISE_UNSUPPORTED_ISSUE_CODES,
    ProfileFeasibilityStatus,
    classify_selected_profile_outcome,
    measure_profile_feasibility,
)
from support.phase56_stage7_corpus_fixtures import build_case

# This suite runs the whole Lane B pipeline once per (context, applicable
# profile) — the isolation instrument's point is that each profile is measured
# on its own pristine Draft, so the work cannot be shared.  It costs ~115
# seconds, which is a quarter of the *entire* budget of a fast shard, and the
# fast/slow split exists to keep the fast lane inside that budget.  It belongs
# in the slow lane: 16 node-sharded workers rather than 4 file-sharded ones.
#
# Nothing is skipped by this.  Both lanes run in the same workflow, both assert
# selected == collected in their own partition audit, and the release gate
# requires both.
pytestmark = pytest.mark.slow


# --------------------------------------------------------------------------
# Independently authored fixtures
# --------------------------------------------------------------------------


def _case(index: int, text: str, gold_patch: dict) -> PublicCorpusCaseV1:
    record = build_case(
        index=index,
        split="public_dev",
        family="single_particle_newton",
        future_terminal="accepted",
        with_answer=True,
    )
    record["split"] = PublicSplit.public_dev
    record["problem_text"] = text
    record["problem_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    record["gold"].update(gold_patch)
    return PublicCorpusCaseV1(**record)


def _fact(role, key, value, unit, quote, subject, segment, **kw):
    base = {
        "role": role,
        "semantic_key": key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject,
        "segment_role": segment,
        "event_role": None,
        "temporal_role": "interval",
        "direction": "not_applicable",
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }
    base.update(kw)
    return base


THROW_TEXT = (
    "연습 상황: 돌을 지면 위에서 위로 던진다. 처음 속력은 9 m/s 이고 "
    "처음 높이는 2 m 이다. 공기 저항은 무시한다. 돌이 최고점에 "
    "도달할 때까지 걸리는 시간을 구하시오."
)


def _throw_gold(
    *, apex_quote="최고점에 도달", query=None, extra_entities=(), extra_relations=()
):
    if query is None:
        query = {
            "role": "q1",
            "output_key": "time",
            "subject_role": "stone",
            "segment_role": "fall",
            "component": "magnitude",
            "event_role": "top",
        }
    return {
        "entities": [
            {"role": "stone", "kind": "particle", "label": "돌"},
            {"role": "ground", "kind": "surface", "label": "지면"},
            *extra_entities,
        ],
        "motion_segments": [
            {
                "role": "fall",
                "order": 1,
                "actor_roles": ["stone"],
                "motion_model": "projectile_free_flight",
                "relevance": "target",
                "start_event_role": "go",
                "end_event_role": "top",
            }
        ],
        "events": [
            {
                "role": "go",
                "kind": "release",
                "subject_roles": ["stone"],
                "segment_role": "fall",
                "evidence_quote": None,
            },
            {
                "role": "top",
                "kind": "highest_point",
                "subject_roles": ["stone"],
                "segment_role": "fall",
                "evidence_quote": apex_quote,
            },
        ],
        "explicit_facts": [
            _fact(
                "v0", "initial_velocity", "9", "m/s", "처음 속력은 9 m/s",
                "stone", "fall", event_role="go", temporal_role="initial",
                direction="upward",
            ),
            _fact(
                "h0", "height", "2", "m", "처음 높이는 2 m",
                "stone", "fall", event_role="go", temporal_role="initial",
                direction="upward",
            ),
        ],
        "relations": list(extra_relations),
        "assumption_proposals": [
            {
                "role": "air",
                "kind": "no_air_resistance",
                "subject_role": "stone",
                "segment_role": "fall",
                "supporting_quote": "공기 저항은 무시한다",
                "server_value_only": True,
            },
            {
                "role": "grav",
                "kind": "constant_gravity",
                "subject_role": "stone",
                "segment_role": "fall",
                "supporting_quote": None,
                "server_value_only": True,
            },
        ],
        "queries": [query],
        "answers": [
            {
                "query_role": "q1",
                "numeric": 0.9174,
                "unit": "s",
                "tolerance_abs": 0.01,
                "reference_expression": "v0/g",
            }
        ],
    }


def _throw_case(**kw) -> PublicCorpusCaseV1:
    return _case(31, THROW_TEXT, _throw_gold(**kw))


MAX_HEIGHT_QUERY = {
    "role": "q1",
    "output_key": "max_height",
    "subject_role": "stone",
    "segment_role": "fall",
    "component": "y",
    "event_role": "top",
}
ACCELERATION_QUERY = {
    "role": "q1",
    "output_key": "acceleration",
    "subject_role": "stone",
    "segment_role": "fall",
    "component": "y",
    "event_role": None,
}


RELATIVE_TEXT = (
    "관측 대차가 오른쪽으로 1.4 m/s^2 로 가속한다. "
    "대차에서 보면 부품은 오른쪽으로 0.6 m/s^2 로 가속한다. "
    "지면 기준 부품의 x 방향 가속도를 구하시오."
)


def _relative_gold() -> dict:
    return {
        "entities": [
            {"role": "observer", "kind": "reference_frame", "label": "관측 대차"},
            {"role": "part", "kind": "particle", "label": "부품"},
        ],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["observer", "part"],
                "motion_model": "relative_motion",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": None,
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["observer", "part"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            }
        ],
        "explicit_facts": [
            _fact(
                "carrier", "acceleration", "1.4", "m/s^2",
                "오른쪽으로 1.4 m/s^2", "observer", "motion_1",
                temporal_role=None, direction="right",
            ),
            _fact(
                "relative", "acceleration", "0.6", "m/s^2",
                "오른쪽으로 0.6 m/s^2", "part", "motion_1",
                temporal_role=None, direction="right",
            ),
        ],
        "relations": [
            {
                "role": "observed",
                "kind": "moves_relative_to",
                "participant_roles": ["part", "observer"],
                "segment_role": "motion_1",
            }
        ],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "acceleration",
                "subject_role": "part",
                "segment_role": "motion_1",
                "component": "x",
                "event_role": None,
            }
        ],
        "answers": [
            {
                "query_role": "q1",
                "numeric": 2.0,
                "unit": "m/s^2",
                "tolerance_abs": 0.01,
                "reference_expression": "a1+a2",
            }
        ],
    }


def _relative_case() -> PublicCorpusCaseV1:
    return _case(32, RELATIVE_TEXT, _relative_gold())


RIGID_TEXT = "바퀴가 고정축을 중심으로 5 rad/s 로 회전한다. 바퀴의 회전 주기를 구하시오."


def _rigid_case() -> PublicCorpusCaseV1:
    return _case(
        33,
        RIGID_TEXT,
        {
            "entities": [{"role": "wheel", "kind": "rigid_body", "label": "바퀴"}],
            "motion_segments": [
                {
                    "role": "spin",
                    "order": 1,
                    "actor_roles": ["wheel"],
                    "motion_model": "rotation_about_fixed_axis",
                    "relevance": "target",
                    "start_event_role": "start",
                    "end_event_role": None,
                }
            ],
            "events": [
                {
                    "role": "start",
                    "kind": "start",
                    "subject_roles": ["wheel"],
                    "segment_role": "spin",
                    "evidence_quote": None,
                }
            ],
            "explicit_facts": [
                _fact(
                    "w", "angular_velocity", "5", "rad/s", "5 rad/s",
                    "wheel", "spin", temporal_role=None,
                )
            ],
            "relations": [],
            "assumption_proposals": [],
            "queries": [
                {
                    "role": "q1",
                    "output_key": "period",
                    "subject_role": "wheel",
                    "segment_role": "spin",
                    "component": "magnitude",
                    "event_role": None,
                }
            ],
            "answers": [
                {
                    "query_role": "q1",
                    "numeric": 1.2566,
                    "unit": "s",
                    "tolerance_abs": 0.01,
                    "reference_expression": "2*pi/w",
                }
            ],
        },
    )


PULLEY_TEXT = THROW_TEXT.replace("던진다.", "던진다. 줄이 도르래를 지나간다.")


def _pulley_overlap_case() -> PublicCorpusCaseV1:
    gold = _throw_gold(
        extra_entities=({"role": "pulley", "kind": "pulley", "label": "도르래"},),
        extra_relations=(
            {
                "role": "wrap",
                "kind": "passes_over_pulley",
                "participant_roles": ["stone", "pulley"],
                "segment_role": "fall",
            },
        ),
    )
    return _case(34, PULLEY_TEXT, gold)


IMPULSE_TEXT = (
    "연습 상황: 차가 정지 상태에서 출발하여 8 s 동안 96 m 를 이동한다. "
    "차가 받은 충격량은 24 N·s 이다. 차의 가속도를 구하시오."
)


def _impulse_case() -> PublicCorpusCaseV1:
    return _case(
        35,
        IMPULSE_TEXT,
        {
            "entities": [{"role": "car", "kind": "particle", "label": "차"}],
            "motion_segments": [
                {
                    "role": "run",
                    "order": 1,
                    "actor_roles": ["car"],
                    "motion_model": "constant_acceleration_1d",
                    "relevance": "target",
                    "start_event_role": "start",
                    "end_event_role": "stop",
                }
            ],
            "events": [
                {
                    "role": "start",
                    "kind": "start",
                    "subject_roles": ["car"],
                    "segment_role": "run",
                    "evidence_quote": None,
                },
                {
                    "role": "stop",
                    "kind": "finish",
                    "subject_roles": ["car"],
                    "segment_role": "run",
                    "evidence_quote": None,
                },
            ],
            "explicit_facts": [
                _fact("t", "time", "8", "s", "8 s", "car", "run"),
                _fact("d", "distance", "96", "m", "96 m", "car", "run"),
                _fact("j", "impulse", "24", "N·s", "24 N·s", "car", "run"),
            ],
            "relations": [],
            "assumption_proposals": [
                {
                    "role": "rest",
                    "kind": "starts_from_rest",
                    "subject_role": "car",
                    "segment_role": "run",
                    "supporting_quote": "정지 상태에서 출발",
                    "server_value_only": True,
                }
            ],
            "queries": [
                {
                    "role": "q1",
                    "output_key": "acceleration",
                    "subject_role": "car",
                    "segment_role": "run",
                    "component": "magnitude",
                    "event_role": None,
                }
            ],
            "answers": [
                {
                    "query_role": "q1",
                    "numeric": 3.0,
                    "unit": "m/s^2",
                    "tolerance_abs": 0.01,
                    "reference_expression": "2*d/t^2",
                }
            ],
        },
    )


def _projection(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.projected, projection.sanitized_reason
    return projection


def _selected(case: PublicCorpusCaseV1, profile_id: ProfileId):
    projection = _projection(case)
    application, result = run_lane_b_case_with_selected_profile(
        projection,
        profile_id,
        execution_token=deterministic_token(0, run_nonce=profile_id.value),
    )
    return (
        application,
        result,
        classify_selected_profile_outcome(profile_id, application, result),
    )


# --------------------------------------------------------------------------
# The closed vocabulary
# --------------------------------------------------------------------------


def test_the_status_vocabulary_is_closed_and_exact():
    assert [status.value for status in ProfileFeasibilityStatus] == [
        "profile_not_implemented",
        "profile_plan_not_formable",
        "profile_transaction_rejected",
        "validation_blocked",
        "normalization_blocked",
        "authorization_blocked",
        "compiler_no_equation",
        "compiler_underdetermined",
        "compiler_unsupported_reachable",
        "solver_rejected",
        "verification_rejected",
        "verified_solve_reachable",
        "verified_deferred_reachable",
        "harness_unclassified",
    ]
    assert NOT_MEASURED_STATUSES == {
        ProfileFeasibilityStatus.profile_not_implemented
    }


def test_the_precise_unsupported_whitelist_is_exact_typed_codes():
    assert {code.value for code in PRECISE_UNSUPPORTED_ISSUE_CODES} == {
        "requires_specialized_model",
        "consistency_inconclusive",
    }


def test_the_profile_table_and_enum_cannot_drift():
    assert tuple(
        signature.profile_id
        for signature in complete_profile_module._PROFILES
    ) == tuple(ProfileId)
    assert IMPLEMENTED_PROFILE_IDS == {
        ProfileId.signed_constant_acceleration_1d,
        ProfileId.particle_work_energy_speed,
        ProfileId.direct_constant_force_work,
        ProfileId.polar_kinematics_state,
        ProfileId.fixed_pulley,
        ProfileId.incline_hanging_pulley,
        ProfileId.table_pulley_two_body,
        ProfileId.incline_kinetic_sliding,
        ProfileId.rigid_fixed_axis,
        ProfileId.rigid_two_point_speed,
        ProfileId.collision_restitution,
        ProfileId.explicit_resultant_force,
        ProfileId.vertical_circle_top_speed,
        ProfileId.rolling_incline_energy_speed,
        ProfileId.free_flight_gravity,
        ProfileId.impulse_momentum,
        ProfileId.slot_pin_relative_frame,
        ProfileId.rotating_relative_frame,
        ProfileId.relative_translating_frame,
        ProfileId.horizontal_contact,
    }


# --------------------------------------------------------------------------
# Classifier decision tree — unit coverage only, never a pipeline claim
# --------------------------------------------------------------------------


def _result(terminal, *, codes=(), status=None, equations=0, exception=None):
    return LaneBResult(
        "0" * 32,
        terminal,
        compiler_codes=tuple(codes),
        compiler_status=status,
        equation_count=equations,
        stage_exception=exception,
    )


def _applied_application(profile_id):
    projection = _projection(_throw_case())
    return ProfileApplication(
        ApplicationOutcome.applied, projection.draft, profile_id
    )


@pytest.mark.parametrize(
    ("terminal", "kwargs", "expected"),
    [
        (LaneBTerminal.needs_figure, {}, ProfileFeasibilityStatus.validation_blocked),
        (LaneBTerminal.needs_confirmation, {}, ProfileFeasibilityStatus.validation_blocked),
        (LaneBTerminal.insufficient_information, {}, ProfileFeasibilityStatus.validation_blocked),
        (LaneBTerminal.validation_rejected, {}, ProfileFeasibilityStatus.validation_blocked),
        (LaneBTerminal.normalization_rejected, {}, ProfileFeasibilityStatus.normalization_blocked),
        (LaneBTerminal.authorization_failed, {}, ProfileFeasibilityStatus.authorization_blocked),
        (LaneBTerminal.verified_unsupported, {}, ProfileFeasibilityStatus.verified_deferred_reachable),
        (
            LaneBTerminal.compiler_unsupported,
            {"codes": ("requires_specialized_model",)},
            ProfileFeasibilityStatus.compiler_unsupported_reachable,
        ),
        (
            LaneBTerminal.compiler_unsupported,
            {"codes": ("consistency_inconclusive",)},
            ProfileFeasibilityStatus.compiler_unsupported_reachable,
        ),
        (
            # A code merely containing the word "unsupported" proves
            # nothing: without an exact whitelisted code the residual is
            # the honest verdict.
            LaneBTerminal.compiler_unsupported,
            {"codes": ("unsupported_feature",)},
            ProfileFeasibilityStatus.harness_unclassified,
        ),
        (
            LaneBTerminal.compiler_failure,
            {"status": "underdetermined", "equations": 0},
            ProfileFeasibilityStatus.compiler_no_equation,
        ),
        (
            LaneBTerminal.compiler_failure,
            {"status": "underdetermined", "equations": 3},
            ProfileFeasibilityStatus.compiler_underdetermined,
        ),
        (
            # A crash is not "no law wrote about the unknown".
            LaneBTerminal.compiler_failure,
            {"status": "underdetermined", "equations": 0, "exception": "ValueError"},
            ProfileFeasibilityStatus.harness_unclassified,
        ),
        (
            LaneBTerminal.compiler_failure,
            {"status": "invalid"},
            ProfileFeasibilityStatus.harness_unclassified,
        ),
        (LaneBTerminal.solve_rejected, {}, ProfileFeasibilityStatus.solver_rejected),
        (LaneBTerminal.verification_rejected, {}, ProfileFeasibilityStatus.verification_rejected),
        (LaneBTerminal.solved, {}, ProfileFeasibilityStatus.verified_solve_reachable),
        (LaneBTerminal.projection_rejected, {}, ProfileFeasibilityStatus.harness_unclassified),
    ],
)
def test_the_decision_tree_is_exact(terminal, kwargs, expected):
    """Unit coverage of every branch.  Not a pipeline-path claim.

    ``verification_rejected``, ``solver_rejected``,
    ``compiler_underdetermined``, and ``compiler_unsupported_reachable``
    have no applied-profile end-to-end producer at this head — the
    extremum waiver closed the one solver-refused shape, the remaining law
    chains emit whole or not at all, and the shape-exclusive transactions
    are the measured reasons, recorded in the structural-blockers report —
    so their coverage here is exactly this decision-tree unit test until
    further profile work produces them.
    """

    status = classify_selected_profile_outcome(
        ProfileId.free_flight_gravity,
        _applied_application(ProfileId.free_flight_gravity),
        _result(terminal, **kwargs),
    )
    assert status is expected


def test_an_unimplemented_profile_short_circuits_before_any_result():
    status = classify_selected_profile_outcome(
        ProfileId.work_energy, None, None
    )
    assert status is ProfileFeasibilityStatus.profile_not_implemented
    assert not profile_has_transaction(ProfileId.work_energy)


def test_plan_and_transaction_verdicts_come_from_the_application():
    projection = _projection(_throw_case())
    for outcome, expected in (
        (
            ApplicationOutcome.not_applied,
            ProfileFeasibilityStatus.profile_plan_not_formable,
        ),
        (
            ApplicationOutcome.rejected,
            ProfileFeasibilityStatus.profile_transaction_rejected,
        ),
    ):
        status = classify_selected_profile_outcome(
            ProfileId.free_flight_gravity,
            ProfileApplication(
                outcome, projection.draft, ProfileId.free_flight_gravity
            ),
            _result(LaneBTerminal.compiler_failure, status="underdetermined"),
        )
        assert status is expected


# --------------------------------------------------------------------------
# End-to-end positive controls — the real pipeline, one selected profile
# --------------------------------------------------------------------------


def test_the_applied_free_flight_time_question_solves_and_verifies():
    """The first applied-profile verified solve, measured end to end.

    The full chain — selected free-flight transaction, evidenced apex
    derivation, the elapsed-duration query binding, the static extremum
    solver waiver, and independent verification — delivers exactly one
    verified candidate.  The exhaustive controls live in
    ``test_phase56_stage7_extremum_boundary_solve.py``.
    """

    application, result, status = _selected(
        _throw_case(), ProfileId.free_flight_gravity
    )
    assert application.outcome is ApplicationOutcome.applied
    assert result.terminal is LaneBTerminal.solved
    assert result.equation_count == 3
    assert set(result.applied_law_ids) == {
        "event_vertical_extremum_velocity",
        "particle_constant_acceleration_velocity",
        "uniform_gravity_acceleration",
    }
    assert result.verified_candidate_count == 1
    assert result.answer_value_si is not None
    assert status is ProfileFeasibilityStatus.verified_solve_reachable


def test_the_applied_free_flight_height_question_measures_no_equation():
    application, result, status = _selected(
        _throw_case(query=MAX_HEIGHT_QUERY), ProfileId.free_flight_gravity
    )
    assert application.outcome is ApplicationOutcome.applied
    assert result.terminal is LaneBTerminal.compiler_failure
    assert result.equation_count == 0
    assert status is ProfileFeasibilityStatus.compiler_no_equation


def test_a_refused_transaction_is_its_own_verdict_not_the_pipelines():
    application, result, status = _selected(
        _throw_case(query=ACCELERATION_QUERY), ProfileId.free_flight_gravity
    )
    assert application.outcome is ApplicationOutcome.rejected
    assert application.sanitized_reason == "profile_shape_not_closable"
    assert status is ProfileFeasibilityStatus.profile_transaction_rejected


def test_an_unformable_plan_is_measured_as_its_own_verdict():
    application, result, status = _selected(
        _impulse_case(), ProfileId.impulse_momentum
    )
    assert application.outcome is ApplicationOutcome.not_applied
    assert status is ProfileFeasibilityStatus.profile_plan_not_formable


def test_the_applied_relative_frame_defers_precisely():
    application, result, status = _selected(
        _relative_case(), ProfileId.relative_translating_frame
    )
    assert application.outcome is ApplicationOutcome.applied
    assert result.terminal is LaneBTerminal.verified_unsupported
    assert (
        "translating_frame_relative_acceleration_deferred"
        in result.compiler_codes
    )
    assert result.answer_value_si is None
    assert status is ProfileFeasibilityStatus.verified_deferred_reachable


# --------------------------------------------------------------------------
# The matrix: honest zeros, independence, and order invariance
# --------------------------------------------------------------------------


def _cases():
    return [
        _throw_case(),
        _relative_case(),
        _rigid_case(),
        _pulley_overlap_case(),
        _impulse_case(),
    ]


def _work_query_case() -> PublicCorpusCaseV1:
    """A work readout: applicable to the unimplemented work_energy profile."""

    return _case(
        34,
        RIGID_TEXT,
        {
            "entities": [{"role": "wheel", "kind": "rigid_body", "label": "바퀴"}],
            "motion_segments": [
                {
                    "role": "spin",
                    "order": 1,
                    "actor_roles": ["wheel"],
                    "motion_model": "rotation_about_fixed_axis",
                    "relevance": "target",
                    "start_event_role": "start",
                    "end_event_role": None,
                }
            ],
            "events": [
                {
                    "role": "start",
                    "kind": "start",
                    "subject_roles": ["wheel"],
                    "segment_role": "spin",
                    "evidence_quote": None,
                }
            ],
            "explicit_facts": [
                _fact(
                    "w", "angular_velocity", "5", "rad/s", "5 rad/s",
                    "wheel", "spin", temporal_role=None,
                )
            ],
            "relations": [],
            "assumption_proposals": [],
            "queries": [
                {
                    "role": "q1",
                    "output_key": "work",
                    "subject_role": "wheel",
                    "segment_role": "spin",
                    "component": "magnitude",
                    "event_role": None,
                }
            ],
            "answers": [
                {
                    "query_role": "q1",
                    "numeric": 10.0,
                    "unit": "J",
                    "tolerance_abs": 0.01,
                    "reference_expression": "deliberately non-authoritative",
                }
            ],
        },
    )


def test_an_unimplemented_profile_is_not_measured_and_carries_no_yield():
    matrix = measure_profile_feasibility([*_cases(), _work_query_case()])
    rows = {row.profile_id: row for row in matrix.rows}
    exemplar = rows[ProfileId.work_energy]
    assert exemplar.implemented is False
    assert exemplar.applicable_contexts >= 1
    assert exemplar.measured_contexts == 0
    assert exemplar.not_measured_contexts == exemplar.applicable_contexts
    assert exemplar.status_counts == {
        "profile_not_implemented": exemplar.applicable_contexts
    }
    for row in matrix.rows:
        if not row.implemented:
            assert set(row.status_counts) <= {"profile_not_implemented"}


def test_one_context_distinguishes_unformable_from_applied():
    """The overlap is measured independently after fixed-pulley is implemented."""

    projection = _projection(_pulley_overlap_case())
    for profile_id in (ProfileId.free_flight_gravity, ProfileId.fixed_pulley):
        plan = plan_complete_profile(
            profile_id,
            projection.draft,
            approved_assumption_ids=projection.approvable_assumption_ids,
        )
        assert plan.disposition is not PlanDisposition.not_applicable
    matrix = measure_profile_feasibility([_pulley_overlap_case()])
    rows = {row.profile_id: row for row in matrix.rows}
    fixed = rows[ProfileId.fixed_pulley]
    assert fixed.implemented is True
    assert fixed.measured_contexts == 1
    assert fixed.status_counts == {"profile_plan_not_formable": 1}
    free_flight = rows[ProfileId.free_flight_gravity]
    assert free_flight.measured_contexts == 1
    assert "profile_not_implemented" not in free_flight.status_counts


def test_the_selected_run_is_independent_of_the_first_wins_winner():
    """The isolated verdict never borrows the closure's outcome.

    On the refused-shape fixture the closure's own walk applies nothing at
    all — and the isolated instrument still measures the profile's own
    transaction rejection.  Where the closure does crown a winner, the
    selected run of that profile measures the same verdict on its own: the
    winner grants nothing, the loser loses nothing.
    """

    case = _throw_case(query=ACCELERATION_QUERY)
    projection = _projection(case)
    bundle = build_lane_b_authority_bundle(projection)
    winner = close_projected_draft(
        projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert winner.outcome is ApplicationOutcome.not_applied
    _, _, status = _selected(case, ProfileId.free_flight_gravity)
    assert status is ProfileFeasibilityStatus.profile_transaction_rejected

    relative = _relative_case()
    relative_projection = _projection(relative)
    relative_bundle = build_lane_b_authority_bundle(relative_projection)
    relative_winner = close_projected_draft(
        relative_projection.draft,
        approved_assumption_ids=relative_bundle.approved_assumption_ids,
        authorized_assumptions=relative_bundle.authorization_map(),
    )
    assert relative_winner.profile_id is ProfileId.relative_translating_frame
    _, _, relative_status = _selected(
        relative, ProfileId.relative_translating_frame
    )
    assert relative_status is ProfileFeasibilityStatus.verified_deferred_reachable


def test_profile_order_never_changes_the_matrix():
    base = measure_profile_feasibility(_cases())
    shuffled = list(ProfileId)
    random.Random(0).shuffle(shuffled)
    for order in (tuple(reversed(ProfileId)), tuple(shuffled)):
        assert order != tuple(ProfileId)
        assert measure_profile_feasibility(_cases(), profile_order=order) == base


def test_declaration_table_order_never_changes_the_matrix(monkeypatch):
    base = measure_profile_feasibility(_cases())
    permuted = tuple(reversed(complete_profile_module._PROFILES))
    assert permuted != complete_profile_module._PROFILES
    monkeypatch.setattr(complete_profile_module, "_PROFILES", permuted)
    monkeypatch.setattr(
        complete_profile_module,
        "_PROFILES_BY_ID",
        {item.profile_id: item for item in permuted},
    )
    assert measure_profile_feasibility(_cases()) == base


def test_case_order_never_changes_the_matrix():
    base = measure_profile_feasibility(_cases())
    assert measure_profile_feasibility(list(reversed(_cases()))) == base


def test_an_incomplete_profile_order_is_refused():
    with pytest.raises(ValueError):
        measure_profile_feasibility(
            _cases(), profile_order=(ProfileId.free_flight_gravity,)
        )


def test_gold_identity_never_changes_the_matrix():
    base = measure_profile_feasibility(_cases())
    tampered_cases = []
    for index, case in enumerate(_cases()):
        payload = case.model_dump(mode="json")
        payload["case_id"] = f"renamed_case_{index}"
        payload["family"] = "renamed_family"
        payload["tags"] = ["routing-bait"]
        payload["gold"]["answers"] = []
        tampered_cases.append(PublicCorpusCaseV1(**payload))
    assert measure_profile_feasibility(tampered_cases) == base


def test_the_matrix_is_counts_only():
    matrix = measure_profile_feasibility(_cases()).as_dict()
    assert set(matrix) == {"version", "context_count", "profiles"}
    for row in matrix["profiles"]:
        assert set(row) == {
            "profile_id",
            "implemented",
            "applicable_contexts",
            "measured_contexts",
            "not_measured_contexts",
            "status_counts",
        }
        assert isinstance(row["implemented"], bool)
        for key, value in row["status_counts"].items():
            assert key in {status.value for status in ProfileFeasibilityStatus}
            assert isinstance(value, int)


def test_the_production_path_does_not_import_the_instrument():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for directory in ("app", "engine"):
        for path in (root / directory).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if (
                "profile_feasibility" in text
                or "run_lane_b_case_with_selected_profile" in text
            ):
                offenders.append(str(path))
    assert offenders == []
