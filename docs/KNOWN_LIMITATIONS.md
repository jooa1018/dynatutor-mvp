# Known Limitations

This document records limitations that still apply after the Phase 46
routing and physics-audit follow-ups.

## CI and runtime budgets

GitHub Actions runs each bounded backend marker group once: fast, benchmark,
audit, and frontend. Together they currently cover every collected backend
test. CI also runs frontend tests/typecheck/build, a warm 43-case solve-latency
budget, and cold import/RSS budgets on every relevant pull request. A new
slow-only test requires a dedicated CI group.

Production/Render enables a process-local rate limit (60 CPU-heavy requests per
minute per client) and a 64 KiB request-body limit by default. These can be
configured with `DYNATUTOR_RATE_LIMIT_PER_MINUTE` and
`DYNATUTOR_MAX_BODY_BYTES`.

The limiter is intentionally process-local for the current personal single
worker deployment. A multi-worker/public service still needs a shared gateway
or datastore-backed limiter and deployment-level timeouts.

## PyChrono numerical simulation not executed here

Phase 21 added a Chrono validation harness and analytic validation.

However, PyChrono was not installed in the build environment, so actual Chrono
numerical simulation was not executed.

Current status:

```text
Automated analytic validation: yes
PyChrono optional hooks: yes
Actual Chrono numerical scene execution here: no
```

## Benchmarks are derived-style regression cases

The Phase 20 benchmark set does not copy textbook/source problem statements.

It uses DynaTutor-generated Korean problems with source-family labels.

This is good for regression testing and license hygiene, but it is not a
formally curated textbook benchmark suite.

## LLM guardrail is not a formal proof

Phase 22 guardrails block common dangerous failures:

```text
changed final answer
new numbers
forbidden formulas
unsupported-problem hallucination
```

But they do not prove that every sentence is pedagogically perfect.

## Natural-language parsing remains finite

The Korean/English parser supports many common patterns, but it can still miss
unusual wording, implicit geometry, diagrams, or multi-part textbook problems.

Unsupported behavior is intentional when information is missing.

## Advanced simulation not normal runtime

SymPy Mechanics, PyDy, and Chrono are advanced validation/simulation layers.
The normal student solve path remains closed-form and lightweight.

## Not commercial/public release

The current engine is suitable as a personal-use release candidate.

Before public/commercial release, add or independently verify:

```text
security review
dependency license review
external private evaluation set and false-solve measurement
deployment-level shared rate limiting and hard worker timeouts
hosted database/storage plan
user accounts/auth review
privacy policy
full source-by-source benchmark curation
```
