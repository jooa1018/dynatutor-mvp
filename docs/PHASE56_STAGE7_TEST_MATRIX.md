# Phase 56 Stage 7 offline test matrix

Status: **preflight matrix frozen before public corpus problem text is opened**

## Stage 6 entry gate

Stage 7 may execute only after all of the following are reconfirmed:

- PR #17 open, Draft, unmerged, with the Phase 55 branch as base;
- PR #16 open, Draft, unmerged;
- main unchanged from `00b3a60de6e13756d089655879a02e4094122047`;
- Stage 6 code candidate `58589ad49982871e7d617489b525e9b67428548a`;
- release run `30045176722` success;
- Phase 55 run `30045176496` success;
- Stage 6 multimodal run `30045176628` success;
- no unreviewed product-code change between the code candidate and the later
  documentation-only head.

## Pre-corpus package

| area | focused evidence |
|---|---|
| contract versions | exact schema/evaluator/report versions |
| public input | expected ZIP SHA, exact 84/16 split, allowlist and size policy |
| current scope | 25 accepted capabilities, exact four deferred families |
| terminal counts | exact 81/12/2/2/2/1 mapping |
| runtime input | one allowed input shape; recursive forbidden-key/private scan |
| cache identity | opaque token excluded; scorer metadata absent |
| gold isolation | runtime module cannot import gold; production cannot import evaluator |
| production packaging | Docker copies only `app` and `engine` |
| snapshot | frozen; solved/non-solved answer and candidate invariants |
| metrics | closed role-based catalog and multiset behavior |
| safety | closed all-zero hard-safety catalog |
| failures | closed failure taxonomy |
| redaction | forbidden raw/gold/provider/image/private/secret fields rejected |
| offline | empty credentials/base URLs and fail-fast socket guard |
| preflight failure | `HARNESS_CONTRACT_FAILURE`, zero runtime/compiler/solver/provider/cost |

## Lane A — integrity and evaluator

- archive SHA and safe extraction;
- path, absolute path, symlink/hardlink, nested archive, and size rejection;
- present-file allowlist;
- UTF-8, JSON/JSONL, schema, count, ID/text uniqueness, hash, and split checks;
- Korean-text, evidence quote/value, finite-reference-answer checks;
- public-only confirmation and private raw-text absence;
- scope-adjusted terminal-count preflight;
- input/gold process boundary and deterministic scorer;
- privacy-safe artifact contract.

All Lane A failures occur before any runtime/compiler/solver/provider call.

## Lane B — deterministic engine

Run all 100 public cases through a family/ID-independent semantic adapter:

- 84 public development cases: 72 supported, 12 deferred;
- 16 public adversarial cases: 9 supported, 2 needs figure, 2 needs
  confirmation, 2 unsupported other, 1 insufficient information.

For supported cases evaluate normalization, authorization, law emission,
Equation Graph closure, plan, all-root retention, deterministic candidate
execution, independent verification, and output projection.  For blocked cases
require the exact neutral terminal and no Generic or legacy answer delivery.

This lane is not parser/modeler quality.  Its adapter defects and engine defects
are reported separately.

## Lane C — recorded/fake modeler

Use only deterministic fake providers, Stage 6 independent synthetic images,
and independently authored recorded structured outputs.  Verify one combined
call, at most one sanitized repair, evidence grounding, reconciliation,
revision/correction, and zero answer authority.  Do not convert corpus gold into
recorded model output and call it parser success.  Actual model quality is
`NOT_RUN / N/A`.

## Lane D — product API/runtime

Exercise text compatibility and multimodal evidence/revision/confirmation/
correction/execute through FastAPI boundaries.  Verify auth, rate and body
limits, CORS, schemas, idempotency fingerprints, request-ID substitution,
stale revisions, owner isolation, verified-answer gate, deferred unsupported,
no legacy leakage, and raw text/image/provider privacy.

## Lane E — frontend

Verify the official HomeClient flow: text, upload/preview/remove/replace,
evidence overlay, conflict choice, source correction, revision, execute,
verified result, blocked states, API base/token, keyboard/accessibility, mobile,
tests, lint, typecheck, and production build.

## Independent suites

- 12 independently authored compositional structures, each using at least two
  reusable laws and independent residual checks;
- all 38 Stage 6 synthetic figures;
- diagnostic metamorphic transformations with identical authoritative results;
- physics-changing transformations that must change result or terminal;
- hard-safety negatives for every authority/leakage/fallback/correction/root/
  figure/private boundary.

## B28A — attested preparation and the sealed campaign population

The v2 shadow measurement's own attack matrix, added after independent
verification found that a *complete* ledger is not the same as an *honest* one.
A context could no longer be omitted, but it could still be relabelled from
`runtime_completed` to an anticipated `projection_refused` — leaving every
completeness rule satisfied by a measurement of nothing.

| area | focused evidence |
|---|---|
| cross-field validation | state / refusal code / draft payload must describe one context; `migration_refused` pinned unreachable |
| raw no-gold scan | on the raw document, before validation, on both sides of the trust boundary; normalized key matching |
| prepare attestation | canonical digest over shared JSON, never a `repr`; file SHA-256 carried separately under its own name |
| refusal identity | handle-set digest over `(index, handle, code)` triples, so a swap at equal counts is visible |
| Phase V replay | rebuild from corpus + manifest, compared against the artifacts; no solver, no runtime, no scorer |
| Phase R binding | full failure set reported, so each control names its own gate; zero runtime calls on refusal |
| snapshot binding | required field, inside the digest material; redacted view carries digests but no handle-set material |
| campaign seal | exact 97 / 3 population, refusal identities, corpus SHA and both manifest hashes, as a versioned contract |
| laundering controls | one context, all 97, identity swap at equal counts, joint input+attestation forgery |
| import isolation | Phase R, Phase G and Phase V import graphs, by AST rather than substring |
| Phase M atomic publication | a refused seal publishes none of the three artifacts, leaves no `.partial`, and does not disturb an earlier honest one; a sealed preparation publishes all three with hashes recomputed from the published bytes |

The Phase M publication controls are a matched pair over one synthetic campaign,
differing only in the two manifest hashes — the same two fields the live blocker
turns on. Both negative controls were confirmed to **fail** against the previous
write-then-seal ordering, so they are shown to fire rather than merely to pass.
A fourth control reads the orchestrator's AST and pins that a Phase M exit 2
returns before Phase V, so "no artifacts" is also "no later phase ran".

Each control asserts the exact gate name it hits. A control that failed for a
different reason than intended is treated as no control at all: a state-map
attack surfacing only as "the file hash changed" would be no evidence that the
state map is checked.

## Exact-head workflow gate

The permanent offline workflow must:

1. install dependencies;
2. set both external model API keys and provider base URLs to empty;
3. run corpus/preflight integrity before execution;
4. enable the fail-fast evaluation network guard;
5. run Lane A, 100 public cases, compositional 12, synthetic 38, metamorphic,
   hard-safety, product/API, and frontend gates;
6. upload only the redacted aggregate report.

It must not edit source, push, dispatch a finalizer, access secrets, use private
or full corpus material, or call an external model endpoint.

Final acceptance additionally requires Stage 6 regression, release, Phase 55,
full backend collection/markers, frontend, performance gates, and a fresh
read-only Checker with zero blocking findings.  Stage 8 remains not started.

The B28A checker is a separate read-only adversary
(`run_phase56_stage7_b28a_readonly_checker.py`) that executes the laundering,
forgery, substitution and isolation attacks against the real types rather than
reading the source and being satisfied.  It reads only: it never writes to the
repository, dispatches a workflow, pushes, mutates a pull request, or touches a
secret.
