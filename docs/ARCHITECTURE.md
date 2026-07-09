# DynaTutor MVP Architecture

## 1. 처리 흐름

```text
User text
↓
Input Normalizer
↓
Quantity Extractor
↓
Canonical Problem Representation
↓
Legacy Rule Hints
↓
Solver Registry
↓
Verification Layer
↓
FBD / Explanation Layer
↓
Tutor Card Renderer
```

## 2. 기존 앱 사용 방식

기존 앱의 비중은 코드 기준으로 작게 잡았습니다. 기존 앱은 메인 엔진이 아니라 다음 역할입니다.

```text
Legacy Rule Hints:
- 문제 유형 후보
- 적용식/비적용식 후보
- 주의사항 후보
```

이 힌트는 최종 정답이 아닙니다. 최종 계산은 solver가 합니다.

## 3. PyDy/SymPy 위치

현재 MVP는 대표 문제를 SymPy/직접 공식 solver로 해결합니다. PyDy는 향후 고급 다물체/강체 시뮬레이션 계층으로 추가할 수 있습니다.

```text
engine/simulation/pydy_adapter.py  # 추후 추가 위치
```

## 4. 다음 개발 단계

1. quantity extractor 강화: v1, v2, I, spring k, distance s 등
2. solver 추가: 포물선, 등가속도, 극좌표, 순간중심
3. DB notebook 추가: Supabase/PostgreSQL
4. LLM explanation layer 추가: 계산 결과를 바꾸지 않는 설명 생성 전용
5. FBD 간단 도식 렌더링
6. Unit Verification Layer
7. Deterministic Explanation Layer
