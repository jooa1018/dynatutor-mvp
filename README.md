# DynaTutor Dynamics Engine — Goal Roadmap v2

이 문서 묶음은 DynaTutor를 **한국어 동역학 문제를 안정적으로 해석하고, 구조화된 물리 모델을 만들고, 해석·수치·외부 시뮬레이션으로 교차 검증하는 교육용 동역학 엔진**으로 강화하기 위한 단계별 작업 명세서다.

## 범위

이 로드맵은 다음 동역학 영역에 집중한다.

- 질점 운동학
- 질점 운동역학
- 직선·곡선·극좌표 운동
- 일–에너지
- 충격량–운동량
- 충돌
- 입자계
- 도르래와 줄 제약
- 마찰과 접촉
- 순수 구름과 미끄럼
- 평면 강체 운동학
- 평면 강체 운동역학
- 회전좌표계와 코리올리 항
- 1자유도 진동
- 위 범위의 해석해·수치 적분·강체 시뮬레이션 검증

## 명시적인 비범위

다음 분야로 범용 확장하는 것이 목표가 아니다.

- 열역학
- 전자기학
- 유체역학
- 재료역학과 탄성 변형
- 연속체역학
- 유한요소해석
- 양자역학
- 상대론
- 일반적인 3차원 로봇 제어 및 최적화

정역학은 동역학 문제의 힘 평형 한계 상태나 구속조건 검증에 필요한 범위에서만 사용한다.

## 최종 목표 구조

```text
한국어 자연어 문제
        ↓
정규화 + 사실 후보 추출
        ↓
CanonicalProblem v2
- 값, 단위, 방향, 객체, 요청 출력
- 원문 위치와 추출 근거
- 명시 조건과 추론 가정 구분
- 후보별 신뢰도
        ↓
Clarification / Unsupported Gate
        ↓
Typed DynamicsModel
- 좌표계
- 벡터
- 강체/질점
- 힘과 모멘트
- 운동학·기하·접촉 제약
- SymPy 식
- 단위와 차원
        ↓
Solver Router
- 상위 후보와 점수
- 필수 입력 충족 여부
- 경합 시 임의 선택 금지
        ↓
해석·기호 솔버
        ↓
모든 후보 해에 공통 검증
- 정의역
- 방정식 잔차
- 차원
- 구속조건
- 에너지·운동량
- 마찰·접촉 상태
- 수치 조건과 민감도
        ↓
학생용 답과 근거 기반 풀이
        ├─ SymPy Mechanics + SciPy 수치 검증
        ├─ PyChrono 독립 강체 검증
        └─ Rapier2D 시각화
```

## 최종 핵심 원칙

1. **그럴듯한 오답보다 명시적인 모호성 또는 미지원이 낫다.**
2. 자연어 파서, 라우터, 모델 빌더, 솔버, 검증기를 각각 독립 평가한다.
3. 변수 이름 문자열이나 결과 배열 순서로 물리적 해를 선택하지 않는다.
4. LLM은 파싱 후보와 설명을 보조할 수 있지만, 검증 없이 물리 정답을 결정하지 않는다.
5. 외부 엔진 결과도 정답을 자동으로 덮어쓰지 않는다.
6. 모든 중요한 값에는 출처, 단위, 가정, 선택 이유를 추적할 수 있어야 한다.
7. 일반 학생 요청은 빠른 해석 경로를 사용하고, 무거운 시뮬레이션은 offline/nightly 검증으로 분리한다.
8. 하나의 goal은 하나의 PR로 구현한다.

## 권장 실행 순서

### 기반과 자연어 계층

1. `phase42_baseline_scope_and_release_contracts.md`
2. `phase43_canonical_problem_v2_and_provenance.md`
3. `phase44_korean_nlp_robustness_and_ambiguity.md`
4. `phase45_typed_dynamics_model_frames_units.md`
5. `phase46_routing_confidence_and_clarification.md`

### 해석 정확성과 검증 계층

6. `phase47_candidate_solution_validation.md`
7. `phase48_dynamics_invariants_and_numerical_conditioning.md`
8. `phase49_solver_consistency_oracles_and_metamorphic_tests.md`

### 독립 수치 검증

9. `phase50_sympy_scipy_numeric_simulation.md`
10. `phase51_pychrono_independent_validation.md`
11. `phase52_cross_engine_ci_performance_observability.md`

### 학생용 출력과 시각화

12. `phase53_explanation_fidelity_and_traceability.md`
13. `phase54_rapier2d_visualization.md`

## 단계 진행 규칙

- 앞 단계의 acceptance criteria가 충족되지 않았으면 다음 단계로 넘어가지 않는다.
- Phase 42~49는 정확성의 기반이므로 필수다.
- Phase 50~52는 무거운 독립 검증 계층이다.
- Phase 53~54는 학생 경험 계층이지만, 정답 계산 로직과 분리한다.
- 한 PR에서 여러 phase를 동시에 구현하지 않는다.
- 큰 phase는 문서의 권장 sub-PR 순서대로 다시 나눌 수 있다.

## 현재 저장소에서 확인된 핵심 파일

```text
backend/engine/models.py
backend/engine/extraction/extractor.py
backend/engine/extraction/normalizer.py
backend/engine/qa/korean_benchmark.py
backend/engine/routing/evidence.py
backend/engine/solvers/registry.py

backend/engine/model_builder/model_types.py
backend/engine/model_builder/
backend/engine/physics_core/equation_system.py
backend/engine/physics_core/validators.py
backend/engine/physics_core/units.py
backend/engine/physics_core/vectors.py
backend/engine/physics_core/constraints.py

backend/engine/equation_generators/
backend/engine/verification/
backend/engine/adapters/sympy_mechanics_adapter.py
backend/engine/adapters/pydy_adapter.py
backend/tools/chrono_validation/
backend/tests/
```

실제 구현 전에는 항상 저장소의 최신 main을 다시 조사한다.

## 공통 완료 정의

로드맵 완료 후 엔진은 최소한 다음을 만족해야 한다.

- 다양한 한국어 표현을 동일한 동역학 의미로 정규화한다.
- 추출한 물리 사실의 원문 근거와 신뢰도를 추적한다.
- 정보 부족, 모호성, 모순, 미지원 문제를 구분한다.
- 경합하는 솔버를 점수만으로 임의 선택하지 않는다.
- 복수 후보 해를 모두 검증하고 선택 또는 모호성 이유를 남긴다.
- 단위 변환에 결과가 변하지 않는다.
- 좌표축 반전 시 값의 부호가 물리적으로 일관되게 변한다.
- 에너지·운동량·구속조건 등 적용 가능한 동역학 불변량을 검사한다.
- 수치적으로 불안정하거나 민감한 문제를 경고한다.
- 수동 공식, 생성 방정식, SciPy, PyChrono 사이의 불일치를 보고한다.
- 학생용 풀이가 실제 선택된 모델과 방정식에서 생성된다.
- Rapier2D는 시각화만 담당하고 정답을 결정하지 않는다.

작업 요청에는 `CODEX_PROMPT_TEMPLATE.md`를 사용하고, 다른 모델로 리뷰할 때는 `CLAUDE_REVIEW_TEMPLATE.md`를 사용한다.
