# Phase 33: 게이트 통합 · 순환 import 해소 · 역대입 100% 커버

## 1. ok=False 강등 단일 게이트 (`engine/verification/gate.py`)

Phase 28~31에서 services.py에 분산됐던 강등 정책 3갈래를 한 곳으로 통합.
- `gate_decision(errors)` 순수 함수: 강등 여부 + 사유 (우선순위: 필수 answer 누락 > 출처 의심 > 물리 검증 일반)
- solver 자체 실패(missing_info)의 기존 사유는 보존 — 게이트는 성공 주장을 끌어내리는 장치.
- 회귀 방지 테스트: `solve_problem` 내 인라인 `ok = False`가 다시 생기면 실패하는 소스 검사 테스트 포함.
- 부수 변경(개선): warning이 error와 공존할 때도 이제 유지됨(이전엔 error 시 warning 소실).

## 2. equation_generators ↔ model_builder 순환 import 해소

- 원인: `model_builder/builder.py`의 모듈 수준 역방향 import. registry를 먼저 import하면 ImportError.
- 수정: 해당 edge를 사용 지점 지연 import로 이동. **하니스·테스트의 우회 guard 전부 제거**해 숨은 의존 없음을 증명.
- 회귀 테스트: fresh subprocess에서 registry 최우선 import 성공 검증.

## 3. 역대입 커버리지 87% → 100% (243/243)

미커버 5개 유형(polar, coriolis, rigid velocity/acceleration, relative translation)에
answers 항목(성분 포함) 추가 + knowns-앵커 잔차 검사기 6종 등록.

| 지표 | 이전 | 이후 |
|---|---|---|
| 역대입 커버 | 212/243 | **243/243** |
| ×1.1 오염 검출 | 212/243 | **243/243 (100%)** |
| 단위 교란 검출 | 231/243 | **243/243 (100%)** |
| 무고 오탐 | 0 | **0 유지** |

균일 스케일 오염이 성분-크기 닫힘식(closure)만으로는 안 잡히므로, 모든 유형에
knowns 앵커식(v_θ−rθ̇, a_C−2ωv_rel, a_B−(a_A+a_rel) 등)을 최소 1개 포함.

### 과정에서 발견·수정한 실제 오답 버그

`relative_acceleration_translation`: 추출 정규식의 무제한 창(`[^\d-]*`)이
"상대가속도 **문제에서** ... aA=1"에 매치되어 arel=1(오파싱) → a_B=2.0(오답, 정답 3.0).
**이 유형은 gold 수치가 없어 벤치마크가 한 번도 잡지 못했음** — "미커버 유형에
오답이 숨는다"의 실증. vrel/aB 계열 동일 취약 창 3곳을 12자로 제한. 회귀 테스트 추가.

## 검증

- 전체 스윕: **246 테스트 / 0 실패** (pint·pydantic·fastapi stub + subprocess PYTHONPATH stub)
- 하니스 전 지표 그린 (위 표 + routing/수치/negative/교란/출처 무변동)
- 신규 회귀 테스트: 게이트 4종, import 순서 1종, arel 버그 1종, 고급 유형 커버 1종
