"""Bounded immutable revision storage for Stage 6 source-only corrections."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
from secrets import token_urlsafe
from threading import RLock
import time
from typing import Any, Callable, Mapping

from engine.mechanics.evidence_reconciliation import (
    EvidenceConfirmation,
    ReconciliationResult,
    ReconciliationStatus,
    reconcile_evidence,
)
from engine.mechanics.multimodal_authority_audit import audit_modeling_payload
from engine.mechanics.multimodal_contracts import (
    CorrectionOperationKind,
    EvidenceSourceType,
    MechanicsCorrectionRequestV1,
    MechanicsModelingEnvelopeV1,
)
from engine.mechanics.multimodal_modeler import evidence_candidates_from_envelope
from engine.mechanics.validation import CorrectionAuthorization


REVISION_POLICY_VERSION = "mechanics-multimodal-revision-v2"
DEFAULT_REVISION_TTL_SECONDS = 30 * 60
DEFAULT_REVISION_MAX_ENTRIES = 256
FORBIDDEN_PATCH_FIELDS = frozenset({
    "final_answer", "executable_equation", "equation_graph", "selected_solver",
    "solver_candidate", "selected_root", "verification_result", "verified_candidate",
    "legacy_route", "runtime_delivery",
})
ALLOWED_OPERATION_KINDS = frozenset(item.value for item in CorrectionOperationKind)


class RevisionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ModelingRevision:
    revision_id: str
    fingerprint: str
    envelope: MechanicsModelingEnvelopeV1
    problem_text: str = field(repr=False)
    owner_key: str = field(repr=False)
    reconciliation: ReconciliationResult
    parent_revision_id: str | None = None
    revision_number: int = 0
    accepted_evidence_ids: tuple[str, ...] = ()
    rejected_evidence_ids: tuple[str, ...] = ()
    approved_assumption_ids: tuple[str, ...] = ()
    correction_authorizations: tuple[CorrectionAuthorization, ...] = ()
    confirmations: tuple[EvidenceConfirmation, ...] = ()
    operation_history: tuple[dict[str, Any], ...] = field(default_factory=tuple, repr=False)
    created_at: float = field(default=0.0, repr=False)
    expires_at: float = field(default=0.0, repr=False)

    def authorization_map(self) -> dict[str, CorrectionAuthorization]:
        return {item.correction_id: item for item in self.correction_authorizations}


def _plain(value: Any) -> Any:
    return value.model_dump(mode="python") if hasattr(value, "model_dump") else value


def _sorted_unique(values) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _new_revision_id() -> str:
    return "revision_" + token_urlsafe(24).replace("-", "_")


def _fingerprint_payload(
    envelope: MechanicsModelingEnvelopeV1,
    *,
    problem_text: str,
    accepted=(), rejected=(), approved=(), authorizations=(), confirmations=(),
) -> str:
    payload = {
        "policy": REVISION_POLICY_VERSION,
        "problem_text_sha256": sha256(problem_text.encode("utf-8")).hexdigest(),
        "envelope": envelope.model_dump(mode="json"),
        "accepted": sorted(set(accepted)), "rejected": sorted(set(rejected)),
        "approved": sorted(set(approved)),
        "authorizations": sorted(({
            "correction_id": item.correction_id, "subject_id": item.subject_id,
            "role": item.role, "raw_value": item.raw_value, "raw_unit": item.raw_unit,
            "interval_id": item.interval_id, "event_id": item.event_id,
        } for item in authorizations), key=lambda item: item["correction_id"]),
        "confirmations": sorted(({
            "conflict_id": item.conflict_id,
            "conflict_fingerprint": item.conflict_fingerprint,
            "chosen_source_id": item.chosen_source_id,
            "chosen_candidate_fingerprint": item.chosen_candidate_fingerprint,
        } for item in confirmations), key=lambda item: item["conflict_id"]),
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256(encoded).hexdigest()


def _reject_authority(value: Any, path: str = "") -> None:
    value = _plain(value)
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key); child_path = f"{path}.{name}" if path else name
            if name in FORBIDDEN_PATCH_FIELDS:
                raise RevisionError("authority_patch_forbidden", f"correction cannot patch authority field: {child_path}")
            _reject_authority(child, child_path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_authority(child, f"{path}[{index}]")


def _replace_by_id(items: list[dict[str, Any]], id_field: str, target_id: str) -> dict[str, Any]:
    matches = [item for item in items if str(item.get(id_field)) == target_id]
    if len(matches) != 1:
        raise RevisionError("correction_target_invalid", f"correction target must resolve exactly once: {target_id}")
    return matches[0]


def _remove_by_id(items: list[dict[str, Any]], id_field: str, target_id: str) -> dict[str, Any]:
    matches = [i for i, item in enumerate(items) if str(item.get(id_field)) == target_id]
    if len(matches) != 1:
        raise RevisionError("correction_target_invalid", f"correction target must resolve exactly once: {target_id}")
    return items.pop(matches[0])


def _find_observation(payload: dict[str, Any], identifier: str) -> dict[str, Any]:
    observations = payload.setdefault("figure_observations", [])
    for field_name in ("observation_id", "evidence_id"):
        matches = [item for item in observations if str(item.get(field_name) or "") == identifier]
        if len(matches) == 1:
            return matches[0]
    raise RevisionError("correction_target_invalid", f"figure evidence must resolve exactly once: {identifier}")


def _quantity_authorization(quantity: Mapping[str, Any], correction_id: str) -> CorrectionAuthorization:
    raw_value, raw_unit = quantity.get("raw_value"), quantity.get("raw_unit")
    if raw_value is None or raw_unit is None:
        raise RevisionError("correction_value_required", "a corrected quantity requires a value and unit")
    role = getattr(quantity.get("role"), "value", quantity.get("role"))
    return CorrectionAuthorization(
        correction_id=correction_id,
        subject_id=str(quantity.get("subject_id") or ""), role=str(role or ""),
        raw_value=str(raw_value), raw_unit=str(raw_unit),
        interval_id=None if quantity.get("interval_id") is None else str(quantity.get("interval_id")),
        event_id=None if quantity.get("event_id") is None else str(quantity.get("event_id")),
    )


def _mark_user_quantity(quantity: dict[str, Any], correction_id: str) -> CorrectionAuthorization:
    quantity["provenance"] = "user_correction"
    quantity["correction_id"] = correction_id
    quantity["model_confidence"] = None
    return _quantity_authorization(quantity, correction_id)


def _apply_operation(
    payload: dict[str, Any], operation: Mapping[str, Any], *,
    accepted: set[str], rejected: set[str], approved_assumptions: set[str],
    authorizations: dict[str, CorrectionAuthorization],
) -> None:
    raw_kind = operation.get("kind")
    kind = str(getattr(raw_kind, "value", raw_kind) or "")
    if kind not in ALLOWED_OPERATION_KINDS:
        raise RevisionError("correction_operation_unsupported", f"unsupported source correction operation: {kind}")
    operation_id = str(operation.get("operation_id") or "")
    draft = payload.setdefault("draft", {})

    if kind in {"accept_evidence", "reject_evidence"}:
        evidence_id = str(operation.get("evidence_id") or "")
        try:
            observation = _find_observation(payload, evidence_id)
        except RevisionError:
            source_ids = {str(item.get("evidence_id") or "") for item in draft.setdefault("source_evidence", [])}
            if evidence_id not in source_ids:
                raise
            if kind == "reject_evidence":
                for quantity in draft.setdefault("quantities", []):
                    quantity["evidence_refs"] = [item for item in quantity.get("evidence_refs", []) if str(item) != evidence_id]
            if kind == "accept_evidence": accepted.add(evidence_id); rejected.discard(evidence_id)
            else: rejected.add(evidence_id); accepted.discard(evidence_id)
            return
        if kind == "accept_evidence":
            if str(observation.get("evidence_origin")) == EvidenceSourceType.figure_convention.value:
                observation["policy_eligibility"] = "convention_only"
            else:
                observation["policy_eligibility"] = "automatic"
                observation["ambiguity_status"] = "resolved"
            accepted.add(evidence_id); rejected.discard(evidence_id)
        else:
            observation["policy_eligibility"] = "rejected"
            rejected.add(evidence_id); accepted.discard(evidence_id)
        return

    if kind in {"replace_quantity_value", "replace_unit", "replace_direction"}:
        quantity_id = str(operation.get("quantity_id") or "")
        quantity = _replace_by_id(draft.setdefault("quantities", []), "quantity_id", quantity_id)
        if kind == "replace_quantity_value":
            quantity["raw_value"] = str(operation.get("raw_value")); quantity["raw_unit"] = str(operation.get("raw_unit"))
        elif kind == "replace_unit": quantity["raw_unit"] = str(operation.get("raw_unit"))
        else: quantity["direction"] = deepcopy(_plain(operation.get("direction")))
        authorizations[operation_id] = _mark_user_quantity(quantity, operation_id)
        return

    if kind == "bind_label_to_entity":
        observation_id = str(operation.get("observation_id") or "")
        observation = _find_observation(payload, observation_id)
        target = dict(observation.get("semantic_target") or {})
        target.update({"kind": "entity", "target_id": str(operation.get("entity_id") or "")})
        observation.update({"semantic_target": target, "ambiguity_status": "resolved", "policy_eligibility": "automatic"})
        accepted.add(str(observation.get("evidence_id") or observation_id))
        return

    if kind == "replace_relation":
        relation = deepcopy(_plain(operation.get("relation")))
        if not isinstance(relation, Mapping):
            raise RevisionError("correction_payload_invalid", "replacement relation is required")
        relation_id = str(relation.get("relation_id") or "")
        geometry = draft.setdefault("geometry", [])
        _remove_by_id(geometry, "relation_id", relation_id); geometry.append(dict(relation)); return

    if kind == "choose_alternative":
        observation_id = str(operation.get("observation_id") or "")
        alternative_id = str(operation.get("alternative_id") or "")
        observation = _find_observation(payload, observation_id)
        matches = [item for item in observation.get("alternatives", []) if str(item.get("alternative_id") or "") == alternative_id]
        if len(matches) != 1:
            raise RevisionError("correction_target_invalid", "alternative must resolve exactly once")
        for field_name in ("semantic_target", "observed_value", "unit_candidate", "direction_candidate"):
            observation[field_name] = deepcopy(matches[0].get(field_name))
        observation.update({"ambiguity_status": "resolved", "policy_eligibility": "automatic"})
        accepted.add(str(observation.get("evidence_id") or observation_id)); return

    if kind == "add_user_fact":
        quantity = deepcopy(_plain(operation.get("quantity")))
        if not isinstance(quantity, Mapping): raise RevisionError("correction_payload_invalid", "a typed quantity is required")
        item = dict(quantity); quantity_id = str(item.get("quantity_id") or "")
        if any(str(existing.get("quantity_id")) == quantity_id for existing in draft.setdefault("quantities", [])):
            raise RevisionError("correction_target_invalid", "quantity ID already exists")
        authorizations[operation_id] = _mark_user_quantity(item, operation_id); draft["quantities"].append(item); return

    if kind == "remove_fact":
        fact_id = str(operation.get("fact_id") or ""); removed = False
        for collection, id_field in (("quantities","quantity_id"),("geometry","relation_id"),("interactions","interaction_id"),("constraints","constraint_id"),("state_conditions","state_condition_id")):
            items = draft.setdefault(collection, []); matches = [i for i,item in enumerate(items) if str(item.get(id_field)) == fact_id]
            if matches:
                if len(matches) != 1 or removed: raise RevisionError("correction_target_invalid", "fact ID is ambiguous")
                items.pop(matches[0]); removed = True
        if not removed: raise RevisionError("correction_target_invalid", "fact ID does not exist")
        return

    if kind == "replace_query":
        query = deepcopy(_plain(operation.get("query")))
        if not isinstance(query, Mapping): raise RevisionError("correction_payload_invalid", "a typed query is required")
        queries = draft.setdefault("queries", []); _remove_by_id(queries, "query_id", str(query.get("query_id") or "")); queries.append(dict(query)); return

    if kind == "replace_frame_or_axis":
        frame = deepcopy(_plain(operation.get("frame")))
        if not isinstance(frame, Mapping): raise RevisionError("correction_payload_invalid", "a typed frame is required")
        frames = draft.setdefault("reference_frames", []); _remove_by_id(frames, "frame_id", str(frame.get("frame_id") or "")); frames.append(dict(frame)); return

    if kind in {"confirm_assumption", "reject_assumption"}:
        assumption_id = str(operation.get("assumption_id") or "")
        assumption = _replace_by_id(draft.setdefault("assumptions", []), "assumption_id", assumption_id)
        if kind == "confirm_assumption": assumption["disposition"] = "approved"; approved_assumptions.add(assumption_id)
        else: assumption["disposition"] = "rejected"; approved_assumptions.discard(assumption_id)
        return
    raise RevisionError("correction_operation_unsupported", f"unhandled source correction operation: {kind}")


def _apply_confirmations_to_payload(payload: dict[str, Any], confirmations, *, authorizations, accepted, rejected, conflicts) -> None:
    observations = payload.setdefault("figure_observations", [])
    bindings = payload.setdefault("proposed_bindings", [])
    quantities = payload.setdefault("draft", {}).setdefault("quantities", [])
    by_source = {str(item.get("evidence_id") or item.get("observation_id") or ""): item for item in observations}
    conflict_by_id = {item.conflict_id: item for item in conflicts}
    for confirmation in confirmations:
        conflict = conflict_by_id.get(confirmation.conflict_id)
        if conflict:
            rejected.update(source for source in conflict.candidate_source_ids if source != confirmation.chosen_source_id)
        selected = by_source.get(confirmation.chosen_source_id)
        accepted.add(confirmation.chosen_source_id)
        if selected is None: continue
        selected.update({"policy_eligibility": "automatic", "ambiguity_status": "resolved"})
        for binding in bindings:
            if str(binding.get("evidence_id") or "") != confirmation.chosen_source_id and str(binding.get("observation_id") or "") != str(selected.get("observation_id") or ""):
                continue
            fact_id = str(binding.get("semantic_fact_id") or "")
            matches = [item for item in quantities if str(item.get("quantity_id") or "") == fact_id]
            if len(matches) != 1: continue
            quantity = matches[0]
            if selected.get("observed_value") is not None: quantity["raw_value"] = str(selected.get("observed_value"))
            if selected.get("unit_candidate") is not None: quantity["raw_unit"] = str(selected.get("unit_candidate"))
            correction_id = "confirmation_" + confirmation.conflict_id
            authorizations[correction_id] = _mark_user_quantity(quantity, correction_id)


def create_initial_revision(envelope, *, problem_text, owner_key, reconciliation, now=None, ttl_seconds=DEFAULT_REVISION_TTL_SECONDS) -> ModelingRevision:
    validated = MechanicsModelingEnvelopeV1.model_validate(_plain(envelope)); timestamp = time.monotonic() if now is None else now
    fingerprint = _fingerprint_payload(validated, problem_text=problem_text)
    return ModelingRevision(_new_revision_id(), fingerprint, validated, problem_text, owner_key, reconciliation, created_at=timestamp, expires_at=timestamp+ttl_seconds)


class RevisionStore:
    def __init__(self, *, ttl_seconds=DEFAULT_REVISION_TTL_SECONDS, max_entries=DEFAULT_REVISION_MAX_ENTRIES, time_fn: Callable[[], float]=time.monotonic) -> None:
        if not 1 <= int(max_entries) <= 4096: raise ValueError("max_entries outside bounded range")
        if not 1 <= float(ttl_seconds) <= 86400: raise ValueError("ttl_seconds outside bounded range")
        self.ttl_seconds=float(ttl_seconds); self.max_entries=int(max_entries); self._time_fn=time_fn
        self._revisions: OrderedDict[tuple[str,str], ModelingRevision] = OrderedDict(); self._requests: dict[tuple[str,str],str] = {}; self._lock=RLock()

    def _purge_locked(self) -> None:
        now=self._time_fn()
        expired=[key for key,item in self._revisions.items() if item.expires_at <= now]
        for key in expired: self._revisions.pop(key,None)
        while len(self._revisions)>self.max_entries: self._revisions.popitem(last=False)
        valid={(owner,rid) for owner,rid in self._revisions}
        for key,rid in list(self._requests.items()):
            if (key[0],rid) not in valid: self._requests.pop(key,None)

    def put(self, revision: ModelingRevision, *, client_request_id: str|None=None) -> ModelingRevision:
        with self._lock:
            self._purge_locked()
            if client_request_id:
                prior=self._requests.get((revision.owner_key,client_request_id))
                if prior:
                    existing=self._revisions.get((revision.owner_key,prior))
                    if existing: return existing
            key=(revision.owner_key,revision.revision_id); self._revisions[key]=revision; self._revisions.move_to_end(key)
            if client_request_id: self._requests[(revision.owner_key,client_request_id)] = revision.revision_id
            self._purge_locked(); return revision

    def create(self, *, owner_key, problem_text, envelope, reconciliation, client_request_id=None) -> ModelingRevision:
        with self._lock:
            self._purge_locked()
            if client_request_id:
                rid=self._requests.get((owner_key,client_request_id)); existing=self._revisions.get((owner_key,rid)) if rid else None
                if existing: return existing
            revision=create_initial_revision(envelope,problem_text=problem_text,owner_key=owner_key,reconciliation=reconciliation,now=self._time_fn(),ttl_seconds=self.ttl_seconds)
            return self.put(revision,client_request_id=client_request_id)

    def get_by_request(self, *, owner_key: str, client_request_id: str) -> ModelingRevision | None:
        with self._lock:
            self._purge_locked()
            revision_id = self._requests.get((owner_key, client_request_id))
            if revision_id is None:
                return None
            return self._revisions.get((owner_key, revision_id))

    def get(self, revision_id: str, *, owner_key: str="local") -> ModelingRevision|None:
        with self._lock:
            self._purge_locked(); key=(owner_key,revision_id); item=self._revisions.get(key)
            if item: self._revisions.move_to_end(key)
            return item

    def require(self, revision_id: str, *, owner_key: str) -> ModelingRevision:
        item=self.get(revision_id,owner_key=owner_key)
        if item is None: raise RevisionError("revision_not_found","revision does not exist or expired")
        return item

    def _child(self, base, *, envelope, reconciliation, accepted, rejected, approved, authorizations, confirmations, history):
        now=self._time_fn(); fingerprint=_fingerprint_payload(envelope,problem_text=base.problem_text,accepted=accepted,rejected=rejected,approved=approved,authorizations=authorizations,confirmations=confirmations)
        return ModelingRevision(_new_revision_id(),fingerprint,envelope,base.problem_text,base.owner_key,reconciliation,base.revision_id,base.revision_number+1,accepted,rejected,approved,authorizations,confirmations,history,now,now+self.ttl_seconds)

    def confirm(self, *, owner_key, revision_id, expected_fingerprint, confirmations, client_request_id) -> ModelingRevision:
        with self._lock:
            self._purge_locked(); prior=self._requests.get((owner_key,client_request_id)); existing=self._revisions.get((owner_key,prior)) if prior else None
            if existing: return existing
            base=self.require(revision_id,owner_key=owner_key)
            if expected_fingerprint != base.fingerprint: raise RevisionError("revision_stale","revision fingerprint is stale")
            candidates=evidence_candidates_from_envelope(base.envelope); reconciliation=reconcile_evidence(candidates,confirmations)
            if reconciliation.status is ReconciliationStatus.blocked: raise RevisionError("confirmation_invalid","confirmation does not match current conflict")
            payload=deepcopy(base.envelope.model_dump(mode="python")); accepted=set(base.accepted_evidence_ids); rejected=set(base.rejected_evidence_ids); authorizations=base.authorization_map()
            _apply_confirmations_to_payload(payload,confirmations,authorizations=authorizations,accepted=accepted,rejected=rejected,conflicts=base.reconciliation.conflicts)
            envelope=MechanicsModelingEnvelopeV1.model_validate(payload)
            if not audit_modeling_payload(envelope).passed: raise RevisionError("authority_patch_forbidden","confirmation crossed authority boundary")
            final_reconciliation=reconcile_evidence([item for item in evidence_candidates_from_envelope(envelope) if item.source_id not in rejected],confirmations)
            child=self._child(base,envelope=envelope,reconciliation=final_reconciliation,accepted=_sorted_unique(accepted),rejected=_sorted_unique(rejected),approved=base.approved_assumption_ids,authorizations=tuple(sorted(authorizations.values(),key=lambda x:x.correction_id)),confirmations=tuple(sorted(confirmations,key=lambda x:x.conflict_id)),history=base.operation_history)
            return self.put(child,client_request_id=client_request_id)

    def apply(self, request, *, owner_key: str="local") -> ModelingRevision:
        validated=request if isinstance(request,MechanicsCorrectionRequestV1) else MechanicsCorrectionRequestV1.model_validate(request)
        request_payload=validated.model_dump(mode="python"); _reject_authority(request_payload); request_id=str(validated.client_request_id or validated.request_id)
        with self._lock:
            self._purge_locked(); prior=self._requests.get((owner_key,request_id)); existing=self._revisions.get((owner_key,prior)) if prior else None
            if existing: return existing
            base=self.require(validated.base_revision_id,owner_key=owner_key)
            if validated.base_revision_fingerprint != base.fingerprint: raise RevisionError("revision_stale","base revision fingerprint is stale")
            payload=deepcopy(base.envelope.model_dump(mode="python")); accepted=set(base.accepted_evidence_ids); rejected=set(base.rejected_evidence_ids); approved=set(base.approved_assumption_ids); auth=base.authorization_map(); operations=[]
            for raw in validated.operations:
                op=raw.model_dump(mode="python"); _apply_operation(payload,op,accepted=accepted,rejected=rejected,approved_assumptions=approved,authorizations=auth); operations.append(raw.model_dump(mode="json"))
            envelope=MechanicsModelingEnvelopeV1.model_validate(payload)
            if not audit_modeling_payload(envelope).passed: raise RevisionError("authority_patch_forbidden","corrected envelope crossed answer-authority boundary")
            candidates=[item for item in evidence_candidates_from_envelope(envelope) if item.source_id not in rejected]
            reconciliation=reconcile_evidence(candidates,base.confirmations)
            child=self._child(base,envelope=envelope,reconciliation=reconciliation,accepted=_sorted_unique(accepted),rejected=_sorted_unique(rejected),approved=_sorted_unique(approved),authorizations=tuple(sorted(auth.values(),key=lambda x:x.correction_id)),confirmations=base.confirmations,history=base.operation_history+tuple(operations))
            return self.put(child,client_request_id=request_id)


__all__ = ["ALLOWED_OPERATION_KINDS","DEFAULT_REVISION_MAX_ENTRIES","DEFAULT_REVISION_TTL_SECONDS","FORBIDDEN_PATCH_FIELDS","ModelingRevision","REVISION_POLICY_VERSION","RevisionError","RevisionStore","create_initial_revision"]
