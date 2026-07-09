# Phase 25 Accuracy Hardening

Phase 25 focuses on the remaining weak points after Phase 24.

## Goals

```text
1. Add basic single-particle Newton's second law solver
2. Strengthen incline-hanging pulley kinetic-friction direction handling
3. Improve km/h natural-language velocity parsing
4. Diagnose incline-hanging candidate when pulley/string is not explicit
5. Pin frontend/backend dependencies
6. Add 100 blind textbook-style benchmark cases
```

## Single-particle Newton solver

Added:

```text
backend/engine/solvers/newton/
  __init__.py
  single_particle.py
```

Supported:

```text
F = ma
a = F/m
m = F/a
```

Examples:

```text
질량 0.5kg인 물체에 힘 10N이 작용한다. 가속도는?
질량 500g인 물체에 10N의 알짜힘이 작용한다. 가속도는?
질량 2kg인 물체가 3m/s²로 가속된다. 필요한 알짜힘은?
```

If multiple forces appear without directions or an explicit net force, DynaTutor
refuses to produce a single answer.

## Incline-hanging pulley friction direction

Updated:

```text
backend/engine/solvers/pulley/incline_hanging.py
```

New behavior:

```text
kinetic friction + explicit direction:
  solve with friction opposite actual motion

kinetic friction + no direction:
  do not give a single confident answer
  return candidate interpretations and ask for direction

static friction:
  check whether static friction holds first
  if not, require direction / kinetic-friction information before final acceleration
```

## km/h parsing

Updated:

```text
backend/engine/extraction/quantity.py
backend/engine/physics_core/units.py
```

Supported initial velocity expressions include:

```text
36km/h에서
36 km/h에서
36km/h로 달리다가
처음 속도 36km/h
초기속도 36km/h
처음에 36km/h로
속도 36km/h에서 출발하여
```

Internal conversion:

```text
36 km/h = 10 m/s
72 km/h = 20 m/s
18 km/h = 5 m/s
```

## Incline-hanging candidate diagnosis

If a problem mentions:

```text
m1 on an incline
m2 hanging
acceleration / tension / motion / friction requested
no string or pulley explicitly stated
```

DynaTutor now marks it as:

```text
incline_hanging_candidate
```

and asks for connection information instead of assuming the bodies are connected.

## Dependency locking

Frontend:

```text
frontend/package.json
frontend/package-lock.json
```

Pinned versions:

```text
next = 15.5.18
react = 19.1.2
react-dom = 19.1.2
typescript = 5.8.3
@types/node = 22.15.30
@types/react = 19.1.8
@types/react-dom = 19.1.6
postcss override = 8.5.10
```

Verified commands:

```bash
cd frontend
npm ci
npm run build
npm audit --json
```

Result:

```text
npm run build: passed
npm audit: 0 vulnerabilities
```

Next.js version note:

```text
Next 15.5.18 was chosen after npm audit and official Next.js security guidance.
```

Backend:

```text
backend/requirements-lock.txt
```

Use:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
pytest
```

Windows:

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-lock.txt
pytest
```

## Blind textbook-style benchmark

Added:

```text
backend/tests/benchmarks/blind_textbook_style/
  kinematics.json
  projectile.json
  newton_laws.json
  incline_friction.json
  pulley.json
  work_energy.json
  momentum_collision.json
  rotation_rolling.json
  rigid_body_2d.json
  unsupported_cases.json
```

Total:

```text
100 cases
```

Distribution:

```text
kinematics: 10
projectile: 10
newton_laws: 10
incline_friction: 12
pulley: 12
work_energy: 10
momentum_collision: 8
rotation_rolling: 10
rigid_body_2d: 8
unsupported_cases: 10
```

## Tests

Added:

```text
backend/tests/test_phase25_core_improvements.py
backend/tests/test_phase25_blind_textbook_benchmark.py
backend/tests/test_phase25_dependency_locks.py
```

## Principle

Phase 25 reinforces the core rule:

```text
Do not confidently answer ambiguous dynamics problems.
Ask for missing physical information instead.
```


## Final verification result

```text
Current backend environment pytest: 168 passed
New venv from backend/requirements-lock.txt: 168 passed
Existing Phase 20 benchmark audit: 492 total, 0 failures
Blind textbook-style benchmark: 100 total, 0 failures
Frontend npm ci: passed
Frontend npm run build: passed
Frontend npm audit: 0 vulnerabilities
```

## Backend lock note

`httpx==0.28.1` is included because FastAPI/Starlette `TestClient` requires it
for API tests.

## Frontend security/version note

Next.js was pinned to `15.5.18` after checking npm audit results and the
official Next.js security update. `postcss` is overridden to `8.5.10`, which
made `npm audit` report 0 vulnerabilities in this environment.
