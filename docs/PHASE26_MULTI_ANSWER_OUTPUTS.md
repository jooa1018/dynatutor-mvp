# Phase 26 Multi-Answer Outputs

Phase 26 fixes the most important remaining issue from Phase 25: problems that
ask for multiple final quantities must return all requested final answers.

## Main changes

```text
SolveResponse.answer   # legacy representative answer
SolveResponse.answers  # new list of final answer items
```

New answer item structure:

```text
label
symbol
numeric
unit
display
role
```

The representative `answer` remains for backward compatibility. New code should
prefer `answers`.

## Requested outputs

`CanonicalProblem` now includes:

```text
requested_outputs: list[str]
launch_angle_deg: float | None
launch_angle_source: str | None
```

Examples:

```text
시간과 수평거리를 구하라 -> ["time", "range"]
가속도와 장력은? -> ["acceleration", "tension"]
충돌 후 두 물체의 속도는? -> ["post_collision_velocity", "v1_after", "v2_after"]
최대높이와 사거리를 구하라 -> ["range", "max_height"]
```

## Projectile multi-answer support

The projectile solver now computes and returns all requested final values when
available:

```text
time: t
range: R
max height: H
```

Horizontal launch is normalized at extraction time:

```text
수평 방향으로 -> theta = 0 deg
launch_angle_source = horizontal_phrase
```

Therefore diagnosis no longer reports a missing launch angle for horizontal
launch problems.

## Pulley and collision outputs

The following solvers now populate `answers`:

```text
pulley_atwood
pulley_table_hanging
pulley_incline_hanging
massive_pulley_atwood
collision_1d
single_particle_newton
```

Examples:

```text
Atwood: a, T
Massive pulley: a, alpha, T1, T2
Elastic collision: v1', v2'
Single particle Newton: a / F / m
```

## Blind benchmark scoring

Blind textbook-style benchmark now supports:

```json
"expected": {
  "answers": [
    {"symbol": "t", "numeric": 2.019, "unit": "s", "tolerance": 0.02},
    {"symbol": "R", "numeric": 20.19, "unit": "m", "tolerance": 0.05}
  ]
}
```

The test helper requires every expected answer to appear in `result.answers`.

## LLM guardrail

`locked_facts` now includes the complete `answers` list.

The LLM guardrail checks that all locked answer numbers and units appear in the
LLM explanation. If any final answer is omitted, template fallback is used.

The external `locked_facts_version` remains `phase22` for backward compatibility.

## Frontend

The result card now displays:

```text
answers[] first
legacy answer second
unsupported_reason if unsupported
```

This means the UI shows:

```text
시간 t = 2.019 s
수평거리 R = 20.193 m
```

instead of only the first answer.

## Frontend build policy

Pytest no longer runs `npm run build`.

The actual build check is isolated in:

```text
scripts/check_frontend_build.sh
scripts/check_frontend_build_windows.bat
```

The shell script runs the build through Python with a 180-second timeout, avoiding
unbounded waits in the Next.js trace collection step.

## Single-particle Newton physical model

`single_particle_newton` now creates a physical model force object:

```text
body: 물체
force: F_net
direction: +x
magnitude_expr: F
```

## Final verification

```text
backend pytest: 176 passed
Phase20 benchmark: 492 total, 0 failures
blind textbook-style benchmark: 100 total, 0 failures
frontend npm ci: passed
frontend npm run build: passed
frontend npm audit: 0 vulnerabilities
```
