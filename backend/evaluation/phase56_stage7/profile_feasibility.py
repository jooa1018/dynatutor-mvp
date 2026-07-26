"""Profile-isolated feasibility: each (profile, context) measured on its own.

The previous revision of this instrument ran ``close_projected_draft`` once
per context, credited the declaration-order first-wins winner, and stamped
every other applicable profile ``profile_transaction_not_formable``.  Under
that scheme an unbuilt profile's "verified yield 0" was a definition, not a
measurement, and a second formable profile in the same context could never
be observed at all.

This revision measures.  For every applicable (profile, context) pair the
selected profile is planned and applied **independently against the pristine
projected Draft** — ``run_lane_b_case_with_selected_profile`` runs the
identical gate/authority/derivation/validation/normalization/authorization/
compilation/solve/verification chain the lane runner executes, with only the
closure step pinned to the one selected profile.  First-wins never enters;
declaration order never enters (planning resolves the profile by identity);
and a profile with no built transaction is recorded ``profile_not_implemented``
— *not measured* — never as a zero yield it never earned.

``compiler_unsupported_reachable`` is granted only on an exact typed
compiler issue code from the closed precise-unsupported whitelist; anything
else lands in the explicit ``harness_unclassified`` residual rather than
being silently promoted to "precise".

No case ID, family, split, text, expected terminal, expected answer, or gold
content enters the matrix; rows carry profile IDs from the closed enum,
bounded status names, and counts.  Nothing here is wired to the product path.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Sequence

from engine.mechanics.compiler.contracts import CompilerIssueCode

from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    ApplicationOutcome,
    ProfileApplication,
    profile_has_transaction,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBResult,
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case_with_selected_profile,
)

PROFILE_FEASIBILITY_VERSION = "phase56-stage7-profile-feasibility-v2-isolated"

# The exact typed compiler issue codes that prove a *precise* unsupported —
# a refusal the engine states with its own vocabulary, not a substring of a
# status word.  Nothing outside this closed set may be reported as
# `compiler_unsupported_reachable`.
PRECISE_UNSUPPORTED_ISSUE_CODES: frozenset[CompilerIssueCode] = frozenset(
    {
        CompilerIssueCode.requires_specialized_model,
        CompilerIssueCode.consistency_inconclusive,
    }
)


class ProfileFeasibilityStatus(str, Enum):
    """What one independent (profile, context) run measured, closed."""

    profile_not_implemented = "profile_not_implemented"
    profile_plan_not_formable = "profile_plan_not_formable"
    profile_transaction_rejected = "profile_transaction_rejected"
    validation_blocked = "validation_blocked"
    normalization_blocked = "normalization_blocked"
    authorization_blocked = "authorization_blocked"
    compiler_no_equation = "compiler_no_equation"
    compiler_underdetermined = "compiler_underdetermined"
    compiler_unsupported_reachable = "compiler_unsupported_reachable"
    solver_rejected = "solver_rejected"
    verification_rejected = "verification_rejected"
    verified_solve_reachable = "verified_solve_reachable"
    verified_deferred_reachable = "verified_deferred_reachable"
    # The explicit residual: an outcome the taxonomy cannot honestly name —
    # a stage exception, an unexpected compiler status, an imprecise
    # unsupported.  Never silently merged into a neighbouring class.
    harness_unclassified = "harness_unclassified"


# Statuses that are bookkeeping, not measurement: the pipeline never ran for
# them, so no yield claim of any kind may be derived from their counts.
NOT_MEASURED_STATUSES: frozenset[ProfileFeasibilityStatus] = frozenset(
    {ProfileFeasibilityStatus.profile_not_implemented}
)

_BLOCKED_VALIDATION_TERMINALS: frozenset[LaneBTerminal] = frozenset(
    {
        LaneBTerminal.needs_figure,
        LaneBTerminal.needs_confirmation,
        LaneBTerminal.insufficient_information,
        LaneBTerminal.validation_rejected,
    }
)


def _classify_measured_result(result: LaneBResult) -> ProfileFeasibilityStatus:
    """Map one applied-profile lane result onto the closed status set."""

    terminal = result.terminal
    if terminal in _BLOCKED_VALIDATION_TERMINALS:
        return ProfileFeasibilityStatus.validation_blocked
    if terminal is LaneBTerminal.normalization_rejected:
        return ProfileFeasibilityStatus.normalization_blocked
    if terminal is LaneBTerminal.authorization_failed:
        return ProfileFeasibilityStatus.authorization_blocked
    if terminal is LaneBTerminal.verified_unsupported:
        return ProfileFeasibilityStatus.verified_deferred_reachable
    if terminal is LaneBTerminal.compiler_unsupported:
        # Precise means the exact typed code, never a substring.
        if any(
            code == precise.value
            for code in result.compiler_codes
            for precise in PRECISE_UNSUPPORTED_ISSUE_CODES
        ):
            return ProfileFeasibilityStatus.compiler_unsupported_reachable
        return ProfileFeasibilityStatus.harness_unclassified
    if terminal is LaneBTerminal.compiler_failure:
        if result.stage_exception is not None:
            # A crash is not "no law wrote about the unknown".
            return ProfileFeasibilityStatus.harness_unclassified
        if result.compiler_status == "underdetermined":
            if result.equation_count == 0:
                return ProfileFeasibilityStatus.compiler_no_equation
            return ProfileFeasibilityStatus.compiler_underdetermined
        return ProfileFeasibilityStatus.harness_unclassified
    if terminal is LaneBTerminal.solve_rejected:
        return ProfileFeasibilityStatus.solver_rejected
    if terminal is LaneBTerminal.verification_rejected:
        return ProfileFeasibilityStatus.verification_rejected
    if terminal is LaneBTerminal.solved:
        return ProfileFeasibilityStatus.verified_solve_reachable
    return ProfileFeasibilityStatus.harness_unclassified


def classify_selected_profile_outcome(
    profile_id: ProfileId,
    application: ProfileApplication | None,
    result: LaneBResult | None,
) -> ProfileFeasibilityStatus:
    """Classify one independent selected-profile run, fail-closed.

    ``profile_not_implemented`` is decided from the transaction registry
    alone and short-circuits — no run happened, so nothing pipeline-shaped
    may be claimed.  An application that did not apply is the profile's own
    plan/transaction verdict; only an applied transaction's lane result is
    read further.
    """

    if not profile_has_transaction(profile_id):
        return ProfileFeasibilityStatus.profile_not_implemented
    if application is None or result is None:
        return ProfileFeasibilityStatus.harness_unclassified
    if application.outcome is ApplicationOutcome.not_applied:
        return ProfileFeasibilityStatus.profile_plan_not_formable
    if application.outcome is ApplicationOutcome.rejected:
        return ProfileFeasibilityStatus.profile_transaction_rejected
    return _classify_measured_result(result)


@dataclass(frozen=True, slots=True)
class ProfileFeasibilityRow:
    """One profile's isolated measurement across every applicable context."""

    profile_id: ProfileId
    implemented: bool
    applicable_contexts: int
    measured_contexts: int
    not_measured_contexts: int
    status_counts: dict[str, int]

    def __post_init__(self) -> None:
        if not self.implemented:
            expected = (
                {
                    ProfileFeasibilityStatus.profile_not_implemented.value: (
                        self.applicable_contexts
                    )
                }
                if self.applicable_contexts
                else {}
            )
            if self.status_counts != expected or self.measured_contexts != 0:
                raise ValueError(
                    "an unimplemented profile carries no measured cell at all"
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id.value,
            "implemented": self.implemented,
            "applicable_contexts": self.applicable_contexts,
            "measured_contexts": self.measured_contexts,
            "not_measured_contexts": self.not_measured_contexts,
            "status_counts": dict(sorted(self.status_counts.items())),
        }


@dataclass(frozen=True, slots=True)
class ProfileFeasibilityMatrix:
    version: str
    context_count: int
    rows: tuple[ProfileFeasibilityRow, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "context_count": self.context_count,
            "profiles": [row.as_dict() for row in self.rows],
        }


def measure_profile_feasibility(
    cases: Iterable[Any],
    *,
    profile_order: Sequence[ProfileId] = tuple(ProfileId),
) -> ProfileFeasibilityMatrix:
    """Measure every applicable (profile, context) pair independently.

    ``profile_order`` exists so the order-invariance controls can permute it;
    the measurement itself must be — and is asserted by test to be —
    independent of it, because every selected run starts from the pristine
    projected Draft and resolves its profile by identity.
    """

    if set(profile_order) != set(ProfileId) or len(profile_order) != len(
        tuple(ProfileId)
    ):
        raise ValueError("profile_order must be a permutation of the closed enum")

    applicable: Counter[ProfileId] = Counter()
    measured: Counter[ProfileId] = Counter()
    not_measured: Counter[ProfileId] = Counter()
    status_counts: dict[ProfileId, Counter[str]] = {
        profile_id: Counter() for profile_id in ProfileId
    }
    context_count = 0

    for index, case in enumerate(cases):
        projection = project_case_to_draft(case)
        if not projection.projected:
            continue
        context_count += 1
        for profile_id in profile_order:
            plan = plan_complete_profile(
                profile_id,
                projection.draft,
                approved_assumption_ids=projection.approvable_assumption_ids,
            )
            if plan.disposition is PlanDisposition.not_applicable:
                continue
            applicable[profile_id] += 1
            if not profile_has_transaction(profile_id):
                not_measured[profile_id] += 1
                status_counts[profile_id][
                    ProfileFeasibilityStatus.profile_not_implemented.value
                ] += 1
                continue
            application, result = run_lane_b_case_with_selected_profile(
                projection,
                profile_id,
                execution_token=deterministic_token(
                    index, run_nonce=profile_id.value
                ),
            )
            status = classify_selected_profile_outcome(
                profile_id, application, result
            )
            measured[profile_id] += 1
            status_counts[profile_id][status.value] += 1

    rows = tuple(
        ProfileFeasibilityRow(
            profile_id=profile_id,
            implemented=profile_has_transaction(profile_id),
            applicable_contexts=applicable[profile_id],
            measured_contexts=measured[profile_id],
            not_measured_contexts=not_measured[profile_id],
            status_counts=dict(status_counts[profile_id]),
        )
        for profile_id in sorted(ProfileId, key=lambda item: item.value)
        if applicable[profile_id]
    )
    return ProfileFeasibilityMatrix(
        version=PROFILE_FEASIBILITY_VERSION,
        context_count=context_count,
        rows=rows,
    )


__all__ = [
    "NOT_MEASURED_STATUSES",
    "PRECISE_UNSUPPORTED_ISSUE_CODES",
    "PROFILE_FEASIBILITY_VERSION",
    "ProfileFeasibilityMatrix",
    "ProfileFeasibilityRow",
    "ProfileFeasibilityStatus",
    "classify_selected_profile_outcome",
    "measure_profile_feasibility",
]
