"""Collision-safe idempotency for Stage 6 server-held revisions.

A client request identifier is a replay key, not permission to substitute a
previous result for different source material.  Each key is therefore bound to
one canonical request fingerprint for its bounded lifetime.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Iterable

from engine.mechanics.evidence_reconciliation import EvidenceConfirmation
from engine.mechanics.image_security import SanitizedImage
from engine.mechanics.multimodal_contracts import MechanicsCorrectionRequestV1
from engine.mechanics.multimodal_revision import ModelingRevision, RevisionError, RevisionStore


IDEMPOTENCY_POLICY_VERSION = "mechanics-multimodal-idempotency-v1"


def _fingerprint(kind: str, payload: Any) -> str:
    encoded = json.dumps(
        {
            "policy": IDEMPOTENCY_POLICY_VERSION,
            "kind": kind,
            "payload": payload,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def initial_request_fingerprint(
    *,
    problem_text: str,
    images: Iterable[SanitizedImage],
    confirmations: Iterable[EvidenceConfirmation] = (),
) -> str:
    image_payload = [
        {
            "image_id": item.image_id,
            "image_index": item.image_index,
            "content_sha256": item.content_sha256,
            "width": item.width,
            "height": item.height,
            "media_type": item.media_type,
        }
        for item in images
    ]
    confirmation_payload = sorted(
        (
            {
                "conflict_id": item.conflict_id,
                "conflict_fingerprint": item.conflict_fingerprint,
                "chosen_source_id": item.chosen_source_id,
                "chosen_candidate_fingerprint": item.chosen_candidate_fingerprint,
            }
            for item in confirmations
        ),
        key=lambda item: item["conflict_id"],
    )
    return _fingerprint(
        "initial",
        {
            "problem_text_sha256": sha256(problem_text.encode("utf-8")).hexdigest(),
            "images": image_payload,
            "confirmations": confirmation_payload,
        },
    )


def _confirmation_request_fingerprint(
    *,
    revision_id: str,
    expected_fingerprint: str,
    confirmations: Iterable[EvidenceConfirmation],
) -> str:
    return _fingerprint(
        "confirmation",
        {
            "revision_id": revision_id,
            "expected_fingerprint": expected_fingerprint,
            "confirmations": sorted(
                (
                    {
                        "conflict_id": item.conflict_id,
                        "conflict_fingerprint": item.conflict_fingerprint,
                        "chosen_source_id": item.chosen_source_id,
                        "chosen_candidate_fingerprint": item.chosen_candidate_fingerprint,
                    }
                    for item in confirmations
                ),
                key=lambda item: item["conflict_id"],
            ),
        },
    )


def _correction_request_fingerprint(request: MechanicsCorrectionRequestV1) -> str:
    return _fingerprint("correction", request.model_dump(mode="json"))


class IdempotentRevisionStore(RevisionStore):
    """RevisionStore that rejects one idempotency key for different payloads."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._request_signatures: dict[tuple[str, str], str] = {}

    def _purge_locked(self) -> None:
        super()._purge_locked()
        live_keys = set(self._requests)
        for key in tuple(self._request_signatures):
            if key not in live_keys:
                self._request_signatures.pop(key, None)

    def _existing_for_signature_locked(
        self,
        *,
        owner_key: str,
        client_request_id: str,
        request_signature: str,
    ) -> ModelingRevision | None:
        self._purge_locked()
        key = (owner_key, client_request_id)
        prior_signature = self._request_signatures.get(key)
        if prior_signature is not None and prior_signature != request_signature:
            raise RevisionError(
                "request_id_conflict",
                "client_request_id is already bound to different request content",
            )
        revision_id = self._requests.get(key)
        if revision_id is None:
            return None
        existing = self._revisions.get((owner_key, revision_id))
        if existing is None:
            self._requests.pop(key, None)
            self._request_signatures.pop(key, None)
            return None
        if prior_signature is None:
            # This state should not occur for this store.  Fail closed rather than
            # binding an unverified historical result to the incoming payload.
            raise RevisionError(
                "request_id_conflict",
                "client_request_id has no verifiable request fingerprint",
            )
        self._revisions.move_to_end((owner_key, revision_id))
        return existing

    def get_by_request_checked(
        self,
        *,
        owner_key: str,
        client_request_id: str,
        request_signature: str,
    ) -> ModelingRevision | None:
        with self._lock:
            return self._existing_for_signature_locked(
                owner_key=owner_key,
                client_request_id=client_request_id,
                request_signature=request_signature,
            )

    def create(
        self,
        *,
        owner_key: str,
        problem_text: str,
        envelope: Any,
        reconciliation: Any,
        client_request_id: str | None = None,
        request_signature: str | None = None,
    ) -> ModelingRevision:
        if not client_request_id:
            return super().create(
                owner_key=owner_key,
                problem_text=problem_text,
                envelope=envelope,
                reconciliation=reconciliation,
                client_request_id=None,
            )
        signature = request_signature or _fingerprint(
            "initial_revision_fallback",
            {
                "problem_text_sha256": sha256(problem_text.encode("utf-8")).hexdigest(),
                "envelope": envelope.model_dump(mode="json")
                if hasattr(envelope, "model_dump")
                else envelope,
            },
        )
        with self._lock:
            existing = self._existing_for_signature_locked(
                owner_key=owner_key,
                client_request_id=client_request_id,
                request_signature=signature,
            )
            if existing is not None:
                return existing
            revision = super().create(
                owner_key=owner_key,
                problem_text=problem_text,
                envelope=envelope,
                reconciliation=reconciliation,
                client_request_id=client_request_id,
            )
            self._request_signatures[(owner_key, client_request_id)] = signature
            return revision

    def confirm(
        self,
        *,
        owner_key: str,
        revision_id: str,
        expected_fingerprint: str,
        confirmations: Iterable[EvidenceConfirmation],
        client_request_id: str,
    ) -> ModelingRevision:
        items = tuple(confirmations)
        signature = _confirmation_request_fingerprint(
            revision_id=revision_id,
            expected_fingerprint=expected_fingerprint,
            confirmations=items,
        )
        with self._lock:
            existing = self._existing_for_signature_locked(
                owner_key=owner_key,
                client_request_id=client_request_id,
                request_signature=signature,
            )
            if existing is not None:
                return existing
            revision = super().confirm(
                owner_key=owner_key,
                revision_id=revision_id,
                expected_fingerprint=expected_fingerprint,
                confirmations=items,
                client_request_id=client_request_id,
            )
            self._request_signatures[(owner_key, client_request_id)] = signature
            return revision

    def apply(
        self,
        request: MechanicsCorrectionRequestV1 | Any,
        *,
        owner_key: str = "local",
    ) -> ModelingRevision:
        validated = (
            request
            if isinstance(request, MechanicsCorrectionRequestV1)
            else MechanicsCorrectionRequestV1.model_validate(request)
        )
        request_id = str(validated.client_request_id or validated.request_id)
        signature = _correction_request_fingerprint(validated)
        with self._lock:
            existing = self._existing_for_signature_locked(
                owner_key=owner_key,
                client_request_id=request_id,
                request_signature=signature,
            )
            if existing is not None:
                return existing
            revision = super().apply(validated, owner_key=owner_key)
            self._request_signatures[(owner_key, request_id)] = signature
            return revision


__all__ = [
    "IDEMPOTENCY_POLICY_VERSION",
    "IdempotentRevisionStore",
    "initial_request_fingerprint",
]
