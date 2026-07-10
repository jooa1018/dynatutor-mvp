from engine.examples.library import list_examples, example_stats
from engine.services import solve_problem
import engine.storage.notebook as notebook


def test_example_library_has_categories_and_expected_solver():
    examples = list_examples()
    assert len(examples) >= 10
    assert any(e["expected_solver"] == "polar_kinematics" for e in examples)
    stats = example_stats()
    assert stats["total"] == len(examples)
    assert "입자 동역학" in stats["categories"]


def test_learning_pack_fields_are_returned():
    out = solve_problem("극좌표에서 r=2 m, r_dot=0.5 m/s, r_ddot=0.1 m/s^2, theta_dot=3 rad/s, theta_ddot=0.2 rad/s^2 일 때 가속도 성분을 구하라.")
    assert out.ok
    assert out.concept_summary
    assert out.common_mistakes
    assert out.study_tips
    assert any("a_r" in eq for eq in out.equation_sheet)


def test_notebook_stats_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(notebook, "DB_PATH", tmp_path / "records.sqlite")
    notebook.add_record({
        "problem_text": "오답 1",
        "solver": "incline_no_friction",
        "answer_display": "a=1",
        "problem_type": "particle_on_incline",
        "tags": ["경사면", "F=ma"],
    })
    notebook.add_record({
        "problem_text": "오답 2",
        "solver": "projectile_motion",
        "answer_display": "R=1",
        "problem_type": "projectile_motion",
        "tags": ["포물선"],
    })
    stats = notebook.record_stats()
    assert stats["total"] == 2
    assert stats["by_type"]["particle_on_incline"] == 1
    assert stats["top_tags"]["경사면"] == 1
