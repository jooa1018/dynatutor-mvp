from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from engine.capabilities.loader import (
    CapabilityConfigError,
    PHASE51_EXTERNAL_PATHS_BY_FAMILY,
    load_capability_matrix,
    validate_capability_validator_ids,
)


CAPABILITY_PATH = (
    Path(__file__).resolve().parents[1]
    / "engine"
    / "capabilities"
    / "dynamics_capabilities.json"
)


@pytest.mark.unit
def test_phase51_capability_paths_are_exact_and_solver_scoped():
    matrix = load_capability_matrix()
    expected = {
        family: (dict(paths) if paths else None)
        for family, paths in PHASE51_EXTERNAL_PATHS_BY_FAMILY.items()
    }
    observed = {
        family: (
            dict(roles["external_validation_path"])
            if roles["external_validation_path"] is not None
            else None
        )
        for family, roles in matrix.solver_path_roles.items()
    }
    assert observed == expected
    assert observed["pulley"] == {
        "massive_pulley_atwood": "phase51.pychrono.massive_pulley"
    }
    assert "pulley_atwood" not in observed["pulley"]
    assert observed["rolling"] == {
        "pure_rolling_energy": "phase51.pychrono.rolling"
    }
    assert "rolling_energy_general" not in observed["rolling"]
    assert observed["work_energy"] is None
    assert observed["fixed_axis_rotation"] is None


@pytest.mark.unit
def test_phase51_capability_entries_match_external_paths_without_manual_claims():
    raw = json.loads(CAPABILITY_PATH.read_text(encoding="utf-8"))
    by_solver = {
        entry["analytic_solver"]: entry["chrono_support"]
        for entry in raw["capabilities"]
    }
    expected = {
        "incline_with_friction": "phase51.pychrono.incline_friction",
        "massive_pulley_atwood": "phase51.pychrono.massive_pulley",
        "pure_rolling_energy": "phase51.pychrono.rolling",
        "collision_1d": "phase51.pychrono.collision_restitution",
    }
    assert {
        solver: support["external_validation_path"]
        for solver, support in by_solver.items()
        if support["status"] == "automated_optional"
    } == expected
    assert by_solver["rolling_energy_general"]["status"] == "none"
    assert "manual_required" not in json.dumps(raw, ensure_ascii=False)


@pytest.mark.unit
def test_phase51_loader_rejects_broadened_or_unknown_external_paths():
    raw = json.loads(CAPABILITY_PATH.read_text(encoding="utf-8"))

    broadened = deepcopy(raw)
    broadened["solver_path_roles"]["pulley"]["external_validation_path"][
        "pulley_atwood"
    ] = "phase51.pychrono.massive_pulley"
    with pytest.raises(CapabilityConfigError, match="external_validation_path"):
        validate_capability_validator_ids(broadened)

    unrelated = deepcopy(raw)
    unrelated["solver_path_roles"]["work_energy"]["external_validation_path"] = {
        "work_energy_speed": "phase51.pychrono.work_energy"
    }
    with pytest.raises(CapabilityConfigError, match="must be null"):
        validate_capability_validator_ids(unrelated)
