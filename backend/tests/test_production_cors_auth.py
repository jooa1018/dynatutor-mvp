from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.main import app, cors_origins
from app.middleware.personal_auth import PersonalAccessTokenMiddleware


def _allowed_origin() -> tuple[str, str]:
    if "*" in cors_origins:
        return "https://frontend.example", "*"
    return cors_origins[0], cors_origins[0]


def test_cors_is_outermost_middleware() -> None:
    middleware_classes = [middleware.cls for middleware in app.user_middleware]
    assert middleware_classes.index(CORSMiddleware) < middleware_classes.index(
        PersonalAccessTokenMiddleware
    )


def test_auth_responses_keep_cors_headers(monkeypatch) -> None:
    monkeypatch.setenv("DYNATUTOR_ACCESS_TOKEN", "production-test-token")
    origin, expected_allow_origin = _allowed_origin()

    with TestClient(app) as client:
        missing = client.get("/examples", headers={"Origin": origin})
        wrong = client.get(
            "/examples",
            headers={
                "Origin": origin,
                "x-dynatutor-token": "wrong-token",
            },
        )
        valid = client.get(
            "/examples",
            headers={
                "Origin": origin,
                "x-dynatutor-token": "production-test-token",
            },
        )

    assert missing.status_code == 401
    assert missing.headers["access-control-allow-origin"] == expected_allow_origin
    assert wrong.status_code == 401
    assert wrong.headers["access-control-allow-origin"] == expected_allow_origin
    assert valid.status_code == 200
    assert valid.headers["access-control-allow-origin"] == expected_allow_origin
