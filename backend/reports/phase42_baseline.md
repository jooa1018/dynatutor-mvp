# Phase 42 Baseline Report

Source main commit: `174e7ec0f724f584628fd85a719af9b5fd2a54b3`  
Measurement date: 2026-07-10  
Fresh runner: GitHub Actions `ubuntu-latest`, Linux 6.17 Azure x86_64, CPython 3.13.14

## Scope

This report freezes the pre-refactor dynamics capability, independent golden cases, API/schema contract, accuracy artifacts, and execution baseline. Phase 42 does not change parser, routing scores, solver algorithms, equation/root selection, or verification behavior.

## Current dynamics support

- `SolverRegistry` contains 29 deterministic analytic solver entries.
- The machine-readable inventory is `backend/engine/capabilities/dynamics_capabilities.json`.
- The independent Phase 42 set contains 43 cases across 16 dynamics domains.
- The set covers constant acceleration, projectile motion, inclines, friction, three pulley families, collision, work-energy, impulse-momentum, rolling, fixed-axis rotation, plane rigid-body motion, polar/rotating-frame motion, and 1-DOF vibration.
- 42 cases currently solve; the fixed-axis tangential-speed case computes the independent value but returns an evidence-confirm clarification because requested `v_t` and answer symbol `v` disagree in verification.
- There is no independent SciPy trajectory path, executable PyChrono numeric scene, or Rapier2D dynamic visualization.

## Versioned pre-existing metrics

These values come from `backend/reports/routing_confusion/report.json`; they are retained as a historical artifact, not presented as a fresh Phase 42 rerun.

| Metric | Recorded value |
|---|---:|
| Routing | 432/432 correct |
| Route confusion | 0 |
| Numeric gold | 127/127 |
| Negative refusal | 60/60 |
| False-solve rate on the labeled negative set | 0/60 (0%) |
| Clarification crafted firing / correct rule | 14/14 / 14/14 |
| Clarification resolvable cases resolved | 10/10 |
| Verification false positives | 0/243 |
| Residual coverage in that report | 243/243 |
| Report duration | 34.13 s |
| Units backend | shim |

The clarification precision/recall values are 1.0 only on the curated evaluated sets. They are not production estimates.

## Fresh command results

Commands were run in the requested order before the additional diagnostic baselines.

| Check | Result | Pytest/runtime duration |
|---|---:|---:|
| Phase 42 contracts | 137 passed | 2.72 s |
| Backend fast | 410 passed, 40 deselected | 8.77 s |
| Requested backend command | 410 passed, 40 deselected | 7.97 s |
| Frontend metadata | passed | <1 s |
| Unfiltered backend diagnostic | 439 passed, 11 failed | 16.59 s |
| Korean benchmarks | 3 passed, 1 failed | 4.30 s |
| Existing routing selector | 7 passed, 306 deselected | 1.60 s |
| Existing clarification/unsupported selector | 9 passed, 304 deselected | 1.66 s |

The requested `python -m pytest backend/tests -q` command inherits `backend/pytest.ini` and excludes benchmark, audit, frontend, and slow markers. The separate unfiltered command therefore uses `-o addopts=`.

### Fresh Korean benchmark accuracy

- Phase 10 Korean quality: 99/100 cases (99%). One spring-mass frequency case routes correctly and computes `f = 0.796 Hz`, but the response is not accepted as `ok`.
- Phase 25 blind textbook: 100/100 cases (100%).
- Combined: 199/200 cases (99.5%).
- The 492 Phase 20 cases remain derived-style regression artifacts and are not treated as independent Phase 42 oracles.

## Solve latency and optional-dependency-free result

The reusable command is:

```bash
PYTHONPATH=backend python backend/scripts/measure_phase42_latency.py --repeats 5 --warmups 1 --block-optional-dependencies
```

It ran every one of the 43 golden prompts five times after one warm-up pass (215 measured samples). Imports of `chrono`, `pychrono`, `pydy`, and `scipy` were blocked before engine import.

| Metric | Result |
|---|---:|
| Mean | 9.458354 ms |
| P95 (nearest-rank) | 32.092011 ms |
| Minimum | 1.584351 ms |
| Maximum | 42.788948 ms |
| Response statuses | 210 solved, 5 clarification |
| Command wall time | 4 s |

This is a laboratory baseline on GitHub Actions, not production or Windows latency. The lock install contains SciPy/PyDy, so the measurement simulates their absence with an import gate rather than claiming the packages were uninstalled. PyChrono was not installed and no external numeric scene ran.

## Golden oracle policy

Each case separates:

- original Korean prompt;
- expected canonical facts;
- expected route;
- expected requested outputs;
- independent numeric/formula oracle;
- tolerance;
- expected response status;
- formula or hand calculation.

Expected numbers come from explicit mechanics laws and hand calculations, not by copying the engine output. The fixed-axis clarification keeps the independent `v=omega r=2 m/s` oracle while honestly recording that the current student API withholds the answer.

## API contract

The following are frozen without runtime changes:

- `CanonicalProblem`
- `SolverResult`
- `VerificationReport`
- `ProblemRequest`, `CanonicalProblemModel`, and `SolveResponse`
- solved, clarification, and unsupported `/solve` response shapes

Contract fixture: `backend/tests/contracts/phase42_api_schema_contract.json`.

## Known existing failures

The unfiltered run has 11 failures, none introduced by Phase 42:

1. One Phase 10 Korean spring-frequency response/verification failure.
2. Six benchmark tests resolve `tests/benchmarks/...` relative to the backend working directory and fail from repository root.
3. Four deployment/frontend checks fail because `frontend/.env.example` and `frontend/.nvmrc` are absent, including the aggregate Phase 24 audit.

Additional repository issues retained for later phases:

- Goal files are at repository root rather than `goal/`.
- The goal upload replaced the prior project README.
- The requested “full” pytest command is marker-filtered.
- Fixed-axis tangential speed is computed but clarification is returned due to the `v_t`/`v` verification mismatch.
- PyChrono hooks do not execute scenes; importable Chrono remains a manual-required path.
- The shared Windows host denied process creation, so fresh evidence was collected on the branch runner.

The missing root `.gitignore` is the only repository hygiene issue fixed in Phase 42.

## Not currently measurable

Production false-solve rate, production clarification precision/recall, production/Windows latency, and real PyChrono cross-engine agreement cannot be measured from the current labeled assets and environment. No values are invented for them.

## Rollback

Revert the Phase 42 commits (or the eventual squash commit). The phase adds contracts, reports, tests, a read-only measurement script, and a root `.gitignore`; it does not migrate runtime schemas or alter solver behavior.
