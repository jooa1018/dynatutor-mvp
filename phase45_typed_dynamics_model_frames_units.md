# Goal: Phase 45 — Typed DynamicsModel, Coordinate Frames, Vectors, and Units

## 목적

현재 문자열 중심 PhysicalModel을 외부 엔진과 공통 validators가 안전하게 사용할 수 있는 typed dynamics model로 점진 전환한다.

## 현재 문제

`PhysicalForce.direction`, `axis`, `magnitude_expr`, 제약 방정식 등이 문자열이면 다음에 취약하다.

- 부호와 방향 혼동
- 좌표축 반전
- 벡터 합
- 모멘트 계산
- 구속조건 잔차 평가
- 단위/차원 검사
- Chrono/SciPy 어댑터 재사용

## 1차 범위

대표 vertical slice 3개를 선택한다.

권장:

1. 마찰 경사면
2. 반발계수 1D 충돌
3. 질량 있는 도르래

이 세 문제는 힘, 접촉, 운동량, 회전관성, 줄 제약을 골고루 포함한다.

## 핵심 타입

### QuantityValue

```text
symbol
magnitude
unit
dimension
source_fact_id
uncertainty
```

### Vector2

```text
x
y
frame_id
dimension
```

### CoordinateFrame

```text
origin
basis_x
basis_y
angular_positive
parent_frame
transform
```

### Body

- particle
- rigid_body_2d
- fixed_body
- mass
- center of mass
- inertia about COM
- geometry metadata

### Force and Moment

- kind
- body
- application point
- vector
- constitutive relation
- active interval/state

### Constraint

- geometric
- kinematic
- contact
- string length
- rolling no-slip
- revolute/fixed-axis
- prescribed motion

계산용 constraint는 SymPy expression 또는 callable residual로 접근 가능해야 한다.

## 단위 정책

- 입력에서는 Pint 또는 기존 unit parser로 SI 변환한다.
- typed model에는 dimension metadata를 유지한다.
- 계산식 생성 전후 차원 검사를 수행한다.
- 각도는 dimensionless이지만 degree/radian 변환을 명시적으로 처리한다.
- 표시용 unit과 내부 SI unit을 분리한다.

전 계산을 즉시 Pint Quantity로 바꾸는 것이 위험하면, 수치값 + dimension metadata 방식으로 단계적으로 전환한다.

## 좌표계 정책

- 모든 벡터는 frame을 가진다.
- “경사면 아래 방향” 같은 자연어는 frame basis로 변환된다.
- angular positive convention을 기록한다.
- 다른 body에 다른 local axis를 사용할 수 있다.
- 학생용 표시는 선택한 좌표계에서 생성한다.

## compatibility

기존 `PhysicalModel.to_dict()`와 학생용 summary를 유지할 adapter를 만든다.

## 필수 테스트

- 좌표축 반전 시 scalar/vector 결과 부호 일관성
- frame 변환 round-trip
- 힘 합과 모멘트 계산
- degree/radian 변환
- dimension mismatch 거부
- 줄 길이 constraint residual
- rolling constraint `v - Rω`
- 세 vertical slice의 기존 답 유지
- typed → legacy serialization

## Acceptance criteria

- 대표 3개 문제에서 typed model이 실제 solver 또는 validator에 사용된다.
- 내부 물리 판정이 자유 문자열 방향 비교에 의존하지 않는다.
- 벡터와 constraint에 frame과 dimension 정보가 있다.
- 계산용 식과 표시용 문자열이 분리된다.
- 기존 응답과 기존 지원 문제는 유지된다.
- 외부 엔진 자료구조에 종속되지 않는다.
