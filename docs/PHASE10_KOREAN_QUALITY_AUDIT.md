# Phase 10 — Korean Quality Audit

Phase 10 is a local-study quality pass. It does **not** add service features. Instead, it stress-tests Korean textbook-style prompts and hardens the parser where it failed.

## Benchmark result

```text
100 Korean dynamics prompts tested
100 solved successfully
0 failures
Full backend tests: 63 passed
```

Run it locally:

```bash
./scripts/run_quality_audit.sh
```

or from the backend folder:

```bash
python tools_run_korean_quality_audit.py
pytest -q tests/test_phase10_korean_quality_benchmark.py
```

## Domains covered by the 100-case benchmark

- Frictionless incline
- Incline with friction
- Table-hanging pulley
- Vertical circle
- Pure rolling energy
- Constant-acceleration 1D kinematics
- Projectile motion
- Constant-force work
- Work-energy speed
- Fixed-axis rotation
- Impulse-momentum
- 1D collision
- Spring-mass vibration
- Spring energy-speed
- Flat curve with friction
- Frictionless banked curve
- Polar kinematics
- Instant center velocity
- Slot-pin relative motion
- Plane rigid body velocity
- Relative acceleration
- Coriolis relative motion
- Plane rigid body acceleration
- Massive pulley Atwood system
- General rolling energy with given inertia

## Bugs found and fixed

### 1. Korean deceleration expression

Before:

```text
처음 속도 10m/s인 물체가 -2m/s²로 감속하여 멈출 때까지 걸리는 시간은?
```

The app knew `v0=10` and `vf=0`, but missed `a=-2` because the phrase used `감속` instead of `가속도`.

After:

```text
solver: constant_acceleration_1d
answer: 시간 = 5.000 s
```

### 2. Instant-center distance phrasing

Before:

```text
순간중심에서 점 P까지 거리 0.8m, 각속도 5rad/s일 때 점 P 속도는?
```

The app extracted the distance as generic displacement `s`, not IC radius `r`.

After:

```text
solver: instant_center_velocity
answer: v = 4.000 m/s
```

### 3. Slot-pin false positive from English “slipping”

Before, the plain substring `pin` could accidentally trigger `slot_pin` from the word `slipping`.

After, slot/pin matching is more conservative, and rolling phrases like `rolling without slipping` are classified as rolling, not slot-pin motion.

### 4. Korean work/force phrasing

Before:

```text
10N의 힘으로 물체를 30cm 밀었다. 한 일을 구하라.
```

The parser missed force/distance when the number came before the Korean noun.

After:

```text
solver: constant_force_work
answer: W = 3.000 J
```

### 5. Collision was sometimes overridden by kinematics

Cases with `v1`, `v2`, `m1`, `m2` were sometimes treated as general kinematics because they had several velocity variables.

After, collision classification has priority over constant-acceleration kinematics when collision cues are present.

### 6. Spring compression after the number

Before:

```text
스프링이 30cm 압축되고 k=50N/m, m=0.5kg이다. 속도는?
```

The parser expected `압축량 30cm`, not `30cm 압축`.

After:

```text
solver: spring_energy_speed
```

## Files added or changed

- `backend/engine/qa/korean_benchmark.py`
- `backend/tests/test_phase10_korean_quality_benchmark.py`
- `backend/tools_run_korean_quality_audit.py`
- `scripts/run_quality_audit.sh`
- `backend/engine/extraction/normalizer.py`
- `backend/engine/extraction/quantity.py`
- `backend/engine/extraction/extractor.py`

## Remaining limits

The benchmark is intentionally limited to supported text-only problem patterns. The app still does not fully solve:

- diagram-only problems,
- long multi-paragraph textbook examples,
- arbitrary 2D/3D vector direction problems,
- symbolic derivations with many unspecified variables,
- free-form handwritten solutions or image OCR.

The next quality pass should focus on either FBD interaction or a larger manually curated Korean textbook-style dataset.
