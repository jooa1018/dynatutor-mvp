# Phase 56 Cross-Device Resume Handoff

## Authoritative Stage 6 disposition — 2026-07-24 Asia/Seoul

`STAGE_6_ACCEPTED / STAGE_7_READY_TO_START`

Stage 7 has **not** been started. The public corpus remains sealed. No Live model call was made.

### Frozen code candidate

- Repository: `jooa1018/dynatutor-mvp`
- Branch: `codex/phase56-generic-mechanics-engine`
- Code-containing candidate: `58589ad49982871e7d617489b525e9b67428548a`
- Main: `00b3a60de6e13756d089655879a02e4094122047`
- PR #17: open, Draft, unmerged; base `codex/phase55-gpt-first-textbook-parser`
- PR #16: open, Draft, unmerged

### Exact-head gates

- DynaTutor release tests: run `30045176722` — **SUCCESS**
- Phase 55 textbook parser: run `30045176496` — **SUCCESS**
- Phase 56 Stage 6 multimodal: run `30045176628` — **SUCCESS**
- Same-model read-only Checker: **PASS**, blocking findings **0**

The Checker first found an idempotency-key substitution gap on an earlier candidate. The final code candidate binds each idempotency key to a canonical request fingerprint, rejects different source or correction payloads with typed `409 request_id_conflict`, and refuses a legacy revision-store injection.

### Accepted Stage 6 product path

```text
problem text + zero to four bounded raster images
→ one combined modeling-envelope call
→ deterministic schema and authority audit
→ deterministic text/figure reconciliation
→ conflict confirmation or typed source-only correction
→ opaque server-held revision
→ normalization and MechanicsProblemIRV1 authorization
→ Equation Graph compilation
→ deterministic solve
→ independent verification
→ exactly one verified answer or fail-closed terminal
```

The browser cannot submit an Equation Graph, solver, root, candidate, verification result, final answer, or legacy route as authority. Corrections rerun the complete safe pipeline and never invoke a second modeling call.

### Security and deployment boundaries

- Multipart is the primary image path; bounded JSON compatibility remains behind a pre-parse wire limit.
- Maximum 4 images, 8 MiB each, 20 MiB decoded total, 30 MiB wire body.
- PNG, JPEG, and static WebP only; magic-byte and decoded-format agreement required.
- Animation, decompression bombs, excessive dimensions, corrupt images, duplicates, hidden transparent RGB payloads, and metadata leakage are rejected or normalized.
- Authentication, rate limiting, request-body limiting, CORS, and production docs policy apply to the multimodal prefix.
- Pillow is bounded in `requirements.txt` and locked exactly in `requirements-lock.txt`.
- HomeClient uses the existing API base, `x-dynatutor-token`, timeout, and `ApiAuthError` policy.
- Vercel static frontend and Render/FastAPI backend remain separate.

### Test evidence

- Stage 6 focused contracts, image security, provider, reconciliation, revision/correction, API/runtime integration, idempotency collision, source audit, and synthetic figures passed.
- Full backend collection and full backend regression passed.
- Release fast, slow, benchmark, audit, frontend-marker, repository metadata, warm/cold budget, pooled performance, frontend tests, typecheck, and production build passed.
- Stage 6 frontend tests, lint, typecheck, and production build passed.
- Synthetic raster manifest: **38** independently generated cases; expected metadata is evaluator-only.
- Temporary workspace-export and self-modifying finalizer workflows are absent; source audit remains exactly **2 passed**.

### Next permitted work

Stage 7 may begin only under a separate instruction. Its first action is the sealed input-only public-corpus harness; do not run Live evaluation or access the textbook PDF as part of the Stage 6 handoff.

### Protections

No merge, ready transition, main update, rebase, force-push, production deployment/environment change, secret access, external model call, corpus opening, PDF access, copyrighted figure commit, test deletion, or threshold relaxation occurred.
