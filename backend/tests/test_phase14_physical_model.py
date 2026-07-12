from engine.extraction.extractor import extract_problem
from engine.model_builder import build_physical_model
from engine.services import diagnose_problem, solve_problem


def test_table_hanging_physical_model_contains_bodies_forces_constraints():
    c = extract_problem('수평면 위 m1=3kg와 매달린 m2=2kg가 도르래와 줄로 연결되어 있고 수평면 마찰계수는 0.2이다. 가속도는?')
    model = build_physical_model(c)
    assert model.equations_ready
    assert [b.role for b in model.bodies] == ['block_on_table', 'hanging_mass']
    assert any(f.kind == 'tension' and f.body_id == 'body_1' for f in model.forces)
    assert any(f.kind == 'friction' for f in model.forces)
    assert any(k.kind == 'same_acceleration_magnitude' for k in model.constraints)
    assert model.coordinates.positive_directions['body_2.y'] == '아래쪽'


def test_ambiguous_pulley_model_is_not_equations_ready():
    c = extract_problem('m1=2kg, m2=3kg가 줄과 도르래로 연결되어 있다. 가속도는?')
    model = build_physical_model(c)
    assert model.equations_ready is False
    assert any('도르래 구조' in x for x in model.missing_info)


def test_rolling_model_requires_shape_or_inertia():
    c = extract_problem('물체가 미끄러지지 않고 높이 1m 굴러 내려온다. 속도는?')
    model = build_physical_model(c)
    assert model.equations_ready is False
    assert any('물체 종류' in x for x in model.missing_info)


def test_diagnosis_response_exposes_physical_model():
    d = diagnose_problem('정지 상태에서 속이 찬 구가 미끄러지지 않고 높이 1m 굴러 내려온다. 속도는?')
    assert d.physical_model is not None
    assert d.physical_model['bodies'][0]['shape'] == 'solid_sphere'
    assert d.physical_model['equations_ready'] is True


def test_solve_steps_start_with_physical_model_cards():
    out = solve_problem('마찰 없는 30도 경사면 위의 5kg 블록이 미끄러진다. 가속도를 구하라.')
    assert out.ok
    assert out.steps[0].title.startswith('물리 모델')
    assert out.diagnosis.physical_model['system_type'] == 'particle_on_incline'
