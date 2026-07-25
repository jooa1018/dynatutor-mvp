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


FAILURE_MATRIX_VERSION = "phase56-stage7-lane-b-failure-matrix-v1"

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
