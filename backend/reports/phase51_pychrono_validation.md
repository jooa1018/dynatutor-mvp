# Phase 51 PyChrono independent validation

- Report version: `phase51-pychrono-report-v1`
- Suite version: `phase51-pychrono-validation-v1`
- Status: **passed**
- Passed: `true`
- Cases: 6/6 passed
- Chrono statuses: `{"error": 0, "failed": 0, "passed": 6, "skipped": 0}`
- Product answer overwrite: `false`
- Offline only: `true`

## Environment

- Python: `3.12.13`
- Platform: `Linux / x86_64`
- Chrono versions: `["9.0.1"]`
- Actual solvers: `["ChSolverPSOR:PSOR:max_iterations=200:sharpness_lambda=0.95", "ChSolverPSOR:PSOR:max_iterations=200:sharpness_lambda=1.0"]`
- Actual contact methods: `["NSC:Coulomb", "NSC:frictionless_restitution", "constraint_driveline:no_contact"]`

## Cases

| Case | Chrono status | Chrono value | Analytic | Product | Passed |
|---|---:|---:|---:|---:|---:|
| rolling_sphere | passed | 2.64702797465 | 2.64710084 | 2.647101 | true |
| rolling_disk | passed | 2.53551623404 | 2.55734237051 | 2.557342 | true |
| incline_friction_slip | passed | 2.89429836831 | 2.89429837553 | 2.8943 | true |
| incline_friction_stick | passed | -7.26752168438e-36 | 0 | n/a | true |
| collision_restitution | passed | -0.8 | -0.8 | -0.8 | true |
| massive_pulley | passed | 3.5316 | 3.5316 | 3.5316 | true |

## Cross-checks

- all_chrono_cases_executed: `true`
- all_chrono_cases_passed: `true`
- all_required_product_comparisons_passed: `true`
- normal_solve_imported_pychrono: `false`
- product_answer_overwrite: `false`
- sphere_speed_exceeds_disk_speed: `true`

The JSON report contains each scene's initial conditions, final state,
constraint errors, invariant errors, modeling assumptions, warnings, and
in-memory artifact summary. No analytic value is used to initialize or
overwrite a Chrono state.
