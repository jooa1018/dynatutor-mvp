"""Pure offline/shadow diagnostics and typed migration-scope accounting.

Nothing here executes another kernel or changes generic graph, plan, candidate,
verification, terminal, or selection authority.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from engine.mechanics.migration.contracts import (
    DEFERRED_LEGACY_SOLVER_IDS,
    LEGACY_SOLVER_DEFERRED_COUNT,
    LEGACY_SOLVER_IN_SCOPE_COUNT,
    LEGACY_SOLVER_INVENTORY,
    LEGACY_SOLVER_INVENTORY_COUNT,
    CandidateInvarianceRecord,
    DiagnosticAttemptInvarianceRecord,
    DiagnosticEntryInvarianceRecord,
    DiagnosticTimeoutInvarianceRecord,
    DifferentialStatus,
    DiscrepancyCode,
    GenericResultInvarianceSignature,
    InvarianceComparison,
    InvarianceField,
    InvarianceVariantComparison,
    LabelledInvarianceVariant,
    LegacyDifferentialReport,
    LegacyMigrationProgress,
    LegacyObservation,
    LegacySolverFutureExtension,
    LegacySolverId,
    LegacySolverInventoryState,
    LegacySolverLegacyAuthority,
    LegacySolverMigrationRecord,
    LegacySolverMigrationState,
    LegacySolverProductGenericAuthority,
    LegacySolverRuntimeBehavior,
    LegacySolverSameFixtureState,
    LegacySolverScopeState,
    LegacySolverSilentFallback,
    LegacyTerminal,
    PARITY_ABSOLUTE_TOLERANCE,
    PARITY_RELATIVE_TOLERANCE,
    VerificationOutcomeInvarianceRecord,
)
from engine.mechanics.solver.contracts import (
    CandidateCoverage,
    canonical_candidate_sha256,
)
from engine.mechanics.verification.contracts import (
    MechanicsSolveResult,
    MechanicsSolveTerminal,
    render_canonical_si_unit,
)


def build_legacy_migration_progress(
    records: tuple[LegacySolverMigrationRecord, ...],
) -> LegacyMigrationProgress:
    """Aggregate exact inventory rows without promoting case-level evidence."""

    if type(records) is not tuple:
        raise TypeError("migration progress records require an exact tuple")
    if any(type(item) is not LegacySolverMigrationRecord for item in records):
        raise TypeError("migration progress requires exact inventory record types")
    exact_records = tuple(
        LegacySolverMigrationRecord.model_validate(item.model_dump(mode="python"))
        for item in records
    )
    accepted = sum(
        item.scope_state is LegacySolverScopeState.IN_CURRENT_COURSE_SCOPE
        and item.migration_state is LegacySolverMigrationState.ACCEPTED
        for item in exact_records
    )
    pending = sum(
        item.scope_state is LegacySolverScopeState.IN_CURRENT_COURSE_SCOPE
        and item.migration_state is LegacySolverMigrationState.PENDING
        for item in exact_records
    )
    return LegacyMigrationProgress(
        records=exact_records,
        inventory_count=LEGACY_SOLVER_INVENTORY_COUNT,
        in_scope_count=LEGACY_SOLVER_IN_SCOPE_COUNT,
        deferred_count=LEGACY_SOLVER_DEFERRED_COUNT,
        accepted_in_scope_count=accepted,
        pending_in_scope_count=pending,
        in_scope_complete=accepted == LEGACY_SOLVER_IN_SCOPE_COUNT,
    )


def assert_legacy_migration_coverage_complete(
    progress: LegacyMigrationProgress,
) -> LegacyMigrationProgress:
    """Return exact complete coverage or reject any partial/deferred overcount."""

    if type(progress) is not LegacyMigrationProgress:
        raise TypeError("migration coverage assertion requires exact progress")
    exact = LegacyMigrationProgress.model_validate(progress.model_dump(mode="python"))
    accepted = sum(
        item.scope_state is LegacySolverScopeState.IN_CURRENT_COURSE_SCOPE
        and item.migration_state is LegacySolverMigrationState.ACCEPTED
        for item in exact.records
    )
    if (
        accepted != LEGACY_SOLVER_IN_SCOPE_COUNT
        or exact.accepted_in_scope_count != LEGACY_SOLVER_IN_SCOPE_COUNT
        or exact.pending_in_scope_count != 0
        or not exact.in_scope_complete
    ):
        raise ValueError(
            "migration coverage is incomplete; deferred records never count as accepted"
        )
    return exact


def build_legacy_differential_report(
    generic_result: MechanicsSolveResult,
    observation: LegacyObservation,
) -> LegacyDifferentialReport:
    """Compare completed paths for diagnostics without changing either result.

    The returned report is suitable only for bounded offline or shadow
    migration evidence.  It cannot select or authorize a numeric answer.
    """

    result = _validated_exact_result(generic_result)
    exact_observation = _validated_exact_observation(observation)
    signature = _build_generic_result_invariance_signature(result)
    discrepancies: set[DiscrepancyCode] = set()
    if result.terminal is not MechanicsSolveTerminal.solved:
        discrepancies.add(DiscrepancyCode.generic_nonsolved_result)
    if exact_observation.terminal is LegacyTerminal.not_comparable:
        discrepancies.add(DiscrepancyCode.observation_not_comparable)
    else:
        generic_unit = _generic_query_si_unit(result)
        if exact_observation.query_symbol_id != result.plan.query_symbol_id:
            discrepancies.add(DiscrepancyCode.query_symbol_mismatch)
        if exact_observation.si_unit != generic_unit:
            discrepancies.add(DiscrepancyCode.canonical_si_unit_mismatch)
        if exact_observation.terminal.value != result.terminal.value:
            discrepancies.add(DiscrepancyCode.terminal_mismatch)
        if exact_observation.residual_passed is False:
            discrepancies.add(DiscrepancyCode.residual_failed)
        selected_matches = _selected_scalar_matches(result, exact_observation)
        if result.terminal is MechanicsSolveTerminal.solved and not selected_matches:
            discrepancies.add(DiscrepancyCode.selected_scalar_mismatch)
        if (
            result.terminal is not MechanicsSolveTerminal.solved
            and exact_observation.terminal is LegacyTerminal.solved
        ):
            discrepancies.add(DiscrepancyCode.generic_nonsolved_promotion_forbidden)

        generic_scalars, scalar_issue = _generic_candidate_scalars(result)
        if scalar_issue is not None:
            discrepancies.add(scalar_issue)
        else:
            if (
                not result.candidate_set.generation_complete
                or result.candidate_set.coverage is not CandidateCoverage.exhaustive_symbolic
            ):
                discrepancies.add(DiscrepancyCode.generic_candidates_not_exhaustive)
            observed_candidates = exact_observation.complete_candidate_scalars_si
            if observed_candidates is None:
                discrepancies.add(DiscrepancyCode.exhaustive_candidates_not_exposed)
            else:
                observed_scalars = tuple(
                    value
                    for item in observed_candidates
                    for value in (item.value_si,) * item.multiplicity
                )
                if generic_scalars is None or not _scalar_multisets_match(generic_scalars, observed_scalars):
                    discrepancies.add(DiscrepancyCode.candidate_multiset_mismatch)

    ordered_discrepancies = tuple(
        item for item in DiscrepancyCode if item in discrepancies
    )
    if (
        DiscrepancyCode.observation_not_comparable in discrepancies
        or DiscrepancyCode.generic_query_not_scalar in discrepancies
        or DiscrepancyCode.generic_nonsolved_result in discrepancies
        or DiscrepancyCode.candidate_multiplicity_bound_exceeded in discrepancies
    ):
        status = DifferentialStatus.not_comparable
    elif not discrepancies:
        status = DifferentialStatus.full_parity
    elif (
        ordered_discrepancies
        == (DiscrepancyCode.exhaustive_candidates_not_exposed,)
        and result.terminal is MechanicsSolveTerminal.solved
        and exact_observation.terminal is LegacyTerminal.solved
    ):
        status = DifferentialStatus.selected_output_only_match
    else:
        status = DifferentialStatus.mismatch

    return LegacyDifferentialReport(
        generic_invariance_signature=signature,
        graph_fingerprint=result.plan.graph_fingerprint,
        plan_fingerprint=result.plan.plan_fingerprint,
        primary_backend=result.plan.primary_backend,
        permitted_numeric_fallback=result.plan.permitted_numeric_fallback,
        generic_terminal=result.terminal,
        generic_candidate_coverage=result.candidate_set.coverage,
        generic_generation_complete=result.candidate_set.generation_complete,
        generic_candidate_manifest=result.candidate_set.manifest,
        generic_candidate_ids=tuple(
            item.candidate_id for item in result.candidate_set.manifest
        ),
        generic_verification_outcomes=signature.verification_outcomes,
        generic_rejection_authoritative_sha256=signature.rejection_authoritative_sha256,
        generic_verified_candidate_ids=signature.verified_candidate_ids,
        generic_selected_candidate_id=result.selected_candidate_id,
        observation_case_id=exact_observation.case_id,
        observation_kernel_id=exact_observation.diagnostic_kernel_id,
        observation_terminal=exact_observation.terminal,
        observation_sha256=_canonical_hash(exact_observation),
        status=status,
        discrepancies=ordered_discrepancies,
    )


def build_generic_result_invariance_signature(
    result: MechanicsSolveResult,
) -> GenericResultInvarianceSignature:
    """Project exact generic authority while excluding elapsed diagnostics.

    This deterministic signature is diagnostics-only and cannot verify,
    select, repair, or replace the supplied generic result.
    """

    exact_result = _validated_exact_result(result)
    return _build_generic_result_invariance_signature(exact_result)


def _build_generic_result_invariance_signature(
    result: MechanicsSolveResult,
) -> GenericResultInvarianceSignature:
    candidates = tuple(
        CandidateInvarianceRecord(
            generation_index=candidate.generation_index,
            candidate_id=candidate.candidate_id,
            backend=candidate.backend,
            root_index=candidate.root_index,
            branch_ids=candidate.branch_ids,
            authoritative_sha256=canonical_candidate_sha256(candidate),
            query_value_si=candidate.query_value_si,
            root_multiplicity=candidate.root_multiplicity,
        )
        for candidate in result.candidate_set.candidates
    )
    outcomes = tuple(
        VerificationOutcomeInvarianceRecord(
            candidate_id=outcome.candidate_id,
            passed=outcome.passed,
            authoritative_sha256=_canonical_hash(outcome),
            rejection_authoritative_sha256=tuple(
                _canonical_hash(rejection) for rejection in outcome.rejections
            ),
        )
        for outcome in result.verification_outcomes
    )
    return GenericResultInvarianceSignature(
        graph_fingerprint=result.plan.graph_fingerprint,
        plan_fingerprint=result.plan.plan_fingerprint,
        primary_backend=result.plan.primary_backend,
        permitted_numeric_fallback=result.plan.permitted_numeric_fallback,
        candidate_coverage=result.candidate_set.coverage,
        generation_complete=result.candidate_set.generation_complete,
        candidate_records=candidates,
        verification_outcomes=outcomes,
        rejection_authoritative_sha256=tuple(
            _canonical_hash(rejection) for rejection in result.rejections
        ),
        verified_candidate_ids=tuple(
            item.candidate.candidate_id for item in result.verified_candidates
        ),
        diagnostic_entries=tuple(
            DiagnosticEntryInvarianceRecord(
                code=item.code,
                severity=item.severity,
                phase=item.phase,
                backend=item.backend,
                referenced_id=item.referenced_id,
            )
            for item in result.diagnostics.entries
        ),
        diagnostic_attempts=tuple(
            DiagnosticAttemptInvarianceRecord(
                attempt_index=item.attempt_index,
                backend=item.backend,
                phase=item.phase,
                completed=item.completed,
            )
            for item in result.diagnostics.attempts
        ),
        diagnostic_timeout=(
            None
            if result.diagnostics.timeout is None
            else DiagnosticTimeoutInvarianceRecord(
                phase=result.diagnostics.timeout.phase,
                backend=result.diagnostics.timeout.backend,
                limit_s=result.diagnostics.timeout.limit_s,
            )
        ),
        terminal=result.terminal,
        selected_candidate_id=result.selected_candidate_id,
    )


def compare_generic_result_invariance(
    baseline: GenericResultInvarianceSignature,
    variants: tuple[LabelledInvarianceVariant, ...],
) -> InvarianceComparison:
    """Compare labelled signatures field-by-field for diagnostic use only."""

    if len(variants) > 64:
        raise ValueError("invariance comparison accepts at most 64 variants")
    labels = tuple(item.label for item in variants)
    if len(set(labels)) != len(labels):
        raise ValueError("invariance variant labels must be unique")
    comparisons = tuple(
        _compare_variant(baseline, variant)
        for variant in variants
    )
    return InvarianceComparison(
        baseline_signature_sha256=baseline.signature_sha256,
        variants=comparisons,
    )


def _compare_variant(
    baseline: GenericResultInvarianceSignature,
    variant: LabelledInvarianceVariant,
) -> InvarianceVariantComparison:
    differing = tuple(
        field
        for field in InvarianceField
        if getattr(baseline, field.value) != getattr(variant.signature, field.value)
    )
    return InvarianceVariantComparison(
        label=variant.label,
        kind=variant.kind,
        variant_signature_sha256=variant.signature.signature_sha256,
        matches_baseline=not differing,
        differing_fields=differing,
    )


def _generic_query_si_unit(result: MechanicsSolveResult) -> str:
    query_symbols = tuple(
        item
        for item in result.plan.graph.symbols
        if item.symbol.symbol_id == result.plan.query_symbol_id
    )
    if len(query_symbols) != 1:
        raise ValueError("generic result query symbol must resolve exactly once")
    return render_canonical_si_unit(query_symbols[0].symbol.dimension)


def _selected_scalar_matches(
    result: MechanicsSolveResult,
    observation: LegacyObservation,
) -> bool:
    if result.terminal is not MechanicsSolveTerminal.solved:
        return observation.selected_scalar_si is None
    selected = tuple(
        item
        for item in result.candidate_set.candidates
        if item.candidate_id == result.selected_candidate_id
    )
    if len(selected) != 1 or observation.selected_scalar_si is None:
        return False
    value = selected[0].query_value_si
    return not isinstance(value, tuple) and _fixed_close(value, observation.selected_scalar_si)


def _generic_candidate_scalars(
    result: MechanicsSolveResult,
) -> tuple[tuple[float, ...] | None, DiscrepancyCode | None]:
    expanded: list[float] = []
    for candidate in result.candidate_set.candidates:
        value = candidate.query_value_si
        if isinstance(value, tuple):
            return None, DiscrepancyCode.generic_query_not_scalar
        if len(expanded) + candidate.root_multiplicity > 1024:
            return None, DiscrepancyCode.candidate_multiplicity_bound_exceeded
        expanded.extend((value,) * candidate.root_multiplicity)
    return tuple(expanded), None


def _scalar_multisets_match(
    generic_values: tuple[float, ...],
    observed_values: tuple[float, ...],
) -> bool:
    if len(generic_values) != len(observed_values):
        return False
    generic_sorted = tuple(sorted(generic_values))
    observed_sorted = tuple(sorted(observed_values))
    return all(
        _fixed_close(generic, observed)
        for generic, observed in zip(generic_sorted, observed_sorted)
    )


def _fixed_close(left: float, right: float) -> bool:
    difference = abs(left - right)
    scale = max(abs(left), abs(right))
    return difference <= max(PARITY_ABSOLUTE_TOLERANCE, PARITY_RELATIVE_TOLERANCE * scale)


def _canonical_hash(model: BaseModel) -> str:
    canonical = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validated_exact_result(result: MechanicsSolveResult) -> MechanicsSolveResult:
    if type(result) is not MechanicsSolveResult:
        raise TypeError("migration factories require an exact MechanicsSolveResult")
    return MechanicsSolveResult.model_validate(result.model_dump(mode="python"))


def _validated_exact_observation(observation: LegacyObservation) -> LegacyObservation:
    if type(observation) is not LegacyObservation:
        raise TypeError("migration factories require an exact LegacyObservation")
    return LegacyObservation.model_validate(observation.model_dump(mode="python"))


_ACCEPTED_MIGRATION_CHECKPOINTS: dict[LegacySolverId, str] = {
    LegacySolverId.single_particle_newton: (
        "8b7c5c4a6f1f972d479323f5a7179b4f177d3800"
    ),
    LegacySolverId.incline_no_friction: (
        "5e49f2f267c4c8d75aec6e99e3714fc36f700257"
    ),
    LegacySolverId.incline_with_friction: (
        "c134664cd863d33b50c7e5ae794af2ad61ed6524"
    ),
    LegacySolverId.pulley_atwood: (
        "dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9"
    ),
    LegacySolverId.pulley_table_hanging: (
        "7fff1b83f42ed5f1ddf6046f456b2c9f924cb54e"
    ),
    LegacySolverId.pulley_incline_hanging: (
        "8f18c710fc6d5d730fcceccfb30e3175c2613902"
    ),
    LegacySolverId.massive_pulley_atwood: (
        "8f18c710fc6d5d730fcceccfb30e3175c2613902"
    ),
    LegacySolverId.pure_rolling_energy: (
        "305c68d6e7173740d478fd41c11b4ae78a245469"
    ),
    LegacySolverId.rolling_energy_general: (
        "305c68d6e7173740d478fd41c11b4ae78a245469"
    ),
    LegacySolverId.vertical_circle: (
        "305c68d6e7173740d478fd41c11b4ae78a245469"
    ),
    LegacySolverId.collision_1d: (
        "67f46e9c84a658d1d5a50b9dfcdce81f78f20d8d"
    ),
    LegacySolverId.constant_acceleration_1d: (
        "67f46e9c84a658d1d5a50b9dfcdce81f78f20d8d"
    ),
    LegacySolverId.projectile_motion: (
        "67f46e9c84a658d1d5a50b9dfcdce81f78f20d8d"
    ),
    LegacySolverId.constant_force_work: (
        "34208235fabed97cc7a500668c13f5a4cf5a109d"
    ),
    LegacySolverId.fixed_axis_rotation: (
        "34208235fabed97cc7a500668c13f5a4cf5a109d"
    ),
    LegacySolverId.horizontal_friction_force: (
        "34208235fabed97cc7a500668c13f5a4cf5a109d"
    ),
    LegacySolverId.impulse_momentum: (
        "34208235fabed97cc7a500668c13f5a4cf5a109d"
    ),
    LegacySolverId.work_energy_speed: (
        "34208235fabed97cc7a500668c13f5a4cf5a109d"
    ),
    LegacySolverId.spring_energy_speed: (
        "114b11d26ee1aa1e4107aa8eea9c66de9ea009af"
    ),
    LegacySolverId.flat_curve_friction: (
        "114b11d26ee1aa1e4107aa8eea9c66de9ea009af"
    ),
    LegacySolverId.banked_curve_no_friction: (
        "114b11d26ee1aa1e4107aa8eea9c66de9ea009af"
    ),
}


def _current_migration_record(
    registry_index: int,
    solver_id: LegacySolverId,
) -> LegacySolverMigrationRecord:
    checkpoint = _ACCEPTED_MIGRATION_CHECKPOINTS.get(solver_id)
    if solver_id in DEFERRED_LEGACY_SOLVER_IDS:
        scope_state = (
            LegacySolverScopeState.DEFERRED_OUT_OF_CURRENT_COURSE_SCOPE
        )
        migration_state = LegacySolverMigrationState.DEFERRED
        same_fixture_state = LegacySolverSameFixtureState.NOT_PLANNED_IN_PHASE56
        product_generic_authority = LegacySolverProductGenericAuthority.NONE
        runtime_behavior = (
            LegacySolverRuntimeBehavior.PRECISE_VERIFIED_UNSUPPORTED
        )
    elif checkpoint is not None:
        scope_state = LegacySolverScopeState.IN_CURRENT_COURSE_SCOPE
        migration_state = LegacySolverMigrationState.ACCEPTED
        same_fixture_state = LegacySolverSameFixtureState.ACCEPTED
        product_generic_authority = (
            LegacySolverProductGenericAuthority.VERIFIED_GENERIC_ONLY
        )
        runtime_behavior = LegacySolverRuntimeBehavior.VERIFIED_GENERIC_ONLY
    else:
        scope_state = LegacySolverScopeState.IN_CURRENT_COURSE_SCOPE
        migration_state = LegacySolverMigrationState.PENDING
        same_fixture_state = LegacySolverSameFixtureState.PENDING
        product_generic_authority = LegacySolverProductGenericAuthority.NONE
        runtime_behavior = LegacySolverRuntimeBehavior.NOT_YET_AUTHORIZED
    return LegacySolverMigrationRecord(
        solver_id=solver_id,
        registry_index=registry_index,
        inventory_state=LegacySolverInventoryState.PRESENT,
        scope_state=scope_state,
        migration_state=migration_state,
        same_fixture_state=same_fixture_state,
        product_generic_authority=product_generic_authority,
        runtime_behavior=runtime_behavior,
        legacy_authority=LegacySolverLegacyAuthority.OFF_MODE_ROLLBACK_ONLY,
        silent_fallback=LegacySolverSilentFallback.FORBIDDEN,
        future_extension=LegacySolverFutureExtension.PRESERVED,
        accepted_checkpoint_hash=checkpoint,
    )


CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS: tuple[
    LegacySolverMigrationRecord, ...
] = tuple(
    _current_migration_record(index, solver_id)
    for index, solver_id in enumerate(LEGACY_SOLVER_INVENTORY, start=1)
)
CURRENT_LEGACY_MIGRATION_PROGRESS = build_legacy_migration_progress(
    CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS
)


__all__ = [
    "CURRENT_LEGACY_MIGRATION_PROGRESS",
    "CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS",
    "assert_legacy_migration_coverage_complete",
    "build_generic_result_invariance_signature",
    "build_legacy_migration_progress",
    "build_legacy_differential_report",
    "compare_generic_result_invariance",
]
