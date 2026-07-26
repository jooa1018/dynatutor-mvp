"""Lane B authority bundle: exact, immutable, bound to one Draft — and attacked.

The bundle is the evaluator's only bridge to the engine's two-keyed
``server_default`` contract, so every test here is about exactness: the right
assumption is authorized to the character of the closed policy, and everything
else — wrong role, wrong value, wrong unit, wrong subject, wrong interval,
unapproved dispositions, duplicates, competitors, forgeries, tampering, and
replays against other Drafts — fails closed.

The engine-side wall (a ``server_default`` quantity whose authorization does
not match to the character is a ``provenance_violation``) is regression-covered
by the Phase 56 validation suite; these tests cover the evaluator layer that
builds and binds the bundle, and the runner wiring that hands one immutable
map to both ``validate_draft`` and ``normalize_draft``.

Every fixture is independently authored.  None is derived from a corpus case,
and none reads a case ID, family, split, expected terminal, or expected answer.
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType

import pytest

from engine.mechanics.validation import AssumptionAuthorization

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_authority import (
    LANE_B_AUTHORITY_BUNDLE_VERSION,
    AuthorityRefusal,
    LaneBAuthorityBundleV1,
    LaneBAuthorityError,
    build_lane_b_authority_bundle,
    draft_fingerprint,
    verify_lane_b_authority_bundle,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjection,
    project_case_to_draft,
)
from support.phase56_stage7_corpus_fixtures import build_case

GRAVITY_PROPOSAL = {
    "role": "g",
    "kind": "constant_gravity",
    "subject_role": "box",
    "segment_role": "motion_1",
    "supporting_quote": None,
    "server_value_only": True,
}


def _case(
    *,
    index: int = 3,
    proposals: tuple[dict, ...] = (GRAVITY_PROPOSAL,),
    **record_overrides,
) -> PublicCorpusCaseV1:
    record = build_case(
        index=index,
        split="public_dev",
        family="single_particle_newton",
        future_terminal="accepted",
        with_answer=True,
    )
    record["split"] = PublicSplit.public_dev
    record["gold"]["assumption_proposals"] = [dict(item) for item in proposals]
    record.update(record_overrides)
    return PublicCorpusCaseV1(**record)


def _projection(**kwargs) -> DraftProjection:
    projection = project_case_to_draft(_case(**kwargs))
    assert projection.projected
    return projection


def _with_tampered_assumption(
    projection: DraftProjection, assumption_id: str, update: dict
) -> DraftProjection:
    draft = projection.draft
    tampered = draft.model_copy(
        update={
            "assumptions": [
                item.model_copy(update=update)
                if item.assumption_id == assumption_id
                else item
                for item in draft.assumptions
            ]
        }
    )
    return dataclasses.replace(projection, draft=tampered)


# --------------------------------------------------------------------------
# The positive control: exactly the closed policy, exactly once
# --------------------------------------------------------------------------


def test_a_constant_gravity_approval_is_authorized_exactly():
    projection = _projection()
    bundle = build_lane_b_authority_bundle(projection)

    assert bundle.version == LANE_B_AUTHORITY_BUNDLE_VERSION
    assert bundle.approved_assumption_ids == tuple(
        sorted(projection.approvable_assumption_ids)
    )
    assert bundle.refusals == ()

    mapping = bundle.authorization_map()
    assert set(mapping) == {"asm_g"}
    authorization = mapping["asm_g"]
    assert type(authorization) is AssumptionAuthorization
    assert authorization == AssumptionAuthorization(
        assumption_id="asm_g",
        subject_id="box",
        role="gravity",
        raw_value="9.81",
        raw_unit="m/s^2",
        interval_id="motion_1",
    )
    assert verify_lane_b_authority_bundle(bundle, projection.draft)


def test_building_twice_from_the_same_projection_is_deterministic():
    projection = _projection()
    assert build_lane_b_authority_bundle(projection) == build_lane_b_authority_bundle(
        projection
    )


def test_authorization_restates_the_approved_record_and_invents_nothing():
    """Authorization is not a new source of values.

    Every field of the issued authorization already stands in the Draft's own
    approved assumption record; the bundle adds identity binding, never
    content.
    """

    projection = _projection()
    bundle = build_lane_b_authority_bundle(projection)
    (record,) = [
        item for item in projection.draft.assumptions if item.assumption_id == "asm_g"
    ]
    ((key, authorization),) = bundle.authorized_assumptions
    assert key == record.assumption_id
    assert authorization.subject_id == record.subject_id
    assert str(authorization.role) == str(
        getattr(record.proposed_role, "value", record.proposed_role)
    )
    assert authorization.raw_value == record.proposed_value
    assert authorization.raw_unit == record.proposed_unit
    assert authorization.interval_id == record.interval_id


# --------------------------------------------------------------------------
# Immutability
# --------------------------------------------------------------------------


def test_the_bundle_is_frozen_and_its_map_is_read_only():
    bundle = build_lane_b_authority_bundle(_projection())
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.version = "forged"  # type: ignore[misc]

    mapping = bundle.authorization_map()
    assert isinstance(mapping, MappingProxyType)
    with pytest.raises(TypeError):
        mapping["asm_g"] = object()  # type: ignore[index]
    with pytest.raises(TypeError):
        del mapping["asm_g"]  # type: ignore[attr-defined]


def test_any_mutation_after_the_fingerprint_verifies_false():
    projection = _projection()
    bundle = build_lane_b_authority_bundle(projection)
    draft = projection.draft
    assert verify_lane_b_authority_bundle(bundle, draft)

    mutated_ids = dataclasses.replace(
        bundle, approved_assumption_ids=(*bundle.approved_assumption_ids, "asm_extra")
    )
    assert not verify_lane_b_authority_bundle(mutated_ids, draft)

    mutated_refusals = dataclasses.replace(
        bundle, refusals=(("asm_g", "policy_mismatch"),)
    )
    assert not verify_lane_b_authority_bundle(mutated_refusals, draft)

    mutated_value = dataclasses.replace(
        bundle,
        authorized_assumptions=tuple(
            (key, dataclasses.replace(value, raw_value="9.8"))
            for key, value in bundle.authorized_assumptions
        ),
    )
    assert not verify_lane_b_authority_bundle(mutated_value, draft)


# --------------------------------------------------------------------------
# Refusals: everything that is not exactly the policy fails closed
# --------------------------------------------------------------------------


def test_no_authorization_for_proposed_visible_or_rejected_dispositions():
    projection = _projection()
    for disposition in ("proposed", "visible", "rejected"):
        tampered = projection.draft.model_copy(
            update={
                "assumptions": [
                    item.model_copy(update={"disposition": disposition})
                    for item in projection.draft.assumptions
                ]
            }
        )
        fake = dataclasses.replace(
            projection, draft=tampered, approvable_assumption_ids=()
        )
        bundle = build_lane_b_authority_bundle(fake)
        assert bundle.authorized_assumptions == ()
        assert bundle.approved_assumption_ids == ()


def test_an_approved_record_outside_the_approvable_set_fails_closed():
    """The projection's set and the Draft's dispositions must agree exactly."""

    projection = _projection()
    with pytest.raises(LaneBAuthorityError):
        build_lane_b_authority_bundle(
            dataclasses.replace(projection, approvable_assumption_ids=())
        )
    with pytest.raises(LaneBAuthorityError):
        build_lane_b_authority_bundle(
            dataclasses.replace(
                projection,
                approvable_assumption_ids=(
                    *projection.approvable_assumption_ids,
                    "asm_ghost",
                ),
            )
        )


def test_a_projection_without_a_draft_cannot_issue_authority():
    projection = _projection()
    with pytest.raises(LaneBAuthorityError):
        build_lane_b_authority_bundle(dataclasses.replace(projection, draft=None))


@pytest.mark.parametrize(
    ("update", "refusal"),
    [
        ({"proposed_role": "acceleration"}, AuthorityRefusal.policy_mismatch),
        ({"proposed_value": "9.8"}, AuthorityRefusal.policy_mismatch),
        ({"proposed_value": "9.81000"}, AuthorityRefusal.policy_mismatch),
        ({"proposed_unit": "m/s"}, AuthorityRefusal.policy_mismatch),
        ({"subject_id": "ghost"}, AuthorityRefusal.subject_unresolved),
        ({"interval_id": "ghost_interval"}, AuthorityRefusal.interval_unresolved),
        (
            {"proposed_value": None, "proposed_unit": None},
            AuthorityRefusal.proposal_incomplete,
        ),
    ],
)
def test_a_deviating_proposal_is_refused(update, refusal):
    projection = _projection()
    fake = _with_tampered_assumption(projection, "asm_g", update)
    bundle = build_lane_b_authority_bundle(fake)
    assert bundle.authorized_assumptions == ()
    assert bundle.refusals == (("asm_g", refusal.value),)


def test_duplicate_gravity_approvals_refuse_both():
    """One physical identity, one approved assumption — two refuse together."""

    projection = _projection(
        proposals=(GRAVITY_PROPOSAL, dict(GRAVITY_PROPOSAL, role="g2"))
    )
    bundle = build_lane_b_authority_bundle(projection)
    assert bundle.authorized_assumptions == ()
    assert set(bundle.refusals) == {
        ("asm_g", AuthorityRefusal.duplicate_identity.value),
        ("asm_g2", AuthorityRefusal.duplicate_identity.value),
    }


def test_a_stated_gravity_fact_blocks_the_server_default():
    """A stated number for the role always outranks the server default."""

    projection = _projection()
    draft = projection.draft
    tampered = draft.model_copy(
        update={
            "quantities": [
                item.model_copy(update={"role": "gravity"})
                if item.quantity_id == "qty_mass"
                else item
                for item in draft.quantities
            ]
        }
    )
    bundle = build_lane_b_authority_bundle(
        dataclasses.replace(projection, draft=tampered)
    )
    assert bundle.authorized_assumptions == ()
    assert bundle.refusals == (
        ("asm_g", AuthorityRefusal.competing_stated_fact.value),
    )


# --------------------------------------------------------------------------
# Competing stated facts are judged at the physical identity, not the role
# --------------------------------------------------------------------------
#
# The assumption under authorization is `asm_g`: gravity for subject `box`
# over interval `motion_1`.  A stated gravity fact occupies that identity only
# when its own subject and interval/event scope land on it; a stated gravity
# for another body, or for another interval of this body, licenses no refusal.


def _with_gravity_fact(projection: DraftProjection, **update) -> DraftProjection:
    """Restate the fixture's mass fact as a stated gravity fact, re-scoped."""

    draft = projection.draft
    tampered = draft.model_copy(
        update={
            "quantities": [
                item.model_copy(update={"role": "gravity", **update})
                if item.quantity_id == "qty_mass"
                else item
                for item in draft.quantities
            ]
        }
    )
    return dataclasses.replace(projection, draft=tampered)


def _with_second_interval(projection: DraftProjection) -> DraftProjection:
    """Add a second interval `motion_2` with its own event `ev_two`."""

    draft = projection.draft
    second_interval = draft.motion_intervals[0].model_copy(
        update={
            "interval_id": "motion_2",
            "order": 2,
            "start_event_id": None,
            "end_event_id": None,
        }
    )
    second_event = draft.events[0].model_copy(
        update={
            "event_id": "ev_two",
            "kind": "finish",
            "interval_ids": ["motion_2"],
        }
    )
    tampered = draft.model_copy(
        update={
            "motion_intervals": [*draft.motion_intervals, second_interval],
            "events": [*draft.events, second_event],
        }
    )
    return dataclasses.replace(projection, draft=tampered)


def _expect_authorized(projection: DraftProjection) -> None:
    bundle = build_lane_b_authority_bundle(projection)
    assert bundle.refusals == ()
    assert [key for key, _ in bundle.authorized_assumptions] == ["asm_g"]


def _expect_refused(projection: DraftProjection) -> None:
    bundle = build_lane_b_authority_bundle(projection)
    assert bundle.authorized_assumptions == ()
    assert bundle.refusals == (
        ("asm_g", AuthorityRefusal.competing_stated_fact.value),
    )


def test_a_same_role_fact_on_another_subject_does_not_block():
    """Another body's stated gravity says nothing about this subject's."""

    _expect_authorized(_with_gravity_fact(_projection(), subject_id="surface"))


def test_a_same_role_fact_in_another_interval_does_not_block():
    """This body's stated gravity elsewhere in time says nothing about here."""

    projection = _with_second_interval(_projection())
    _expect_authorized(_with_gravity_fact(projection, interval_id="motion_2"))


@pytest.mark.parametrize(
    "provenance", ["explicit_source", "user_correction", "server_default"]
)
def test_a_stated_fact_at_the_same_identity_blocks_for_every_stated_provenance(
    provenance,
):
    """Same subject, same interval: every number-bearing provenance outranks."""

    _expect_refused(_with_gravity_fact(_projection(), provenance=provenance))


def test_an_event_scoped_fact_touching_the_authorized_interval_blocks():
    """An event on this interval's boundary is this interval's own instant."""

    _expect_refused(
        _with_gravity_fact(_projection(), interval_id=None, event_id="start")
    )


def test_an_event_scoped_fact_provably_attached_elsewhere_does_not_block():
    """An event that belongs only to another interval separates cleanly."""

    projection = _with_second_interval(_projection())
    _expect_authorized(
        _with_gravity_fact(projection, interval_id=None, event_id="ev_two")
    )


def test_an_unprovable_event_scope_fails_closed():
    """No attachment, or a dangling event reference, proves no separation."""

    projection = _with_second_interval(_projection())
    draft = projection.draft
    floating_event = draft.events[0].model_copy(
        update={"event_id": "ev_float", "kind": "other", "interval_ids": []}
    )
    with_floating = dataclasses.replace(
        projection,
        draft=draft.model_copy(update={"events": [*draft.events, floating_event]}),
    )
    _expect_refused(
        _with_gravity_fact(with_floating, interval_id=None, event_id="ev_float")
    )
    _expect_refused(
        _with_gravity_fact(projection, interval_id=None, event_id="ev_ghost")
    )


def test_an_interval_free_stated_fact_still_blocks():
    """A fact scoped to no interval states the value for every interval."""

    _expect_refused(
        _with_gravity_fact(_projection(), interval_id=None, event_id=None)
    )


def test_competing_fact_scoping_is_array_order_invariant():
    projection = _with_gravity_fact(_projection(), subject_id="surface")
    draft = projection.draft
    reversed_quantities = dataclasses.replace(
        projection,
        draft=draft.model_copy(
            update={"quantities": list(reversed(draft.quantities))}
        ),
    )
    bundle = build_lane_b_authority_bundle(projection)
    reordered = build_lane_b_authority_bundle(reversed_quantities)
    assert bundle.authorized_assumptions == reordered.authorized_assumptions
    assert bundle.refusals == reordered.refusals


def test_competing_fact_scoping_is_id_rename_invariant():
    """Consistently renaming the other subject changes no outcome."""

    def rename(projection: DraftProjection, old: str, new: str) -> DraftProjection:
        draft = projection.draft
        tampered = draft.model_copy(
            update={
                "entities": [
                    item.model_copy(update={"entity_id": new})
                    if item.entity_id == old
                    else item
                    for item in draft.entities
                ],
                "quantities": [
                    item.model_copy(update={"subject_id": new})
                    if item.subject_id == old
                    else item
                    for item in draft.quantities
                ],
            }
        )
        return dataclasses.replace(projection, draft=tampered)

    blocked = _with_gravity_fact(_projection())
    allowed = _with_gravity_fact(_projection(), subject_id="surface")
    for original, expect in ((blocked, _expect_refused), (allowed, _expect_authorized)):
        expect(original)
        expect(rename(original, "surface", "plate_renamed"))


# --------------------------------------------------------------------------
# Binding: this bundle, this Draft, this revision — nothing else
# --------------------------------------------------------------------------


def test_the_bundle_speaks_only_for_its_own_draft_revision():
    projection = _projection()
    bundle = build_lane_b_authority_bundle(projection)
    assert verify_lane_b_authority_bundle(bundle, projection.draft)

    other = _projection(index=4)
    assert not verify_lane_b_authority_bundle(bundle, other.draft)
    assert not verify_lane_b_authority_bundle(
        build_lane_b_authority_bundle(other), projection.draft
    )

    stale_revision = projection.draft.model_copy(
        update={
            "quantities": [
                item.model_copy(update={"raw_value": "999"})
                if item.quantity_id == "qty_mass"
                else item
                for item in projection.draft.quantities
            ]
        }
    )
    assert not verify_lane_b_authority_bundle(bundle, stale_revision)


def test_forged_and_tampered_bundles_verify_false():
    projection = _projection()
    bundle = build_lane_b_authority_bundle(projection)
    draft = projection.draft

    class ForgedAuthorization(AssumptionAuthorization):
        pass

    forged_type = dataclasses.replace(
        bundle,
        authorized_assumptions=tuple(
            (key, ForgedAuthorization(**dataclasses.asdict(value)))
            for key, value in bundle.authorized_assumptions
        ),
    )
    assert not verify_lane_b_authority_bundle(forged_type, draft)

    mismatched_key = dataclasses.replace(
        bundle,
        authorized_assumptions=tuple(
            ("asm_other", value) for _, value in bundle.authorized_assumptions
        ),
    )
    assert not verify_lane_b_authority_bundle(mismatched_key, draft)

    outside_approved = dataclasses.replace(bundle, approved_assumption_ids=())
    assert not verify_lane_b_authority_bundle(outside_approved, draft)

    forged_fingerprint = dataclasses.replace(
        bundle, authority_fingerprint="0" * 64
    )
    assert not verify_lane_b_authority_bundle(forged_fingerprint, draft)

    wrong_version = dataclasses.replace(bundle, version="v0")
    assert not verify_lane_b_authority_bundle(wrong_version, draft)

    assert not verify_lane_b_authority_bundle(object(), draft)


def test_reordering_the_authority_arrays_breaks_the_fingerprint():
    projection = _projection(
        proposals=(
            GRAVITY_PROPOSAL,
            dict(GRAVITY_PROPOSAL, role="g2", subject_role="surface"),
        )
    )
    bundle = build_lane_b_authority_bundle(projection)
    assert len(bundle.authorized_assumptions) == 2

    reordered = dataclasses.replace(
        bundle, authorized_assumptions=tuple(reversed(bundle.authorized_assumptions))
    )
    assert not verify_lane_b_authority_bundle(reordered, projection.draft)

    reordered_ids = dataclasses.replace(
        bundle,
        approved_assumption_ids=tuple(reversed(bundle.approved_assumption_ids)),
    )
    assert not verify_lane_b_authority_bundle(reordered_ids, projection.draft)


def test_case_identity_and_gold_metadata_contribute_nothing():
    """The same source structure under other gold labels authorizes identically."""

    first = _case()
    second = _case(
        case_id="fx_other_identity",
        family="totally_different_family",
        tags=["other", "labels"],
        difficulty=5,
    )
    bundle_first = build_lane_b_authority_bundle(project_case_to_draft(first))
    bundle_second = build_lane_b_authority_bundle(project_case_to_draft(second))
    assert bundle_first == bundle_second
    assert bundle_first.authority_fingerprint == bundle_second.authority_fingerprint


# --------------------------------------------------------------------------
# Runner wiring: one immutable map, both stages, authority before validation
# --------------------------------------------------------------------------


def test_the_runner_hands_the_same_immutable_map_to_validate_and_normalize(
    monkeypatch,
):
    from evaluation.phase56_stage7 import lane_b_runner

    seen: dict[str, dict] = {}
    real_validate = lane_b_runner.validate_draft
    real_normalize = lane_b_runner.normalize_draft

    def spy_validate(text, draft, **kwargs):
        seen["validate"] = dict(kwargs)
        return real_validate(text, draft, **kwargs)

    def spy_normalize(text, draft, **kwargs):
        seen["normalize"] = dict(kwargs)
        return real_normalize(text, draft, **kwargs)

    monkeypatch.setattr(lane_b_runner, "validate_draft", spy_validate)
    monkeypatch.setattr(lane_b_runner, "normalize_draft", spy_normalize)

    projection = _projection()
    lane_b_runner.run_lane_b_case(projection, execution_token="0" * 32)

    validate_map = seen["validate"]["authorized_assumptions"]
    normalize_map = seen["normalize"]["authorized_assumptions"]
    assert validate_map is normalize_map
    assert isinstance(validate_map, MappingProxyType)
    assert set(validate_map) == {"asm_g"}
    assert tuple(seen["validate"]["approved_assumption_ids"]) == tuple(
        seen["normalize"]["approved_assumption_ids"]
    )


def test_an_inconsistent_projection_fails_the_authority_stage_closed(monkeypatch):
    """A projection whose approvable set lies about its Draft never validates."""

    from evaluation.phase56_stage7 import lane_b_runner

    projection = _projection()
    inconsistent = dataclasses.replace(projection, approvable_assumption_ids=())

    called = {"validate": 0}
    real_validate = lane_b_runner.validate_draft

    def spy_validate(text, draft, **kwargs):
        called["validate"] += 1
        return real_validate(text, draft, **kwargs)

    monkeypatch.setattr(lane_b_runner, "validate_draft", spy_validate)
    result = lane_b_runner.run_lane_b_case(inconsistent, execution_token="0" * 32)
    assert result.terminal is lane_b_runner.LaneBTerminal.authorization_failed
    assert result.stage_exception == "LaneBAuthorityError"
    assert called["validate"] == 0
    assert result.answer_value_si is None


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------


def test_the_production_path_does_not_import_the_authority_module():
    """Evaluator-only: no engine or app module may reach the bundle."""

    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for base in ("engine", "app"):
        for path in (root / base).rglob("*.py"):
            if "lane_b_authority" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_the_refusal_vocabulary_is_closed():
    assert {item.value for item in AuthorityRefusal} == {
        "proposal_incomplete",
        "subject_unresolved",
        "interval_unresolved",
        "policy_mismatch",
        "grammar_rejected",
        "role_not_in_closed_mapping",
        "duplicate_identity",
        "competing_value_identity",
        "competing_stated_fact",
    }


def test_the_draft_fingerprint_is_the_exact_revision():
    projection = _projection()
    first = draft_fingerprint(projection.draft)
    assert first == draft_fingerprint(projection.draft)
    changed = projection.draft.model_copy(
        update={
            "quantities": [
                item.model_copy(update={"raw_value": "1.23"})
                if item.quantity_id == "qty_mass"
                else item
                for item in projection.draft.quantities
            ]
        }
    )
    assert first != draft_fingerprint(changed)
