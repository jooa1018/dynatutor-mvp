# Chrono offline validation

Project Chrono / PyChrono is **not** a DynaTutor runtime dependency.

Phase 21 adds a real validation harness with two layers:

```text
1. DynaTutor closed-form vs analytic reference
2. Optional local PyChrono numerical simulation hooks
```

The first layer runs everywhere. The second requires a separate local PyChrono
installation.

## Run all automated validation

From `backend`:

```bash
PYTHONPATH=. python tools/chrono_validation/run_all_validations.py --strict
```

## Run individual suites

```bash
PYTHONPATH=. python tools/chrono_validation/validate_rolling_sphere.py --strict
PYTHONPATH=. python tools/chrono_validation/validate_rolling_disk.py --strict
PYTHONPATH=. python tools/chrono_validation/validate_incline_friction.py --strict
PYTHONPATH=. python tools/chrono_validation/validate_collision_restitution.py --strict
PYTHONPATH=. python tools/chrono_validation/validate_massive_pulley.py --strict
```

## PyChrono install note

Install PyChrono in a separate environment. Do not add it to normal
`backend/requirements.txt`.

Example outline:

```bash
conda create -n dynatutor-chrono python=3.11
conda activate dynatutor-chrono
# install pychrono according to your OS-specific Project Chrono docs
```

## What happens without PyChrono?

The validation scripts still run analytic references. PyChrono hooks return:

```text
status = skipped
source = chrono_unavailable
```

This is intentional. Normal DynaTutor use must not depend on Chrono.

## Current coverage

```text
rolling sphere
rolling disk
incline with kinetic friction
elastic collision / restitution equation
massive pulley Atwood
```
