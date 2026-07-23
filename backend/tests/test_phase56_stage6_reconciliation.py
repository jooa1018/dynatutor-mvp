from __future__ import annotations

from engine.mechanics.evidence_reconciliation import (
    EvidenceCandidate,
    EvidenceConfirmation,
    ReconciliationStatus,
    reconcile_evidence,
)


def _candidate(source_id: str, value: str, *, eligibility: str = "automatic", provenance: str = "explicit") -> EvidenceCandidate:
    return EvidenceCandidate(
        source_id=source_id,
        source_type="text" if source_id.startswith("text") else "figure",
        semantic_target_key="a" * 64,
        normalized_value=value,
        normalized_unit="N",
        policy_eligibility=eligibility,
        provenance=provenance,
    )


def test_reconciliation_is_input_order_invariant() -> None:
    first = _candidate("text_1", "10")
    second = _candidate("figure_1", "10")
    forward = reconcile_evidence((first, second))
    reverse = reconcile_evidence((second, first))
    assert forward == reverse
    assert forward.status is ReconciliationStatus.ready
    assert forward.selected[0].source_id == "figure_1"


def test_explicit_conflict_requires_exact_confirmation() -> None:
    text = _candidate("text_1", "10")
    figure = _candidate("figure_1", "12")
    unresolved = reconcile_evidence((text, figure))
    assert unresolved.status is ReconciliationStatus.confirmation_required
    assert len(unresolved.conflicts) == 1
    conflict = unresolved.conflicts[0]

    chosen = figure
    confirmation = EvidenceConfirmation(
        conflict_id=conflict.conflict_id,
        conflict_fingerprint=conflict.fingerprint,
        chosen_source_id=chosen.source_id,
        chosen_candidate_fingerprint=chosen.fingerprint,
    )
    resolved = reconcile_evidence((figure, text), (confirmation,))
    assert resolved.status is ReconciliationStatus.ready
    assert resolved.conflicts == ()
    assert resolved.selected == (figure,)


def test_stale_conflict_binding_is_blocked() -> None:
    text = _candidate("text_1", "10")
    figure = _candidate("figure_1", "12")
    conflict = reconcile_evidence((text, figure)).conflicts[0]
    stale = EvidenceConfirmation(
        conflict_id=conflict.conflict_id,
        conflict_fingerprint="0" * 64,
        chosen_source_id=text.source_id,
        chosen_candidate_fingerprint=text.fingerprint,
    )
    result = reconcile_evidence((text, figure), (stale,))
    assert result.status is ReconciliationStatus.blocked
    assert result.selected == ()


def test_figure_convention_is_never_silently_promoted() -> None:
    explicit = _candidate("text_1", "10")
    convention = _candidate(
        "figure_convention",
        "12",
        eligibility="automatic",
        provenance="figure_convention",
    )
    result = reconcile_evidence((explicit, convention))
    assert result.status is ReconciliationStatus.ready
    assert result.selected == (explicit,)
    assert result.ignored_source_ids == ("figure_convention",)
