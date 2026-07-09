from fastapi.testclient import TestClient

from app.main import app
from app.schemas.llm import LockedFacts
from engine.llm.guardrails import build_locked_facts, validate_llm_explanation
from engine.llm.prompt import build_llm_prompt
from engine.services import solve_problem

client = TestClient(app)


def _incline_locked():
    solution = solve_problem("질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.")
    return build_locked_facts(solution), solution


def test_phase22_locked_facts_include_hash_allowed_numbers_and_not_applicable():
    locked, solution = _incline_locked()
    assert locked.locked_facts_version == "phase22"
    assert locked.locked_hash
    assert locked.solver_ok is True
    assert locked.answer_display == "a = 4.905 m/s²"
    assert 4.905 in locked.answer_numbers
    assert locked.answer_unit == "m/s²"
    assert locked.allowed_numbers
    assert isinstance(locked.not_applicable_equations, list)


def test_phase22_prompt_contains_locked_facts_json_and_hash():
    locked, solution = _incline_locked()
    prompt = build_llm_prompt("문제", None, solution, locked, "beginner", "friendly")
    assert "LOCKED_FACTS_JSON" in prompt
    assert locked.locked_hash in prompt
    assert "answer_display" in prompt
    assert "쓰면 안 되는 식" in prompt
    assert "새 숫자" in prompt


def test_phase22_guardrail_accepts_safe_explanation():
    locked, _ = _incline_locked()
    text = """
### 한눈에 보기
경사면 방향 힘 성분을 이용하는 문제입니다.

### 왜 이 식을 쓰는가
마찰이 없으므로 경사면 방향으로 mg sinθ = ma를 씁니다.

### 단계별 설명
1. θ=30 deg를 확인합니다.
2. solver 결과를 그대로 설명합니다.
3. 가속도는 4.905 m/s² 입니다.

### 실수 방지
수직방향 힘을 경사면 방향 식에 넣지 않습니다.

### 마지막 확인
최종 답은 a = 4.905 m/s² 입니다.
"""
    result = validate_llm_explanation(text, locked)
    assert result.passed is True
    assert not result.warnings


def test_phase22_guardrail_rejects_changed_final_number():
    locked, _ = _incline_locked()
    result = validate_llm_explanation("### 마지막 확인\n최종 답은 a = 9.99 m/s² 입니다.", locked)
    assert result.passed is False
    assert any("없던 숫자" in w or "최종답" in w for w in result.warnings)


def test_phase22_guardrail_rejects_missing_final_answer():
    locked, _ = _incline_locked()
    result = validate_llm_explanation("### 한눈에 보기\n경사면 문제입니다. 쉽게 풀 수 있습니다.", locked)
    assert result.passed is False
    assert any("최종답" in w or "최종 답" in w for w in result.warnings)


def test_phase22_guardrail_rejects_not_applicable_equation():
    locked, _ = _incline_locked()
    locked.not_applicable_equations = ["v_f^2 = v_0^2 + 2as"]
    result = validate_llm_explanation("### 마지막 확인\n최종 답은 a = 4.905 m/s² 입니다. v_f^2 = v_0^2 + 2as를 쓰면 됩니다.", locked)
    assert result.passed is False
    assert any("쓰면 안 되는 식" in w for w in result.warnings)


def test_phase22_unsupported_problem_cannot_get_fake_numeric_answer():
    unsupported = solve_problem("m1=2kg, m2=3kg가 줄과 도르래로 연결되어 있다. 가속도는?")
    locked = build_locked_facts(unsupported)
    assert locked.solver_ok is False
    result = validate_llm_explanation("정답은 3.14 m/s² 입니다. 계산하면 바로 나옵니다.", locked)
    assert result.passed is False
    assert any("지원하지 않는 문제" in w for w in result.warnings)


def test_phase22_template_endpoint_reports_integrity_metadata(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_ENABLED", "auto")
    res = client.post("/explain/ai", json={
        "problem_text": "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.",
        "force_template": True,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["used_llm"] is False
    assert data["displayed_source"] == "template"
    assert data["integrity_passed"] is True
    assert data["locked_facts"]["locked_hash"]
    assert data["locked_facts"]["locked_facts_version"] == "phase22"
    assert "### 마지막 확인" in data["explanation"]


def test_phase22_mock_llm_falls_back_when_final_answer_missing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_ENABLED", "true")
    res = client.post("/explain/ai", json={
        "problem_text": "힘 F=10 N이 거리 s=3 m 동안 같은 방향으로 작용한다. 한 일을 구하라.",
        "style": "friendly",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "mock"
    assert data["used_llm"] is False
    assert data["displayed_source"] == "template_fallback_after_guardrail"
    assert data["integrity_passed"] is False
    assert "W = 30.000 J" in data["explanation"]
