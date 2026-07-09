# Phase 38 Predeploy Stabilization

## 공식 검증 기준

Phase 38의 기준은 “빠른 테스트만 통과”가 아니라 현재 배포 정책과 맞는 공식 테스트 세트 통과다.

권장 실행:

```bash
cd backend
PYTHONPATH=. pytest -q -o addopts=
```

긴 벤치마크/감사 그룹은 환경에 따라 오래 걸릴 수 있으므로, 필요하면 파일 단위로 나눠 실행한다.
예전 테스트가 보안 정책이나 배포 구조와 충돌하면 테스트 기대값을 현재 정책에 맞춘다.

## table-hanging pulley 정책

수평 테이블 위 물체와 매달린 물체가 줄/도르래로 연결된 문제는 마찰 조건이 중요하다.

- `마찰 없음`, `마찰은 무시`, `frictionless`가 있으면 마찰 없는 table-hanging pulley로 바로 푼다.
- `마찰계수 μ`가 있으면 마찰 포함 table-hanging pulley로 푼다.
- 마찰 조건이 빠지면 바로 풀지 않고 clarification을 띄운다.

왜 필요한가: 테이블 위 물체에는 마찰력이 작용할 수도 있고 없을 수도 있다. 마찰이 있으면 `μm₁g`가 운동을 방해해 가속도와 장력이 달라진다.

## work requested_outputs 수정

다음 표현은 주어진 조건이다.

- `3m 이동하는 동안`
- `변위가 3m일 때`
- `힘 방향으로 5m 이동시켰다`

질문이 `한 일은?`, `일을 구하라`, `work?`이면 requested output은 `work`만 잡는다. `이동거리를 구하라`, `변위를 구하라`, `얼마나 이동했는가`처럼 직접 물을 때만 `distance`를 requested output으로 잡는다.

## Frontend build 정책

Phase 38은 방향 A를 채택한다.

- 개발: `npm run dev`로 Next dev server 사용
- 배포: `npm run build`가 `scripts/build-static.js`를 실행
- 산출물: `out/index.html`, `out/assets/app.js`, `out/assets/app.css`
- Vercel output directory: `out`

`next start`는 production 배포 명령이 아니다. 실제 배포 문서와 audit는 custom static build 기준을 사용한다.

## Render 무료 플랜 UX

Render 무료 서버는 sleep 상태에서 첫 요청이 느릴 수 있다. 프론트는 첫 solve/API 요청이 오래 걸리면 “서버를 깨우는 중” 안내를 표시하고, 네트워크/timeout 실패는 자동 retry한다. 최종 실패 시 백엔드 주소, 토큰, Render cold start, CORS 설정을 확인하라는 메시지를 보여준다.

## 무료 배포 기록 저장 정책

Render 무료 배포의 기본 DB는 다음 경로다.

```text
DYNATUTOR_DB=/tmp/dynatutor_records.sqlite
```

이 경로는 서버 재시작/재배포 시 초기화될 수 있다. 앱은 사용자에게 이 점을 안내하고, 서버 저장 실패 시 브라우저 `localStorage`에 임시 기록을 남긴다. 중요한 기록은 export로 백업한다.

## API docs 공개 옵션

production에서는 기본적으로 `/docs`, `/redoc`, `/openapi.json`을 공개하지 않는다.

```text
DYNATUTOR_PUBLIC_DOCS=false
```

개발 환경에서는 기본 공개다. production에서 의도적으로 열고 싶을 때만 `DYNATUTOR_PUBLIC_DOCS=true`로 설정한다.

## CORS 최종 설정

초기 smoke test:

```text
DYNATUTOR_CORS_ORIGINS=*
```

최종 배포:

```text
DYNATUTOR_CORS_ORIGINS=https://your-app.vercel.app
```

끝에 `/`를 붙이지 않는다.

CORS 오류 체크리스트:

1. Vercel 실제 주소와 Render의 `DYNATUTOR_CORS_ORIGINS`가 정확히 같은가?
2. 주소 끝에 `/`가 붙지 않았는가?
3. http/https가 맞는가?
4. 프론트의 `NEXT_PUBLIC_DYNATUTOR_API_BASE`가 Render 백엔드 주소인가?
5. Render 서버가 sleep 상태에서 깨어나는 중은 아닌가?
6. 토큰 오류(401)와 CORS 오류를 혼동하고 있지 않은가?

## clarification / 부분 답변 / 이해한 조건 카드

Clarification에는 “왜 이 조건이 필요한지” 1~2문장 설명을 붙인다. 실패 응답은 “현재 정보로 가능한 것”과 “추가로 필요한 조건”을 분리해 보여준다.

프론트는 `앱이 이해한 조건` 카드를 표시한다. 사용자는 질량, 속도, 힘, 거리, 각도, 마찰 조건, requested outputs 등을 수정하고 “수정한 조건으로 다시 풀기”를 누를 수 있다. 수정값은 `canonical_patch`로 백엔드에 전달되어 diagnosis, selected solver, physical model, requested_outputs, verification이 수정 조건 기준으로 다시 계산된다.
