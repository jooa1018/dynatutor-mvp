# Codex 구현 요청 템플릿

`<GOAL_FILE>`을 실제 파일명으로 바꿔 사용한다.

```text
goal/<GOAL_FILE>과 goal/00_GLOBAL_RULES.md를 먼저 끝까지 읽어줘.

이번 작업은 해당 goal의 범위만 구현해.

작업 전:
1. 최신 main 기준 관련 코드, 호출부, 테스트를 조사해.
2. 현재 동작과 근본 문제를 짧게 설명해.
3. 구현 계획, 예상 변경 파일, migration 위험을 정리해.
4. acceptance criteria를 테스트 목록으로 변환해.

작업 규칙:
- main에 직접 push하지 마.
- 새 브랜치와 하나의 PR을 사용해.
- goal과 무관한 리팩토링을 섞지 마.
- 기존 학생용 API와 풀이 출력을 명시적 이유 없이 깨뜨리지 마.
- 테스트를 통과시키려고 검증을 약화하거나 테스트를 삭제하지 마.
- 임의로 첫 번째 solver나 첫 번째 해를 선택하지 마.
- 외부 선택 의존성이 없어도 일반 앱이 정상 동작해야 해.
- 새 tolerance와 threshold는 중앙 설정에 두고 근거를 테스트로 남겨.
- 불확실하면 정상 답을 꾸미지 말고 ambiguity/clarification/unsupported로 표현해.

완료 전:
1. 관련 단위 테스트를 먼저 실행해.
2. 관련 회귀 및 metamorphic 테스트를 실행해.
3. bash scripts/check_backend_fast.sh를 실행해.
4. 필요하면 전체 backend tests를 실행해.
5. 프론트엔드를 수정했다면 metadata 검사와 build를 실행해.
6. git diff를 검토해 goal 밖 변경을 제거해.
7. 성능과 API schema 회귀를 확인해.

최종 보고:
- 근본 원인
- 설계 결정
- 변경 파일과 이유
- acceptance criteria별 결과
- 테스트 명령과 결과
- 성능 변화
- 알려진 한계와 남은 위험
- rollback 방법
- PR 링크 또는 PR 생성 상태
```
