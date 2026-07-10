# Goal: Phase 42 — Baseline, Scope Matrix, and Release Contracts

## 목적

구조를 바꾸기 전에 현재 동작, 지원 동역학 범위, 성능, API 계약을 고정한다.

## 핵심 문제

현재 테스트가 많아도 다음이 명확하지 않으면 대규모 개선 후 무엇이 좋아졌거나 나빠졌는지 판단하기 어렵다.

- 정확히 어떤 문제를 지원하는가
- 각 문제에 어떤 입력과 출력이 필요한가
- 파서·라우터·솔버·검증 중 어디가 실패했는가
- 현재 false-solve 비율이 얼마인가
- API와 학생용 풀이 계약이 무엇인가
- 속도와 테스트 실행 시간이 얼마인가

## 구현 범위

### 1. Dynamics Capability Matrix

현재 `SolverRegistry`와 각 solver의 `match()` 및 요구 입력을 조사해 machine-readable matrix를 만든다.

각 항목:

```text
system_type
subtypes
required_inputs
optional_inputs
requested_outputs
assumptions
analytic_solver
validators
numeric_support
chrono_support
visualization_support
known_limitations
```

### 2. 기준선 테스트 보고서

최소 다음을 기록한다.

- 빠른 백엔드 테스트 통과/실패/제외
- 전체 테스트 통과/실패/제외
- 한국어 benchmark 정확도
- route confusion 개수
- clarification precision/recall을 계산할 수 있으면 기록
- 대표 API 응답 snapshot
- 평균 및 P95 실행 시간
- 외부 의존성 없는 환경의 결과

### 3. Golden Dynamics Cases

현재 지원 영역별로 검증된 대표 문제를 만든다.

최소 범위:

- 등가속도
- 포물선
- 경사면
- 마찰
- 도르래 3종 이상
- 충돌
- 일–에너지
- 충격량–운동량
- 순수 구름
- 고정축 회전
- 평면 강체 속도/가속도
- 극좌표 또는 코리올리
- 1자유도 진동

각 case는 다음을 포함한다.

- 원문
- canonical expected facts
- expected route
- expected output
- independent expected value
- tolerance
- expected status
- 근거 출처 또는 손계산 기록

### 4. API 및 schema 계약

다음을 snapshot 또는 schema test로 고정한다.

- `CanonicalProblem`
- `SolverResult`
- `VerificationReport`
- `/solve` 주요 응답
- clarification 응답
- unsupported 응답

## 하지 않을 일

- solver 알고리즘을 변경하지 않는다.
- 기존 모델을 typed model로 전환하지 않는다.
- Chrono를 구현하지 않는다.
- benchmark 실패를 고치기 위해 기대값을 임의 변경하지 않는다.

## Acceptance criteria

- machine-readable capability matrix가 있다.
- 최소 30개의 독립 golden case가 있다.
- 각 golden case는 파서, route, answer 기대값을 구분한다.
- 현재 false-solve와 clarification 기준선을 알 수 있다.
- API schema regression test가 있다.
- 실행 시간 기준선이 기록된다.
- 기존 빠른 테스트 결과가 나빠지지 않는다.

## 권장 테스트

```bash
bash scripts/check_backend_fast.sh
python -m pytest backend/tests -q
bash scripts/check_frontend_metadata.sh
```

## PR 보고

- 현재 지원 범위
- 기준선 수치
- 가장 큰 오답 유형
- 가장 큰 route confusion
- 성능 기준선
- 다음 단계가 유지해야 할 계약
