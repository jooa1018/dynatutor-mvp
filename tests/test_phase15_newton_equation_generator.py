import math

from engine.equation_generators import build_particle_newton_system, solve_particle_newton_system
from engine.extraction.extractor import extract_problem
from engine.model_builder import build_physical_model
from engine.services import diagnose_problem, solve_problem


def test_phase15_incline_generator_emits_simplified_newton_equation():
    c = extract_problem("마찰 없는 30도 경사면에서 블록의 가속도를 구하라.")
    model = build_physical_model(c)
    system = model.generated_equation_system
    assert system is not None
    assert system.generator == "particle_newton"
    assert system.equations_ready
    assert any(eq.equation == "g*sin(theta) = a" for eq in system.equations)
    solved = solve_particle_newton_system(c, model)
    assert solved.ok
    assert math.isclose(float(solved.solution[next(k for k in solved.solution if str(k) == "a")]), 4.905, rel_tol=1e-4)


def test_phase15_table_hanging_generator_drives_solver_step():
    out = solve_problem("수평면 위 m1=3kg와 매달린 m2=2kg가 도르래와 줄로 연결되어 있고 수평면 마찰계수는 0.2이다. 가속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "pulley_table_hanging"
    assert any(step.title == "모델 기반 방정식 생성" for step in out.steps)
    text = "\n".join(step.body for step in out.steps)
    assert "T - f = m1*a" in text
    assert "m2*g - T = m2*a" in text


def test_phase15_atwood_equations_are_generated_from_physical_model():
    c = extract_problem("m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도는?")
    model = build_physical_model(c)
    system = build_particle_newton_system(c, model)
    assert system.equations_ready
    assert [eq.equation for eq in system.equations] == ["T - m1*g = m1*a", "m2*g - T = m2*a"]
    out = solve_problem(c.raw_text)
    assert out.ok
    assert math.isclose(out.answer.numeric, 1.962, rel_tol=2e-3)


def test_phase15_massive_pulley_includes_newton_euler_equation():
    c = extract_problem("질량 있는 도르래에 m1=2 kg, m2=5 kg가 줄로 연결되어 있다. 도르래 관성모멘트 I=0.12 kgm^2, 도르래 반지름 R=0.3 m 일 때 가속도를 구하라.")
    model = build_physical_model(c)
    system = model.generated_equation_system
    assert system is not None
    assert any(eq.kind == "newton_euler" for eq in system.equations)
    assert any("(T2-T1)*R = I*(a/R)" in eq.equation for eq in system.equations)


def test_phase15_diagnosis_exposes_generated_equation_system_dict():
    d = diagnose_problem("m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도는?")
    system = d.physical_model["generated_equation_system"]
    assert system["generator"] == "particle_newton"
    assert system["equations_ready"] is True
    assert any(eq["kind"] == "newton_second_law" for eq in system["equations"])
