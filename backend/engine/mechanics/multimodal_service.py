"""Application service joining safe image ingestion and typed interpretation."""
from __future__ import annotations

import base64
import binascii
from typing import Callable, Sequence

from engine.mechanics.evidence_reconciliation import EvidenceConfirmation
from engine.mechanics.image_security import ImageSecurityError, RawImageInput, sanitize_images
from engine.mechanics.multimodal_api_contracts import (
    EvidenceConflictDescriptor,
    MultimodalEvidenceRequest,
    MultimodalEvidenceResponse,
    SanitizedImageDescriptor,
)
from engine.mechanics.multimodal_modeler import MechanicsMultimodalModeler
from engine.mechanics.multimodal_observability import build_multimodal_metric_event
from engine.mechanics.multimodal_revision import create_initial_revision


class MultimodalRequestError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MultimodalRequestError("invalid_base64", "Image data is not valid base64.") from exc


class MultimodalEvidenceService:
    def __init__(
        self,
        *,
        modeler: MechanicsMultimodalModeler,
        event_sink: Callable[[dict[str, int | str]], None] | None = None,
    ) -> None:
        self._modeler = modeler
        self._event_sink = event_sink

    def process(self, request: MultimodalEvidenceRequest) -> MultimodalEvidenceResponse:
        try:
            images = sanitize_images(
                tuple(
                    RawImageInput(
                        image_id=item.image_id,
                        content=_decode_base64(item.data_base64),
                        declared_media_type=item.media_type,
                    )
                    for item in request.images
                )
            )
        except ImageSecurityError as exc:
            raise MultimodalRequestError(exc.code, str(exc)) from exc

        confirmations = tuple(
            EvidenceConfirmation(
                conflict_id=item.conflict_id,
                conflict_fingerprint=item.conflict_fingerprint,
                chosen_source_id=item.chosen_source_id,
                chosen_candidate_fingerprint=item.chosen_candidate_fingerprint,
            )
            for item in request.confirmations
        )
        outcome = self._modeler.interpret(
            problem_text=request.problem_text,
            images=images,
            confirmations=confirmations,
        )

        revision_id = None
        revision_fingerprint = None
        draft = None
        observations: tuple[dict[str, object], ...] = ()
        if outcome.envelope is not None:
            observations = tuple(
                item.model_dump(mode="json") for item in outcome.envelope.figure_observations
            )
            revision = create_initial_revision(outcome.envelope)
            revision_id = revision.revision_id
            revision_fingerprint = revision.fingerprint
            if outcome.draft_for_runtime is not None:
                draft = outcome.draft_for_runtime.model_dump(mode="json")

        response = MultimodalEvidenceResponse(
            terminal=outcome.terminal.value,
            sanitized_images=tuple(
                SanitizedImageDescriptor(
                    image_id=item.image_id,
                    image_index=item.image_index,
                    content_sha256=item.content_sha256,
                    width=item.width,
                    height=item.height,
                )
                for item in images
            ),
            conflicts=tuple(
                EvidenceConflictDescriptor(
                    conflict_id=item.conflict_id,
                    fingerprint=item.fingerprint,
                    semantic_target_key=item.semantic_target_key,
                    candidate_source_ids=item.candidate_source_ids,
                    candidate_fingerprints=item.candidate_fingerprints,
                )
                for item in outcome.reconciliation.conflicts
            ),
            observations=observations,
            diagnostics=outcome.diagnostics,
            revision_id=revision_id,
            revision_fingerprint=revision_fingerprint,
            draft=draft,
        )
        if self._event_sink is not None:
            metric = build_multimodal_metric_event(
                terminal=outcome.terminal,
                image_count=len(images),
                observation_count=len(observations),
                conflict_count=len(response.conflicts),
                confirmation_count=len(confirmations),
            )
            self._event_sink(metric.as_dict())
        return response


__all__ = ["MultimodalEvidenceService", "MultimodalRequestError"]
