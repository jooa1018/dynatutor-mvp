# Goal: Phase 53 — Student Explanation Fidelity and Traceability

## 목적

학생용 풀이가 자유로운 문장 생성이 아니라 실제 선택된 모델, 좌표계, 방정식, 검증 결과에서 만들어지도록 한다.

## 핵심 위험

정답 숫자가 맞아도 풀이 과정이 다음과 같으면 교육용 엔진으로 신뢰할 수 없다.

- 사용하지 않은 공식을 설명함
- 부호 convention이 계산과 다름
- 없는 가정을 추가함
- 다른 solver의 식을 섞음
- 검증 경고를 숨김
- LLM이 새로운 수치나 식을 만들어냄

## ExplanationTrace

최소 항목:

```text
selected_solver
route_reason
coordinate_frame
explicit_facts
assumptions
equation_ids
substitutions
candidate_summary
validation_summary
answer_derivation
warnings
```

## 생성 원칙

### 1. Model-first

설명은 typed model과 equation trace를 입력으로 사용한다.

### 2. Equation provenance

각 표시 식이 다음 중 어디에서 왔는지 추적한다.

- Newton equation generator
- energy equation
- momentum equation
- kinematic constraint
- manual closed form
- algebraic rearrangement

### 3. 좌표와 부호

풀이 초반에 선택한 양의 방향을 명시하고, 음수 답의 의미를 설명한다.

### 4. 가정

명시 조건과 엔진 기본 가정을 구분해 보여준다.

### 5. 검증

학생에게 필요한 수준으로 다음을 보여줄 수 있다.

- 차원 확인
- 식 역대입
- 에너지/운동량 확인
- 수치 시뮬레이션과 차이

### 6. LLM 설명 보조

LLM은 trace를 자연스러운 문장으로 바꿀 수 있지만:

- trace에 없는 식/값/가정을 추가하지 않는다.
- schema 검사를 한다.
- deterministic template fallback이 있다.
- LLM 미사용 환경에서도 설명이 생성된다.

## 정답과 설명 일관성 테스트

- answer numeric과 마지막 계산 단계 일치
- 사용 식과 `used_equations` 일치
- 좌표계 부호 일치
- unit 일치
- assumption trace 일치
- ambiguous/unsupported에서 확정적 표현 금지
- 검증 warning이 적절히 표시됨

## Acceptance criteria

- 주요 solver 최소 10개가 ExplanationTrace를 만든다.
- 표시된 모든 핵심 식의 provenance가 있다.
- trace 없는 값이나 식이 설명에 나타나지 않는다.
- LLM on/off에서 물리 내용이 일관된다.
- 정답과 설명 불일치 regression test가 있다.
- 학생에게 과도한 내부 기술 정보는 숨기되 주요 가정과 경고는 보인다.
