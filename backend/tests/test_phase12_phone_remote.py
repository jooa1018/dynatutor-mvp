import os
from fastapi.testclient import TestClient


def _client(monkeypatch, token="secret-token"):
    monkeypatch.setenv("DYNATUTOR_ACCESS_TOKEN", token)
    from app.main import app
    return TestClient(app)


def test_personal_token_blocks_protected_api(monkeypatch):
    client = _client(monkeypatch)
    res = client.post("/solve", json={"problem_text": "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라."})
    assert res.status_code == 401
    assert res.json()["code"] == "dynatutor_token_required"


def test_personal_token_header_allows_solve(monkeypatch):
    client = _client(monkeypatch)
    res = client.post(
        "/solve",
        headers={"x-dynatutor-token": "secret-token"},
        json={"problem_text": "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라."},
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_personal_token_query_allows_export(monkeypatch):
    client = _client(monkeypatch)
    # Phase 35: 쿼리 토큰은 로그 유출 위험으로 제거 — 이제 401이어야 한다.
    res = client.get("/records/export?access_token=secret-token")
    assert res.status_code == 401
    # 같은 요청이 헤더 인증으로는 통과한다 (export도 헤더 방식).
    res = client.get("/records/export", headers={"x-dynatutor-token": "secret-token"})
    assert res.status_code == 200
    assert res.json()["format"] == "dynatutor-local-notebook-v1"


def test_unset_token_keeps_local_mode_open(monkeypatch):
    monkeypatch.delenv("DYNATUTOR_ACCESS_TOKEN", raising=False)
    from app.main import app
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    res = client.post("/solve", json={"problem_text": "힘 10N이 물체를 30cm 이동시켰다. 한 일을 구하라."})
    assert res.status_code == 200


def test_production_requires_access_token(monkeypatch):
    """Phase 35: production 환경에서 토큰 미설정 시 서버 기동을 거부한다."""
    from app.main import _enforce_production_token

    monkeypatch.setenv("DYNATUTOR_ENV", "production")
    monkeypatch.delenv("DYNATUTOR_ACCESS_TOKEN", raising=False)
    import pytest as _pytest

    with _pytest.raises(RuntimeError):
        _enforce_production_token()
    # 토큰이 있으면 통과
    monkeypatch.setenv("DYNATUTOR_ACCESS_TOKEN", "tok")
    _enforce_production_token()
    # 로컬(환경 미표시)은 토큰 없이도 통과
    monkeypatch.setenv("DYNATUTOR_ENV", "")
    monkeypatch.delenv("DYNATUTOR_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    _enforce_production_token()
