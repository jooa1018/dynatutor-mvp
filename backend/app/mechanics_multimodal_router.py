"""Additive FastAPI route for source-grounded multimodal evidence."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from engine.mechanics.multimodal_api_contracts import (
    MultimodalEvidenceRequest,
    MultimodalEvidenceResponse,
)
from engine.mechanics.multimodal_modeler import MechanicsMultimodalModeler
from engine.mechanics.multimodal_service import MultimodalEvidenceService, MultimodalRequestError

router = APIRouter(tags=["mechanics-multimodal"])


@router.post(
    "/api/mechanics/multimodal/evidence",
    response_model=MultimodalEvidenceResponse,
    status_code=status.HTTP_200_OK,
)
def interpret_mechanics_multimodal_evidence(
    payload: MultimodalEvidenceRequest,
    request: Request,
) -> MultimodalEvidenceResponse:
    generator = getattr(request.app.state, "mechanics_multimodal_envelope_generator", None)
    if generator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "multimodal_modeler_unavailable",
                "message": "The multimodal interpretation adapter is not configured.",
            },
        )
    event_sink = getattr(request.app.state, "mechanics_multimodal_event_sink", None)
    service = MultimodalEvidenceService(
        modeler=MechanicsMultimodalModeler(generator),
        event_sink=event_sink,
    )
    try:
        return service.process(payload)
    except MultimodalRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_modeling_envelope",
                "message": "The generated modeling envelope did not satisfy the Stage 6 contract.",
            },
        ) from exc


__all__ = ["router"]
