# Phase 39: 사용성 개선 + 수학 기호 팔레트

## 기호 팔레트 (SymbolPad) — 명시 요청
문제 입력 textarea 아래에 접이식 팔레트 추가 (`components/SymbolPad.tsx`):
- **기호**: θ ω α μ τ Δ ° ² √ · ± →
- **표기**: v₀= ω₀= m₁= m₂= θ= μ= k= F= I= e=
- **단위**: m/s m/s² rad/s rad/s² kg N N/m N·m kg·m² J cm 초
- 탭 한 번으로 **커서 위치에 삽입** + 포커스 유지 (모바일 44px 터치 타깃).
- 원칙: 팔레트의 모든 표기는 백엔드가 이해하는 것만 — `test_phase39_usability.py`가
  기호식 입력 6종의 **정답 왕복**을 보증 (θ=30°, μ=0.2, ω=3rad/s, α+ω₀, Δx, τ+N·m).
- 부수: Ctrl+Enter(⌘+Enter)로 바로 풀기.

## 팔레트 대응 엔진 확장 — 기호식 짧은 입력이 부딪히던 구멍 5개
1. **첨자 정규화**: ω₀/m₁/v₂ 등 첨자 숫자 → 일반 숫자 (ω₀=5가 omega0로 안 읽히던 버그).
2. **수평면 마찰력** 신규 유형 `horizontal_friction_force`: "μ=0.2, m=2kg, 마찰력은?" → f=μmg
   (+수직항력). μ 값 존재 자체를 마찰 증거로 인정("마찰" 단어 불요), 단일 물체 문맥의 m₁ 허용.
3. **회전 kinematics**: fixed_axis solver가 τ·I 없이도 ω=ω₀+αt, v=ωr 두 갈래 지원.
4. **탄성 에너지 직접 질문**: "저장된 에너지는?" → E=½kx² (질량 불요).
5. **rolling 과포섭 수정**: "원판/원통/바퀴" 단어만으로 rolling 판정하던 것을
   "구름/굴러/구르"로 좁힘 — "회전하는 원판 위 점의 속력"이 rolling으로 새던 문제 해소.
   rad/s 단위 자체를 회전 증거로 추가 (기호식 입력엔 "각속도" 단어가 없음).
- 신규 답 전부 knowns-앵커 잔차 검사기 등록 (f−μmg, N−mg, ω−(ω₀+αt), v−ωr, E−½kx²)
  — 역대입 커버리지·오염 검출 유지.

## 발견·수정한 숨은 회귀 (스테일 리포트 뒤에 있던 것)
zip에 동봉된 하니스 리포트는 교란 0 breaks였지만 **코드 재실행 결과 58 breaks** —
phase38의 table-hanging 정책 변경 후 하니스 미실행 상태로 패키징된 것.
- 증상: 방해문 "실험 준비는 … 책상 위에서 했다"가 도르래 명시 Atwood 문제를
  `pulley_table_hanging`으로 가로챔 (58/432 케이스).
- 수정: 도르래 단어 없는 경우를 위한 이른 table-hanging 규칙에 `not pulley` 가드 —
  도르래가 명시되면 정식 topology(양쪽 매달림=Atwood 우선)가 판정.
- 원본 코드로 재현 확인 후 수정, 교란 0 breaks 복구. 회귀 테스트 2건
  (방해문 Atwood 유지 + 도르래 단어 없는 정상 table-hanging 유지).

## 최종 상태
전체 스윕 **303 테스트 0 실패** · routing 432/432 · 수치 127/127 · negative 60/60 ·
교란 0 breaks · 검증 FP 0, 역대입 243/243 · clarify 14/14·10/10·60/60 · provenance 999/999.

## 사용자 환경 확인
- `cd frontend && npm ci && npm run build` (tsc + esbuild — sandbox에서 실행 불가, 정적 검증만 통과)
- `cd backend && PYTHONPATH=. pytest -q -o addopts=` + `python tools/routing_confusion_report.py`
