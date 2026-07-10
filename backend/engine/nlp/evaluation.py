from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
import json
import math
from pathlib import Path
from typing import Any

from engine.extraction.extractor import extract_problem
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
    "silent_assumption_rate": 0.05,
    "contradictory_input_detection_rate": 1.0,
    "canonical_consistency_accuracy": 0.98,
    "high_confidence_false_solves": 0,
}


def load_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ratio(numerator: int, denominator: int, *, empty: float = 1.0) -> float:
    return round(numerator / denominator, 6) if denominator else empty


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
        topk_ok = expected_system in _candidate_types(canonical)
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

        for forbidden in expected.get("forbidden_knowns", []):
            if forbidden in canonical.knowns:
                counters["quantity_fp"] += 1
                failures["quantity"].append(
                    {"id": case["id"], "forbidden_symbol": forbidden}
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
                counters["silent_assumptions"] += 1
                failures["assumption"].append(
                    {
                        "id": case["id"],
                        "symbol": condition["symbol"],
                        "expected": condition["status"],
                        "actual": None if fact is None else fact.status,
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

    quantity_precision = _ratio(
        counters["quantity_tp"],
        counters["quantity_tp"] + counters["quantity_fp"],
    )
    quantity_recall = _ratio(
        counters["quantity_tp"],
        counters["quantity_tp"] + counters["quantity_fn"],
    )
    unsupported_precision = _ratio(
        counters["unsupported_tp"],
        counters["unsupported_tp"] + counters["unsupported_fp"],
    )
    unsupported_recall = _ratio(
        counters["unsupported_tp"],
        counters["unsupported_tp"] + counters["unsupported_fn"],
    )

    metrics = {
        "case_count": counters["cases"],
        "status_accuracy": _ratio(counters["status_correct"], counters["cases"]),
        "subtype_accuracy": _ratio(counters["subtype_correct"], counters["subtype_expected"]),
        "candidate_coverage_accuracy": _ratio(counters["candidate_coverage_correct"], counters["candidate_coverage_expected"]),
        "missing_info_accuracy": _ratio(counters["missing_info_correct"], counters["missing_info_expected"]),
        "conflict_symbol_accuracy": _ratio(counters["conflict_symbol_correct"], counters["conflict_symbol_expected"]),
        "quantity_precision": quantity_precision,
        "quantity_recall": quantity_recall,
        "unit_normalization_accuracy": _ratio(counters["unit_correct"], counters["unit_expected"]),
        "subject_binding_accuracy": _ratio(counters["subject_correct"], counters["subject_expected"]),
        "requested_output_accuracy": _ratio(counters["requested_correct"], counters["requested_expected"]),
        "direction_accuracy": _ratio(counters["direction_correct"], counters["direction_expected"]),
        "assumption_classification_accuracy": _ratio(counters["condition_correct"], counters["condition_expected"]),
        "system_type_top1_accuracy": _ratio(counters["top1_correct"], counters["cases"]),
        "system_type_topk_recall": _ratio(counters["topk_correct"], counters["cases"]),
        "ambiguity_detection_recall": _ratio(counters["ambiguous_detected"], counters["ambiguous_expected"]),
        "unsupported_precision": unsupported_precision,
        "unsupported_recall": unsupported_recall,
        "false_solve_rate": _ratio(counters["false_solves"], counters["should_not_solve"], empty=0.0),
        "unnecessary_clarification_rate": _ratio(counters["unnecessary_clarifications"], counters["should_solve"], empty=0.0),
        "missing_clarification_rate": _ratio(counters["missing_clarifications"], counters["clarification_expected"], empty=0.0),
        "silent_assumption_rate": _ratio(counters["silent_assumptions"], counters["condition_expected"], empty=0.0),
        "contradictory_input_detection_rate": _ratio(counters["contradiction_detected"], counters["contradiction_expected"]),
        "canonical_consistency_accuracy": _ratio(consistent_groups, evaluated_groups),
        "high_confidence_false_solves": counters["high_confidence_false_solves"],
    }

    gate_results: dict[str, bool] = {}
    lower_is_better = {
        "false_solve_rate",
        "unnecessary_clarification_rate",
        "missing_clarification_rate",
        "silent_assumption_rate",
        "high_confidence_false_solves",
    }
    for key, threshold in GATES.items():
        value = metrics[key]
        gate_results[key] = value <= threshold if key in lower_is_better else value >= threshold

    for values in confidence_bins.values():
        values["accuracy"] = _ratio(values["correct"], values["count"])

    return {
        "schema_version": 1,
        "phase": 44,
        "source": "rule_based_extractor",
        "llm_used": False,
        "case_count": counters["cases"],
        "metrics": metrics,
        "confidence_bins": confidence_bins,
        "counts": dict(sorted(counters.items())),
        "gates": {"thresholds": GATES, "results": gate_results, "passed": all(gate_results.values())},
        "failures": {key: value[:100] for key, value in sorted(failures.items())},
    }


def evaluate_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    return evaluate_cases(load_fixture(path)["cases"])


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 44 Korean NLP Metrics",
        "",
        f"- Cases: {report['case_count']}",
        f"- LLM used: {str(report['llm_used']).lower()}",
        f"- Gates passed: {str(report['gates']['passed']).lower()}",
        "",
        "| Metric | Value | Threshold | Passed |",
        "|---|---:|---:|:---:|",
    ]
    for key, value in report["metrics"].items():
        threshold = report["gates"]["thresholds"].get(key, "report-only")
        passed = report["gates"]["results"].get(key)
        lines.append(
            f"| {key} | {value} | {threshold} | "
            + ("yes" if passed is True else "no" if passed is False else "n/a")
            + " |"
        )
    lines.extend(["", "## Confidence calibration", ""])
    for name, values in report["confidence_bins"].items():
        lines.append(
            f"- {name}: count={values['count']}, accuracy={values['accuracy']}, "
            f"false_solves={values['false_solves']}"
        )
    return "\n".join(lines) + "\n"
