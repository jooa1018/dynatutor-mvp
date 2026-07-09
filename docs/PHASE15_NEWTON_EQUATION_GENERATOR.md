# Phase 15 Newton Equation Generator

Phase 15 connects the Phase 14 PhysicalModel layer to an actual equation
generator.

## Goal

Instead of every solver hand-writing all equations internally, supported Newton
systems now follow this path:

```text
CanonicalProblem
→ PhysicalModel
→ ParticleNewtonEquationGenerator
→ SymPy EquationSystem
→ SolverResult
```

## New folder

```text
backend/engine/equation_generators/
  __init__.py
  particle_newton.py
```

## Generated equation model

`backend/engine/model_builder/model_types.py` now includes:

```text
GeneratedEquation
GeneratedEquationSystem
```

`PhysicalModel` now exposes:

```text
generated_equation_system
```

This is also returned through `diagnose_problem()` as part of
`diagnosis.physical_model`.

## Supported in Phase 15

The first generator covers Newton-style translational systems:

```text
particle_on_incline
pulley_atwood
pulley_table_hanging
pulley_incline_hanging
massive_pulley_atwood
```

For these, equations are built from the model's bodies/forces/constraints and
then passed to the shared SymPy `EquationSystem`.

## Solver connections

The following solvers now use the generated equations for their actual solve
path:

```text
InclineNoFrictionSolver
InclineWithFrictionSolver
AtwoodPulleySolver
TableHangingPulleySolver
InclineHangingPulleySolver
MassivePulleyAtwoodSolver
```

## Example

For an Atwood problem:

```text
m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도는?
```

The generator creates:

```text
T - m1*g = m1*a
m2*g - T = m2*a
```

Then SymPy solves for:

```text
a, T
```

## Important design choice

For incline problems without explicit mass, the generator solves the
mass-cancelled acceleration equation:

```text
g*sin(theta) = a
```

Normal force and friction construction equations are still recorded in the
generated equation list for explanation, but they do not block solving when mass
is not needed.

## Tests

Added:

```text
backend/tests/test_phase15_newton_equation_generator.py
```

Validated:

```text
- incline generated equation
- table-hanging generated equations appear in StepCard
- Atwood equations generated from PhysicalModel
- massive pulley includes Newton-Euler equation
- diagnosis exposes generated_equation_system
```

Test result:

```text
95 passed
```

## Still not Phase 16

Phase 15 is not the full friction/constraint engine yet.

Remaining for Phase 16:

```text
- static friction inequalities
- motion/no-motion decision from generated model
- general string topology graph
- moving pulley constraints
- deeper friction direction selection
```
