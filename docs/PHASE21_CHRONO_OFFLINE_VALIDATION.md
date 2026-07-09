# Phase 21 Chrono Offline Validation

Phase 21 replaces the old Chrono placeholder scripts with a real validation
harness.

## Goal

Compare DynaTutor closed-form solver results against external validation
references.

Phase 21 has two layers:

```text
Layer 1: DynaTutor closed-form vs analytic reference
  - automated
  - part of tests
  - works in normal environment

Layer 2: DynaTutor closed-form vs PyChrono numerical simulation
  - optional
  - local/manual
  - requires separate PyChrono installation
```

## Why two layers?

Project Chrono / PyChrono is intentionally not a runtime dependency.

DynaTutor must stay lightweight for personal study use. Chrono is useful for
offline developer validation, but it should not be required for solving ordinary
homework-style problems.

## Updated files

```text
backend/tools/chrono_validation/common.py
backend/tools/chrono_validation/analytic_cases.py
backend/tools/chrono_validation/chrono_simulators.py
backend/tools/chrono_validation/run_all_validations.py
backend/tools/chrono_validation/validate_rolling_sphere.py
backend/tools/chrono_validation/validate_rolling_disk.py
backend/tools/chrono_validation/validate_incline_friction.py
backend/tools/chrono_validation/validate_collision_restitution.py
backend/tools/chrono_validation/validate_massive_pulley.py
```

## Validation suites

### Rolling sphere

```text
v = sqrt(2gh/(1+2/5))
```

### Rolling disk

```text
v = sqrt(2gh/(1+1/2))
```

### Incline with kinetic friction

```text
a = g(sinθ - μ cosθ)
```

### Collision with restitution / elastic collision

```text
momentum conservation
v2' - v1' = e(v1 - v2)
```

The validator supports multi-value outputs by extracting `v1'` from the
DynaTutor display string when the solver reports both final velocities.

### Massive pulley Atwood

```text
a = (m2-m1)g / (m1 + m2 + I/R²)
```

## Running validation

From `backend`:

```bash
PYTHONPATH=. python tools/chrono_validation/run_all_validations.py --strict
```

Individual suites:

```bash
PYTHONPATH=. python tools/chrono_validation/validate_rolling_sphere.py --strict
PYTHONPATH=. python tools/chrono_validation/validate_rolling_disk.py --strict
PYTHONPATH=. python tools/chrono_validation/validate_incline_friction.py --strict
PYTHONPATH=. python tools/chrono_validation/validate_collision_restitution.py --strict
PYTHONPATH=. python tools/chrono_validation/validate_massive_pulley.py --strict
```

The scripts also run without manually setting PYTHONPATH because
`chrono_validation/common.py` adds the backend root to `sys.path`.

## Current validation result

```text
Phase 21 validation cases: 25
Automated analytic validation: passed
PyChrono available in this execution environment: no
```

PyChrono numerical simulation was not executed in the current build environment.
The code reports this explicitly instead of pretending that Chrono ran.

## PyChrono hooks

`chrono_simulators.py` exposes safe optional hooks:

```text
simulate_rolling_down_ramp
simulate_incline_friction
simulate_collision_restitution
simulate_massive_pulley
```

If PyChrono is not installed, these return:

```text
status = skipped
source = chrono_unavailable
```

If PyChrono is importable, they return:

```text
status = manual_required
source = chrono_available_manual_run_required
```

This keeps the app safe while documenting exactly where local Chrono numerical
simulation should be connected.

## Tests

Added:

```text
backend/tests/test_phase21_chrono_offline_validation.py
```

Validated:

```text
- all Phase 21 analytic validation cases pass
- collision multi-value validation works
- chrono_status has a stable JSON shape
- Chrono simulator hooks do not crash without PyChrono
- run_all_validations.py outputs JSON and exits 0 in strict mode
```

Test result:

```text
134 passed
```

## Important honesty note

Phase 21 does not claim that PyChrono numerical simulation was run in this
container. It implements the validation harness, analytic oracle comparison, and
safe PyChrono integration points.

A future Phase 21.5 or Phase 24 could add fully executable PyChrono scene files
for a specific pinned Chrono installation.
