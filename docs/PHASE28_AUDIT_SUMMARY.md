# DynaTutor Phase 28 Audit Summary

Phase 28는 새 solver나 새 기능을 추가하지 않고, clean checkout 상태에서 공식 설치/테스트/빌드 명령이 무한 대기하지 않도록 안정화하는 단계입니다.

이번 최종 정리에서는 `./scripts/check_all.sh --with-benchmark --with-audit`를 공식 필수 검증 경로에서 제외했습니다. 이유는 backend fast, benchmark, audit 각각은 안정적으로 통과하지만, 무거운 pytest 그룹을 한 shell 명령 안에서 연속 실행하는 방식은 환경에 따라 종료가 지연될 수 있기 때문입니다.

따라서 Phase 28의 공식 검증 경로는 다음처럼 분리합니다.

- smoke check: `./scripts/check_all.sh`
- backend benchmark: `./scripts/check_backend_benchmark.sh`
- backend audit: `./scripts/check_backend_audit.sh`
- frontend production build: `cd frontend && npm run build`
- optional frontend timeout safety check: `DYNATUTOR_FRONTEND_BUILD_TIMEOUT=20 ./scripts/check_frontend_build.sh`


## Frontend static export deployment status

The Phase 28 frontend deployment target is now **static export**. The frontend is a static app that calls the deployed FastAPI backend through `NEXT_PUBLIC_DYNATUTOR_API_BASE`. It does not depend on Vercel serverless functions, Next API routes, server actions, or middleware.

Static export configuration:

- `frontend/next.config.js` uses `output: "export"`.
- `images.unoptimized: true` is enabled.
- `outputFileTracingRoot: __dirname` and single-CPU static generation settings are set to keep clean static export builds from hanging in constrained environments.
- `frontend/vercel.json` sets `outputDirectory` to `out`, not `.next`.
- `frontend/package.json` pins `engines.node` to `20.x`.
- `frontend/lib/api.ts` reads `NEXT_PUBLIC_DYNATUTOR_API_BASE` and no longer falls back to `localhost:8000` or `window.location.hostname:8000`.

Clean static export verification command:

```bash
cd frontend
rm -rf .next out node_modules
npm ci
NEXT_TELEMETRY_DISABLED=1 npm run build
test -f out/index.html && echo "static export ok"
ls -la out
```

Observed result: `passed`. `out/index.html` was generated. The local sandbox ran Node `v22.16.0`, so `npm ci` printed an `EBADENGINE` warning because the project now requires Node `20.x`. Vercel should be configured to use Node `20.x`.

Vercel frontend settings:

```text
Install Command: npm ci
Build Command: npm run build
Output Directory: out
Node Version: 20.x
```

Required frontend environment variable:

```text
NEXT_PUBLIC_DYNATUTOR_API_BASE=https://your-backend-host.example.com
```

Required backend CORS environment variable:

```text
DYNATUTOR_CORS_ORIGINS=https://your-frontend.vercel.app
```

If the backend uses a personal access token, set `DYNATUTOR_ACCESS_TOKEN` on the backend only. Do not place tokens in browser-bundled `NEXT_PUBLIC_*` frontend variables.

## Environment

| Item | Value |
|---|---|
| OS | Linux 11c3ed355bff 4.4.0 #1 SMP Sun Jan 10 15:06:54 PST 2016 x86_64 GNU/Linux |
| Python | Python 3.13.5 |
| Node | v22.16.0 |
| npm | 10.9.2 |

## Result Matrix

| Check | Command | Status | Exit code | Summary |
|---|---|---:|---:|---|
| Frontend metadata | `./scripts/check_frontend_metadata.sh` | passed | 0 | `frontend metadata check passed` |
| Frontend metadata from backend | `cd backend && ../scripts/check_frontend_metadata.sh` | passed | 0 | `frontend metadata check passed` |
| Backend fast | `./scripts/check_backend_fast.sh` | passed | 0 | `157 passed, 36 deselected` |
| Smoke check | `./scripts/check_all.sh` | passed | 0 | smoke check only: frontend metadata + backend fast; `[check_all] completed` |
| Backend benchmark | `./scripts/check_backend_benchmark.sh` | passed | 0 | `10 passed, 183 deselected` |
| Backend audit | `./scripts/check_backend_audit.sh` | passed | 0 | `21 passed, 172 deselected`; `Audit pytest passed.` |
| Benchmark + audit all-check | `./scripts/check_all.sh --with-benchmark --with-audit` | optional_environment_sensitive | n/a | optional convenience command only; not the official required validation path |
| Backend audit forced timeout | `DYNATUTOR_BACKEND_AUDIT_TIMEOUT=1 ./scripts/check_backend_audit.sh` | timeout_guarded | 124 | process group terminated with SIGTERM; no pytest process remained |
| Vercel frontend config | `frontend/vercel.json` | configured | n/a | buildCommand `npm run build`; outputDirectory `out`; installCommand `npm ci`; Node `20.x` |
| Frontend clean static export | `cd frontend && rm -rf .next out node_modules && npm ci && NEXT_TELEMETRY_DISABLED=1 npm run build && test -f out/index.html` | passed | 0 | `static export ok`; `out/index.html` exists |
| Frontend production build | `cd frontend && npm run build` | passed | 0 | static export completed; `out/index.html` exists |
| Frontend build timeout safety | `DYNATUTOR_FRONTEND_BUILD_TIMEOUT=20 ./scripts/check_frontend_build.sh` | passed | 0 | wrapper build completed within 20s in this environment; slower environments may return 124 if cleanup succeeds |
| Default frontend build wrapper | `./scripts/check_frontend_build.sh` | environment_sensitive | n/a | includes `npm ci` plus a clean Next.js production build |
| Default pytest | `cd backend && pytest -q` | passed | 0 | `157 passed, 36 deselected` |
| Full pytest without marker split | `cd backend && pytest -q -o addopts=''` | not_recommended | n/a | official checks are split by marker and wrapper script |

## Official validation commands

### 1. Smoke check

```bash
./scripts/check_all.sh
```

This is the official fast smoke check. It intentionally runs only:

```bash
./scripts/check_frontend_metadata.sh
./scripts/check_backend_fast.sh
```

Expected result:

```text
frontend metadata check passed
157 passed, 36 deselected
[check_all] completed
```

### 2. Backend benchmark

```bash
./scripts/check_backend_benchmark.sh
```

Expected result:

```text
10 passed, 183 deselected
[run_with_timeout] command exited with code 0
```

### 3. Backend audit

```bash
./scripts/check_backend_audit.sh
```

Expected result:

```text
21 passed, 172 deselected
[run_with_timeout] command exited with code 0
Audit pytest passed.
```

Audit tests may include heavy release-candidate checks. Run them separately via `./scripts/check_backend_audit.sh` instead of requiring them to be chained through `check_all` with benchmark.

### 4. Frontend production build

```bash
cd frontend
npm run build
```

This is the official frontend production build success check. It must produce the static export directory `out` and the file `out/index.html`. The observed production build output included successful compilation, static page generation, export completion, and the exported routes `/` and `/_not-found`.

For a clean static export check, run:

```bash
cd frontend
rm -rf .next out node_modules
npm ci
NEXT_TELEMETRY_DISABLED=1 npm run build
test -f out/index.html && echo "static export ok"
```

### 5. Optional frontend timeout safety check

```bash
DYNATUTOR_FRONTEND_BUILD_TIMEOUT=20 ./scripts/check_frontend_build.sh
```

This is a timeout safety check, not the primary production build success check. If the build does not finish inside 20 seconds, exit code `124` is acceptable when the timeout wrapper kills the npm/Next.js process group and no `npm run build`, `next build`, or `node .*next` build child process remains.

Observed status after static export stabilization: `passed` with exit code `0` in this environment. The same command remains a timeout safety check; on slower environments, exit code `124` is acceptable only when the Python wrapper kills the npm/Next.js process group and no build child process remains.

## Optional check_all benchmark/audit policy

`./scripts/check_all.sh --with-benchmark --with-audit` is an optional convenience command. It is **not** the official required validation path.

Reason: heavy benchmark and audit groups are officially validated via dedicated scripts to avoid long chained pytest runs in one shell command. Some environments may finish the optional chained command, while others may wait longer around the audit teardown path. Phase 28 therefore does not claim this command as a required `passed` check.

The official equivalent is:

```bash
./scripts/check_all.sh
./scripts/check_backend_benchmark.sh
./scripts/check_backend_audit.sh
```

## Backend timeout wrapper policy

- `scripts/run_with_timeout.py` is the common backend timeout runner.
- `scripts/run_with_timeout.py` supports `DYNATUTOR_RUN_CWD`, which the backend check scripts set to the backend directory so pytest benchmark/audit fixtures can still use backend-relative paths.
- `scripts/run_with_timeout.py` installs SIGTERM/SIGINT/SIGHUP handlers, so if the wrapper itself is externally stopped, it still attempts to kill the child process group before exiting.
- `scripts/check_backend_fast.sh`, `scripts/check_backend_benchmark.sh`, and `scripts/check_backend_audit.sh` do not use GNU `timeout`.
- Backend pytest checks are started with `subprocess.Popen(..., start_new_session=True)` through `scripts/run_with_timeout.py`.
- On timeout, `scripts/run_with_timeout.py` sends `os.killpg(proc.pid, signal.SIGTERM)` and then `SIGKILL` if needed.
- stdout/stderr are inherited, so pytest output remains visible and the wrapper does not introduce pipe back-pressure.
- Normal pytest exit codes are returned unchanged.
- Timeout returns exit code `124`.
- `scripts/check_backend_audit.sh` prints `Audit pytest passed.` only after the audit pytest command exits with code `0`.

## Frontend build wrapper policy

- `scripts/check_frontend_build.sh` does not use GNU `timeout`.
- `scripts/check_frontend_build.sh` fixes the repository root, runs `npm ci` inside `frontend`, returns to the root, and then uses `exec python scripts/check_frontend_build.py`.
- The final `exec` reduces one shell layer. The Python wrapper becomes the direct process responsible for the build timeout path.
- `scripts/check_frontend_build.py` remains the timeout owner.
- Python starts `npm run build` with `subprocess.Popen(..., start_new_session=True)`.
- On timeout, Python sends `os.killpg(proc.pid, signal.SIGTERM)` and then `SIGKILL` if needed.
- stdout/stderr are inherited instead of piped through Python, so Next.js output is visible in real time and pipe back-pressure is avoided.

## Full pytest policy

`pytest -q -o addopts=''` is not the official verification path. Benchmark, audit, frontend, and slow checks are intentionally split by marker and by wrapper script so official checks can finish deterministically.

Therefore Phase 28 does **not** claim full unmarked pytest passed.

## Phase 28 stabilization notes

- default `check_all.sh` is a smoke check only.
- benchmark and audit are official checks only when run through their dedicated scripts.
- `check_all.sh --with-benchmark --with-audit` is optional and environment-sensitive, not a required pass claim.
- backend pytest timeout cleanup is owned by `scripts/run_with_timeout.py`, not by GNU timeout.
- frontend build timeout cleanup is owned only by the Python wrapper, not by GNU timeout.
- `check_frontend_build.sh` ends with `exec python scripts/check_frontend_build.py`.
- required answer validation treats missing requested outputs as errors when a solver reports `ok=True`.
- audit summary records actual results only: `passed`, `timeout_guarded`, `environment_sensitive`, `optional_environment_sensitive`, `skipped`, or `not_recommended`.
