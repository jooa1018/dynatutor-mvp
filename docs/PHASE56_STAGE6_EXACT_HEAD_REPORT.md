# Phase 56 Stage 6 exact-head acceptance report

## Disposition

`STAGE_6_ACCEPTED / STAGE_7_READY_TO_START`

Stage 7 was not started. Public corpus, private held-out material, textbook PDF, external model calls, secrets, and production deployment remained untouched.

## Repository state

- Repository: `jooa1018/dynatutor-mvp`
- Branch: `codex/phase56-generic-mechanics-engine`
- Code candidate: `58589ad49982871e7d617489b525e9b67428548a`
- Main: `00b3a60de6e13756d089655879a02e4094122047`
- PR #17: open / Draft / unmerged; base `codex/phase55-gpt-first-textbook-parser`
- PR #16: open / Draft / unmerged
- Documentation head: the later documentation-only commit containing this report; see PR #17 body for its SHA.

## Exact-head CI

| Workflow | Run | Exact-head result |
|---|---:|---|
| DynaTutor release tests | `30045176722` | SUCCESS |
| Phase 55 textbook parser | `30045176496` | SUCCESS |
| Phase 56 Stage 6 multimodal | `30045176628` | SUCCESS |

Release gates passed: backend fast, complete slow, benchmark, audit, frontend-marker, repository metadata, warm solve, cold import/RSS, balanced pooled performance, frontend tests, typecheck, production build, and final release gate.

Stage 6 gates passed: locked Pillow verification, backend compile, focused contracts, full collection, full backend regression, frontend tests, lint, typecheck, and production build.

## Functional acceptance

- Text-only behavior preserved.
- Text plus real bounded raster-image path integrated.
- Exactly one combined primary modeling call, with at most one sanitized repair.
- FigureObservation and modeling-envelope contracts versioned and strict.
- Text/figure evidence distinct, region-grounded, and reconciled deterministically.
- Unresolved conflict blocks compilation.
- Opaque server revisions support optimistic concurrency, cumulative typed correction, deterministic replay, bounded TTL/capacity, and cross-request isolation.
- Idempotency keys are request-fingerprint bound; payload substitution is a typed conflict.
- Ready revisions run through normalization, IR authorization, compiler, Equation Graph, deterministic solve, and independent verification.
- Browser/model cannot patch graph, solver, root, candidate, verification, answer, or legacy route.
- Official HomeClient includes upload, preview, evidence, conflict, correction, revision, and verified-result UX.
- Vercel static frontend and Render/FastAPI API separation preserved.

## Security acceptance

- Authentication, rate limit, pre-parser wire limit, CORS, and production docs policy apply to multimodal APIs.
- Four images maximum; 8 MiB each; 20 MiB decoded total; 30 MiB wire ceiling.
- PNG/JPEG/static WebP; format agreement and safe Pillow decode required.
- Animation, corrupt inputs, decompression bombs, excessive dimensions, duplicate content, metadata, and transparent hidden RGB are handled fail-closed.
- Provider disabled by default; no implicit secret probing or Live fallback.
- Raw image/base64/text/provider output is absent from telemetry.
- Temporary workspace-export and self-modifying finalizer workflows are absent.

## Evaluation

- Synthetic deterministic raster cases: 38.
- Source audit: exactly 2 passed.
- Full backend and all release wrappers passed on the same code candidate.
- Frontend tests, lint, typecheck, and production build passed on the same code candidate.

## Checker

- Checker ID: `stage6-final-same-model-readonly`
- Audited SHA: `58589ad49982871e7d617489b525e9b67428548a`
- Classification: same-model read-only audit; not represented as independent.
- Result: PASS
- Blocking findings: 0
- Unresolved review threads: 0

The first checker pass on an earlier candidate found an idempotency-key substitution vulnerability. The final candidate adds canonical request fingerprints, exact replay, typed conflict rejection for different payloads, legacy-store fail-closed behavior, and focused regression tests. The final re-audit found no remaining blocking authority, security, routing, correction, privacy, or corpus-leak finding.

## Protections

No PR merge, Draft transition, main update, force-push, rebase, history rewrite, deployment, environment change, secret access, external model call, corpus opening, PDF access, copyrighted figure commit, failure-test deletion, or quality/performance-threshold relaxation occurred.
