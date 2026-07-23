"""Interpretation-only orchestration for Stage 6 multimodal modeling.

The injected generator may describe source-grounded evidence and a typed draft.
It cannot select equations, solvers, roots, verification results, or answers.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from engine.mechanics.evidence_reconciliation import (
    EvidenceCandidate,
    EvidenceConfirmation,
    EvidenceConflict,
    ReconciliationResult,
    ReconciliationStatus,
    candidate_from_mapping,
    reconcile_evidence,
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
        self,
        problem_text: str,
        images: tuple[SanitizedImage, ...],
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
        return dict(value.model_dump(mode="python"))
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
    result: list[EvidenceCandidate] = []
    for evidence in envelope.text_evidence:
        payload = _dump(evidence)
        if payload.get("normalized_value") is None and payload.get("observed_value") is None and payload.get("direction_candidate") is None:
            continue
        result.append(candidate_from_mapping(payload))
    return result


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

        image_id = str(payload.get("image_id") or "")
        image = by_id.get(image_id)
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
            actual = payload.get(field)
            if actual != expected_value:
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
    """Validate a generated envelope and hand only confirmed draft data onward."""

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
        envelope = (
            generated
            if isinstance(generated, MechanicsModelingEnvelopeV1)
            else MechanicsModelingEnvelopeV1.model_validate(generated)
        )
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

        candidates = tuple(_text_candidates(envelope) + _figure_candidates(envelope))
        reconciliation = reconcile_evidence(candidates, confirmations)
        terminal = {
            ReconciliationStatus.ready: MultimodalModelerTerminal.ready,
            ReconciliationStatus.confirmation_required: MultimodalModelerTerminal.confirmation_required,
            ReconciliationStatus.blocked: MultimodalModelerTerminal.blocked,
        }[reconciliation.status]
        return MultimodalModelerOutcome(
            terminal=terminal,
            envelope=envelope,
            reconciliation=reconciliation,
            authority_audit=authority,
            diagnostics=(),
        )


__all__ = [
    "EnvelopeGenerator",
    "MechanicsMultimodalModeler",
    "MultimodalModelerOutcome",
    "MultimodalModelerTerminal",
]
