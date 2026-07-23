"""Stage 6 multimodal contract and authority-boundary tests."""
from __future__ import annotations

import hashlib
import math

import pytest
from pydantic import ValidationError

from engine.mechanics.contracts import DRAFT_SCHEMA_NAME, DRAFT_SCHEMA_VERSION, MechanicsProblemDraftV1
from engine.mechanics.multimodal_contracts import (
    EvidenceConflictV1,
    EvidenceReconciliationStatus,
    EvidenceReconciliationV1,
    EvidenceSourceType,
    FigureObservationV1,
    MechanicsCorrectionRequestV1,
    MechanicsModelingEnvelopeV1,
    ObservationKind,
    PolicyEligibility,
    SemanticTargetKind,
)


_DIGEST = hashlib.sha256(b"sanitized-stage6-image").hexdigest()


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


def _draft_payload() -> dict[str, object]:
    return {
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
        "source_assets": [
            {
                "asset_id": "image1",
                "kind": "image",
                "content_sha256": _DIGEST,
                "media_type": "image/png",
                "page_id": None,
                "page_number": None,
                "parent_asset_id": None,
            }
        ],
        "source_evidence": [
            {
                "kind": "figure",
                "evidence_id": "figure1",
                "asset_id": "image1",
                "page_id": None,
                "region": {
                    "bbox": {"left": 0.1, "top": 0.1, "right": 0.4, "bottom": 0.3},
                    "polygon": None,
                },
                "recognized_label": "30 deg",
                "visual_relation": "incline angle",
                "confidence": 0.95,
            }
        ],
        "entities": [
            {
                "entity_id": "body1",
                "primitive": "particle",
                "label": "block",
                "aliases": [],
                "component_of_entity_id": None,
                "evidence_refs": [],
                "model_confidence": None,
            }
        ],
        "points": [],
        "reference_frames": [],
        "motion_intervals": [],
        "events": [],
        "symbols": [],
        "quantities": [],
        "geometry": [],
        "interactions": [],
        "constraints": [],
        "state_conditions": [],
        "queries": [
            {
                "query_id": "query1",
                "target": {
                    "role": "position",
                    "subject_id": "body1",
                    "point_id": None,
                    "frame_id": None,
                    "interval_id": None,
                    "event_id": None,
                    "component": "unspecified",
                    "direction": None,
                    "target_quantity_id": None,
                },
                "output_unit": "m",
                "output_dimension": _dimension(length=1),
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


def _observation_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "dynatutor.figure_observation",
        "version": "1.0",
        "image_id": "image1",
        "image_index": 0,
        "sanitized_content_sha256": _DIGEST,
        "width": 640,
        "height": 480,
        "observation_id": "obs1",
        "observation_kind": "angle_annotation",
        "semantic_target": {
            "kind": "quantity",
            "target_id": "angle1",
            "role": "angle",
            "component": None,
            "relation_kind": None,
        },
        "region": {
            "kind": "bbox",
            "bbox": {"left": 0.1, "top": 0.1, "right": 0.4, "bottom": 0.3},
        },
        "observed_label": "30 deg",
        "observed_value": "30",
        "unit_candidate": "deg",
        "direction_candidate": None,
        "relation_participant_ids": [],
        "ambiguity_status": "resolved",
        "alternatives": [],
        "visibility": "visible",
        "evidence_origin": "FIGURE_EXPLICIT_LABEL",
        "provenance": "FIGURE_EXPLICIT_LABEL",
        "diagnostic_confidence": 0.95,
        "policy_eligibility": "automatic",
        "source_digest": _DIGEST,
        "source_version": "figure-observer-v1",
        "evidence_id": "figure1",
    }
    payload.update(updates)
    return payload


def _observation(**updates: object) -> FigureObservationV1:
    return FigureObservationV1.model_validate(_observation_payload(**updates))


def _envelope_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "dynatutor.mechanics_modeling_envelope",
        "version": "1.0",
        "draft": _draft_payload(),
        "figure_observations": [_observation_payload()],
        "text_evidence": [],
        "proposed_bindings": [
            {
                "binding_id": "binding1",
                "observation_id": "obs1",
                "evidence_id": "figure1",
                "semantic_fact_id": "angle1",
                "semantic_target": _observation_payload()["semantic_target"],
                "binding_kind": "supplies_value",
            }
        ],
        "unresolved_ambiguities": [],
        "model_diagnostics": [],
    }
    payload.update(updates)
    return payload


def _fingerprint() -> str:
    return hashlib.sha256(b"stage6-revision").hexdigest()


def test_figure_observation_contract_has_closed_typed_ontology() -> None:
    observation = _observation()
    assert observation.observation_kind is ObservationKind.angle_annotation
    assert observation.semantic_target.kind is SemanticTargetKind.quantity
    assert observation.policy_eligibility is PolicyEligibility.automatic
    assert len(ObservationKind) == 28
    assert FigureObservationV1.model_validate(
        observation.model_dump(mode="python")
    ) == observation


@pytest.mark.parametrize(
    "region",
    [
        {"kind": "bbox", "bbox": {"left": -0.1, "top": 0.1, "right": 0.4, "bottom": 0.3}},
        {"kind": "bbox", "bbox": {"left": 0.4, "top": 0.1, "right": 0.4, "bottom": 0.3}},
        {"kind": "line", "start": {"x": 0.2, "y": 0.2}, "end": {"x": 0.2, "y": 0.2}},
        {"kind": "polygon", "points": [{"x": 0.0, "y": 0.0}, {"x": 1.1, "y": 0.0}, {"x": 0.0, "y": 1.0}]},
    ],
)
def test_figure_observation_rejects_invalid_regions(region: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _observation(region=region)


def test_figure_observation_rejects_non_finite_coordinates() -> None:
    payload = _observation_payload()
    payload["region"] = {
        "kind": "bbox",
        "bbox": {"left": 0.1, "top": 0.1, "right": math.inf, "bottom": 0.3},
    }
    with pytest.raises(ValidationError):
        FigureObservationV1.model_validate(payload)


def test_confidence_is_diagnostic_and_cannot_authorize_low_confidence_evidence() -> None:
    with pytest.raises(ValidationError, match="low-confidence"):
        _observation(diagnostic_confidence=0.79)
    confirmed = _observation(
        diagnostic_confidence=0.01,
        policy_eligibility="confirmation_required",
    )
    assert confirmed.diagnostic_confidence == 0.01


def test_figure_convention_cannot_be_silently_promoted() -> None:
    with pytest.raises(ValidationError, match="convention"):
        _observation(
            evidence_origin="FIGURE_CONVENTION",
            provenance="FIGURE_CONVENTION",
            policy_eligibility="automatic",
        )
    convention = _observation(
        evidence_origin="FIGURE_CONVENTION",
        provenance="FIGURE_CONVENTION",
        policy_eligibility="convention_only",
    )
    assert convention.evidence_origin is EvidenceSourceType.figure_convention


def test_modeling_envelope_round_trips_and_binds_observation_to_sanitized_asset() -> None:
    envelope = MechanicsModelingEnvelopeV1.model_validate(_envelope_payload())
    assert isinstance(envelope.draft, MechanicsProblemDraftV1)
    assert envelope.figure_observations[0].image_id == "image1"
    assert envelope.proposed_bindings[0].evidence_id == "figure1"
    assert MechanicsModelingEnvelopeV1.model_validate(
        envelope.model_dump(mode="python")
    ) == envelope


def test_modeling_envelope_rejects_digest_mismatch_and_unknown_references() -> None:
    bad = _envelope_payload()
    bad["figure_observations"][0]["sanitized_content_sha256"] = hashlib.sha256(b"other").hexdigest()
    with pytest.raises(ValidationError, match="digest"):
        MechanicsModelingEnvelopeV1.model_validate(bad)
    bad = _envelope_payload()
    bad["proposed_bindings"][0]["evidence_id"] = "missing"
    with pytest.raises(ValidationError, match="resolve"):
        MechanicsModelingEnvelopeV1.model_validate(bad)


@pytest.mark.parametrize(
    "field",
    [
        "final_answer",
        "executable_equation",
        "selected_solver",
        "selected_root",
        "verification_result",
        "legacy_route",
    ],
)
def test_modeling_envelope_rejects_answer_and_execution_authority(field: str) -> None:
    payload = _envelope_payload()
    payload[field] = "forbidden"
    with pytest.raises(ValidationError, match="forbidden"):
        MechanicsModelingEnvelopeV1.model_validate(payload)


def test_correction_contract_rejects_direct_answer_and_graph_patch() -> None:
    base = {
        "schema": "dynatutor.mechanics_correction_request",
        "version": "1.0",
        "request_id": "request1",
        "base_revision_id": "revision0",
        "base_revision_fingerprint": _fingerprint(),
        "operations": [
            {
                "kind": "replace_quantity_value",
                "operation_id": "operation1",
                "quantity_id": "mass1",
                "raw_value": "5",
                "raw_unit": "kg",
            }
        ],
        "client_request_id": "client1",
    }
    request = MechanicsCorrectionRequestV1.model_validate(base)
    assert request.operations[0].kind.value == "replace_quantity_value"
    for forbidden in ("final_answer", "selected_solver", "verification_result"):
        bad = dict(base)
        bad[forbidden] = "patched"
        with pytest.raises(ValidationError, match="correction cannot patch"):
            MechanicsCorrectionRequestV1.model_validate(bad)


def test_conflict_contract_binds_values_in_evidence_order() -> None:
    payload = {
        "schema": "dynatutor.evidence_conflict",
        "version": "1.0",
        "conflict_id": "conflict1",
        "semantic_target": {
            "kind": "quantity",
            "target_id": "angle1",
            "role": "angle",
            "component": None,
            "relation_kind": None,
        },
        "competing_evidence_ids": ["text1", "figure1"],
        "conflict_kind": "value_mismatch",
        "competing_values": [
            {
                "source_id": "text1",
                "source_type": "TEXT_EXPLICIT",
                "semantic_target": {
                    "kind": "quantity",
                    "target_id": "angle1",
                    "role": "angle",
                    "component": None,
                    "relation_kind": None,
                },
                "raw_value": "30",
                "raw_unit": "deg",
                "normalized_value": "30",
                "normalized_unit": "deg",
                "direction_candidate": None,
            },
            {
                "source_id": "figure1",
                "source_type": "FIGURE_EXPLICIT_LABEL",
                "semantic_target": {
                    "kind": "quantity",
                    "target_id": "angle1",
                    "role": "angle",
                    "component": None,
                    "relation_kind": None,
                },
                "raw_value": "35",
                "raw_unit": "deg",
                "normalized_value": "35",
                "normalized_unit": "deg",
                "direction_candidate": None,
            },
        ],
        "impact_on_compilation": "blocks_compilation",
        "allowed_resolution_actions": ["use_text", "use_figure", "enter_value"],
        "safe_user_summary": "문장과 그림의 각도가 서로 다릅니다.",
        "revision_fingerprint": _fingerprint(),
    }
    conflict = EvidenceConflictV1.model_validate(payload)
    assert tuple(item.source_id for item in conflict.competing_values) == (
        "text1",
        "figure1",
    )
    payload["competing_values"] = list(reversed(payload["competing_values"]))
    with pytest.raises(ValidationError, match="order"):
        EvidenceConflictV1.model_validate(payload)


def test_reconciliation_never_accepts_unresolved_conflict_or_confirmation() -> None:
    base = {
        "schema": "dynatutor.evidence_reconciliation",
        "version": "1.0",
        "policy_version": "mechanics-multimodal-evidence-v1",
        "status": "accepted",
        "accepted_evidence_ids": ["figure1"],
        "corroborating_evidence_ids": [],
        "duplicate_evidence_ids": [],
        "ambiguous_evidence_ids": [],
        "insufficient_evidence_ids": [],
        "rejected_evidence_ids": [],
        "accepted_figure_evidence_ids": ["figure1"],
        "conflicts": [],
        "confirmations": [],
        "revision_fingerprint": _fingerprint(),
    }
    accepted = EvidenceReconciliationV1.model_validate(base)
    assert accepted.status is EvidenceReconciliationStatus.accepted
    bad = dict(base)
    bad["ambiguous_evidence_ids"] = ["figure1"]
    with pytest.raises(ValidationError, match="unresolved"):
        EvidenceReconciliationV1.model_validate(bad)
