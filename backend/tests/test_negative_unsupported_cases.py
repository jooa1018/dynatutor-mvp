from engine.services import solve_problem


def test_rolling_without_shape_should_not_solve():
    out = solve_problem("물체가 미끄러지지 않고 높이 1m 굴러 내려온다. 속도는?")
    assert out.ok is False
    assert "물체 종류" in (out.unsupported_reason or "") or any("물체 종류" in e for e in out.verification.errors + out.diagnosis.canonical.missing_info)


def test_ambiguous_pulley_should_not_solve():
    out = solve_problem("m1=2kg, m2=3kg가 줄과 도르래로 연결되어 있다. 가속도는?")
    assert out.ok is False
    assert out.diagnosis.canonical.system_type == "ambiguous_pulley"
    assert any("도르래 구조" in x for x in out.diagnosis.canonical.missing_info)


def test_work_without_direction_strict_mode():
    out = solve_problem("힘 10N이 물체에 작용해 3m 이동했다. 한 일은?")
    assert out.ok is False
    assert any("방향" in e or "각도" in e for e in out.verification.errors + out.diagnosis.canonical.missing_info)


def test_rigid_body_without_direction_should_not_solve():
    out = solve_problem("평면강체에서 A와 B 사이 거리는 1m, 각속도는 2rad/s이다. B점 속도는?")
    assert out.ok is False
    assert any("A점 속도" in e or "방향" in e or "좌표" in e for e in out.verification.errors + out.diagnosis.canonical.missing_info)
