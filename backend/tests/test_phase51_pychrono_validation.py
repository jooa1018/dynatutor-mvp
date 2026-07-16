from __future__ import annotations

import json
import math
import sys

import pytest

from engine.services import solve_problem
from tools.chrono_validation import chrono_compat
from tools.chrono_validation.chrono_simulators import (
    simulate_collision_restitution,
    simulate_incline_friction,
    simulate_massive_pulley,
    simulate_rolling_down_ramp,
)
from tools.chrono_validation.contracts import (
    CHRONO_STATUSES,
    ChronoResult,
    DEFAULT_CHRONO_POLICY,
)


REQUIRED_RESULT_FIELDS = {
    "case_id",
    "status",
    "observable",
    "value",
    "unit",
    "chrono_version",
    "solver",
    "contact_method",
    "time_step",
    "duration",
    "initial_conditions",
    "final_state",
    "constraint_errors",
    "invariant_errors",
    "warnings",
    "artifacts",
}


def _missing_import(name: str):
    raise ModuleNotFoundError(
        f"No module named {name!r}",
        name="pychrono",
    )


class _SpyVector:
    def __init__(self, x: float, y: float, z: float):
        self.values = (x, y, z)


class _SpyBaseIterativeSolver:
    def __init__(self):
        self.max_iterations_calls: list[int] = []
        self.as_iterative_calls = 0

    def AsIterative(self):
        self.as_iterative_calls += 1
        return self

    def SetMaxIterations(self, value: int):
        self.max_iterations_calls.append(value)


class _SpySolverType:
    PSOR = object()


class _SpySolverHolder:
    Type = _SpySolverType


class _SpyCollisionType:
    BULLET = object()


class _SpyCollisionHolder:
    Type = _SpyCollisionType


def _spy_chrono_adapter(
    *,
    expose_concrete_solver: bool = True,
    expose_set_solver: bool = True,
):
    state = {"systems": [], "solvers": []}

    class _SpyPsorSolver:
        def __init__(self):
            self.max_iterations_calls: list[int] = []
            self.sharpness_lambda_calls: list[float] = []
            state["solvers"].append(self)

        def SetMaxIterations(self, value: int):
            self.max_iterations_calls.append(value)

        def SetSharpnessLambda(self, value: float):
            self.sharpness_lambda_calls.append(value)

    class _SpyNscSystem:
        def __init__(self):
            self.base_solver = _SpyBaseIterativeSolver()
            self.collision_system = object()
            self.collision_system_type = None
            self.solver_type_calls = []
            self.get_solver_calls = 0
            self.set_solver_calls = []
            self.attached_solver = None
            self.gravity = None
            self.min_bounce_speed = None
            if not expose_set_solver:
                self.SetSolver = None
            state["systems"].append(self)

        def SetCollisionSystemType(self, value):
            self.collision_system_type = value

        def GetCollisionSystem(self):
            return self.collision_system

        def SetGravitationalAcceleration(self, value):
            self.gravity = value

        def SetSolverType(self, value):
            self.solver_type_calls.append(value)

        def GetSolver(self):
            self.get_solver_calls += 1
            return self.base_solver

        def SetSolver(self, value):
            self.set_solver_calls.append(value)
            self.attached_solver = value

        def SetMinBounceSpeed(self, value):
            self.min_bounce_speed = value

    module = type("_SpyChronoModule", (), {})()
    module.__version__ = "9.0.1"
    module.ChSystemNSC = _SpyNscSystem
    module.ChVector3d = _SpyVector
    module.ChSolver = _SpySolverHolder
    module.ChCollisionSystem = _SpyCollisionHolder
    if expose_concrete_solver:
        module.ChSolverPSOR = _SpyPsorSolver
    return chrono_compat.ChronoAdapter(module), state


@pytest.mark.unit
def test_phase51_result_contract_is_finite_versioned_and_complete():
    result = ChronoResult(
        case_id="contract",
        status="passed",
        observable="speed",
        value=1.25,
        unit="m/s",
        analytic_value=1.2,
        abs_error=0.05,
        relative_error=1.0 / 24.0,
        chrono_version="10.0.0",
        solver="ChSolverPSOR:PSOR:max_iterations=200:sharpness_lambda=1.0",
        contact_method="NSC:Coulomb",
        time_step=0.001,
        duration=0.5,
        initial_conditions={"v0": 0.0},
        final_state={"v": 1.25},
        constraint_errors={"signed": 0.0},
        invariant_errors={"energy_relative": 0.001},
        warnings=("test warning",),
        artifacts=({"kind": "test", "count": 1},),
        modeling_assumptions=("test assumption",),
    )
    payload = result.to_dict()
    assert REQUIRED_RESULT_FIELDS <= set(payload)
    assert payload["passed"] is True
    assert payload["schema_version"] == 1
    assert payload["suite_version"] == "phase51-pychrono-validation-v1"
    assert payload["policy_version"] == DEFAULT_CHRONO_POLICY.policy_version
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
    assert '"status": "passed"' in encoded
    assert CHRONO_STATUSES == {"passed", "failed", "skipped", "error"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sharpness_kwargs", "expected_sharpness", "expected_solver_name"),
    [
        pytest.param(
            {"sharpness_lambda": 0.9},
            0.9,
            "_SpyPsorSolver:PSOR:max_iterations=200:sharpness_lambda=0.9",
            id="explicit-disk",
        ),
        pytest.param(
            {},
            1.0,
            "_SpyPsorSolver:PSOR:max_iterations=200:sharpness_lambda=1.0",
            id="default",
        ),
    ],
)
def test_phase51_nsc_system_applies_and_records_psor_settings(
    sharpness_kwargs,
    expected_sharpness,
    expected_solver_name,
):
    adapter, state = _spy_chrono_adapter()

    system, solver_name = adapter.new_nsc_system(
        gravity=(0.0, -9.81, 0.0),
        max_iterations=200,
        **sharpness_kwargs,
    )

    assert state["systems"] == [system]
    assert state["solvers"] == [system.attached_solver]
    concrete_solver = state["solvers"][0]
    assert system.set_solver_calls == [concrete_solver]
    assert concrete_solver.max_iterations_calls == [200]
    assert concrete_solver.sharpness_lambda_calls == [expected_sharpness]
    assert system.solver_type_calls == []
    assert system.get_solver_calls == 0
    assert system.base_solver.as_iterative_calls == 0
    assert system.base_solver.max_iterations_calls == []
    assert solver_name == expected_solver_name


@pytest.mark.unit
@pytest.mark.parametrize(
    ("adapter_kwargs", "missing_api", "constructed_solver_count"),
    [
        pytest.param(
            {"expose_concrete_solver": False},
            "ChSolverPSOR",
            0,
            id="missing-concrete-solver",
        ),
        pytest.param(
            {"expose_set_solver": False},
            "SetSolver",
            1,
            id="missing-system-setter",
        ),
    ],
)
def test_phase51_nsc_system_fails_closed_without_concrete_solver_path(
    adapter_kwargs,
    missing_api,
    constructed_solver_count,
):
    adapter, state = _spy_chrono_adapter(**adapter_kwargs)

    with pytest.raises(
        chrono_compat.ChronoCompatibilityError,
        match=missing_api,
    ):
        adapter.new_nsc_system(
            gravity=(0.0, -9.81, 0.0),
            max_iterations=200,
            sharpness_lambda=0.9,
        )

    assert len(state["systems"]) == 1
    assert len(state["solvers"]) == constructed_solver_count
    assert state["systems"][0].attached_solver is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "max_iterations",
    [
        pytest.param(True, id="bool"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(200.0, id="float"),
        pytest.param("200", id="string"),
        pytest.param(math.nan, id="nan"),
        pytest.param(math.inf, id="positive-infinity"),
        pytest.param(-math.inf, id="negative-infinity"),
    ],
)
def test_phase51_nsc_system_rejects_invalid_max_iterations_before_creation(
    max_iterations,
):
    adapter, state = _spy_chrono_adapter()

    with pytest.raises(chrono_compat.ChronoCompatibilityError):
        adapter.new_nsc_system(
            gravity=(0.0, -9.81, 0.0),
            max_iterations=max_iterations,
        )

    assert state["systems"] == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "sharpness_lambda",
    [
        pytest.param(True, id="bool"),
        pytest.param(math.nan, id="nan"),
        pytest.param(math.inf, id="positive-infinity"),
        pytest.param(-math.inf, id="negative-infinity"),
        pytest.param(0.0, id="zero"),
        pytest.param(-0.1, id="negative"),
        pytest.param(1.000001, id="greater-than-one"),
    ],
)
def test_phase51_nsc_system_rejects_invalid_sharpness_before_creation(
    sharpness_lambda,
):
    adapter, state = _spy_chrono_adapter()

    with pytest.raises(chrono_compat.ChronoCompatibilityError):
        adapter.new_nsc_system(
            gravity=(0.0, -9.81, 0.0),
            max_iterations=200,
            sharpness_lambda=sharpness_lambda,
        )

    assert state["systems"] == []


@pytest.mark.unit
@pytest.mark.parametrize("field", ["value", "abs_error", "relative_error"])
def test_phase51_result_contract_rejects_nonfinite_evidence(field):
    kwargs = {
        "case_id": "nonfinite",
        "status": "passed",
        "observable": "speed",
        "value": 1.0,
        "unit": "m/s",
        "chrono_version": "10.0.0",
        "solver": "PSOR",
        "contact_method": "NSC",
        "time_step": 0.001,
        "duration": 0.1,
    }
    kwargs[field] = math.nan
    with pytest.raises(ValueError, match="finite"):
        ChronoResult(**kwargs)


@pytest.mark.unit
def test_phase51_missing_dependency_is_explicit_skip(monkeypatch):
    monkeypatch.setattr(chrono_compat.importlib, "import_module", _missing_import)
    results = [
        simulate_rolling_down_ramp(height_m=0.5, body="sphere"),
        simulate_rolling_down_ramp(height_m=0.5, body="disk"),
        simulate_incline_friction(theta_deg=20.0, mu=0.05),
        simulate_collision_restitution(
            m1=2.0,
            m2=3.0,
            v1=4.0,
            v2=0.0,
            restitution=1.0,
        ),
        simulate_massive_pulley(m1=2.0, m2=5.0, inertia=0.12, radius=0.3),
    ]
    assert {result.status for result in results} == {"skipped"}
    assert all(result.value is None for result in results)
    assert all(REQUIRED_RESULT_FIELDS <= set(result.to_dict()) for result in results)
    assert all("manual_required" not in json.dumps(result.to_dict()) for result in results)
    assert results[-1].contact_method == "constraint_driveline:no_contact"


@pytest.mark.unit
def test_phase51_broken_dependency_is_error_not_skip(monkeypatch):
    def broken_import(name: str):
        raise ImportError("DLL load failed while importing Chrono")

    monkeypatch.setattr(chrono_compat.importlib, "import_module", broken_import)
    result = simulate_rolling_down_ramp(height_m=0.5, body="sphere")
    assert result.status == "error"
    assert result.value is None
    assert "installation/ABI error" in result.warnings[0]


@pytest.mark.unit
def test_phase51_normal_solve_does_not_import_or_mutate_through_chrono(monkeypatch):
    before = solve_problem(
        "정지 상태에서 속이 찬 구가 미끄러지지 않고 높이 0.5m 굴러 내려온다. 속도는?"
    )
    assert before.ok and before.answer is not None
    answer_snapshot = (
        before.answer.numeric,
        before.answer.display,
        before.answer.unit,
    )
    pychrono_modules_before = {
        name for name in sys.modules if name == "pychrono" or name.startswith("pychrono.")
    }

    monkeypatch.setattr(chrono_compat.importlib, "import_module", _missing_import)
    result = simulate_rolling_down_ramp(height_m=0.5, body="sphere")

    assert result.status == "skipped"
    assert (
        before.answer.numeric,
        before.answer.display,
        before.answer.unit,
    ) == answer_snapshot
    assert {
        name for name in sys.modules if name == "pychrono" or name.startswith("pychrono.")
    } == pychrono_modules_before


@pytest.mark.regression
def test_phase51_real_pychrono_scenes_when_dependency_is_available():
    import_state = chrono_compat.import_chrono()
    if import_state.status == "unavailable":
        pytest.skip(import_state.message)
    assert import_state.status == "available", import_state.message

    results = [
        simulate_rolling_down_ramp(height_m=0.5, body="sphere"),
        simulate_rolling_down_ramp(height_m=0.5, body="disk"),
        simulate_incline_friction(theta_deg=20.0, mu=0.05),
        simulate_incline_friction(theta_deg=10.0, mu=0.30),
        simulate_collision_restitution(
            m1=2.0,
            m2=3.0,
            v1=4.0,
            v2=0.0,
            restitution=1.0,
        ),
        simulate_massive_pulley(m1=2.0, m2=5.0, inertia=0.12, radius=0.3),
    ]
    failures = {
        result.case_id: result.to_dict()
        for result in results
        if not result.passed
    }
    if failures:
        print(
            json.dumps(
                failures,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
    assert not failures
    assert results[1].initial_conditions["collision_envelope_m"] == (
        chrono_compat.COLLISION_ENVELOPE_M
    )
    assert results[1].initial_conditions["collision_safe_margin_m"] == (
        chrono_compat.COLLISION_SAFE_MARGIN_M
    )
    assert (
        results[1].initial_conditions["collision_shape_construction"]
        == "custom_ChBody_AddCylinder"
    )
    assert results[0].time_step == DEFAULT_CHRONO_POLICY.rolling_step_s
    assert results[1].time_step == DEFAULT_CHRONO_POLICY.rolling_step_s
    assert results[1].initial_conditions["time_step_s"] == results[1].time_step
    assert results[0].initial_conditions["solver_max_iterations"] == 200
    assert results[1].initial_conditions["solver_max_iterations"] == 200
    assert results[0].initial_conditions["solver_sharpness_lambda"] == 1.0
    assert results[1].initial_conditions["solver_sharpness_lambda"] == 0.9
    for index in (0, 2, 3, 4, 5):
        assert results[index].solver.endswith(
            "max_iterations=200:sharpness_lambda=1.0"
        )
    assert results[1].solver.endswith(
        "max_iterations=200:sharpness_lambda=0.9"
    )
    assert results[1].final_state["planar_guide"] == "ChLinkMatePlanar"
    assert results[1].artifacts[0]["planar_guide_count"] == 1
    assert results[1].constraint_errors["collision_geometry"] == pytest.approx(
        {
            "envelope_m": chrono_compat.COLLISION_ENVELOPE_M,
            "safe_margin_m": chrono_compat.COLLISION_SAFE_MARGIN_M,
        },
        rel=0.0,
        abs=1e-9,
    )
    assert all(result.chrono_version != "unavailable" for result in results)
    assert all(result.value is not None and math.isfinite(result.value) for result in results)
    assert results[0].value > results[1].value
    assert results[2].final_state["observed_regime"] == "slip"
    assert results[3].final_state["observed_regime"] == "stick"
    collision = results[4]
    assert collision.final_state["contact_start_s"] is not None
    assert collision.final_state["separation_time_s"] is not None
    pulley = results[5]
    assert pulley.final_state["gear_reactions_Nm"]["mass_1"] != 0.0
    assert pulley.final_state["gear_reactions_Nm"]["mass_2"] != 0.0
