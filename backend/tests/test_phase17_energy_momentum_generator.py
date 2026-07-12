import math

from engine.equation_generators.energy_momentum import build_energy_momentum_system, solve_energy_momentum_system
from engine.extraction.extractor import extract_problem
from engine.model_builder import build_physical_model
from engine.services import diagnose_problem, solve_problem


def test_phase17_constant_force_work_generator():
    c = extract_problem("힘 10N이 이동 방향으로 3m 작용했다. 한 일은?")
    model = build_physical_model(c)
    system = model.generated_energy_momentum_system
    assert system is not None
    assert system.generator == "energy_momentum"
    assert any(eq.equation == "W = F*s*cos(theta)" for eq in system.equations)
    solved = solve_energy_momentum_system(c, model)
    assert solved.ok
    assert math.isclose(solved.solution["W"], 30.0, rel_tol=1e-9)


def test_phase17_work_energy_speed_generator_drives_solver():
    out = solve_problem("정지 상태에서 질량 2kg 물체에 알짜일 16J이 작용했다. 최종속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "work_energy_speed"
    assert math.isclose(out.answer.numeric, 4.0, rel_tol=1e-9)
    assert any(step.title == "모델 기반 에너지/운동량 방정식" for step in out.steps)
    text = "\n".join(step.body for step in out.steps)
    assert "W_net = ΔK" in text


def test_phase17_spring_energy_generator():
    out = solve_problem("스프링 상수 k=200N/m, 압축 0.1m, 질량 2kg일 때 속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "spring_energy_speed"
    assert math.isclose(out.answer.numeric, 1.0, rel_tol=1e-9)
    system = out.diagnosis.physical_model["generated_energy_momentum_system"]
    assert any(eq["kind"] == "spring_energy" for eq in system["equations"])


def test_phase17_rolling_energy_generator_uses_shape_beta():
    out = solve_problem("정지 상태에서 속이 찬 구가 미끄러지지 않고 높이 1m 굴러 내려온다. 속도는?")
    assert out.ok
    expected = math.sqrt(2 * 9.81 / (1 + 2/5))
    assert math.isclose(out.answer.numeric, expected, rel_tol=1e-5)
    system = out.diagnosis.physical_model["generated_energy_momentum_system"]
    assert any(eq["kind"] == "shape_inertia" for eq in system["equations"])


def test_phase17_impulse_momentum_generator():
    out = solve_problem("힘 10N이 시간 2s 동안 작용한다. 충격량을 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "impulse_momentum"
    assert math.isclose(out.answer.numeric, 20.0, rel_tol=1e-9)
    system = out.diagnosis.physical_model["generated_energy_momentum_system"]
    assert any(eq["equation"] == "J = F*Δt" for eq in system["equations"])


def test_phase17_collision_generator_for_perfectly_inelastic():
    c = extract_problem("m1=2kg, m2=3kg, v1=4m/s, v2=0m/s, 완전비탄성 충돌이다. 충돌 후 속도는?")
    system = build_energy_momentum_system(c)
    assert system.equations_ready
    assert any(eq.equation == "v1f = v2f = v_f" for eq in system.equations)
    solved = solve_energy_momentum_system(c)
    assert solved.ok
    assert math.isclose(solved.solution["v_f"], 1.6, rel_tol=1e-9)


def test_phase17_diagnosis_exposes_energy_momentum_system():
    d = diagnose_problem("힘 10N이 이동 방향으로 3m 작용했다. 한 일은?")
    system = d.physical_model["generated_energy_momentum_system"]
    assert system["generator"] == "energy_momentum"
    assert system["equations_ready"] is True
