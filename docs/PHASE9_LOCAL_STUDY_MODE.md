# Phase 9 — Local Study Mode

이번 단계는 서비스화가 아니라 개인 공부 도구에 맞춘 로컬 학습 경험 강화 단계입니다.

## 추가 기능

- 로컬 SQLite 오답노트 스키마 확장
  - favorite
  - review_due
  - review_count
  - last_reviewed_at
  - mastery
  - difficulty
  - source
- 복습 일정 API
  - `POST /records/{id}/review`
  - 정답이면 복습 간격이 길어지고, 오답이면 다음 날 다시 보게 합니다.
- 개인 학습 대시보드
  - `GET /study/dashboard`
  - 오늘 복습할 문제
  - 약점 유형
  - 추천 예제
  - 오늘 할 일
- 개인 연습 세트
  - `GET /study/practice`
  - 개인 학습 드릴 / 한국어 드릴 등에서 문제 세트를 가져옵니다.
- 백업/복원
  - `GET /records/export`
  - `POST /records/import`
- 원클릭 실행 스크립트
  - `scripts/run_backend.sh`
  - `scripts/run_frontend.sh`
  - `scripts/run_local.sh`
  - `scripts/run_local_windows.bat`

## 철학

개인용 앱이므로 사용자 계정, 결제, 클라우드 DB, rate limit은 넣지 않았습니다. 대신 오답노트와 복습 흐름을 로컬에서 빠르게 돌릴 수 있게 했습니다.

## 추천 사용법

1. 예제 또는 직접 입력으로 문제를 풉니다.
2. 틀렸거나 다시 보고 싶은 문제를 오답노트에 저장합니다.
3. 다음 날 `오늘의 개인 학습 모드`에서 복습 문제를 다시 풉니다.
4. 다시 풀고 맞았으면 `정답`, 틀렸으면 `오답`을 누릅니다.
5. 주기적으로 `오답노트 백업 JSON`으로 기록을 저장합니다.

## 아직 남은 한계

- 복습 알고리즘은 간단한 spaced repetition입니다.
- 계정 간 동기화는 없습니다.
- 백업 복원 시 중복 제거는 아직 하지 않고 append합니다.
- 문제 사진 자동 해석은 아직 없습니다.
