from __future__ import annotations

from dataclasses import replace
import os
import sys

from engine.textbook_parser.config import ParserMode, TextbookParserConfig
from engine.textbook_parser.seed_corpus import repository_safe_seed_manifest
from engine.textbook_parser.orchestrator import parse_textbook_problem


CASE_LIMIT = 20
COST_LIMIT_USD = 0.25


def main() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("SKIPPED: OPENAI_API_KEY is not configured; no live PASS is claimed.")
        return 2
    config = replace(
        TextbookParserConfig.from_env(),
        enabled=True,
        mode=ParserMode.required,
    )
    cases = repository_safe_seed_manifest().cases[:CASE_LIMIT]
    total_cost = 0.0
    failures: list[str] = []
    for case in cases:
        if total_cost >= COST_LIMIT_USD:
            print(f"ABORTED: cumulative estimated cost reached ${total_cost:.6f}.")
            return 3
        outcome = parse_textbook_problem(case.problem_text, config=config)
        total_cost += outcome.usage.estimated_cost_usd
        if outcome.status.value in {"parser_error", "parser_unavailable"}:
            failures.append(f"{case.case_id}:{outcome.failure_code or outcome.status.value}")
        if outcome.validated and any(
            issue.code.value == "invented_explicit_number"
            for issue in outcome.validated.issues
        ):
            failures.append(f"{case.case_id}:invented_explicit_number")
        print(
            f"{case.case_id} status={outcome.status.value} "
            f"tokens={outcome.usage.input_tokens}/{outcome.usage.output_tokens} "
            f"cost=${outcome.usage.estimated_cost_usd:.6f}"
        )
    print(f"Live smoke cases={len(cases)} estimated_cost=${total_cost:.6f}")
    if total_cost > COST_LIMIT_USD:
        print("FAILED: cost limit exceeded.")
        return 3
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
