from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.nlp.evaluation import DEFAULT_FIXTURE, evaluate_fixture, report_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 44 curated Korean NLP benchmark")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()

    report = evaluate_fixture(args.fixture)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(payload, end="")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload, encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(report_markdown(report), encoding="utf-8")
    return 0 if report["gates"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
