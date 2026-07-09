import math
from engine.services import solve_problem, diagnose_problem
import engine.storage.notebook as notebook


def test_constant_acceleration_final_velocity():
    out = solve_problem("정지한 물체가 등가속도 a=2 m/s^2 로 시간 5 s 동안 직선 운동한다. 최종속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "constant_acceleration_1d"
    assert out.answer.unit == "m/s"
    assert math.isclose(out.answer.numeric, 10.0, rel_tol=1e-4)


def test_projectile_range():
    out = solve_problem("초속도 20 m/s, 발사각 30도인 포물선 운동에서 같은 높이에 착지할 때 사거리를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "projectile_motion"
    assert out.answer.unit == "m"
    assert 34 < out.answer.numeric < 36


def test_constant_force_work():
    out = solve_problem("힘 F=10 N이 거리 s=3 m 동안 같은 방향으로 작용한다. 한 일을 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "constant_force_work"
    assert math.isclose(out.answer.numeric, 30.0, rel_tol=1e-4)


def test_fixed_axis_rotation():
    out = solve_problem("고정축 회전체에 토크 tau=12 Nm, 관성모멘트 I=3 kgm^2 이 작용한다. 각가속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "fixed_axis_rotation"
    assert math.isclose(out.answer.numeric, 4.0, rel_tol=1e-4)


def test_elastic_collision_with_e():
    out = solve_problem("1차원 충돌에서 m1=2 kg, m2=3 kg, v1=4 m/s, v2=0 m/s, 반발계수 e=0.5 이다. 충돌 후 속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "collision_1d"
    assert "v1'" in out.answer.display


def test_records_storage_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(notebook, "DB_PATH", tmp_path / "records.sqlite")
    item = notebook.add_record({
        "problem_text": "테스트 문제",
        "solver": "unit_test",
        "answer_display": "a=1",
        "problem_type": "test",
        "tags": ["phase2"],
    })
    assert item["id"] >= 1
    items = notebook.list_records(5)
    assert any(r["problem_text"] == "테스트 문제" for r in items)


def test_diagnosis_for_projectile_cards():
    out = diagnose_problem("초속도 10 m/s, 45도 포물선 운동의 최대높이를 구하라.")
    assert out.canonical.system_type == "projectile_motion"
    assert "x축: 수평 방향" in out.coordinate_guide
