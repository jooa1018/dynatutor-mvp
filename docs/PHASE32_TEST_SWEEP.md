# 전체 테스트 스윕 회귀 보고 (Phase 32)

목적: sandbox에서 네트워크 없이(진짜 pytest/pydantic/fastapi 설치 불가) 34개 테스트 파일 전체를 pint shim + pydantic stub + 최소 pytest 대체로 실행해, 검증·출처 레이어가 **기존 테스트를 깨뜨리는지** 사용자 실행 전에 확인.

## 결과

| 항목 | 값 |
|---|---|
| 실행/통과 | 201 pass, 0 real fail |
| 스텁 한계로 미실행(collect) | fastapi 의존 4파일 (routes/TestClient) |
| 스텁 잔여 실패 2건 | 모두 환경 아티팩트(회귀 아님) |

### 발견하고 고친 진짜 회귀 3건 (모두 검증 스위트의 무고 오탐)

전부 "맞는 답을 검증이 죽이는" 케이스 — 하니스가 놓친 이유는 해당 유형이 벤치마크의 수치 검증 집합 밖이었기 때문. 전체 스윕이 아니었으면 사용자 환경에서 터졌을 것들.

1. **진동 주기 T를 장력으로 오판** — `T`가 장력(N)으로 하드코딩돼 진동 문제의 주기(s)를 차원 불일치 error로 처리. → `EXPECTED_UNIT_BY_CONTEXT`로 (system_type, symbol) 문맥 인식 도입.
2. **마찰일 음수(-30 J)를 역대입이 오탐** — 부호를 W에 인코딩하는 solver를 `W - F·s·cosθ`(θ=0 가정)가 |r|=60으로 실패 처리. → 크기 항등식 + 별도 부호 타당성으로 분리. 오염은 여전히 검출.
3. **정지마찰 a=0 / 경사면-도르래 방향 변형을 역대입이 오탐** — 미끄러짐 방정식을 정지 평형에 적용, 또 마찰 부호를 운동 방향에 하드코딩. → a=0이면 정지조건(tanθ≤μs) 검사로 분기, 방향은 가속도·마찰 부호 4조합 시도(두 방정식 동시 성립 요구라 오염 검출력은 유지).

각 건에 회귀 테스트 추가(`test_phase30_verification.py`).

### 회귀 아닌 잔여 2건

- `test_pint_unit_conversions`: shim에 `g`(gram) 토큰과 `Q*Q` 곱셈 미구현. 진짜 pint에선 통과. **shim 한계**.
- `test_phase21_...run_all_validations`: subprocess를 띄우는데 그 자식 프로세스는 in-process 스텁을 상속 못 해 진짜 pydantic 부재로 실패. **환경 아티팩트**.

## 사용자 환경에서 남은 필수 확인 (축소됨)

1. `./scripts/check_backend_fast.sh` — 진짜 pytest로 전체. 특히 fastapi 의존 4파일(스윕에서 미실행)과 서비스 레벨 강등 테스트.
2. `python tools/routing_confusion_report.py` — 진짜 pint로 하니스 재실행(shim 숫자 재현 확인).

스윕이 커버한 범위(순수 엔진 로직 201 테스트) 밖의 리스크만 남았다.

## 최종 업데이트: (a) fastapi 계층 + (b) shim gap 해소 후

| 항목 | 값 |
|---|---|
| **전체 34파일 227 테스트: 227 pass, 0 fail** | fastapi/starlette stub + 서브프로세스용 on-disk stub(PYTHONPATH) 포함 |
| fastapi 의존 4파일 | stub TestClient로 실행 — 인증 미들웨어(401/헤더 인증/쿼리 토큰 거부), records CRUD/import-export, explain, study 전부 통과. 발견된 stub gap 1건(`payload: dict` body 바인딩)은 stub 수정으로 해결(엔진 문제 아님) |
| chrono validation (subprocess) | PYTHONPATH on-disk stub으로 자식 프로세스까지 실행 — 25/25 검증 통과 |
| pint shim gap | 축약 단위 토큰(g, km, N, J 등)과 Quantity 곱셈/나눗셈 구현 → `test_pint_unit_conversions` 통과. 하니스 전 지표 무변동 확인 |

### 정직한 한계 (stub ≠ 실물)

- **fastapi stub은 핸들러+미들웨어 로직을 검증하지, FastAPI 자체를 검증하지 않는다.** 요청 검증(422), 직렬화 세부, ASGI 동작은 실물에서만 확인됨.
- **pint shim은 이 코드베이스가 쓰는 단위 부분집합만 구현.** 변환 배율은 정확 상수라 수치가 일치하지만, 실물 재현 확인이 릴리스 기준.
- 따라서 사용자 환경 1회 실행은 여전히 의미가 있다: `./scripts/check_backend_fast.sh && python tools/routing_confusion_report.py`. 다만 이제 그 실행은 "회귀 탐색"이 아니라 **"stub 충실도 확인"**으로 성격이 바뀌었다 — 순수 로직 회귀는 이 스윕이 소진했다.

### 검증 스위트 sign 검출률 변화 (투명 기록)

무고 오탐 3건 수정의 정직한 비용으로 부호반전 검출이 178→131/243로 감소했다. 이유: 일(W)과 경사-도르래의 부호는 solver마다 방향 관례가 다른 **정당한** 차이임이 확인되어, 부호 기반 검출을 크기 항등식으로 완화했기 때문. 오염(×1.1)·단위·주입 검출률은 유지(212/243, 231/243, 969/969).
