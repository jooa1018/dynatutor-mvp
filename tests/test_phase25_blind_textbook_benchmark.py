import json
import math
from pathlib import Path

from engine.services import solve_problem


ROOT = Path("tests/benchmarks/blind_textbook_style")


def assert_has_answer(answers, *, symbol=None, label=None, numeric=None, unit=None, tolerance=1e-3):
    hits = []
    for ans in answers:
        if symbol is not None and ans.symbol == symbol:
            hits.append(ans)
        if label is not None and label in ans.label:
            hits.append(ans)
    assert hits, f"required answer missing: symbol={symbol!r}, label={label!r}, got={answers}"
    ans = hits[0]
    if numeric is not None:
        assert ans.numeric is not None
        assert math.isclose(float(ans.numeric), float(numeric), rel_tol=tolerance, abs_tol=tolerance), ans
    if unit is not None:
        assert ans.unit == unit, ans
    return ans


def _cases():
    for path in sorted(ROOT.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for case in data:
            yield path.name, case


def test_phase25_blind_textbook_inventory():
    cases = list(_cases())
    assert len(cases) == 100
    files = {name for name, _ in cases}
    assert files == {
        "kinematics.json",
        "projectile.json",
        "newton_laws.json",
        "incline_friction.json",
        "pulley.json",
        "work_energy.json",
        "momentum_collision.json",
        "rotation_rolling.json",
        "rigid_body_2d.json",
        "unsupported_cases.json",
    }
    assert all(case.get("must_not_use_llm_for_answer") is True for _, case in cases)


def test_phase25_blind_textbook_cases():
    failures = []
    for filename, case in _cases():
        out = solve_problem(case["problem_ko"])
        if case["should_solve"]:
            if not out.ok:
                failures.append((filename, case["id"], "not_ok", out.unsupported_reason, out.diagnosis.canonical.missing_info))
                continue
            if out.diagnosis.selected_solver != case["expected_solver"]:
                failures.append((filename, case["id"], "solver", out.diagnosis.selected_solver, case["expected_solver"]))
                continue
            expected = case.get("expected", {})
            if "answers" in expected:
                try:
                    for item in expected["answers"]:
                        assert_has_answer(
                            out.answers,
                            symbol=item.get("symbol"),
                            label=item.get("label"),
                            numeric=item.get("numeric"),
                            unit=item.get("unit"),
                            tolerance=item.get("tolerance", case.get("tolerance", 1e-3)),
                        )
                except AssertionError as exc:
                    failures.append((filename, case["id"], "answers", str(exc), [a.display for a in out.answers]))
                    continue
            elif "numeric" in expected:
                if not out.answer or out.answer.numeric is None:
                    failures.append((filename, case["id"], "no_numeric", out.answer.display if out.answer else None))
                    continue
                tol = case.get("tolerance", 1e-3)
                if not math.isclose(float(out.answer.numeric), float(expected["numeric"]), rel_tol=tol, abs_tol=tol):
                    failures.append((filename, case["id"], "numeric", out.answer.numeric, expected["numeric"], out.answer.display))
        else:
            if out.ok:
                failures.append((filename, case["id"], "unexpected_ok", out.diagnosis.selected_solver, out.answer.display if out.answer else None))
    assert not failures[:12]
