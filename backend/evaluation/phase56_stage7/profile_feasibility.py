"""Full-pipeline profile feasibility: what each candidate is actually worth.

The complete-profile census counts how close each profile's *plan* is to
closing; those numbers are structure counts, not verified-solve yield, and
choosing the next package by them would be choosing by prediction.  This
instrument classifies every applicable (profile, context) pair by what the
**real pipeline** does today — the same projection, authority, transactional
closure, event-boundary derivation, validation, normalization, authorization,
compilation, solve, and verification the runner executes, with nothing
simulated.

Two verdicts are recorded per profile, both counts-only:

* the **feasibility class** of each applicable context under the closed
  eleven-way vocabulary below — a context counts toward a profile's deep
  classes only when that profile's own transaction actually applied, so an
  unbuilt profile's population honestly reads
  ``profile_transaction_not_formable`` instead of borrowing the pipeline's
  progress; and
* the population's **as-is terminal** distribution — how far those contexts
  already get regardless of profile — which is the texture that separates a
  population parked one wall from the end from one that dies at projection.

No case ID, family, split, text, expected terminal, expected answer, or gold
content enters the matrix; rows carry profile IDs from the closed enum,
bounded class names, and counts.  Nothing here is wired to the product path.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_every_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    close_projected_draft,
)
from evaluation.phase56_stage7.lane_b_authority import (
    build_lane_b_authority_bundle,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBResult,
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
)

PROFILE_FEASIBILITY_VERSION = "phase56-stage7-profile-feasibility-v1"


class FeasibilityClass(str, Enum):
    """Where one applicable (profile, context) pair stops, full pipeline."""

    profile_transaction_not_formable = "profile_transaction_not_formable"
    validation_blocked = "validation_blocked"
    normalization_blocked = "normalization_blocked"
    authorization_blocked = "authorization_blocked"
    compiler_no_equation = "compiler_no_equation"
    compiler_underdetermined = "compiler_underdetermined"
    solver_rejected = "solver_rejected"
    verification_rejected = "verification_rejected"
    verified_solve_reachable = "verified_solve_reachable"
    verified_deferred_reachable = "verified_deferred_reachable"
    precise_unsupported_reachable = "precise_unsupported_reachable"


# Neutral engine gates — a figure dependency, a reader confirmation, missing
# information — stop the pipeline at the validation stage, so they classify
# as `validation_blocked`; the as-is terminal table keeps the exact terminal.
_TERMINAL_CLASSES: dict[LaneBTerminal, FeasibilityClass] = {
    LaneBTerminal.needs_figure: FeasibilityClass.validation_blocked,
    LaneBTerminal.needs_confirmation: FeasibilityClass.validation_blocked,
    LaneBTerminal.insufficient_information: FeasibilityClass.validation_blocked,
    LaneBTerminal.validation_rejected: FeasibilityClass.validation_blocked,
    LaneBTerminal.normalization_rejected: FeasibilityClass.normalization_blocked,
    LaneBTerminal.authorization_failed: FeasibilityClass.authorization_blocked,
    LaneBTerminal.compiler_unsupported: (
        FeasibilityClass.precise_unsupported_reachable
    ),
    LaneBTerminal.verified_unsupported: (
        FeasibilityClass.verified_deferred_reachable
    ),
    LaneBTerminal.solve_rejected: FeasibilityClass.solver_rejected,
    LaneBTerminal.verification_rejected: FeasibilityClass.verification_rejected,
    LaneBTerminal.solved: FeasibilityClass.verified_solve_reachable,
}


def classify_lane_result(result: LaneBResult) -> FeasibilityClass:
    """The closed class one real pipeline run lands in.

    ``compiler_failure`` splits on the blocked graph's own equation count:
    zero equations in the query's component means no law wrote about the
    queried unknown at all, which is a different wall from an equation set
    that exists and does not close.
    """

    mapped = _TERMINAL_CLASSES.get(result.terminal)
    if mapped is not None:
        return mapped
    if result.terminal is LaneBTerminal.compiler_failure:
        if result.equation_count == 0:
            return FeasibilityClass.compiler_no_equation
        return FeasibilityClass.compiler_underdetermined
    # A projection-stage terminal reaching this classifier is a harness error;
    # fail closed to the shallowest class rather than inventing progress.
    return FeasibilityClass.profile_transaction_not_formable


@dataclass(frozen=True, slots=True)
class ProfileFeasibilityRow:
    """One profile's measured full-pipeline feasibility, counts only."""

    profile_id: str
    applicable_contexts: int
    class_counts: tuple[tuple[str, int], ...]
    as_is_terminal_counts: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "applicable_contexts": self.applicable_contexts,
            "class_counts": dict(self.class_counts),
            "as_is_terminal_counts": dict(self.as_is_terminal_counts),
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


def measure_profile_feasibility(cases: Iterable[Any]) -> ProfileFeasibilityMatrix:
    """Classify every applicable (profile, context) pair through the real lane.

    One pipeline run per context; the run's class is credited to the profile
    whose transaction actually applied, and every other applicable profile
    for that context counts ``profile_transaction_not_formable``.  Planning
    and closure are the runner's own stages re-executed deterministically, so
    the credit assignment can never disagree with what the lane really did.
    """

    class_counts: dict[str, Counter[str]] = {}
    terminal_counts: dict[str, Counter[str]] = {}
    applicable: Counter[str] = Counter()
    context_count = 0

    for index, case in enumerate(cases):
        projection = project_case_to_draft(case)
        if not projection.projected:
            continue
        context_count += 1
        plans = plan_every_profile(
            projection.draft,
            approved_assumption_ids=projection.approvable_assumption_ids,
        )
        applied_profile: ProfileId | None = None
        try:
            bundle = build_lane_b_authority_bundle(projection)
            application = close_projected_draft(
                projection.draft,
                approved_assumption_ids=bundle.approved_assumption_ids,
                authorized_assumptions=bundle.authorization_map(),
            )
            if application.applied:
                applied_profile = application.profile_id
        except Exception:
            applied_profile = None
        result = run_lane_b_case(
            projection, execution_token=deterministic_token(index)
        )
        run_class = classify_lane_result(result)
        for plan in plans:
            if plan.disposition is PlanDisposition.not_applicable:
                continue
            profile_key = plan.profile_id.value
            applicable[profile_key] += 1
            terminal_counts.setdefault(profile_key, Counter())[
                result.terminal.value
            ] += 1
            landed = (
                run_class
                if applied_profile is plan.profile_id
                else FeasibilityClass.profile_transaction_not_formable
            )
            class_counts.setdefault(profile_key, Counter())[landed.value] += 1

    rows = tuple(
        ProfileFeasibilityRow(
            profile_id=profile_key,
            applicable_contexts=applicable[profile_key],
            class_counts=tuple(sorted(class_counts[profile_key].items())),
            as_is_terminal_counts=tuple(
                sorted(terminal_counts[profile_key].items())
            ),
        )
        for profile_key in sorted(applicable)
    )
    return ProfileFeasibilityMatrix(
        version=PROFILE_FEASIBILITY_VERSION,
        context_count=context_count,
        rows=rows,
    )


__all__ = [
    "PROFILE_FEASIBILITY_VERSION",
    "FeasibilityClass",
    "ProfileFeasibilityMatrix",
    "ProfileFeasibilityRow",
    "classify_lane_result",
    "measure_profile_feasibility",
]
