# Phase 54 — VisualizationScene v1.0 (Rapier2D 시각화, 정답 권위 분리)

## 계약 요약

- Public schema: `dynatutor.visualization_scene`, version `1.0`
- Response field: `SolveResponse.visualization_scene` (additive, optional, 기본 `null`)
- API schema contract: v7 (`phase42_api_schema_contract.json`, append-only)
- Definition: `backend/app/schemas/visualization_scene.py`
- Builder: `backend/engine/visualization/scene_builder.py` + `backend/engine/visualization/scenes/*`
- Simulation mode: **`kinematic_playback`** — 모든 운동은 backend typed 값에서 만든
  닫힌형(closed-form) motion program이며, 프론트엔드 Rapier2D world는 kinematic body의
  transform 재생에만 쓰인다. Rapier 솔버(중력·접촉·마찰 해석)는 어떤 수치도 만들지 않는다.

## 파이프라인 위치와 권위 경계

```
parse → model → route → solve/select → verify → answer consistency
  → apply_result_gate (유일한 강등 지점)
  → explanation projection / ExplanationTrace
  → attach_visualization_scene   ← Phase 54 (post-gate, additive, fail-open)
```

- `attach_visualization_scene`은 `response.visualization_scene` 한 필드만 쓴다.
- Scene 생성 실패는 어떤 경우에도 /solve 실패로 이어지지 않는다
  (`unavailable` scene 또는 `null`; 기존 답·풀이·검증·FBD는 그대로).
- 정답 권위: post-gate `answer`/`answers`/`verification`/fully-grounded
  `explanation_trace`. Scene의 `answer_overlay`는 delivered answer의 verbatim 투영이다.
- `authority` 블록은 `Literal` 타입으로 코드 강제된다:
  `answer_authority="backend"`, `visualization_authority="approximate"`,
  `grading=False`, `answer_selection=False`, `student_answer_overwrite=False`.
- 금지 사항(빌더가 하지 않는 것): 문제 자연어 재파싱, 표시 문자열 수치 추출,
  solver/verification 재실행, scene 결과로 answer 수정, unsupported를 ready로 표시.

## 지원 장면 (Phase 54)

| scene_type | source solver | 핵심 typed evidence | 비고 |
|---|---|---|---|
| `incline_block` | `incline_no_friction` | θ(deg known), post-gate `acceleration` | 정지 출발은 시각화 가정으로 명시 |
| `incline_block` | `incline_with_friction` | 위 + `friction_type=="kinetic"` **및** `displacement_direction=="down_slope"`(명시 typed), a>0 | solver evidence guard와 동일 gate. 현 NL extractor는 down_slope를 생성하지 않으므로 product NL 경로에서는 정직하게 unavailable |
| `mass_spring` | `spring_mass_vibration` | k·m known, post-gate ω/T/f | 진폭 미제시 시 시각화 전용 진폭 명시; 명시 진폭 A는 정확히 사용(배경만 스케일) |
| `pure_rolling` | `pure_rolling_energy` | h known, body_shape, post-gate `final_velocity` | 반지름 없으면 회전은 render-scale(schematic) |
| `collision_1d` | `collision_1d` | m1·m2·v1·v2 known, 충돌 유형 typed flag/e, post-gate `v1_after`/`v2_after` | timeline은 backend 전/후 속도 그대로; Rapier 접촉 해석 없음 |

### 명시적 deferred

- **단진자(pendulum)**: product solver/typed model/answer 계약이 존재하지 않아 보류.
  `engine/visualization/scenes/pendulum.py`는 항상 deferred `unavailable`을 반환하며
  `_SCENE_BUILDERS`에 연결되어 있지 않다. Phase 50 offline pendulum 검증 데이터는
  product 풀이가 아니므로 사용하지 않는다.
- **도르래(pulley)**: constraint 표현이 안정된 뒤 후속 장면.

## Schematic(시각화 전용) 값 규칙

실제 물리량이 아닌 값은 반드시 아래 중 하나로 표시된다.

- body의 `schematic_size: true` (경사면 길이, 블록/수레 크기, 초기 간격 등)
- motion segment의 `angular_schematic: true` (render 반지름 기반 회전)
- scene의 `schematic_notes[]` (진폭, 환산 ω, 시각화용 가속도 등 설명)

프론트엔드는 이런 값을 backend 계산값처럼 표시하면 안 된다.

## Fallback 정책

| 상황 | 결과 |
|---|---|
| `ok != True` (clarify/unsupported/실패) | `visualization_scene = null` |
| ok지만 미지원 solver | `status="unavailable"` + 사유 |
| ok지만 typed evidence 부족(예: 모호한 μ, 단위 불명) | `status="unavailable"` + 사유 |
| 빌더 예외 | `unavailable` scene, 그것도 실패하면 `null` (fail-open) |

## DTO 검증 규칙

- 모든 float는 유한값(NaN/Infinity 거부, `allow_inf_nan=False`)
- motion/force의 `body_id`는 실제 body 참조여야 함
- 같은 body의 motion segment는 시간 구간이 겹치면 안 됨
- `ready`는 bodies·motion·camera·timestep·answer_overlay 필수
- `unavailable`은 `fallback_reason` 필수, playback 재료 금지
- `schema`/`version`은 Literal로 고정

## 테스트

`backend/tests/test_phase54_visualization_scene.py`

- DTO schema/version/authority 코드 강제
- NaN/Infinity/잘못된 참조/버전 위조 거부
- 장면별 빌더 (4 장면 + branch)
- overlay == post-gate answers verbatim
- unsupported/partial/fail-open fallback
- scene 부착 전후 기존 필드 불변 (visualization_scene 제외 dump 비교)
- 단진자 deferred 명시

Capability registry: 구현된 5개 entry(경사면 2, 스프링, 구름, 충돌)의
`visualization_support.status = "rapier2d_kinematic_playback_v1"`; `dynamic_physics`는
독립 물리 시뮬레이션이 아니므로 `false`를 유지한다.
