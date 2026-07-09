# Routing Confusion & Accuracy Report

- units backend: **shim** _(shim: 정식 pint 환경에서 재실행 권장)_
- routing cases: 432 · negative cases: 60 · duration: 34.13s

## 핵심 지표

| 지표 | 값 |
|---|---|
| Routing 정확도 (올바른 solver 선택) | **100.0%** (432/432) |
| 수치 정답률 (gold 수치 보유 문항) | **100.0%** (127/127) |
| Negative 거절률 (못 푸는 문제를 거절) | **100.0%** (60/60) |
| 모호 케이스 (top1-top2 ≤ 8) | 0 |

## 상위 혼동 쌍 (재설계 우선순위)

| expected → selected | count |
|---|---|
| (혼동 없음) | - |

## Solver별 precision / recall

| solver | support | recall | precision |
|---|---|---|---|
| `collision_1d` | 5 | 100% | 100% |
| `constant_acceleration_1d` | 50 | 100% | 100% |
| `constant_force_work` | 58 | 100% | 100% |
| `coriolis_relative_motion` | 6 | 100% | 100% |
| `fixed_axis_rotation` | 5 | 100% | 100% |
| `impulse_momentum` | 8 | 100% | 100% |
| `incline_no_friction` | 60 | 100% | 100% |
| `incline_with_friction` | 8 | 100% | 100% |
| `plane_rigid_body_acceleration` | 6 | 100% | 100% |
| `plane_rigid_body_velocity` | 8 | 100% | 100% |
| `polar_kinematics` | 6 | 100% | 100% |
| `projectile_motion` | 70 | 100% | 100% |
| `pulley_atwood` | 58 | 100% | 100% |
| `pulley_table_hanging` | 8 | 100% | 100% |
| `pure_rolling_energy` | 59 | 100% | 100% |
| `relative_acceleration_translation` | 5 | 100% | 100% |
| `spring_energy_speed` | 5 | 100% | 100% |
| `work_energy_speed` | 7 | 100% | 100% |

## 모호 케이스 (gap ≤ 8) — '되묻기' 후보

없음 — 현재 선택은 점수 격차가 충분히 큼.

## 수치 오답

없음 — gold 수치 127문항 전부 tolerance 내 일치.

## Negative false-positive (환각성 오탐)

없음 — negative 60문항 전부 올바르게 거절.

## 검증 스위트 — 무고 오탐 & 오염 검출률(mutation sensitivity)

- 검증 대상(정답 결과): 243 · 역대입 커버 243 (100%)
- **무고 오탐(FP): 0** (0.0%) — 0이어야 함
- 오염 검출률: ×1.1 → **243/243** (100%) · 부호반전 → 162/243 (67%) · 단위교란 → 243/243 (100%)

| system_type | n | 역대입 커버 | FP | ×1.1 검출 | 부호 검출 | 단위 검출 |
|---|---|---|---|---|---|---|
| `collision_1d` | 5 | 5 | 0 | 5 | 5 | 5 |
| `constant_acceleration_1d` | 30 | 30 | 0 | 30 | 30 | 30 |
| `constant_force_work` | 47 | 47 | 0 | 47 | 0 | 47 |
| `coriolis_relative_motion` | 6 | 6 | 0 | 6 | 6 | 6 |
| `fixed_axis_rotation` | 5 | 5 | 0 | 5 | 5 | 5 |
| `impulse_momentum` | 8 | 8 | 0 | 8 | 8 | 8 |
| `particle_on_incline` | 18 | 18 | 0 | 18 | 18 | 18 |
| `plane_rigid_body_acceleration` | 6 | 6 | 0 | 6 | 6 | 6 |
| `plane_rigid_body_velocity` | 8 | 8 | 0 | 8 | 8 | 8 |
| `polar_kinematics` | 6 | 6 | 0 | 6 | 6 | 6 |
| `projectile_motion` | 50 | 50 | 0 | 50 | 42 | 50 |
| `pulley_atwood` | 15 | 15 | 0 | 15 | 15 | 15 |
| `pulley_table_hanging` | 8 | 8 | 0 | 8 | 8 | 8 |
| `pure_rolling_energy` | 14 | 14 | 0 | 14 | 0 | 14 |
| `relative_acceleration_translation` | 5 | 5 | 0 | 5 | 5 | 5 |
| `spring_energy` | 5 | 5 | 0 | 5 | 0 | 5 |
| `work_energy_speed` | 7 | 7 | 0 | 7 | 0 | 7 |

## 되묻기(clarification) 라우터

- 벤치마크 오발동(FP): **0** (풀리는 문제를 질문으로 막은 횟수 — 0이어야 함)
- 제작 모호 세트: 발동 14/14 · 규칙 일치 14 · 해소 성공 10/10
- negative 60건 중 질문 전환: 60 (거절 → 선택지 있는 대화)

| 문제 | 기대 규칙 | 발동 규칙 | 해소 |
|---|---|---|---|
| 30도 경사면 위 블록의 가속도를 구하라. | incline_friction_unknown | incline_friction_unknown | True |
| 경사각 25도 빗면에서 물체가 미끄러진다. 가속도는? | incline_friction_unknown | incline_friction_unknown | True |
| 블록이 도르래 줄에 연결된 채 30도 경사면 위에 놓여 있다. 가속도는? | pulley_topology_unknown | pulley_topology_unknown | - |
| 두 물체가 줄과 도르래로 연결되어 있다. 가속도를 구하라. | pulley_topology_unknown | pulley_topology_unknown | - |
| 30도 경사면 위에서 블록이 용수철에 연결되어 있다. 블록을 놓으면 속도는? | mixed_spring_conflict | mixed_spring_conflict | chained→missing_values |
| 공을 45도로 발사했다. 사거리는? | missing_values | missing_values | True |
| 스프링 상수 200N/m인 진동계의 주기를 구하라. | missing_values | missing_values | True |
| 질량 2kg와 3kg인 두 공이 정면 충돌한다. 충돌 후 속도는? | missing_values | missing_values | - |
| 평면강체에서 A와 B 사이 거리는 0.7m, 각속도는 3rad/s이다. B점 속도는? | rigid_missing_reference | rigid_missing_reference | True |
| 용수철 장치가 있다. 무엇을 구할 수 있을까? | unknown_with_evidence | unknown_with_evidence | chained→missing_values |
| 커브 도로가 있다. 이 상황을 설명하라. | unknown_with_evidence | unknown_with_evidence | chained→missing_values |
| 등가속도 상황이다. 무엇을 구할 수 있는가? | missing_values | missing_values | - |
| 물체가 구르는 상황이다. 설명하라. | evidence_confirm | evidence_confirm | chained→missing_values |
| m1=10kg가 30도 경사면 위에 있고 m2=1kg가 매달려 있다. 가속도는? | incline_hanging_candidate | incline_hanging_candidate | True |

## 출처(provenance) — 배경 문장 주입 검출

- 클린 텍스트 무고 플래그: **0** (0이어야 함)
- 주입 성사 999건 중 검출 **999** (100%)

| 주입 문장 | 성사 | 검출 | 답 보류(사용 심볼) | 답 유지+경고(미사용) |
|---|---|---|---|---|
| 배경 질량(m) | 215 | 215 | 38 | 164 |
| 배경 시간(t) | 205 | 205 | 5 | 200 |
| 배경 힘(F) | 183 | 183 | 37 | 146 |
| 배경 높이(h) | 221 | 221 | 42 | 179 |
| 배경 각도(theta) | 175 | 175 | 47 | 128 |

## 교란(perturbation) 강건성 — 라벨 보존 변형 후 불변량 유지

| 변형 | 적용 | routing 깨짐 | outputs 표류 | 수치 깨짐 | 파손율 |
|---|---|---|---|---|---|
| 동의어: 구하라→계산하라 | 126 | 0 | 0 | 0 | 0.0% |
| 동의어: 경사면→빗면 | 68 | 0 | 0 | 0 | 0.0% |
| 동의어: 마찰 없는→매끄러운 | 60 | 0 | 0 | 0 | 0.0% |
| 동의어: 블록→물체 | 68 | 0 | 0 | 0 | 0.0% |
| 동의어: 스프링→용수철 | 5 | 0 | 0 | 0 | 0.0% |
| 동의어: 등가속도→일정한 가속도 | 0 | 0 | 0 | 0 | - |
| 동의어: 속력→빠르기 | 12 | 0 | 0 | 0 | 0.0% |
| 동의어: 매달려→걸려 | 58 | 0 | 0 | 0 | 0.0% |
| 동의어: 충돌한다→부딪친다 | 0 | 0 | 0 | 0 | - |
| 동의어: 정지 상태에서→가만히 있다가 | 50 | 0 | 0 | 0 | 0.0% |
| 동의어: 수평 방향으로→수평하게 | 0 | 0 | 0 | 0 | - |
| 표기: N도→N° | 130 | 0 | 0 | 0 | 0.0% |
| 표기: 단위 유니코드(㎏ ㎞ ㎧) | 194 | 0 | 0 | 0 | 0.0% |
| 표기: 정수→소수(10→10.0) | 1 | 0 | 0 | 0 | 0.0% |
| 표기: km/h→시속 | 0 | 0 | 0 | 0 | - |
| 띄어쓰기: '10 m/s'→'10m/s' | 6 | 0 | 0 | 0 | 0.0% |
| 어순: 질문 먼저 | 335 | 0 | 0 | 0 | 0.0% |
| 앞 filler 문장 추가 | 432 | 0 | 0 | 0 | 0.0% |
| 뒤 filler 문장 추가 | 432 | 0 | 0 | 0 | 0.0% |
| 방해문: 무관 숫자(온도) | 432 | 0 | 0 | 0 | 0.0% |
| 방해문: 동음이의어 '줄'(대기열) | 432 | 0 | 0 | 0 | 0.0% |
| 방해문: 동음이의어 '일'(task) | 432 | 0 | 0 | 0 | 0.0% |
| 방해문: 트랩 키워드 '수평면' | 432 | 0 | 0 | 0 | 0.0% |
| 방해문: 무관 거리 숫자 | 432 | 0 | 0 | 0 | 0.0% |
