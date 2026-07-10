# Goal: Phase 49 — Solver Consistency, Independent Oracles, and Metamorphic Tests

## 목적

수동 공식, 생성 방정식, symbolic solver가 같은 오류를 공유하지 않도록 독립적인 검증 자료와 변환 기반 테스트를 추가한다.

## 1. Solver Path Roles

각 문제 유형에 다음을 선언한다.

```text
student_answer_path
secondary_analytic_path
numeric_validation_path
external_validation_path
fallback_path
```

한쪽 결과가 다른 쪽을 조용히 덮어쓰지 않는다.

## 2. Independent Dynamics Oracle Set

기존 엔진 출력으로 기대값을 생성하지 않는다.

oracle 출처:

- 손으로 독립 유도한 closed form
- 검증된 교재 예제
- 단순 특수해
- 보존법칙
- 별도 CAS 계산
- 외부 수치 엔진

각 case에는 식 유도 또는 출처 note를 남긴다.

권장 최소 60개:

- 각 주요 family 4~6개
- 경계값
- 대칭값
- 모호성/해 없음
- 수치적으로 민감한 사례

## 3. Metamorphic Tests

정답 숫자를 모두 미리 알지 못해도 반드시 성립해야 하는 관계를 검사한다.

### 단위 불변성

- m ↔ cm
- kg ↔ g
- km/h ↔ m/s
- deg ↔ rad

### 좌표 변환

- x축 반전 시 vector 성분 부호 변화
- 동일 물리량의 크기 불변
- origin translation에 속도 관계가 불필요하게 변하지 않음

### 물리적 극한

- 마찰 0 → 무마찰 식
- pulley inertia 0 → ideal pulley
- restitution 0 → perfectly inelastic relation
- restitution 1 → elastic relation
- damping 0 → undamped oscillator
- rolling inertia factor 변화에 따른 단조성

### 대칭성

- 동일 질량 교환
- 물체 라벨 변경
- 충돌 문제에서 index 교환과 좌표 반전
- 줄 연결 물체 순서 변경

### 입력 교란

- 무관한 문장 추가
- 표현 순서 변경
- 동의어 변경
- rounding 수준 변경

## 4. Manual vs Generated Equation Consistency

우선 적용:

- incline
- pulley
- collision
- rolling
- work-energy
- fixed-axis rotation

비교:

- 값
- 단위
- 부호
- 가정
- 해 개수
- 모호성
- 사용한 식

## 5. Mutation Testing

가능하면 중요한 sign, coefficient, unit conversion, constraint를 의도적으로 변형해 테스트가 잡는지 확인한다.

## Acceptance criteria

- 독립 oracle case가 최소 60개다.
- metamorphic family가 최소 15개다.
- 주요 6개 family에서 두 analytic path를 비교한다.
- 불일치는 구조화 report로 남는다.
- 엔진 출력으로 oracle 기대값을 자동 생성하지 않는다.
- 중요 식 변형을 테스트가 실제로 탐지한다.
