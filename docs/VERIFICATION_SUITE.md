# 물리 검증 스위트 (Phase 30)

`engine/verification/` — "검증됨" 배지가 실제 의미를 갖게 하는 레이어. 목표는 **조용한 오답 차단**: 자신 있게 틀린 답이 사용자에게 나가기 전에 잡는다.

## 구조

```
suite.verify_result(canonical, solver_result) → VerificationReport
  ├─ dimensions.py    답 단위가 심볼의 기대 차원과 일치? (불일치 = error)
  ├─ plausibility.py  물리적으로 가능한 값? (t≤0, 광속 초과, NaN 등 = error)
  └─ residuals.py     지배 방정식에 답을 역대입 → 잔차 ≈ 0? (초과 = error)
```

`services.solve_problem`이 solver 직후 스위트를 실행하고, error가 있으면 **ok=False로 강등** + "답을 보류합니다" 사유를 답니다. (Phase 28의 "필수 answer 누락 = error" 정책과 동일 철학.)

## 설계 원칙과 정책

1. **맞는 답은 절대 죽이지 않는다.** hard error는 물리적으로 불가능하거나 방정식이 깨진 경우만. 특이하지만 가능한 값(μ>2, 초대형 가속도)은 warning. 무고 오탐(FP)은 하니스가 상시 측정하며 0이어야 한다.
2. **역대입은 풀이 공식의 재실행이 아니다.** 예: Atwood는 a 공식을 다시 계산하지 않고 두 물체 각각의 뉴턴 방정식 잔차를 검사한다 — a와 T가 **동시에** 맞아야 통과. 결합 항등식이라 한 값만 오염돼도 걸린다.
3. **커버리지 밖은 정직하게.** 역대입 미지원 유형(polar, rigid body, coriolis 등)은 checks에 "미지원 (검증 커버리지 밖)"으로 남긴다. 조용히 통과시키지 않는다.

## 허용치

`residuals.REL_TOL = 1e-4`, `ABS_TOL = 1e-8`. solver numeric이 ~6유효숫자로 반올림되므로(상대 ~2e-6) 1e-6은 무고 오탐을 냈다(실측 18건). 1e-4는 반올림은 통과시키고, g=9.8↔9.81급 슬립(0.1%)과 그 이상의 오류는 검출한다.

## 측정 결과 (sandbox, 2026-07-08 — 하니스 `verification` 섹션)

| 지표 | 값 |
|---|---|
| 무고 오탐 (정답 243건에 error) | **0** |
| 역대입 커버리지 | 212/243 (87%) — 15개 유형 |
| ×1.1 오염 검출 | 212/243 (커버 유형 내 **100%**) |
| 부호 반전 검출 | 178/243 (에너지형 방정식은 v² 대칭이라 원리상 못 봄 — 타당성 층이 t<0 등 보완) |
| 단위 교란 검출 | 231/243 (95%) |

역대입 커버 유형(15): incline, atwood, table/incline-hanging pulley, projectile(t·R 결합 항등식 + θ 오염 검출), collision(운동량+탄성 시 KE), const-acceleration, work-energy, spring energy/vibration, const-force work, impulse, fixed-axis rotation, rolling energy, flat/banked curve.

## 온도 버그와의 관계

Phase 29에서 발견한 "온도 20도 → θ 주입 → 조용한 사거리 오답"은 normalizer에서 1차 차단했지만, 이 스위트는 **그 클래스 전체**를 2차로 막는다: 오염된 θ가 어떤 경로로든 knowns에 들어오면 y-항등식 잔차가 깨져 답이 보류된다 (`test_projectile_joint_identity_catches_theta_injection`).

## 확장 방법

새 유형의 역대입 추가 = `residuals.py`의 `CHECKERS`에 `system_type → fn(cp, pool) -> [ResidualCheck]` 등록. 규칙: 풀이 공식이 아니라 **지배 방정식**을 쓰고, scale을 명시하고, 방향 관례가 모호하면 incline-hanging처럼 양 부호를 시도하되 방정식 전체가 동시에 성립해야 통과.

새 답 심볼 = `dimensions.EXPECTED_UNIT_BY_SYMBOL`에 기대 단위 등록. 대표 answer가 한국어 라벨이면 `suite._KOREAN_LABEL_TO_SYMBOL`에도.

## 출처(provenance) 레이어 (Phase 31)

`engine/verification/provenance.py` — 모든 known이 "어느 문장에서 왔는지"를 재구성한다.

**왜 별도 층인가**: 배경 문장의 수치("시험 시간 60 초", "칠판에는 각도 25도")가 knowns로 주입되면, 그 값으로 계산한 답은 그 값을 넣은 방정식과 *일관*되어 역대입이 원리상 못 잡는다 (garbage-in, consistent-out). 출처 검증이 이 클래스의 유일한 방어선.

**동작**: 정규화 텍스트를 문장 분해 → 각 문장을 question/background/physics/neutral로 분류(배경 마커가 물리 단어보다 우선 — 주입 문장이 "질량" 같은 물리 단어를 포함하기 때문) → 각 known의 source_text 스니펫을 **값(숫자) 위치 앵커**로 문장에 귀속(스니펫이 문장 경계를 넘는 경우 대응) → 동일 표기가 물리·배경 문장에 모두 있으면 ambiguous.

**에스컬레이션 정책**:

| 상황 | 처리 |
|---|---|
| 배경 문장 유래 + 해당 유형이 **사용하는** 심볼 (`residuals.RELEVANT_KNOWNS`) | **error — 답 보류** + 원인 문장 명시 |
| 배경 문장 유래 + 미사용 심볼 | warning — 답 유지 |
| 역대입 미커버 유형의 배경 유래 값 | error (안전망이 없으므로 보수적으로) |
| 다의적(물리·배경 양쪽에 동일 표기) | 항상 warning — 맞는 답을 죽이지 않음 |
| 기본값/문구 유도 (g=9.81, "수평으로"→θ=0) | trusted — 검사 제외 |

**측정 (하니스 provenance 섹션)**: 클린 243문항 + 24개 교란 변형 전체에서 무고 플래그 **0** · 검증된 주입 문장 5종 × 전 문항 = 주입 성사 969건 중 검출 **969 (100%)**.

**부수 발견**: 배경 질량 주입이 추출기의 다중질량 로직을 건드려 기존 m이 m1로 재구조화되고 일부 유형(work_energy)의 라우팅이 거절로 바뀔 수 있다. 오답이 아닌 안전한 실패(거절 + m2 플래그 동반)라 수용하되, 추출기 다중질량 로직의 알려진 취약점으로 기록한다.

## 알려진 한계 / 다음 단계

- 고급 유형(31/243) 역대입 미커버 — 벡터 성분이 display 문자열에만 있어 pool 구성이 안 됨. 근본 해결은 해당 solver들이 `answers` 항목을 채우는 것(Phase 26 패턴).
- 부호 반전은 에너지형에서 원리상 못 잡음 — 방향 정보가 필요한 유형은 answers에 방향 필드 추가 검토.
- sandbox 측정은 pint shim 기반 (`tools/_pint_shim.py` — 이번에 지수 파싱 버그를 mutation 프로브가 잡아 수정함). 릴리스 숫자는 실제 pint로 재실행: `cd backend && python tools/routing_confusion_report.py`.

## 테스트

`tests/test_phase30_verification.py` — unit 8 + regression 7. sandbox에서 14개 직접 실행 통과, `test_service_demotes_ok_on_verification_failure`(monkeypatch 필요)는 사용자 환경 pytest에서 실행.
