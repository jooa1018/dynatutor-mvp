# Goal: Phase 54 — Rapier2D Visualization, Isolated from Answer Authority

## 목적

동역학 문제의 움직임, 힘, 충돌, 방향을 브라우저에서 직관적으로 보여준다.

## 절대 원칙

Rapier2D는 시각화 전용이다.

- 최종 답 결정 금지
- 채점 금지
- 백엔드 해석값 덮어쓰기 금지
- WASM 실패가 풀이 실패로 이어지면 안 됨

## 흐름

```text
Typed DynamicsModel
 → VisualizationScene DTO
 → Rapier2D adapter
 → browser animation
```

프론트엔드가 자연어를 다시 해석하지 않는다.

## 1차 장면

- 경사면 블록
- 1D 충돌
- 질량-스프링
- 순수 구름
- 단진자

도르래는 constraint 표현이 안정된 뒤 후속 장면으로 추가한다.

## VisualizationScene

- bodies/shapes
- initial transforms
- velocities
- forces and moment arrows
- constraints
- labels
- coordinate axes
- time scale
- camera bounds
- backend answer overlay
- simplifying assumptions
- scene version

## 재현성

- fixed time step
- reset
- pause/play
- slow motion
- deterministic option
- scene JSON export/import

## 교육적 표시

- 양의 방향
- 속도와 가속도 화살표
- 힘 자유물체도 overlay
- 충돌 전후 상태
- backend 계산값과 animation approximation 구분
- 단순화 가정

## fallback

- WASM 로드 실패
- 모바일 성능 부족
- 지원되지 않는 scene
- accessibility reduced-motion

어떤 경우에도 텍스트 풀이와 정답은 유지한다.

## 필수 테스트

- DTO schema
- 장면 생성
- reset 재현성
- backend overlay
- WASM fallback
- reduced motion
- 프론트엔드 build
- 기존 결과 카드 회귀

## Acceptance criteria

- 최소 4개 장면이 동작한다.
- typed model에서 DTO가 생성된다.
- 정답 권위가 백엔드에 있음을 코드 구조로 보장한다.
- fallback 시 풀이가 정상 유지된다.
- backend 값과 animation 근사값이 명확히 구분된다.
