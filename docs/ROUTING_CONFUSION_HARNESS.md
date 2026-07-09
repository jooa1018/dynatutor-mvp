# Routing Confusion & Accuracy Harness

오탐(잘못된 solver 선택)·오답(틀린 수치)·환각(못 푸는 문제를 푼다고 주장)을 숫자로 보는 진단 도구입니다. 엔진 재설계는 이 리포트를 보면서 데이터 기반으로 진행합니다.

## 실행

```bash
cd backend
python tools/routing_confusion_report.py            # 전체 (432 routing + 60 negative + 9 교란)
python tools/routing_confusion_report.py --limit 50 # 빠른 패스
python tools/routing_confusion_report.py --gap 10   # 모호 판정 임계값 조정
```

출력: `backend/reports/routing_confusion/report.md` + `report.json`

## 측정 항목

| 항목 | 의미 | 데이터 |
|---|---|---|
| Routing 정확도 | 올바른 solver가 선택됐는가 (혼동행렬 포함) | generated_300 + phase20_derived (432) |
| 수치 정답률 | 대표 답이 gold 값과 tolerance 내 일치하는가 | phase20_derived 중 127문항 |
| Negative 거절률 | 못 푸는 문제를 ok=True로 오주장하지 않는가 | phase20_negative (60) |
| 모호 케이스 | top1-top2 match 점수 격차 ≤ gap — "되묻기" 후보 | 전 routing 케이스 |
| 교란 강건성 | 라벨 보존 한국어 변형(동의어·띄어쓰기·filler·방해문) 후에도 routing이 유지되는가 | 9개 변형 × 적용 가능 문항 |

## 첫 실행 결과 (2026-07-08, sandbox)

- 기존 벤치마크는 **포화 상태**: routing 432/432, 수치 127/127, negative 60/60 전부 100%. 벤치마크와 정규식 규칙이 phase마다 공진화한 결과로, **기존 문항으로는 더 이상 오탐이 안 보입니다.** 체감 오탐은 벤치마크 분포 밖(표현 변주)에서 발생합니다.
- 교란 프로브가 즉시 실증: **"경사면→빗면" 변형에서 68/68 전멸** (system_type=unknown → solver 없음). 교과서 표준 동의어 하나가 통째로 빠져 있었음.
- 수정: extractor incline 패턴에 `빗면`, `사면` 추가 → 재실행 시 교란 파손 0, 기존 432문항 무회귀. 회귀 테스트 `test_bitmyeon_synonym_routes_to_incline` 추가.

## 2차 실행: 교란 24종 확장 (2026-07-08)

변형을 9→24종으로 늘리고 불변량을 3개(routing / requested_outputs / gold 수치)로 확장한 결과, **447건 파손 → 4개 실버그 발견 → 수정 후 0건**:

| 발견 | 파손 | 원인 | 수정 |
|---|---|---|---|
| 온도 방해문 → **조용한 오답** | 수치 8 | normalizer가 모든 `N도`→`deg` 변환, "온도는 20도"가 발사각 θ=20°로 주입 | 온도/기온/섭씨/화씨/체온 문맥의 `N도`는 각도 변환 제외 |
| "줄을 서서" → 대량 거절 | routing 366 | pulley 플래그에 '줄' 포함, 대기열 관용구도 매치 → `ambiguous_pulley` fallback이 라우팅 납치 | `줄(?!\s*을?\s*서)` — 관용구 제외, 진짜 rope는 유지 (negative 60 무회귀 확인) |
| "계산하라" → 요청 항목 소실 | outputs 68 | requested_outputs가 "구하라"류만 인식 | 질의 동사 정규화: 계산하라→구하라 |
| "용수철" 미탐 | routing 5 | spring 패턴에 표준어 '용수철' 누락 | 패턴 추가 |

각 수정에 회귀 테스트 5개 추가 (`test_phase28_stability.py`). 온도 건이 시사하는 구조적 교훈: **방해 숫자는 거절이 아니라 오답을 만든다** — knowns 주입은 문맥 검증 없이는 위험하며, 3단계(검증 강화)에서 "사용된 knowns의 출처 문장" 추적을 검토할 가치가 있음.

주의: 현재 24종 변형은 이제 전부 통과하므로 이 역시 포화됩니다. 다음 라운드는 어순 대변형, 두 유형 키워드 혼합, 복합 방해문(숫자+트랩 키워드 동시)을 추가하세요.

## 재설계에 쓰는 법

1. **교란 변형을 늘리는 것이 지금 가장 수익이 큽니다** — 어순 변형, 단위 표기 변형(km/h↔m/s 혼용 표기), 조사 변형, 두 유형 키워드가 섞인 문제. 파손율이 높은 변형이 곧 특징(feature) 레이어의 약점 지도입니다.
2. 분류기를 점수화 구조로 옮길 때, **모호 케이스 목록이 "되묻기" 트리거의 학습 데이터**가 됩니다 (현재 gap≤8이 0건인 것도 벤치마크 포화의 증상 — 교란 문항에서 다시 측정하세요).
3. 골드셋 확장 시 `generated_300`에 `expected_numeric`을 붙이면 수치 정답률 커버리지가 300문항 늘어납니다 (하니스는 필드만 있으면 자동 측정).

## 환경 주의

sandbox처럼 pint가 없으면 `tools/_pint_shim.py`(정확 배율 상수만 구현한 최소 대체)로 실행되고 리포트에 `units_backend: shim`이 찍힙니다. 릴리스 판단에 쓸 숫자는 실제 pint 환경에서 재실행해 확인하세요. 이 shim은 진단 도구 전용이며 런타임 의존성 대체가 아닙니다.

또한 이 도구는 `engine.model_builder`를 먼저 import합니다 — `equation_generators ↔ model_builder` 순환 import가 있어 import 순서에 따라 registry 로드가 실패할 수 있기 때문입니다 (엔진 자체의 잠재 취약점이니 언젠가 정리 권장).
