# DynaTutor Release Checklist

기준: Phase 40 (2026-07). 아래 명령이 모두 통과해야 패키징/배포한다.
**패키징 전 하니스 실행은 필수다** — Phase 39에서 스테일 리포트 뒤에 교란 58건 회귀가
숨어 있던 사례가 있다.

## Backend — 공식 release validation (Phase 41 기준)

전체 한 방 실행(`pytest -q -o addopts=`)은 환경에 따라 timeout될 수 있어
**공식 기준은 marker 그룹별 실행**이다. 각 스크립트는 timeout 래퍼로 감싸져 있고,
자식 종료 후 잔존 프로세스 그룹도 정리하므로 매달리지 않는다.

```bash
./scripts/check_backend_fast.sh        # 기본 세트 (unit/regression/negative — pytest 기본 addopts)
./scripts/check_backend_benchmark.sh   # -m benchmark
./scripts/check_backend_audit.sh       # -m audit
(cd backend && PYTHONPATH=. pytest -q -o addopts='' -m "frontend")
(cd backend && PYTHONPATH=. python tools/routing_confusion_report.py)
```

Expected:

```text
fast / benchmark / audit: 각 그룹 0 failed
routing 432/432 · numeric 127/127 · negative 60/60 · perturbation 0 breaks
verification FP 0 · resid-cov 243/243 · clarify negatives→질문 60/60 · provenance 100%
```

선택(시간이 더 걸리는 심층 감사):

```bash
cd backend
PYTHONPATH=. python tools/run_phase20_benchmark_audit.py
PYTHONPATH=. python tools/chrono_validation/run_all_validations.py --strict   # PyChrono 설치 시
PYTHONPATH=. python tools/run_release_candidate_audit.py
```

## Frontend

```bash
./scripts/check_frontend_build.sh   # npm ci + npm run build + out/ 산출물 검증 (Node 20)
```

Expected: `outputs verified: out/index.html, out/assets/app.js` 출력 후 **즉시 종료 코드 0**
(빌드 도구가 남긴 잔존 프로세스는 래퍼가 정리한다 — 프롬프트가 돌아오지 않으면 버그로 보고).

로컬에서 production 산출물 미리보기: `cd frontend && npm run start` (out/을 정적 서빙).

## Historical (Phase 23 당시 기준 — 참고용)

```text
pytest: 145 passed
benchmark audit: passed
Phase 21 validation: passed
release candidate audit: overall_passed true
```

## Frontend

The container used for Phase 23 did not have `frontend/node_modules`.

Before deployment:

```bash
cd frontend
node -v   # must be v20.x
npm ci
npm run build
test -d out
```

## Personal remote mode

Required backend env for private cloud use:

```text
DYNATUTOR_ACCESS_TOKEN=<long random token>
DYNATUTOR_CORS_ORIGINS=<your Vercel URL or * for initial testing>
DYNATUTOR_DB=/tmp/dynatutor_records.sqlite
DYNATUTOR_PUBLIC_DOCS=false
```

Required frontend env:

```text
NEXT_PUBLIC_DYNATUTOR_API_BASE=<your backend URL>
```

## Optional LLM

Safe default:

```text
LLM_ENABLED=auto
```

With API key:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=<key>
OPENAI_MODEL=<model>
```

The LLM layer is optional and guarded. If disabled or unsafe, template fallback
is used.

## Optional PyChrono

Do not install PyChrono into normal runtime unless you know why.

Recommended:

```bash
conda create -n dynatutor-chrono python=3.11
conda activate dynatutor-chrono
# install pychrono according to your OS-specific Project Chrono docs
```

## Zip hygiene

Before sharing a release zip, exclude:

```text
__pycache__
.pytest_cache
node_modules
.next
.venv
venv
*.pyc
*.pyo
*.sqlite
*.sqlite3
*.db
backend/dynatutor_records.sqlite
frontend/out
```


## Phase 38 final deployment notes

- Official backend validation: `cd backend && PYTHONPATH=. pytest -q -o addopts=`. If the sandbox times out, run the same tests in file groups and confirm all groups pass.
- Table-hanging pulley without friction information should clarify, not silently assume frictionless. Benchmarks that expect solving must explicitly say `마찰 없음`, `마찰은 무시한다`, or `frictionless`.
- Frontend production build mode is custom static build: `npm run build` → `scripts/build-static.js` → `out/index.html` + `out/assets/`. Vercel output directory must be `out`.
- Development uses `npm run dev`; `next start` is not the production command for this static deployment.
- Render free DB path is `DYNATUTOR_DB=/tmp/dynatutor_records.sqlite`; records may disappear after restart/redeploy. Use export backup.
- Persistent disk paths such as `/data/dynatutor_records.sqlite` are paid persistent-disk options only.
- Export uses header authentication (`x-dynatutor-token`); do not document query-string tokens.
- Never create or use `NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN`. The user enters the token in the UI and it is stored locally on that device.
- CORS initial test may use `*`; final deployment should use exactly `https://your-app.vercel.app` with no trailing slash.
- Production API docs are controlled by `DYNATUTOR_PUBLIC_DOCS`; recommended production value is `false`.
