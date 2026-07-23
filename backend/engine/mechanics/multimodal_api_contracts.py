"""Strict wire contracts for the additive Stage 6 multimodal endpoint."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictWireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EncodedImageInput(StrictWireModel):
    image_id: str = Field(min_length=1, max_length=128)
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    data_base64: str = Field(min_length=1, max_length=12_000_000, repr=False)


class ConfirmationInput(StrictWireModel):
    conflict_id: str = Field(min_length=1, max_length=128)
    conflict_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    chosen_source_id: str = Field(min_length=1, max_length=256)
    chosen_candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class MultimodalEvidenceRequest(StrictWireModel):
    problem_text: str = Field(min_length=1, max_length=30_000)
    images: tuple[EncodedImageInput, ...] = Field(default=(), max_length=4)
    confirmations: tuple[ConfirmationInput, ...] = Field(default=(), max_length=64)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def unique_ids(self) -> "MultimodalEvidenceRequest":
        image_ids = [item.image_id for item in self.images]
        if len(set(image_ids)) != len(image_ids):
            raise ValueError("image_id values must be unique")
        conflict_ids = [item.conflict_id for item in self.confirmations]
        if len(set(conflict_ids)) != len(conflict_ids):
            raise ValueError("one confirmation is allowed per conflict")
        return self


class SanitizedImageDescriptor(StrictWireModel):
    image_id: str
    image_index: int = Field(ge=0, le=3)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0, le=2048)
    height: int = Field(gt=0, le=2048)
    media_type: Literal["image/png"] = "image/png"


class EvidenceConflictDescriptor(StrictWireModel):
    conflict_id: str
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_target_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_source_ids: tuple[str, ...]
    candidate_fingerprints: tuple[str, ...]


class MultimodalEvidenceResponse(StrictWireModel):
    schema: Literal["dynatutor.mechanics_multimodal_response"] = "dynatutor.mechanics_multimodal_response"
    version: Literal["1.0"] = "1.0"
    terminal: Literal["ready", "confirmation_required", "blocked"]
    sanitized_images: tuple[SanitizedImageDescriptor, ...] = ()
    conflicts: tuple[EvidenceConflictDescriptor, ...] = ()
    observations: tuple[dict[str, Any], ...] = ()
    diagnostics: tuple[str, ...] = ()
    revision_id: str | None = None
    revision_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    draft: dict[str, Any] | None = None

    @model_validator(mode="after")
    def authority_boundary(self) -> "MultimodalEvidenceResponse":
        if self.terminal != "ready" and self.draft is not None:
            raise ValueError("draft cannot be exposed before reconciliation is ready")
        if self.terminal == "ready" and self.conflicts:
            raise ValueError("ready responses cannot contain unresolved conflicts")
        return self


__all__ = [
    "ConfirmationInput",
    "EncodedImageInput",
    "EvidenceConflictDescriptor",
    "MultimodalEvidenceRequest",
    "MultimodalEvidenceResponse",
    "SanitizedImageDescriptor",
]
