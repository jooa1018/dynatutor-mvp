# Phase 27 Stability

Phase 27 is not a new solver phase. It makes DynaTutor more reproducible and
less likely to hang in clean checkout / CI-style environments.

## Main goals

```text
- Split tests into fast / benchmark / audit / frontend metadata groups
- Keep frontend build out of pytest
- Make frontend build script terminate with success, failure, or timeout
- Kill npm/Next child processes on timeout
- Fix requested_outputs false-positive work detection
- Add answer consistency validator for answers[]
- Record real audit results honestly
```

## Pytest markers

Configured in:

```text
backend/pytest.ini
backend/tests/conftest.py
```

Markers:

```text
unit
regression
negative
benchmark
audit
frontend
slow
```

Default `pytest` behavior from `backend` now excludes:

```text
benchmark
audit
frontend
slow
```

Run fast tests:

```bash
cd backend
pytest -q
```

Equivalent script:

```bash
./scripts/check_backend_fast.sh
```

## Split validation scripts

Added/updated:

```text
scripts/check_backend_fast.sh
scripts/check_backend_benchmark.sh
scripts/check_backend_audit.sh
scripts/check_frontend_metadata.sh
scripts/check_frontend_build.py
scripts/check_frontend_build.sh
scripts/check_frontend_build_windows.bat
scripts/check_all.sh
```

`check_all.sh` intentionally does **not** run frontend build.

Use:

```bash
./scripts/check_all.sh
```

for:

```text
backend fast tests
benchmark tests + Phase20 benchmark audit
audit pytest
frontend metadata check
```

Run frontend build separately:

```bash
./scripts/check_frontend_build.sh
```

## Why frontend build is separate

`npm ci` and `next build` passed as an isolated job.

However, in this runtime, chaining frontend build after long backend pytest jobs
inside `check_all.sh --with-frontend-build` could leave the process attached
after build output. To avoid CI hangs, Phase 27 makes frontend build a separate
job.

This is the stable policy:

```text
pytest never runs frontend build
check_all.sh never runs frontend build
frontend build is its own isolated script/CI job
```

## Frontend build timeout

`check_frontend_build.sh` now uses:

```text
scripts/check_frontend_build.py
```

The Python wrapper uses:

```text
subprocess.Popen(..., start_new_session=True)
os.killpg(...)
```

Timeouts:

```text
npm ci: 120s
npm run build: 180s
SIGTERM, then SIGKILL after 10s
```

This prevents npm/Next child processes from surviving after timeout.

## requested_outputs work false-positive fix

Before Phase 27, `"일 때"` could be mistaken as `work`.

Fixed in:

```text
backend/engine/extraction/extractor.py
```

Positive work patterns include:

```text
한 일
일을 구하라
일은?
일의 크기
마찰력이 한 일
중력이 한 일
알짜일
총 일
work
W=
일 16J
```

Negative patterns include:

```text
일 때
1일
동일
일정
일반
일어나
일직선
일단
```

## answers[] consistency validator

Added:

```text
backend/engine/physics_core/answer_validators.py
```

It checks:

```text
ok=True has answer or answers
answer and answers[0] are consistent
primary answers have units
numeric answers roughly appear in display
requested_outputs are represented in answers
```

The service attaches validator warnings to the verification report instead of
silently ignoring inconsistencies.

## Actual verification

See:

```text
docs/PHASE27_AUDIT_SUMMARY.json
```

Observed results:

```text
backend fast: 148 passed, 35 deselected
backend benchmark: 10 pytest tests passed + Phase20 benchmark 492 total, 0 failures
backend audit: 25 passed, 158 deselected
frontend metadata: passed
frontend build isolated: passed, 33.05s
full explicit pytest: 183 passed
```

## Important honesty note

If frontend build times out in another environment, record it as timeout. Do not
document it as passed. The build script is designed to exit with code 124 on
timeout rather than hanging forever.
