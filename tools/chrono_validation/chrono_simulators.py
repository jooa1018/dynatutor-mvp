from __future__ import annotations

from dataclasses import dataclass

try:
    from .common import try_import_chrono
except ImportError:  # direct script execution from tools/chrono_validation
    from common import try_import_chrono


@dataclass
class ChronoSimulationValue:
    value: float | None
    source: str
    status: str
    notes: list[str]


def _missing_chrono(topic: str) -> ChronoSimulationValue:
    _, message = try_import_chrono()
    return ChronoSimulationValue(
        value=None,
        source="chrono_unavailable",
        status="skipped",
        notes=[
            f"PyChrono is not available, so {topic} numerical simulation was skipped.",
            message,
            "Analytic validation still runs and is used for automated tests.",
        ],
    )


def simulate_rolling_down_ramp(*, height_m: float, body: str) -> ChronoSimulationValue:
    """Best-effort PyChrono hook for rolling validation.

    This function intentionally returns a skipped result unless PyChrono is
    importable. When PyChrono is available, it records that numerical simulation
    should be performed in the local Chrono environment. Project Chrono examples
    vary by installation, so the normal regression test does not depend on this.
    """
    chrono, _ = try_import_chrono()
    if chrono is None:
        return _missing_chrono(f"rolling_{body}")
    return ChronoSimulationValue(
        value=None,
        source="chrono_available_manual_run_required",
        status="manual_required",
        notes=[
            "PyChrono is importable. Build a local ramp/rolling-body scene with the installation-specific Chrono collision system.",
            f"Validation target: {body}, drop height={height_m} m.",
            "Compare final center-of-mass speed to DynaTutor's closed-form rolling energy result.",
        ],
    )


def simulate_incline_friction(*, theta_deg: float, mu: float) -> ChronoSimulationValue:
    chrono, _ = try_import_chrono()
    if chrono is None:
        return _missing_chrono("incline_friction")
    return ChronoSimulationValue(
        value=None,
        source="chrono_available_manual_run_required",
        status="manual_required",
        notes=[
            "PyChrono is importable. Build a sliding block on an inclined plane and estimate acceleration from velocity-time slope.",
            f"Validation target: theta={theta_deg} deg, mu={mu}.",
        ],
    )


def simulate_collision_restitution(*, m1: float, m2: float, v1: float, v2: float, restitution: float) -> ChronoSimulationValue:
    chrono, _ = try_import_chrono()
    if chrono is None:
        return _missing_chrono("collision_restitution")
    return ChronoSimulationValue(
        value=None,
        source="chrono_available_manual_run_required",
        status="manual_required",
        notes=[
            "PyChrono is importable. Build two collinear bodies with contact restitution and compare post-impact velocity.",
            f"Validation target: m1={m1}, m2={m2}, v1={v1}, v2={v2}, e={restitution}.",
        ],
    )


def simulate_massive_pulley(*, m1: float, m2: float, inertia: float, radius: float) -> ChronoSimulationValue:
    chrono, _ = try_import_chrono()
    if chrono is None:
        return _missing_chrono("massive_pulley")
    return ChronoSimulationValue(
        value=None,
        source="chrono_available_manual_run_required",
        status="manual_required",
        notes=[
            "PyChrono is importable. Build two masses and a rotational pulley constraint, then estimate acceleration.",
            f"Validation target: m1={m1}, m2={m2}, I={inertia}, R={radius}.",
        ],
    )
