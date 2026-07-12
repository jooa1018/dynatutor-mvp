from __future__ import annotations

import pytest
from fastapi import HTTPException

import app.routes.diagnose as diagnose_route
import app.routes.solve as solve_route
from app.schemas.problem import ProblemRequest
from engine.errors import PhysicsDomainError


def _raise(exc: Exception):
    def raiser(*args, **kwargs):
        raise exc

    return raiser


def test_solve_maps_domain_failures_to_422_without_raw_exception(monkeypatch):
    monkeypatch.setattr(
        solve_route,
        "solve_problem",
        _raise(PhysicsDomainError("질량은 0보다 커야 합니다.")),
    )

    with pytest.raises(HTTPException) as caught:
        solve_route.solve(ProblemRequest(problem_text="test"))

    assert caught.value.status_code == 422
    assert "질량" in str(caught.value.detail)


def test_solve_maps_unexpected_failure_to_trace_id(monkeypatch):
    monkeypatch.setattr(
        solve_route,
        "solve_problem",
        _raise(RuntimeError("sensitive internal detail")),
    )

    with pytest.raises(HTTPException) as caught:
        solve_route.solve(ProblemRequest(problem_text="test"))

    assert caught.value.status_code == 500
    assert "trace_id=" in str(caught.value.detail)
    assert "sensitive internal detail" not in str(caught.value.detail)


def test_diagnose_maps_unexpected_index_failure_to_500(monkeypatch):
    monkeypatch.setattr(
        diagnose_route,
        "diagnose_problem",
        _raise(IndexError("bad parse index")),
    )

    with pytest.raises(HTTPException) as caught:
        diagnose_route.diagnose(ProblemRequest(problem_text="test"))

    assert caught.value.status_code == 500
    assert "trace_id=" in str(caught.value.detail)
    assert "bad parse index" not in str(caught.value.detail)
