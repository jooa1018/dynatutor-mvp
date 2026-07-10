# Goal: Phase 46 — Solver Routing Confidence, Capability Checks, and Clarification

## 목적

`SolverRegistry.select()`가 상위 점수 하나를 무조건 선택하는 구조를 개선하고, 경합과 정보 부족을 안전하게 처리한다.

## 현재 문제

현재 registry는 match 결과를 점수순으로 정렬한 뒤 첫 번째를 선택한다.

이 방식은 다음 상황에 취약하다.

- 상위 두 solver 점수가 비슷함
- solver가 요구하는 입력이 없음
- 여러 유형의 키워드가 섞임
- generic solver가 specific solver를 이김
- 미지원 문제를 가장 비슷한 solver가 가져감

## 목표 흐름

```text
CanonicalProblem
 → route candidates
 → capability requirement check
 → evidence and contradiction check
 → calibrated score and margin
 → select | clarify | unsupported
```

## 구현 요구사항

### 1. RouteCandidate

```text
solver_id
family
raw_score
normalized_score
evidence
missing_requirements
contradictions
supported_outputs
risk_flags
```

### 2. 필수 입력 검사

capability matrix와 연결해 solver match 이후가 아니라 선택 이전에 확인한다.

예:

- massive pulley에는 `m1`, `m2`, `I`, `R`
- projectile range에는 launch speed와 angle 또는 동등 정보
- friction mode에는 coefficient와 motion tendency 정보

### 3. margin 정책

- top-1과 top-2 차이가 작으면 임의 선택 금지
- 서로 다른 family가 경합하면 clarification
- 같은 family의 subtype 경합은 필요한 구분 정보를 질문
- 명확한 generic fallback이 있는 경우에도 warning 기록

threshold는 benchmark로 보정하고 중앙 설정에서 관리한다.

### 4. requested output compatibility

solver가 사용자가 요구한 출력값을 실제로 제공할 수 있는지 확인한다.

### 5. unsupported gate

현재 동역학 범위를 벗어나거나 3D/변형체/복잡한 비선형 접촉이 필요한 문제를 명확히 unsupported로 처리한다.

## clarification 품질

질문은 “정보가 부족합니다”가 아니라 필요한 값을 구체적으로 묻는다.

예:

- 정지마찰계수와 운동마찰계수 중 어떤 값인가요?
- 도르래 자체의 질량 또는 관성모멘트를 무시하나요?
- 충돌 후 두 물체가 붙나요, 아니면 반발계수 값이 있나요?

## 필수 테스트

- top-1/top-2 박빙
- generic vs specific solver
- mixed incline + pulley
- projectile output별 요구 입력 차이
- friction state ambiguity
- unsupported 3D problem
- irrelevant sentence 추가 시 route 불변
- 단위 변환 시 route 불변
- paraphrase 시 route 일관성
- 기존 명확한 문제의 불필요 clarification 증가 방지

## Acceptance criteria

- route 결과가 후보 목록과 이유를 포함한다.
- 첫 번째 점수만으로 선택하지 않는다.
- score margin과 필수 입력이 선택에 반영된다.
- clarification과 unsupported가 구분된다.
- false route가 기준선보다 감소한다.
- unnecessary clarification이 기준선보다 악화되지 않는다.
