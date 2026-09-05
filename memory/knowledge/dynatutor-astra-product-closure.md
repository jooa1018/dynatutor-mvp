# DynaTutor product closure checkpoint

2026-09-05 — **INCOMPLETE**, not a personal-use, MVRG or release claim.
Branch: `codex/dynatutor-astra-product-closure`; Draft PR #79 targets
`codex/phase57-reproducible-public-evaluation`. PR #49 stays Draft/unmerged.
Original checkpoint `054d3641568b5b3425009b5c46c07cc3633a841e` is preserved.
The exact final head and downloaded CI artifact identities are recorded in PR #79.

## Reproduced defects and fixes

- HomeClient late responses restored obsolete inputs; editable input could be
  saved with a prior result. Request ownership fences, duplicate suppression,
  invalidation and immutable result-bound save snapshots now prevent this.
  Original blob `27120b98ec85c6709b3c5379ac6e98f0003194ae` was hash-verified.
  Controlled callback regressions: before 2/12 passed; after 12/12 passed.
- Actual Chromium cold start exposed concurrent SQLite migration failures:
  two requests observed the same missing column and both attempted ALTER TABLE.
  `_connect()` now reserves one SQLite write transaction before schema inspection,
  commits the same additive migration, and rolls back/closes on failure. No data
  deletion or verification-policy change. Real SQLite tests: before 1/4 passed,
  after 4/4 passed, including old-data preservation and failed-receipt honesty.
- Generic multimodal UI had the analogous obsolete revision/callback race.
  Shared request ownership within that component now covers modeling, confirmation,
  corrections and execute. Controlled callback regressions: before 0/5 passed,
  after 5/5 passed. Server revision/receipt authority is unchanged.

Local callback tests use Node 22.16.0 / TypeScript 5.8.3 and API/hook doubles;
SQLite tests use Python 3.13.5 and genuine temporary databases. These are not
full locked-environment or mathematical/MVRG evidence. No independent reviewer
or subagent was used. Performance was not measured.

## Actual product and public evidence

Existing Node 20 locked npm checks passed at intermediate head `70d6378`.
Actual Chromium + Python 3.11/Pint product execution there passed natural-language
incline solve, independent numerical comparison, changed angle/mass units,
full saved-artifact readback through the existing export API, reload/history/
export/rerun, missing/unsupported inputs and late-response invalidation. The
browser run then failed because its duplicate-click selector selected the
separate Generic button; the selector is corrected without weakening assertions.
The first browser harness also incorrectly expected raw_result in RecordItem;
full-fidelity readback now uses the existing export contract, not a changed API.

The new exact-head workflow reruns all frontend checks, SQLite and real Chromium
regressions, plus the existing Phase 57 public runner and artifact identity gate.
No final-head PASS is predeclared here. Browser evidence explicitly separates
injected transport failure, real solver responses and disabled-provider behavior.

Downloaded and SHA-verified **fresh** V2 public campaign at `ca66ce2`:
65/81 supported correct; zero wrong/unscored/regressions/query-binding mismatches/
forbidden solves; 100 total contexts, 97 runtime-completed, 3 projection-refused.
Regression acceptance PASS; quality IN_PROGRESS (`supported_correct:65<81`).
The UI/storage fixes do not claim to have improved this mathematical count.
Remaining 16 individual failure roots have not been established from the public
aggregate. They are not relabeled ASSEMBLED_UNVERIFIED or excluded.

Some normalized connector responses contradicted immutable Git objects about
this repository's structure/history. Historical 50/31 and persisted 63/18 claims
are not final-head fresh results. Use immutable trees, source SHA and verified
artifact bytes; do not substitute the public M/V/R/G procedure for real-study MVRG.

## Remaining boundaries / next execution

Status remains INCOMPLETE pending final exact-head CI, public quality gaps,
formal real-study MVRG and actual Preview. The real Generic NLP route requires
an interpretation adapter/revision-store configuration: disabled CI exercises
its honest 503, not an actual configured-model Gen2 E2E success. Legacy `/solve`
product-browser results and typed public evaluation are separately reported.

Render workspace selection awaits the user confirmation requested in this
session. Connected Vercel team lists HarmonyMaker, not DynaTutor. Production
Render YAML is unchanged; no Preview URL, deployment SHA, paid model call,
production promotion, main merge or release is established. Do not hide these
limitations behind a green build. Next: read final-head jobs and downloaded
browser/public artifacts; use the authorized nonproduction infrastructure once
workspace access is confirmed, then perform configured Gen2 and MVRG validation.
Rollback is additive revert, never reset/force-push or data deletion.
