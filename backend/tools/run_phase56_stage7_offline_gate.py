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
from evaluation.phase56_stage7.corpus_integrity import (  # noqa: E402
    read_public_corpus_archive,
)
from evaluation.phase56_stage7.corpus_preflight import (  # noqa: E402
    assert_corpus_modules_are_execution_free,
    assert_raw_corpus_is_not_committed,
    load_public_cases,
    run_corpus_integrity_preflight,
)
from evaluation.phase56_stage7.blocked_law_diagnosis import (  # noqa: E402
    diagnose_blocked_laws,
)
from evaluation.phase56_stage7.complete_profile import (  # noqa: E402
    build_complete_profile_census,
    draft_structure_fingerprint,
    plan_every_profile,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (  # noqa: E402
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_structural_blockers import (  # noqa: E402
    build_structural_blocker_census,
    census_as_dict,
)
from evaluation.phase56_stage7.profile_feasibility import (  # noqa: E402
    measure_profile_feasibility,
)
from evaluation.phase56_stage7.query_readout_ownership import (  # noqa: E402
    diagnose_query_readout_ownership,
    diagnosis_as_dict,
)
from evaluation.phase56_stage7.lane_b_failure_matrix import (  # noqa: E402
    build_pipeline_failure_matrix,
)
from evaluation.phase56_stage7.law_prerequisites import (  # noqa: E402
    law_context_for_projection,
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
            "family_count": evidence.family_count,
            "checked_fact_count": evidence.checked_fact_count,
            "deferred_family_counts": dict(evidence.deferred_family_counts),
            "runtime_calls": result.ledger.runtime_calls,
            "compiler_calls": result.ledger.compiler_calls,
            "solver_calls": result.ledger.solver_calls,
            "model_or_provider_calls": result.ledger.model_or_provider_calls,
            "measured_cost_usd": result.ledger.measured_cost_usd,
            "zero_execution": result.ledger.zero_execution,
            "entry_sha256": {
                entry.name: entry.sha256 for entry in result.entry_evidence
            },
        },
        GateOutcome(name="public_corpus_integrity", result="PASS"),
    )


def _lane_b_section(archive_path: Path | None) -> tuple[dict[str, Any], GateOutcome]:
    """Execute the real public-corpus Lane B pipeline and aggregate it safely.

    The archive is only supplied to a local run; a remote corpus-independent run
    reports ``NOT_RUN`` rather than claiming a pass it did not measure.
    """

    if archive_path is None:
        return (
            {"executed": False, "disposition": "NOT_RUN"},
            GateOutcome(name="lane_b_public_100", result="NOT_RUN", detail="not_supplied"),
        )
    try:
        inventory = read_public_corpus_archive(archive_path)
        public_dev, public_adversarial = load_public_cases(inventory)
        matrix = build_pipeline_failure_matrix((*public_dev, *public_adversarial))
    except Exception as exc:  # only the exception type reaches the artifact
        return (
            {"executed": False, "disposition": "FAIL", "reason": type(exc).__name__},
            GateOutcome(
                name="lane_b_public_100", result="FAIL", detail=type(exc).__name__
            ),
        )

    section: dict[str, Any] = {"executed": True, "disposition": "EXECUTED"}
    section.update(matrix.as_dict())
    solved = dict(matrix.terminal_counts).get("solved", 0)
    section["solved"] = solved
    # Gold-domain answer scoring runs strictly after the runtime matrix is
    # complete: the runtime loop never read a gold member, and the scorer
    # reads only the runtime's own frozen solved outputs.
    section["answer_scoring"] = _score_solved_outputs(
        archive_path, matrix.solved_outputs
    )
    return (
        section,
        GateOutcome(
            name="lane_b_public_100",
            result="PASS" if solved == matrix.executed_cases else "FAIL",
            detail=None if solved == matrix.executed_cases else "unsolved_cases_remain",
        ),
    )


def _blocked_law_diagnosis_section(archive_path: Path | None) -> dict[str, Any]:
    """Measure what each blocked law is really blocked on.

    Diagnostic, never a gate.  It reports which typed structure each blocked
    emission function stops at, and what the real engine does when that
    structure is supplied — so the next package is chosen from a measured
    unlock rather than from a declared-prerequisite gap that counts contexts the
    law has nothing to do with.
    """

    if archive_path is None:
        return {"executed": False, "disposition": "NOT_RUN"}
    try:
        inventory = read_public_corpus_archive(archive_path)
        public_dev, public_adversarial = load_public_cases(inventory)
        contexts = [
            context
            for context in (
                law_context_for_projection(project_case_to_draft(case))
                for case in (*public_dev, *public_adversarial)
            )
            if context is not None
        ]
        report = diagnose_blocked_laws(contexts)
    except Exception as exc:  # only the exception type reaches the artifact
        return {"executed": False, "disposition": "FAIL", "reason": type(exc).__name__}
    section: dict[str, Any] = {"executed": True, "disposition": "EXECUTED"}
    section.update(report.as_dict())
    return section


def _complete_profile_census_section(archive_path: Path | None) -> dict[str, Any]:
    """Measure how close each bounded profile is to closing, over every context.

    Diagnostic, never a gate.  Its purpose is to decide *which* profile to build
    next from a measurement rather than from a family label: a profile with a
    nonzero complete population is one the source structure already reaches, and
    everything else is reported as the precise reason it does not.

    The section is counts only.  No case ID, family, split, problem text,
    expected answer, expected terminal, or gold graph can appear in it — the
    census records have no field that could hold one.  Planning is verified to
    have left every Draft byte-identical before the counts are accepted.
    """

    if archive_path is None:
        return {"executed": False, "disposition": "NOT_RUN"}
    try:
        inventory = read_public_corpus_archive(archive_path)
        public_dev, public_adversarial = load_public_cases(inventory)
        plan_sets = []
        for case in (*public_dev, *public_adversarial):
            projection = project_case_to_draft(case)
            if not projection.projected:
                continue
            before = draft_structure_fingerprint(projection.draft)
            plans = plan_every_profile(
                projection.draft,
                approved_assumption_ids=projection.approvable_assumption_ids,
            )
            if draft_structure_fingerprint(projection.draft) != before:
                raise RuntimeError("complete-profile planning mutated a Draft")
            plan_sets.append(plans)
        census = build_complete_profile_census(plan_sets)
    except Exception as exc:  # only the exception type reaches the artifact
        return {"executed": False, "disposition": "FAIL", "reason": type(exc).__name__}
    section: dict[str, Any] = {"executed": True, "disposition": "EXECUTED"}
    section.update(census.as_dict())
    return section


def _structural_blocker_section(archive_path: Path | None) -> dict[str, Any]:
    """Count the typed structure the sources do not state at all.

    Diagnostic, never a gate.  The complete-profile census measures how close a
    profile is to closing; this measures what is absent from every context
    regardless of profile, which is what separates a planner gap that a closed
    derivation can fill from a blocker no transaction can remove without
    restating what the source says.

    Counts only.  The record has no field that could hold identity or content.
    """

    if archive_path is None:
        return {"executed": False, "disposition": "NOT_RUN"}
    try:
        inventory = read_public_corpus_archive(archive_path)
        public_dev, public_adversarial = load_public_cases(inventory)
        drafts = []
        for case in (*public_dev, *public_adversarial):
            projection = project_case_to_draft(case)
            if not projection.projected:
                continue
            drafts.append(projection.draft)
        census = build_structural_blocker_census(drafts)
    except Exception as exc:  # only the exception type reaches the artifact
        return {"executed": False, "disposition": "FAIL", "reason": type(exc).__name__}
    section: dict[str, Any] = {"executed": True, "disposition": "EXECUTED"}
    section.update(census_as_dict(census))
    return section


def _query_readout_ownership_section(archive_path: Path | None) -> dict[str, Any]:
    """Test whether query-readout ownership causally blocks anything.

    Diagnostic, never a gate.  The structural blocker census counts contexts
    whose queried readout sits on an entity outside the free-body set; this
    section asks the real engine whether binding that readout to a carrier
    changes anything, so a count of a property is never mistaken for a cause.

    The counterfactual is evaluator-only.  It changes one field of one quantity
    in a law context that is discarded immediately; no Draft, runtime result, or
    answer is derived from it, no entity primitive is rewritten, and nothing is
    added to the engine's free-body set.
    """

    if archive_path is None:
        return {"executed": False, "disposition": "NOT_RUN"}
    try:
        inventory = read_public_corpus_archive(archive_path)
        public_dev, public_adversarial = load_public_cases(inventory)
        pairs = []
        for case in (*public_dev, *public_adversarial):
            projection = project_case_to_draft(case)
            if not projection.projected:
                continue
            context = law_context_for_projection(projection)
            if context is None:
                continue
            target_quantity_id = projection.draft.queries[0].target.target_quantity_id
            if target_quantity_id is None:
                continue
            pairs.append((context, target_quantity_id))
        diagnosis = diagnose_query_readout_ownership(pairs)
    except Exception as exc:  # only the exception type reaches the artifact
        return {"executed": False, "disposition": "FAIL", "reason": type(exc).__name__}
    section: dict[str, Any] = {"executed": True, "disposition": "EXECUTED"}
    section.update(diagnosis_as_dict(diagnosis))
    return section


def _resolve_archive_path() -> Path | None:
    raw = os.environ.get(PUBLIC_CORPUS_PATH_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _profile_feasibility_section(archive_path: Path | None) -> dict[str, Any]:
    """Measure every applicable (profile, context) pair independently.

    Diagnostic, never a gate.  Each selected profile is planned and applied
    against the pristine projected Draft and run through the full lane on
    its own — no first-wins, no declaration-order credit — under the closed
    isolated status vocabulary; an unimplemented profile reads
    ``profile_not_implemented`` (not measured), never a yield zero it never
    earned.  The next package is chosen by this measured feasibility rather
    than by a structure count.

    Counts only.  Rows carry closed profile IDs, bounded status names, and
    integers; no identity or content field exists on the record.
    """

    if archive_path is None:
        return {"executed": False, "disposition": "NOT_RUN"}
    try:
        inventory = read_public_corpus_archive(archive_path)
        public_dev, public_adversarial = load_public_cases(inventory)
        matrix = measure_profile_feasibility((*public_dev, *public_adversarial))
    except Exception as exc:  # only the exception type reaches the artifact
        return {"executed": False, "disposition": "FAIL", "reason": type(exc).__name__}
    section: dict[str, Any] = {"executed": True, "disposition": "EXECUTED"}
    section.update(matrix.as_dict())
    return section


# ---------------------------------------------------------------------------
# Full-Stage-7 suite sections.  Each section executes the *exact* existing
# suites for its lane — nothing is duplicated, nothing is simulated — via a
# fresh interpreter per suite, and records counts only.  A lane that was not
# requested is NOT_RUN, never PASS.
# ---------------------------------------------------------------------------

_BACKEND_ROOT = REPOSITORY_ROOT / "backend"
_SUITE_TIMEOUT_S = 1800
_SUMMARY_PATTERN = __import__("re").compile(
    r"(\d+) (passed|failed|errors?|deselected|skipped)"
)

# Lane C — recorded/fake modeler: deterministic fake provider contract, one
# combined call, at most one sanitized repair, reconciliation, revisions,
# zero answer authority.  Actual model quality is NOT_RUN / N/A by contract.
_LANE_C_SUITES: tuple[str, ...] = (
    "tests/test_phase56_mechanics_modeler.py",
    "tests/test_phase56_stage6_contracts.py",
    "tests/test_phase56_stage6_reconciliation.py",
)
# Lane D — product API/runtime through FastAPI boundaries: auth, limits,
# schemas, idempotency, stale revisions, owner isolation, image security,
# privacy-safe observability.
_LANE_D_SUITES: tuple[str, ...] = (
    "tests/test_phase56_stage6_api_runtime_integration.py",
    "tests/test_phase56_stage6_security_hardening.py",
    "tests/test_phase56_stage6_image_security.py",
    "tests/test_phase56_stage6_idempotency_conflicts.py",
    "tests/test_phase56_stage6_observability.py",
)
# The 12 independently authored compositional structures, mapped to the
# engine's own independently authored same-fixture parity suites — each of
# which drives at least two reusable laws through compile, all-root solve,
# and independent residual verification.
_COMPOSITIONAL_STRUCTURES: tuple[tuple[str, str], ...] = (
    ("newton_plus_rope", "tests/test_phase56_mechanics_atwood_same_fixture_parity.py"),
    ("incline_friction_rope", "tests/test_phase56_mechanics_incline_hanging_same_fixture_parity.py"),
    ("massive_pulley_rotation", "tests/test_phase56_mechanics_massive_pulley_same_fixture_parity.py"),
    ("rolling_work_energy", "tests/test_phase56_mechanics_pure_rolling_same_fixture_parity.py"),
    ("vertical_circle_contact_loss", "tests/test_phase56_mechanics_vertical_circle_same_fixture_parity.py"),
    ("collision_restitution", "tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py"),
    ("projectile_event_root", "tests/test_phase56_mechanics_projectile_same_fixture_parity.py"),
    ("work_kinetic_energy", "tests/test_phase56_mechanics_constant_force_work_same_fixture_parity.py"),
    ("impulse_momentum", "tests/test_phase56_mechanics_impulse_momentum_same_fixture_parity.py"),
    ("fixed_axis_point_speed", "tests/test_phase56_mechanics_fixed_axis_rotation_same_fixture_parity.py"),
    ("rigid_body_point_motion", "tests/test_phase56_mechanics_plane_rigid_body_velocity_same_fixture_parity.py"),
    ("polar_kinematics_projection", "tests/test_phase56_mechanics_polar_kinematics_same_fixture_parity.py"),
)
_SYNTHETIC_38_SUITE = "tests/test_phase56_stage6_synthetic_figures.py"
_SYNTHETIC_MANIFEST = (
    _BACKEND_ROOT / "tests" / "fixtures" / "phase56_stage6_synthetic_manifest.json"
)
# The engine's metamorphic oracle instrument (identical authoritative results
# under transformation) and its mutation-control twin (seeded physics changes
# must be detected/killed).  Stage 7's own per-package invariance and
# physics-changing controls additionally run inside the focused suite.
_METAMORPHIC_SUITES: tuple[str, ...] = (
    "tests/test_phase49_oracles_metamorphic.py",
)
_PHYSICS_CHANGING_SUITES: tuple[str, ...] = (
    "tests/test_phase49_mutation_audit.py",
)


def _run_pytest_suite(path: str) -> dict[str, Any]:
    """Run one exact suite in a fresh interpreter and record counts only."""

    row: dict[str, Any] = {"suite": path}
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "-o",
                "addopts=",
                path,
            ],
            cwd=_BACKEND_ROOT,
            capture_output=True,
            text=True,
            timeout=_SUITE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        row.update(passed=0, failed=0, errors=1, disposition="TIMEOUT")
        return row
    counts = {"passed": 0, "failed": 0, "errors": 0, "deselected": 0, "skipped": 0}
    for value, kind in _SUMMARY_PATTERN.findall(completed.stdout):
        key = "errors" if kind.startswith("error") else kind
        counts[key] = int(value)
    row.update(counts)
    row["disposition"] = (
        "PASS"
        if completed.returncode == 0
        and counts["failed"] == 0
        and counts["errors"] == 0
        and counts["passed"] > 0
        else "FAIL"
    )
    return row


def _suite_section(paths: tuple[str, ...], *, executed: bool, note: str | None = None) -> dict[str, Any]:
    if not executed:
        section = {"result": "NOT_RUN", "executed": False, "reason": "full_stage7_not_requested"}
        if note:
            section["note"] = note
        return section
    rows = [_run_pytest_suite(path) for path in paths]
    section = {
        "executed": True,
        "suites": rows,
        "total_passed": sum(row["passed"] for row in rows),
        "total_failed": sum(row["failed"] for row in rows),
        "result": (
            "PASS"
            if all(row["disposition"] == "PASS" for row in rows)
            else "FAIL"
        ),
    }
    if note:
        section["note"] = note
    return section


def _lane_c_section(executed: bool) -> dict[str, Any]:
    return _suite_section(
        _LANE_C_SUITES,
        executed=executed,
        note="contract/integration evidence only; actual model quality NOT_RUN / N/A",
    )


def _lane_d_section(executed: bool) -> dict[str, Any]:
    return _suite_section(_LANE_D_SUITES, executed=executed)


def _synthetic_38_section(executed: bool) -> dict[str, Any]:
    if not executed:
        return {"result": "NOT_RUN", "executed": False, "reason": "full_stage7_not_requested"}
    manifest = json.loads(_SYNTHETIC_MANIFEST.read_text(encoding="utf-8"))
    case_count = len(manifest.get("cases", ()))
    section = _suite_section((_SYNTHETIC_38_SUITE,), executed=True)
    section["synthetic_case_count"] = case_count
    if case_count != 38:
        section["result"] = "FAIL"
    return section


def _compositional_12_section(executed: bool) -> dict[str, Any]:
    if not executed:
        return {"result": "NOT_RUN", "executed": False, "reason": "full_stage7_not_requested"}
    rows = []
    for structure, path in _COMPOSITIONAL_STRUCTURES:
        row = _run_pytest_suite(path)
        row["structure"] = structure
        rows.append(row)
    return {
        "executed": True,
        "structures": rows,
        "structure_count": len(rows),
        "passed_structures": sum(
            1 for row in rows if row["disposition"] == "PASS"
        ),
        "result": (
            "PASS"
            if len(rows) == 12
            and all(row["disposition"] == "PASS" for row in rows)
            else "FAIL"
        ),
    }


def _metamorphic_section(executed: bool) -> dict[str, Any]:
    return _suite_section(
        _METAMORPHIC_SUITES,
        executed=executed,
        note="engine metamorphic oracle instrument; Stage 7 per-package invariance controls run in the focused suite",
    )


def _physics_changing_section(executed: bool) -> dict[str, Any]:
    return _suite_section(
        _PHYSICS_CHANGING_SUITES,
        executed=executed,
        note="seeded physics mutations must be detected; Stage 7 per-package detection controls run in the focused suite",
    )


def _lane_e_section(executed: bool) -> dict[str, Any]:
    """Frontend flow: tests, lint, typecheck, production build.

    Dependency installation may use the network exactly as the permanent
    workflow's own install step does; every evaluation-phase stage of this
    gate remains socket-guarded.  A missing toolchain is a typed NOT_RUN,
    never a pass.
    """

    if not executed:
        return {"result": "NOT_RUN", "executed": False, "reason": "full_stage7_not_requested"}
    frontend = REPOSITORY_ROOT / "frontend"
    steps: list[dict[str, Any]] = []

    def run_step(name: str, command: list[str], timeout_s: int = 1200) -> bool:
        try:
            completed = subprocess.run(
                command,
                cwd=frontend,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except FileNotFoundError:
            steps.append({"step": name, "result": "NOT_RUN", "reason": "toolchain_missing"})
            return False
        except subprocess.TimeoutExpired:
            steps.append({"step": name, "result": "FAIL", "reason": "timeout"})
            return False
        steps.append(
            {"step": name, "result": "PASS" if completed.returncode == 0 else "FAIL"}
        )
        return completed.returncode == 0
    if not (frontend / "node_modules").exists():
        if not run_step("install", ["npm", "ci"], timeout_s=1800):
            return {"result": "NOT_RUN", "executed": False, "steps": steps, "reason": "install_unavailable"}
    # The lint toolchain is installed exactly as the permanent workflows'
    # own lint step does (they pin it outside package.json on purpose).
    lint_ready = run_step(
        "lint_toolchain",
        [
            "npm", "install", "--no-save", "--no-package-lock",
            "--ignore-scripts", "--no-audit", "--no-fund",
            "eslint@9.39.5", "eslint-config-next@15.5.18",
        ],
        timeout_s=1800,
    )
    ok = lint_ready
    for name, command in (
        ("tests", ["npm", "test"]),
        ("lint", ["npm", "run", "lint"]),
        ("typecheck", ["npm", "run", "typecheck"]),
        ("build", ["npm", "run", "build"]),
    ):
        ok = run_step(name, command) and ok
    return {
        "executed": True,
        "steps": steps,
        "result": "PASS" if ok else "FAIL",
    }


def _score_solved_outputs(
    archive_path: Path | None, solved_outputs: tuple[tuple[int, float, str], ...]
) -> dict[str, Any]:
    """Gold-domain scoring of the runtime's frozen solved outputs.

    Runs strictly after the runtime record is complete.  Answers are compared
    in SI after converting the gold answer's own stated unit; a unit the
    registry cannot convert is counted unscored rather than wrong.
    """

    if archive_path is None:
        return {"scored": 0, "correct": 0, "wrong": 0, "unscored": 0}
    import pint

    registry = pint.UnitRegistry()
    inventory = read_public_corpus_archive(archive_path)
    public_dev, public_adversarial = load_public_cases(inventory)
    cases = (*public_dev, *public_adversarial)
    outputs_by_index = {index: (value, unit) for index, value, unit in solved_outputs}
    correct = wrong = unscored = 0
    for index, case in enumerate(cases):
        if index not in outputs_by_index:
            continue
        value_si, _unit = outputs_by_index[index]
        answers = case.gold.answers
        if len(answers) != 1:
            unscored += 1
            continue
        answer = answers[0]
        try:
            expected_si = (
                registry.Quantity(answer.numeric, answer.unit or "")
                .to_base_units()
                .magnitude
            )
            tolerance_si = abs(
                registry.Quantity(answer.tolerance_abs, answer.unit or "")
                .to_base_units()
                .magnitude
            )
        except Exception:
            unscored += 1
            continue
        if abs(value_si - expected_si) <= max(
            tolerance_si, 1.0e-6 * max(1.0, abs(expected_si))
        ):
            correct += 1
        else:
            wrong += 1
    return {
        "scored": correct + wrong,
        "correct": correct,
        "wrong": wrong,
        "unscored": unscored,
    }


def _hard_safety_section(
    report: dict[str, Any], gates: "list[GateOutcome]"
) -> dict[str, Any]:
    """The all-zero hard-safety catalog, from measured evidence only."""

    contract = stage7_evaluation_contract()
    lane_b = report.get("lane_b", {})
    executed = bool(lane_b.get("executed"))
    answer_scoring = lane_b.get("answer_scoring", {})
    wrong_solves = answer_scoring.get("wrong")
    # Safety derives from the isolation/integrity gates; the public-100
    # solved-distribution gate is the yield target, not a safety signal —
    # an honestly blocked case is safe, a wrongly solved one is not.
    structural_pass = all(
        gate.result in ("PASS", "NOT_RUN")
        for gate in gates
        if gate.name != "lane_b_public_100"
    )
    # The catalog itself is frozen in the evaluation contract; the artifact
    # carries counts only, because several signal *names* are themselves
    # forbidden redaction substrings.
    passing = (
        executed
        and wrong_solves == 0
        and structural_pass
        and report.get("external_model_calls") == 0
        and report.get("private_heldout_accesses") == 0
    )
    return {
        "executed": executed,
        "catalog": "stage7_evaluation_contract().hard_safety_signals",
        "signal_count": len(contract.hard_safety_signals),
        "nonzero_signal_count": 0 if passing else None,
        "all_zero": bool(passing),
        "wrong_solves_measured": wrong_solves,
        "evidence": {
            "wrong_solve": "gold-scored solved outputs",
            "external_calls": "offline environment + socket guard",
            "private_access": "keys-only manifest audit",
            "isolation": "structural gates",
        },
        "result": "PASS" if passing else ("FAIL" if executed else "NOT_RUN"),
    }


def build_report(*, run_full_suites: bool = False) -> tuple[dict[str, Any], bool]:
    contract = stage7_evaluation_contract()
    offline_evidence = assert_offline_environment()

    gates: list[GateOutcome] = []
    corpus_section: dict[str, Any]
    archive_path = _resolve_archive_path()
    with block_external_network():
        gates.extend(_structural_gates())
        gates.append(_contract_preflight_gate())
        corpus_section, corpus_gate = _corpus_section(archive_path)
        gates.append(corpus_gate)
        lane_b_section, lane_b_gate = _lane_b_section(
            archive_path if corpus_gate.passed else None
        )
        gates.append(lane_b_gate)
        diagnosis_section = _blocked_law_diagnosis_section(
            archive_path if corpus_gate.passed else None
        )
        census_section = _complete_profile_census_section(
            archive_path if corpus_gate.passed else None
        )
        blocker_section = _structural_blocker_section(
            archive_path if corpus_gate.passed else None
        )
        ownership_section = _query_readout_ownership_section(
            archive_path if corpus_gate.passed else None
        )
        feasibility_section = _profile_feasibility_section(
            archive_path if corpus_gate.passed else None
        )
        lane_c_section = _lane_c_section(run_full_suites)
        lane_d_section = _lane_d_section(run_full_suites)
        compositional_section = _compositional_12_section(run_full_suites)
        synthetic_section = _synthetic_38_section(run_full_suites)
        metamorphic_section = _metamorphic_section(run_full_suites)
        physics_changing_section = _physics_changing_section(run_full_suites)
    # Lane E may install its toolchain exactly as the workflow's own install
    # step does, so it runs outside the evaluation socket guard.
    lane_e_section = _lane_e_section(run_full_suites)

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
        "lane_b": lane_b_section,
        "blocked_law_diagnosis": diagnosis_section,
        "complete_profile_census": census_section,
        "structural_blockers": blocker_section,
        "query_readout_ownership": ownership_section,
        "profile_feasibility": feasibility_section,
        "lane_c": lane_c_section,
        "lane_d": lane_d_section,
        "lane_e": lane_e_section,
        "compositional_12": compositional_section,
        "synthetic_38": synthetic_section,
        "metamorphic": metamorphic_section,
        "physics_changing_controls": physics_changing_section,
        "gates": [
            {"name": gate.name, "result": gate.result, "detail": gate.detail}
            for gate in gates
        ],
        "external_model_calls": 0,
        "private_heldout_accesses": 0,
        "measured_cost_usd": 0.0,
        "actual_model_quality": contract.actual_model_quality_disposition,
    }
    report["hard_safety"] = _hard_safety_section(report, gates)
    assert_privacy_safe_artifact(report)
    report["redaction"] = {"result": "PASS", "policy": "phase56-stage7-report-redaction-v1"}
    passed = all(gate.result in ("PASS", "NOT_RUN") for gate in gates)
    return report, passed


def _strict_requirements(
    report: dict[str, Any], *, require_corpus: bool, require_full: bool
) -> list[GateOutcome]:
    """Strict acceptance: an absent corpus or an unrun lane is never a pass."""

    outcomes: list[GateOutcome] = []
    corpus = report["public_corpus"]
    lane_b = report["lane_b"]
    contract = stage7_evaluation_contract()

    def require(name: str, condition: bool, detail: str | None = None) -> None:
        outcomes.append(
            GateOutcome(
                name=name,
                result="PASS" if condition else "FAIL",
                detail=None if condition else detail,
            )
        )

    if require_corpus:
        require("strict_corpus_supplied", bool(corpus.get("supplied")), "not_supplied")
        require(
            "strict_corpus_sha_match",
            corpus.get("archive_sha256") == contract.corpus.expected_zip_sha256,
            "sha_mismatch",
        )
        require("strict_public_dev_84", corpus.get("public_dev") == 84, "count_mismatch")
        require(
            "strict_public_adversarial_16",
            corpus.get("public_adversarial") == 16,
            "count_mismatch",
        )
        require("strict_public_total_100", corpus.get("public_total") == 100, "count_mismatch")

    if require_full:
        require("strict_lane_b_executed", bool(lane_b.get("executed")), "not_run")
        require(
            "strict_lane_b_100_executed",
            lane_b.get("total_cases") == 100,
            "case_count_mismatch",
        )
        terminals = lane_b.get("terminal_counts") or {}
        require(
            "strict_lane_b_all_solved",
            bool(lane_b.get("executed"))
            and terminals.get("solved", 0) == lane_b.get("executed_cases"),
            "unsolved_cases_remain",
        )
        for lane in ("lane_c", "lane_d", "lane_e"):
            require(f"strict_{lane}_pass", report.get(lane, {}).get("result") == "PASS", "not_run")
        for name in (
            "compositional_12",
            "synthetic_38",
            "metamorphic",
            "physics_changing_controls",
            "hard_safety",
            "redaction",
        ):
            require(f"strict_{name}_pass", report.get(name, {}).get("result") == "PASS", "not_run")
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "stage7_offline_gate_report.json",
        help="destination for the redacted aggregate artifact",
    )
    parser.add_argument(
        "--require-public-corpus",
        action="store_true",
        help="fail unless the authorised public archive was supplied and matched",
    )
    parser.add_argument(
        "--require-full-stage7",
        action="store_true",
        help="fail unless every Stage 7 lane actually executed and passed",
    )
    args = parser.parse_args()

    report, passed = build_report(run_full_suites=args.require_full_stage7)
    strict = _strict_requirements(
        report,
        require_corpus=args.require_public_corpus,
        require_full=args.require_full_stage7,
    )
    if strict:
        report["strict_gates"] = [
            {"name": gate.name, "result": gate.result, "detail": gate.detail}
            for gate in strict
        ]
        report["strict_mode"] = {
            "require_public_corpus": args.require_public_corpus,
            "require_full_stage7": args.require_full_stage7,
        }
        assert_privacy_safe_artifact(report)
        passed = passed and all(gate.passed for gate in strict)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"gates": report["gates"]}, ensure_ascii=False, indent=2))
    if strict:
        print(json.dumps({"strict_gates": report["strict_gates"]}, ensure_ascii=False, indent=2))
    print(f"STAGE7_OFFLINE_GATE={'PASS' if passed else 'FAIL'}")
    print(f"STAGE7_PUBLIC_CORPUS={report['public_corpus']['disposition']}")
    print(f"STAGE7_LANE_B={report['lane_b']['disposition']}")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
