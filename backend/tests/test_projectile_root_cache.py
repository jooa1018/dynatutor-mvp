from __future__ import annotations

import math

import sympy as sp

import engine.solvers.projectile as projectile_module
from engine.models import CanonicalProblem, Quantity
from engine.solvers.projectile import ProjectileMotionSolver


def _direct_roots(y0, vy, g, y_target):
    equation = sp.Eq(
        y0
        + vy * projectile_module._RAW_FLIGHT_TIME
        - sp.Rational(1, 2)
        * g
        * projectile_module._RAW_FLIGHT_TIME**2,
        y_target,
    )
    return tuple(sp.solve(equation, projectile_module._RAW_FLIGHT_TIME))


def _projectile_problem(
    raw_text: str = "first time the projectile reaches 10 m",
    *,
    landing_height: float = 10.0,
) -> CanonicalProblem:
    return CanonicalProblem(
        system_type="projectile_motion",
        knowns={
            "v0": Quantity("v0", 20.0, "m/s"),
            "theta": Quantity("theta", 60.0, "deg"),
            "g": Quantity("g", 9.81, "m/s^2"),
        },
        unknowns=["time"],
        requested_outputs=["time"],
        launch_height=0.0,
        landing_height=landing_height,
        raw_text=raw_text,
    )


def setup_function() -> None:
    projectile_module._projectile_height_roots.cache_clear()


def teardown_function() -> None:
    projectile_module._projectile_height_roots.cache_clear()


def test_root_cache_preserves_direct_solve_order_and_reuses_identical_input(
    monkeypatch,
) -> None:
    inputs = (0.0, 17.32050807568877, 9.81, 10.0)
    expected = _direct_roots(*inputs)
    solve_calls = []
    original_solve = projectile_module.sp.solve

    def counted_solve(*args, **kwargs):
        solve_calls.append((args, kwargs))
        return original_solve(*args, **kwargs)

    monkeypatch.setattr(projectile_module.sp, "solve", counted_solve)

    first = projectile_module._projectile_height_roots(*inputs)
    second = projectile_module._projectile_height_roots(*inputs)

    assert isinstance(first, tuple)
    assert first == expected
    assert [str(root) for root in first] == [str(root) for root in expected]
    assert second is first
    assert len(solve_calls) == 1
    assert projectile_module._projectile_height_roots.cache_info().hits == 1


def test_root_cache_misses_for_changed_input_and_typed_variants(
    monkeypatch,
) -> None:
    solve_calls = []
    original_solve = projectile_module.sp.solve

    def counted_solve(*args, **kwargs):
        solve_calls.append((args, kwargs))
        return original_solve(*args, **kwargs)

    monkeypatch.setattr(projectile_module.sp, "solve", counted_solve)

    exact = projectile_module._projectile_height_roots(0, 2, 1, 0)
    approximate = projectile_module._projectile_height_roots(
        0.0, 2.0, 1.0, 0.0
    )
    changed_target = projectile_module._projectile_height_roots(
        0.0, 2.0, 1.0, 1.0
    )
    info = projectile_module._projectile_height_roots.cache_info()

    assert [str(root) for root in exact] != [
        str(root) for root in approximate
    ]
    assert changed_target != approximate
    assert len(solve_calls) == 3
    assert info.misses == 3
    assert info.hits == 0


def test_root_cache_is_bounded_and_callers_cannot_mutate_cached_tuple() -> None:
    parameters = projectile_module._projectile_height_roots.cache_parameters()
    roots = projectile_module._projectile_height_roots(
        0.0, 17.32050807568877, 9.81, 10.0
    )

    first_list = list(roots)
    first_list.append(sp.Integer(999))
    second_list = list(
        projectile_module._projectile_height_roots(
            0.0, 17.32050807568877, 9.81, 10.0
        )
    )

    assert parameters == {"maxsize": 256, "typed": True}
    assert isinstance(roots, tuple)
    assert first_list is not second_list
    assert sp.Integer(999) not in second_list
    assert tuple(second_list) == roots


def test_real_projectile_solves_reuse_roots_but_rebuild_selection_evidence() -> None:
    solver = ProjectileMotionSolver()
    problem = _projectile_problem()

    first = solver.solve(problem)
    after_first = projectile_module._projectile_height_roots.cache_info()
    second = solver.solve(problem)
    after_second = projectile_module._projectile_height_roots.cache_info()

    assert first.ok is second.ok is True
    assert first.answer == second.answer
    assert first.answers == second.answers
    expected_first_root = _direct_roots(
        0.0, 20.0 * math.sin(math.radians(60.0)), 9.81, 10.0
    )[0]
    assert first.answer.numeric == round(float(expected_first_root), 6)
    assert after_first.misses == 1
    assert after_second.misses == 1
    assert after_second.hits == after_first.hits + 1
    assert first is not second
    assert first.answers is not second.answers
    assert first.selection_decision is not second.selection_decision
    assert (
        first.selection_decision.selected_candidate
        is not second.selection_decision.selected_candidate
    )
    assert (
        first.selection_decision.selected_candidate.branch_info
        is not second.selection_decision.selected_candidate.branch_info
    )


def test_cached_roots_preserve_rejected_zero_root_branch_evidence() -> None:
    solver = ProjectileMotionSolver()
    problem = _projectile_problem(
        "landing time when the projectile returns to the ground",
        landing_height=0.0,
    )

    first = solver.solve(problem)
    second = solver.solve(problem)

    for result in (first, second):
        assert result.ok is True
        assert result.selection_decision.status == "selected"
        assert len(result.selection_decision.rejected_candidates) == 1
        rejected = result.selection_decision.rejected_candidates[0]
        assert rejected.candidate.branch_info["root_index"] == 0
        assert str(rejected.candidate.branch_info["raw_root"]) in {
            "0",
            "0.0",
        }
        assert any(
            check.check_id == "variable:t" and not check.passed
            for check in rejected.checks
        )

    assert (
        first.selection_decision.rejected_candidates[0].candidate
        is not second.selection_decision.rejected_candidates[0].candidate
    )


def test_replaced_solve_dependency_bypasses_prewarmed_roots(monkeypatch) -> None:
    solver = ProjectileMotionSolver()
    problem = _projectile_problem()
    warm = solver.solve(problem)
    before_override = projectile_module._projectile_height_roots.cache_info()
    monkeypatch.setattr(
        projectile_module.sp,
        "solve",
        lambda *_args, **_kwargs: [],
    )

    injected = solver.solve(problem)
    after_override = projectile_module._projectile_height_roots.cache_info()

    assert warm.ok is True
    assert injected.ok is False
    assert injected.selection_decision.status == "no_valid_solution"
    assert injected.selection_decision.selected_candidate is None
    assert "no candidate" in injected.selection_decision.explanation
    assert after_override == before_override
