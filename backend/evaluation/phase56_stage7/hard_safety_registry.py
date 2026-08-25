"""One named instrument per hard-safety signal, and the measurement it yields.

Why this exists.  The gate used to report `hard_safety: {result: PASS,
all_zero: true}` over a catalog of twenty-three signals while six of them had a
counter and the other seventeen had nothing bound at all.  Seventeen unexamined
properties reported as zero is not a safety claim; it is the absence of one.

The rule this module enforces is therefore: **an unmeasured signal is
NOT_MEASURED, and NOT_MEASURED fails strict mode.**  A signal reaches zero only
by an instrument that ran in *this* run and could have said otherwise.

Two kinds of binding exist, and both must produce evidence from the run itself:

* a **counter** — a number the Lane B scorer or the environment guard actually
  produced.  Present-and-integral counts as measured; absent or `None` does not,
  because "the scorer never ran" and "the scorer found none" are different
  states and only one of them is safe.
* a **test binding** — exact pytest node IDs that attack the property.  Measured
  requires every bound node to have *run*; violations are the ones that failed.
  A node that could not be collected is NOT_MEASURED, never an implicit pass.

Nothing here reads a case, a family, a problem text, or an expected answer: an
instrument names a module or a test, and yields an integer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from evaluation.phase56_stage7.contracts import Stage7HardSafetySignal

HARD_SAFETY_REGISTRY_VERSION = "phase56-stage7-hard-safety-registry-v1"

_ATTACKS = "tests/test_phase56_stage7_hard_safety_instruments.py"
_GOLD = "tests/test_phase56_stage7_gold_isolation.py"
_API = "tests/test_phase56_stage6_api_runtime_integration.py"
_RECONCILE = "tests/test_phase56_stage6_reconciliation.py"
_COMPILER = "tests/test_phase56_mechanics_compiler.py"
_SOLVER = "tests/test_phase56_mechanics_solver_execution.py"
_PARSER = "tests/test_phase55_textbook_parser.py"


class InstrumentKind(str, Enum):
    """How a signal is measured.  Not decoration: it states what the zero rests on."""

    scorer_counter = "scorer_counter"
    runtime_counter = "runtime_counter"
    attack_test = "attack_test"
    static_source_guard = "static_source_guard"
    api_negative_control = "api_negative_control"
    solver_candidate_audit = "solver_candidate_audit"
    privacy_logging_audit = "privacy_logging_audit"
    revision_correction_audit = "revision_correction_audit"


@dataclass(frozen=True, slots=True)
class HardSafetyInstrumentV1:
    """The binding between one signal and the evidence that can refute it."""

    signal: Stage7HardSafetySignal
    kind: InstrumentKind
    # Counter keys are read from the gate's own measured counters.
    counter_keys: tuple[str, ...] = ()
    # Node IDs are run by the gate and must all have executed.
    node_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.counter_keys and not self.node_ids:
            raise ValueError(f"{self.signal.value} has no binding at all")


def _n(*names: str) -> tuple[str, ...]:
    return names


REGISTRY: tuple[HardSafetyInstrumentV1, ...] = (
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.confident_wrong_solve,
        kind=InstrumentKind.scorer_counter,
        counter_keys=_n("wrong_solves", "solved_but_unscored", "blocked_numeric_answers"),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.invented_explicit_numeric_fact,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_COMPILER}::test_direct_query_value_injection_is_nonclosing",
            f"{_COMPILER}::test_indirect_two_unknown_injection_cannot_borrow_a_server_equation",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.answer_authority_violation,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_ATTACKS}::test_every_audited_authority_field_is_rejected_at_the_top_level",
            f"{_ATTACKS}::test_every_audited_authority_field_is_rejected_when_buried",
            f"{_ATTACKS}::test_every_draft_answer_authority_field_is_found_when_buried",
            f"{_ATTACKS}::test_the_draft_prescan_refuses_the_answer_core",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.model_selected_solver_authority,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_ATTACKS}::test_every_envelope_authority_field_is_found_when_buried",
            f"{_ATTACKS}::test_every_surface_effectively_refuses_the_authority_core",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.executable_model_equation,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_ATTACKS}::test_every_audited_authority_field_is_rejected_when_buried",
            f"{_ATTACKS}::test_every_envelope_authority_field_is_found_when_buried",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.selected_root_authority,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_ATTACKS}::test_every_surface_effectively_refuses_the_authority_core",
            f"{_ATTACKS}::test_correction_cannot_carry_an_authority_key_at_the_top_level",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.expected_answer_leakage,
        kind=InstrumentKind.static_source_guard,
        node_ids=_n(
            f"{_GOLD}::test_expected_answer_lookup_cannot_reach_runtime_or_cache",
            f"{_ATTACKS}::test_production_runtime_never_reads_a_gold_member_by_name",
            f"{_ATTACKS}::test_the_gold_member_guard_can_actually_fail",
            f"{_ATTACKS}::test_the_gold_member_guard_does_not_flag_a_denylist",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.gold_metadata_runtime_leakage,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_GOLD}::test_adapter_emits_no_gold_token_into_runtime_material",
            f"{_GOLD}::test_direct_forbidden_field_is_rejected",
            f"{_GOLD}::test_nested_forbidden_field_is_rejected_at_depth",
            f"{_GOLD}::test_alias_spellings_of_forbidden_fields_are_rejected",
            f"{_GOLD}::test_runtime_domain_module_never_imports_gold_or_corpus_modules",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.case_id_routing,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_GOLD}::test_case_id_routing_cannot_change_a_deterministic_result",
            f"{_GOLD}::test_cache_identity_excludes_the_opaque_token_but_covers_real_input",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.family_routing,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_GOLD}::test_family_split_chapter_and_terminal_routing_cannot_reach_runtime",
            f"{_GOLD}::test_filename_and_path_routing_is_not_expressible",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.unsafe_legacy_fallback,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_ATTACKS}::test_every_audited_authority_field_is_rejected_at_the_top_level",
            f"{_ATTACKS}::test_every_audited_authority_field_is_rejected_when_buried",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.deferred_silent_solve,
        kind=InstrumentKind.scorer_counter,
        counter_keys=_n("deferred_silent_solves", "blocked_silent_solves"),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.unresolved_conflict_solve,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_RECONCILE}::test_explicit_conflict_requires_exact_confirmation",
            f"{_RECONCILE}::test_stale_conflict_binding_is_blocked",
            f"{_RECONCILE}::test_figure_convention_is_never_silently_promoted",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.correction_bypass,
        kind=InstrumentKind.revision_correction_audit,
        node_ids=_n(
            f"{_ATTACKS}::test_correction_cannot_smuggle_an_authority_key_inside_an_operation",
            f"{_ATTACKS}::test_every_forbidden_patch_field_is_covered_by_an_attack",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.stale_revision_acceptance,
        kind=InstrumentKind.api_negative_control,
        node_ids=_n(
            f"{_API}::test_source_only_correction_is_revisioned_idempotent_and_reruns_runtime",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.direct_graph_patch,
        kind=InstrumentKind.revision_correction_audit,
        node_ids=_n(
            f"{_ATTACKS}::test_correction_cannot_carry_an_authority_key_at_the_top_level",
            f"{_ATTACKS}::test_correction_cannot_smuggle_an_authority_key_inside_an_operation",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.direct_answer_patch,
        kind=InstrumentKind.revision_correction_audit,
        node_ids=_n(
            f"{_ATTACKS}::test_correction_cannot_carry_an_authority_key_at_the_top_level",
            f"{_ATTACKS}::test_every_forbidden_patch_field_is_covered_by_an_attack",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.raw_image_or_base64_logging,
        kind=InstrumentKind.privacy_logging_audit,
        node_ids=_n(
            f"{_ATTACKS}::test_no_log_record_carries_image_bytes_or_base64",
            f"{_ATTACKS}::test_metric_payload_audit_rejects_source_bearing_telemetry",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.raw_provider_output_logging,
        kind=InstrumentKind.privacy_logging_audit,
        node_ids=_n(
            f"{_ATTACKS}::test_no_log_record_carries_raw_provider_output",
            f"{_ATTACKS}::test_metric_payload_audit_rejects_source_bearing_telemetry",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.prompt_injection_authority,
        kind=InstrumentKind.attack_test,
        node_ids=_n(
            f"{_PARSER}::test_problem_prompt_injection_is_only_source_content",
            f"{_GOLD}::test_prompt_material_is_exactly_the_user_like_input",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.unbounded_repair_or_retry,
        kind=InstrumentKind.api_negative_control,
        node_ids=_n(
            f"{_API}::test_provider_repair_is_at_most_one_fresh_full_attempt",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.candidate_root_early_discard,
        kind=InstrumentKind.solver_candidate_audit,
        node_ids=_n(
            f"{_SOLVER}::test_polynomial_retains_both_real_roots_in_canonical_order",
            f"{_SOLVER}::test_univariate_polynomial_certificate_preserves_repeated_root_multiplicity",
            f"{_SOLVER}::test_parent_detects_x_squared_root_omission_and_multiplicity_mismatch",
        ),
    ),
    HardSafetyInstrumentV1(
        signal=Stage7HardSafetySignal.private_heldout_access,
        kind=InstrumentKind.runtime_counter,
        counter_keys=_n("private_heldout_accesses"),
    ),
)


def _validate_registry() -> None:
    bound = tuple(item.signal for item in REGISTRY)
    if len(set(bound)) != len(bound):
        raise ValueError("a signal may be bound exactly once")
    if set(bound) != set(Stage7HardSafetySignal):
        missing = sorted(
            signal.value for signal in Stage7HardSafetySignal if signal not in set(bound)
        )
        raise ValueError(f"unbound hard-safety signals: {missing}")


_validate_registry()


def bound_node_ids() -> tuple[str, ...]:
    """Every node ID the registry needs run, de-duplicated and ordered."""

    return tuple(sorted({node for item in REGISTRY for node in item.node_ids}))


# Several catalog signal names are themselves forbidden redaction substrings —
# `private_heldout_access` contains `private_heldout`, and the artifact's privacy
# guard rejects that marker wherever it appears, correctly and without
# exception.  The artifact therefore identifies a signal by its **index into the
# frozen catalog**, which the evaluation contract pins in declaration order and
# refuses to let drift.  The index is exact and reversible for anyone holding the
# contract, and carries no substring at all.
_CATALOG_INDEX: Mapping[Stage7HardSafetySignal, int] = {
    signal: index for index, signal in enumerate(Stage7HardSafetySignal)
}

# Why a signal was not measured, as a closed vocabulary.  The specific counter
# key or node name is deliberately not emitted: node IDs are free text from the
# test tree, and the artifact does not carry free text.
_UNMEASURED_COUNTER = "counter_absent"
_UNMEASURED_ATTACK = "attack_not_run"


@dataclass(frozen=True, slots=True)
class SignalMeasurement:
    signal: Stage7HardSafetySignal
    kind: InstrumentKind
    measured: bool
    violations: int | None
    detail: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_index": _CATALOG_INDEX[self.signal],
            "instrument": self.kind.value,
            "measured": self.measured,
            "violations": self.violations,
            "unmeasured_reason": self.detail,
        }


def measure_signals(
    *,
    counters: Mapping[str, Any],
    node_outcomes: Mapping[str, str],
) -> tuple[SignalMeasurement, ...]:
    """Measure every catalog signal from this run's own evidence.

    `counters` maps counter key to the number the run produced (or None).
    `node_outcomes` maps a bound node ID to "PASSED", "FAILED", or "NOT_RUN".
    """

    results: list[SignalMeasurement] = []
    for item in REGISTRY:
        violations = 0
        measured = True
        detail: str | None = None

        for key in item.counter_keys:
            value = counters.get(key)
            if not isinstance(value, int) or isinstance(value, bool):
                measured = False
                detail = _UNMEASURED_COUNTER
                break
            violations += value

        if measured:
            for node in item.node_ids:
                outcome = node_outcomes.get(node, "NOT_RUN")
                if outcome == "FAILED":
                    violations += 1
                elif outcome != "PASSED":
                    measured = False
                    detail = _UNMEASURED_ATTACK
                    break

        results.append(
            SignalMeasurement(
                signal=item.signal,
                kind=item.kind,
                measured=measured,
                violations=violations if measured else None,
                detail=detail,
            )
        )
    return tuple(results)


def summarize(measurements: tuple[SignalMeasurement, ...]) -> dict[str, Any]:
    """The counts the strict gate binds to, plus the per-signal registry."""

    measured = [item for item in measurements if item.measured]
    nonzero = [item for item in measured if (item.violations or 0) > 0]
    return {
        "registry_version": HARD_SAFETY_REGISTRY_VERSION,
        "per_signal_instrument_registry": "IMPLEMENTED",
        "signal_count": len(measurements),
        "measured_signal_count": len(measured),
        "unbound_signal_count": len(measurements) - len(measured),
        "nonzero_signal_count": len(nonzero),
        "signals": [item.as_dict() for item in measurements],
    }


__all__ = [
    "HARD_SAFETY_REGISTRY_VERSION",
    "HardSafetyInstrumentV1",
    "InstrumentKind",
    "REGISTRY",
    "SignalMeasurement",
    "bound_node_ids",
    "measure_signals",
    "summarize",
]
