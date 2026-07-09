# Phase 41: Phase 40 피드백 후속 6건

| # | 항목 | 처리 |
|---|---|---|
| 1 | 검증 스크립트 종료성 | **원인 확정**: `run_with_timeout.py`가 자식 정상 종료 시 프로세스 그룹 잔존을 확인하지 않았음 (frontend 래퍼에는 있던 로직). 정상 종료 경로에 그룹 잔존 감지→SIGTERM/SIGKILL 정리 추가. **실동작 검증**: `sleep 300` 손자를 남기는 명령이 즉시 정리 후 코드 0으로 반환 (이전엔 외부 timeout까지 매달림). pytest 회귀 테스트 포함. frontend 래퍼는 동일 로직+산출물 검증 보유 — Node 20 실환경 최종 확인은 사용자 실행 필요 |
| 2 | 공식 release validation | RELEASE_CHECKLIST를 **marker 그룹별 스크립트 기준**으로 공식화 (`check_backend_fast/benchmark/audit.sh` + 하니스). 전체 한 방 pytest는 timeout 가능성 명기하고 비공식화 |
| 3 | 포물선 부분 답 | projectile flag에 "던졌/던져/던진" 추가(기존엔 "사거리" 단어에만 의존해 라우팅됨), "비행시간은?" 질문 시 지면 착지 추정. solver에 v0-불요 경로: θ=0 + time 질문 → **t=√(2Δh/g)** (풀이에 "수평거리는 v0 필요" 안내 포함). 사거리 질문이면 기존대로 missing_info("초속도 v0") 안내. 기존 완전 케이스 무회귀 |
| 4 | 누락 물리량 추가 | UnderstandingCard에 "누락된 값 추가…" 셀렉트+추가 버튼 — LABELS의 미추출 심볼을 행으로 추가해 기존 set_knowns patch로 전달. 추가 가능 심볼 전체가 `ALLOWED_KNOWN_SYMBOLS` 부분집합임을 대조 확인. 왕복 테스트: v2 누락 충돌 → v2=0 추가 → v_f=1.6 정답. **부수 발견·수정**: (a) "2kg 물체가 4m/s로 …와 충돌"의 익명 진행 물체 속도가 v0로만 잡혀 v1이 비던 것 → extractor에서 v1 별칭 주입(generator·검증·출처가 같은 값을 보도록 canonical 수준에서), (b) 그 과정에서 지역 `from engine.models import Quantity`가 모듈 import를 가리던 shadowing 제거 |
| 5 | OUTPUTS 목록 동기화 | 백엔드 whitelist 23종과 프론트 체크박스 **완전 일치** (initial_velocity/mass/kinetic·potential_energy/v1_after/v2_after/tangential_velocity/centripetal_acceleration 추가). 대조 스크립트로 잔차 0 확인 |
| 6 | start script 정리 | `next start` 제거 → `node scripts/serve-static.js` (zero-dep, out/ 정적 서빙 + SPA fallback — production 산출물 로컬 미리보기). out/ 부재 시 빌드 안내 후 종료. 체크리스트에 용도 명기 |

최종: 전체 스윕 **313 테스트 0 실패**, 하니스 전 지표 그린.
프론트 정적 검증(백엔드-프론트 목록 일치·괄호·import) 통과 — `./scripts/check_frontend_build.sh`
Node 20 실행으로 "outputs verified 후 즉시 종료"를 최종 확인해 주세요.
