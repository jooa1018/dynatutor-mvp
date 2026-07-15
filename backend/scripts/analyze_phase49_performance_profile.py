from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


METRIC_ORDER = (
    "registry_construction",
    "route",
    "solve_total",
    "projectile",
    "rigid_body",
)
MAX_REGRESSION_PERCENT = 15.0
MIN_REGRESSION_MS = 1.0


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def _summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("raw sample set is empty")
    return {
        "samples": len(values),
        "p50_ms": round(statistics.median(values), 6),
        "p95_ms": round(_percentile(values, 0.95), 6),
        "mean_ms": round(statistics.fmean(values), 6),
        "min_ms": round(min(values), 6),
        "max_ms": round(max(values), 6),
    }


def _comparison(
    base_values: list[float], head_values: list[float]
) -> dict[str, Any]:
    base = _summary(base_values)
    head = _summary(head_values)
    base_p50 = float(base["p50_ms"])
    base_p95 = float(base["p95_ms"])
    head_p50 = float(head["p50_ms"])
    head_p95 = float(head["p95_ms"])
    delta_ms = head_p95 - base_p95
    change_percent = (
        0.0
        if base_p95 <= 0
        else delta_ms / base_p95 * 100.0
    )
    return {
        "base": base,
        "head": head,
        "p50_head_over_base_ratio": (
            None if base_p50 <= 0 else round(head_p50 / base_p50, 6)
        ),
        "p95_head_over_base_ratio": (
            None if base_p95 <= 0 else round(head_p95 / base_p95, 6)
        ),
        "p95_change_percent": round(change_percent, 3),
        "p95_delta_ms": round(delta_ms, 6),
        "existing_gate_exceeded": (
            change_percent > MAX_REGRESSION_PERCENT
            and delta_ms > MIN_REGRESSION_MS
        ),
    }


def _samples(document: dict[str, Any], metric: str) -> list[float]:
    values = document["metrics"][metric]["raw_samples_ms"]
    if len(values) != document["repeats"]:
        raise ValueError(
            f"{document['label']} round {document['round']} metric {metric} "
            "does not contain the declared number of raw samples"
        )
    return [float(value) for value in values]


def analyze(input_dir: Path, expected_rounds: int) -> dict[str, Any]:
    documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(input_dir.glob("round-*.json"))
    ]
    if len(documents) != expected_rounds * 2:
        raise ValueError(
            f"expected {expected_rounds * 2} profile documents, "
            f"found {len(documents)}"
        )

    indexed: dict[int, dict[str, dict[str, Any]]] = {}
    for document in documents:
        if document.get("schema_version") != 1:
            raise ValueError("unsupported profile schema")
        if document.get("metric_order") != list(METRIC_ORDER):
            raise ValueError("profile metric order differs from the benchmark")
        round_number = int(document["round"])
        label = str(document["label"])
        labels = indexed.setdefault(round_number, {})
        if label in labels:
            raise ValueError(f"duplicate {label} document for round {round_number}")
        labels[label] = document

    if sorted(indexed) != list(range(1, expected_rounds + 1)):
        raise ValueError("profile rounds are not contiguous")

    rounds: list[dict[str, Any]] = []
    pooled: dict[str, dict[str, list[float]]] = {
        metric: {"base": [], "head": []} for metric in METRIC_ORDER
    }
    for round_number in sorted(indexed):
        pair = indexed[round_number]
        if set(pair) != {"base", "head"}:
            raise ValueError(f"round {round_number} lacks a head/base pair")
        order = pair["head"]["order"]
        if order != pair["base"]["order"]:
            raise ValueError(f"round {round_number} has conflicting order metadata")
        expected_order = (
            "head-then-base" if round_number % 2 else "base-then-head"
        )
        if order != expected_order:
            raise ValueError(
                f"round {round_number} is {order!r}, expected {expected_order!r}"
            )

        metric_results: dict[str, Any] = {}
        for metric in METRIC_ORDER:
            base_values = _samples(pair["base"], metric)
            head_values = _samples(pair["head"], metric)
            pooled[metric]["base"].extend(base_values)
            pooled[metric]["head"].extend(head_values)
            metric_results[metric] = _comparison(base_values, head_values)
        rounds.append(
            {"round": round_number, "order": order, "metrics": metric_results}
        )

    aggregate = {
        metric: _comparison(values["base"], values["head"])
        for metric, values in pooled.items()
    }
    return {
        "schema_version": 1,
        "diagnostic_only": True,
        "gate_contract": {
            "p95_change_percent_greater_than": MAX_REGRESSION_PERCENT,
            "p95_delta_ms_greater_than": MIN_REGRESSION_MS,
        },
        "metric_order": list(METRIC_ORDER),
        "rounds": rounds,
        "aggregate": aggregate,
        "aggregate_gate_exceeded_metrics": [
            metric
            for metric in METRIC_ORDER
            if aggregate[metric]["existing_gate_exceeded"]
        ],
    }


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Phase 49 performance profile",
        "",
        "Diagnostic only: exceeding the existing >15% and >1ms p95 gate "
        "does not fail this workflow.",
        "",
        "## Aggregate (pooled raw samples)",
        "",
        "| metric | base p50 | head p50 | p50 ratio | base p95 | head p95 | p95 ratio | change | gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for metric in METRIC_ORDER:
        item = result["aggregate"][metric]
        lines.append(
            f"| {metric} | {item['base']['p50_ms']:.6f} | "
            f"{item['head']['p50_ms']:.6f} | "
            f"{item['p50_head_over_base_ratio']:.6f} | "
            f"{item['base']['p95_ms']:.6f} | "
            f"{item['head']['p95_ms']:.6f} | "
            f"{item['p95_head_over_base_ratio']:.6f} | "
            f"{item['p95_change_percent']:.3f}% | "
            f"{'YES' if item['existing_gate_exceeded'] else 'no'} |"
        )

    lines.extend(["", "## Per round", ""])
    for round_result in result["rounds"]:
        lines.extend(
            [
                f"### Round {round_result['round']} ({round_result['order']})",
                "",
                "| metric | base p50 | head p50 | p50 ratio | base p95 | head p95 | p95 ratio | change | gate |",
                "|---|---:|---:|---:|---:|---:|---:|---:|:---:|",
            ]
        )
        for metric in METRIC_ORDER:
            item = round_result["metrics"][metric]
            lines.append(
                f"| {metric} | {item['base']['p50_ms']:.6f} | "
                f"{item['head']['p50_ms']:.6f} | "
                f"{item['p50_head_over_base_ratio']:.6f} | "
                f"{item['base']['p95_ms']:.6f} | "
                f"{item['head']['p95_ms']:.6f} | "
                f"{item['p95_head_over_base_ratio']:.6f} | "
                f"{item['p95_change_percent']:.3f}% | "
                f"{'YES' if item['existing_gate_exceeded'] else 'no'} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--expected-rounds", type=int, default=4)
    args = parser.parse_args()

    result = analyze(args.input_dir, args.expected_rounds)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(_markdown(result), encoding="utf-8")
    # Deliberately do not exit non-zero for diagnostic gate exceedances.


if __name__ == "__main__":
    main()
