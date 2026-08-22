"""Mass-cancelled banked/flat circular-road design invariants."""

from __future__ import annotations

import math
import pytest

from engine.mechanics.contracts import MechanicsProblemDraftV1
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjectionTerminal,
)
from evaluation.phase56_stage7.lane_b_runner import LaneBTerminal, run_lane_b_case


pytestmark = pytest.mark.slow


def _dimension(*, length: int = 0, time: int = 0) -> dict[str, int]:
    return {
        "mass": 0,
        "length": length,
        "time": time,
        "current": 0,
        "temperature": 0,
        "amount": 0,
        "luminous_intensity": 0,
    }


def _evidence(
    text: str, evidence_id: str, quote: str, quantity_text: str | None = None
) -> dict:
    start = text.index(quote)
    record = {
        "kind": "text",
        "evidence_id": evidence_id,
        "quote": quote,
        "source_span": {"start": start, "end": start + len(quote)},
        "occurrence_index": 0,
    }
    if quantity_text is not None:
        quantity_start = text.index(quantity_text, start, start + len(quote))
        record["quantity_span"] = {
            "start": quantity_start,
            "end": quantity_start + len(quantity_text),
        }
    return record


def _quantity(
    quantity_id: str,
    role: str,
    subject_id: str,
    dimension: dict[str, int],
    *,
    value: str | None,
    unit: str | None,
    evidence_id: str | None,
    interval_id: str | None,
    event_id: str | None = None,
    component: str = "unspecified",
) -> dict:
    return {
        "quantity_id": quantity_id,
        "symbol_id": f"sym_{quantity_id}",
        "role": role,
        "subject_id": subject_id,
        "point_id": None,
        "frame_id": None,
        "interval_id": interval_id,
        "event_id": event_id,
        "component": component,
        "direction": None,
        "shape": "scalar",
        "dimension": dimension,
        "provenance": "explicit_source" if value is not None else "unknown",
        "evidence_refs": [evidence_id] if evidence_id else [],
        "raw_value": value,
        "raw_unit": unit,
        "assumption_policy_ref": None,
        "correction_id": None,
        "model_confidence": None,
    }


def _payload(kind: str) -> tuple[str, dict]:
    flat = kind == "flat"
    text = (
        "radius 60 m; coefficient 0.35; gravity 9.81 m/s^2; "
        "horizontal road; maximum speed"
        if flat
        else "radius 70 m; angle 18 deg; gravity 9.81 m/s^2; frictionless bank"
    )
    design_id = "qty_coefficient" if flat else "qty_angle"
    design_role = "coefficient_friction" if flat else "angle"
    design_value = "0.35" if flat else "18"
    design_unit = "" if flat else "deg"
    design_quote = "coefficient 0.35" if flat else "angle 18 deg"
    evidence = [
        _evidence(
            text,
            "ev_radius",
            "radius 60 m" if flat else "radius 70 m",
            "60 m" if flat else "70 m",
        ),
        _evidence(
            text,
            "ev_design",
            design_quote,
            "0.35" if flat else "18 deg",
        ),
        _evidence(text, "ev_gravity", "gravity 9.81 m/s^2"),
    ]
    if flat:
        evidence.extend(
            [
                _evidence(text, "ev_horizontal", "horizontal road"),
                _evidence(text, "ev_objective", "maximum speed"),
            ]
        )
    else:
        evidence.append(_evidence(text, "ev_frictionless", "frictionless bank"))

    quantities = [
        _quantity(
            "qty_radius",
            "radius",
            "body",
            _dimension(length=1),
            value="60" if flat else "70",
            unit="m",
            evidence_id="ev_radius",
            interval_id="motion",
        ),
        _quantity(
            design_id,
            design_role,
            "road",
            _dimension(),
            value=design_value,
            unit=design_unit,
            evidence_id="ev_design",
            interval_id=None,
        ),
        _quantity(
            "qty_speed",
            "velocity",
            "body",
            _dimension(length=1, time=-1),
            value=None,
            unit=None,
            evidence_id=None,
            interval_id="motion",
            event_id="finish",
            component="magnitude",
        ),
    ]
    frames = []
    if flat:
        frames = [
            {
                "frame_id": "world",
                "frame_type": "cartesian_2d",
                "origin": {"kind": "world"},
                "axes": [
                    {"axis": "x", "direction": {"kind": "axis", "frame_id": "world", "axis": "x", "sign": 1}},
                    {"axis": "y", "direction": {"kind": "axis", "frame_id": "world", "axis": "y", "sign": 1}},
                ],
                "parent_frame_id": None,
                "translating_with_entity_id": None,
                "rotating_about_point_id": None,
                "generalized_coordinate_symbol_ids": [],
                "evidence_refs": ["ev_horizontal"],
            },
            {
                "frame_id": "support",
                "frame_type": "cartesian_2d",
                "origin": {"kind": "entity", "entity_id": "road"},
                "axes": [
                    {"axis": "tangent", "direction": {"kind": "axis", "frame_id": "world", "axis": "x", "sign": 1}},
                    {"axis": "normal", "direction": {"kind": "axis", "frame_id": "world", "axis": "y", "sign": 1}},
                ],
                "parent_frame_id": "world",
                "translating_with_entity_id": None,
                "rotating_about_point_id": None,
                "generalized_coordinate_symbol_ids": [],
                "evidence_refs": ["ev_horizontal"],
            },
        ]
    assumptions = [
        {
            "assumption_id": "asm_gravity",
            "kind": "constant_gravity",
            "subject_id": "body",
            "interval_id": "motion",
            "disposition": "approved",
            "proposed_role": "gravity",
            "proposed_value": "9.81",
            "proposed_unit": "m/s^2",
            "reason": "source-stated gravity",
            "evidence_refs": ["ev_gravity"],
        }
    ]
    if not flat:
        assumptions.append(
            {
                "assumption_id": "asm_frictionless",
                "kind": "frictionless",
                "subject_id": "body",
                "interval_id": "motion",
                "disposition": "approved",
                "proposed_role": "coefficient_friction",
                "proposed_value": "0",
                "proposed_unit": "",
                "reason": "source-stated frictionless bank",
                "evidence_refs": ["ev_frictionless"],
            }
        )
    payload = {
        "schema": "dynatutor.mechanics_problem_draft",
        "version": "1.0",
        "metadata": {"language": "ko", "correction_revision": 0},
        "source_assets": [],
        "source_evidence": evidence,
        "entities": [
            {"entity_id": "body", "primitive": "rigid_body", "aliases": [], "evidence_refs": []},
            {"entity_id": "road", "primitive": "surface", "aliases": [], "evidence_refs": []},
        ],
        "points": [],
        "reference_frames": frames,
        "motion_intervals": [
            {"interval_id": "motion", "subject_ids": ["body"], "frame_id": None, "start_event_id": "start", "end_event_id": "finish", "order": 1, "evidence_refs": []}
        ],
        "events": [
            {"event_id": "start", "kind": "start", "subject_ids": ["body"], "interval_ids": ["motion"], "occurs_in_interval_ids": [], "time_quantity_id": None, "evidence_refs": []},
            {"event_id": "finish", "kind": "finish", "subject_ids": ["body"], "interval_ids": ["motion"], "occurs_in_interval_ids": [], "time_quantity_id": None, "evidence_refs": []},
        ],
        "symbols": [
            {"symbol_id": item["symbol_id"], "quantity_id": item["quantity_id"], "dimension": item["dimension"], "shape": "scalar"}
            for item in quantities
        ],
        "geometry": [],
        "interactions": [
            {"interaction_id": "contact", "kind": "contact", "participant_ids": ["body", "road"], "point_ids": [], "frame_id": None, "interval_id": None, "event_id": None, "quantity_ids": [], "evidence_refs": [], "contact_side": None}
        ],
        "constraints": [],
        "state_conditions": [],
        "quantities": quantities,
        "queries": [
            {"query_id": "query", "target": {"role": "velocity", "subject_id": "body", "point_id": None, "frame_id": None, "interval_id": "motion", "event_id": "finish", "component": "magnitude", "direction": None, "target_quantity_id": "qty_speed"}, "output_unit": "m/s", "output_dimension": _dimension(length=1, time=-1), "shape": "scalar", "evidence_refs": ["ev_objective"] if flat else [], "objective": "maximum" if flat else None}
        ],
        "principle_hints": [],
        "assumptions": assumptions,
        "ambiguities": [],
        "figure_dependency": {"level": "none", "missing_information": [], "evidence_refs": []},
        "unsupported_features": [],
    }
    return text, payload


class _Projected:
    def __init__(self, text: str, draft: MechanicsProblemDraftV1, approved: tuple[str, ...]):
        self.terminal = DraftProjectionTerminal.projected
        self.problem_text = text
        self.draft = draft
        self.sanitized_reason = None
        self.environment_scoped_quantity_ids = tuple(
            item.quantity_id for item in draft.quantities if item.subject_id == "road"
        )
        self.segment_internal_event_ids = ()
        self.approvable_assumption_ids = approved
        self.known_symbol_ids = tuple(
            item.symbol_id for item in draft.quantities if item.raw_value is not None
        )
        self.unknown_symbol_ids = ("sym_qty_speed",)
        self.event_authority_gaps = ()

    @property
    def projected(self) -> bool:
        return True


def _run(kind: str, mutate=None):
    text, payload = _payload(kind)
    if mutate is not None:
        mutate(payload)
    draft = MechanicsProblemDraftV1.model_validate(payload)
    approved = tuple(item["assumption_id"] for item in payload["assumptions"])
    result = run_lane_b_case(
        _Projected(text, draft, approved), execution_token=f"curve-{kind}-test"
    )
    return draft, result


@pytest.mark.parametrize("kind", ("banked", "flat"))
def test_curve_design_invariant_solves_without_inventing_mass(kind: str) -> None:
    draft, result = _run(kind)
    assert not any(item.role.value == "mass" for item in draft.quantities)
    assert result.terminal is LaneBTerminal.solved
    expected = (
        math.sqrt(9.81 * 60.0 * 0.35)
        if kind == "flat"
        else math.sqrt(9.81 * 70.0 * math.tan(math.radians(18.0)))
    )
    assert result.answer_value_si == pytest.approx(expected)
    assert result.verified_candidate_count == 1
    assert result.applied_law_ids == (
        (
            "flat_curve_maximum_speed_invariant"
            if kind == "flat"
            else "banked_curve_design_speed_invariant"
        ),
        "translational_speed_nonnegative",
    )


def test_flat_curve_requires_evidenced_maximum_objective() -> None:
    def remove_objective(payload: dict) -> None:
        payload["queries"][0]["objective"] = None
        payload["queries"][0]["evidence_refs"] = []

    draft, result = _run("flat", remove_objective)
    plan = plan_complete_profile(
        ProfileId.curve_design_speed,
        draft,
        approved_assumption_ids=("asm_gravity",),
    )
    assert plan.disposition is PlanDisposition.not_applicable
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_banked_curve_requires_frictionless_authority() -> None:
    def remove_authority(payload: dict) -> None:
        payload["assumptions"] = [payload["assumptions"][0]]

    draft, result = _run("banked", remove_authority)
    plan = plan_complete_profile(
        ProfileId.curve_design_speed,
        draft,
        approved_assumption_ids=("asm_gravity",),
    )
    assert plan.disposition is PlanDisposition.not_applicable
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_identifiers_metadata_and_order_are_not_curve_authority() -> None:
    _, baseline = _run("flat")

    def reorder(payload: dict) -> None:
        payload["entities"].reverse()
        payload["quantities"].reverse()
        payload["symbols"].reverse()
        payload["events"].reverse()
        payload["metadata"]["system_type"] = "banked_curve_no_friction"

    _, variant = _run("flat", reorder)
    assert variant.terminal is LaneBTerminal.solved
    assert variant.answer_value_si == pytest.approx(baseline.answer_value_si)
