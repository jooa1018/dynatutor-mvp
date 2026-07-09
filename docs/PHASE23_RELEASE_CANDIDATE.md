# Phase 23 Accuracy Audit / Release Candidate

Phase 23 packages DynaTutor as a personal-use release candidate.

## Goal

Phase 23 does not add a major new physics solver. It audits the system created
through Phase 22 and records what is ready, what passed, and what is still
limited.

## Added files

```text
backend/tools/run_release_candidate_audit.py
backend/tests/test_phase23_release_candidate_audit.py
release_manifest_phase23.json
docs/PHASE23_RELEASE_CANDIDATE.md
docs/RELEASE_CHECKLIST.md
docs/KNOWN_LIMITATIONS.md
docs/RC_AUDIT_SUMMARY.json
```

## Release candidate audit

Run from `backend`:

```bash
PYTHONPATH=. python tools/run_release_candidate_audit.py
```

Optional full nested pytest audit:

```bash
PYTHONPATH=. python tools/run_release_candidate_audit.py --include-pytest
```

The default audit checks:

```text
benchmark audit
Phase 21 validation summary
LLM guardrail audit
artifact/document inventory
known limitation reporting
```

## Current RC result

```text
overall_passed: true
backend tests: 145 passed
benchmark total: 492
benchmark failures: 0
Phase 21 validation: 25 passed, 0 failed
LLM guardrail audit: passed
```

## Benchmark status

```text
synthetic benchmark: 300
derived-style benchmark: 132
negative benchmark: 60
total: 492
```

All Phase 20 benchmark checks passed.

## Phase 21 validation status

```text
analytic validation cases: 25
passed: 25
failed: 0
```

PyChrono note:

```text
PyChrono was not available in this environment.
Actual Chrono numerical simulation was not run.
The optional hooks report this honestly.
```

## LLM guardrail status

The Phase 23 audit confirms:

```text
safe explanation passes
changed final answer is rejected
unsupported-problem hallucinated answer is rejected
```

## Test result

```text
145 passed
```

Warnings remain for Python invalid escape sequences in several LaTeX-ish strings.
These warnings do not fail tests but can be cleaned in a future polish phase by
using raw strings or escaping backslashes.

## Frontend build status

Frontend build was not run in the container because:

```text
frontend/node_modules is missing
```

This is not a runtime proof failure for the backend, but before actual deployment
you should run:

```bash
cd frontend
npm install
npm run build
```

## Release zip policy

The release zip excludes:

```text
__pycache__
.pytest_cache
node_modules
.next
.venv
venv
*.pyc
*.pyo
```

## RC meaning

This is a solid personal-use release candidate for the current DynaTutor scope:

```text
physics-model-based solver layers
Newton equation generator
energy/momentum generator
2D rigid-body coordinate upgrade
SymPy Mechanics/PyDy adapter
benchmark audit
offline validation harness
LLM guardrail v2
phone-only remote/PWA structure
```

It is not yet a commercial/public product release.
