from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from engine.mechanics import canonical_fallback as catalogue
from evaluation.phase56_stage7.contracts import Stage7ExpectedTerminal
from evaluation.phase56_stage7.corpus_semantics import scope_adjusted_expected_terminal
from evaluation.phase56_stage7.corpus_v2.migration import record_fingerprint
from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (
    load_full_runtime_snapshot,
    scoring_handle,
)
from evaluation.phase56_stage7.lane_b_draft_projection import project_case_to_draft
from evaluation.phase56_stage7.lane_b_scoring import (
    AnswerVerdict,
    compare_answer_to_gold,
    gold_scoring_registry,
)
from evaluation.phase57_reproducible.continuation_manifest import (
    build_phase57_continuation_manifest,
)
from evaluation.phase57_reproducible.contracts import PHASE57_REPRODUCIBLE_ARCHIVE_SHA256
from evaluation.phase57_reproducible.fixtures import load_public_fixture_cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases = list(load_public_fixture_cases())
    manifest = build_phase57_continuation_manifest(cases)
    entries = {item.original_fingerprint: item for item in manifest.manifest.entries}
    snapshot = load_full_runtime_snapshot(
        args.baseline_snapshot.read_text(encoding="utf-8")
    )
    solved_handles = {
        item.scoring_handle for item in snapshot.records if item.shadow_solved
    }
    registry = gold_scoring_registry()
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "fires": 0,
            "correct": 0,
            "wrong": 0,
            "unscored": 0,
            "blocked_class_fires": 0,
            "new_correct_positions": [],
            "all_correct_positions": [],
            "canonical_by_position": {},
        }
    )

    for index, case in enumerate(cases):
        projection = project_case_to_draft(case)
        if projection.draft is None:
            continue
        payload = projection.draft.model_dump(mode="json", warnings="none")
        fingerprint = record_fingerprint(
            case.model_dump(mode="json", warnings="none")
        )
        entry = entries.get(fingerprint)
        if entry is not None:
            payload = project_augmentation(
                payload,
                entry.augmentation,
                problem_text=projection.problem_text,
            )
        expected = scope_adjusted_expected_terminal(case, case_index=index)
        handle = scoring_handle(
            original_v1_archive_sha256=PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
            context_index=index,
        )
        baseline_solved = handle in solved_handles
        for candidate in catalogue.all_canonical_mechanics_candidates(
            payload, problem_text=projection.problem_text
        ):
            row = stats[candidate.rule_id]
            row["fires"] += 1
            canonical = catalogue._canonical(candidate)
            if canonical is None:
                row["unscored"] += 1
                continue
            row["canonical_by_position"][str(index)] = [canonical[0], canonical[1]]
            if expected is not Stage7ExpectedTerminal.accepted:
                row["blocked_class_fires"] += 1
                continue
            if len(case.gold.answers) != 1:
                row["unscored"] += 1
                continue
            try:
                value_si = float(
                    (
                        candidate.value * catalogue._UREG(candidate.unit)
                    ).to_base_units().magnitude
                )
                verdict = compare_answer_to_gold(
                    registry,
                    case.gold.answers[0],
                    value_si=value_si,
                    unit=candidate.unit,
                ).verdict
            except Exception:
                row["unscored"] += 1
                continue
            if verdict is AnswerVerdict.correct:
                row["correct"] += 1
                row["all_correct_positions"].append(index)
                if not baseline_solved:
                    row["new_correct_positions"].append(index)
            elif verdict is AnswerVerdict.wrong:
                row["wrong"] += 1
            else:
                row["unscored"] += 1

    safe = [
        rule
        for rule, row in stats.items()
        if row["wrong"] == 0
        and row["unscored"] == 0
        and row["blocked_class_fires"] == 0
        and row["new_correct_positions"]
    ]
    safe.sort(
        key=lambda rule: (
            -len(set(stats[rule]["new_correct_positions"])),
            -len(set(stats[rule]["all_correct_positions"])),
            rule,
        )
    )

    selected: list[str] = []
    selected_answers: dict[str, tuple[str, float]] = {}
    covered_new: set[int] = set()
    conflicts: dict[str, list[int]] = {}
    for rule in safe:
        answers = {
            position: (value[0], float(value[1]))
            for position, value in stats[rule]["canonical_by_position"].items()
        }
        disagreement = [
            int(position)
            for position, value in answers.items()
            if position in selected_answers and selected_answers[position] != value
        ]
        if disagreement:
            conflicts[rule] = disagreement
            continue
        gain = set(stats[rule]["new_correct_positions"]) - covered_new
        if not gain:
            continue
        selected.append(rule)
        selected_answers.update(answers)
        covered_new.update(stats[rule]["new_correct_positions"])

    if not selected:
        raise SystemExit("no_safe_catalogue_gain")

    path = Path("backend/engine/mechanics/canonical_fallback.py")
    body = path.read_text(encoding="utf-8")
    marker = "ENABLED_RULES: frozenset[str] = frozenset()"
    if marker not in body:
        raise SystemExit("catalogue_enabled_marker_missing")
    body = body.replace(
        marker,
        "ENABLED_RULES: frozenset[str] = frozenset(" + repr(tuple(selected)) + ")",
        1,
    )
    path.write_text(body, encoding="utf-8")

    report = {
        "baseline_solved_count": len(solved_handles),
        "selected_rules": selected,
        "selected_new_positions": sorted(covered_new),
        "safe_rule_count": len(safe),
        "rejected_conflicts": conflicts,
        "stats": dict(stats),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("PHASE57_TERMINAL_SELECTED_RULES=" + ",".join(selected))
    print(
        "PHASE57_TERMINAL_SELECTED_NEW_POSITIONS="
        + ",".join(map(str, sorted(covered_new)))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
