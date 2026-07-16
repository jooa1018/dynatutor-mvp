# Phase 51 PyChrono independent validation

Phase 51 replaces the old informational hooks with real, offline Project Chrono
execution. It validates five target physics paths: solid-sphere rolling,
solid-disk rolling, incline friction, one-dimensional restitution collision,
and a massive Atwood pulley. A sixth supplemental incline case exercises the
stick branch so a slip-only implementation cannot pass.

## Runtime boundary

PyChrono is not a backend runtime dependency. Nothing under the normal
`/solve` import or call path imports PyChrono, and a Chrono result is never
allowed to replace or mutate a student answer. The optional code lives under
`backend/tools/chrono_validation`.

Dependency states are fail-closed:

- a genuine missing `pychrono` module is `skipped`;
- a DLL, ABI, transitive-import, or required-API failure is `error`;
- an executed scene that violates an observable, constraint, or invariant is
  `failed`;
- only an executed scene satisfying every required check is `passed`.

`--strict` returns nonzero for skipped, error, or failed results. Therefore a
machine without PyChrono can still run the application and non-strict reporting,
but it cannot create Phase 51 acceptance evidence.

## Reproducible environment

Project Chrono recommends a dedicated conda environment. The checked-in
`backend/environment-phase51-chrono.yml` pins the official Linux
PyChrono 9.0.1 / Python 3.12 build used for acceptance.

```bash
micromamba create -f backend/environment-phase51-chrono.yml
micromamba activate dynatutor-phase51-chrono
python -m pip install -r backend/requirements.txt
python backend/tools/chrono_validation/version_evidence.py \
  --expected-package projectchrono::pychrono \
  --expected-version 9.0.1 \
  --expected-build py312hf1de3a3_6463 \
  --expected-channel projectchrono \
  --expected-python 3.12
```

The verifier reads the active environment's installed `conda-meta` package
record. Module version evidence is preferred when present; when it is absent,
the installed package name, exact version, build, channel/source, Python runtime,
import result, and `ChSystemNSC` API provide the evidence. Missing, malformed,
ambiguous, mismatched, or contradictory evidence fails closed.

The compatibility adapter uses the documented Chrono 9/10 names and the
corresponding Chrono 8 aliases. An unknown API is an error, not an analytic
fallback.

Official references:

- https://api.projectchrono.org/pychrono_installation.html
- https://api.projectchrono.org/9.0.0/classchrono_1_1_ch_system_n_s_c.html
- https://api.projectchrono.org/9.0.0/classchrono_1_1_ch_shafts_gear.html
- https://api.projectchrono.org/tutorial_demo_powertrain.html

## Fixed numerical policy

The versioned policy is `phase51-pychrono-policy-v1`.

| Scene | Solver/contact | Step | Duration/stop | Observable tolerance |
|---|---|---:|---:|---:|
| rolling | PSOR 200 iterations / NSC Coulomb | 0.0005 s | target height, max 3.0 s | 0.03 m/s absolute or 1% relative |
| incline | PSOR 200 iterations / NSC Coulomb | 0.0005 s | 0.8 s | 0.05 m/s² absolute or 2% relative |
| collision | PSOR 200 iterations / NSC restitution | 0.0001 s | 0.25 s | 0.05 m/s absolute or 1% relative |
| massive pulley | PSOR 200 iterations / bilateral shaft gears | 0.001 s | 0.5 s | 0.005 m/s² absolute or 0.5% relative |

Constraint and invariant limits are separate, unit-specific fields in
`ChronoValidationPolicy`; they do not reuse the observable OR rule. JSON
serialization rejects NaN and infinity.

## Independent scene contracts

Rolling reads center-of-mass velocity and parent-frame angular velocity from the
rigid body. It checks the signed residual `v_x + R*omega_z`, contact height,
actual COM displacement energy balance, and the body inertia ratio. Sphere and
disk results must be distinct and ordered physically.

Incline acceleration is a least-squares slope from the final 80% of the Chrono
velocity trajectory. It also checks contact height, actual contact normal force,
friction direction or static balance, and the observed stick/slip regime.

Collision uses two finite rigid spheres. A result is not post-impact evidence
unless both contact start and later separation are observed. It checks both
final velocities, momentum, signed realized restitution, and event time.

The massive pulley uses Chrono's supported reduced-coordinate multibody
driveline: three real `ChShaft` inertias and two signed
`ChShaftsGear` bilateral constraints stepped by `ChSystemNSC`. Gravity
loads are derived only from primitive inputs. Acceleration is read from stepped
shaft state; tensions are read from gear reactions. Signed no-slip, energy,
tension difference, and two free-body residuals are required. The analytic
target is comparison-only.

## Reports and commands

```bash
cd backend
python tools/chrono_validation/phase51_runner.py --mode chrono --strict
pytest -q tests/test_phase51_pychrono_validation.py tests/test_phase51_runner.py tests/test_phase51_capability_contract.py
```

The runner writes:

- `backend/reports/phase51_pychrono_validation.json`
- `backend/reports/phase51_pychrono_validation.md`

It has no timestamp or wall-clock measurements. Case ordering, sorted JSON keys,
warnings, artifacts, and float serialization are deterministic. Acceptance runs
the runner twice and byte-compares both outputs.

The capability matrix declares external paths by exact solver ID. It does not
claim coverage for the three massless pulley solvers, arbitrary-inertia
`rolling_energy_general`, work-energy, or fixed-axis rotation.

Phase 52 owns cross-engine aggregation and general CI tiering. Phase 51 adds only
its dedicated optional PyChrono execution lane.
