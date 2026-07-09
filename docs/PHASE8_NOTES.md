# Phase 8 Notes — Advanced Dynamics Solver Expansion

## What changed

Phase 8 adds advanced undergraduate dynamics solvers while keeping the app's original safety philosophy:

```text
problem structuring → solver → verification → explanation
```

New solvers:

1. `relative_acceleration_translation`
2. `coriolis_relative_motion`
3. `plane_rigid_body_acceleration`
4. `massive_pulley_atwood`
5. `rolling_energy_general`

## Why these solvers

These are common bottleneck topics in second-year engineering dynamics:

- relative acceleration and rotating axes
- Coriolis acceleration
- planar rigid-body acceleration
- pulley systems where the pulley has non-negligible rotational inertia
- rolling energy problems with a supplied moment of inertia instead of a built-in disk assumption

## Main formulas

```text
a_B = a_A + a_B/A
```

```text
a = a_O + α×r + ω×(ω×r) + 2ω×v_rel + a_rel
```

```text
a_C = 2ωv_rel
```

```text
a_B = a_A + α×r_B/A + ω×(ω×r_B/A)
a_t = αr
a_n = ω²r
```

```text
a = (m2 - m1)g / (m1 + m2 + I/R²)
```

```text
mgh = 1/2mv² + 1/2Iω²
v = ωR
v = sqrt(2mgh / (m + I/R²))
```

## Current limitations

- Vector directions are still simplified in several MVP solvers.
- Direction angles are not yet generally parsed.
- Plane rigid-body acceleration is a magnitude/component tutoring solver, not a full symbolic vector engine.
- PyDy is still not invoked directly; this phase intentionally uses closed-form textbook-style solver classes.

## Recommended next step

Phase 9 should move toward real service readiness: auth, cloud database, rate limiting, and deployment.
