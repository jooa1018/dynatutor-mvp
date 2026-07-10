# Goal: Phase 52 — Cross-Engine CI, Performance, Reproducibility, and Observability

## 목적

파서부터 외부 시뮬레이션까지 결과를 한 형식으로 관찰하고, 속도·정확도·재현성을 release gate로 관리한다.

## 1. Pipeline Trace

한 요청에서 다음 단계 결과를 연결한다.

```text
request_id
raw_text_hash
normalization
parse candidates
canonical fingerprint
clarification decision
route candidates
model fingerprint
equation set
solution candidates
validation decision
student answer
numeric validations
```

민감한 원문 저장 정책은 별도로 두고 기본 report에는 hash 또는 짧은 안전한 summary를 사용할 수 있다.

## 2. Version 기록

- canonical schema version
- model schema version
- solver version
- tolerance policy version
- benchmark version
- SymPy/SciPy/PyChrono version
- optional LLM model identifier
- git commit

## 3. CI 계층

### PR Fast

- parser unit
- route unit
- solver regression
- validators
- golden smoke
- API schema

### PR Extended

- 전체 curated NLP benchmark
- metamorphic tests
- analytic path consistency
- 짧은 SciPy simulation

### Nightly Offline

- 긴 SciPy accuracy
- PyChrono 다섯 사례
- cross-engine report
- performance trend
- benchmark drift

## 4. CrossEngineReport

- case_id
- reference path
- candidate paths
- values and units
- absolute/relative errors
- invariant checks
- assumptions
- engine settings
- runtime
- status

상태:

```text
passed
passed_with_warning
disagreement
inconclusive
skipped
unsupported
error
```

## 5. Performance Budget

Phase 42 baseline을 기준으로 budget을 정한다.

원칙:

- deterministic fast path는 baseline 대비 과도한 회귀 금지
- 무거운 validation은 사용자 응답 critical path에서 제외
- parse, route, solve, verify 시간을 각각 측정
- P50/P95와 worst cases 기록
- cache가 correctness를 바꾸지 않도록 fingerprint 기반 사용

구체 숫자는 기준선 측정 후 문서화한다.

## 6. Reproducibility

- seed
- fixed integration settings
- deterministic ordering
- stable case IDs
- exact environment versions
- report artifact 보관

## 7. Release Dashboard

최소 지표:

- golden answer pass rate
- false-solve rate
- clarification precision/recall
- routing accuracy
- residual/invariant failure count
- cross-engine disagreement count
- P95 fast path latency
- flaky test count

## Acceptance criteria

- 하나의 request trace로 결정 과정을 추적할 수 있다.
- CI가 fast/extended/nightly로 분리된다.
- JSON과 Markdown report가 생성된다.
- 엔진 미설치와 실제 실패가 구분된다.
- 성능 회귀 기준이 있다.
- 동일 commit과 설정에서 재현 가능한 report가 나온다.
- release gate가 자동 또는 명시적으로 평가된다.
