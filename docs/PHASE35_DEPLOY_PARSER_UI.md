# Phase 35: 무료 배포 정리 · 보안 · 자연어 파서 · diagnosis 갱신 · UI 단순화 · 컴포넌트 분리

요구서 6항목을 우선순위 순서대로 전부 반영. 전체 스윕 **273 테스트 0 실패**,
하니스 전 지표 그린 (routing 432/432 · 수치 127/127 · negative 60/60 · 검증 FP 0 ·
clarify resolve 10/10 · provenance 999/999).

## 1. Render 무료 배포 정리 (render.yaml)
- Render 무료 플랜은 persistent disk를 쓰지 않는다. `DYNATUTOR_DB=/tmp/dynatutor_records.sqlite`로 통일한다 (ephemeral — 재시작 시 초기화). 유료 디스크를 붙일 때만 `/data/...` 같은 영구 경로를 별도 사용한다.
- `PYTHON_VERSION=3.11.9` 고정, buildCommand → `requirements-lock.txt` (전 의존성 == pin).
- Node 20 고정: `frontend/.nvmrc` + `frontend/.node-version` + package.json engines `>=20 <21`; production build는 `scripts/build-static.js`가 `out/`을 생성한다.
- `backend/dynatutor_records.sqlite` repo에서 삭제, `.gitignore`에 `*.sqlite` 추가, zip 패키징에서도 제외.

## 2. 토큰 / CORS / export 보안
- **production 기동 가드**: `DYNATUTOR_ENV=production` 또는 `RENDER=true`인데
  `DYNATUTOR_ACCESS_TOKEN` 미설정이면 RuntimeError로 서버가 열리지 않음 (`app/main.py`).
- **쿼리 문자열 토큰 인증 폐지**: URL query 방식 인증 설명을 제거하고 헤더(x-dynatutor-token / Bearer)만 사용.
  로그·히스토리 유출 차단. phase12 테스트를 "쿼리→401, 헤더→200"으로 갱신.
- **NEXT_PUBLIC 토큰 제거**: 프론트는 사용자가 앱에서 직접 입력한 localStorage 토큰만 사용.
- **export 헤더 인증**: `notebookExportUrl()`(URL 쿼리) 삭제 → `downloadNotebookExport()`
  (헤더 fetch + blob 다운로드).
- CORS: `DYNATUTOR_CORS_ORIGINS` env — 초기 테스트 때만 `*`, 최종 배포 전에는 Vercel 주소만 허용 (render.yaml 주석 안내).
- 401 응답은 프론트에서 `ApiAuthError`로 구분 → 토큰 입력 모달.

## 3. 자연어 파서 개선 (요구서 예문 전량 실측 → 9/9 해결)
| 표현 | 처리 |
|---|---|
| 정지해 있는 / 멈춰 있는 / 처음 정지 | v0=0 |
| 멈춘다 / 정지한다 | vf=0 |
| "X m 아래 지점에 떨어진다" | 발사점 아래 착지 (h=X, Δy=-X) |
| "X m 위 지점에 떨어진다" | landing_height=+X |
| "힘 방향으로 이동" | θ=0 (즉시 풀이) |
| A 물체/B 물체, 첫/두 번째 물체 + 속도·질량 | m1·m2·v1·v2 (자기 질량이 속도보다 앞에 와도 처리) |
| "3 m/s²로 움직인다" | a (라벨 없는 가속도) |
| "함께 움직인다 / 한 덩어리" | 완전비탄성 |
| "마찰은 무시한다" | no_friction |
| m+a에서 "힘은?" | single_particle_newton 라우팅 (F=ma) |
- **일-방향 되묻기** `work_direction_unknown`: F·s는 있는데 방향이 없으면 실패 대신
  같은 방향/반대/수직/각도 입력 4선택지. 반대 선택 시 W=-F·s 확인.
- **창 제한 전역화**: 라벨-값 사이 `[^\d-]*` 무제한 창 46곳 → `{0,12}` (arel 오파싱 버그
  클래스 근절). 부작용으로 깨진 교과서식 긴 수식어("힘은 변위와 같은 방향이며 크기는 10N")는
  문장 경계 차단 브릿지 패턴으로 복구.
- clarification whitelist에 `a`, `W` 추가.
- 회귀 테스트 15개: `tests/test_phase35_natural_korean.py`.

## 4. clarification patch 후 diagnosis 갱신
- `solve_problem`이 patch 적용 **후의** canonical로 diagnosis를 생성하도록 순서 교정
  (`diagnose_problem(..., canonical=...)` 주입 경로 신설).
- 검증: "마찰 없음" 선택 후 diagnosis.selected_solver = incline_no_friction,
  subtype = no_friction, response.physical_model == diagnosis.physical_model.
- 프론트 `SolveResult`는 `response.physical_model`을 우선 사용.

## 5+6. UI 단순화 · 컴포넌트 분리 (page.tsx 560줄 → 346줄 + 컴포넌트 9개)
- 기본 화면: **최종 답 → 핵심 개념 → 풀이 3단계 → 검산 요약 → 자주 하는 실수 1개**.
  나머지(전체 단계·공식·문제 구조·물리 모델·자유물체도·요약·복습 팁)는 "자세히 보기" 접기.
- `ClarificationCard`: needs_value 입력칸에 **단위 표시** (예: 가속도 [ ] m/s²) —
  단위는 옵션 patch.set_known.unit에서 자동.
- `SupportedTypesCard`: 지원 문제 유형 안내 (4개 그룹 접기 카드).
- `TokenSettings`: 오답노트 탭 카드 + **401 발생 시 모달**로 자동 표시.
- `SafeSvg`: FBD SVG를 화이트리스트 sanitizer(허용 태그/속성, script·on*·javascript: 차단)
  통과 후 렌더링 — 기존 raw dangerouslySetInnerHTML 대체.
- 분리: SolveResult / AnswerCard / VerificationPanel / ClarificationCard / NotebookPanel(RecordCard) /
  SupportedTypesCard / TokenSettings / SafeSvg (+기존 Card·MathBlock).
- 기존 API 호출·핸들러·데이터 필드 전부 보존 (정적 무결성 검증: import·export·CSS 클래스 대조 통과).

## 사용자 환경에서 확인 필요
- Node 20 기준 `cd frontend && npm ci && npm run build`로 `out/index.html` 생성 확인.
- 백엔드: `./scripts/check_backend_fast.sh` + `python tools/routing_confusion_report.py`.
- 배포 순서: Render(백엔드, 토큰 env 설정) → Vercel(프론트, NEXT_PUBLIC_DYNATUTOR_API_BASE만; 토큰 env 금지) →
  CORS를 Vercel 주소로 좁히기 → 앱에서 토큰 1회 입력.
