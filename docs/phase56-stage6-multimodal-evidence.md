# Phase 56 Stage 6 — Source-grounded multimodal mechanics evidence

## Scope

Stage 6 adds an optional image-evidence boundary to the existing text-first mechanics modeler. It does **not** grant the model equation selection, solver selection, root selection, verification, or final-answer authority. The deterministic mechanics runtime remains the only component allowed to perform those operations.

The text-only path remains unchanged. The new endpoint is additive:

`POST /api/mechanics/multimodal/evidence`

A deployment must explicitly inject `app.state.mechanics_multimodal_envelope_generator`. There is no implicit model provider, credential lookup, or live-network fallback in the repository.

## Trust boundary

1. The browser enforces early count, media-type, and byte limits.
2. The backend decodes base64 with strict validation.
3. Pillow decodes the image under decompression-bomb and dimension limits.
4. Animated inputs and declared/decoded format mismatches are rejected.
5. EXIF orientation is applied, the pixels are copied into a fresh image, and the result is re-encoded as deterministic PNG.
6. Only the sanitized PNG, its dimensions, and its SHA-256 digest may reach the injected interpretation adapter.
7. Every figure observation must bind to the exact image id, index, dimensions, and sanitized digest.
8. The envelope is revalidated against `MechanicsModelingEnvelopeV1` and recursively audited for forbidden answer or execution authority.
9. Text/figure conflicts are reconciled deterministically. Confidence is never an automatic tie-breaker, and visual conventions are never silently promoted.
10. A draft is withheld until every explicit conflict is confirmed with an exact conflict fingerprint and exact candidate fingerprint.

Original image bytes, filenames, EXIF metadata, problem text, labels, values, and draft content are excluded from telemetry. Metrics contain only bounded counts and a terminal label.

## Limits

| Limit | Value |
|---|---:|
| Images per request | 4 |
| Bytes per image | 8 MiB |
| Combined input bytes | 20 MiB |
| Source pixels | 16,000,000 |
| Source edge | 4096 px |
| Sanitized/model edge | 2048 px |
| Accepted formats | PNG, JPEG, WebP |
| Sanitized output | metadata-free PNG |

## Conflict policy

For a shared semantic target:

- Identical eligible values collapse deterministically.
- A figure convention is ignored unless explicitly confirmed; it never becomes a fact because of confidence.
- Different explicit values create an immutable conflict fingerprint.
- The response terminal is `confirmation_required`, and `draft` is `null`.
- A follow-up confirmation must bind conflict id, conflict fingerprint, chosen source id, and chosen candidate fingerprint.
- A stale or mismatched binding is blocked rather than guessed.

## Corrections and revisions

Corrections are source-only, immutable revisions. Every request binds the base revision id and fingerprint. Operations that attempt to patch equation graphs, solvers, roots, verification, runtime delivery, or final answers are rejected. The full envelope is revalidated after every accepted source correction.

## Synthetic validation

Repository tests use only generated incline, pulley, and free-body diagrams. They do not read textbook PDFs, OCR corpora, held-out benchmark images, or live model responses. The synthetic manifest covers matching labels, explicit conflicts, directions, figure-only evidence, and visual-convention non-promotion.

## Operational gates

The permanent Stage 6 workflow performs:

- backend compilation;
- all `test_phase56_stage6*.py` contract, security, reconciliation, authority, telemetry, and synthetic tests;
- existing backend regression tests;
- frontend install, tests when configured, lint when configured, and production build;
- a source audit banning OCR and implicit live model clients;
- an audit that the temporary workspace-export workflow is absent.

No threshold, timeout, assertion, or compatibility wrapper is weakened by this stage.
