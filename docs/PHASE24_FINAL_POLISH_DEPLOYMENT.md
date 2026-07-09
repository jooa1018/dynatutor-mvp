# Phase 24 Final Polish / Deployment Verification

Phase 24 is the final personal-use polish stage.

## Goal

Phase 24 does not add a new physics solver. It verifies and documents how to
actually run and deploy the app after the Phase 23 release candidate.

## Added / updated files

```text
backend/tools/run_phase24_deployment_audit.py
backend/tests/test_phase24_final_polish_deployment.py
scripts/check_frontend_build.sh
scripts/check_frontend_build_windows.bat
scripts/final_local_check.sh
scripts/final_local_check_windows.bat
docs/PHASE24_FINAL_POLISH_DEPLOYMENT.md
docs/DEPLOYMENT_GUIDE_PERSONAL.md
docs/FINAL_LOCAL_RUNBOOK.md
release_manifest_phase24.json
```

## Small code polish

`frontend/lib/api.ts` now supports both env names:

```text
NEXT_PUBLIC_DYNATUTOR_API_BASE
NEXT_PUBLIC_API_BASE
```

The preferred env name is:

```text
NEXT_PUBLIC_DYNATUTOR_API_BASE
```

`frontend/.env.example` documents both.

## Warning polish

Several LaTeX-like StepCard strings were changed to raw strings to reduce Python
invalid-escape warnings.

## Deployment audit

Run:

```bash
cd backend
PYTHONPATH=. python tools/run_phase24_deployment_audit.py
```

With frontend build check attempt:

```bash
PYTHONPATH=. python tools/run_phase24_deployment_audit.py --attempt-frontend-build
```

If `frontend/node_modules` is missing, the frontend build check exits with code
2 and the audit reports this as a dependency skip, not a compiled build pass.

## Final local check

Mac/Linux:

```bash
./scripts/final_local_check.sh
```

Windows:

```bat
scripts\final_local_check_windows.bat
```

This runs:

```text
backend pytest
benchmark audit
Chrono analytic validation harness
release candidate audit
frontend build check
```

## Final build status in this container

The backend test suite was run and passed:

```text
150 passed
```

The frontend build was not fully run because `frontend/node_modules` was not
available in the container. This is recorded honestly.

Before real deployment, run:

```bash
cd frontend
npm install
npm run build
```

## Final meaning

For the stated goal—personal Dynamics tutor app—Phase 24 is the first complete
stopping point.

It is suitable for:

```text
personal study
local use
private phone-only remote deployment
iPhone Safari / PWA use
```

It is not a public/commercial release package.
