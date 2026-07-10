# Goal: Phase 47 — Candidate Solution Validation and Explicit Selection Policy

## 목적

SymPy와 생성 솔버가 반환한 모든 후보 해를 검증하고, 변수 이름이나 배열 순서가 아니라 명시적인 물리 제약으로 해를 선택한다.

## 현재 문제

`backend/engine/physics_core/equation_system.py`는 심볼 이름 문자열을 확인해 음수 값을 제거한다. 생성 솔버 일부도 첫 번째 해를 사용할 위험이 있다.

## 목표 구조

```text
solve equations
 → CandidateSolution[]
 → symbolic validation
 → numeric validation
 → dynamics constraints
 → ValidatedCandidate[]
 → selected | ambiguous | no_valid_solution
```

## 핵심 데이터 구조

### VariableConstraint

- symbol
- real
- finite
- lower/upper bound
- inclusive
- integer
- allowed interval
- custom predicate
- reason/source

### CandidateSolution

- raw symbolic mapping
- numerical mapping
- unresolved symbols
- domain conditions
- branch information
- validation checks
- rejection reasons
- rank metadata

### SelectionDecision

- status
- selected candidate
- alternatives
- policy
- explanation

## validators

`backend/engine/physics_core/validators.py`를 실제 공통 계층으로 만든다.

최소 검사:

- real/finite
- unresolved symbols
- bounds and sign
- original equation residual
- denominator zero
- singular point
- assumptions consistency
- requested output availability
- model constraint residual

## selection policy

- 통과 후보 하나: 선택
- 통과 후보 여러 개지만 명시적 시간/방향/범위로 구분: 정책에 따라 선택
- 여러 후보가 모두 가능: ambiguous
- 통과 후보 없음: no_valid_solution
- numerical approximation이 필요하면 방법과 initial guess 기록

“작은 값”, “첫 번째 값”, “양수 값” 같은 암묵적 정책은 문제 의미와 연결되지 않으면 사용하지 않는다.

## 기존 호환성

호출부를 조사해 다음과 같이 점진 전환한다.

```text
solve_candidates()
validate_candidates()
select_solution()
solve()  # 호환 wrapper
```

## 필수 테스트

- 변수 이름 변경 불변성
- 양/음 근
- 두 양의 물리적 근
- 복소근
- infinite/NaN
- 분모 0
- piecewise/conditional solution
- unresolved symbol
- residual이 큰 수치근
- time interval에 따라 선택되는 근
- 충돌 또는 구름 constraint로 탈락하는 근
- 기존 대표 solver 결과 유지

## Acceptance criteria

- 물리 해 판정에서 심볼 이름 allowlist가 제거된다.
- 모든 후보가 검증된다.
- 첫 번째 해 자동 선택이 제거된다.
- ambiguous가 API 내부 상태로 표현된다.
- 각 후보의 탈락 이유를 확인할 수 있다.
- 기존 학생용 응답 호환성이 유지된다.
