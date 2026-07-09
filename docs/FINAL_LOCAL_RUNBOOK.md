# Final Local Runbook

## Backend only

```bash
cd backend
pytest -q
PYTHONPATH=. python tools/run_phase20_benchmark_audit.py
PYTHONPATH=. python tools/chrono_validation/run_all_validations.py --strict
PYTHONPATH=. python tools/run_release_candidate_audit.py
PYTHONPATH=. python tools/run_phase24_deployment_audit.py
```

## Frontend build

```bash
cd frontend
npm ci
npm run build
```

## Full check script

Mac/Linux:

```bash
./scripts/final_local_check.sh
```

Windows:

```bat
scripts\final_local_check_windows.bat
```

## Local app run

Backend:

```bash
./scripts/run_backend.sh
```

Frontend:

```bash
./scripts/run_frontend.sh
```

Combined local helper:

```bash
./scripts/run_local.sh
```

## iPhone LAN mode

Mac/Linux:

```bash
./scripts/run_iphone_lan.sh
```

Windows:

```bat
scripts\run_iphone_lan_windows.bat
```

Open the shown LAN URL in iPhone Safari.

## Phone-only remote mode

Use cloud backend + cloud frontend.

Backend env:

```text
DYNATUTOR_ACCESS_TOKEN
DYNATUTOR_CORS_ORIGINS
DYNATUTOR_DB
```

Frontend env:

```text
NEXT_PUBLIC_DYNATUTOR_API_BASE
```

## Expected final audit

```text
backend tests: pass
benchmark audit: pass
Chrono analytic validation: pass
release candidate audit: pass
deployment audit: pass
frontend build: pass locally after npm ci, skipped in this container if node_modules missing
```
