"""Interpretation-only orchestration for Stage 6 multimodal modeling."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from typing import Any, Iterable, Mapping, Protocol, Sequence

from engine.mechanics.evidence_reconciliation import (
    EvidenceCandidate,
    EvidenceConfirmation,
    ReconciliationResult,
    ReconciliationStatus,
    candidate_from_mapping,
    reconcile_evidence,
    semantic_target_key,
)
from engine.mechanics.image_security import SanitizedImage
from engine.mechanics.multimodal_authority_audit import AuthorityAudit, audit_modeling_payload
from engine.mechanics.multimodal_contracts import MechanicsModelingEnvelopeV1


class MultimodalModelerTerminal(StrEnum):
    ready = "ready"
    confirmation_required = "confirmation_required"
    blocked = "blocked"


class EnvelopeGenerator(Protocol):
    def __call__(
        self, problem_text: str, images: tuple[SanitizedImage, ...]
    ) -> MechanicsModelingEnvelopeV1 | Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class MultimodalModelerOutcome:
    terminal: MultimodalModelerTerminal
    envelope: MechanicsModelingEnvelopeV1 | None
    reconciliation: ReconciliationResult
    authority_audit: AuthorityAudit
    diagnostics: tuple[str, ...]

    @property
    def draft_for_runtime(self) -> Any | None:
        if self.terminal is not MultimodalModelerTerminal.ready or self.envelope is None:
            return None
        return self.envelope.draft


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"unsupported evidence value: {type(value).__name__}")


def _figure_candidates(envelope: MechanicsModelingEnvelopeV1) -> list[EvidenceCandidate]:
    result: list[EvidenceCandidate] = []
    for observation in envelope.figure_observations:
        payload = _dump(observation)
        if payload.get("observed_value") is None and payload.get("direction_candidate") is None:
            continue
        result.append(candidate_from_mapping(payload))
    return result


def _text_candidates(envelope: MechanicsModelingEnvelopeV1) -> list[EvidenceCandidate]:
    """Project source-bound explicit quantities into deterministic candidates."""

    result: list[EvidenceCandidate] = []
    source_by_id = {item.evidence_id: item for item in envelope.draft.source_evidence}
    declared_text_ids = {item.evidence_id for item in envelope.text_evidence}
    for quantity in envelope.draft.quantities:
        if quantity.raw_value is None or quantity.raw_unit is None:
            continue
        for evidence_id in quantity.evidence_refs:
            source = source_by_id.get(evidence_id)
            if source is None or getattr(source, "kind", None) != "text":
                continue
            if declared_text_ids and evidence_id not in declared_text_ids:
                continue
            target = {
                "kind": "quantity",
                "target_id": quantity.quantity_id,
                "role": getattr(quantity.role, "value", quantity.role),
                "component": getattr(quantity.component, "value", quantity.component),
                "relation_kind": None,
            }
            direction = quantity.direction
            result.append(
                EvidenceCandidate(
                    source_id=evidence_id,
                    source_type="TEXT_EXPLICIT",
                    semantic_target_key=semantic_target_key(target),
                    normalized_value=str(quantity.raw_value),
                    normalized_unit=str(quantity.raw_unit),
                    direction=(
                        json.dumps(direction.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
                        if direction is not None else None
                    ),
                    policy_eligibility="automatic",
                    provenance="TEXT_EXPLICIT",
                )
            )
    return result


def evidence_candidates_from_envelope(envelope: MechanicsModelingEnvelopeV1) -> tuple[EvidenceCandidate, ...]:
    validated = MechanicsModelingEnvelopeV1.model_validate(envelope.model_dump(mode="python"))
    return tuple(_text_candidates(validated) + _figure_candidates(validated))


def _validate_image_bindings(
    envelope: MechanicsModelingEnvelopeV1,
    images: Sequence[SanitizedImage],
) -> tuple[str, ...]:
    diagnostics: list[str] = []
    by_id = {item.image_id: item for item in images}
    if len(by_id) != len(images):
        return ("duplicate_sanitized_image_id",)
    observation_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for observation in envelope.figure_observations:
        payload = _dump(observation)
        observation_id = str(payload.get("observation_id") or "")
        evidence_id = str(payload.get("evidence_id") or "")
        if not observation_id or observation_id in observation_ids:
            diagnostics.append("invalid_or_duplicate_observation_id")
        observation_ids.add(observation_id)
        if evidence_id:
            evidence_ids.add(evidence_id)
        image = by_id.get(str(payload.get("image_id") or ""))
        if image is None:
            diagnostics.append("unknown_observation_image")
            continue
        expected = {
            "image_index": image.image_index,
            "sanitized_content_sha256": image.content_sha256,
            "source_digest": image.content_sha256,
            "width": image.width,
            "height": image.height,
        }
        for field, expected_value in expected.items():
            if payload.get(field) != expected_value:
                diagnostics.append(f"observation_{field}_mismatch")
    for binding in envelope.proposed_bindings:
        payload = _dump(binding)
        if str(payload.get("observation_id") or "") not in observation_ids:
            diagnostics.append("binding_unknown_observation")
        evidence_id = str(payload.get("evidence_id") or "")
        if evidence_id and evidence_id not in evidence_ids:
            diagnostics.append("binding_unknown_evidence")
    return tuple(sorted(set(diagnostics)))


class MechanicsMultimodalModeler:
    def __init__(self, generator: EnvelopeGenerator) -> None:
        if generator is None:
            raise ValueError("An explicit envelope generator is required.")
        self._generator = generator

    def interpret(
        self,
        *,
        problem_text: str,
        images: Sequence[SanitizedImage] = (),
        confirmations: Iterable[EvidenceConfirmation] = (),
    ) -> MultimodalModelerOutcome:
        if not isinstance(problem_text, str) or not problem_text.strip():
            empty = reconcile_evidence(())
            return MultimodalModelerOutcome(
                terminal=MultimodalModelerTerminal.blocked,
                envelope=None,
                reconciliation=empty,
                authority_audit=AuthorityAudit(passed=True, findings=()),
                diagnostics=("problem_text_required",),
            )
        generated = self._generator(problem_text, tuple(images))
        envelope = generated if isinstance(generated, MechanicsModelingEnvelopeV1) else MechanicsModelingEnvelopeV1.model_validate(generated)
        authority = audit_modeling_payload(envelope)
        image_diagnostics = _validate_image_bindings(envelope, images)
        if not authority.passed or image_diagnostics:
            reconciliation = reconcile_evidence(())
            return MultimodalModelerOutcome(
                terminal=MultimodalModelerTerminal.blocked,
                envelope=None,
                reconciliation=reconciliation,
                authority_audit=authority,
                diagnostics=tuple(sorted(set(image_diagnostics + (("forbidden_authority",) if not authority.passed else ())))),
            )
        reconciliation = reconcile_evidence(evidence_candidates_from_envelope(envelope), confirmations)
        terminal = {
            ReconciliationStatus.ready: MultimodalModelerTerminal.ready,
            ReconciliationStatus.confirmation_required: MultimodalModelerTerminal.confirmation_required,
            ReconciliationStatus.blocked: MultimodalModelerTerminal.blocked,
        }[reconciliation.status]
        return MultimodalModelerOutcome(terminal, envelope, reconciliation, authority, ())


__all__ = [
    "EnvelopeGenerator",
    "MechanicsMultimodalModeler",
    "MultimodalModelerOutcome",
    "MultimodalModelerTerminal",
    "evidence_candidates_from_envelope",
]
