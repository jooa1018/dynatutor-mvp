from __future__ import annotations

import math
import os
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


DEFAULT_PROTECTED_PREFIXES = ("/solve", "/diagnose", "/feedback", "/explain")


def _is_production() -> bool:
    return (
        os.environ.get("DYNATUTOR_ENV", "").strip().lower() == "production"
        or os.environ.get("RENDER", "").strip().lower() in {"1", "true"}
    )


def configured_rate_limit() -> int:
    raw = os.environ.get("DYNATUTOR_RATE_LIMIT_PER_MINUTE")
    if raw is None:
        return 60 if _is_production() else 0
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("DYNATUTOR_RATE_LIMIT_PER_MINUTE must be an integer") from exc
    if value < 0:
        raise RuntimeError("DYNATUTOR_RATE_LIMIT_PER_MINUTE must be >= 0")
    return value


def configured_max_body_bytes() -> int:
    raw = os.environ.get("DYNATUTOR_MAX_BODY_BYTES")
    if raw is None:
        return 64 * 1024 if _is_production() else 0
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("DYNATUTOR_MAX_BODY_BYTES must be an integer") from exc
    if value < 0:
        raise RuntimeError("DYNATUTOR_MAX_BODY_BYTES must be >= 0")
    return value


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        max_body_bytes: int,
        protected_prefixes: Iterable[str] = DEFAULT_PROTECTED_PREFIXES,
    ) -> None:
        super().__init__(app)
        self.max_body_bytes = max(0, int(max_body_bytes))
        self.protected_prefixes = tuple(protected_prefixes)

    async def dispatch(self, request: Request, call_next):
        if (
            self.max_body_bytes <= 0
            or request.method not in {"POST", "PUT", "PATCH"}
            or not request.url.path.startswith(self.protected_prefixes)
        ):
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > self.max_body_bytes
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": "요청 본문이 허용 크기를 초과했습니다.",
                        "code": "request_body_too_large",
                        "max_body_bytes": self.max_body_bytes,
                    },
                )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        requests_per_window: int,
        window_seconds: float = 60.0,
        protected_prefixes: Iterable[str] = DEFAULT_PROTECTED_PREFIXES,
    ) -> None:
        super().__init__(app)
        self.requests_per_window = max(0, int(requests_per_window))
        self.window_seconds = max(1.0, float(window_seconds))
        self.protected_prefixes = tuple(protected_prefixes)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _client_key(self, request: Request) -> str:
        if request.client is None or not request.client.host:
            return "unknown"
        return request.client.host

    async def dispatch(self, request: Request, call_next):
        if (
            self.requests_per_window <= 0
            or request.method == "OPTIONS"
            or not request.url.path.startswith(self.protected_prefixes)
        ):
            return await call_next(request)

        now = time.monotonic()
        cutoff = now - self.window_seconds
        key = self._client_key(request)
        retry_after = 1
        limited = False
        with self._lock:
            bucket = self._requests[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.requests_per_window:
                limited = True
                retry_after = max(1, math.ceil(self.window_seconds - (now - bucket[0])))
            else:
                bucket.append(now)

            if len(self._requests) > 2048:
                stale = [
                    client
                    for client, values in self._requests.items()
                    if not values or values[-1] <= cutoff
                ]
                for client in stale:
                    self._requests.pop(client, None)

        if limited:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "detail": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
                    "code": "rate_limit_exceeded",
                    "retry_after_seconds": retry_after,
                },
            )
        return await call_next(request)
