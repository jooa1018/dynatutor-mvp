# Phase 16 Friction / Constraint Engine

Phase 16 strengthens DynaTutor's friction and string/pulley constraint logic.

## Goal

Static friction problems must not be solved as kinetic-motion problems first.

New rule:

```text
If static friction is present:
  1. compute driving force
  2. compute max static friction
  3. if |driving| <= μ_s N:
       a = 0
     else:
       switch to kinetic-motion path
```

## New / expanded files

```text
backend/engine/physics_core/friction.py
backend/engine/physics_core/string_topology.py
backend/engine/model_builder/friction_analyzer.py
```

## Friction engine

`physics_core/friction.py` now includes:

```text
FrictionDecision
decide_static_friction
decide_incline_static
decide_table_hanging_static
decide_incline_hanging_static
kinetic_direction_from_driving
```

Supported static-friction decisions:

```text
particle_on_incline:
  mg sinθ <= μ_s mg cosθ

pulley_table_hanging:
  m2g <= μ_s m1g

pulley_incline_hanging:
  |m2g - m1g sinθ| <= μ_s m1g cosθ
```

If the inequality holds, the solver returns:

```text
a = 0
```

instead of applying a kinetic acceleration formula.

## String topology

`physics_core/string_topology.py` adds explicit topology records for:

```text
pulley_atwood
pulley_table_hanging
pulley_incline_hanging
massive_pulley_atwood
```

Each topology records:

```text
nodes
tension symbols
acceleration constraints
tension constraints
rotation constraints
notes
```

This makes the pulley model more explicit and prepares for future moving/compound
pulley constraints.

## PhysicalModel additions

`PhysicalModel` now exposes:

```text
friction_decisions
string_topology
```

These are included in `diagnose_problem()` through:

```text
diagnosis.physical_model
```

Solve step cards now include:

```text
물리 모델: 줄/도르래 제약
물리 모델: 마찰 판정
```

when applicable.

## Solver changes

The following solvers now use static-friction-first logic:

```text
InclineWithFrictionSolver
TableHangingPulleySolver
InclineHangingPulleySolver
```

`particle_newton.py` also improves friction direction handling for
`pulley_incline_hanging` when the actual motion tendency is opposite the default
m2-down assumption.

## Tests

Added:

```text
backend/tests/test_phase16_friction_constraint_engine.py
```

Validated:

```text
- incline static friction hold
- table-hanging static friction hold
- incline-hanging static friction hold
- friction decision utility functions
- string topology for Atwood and massive pulley
- physical_model exposes friction_decisions and string_topology
- static friction slip switches to kinetic-motion path
```

Result:

```text
102 passed
```

## Still not Phase 17

Phase 16 covers friction/constraint safety for Newton systems.

Remaining for Phase 17:

```text
Energy / Momentum Generator
- energy conservation model
- non-conservative work model
- impulse-momentum generator
- collision equation generator
- rolling energy model integration
```
