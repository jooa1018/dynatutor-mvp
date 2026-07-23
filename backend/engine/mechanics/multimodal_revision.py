"""Immutable, source-only revision handling for Stage 6 corrections."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from engine.mechanics.multimodal_authority_audit import audit_modeling_payload
from engine.mechanics.multimodal_contracts import MechanicsCorrectionRequestV1, MechanicsModelingEnvelopeV1

FORBIDDEN_PATCH_FIELDS = frozenset(
    {
        "final_answer",
        "executable_equation",
        "equation_graph",
        "selected_solver",
        "solver_candidate",
        "selected_root",
        "verification_result",
        "verified_candidate",
        "legacy_route",
        "runtime_delivery",
    }
)
ALLOWED_OPERATION_KINDS = frozenset(
    {
        "replace_quantity_value",
        "replace_quantity_unit",
        "replace_observation_value",
        "replace_observation_unit",
        "replace_direction",
        "choose_ambiguity_alternative",
        "replace_relation_participants",
    }
)


class RevisionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelingRevision:
    revision_id: str
    fingerprint: str
    envelope: MechanicsModelingEnvelopeV1
    parent_revision_id: str | None = None


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    return value


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        _plain(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: getattr(item, "value", str(item)),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def create_initial_revision(envelope: MechanicsModelingEnvelopeV1) -> ModelingRevision:
    validated = MechanicsModelingEnvelopeV1.model_validate(_plain(envelope))
    fingerprint = _fingerprint(validated)
    return ModelingRevision(
        revision_id=f"revision_{fingerprint[:20]}",
        fingerprint=fingerprint,
        envelope=validated,
    )


def _request_field(payload: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload:
            return payload[name]
    return None


def _operation_kind(operation: Mapping[str, Any]) -> str:
    raw = operation.get("kind")
    return str(getattr(raw, "value", raw) or "")


def _reject_authority(value: Any, path: str = "") -> None:
    value = _plain(value)
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_PATCH_FIELDS:
                raise RevisionError(f"correction cannot patch authority field: {child_path}")
            _reject_authority(child, child_path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_authority(child, f"{path}[{index}]")


def _replace_by_id(items: list[dict[str, Any]], id_field: str, target_id: str) -> dict[str, Any]:
    matches = [item for item in items if str(item.get(id_field)) == target_id]
    if len(matches) != 1:
        raise RevisionError(f"correction target must resolve exactly once: {target_id}")
    return matches[0]


def _apply_operation(payload: dict[str, Any], operation: Mapping[str, Any]) -> None:
    kind = _operation_kind(operation)
    if kind not in ALLOWED_OPERATION_KINDS:
        raise RevisionError(f"unsupported source correction operation: {kind}")

    if kind in {"replace_quantity_value", "replace_quantity_unit"}:
        draft = payload.setdefault("draft", {})
        quantities = draft.setdefault("quantities", [])
        quantity_id = str(operation.get("quantity_id") or "")
        item = _replace_by_id(quantities, "quantity_id", quantity_id)
        if kind == "replace_quantity_value":
            value = operation.get("raw_value", operation.get("value"))
            if value is None:
                raise RevisionError("replacement quantity value is required")
            item["raw_value"] = str(value)
        else:
            unit = operation.get("raw_unit", operation.get("unit"))
            if unit is None:
                raise RevisionError("replacement quantity unit is required")
            item["raw_unit"] = str(unit)
        return

    if kind in {"replace_observation_value", "replace_observation_unit", "replace_direction"}:
        observations = payload.setdefault("figure_observations", [])
        observation_id = str(operation.get("observation_id") or "")
        item = _replace_by_id(observations, "observation_id", observation_id)
        if kind == "replace_observation_value":
            value = operation.get("observed_value", operation.get("raw_value", operation.get("value")))
            if value is None:
                raise RevisionError("replacement observation value is required")
            item["observed_value"] = str(value)
        elif kind == "replace_observation_unit":
            unit = operation.get("unit_candidate", operation.get("raw_unit", operation.get("unit")))
            item["unit_candidate"] = None if unit is None else str(unit)
        else:
            direction = operation.get("direction_candidate", operation.get("direction"))
            item["direction_candidate"] = None if direction is None else str(direction)
        item["policy_eligibility"] = "confirmation_required"
        return

    if kind == "choose_ambiguity_alternative":
        ambiguities = payload.setdefault("unresolved_ambiguities", [])
        ambiguity_id = str(operation.get("ambiguity_id") or "")
        item = _replace_by_id(ambiguities, "ambiguity_id", ambiguity_id)
        chosen = operation.get("alternative_id", operation.get("chosen_alternative_id"))
        if chosen is None:
            raise RevisionError("an ambiguity alternative is required")
        item["chosen_alternative_id"] = str(chosen)
        item["status"] = "resolved_by_user"
        return

    if kind == "replace_relation_participants":
        observations = payload.setdefault("figure_observations", [])
        observation_id = str(operation.get("observation_id") or "")
        item = _replace_by_id(observations, "observation_id", observation_id)
        participants = operation.get("relation_participant_ids")
        if not isinstance(participants, (list, tuple)) or not participants:
            raise RevisionError("relation participants are required")
        item["relation_participant_ids"] = [str(value) for value in participants]
        item["policy_eligibility"] = "confirmation_required"
        return

    raise RevisionError(f"unhandled source correction operation: {kind}")


class RevisionStore:
    """Small in-memory store with request idempotency and stale-revision vetoes."""

    def __init__(self) -> None:
        self._revisions: dict[str, ModelingRevision] = {}
        self._requests: dict[str, ModelingRevision] = {}

    def put(self, revision: ModelingRevision) -> None:
        self._revisions[revision.revision_id] = revision

    def get(self, revision_id: str) -> ModelingRevision | None:
        return self._revisions.get(revision_id)

    def apply(
        self,
        request: MechanicsCorrectionRequestV1 | Mapping[str, Any],
    ) -> ModelingRevision:
        validated = (
            request
            if isinstance(request, MechanicsCorrectionRequestV1)
            else MechanicsCorrectionRequestV1.model_validate(request)
        )
        request_payload = validated.model_dump(mode="python")
        _reject_authority(request_payload)
        request_id = str(_request_field(request_payload, "request_id", "client_request_id") or "")
        if request_id and request_id in self._requests:
            return self._requests[request_id]

        base_revision_id = str(_request_field(request_payload, "base_revision_id", "revision_id") or "")
        expected_fingerprint = str(
            _request_field(request_payload, "base_revision_fingerprint", "revision_fingerprint") or ""
        )
        base = self._revisions.get(base_revision_id)
        if base is None:
            raise RevisionError("base revision does not exist")
        if expected_fingerprint != base.fingerprint:
            raise RevisionError("base revision fingerprint is stale")

        payload = deepcopy(base.envelope.model_dump(mode="python"))
        operations = request_payload.get("operations") or ()
        if not operations:
            raise RevisionError("at least one correction operation is required")
        for raw_operation in operations:
            operation = _plain(raw_operation)
            if not isinstance(operation, Mapping):
                raise RevisionError("correction operation must be an object")
            _apply_operation(payload, operation)

        envelope = MechanicsModelingEnvelopeV1.model_validate(payload)
        audit = audit_modeling_payload(envelope)
        if not audit.passed:
            raise RevisionError("corrected envelope crossed the answer-authority boundary")
        fingerprint = _fingerprint(envelope)
        revision = ModelingRevision(
            revision_id=f"revision_{fingerprint[:20]}",
            fingerprint=fingerprint,
            envelope=envelope,
            parent_revision_id=base.revision_id,
        )
        self._revisions[revision.revision_id] = revision
        if request_id:
            self._requests[request_id] = revision
        return revision


__all__ = [
    "ALLOWED_OPERATION_KINDS",
    "FORBIDDEN_PATCH_FIELDS",
    "ModelingRevision",
    "RevisionError",
    "RevisionStore",
    "create_initial_revision",
]
