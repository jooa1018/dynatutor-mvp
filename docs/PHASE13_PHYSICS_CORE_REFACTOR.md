# Phase 13 Physics-Core Refactor

Phase 13 changes DynaTutor from a formula-matching MVP toward a physics-model
based dynamics engine.

## New core flow

문장 입력
→ 물체/힘/방향/제약조건 추출
→ CanonicalProblem 확장 필드 생성
→ 물리 모델 생성
→ SymPy EquationSystem으로 방정식 풀이
→ Pint 기반 단위 검증
→ 물리적 극한상황 검산
→ StepCard 설명 생성
→ Optional LLM Teacher Layer는 locked facts만 설명

## Added runtime dependencies

- Pint
- NumPy
- SciPy
- PyDy

PyChrono / Project Chrono is not a runtime dependency. It is documented only as
an optional offline validation tool under `backend/tools/chrono_validation`.

## Added physics core

`backend/engine/physics_core/`

- `units.py`: Pint UnitRegistry, SI conversion, dimension assertion
- `symbols.py`: shared SymPy symbols
- `vectors.py`: Vec2 and 2D rigid-body velocity/acceleration helpers
- `equation_system.py`: shared SymPy equation solving + physical solution filter
- `direction_parser.py`: force/displacement direction inference
- `inertia.py`: rolling-body inertia beta table
- `friction.py`: static/kinetic friction helpers
- placeholders for bodies, forces, constraints, validators, assumptions

## Refactored solvers

### Pulley

`backend/engine/solvers/pulley/`

- `atwood.py`
- `table_hanging.py`
- `incline_hanging.py`
- `massive_pulley.py`

Ambiguous pulley topology now stops instead of guessing.

### Rolling

`backend/engine/solvers/rolling/`

- `rolling_energy.py`
- `rolling_general_I.py`

The old disk default was removed. Rolling problems need either body shape or
moment of inertia data.

### Work

`ConstantForceWorkSolver` now uses:

`W = F s cos(theta)`

It requires direction or angle in strict mode.

### Projectile

`ProjectileMotionSolver` now solves the general equations:

`x(t)=x0+v0 cos(theta)t`
`y(t)=y0+v0 sin(theta)t - 1/2 g t^2`

Positive time roots are selected.

### 2D rigid body

`backend/engine/solvers/rigid_body_2d/`

- velocity
- acceleration
- relative motion

Vector helpers are used internally.

## Added tests

- `test_negative_unsupported_cases.py`
- `test_regression_physics_errors.py`
- `test_phase13_physics_core.py`
- `test_phase13_benchmark_300.py`

Result:

`85 passed`

## Important policy

DynaTutor should:
1. solve clear problems accurately,
2. ask for more conditions when ambiguous,
3. stop on unsupported problems,
4. keep LLM explanatory only,
5. validate units and physical limits.
