# Phase 17 Energy / Momentum Generator

Phase 17 adds a model-based generator for energy, work, impulse, and collision
equations.

## Goal

Newton systems already use the Phase 15 `particle_newton` generator.

Phase 17 adds the parallel path:

```text
CanonicalProblem
→ PhysicalModel
→ EnergyMomentumGenerator
→ solver-specific numeric solve
→ SolverResult
```

## New file

```text
backend/engine/equation_generators/energy_momentum.py
```

## PhysicalModel addition

`PhysicalModel` now exposes:

```text
generated_energy_momentum_system
```

This is returned through:

```text
diagnosis.physical_model.generated_energy_momentum_system
```

and rendered as a StepCard:

```text
모델 기반 에너지/운동량 방정식
```

## Supported generator cases

```text
constant_force_work
work_energy_speed
spring_mass_vibration
spring_energy / spring_energy_speed
pure_rolling_energy
rolling_energy_general
impulse_momentum
collision_1d
```

## Solver connections

The following solvers now call the Energy/Momentum generator in their solve path:

```text
ConstantForceWorkSolver
WorkEnergySpeedSolver
SpringMassVibrationSolver
SpringEnergySpeedSolver
PureRollingEnergySolver
RollingEnergyGeneralSolver
ImpulseMomentumSolver
Collision1DSolver
```

## Generated equations

### Work

```text
W = F*s*cos(theta)
```

### Work-energy

```text
W_net = ΔK = 1/2*m*v_f^2 - 1/2*m*v_i^2
v_f = sqrt(v_i^2 + 2*W_net/m)
```

### Spring vibration

```text
m*x_ddot + k*x = 0
omega_n = sqrt(k/m)
T = 2*pi/omega_n
f = 1/T
```

### Spring energy

```text
1/2*k*x^2 = 1/2*m*v^2
v = x*sqrt(k/m)
```

### Rolling energy

```text
m*g*h = 1/2*m*v^2 + 1/2*I*omega^2
v = omega*R
I = beta*m*R^2
v = sqrt(2*g*h/(1+beta))
```

or with explicit inertia:

```text
v = sqrt(2*m*g*h/(m + I/R^2))
```

### Impulse-momentum

```text
J = F*Δt
J = Δp = m*(v_f - v_i)
```

### Collision

```text
m1*v1 + m2*v2 = m1*v1f + m2*v2f
v1f = v2f = v_f       # perfectly inelastic
v2f - v1f = e*(v1-v2) # restitution
```

## Tests

Added:

```text
backend/tests/test_phase17_energy_momentum_generator.py
```

Validated:

```text
- constant force work generator
- work-energy speed solver uses generated equation
- spring energy generator
- rolling energy generator uses shape beta
- impulse-momentum generator
- collision generator for perfectly inelastic collision
- diagnosis exposes generated_energy_momentum_system
```

Result:

```text
109 passed
```

## Still not Phase 18

Phase 17 does not complete the 2D rigid-body/coordinate system roadmap.

Remaining for Phase 18:

```text
- stronger direction / coordinate parser
- r_B/A vector parsing from Korean text
- clockwise/counterclockwise sign handling
- planar rigid-body velocity/acceleration solver upgrade
- better unsupported behavior when direction is ambiguous
```
