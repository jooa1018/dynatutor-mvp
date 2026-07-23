from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import Sequence

from PIL import Image, ImageDraw

from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
)
from engine.mechanics.image_security import SanitizedImage
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.multimodal_contracts import MechanicsModelingEnvelopeV1


FORCE_PROBLEM_TEXT = (
    "A 2 kg particle has a 10 N force in the +x direction. "
    "Find its acceleration along +x."
)
MASS = DimensionVector(mass=1)
FORCE = DimensionVector(mass=1, length=1, time=-2)
ACCELERATION = DimensionVector(length=1, time=-2)


def synthetic_png(*, label: str = "F", width: int = 320, height: int = 240) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 100, 140, 170), outline="black", width=4)
    draw.line((140, 135, 260, 135), fill="black", width=5)
    draw.polygon(((260, 135), (235, 122), (235, 148)), fill="black")
    draw.text((175, 100), label, fill="black")
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _text_evidence(
    source_text: str,
    *,
    evidence_id: str,
    quote: str,
    quantity_token: str,
) -> dict[str, object]:
    start = source_text.index(quote)
    quantity_start = start + quote.index(quantity_token)
    return {
        "kind": "text",
        "evidence_id": evidence_id,
        "quote": quote,
        "source_span": {"start": start, "end": start + len(quote)},
        "quantity_span": {
            "start": quantity_start,
            "end": quantity_start + len(quantity_token),
        },
        "occurrence_index": source_text[:start].count(quote),
    }


def _symbol(
    symbol_id: str,
    quantity_id: str,
    dimension: DimensionVector,
) -> dict[str, object]:
    return {
        "symbol_id": symbol_id,
        "quantity_id": quantity_id,
        "dimension": dimension.model_dump(mode="json"),
        "shape": "scalar",
        "vector_length": None,
    }


def force_draft_payload(
    *,
    problem_text: str = FORCE_PROBLEM_TEXT,
    force_value: str = "10",
    images: Sequence[SanitizedImage] = (),
) -> dict[str, object]:
    mass_quote = "2 kg"
    force_quote = f"a {force_value} N force in the +x direction"
    source_assets: list[dict[str, object]] = []
    source_evidence: list[dict[str, object]] = [
        _text_evidence(
            problem_text,
            evidence_id="massEvidence",
            quote=mass_quote,
            quantity_token=mass_quote,
        ),
        _text_evidence(
            problem_text,
            evidence_id="forceEvidence",
            quote=force_quote,
            quantity_token=f"{force_value} N",
        ),
    ]
    for image in images:
        evidence_id = f"figureEvidence{image.image_index}"
        source_assets.append(
            {
                "asset_id": image.image_id,
                "kind": "image",
                "content_sha256": image.content_sha256,
                "media_type": "image/png",
                "page_id": None,
                "page_number": None,
                "parent_asset_id": None,
            }
        )
        source_evidence.append(
            {
                "kind": "figure",
                "evidence_id": evidence_id,
                "asset_id": image.image_id,
                "page_id": None,
                "region": {
                    "bbox": {
                        "left": 0.1,
                        "top": 0.35,
                        "right": 0.9,
                        "bottom": 0.75,
                    },
                    "polygon": None,
                },
                "recognized_label": "force diagram",
                "visual_relation": "particle and applied force",
                "confidence": 0.95,
            }
        )

    payload: dict[str, object] = {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnostic-only-label",
            "subtype": None,
            "model_id": "stage6-fake-provider",
            "model_hash": None,
            "prompt_hash": None,
            "source_text_sha256": sha256(problem_text.encode("utf-8")).hexdigest(),
            "model_confidence": 0.95,
        },
        "source_assets": source_assets,
        "source_evidence": source_evidence,
        "entities": [
            {
                "entity_id": "bodyA",
                "primitive": "particle",
                "label": "particle",
                "aliases": [],
                "component_of_entity_id": None,
                "evidence_refs": [],
                "model_confidence": 0.95,
            }
        ],
        "points": [],
        "reference_frames": [
            {
                "frame_id": "frame1",
                "frame_type": "cartesian_1d",
                "origin": {"kind": "world"},
                "axes": [
                    {
                        "axis": "x",
                        "direction": {
                            "kind": "axis",
                            "frame_id": "frame1",
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
        ],
        "motion_intervals": [
            {
                "interval_id": "interval1",
                "order": 1,
                "subject_ids": ["bodyA"],
                "frame_id": "frame1",
                "start_event_id": None,
                "end_event_id": None,
                "evidence_refs": [],
            }
        ],
        "events": [],
        "symbols": [
            _symbol("mA", "massA", MASS),
            _symbol("fA", "forceA", FORCE),
            _symbol("aA", "accelerationA", ACCELERATION),
        ],
        "quantities": [
            {
                "quantity_id": "massA",
                "symbol_id": "mA",
                "role": "mass",
                "subject_id": "bodyA",
                "shape": "scalar",
                "dimension": MASS.model_dump(mode="json"),
                "provenance": "explicit_source",
                "evidence_refs": ["massEvidence"],
                "raw_value": "2",
                "raw_unit": "kg",
            },
            {
                "quantity_id": "forceA",
                "symbol_id": "fA",
                "role": "force",
                "subject_id": "bodyA",
                "frame_id": "frame1",
                "interval_id": "interval1",
                "component": "x",
                "direction": {
                    "kind": "axis",
                    "frame_id": "frame1",
                    "axis": "x",
                    "sign": 1,
                },
                "shape": "scalar",
                "dimension": FORCE.model_dump(mode="json"),
                "provenance": "explicit_source",
                "evidence_refs": ["forceEvidence"],
                "raw_value": force_value,
                "raw_unit": "N",
            },
            {
                "quantity_id": "accelerationA",
                "symbol_id": "aA",
                "role": "acceleration",
                "subject_id": "bodyA",
                "frame_id": "frame1",
                "interval_id": "interval1",
                "component": "x",
                "direction": {
                    "kind": "axis",
                    "frame_id": "frame1",
                    "axis": "x",
                    "sign": 1,
                },
                "shape": "scalar",
                "dimension": ACCELERATION.model_dump(mode="json"),
                "provenance": "inferred",
                "evidence_refs": [],
            },
        ],
        "geometry": [],
        "interactions": [
            {
                "interaction_id": "appliedForce",
                "kind": "applied_force",
                "participant_ids": ["bodyA"],
                "point_ids": [],
                "frame_id": "frame1",
                "interval_id": "interval1",
                "event_id": None,
                "quantity_ids": ["forceA"],
                "evidence_refs": ["forceEvidence"],
            }
        ],
        "constraints": [],
        "state_conditions": [],
        "queries": [
            {
                "query_id": "queryA",
                "target": {
                    "role": "acceleration",
                    "subject_id": "bodyA",
                    "point_id": None,
                    "frame_id": "frame1",
                    "interval_id": "interval1",
                    "event_id": None,
                    "component": "x",
                    "direction": {
                        "kind": "axis",
                        "frame_id": "frame1",
                        "axis": "x",
                        "sign": 1,
                    },
                    "target_quantity_id": "accelerationA",
                },
                "output_unit": "m/s^2",
                "output_dimension": ACCELERATION.model_dump(mode="json"),
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
    return payload


def force_envelope(
    *,
    problem_text: str = FORCE_PROBLEM_TEXT,
    images: Sequence[SanitizedImage] = (),
) -> MechanicsModelingEnvelopeV1:
    draft_payload = force_draft_payload(problem_text=problem_text, images=images)
    observations: list[dict[str, object]] = []
    for image in images:
        evidence_id = f"figureEvidence{image.image_index}"
        observations.append(
            {
                "schema": "dynatutor.figure_observation",
                "version": "1.0",
                "image_id": image.image_id,
                "image_index": image.image_index,
                "sanitized_content_sha256": image.content_sha256,
                "width": image.width,
                "height": image.height,
                "observation_id": f"observation{image.image_index}",
                "observation_kind": "entity_label",
                "semantic_target": {
                    "kind": "entity",
                    "target_id": "bodyA",
                    "role": "particle",
                    "component": None,
                    "relation_kind": None,
                },
                "region": {
                    "kind": "bbox",
                    "bbox": {
                        "left": 0.1,
                        "top": 0.35,
                        "right": 0.9,
                        "bottom": 0.75,
                    },
                },
                "observed_label": "particle",
                "observed_value": None,
                "unit_candidate": None,
                "direction_candidate": None,
                "relation_participant_ids": [],
                "ambiguity_status": "resolved",
                "alternatives": [],
                "visibility": "visible",
                "evidence_origin": "FIGURE_EXPLICIT_LABEL",
                "provenance": "FIGURE_EXPLICIT_LABEL",
                "diagnostic_confidence": 0.95,
                "policy_eligibility": "automatic",
                "source_digest": image.content_sha256,
                "source_version": "stage6-fixture-v1",
                "evidence_id": evidence_id,
            }
        )
    return MechanicsModelingEnvelopeV1.model_validate(
        {
            "schema": "dynatutor.mechanics_modeling_envelope",
            "version": "1.0",
            "draft": MechanicsProblemDraftV1.model_validate(draft_payload),
            "figure_observations": observations,
            "text_evidence": [],
            "proposed_bindings": [],
            "unresolved_ambiguities": [],
            "model_diagnostics": [],
        }
    )


__all__ = [
    "ACCELERATION",
    "FORCE_PROBLEM_TEXT",
    "force_draft_payload",
    "force_envelope",
    "synthetic_png",
]
