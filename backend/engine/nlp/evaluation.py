from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
import json
import math
from pathlib import Path
from typing import Any

from engine.extraction.extractor import extract_problem
from engine.extraction.normalizer import NORMALIZATION_SURFACE_FORMS
from engine.services import solve_problem


DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "benchmarks"
    / "phase44_korean_nlp_curated.json"
)

GATES = {
    "case_count": 300,
    "status_accuracy": 0.95,
    "subtype_accuracy": 0.95,
    "candidate_coverage_accuracy": 0.95,
    "missing_info_accuracy": 1.0,
    "conflict_symbol_accuracy": 1.0,
    "quantity_precision": 0.98,
    "quantity_recall": 0.98,
    "unit_normalization_accuracy": 0.99,
    "subject_binding_accuracy": 0.95,
    "requested_output_accuracy": 0.97,
    "direction_accuracy": 0.95,
    "assumption_classification_accuracy": 0.95,
    "system_type_top1_accuracy": 0.95,
    "system_type_topk_recall": 0.98,
    "ambiguity_detection_recall": 0.95,
    "unsupported_precision": 1.0,
    "unsupported_recall": 1.0,
    "false_solve_rate": 0.0,
    "unnecessary_clarification_rate": 0.02,
    "missing_clarification_rate": 0.02,
    "condition_classification_error_rate": 0.05,
    "contradictory_input_detection_rate": 1.0,
    "canonical_consistency_accuracy": 0.98,
    "high_confidence_false_solves": 0,
}

TOP_K = 3
MIN_SAMPLES = {
    key: (300 if key == "case_count" else 1)
    for key in GATES
}


def load_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _close(actual: Any, expected: Any) -> bool:
    if actual is None or expected is None:
        return actual is expected
    try:
        return math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9)
    except (TypeError, ValueError):
        return actual == expected


def _candidate_types(canonical) -> set[str]:
    v2 = canonical.canonical_v2
    candidates = {canonical.system_type}
    if v2 is not None:
        for parse_candidate in v2.parse_candidates:
            candidates.update(item.system_type for item in parse_candidate.system_type_candidates)
    return candidates


def _topk_candidate_types(canonical, k: int = TOP_K) -> list[str]:
    ranked: list[tuple[float, int, str]] = [(1.0, -1, canonical.system_type)]
    v2 = canonical.canonical_v2
    if v2 is not None:
        order = 0
        for parse_candidate in v2.parse_candidates:
            for item in parse_candidate.system_type_candidates:
                ranked.append((float(item.score), order, item.system_type))
                order += 1
    ranked.sort(key=lambda item: (-item[0], item[1]))
    unique: list[str] = []
    for _, _, system_type in ranked:
        if system_type not in unique:
            unique.append(system_type)
        if len(unique) == k:
            break
    return unique


def _candidate_interpretations(canonical) -> set[tuple[str, str | None]]:
    interpretations = {(canonical.system_type, canonical.subtype)}
    v2 = canonical.canonical_v2
    if v2 is not None:
        for parse_candidate in v2.parse_candidates:
            interpretations.update(
                (item.system_type, item.subtype)
                for item in parse_candidate.system_type_candidates
            )
    return interpretations


def _confidence(canonical) -> float:
    v2 = canonical.canonical_v2
    scores = [
        float(candidate.score)
        for candidate in (v2.parse_candidates if v2 is not None else [])
    ]
    if scores:
        return max(scores)
    return {"높음": 0.95, "보통": 0.7, "낮음": 0.35}.get(canonical.confidence, 0.5)


def _has_multiple_interpretations(canonical) -> bool:
    return len(_candidate_interpretations(canonical)) > 1


def observed_status(canonical, response) -> str:
    v2 = canonical.canonical_v2
    if v2 is not None and v2.conflicts:
        return "contradictory"
    if canonical.system_type == "unsupported":
        return "unsupported"
    if response.ok:
        return "solved"
    if response.clarification is not None:
        if _has_multiple_interpretations(canonical):
            return "ambiguous"
        return "needs_clarification"
    if canonical.system_type in {"unknown", "unsupported"}:
        return "unsupported"
    if canonical.missing_info:
        return "needs_clarification"
    return "unsupported"


def _semantic_signature(canonical, expected_knowns: dict[str, Any]) -> tuple[Any, ...]:
    values = []
    for symbol in sorted(expected_knowns):
        quantity = canonical.knowns.get(symbol)
        values.append(
            (
                symbol,
                None if quantity is None or quantity.value is None else round(float(quantity.value), 9),
                None if quantity is None else quantity.unit,
            )
        )
    requested_outputs = list(canonical.requested_outputs)
    if canonical.system_type == "collision_1d" and "final_velocity" in requested_outputs:
        requested_outputs.remove("final_velocity")
    return (
        canonical.system_type,
        canonical.subtype,
        tuple(values),
        tuple(requested_outputs),
    )


def _numeric_stimulus_signature(text: str) -> str:
    return re.sub(
        r"-?\d+(?:,\d{3})*(?:\.\d+)?",
        "<num>",
        " ".join(text.lower().split()),
    )


def benchmark_reliability(cases: list[dict[str, Any]]) -> dict[str, Any]:
    exact_texts = {case["text"] for case in cases}
    stimuli = {_numeric_stimulus_signature(case["text"]) for case in cases}
    category_stats: dict[str, dict[str, int]] = {}
    for category in sorted({case["category"] for case in cases}):
        category_cases = [case for case in cases if case["category"] == category]
        category_stats[category] = {
            "case_count": len(category_cases),
            "exact_unique_count": len({case["text"] for case in category_cases}),
            "unique_stimulus_count": len(
                {_numeric_stimulus_signature(case["text"]) for case in category_cases}
            ),
        }
    corpus = "\n".join(case["text"].lower() for case in cases)
    overlapping_forms = sorted(
        {
            form
            for form in NORMALIZATION_SURFACE_FORMS
            if form.lower() in corpus
        }
    )
    return {
        "suite_kind": "curated_regression_suite",
        "identical_sentence_count": len(cases) - len(exact_texts),
        "exact_unique_sentence_count": len(exact_texts),
        "numeric_only_duplicate_count": len(exact_texts) - len(stimuli),
        "unique_sentence_stimulus_count": len(stimuli),
        "category_unique_sentence_counts": category_stats,
        "parser_dictionary_surface_overlap_count": len(overlapping_forms),
        "parser_dictionary_surface_overlaps": overlapping_forms,
        "limitations": [
            "The 320 cases are a curated regression suite.",
            "They do not demonstrate generalization to the distribution of real student inputs.",
            "A score of 1.0 applies only to the current fixed fixtures.",
            "Benchmark independence is limited by repeated templates and parser-dictionary overlap.",
            "An external held-out validation set is follow-up work.",
        ],
    }


def evaluate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    counters: Counter[str] = Counter()
    failures: dict[str, list[dict[str, Any]]] = defaultdict(list)
    confidence_bins = {
        "0.00-0.59": {"count": 0, "correct": 0, "false_solves": 0},
        "0.60-0.79": {"count": 0, "correct": 0, "false_solves": 0},
        "0.80-1.00": {"count": 0, "correct": 0, "false_solves": 0},
    }
    group_signatures: dict[str, list[tuple[str, tuple[Any, ...]]]] = defaultdict(list)

    for case in cases:
        expected = case["expected"]
        canonical = extract_problem(case["text"])
        response = solve_problem(case["text"])
        status = observed_status(canonical, response)
        expected_status = expected["status"]
        expected_system = expected["system_type"]
        top1_ok = canonical.system_type == expected_system
        topk_ok = expected_system in _topk_candidate_types(canonical)
        status_ok = status == expected_status
        subtype_expected = "subtype" in expected
        subtype_ok = (not subtype_expected) or canonical.subtype == expected.get("subtype")
        expected_candidates = set(expected.get("candidate_types", []))
        candidate_coverage_ok = not expected_candidates or expected_candidates.issubset(_candidate_types(canonical))
        counters["cases"] += 1
        counters["status_correct"] += int(status_ok)
        counters["top1_correct"] += int(top1_ok)
        counters["topk_correct"] += int(topk_ok)
        if subtype_expected:
            counters["subtype_expected"] += 1
            counters["subtype_correct"] += int(subtype_ok)
        if expected_candidates:
            counters["candidate_coverage_expected"] += 1
            counters["candidate_coverage_correct"] += int(candidate_coverage_ok)

        if not status_ok:
            failures["status"].append(
                {"id": case["id"], "expected": expected_status, "actual": status}
            )
        if not top1_ok:
            failures["system_type"].append(
                {"id": case["id"], "expected": expected_system, "actual": canonical.system_type}
            )

        if not subtype_ok:
            failures["subtype"].append(
                {"id": case["id"], "expected": expected.get("subtype"), "actual": canonical.subtype}
            )
        if not candidate_coverage_ok:
            failures["candidate_coverage"].append(
                {
                    "id": case["id"],
                    "expected": sorted(expected_candidates),
                    "actual": sorted(_candidate_types(canonical)),
                }
            )

        for symbol, oracle in expected.get("knowns", {}).items():
            counters["quantity_expected"] += 1
            actual = canonical.knowns.get(symbol)
            value_ok = actual is not None and _close(actual.value, oracle.get("value"))
            if value_ok:
                counters["quantity_tp"] += 1
            else:
                counters["quantity_fn"] += 1
                if actual is not None:
                    counters["quantity_fp"] += 1
                failures["quantity"].append(
                    {
                        "id": case["id"],
                        "symbol": symbol,
                        "expected": oracle,
                        "actual": None
                        if actual is None
                        else {"value": actual.value, "unit": actual.unit},
                    }
                )
            counters["unit_expected"] += 1
            unit_ok = actual is not None and actual.unit == oracle.get("unit")
            counters["unit_correct"] += int(unit_ok)
            if not unit_ok:
                failures["unit"].append(
                    {
                        "id": case["id"],
                        "symbol": symbol,
                        "expected": oracle.get("unit"),
                        "actual": None if actual is None else actual.unit,
                    }
                )

        expected_symbols = set(expected.get("knowns", {}))
        allowed_extra = set(expected.get("allowed_extra_knowns", [])) | {"g"}
        forbidden_symbols = set(expected.get("forbidden_knowns", []))
        unexpected_symbols = (
            set(canonical.knowns)
            - expected_symbols
            - allowed_extra
        ) | (set(canonical.knowns) & forbidden_symbols)
        for unexpected in sorted(unexpected_symbols):
            counters["quantity_fp"] += 1
            failures["quantity"].append(
                {
                    "id": case["id"],
                    "unexpected_symbol": unexpected,
                    "actual": {
                        "value": canonical.knowns[unexpected].value,
                        "unit": canonical.knowns[unexpected].unit,
                    },
                }
            )

        facts_by_key = {
            fact.compatibility_key: fact
            for fact in (canonical.canonical_v2.facts if canonical.canonical_v2 else [])
            if fact.compatibility_key
        }
        for symbol, subject in expected.get("subjects", {}).items():
            counters["subject_expected"] += 1
            fact = facts_by_key.get(symbol)
            ok = fact is not None and fact.subject_id == subject
            counters["subject_correct"] += int(ok)
            if not ok:
                failures["subject"].append(
                    {
                        "id": case["id"],
                        "symbol": symbol,
                        "expected": subject,
                        "actual": None if fact is None else fact.subject_id,
                    }
                )

        counters["requested_expected"] += 1
        expected_requested = expected.get("requested_outputs", [])
        observed_requested = list(canonical.requested_outputs)
        # final_velocity is a long-standing student-API compatibility alias
        # for collision velocity. Phase 44 measures the specific collision
        # outputs while allowing that non-breaking alias to remain.
        if (
            "post_collision_velocity" in expected_requested
            and "final_velocity" not in expected_requested
            and "final_velocity" in observed_requested
        ):
            observed_requested.remove("final_velocity")
        requested_ok = observed_requested == expected_requested
        counters["requested_correct"] += int(requested_ok)
        if not requested_ok:
            failures["requested_outputs"].append(
                {
                    "id": case["id"],
                    "expected": expected.get("requested_outputs", []),
                    "actual": canonical.requested_outputs,
                }
            )

        missing_fragment = expected.get("missing_contains")
        if missing_fragment is not None:
            counters["missing_info_expected"] += 1
            missing_ok = any(missing_fragment in item for item in canonical.missing_info)
            counters["missing_info_correct"] += int(missing_ok)
            if not missing_ok:
                failures["missing_info"].append(
                    {"id": case["id"], "expected_contains": missing_fragment, "actual": canonical.missing_info}
                )

        if expected.get("direction") is not None:
            counters["direction_expected"] += 1
            direction_ok = canonical.force_direction == expected["direction"]
            counters["direction_correct"] += int(direction_ok)
            if not direction_ok:
                failures["direction"].append(
                    {
                        "id": case["id"],
                        "expected": expected["direction"],
                        "actual": canonical.force_direction,
                    }
                )

        condition_facts = {
            fact.symbol: fact
            for fact in (canonical.canonical_v2.facts if canonical.canonical_v2 else [])
            if fact.kind == "condition"
        }
        for condition in expected.get("conditions", []):
            counters["condition_expected"] += 1
            fact = condition_facts.get(condition["symbol"])
            ok = fact is not None and fact.status == condition["status"]
            counters["condition_correct"] += int(ok)
            if not ok:
                counters["condition_classification_errors"] += 1
                failures["assumption"].append(
                    {
                        "id": case["id"],
                        "symbol": condition["symbol"],
                        "expected": condition["status"],
                        "actual": None if fact is None else fact.status,
                    }
                )

        # A genuine silent-assumption audit needs an oracle describing which
        # solver defaults are allowed for that case. Cases without that annotation
        # are not silently treated as successes.
        if response.ok and "allowed_assumption_kinds" in expected:
            counters["silent_assumption_expected"] += 1
            allowed_assumptions = set(expected["allowed_assumption_kinds"])
            unexpected_assumptions = sorted(
                {
                    assumption.kind
                    for assumption in (
                        canonical.canonical_v2.assumptions
                        if canonical.canonical_v2 is not None
                        else []
                    )
                    if assumption.source == "solver_default"
                    and assumption.kind not in allowed_assumptions
                }
            )
            if unexpected_assumptions:
                counters["silent_assumption_cases"] += 1
                failures["silent_assumption"].append(
                    {
                        "id": case["id"],
                        "unexpected_assumption_kinds": unexpected_assumptions,
                    }
                )

        if expected_status == "ambiguous":
            counters["ambiguous_expected"] += 1
            detected = (
                response.clarification is not None
                and _has_multiple_interpretations(canonical)
            )
            counters["ambiguous_detected"] += int(detected)
            if not detected:
                failures["ambiguity"].append({"id": case["id"]})

        predicted_unsupported = status == "unsupported"
        true_unsupported = expected_status == "unsupported"
        counters["unsupported_tp"] += int(predicted_unsupported and true_unsupported)
        counters["unsupported_fp"] += int(predicted_unsupported and not true_unsupported)
        counters["unsupported_fn"] += int(not predicted_unsupported and true_unsupported)

        if expected_status != "solved":
            counters["should_not_solve"] += 1
            if response.ok:
                counters["false_solves"] += 1
                failures["false_solve"].append(
                    {
                        "id": case["id"],
                        "expected_status": expected_status,
                        "system_type": canonical.system_type,
                    }
                )
        else:
            counters["should_solve"] += 1
            if not response.ok and response.clarification is not None:
                counters["unnecessary_clarifications"] += 1

        if expected_status in {"ambiguous", "needs_clarification", "contradictory"}:
            counters["clarification_expected"] += 1
            if response.clarification is None:
                counters["missing_clarifications"] += 1
                failures["missing_clarification"].append({"id": case["id"]})

        if expected_status == "contradictory":
            counters["contradiction_expected"] += 1
            detected = bool(canonical.canonical_v2 and canonical.canonical_v2.conflicts)
            counters["contradiction_detected"] += int(detected)
            if not detected:
                failures["contradiction"].append({"id": case["id"]})
            expected_conflict_symbols = expected.get("conflict_symbols", [])
            for symbol in expected_conflict_symbols:
                counters["conflict_symbol_expected"] += 1
                symbol_ok = any(symbol in item for item in (canonical.canonical_v2.conflicts if canonical.canonical_v2 else []))
                counters["conflict_symbol_correct"] += int(symbol_ok)
                if not symbol_ok:
                    failures["conflict_symbol"].append(
                        {"id": case["id"], "symbol": symbol, "actual": canonical.canonical_v2.conflicts if canonical.canonical_v2 else []}
                    )

        score = _confidence(canonical)
        if score < 0.6:
            bin_name = "0.00-0.59"
        elif score < 0.8:
            bin_name = "0.60-0.79"
        else:
            bin_name = "0.80-1.00"
        confidence_bins[bin_name]["count"] += 1
        case_correct = status_ok and top1_ok
        confidence_bins[bin_name]["correct"] += int(case_correct)
        false_solve = expected_status != "solved" and response.ok
        confidence_bins[bin_name]["false_solves"] += int(false_solve)
        if score >= 0.8 and false_solve:
            counters["high_confidence_false_solves"] += 1

        group = case.get("equivalence_group")
        if group:
            group_signatures[group].append(
                (case["id"], _semantic_signature(canonical, expected.get("knowns", {})))
            )

    consistent_groups = 0
    evaluated_groups = 0
    for group, signatures in group_signatures.items():
        if len(signatures) < 2:
            continue
        evaluated_groups += 1
        unique = {signature for _, signature in signatures}
        if len(unique) == 1:
            consistent_groups += 1
        else:
            failures["canonical_consistency"].append(
                {"group": group, "case_ids": [item[0] for item in signatures]}
            )

    sample_specs: dict[str, tuple[int, int]] = {
        "case_count": (counters["cases"], counters["cases"]),
        "status_accuracy": (counters["status_correct"], counters["cases"]),
        "subtype_accuracy": (counters["subtype_correct"], counters["subtype_expected"]),
        "candidate_coverage_accuracy": (
            counters["candidate_coverage_correct"],
            counters["candidate_coverage_expected"],
        ),
        "missing_info_accuracy": (
            counters["missing_info_correct"],
            counters["missing_info_expected"],
        ),
        "conflict_symbol_accuracy": (
            counters["conflict_symbol_correct"],
            counters["conflict_symbol_expected"],
        ),
        "quantity_precision": (
            counters["quantity_tp"],
            counters["quantity_tp"] + counters["quantity_fp"],
        ),
        "quantity_recall": (
            counters["quantity_tp"],
            counters["quantity_tp"] + counters["quantity_fn"],
        ),
        "unit_normalization_accuracy": (
            counters["unit_correct"],
            counters["unit_expected"],
        ),
        "subject_binding_accuracy": (
            counters["subject_correct"],
            counters["subject_expected"],
        ),
        "requested_output_accuracy": (
            counters["requested_correct"],
            counters["requested_expected"],
        ),
        "direction_accuracy": (
            counters["direction_correct"],
            counters["direction_expected"],
        ),
        "assumption_classification_accuracy": (
            counters["condition_correct"],
            counters["condition_expected"],
        ),
        "condition_classification_error_rate": (
            counters["condition_classification_errors"],
            counters["condition_expected"],
        ),
        "system_type_top1_accuracy": (
            counters["top1_correct"],
            counters["cases"],
        ),
        "system_type_topk_recall": (
            counters["topk_correct"],
            counters["cases"],
        ),
        "ambiguity_detection_recall": (
            counters["ambiguous_detected"],
            counters["ambiguous_expected"],
        ),
        "unsupported_precision": (
            counters["unsupported_tp"],
            counters["unsupported_tp"] + counters["unsupported_fp"],
        ),
        "unsupported_recall": (
            counters["unsupported_tp"],
            counters["unsupported_tp"] + counters["unsupported_fn"],
        ),
        "false_solve_rate": (
            counters["false_solves"],
            counters["should_not_solve"],
        ),
        "unnecessary_clarification_rate": (
            counters["unnecessary_clarifications"],
            counters["should_solve"],
        ),
        "missing_clarification_rate": (
            counters["missing_clarifications"],
            counters["clarification_expected"],
        ),
        "silent_assumption_rate": (
            counters["silent_assumption_cases"],
            counters["silent_assumption_expected"],
        ),
        "contradictory_input_detection_rate": (
            counters["contradiction_detected"],
            counters["contradiction_expected"],
        ),
        "canonical_consistency_accuracy": (
            consistent_groups,
            evaluated_groups,
        ),
        "high_confidence_false_solves": (
            counters["high_confidence_false_solves"],
            counters["should_not_solve"],
        ),
    }
    metrics = {
        key: (
            numerator
            if key in {"case_count", "high_confidence_false_solves"}
            else _ratio(numerator, denominator)
        )
        for key, (numerator, denominator) in sample_specs.items()
    }
    metric_samples = {
        key: {
            "numerator": numerator,
            "denominator": denominator,
            "minimum_samples": MIN_SAMPLES.get(key),
            "sufficient_samples": (
                denominator >= MIN_SAMPLES[key]
                if key in MIN_SAMPLES
                else denominator > 0
            ),
        }
        for key, (numerator, denominator) in sample_specs.items()
    }

    gate_results: dict[str, bool] = {}
    gate_details: dict[str, str] = {}
    lower_is_better = {
        "false_solve_rate",
        "unnecessary_clarification_rate",
        "missing_clarification_rate",
        "condition_classification_error_rate",
        "high_confidence_false_solves",
    }
    for key, threshold in GATES.items():
        value = metrics[key]
        samples = metric_samples[key]
        if value is None or not samples["sufficient_samples"]:
            gate_results[key] = False
            gate_details[key] = "insufficient_samples"
        else:
            gate_results[key] = (
                value <= threshold
                if key in lower_is_better
                else value >= threshold
            )
            gate_details[key] = "passed" if gate_results[key] else "failed"

    for values in confidence_bins.values():
        values["accuracy"] = _ratio(values["correct"], values["count"])

    return {
        "schema_version": 1,
        "phase": 44,
        "source": "rule_based_extractor",
        "llm_used": False,
        "case_count": counters["cases"],
        "top_k": TOP_K,
        "metrics": metrics,
        "metric_samples": metric_samples,
        "benchmark_reliability": benchmark_reliability(cases),
        "confidence_bins": confidence_bins,
        "counts": dict(sorted(counters.items())),
        "gates": {
            "thresholds": GATES,
            "minimum_samples": MIN_SAMPLES,
            "results": gate_results,
            "details": gate_details,
            "passed": all(gate_results.values()),
        },
        "failures": {key: value[:100] for key, value in sorted(failures.items())},
    }


def evaluate_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    return evaluate_cases(load_fixture(path)["cases"])


def report_markdown(report: dict[str, Any]) -> str:
    reliability = report["benchmark_reliability"]
    lines = [
        "# Phase 44 Korean NLP Metrics",
        "",
        f"- Cases: {report['case_count']}",
        f"- Top-k: k={report['top_k']}",
        f"- LLM used: {str(report['llm_used']).lower()}",
        f"- Gates passed: {str(report['gates']['passed']).lower()}",
        "",
        "| Metric | Value | Numerator | Denominator | Threshold | Gate |",
        "|---|---:|---:|---:|---:|:---:|",
    ]
    for key, value in report["metrics"].items():
        threshold = report["gates"]["thresholds"].get(key, "report-only")
        gate = report["gates"]["details"].get(key, "n/a")
        samples = report["metric_samples"][key]
        rendered_value = "N/A" if value is None else value
        lines.append(
            f"| {key} | {rendered_value} | {samples['numerator']} | "
            f"{samples['denominator']} | {threshold} | {gate} |"
        )
    lines.extend(["", "## Confidence calibration", ""])
    for name, values in report["confidence_bins"].items():
        accuracy = "N/A" if values["accuracy"] is None else values["accuracy"]
        lines.append(
            f"- {name}: count={values['count']}, accuracy={accuracy}, "
            f"false_solves={values['false_solves']}"
        )
    lines.extend(
        [
            "",
            "## Benchmark reliability",
            "",
            f"- Completely identical sentences beyond the first copy: {reliability['identical_sentence_count']}",
            f"- Exact unique sentences: {reliability['exact_unique_sentence_count']}",
            f"- Numeric-only/template duplicates beyond one representative: {reliability['numeric_only_duplicate_count']}",
            f"- Unique sentence stimuli after numeric-template collapse: {reliability['unique_sentence_stimulus_count']}",
            f"- Parser-dictionary overlapping surface forms: {reliability['parser_dictionary_surface_overlap_count']}",
            "",
            "| Category | Cases | Exact unique | Unique stimuli |",
            "|---|---:|---:|---:|",
        ]
    )
    for category, values in reliability["category_unique_sentence_counts"].items():
        lines.append(
            f"| {category} | {values['case_count']} | "
            f"{values['exact_unique_count']} | {values['unique_stimulus_count']} |"
        )
    lines.extend(
        [
            "",
            "The 320 cases are a curated regression suite. They do not prove "
            "generalization to the real student-input distribution. A 1.0 metric "
            "describes only the current fixed fixtures. Benchmark independence is "
            "limited, and an external held-out validation set remains follow-up work.",
        ]
    )
    return "\n".join(lines) + "\n"
