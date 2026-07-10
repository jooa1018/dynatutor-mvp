# DynaTutor Dynamics Engine — Release Gates

아래 gate를 통과하지 못하면 “강한 동역학 엔진” 완료로 간주하지 않는다.

## Gate A — 자연어 안전성

- curated Korean benchmark 통과 기준 충족
- 높은 confidence false solve 0 또는 명시적 허용 기준 이하
- ambiguity detection 기준 충족
- unsupported 문제를 잘못 푸는 비율 기준 이하
- 단위·어순·동의어 변환 consistency 통과

## Gate B — 모델 일관성

- 주요 사실에 provenance 존재
- typed frame/vector/constraint 사용
- dimension mismatch 차단
- model fingerprint 재현성
- explicit assumption과 inferred assumption 분리

## Gate C — 라우팅 안전성

- top candidate margin 정책 적용
- capability 요구 입력 검사
- 박빙 경합 시 clarification
- requested output 지원 여부 검사
- 주요 confusion matrix 회귀 없음

## Gate D — 해 선택 안전성

- 모든 후보 해 검증
- first-solution 선택 없음
- 변수명 기반 물리 판정 없음
- ambiguous 상태 지원
- 잔차와 정의역 검사

## Gate E — 동역학 검증

- 적용 가능한 invariant 검사
- 줄/구름/접촉 constraint 검사
- 에너지/운동량 적용 조건 검사
- centralized tolerance
- 수치 조건/민감도 경고

## Gate F — 독립 오라클

- 독립 oracle set
- metamorphic test
- manual/generated consistency
- 최소 2개 SciPy simulation
- 다섯 PyChrono case 또는 명확한 환경 제약과 자동 실행 경로

## Gate G — 설명 신뢰성

- 설명 trace
- 식 provenance
- 답과 마지막 계산 일치
- 좌표/부호/단위 일치
- LLM on/off 물리 내용 일관성

## Gate H — 운영 품질

- fast/extended/nightly CI
- 성능 budget
- flaky test 관리
- 버전과 환경 기록
- JSON/Markdown verification report
- rollback 가능한 PR 구조
