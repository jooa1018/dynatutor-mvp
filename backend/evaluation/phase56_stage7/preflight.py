from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, NoReturn

from evaluation.phase56_stage7.contracts import (
    Stage7EvaluationContractV1,
    Stage7FailureKind,
    stage7_evaluation_contract,
)
from evaluation.phase56_stage7.isolation import (
    assert_production_runtime_isolated,
    assert_public_fixtures_excluded_from_production_image,
    assert_runtime_domain_does_not_import_gold,
)


class PreflightTerminal(str, Enum):
    passed = "passed"
    harness_contract_failure = "HARNESS_CONTRACT_FAILURE"


@dataclass(frozen=True, slots=True)
class PreflightCallLedger:
    runtime_calls: int = 0
    compiler_calls: int = 0
    solver_calls: int = 0
    model_or_provider_calls: int = 0
    measured_cost_usd: float = 0.0

    @property
    def zero_execution(self) -> bool:
        return (
            self.runtime_calls == 0
            and self.compiler_calls == 0
            and self.solver_calls == 0
            and self.model_or_provider_calls == 0
            and self.measured_cost_usd == 0.0
        )


@dataclass(frozen=True, slots=True)
class Stage7PreflightResult:
    terminal: PreflightTerminal
    contract: Stage7EvaluationContractV1
    ledger: PreflightCallLedger
    failure_kind: Stage7FailureKind | None = None
    sanitized_reason: str | None = None


def fail_preflight(reason: str) -> Stage7PreflightResult:
    bounded = " ".join(reason.split())[:160] or "preflight failure"
    return Stage7PreflightResult(
        terminal=PreflightTerminal.harness_contract_failure,
        contract=stage7_evaluation_contract(),
        ledger=PreflightCallLedger(),
        failure_kind=Stage7FailureKind.harness_failure,
        sanitized_reason=bounded,
    )


def run_contract_preflight(repository_root: Path) -> Stage7PreflightResult:
    contract = stage7_evaluation_contract()
    ledger = PreflightCallLedger()
    try:
        assert_runtime_domain_does_not_import_gold(repository_root)
        assert_production_runtime_isolated(repository_root)
        assert_public_fixtures_excluded_from_production_image(repository_root)
    except (OSError, SyntaxError, ValueError) as exc:
        return fail_preflight(type(exc).__name__)
    return Stage7PreflightResult(
        terminal=PreflightTerminal.passed,
        contract=contract,
        ledger=ledger,
    )
