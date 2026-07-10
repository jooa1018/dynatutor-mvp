# Goal: Phase 50 — SymPy Mechanics and SciPy Numerical Simulation

## 목적

현재 symbolic blueprint를 실제 시간 적분 경로로 완성하고, 해석 솔버를 독립적으로 검증한다.

## 1차 모델

- simple pendulum
- mass-spring-damper

2차 모델:

- particle on rotating rod
- planar rigid body rotation
- connected particles spring

## 목표 흐름

```text
Typed DynamicsModel
 → SymPy Mechanics derivation
 → mass matrix and forcing
 → lambdified numeric functions
 → first-order state system
 → scipy.solve_ivp
 → NumericTrajectory
 → invariant and analytic comparison
```

## NumericSimulationSpec

- model_id
- state variables
- parameters and units
- initial state
- t_start/t_end
- evaluation grid
- integration method
- rtol/atol/max_step
- event definitions
- random seed if applicable
- model/schema version

## NumericSimulationResult

- status
- time
- states
- observables
- solver diagnostics
- nfev/njev
- invariant drift
- constraint violation
- analytic error
- warnings

## 수치 안전성

- mass matrix singularity
- invalid initial condition
- integration failure
- event handling
- runaway state
- NaN/Inf
- stiffness warning
- overly large energy drift

## 기본 검증

### 단진자

- 작은 각도 주기
- 에너지 보존
- 정지 equilibrium
- 큰 각도에서 small-angle 식과 차이 보고

### 질량-스프링-댐퍼

- 무감쇠 해석해
- 감쇠 에너지 감소
- under/critical/over damping
- 강제진동은 별도 후속 범위로 둘 수 있음

## 성능 분리

- 일반 `/solve` 요청에서 실행하지 않는다.
- 명시적 validation 또는 offline 명령으로 실행한다.
- 짧은 numeric smoke test와 긴 accuracy test를 분리한다.

## PyDy

PyDy가 있으면 선택적으로 `System`을 구성하되, 핵심 수치 경로는 SciPy로 동작해야 한다.

## Acceptance criteria

- 최소 2개 모델이 실제 trajectory를 반환한다.
- solver 설정과 버전이 기록된다.
- 에너지/해석해/constraint diagnostics가 있다.
- 수치 실패가 명시적 상태로 나온다.
- 일반 학생용 빠른 경로 성능을 악화시키지 않는다.
- PyDy 미설치 환경에서도 기본 기능이 정상이다.
