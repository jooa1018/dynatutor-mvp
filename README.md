# DynaTutor MVP

## Phase 36 Frontend Static Deployment

The frontend is a static browser app. It does not rely on Vercel serverless functions, API routes, server actions, middleware, or runtime secrets. The browser bundle calls the deployed FastAPI backend through `NEXT_PUBLIC_DYNATUTOR_API_BASE`.

### Static build settings

- `frontend/scripts/build-static.js` type-checks the React app, bundles it, copies `public/`, and writes `out/index.html`.
- `frontend/vercel.json` sets `outputDirectory` to `out`, not `.next`.
- `frontend/package.json` pins `engines.node` to `>=20 <21`. Use Node 20 for local and Vercel builds.
- The app still keeps small Next compatibility files for local preview/history, but production deployment uses the static `out/` build output.

### Vercel frontend settings

Use these settings for the frontend project:

```text
Framework Preset: Other / Static, with Output Directory set to out
Install Command: npm ci
Build Command: npm run build
Output Directory: out
Node Version: 20.x
```

Set this frontend environment variable in Vercel:

```text
NEXT_PUBLIC_DYNATUTOR_API_BASE=https://your-backend-host.example.com
```

Example:

```text
NEXT_PUBLIC_DYNATUTOR_API_BASE=https://dynatutor-backend.onrender.com
```

The frontend no longer falls back to `localhost:8000` or `window.location.hostname:8000`. If the API base URL is missing, API calls fail with a clear configuration error instead of silently calling localhost.

### Phase 38 deploy notes

Frontend build mode is intentionally custom static build:

- Development: `npm run dev` uses the Next dev server.
- Production: `npm run build` runs `frontend/scripts/build-static.js`.
- Output: `out/index.html` and `out/assets/`.
- Vercel output directory: `out`.
- `next start` is not the production deployment command for this static build mode.

Render free-plan backend storage uses `DYNATUTOR_DB=/tmp/dynatutor_records.sqlite`. This is temporary storage and can reset after restart/redeploy. The UI warns users and falls back to browser `localStorage` when server notebook saving fails.

Production API docs are private by default. Set `DYNATUTOR_PUBLIC_DOCS=true` only if you intentionally want `/docs`, `/redoc`, and `/openapi.json` public.

### Backend CORS settings

For initial smoke testing only:

```text
DYNATUTOR_CORS_ORIGINS=*
```

For final deployment, set the backend deployment environment variable to the exact deployed frontend origin, without a trailing `/`:

```text
DYNATUTOR_CORS_ORIGINS=https://your-frontend.vercel.app
```

CORS checklist: exact Vercel origin, no trailing `/`, correct https/http, correct `NEXT_PUBLIC_DYNATUTOR_API_BASE`, Render cold start, and whether the browser error is actually a 401 token response.

If a personal access token is enabled on the backend, set:

```text
DYNATUTOR_ACCESS_TOKEN=<long-random-token>
```

Do not put a sensitive production token in any `NEXT_PUBLIC_*` variable because those values are bundled into browser JavaScript. For a private personal app, enter the token in the UI localStorage flow instead of hardcoding it into the public bundle.

### Clean static export verification

Run:

```bash
cd frontend
rm -rf out node_modules
npm ci
NEXT_TELEMETRY_DISABLED=1 npm run build
test -f out/index.html && echo "static export ok"
ls -la out
```

Expected result: `static export ok`, with `out/index.html` present.

## Phase 28 Final Validation Structure

Phase 28 treats `./scripts/check_all.sh` as a fast smoke check. Heavy benchmark and audit groups are officially validated through their dedicated scripts instead of being required to run through one chained `check_all` command. This avoids environment-sensitive long chained pytest runs while keeping each important check reproducible.

## Official validation commands

Run the smoke check:

```bash
./scripts/check_all.sh
```

Run backend benchmark:

```bash
./scripts/check_backend_benchmark.sh
```

Run backend audit:

```bash
./scripts/check_backend_audit.sh
```

Run frontend production build:

```bash
cd frontend
npm run build
```

Optional frontend timeout safety check:

```bash
DYNATUTOR_FRONTEND_BUILD_TIMEOUT=20 ./scripts/check_frontend_build.sh
```

`DYNATUTOR_FRONTEND_BUILD_TIMEOUT=20 ./scripts/check_frontend_build.sh` is a timeout cleanup check, not the primary production-build success check. Exit code `124` is acceptable if the wrapper kills the npm/frontend build process group and no build child process remains.

`./scripts/check_all.sh --with-benchmark --with-audit` is an optional convenience command, not the official required validation path. Heavy benchmark and audit tests are intentionally validated via dedicated scripts. Audit tests may include heavy release-candidate checks; run them separately with `./scripts/check_backend_audit.sh` instead of requiring them to be chained with benchmark through `check_all`.


## Phase 27 Stability

This version stabilizes clean checkout testing/build workflows.

Added/updated:

- `backend/pytest.ini`
- `backend/tests/conftest.py`
- `backend/engine/physics_core/answer_validators.py`
- `backend/tests/test_phase27_stability.py`
- `scripts/check_backend_fast.sh`
- `scripts/check_backend_benchmark.sh`
- `scripts/check_backend_audit.sh`
- `scripts/check_frontend_metadata.sh`
- `scripts/check_frontend_build.py`
- `scripts/check_frontend_build.sh`
- `scripts/check_all.sh`
- `docs/PHASE27_STABILITY.md`
- `docs/PHASE27_AUDIT_SUMMARY.json`

Run fast backend tests:

```bash
cd backend
pytest -q
# or
./scripts/check_backend_fast.sh
```

Run split checks:

```bash
./scripts/check_backend_fast.sh
./scripts/check_backend_benchmark.sh
./scripts/check_backend_audit.sh
./scripts/check_frontend_metadata.sh
./scripts/check_frontend_build.sh
```

Run combined non-build check:

```bash
./scripts/check_all.sh
```

Frontend build is intentionally separate:

```bash
./scripts/check_frontend_build.sh
```

Observed Phase 27 results:

- fast backend: `148 passed, 35 deselected`
- benchmark: `10 passed` plus Phase20 benchmark `492 total, 0 failures`
- audit: `25 passed`
- frontend metadata: passed
- frontend build isolated: passed in about `33.05s`
- full explicit pytest: `183 passed`

Important parser fix:

- `"일 때"` is no longer treated as work.
- `"마찰력이 한 일"` and `"일 16J"` are still treated as work.

See `docs/PHASE27_STABILITY.md`.


## Phase 26 Multi-Answer Outputs

This version adds real multi-answer output support.

Added:

- `AnswerItem` / `answers[]` in backend solver/API responses
- `CanonicalProblem.requested_outputs`
- `launch_angle_deg` / `launch_angle_source`
- projectile time + range + max-height multi-output
- pulley acceleration + tension multi-output
- collision post-impact velocity multi-output
- LLM locked facts with full `answers[]`
- frontend final-answer list rendering
- single-particle Newton physical-model force object
- frontend build script timeout policy

Verified:

- backend pytest: `176 passed`
- existing benchmark audit: `492 total, 0 failures`
- blind textbook-style benchmark: `100 total, 0 failures`
- frontend `npm ci`: passed
- frontend `npm run build`: passed
- frontend `npm audit`: `0 vulnerabilities`

Pytest no longer runs the frontend build directly. Use:

```bash
./scripts/check_frontend_build.sh
```

The script runs the build with a 180-second timeout.

See `docs/PHASE26_MULTI_ANSWER_OUTPUTS.md`.


## Phase 25 Accuracy Hardening

This version addresses remaining accuracy and reproducibility gaps.

Added:

- `backend/engine/solvers/newton/single_particle.py`
- `backend/tests/test_phase25_core_improvements.py`
- `backend/tests/test_phase25_blind_textbook_benchmark.py`
- `backend/tests/test_phase25_dependency_locks.py`
- `backend/tests/benchmarks/blind_textbook_style/*.json`
- `backend/requirements-lock.txt`
- `frontend/package-lock.json`
- `docs/PHASE25_ACCURACY_HARDENING.md`

Key improvements:

- basic single-particle Newton solver: `F=ma`
- gram mass parsing for simple Newton problems
- km/h natural-language velocity parsing
- incline-hanging pulley kinetic-friction direction safety
- incline-hanging candidate diagnosis without explicit pulley/string
- frontend exact dependency versions, no `latest`
- frontend `npm ci && npm run build` verified; `npm audit` reports 0 vulnerabilities
- frontend `npm audit` reported 0 vulnerabilities with postcss override
- blind textbook-style benchmark: 100 cases

Reproducible frontend build:

```bash
cd frontend
npm ci
npm run build
npm audit  # verified: 0 vulnerabilities
```

Reproducible backend install:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
pytest  # verified: 168 passed
```

Windows backend:

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-lock.txt
pytest  # verified: 168 passed
```

See `docs/PHASE25_ACCURACY_HARDENING.md`.


## Phase 24 Final Polish / Deployment Verification

This version is the final personal-use stopping point.

Added:

- `backend/tools/run_phase24_deployment_audit.py`
- `backend/tests/test_phase24_final_polish_deployment.py`
- `scripts/check_frontend_build.sh`
- `scripts/check_frontend_build_windows.bat`
- `scripts/final_local_check.sh`
- `scripts/final_local_check_windows.bat`
- `docs/PHASE24_FINAL_POLISH_DEPLOYMENT.md`
- `docs/DEPLOYMENT_GUIDE_PERSONAL.md`
- `docs/FINAL_LOCAL_RUNBOOK.md`
- `docs/PHASE24_AUDIT_SUMMARY.json`
- `release_manifest_phase24.json`

Polish changes:

- frontend now supports both `NEXT_PUBLIC_DYNATUTOR_API_BASE` and `NEXT_PUBLIC_API_BASE`
- `.env.example` documents the preferred frontend API env
- PWA/deployment files are audited
- Python LaTeX-string warnings were reduced with raw strings

Final status:

- backend tests: `150 passed`
- Phase 24 deployment audit: passed
- frontend build: dependency skip in this container because `frontend/node_modules` is missing

Before real deployment, run:

```bash
cd frontend
npm install
npm run build
```

See `docs/PHASE24_FINAL_POLISH_DEPLOYMENT.md`.


## Phase 23 Accuracy Audit / Release Candidate

This version packages DynaTutor as a personal-use release candidate.

Added:

- `backend/tools/run_release_candidate_audit.py`
- `backend/tests/test_phase23_release_candidate_audit.py`
- `release_manifest_phase23.json`
- `docs/PHASE23_RELEASE_CANDIDATE.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/KNOWN_LIMITATIONS.md`
- `docs/RC_AUDIT_SUMMARY.json`

RC result:

- backend tests: `145 passed`
- benchmark total: `492`
- benchmark failures: `0`
- Phase 21 validation: `25 passed`
- LLM guardrail audit: passed
- frontend build: not run because `frontend/node_modules` was missing

See `docs/PHASE23_RELEASE_CANDIDATE.md`.


## Phase 22 LLM Teacher Guardrail v2

This version strengthens the optional LLM teacher layer.

Updated:

- `backend/app/schemas/llm.py`
- `backend/engine/llm/guardrails.py`
- `backend/engine/llm/prompt.py`
- `backend/engine/llm/service.py`
- `backend/engine/llm/template.py`

New guardrail behavior:

- locked facts include answer numbers, answer unit, allowed numbers, not-applicable equations, and locked_hash
- prompt includes `LOCKED_FACTS_JSON`
- LLM output is checked for changed final answer, new numbers, forbidden formulas, and unsupported-problem hallucination
- failed LLM output falls back to the safe template explanation

Backend tests: `143 passed`.

See `docs/PHASE22_LLM_GUARDRAIL_V2.md`.


## Phase 21 Chrono Offline Validation

This version replaces the Chrono placeholder scripts with a validation harness.

New/updated:

- `backend/tools/chrono_validation/common.py`
- `backend/tools/chrono_validation/analytic_cases.py`
- `backend/tools/chrono_validation/chrono_simulators.py`
- `backend/tools/chrono_validation/run_all_validations.py`
- individual validation scripts for rolling, incline friction, collision, and massive pulley

Validation layers:

- automated DynaTutor vs analytic-reference checks
- optional PyChrono hooks for local numerical validation

Current environment note:

- PyChrono was not importable in this container
- automated analytic validation passed
- PyChrono numerical simulation was not falsely claimed as executed

Backend tests: `134 passed`.

See `docs/PHASE21_CHRONO_OFFLINE_VALIDATION.md`.


## Phase 20 Benchmark Audit

This version expands DynaTutor's verification benchmark coverage.

New benchmark files:

- `backend/tests/benchmarks/phase20_derived/openstax_style_derived_050.json`
- `backend/tests/benchmarks/phase20_derived/fossee_style_derived_048.json`
- `backend/tests/benchmarks/phase20_derived/mit_ocw_style_derived_031.json`
- `backend/tests/benchmarks/phase20_negative/negative_unsupported_060.json`

Benchmark totals:

- synthetic: 300
- derived-style: 132
- negative: 60
- total: 492

New audit tool:

- `backend/tools/run_phase20_benchmark_audit.py`

Backend tests: `129 passed`.

See:

- `docs/PHASE20_BENCHMARK_AUDIT.md`
- `docs/BENCHMARK_SCHEMA.md`


## Phase 19 SymPy Mechanics / PyDy Adapter

This version turns the advanced mechanics adapter from a placeholder into
working equation-generation code.

Updated:

- `backend/engine/adapters/sympy_mechanics_adapter.py`
- `backend/engine/adapters/pydy_adapter.py`
- `backend/tools/run_mechanics_adapter_examples.py`

Implemented SymPy Mechanics derivations:

- simple pendulum
- mass-spring-damper
- particle on rotating rod
- planar rigid-body rotation
- connected particles with spring

PyDy remains optional and is not required for the normal student solve path.
When PyDy is unavailable, the adapter returns a safe symbolic blueprint.

Backend tests: `125 passed`.

See `docs/PHASE19_SYMPY_MECHANICS_PYDY_ADAPTER.md`.


## Phase 18 2D Rigid Body / Direction & Coordinate Upgrade

This version improves 2D direction and coordinate parsing for planar rigid-body
problems.

New file:

- `backend/engine/physics_core/coordinate_parser.py`

Improvements:

- right/left/up/down direction parsing
- clockwise/counterclockwise angular sign
- Korean r_B/A phrase parsing
- A-point velocity/acceleration direction parsing
- signed omega/alpha in rigid-body vector solvers
- coordinate notes exposed through `PhysicalModel`

Updated solvers:

- `backend/engine/solvers/rigid_body_2d/velocity.py`
- `backend/engine/solvers/rigid_body_2d/acceleration.py`

Backend tests: `117 passed`.

See `docs/PHASE18_RIGID_BODY_COORDINATE_UPGRADE.md`.


## Phase 17 Energy / Momentum Generator

This version adds a model-based energy/momentum equation generator.

New file:

- `backend/engine/equation_generators/energy_momentum.py`

`PhysicalModel` now includes:

- `generated_energy_momentum_system`

Solvers now connected to the generator:

- constant force work
- work-energy speed
- spring vibration
- spring energy speed
- pure rolling energy
- rolling energy with general I
- impulse-momentum
- 1D collision

Backend tests: `109 passed`.

See `docs/PHASE17_ENERGY_MOMENTUM_GENERATOR.md`.


## Phase 16 Friction / Constraint Engine

This version adds static-friction-first decisions and explicit string/pulley
topology records.

New pieces:

- `backend/engine/physics_core/friction.py`
- `backend/engine/physics_core/string_topology.py`
- `backend/engine/model_builder/friction_analyzer.py`

`PhysicalModel` now includes:

- `friction_decisions`
- `string_topology`

Solvers improved:

- incline with friction
- table-hanging pulley
- incline-hanging pulley

Backend tests: `102 passed`.

See `docs/PHASE16_FRICTION_CONSTRAINT_ENGINE.md`.


## Phase 15 Newton Equation Generator

This version adds a first general equation generator:

- `backend/engine/equation_generators/particle_newton.py`
- `GeneratedEquation`
- `GeneratedEquationSystem`
- `PhysicalModel.generated_equation_system`

The following solvers now use generated Newton equations internally:

- incline without friction
- incline with friction
- Atwood pulley
- table-hanging pulley
- incline-hanging pulley
- massive pulley Atwood

Backend tests: `95 passed`.

See `docs/PHASE15_NEWTON_EQUATION_GENERATOR.md`.


## Phase 14 PhysicalModel Builder

Phase 14 adds `backend/engine/model_builder`, which converts `CanonicalProblem`
into a structured `PhysicalModel` containing bodies, forces, constraints, and
coordinate axes. The diagnosis API and frontend now expose this model so the
user can see what physical system DynaTutor thinks it is solving.

See `docs/PHASE14_PHYSICAL_MODEL_BUILDER.md`.


## Phase 13 Physics-Core Refactor

This version adds a physics-model based core:

- Pint unit engine
- Shared SymPy symbols/equation system
- 2D vector rigid-body helpers
- Direction parser for work/force problems
- Friction decision helpers
- Inertia beta table for rolling bodies
- Pulley topology separation
- General projectile solver
- Strict unsupported/ambiguous problem handling
- OSS usage/license notes

Backend tests: `85 passed`.

See:

- `docs/PHASE13_PHYSICS_CORE_REFACTOR.md`
- `docs/OSS_USAGE.md`
- `docs/LICENSE_NOTICES.md`
- `docs/SOURCES_EDUCATIONAL.md`

# DynaTutor MVP — Phase 8.5

## Phase 12 — Phone-only Remote Mode

이 버전은 iPhone만으로 사용하기 위한 개인용 원격 실행 모드를 추가했습니다. PC에서 로컬 서버를 켜지 않아도, FastAPI 백엔드를 클라우드에 배포하고 iPhone Safari/PWA로 접속하면 사용할 수 있습니다.

핵심 추가 사항:

- `DYNATUTOR_ACCESS_TOKEN` 개인용 접근 토큰
- iPhone UI에서 토큰 저장
- 모든 API 요청에 `x-dynatutor-token` 자동 첨부
- 백업 export는 앱의 헤더 인증 fetch 방식 사용
- Render 배포용 `render.yaml`
- FastAPI Dockerfile / Procfile
- Vercel용 frontend 설정 파일
- `docs/PHASE12_PHONE_ONLY_REMOTE.md`

완전 오프라인 네이티브 앱은 아니며, 인터넷에 올라간 백엔드가 필요합니다. 하지만 사용자는 iPhone만 들고 Safari/PWA로 접속해서 사용할 수 있습니다.


DynaTutor is a Korean-friendly dynamics tutoring app prototype.

It is designed around this principle:

```text
Do not let AI decide the physics.
Use structured problem representation, solver registry, and verification first.
Use LLM only after the answer is grounded and locked.
```

## Current architecture

```text
User Input
→ Input Normalizer
→ Quantity Extractor
→ Canonical Problem Representation
→ Legacy Rule Hints
→ Solver Registry
→ Verification Layer
→ High-Fidelity FBD Sketch Layer
→ Deterministic Explanation Layer
→ Optional LLM Teacher Layer
→ Tutor Card UI
→ Notebook / Review Layer
```

The user's previous app is treated as a source of rule ideas, template seeds, and regression-test thinking, not as the main engine.

## Phase 8 focus

Phase 8 adds advanced undergraduate dynamics solver families after checking standard references for rotating-axis motion, Coriolis acceleration, and planar rigid-body acceleration. The goal is not full multibody simulation yet; it is a stable set of closed-form tutoring solvers for common textbook problem forms.

## Phase 8 features

- FastAPI backend
- Static React frontend
- Canonical problem model
- Solver registry
- Verification report
- Higher-quality SVG FBD sketch layer
- Color-coded FBD legends
- Diagram annotation notes
- Safe deterministic explanation layer
- Optional LLM teacher explanation layer
- Locked-fact prompt builder
- Lightweight numeric integrity guard
- No-key fallback template mode
- Mock LLM mode for local UI testing
- Example library
- Formula card / equation sheet
- Common mistake cards
- Study tip cards
- SQLite notebook storage
- Notebook statistics dashboard
- **New: relative acceleration translation solver**
- **New: Coriolis / rotating-frame relative-motion solver**
- **New: planar rigid-body acceleration solver**
- **New: massive pulley Atwood solver**
- **New: general rolling-energy solver using supplied moment of inertia**

## Supported solver families

- Frictionless incline
- Incline with friction
- Table-hanging pulley
- Pure rolling energy
- General rolling energy with supplied inertia `I`
- Vertical circle basic cases
- 1D collision with restitution coefficient
- Constant acceleration 1D kinematics
- Projectile motion basic cases
- Constant force work
- Work-energy speed
- Fixed-axis rotation
- Impulse-momentum
- Spring-mass vibration
- Spring energy speed
- Flat curve friction limit
- Banked curve no-friction design speed
- Polar kinematics
- Instant center velocity
- Slot-pin relative motion
- Plane rigid body velocity basic case
- Relative acceleration in a translating frame
- Coriolis / rotating-frame relative acceleration
- Plane rigid body acceleration basic case
- Massive pulley Atwood system

## Phase 8 advanced examples

```text
A점 가속도 aA=1.2 m/s^2 이고 A에 대한 B의 상대가속도 a_rel=0.8 m/s^2 이다. B점 가속도를 구하라.
```

```text
회전좌표계에서 r=0.5 m, 상대속도 v_rel=0.4 m/s, 상대가속도 a_rel=0.1 m/s^2, 각속도 omega=6 rad/s, 각가속도 alpha=2 rad/s^2 이다. 코리올리 가속도와 절대가속도 성분을 구하라.
```

```text
평면강체 가속도 문제에서 거리 r=0.6 m, 각속도 omega=4 rad/s, 각가속도 alpha=3 rad/s^2 이다. B점의 A에 대한 가속도 성분을 구하라.
```

```text
질량 있는 도르래에 m1=2 kg, m2=5 kg가 줄로 연결되어 있다. 도르래 관성모멘트 I=0.12 kgm^2, 도르래 반지름 R=0.3 m 일 때 가속도를 구하라.
```

```text
질량 3 kg, 반지름 R=0.4 m, 관성모멘트 I=0.18 kgm^2 인 강체가 미끄러지지 않고 경사면을 높이 h=1.2 m만큼 굴러 내려간다. 속도를 구하라.
```

## Optional LLM mode

The app works with no LLM key. In that case, the `AI 선생님 설명` button returns a safe template explanation.

To enable an OpenAI-compatible LLM provider:

```bash
cd backend
cp .env.example .env
# then set OPENAI_API_KEY and optionally OPENAI_MODEL
```

Environment variables:

```text
LLM_ENABLED=auto        # auto, true, false
LLM_PROVIDER=openai     # openai, openai-compatible, mock
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

For local integration testing without an API bill:

```bash
LLM_PROVIDER=mock LLM_ENABLED=true uvicorn app.main:app --reload --port 8000
```

## Run backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

## Run tests

```bash
cd backend
pytest -q
```

Current status:

```text
45 passed
```

## Useful API endpoints

```text
POST /diagnose
POST /solve
POST /feedback
GET  /examples
GET  /explain/status
POST /explain/ai
POST /records
GET  /records
GET  /records/stats
```

## Next recommended phase

Phase 9 should focus on service readiness:

1. User account and cloud notebook storage
2. Supabase/PostgreSQL migration
3. API rate limit and LLM cost limit
4. Deployment configuration
5. More polished onboarding and error messages


## Phase 8.5 한국어 문제 인식 강화

이번 단계에서는 한국어 자연문장 입력을 더 안정적으로 처리하도록 파서를 강화했습니다.

- `500g`, `30cm`, `72 km/h`, `2분` 같은 단위를 SI 단위로 변환합니다.
- `정지 상태에서 출발`은 `v0=0`, `최종적으로 정지`는 `vf=0`으로 해석합니다.
- `걸리는 시간은?`, `최종속도를 구하라`, `한 일을 구하라`처럼 한국어 구할 값 표현을 더 잘 잡습니다.
- `마찰이 없는`, `마찰 없음`, `마찰을 무시` 같은 표현을 frictionless 조건으로 처리합니다.
- 한국어 파서 회귀 테스트가 추가되어 현재 `58 passed`입니다.

자세한 내용은 `docs/PHASE8_5_KOREAN_PARSER.md`를 참고하세요.


## Phase 9 — Local Study Mode

개인용 학습모드를 강화했습니다. 서비스 배포/계정/클라우드 DB 대신 로컬 SQLite 기반 오답노트와 복습 흐름에 집중합니다.

새 기능:

- 오늘의 개인 학습 대시보드: `GET /study/dashboard`
- 개인 연습 세트: `GET /study/practice`
- 복습 결과 기록: `POST /records/{id}/review`
- 즐겨찾기/복습일/숙련도/복습횟수 저장
- 로컬 백업: `GET /records/export`
- 로컬 복원: `POST /records/import`
- 실행 스크립트: `scripts/run_backend.sh`, `scripts/run_frontend.sh`, `scripts/run_local.sh`, `scripts/run_local_windows.bat`

빠른 실행:

```bash
./scripts/run_backend.sh
# 새 터미널
./scripts/run_frontend.sh
```

브라우저에서 `http://localhost:3000`을 열면 됩니다.

자세한 내용은 `docs/PHASE9_LOCAL_STUDY_MODE.md`를 참고하세요.

## Phase 10 — Korean Quality Audit

Phase 10 adds a 100-case Korean dynamics benchmark and fixes parser weaknesses found during the audit. It is still local-study focused, not service-oriented.

Run the audit:

```bash
./scripts/run_quality_audit.sh
```

Current backend test result:

```text
63 passed
```

Highlights:

- 100 Korean textbook-style prompts added as regression cases
- Korean deceleration expressions such as `감속하여 멈출 때까지` fixed
- `순간중심에서 점까지 거리` now maps to IC radius `r`
- `rolling without slipping` no longer misfires as slot-pin because of the substring `pin`
- Korean work phrasing like `10N의 힘으로 30cm 밀었다` improved
- collision classification now has priority over generic kinematics
- spring compression phrasing like `30cm 압축` improved

See `docs/PHASE10_KOREAN_QUALITY_AUDIT.md`.


## Phase 11 · iPhone 14 최적화

이번 버전은 iPhone 14에서 개인용 로컬 앱처럼 쓰기 좋게 PWA/모바일 레이아웃을 강화했습니다.

```bash
./scripts/run_iphone_lan.sh
```

실행 후 같은 Wi‑Fi의 iPhone Safari에서 터미널에 표시된 `http://<PC-IP>:3000` 주소를 열고, 공유 버튼 → 홈 화면에 추가를 누르면 앱처럼 사용할 수 있습니다.

주요 변경점:

- iPhone 14 세로 화면 중심 반응형 UI
- 하단 엄지 네비게이션
- PWA manifest / Apple touch icon
- safe-area inset 대응
- 터치 타깃 44px 이상
- LAN 접속 시 API 주소 자동 보정
- iPhone LAN 실행 스크립트

자세한 내용은 `docs/PHASE11_IPHONE14_PWA.md`를 참고하세요.
