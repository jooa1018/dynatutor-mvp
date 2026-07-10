# Goal: Phase 48 — Dynamics Invariants, Constraint Checks, and Numerical Conditioning

## 목적

답의 차원과 단순 타당성뿐 아니라 동역학 법칙과 수치 안정성을 공통 검증한다.

## validator 적용 원칙

모든 문제에 모든 검사를 적용하지 않는다.  
각 capability가 적용 가능한 validator 목록을 선언한다.

## 공통 검증 영역

### 1. 방정식 잔차

- 원래 지배 방정식
- 생성 방정식
- constraint equation
- 초기조건

### 2. 운동학 제약

- 줄 길이 일정
- 연결된 물체의 속도·가속도 관계
- 순수 구름 `v = Rω`
- 평면 강체 상대 속도/가속도 관계
- 회전좌표계 변환 관계

### 3. 운동량과 충격량

적용 조건이 만족될 때:

- 총 선운동량
- 특정 축 운동량
- 충격량–운동량
- 충돌 전후 운동량
- 반발계수 관계

### 4. 에너지와 일

적용 조건에 따라:

- 보존력만 있을 때 기계적 에너지
- 마찰 일
- 외력 일
- 회전 운동에너지
- 스프링 에너지
- 감쇠계 에너지 감소 방향

### 5. 힘과 접촉

- 정상력 음수 여부
- 접촉 유지/이탈
- 정지마찰 요구량 ≤ 최대 정지마찰
- 운동마찰 방향
- 장력 비음수 조건
- slack string 가능성
- 도르래 무미끄럼

### 6. 극한값과 특수값

- μ → 0
- I → 0
- e → 0 또는 1
- 동일 질량
- θ → 0
- 초기속도 → 0
- 감쇠 → 0

### 7. 수치 조건과 민감도

다음을 감지하고 report한다.

- singular/near-singular Jacobian
- ill-conditioned linear system
- 거의 상쇄되는 값
- 작은 입력 변화에 큰 출력 변화
- tolerance에 민감한 후보 선택
- 근이 서로 매우 가까운 경우

가능하면:

- condition estimate
- local perturbation sensitivity
- warning threshold

를 제공한다.

## tolerance policy

중앙 `TolerancePolicy`를 만든다.

- abs_tol
- rel_tol
- residual_tol
- constraint_tol
- conservation_tol
- near_zero_tol
- engine-specific tolerance

## VerificationReport 확장

검사마다:

```text
check_id
category
status
observed
expected
absolute_error
relative_error
tolerance
message
evidence
```

## 필수 테스트

- 에너지 보존 정상/위반
- 비보존력 존재 시 올바른 에너지 변화
- 충돌 운동량과 반발계수
- rolling constraint
- string constraint
- negative normal force
- static friction transition
- ill-conditioned equation
- near-zero comparison
- tolerance 경계
- 적용 불가능한 검사를 잘못 실패 처리하지 않음

## Acceptance criteria

- 최소 5개 동역학 invariant validator가 실제 solver에 연결된다.
- validator 적용 조건이 명시된다.
- condition/sensitivity warning이 있다.
- tolerance가 중앙화된다.
- report가 관측값과 오차를 구조적으로 제공한다.
- false positive를 mutation/regression harness로 점검한다.
