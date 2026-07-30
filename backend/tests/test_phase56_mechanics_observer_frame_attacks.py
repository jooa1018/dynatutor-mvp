"""Attacks on the observer deferral: what counts as a frame of reference.

Deferring a problem as "requires a specialized mechanics model" is the strongest
claim this compiler makes and the only one that is final — a deferred problem is
never reconsidered.  So the evidence for it has to be a typed reference from the
model to the observer, and nothing weaker.

These tests attack that rule from both sides.  A string that merely *equals* an
entity id — a label, an evidence id, a symbol id, a written value or unit — is
not a reference, and must not buy the strong claim.  A second observer, or an
observer whose stated rest is scoped to an instant, to one interval of several,
or to a frame that is itself moving, must not buy the *exemption* either.

No family, case ID, split, expected system type, expected terminal, or answer is
read anywhere here.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from engine.mechanics.compiler.compiler import (
    _ENTITY_REFERENCE_FIELDS,
    _declared_at_rest,
    _entity_is_modelled,
    _typed_entity_references,
)
from engine.mechanics.compiler.contracts import CompilerIssueCode
from engine.mechanics.contracts import MechanicsProblemIRV1

from test_phase56_mechanics_compiler import (
    LENGTH,
    VELOCITY,
    compile_mechanics_ir,
    _ir,
    _quantity,
    _symbol,
)
from test_phase56_mechanics_observer_frame_unsupported import _observer_payload

OBSERVER = "observerFrame"


def _codes(result) -> set[str]:
    return {item.code.value for item in result.issues}


def _deferred(payload: dict[str, object]) -> bool:
    result = compile_mechanics_ir(_ir(payload))
    return CompilerIssueCode.requires_specialized_model.value in _codes(result)


def _second_observer(entity_id: str) -> dict[str, object]:
    return {
        "entity_id": entity_id,
        "primitive": "reference_frame",
        "label": "second observer",
        "aliases": [],
        "component_of_entity_id": None,
        "evidence_refs": [],
        "model_confidence": None,
    }


def _observer_evidence(evidence_id: str) -> dict[str, object]:
    return {
        "kind": "text",
        "evidence_id": evidence_id,
        "quote": "The observer's own motion is stated by the source.",
        "source_span": {"start": 0, "end": 49},
        "quantity_span": None,
        "occurrence_index": 0,
    }


# --------------------------------------------------------------------------
# A string that equals an entity id is not a reference to it
# --------------------------------------------------------------------------


def test_a_label_that_repeats_the_entity_id_is_not_a_reference() -> None:
    payload = _observer_payload(modelled=False)
    payload["entities"][0]["label"] = OBSERVER
    assert not _entity_is_modelled(_ir(payload), OBSERVER)
    assert not _deferred(payload)


def test_an_alias_that_repeats_the_entity_id_is_not_a_reference() -> None:
    payload = _observer_payload(modelled=False)
    payload["entities"][0]["aliases"] = [OBSERVER]
    assert not _entity_is_modelled(_ir(payload), OBSERVER)
    assert not _deferred(payload)


def test_an_evidence_id_that_repeats_the_entity_id_is_not_a_reference() -> None:
    payload = _observer_payload(modelled=False)
    payload["source_evidence"] = [_observer_evidence(OBSERVER)]
    payload["quantities"][0]["evidence_refs"] = [OBSERVER]
    assert not _entity_is_modelled(_ir(payload), OBSERVER)
    assert not _deferred(payload)


def test_a_symbol_id_that_repeats_the_entity_id_is_not_a_reference() -> None:
    payload = _observer_payload(modelled=False)
    payload["symbols"] = [_symbol(OBSERVER, "targetQ", LENGTH)]
    payload["quantities"][0]["symbol_id"] = OBSERVER
    assert not _entity_is_modelled(_ir(payload), OBSERVER)


@pytest.mark.parametrize(
    "field", ["raw_value", "raw_unit", "si_unit", "symbol_id", "evidence_refs"]
)
def test_a_written_value_unit_symbol_or_evidence_is_never_a_reference(field) -> None:
    """A value, a unit, a symbol, and an evidence id are not entity references.

    The IR's own validators keep a written value and unit numeric today, so no
    payload can currently smuggle an entity id through them.  Asserting the
    classification rather than a payload states the guarantee that survives a
    later change to those validators.
    """

    assert field not in _ENTITY_REFERENCE_FIELDS["IRQuantity"]


def test_a_quantity_id_that_repeats_the_entity_id_is_not_a_reference() -> None:
    payload = _observer_payload(modelled=False)
    payload["symbols"] = [_symbol("target", OBSERVER, LENGTH)]
    payload["quantities"] = [_quantity(OBSERVER, "target", "velocity", "bodyA", VELOCITY)]
    payload["queries"][0]["target"]["target_quantity_id"] = OBSERVER
    assert not _entity_is_modelled(_ir(payload), OBSERVER)


def test_a_typed_subject_reference_still_counts() -> None:
    """The narrowing must not have thrown away the real signal."""

    assert _entity_is_modelled(_ir(_observer_payload(modelled=True)), OBSERVER)
    assert _deferred(_observer_payload(modelled=True))


def test_an_ambiguity_pointing_at_the_observer_is_not_the_model_referring_to_it() -> None:
    """An unresolved read is a note about the parse, not about the physics."""

    payload = _observer_payload(modelled=False)
    payload["ambiguities"] = [
        {
            "ambiguity_id": "amb1",
            "kind": "interpretation",
            "referenced_ids": [OBSERVER],
            "description": "The reader could not resolve what this names.",
            "blocking": False,
            "evidence_refs": [],
        }
    ]
    assert not _entity_is_modelled(_ir(payload), OBSERVER)


# --------------------------------------------------------------------------
# More than one observer
# --------------------------------------------------------------------------


def test_a_dangling_observer_does_not_shadow_a_modelled_one() -> None:
    """Reading only the first declaration would let a name hide a frame."""

    payload = _observer_payload(modelled=True)
    payload["entities"].insert(1, _second_observer("danglingObserver"))
    assert not _entity_is_modelled(_ir(payload), "danglingObserver")
    assert _entity_is_modelled(_ir(payload), OBSERVER)
    assert _deferred(payload)


def test_two_dangling_observers_still_defer_nothing() -> None:
    payload = _observer_payload(modelled=False)
    payload["entities"].append(_second_observer("danglingTwo"))
    assert not _deferred(payload)


def test_the_issue_names_the_observer_that_actually_makes_it_relative() -> None:
    payload = _observer_payload(modelled=True)
    payload["entities"].insert(1, _second_observer("danglingObserver"))
    result = compile_mechanics_ir(_ir(payload))
    issue = next(
        item
        for item in result.issues
        if item.code is CompilerIssueCode.requires_specialized_model
    )
    assert issue.referenced_id == OBSERVER


def test_a_resting_observer_beside_a_moving_one_does_not_exempt_the_moving_one() -> None:
    payload = _observer_payload(at_rest=True)
    payload["entities"].append(_second_observer("movingObserver"))
    payload["symbols"].append(_symbol("movingV", "movingQ", VELOCITY))
    payload["quantities"].append(
        _quantity(
            "movingQ",
            "movingV",
            "velocity",
            "movingObserver",
            VELOCITY,
            value=7.0,
            unit="m/s",
            evidence_refs=("observerEvidence",),
        )
    )
    assert _deferred(payload)


# --------------------------------------------------------------------------
# What "at rest" has to mean to earn the exemption
# --------------------------------------------------------------------------


def test_rest_at_an_instant_is_not_rest_over_the_question() -> None:
    """A body at rest at one event is moving either side of it."""

    payload = _observer_payload(at_rest=True)
    payload["events"] = [
        {
            "event_id": "instant",
            "kind": "start",
            "subject_ids": [OBSERVER],
            "interval_ids": [],
            "time_quantity_id": None,
            "evidence_refs": [],
        }
    ]
    payload["state_conditions"][0]["event_id"] = "instant"
    assert not _declared_at_rest(_ir(payload), OBSERVER)
    assert _deferred(payload)


def test_rest_over_one_interval_of_several_does_not_cover_the_others() -> None:
    payload = _observer_payload(at_rest=True)
    payload["motion_intervals"] = [
        {
            "interval_id": "segOne",
            "order": 1,
            "subject_ids": ["bodyA"],
            "frame_id": None,
            "start_event_id": None,
            "end_event_id": None,
            "evidence_refs": [],
        },
        {
            "interval_id": "segTwo",
            "order": 2,
            "subject_ids": ["bodyA"],
            "frame_id": None,
            "start_event_id": None,
            "end_event_id": None,
            "evidence_refs": [],
        },
    ]
    payload["state_conditions"][0]["interval_id"] = "segOne"
    assert not _declared_at_rest(_ir(payload), OBSERVER)
    assert _deferred(payload)


def test_rest_over_the_only_interval_still_earns_the_exemption() -> None:
    payload = _observer_payload(at_rest=True)
    payload["motion_intervals"] = [
        {
            "interval_id": "segOne",
            "order": 1,
            "subject_ids": ["bodyA"],
            "frame_id": None,
            "start_event_id": None,
            "end_event_id": None,
            "evidence_refs": [],
        }
    ]
    payload["state_conditions"][0]["interval_id"] = "segOne"
    assert _declared_at_rest(_ir(payload), OBSERVER)
    assert not _deferred(payload)


@pytest.mark.parametrize("frame_type", ["translating", "rotating", "body_fixed"])
def test_rest_in_a_moving_frame_is_not_rest_in_the_ground_frame(frame_type) -> None:
    """At rest relative to something that moves is still moving."""

    payload = _observer_payload(at_rest=True)
    payload["reference_frames"] = [
        {
            "frame_id": "movingFrame",
            "frame_type": frame_type,
            "origin": {"kind": "world"},
            "axes": [
                {
                    "axis": "x",
                    "direction": {
                        "kind": "axis",
                        "frame_id": "movingFrame",
                        "axis": "x",
                        "sign": 1,
                    },
                }
            ],
            "parent_frame_id": None,
            "translating_with_entity_id": "bodyA" if frame_type == "translating" else None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": [],
        }
    ]
    for quantity in payload["quantities"]:
        if quantity["quantity_id"] == "observerQ":
            quantity["frame_id"] = "movingFrame"
    assert not _declared_at_rest(_ir(payload), OBSERVER)
    assert _deferred(payload)


def test_rest_in_the_ground_frame_still_earns_the_exemption() -> None:
    payload = _observer_payload(at_rest=True)
    payload["reference_frames"] = [
        {
            "frame_id": "groundFrame",
            "frame_type": "cartesian_1d",
            "origin": {"kind": "world"},
            "axes": [
                {
                    "axis": "x",
                    "direction": {
                        "kind": "axis",
                        "frame_id": "groundFrame",
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
    for quantity in payload["quantities"]:
        if quantity["quantity_id"] == "observerQ":
            quantity["frame_id"] = "groundFrame"
    assert _declared_at_rest(_ir(payload), OBSERVER)


# --------------------------------------------------------------------------
# An observer the question does not depend on
# --------------------------------------------------------------------------


@pytest.mark.parametrize("query_role", ["mass", "position", "velocity"])
def test_an_observer_unrelated_to_the_query_does_not_change_the_terminal(
    query_role,
) -> None:
    """The same question answers the same way beside a dangling observer."""

    without = compile_mechanics_ir(
        _ir(_observer_payload(query_role=query_role, with_observer=False))
    )
    beside = compile_mechanics_ir(
        _ir(_observer_payload(query_role=query_role, modelled=False))
    )
    assert without.status is beside.status
    assert _codes(without) == _codes(beside)


def test_a_non_kinematic_query_is_unaffected_by_a_modelled_moving_observer() -> None:
    result = compile_mechanics_ir(_ir(_observer_payload(query_role="mass")))
    assert CompilerIssueCode.requires_specialized_model.value not in _codes(result)


# --------------------------------------------------------------------------
# The classification is complete, so a new field cannot change it silently
# --------------------------------------------------------------------------


def _ir_models() -> set[type[BaseModel]]:
    seen: set[type[BaseModel]] = set()

    def walk(model: type[BaseModel]) -> None:
        if model in seen:
            return
        seen.add(model)
        for field in model.model_fields.values():
            stack = [field.annotation]
            while stack:
                annotation = stack.pop()
                if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                    walk(annotation)
                stack.extend(getattr(annotation, "__args__", ()) or ())

    walk(MechanicsProblemIRV1)
    return seen


# Fields that carry a string but name something other than an entity: another
# id namespace, or free text.  Listed so that a *new* field on any IR model
# fails this test rather than silently deciding an observer is modelled.
_NON_ENTITY_STRING_FIELDS: frozenset[str] = frozenset(
    {
        "aliases",
        "ambiguity_id",
        "asset_id",
        "assumption_id",
        "assumption_policy_ref",
        "constraint_id",
        "content_sha256",
        "correction_id",
        "correction_revision",
        "description",
        "end_event_id",
        "entity_id",
        "event_id",
        "evidence_id",
        "evidence_refs",
        "feature_code",
        "frame_id",
        "generalized_coordinate_symbol_ids",
        "hint_id",
        "interaction_id",
        "interval_id",
        "interval_ids",
        "occurs_in_interval_ids",
        "kind",
        "label",
        "language",
        "media_type",
        "missing_information",
        "model_hash",
        "model_id",
        "normalization_policy_version",
        "page_id",
        "parent_asset_id",
        "parent_frame_id",
        "point_id",
        "point_ids",
        "prompt_hash",
        "prompt_version",
        "proposed_unit",
        "prompt_id",
        "quantity_id",
        "quantity_ids",
        "query_id",
        "quote",
        "raw_unit",
        "raw_value",
        "reason",
        "recognized_label",
        "referenced_ids",
        "relation_id",
        "rotating_about_point_id",
        "schema",
        "scope_ids",
        "si_unit",
        "source_text_sha256",
        "start_event_id",
        "state_condition_id",
        "subtype",
        "symbol_id",
        "system_type",
        "target_quantity_id",
        "time_quantity_id",
        "validation_policy_version",
        "version",
        "visual_relation",
        "wrt_symbol_id",
    }
)

# Fields whose values are numbers, enums, booleans, or nested models — never a
# bare identifier string, so they cannot be mistaken for one.
_NON_STRING_FIELDS: frozenset[str] = frozenset(
    {
        "amount",
        "ambiguities",
        "argument",
        "condition",
        "occurrence_index",
        "assumptions",
        "axes",
        "axis",
        "base",
        "bbox",
        "blocking",
        "bottom",
        "branches",
        "component",
        "components",
        "confidence",
        "constraints",
        # Typed contact-normal orientation: an enum, never a frame or
        # entity reference.
        "contact_side",
        "current",
        "denominator",
        "dimension",
        "direction",
        "disposition",
        "entities",
        "events",
        "exponent",
        "expression",
        "factors",
        "figure_dependency",
        "geometry",
        "interactions",
        "items",
        "left",
        "length",
        "level",
        "lower",
        "luminous_intensity",
        "mass",
        "metadata",
        "model_confidence",
        "motion_intervals",
        "numerator",
        # Typed extremal query objective: an enum, never a frame or entity
        # reference.
        "objective",
        "op",
        "operand",
        "order",
        "origin",
        "otherwise",
        "output_dimension",
        "output_unit",
        "page_number",
        "points",
        "polygon",
        "primitive",
        "principle",
        "principle_hints",
        "provenance",
        "proposed_role",
        "proposed_value",
        "quantities",
        "queries",
        "reference_frames",
        "region",
        "relation",
        "right",
        "role",
        "shape",
        "si_value",
        "sign",
        "source_assets",
        "source_evidence",
        "source_span",
        "quantity_span",
        "start",
        "end",
        "state",
        "state_conditions",
        "symbols",
        "target",
        "temperature",
        "terms",
        "time",
        "top",
        "unsupported_features",
        "upper",
        "value",
        "vector_length",
        "x",
        "y",
        "frame_type",
    }
)


def test_every_ir_field_is_classified_as_a_reference_or_explicitly_not_one() -> None:
    """A new typed field must be classified deliberately, not by default.

    The old scan treated every string as a possible reference, which made a
    label enough to defer a problem.  The fix narrows that to declared
    reference fields — and this test is what keeps the narrowing honest: adding
    a field to any IR model fails here until someone decides which it is.
    """

    unclassified: list[str] = []
    for model in _ir_models():
        entity_fields = _ENTITY_REFERENCE_FIELDS.get(model.__name__, frozenset())
        for name in model.model_fields:
            if name in entity_fields:
                continue
            if name in _NON_ENTITY_STRING_FIELDS or name in _NON_STRING_FIELDS:
                continue
            unclassified.append(f"{model.__name__}.{name}")
    assert unclassified == []


def test_every_declared_reference_field_exists_on_its_model() -> None:
    by_name = {model.__name__: model for model in _ir_models()}
    for model_name, fields in _ENTITY_REFERENCE_FIELDS.items():
        assert model_name in by_name, model_name
        assert fields <= set(by_name[model_name].model_fields), model_name


def test_an_entity_declaring_its_own_id_is_not_referring_to_itself() -> None:
    ir = _ir(_observer_payload(modelled=False))
    observer = next(item for item in ir.entities if item.entity_id == OBSERVER)
    assert OBSERVER not in _typed_entity_references(observer)
