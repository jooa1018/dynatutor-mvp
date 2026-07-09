# Phase 19 SymPy Mechanics / PyDy Adapter

Phase 19 turns the advanced dynamics adapter layer from a placeholder into
working symbolic equation-generation code.

## Goal

DynaTutor's normal student solve path should remain fast and closed-form.
SymPy Mechanics / PyDy is used as an advanced adapter for:

```text
- high-level equation generation examples
- offline validation
- future simulation workflows
- checking advanced solver formulas
```

It is not called for every ordinary student problem.

## Updated files

```text
backend/engine/adapters/sympy_mechanics_adapter.py
backend/engine/adapters/pydy_adapter.py
backend/tools/run_mechanics_adapter_examples.py
```

## SymPy Mechanics implementation

The following models now generate real symbolic equations using
`sympy.physics.mechanics` and Lagrange's method.

### 1. Simple pendulum

Function:

```text
derive_simple_pendulum()
```

Generated normalized equation:

```text
L*theta_ddot + g*sin(theta) = 0
```

### 2. Mass-spring-damper

Function:

```text
derive_mass_spring_damper()
```

Generated equation:

```text
m*x_ddot + c*x_dot + k*x = 0
```

### 3. Particle on rotating rod

Function:

```text
derive_particle_on_rotating_rod()
```

Assumption:

```text
theta(t) = omega*t
```

Generated radial equation:

```text
r_ddot - omega^2*r = 0
```

### 4. Planar rigid-body rotation

Function:

```text
derive_planar_rigid_body_rotation()
```

Generated equation:

```text
I*q_ddot - tau = 0
```

### 5. Connected particles with spring

Function:

```text
derive_connected_particles_spring()
```

Generated coupled 1D spring equations for two particles.

## PyDy adapter behavior

PyDy remains optional at runtime.

Function:

```text
get_pydy_status()
```

returns whether PyDy is importable.

Function:

```text
build_pydy_blueprint(name)
```

always returns a symbolic blueprint using the SymPy Mechanics derivation.

Function:

```text
build_optional_pydy_system(name)
```

attempts to detect `pydy.system.System` but returns a safe serializable payload
instead of forcing PyDy into the normal app state.

If PyDy is not installed, the app still works and returns:

```text
ok = false
reason = PyDy is not importable...
blueprint = symbolic equations
```

## Developer tool

Run:

```bash
cd backend
PYTHONPATH=. python tools/run_mechanics_adapter_examples.py
```

This prints all generated adapter equations, mass matrices, and forcing vectors.

## Tests

Added:

```text
backend/tests/test_phase19_sympy_mechanics_pydy_adapter.py
```

Validated:

```text
- simple pendulum Lagrange equation
- mass-spring-damper equation
- rotating rod particle equation
- planar rigid body rotation equation
- connected particle spring equations
- derive_model dispatcher
- PyDy optional status and blueprint
- adapter model list
```

Result:

```text
125 passed
```

## Important limitation

Phase 19 does not yet make PyDy a real-time student solver.

That remains intentional:

```text
student problem solve path:
  closed-form / SymPy / Pint

advanced validation/simulation path:
  SymPy Mechanics / optional PyDy
```

## Next phase

Phase 20 should expand benchmarks:

```text
- derived benchmark sets
- negative benchmark expansion
- source-family documentation
- expected-answer tolerances
- total benchmark count target: 450+
```
