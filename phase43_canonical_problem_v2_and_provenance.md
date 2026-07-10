# Goal: Phase 43 — CanonicalProblem v2, Provenance, and Assumption Control

## 목적

자연어에서 추출한 사실을 단순 dict가 아니라 출처·단위·방향·신뢰도를 가진 구조로 보관한다.

## 현재 문제

현재 `CanonicalProblem`의 `knowns`, `flags`, `coordinate_data`, 문자열 필드는 유용하지만 다음을 충분히 표현하기 어렵다.

- 어느 문장에서 값을 추출했는가
- 명시된 값인가 추론한 값인가
- 여러 해석 후보가 있는가
- 방향과 좌표계가 무엇인가
- 값이 어떤 물체에 속하는가
- confidence가 왜 낮은가
- schema가 변경됐을 때 호환 가능한가

## 설계 요구사항

### 1. ExtractedFact

최소 필드:

```text
fact_id
kind
subject_id
symbol
value
unit
dimension
direction
source_text
source_span
provenance
confidence
status
alternatives
```

`status` 예시:

```text
explicit
normalized
inferred
assumed
defaulted
conflicting
```

### 2. AssumptionRecord

가정은 문자열 목록만 사용하지 않고 다음을 기록한다.

```text
assumption_id
kind
value
reason
source
confidence
user_visible
```

예:

- 줄은 질량이 없다.
- 도르래 축 마찰은 무시한다.
- 공기저항은 무시한다.
- 중력가속도는 9.81 m/s²를 사용한다.

### 3. ParseCandidate

자연어가 두 가지 이상으로 해석될 때 후보를 보존한다.

```text
candidate_id
facts
system_type_candidates
score
warnings
missing_info
conflicts
```

### 4. Schema version과 fingerprint

- `schema_version`
- canonical JSON 직렬화
- 순서에 영향을 받지 않는 fingerprint
- migration 또는 v1 compatibility adapter

### 5. 기존 호환성

기존 solver가 사용하는 `knowns`, `flags`, `requested_outputs`는 compatibility view로 유지한다.

## 자연어 계층 안전 규칙

- 원문에 없는 수치를 생성하지 않는다.
- 단위 없는 값의 의미가 분명하지 않으면 후보 또는 clarification으로 남긴다.
- “정지해 있다”를 속도 0으로 변환할 때 원문 근거를 기록한다.
- “매끄러운”을 마찰 0으로 해석할 때 domain rule을 provenance로 기록한다.
- 배경 문장의 값과 실제 문제 데이터가 섞이지 않도록 subject 연결을 검증한다.

## 필수 테스트

- 명시값과 추론값 구분
- 동일한 값의 다른 단위 정규화
- 여러 물체의 같은 기호 분리
- 원문 span 보존
- 충돌하는 두 값 탐지
- v1 → v2 호환 view
- canonical fingerprint 안정성
- 직렬화 round-trip
- 원문에 없는 가정이 explicit로 표시되지 않음

## Acceptance criteria

- 주요 추출 값에 provenance와 confidence가 있다.
- 명시 조건과 가정이 분리된다.
- 여러 parse 후보를 표현할 수 있다.
- 기존 solver는 compatibility layer를 통해 계속 작동한다.
- schema version과 fingerprint가 있다.
- 기존 API 응답은 깨지지 않는다.
