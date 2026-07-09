# Phase 20 Benchmark Audit

Phase 20 expands DynaTutor's verification coverage.

## Goal

The target was:

```text
synthetic benchmark: 300+
derived benchmark: 100+
negative benchmark: 50+
total benchmark: 450+
```

Phase 20 result:

```text
synthetic benchmark: 300
derived benchmark: 132
negative benchmark: 60
total benchmark: 492
```

## New benchmark files

```text
backend/tests/benchmarks/phase20_derived/
  openstax_style_derived_050.json
  fossee_style_derived_048.json
  mit_ocw_style_derived_031.json

backend/tests/benchmarks/phase20_negative/
  negative_unsupported_060.json
```

## Source-family policy

These benchmarks are **derived-style test cases**, not copied source problems.

Each case includes:

```text
source_family
license_note
derivation_note
topic
problem_ko
expected_solver
expected_ok
expected_numeric, optional
tolerance, optional
must_not_use_llm_for_answer
```

Important:

```text
No original OpenStax/FOSSEE/MIT wording was copied.
No external solution text was copied.
Numbers and wording were generated for DynaTutor regression testing.
```

## Derived benchmark distribution

```text
OpenStax University Physics style derived: 53
FOSSEE Engineering Dynamics style derived: 48
MIT OCW dynamics style derived: 31
```

Topics include:

```text
projectile motion
constant force work
work-energy speed
spring energy
impulse-momentum
1D collision
incline dynamics
Atwood pulley
table-hanging pulley
rolling energy
fixed-axis rotation
planar rigid-body velocity
planar rigid-body acceleration
polar kinematics
Coriolis / rotating frame
relative acceleration
```

## Negative benchmark distribution

Total:

```text
60
```

Negative topics:

```text
ambiguous pulley topology
rolling motion without shape / inertia
projectile range without launch angle / horizontal condition
rigid body velocity without v_A or fixed point
collision without elastic / perfectly inelastic / restitution condition
```

These cases must refuse to hallucinate a solution.

## Audit tool

Run:

```bash
cd backend
PYTHONPATH=. python tools/run_phase20_benchmark_audit.py
```

Expected output summary:

```text
synthetic_count: 300
derived_count: 132
negative_count: 60
total_count: 492
passed: true
failure_count: 0
```

## Tests

Added:

```text
backend/tests/test_phase20_benchmark_audit.py
```

Validated:

```text
benchmark inventory counts
all derived cases solve with expected solver
numeric oracle checks where applicable
all negative cases refuse to solve
source families present
LLM is marked as not allowed to answer benchmark cases
```

Test result:

```text
129 passed
```

## Current limitation

These are derived-style benchmarks and internal regression cases.
They are not yet a line-by-line formally curated textbook benchmark set.

A future stronger benchmark pass could add:

```text
source URL per source-family
human-reviewed derivation notes
problem-by-problem dimensional derivation
separate tolerance policy per solver family
```

## Next phase

Phase 21 should implement actual Chrono/PyChrono offline validation:

```text
DynaTutor closed-form result
vs
Chrono numerical simulation result
```

Recommended first targets:

```text
rolling sphere
incline with friction
restitution collision
massive pulley
```
