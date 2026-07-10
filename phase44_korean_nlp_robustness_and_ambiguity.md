# Goal: Phase 44 — Korean Dynamics NLP Robustness, Ambiguity, and Calibration

## 목적

한국어 표현 다양성에 강하면서도, 모르는 문제를 억지로 푸는 false-solve를 줄인다.

## 핵심 원칙

자연어 성능은 최종 정답률 하나로만 측정하지 않는다.

다음을 각각 측정한다.

- 물체 추출
- 값과 단위 추출
- 방향 추출
- 조건/가정 추출
- 요청 출력 추출
- system type 후보
- clarification 판단
- unsupported 판단
- confidence calibration

## benchmark 확장

기존 benchmark를 유지하고 다음 curated case를 추가한다.

### 권장 최소 추가량

- 같은 의미의 한국어 paraphrase: 100
- 주어 생략과 대명사/문맥 연결: 40
- 단위·기호·첨자·띄어쓰기 변형: 50
- 오탈자와 구어체: 30
- 무관한 배경 정보가 섞인 문제: 30
- 여러 물체의 값 연결이 어려운 문제: 40
- 의도적으로 모호한 문제: 50
- 정보 부족 문제: 40
- 서로 모순된 조건: 30
- 지원 범위 밖 또는 3D/변형체 문제: 40

기대값은 자동 생성 결과를 그대로 사용하지 않고 사람이 검토한다.

## 주요 평가 지표

### 추출

- quantity precision/recall
- unit normalization accuracy
- subject binding accuracy
- requested output accuracy
- direction accuracy
- assumption classification accuracy

### 분류와 라우팅 전 단계

- system type top-1 accuracy
- system type top-k recall
- ambiguity detection recall
- unsupported detection precision/recall

### 안전성

가장 중요한 지표:

```text
false_solve_rate
```

정답을 확정하면 안 되는 문제를 정상 답으로 내는 비율이다.

추가:

- unnecessary_clarification_rate
- missing_clarification_rate
- silent_assumption_rate
- contradictory_input_detection_rate

### confidence calibration

confidence를 문자열 “높음/보통/낮음”으로만 두지 말고 가능하면 0~1 score와 이유를 둔다.

- confidence bin별 실제 정확도
- 높은 confidence의 false solve 수
- top-1과 top-2 score margin

## robustness 규칙

다음 변형에서 canonical meaning이 유지되어야 한다.

- 단위 변환
- 띄어쓰기 변화
- 어순 변화
- 동의어
- 기호와 한글 표현 교환
- 불필요한 문장 추가
- 문제 순서 변경

## LLM 사용 시

- 규칙 기반 결과와 LLM 후보를 병렬 비교할 수 있다.
- LLM 결과는 schema와 capability matrix를 통과해야 한다.
- LLM이 낮은 confidence일 때 deterministic clarification으로 전환한다.
- benchmark에서 LLM 사용 여부와 모델 버전을 기록한다.
- 외부 LLM 불가 환경에서도 핵심 benchmark subset을 실행한다.

## 하지 않을 일

- benchmark 문장을 그대로 하드코딩해 정답을 맞히지 않는다.
- 자연어 confidence만으로 최종 답을 확정하지 않는다.
- 미지원 문제를 가장 비슷한 solver에 강제로 보낸다.

## Acceptance criteria

- 추가 curated case가 최소 300개 이상이다.
- 단계별 metric report가 생성된다.
- false-solve rate가 기준선보다 감소한다.
- 높은 confidence 오답이 명확히 추적된다.
- 모호성, 정보 부족, 모순, 미지원을 구분한다.
- paraphrase와 단위 변환에서 canonical consistency test가 있다.
- benchmark가 solver 정답뿐 아니라 intermediate parse를 검사한다.
