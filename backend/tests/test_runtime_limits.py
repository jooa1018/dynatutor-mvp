from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.runtime_limits import (
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
    configured_max_body_bytes,
    configured_rate_limit,
)


def _app_with_limits(*, rate: int = 0, body: int = 0) -> TestClient:
    app = FastAPI()

    @app.post("/solve")
    def solve():
        return {"ok": True}

    @app.get("/")
    def health():
        return {"ok": True}

    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=body)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_window=rate,
        window_seconds=60,
    )
    return TestClient(app)


def test_production_runtime_limits_have_safe_defaults(monkeypatch):
    monkeypatch.setenv("DYNATUTOR_ENV", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("DYNATUTOR_RATE_LIMIT_PER_MINUTE", raising=False)
    monkeypatch.delenv("DYNATUTOR_MAX_BODY_BYTES", raising=False)

    assert configured_rate_limit() == 60
    assert configured_max_body_bytes() == 64 * 1024


def test_local_runtime_limits_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DYNATUTOR_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("DYNATUTOR_RATE_LIMIT_PER_MINUTE", raising=False)
    monkeypatch.delenv("DYNATUTOR_MAX_BODY_BYTES", raising=False)

    assert configured_rate_limit() == 0
    assert configured_max_body_bytes() == 0


def test_rate_limit_returns_429_with_retry_after():
    client = _app_with_limits(rate=2)

    assert client.post("/solve").status_code == 200
    assert client.post("/solve").status_code == 200
    limited = client.post("/solve")

    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json()["code"] == "rate_limit_exceeded"
    assert client.get("/").status_code == 200


def test_body_limit_rejects_before_endpoint_execution():
    client = _app_with_limits(body=32)

    response = client.post(
        "/solve",
        content=b"x" * 33,
        headers={"content-type": "application/octet-stream"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "request_body_too_large"


def test_invalid_runtime_limit_configuration_fails_fast(monkeypatch):
    monkeypatch.setenv("DYNATUTOR_RATE_LIMIT_PER_MINUTE", "not-an-int")

    try:
        configured_rate_limit()
    except RuntimeError as exc:
        assert "must be an integer" in str(exc)
    else:
        raise AssertionError("invalid rate limit configuration must fail")
