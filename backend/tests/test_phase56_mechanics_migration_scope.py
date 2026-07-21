from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from engine.mechanics.migration import (
    CURRENT_LEGACY_MIGRATION_PROGRESS,
    CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS,
    DEFERRED_LEGACY_SOLVER_IDS,
    IN_SCOPE_LEGACY_SOLVER_IDS,
    LEGACY_SOLVER_DEFERRED_COUNT,
    LEGACY_SOLVER_IN_SCOPE_COUNT,
    LEGACY_SOLVER_INVENTORY,
    LEGACY_SOLVER_INVENTORY_COUNT,
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
    assert_legacy_migration_coverage_complete,
    build_legacy_migration_progress,
)
from engine.solvers.registry import SolverRegistry


EXPECTED_INVENTORY = (
    "single_particle_newton",
    "incline_no_friction",
    "incline_with_friction",
    "pulley_atwood",
    "pulley_table_hanging",
    "pulley_incline_hanging",
    "massive_pulley_atwood",
    "pure_rolling_energy",
    "rolling_energy_general",
    "vertical_circle",
    "collision_1d",
    "constant_acceleration_1d",
    "projectile_motion",
    "constant_force_work",
    "fixed_axis_rotation",
    "horizontal_friction_force",
    "impulse_momentum",
    "work_energy_speed",
    "spring_mass_vibration",
    "spring_energy_speed",
    "flat_curve_friction",
    "banked_curve_no_friction",
    "relative_acceleration_translation",
    "coriolis_relative_motion",
    "plane_rigid_body_acceleration",
    "polar_kinematics",
    "instant_center_velocity",
    "slot_pin_relative_motion",
    "plane_rigid_body_velocity",
)
EXPECTED_DEFERRED = {
    "spring_mass_vibration": 19,
    "relative_acceleration_translation": 23,
    "coriolis_relative_motion": 24,
    "slot_pin_relative_motion": 28,
}
EXPECTED_ACCEPTED = {
    "single_particle_newton",
    "incline_no_friction",
    "incline_with_friction",
    "pulley_atwood",
    "pulley_table_hanging",
}


def _dump_record(record: LegacySolverMigrationRecord) -> dict[str, object]:
    return deepcopy(record.model_dump(mode="python"))


def _replace_record(
    record: LegacySolverMigrationRecord,
    **changes: object,
) -> LegacySolverMigrationRecord:
    payload = _dump_record(record)
    payload.update(changes)
    return LegacySolverMigrationRecord.model_validate(payload)


def _complete_records() -> tuple[LegacySolverMigrationRecord, ...]:
    completed: list[LegacySolverMigrationRecord] = []
    for record in CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS:
        if record.scope_state is LegacySolverScopeState.IN_CURRENT_COURSE_SCOPE:
            record = _replace_record(
                record,
                migration_state=LegacySolverMigrationState.ACCEPTED,
                same_fixture_state=LegacySolverSameFixtureState.ACCEPTED,
                product_generic_authority=(
                    LegacySolverProductGenericAuthority.VERIFIED_GENERIC_ONLY
                ),
                runtime_behavior=LegacySolverRuntimeBehavior.VERIFIED_GENERIC_ONLY,
                accepted_checkpoint_hash=(
                    record.accepted_checkpoint_hash or "f" * 40
                ),
            )
        completed.append(record)
    return tuple(completed)


def test_registry_inventory_is_exact_ordered_29_with_exact_25_4_split() -> None:
    assert LEGACY_SOLVER_INVENTORY_COUNT == len(EXPECTED_INVENTORY) == 29
    assert LEGACY_SOLVER_IN_SCOPE_COUNT == 25
    assert LEGACY_SOLVER_DEFERRED_COUNT == 4
    assert tuple(item.value for item in LegacySolverId) == EXPECTED_INVENTORY
    assert tuple(item.value for item in LEGACY_SOLVER_INVENTORY) == EXPECTED_INVENTORY
    assert tuple(item.value for item in IN_SCOPE_LEGACY_SOLVER_IDS) == tuple(
        solver_id
        for solver_id in EXPECTED_INVENTORY
        if solver_id not in EXPECTED_DEFERRED
    )
    assert {
        item.value for item in DEFERRED_LEGACY_SOLVER_IDS
    } == set(EXPECTED_DEFERRED)
    assert LegacySolverId.polar_kinematics in IN_SCOPE_LEGACY_SOLVER_IDS


def test_typed_inventory_is_bound_to_the_live_legacy_registry_order() -> None:
    assert tuple(solver.name for solver in SolverRegistry().solvers) == EXPECTED_INVENTORY


def test_current_progress_is_29_classified_5_accepted_20_pending_4_deferred() -> None:
    progress = CURRENT_LEGACY_MIGRATION_PROGRESS
    assert progress.records == CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS
    assert tuple(item.registry_index for item in progress.records) == tuple(range(1, 30))
    assert progress.inventory_count == 29
    assert progress.in_scope_count == 25
    assert progress.deferred_count == 4
    assert progress.accepted_in_scope_count == 5
    assert progress.pending_in_scope_count == 20
    assert progress.in_scope_complete is False
    assert {
        item.solver_id.value
        for item in progress.records
        if item.migration_state is LegacySolverMigrationState.ACCEPTED
    } == EXPECTED_ACCEPTED


def test_each_deferred_row_has_the_complete_typed_policy_profile() -> None:
    deferred = {
        item.solver_id.value: item
        for item in CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS
        if item.scope_state
        is LegacySolverScopeState.DEFERRED_OUT_OF_CURRENT_COURSE_SCOPE
    }
    assert set(deferred) == set(EXPECTED_DEFERRED)
    for solver_id, registry_index in EXPECTED_DEFERRED.items():
        record = deferred[solver_id]
        assert record.registry_index == registry_index
        assert record.inventory_state is LegacySolverInventoryState.PRESENT
        assert record.migration_state is LegacySolverMigrationState.DEFERRED
        assert (
            record.same_fixture_state
            is LegacySolverSameFixtureState.NOT_PLANNED_IN_PHASE56
        )
        assert (
            record.product_generic_authority
            is LegacySolverProductGenericAuthority.NONE
        )
        assert (
            record.runtime_behavior
            is LegacySolverRuntimeBehavior.PRECISE_VERIFIED_UNSUPPORTED
        )
        assert (
            record.legacy_authority
            is LegacySolverLegacyAuthority.OFF_MODE_ROLLBACK_ONLY
        )
        assert record.silent_fallback is LegacySolverSilentFallback.FORBIDDEN
        assert record.future_extension is LegacySolverFutureExtension.PRESERVED
        assert record.accepted_checkpoint_hash is None


def test_scope_contracts_are_frozen_extra_forbid_and_scalar_strict() -> None:
    record = CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS[0]
    progress = CURRENT_LEGACY_MIGRATION_PROGRESS
    with pytest.raises(ValidationError, match="frozen"):
        record.registry_index = 2
    with pytest.raises(ValidationError, match="frozen"):
        progress.in_scope_complete = True

    extra_record = _dump_record(record)
    extra_record["case_id"] = "caseLevelEvidenceMustNotEnterInventory"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LegacySolverMigrationRecord.model_validate(extra_record)

    bool_index = _dump_record(record)
    bool_index["registry_index"] = True
    with pytest.raises(ValidationError):
        LegacySolverMigrationRecord.model_validate(bool_index)

    malformed_checkpoint = _dump_record(record)
    malformed_checkpoint["accepted_checkpoint_hash"] = "A" * 40
    with pytest.raises(ValidationError):
        LegacySolverMigrationRecord.model_validate(malformed_checkpoint)


@pytest.mark.parametrize(
    "mutation",
    (
        "reordered",
        "duplicate",
        "mis_scoped",
        "forged_accepted_count",
        "forged_pending_count",
        "false_complete",
    ),
)
def test_progress_rejects_reordering_duplicates_scope_drift_and_forged_totals(
    mutation: str,
) -> None:
    records = list(CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS)
    progress_payload = CURRENT_LEGACY_MIGRATION_PROGRESS.model_dump(mode="python")
    if mutation == "reordered":
        records[0], records[1] = records[1], records[0]
        progress_payload["records"] = tuple(records)
    elif mutation == "duplicate":
        records[1] = records[0]
        progress_payload["records"] = tuple(records)
    elif mutation == "mis_scoped":
        record_payload = _dump_record(records[0])
        record_payload["scope_state"] = (
            LegacySolverScopeState.DEFERRED_OUT_OF_CURRENT_COURSE_SCOPE
        )
        with pytest.raises(ValidationError, match="fixed scope policy"):
            LegacySolverMigrationRecord.model_validate(record_payload)
        return
    elif mutation == "forged_accepted_count":
        progress_payload["accepted_in_scope_count"] = 6
    elif mutation == "forged_pending_count":
        progress_payload["pending_in_scope_count"] = 19
    elif mutation == "false_complete":
        progress_payload["in_scope_complete"] = True
    with pytest.raises(ValidationError):
        LegacyMigrationProgress.model_validate(progress_payload)


@pytest.mark.parametrize("delta", (-1, 1))
def test_progress_rejects_missing_and_extra_inventory_rows(delta: int) -> None:
    payload = CURRENT_LEGACY_MIGRATION_PROGRESS.model_dump(mode="python")
    records = list(payload["records"])
    if delta < 0:
        records.pop()
    else:
        records.append(records[-1])
    payload["records"] = tuple(records)
    with pytest.raises(ValidationError):
        LegacyMigrationProgress.model_validate(payload)


def test_deferred_row_cannot_be_accepted_or_contribute_to_progress() -> None:
    deferred = next(
        item
        for item in CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS
        if item.solver_id is LegacySolverId.spring_mass_vibration
    )
    forged = _dump_record(deferred)
    forged.update(
        migration_state=LegacySolverMigrationState.ACCEPTED,
        same_fixture_state=LegacySolverSameFixtureState.ACCEPTED,
        product_generic_authority=(
            LegacySolverProductGenericAuthority.VERIFIED_GENERIC_ONLY
        ),
        runtime_behavior=LegacySolverRuntimeBehavior.VERIFIED_GENERIC_ONLY,
        accepted_checkpoint_hash="e" * 40,
    )
    with pytest.raises(ValidationError, match="exact policy profile"):
        LegacySolverMigrationRecord.model_validate(forged)

    with pytest.raises(ValueError, match="deferred records never count"):
        assert_legacy_migration_coverage_complete(CURRENT_LEGACY_MIGRATION_PROGRESS)


def test_coverage_gate_passes_exactly_when_all_25_in_scope_rows_are_accepted() -> None:
    complete = build_legacy_migration_progress(_complete_records())
    assert complete.accepted_in_scope_count == 25
    assert complete.pending_in_scope_count == 0
    assert complete.deferred_count == 4
    assert complete.in_scope_complete is True
    assert assert_legacy_migration_coverage_complete(complete) == complete

    one_pending = list(_complete_records())
    accepted = one_pending[0]
    one_pending[0] = _replace_record(
        accepted,
        migration_state=LegacySolverMigrationState.PENDING,
        same_fixture_state=LegacySolverSameFixtureState.PENDING,
        product_generic_authority=LegacySolverProductGenericAuthority.NONE,
        runtime_behavior=LegacySolverRuntimeBehavior.NOT_YET_AUTHORIZED,
        accepted_checkpoint_hash=None,
    )
    partial = build_legacy_migration_progress(tuple(one_pending))
    assert partial.accepted_in_scope_count == 24
    with pytest.raises(ValueError, match="incomplete"):
        assert_legacy_migration_coverage_complete(partial)


def test_progress_builder_rejects_lists_nonrecords_and_case_level_evidence() -> None:
    with pytest.raises(TypeError, match="exact tuple"):
        build_legacy_migration_progress(list(CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS))
    with pytest.raises(TypeError, match="exact inventory record types"):
        build_legacy_migration_progress((object(),))

    observation = LegacyObservation(
        case_id="caseLevelObservation",
        diagnostic_kernel_id="independentOracle",
        terminal=LegacyTerminal.not_comparable,
    )
    with pytest.raises(TypeError, match="exact inventory record types"):
        build_legacy_migration_progress((observation,))
