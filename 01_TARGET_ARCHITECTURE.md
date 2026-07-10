# Target Architecture — Dynamics Only

## 1. 계층별 책임

### Natural Language Layer

책임:

- 한국어 표현 정규화
- 물체, 값, 단위, 방향, 조건, 질문 대상 추출
- 원문 span과 추출 근거 기록
- 여러 가능한 해석 후보 생성
- 모호성 탐지

하지 않는 일:

- 최종 물리 답 결정
- 임의의 가정 확정
- 외부 엔진 실행

### CanonicalProblem v2

책임:

- 자연어와 물리 모델 사이의 안정적인 계약
- 사실과 가정 구분
- 값, 단위, 차원, 방향, 출처, 신뢰도 보관
- 요청 출력과 문제 유형 후보 보관
- schema version과 canonical fingerprint 제공

### Clarification and Routing Layer

책임:

- 필수 정보 충족 여부 확인
- 상위 solver 후보와 점수 비교
- 점수 차이가 작거나 필수 조건이 충돌하면 되묻기
- 현재 지원 범위 밖 문제 차단

### Typed DynamicsModel

책임:

- 질점/강체
- 기준좌표계
- 위치·속도·가속도 벡터
- 힘·모멘트
- 질량·관성
- 기하·운동학·접촉·줄·구름 제약
- SymPy 식과 방정식
- 단위와 차원

### Analytic Solver Layer

책임:

- 해석식과 기호 방정식 생성
- 모든 후보 해 반환
- 학생용 핵심 답 후보 생성

### Validation Layer

책임:

- 정의역
- 방정식 잔차
- 차원
- 물리적 부호와 범위
- 운동학 제약
- 에너지·운동량
- 마찰/접촉 상태
- 수치 조건과 민감도
- 후보 선택 또는 모호성 판정

### Independent Numerical Layer

책임:

- SymPy Mechanics + SciPy 시간 적분
- PyChrono 강체·접촉 교차 검증
- 해석값과 수치값 차이 보고

### Presentation Layer

책임:

- 실제 선택된 모델과 식을 사용한 풀이
- 가정과 좌표계 설명
- 검증 결과와 경고 표시
- Rapier2D 시각화 scene 생성

## 2. 핵심 데이터 흐름

```text
raw_text
 → normalized_text
 → ParseCandidate[]
 → CanonicalProblemV2
 → ClarificationDecision
 → DynamicsModel
 → SolverCandidate[]
 → CandidateSolution[]
 → ValidationReport
 → SelectedSolution | Ambiguous | Unsupported
 → SolverResult
 → ExplanationTrace
 → VisualizationScene
```

## 3. 핵심 상태

각 단계는 `ok` 하나로 모든 상황을 뭉개지 않는다.

```text
solved
solved_with_warning
needs_clarification
ambiguous
contradictory
unsupported
numerically_unstable
verification_disagreement
internal_error
```

## 4. 지원 범위 매트릭스

각 system type은 다음 metadata를 가져야 한다.

- 필요한 입력
- 선택 입력
- 지원하는 요청 출력
- 사용 가능한 해석 솔버
- 적용 가능한 validator
- 수치 검증 지원 여부
- Chrono 지원 여부
- 시각화 지원 여부
- 알려진 제한

이 매트릭스를 라우팅, clarification, 문서, 테스트가 공통 사용하도록 한다.
