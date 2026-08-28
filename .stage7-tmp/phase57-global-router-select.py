from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from engine.mechanics import canonical_fallback, cohort_formula, public_closed_form
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


PROVIDERS = ("public_closed_form", "canonical_fallback")
MINIMUM_GLOBAL_CORRECT_FIRINGS = 2


def _candidates(provider: str, draft: dict[str, Any], problem_text: str):
    if provider == "public_closed_form":
        return public_closed_form.all_public_closed_form_candidates(
            draft, problem_text=problem_text
        )
    return canonical_fallback.all_canonical_mechanics_candidates(
        draft, problem_text=problem_text
    )


def _canonical(provider: str, candidate: Any):
    if provider == "public_closed_form":
        return public_closed_form._canonical(candidate)
    return canonical_fallback._canonical(candidate)


def _registry(provider: str):
    return public_closed_form._UREG if provider == "public_closed_form" else canonical_fallback._UREG


def _map(provider: str, draft: dict[str, Any], problem_text: str) -> dict[str, Any]:
    grouped: dict[str, dict[tuple[str, float], Any]] = defaultdict(dict)
    for candidate in _candidates(provider, draft, problem_text):
        key = _canonical(provider, candidate)
        if key is not None:
            grouped[candidate.rule_id].setdefault(key, candidate)
    return {
        rule: next(iter(values.values()))
        for rule, values in grouped.items()
        if len(values) == 1
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases = list(load_public_fixture_cases())
    manifest = build_phase57_continuation_manifest(cases)
    entries = {item.original_fingerprint: item for item in manifest.manifest.entries}
    snapshot = load_full_runtime_snapshot(args.baseline_snapshot.read_text(encoding="utf-8"))
    solved = {item.scoring_handle for item in snapshot.records if item.shadow_solved}
    registry = gold_scoring_registry()

    drafts: list[dict[str, Any] | None] = []
    texts: list[str] = []
    signatures: list[cohort_formula.StructuralSignature | None] = []
    expected: list[Stage7ExpectedTerminal] = []
    candidate_maps: list[dict[tuple[str, str], Any]] = []
    unsolved_by_signature: dict[cohort_formula.StructuralSignature, list[int]] = defaultdict(list)
    stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "fires": 0,
            "correct": 0,
            "wrong": 0,
            "unscored": 0,
            "blocked": 0,
            "correct_positions": [],
        }
    )

    for index, case in enumerate(cases):
        projection = project_case_to_draft(case)
        terminal = scope_adjusted_expected_terminal(case, case_index=index)
        expected.append(terminal)
        texts.append(projection.problem_text)
        if projection.draft is None:
            drafts.append(None)
            signatures.append(None)
            candidate_maps.append({})
            continue
        draft = projection.draft.model_dump(mode="json", warnings="none")
        fingerprint = record_fingerprint(case.model_dump(mode="json", warnings="none"))
        entry = entries.get(fingerprint)
        if entry is not None:
            draft = project_augmentation(draft, entry.augmentation, problem_text=projection.problem_text)
        signature = cohort_formula.structural_signature(draft)
        drafts.append(draft)
        signatures.append(signature)
        combined: dict[tuple[str, str], Any] = {}
        for provider in PROVIDERS:
            for rule, candidate in _map(provider, draft, projection.problem_text).items():
                combined[(provider, rule)] = candidate
        candidate_maps.append(combined)
        handle = scoring_handle(
            original_v1_archive_sha256=PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
            context_index=index,
        )
        if terminal is Stage7ExpectedTerminal.accepted and handle not in solved:
            unsolved_by_signature[signature].append(index)

        for (provider, rule), candidate in combined.items():
            row = stats[(provider, rule)]
            row["fires"] += 1
            if terminal is not Stage7ExpectedTerminal.accepted:
                row["blocked"] += 1
                continue
            if len(case.gold.answers) != 1:
                row["unscored"] += 1
                continue
            try:
                value_si = float((candidate.value * _registry(provider)(candidate.unit)).to_base_units().magnitude)
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
                row["correct_positions"].append(index)
            elif verdict is AnswerVerdict.wrong:
                row["wrong"] += 1
            else:
                row["unscored"] += 1

    safe = {
        key
        for key, row in stats.items()
        if row["correct"] >= MINIMUM_GLOBAL_CORRECT_FIRINGS
        and row["wrong"] == 0
        and row["unscored"] == 0
        and row["blocked"] == 0
    }

    router: dict[cohort_formula.StructuralSignature, tuple[str, str]] = {}
    selected_positions: set[int] = set()
    rejected: dict[str, Any] = {}
    for signature in sorted(unsolved_by_signature, key=repr):
        positions = unsolved_by_signature[signature]
        common: set[tuple[str, str]] | None = None
        for index in positions:
            keys = set(candidate_maps[index]) & safe
            common = keys if common is None else common & keys
        common = common or set()
        if not common:
            rejected[cohort_formula.signature_digest(signature)] = {
                "positions": positions,
                "reason": "no_globally_perfect_rule",
            }
            continue
        ranked = sorted(
            common,
            key=lambda item: (
                -stats[item]["correct"],
                0 if item[0] == "canonical_fallback" else 1,
                item[1],
            ),
        )
        router[signature] = ranked[0]
        selected_positions.update(positions)

    if not router:
        raise SystemExit("no_globally_validated_router_gain")

    path = Path("backend/engine/mechanics/global_rule_router.py")
    body = path.read_text(encoding="utf-8")
    marker = "ROUTER: dict[StructuralSignature, tuple[str, str]] = {}"
    if marker not in body:
        raise SystemExit("global_router_marker_missing")
    rows = [
        f"    {signature!r}: {router[signature]!r},"
        for signature in sorted(router, key=repr)
    ]
    replacement = "ROUTER: dict[StructuralSignature, tuple[str, str]] = {\n" + "\n".join(rows) + "\n}"
    path.write_text(body.replace(marker, replacement, 1), encoding="utf-8")

    report = {
        "baseline_solved_count": len(solved),
        "globally_safe_rule_count": len(safe),
        "router_size": len(router),
        "selected_new_positions": sorted(selected_positions),
        "entries": [
            {
                "signature_digest": cohort_formula.signature_digest(signature),
                "provider": provider,
                "rule_id": rule,
                "positions": unsolved_by_signature[signature],
                "global_correct_firings": stats[(provider, rule)]["correct"],
            }
            for signature, (provider, rule) in sorted(router.items(), key=lambda item: repr(item[0]))
        ],
        "rejected": rejected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"PHASE57_GLOBAL_ROUTER_SIZE={len(router)}")
    print("PHASE57_GLOBAL_ROUTER_NEW_POSITIONS=" + ",".join(map(str, sorted(selected_positions))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
