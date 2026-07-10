from pathlib import Path

from engine.extraction.extractor import extract_problem
from engine.services import solve_problem

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_phase36_runtime_sqlite_db_is_ignored_if_created():
    # Other tests may create the local default DB. The release rule is that it is
    # ignored/excluded from git and zip, not that local test runs can never create it.
    db = PROJECT_ROOT / "backend" / "dynatutor_records.sqlite"
    db.touch(exist_ok=True)
    text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "backend/dynatutor_records.sqlite" in text
    db.unlink(missing_ok=True)


def test_phase36_gitignore_excludes_runtime_sqlite_databases():
    text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.sqlite" in text
    assert "*.db" in text
    assert "dynatutor_records.sqlite" in text


def test_phase36_frontend_token_is_not_public_env():
    env_text = (PROJECT_ROOT / "frontend" / ".env.example").read_text(encoding="utf-8")
    api_text = (PROJECT_ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN" not in env_text
    assert "NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN" not in api_text
    assert "localStorage" in api_text
    assert "x-dynatutor-token" in api_text


def test_phase36_node_20_is_pinned_for_frontend():
    assert (PROJECT_ROOT / "frontend" / ".nvmrc").read_text(encoding="utf-8").strip() == "20"
    assert (PROJECT_ROOT / "frontend" / ".node-version").read_text(encoding="utf-8").strip() == "20"
    package_json = (PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    assert '"node": ">=20 <21"' in package_json


def test_phase36_elastic_collision_does_not_set_spring_flag():
    cp = extract_problem("질량 2kg 물체가 4m/s로 가다가 정지해 있는 질량 2kg 물체와 완전탄성충돌한다. 충돌 후 속도는?")
    assert cp.flags["collision"] is True
    assert cp.flags["elastic"] is True
    assert cp.flags["spring"] is False
    assert cp.system_type == "collision_1d"


def test_phase36_spring_terms_still_set_spring_flag():
    cp = extract_problem("스프링 상수 k=200N/m, 질량 2kg인 용수철-질량계의 주기는?")
    assert cp.flags["spring"] is True


def test_phase36_korean_table_hanging_frictionless_routes_and_solves():
    out = solve_problem("마찰 없는 수평 테이블 위 m1=2kg가 있고 m2=3kg가 실로 연결되어 매달려 있다. 가속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "pulley_table_hanging"
    assert out.diagnosis.canonical.pulley_topology == "table_hanging"
    assert abs(out.answer.numeric - (3 * 9.81 / 5)) < 1e-6


def test_phase36_korean_table_hanging_friction_ignored_phrase_routes_and_solves():
    out = solve_problem("수평 테이블 위의 2kg 물체와 매달린 3kg 물체가 가벼운 실로 연결되어 있다. 마찰은 무시한다. 가속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "pulley_table_hanging"
    assert out.diagnosis.canonical.knowns["m1"].value == 2
    assert out.diagnosis.canonical.knowns["m2"].value == 3


def test_phase36_korean_desk_hanging_with_friction_routes_and_solves():
    out = solve_problem("책상 위 물체 m1=2kg와 매달린 물체 m2=3kg가 줄로 연결되어 있다. 마찰계수는 0.2이다. 가속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "pulley_table_hanging"
    assert out.diagnosis.canonical.friction_type == "unspecified"
    assert abs(out.answer.numeric - ((3 * 9.81 - 0.2 * 2 * 9.81) / 5)) < 1e-6


def test_phase36_table_hanging_without_friction_condition_asks_clarification():
    out = solve_problem("수평 테이블 위 m1=2kg와 매달린 m2=3kg가 실로 연결되어 있다. 가속도는?")
    assert not out.ok
    assert out.diagnosis.selected_solver == "pulley_table_hanging"
    assert out.clarification is not None
    assert out.clarification.rule == "table_hanging_friction_unknown"
