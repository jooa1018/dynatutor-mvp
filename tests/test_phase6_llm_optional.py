from fastapi.testclient import TestClient

from app.main import app
from engine.llm.guardrails import validate_llm_explanation
from app.schemas.llm import LockedFacts

client = TestClient(app)


def test_llm_status_endpoint_without_key_is_safe(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_ENABLED", "auto")
    res = client.get("/explain/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert "API 키" in data["reason"]


def test_ai_explain_template_mode_returns_locked_facts(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    res = client.post("/explain/ai", json={
        "problem_text": "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.",
        "student_solution": "mg=ma라고 생각했습니다.",
        "force_template": True,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["used_llm"] is False
    assert data["locked_facts"]["answer_display"] == "a = 4.905 m/s²"
    assert "안전 설명" in data["explanation"]
    assert data["integrity_passed"] is True
    assert "쓰면 안 되는 식" in data["prompt_preview"]


def test_ai_explain_mock_mode(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_ENABLED", "true")
    res = client.post("/explain/ai", json={
        "problem_text": "힘 F=10 N이 거리 s=3 m 동안 같은 방향으로 작용한다. 한 일을 구하라.",
        "style": "friendly",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "mock"
    # Mock text intentionally does not repeat the locked numeric answer, so guard may fall back safely.
    assert data["explanation"]
    assert data["locked_facts"]["selected_solver"] == "constant_force_work"


def test_llm_guard_catches_new_numbers():
    locked = LockedFacts(
        problem_type="particle_on_incline",
        selected_solver="incline_no_friction",
        answer_display="a = 4.905 m/s²",
        known_values={"theta": "30 deg", "m": "5 kg"},
    )
    result = validate_llm_explanation("최종 답은 99 m/s² 입니다.", locked)
    assert result.passed is False
    assert result.warnings
