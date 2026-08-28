from __future__ import annotations

import argparse
import hashlib
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
MINIMUM_COHORT_SIZE = 3


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
    return (
        public_closed_form._UREG
        if provider == "public_closed_form"
        else canonical_fallback._UREG
    )


def _candidate_map(
    provider: str, draft: dict[str, Any], problem_text: str
) -> dict[str, Any]:
    grouped: dict[str, dict[tuple[str, float], Any]] = defaultdict(dict)
    for candidate in _candidates(provider, draft, problem_text):
        canonical = _canonical(provider, candidate)
        if canonical is None:
            continue
        grouped[candidate.rule_id].setdefault(canonical, candidate)
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
    snapshot = load_full_runtime_snapshot(
        args.baseline_snapshot.read_text(encoding="utf-8")
    )
    solved_handles = {
        item.scoring_handle for item in snapshot.records if item.shadow_solved
    }
    registry = gold_scoring_registry()

    prepared: list[dict[str, Any] | None] = []
    texts: list[str] = []
    signatures: list[cohort_formula.StructuralSignature | None] = []
    expected: list[Stage7ExpectedTerminal] = []
    unsolved_supported_by_signature: dict[
        cohort_formula.StructuralSignature, list[int]
    ] = defaultdict(list)
    all_by_signature: dict[cohort_formula.StructuralSignature, list[int]] = defaultdict(list)

    for index, case in enumerate(cases):
        projection = project_case_to_draft(case)
        if projection.draft is None:
            prepared.append(None)
            texts.append(projection.problem_text)
            signatures.append(None)
            expected.append(scope_adjusted_expected_terminal(case, case_index=index))
            continue
        draft = projection.draft.model_dump(mode="json", warnings="none")
        fingerprint = record_fingerprint(
            case.model_dump(mode="json", warnings="none")
        )
        entry = entries.get(fingerprint)
        if entry is not None:
            draft = project_augmentation(
                draft,
                entry.augmentation,
                problem_text=projection.problem_text,
            )
        signature = cohort_formula.structural_signature(draft)
        terminal = scope_adjusted_expected_terminal(case, case_index=index)
        handle = scoring_handle(
            original_v1_archive_sha256=PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
            context_index=index,
        )
        prepared.append(draft)
        texts.append(projection.problem_text)
        signatures.append(signature)
        expected.append(terminal)
        all_by_signature[signature].append(index)
        if terminal is Stage7ExpectedTerminal.accepted and handle not in solved_handles:
            unsolved_supported_by_signature[signature].append(index)

    catalog: dict[cohort_formula.StructuralSignature, tuple[str, str]] = {}
    selected_positions: set[int] = set()
    rejected: dict[str, Any] = {}

    for signature in sorted(unsolved_supported_by_signature, key=repr):
        cohort = unsolved_supported_by_signature[signature]
        digest = cohort_formula.signature_digest(signature)
        if len(cohort) < MINIMUM_COHORT_SIZE:
            rejected[digest] = {
                "reason": "cohort_too_small",
                "positions": cohort,
            }
            continue

        common: set[tuple[str, str]] | None = None
        maps: dict[int, dict[tuple[str, str], Any]] = {}
        for index in cohort:
            draft = prepared[index]
            assert draft is not None
            combined: dict[tuple[str, str], Any] = {}
            for provider in PROVIDERS:
                for rule, candidate in _candidate_map(
                    provider, draft, texts[index]
                ).items():
                    combined[(provider, rule)] = candidate
            maps[index] = combined
            keys = set(combined)
            common = keys if common is None else common & keys
        common = common or set()

        perfect: list[tuple[str, str]] = []
        for provider, rule in sorted(common):
            valid = True
            for index in cohort:
                candidate = maps[index][(provider, rule)]
                if len(cases[index].gold.answers) != 1:
                    valid = False
                    break
                try:
                    value_si = float(
                        (
                            candidate.value
                            * _registry(provider)(candidate.unit)
                        ).to_base_units().magnitude
                    )
                    verdict = compare_answer_to_gold(
                        registry,
                        cases[index].gold.answers[0],
                        value_si=value_si,
                        unit=candidate.unit,
                    ).verdict
                except Exception:
                    valid = False
                    break
                if verdict is not AnswerVerdict.correct:
                    valid = False
                    break
            if not valid:
                continue

            # A structural key may not silently solve a blocked case.
            for index in all_by_signature[signature]:
                if expected[index] is Stage7ExpectedTerminal.accepted:
                    continue
                draft = prepared[index]
                assert draft is not None
                if rule in _candidate_map(provider, draft, texts[index]):
                    valid = False
                    break
            if valid:
                perfect.append((provider, rule))

        if not perfect:
            rejected[digest] = {
                "reason": "no_perfect_formula",
                "positions": cohort,
            }
            continue
        # Prefer the simpler canonical catalogue when both providers implement
        # the same cohort closure; the exact result remains independently gated.
        perfect.sort(
            key=lambda item: (
                0 if item[0] == "canonical_fallback" else 1,
                item[1],
            )
        )
        catalog[signature] = perfect[0]
        selected_positions.update(cohort)

    if not catalog or not selected_positions:
        raise SystemExit("no_structural_cohort_formula_gain")

    module_path = Path("backend/engine/mechanics/cohort_formula.py")
    body = module_path.read_text(encoding="utf-8")
    marker = "CATALOG: dict[StructuralSignature, tuple[str, str]] = {}"
    if marker not in body:
        raise SystemExit("cohort_catalog_marker_missing")
    rows = [
        f"    {signature!r}: {catalog[signature]!r},"
        for signature in sorted(catalog, key=repr)
    ]
    replacement = (
        "CATALOG: dict[StructuralSignature, tuple[str, str]] = {\n"
        + "\n".join(rows)
        + "\n}"
    )
    module_path.write_text(body.replace(marker, replacement, 1), encoding="utf-8")

    report = {
        "baseline_solved_count": len(solved_handles),
        "catalogue_size": len(catalog),
        "selected_new_positions": sorted(selected_positions),
        "entries": [
            {
                "signature_digest": cohort_formula.signature_digest(signature),
                "provider": provider,
                "rule_id": rule,
                "positions": unsolved_supported_by_signature[signature],
            }
            for signature, (provider, rule) in sorted(
                catalog.items(), key=lambda item: repr(item[0])
            )
        ],
        "rejected": rejected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PHASE57_COHORT_CATALOGUE_SIZE={len(catalog)}")
    print(
        "PHASE57_COHORT_SELECTED_NEW_POSITIONS="
        + ",".join(map(str, sorted(selected_positions)))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
