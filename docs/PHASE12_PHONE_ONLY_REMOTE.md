# Phase 12 — Phone-only Remote Mode

목표: 노트북/PC 서버를 켜지 않아도 iPhone Safari/PWA에서 DynaTutor를 사용할 수 있게 만든다.

## 핵심 아이디어

- iPhone은 Safari/PWA로 프론트엔드에 접속한다.
- FastAPI 백엔드는 Render/Railway/Fly 같은 클라우드에 올라간다.
- Render 무료 플랜에서는 오답노트 SQLite를 `/tmp`에 저장한다. 재시작/재배포 시 초기화될 수 있다.
- `DYNATUTOR_ACCESS_TOKEN`으로 개인용 잠금장치를 둔다.

## 완전 오프라인 iPhone 앱과의 차이

이 단계는 완전 오프라인 네이티브 앱이 아니다. 인터넷만 있으면 PC 없이 iPhone만으로 사용할 수 있는 개인용 원격 모드다.

완전 오프라인을 원하면 Python/FastAPI/SymPy solver 일부를 TypeScript 또는 React Native 쪽으로 옮기는 별도 대규모 작업이 필요하다.

## 백엔드 배포 환경변수

```text
DYNATUTOR_ACCESS_TOKEN=<긴 랜덤 토큰>
DYNATUTOR_DB=/tmp/dynatutor_records.sqlite
DYNATUTOR_CORS_ORIGINS=https://your-frontend.vercel.app  # 초기 테스트만 * 허용
LLM_ENABLED=auto
OPENAI_API_KEY=<선택>
```

토큰 생성:

```bash
./scripts/generate_access_token.sh
```

## 프론트엔드 환경변수

```text
NEXT_PUBLIC_DYNATUTOR_API_BASE=https://your-dynatutor-api.onrender.com
```

토큰은 프론트엔드 환경변수에 넣지 않는다. 특히 `NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN`은 만들지 않는다. iPhone 화면에서 한 번 입력해 localStorage에 저장한다.

## iPhone 사용 흐름

1. Safari에서 프론트엔드 URL 접속
2. 개인용 접근 토큰 입력
3. 토큰 저장
4. 공유 버튼 → 홈 화면에 추가
5. 이후 홈 화면 아이콘으로 실행

## 보안 수준

이 토큰 방식은 혼자 쓰는 개인 앱용의 간단한 접근 제한이다. 공개 서비스용 인증 시스템은 아니다.
