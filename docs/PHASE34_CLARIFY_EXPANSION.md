# Phase 34: 되묻기 라우터 확장

기존 5규칙(ambiguous_pulley, mixed_spring, mixed_collision, incline_friction, missing_values)에
**증거 점수기 기반 일반화 + 신규 규칙 4종**을 추가. 원칙 유지: 되묻기는 solver 실패 시에만
발동(정상 풀이 불가침), 모든 patch는 화이트리스트 검증, 선택 결과는 검증·출처 레이어를 그대로 통과.

## 신규 구성요소

### 증거 점수기 (`engine/routing/evidence.py`)
캐스케이드가 유형을 확정하기 전 텍스트에 공존한 유형 단서를 계량:
11개 패밀리(경사면/도르래/용수철/충돌/포물선/일-에너지/회전/충격량/커브/구름/등가속도),
패밀리 flag 적중 +2, 시그니처 known +1, floor=2 (흔한 심볼 오발동 방지).

### 신규 규칙 4종 (발동 순서 내 위치)
| 규칙 | 신호 | 동작 |
|---|---|---|
| `incline_hanging_candidate` | 경사면+매달림인데 줄/도르래 미언급 | "연결된 구성인가요?" — 연결(도르래 모형)/단독(경사면) 원탭. 기존 정적 거절을 대체 |
| `rigid_missing_reference` | 평면강체 속도에서 vA·고정조건 부재 | "A점 고정인가요?" — vA=0 원탭 / vA 입력. **negatives 미커버 5건 전부 해소** |
| `unknown_with_evidence` | 유형 unknown + 단서 flag 존재 | 후보 모형 제시 (missing_values는 unknown을 스킵하므로 필수) |
| `evidence_conflict` / `evidence_confirm` | **최후 안전망**(missing_values 뒤) | 타 패밀리 단서 공존 시 모형 선택 / solver 미연결 중간 타입(예: rolling)엔 확인형 1옵션 |

배치 원칙: 일반 규칙이 missing_values의 "값 입력" 질문을 **가로채지 않도록** 안전망은 맨 뒤.
unknown 전용 규칙만 그 앞(어차피 missing_values가 스킵하는 영역).

### 옵션 dry-run
제시 전 각 옵션 patch를 사본에 적용해 (a) solver 매치 또는 (b) 후속 되묻기 연쇄 존재를 확인.
"선택했는데 그것도 안 됨"을 구조적으로 차단. 3단 연쇄(유형→모형→값) 동작:
`용수철 장치가 있다` → unknown_with_evidence → spring_energy 확정 → missing_values(k, x, m).

### 부수 확장
- `_MISSING_TO_SYMBOL`: 각속도 ω/각가속도 α/상대속도/상대가속도 + 등가속도 3변수(v0·a·t 복수 옵션, 문자열당 다중 매핑 허용)
- 화이트리스트: system_type +4종(impulse/rotation/rolling/curve 대표), known +6심볼(vA·aA·ω·α·vrel·arel)

## 측정 (하니스 clarify 섹션)

| 지표 | 이전 | 이후 |
|---|---|---|
| 벤치마크 FP (풀리는 문제에 되묻기) | 0 | **0** |
| crafted 발동·규칙 일치 | 8/8 | **14/14** |
| 옵션 resolve 왕복(연쇄 포함) | 5/5 | **10/10** |
| **negatives → 질문 전환** | 55/60 | **60/60** |

negatives 규칙 분포: missing_values 40 · pulley_topology 15 · rigid_missing_reference 5.
routing/수치/교란/검증/출처 전 지표 무변동. 전체 스윕 257 테스트 0 실패.

## 정직한 한계
- `evidence_conflict`(진짜 혼합 안전망)의 자연 발동은 희소 — 기존 특화 규칙과 missing_values가
  대부분 먼저 받는다(설계 의도). 합성 witness 단위 테스트로 로직만 보증.
- 증거 패밀리에 없는 유형(수직원, 극좌표 등 고급 유형)은 일반 규칙의 옵션으로 제시되지 않음 —
  해당 유형은 자체 missing_info 경로에 의존.
- 기존 `test_incline_hanging_candidate...` 테스트의 정적 거절 문구 단언을 되묻기+원탭 resolve
  단언으로 갱신(동작 개선에 따른 의도적 변경).
