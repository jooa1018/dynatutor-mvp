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
        solver="ChSolverPSOR:PSOR:max_iterations=200",
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
    assert not failures
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
