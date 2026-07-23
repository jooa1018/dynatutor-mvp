"""Protected Stage 6 FastAPI routes for multimodal evidence and execution."""
from __future__ import annotations

from hashlib import sha256
import json

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from engine.mechanics.image_security import MAX_IMAGE_BYTES, MAX_IMAGE_COUNT, MAX_TOTAL_IMAGE_BYTES, RawImageInput
from engine.mechanics.multimodal_api_contracts import ExecuteRevisionRequest, MultimodalEvidenceRequest, MultimodalEvidenceResponse, RevisionConfirmationRequest
from engine.mechanics.multimodal_contracts import MechanicsCorrectionRequestV1
from engine.mechanics.multimodal_modeler import MechanicsMultimodalModeler
from engine.mechanics.multimodal_revision import RevisionStore
from engine.mechanics.multimodal_service import MultimodalEvidenceService, MultimodalRequestError

router=APIRouter(prefix="/api/mechanics/multimodal",tags=["mechanics-multimodal"])
_READ_CHUNK=1024*1024
_IMAGE_ONLY_MARKER="[IMAGE_ONLY_SOURCE]"


def _owner_key(request: Request) -> str:
    bearer=request.headers.get("authorization","")
    token=bearer[7:].strip() if bearer.lower().startswith("bearer ") else request.headers.get("x-dynatutor-token","").strip()
    session=request.headers.get("x-dynatutor-session","").strip()[:128]
    client=request.client.host if request.client is not None else "unknown"
    return sha256(f"{token}|{session}|{client}".encode()).hexdigest()


def _service(request: Request, *, require_modeler: bool=False) -> MultimodalEvidenceService:
    store=getattr(request.app.state,"mechanics_multimodal_revision_store",None)
    if not isinstance(store,RevisionStore):
        raise HTTPException(status_code=503,detail={"code":"multimodal_revision_store_unavailable","message":"The multimodal revision store is not configured."})
    generator=getattr(request.app.state,"mechanics_multimodal_envelope_generator",None)
    if require_modeler and generator is None:
        raise HTTPException(status_code=503,detail={"code":"multimodal_modeler_unavailable","message":"The multimodal interpretation adapter is not configured."})
    modeler=MechanicsMultimodalModeler(generator) if generator is not None else None
    return MultimodalEvidenceService(modeler=modeler,revision_store=store,owner_key=_owner_key(request),event_sink=getattr(request.app.state,"mechanics_multimodal_event_sink",None))


def _raise_request_error(exc: MultimodalRequestError):
    if exc.code in {"revision_stale","revision_id_mismatch","confirmation_invalid"}: code=409
    elif exc.code == "revision_not_found": code=404
    elif exc.code in {"multimodal_modeler_unavailable","multimodal_provider_unavailable","multimodal_provider_failure","multimodal_provider_incomplete","multimodal_provider_invalid_output"}: code=503
    else: code=422
    raise HTTPException(status_code=code,detail={"code":exc.code,"message":str(exc)}) from exc


async def _read_upload(file: UploadFile, *, image_id: str) -> RawImageInput:
    total=0; chunks=[]
    try:
        while True:
            chunk=await file.read(_READ_CHUNK)
            if not chunk: break
            total += len(chunk)
            if total > MAX_IMAGE_BYTES: raise MultimodalRequestError("image_bytes_exceeded","The image exceeds the per-image safety limit.")
            chunks.append(chunk)
    finally:
        await file.close()
    return RawImageInput(image_id=image_id,content=b"".join(chunks),declared_media_type=file.content_type)


async def _parse_multipart(request: Request) -> tuple[str,tuple[RawImageInput,...],str|None]:
    try: form=await request.form(max_files=MAX_IMAGE_COUNT,max_fields=32)
    except Exception as exc: raise MultimodalRequestError("invalid_multipart","The multipart request could not be decoded safely.") from exc
    problem_text=str(form.get("problem_text") or "")
    request_id=form.get("client_request_id"); client_request_id=None if request_id is None else str(request_id)
    files=list(form.getlist("images"))
    if len(files)>MAX_IMAGE_COUNT: raise MultimodalRequestError("image_count_exceeded","Too many images were supplied.")
    images=[]; total=0
    for index,item in enumerate(files):
        if not isinstance(item,UploadFile): raise MultimodalRequestError("invalid_multipart","Every image field must be a file upload.")
        image_id=str(form.get(f"image_id_{index}") or f"image_{index+1}")
        raw=await _read_upload(item,image_id=image_id); total += len(raw.content)
        if total>MAX_TOTAL_IMAGE_BYTES: raise MultimodalRequestError("total_image_bytes_exceeded","The combined image bytes exceed the safety limit.")
        images.append(raw)
    if not problem_text.strip() and not images: raise MultimodalRequestError("problem_source_required","Problem text or at least one image is required.")
    return problem_text,tuple(images),client_request_id


async def _parse_json(request: Request) -> MultimodalEvidenceRequest:
    try: payload=json.loads(await request.body())
    except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise MultimodalRequestError("invalid_json","The JSON request could not be decoded safely.") from exc
    try: return MultimodalEvidenceRequest.model_validate(payload)
    except ValidationError as exc: raise MultimodalRequestError("invalid_request","The multimodal request did not satisfy the wire contract.") from exc


@router.post("/evidence",response_model=MultimodalEvidenceResponse,status_code=status.HTTP_200_OK)
async def interpret_mechanics_multimodal_evidence(request: Request) -> MultimodalEvidenceResponse:
    content_type=request.headers.get("content-type","").lower(); service=_service(request,require_modeler=True)
    try:
        if content_type.startswith("multipart/form-data"):
            problem_text,images,client_request_id=await _parse_multipart(request)
            return service.process_raw(problem_text=problem_text.strip() or _IMAGE_ONLY_MARKER,images=images,client_request_id=client_request_id)
        if content_type.startswith("application/json"):
            payload=await _parse_json(request)
            if not payload.problem_text.strip() and not payload.images: raise MultimodalRequestError("problem_source_required","Problem text or at least one image is required.")
            if not payload.problem_text.strip(): payload=payload.model_copy(update={"problem_text":_IMAGE_ONLY_MARKER})
            return service.process_encoded(payload)
        raise MultimodalRequestError("unsupported_content_type","Use multipart/form-data or application/json.")
    except MultimodalRequestError as exc: _raise_request_error(exc)
    except ValidationError as exc: raise HTTPException(status_code=422,detail={"code":"invalid_modeling_envelope","message":"The generated modeling envelope did not satisfy the Stage 6 contract."}) from exc


@router.get("/revisions/{revision_id}",response_model=MultimodalEvidenceResponse)
def get_mechanics_multimodal_revision(revision_id: str,request: Request)->MultimodalEvidenceResponse:
    try:return _service(request).lookup(revision_id)
    except MultimodalRequestError as exc:_raise_request_error(exc)


@router.post("/revisions/{revision_id}/confirm",response_model=MultimodalEvidenceResponse)
def confirm_mechanics_multimodal_revision(revision_id: str,payload: RevisionConfirmationRequest,request: Request)->MultimodalEvidenceResponse:
    try:return _service(request).confirm(revision_id=revision_id,request=payload)
    except MultimodalRequestError as exc:_raise_request_error(exc)


@router.post("/revisions/{revision_id}/correct",response_model=MultimodalEvidenceResponse)
def correct_mechanics_multimodal_revision(revision_id: str,payload: MechanicsCorrectionRequestV1,request: Request)->MultimodalEvidenceResponse:
    if payload.base_revision_id != revision_id: raise HTTPException(status_code=409,detail={"code":"revision_id_mismatch","message":"The correction URL and base revision must match."})
    try:return _service(request).correct(payload)
    except MultimodalRequestError as exc:_raise_request_error(exc)


@router.post("/revisions/{revision_id}/execute",response_model=MultimodalEvidenceResponse)
def execute_mechanics_multimodal_revision(revision_id: str,payload: ExecuteRevisionRequest,request: Request)->MultimodalEvidenceResponse:
    try:return _service(request).execute(revision_id=revision_id,revision_fingerprint=payload.revision_fingerprint)
    except MultimodalRequestError as exc:_raise_request_error(exc)


__all__=["router"]
