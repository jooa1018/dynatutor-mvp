"""Public diagnostics-only API for offline or shadow mechanics migration.

The package observes already completed executions.  It never runs another
kernel and never selects, repairs, verifies, or replaces a generic answer.
"""

from engine.mechanics.migration.contracts import *
from engine.mechanics.migration.contracts import __all__ as _contract_exports
from engine.mechanics.migration.parity import (
    CURRENT_LEGACY_MIGRATION_PROGRESS,
    CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS,
    assert_legacy_migration_coverage_complete,
    build_generic_result_invariance_signature,
    build_legacy_differential_report,
    build_legacy_migration_progress,
    compare_generic_result_invariance,
)
from engine.mechanics.migration.harness import (
    LabelledIRProbeVariant,
    MechanicsMigrationInvarianceComparison,
    MechanicsMigrationProbeExecution,
    MigrationProbeFailure,
    MigrationProbeStage,
    MigrationProbeTerminal,
    MigrationProbeVariantComparison,
    compare_mechanics_ir_invariance,
    execute_mechanics_ir_probe,
)


__all__ = [
    *_contract_exports,
    "CURRENT_LEGACY_MIGRATION_PROGRESS",
    "CURRENT_LEGACY_SOLVER_MIGRATION_RECORDS",
    "assert_legacy_migration_coverage_complete",
    "build_generic_result_invariance_signature",
    "build_legacy_differential_report",
    "build_legacy_migration_progress",
    "compare_generic_result_invariance",
    "LabelledIRProbeVariant",
    "MechanicsMigrationInvarianceComparison",
    "MechanicsMigrationProbeExecution",
    "MigrationProbeFailure",
    "MigrationProbeStage",
    "MigrationProbeTerminal",
    "MigrationProbeVariantComparison",
    "compare_mechanics_ir_invariance",
    "execute_mechanics_ir_probe",
]
