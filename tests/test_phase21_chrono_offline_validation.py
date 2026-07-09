import json
import subprocess
import sys
from pathlib import Path

from tools.chrono_validation.analytic_cases import all_phase21_cases, collision_restitution_cases, rolling_sphere_cases
from tools.chrono_validation.common import chrono_status, run_analytic_suite, suite_summary
from tools.chrono_validation.chrono_simulators import (
    simulate_collision_restitution,
    simulate_incline_friction,
    simulate_massive_pulley,
    simulate_rolling_down_ramp,
)


def test_phase21_analytic_validation_suite_passes():
    cases = all_phase21_cases()
    assert len(cases) >= 25
    results = run_analytic_suite(cases)
    summary = suite_summary(results)
    assert summary["count"] == len(cases)
    assert summary["failed"] == 0
    assert summary["passed"] == len(cases)


def test_phase21_collision_multi_value_display_validation():
    cases = collision_restitution_cases()
    results = run_analytic_suite(cases)
    assert results
    assert all(r.passed for r in results)
    assert any("numeric extracted from display label v1'" in note for r in results for note in r.notes)


def test_phase21_chrono_status_shape():
    status = chrono_status()
    assert "available" in status
    assert "message" in status
    assert isinstance(status["available"], bool)


def test_phase21_chrono_simulators_safe_without_pychrono():
    # These functions must not crash in environments without PyChrono.
    values = [
        simulate_rolling_down_ramp(height_m=1.0, body="sphere"),
        simulate_incline_friction(theta_deg=30, mu=0.1),
        simulate_collision_restitution(m1=2, m2=3, v1=4, v2=0, restitution=1.0),
        simulate_massive_pulley(m1=2, m2=5, inertia=0.12, radius=0.3),
    ]
    assert all(v.status in {"skipped", "manual_required"} for v in values)
    assert all(v.source in {"chrono_unavailable", "chrono_available_manual_run_required"} for v in values)


def test_phase21_run_all_validation_script_outputs_json():
    backend = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/chrono_validation/run_all_validations.py", "--strict"],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["suite"] == "phase21_all"
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["count"] >= 25
    assert "chrono_status" in payload
