# Phase 56 Stage 6 — Source-grounded multimodal mechanics evidence

## Accepted scope

Stage 6 is accepted at code candidate `58589ad49982871e7d617489b525e9b67428548a`. It adds a production-integrated text-plus-raster-image route without transferring equation, solver, root, candidate, verification, or final-answer authority to the model or browser.

```text
text + sanitized images
→ one combined structured modeling envelope
→ deterministic validation and authority audit
→ deterministic evidence reconciliation
→ confirmation/source-only correction when required
→ opaque server revision
→ Generic Mechanics IR authorization
→ Equation Graph compiler
→ deterministic solve
→ independent verification
→ verified answer or fail-closed terminal
```

Text-only `/solve` and `/diagnose` remain backward-compatible. A ready multimodal draft is never reinterpreted through the legacy text route.

## Provider contract

- Explicit provider adapter only; disabled/unconfigured is a typed `503`.
- One combined text-plus-all-images primary call.
- No Phase 55 parser plus Mechanics modeler chain and no per-image fanout.
- Fixed structured-output contract `MechanicsModelingEnvelopeV1`.
- Bounded timeout/output, provider retries disabled, and at most one sanitized full repair in the modeler.
- `store=False`; no prompt, raw provider response, source text, image bytes, or secrets are persisted.
- Offline tests use deterministic fake providers. No external call was made in Stage 6.

## Image and request boundaries

| Boundary | Accepted value |
|---|---:|
| Images per request | 4 |
| Raw bytes per image | 8 MiB |
| Decoded/sanitized total | 20 MiB |
| Wire request ceiling | 30 MiB |
| Source pixels | 16,000,000 |
| Source edge | 4096 px |
| Model edge | 2048 px |
| Input formats | PNG, JPEG, static WebP |
| Provider image format | metadata-free RGB PNG |

The request-body middleware counts actual ASGI bytes before FastAPI form/JSON parsing, including chunked and missing-Content-Length requests. Conflicting or duplicate framing headers are rejected. Base64 expansion cannot bypass the wire limit.

Image processing verifies magic bytes and decoded format, rejects corrupt/animated/oversized/decompression-bomb inputs, applies EXIF orientation, removes metadata, flattens transparency onto white RGB pixels, re-encodes deterministically, hashes the sanitized result, and rejects duplicate sanitized content.

## API

- `POST /api/mechanics/multimodal/evidence`
- `GET /api/mechanics/multimodal/revisions/{revision_id}`
- `POST /api/mechanics/multimodal/revisions/{revision_id}/confirm`
- `POST /api/mechanics/multimodal/revisions/{revision_id}/correct`
- `POST /api/mechanics/multimodal/revisions/{revision_id}/execute`

The router is registered exactly once in `backend/app/main.py`. The prefix is protected by the existing personal-token authentication, rate limiter, pre-parse body limiter, and CORS policy. Production docs remain closed by default.

## Evidence and correction policy

Text evidence and figure evidence remain distinct. Exact agreement may corroborate one semantic fact while preserving both source references. Explicit conflicts never use confidence or source order as a tie-breaker and block compilation until an exact fingerprinted choice is supplied.

Supported source-only operations include evidence accept/reject, quantity value, unit, direction, entity binding, relation, alternative, user fact, fact removal, query, frame/axis, and assumption confirm/reject. Pydantic contracts and a recursive authority pre-scan reject direct equation graph, solver, backend, candidate, root, verification, final answer, or legacy-route patches.

Every confirmation or correction creates an immutable child revision and reruns reconciliation, normalization, validation, authorization, compilation, deterministic solving, and independent verification. The in-memory store has bounded TTL and capacity and is isolated by a privacy-safe owner key.

Idempotency keys are bound to canonical request fingerprints. Exact retries replay the same revision; the same key with different problem text, sanitized image identity, conflict choice, or correction payload receives typed `409 request_id_conflict`. The product router refuses a legacy non-collision-safe revision store.

## Student UI

The official `HomeClient` solve screen renders `MechanicsMultimodalPanel` using the existing problem-text state. The client uses `NEXT_PUBLIC_DYNATUTOR_API_BASE`, the existing `x-dynatutor-token`, timeout/error helpers, and `ApiAuthError` token-modal flow.

The UI supports image select/drag/drop/paste, preview/remove/replace, evidence regions, conflict choices, source-only correction forms, revision display, deterministic execution status, verification checks, and verified-result display. It does not expose an unverified answer. Keyboard labels, live status, alerts, responsive layout, and reduced-motion behavior are included.

## Evaluation and acceptance

- Synthetic-only deterministic raster manifest: 38 cases spanning core mechanics, conflicts, ambiguity, occlusion, prompt injection, compression/resolution/metadata and other metamorphic variants.
- Evaluator metadata is never passed to runtime.
- Source audit has exactly 2 tests and verifies no OCR/implicit client plus absence of the temporary mutating workflows.
- Exact-head CI: release `30045176722`, Phase 55 `30045176496`, Stage 6 `30045176628`, all SUCCESS.
- Final same-model read-only Checker: PASS, blocking findings 0.

Stage 7 remains not started and the public corpus remains sealed.
