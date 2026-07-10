import math

from engine.extraction.extractor import extract_problem
from engine.physics_core.units import magnitude_si
from engine.services import solve_problem


def test_single_particle_force_to_acceleration():
    out = solve_problem("질량 0.5kg인 물체에 힘 10N이 작용한다. 가속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "single_particle_newton"
    assert math.isclose(out.answer.numeric, 20.0, rel_tol=1e-9)


def test_single_particle_mass_in_grams():
    out = solve_problem("질량 500g인 물체에 10N의 알짜힘이 작용한다. 가속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "single_particle_newton"
    assert math.isclose(out.answer.numeric, 20.0, rel_tol=1e-9)


def test_single_particle_acceleration_to_force():
    out = solve_problem("질량 2kg인 물체가 3m/s²로 가속된다. 필요한 알짜힘은?")
    assert out.ok
    assert out.diagnosis.selected_solver == "single_particle_newton"
    assert math.isclose(out.answer.numeric, 6.0, rel_tol=1e-9)


def test_single_particle_force_direction_ambiguous():
    out = solve_problem("물체에 10N과 5N의 힘이 작용한다. 가속도는?")
    assert not out.ok
    assert "힘 방향" in (out.unsupported_reason or "") or "합력" in (out.unsupported_reason or "")


def test_incline_hanging_kinetic_friction_direction_missing():
    problem = "m1=10kg가 30도 경사면 위에 있고 m2=1kg가 도르래에 매달려 있다. 운동마찰계수 0.5일 때 가속도는?"
    out = solve_problem(problem)
    assert not out.ok
    assert out.diagnosis.selected_solver == "pulley_incline_hanging"
    assert "운동마찰 방향" in "\n".join(out.verification.errors + out.verification.warnings) or "운동 방향" in (out.unsupported_reason or "")


def test_incline_hanging_m2_down_direction_given():
    problem = "m1=10kg가 30도 경사면 위에 있고 m2=8kg가 도르래에 매달려 있다. m2가 아래로 내려간다. 운동마찰계수 0.2일 때 가속도는?"
    out = solve_problem(problem)
    assert out.ok
    assert out.diagnosis.selected_solver == "pulley_incline_hanging"
    expected = (8*9.81 - 10*9.81*math.sin(math.radians(30)) - 0.2*10*9.81*math.cos(math.radians(30))) / (10+8)
    assert math.isclose(out.answer.numeric, expected, rel_tol=1e-5)


def test_incline_hanging_m1_down_direction_given():
    problem = "m1=10kg가 30도 경사면 아래로 내려가고 m2=1kg가 매달려 있다. 운동마찰계수 0.2일 때 가속도는?"
    out = solve_problem(problem)
    assert out.ok
    assert out.diagnosis.selected_solver == "pulley_incline_hanging"
    expected = (10*9.81*math.sin(math.radians(30)) - 0.2*10*9.81*math.cos(math.radians(30)) - 1*9.81) / (10+1)
    assert math.isclose(out.answer.numeric, expected, rel_tol=1e-5)


def test_initial_velocity_kmh_expression_1():
    out = solve_problem("자동차가 36km/h에서 10초 동안 가속도 2m/s²로 달린다. 최종속도는?")
    assert out.ok
    assert math.isclose(out.answer.numeric, 30.0, rel_tol=1e-9)


def test_initial_velocity_kmh_expression_2():
    out = solve_problem("자동차가 처음 속도 36km/h로 달리다가 10초 동안 2m/s²로 가속한다. 최종속도는?")
    assert out.ok
    assert math.isclose(out.answer.numeric, 30.0, rel_tol=1e-9)


def test_initial_velocity_kmh_expression_3():
    out = solve_problem("자동차가 36km/h로 달리다가 10초 동안 2m/s²의 가속도를 받았다. 나중 속도는?")
    assert out.ok
    assert math.isclose(out.answer.numeric, 30.0, rel_tol=1e-9)


def test_kmh_to_ms_unit_conversion():
    c = extract_problem("자동차가 36 km/h에서 출발하여 10초 동안 가속도 2m/s²로 달린다. 최종속도는?")
    assert "v0" in c.knowns
    assert math.isclose(magnitude_si(c.knowns["v0"], "m/s"), 10.0, rel_tol=1e-9)


def test_incline_hanging_candidate_without_word_pulley():
    # Phase 34: 정적 거절("줄/도르래 필요") → 원탭 확정 질문으로 개선.
    out = solve_problem("m1=10kg가 30도 경사면 위에 있고 m2=1kg가 매달려 있다. 가속도는?")
    assert not out.ok
    assert out.diagnosis.canonical.system_type == "incline_hanging_candidate"
    assert out.clarification is not None
    assert out.clarification.rule == "incline_hanging_candidate"
    # 원탭 resolve: '연결됨' 선택 → pulley_incline_hanging으로 풀림
    import copy as _copy
    from engine.routing.clarify import apply_clarify_patch
    from engine.extraction.extractor import extract_problem
    cp = extract_problem("m1=10kg가 30도 경사면 위에 있고 m2=1kg가 매달려 있다. 가속도는?")
    patch = next(o for o in out.clarification.options if o.id == "connected_pulley").patch
    cp2 = apply_clarify_patch(_copy.deepcopy(cp), dict(patch))
    from engine.solvers.registry import SolverRegistry
    r = SolverRegistry().select(cp2).solve(cp2)
    assert r.ok


def test_incline_hanging_with_pulley_word_should_solve_or_check_direction():
    out = solve_problem("m1=10kg가 30도 경사면 위에 있고 m2=1kg가 도르래에 매달려 있다. 가속도는?")
    assert out.diagnosis.canonical.system_type == "pulley_incline_hanging"
    assert out.diagnosis.selected_solver == "pulley_incline_hanging"
    assert out.ok
