# Phase 14 PhysicalModel Builder

Phase 14 is the first step of the 10-step second refactor plan.

## Goal

Convert `CanonicalProblem` into an explicit `PhysicalModel` before solving.

```text
CanonicalProblem
→ PhysicalModel(bodies, forces, constraints, coordinates)
→ solver/equation generator
```

## Added files

```text
backend/engine/model_builder/
  __init__.py
  model_types.py
  object_extractor.py
  force_extractor.py
  constraint_extractor.py
  coordinate_builder.py
  builder.py
```

## PhysicalModel contents

- `bodies`: physical bodies such as block_on_table, hanging_mass, rolling_body
- `forces`: weight, normal, tension, friction, spring, impulse, kinematic relation
- `constraints`: massless string, same acceleration, no slip, rigid distance, no air resistance
- `coordinates`: positive directions and body-specific axes
- `equations_ready`: whether this model has enough information to generate equations
- `missing_info`: clarifying information needed before solving

## API/UI integration

`DiagnosisResponse` now includes:

```text
physical_model: dict | None
```

The frontend result page displays a new **물리 모델** card showing bodies, forces,
constraints, and coordinates.

## Important limitation

Phase 14 builds the physical model, but most existing solvers still use their
specialized equation logic. Phase 15 should connect this model to a general
Newton equation generator.

## Tests

Added:

```text
backend/tests/test_phase14_physical_model.py
```

Expected full test result after Phase 14:

```text
90 passed
```
