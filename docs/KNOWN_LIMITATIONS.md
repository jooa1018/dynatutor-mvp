# Known Limitations

This document records known limitations as of Phase 23.

## Frontend build not verified in container

The backend test suite passed, but frontend build was not run because
`frontend/node_modules` was missing.

Run locally before deployment:

```bash
cd frontend
npm install
npm run build
```

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

Phase 23 is suitable as a personal-use release candidate.

Before public/commercial release, add:

```text
security review
dependency license review
frontend production build verification
hosted database/storage plan
user accounts/auth review
privacy policy
full source-by-source benchmark curation
```
