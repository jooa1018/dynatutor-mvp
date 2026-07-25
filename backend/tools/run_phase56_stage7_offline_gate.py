"""Permanent Stage 7 offline evaluation gate.

The gate is read-only.  It never edits source, never pushes, never dispatches a
finalizer, never modifies itself, never reads a secret, and never contacts an
external endpoint: credentials and provider base URLs must be empty and socket
creation is blocked for the whole evaluation phase.

Corpus integrity runs before any execution.  When the authorised public archive
is not supplied to the runner, the public-100 lanes are reported as
``NOT_RUN`` — they are never reported as passing.

Only a redacted aggregate artifact is emitted; the redaction contract is
enforced before the artifact is written, so a redaction failure blocks report
generation instead of leaking.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.contracts import (  # noqa: E402
    STAGE7_CONTRACT_VERSION,
    STAGE7_EVALUATOR_VERSION,
    stage7_evaluation_contract,
)
from evaluation.phase56_stage7.corpus_preflight import (  # noqa: E402
    assert_corpus_modules_are_execution_free,
    assert_raw_corpus_is_not_committed,
    run_corpus_integrity_preflight,
)
from evaluation.phase56_stage7.evaluator_adapter import (  # noqa: E402
    assert_gold_domain_has_no_execution_authority,
)
from evaluation.phase56_stage7.isolation import (  # noqa: E402
    assert_production_runtime_isolated,
    assert_public_fixtures_excluded_from_production_image,
    assert_runtime_domain_does_not_import_gold,
)
from evaluation.phase56_stage7.network_guard import (  # noqa: E402
    assert_offline_environment,
    block_external_network,
)
from evaluation.phase56_stage7.preflight import (  # noqa: E402
    PreflightTerminal,
    run_contract_preflight,
)
from evaluation.phase56_stage7.redaction import (  # noqa: E402
    assert_privacy_safe_artifact,
)

OFFLINE_GATE_SCHEMA = "dynatutor.phase56_stage7.offline_gate"
OFFLINE_GATE_VERSION = "1.0"
PUBLIC_CORPUS_PATH_ENV = "STAGE7_PUBLIC_CORPUS_PATH"


@dataclass(frozen=True, slots=True)
class GateOutcome:
    name: str
    result: str
    detail: str | None = None

    @property
    def passed(self) -> bool:
        return self.result == "PASS"


def _run_gate(name: str, action) -> GateOutcome:
    try:
        action()
    except Exception as exc:  # only the exception type reaches the artifact
        return GateOutcome(name=name, result="FAIL", detail=type(exc).__name__)
    return GateOutcome(name=name, result="PASS")


def _exact_head_sha() -> str:
    env_sha = os.environ.get("GITHUB_SHA", "")
    if len(env_sha) == 40 and all(c in "0123456789abcdef" for c in env_sha.casefold()):
        return env_sha.casefold()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "0" * 40
    return completed.stdout.strip().casefold()


def _structural_gates() -> list[GateOutcome]:
    return [
        _run_gate(
            "runtime_domain_does_not_import_gold",
            lambda: assert_runtime_domain_does_not_import_gold(REPOSITORY_ROOT),
        ),
        _run_gate(
            "production_runtime_isolated_from_evaluator",
            lambda: assert_production_runtime_isolated(REPOSITORY_ROOT),
        ),
        _run_gate(
            "public_fixtures_excluded_from_production_image",
            lambda: assert_public_fixtures_excluded_from_production_image(
                REPOSITORY_ROOT
            ),
        ),
        _run_gate(
            "gold_domain_has_no_execution_authority",
            lambda: assert_gold_domain_has_no_execution_authority(REPOSITORY_ROOT),
        ),
        _run_gate(
            "corpus_modules_are_execution_free",
            lambda: assert_corpus_modules_are_execution_free(REPOSITORY_ROOT),
        ),
        _run_gate(
            "raw_corpus_is_not_committed",
            lambda: assert_raw_corpus_is_not_committed(REPOSITORY_ROOT),
        ),
    ]


def _contract_preflight_gate() -> GateOutcome:
    result = run_contract_preflight(REPOSITORY_ROOT)
    if result.terminal is not PreflightTerminal.passed:
        return GateOutcome(
            name="stage7_contract_preflight",
            result="FAIL",
            detail=result.sanitized_reason,
        )
    if not result.ledger.zero_execution:
        return GateOutcome(
            name="stage7_contract_preflight",
            result="FAIL",
            detail="non_zero_execution_ledger",
        )
    return GateOutcome(name="stage7_contract_preflight", result="PASS")


def _corpus_section(archive_path: Path | None) -> tuple[dict[str, Any], GateOutcome]:
    if archive_path is None:
        return (
            {
                "supplied": False,
                "disposition": "NOT_RUN",
                "reason": "authorised_public_archive_not_supplied_to_this_runner",
                "public_dev": "NOT_RUN",
                "public_adversarial": "NOT_RUN",
                "public_total": "NOT_RUN",
            },
            GateOutcome(
                name="public_corpus_integrity", result="NOT_RUN", detail="not_supplied"
            ),
        )

    result = run_corpus_integrity_preflight(archive_path)
    if result.terminal is not PreflightTerminal.passed:
        return (
            {
                "supplied": True,
                "disposition": "HARNESS_CONTRACT_FAILURE",
                "reason": result.sanitized_reason,
                "runtime_calls": result.ledger.runtime_calls,
                "compiler_calls": result.ledger.compiler_calls,
                "solver_calls": result.ledger.solver_calls,
                "model_or_provider_calls": result.ledger.model_or_provider_calls,
                "measured_cost_usd": result.ledger.measured_cost_usd,
            },
            GateOutcome(
                name="public_corpus_integrity",
                result="FAIL",
                detail=result.sanitized_reason,
            ),
        )

    evidence = result.semantic_evidence
    assert evidence is not None
    return (
        {
            "supplied": True,
            "disposition": "PASS",
            "archive_sha256": result.archive_sha256,
            "public_dev": evidence.public_dev_count,
            "public_adversarial": evidence.public_adversarial_count,
            "public_total": evidence.public_dev_count
            + evidence.public_adversarial_count,
            "scope_adjusted_distribution": {
                "supported_accepted": evidence.distribution.supported_accepted,
                "deferred_unsupported": evidence.distribution.deferred_unsupported,
                "unsupported_other": evidence.distribution.unsupported_other,
                "needs_figure": evidence.distribution.needs_figure,
                "needs_confirmation": evidence.distribution.needs_confirmation,
                "insufficient_information": (
                    evidence.distribution.insufficient_information
                ),
            },
            "entry_sha256": {
                entry.name: entry.sha256 for entry in result.entry_evidence
            },
        },
        GateOutcome(name="public_corpus_integrity", result="PASS"),
    )


def _resolve_archive_path() -> Path | None:
    raw = os.environ.get(PUBLIC_CORPUS_PATH_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def build_report() -> tuple[dict[str, Any], bool]:
    contract = stage7_evaluation_contract()
    offline_evidence = assert_offline_environment()

    gates: list[GateOutcome] = []
    corpus_section: dict[str, Any]
    with block_external_network():
        gates.extend(_structural_gates())
        gates.append(_contract_preflight_gate())
        corpus_section, corpus_gate = _corpus_section(_resolve_archive_path())
        gates.append(corpus_gate)

    report: dict[str, Any] = {
        "schema": OFFLINE_GATE_SCHEMA,
        "version": OFFLINE_GATE_VERSION,
        "evaluator_version": STAGE7_EVALUATOR_VERSION,
        "contract_version": STAGE7_CONTRACT_VERSION,
        "exact_head_sha": _exact_head_sha(),
        "expected_corpus_zip_sha256": contract.corpus.expected_zip_sha256,
        "offline_environment": {
            "openai_key_empty": offline_evidence.openai_key_empty,
            "anthropic_key_empty": offline_evidence.anthropic_key_empty,
            "provider_base_urls_absent": offline_evidence.provider_base_urls_absent,
        },
        "public_corpus": corpus_section,
        "gates": [
            {"name": gate.name, "result": gate.result, "detail": gate.detail}
            for gate in gates
        ],
        "external_model_calls": 0,
        "private_heldout_accesses": 0,
        "measured_cost_usd": 0.0,
        "actual_model_quality": contract.actual_model_quality_disposition,
    }
    assert_privacy_safe_artifact(report)
    passed = all(gate.result in ("PASS", "NOT_RUN") for gate in gates)
    return report, passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "stage7_offline_gate_report.json",
        help="destination for the redacted aggregate artifact",
    )
    args = parser.parse_args()

    report, passed = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"gates": report["gates"]}, ensure_ascii=False, indent=2))
    print(f"STAGE7_OFFLINE_GATE={'PASS' if passed else 'FAIL'}")
    print(f"STAGE7_PUBLIC_CORPUS={report['public_corpus']['disposition']}")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
