# Goal: Phase 51 — Real PyChrono Independent Validation

## 목적

현재 `manual_required` 훅을 실제 PyChrono 강체 시뮬레이션으로 전환한다.

## 구현 대상

권장 순서:

1. rolling sphere
2. rolling disk
3. incline friction
4. collision restitution
5. massive pulley

각 사례는 별도 sub-PR로 나눌 수 있다.

## 공통 원칙

- PyChrono는 일반 runtime dependency가 아니다.
- 일반 API는 PyChrono 없이 작동한다.
- 결과가 해석값을 자동으로 덮어쓰지 않는다.
- 동일한 typed model 또는 명확한 adapter input을 사용한다.
- Chrono 장면의 추가 모델링 가정을 report한다.
- fixed step, solver, contact model, tolerance, version을 기록한다.

## Common ChronoResult

```text
case_id
status
observable
value
unit
chrono_version
solver
contact_method
time_step
duration
initial_conditions
final_state
constraint_errors
invariant_errors
warnings
artifacts
```

## Rolling sphere/disk

검사:

- COM 최종 속도
- angular velocity
- `v - Rω`
- energy balance
- sphere/disk inertia 차이에 따른 결과 구분

## Incline friction

검사:

- acceleration from trajectory
- contact maintained
- friction direction
- stick/slip state
- normal force

Chrono 접촉 마찰 모델과 교과서 Coulomb 모델의 차이를 문서화한다.

## Collision restitution

검사:

- post-impact velocities
- momentum error
- realized coefficient of restitution
- contact event timing

목표 e와 실제 contact model의 realized e가 다를 수 있음을 보고한다.

## Massive pulley

검사:

- mass acceleration
- pulley angular acceleration
- no-slip/string constraints
- energy balance
- tension difference

## 환경

- 별도 requirements/environment 문서
- 설치 확인 명령
- strict mode
- JSON/Markdown report
- 미설치 시 skipped
- 전용 CI 또는 manual/nightly runner

## Acceptance criteria

- 다섯 simulator가 실제 값 또는 명확한 skipped/error를 반환한다.
- `manual_required`가 제거된다.
- PyChrono 환경에서 자동 검증 가능하다.
- 기본 환경에서 import failure가 앱을 깨뜨리지 않는다.
- 각 사례가 주 observable 외에 최소 하나의 invariant/constraint를 검사한다.
- 해석값과 차이가 report에 남는다.
