"""Deterministic reconciliation for text and figure evidence.

Confidence is diagnostic only. Conflicting explicit evidence is never resolved by
model confidence or source order; an exact user confirmation is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence


class ReconciliationStatus(StrEnum):
    ready = "ready"
    confirmation_required = "confirmation_required"
    blocked = "blocked"


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    source_id: str
    source_type: str
    semantic_target_key: str
    normalized_value: str | None
    normalized_unit: str | None
    direction: str | None = None
    policy_eligibility: str = "automatic"
    provenance: str | None = None

    @property
    def value_key(self) -> tuple[str | None, str | None, str | None]:
        return self.normalized_value, self.normalized_unit, self.direction

    @property
    def fingerprint(self) -> str:
        return _digest(
            {
                "source_id": self.source_id,
                "source_type": self.source_type,
                "semantic_target_key": self.semantic_target_key,
                "value_key": self.value_key,
                "policy_eligibility": self.policy_eligibility,
                "provenance": self.provenance,
            }
        )


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    conflict_id: str
    fingerprint: str
    semantic_target_key: str
    candidate_fingerprints: tuple[str, ...]
    candidate_source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceConfirmation:
    conflict_id: str
    conflict_fingerprint: str
    chosen_source_id: str
    chosen_candidate_fingerprint: str


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    status: ReconciliationStatus
    selected: tuple[EvidenceCandidate, ...]
    conflicts: tuple[EvidenceConflict, ...]
    ignored_source_ids: tuple[str, ...]


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(type(value).__name__)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def semantic_target_key(target: Any) -> str:
    if hasattr(target, "model_dump"):
        target = target.model_dump(mode="json")
    if isinstance(target, Mapping):
        allowed = {
            "kind": target.get("kind"),
            "target_id": target.get("target_id"),
            "role": target.get("role"),
            "component": target.get("component"),
            "relation_kind": target.get("relation_kind"),
        }
        return _digest(allowed)
    return _digest(str(target))


def candidate_from_mapping(value: Mapping[str, Any]) -> EvidenceCandidate:
    target = value.get("semantic_target")
    return EvidenceCandidate(
        source_id=str(value.get("source_id") or value.get("evidence_id") or value.get("observation_id") or ""),
        source_type=str(value.get("source_type") or value.get("evidence_origin") or value.get("provenance") or "unknown"),
        semantic_target_key=semantic_target_key(target),
        normalized_value=_optional_text(value.get("normalized_value", value.get("observed_value"))),
        normalized_unit=_optional_text(value.get("normalized_unit", value.get("unit_candidate"))),
        direction=_optional_text(value.get("direction_candidate", value.get("direction"))),
        policy_eligibility=str(value.get("policy_eligibility") or "automatic"),
        provenance=_optional_text(value.get("provenance")),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    text = str(value).strip()
    return text or None


def _automatic(candidate: EvidenceCandidate) -> bool:
    eligibility = candidate.policy_eligibility.lower()
    provenance = (candidate.provenance or candidate.source_type).lower()
    if eligibility != "automatic":
        return False
    if "convention" in provenance:
        return False
    return True


def _build_conflict(target_key: str, candidates: Sequence[EvidenceCandidate]) -> EvidenceConflict:
    ordered = tuple(sorted(candidates, key=lambda item: (item.source_id, item.fingerprint)))
    fingerprints = tuple(item.fingerprint for item in ordered)
    source_ids = tuple(item.source_id for item in ordered)
    fingerprint = _digest(
        {
            "semantic_target_key": target_key,
            "candidate_fingerprints": fingerprints,
            "candidate_source_ids": source_ids,
        }
    )
    return EvidenceConflict(
        conflict_id=f"conflict_{fingerprint[:20]}",
        fingerprint=fingerprint,
        semantic_target_key=target_key,
        candidate_fingerprints=fingerprints,
        candidate_source_ids=source_ids,
    )


def reconcile_evidence(
    candidates: Iterable[EvidenceCandidate],
    confirmations: Iterable[EvidenceConfirmation] = (),
) -> ReconciliationResult:
    ordered = tuple(sorted(candidates, key=lambda item: (item.semantic_target_key, item.source_id, item.fingerprint)))
    if any(not item.source_id or not item.semantic_target_key for item in ordered):
        return ReconciliationResult(ReconciliationStatus.blocked, (), (), ())

    confirmation_by_conflict = {item.conflict_id: item for item in confirmations}
    if len(confirmation_by_conflict) != len(tuple(confirmations)):
        return ReconciliationResult(ReconciliationStatus.blocked, (), (), ())

    selected: list[EvidenceCandidate] = []
    conflicts: list[EvidenceConflict] = []
    ignored: list[str] = []
    groups: dict[str, list[EvidenceCandidate]] = {}
    for candidate in ordered:
        groups.setdefault(candidate.semantic_target_key, []).append(candidate)

    for target_key in sorted(groups):
        group = groups[target_key]
        eligible = [item for item in group if _automatic(item)]
        ignored.extend(item.source_id for item in group if item not in eligible)
        if not eligible:
            continue

        value_groups: dict[tuple[str | None, str | None, str | None], list[EvidenceCandidate]] = {}
        for item in eligible:
            value_groups.setdefault(item.value_key, []).append(item)
        if len(value_groups) == 1:
            selected.append(sorted(eligible, key=lambda item: (item.source_id, item.fingerprint))[0])
            continue

        conflict = _build_conflict(target_key, eligible)
        confirmation = confirmation_by_conflict.get(conflict.conflict_id)
        if confirmation is None:
            conflicts.append(conflict)
            continue
        if confirmation.conflict_fingerprint != conflict.fingerprint:
            return ReconciliationResult(ReconciliationStatus.blocked, (), tuple(conflicts + [conflict]), tuple(sorted(set(ignored))))
        matches = [
            item
            for item in eligible
            if item.source_id == confirmation.chosen_source_id
            and item.fingerprint == confirmation.chosen_candidate_fingerprint
        ]
        if len(matches) != 1:
            return ReconciliationResult(ReconciliationStatus.blocked, (), tuple(conflicts + [conflict]), tuple(sorted(set(ignored))))
        selected.append(matches[0])

    status = ReconciliationStatus.confirmation_required if conflicts else ReconciliationStatus.ready
    return ReconciliationResult(
        status=status,
        selected=tuple(sorted(selected, key=lambda item: (item.semantic_target_key, item.source_id))),
        conflicts=tuple(sorted(conflicts, key=lambda item: item.conflict_id)),
        ignored_source_ids=tuple(sorted(set(ignored))),
    )


__all__ = [
    "EvidenceCandidate",
    "EvidenceConfirmation",
    "EvidenceConflict",
    "ReconciliationResult",
    "ReconciliationStatus",
    "candidate_from_mapping",
    "reconcile_evidence",
    "semantic_target_key",
]
