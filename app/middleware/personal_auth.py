import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

PUBLIC_EXACT_PATHS = {"/", "/explain/status"}
PUBLIC_PREFIXES: tuple[str, ...] = ()


def _configured_token() -> str:
    return os.environ.get("DYNATUTOR_ACCESS_TOKEN", "").strip()


def _request_token(request: Request) -> str:
    """헤더 인증만 허용한다 (Phase 35).

    쿼리 파라미터(?access_token=)는 서버/프록시 로그와 브라우저 히스토리에
    토큰이 남으므로 제거했다. export 다운로드도 프론트에서 헤더 fetch + blob
    방식으로 전환됐다.
    """
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return request.headers.get("x-dynatutor-token", "").strip()


class PersonalAccessTokenMiddleware(BaseHTTPMiddleware):
    """Tiny personal-use gate for cloud deployments.

    If DYNATUTOR_ACCESS_TOKEN is unset, the app behaves exactly like the local-only
    versions. If it is set, every useful API endpoint requires either:

    - x-dynatutor-token: <token>
    - Authorization: Bearer <token>

    This is intentionally simple, because DynaTutor is a personal study tool rather
    than a multi-user service.
    """

    async def dispatch(self, request: Request, call_next):
        token = _configured_token()
        if not token or request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in PUBLIC_EXACT_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        if _request_token(request) != token:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "DynaTutor 개인용 접근 토큰이 필요합니다. iPhone 화면의 토큰 설정에 DYNATUTOR_ACCESS_TOKEN 값을 입력하세요.",
                    "code": "dynatutor_token_required",
                },
            )
        return await call_next(request)
