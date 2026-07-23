"""Application service joining safe ingestion, revisions, and deterministic solve."""
from __future__ import annotations

import base64
import binascii
import time
from typing import Callable

from engine.mechanics.evidence_reconciliation import EvidenceConfirmation
from engine.mechanics.image_security import ImageSecurityError, RawImageInput, SanitizedImage, sanitize_images
from engine.mechanics.multimodal_api_contracts import (
    EvidenceConflictDescriptor, MultimodalEvidenceRequest, MultimodalEvidenceResponse,
    RevisionConfirmationRequest, SanitizedImageDescriptor,
)
from engine.mechanics.multimodal_contracts import MechanicsCorrectionRequestV1
from engine.mechanics.multimodal_modeler import MechanicsMultimodalModeler
from engine.mechanics.multimodal_observability import build_multimodal_metric_event
from engine.mechanics.multimodal_revision import ModelingRevision, RevisionError, RevisionStore
from engine.mechanics.multimodal_runtime import MultimodalRuntimeResult, execute_multimodal_revision


class MultimodalRequestError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message); self.code=code


def _decode_base64(value: str) -> bytes:
    try: return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MultimodalRequestError("invalid_base64","Image data is not valid base64.") from exc


def _descriptor(item: SanitizedImage) -> SanitizedImageDescriptor:
    return SanitizedImageDescriptor(image_id=item.image_id,image_index=item.image_index,content_sha256=item.content_sha256,width=item.width,height=item.height)


def _revision_image_descriptors(revision: ModelingRevision) -> tuple[SanitizedImageDescriptor,...]:
    result=[]; by_id={}
    for observation in revision.envelope.figure_observations:
        by_id.setdefault(observation.image_id,observation)
    for asset in revision.envelope.draft.source_assets:
        if asset.kind != "image": continue
        observation=by_id.get(asset.asset_id)
        if observation is None: continue
        result.append(SanitizedImageDescriptor(image_id=asset.asset_id,image_index=observation.image_index,content_sha256=asset.content_sha256,width=observation.width,height=observation.height))
    return tuple(sorted(result,key=lambda item:item.image_index))


def _terminal_for_runtime(runtime: MultimodalRuntimeResult|None) -> str:
    if runtime is None: return "ready"
    value=runtime.terminal.value
    if value == "solved": return "solved"
    if value in {"validation_rejected","compiler_rejected","solve_rejected"}: return value
    return "blocked"


class MultimodalEvidenceService:
    def __init__(self, *, modeler: MechanicsMultimodalModeler|None, revision_store: RevisionStore, owner_key: str, event_sink: Callable[[dict[str,int|str]],None]|None=None) -> None:
        self._modeler=modeler; self._revision_store=revision_store; self._owner_key=owner_key; self._event_sink=event_sink

    def process(self, request: MultimodalEvidenceRequest) -> MultimodalEvidenceResponse:
        return self.process_encoded(request)

    def process_encoded(self, request: MultimodalEvidenceRequest) -> MultimodalEvidenceResponse:
        raw=tuple(RawImageInput(item.image_id,_decode_base64(item.data_base64),item.media_type) for item in request.images)
        return self.process_raw(problem_text=request.problem_text,images=raw,client_request_id=request.client_request_id,confirmations=tuple(EvidenceConfirmation(item.conflict_id,item.conflict_fingerprint,item.chosen_source_id,item.chosen_candidate_fingerprint) for item in request.confirmations))

    def process_raw(self, *, problem_text: str, images: tuple[RawImageInput,...], client_request_id: str|None=None, confirmations: tuple[EvidenceConfirmation,...]=()) -> MultimodalEvidenceResponse:
        if client_request_id:
            existing=self._revision_store.get_by_request(owner_key=self._owner_key,client_request_id=client_request_id)
            if existing is not None: return self._response(existing)
        if self._modeler is None: raise MultimodalRequestError("multimodal_modeler_unavailable","The multimodal interpretation adapter is not configured.")
        try: sanitized=sanitize_images(images)
        except ImageSecurityError as exc: raise MultimodalRequestError(exc.code,str(exc)) from exc
        try: outcome=self._modeler.interpret(problem_text=problem_text,images=sanitized,confirmations=confirmations)
        except Exception as exc:
            code=getattr(exc,"code","multimodal_provider_failure")
            raise MultimodalRequestError(str(code),"The multimodal modeling provider failed safely.") from exc
        if outcome.envelope is None:
            response=MultimodalEvidenceResponse(terminal=outcome.terminal.value,sanitized_images=tuple(_descriptor(item) for item in sanitized),diagnostics=outcome.diagnostics)
            self._emit(response,image_count=len(sanitized),confirmation_count=len(confirmations)); return response
        revision=self._revision_store.create(owner_key=self._owner_key,problem_text=problem_text,envelope=outcome.envelope,reconciliation=outcome.reconciliation,client_request_id=client_request_id)
        response=self._response(revision,images=tuple(_descriptor(item) for item in sanitized))
        self._emit(response,image_count=len(sanitized),confirmation_count=len(confirmations)); return response

    def confirm(self, *, revision_id: str, request: RevisionConfirmationRequest) -> MultimodalEvidenceResponse:
        confirmations=tuple(EvidenceConfirmation(item.conflict_id,item.conflict_fingerprint,item.chosen_source_id,item.chosen_candidate_fingerprint) for item in request.confirmations)
        try: revision=self._revision_store.confirm(owner_key=self._owner_key,revision_id=revision_id,expected_fingerprint=request.revision_fingerprint,confirmations=confirmations,client_request_id=request.client_request_id)
        except RevisionError as exc: raise MultimodalRequestError(exc.code,str(exc)) from exc
        response=self._response(revision); self._emit(response,image_count=len(response.sanitized_images),confirmation_count=len(confirmations)); return response

    def correct(self, request: MechanicsCorrectionRequestV1) -> MultimodalEvidenceResponse:
        try: revision=self._revision_store.apply(request,owner_key=self._owner_key)
        except RevisionError as exc: raise MultimodalRequestError(exc.code,str(exc)) from exc
        response=self._response(revision); self._emit(response,image_count=len(response.sanitized_images),confirmation_count=0); return response

    def lookup(self, revision_id: str) -> MultimodalEvidenceResponse:
        try: revision=self._revision_store.require(revision_id,owner_key=self._owner_key)
        except RevisionError as exc: raise MultimodalRequestError(exc.code,str(exc)) from exc
        return self._response(revision,auto_execute=False)

    def execute(self, *, revision_id: str, revision_fingerprint: str) -> MultimodalEvidenceResponse:
        try: revision=self._revision_store.require(revision_id,owner_key=self._owner_key)
        except RevisionError as exc: raise MultimodalRequestError(exc.code,str(exc)) from exc
        if revision.fingerprint != revision_fingerprint: raise MultimodalRequestError("revision_stale","revision fingerprint is stale")
        return self._response(revision,auto_execute=True)

    def _response(self, revision: ModelingRevision, *, images: tuple[SanitizedImageDescriptor,...]|None=None, auto_execute: bool=True) -> MultimodalEvidenceResponse:
        reconciliation=revision.reconciliation
        conflicts=tuple(EvidenceConflictDescriptor(conflict_id=item.conflict_id,fingerprint=item.fingerprint,semantic_target_key=item.semantic_target_key,candidate_source_ids=item.candidate_source_ids,candidate_fingerprints=item.candidate_fingerprints) for item in reconciliation.conflicts)
        runtime=execute_multimodal_revision(revision) if auto_execute and reconciliation.status.value == "ready" else None
        if reconciliation.status.value == "confirmation_required": terminal="confirmation_required"
        elif reconciliation.status.value == "blocked": terminal="blocked"
        else: terminal=_terminal_for_runtime(runtime)
        runtime_payload=runtime.as_dict() if runtime is not None else None
        answer=None if runtime_payload is None else runtime_payload.get("verified_answer")
        draft=revision.envelope.draft.model_dump(mode="json") if reconciliation.status.value == "ready" else None
        return MultimodalEvidenceResponse(
            terminal=terminal,sanitized_images=_revision_image_descriptors(revision) if images is None else images,
            conflicts=conflicts,observations=tuple(item.model_dump(mode="json") for item in revision.envelope.figure_observations),diagnostics=(),
            revision_id=revision.revision_id,parent_revision_id=revision.parent_revision_id,revision_number=revision.revision_number,
            revision_fingerprint=revision.fingerprint,expires_in_seconds=max(0,int(revision.expires_at-time.monotonic())),reconciliation_status=reconciliation.status.value,
            accepted_evidence_ids=revision.accepted_evidence_ids,rejected_evidence_ids=revision.rejected_evidence_ids,corrections_applied=revision.operation_history,
            draft=draft,runtime=runtime_payload,verified_answer=answer,
        )

    def _emit(self,response: MultimodalEvidenceResponse,*,image_count:int,confirmation_count:int)->None:
        if self._event_sink is None:return
        event=build_multimodal_metric_event(terminal="ready" if response.terminal in {"ready","solved"} else response.terminal,image_count=image_count,observation_count=len(response.observations),conflict_count=len(response.conflicts),confirmation_count=confirmation_count)
        self._event_sink(event.as_dict())


__all__=["MultimodalEvidenceService","MultimodalRequestError"]
