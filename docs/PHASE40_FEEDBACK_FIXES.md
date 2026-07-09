# Phase 40: Phase 39 피드백 7건 반영

| # | 항목 | 처리 |
|---|---|---|
| 1 | patch whitelist 보강 | `ALLOWED_REQUESTED_OUTPUTS` += friction_force · normal_force · elastic_energy. UnderstandingCard OUTPUTS 라벨(마찰력/수직항력/탄성 에너지) 추가. 재풀이 patch 왕복 테스트로 ClarifyPatchError 재발 방지 |
| 2 | stale missing_info | fixed_axis: 회전 kinematics(ω=ω₀+αt, v=ωr)로 풀리는 조합이면 τ·I를 missing에 안 넣음. spring_energy: elastic_energy 질문이면 질량 m 제외. "ok=True + 확인 필요" 모순 해소 — τ·I가 정말 필요한 경우엔 여전히 표시됨을 함께 테스트 |
| 3 | 단위 생략 허용 | `v₀=0`→m/s, `ω₀=0`→rad/s, `θ=30`→deg. 명시적 "심볼=값" 형태에만 적용, 단위가 붙어 있으면 기존 해석 우선(negative lookahead — θ=0.5 rad 보존) |
| 4 | a=3m/s² 중복 추출 | 진폭 패턴(`A=…m`)에 `m(?!/s)` — IGNORECASE로 a=3의 'm'을 진폭 A=3 m으로 오인하던 것 차단 |
| 5 | localStorage 기록 보강 | local_only(음수 id) 기록: review/favorite을 서버 API 없이 localStorage에서 처리(`reviewLocalRecord`/`toggleLocalFavorite`), 삭제(`deleteLocalRecord`) + 서버 기록 삭제(`deleteRecord`, DELETE /records/{id}) 지원. RecordCard에 "이 기기" 배지 + 삭제 버튼. export JSON은 서버 데이터 + `local_records`를 병합하고, 서버 실패(오프라인) 시 local만으로도 내려받기 |
| 6 | 빌드 체크 스크립트 | 종료 코드 0이어도 `out/index.html`·`out/assets/app.js` 부재 시 실패 처리(산출물 검증). npm 종료 후 잔존 프로세스 그룹 정리 로직은 기존 유지 — Node 20 실환경 종료 확인은 사용자 실행 필요(sandbox npm 차단) |
| 7 | RELEASE_CHECKLIST | Phase 23 기준(145 passed)을 Historical 섹션으로 이동, 현행 명령(`pytest -q -o addopts=` + 하니스 + `check_frontend_build.sh`)과 기대치로 갱신. "패키징 전 하니스 필수" 명기 |

최종: 전체 스윕 **307 테스트 0 실패**, 하니스 전 지표 그린 (routing 432/432 · 수치 127/127 ·
교란 0 · 검증 FP 0 · resid-cov 243/243 · clarify 60/60 · provenance 100%).

프론트 정적 검증(import/export/CSS/괄호) 통과 — `npm ci && npm run build` 최종 확인은 사용자 환경에서.
