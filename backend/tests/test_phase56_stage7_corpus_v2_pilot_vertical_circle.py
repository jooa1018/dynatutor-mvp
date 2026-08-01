"""The vertical-circle limiting-contact pilot: a v2 closure from source words.

The B12 revocation established that the public corpus shape cannot solve this
family: the v1 contract has no field for the contact's side, the maintained
contact, or the active contact-limit boundary — even though the *source text*
states all three ("moves along the **inside** of the track", "the least speed
that **just maintains contact**", "at the **top** of the track") and the C1
correction already carries the minimum objective from the v1 output key.

This pilot states those three carriers in v2, cites the source's own words as
evidence through verbatim aligned quotes, and closes the family with the
existing `vertical_circle_top_speed` profile and the existing
`vertical_circle_top_minimum_speed` law.  No new physics, no new engine
authority, no relaxation: every ablation below must stay fail-closed exactly
as the B12 revocation left it.

Everything here is synthetic — the fixture case is the B12 test file's own
independent fixture, never the public archive.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.mechanics.contracts import MechanicsProblemDraftV1
from evaluation.phase56_stage7.corpus_v2.records import (
    ConstraintAuthority,
    ConstraintAuthorityV2,
    ContactSide,
    ContactSideV2,
    CorpusV2AugmentationV1,
    EndpointCondition,
    EndpointConditionV2,
    SourceQuoteEvidenceV2,
)
from evaluation.phase56_stage7.corpus_v2.shadow_runner import run_shadow_context
from evaluation.phase56_stage7.corpus_v2.validation import (
    V2ValidationError,
    V2ValidationReason,
    validate_augmentation,
)
from evaluation.phase56_stage7.lane_b_draft_projection import project_case_to_draft
from evaluation.phase56_stage7.lane_b_runner import LaneBTerminal, run_lane_b_case
from tests.test_phase56_stage7_b12_vertical_circle_top_speed import (
    _LIMIT_QUOTE,
    _case,
)

pytestmark = pytest.mark.slow


def _pilot_augmentation(
    payload: dict,
    *,
    with_side: bool = True,
    with_maintained: bool = True,
    with_boundary: bool = True,
    side: ContactSide = ContactSide.inside_track,
    inside_quote: str = "안쪽",
) -> CorpusV2AugmentationV1:
    particle = next(
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "particle"
    )
    track = next(
        item["entity_id"]
        for item in payload["entities"]
        if item["primitive"] == "surface"
    )
    interval = payload["motion_intervals"][0]["interval_id"]
    interaction = payload["interactions"][0]["interaction_id"]
    top = next(
        item["event_id"]
        for item in payload["events"]
        if item["kind"] == "highest_point"
    )
    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id="v2_ev_inside", quote=inside_quote),
            SourceQuoteEvidenceV2(evidence_id="v2_ev_limit", quote=_LIMIT_QUOTE),
        ),
        contact_sides=(
            (
                ContactSideV2(
                    contact_id="v2_contact_inside",
                    interaction_id=interaction,
                    side=side,
                    subject_id=particle,
                    evidence_refs=("v2_ev_inside",),
                ),
            )
            if with_side
            else ()
        ),
        constraint_authorities=(
            (
                ConstraintAuthorityV2(
                    constraint_id="v2_contact_maintained",
                    authority=ConstraintAuthority.contact_maintained,
                    participant_ids=(particle, track),
                    subject_id=particle,
                    interval_id=interval,
                    evidence_refs=("v2_ev_limit",),
                ),
            )
            if with_maintained
            else ()
        ),
        endpoint_conditions=(
            (
                EndpointConditionV2(
                    endpoint_id="v2_contact_limit_boundary",
                    condition=EndpointCondition.contact_limit,
                    boundary_event_id=top,
                    subject_id=particle,
                    interval_id=interval,
                    evidence_refs=("v2_ev_limit",),
                ),
            )
            if with_boundary
            else ()
        ),
    )


def _shadow(case=None, **augmentation_knobs):
    projection = project_case_to_draft(case if case is not None else _case())
    payload = projection.draft.model_dump(mode="json", warnings="none")
    augmentation = _pilot_augmentation(payload, **augmentation_knobs)

    def run(candidate_payload):
        draft = MechanicsProblemDraftV1.model_validate(candidate_payload)
        return run_lane_b_case(
            replace(projection, draft=draft), execution_token="b12-pilot-token"
        )

    return (
        run_shadow_context(
            draft_payload=payload,
            augmentation=augmentation,
            run=run,
            problem_text=projection.problem_text,
        ),
        run,
        payload,
        augmentation,
        projection,
    )


def _known(payload: dict) -> dict:
    return {
        "known_entity_ids": [item["entity_id"] for item in payload["entities"]],
        "known_interval_ids": [
            item["interval_id"] for item in payload["motion_intervals"]
        ],
        "known_event_ids": [item["event_id"] for item in payload["events"]],
        "known_evidence_ids": [
            item["evidence_id"] for item in payload["source_evidence"]
        ],
        "known_interaction_ids": [
            item["interaction_id"] for item in payload["interactions"]
        ],
        "known_query_ids": [item["query_id"] for item in payload["queries"]],
        "authored_ids": [item["entity_id"] for item in payload["entities"]],
    }


# ---------------------------------------------------------------------------
# The closure
# ---------------------------------------------------------------------------


def test_the_source_stated_carriers_close_the_corpus_shape() -> None:
    result, run, payload, augmentation, projection = _shadow()

    assert result.baseline_solved is False
    assert result.shadow_solved is True
    assert result.newly_solved is True
    assert result.regressed is False
    assert set(result.carriers_supplied) == {
        "contact_side",
        "constraint_authority",
        "endpoint_condition",
        "source_quote",
    }


def test_the_pilot_answer_is_the_boundary_equality_exactly() -> None:
    # The fixture radius is 2 m and the authorised gravity is 9.81 m/s^2, so
    # the one admissible boundary speed is sqrt(g r).  This is the law's own
    # number on a synthetic fixture — no public answer is read anywhere.
    from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation

    _, run, payload, augmentation, projection = _shadow()
    merged = project_augmentation(
        payload, augmentation, problem_text=projection.problem_text
    )
    outcome = run(merged)
    assert outcome.terminal is LaneBTerminal.solved
    assert outcome.answer_value_si == pytest.approx((9.81 * 2.0) ** 0.5)
    assert outcome.answer_unit == "m/s"
    assert "vertical_circle_top_minimum_speed" in outcome.applied_law_ids


def test_the_augmentation_validates_against_the_sources_own_identifiers() -> None:
    _, run, payload, augmentation, _ = _shadow()
    validate_augmentation(augmentation, **_known(payload))


def test_the_pilot_is_deterministic() -> None:
    first, *_ = _shadow()
    second, *_ = _shadow()
    assert first == second


# ---------------------------------------------------------------------------
# Ablations — each missing authority keeps the B12 refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "knobs",
    [
        {"with_side": False},
        {"with_maintained": False},
        {"with_boundary": False},
        {"with_side": False, "with_maintained": False, "with_boundary": False},
    ],
)
def test_a_missing_authority_keeps_the_family_fail_closed(knobs) -> None:
    result, *_ = _shadow(**knobs)
    assert result.shadow_solved is False
    assert result.newly_solved is False
    assert result.regressed is False


def test_an_outside_track_statement_does_not_solve() -> None:
    # An outside track has no minimum-to-maintain-contact boundary at the
    # top; the profile refuses the shape rather than answering the mirror
    # question.  (The fixture's own text still says inside; the side under
    # test is the typed statement, which is what the profile reads.)
    result, *_ = _shadow(side=ContactSide.outside_track)
    assert result.shadow_solved is False


def test_a_quote_the_source_never_wrote_refuses_the_projection() -> None:
    projection = project_case_to_draft(_case())
    payload = projection.draft.model_dump(mode="json", warnings="none")
    augmentation = _pilot_augmentation(payload, inside_quote="바깥쪽 궤도를 따라")

    def run(candidate_payload):
        draft = MechanicsProblemDraftV1.model_validate(candidate_payload)
        return run_lane_b_case(
            replace(projection, draft=draft), execution_token="b12-pilot-token"
        )

    with pytest.raises(V2ValidationError) as caught:
        run_shadow_context(
            draft_payload=payload,
            augmentation=augmentation,
            run=run,
            problem_text=projection.problem_text,
        )
    assert caught.value.reason is V2ValidationReason.evidence_quote_not_in_source


def test_a_projection_without_the_source_text_refuses_quotes() -> None:
    from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation

    projection = project_case_to_draft(_case())
    payload = projection.draft.model_dump(mode="json", warnings="none")
    augmentation = _pilot_augmentation(payload)

    with pytest.raises(V2ValidationError) as caught:
        project_augmentation(payload, augmentation)
    assert caught.value.reason is V2ValidationReason.evidence_quote_not_in_source


def test_an_empty_augmentation_still_moves_nothing() -> None:
    projection = project_case_to_draft(_case())
    payload = projection.draft.model_dump(mode="json", warnings="none")

    def run(candidate_payload):
        draft = MechanicsProblemDraftV1.model_validate(candidate_payload)
        return run_lane_b_case(
            replace(projection, draft=draft), execution_token="b12-pilot-token"
        )

    result = run_shadow_context(
        draft_payload=payload,
        augmentation=CorpusV2AugmentationV1(),
        run=run,
        problem_text=projection.problem_text,
    )
    assert result.baseline_rung == result.shadow_rung
    assert result.augmented is False


def test_the_v1_official_path_is_untouched_by_the_pilot() -> None:
    # The corpus shape with no augmentation still refuses — the pilot adds
    # shadow-side carriers and changes nothing about the official run.
    projection = project_case_to_draft(_case())
    outcome = run_lane_b_case(projection, execution_token="b12-pilot-token")
    assert outcome.terminal is not LaneBTerminal.solved
    assert outcome.answer_value_si is None
