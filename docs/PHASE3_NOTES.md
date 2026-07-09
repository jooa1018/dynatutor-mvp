# Phase 3 Notes

## 이번 단계의 목표

Phase 3의 목표는 앱이 단순 계산기처럼 보이지 않게 만드는 것이었습니다. 그래서 다음 세 가지를 중심으로 강화했습니다.

```text
FBD 간단 도식
단위 검산
에너지/진동/커브 solver 확장
```

## 추가된 solver

- `work_energy_speed`
- `spring_mass_vibration`
- `spring_energy_speed`
- `flat_curve_friction`
- `banked_curve_no_friction`

## FBD 도식

`engine/visualization/fbd.py`에서 문제 유형별 SVG를 생성합니다. 지금은 개념도 수준입니다.

지원 도식:

- 경사면 블록
- 수평면-도르래
- 수직 원운동
- 순수 구름
- 스프링-질량계

## 단위 검산

`engine/units/dimensions.py`에서 결과 단위가 미지수 유형과 맞는지 확인합니다.

예:

```text
velocity → m/s
acceleration → m/s²
work → J
angular_frequency → rad/s
period → s
frequency → Hz
```

## 설명층

`engine/explanation.py`는 LLM을 붙이기 전 단계의 안전한 설명층입니다. 나중에 LLM이 들어오면 이 요약과 solver 결과를 기반으로 말투만 부드럽게 바꾸게 할 수 있습니다.

## 아직 남은 한계

- SVG FBD는 정확한 기하를 반영하지 않는 개념도입니다.
- 단위 검산은 완전한 단위 대수 시스템이 아니라 대표 출력 단위 확인 수준입니다.
- 스프링 solver는 감쇠/외력 없는 1자유도 기본 모델만 지원합니다.
- 커브 solver는 기본형만 지원합니다.
- PyDy는 아직 직접 호출하지 않습니다.
