import math

from engine.extraction.extractor import extract_problem
from engine.extraction.normalizer import normalize
from engine.services import solve_problem


def test_phase38_work_distance_condition_not_requested_output():
    out = solve_problem("물체에 작용한 힘은 변위와 같은 방향이며 크기는 10N이다. 물체가 3m 이동하는 동안 이 힘이 한 일은?")
    assert out.ok
    assert out.diagnosis.selected_solver == "constant_force_work"
    assert math.isclose(out.answer.numeric, 30.0, rel_tol=1e-9)
    assert out.diagnosis.canonical.requested_outputs == ["work"]


def test_phase38_work_force_direction_phrase_solves_without_distance_output():
    out = solve_problem("10N의 힘이 물체를 힘 방향으로 5m 이동시켰다. 한 일은?")
    assert out.ok
    assert math.isclose(out.answer.numeric, 50.0, rel_tol=1e-9)
    assert "distance" not in out.diagnosis.canonical.requested_outputs
    assert "work" in out.diagnosis.canonical.requested_outputs


def test_phase38_distance_requested_only_when_asked():
    cp = extract_problem("힘 10N이 작용하고 물체가 5m 이동했다. 이동거리를 구하라.")
    assert "distance" in cp.requested_outputs


def test_phase38_table_hanging_missing_friction_clarifies():
    out = solve_problem("수평면 위 물체 m1=2kg와 매달린 물체 m2=3kg가 줄과 도르래로 연결된다. 가속도와 장력을 구하라.")
    assert not out.ok
    assert out.diagnosis.selected_solver == "pulley_table_hanging"
    assert out.clarification is not None
    assert out.clarification.rule == "table_hanging_friction_unknown"
    assert out.clarification.why


def test_phase38_elastic_collision_not_spring_flag_regression():
    cp = extract_problem("완전탄성충돌: m1=1kg, m2=1kg, v1=5m/s, v2=0m/s이다. 나중 속도는?")
    assert cp.flags["collision"] is True
    assert cp.flags["elastic"] is True
    assert cp.flags["spring"] is False


def test_phase38_unit_normalization_variants():
    text = normalize("가속도 3m/s2, 각가속도 2rad/s^2, 토크 5뉴턴미터, 관성모멘트 2kg m^2")
    assert "3 m/s^2" in text
    assert "2 rad/s^2" in text
    assert "5 N*m" in text
    assert "2 kg*m^2" in text


def test_phase38_understood_card_patch_can_fix_requested_outputs():
    out = solve_problem(
        "물체에 작용한 힘은 변위와 같은 방향이며 크기는 10N이다. 물체가 3m 이동하는 동안 이 힘이 한 일은?",
        canonical_patch={"requested_outputs": ["work"]},
    )
    assert out.ok
    assert out.diagnosis.canonical.requested_outputs == ["work"]



def test_phase38_public_docs_env_policy(monkeypatch):
    from app.main import _public_docs_enabled

    monkeypatch.setenv("DYNATUTOR_ENV", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("DYNATUTOR_PUBLIC_DOCS", raising=False)
    assert _public_docs_enabled() is False

    monkeypatch.setenv("DYNATUTOR_PUBLIC_DOCS", "true")
    assert _public_docs_enabled() is True

    monkeypatch.setenv("DYNATUTOR_ENV", "development")
    monkeypatch.delenv("DYNATUTOR_PUBLIC_DOCS", raising=False)
    assert _public_docs_enabled() is True
