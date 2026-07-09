# Phase 18 2D Rigid Body / Direction & Coordinate Upgrade

Phase 18 upgrades DynaTutor's 2D direction and coordinate parsing for planar
rigid-body problems.

## Goal

Rigid-body problems should not rely on scalar magnitude fallbacks when direction
information is available.

Phase 18 improves this path:

```text
Korean/English direction text
→ coordinate_data
→ Vec2
→ rigid-body vector equations
→ component answer
```

## New file

```text
backend/engine/physics_core/coordinate_parser.py
```

## New parsing features

### Direction words

```text
오른쪽 / right       → +x
왼쪽 / left         → -x
위쪽 / upward       → +y
아래쪽 / downward   → -y
30도 / 30 deg       → polar direction
```

### Angular sign

```text
반시계방향 / counterclockwise / ccw → +
시계방향 / clockwise / cw          → -
```

Korean note: `반시계방향` contains `시계방향`, so the parser checks
counterclockwise expressions first.

### Relative position vector

Supported examples:

```text
B는 A에서 오른쪽으로 0.5m 떨어져 있다.
A에서 B까지 위쪽 0.5m
r_B/A = (0.3, 0.4)m
rBA = (0.3, 0.4)m
```

These become:

```text
coordinate_data["rBAx"]
coordinate_data["rBAy"]
```

### A-point vector data

Supported examples:

```text
A점 속도는 오른쪽 3m/s
A점 가속도는 오른쪽 1m/s2
```

These become:

```text
vAx, vAy
aAx, aAy
```

## Solver changes

Updated:

```text
backend/engine/solvers/rigid_body_2d/velocity.py
backend/engine/solvers/rigid_body_2d/acceleration.py
```

The solvers now use:

```text
v_B = v_A + omega × r_B/A
a_B = a_A + alpha × r_B/A + omega × (omega × r_B/A)
```

with signed `omega` and signed `alpha`.

## Examples

### Counterclockwise

```text
A점은 고정되어 있고 B는 A에서 오른쪽으로 0.5m 떨어져 있다.
각속도는 반시계방향 4rad/s이다.
```

Result:

```text
v_B = (0, 2) m/s
```

### Clockwise

```text
A점은 고정되어 있고 B는 A에서 오른쪽으로 0.5m 떨어져 있다.
각속도는 시계방향 4rad/s이다.
```

Result:

```text
v_B = (0, -2) m/s
```

### Translating A point

```text
A점 속도는 오른쪽 3m/s이고
B는 A에서 위쪽으로 0.5m 떨어져 있다.
각속도는 반시계방향 4rad/s이다.
```

Result:

```text
v_A = (3,0)
omega × r_B/A = (-2,0)
v_B = (1,0) m/s
```

## Unsupported behavior preserved

If the problem says only:

```text
A와 B 사이 거리는 1m, 각속도는 2rad/s이다. B점 속도는?
```

DynaTutor still stops because A-point velocity/fixed condition is missing.

## Tests

Added:

```text
backend/tests/test_phase18_rigid_body_coordinate_upgrade.py
```

Validated:

```text
- cardinal direction parsing
- clockwise/counterclockwise sign
- r_B/A from Korean direction phrase
- fixed-point velocity vector
- clockwise velocity vector sign
- v_A direction not mixed with later B-position direction
- planar rigid-body acceleration vector components
- unsupported behavior for missing fixed point/v_A
- diagnosis coordinate notes exposed
```

Result:

```text
117 passed
```

## Still not Phase 19

Phase 18 focuses on 2D rigid-body coordinate/vector correctness.

Remaining for Phase 19:

```text
- SymPy Mechanics adapter actual equation generation examples
- PyDy adapter actual high-level examples
- simple pendulum
- mass-spring-damper
- rotating rod particle
- connected particle system scaffold
```
