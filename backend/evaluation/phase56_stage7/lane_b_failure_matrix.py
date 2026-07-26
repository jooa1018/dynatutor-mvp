"""Lane B privacy-safe failure matrix.

Aggregates projection and validator outcomes over the public corpus without
recording raw problem text, case IDs, families, splits, expected terminals, or
expected answers.  Only closed reason codes, issue codes, index-stripped issue
paths, and structural counts are emitted.

Comparison against an expected terminal is deliberately *not* performed here.
That belongs to the gold domain, after the runtime snapshot is frozen.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from evaluation.phase56_stage7.lane_b_draft_projection import (
    DRAFT_PROJECTION_VERSION,
    DraftProjectionTerminal,
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LANE_B_RUNNER_VERSION,
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
)


FAILURE_MATRIX_VERSION = "phase56-stage7-lane-b-failure-matrix-v1"
PIPELINE_MATRIX_VERSION = "phase56-stage7-lane-b-pipeline-matrix-v1"

# The closed Stage 7 failure taxonomy.  Every executed case lands in exactly one
# bucket, so a failure is classified by the stage that owns it rather than
# collapsed into a single runtime failure.
_TAXONOMY: dict[str, str] = {
    LaneBTerminal.projection_rejected.value: "PROJECTION_FAILURE",
    LaneBTerminal.validation_rejected.value: "VALIDATION_FAILURE",
    LaneBTerminal.normalization_rejected.value: "NORMALIZATION_FAILURE",
    LaneBTerminal.authorization_failed.value: "AUTHORIZATION_FAILURE",
    LaneBTerminal.compiler_failure.value: "COMPILER_FAILURE",
    LaneBTerminal.compiler_unsupported.value: "COMPILER_UNSUPPORTED",
    LaneBTerminal.solve_rejected.value: "SOLVER_FAILURE",
    LaneBTerminal.verification_rejected.value: "VERIFICATION_FAILURE",
    LaneBTerminal.solved.value: "SOLVED",
    LaneBTerminal.verified_unsupported.value: "VERIFIED_UNSUPPORTED",
    LaneBTerminal.needs_figure.value: "BLOCKED_NEEDS_FIGURE",
    LaneBTerminal.needs_confirmation.value: "BLOCKED_NEEDS_CONFIRMATION",
    LaneBTerminal.insufficient_information.value: "BLOCKED_INSUFFICIENT_INFORMATION",
}

_INDEX = re.compile(r"\.\d+")


def _path_family(path: str | None) -> str:
    """Strip collection indices so paths aggregate instead of identifying a case."""

    return _INDEX.sub(".N", path or "")


@dataclass(frozen=True, slots=True)
class LaneBFailureMatrix:
    version: str
    projection_version: str
    total_cases: int
    terminal_counts: tuple[tuple[str, int], ...]
    projection_rejection_counts: tuple[tuple[str, int], ...]
    validator_issue_counts: tuple[tuple[str, int], ...]
    validator_code_path_counts: tuple[tuple[str, str, int], ...]
    structure_counts: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "projection_version": self.projection_version,
            "total_cases": self.total_cases,
            "terminal_counts": dict(self.terminal_counts),
            "projection_rejection_counts": dict(self.projection_rejection_counts),
            "validator_issue_counts": dict(self.validator_issue_counts),
            "validator_code_path_counts": [
                {"code": code, "path": path, "count": count}
                for code, path, count in self.validator_code_path_counts
            ],
            "structure_counts": dict(self.structure_counts),
        }


@dataclass(frozen=True, slots=True)
class LaneBPipelineMatrix:
    """Privacy-safe aggregate of one real public-corpus pipeline execution.

    Carries no case ID, family, split, problem text, expected terminal,
    expected answer, source quote, full equation, or private metadata.  A
    diagnostic path is reduced to its typed-field shape before aggregation, so
    a defect *class* is visible while the record that produced it is not.
    """

    version: str
    projection_version: str
    runner_version: str
    total_cases: int
    executed_cases: int
    terminal_counts: tuple[tuple[str, int], ...]
    taxonomy_counts: tuple[tuple[str, int], ...]
    compiler_status_counts: tuple[tuple[str, int], ...]
    normalization_terminal_counts: tuple[tuple[str, int], ...]
    solve_terminal_counts: tuple[tuple[str, int], ...]
    stage_exception_counts: tuple[tuple[str, int], ...]
    validation_code_path_counts: tuple[tuple[str, str, int], ...]
    compiler_code_path_counts: tuple[tuple[str, str, int], ...]
    solve_code_counts: tuple[tuple[str, int], ...]
    law_id_counts: tuple[tuple[str, int], ...]
    verification_check_counts: tuple[tuple[str, str, int], ...]
    structure_counts: tuple[tuple[str, int], ...]
    # The runtime's own frozen outputs for solved cases, keyed by execution
    # index only — a verified answer is snapshot-permitted content, and the
    # gold domain scores it *after* this record is complete.  The runtime
    # loop that fills it never reads a gold member.
    solved_outputs: tuple[tuple[int, float, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "projection_version": self.projection_version,
            "runner_version": self.runner_version,
            "total_cases": self.total_cases,
            "executed_cases": self.executed_cases,
            "terminal_counts": dict(self.terminal_counts),
            "taxonomy_counts": dict(self.taxonomy_counts),
            "compiler_status_counts": dict(self.compiler_status_counts),
            "normalization_terminal_counts": dict(self.normalization_terminal_counts),
            "solve_terminal_counts": dict(self.solve_terminal_counts),
            "stage_exception_counts": dict(self.stage_exception_counts),
            "validation_code_path_counts": [
                {"code": code, "path": path, "count": count}
                for code, path, count in self.validation_code_path_counts
            ],
            "compiler_code_path_counts": [
                {"code": code, "path": path, "count": count}
                for code, path, count in self.compiler_code_path_counts
            ],
            "solve_code_counts": dict(self.solve_code_counts),
            "law_id_counts": dict(self.law_id_counts),
            "verification_check_counts": [
                {"kind": kind, "status": status, "count": count}
                for kind, status, count in self.verification_check_counts
            ],
            "structure_counts": dict(self.structure_counts),
            "solved_case_count": len(self.solved_outputs),
        }


def build_pipeline_failure_matrix(cases: Iterable[Any]) -> LaneBPipelineMatrix:
    """Run the real Lane B pipeline and aggregate it privacy-safely.

    The runtime never consults an expected terminal, an expected answer, a
    family, a split, or a case ID; comparison against those belongs to the gold
    domain after the runtime snapshot is frozen.
    """

    terminals: Counter[str] = Counter()
    taxonomy: Counter[str] = Counter()
    compiler_statuses: Counter[str] = Counter()
    normalization_terminals: Counter[str] = Counter()
    solve_terminals: Counter[str] = Counter()
    exceptions: Counter[str] = Counter()
    validation_paths: Counter[tuple[str, str]] = Counter()
    compiler_paths: Counter[tuple[str, str]] = Counter()
    solve_codes: Counter[str] = Counter()
    law_ids: Counter[str] = Counter()
    checks: Counter[tuple[str, str]] = Counter()
    structures: Counter[str] = Counter()
    solved_outputs: list[tuple[int, float, str]] = []
    total = 0
    executed = 0

    for index, case in enumerate(cases):
        total += 1
        projection = project_case_to_draft(case)
        structures["segment_internal_events"] += len(
            projection.segment_internal_event_ids
        )
        structures["environment_scoped_quantities"] += len(
            projection.environment_scoped_quantity_ids
        )
        structures["approved_assumptions"] += len(projection.approvable_assumption_ids)
        structures["known_symbols"] += len(projection.known_symbol_ids)
        structures["unknown_symbols"] += len(projection.unknown_symbol_ids)
        if projection.projected:
            structures["projected"] += 1
            executed += 1

        result = run_lane_b_case(
            projection, execution_token=deterministic_token(index)
        )
        terminals[result.terminal.value] += 1
        taxonomy[_TAXONOMY.get(result.terminal.value, "UNCLASSIFIED")] += 1
        if result.compiler_status is not None:
            compiler_statuses[result.compiler_status] += 1
        if result.normalization_terminal is not None:
            normalization_terminals[result.normalization_terminal] += 1
        if result.solve_terminal is not None:
            solve_terminals[result.solve_terminal] += 1
        if result.stage_exception is not None:
            exceptions[result.stage_exception] += 1
        for code, path in result.validation_code_paths:
            validation_paths[(code, path)] += 1
        for code, path in result.compiler_code_paths:
            compiler_paths[(code, path)] += 1
        for code in result.solve_codes:
            solve_codes[code] += 1
        for law_id in result.applied_law_ids:
            law_ids[law_id] += 1
        for kind, status in result.verification_checks:
            checks[(kind, status)] += 1
        structures["equations"] += result.equation_count
        structures["candidates"] += result.candidate_count
        structures["rejected_candidates"] += result.rejected_candidate_count
        structures["verified_candidates"] += result.verified_candidate_count
        if (
            result.terminal.value == "solved"
            and result.answer_value_si is not None
        ):
            solved_outputs.append(
                (index, result.answer_value_si, result.answer_unit or "")
            )

    return LaneBPipelineMatrix(
        version=PIPELINE_MATRIX_VERSION,
        projection_version=DRAFT_PROJECTION_VERSION,
        runner_version=LANE_B_RUNNER_VERSION,
        total_cases=total,
        executed_cases=executed,
        terminal_counts=tuple(sorted(terminals.items())),
        taxonomy_counts=tuple(sorted(taxonomy.items())),
        compiler_status_counts=tuple(sorted(compiler_statuses.items())),
        normalization_terminal_counts=tuple(sorted(normalization_terminals.items())),
        solve_terminal_counts=tuple(sorted(solve_terminals.items())),
        stage_exception_counts=tuple(sorted(exceptions.items())),
        validation_code_path_counts=tuple(
            (code, path, count)
            for (code, path), count in sorted(validation_paths.items())
        ),
        compiler_code_path_counts=tuple(
            (code, path, count)
            for (code, path), count in sorted(compiler_paths.items())
        ),
        solve_code_counts=tuple(sorted(solve_codes.items())),
        law_id_counts=tuple(sorted(law_ids.items())),
        verification_check_counts=tuple(
            (kind, status, count) for (kind, status), count in sorted(checks.items())
        ),
        structure_counts=tuple(sorted(structures.items())),
        solved_outputs=tuple(solved_outputs),
    )


def build_failure_matrix(cases: Iterable[Any], *, validate) -> LaneBFailureMatrix:
    """Build the matrix from corpus cases and a draft validator callable."""

    terminals: Counter[str] = Counter()
    rejections: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    code_paths: Counter[tuple[str, str]] = Counter()
    structures: Counter[str] = Counter()
    total = 0

    for case in cases:
        total += 1
        projection = project_case_to_draft(case)
        terminals[projection.terminal.value] += 1
        structures["segment_internal_events"] += len(
            projection.segment_internal_event_ids
        )
        structures["environment_scoped_quantities"] += len(
            projection.environment_scoped_quantity_ids
        )
        structures["approvable_assumptions"] += len(projection.approvable_assumption_ids)

        if projection.terminal is DraftProjectionTerminal.projection_rejected:
            rejections[projection.sanitized_reason or "unknown"] += 1
            continue
        if projection.terminal is not DraftProjectionTerminal.projected:
            continue

        structures["entities"] += len(projection.draft.entities)
        structures["motion_intervals"] += len(projection.draft.motion_intervals)
        structures["events"] += len(projection.draft.events)
        structures["quantities"] += len(projection.draft.quantities)
        structures["interactions"] += len(projection.draft.interactions)
        structures["queries"] += len(projection.draft.queries)

        result = validate(
            projection.problem_text,
            projection.draft,
            approved_assumption_ids=projection.approvable_assumption_ids,
        )
        if result.accepted:
            structures["validate_draft_accepted"] += 1
            continue
        structures["validate_draft_rejected"] += 1
        for issue in result.issues:
            code = str(getattr(issue.code, "value", issue.code))
            issues[code] += 1
            code_paths[(code, _path_family(issue.path))] += 1

    return LaneBFailureMatrix(
        version=FAILURE_MATRIX_VERSION,
        projection_version=DRAFT_PROJECTION_VERSION,
        total_cases=total,
        terminal_counts=tuple(sorted(terminals.items())),
        projection_rejection_counts=tuple(sorted(rejections.items())),
        validator_issue_counts=tuple(sorted(issues.items())),
        validator_code_path_counts=tuple(
            (code, path, count) for (code, path), count in sorted(code_paths.items())
        ),
        structure_counts=tuple(sorted(structures.items())),
    )
