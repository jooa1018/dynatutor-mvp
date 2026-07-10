# Phase 42 Baseline Report

Source commit: `174e7ec0f724f584628fd85a719af9b5fd2a54b3`  
Measurement date: 2026-07-10

## Scope

This report freezes the pre-refactor dynamics capability, curated accuracy artifacts, API/schema contract, and test commands. It does not change parser, routing, solver, equation selection, or verification behavior.

## Current support

- `SolverRegistry` contains 29 analytic solver entries.
- The machine-readable inventory is `backend/engine/capabilities/dynamics_capabilities.json`.
- The independent Phase 42 set contains 43 cases across 16 dynamics domains.
- All student answers remain on the existing deterministic analytic path.
- There is no SciPy trajectory path, executable PyChrono scene, or Rapier2D dynamic visualization.

## Versioned pre-existing metrics

These values come from `backend/reports/routing_confusion/report.json`, not from a fresh Phase 42 run.

| Metric | Recorded value |
|---|---:|
| Routing | 432/432 correct |
| Route confusion | 0 |
| Numeric gold | 127/127 |
| Negative refusal | 60/60 |
| False-solve rate on the labeled negative set | 0/60 (0%) |
| Clarification crafted firing | 14/14 |
| Clarification resolvable cases resolved | 10/10 |
| Verification false positives | 0/243 |
| Residual coverage in that report | 243/243 |
| Report duration | 34.13 s |
| Units backend | shim |

The 100 blind-textbook and 492 Phase 20 cases are derived-style regression sets. They are useful baselines but are not treated as independent Phase 42 oracles.

## Fresh command results

Initially not run: the current Codex Windows host rejects process creation before a command starts. Exact results will be updated from the isolated branch runner before the PR is opened.

| Check | Command | Status |
|---|---|---|
| Phase 42 | `python -m pytest backend/tests/test_phase42_baseline_contracts.py -q -o addopts=''` | not run |
| Backend fast | `bash scripts/check_backend_fast.sh` | not run |
| Requested backend command | `python -m pytest backend/tests -q` | not run |
| Truly unfiltered backend | `python -m pytest backend/tests -q -o addopts=''` | not run |
| Frontend metadata | `bash scripts/check_frontend_metadata.sh` | not run |

Important: the requested backend command inherits `backend/pytest.ini` and excludes benchmark, audit, frontend, and slow markers. The unfiltered command is therefore recorded separately.

## API contract

The following are frozen without runtime changes:

- `CanonicalProblem`
- `SolverResult`
- `VerificationReport`
- `ProblemRequest`, `CanonicalProblemModel`, and `SolveResponse`
- solved, clarification, and unsupported `/solve` response shapes

Contract fixture: `backend/tests/contracts/phase42_api_schema_contract.json`.

## Known existing issues

1. The root `.gitignore` is absent.
2. Goal files were uploaded at repository root instead of `goal/`.
3. The same upload replaced the project README with the goal roadmap.
4. The command described as “full” is marker-filtered by pytest configuration.
5. PyChrono hooks do not execute scenes; importable Chrono still returns `manual_required`.
6. Requested-output coverage is incomplete for some existing solver outputs such as impulse, vibration period/frequency, instantaneous-center speed, and curve design speed.

Only item 1 is corrected in Phase 42 because it is a minimal repository hygiene prerequisite. The others are documented and deferred.

## Rollback

Revert the Phase 42 commit. The change adds contracts, reports, tests, and a root `.gitignore`; it does not migrate runtime schemas or alter solver behavior.
