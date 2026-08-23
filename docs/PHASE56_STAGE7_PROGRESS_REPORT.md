# Phase 56 Stage 7 progress report

Disposition: **`STAGE_7_IN_PROGRESS / NOT_ACCEPTED`**

Stage 7 is **not** accepted. Stage 8 has **not** been started. PR #16 and PR #17
remain open, Draft, and unmerged, and `main` is unchanged at
`00b3a60de6e13756d089655879a02e4094122047`.

## Current disposition — the authoritative list

Every per-package table further down this document belongs to the session that
wrote it and is retained as history. Where an older table says `ACCEPTED` and
this one does not, **this one is current**.

| Package | Current disposition |
|---|---|
| B28A Stage 7 exact-head artifact integrity | `B28A_STAGE7_EXACT_HEAD_ARTIFACT_INTEGRITY_HARDENING_CONFIRMED` |
| B28A prepare attestation + refusal population seal | historical acceptance remains `B28A_V2_PREPARE_ATTESTATION_AND_REFUSAL_POPULATION_SEAL_INCOMPLETE` — blocker `EXACT_MANIFEST_UNAVAILABLE`; the distinct supplemental seal passes and is not a substitute |
| B28 gold-scored shadow + evidence hardening | historical acceptance remains `B28_V2_GOLD_SCORED_SHADOW_AND_EVIDENCE_HARDENING_INCOMPLETE`; the distinct supplemental M/V/R/G campaign passes with `+9` and cannot retroactively accept B28 |
| B29 horizontal-contact free body | `ENGINE_IMPLEMENTATION_CONFIRMED`; `GOLD_SCORED_ACCEPTANCE_BLOCKED_ON_EXACT_MANIFEST` |
| B32 spring natural-length endpoint | `ENGINE_IMPLEMENTATION_CONFIRMED`; `GOLD_SCORED_ACCEPTANCE_BLOCKED_ON_EXACT_MANIFEST` |
| B30 table-pulley typed frame | **not re-declared accepted** — not re-measured in the B28A sealed pipeline |
| B31 incline kinetic motion sense | **not re-declared accepted** — not re-measured in the B28A sealed pipeline |
| Stage 7 | `STAGE_7_IN_PROGRESS / NOT_ACCEPTED` |
| Stage 8 | `STAGE_8_NOT_STARTED` |

B30 and B31 were measured as 3-of-3 at the `e511b63` checkpoint and that record
stands as history. They were not re-measured under the sealed B28A pipeline —
the manifest that half of the campaign depends on is unavailable — so they are
not carried forward as accepted here.

## Continuation evidence (2026-08-24, latest) — read this first

The authoritative branch remains `codex/phase56-generic-mechanics-engine`.
Commit `a44213620d2a999305fe9640d8351377137613c1` is the current product head.
Commit `9d206556a7874c78a18ca7fe9aab573377264fc6` remediates and locks frontend
dependencies, makes the existing lint toolchain reproducible through `npm ci`,
and enforces `npm audit` in every frontend-bearing workflow. `6bff99e` then
migrates the tracked Render Blueprint to current `runtime` syntax and declares
the existing public root health check. `a442136` aligns the existing Node-engine
contract test with the security-required `>=20.9 <21` range after the first new
push CI exposed the stale `>=20 <21` literal. None changes mechanics, corpus
population, gold, scorer, threshold, tolerance, or any Stage 7 disposition.

The latest exact mechanics-and-frontend evidence predecessor is
`b3b7291d2a6bc38b853a5d16d1a26117ddf5008b`. Its official-v1 locked strict
report has SHA-256
`1a935f0a45452c1da1b4362530f53485fe0152519f8b4fe42337ca09a94712e7`:
44/81 supported correct, zero wrong, 37 supported unresolved, 12/12 deferred,
0/2 unsupported-other, 61/100 terminal mapping, and all 23 hard-safety signals
measured with zero unbound or nonzero values. Lane C/D/E and all control lanes
pass; the strict inner exit remains `2` with exactly ten yield/coverage gate
failures. This remains an acceptance failure, not a safety or harness failure.

The unchanged supplemental M -> V -> R -> G transaction also passed at exact
`b3b7291`: 100 accounted, 97 runtime-completed, 3 projection-refused, 6/6
newly solved correct, 50 total correct (`+9` from the exact-byte baseline 41),
and zero wrong, unscored, forbidden-class, regressed, or query-mismatch cases.
Publication id:
`1af0a36293a324aeee97a0251a0880544acff4894abd125c69a0e6222e8f0f2b`;
scorecard SHA-256:
`5036c9e676546f9d4751fa3b6d631c23d1414ea1317862e9d0e1fc20bb929658`.
It remains supplemental only.

PR CI run `32627235071` at `b3b7291` is still a real failed run: pooled PR10
`rigid_body` p95 was `+25.138%` against the unchanged 15% maximum. The exact
workflow was replayed twice under Linux/Python 3.11.16 with native container
filesystems; both independent campaigns passed at `-1.895%` and `-3.515%`.
That narrows the evidence but does not erase the failed hosted run or establish
its external cause. A new exact-head PR run is required before current CI can
be called green.

The locked baseline frontend graph reproduced four high-severity npm package
records (`next`, `postcss`, `nanoid`, optional `sharp`). At `9d20655`, a clean
Node 20 install resolves `next 15.5.23`, `postcss 8.5.26`, `nanoid 3.3.18`, and
`sharp 0.35.3`; `npm audit` reports zero current findings. Frontend verification
passes 53/53 tests, lint with zero errors and nine existing warnings, typecheck,
static production build, and a native sharp/libvips PNG smoke. This is a dated
dependency-audit result, not a universal security or production claim.

The old Render Blueprint failed the current live schema because it used the
deprecated `env` field. At `6bff99e` the Blueprint validates with zero schema
errors. Eighteen focused deployment/CORS/auth tests pass, and a real local
production-mode Uvicorn process returned health 200, protected API 401 without
and 200 with a token, disabled OpenAPI 404 with authentication, and the exact
configured CORS origin. This is deployment-readiness evidence only: no hosted
service, live secret, DNS/TLS, durable storage, or production traffic changed.

None of this supplies the absent historical manifest or typed authority for the
remaining official cases. Current disposition therefore remains
`STAGE_7_IN_PROGRESS / NOT_ACCEPTED`; Stage 8 remains `STAGE_8_NOT_STARTED` and
was not inspected or begun.

## Completion-goal evidence session (2026-08-23, historical closure)

This section supersedes the current measurements and package descriptions above
where they differ; it does not rewrite any historical result below. The
authoritative branch is `codex/phase56-generic-mechanics-engine`. The final
mechanics code head measured here is
`7794168734321be78b6fa54373bf20a6938d4bd4`; later commits in this section are
documentation or Ballast recovery descendants and no result is re-attributed
to them.

### The separate supplemental campaign is complete

The source-only nine-context selection was frozen before capability changes.
Its canonical manifest digest is
`32aa3ce51e3006e533913b2f822251d22dccba2a379a35008f19e7a7e1aef7cd`, its
manifest file SHA-256 is
`946cd6364669c123341d54999a87a468bc22f7260ea2b8500ddee267878bcd3a`, and its
seal is `phase56-stage7-v2-supplemental-yield-campaign-v1`. The population,
scorer, thresholds, gold boundary, and seal were unchanged between baseline and
final measurement.

| Exact head | Accounted | Runtime / refused | Augmented | All correct | Newly solved correct | Wrong / unscored / regressed | Cohort yield |
|---|---:|---:|---:|---:|---:|---:|---:|
| `51a9c68` pre-change baseline | 100 | 97 / 3 | 6 | 41 | 0 | 0 / 0 / 0 | 0 |
| `7794168` final | 100 | 97 / 3 | 6 | **50** | **6 / 6** | **0 / 0 / 0** | **2** |

The same frozen population therefore improved by exactly `+9` correct from the
portable pre-change baseline. Final Phase M -> V -> R -> G returned PASS.
Publication id:
`e67098ab596907c965ae1e312be1bc73c17a1e0ae83df64b3a4367fccc759746`.
The final runtime, redacted, shadow, and scorecard raw-file SHA-256 values are
respectively `14c217f089d0c7aa5c9780854bf876b1bceada88469b087379636f5aa9bf8c31`,
`ca85b703b0a4f37c7621a71513f4c16a70a13cce3915bb1eedf429ad169d9c5f`,
`00ecaee13e89fd4a3ada64d8b46352f194b07a9260b20b7c083c1757f9c81adc`, and
`da4ee952113fd4bee57b7110bb9c95d104773608a1f11cadea21c1fefdf57242`.

The new capability is general typed mechanics, not corpus routing:

- flat limiting-friction and frictionless banked-curve speed invariants read
  only typed source structure and source-authorized query objective;
- event-scoped instantaneous-centre authority now supports a two-radius,
  two-point velocity chain;
- constraint scope no longer depends on content-hash equation ordering. Two
  order-variant cases that reproduced the defect are permanent regressions.

Focused verification at the code head passed 56 B10/instantaneous-centre tests
including slow tests and 175 adjacent compiler/solver tests. Earlier tests for
the complete curve/IC implementation passed 147 corpus/profile, 47 slow
B10/curve, and 228 adjacent compiler/solver/verifier tests. No case id, family,
expected answer, gold field, array order, variable name, first root, tolerance,
threshold, or population participated in routing or answer selection.

### Current official-v1 result and safety boundary

The supported locked strict command was re-run in a detached worktree at exact
`7794168` against approved archive SHA-256
`cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef`.
Lane D passed 1 isolated and 24 whole-lane tests. The strict report SHA-256 is
`2ae079b071388e8d738991b6e441a95d186c40e253ea44694fa9ca1b159e5b44`.

| Metric | Current official v1 |
|---|---:|
| supported correct | **44 / 81** |
| supported wrong | **0** |
| solved-but-unscored | **0** |
| supported unresolved/unscored | **37** |
| deferred matched | **12 / 12** |
| unsupported-other matched | **0 / 2** |
| terminal mapping | **61 / 100** |
| hard-safety | **23 / 23 measured, 0 unbound, 0 nonzero** |

Lane C, Lane D, Lane E, compositional 12, synthetic 38, metamorphic,
physics-changing controls, redaction, and every safety gate passed. The strict
inner exit is correctly `2`: 81/81 supported, 2/2 unsupported-other, terminal
mapping, six derived 100-percent metrics, and the supported-unscored gate remain
unmet. This is an honest acceptance failure, not a harness or safety failure.

B28A's clean-tree read-only checker again passed all 24 attacks with zero
blocking and zero non-blocking findings; its report SHA-256 remains
`545779ad258a8489d88b9da36c7114535b883dbe33c1bb66e04f9245ccc90a4d`.

### Why Stage 7 remains blocked rather than accepted

Three legitimate paths were exhausted without weakening the contract:

1. The historical exact augmentation manifest remains absent after the recorded
   recovery audit. Reconstructing, guessing, synthesizing, or substituting it is
   prohibited, so its historical campaign cannot be re-measured or sealed.
2. Raw official v1 cannot honestly close the remaining supported population:
   the complete authority census shows the missing reference frames, contact
   side, interval-scoped motion direction, endpoint state, and specialized-model
   declarations are not typed by those source records. Manufacturing them would
   turn assumptions into source facts and violate the physics/provenance gate.
3. The separately identified supplemental route has now met its own `+9`,
   reproducibility, gold-isolation, and zero-regression target. Its contract
   explicitly forbids using it as the historical campaign or as Stage 7
   acceptance.

B29 and B32 remain implemented and regression-tested, but their cohort evidence
belongs to the unavailable historical augmentation campaign; implementation
complete is not acceptance complete. B30/B31 historical results are not promoted.
Accordingly `STAGE_7_IN_PROGRESS / NOT_ACCEPTED` and
`STAGE_8_NOT_STARTED` remain current. Stage 8 was neither searched nor started.

## The uploaded-artifact identity session (2026-08-02, latest) — read this first

External review accepted the Phase M publication work below and found a
separate defect in the evidence *about* it: the Stage 7 artifact the CI
uploaded named a commit that no run had checked out. This session closed
that and nothing else. No cohort was added or removed, no threshold moved,
no physics changed, and B29, B32 and Stage 8 were not touched.

### The defect

`_exact_head_sha()` in the offline gate read `GITHUB_SHA` in preference to
the worktree. On a `pull_request` event GitHub sets `GITHUB_SHA` to the
ephemeral `refs/pull/&lt;n&gt;/merge` commit — the test-merge of the head into
the base — not to the commit `actions/checkout` places in the worktree. The
workflow's own `EXACT_HEAD_SHA` was correct and was used for the checkout;
the gate never read it. So every **pull_request-event** run recorded the
merge commit while compiling, testing and gating the head, and nothing in
the workflow ever compared the two.

| head | run | event | checkout | report `exact_head_sha` |
|---|---|---|---|---|
| `df27bc7d` | `30729850273` | pull_request | `df27bc7d` | `42b0f2f1…` |
| `d709c851` | `30731194110` | pull_request | `d709c851` | `014732…` |

Both recorded values are test-merge commits, reachable from no branch: the
commits API answers **422 No commit found** for `42b0f2f1e57ddd…`. Fetching
`refs/pull/17/merge` at the time of writing gives
`014732bea2e4b927c2a59a0194d01fe1b212187e`, whose parents are exactly the
base `4762727e` and the head `d709c851` — the same construction, for the
same PR. The push-event runs at those heads were unaffected, because on a
push `GITHUB_SHA` *is* the head.

Reproduced directly rather than inferred: with `GITHUB_SHA` set to that
merge commit the pre-fix resolver returns it, and the `git rev-parse HEAD`
fallback — which was already correct — is never reached.

**The overwrite hypothesis is disproved and recorded as such.** The
suspicion was that a later `pytest` step re-used a shared default report
path and clobbered the file before upload. It did not. The runner's default
output was `REPOSITORY_ROOT/stage7_offline_gate_report.json`, never the
`RUNNER_TEMP` path the workflow wrote and uploaded; no test writes that
path; and the one in-suite subprocess invocation of the gate already wrote
into its own `TemporaryDirectory`. The defect was provenance, not
collision. The path hardening below was still done — a default output
inside the working tree is a latent hazard — but it is not what caused this.

### What changed

| Point | Guarantee |
|---|---|
| gate resolves the head from `git rev-parse HEAD` only | the environment describes the *event*; only the worktree describes the *source*, and the artifact is evidence about the source. An unresolvable head raises instead of degrading to a placeholder |
| `--expect-head-sha` | configured head and worktree must agree *before* anything is measured, so a disagreement costs a second and can never reach a written report |
| `--output` required, no default | no two commands in one job have a shared path to collide on |
| `stage7-offline-&lt;head&gt;-&lt;run id&gt;-&lt;attempt&gt;.json` | the path names the run and the source, and an existing path is a failure rather than an overwrite |
| `check_stage7_ci_artifact_identity.py` before the upload | re-opens the file, parses it structurally, and requires configured head == `git rev-parse HEAD` == report `exact_head_sha`, canonical 40-lowercase-hex, the schema, the privacy contract, no public-100 PASS in a corpus-independent run, and the sealed raw digest |
| upload conditioned on that check | a mismatched or tampered report is refused, not published |
| raw-byte seal | hashed from `read_bytes()`, so CRLF and LF cannot seal alike |

The checker parses rather than greps: the correct SHA appearing elsewhere in
the document does not satisfy it.

48 controls in `test_phase56_stage7_ci_artifact_identity.py`, each asserting
the **name** of the gate it hits; the matrix is in
`docs/PHASE56_STAGE7_TEST_MATRIX.md`. The mismatch control was confirmed to
fire against the actual pre-fix resolver, so it is shown to fire rather than
merely to pass. One of them exists because a control named `..._for_external_audit`
collected and never ran: `tests/conftest.py` marks any nodeid containing
"audit" and `pytest.ini` deselects that marker, so the test read like coverage
while being absent from every default run. It was caught by the collected
count moving, and is now pinned.

### Local evidence at the exact code head `d49d3610`

venv rebuilt for this session from `backend/requirements-lock.txt`;
`/home/user/.venv-stage7/bin/python`, Python 3.11.15.

| run | exit | result | wall |
|---|---:|---|---:|
| repository-default backend regression (`python -m pytest -q`) | 0 | **4618 passed**, 1 skipped, 0 failed, 903 deselected | 1634.07 s |
| Stage 7 focused glob (`tests/test_phase56_stage7_*.py`) | 0 | 1454 passed, 474 deselected | 312.68 s |
| Phase M publication + attestation seal + fail-closed + gold-scored + gold isolation | 0 | 234 passed | 77.88 s |
| artifact identity focused (`test_phase56_stage7_ci_artifact_identity.py`) | 0 | 48 passed, 0 deselected | 8.0 s |
| B28A read-only checker | 0 | 24 checks, 0 blocking, `ACCEPTANCE=PASS` | — |
| Stage 7 offline gate | 0 | `CORPUS_INDEPENDENT_REGRESSION`, public lanes `NOT_RUN` | — |
| artifact identity checker | 0 | `STAGE7_CI_ARTIFACT_IDENTITY=PASS` | — |
| `python -m compileall -q app engine evaluation tools tests` | 0 | clean | — |

**4618 = the previously recorded 4570 plus exactly the 48 new controls**, and
the deselected count is unchanged at 903 — the corroboration that nothing else
moved. This is the repository-default backend regression selection, not a full
backend suite: `pytest.ini` deselects
`benchmark`, `audit`, `frontend` and `slow`.

### Auditing the artifact from outside the run

The uploaded artifact could previously only be checked by downloading it
from the Actions blob store. Where egress policy blocks that host — as it
does in this environment, which is denied `productionresultssa7.blob.core.windows.net`
at CONNECT — the run's own verdict was the only evidence available, which is
exactly the dependency this package exists to remove. The run now reproduces
the **exact uploaded bytes** in its log as base64, after the upload,
alongside the artifact id and the uploader's digest. Decoding and hashing
them reproduces `STAGE7_ARTIFACT_REPORT_RAW_SHA256` and yields the report's
own `exact_head_sha`, so the invariant is checkable against the log rather
than assertable by the job. The Artifacts API reports the same digest for
the same artifact id, which binds the stored blob to those bytes.

### The superseded declaration

`EXACT_HEAD_CI_EVIDENCE_CLOSED`, as declared for the `df27bc7d` / `d709c851`
pass, **was not true of the uploaded artifacts** and is withdrawn for those
heads. What held there is narrower and is restated as:

```
CI_WORKFLOW_CONCLUSIONS_GREEN
STAGE7_UPLOADED_EXACT_HEAD_ARTIFACT_INTEGRITY_INCOMPLETE
```

`PHASE_M_SINGLE_COMMIT_GENERATION_PUBLICATION_CONFIRMED` stands: the
publication protocol was reviewed and found valid, this session did not
touch it, and its regression is re-run at this head.

### Exact-head CI and the uploaded artifact

Two code heads, each with a complete run set. **16 runs, 16 success, 0
non-success, no re-run, no empty commit.** `in_progress`, `queued`,
`cancelled` and `skipped` are not counted as success.

| head | event | workflow | run ID | attempt | conclusion | duration |
|---|---|---|---|---|---|---|
| `76dce50d` | push | Phase 55 textbook parser | `30734816960` | 1 | success | 0m38s |
| `76dce50d` | push | Phase 56 Stage 6 multimodal | `30734816967` | 1 | success | 18m08s |
| `76dce50d` | push | Phase 56 Stage 7 offline evaluation | `30734816959` | 1 | success | 23m26s |
| `76dce50d` | push | DynaTutor release tests | `30734816969` | 1 | success | 21m28s |
| `76dce50d` | pull_request | Phase 55 textbook parser | `30734818390` | 1 | success | 6m40s |
| `76dce50d` | pull_request | Phase 56 Stage 6 multimodal | `30734818379` | 1 | success | 17m41s |
| `76dce50d` | pull_request | Phase 56 Stage 7 offline evaluation | `30734818367` | 1 | success | 23m59s |
| `76dce50d` | pull_request | DynaTutor release tests | `30734818374` | 1 | success | 21m38s |
| `d49d3610` | push | Phase 55 textbook parser | `30735017371` | 1 | success | 2m52s |
| `d49d3610` | push | Phase 56 Stage 6 multimodal | `30735017397` | 1 | success | 13m51s |
| `d49d3610` | push | Phase 56 Stage 7 offline evaluation | `30735017381` | 1 | success | 28m13s |
| `d49d3610` | push | DynaTutor release tests | `30735017379` | 1 | success | 16m36s |
| `d49d3610` | pull_request | Phase 55 textbook parser | `30735018750` | 1 | success | 1m25s |
| `d49d3610` | pull_request | Phase 56 Stage 6 multimodal | `30735018748` | 1 | success | 14m28s |
| `d49d3610` | pull_request | Phase 56 Stage 7 offline evaluation | `30735018754` | 1 | success | 25m59s |
| `d49d3610` | pull_request | DynaTutor release tests | `30735018746` | 1 | success | 16m59s |

**The defect shown closed, at `76dce50d`.** The push run and the pull_request
run at that head produced **byte-identical** reports —
`STAGE7_ARTIFACT_REPORT_RAW_SHA256=0191341d…` in both. On a push
`GITHUB_SHA` is the head; on a pull_request it is the merge commit. Under the
old resolver the two reports would have differed in exactly one field. They
do not differ at all.

**The uploaded artifact, audited at `d49d3610`.**

```
STAGE7_ARTIFACT_RUN_ID=30735017381
STAGE7_ARTIFACT_RUN_ATTEMPT=1
STAGE7_ARTIFACT_RUN_HEAD_SHA=d49d3610877a03653fea83efde42f7ffff60d199
STAGE7_ARTIFACT_CHECKOUT_SHA=d49d3610877a03653fea83efde42f7ffff60d199
STAGE7_ARTIFACT_REPORT_SHA=d49d3610877a03653fea83efde42f7ffff60d199
STAGE7_ARTIFACT_REPORT_RAW_SHA256=8725c3bd264a33924f348b3979a4d12c96c410ad517ba1d2359b56903215443d
STAGE7_ARTIFACT_ID=8829540891
STAGE7_ARTIFACT_ZIP_SHA256=d25f8705127f77ae5330033dd164c0c6e7907c68ead82206481df7027d90eb92
STAGE7_ARTIFACT_IDENTITY_MATCH=true
```

Three independent confirmations, not one:

1. the run's own pre-upload checker passed, and the upload was conditioned
   on it;
2. the report bytes republished in the run log decode to JSON carrying
   `"exact_head_sha": "d49d3610877a03653fea83efde42f7ffff60d199"`, with
   `public_corpus` and `lane_b` `NOT_RUN`, `external_model_calls` 0 and
   `private_heldout_accesses` 0 — the corpus-independent scope intact;
3. the report was **regenerated independently at this head outside CI** and
   came out byte-identical — same SHA-256 `8725c3bd…`, same base64 prefix and
   suffix — so the uploaded bytes are reproducible from the source rather than
   merely asserted by the run that made them.

The uploader's digest `d25f8705…` equals the digest the Artifacts API reports
for artifact `8829540891`, which binds the stored blob to those bytes.

**Stated exactly:** the artifact ZIP itself was *not* re-downloaded, because
this environment's egress policy denies
`productionresultssa7.blob.core.windows.net` at CONNECT (403). That host was
not routed around. The three confirmations above are what replaces it, and
the byte-level reproduction in (3) is stronger than a download would have
been: a download proves what was stored, a reproduction proves what the
source produces.

`EXACT_HEAD_CI_EVIDENCE_CLOSED` — for `76dce50d` and `d49d3610`, on the
evidence above.

### B29 and B32

Neither was started. Beyond the engine walls recorded further down, both are
blocked from *acceptance* at this head for the same reason B28A is: their
closure evidence is the augmented-campaign measurement, and the augmented
half of the campaign is a function of the exact augmentation manifest, which
is unavailable. Engine capability work on them could proceed independently;
a moved disposition could not.

## The single-commit publication session (2026-08-02, previous) — superseded only where §latest states

Independent review of the previous cleanup found its central declaration
overstated, and this session closed only that. No cohort was added or removed,
no threshold moved, no physics changed, and B29, B32 and Stage 8 were not
touched.

**The defect.** `PHASE_M_ATOMIC_PUBLICATION_CONFIRMED` was declared over a
publication that renamed three artifacts to three final paths in sequence.
Each rename was atomic; the set was not. An exception or a process kill
between the renames left the authoritative paths holding a new candidate
archive beside an old runtime input and an old attestation — confirmed by
driving the actual pre-fix tool (restored from `2073ebaf`, file SHA-256
`975ccd98…`) under a fault at its second rename: the mixture appeared and the
old cleanup path, which ran exactly as written, could not undo the rename that
had already happened. The fixed `<name>.partial` staging names were shared by
every run, so concurrent writers could overwrite each other's staging, and a
read-back mismatch could return before its staged path was registered for
cleanup.

**What closes it.** A publication layer
(`evaluation/phase56_stage7/corpus_v2/publication.py`): each run stages into a
private `generations/.tmp-<uuid4>` directory; the complete, validated
generation — read-back hashes, attestation, campaign seal, cross-artifact
binding, all judged from the staged bytes — is promoted by one directory
rename to `generations/<attestation-digest>` (format-pinned to 64 hex before
any path use) and never modified again; and authority changes exactly once, at
`os.replace` of a validated fsynced `CURRENT.<token>.partial` onto
`CURRENT.json`. A failure before the promote removes only the run's own
staging; a failure after it leaves the previous authority byte-unchanged and
the new generation as a complete, unreferenced orphan — deliberately, since
deleting it could delete a directory another writer just committed to.
Durability is claimed at process level (fsync ordering, best-effort directory
fsync), not as power-loss proof.

**The pipeline is pinned.** Phase M prints
`STAGE7_V2_PREPARE_PUBLICATION_ID=<generation-id>`; the orchestrator captures
it once — AST-pinned, with a guard that refuses to continue unpinned — and
Phase V, R and G resolve that exact generation via
`--publication-root`/`--publication-id` without ever re-reading
`CURRENT.json`, so a pointer moved by a second writer mid-pipeline cannot make
two phases observe two preparations. The readers' explicit path flags remain
as the non-authoritative probe harness the laundering matrix needs; Phase M's
flat-path output flags are gone entirely, and an AST control pins that the
prepare tool performs no `replace`, `rename` or `write_text` of its own. The
checker's attestation-required probe was replaced — not weakened — by a
behavioral check, because with a publication-pinned mode the attestation can
arrive from inside a resolved generation and `required=True` would have
checked the spelling rather than the property.

**Evidence.** 31 new controls in
`test_phase56_stage7_corpus_v2_publication_transaction.py` — the legacy
protocol reproduced failing first, then interruption at every new-protocol
boundary, per-artifact read-back mismatch cleanup, orphan semantics, pointer
replace failure, success completeness/idempotence/immutability, reader
pinning, deterministic interleaved concurrent writers, collision refusal, and
gate-by-gate pointer validation with re-signed forgeries — plus the four
earlier publication controls restated against the new protocol. At the exact
code head `df27bc7dafd3a33abe7f8c49995296d17e22dfda`
(venv rebuilt from `backend/requirements-lock.txt`;
`/home/user/.venv-stage7/bin/python`, Python 3.11.15, pytest resolving to
`/home/user/.venv-stage7/bin/pytest`):

| run | exit | result | wall |
|---|---:|---|---:|
| full backend suite | 0 | **4570 passed**, 1 skipped, 0 failed, 903 deselected | 1093.68 s |
| Stage 7 focused glob | 0 | 1408 passed, 474 deselected | 208.83 s |
| publication + seal + fail-closed + gold-scored | 0 | 190 passed | 51.07 s |
| B28A read-only checker | 0 | 24 checks, 0 blocking, 0 non-blocking, PASS | — |
| Stage 7 offline gate | 0 | `CORPUS_INDEPENDENT_REGRESSION`, public lanes `NOT_RUN` | — |

4570 is the previously recorded 4539 plus exactly the 31 new controls.
Exact-head CI run IDs are recorded in PR #17 §5.1; the mirror work branch
creates no push runs because every workflow filters its push trigger to the
authoritative branch, which is the filter working, not a gap. One run's
re-runs are disclosed in full there: the pull_request Stage 6 run's attempt 1
was cancelled when one shard's test step stalled into the job's 20-minute
timeout (the same shard had already passed at the same SHA in the push-event
run); attempt 2 re-ran only the failed jobs, the shard passed in 2m43s, and
the partition audit failed by construction — it requires all eight
attempt-scoped manifests and a partial re-run uploads only one; attempt 3 was
a full re-run so the audit could see the whole partition. Nothing else was
re-run and no empty commit was made to provoke a run.

`PHASE_M_SINGLE_COMMIT_GENERATION_PUBLICATION_CONFIRMED`. The earlier
`PHASE_M_ATOMIC_PUBLICATION_CONFIRMED` is **superseded** and retained below as
history. Phase V's replay remains defense in depth, not a substitute for
publication atomicity. B28A stays
`B28A_V2_PREPARE_ATTESTATION_AND_REFUSAL_POPULATION_SEAL_INCOMPLETE` on
`EXACT_MANIFEST_UNAVAILABLE` — the exact manifest (canonical digest
`c7222978…`, file SHA-256 `95aca084…`) is still absent from this environment,
and no manifest was reconstructed, guessed or approximated. B28, B29 and B32
stay `INCOMPLETE`; B30/B31 are not re-declared; `STAGE_7_IN_PROGRESS /
NOT_ACCEPTED` and `STAGE_8_NOT_STARTED` stand. PR #16 untouched; PR #17 open,
Draft, unmerged; `main` unchanged.

## The attested-preparation session (2026-08-01) — read this first

Independent verification of the previous checkpoint found one further
structural fail-open path in the B28 acceptance seal, and this session closed
only that. No cohort was added or removed, no threshold moved, no physics
changed, and B29, B32 and Stage 8 were not touched.

**The defect.** The ledger closed *silent omission* — every context gets a row,
so nothing can leave the run by vanishing. But every completeness rule read the
runtime input, and the runtime input was an unsigned JSON document. So instead
of removing a context you relabel one as an anticipated refusal with a null
draft. Do it to all 97 measurable contexts and the run reports a hundred-row
ledger, a hundred permitted refusals, zero records, zero wrong, zero unscored,
zero regressed — and acceptance PASS. The shape changed from **silent
omission** to **allowed-refusal laundering**; the consequence did not.

**What closes it.** Cross-field validation, so the laundered row cannot be
spelled while it keeps anything the projection produced. A prepare attestation,
so Phase M states and hashes what it produced — including *which* contexts were
refused, not merely how many. A new Phase V that rebuilds the preparation from
the corpus and the manifest, because every other check is a comparison between
two documents Phase M wrote and a forger who rewrites both consistently
satisfies all of them. And a frozen campaign seal pinning this campaign's exact
97/3 population, so a run coherent about some other population is still not
this measurement.

Forward-only from `3afed91`; no reset, rebase, amend, squash, force-push, or
history rewrite.

```
3afed91  (B28A session start = prior documentation head)
61a940b  fix(stage7): bind runtime inputs to attested prepare state          [B28A]
3e0f75f  test(stage7): pin refusal laundering and prepare replay attacks     [B28A]
0263dd0  docs(stage7): record the attested-preparation checkpoint            [B28A]
8471126  fix(stage7): publish prepare artifacts only after sealed validation [B28A cleanup]
         docs(stage7): close exact-head CI and PR status evidence            [B28A cleanup]
```

The final code head of the cleanup pass is `8471126b5c3a12346657f210a443a10754e34e58`;
this document is its documentation-only descendant, with no code change between
them. Exact-head CI for both is recorded in PR #17, which a commit cannot
contain its own SHA to record here.

| Package | Commit | Disposition |
|---|---|---|
| B28A prepare attestation + refusal population seal | `3e0f75f` | **`B28A_V2_PREPARE_ATTESTATION_AND_REFUSAL_POPULATION_SEAL_INCOMPLETE`** — blocker `EXACT_MANIFEST_UNAVAILABLE` |

**The blocker.** The exact augmentation manifest (canonical digest
`c7222978…`, file SHA-256 `95aca084…`) is a restricted out-of-tree artifact and
is not present in this environment. Every structural gate B28A adds is
implemented, tested and independently checked; the *augmented* half of the
public campaign — 15 augmented records, 9 newly solved, the three closed
cohorts — could not be re-measured, because every one of those numbers is a
function of the manifest. No augmented v2 number is restated here as
re-measured, and none is withdrawn.

Running Phase M against the approved corpus with the seal enforced fails on
exactly two gates and no others:

```
STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:campaign_seal_manifest_digest_mismatch,
                                  campaign_seal_manifest_file_sha_mismatch
```

which is itself the evidence for the other nine sealed values: the corpus hash,
the context count, the context order, the handle sequence, the prepared-state
map, the refusal handle set and both count vectors all matched the seal against
the real archive.

**Unchanged at this head.** `OFFICIAL_V1` strict: 41/81 supported correct, 0
wrong, 0 solved-but-unscored, 12/12 deferred, 0 blocked-numeric, 0
blocked-silent, 0 deferred-silent, 0 of 23 hard-safety signals non-zero, lanes
C/D/E PASS. Strict still exits 2 on the Stage-7-incomplete gates, as it has
throughout. The v1 terminal map is byte-identical to the previous checkpoint's.

`STAGE_7_IN_PROGRESS / NOT_ACCEPTED` and `STAGE_8_NOT_STARTED` stand.

### Phase M publishes only after the seal passes

A follow-up read found Phase M's docstring overstating its own guarantee. It
claimed a failed preparation "leaves no partial evidence behind"; the
forbidden-key scan does run before any write, but the **campaign seal did not**.
The candidate archive and the runtime input went to their final paths first, and
a preparation refused for being some other campaign exited 2 with two of its
three artifacts left where Phase V, and a hand-run Phase R, look for them.

Not an acceptance bypass — Phase V re-reads all three and refuses a set with no
attestation — but a code/comment disagreement on a fail-closed path, which is
what a bypass looks like one edit before it becomes one.

The ordering constraint cannot be removed: the seal is judged over the
attestation, the attestation carries each artifact's file SHA-256, and a file
hash needs bytes on a filesystem. So the write stays and the **publication**
moves. Each artifact is staged beside its destination as `<name>.partial`, its
hash is recomputed from the bytes read back off the filesystem, the attestation
and the seal are judged, and only then are all three renamed into place. A
refusal unlinks its own staged files and leaves the final paths exactly as it
found them — including an earlier honest preparation, which the old ordering
overwrote before the seal had run.

Three controls pin it, plus one on the orchestrator. Both negative controls were
confirmed to **fail** against the previous ordering, so they are shown to fire
rather than merely to pass; the seal they are judged against is derived from the
synthetic campaign's own honest attestation, so the negative pair differs from
the positive one by the two manifest hashes alone.

`PHASE_M_ATOMIC_PUBLICATION_CONFIRMED` was declared here and is **superseded**
by the 2026-08-02 session above: the refusal-path guarantee stands, but the
success path this pass declared atomic still published through three
sequential renames, and the current declaration is
`PHASE_M_SINGLE_COMMIT_GENERATION_PUBLICATION_CONFIRMED`. No threshold,
tolerance, budget or population changed in this pass, and B28A's disposition
was unmoved.

### Exact-head CI, closed

| head | push | pull_request |
|---|---|---|
| `3e0f75f` (final code) | 4 workflows, 4 success | 4 workflows, 4 success |
| `0263dd0` (documentation) | 3 workflows, 3 success | 4 workflows, 4 success |

15 runs, 15 success, **0 non-success**; run IDs are recorded in
`PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md` §-3.9. Nothing was re-run and no empty
commit was made to provoke a run.

The push `DynaTutor release tests` at `0263dd0` **does not exist**, and that is
the path filter working: `backend-tests.yml` filters its push trigger to
`backend/**`, `frontend/**`, `scripts/**` and its own file, and `0263dd0` touches
only `docs/`. An earlier report described that run as still in flight; it was
never queued, so it had no terminal state to reach. The run actually still going
at that moment was the push `Phase 56 Stage 7 offline evaluation` `30708379886`,
which completed **success** after 27m44s. The Release suite is attested at this
documentation head by the pull_request run `30708381513` (success).

### Two earlier reports corrected

1. The **23.1-minute Stage 7 regression run was not a hang.** It completed
   normally; the wall time was runner contention, and it was misread as a stall.
2. The **benchmark wrapper failure was an invocation artifact, not a defect.**
   The venv's `bin` was missing from `PATH`, so a bare `pytest` subprocess
   resolved to a different interpreter that could not import the project's
   dependencies. Running with the venv first on `PATH` — the discipline every
   local figure in this document now follows — reproduces neither failure.

## The gold-scoring and pilot-campaign session (2026-08-01, earlier) — read this first

The previous session reported a v2 shadow result of **3 newly solved, 0 wrong**.
The first number was a real runtime measurement. The second was not a
measurement at all.

`run_shadow_context` took an optional `compare_answer` callback and the public
runner never passed one, so a solved context came back neither correct nor
wrong and the aggregate published `wrong: 0` — which meant "nothing was
compared" and read as "nothing was wrong". This session closed that, and the
scorer immediately earned its keep by catching three confidently wrong answers
in a cohort that would otherwise have been booked as yield.

Forward-only from `e8cc866`; no reset, rebase, amend, squash, force-push, or
history rewrite.

```
e8cc866  (session start = prior documentation head)
d19370b  fix(stage7): score frozen v2 shadow outcomes in the gold domain        [B28]
0a50ccd  engine(stage7): close v2 table-pulley profiles from typed frames        [B30]
afe95c5  engine(stage7): consume typed incline motion states                     [B31]
7aba65f  test(stage7): pin the B29 and B32 closure-catalogue walls               [B29/B32]
3e71494  perf(stage7): answer the frame orientation without serialising a Draft
8352079  test(stage7): state the B30 support-orientation contract in the B15 suite
```

**Historical / superseded.** The dispositions in the table below are the ones
this earlier session declared, at the `e511b63` checkpoint. Three of them no
longer stand: B28 is now `INCOMPLETE`, and B30 and B31 are not re-declared
accepted because the sealed B28A pipeline did not re-measure them. Read the
authoritative list at the top of this document instead.

| Package | Commit | Disposition **as declared then** |
|---|---|---|
| B28 gold-scored shadow + evidence/axis hardening | `d19370b` | `B28_V2_GOLD_SCORED_SHADOW_AND_EVIDENCE_HARDENING_ACCEPTED` — **superseded, now `INCOMPLETE`** |
| B29 V2 horizontal-contact free body | `7aba65f` (evidence) | **`B29_V2_HORIZONTAL_CONTACT_FREE_BODY_INCOMPLETE`** — engine wall, still current |
| B30 V2 table-pulley typed frame | `0a50ccd` | `B30_V2_TABLE_PULLEY_TYPED_FRAME_ACCEPTED` — 3 of 3 **at that checkpoint; not re-declared accepted** |
| B31 V2 incline kinetic motion sense | `afe95c5` | `B31_V2_INCLINE_KINETIC_MOTION_SENSE_ACCEPTED` — 3 of 3 **at that checkpoint; not re-declared accepted** |
| B32 V2 spring natural-length endpoint | `7aba65f` (evidence) | **`B32_V2_SPRING_NATURAL_LENGTH_ENDPOINT_INCOMPLETE`** — catalogue wall, still current |

### The two scores, which are different objects

**`OFFICIAL_V1` did not change and that is the result.** 41/81 supported, wrong
0, solved-but-unscored 0. Verified after every engine change by diffing the
runtime terminal map over all 100 public contexts against the pre-change
baseline: **byte-identical**, three times.

**`EXPERIMENTAL_V2_SHADOW_SCORED`** — a measurement against an out-of-tree
candidate archive that is not the frozen public corpus, and never an official
score:

| Figure | Value |
|---|---:|
| Augmented contexts | 15 of 97 |
| Newly solved | 9 |
| Newly solved **correct** | **9** |
| Newly solved wrong | 0 |
| Newly solved unscored | 0 |
| All shadow correct / wrong / unscored | 50 / 0 / 0 |
| Forbidden-class solves | 0 |
| Regressions | 0 |
| Cohort yield | 3 |
| Deterministic rebuild | byte-identical |

The 50 all-shadow correct is 41 pre-existing solves plus the 9 new ones, and
the 41 scoring correct under this comparator is the same comparator agreeing
with the official gate — a useful cross-check, not a second score.

### B28 — runtime before gold, and three counts instead of two

Scoring is now sequenced rather than interleaved. *Phase R* projects, compiles,
solves and verifies without reaching an expected answer, terminal, failure code,
family or case id, then seals every context into a frozen
`ShadowRuntimeSnapshotV2` and hashes it. *Phase G* opens the gold for the first
time, pairs each case to a frozen record by an opaque handle derived from the
archive digest and the context position, and compares. The scorer holds a
snapshot rather than a Draft, so it cannot re-run the pipeline having seen the
answer, and it refuses a snapshot whose contents no longer match the digest it
was sealed with.

The comparison is not new code. `compare_answer_to_gold` was factored out of the
official strict scorer and both callers go through it, so a shadow "correct"
means exactly what an official one means. The shadow scorer contains no float
literal, no `abs`, no `isclose` and no numeric comparison of its own, and a test
reads that off its AST rather than trusting the prose.

`ShadowScorecardV2` counts correct, wrong and unscored separately. A newly
solved context nobody could score fails acceptance instead of vanishing into the
wrong count; a context whose expected class has no answer and which solved
anyway is a `forbidden_class_solve`.

Gold isolation is measured, not asserted: changing an expected answer, an answer
unit, a tolerance or an expected terminal leaves the runtime snapshot's digest
material byte-identical while the score moves.

**Two bypasses closed with it.** The validator's unknown-evidence check was
guarded on the universe being non-empty (`if evidence and any(...)`), so a
context with no source evidence and no authored quote had an empty universe and
every reference passed unexamined — the check failed *open* in exactly the case
it exists for. And `AxisSense` is now explicitly not runtime authority: changing
only a sense leaves the projection identical, a sense never completes a missing
binding, and its one power is refusing a cross-frame binding whose two axes
carry directly opposed senses and a sign agreeing with neither. Senses from
different oppositions — world up against a surface normal — are not compared at
all, because deciding between them would need geometry this contract does not
carry.

### B30 — one reading of a stated support orientation, in four places

B15 was revoked because a generic `surface` primitive proves nothing about
orientation and a support-owned angle of zero fixes no reference. Both hold. The
contract that replaced them required the source to state the orientation
*twice*: once as the frame binding that says this support's tangent **is** the
world's x axis and its normal **is** the world's y, and again as a numeric zero.

The binding is the complete statement — which is why the planner, the closure,
the compiler contract and the law recognizer all make it mandatory. Demanding
the zero on top asked the source to repeat itself in a form the public v1 record
has no field for. Four places asked that question and three had their own
answer; the reading moved to `typed_support_frames.stated_support_orientation`
and a test pins that all four are the same object. The numeric zero became an
optional second statement that must agree when present.

Nothing widened: the frame binding stays mandatory everywhere, a tangent bound
to world y still states a vertical support, a reversed normal is still a
different statement, and the frame-less v1 shape the public corpus carries still
fails closed exactly as B15 left it.

**3 of 3 closed.** A representative context solves at 2.8029 m/s² —
`m_B g / (m_A + m_B)` for 5 kg and 2 kg.

### B31 — a direction is not a speed, and the scorer proved why that matters

The kinetic-slide law reads `motion_sign` and nothing else, yet both it and the
closure demanded a positive numeric speed. A corpus could therefore only express
"it is sliding down the slope" by also inventing a magnitude, and an invented
magnitude is indistinguishable downstream from a stated one. A value-free
directed motion record is now admitted — `raw_value: None`, provenance
`unknown`, carrying axis, sign, subject, interval and the source's own evidence
— and a stated speed is still checked exactly as before.

It also derives the typed slide-motion authority the law requires, from the
typed structure alone. A manifest cannot name that authority: there is no
carrier field for it. The derived ids are declared approvable by the caller and
the authority bundle still checks that the Draft's approved dispositions equal
that set, so a carrier cannot approve itself.

**The gold scorer caught a real defect on the first run.** `SENSE_SIGN` maps
`down_slope` to −1, which assumes an up-slope-positive tangent; the engine's
kinetic-slide law resolves the same axis down-slope-positive and drives
`+g sin θ` along it. A slide authored with the slope-relative spelling reached
the *up-slope* formula and produced three solved, verified, confidently wrong
answers — **5.2128 m/s² where the physics gives 3.0790**. The three counts
reported `newly_solved_wrong: 3`. The pre-B28 runner would have reported "newly
solved 3, wrong 0" and the yield would have been booked.

The fix adds no second convention. A self-referential tangent binding — the only
kind an incline frame carries — states an identity and no orientation, so
`up_slope`/`down_slope` on that axis is refused rather than resolved, and the
axis-relative spelling, whose meaning the binding alone fixes, is required.

**3 of 3 closed**, at 3.0790 m/s² for 25° and μ = 0.12.

### B29 and B32 — the source can say it; the closure catalogue cannot build it

Both were opened and both were carried as far as the v2 contract reaches. Their
carriers were authored, projected and measured: augmented +6, newly solved +0,
regressed 0. What stops them is not the corpus.

**B29** — `_horizontal_surface_contact_profile` admits exactly two regimes:
`sticking` (a body at rest under an applied force, a = 0) and `sliding` (a
moving body with **no** applied force and **no** tangential-acceleration
unknown). B29 is a moving body *with* an applied force *and* an unknown
tangential acceleration, which the sliding branch rejects by construction, and
nothing emits `Σ F_t = m a_t` for a horizontal contact. There is no
`ProfileId.horizontal_contact` transaction either.

**B32** — `ProfileId` has no spring-energy member at all. Its only spring entry
matches period/frequency queries and declares no capability, and `_TRANSACTIONS`
has no spring transaction. Both `spring_potential` and `kinetic_energy` laws
exist, so the gap is the free body nobody builds, not the physics.

Closing either needs a new engine law or a new closure transaction — capability
work, not authority work. That distinction is the whole point of the census, so
it is pinned as tests reading the catalogue and the engine source directly,
including the sliding-regime guard read off its own AST.

### What this does not claim

The 9 newly-solved-correct is **not** an official score and must not be added to
41. It is a measurement against a candidate archive built from a
human-authored manifest, over 15 of 97 public contexts, on cohorts chosen
because their sources state what v1 has no field for. Nothing here is a claim
about private held-out generalization, and nothing here changes the frozen v1
corpus, the v1 acceptance target, or Stage 7's disposition.

---

## The v2 correction session (2026-08-01, earlier) — superseded in part by the section above

An independent audit found three blocking defects in the v2 candidate below,
and this session corrected them forward-only from `99789b0` — no reset,
rebase, amend, squash, force-push, or history rewrite — and closed the first
real pilot cohort in shadow.  The section below this one is kept as written
and superseded only where stated here and in
`docs/PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md` §0.

```
99789b0  (session start = prior documentation head)
4022e91  fix(stage7): trace source-stated query objectives correctly            [C1]
c7de7be  fix(stage7): make v2 augmentation fill-only and conflict-safe          [C2]
742105b  fix(stage7): project v2 frames as typed axis bindings                  [C3]
7458a2c  engine(stage7): close the vertical-circle limiting-contact cohort ...  [pilot]
1777c91  test(stage7): pin the static-frame admission determination             [C4 determination]
```

| Package | Commit | Disposition |
|---|---|---|
| C1 query-objective source mapping | `4022e91` | **`C1_QUERY_OBJECTIVE_PRESERVATION_ACCEPTED`** |
| C2 v2 fill-only conflict contract | `c7de7be` | **`C2_V2_FILL_ONLY_CONFLICT_CONTRACT_ACCEPTED`** |
| C3 v2 reference-frame projection | `742105b` | **`C3_V2_REFERENCE_FRAME_PROJECTION_ACCEPTED`** |
| C4 static-frame compiler compatibility | `1777c91` (tests only) | **NOT NEEDED** — measured: typed static frames are already admitted; the old regressions were the malformed projection |
| Vertical-circle limiting-contact pilot | `7458a2c` | **CLOSED** — 3 newly solved, 0 wrong, 0 regressed, cohort yield 1 |

**The corrected shadow checkpoint** (all artifacts regenerated at the exact
code head; no prior out-of-tree hash reused): shadow regressions **3 → 0**,
shadow wrong **0**, newly solved **0 → 3**, cohort yield **0 → 1**, augmented
contexts 3 of 97, deterministic rebuild byte-identical, regression guard in
its fail-closed default.  Manifest digest `0e5a8d11…8534`, candidate archive
SHA-256 `06bf23a2…355e`, shadow report file SHA-256 `c314b189…58d7`, scorecard
digest `9618779c…fd1b`.

**Official v1 is unchanged**, re-measured under the dependency lock at the
exact final code head `1777c91`: supported **41/81**, wrong **0**,
solved-but-unscored 0, deferred 12/12, terminal mapping 58/100, hard safety
23/23 with every counter zero, Lanes C/D/E PASS, strict gates 29 PASS / 10
FAIL with exit 2 — byte-for-byte the Stage-7-incomplete profile.  Strict
report (out-of-repo) SHA-256
`e5e1ff3f0288721e175a70382c14bbffa117bd123f3c29957cb31b3b159dc704`.  The
corpus SHA is the frozen `cc8d8b27…1bef` and no v2 number is added to any
official figure.

**The B22 correction.**  The semantic audit's "seven missing carriers" was a
measurement error the audit itself now refuses to repeat: `query_objective`
has a controlled v1 source carrier (`query.output_key = minimum_speed →
minimum`, the B12 repair), the canonical table is consumed by both the
projection and the audit, and the machine-measured omission count is **6**
(`STAGE7_SEMANTIC_AUDIT_SOURCE_OMISSIONS=6`).

**B24–B27 dispositions after the checkpoint:**

| Package | Disposition |
|---|---|
| B24 typed reference frame and angle datum | **`B24_TYPED_REFERENCE_FRAME_AND_ANGLE_DATUM_INCOMPLETE`** — the projection is corrected and parity-pinned, regressions are 0, but no frame-*dependent* pilot context has solved: the frame-needing cohorts are blocked on `underdetermined` free-body completion, an engine package this session did not open |
| B25 typed contact side | **ACCEPTED** — a contact pilot with full boundary authority solved (3 contexts), the side can no longer overwrite a source statement, wrong 0 |
| B26 typed motion sense and endpoint condition | **ACCEPTED** — the endpoint cohort solved via `contact_limit`, event/interval widening is structurally refused, wrong 0 |
| B27 v2 migration, shadow evaluation and pilot closures | **`B27_V2_MIGRATION_SHADOW_EVALUATION_AND_PILOT_CLOSURES_ACCEPTED`** — deterministic migration/archive/report, regression 0, pilot closures 3, shadow wrong 0 |

What did **not** change: no file under `backend/engine/` or `backend/app/`
was touched; no threshold, tolerance or budget moved; no test was deleted (one
wrong audit pin was replaced by the corrected, stricter pin the independent
audit demanded); the corpus stays out of the repository; and
`STAGE_7_IN_PROGRESS / NOT_ACCEPTED`, `STAGE_8_NOT_STARTED` stand.

## Reproducible evidence and the v2 candidate (2026-08-01) — superseded in part above

This session produced no change to the official v1 score and two things that
were previously only claims: a strict report that reproduces, and a census that
executes.  The sections below it are kept as written and are superseded only
where this section says so.

Forward-only from `e391672`.  No reset, rebase, amend, squash, force-push, or
history rewrite.

| Item | Commit | Disposition |
|---|---|---|
| B20 strict environment reproducibility | `c37166d` | **ACCEPTED** |
| B21 executable authority census | `1a1530d` | **ACCEPTED** |
| B21 census correction | `c376b29` | **ACCEPTED** |
| B22 semantic preservation audit | `830561e` | **ACCEPTED** |
| B23 corpus contract v2 foundation | `1b2220a` | **ACCEPTED** |
| B24 typed reference frame and angle datum | `1b2220a` | **INCOMPLETE** — yields 0, regresses 3 |
| B25 typed contact side | `1b2220a` | **INCOMPLETE** — 6 carried, 0 yield, 0 regression |
| B26 typed motion sense and endpoint | `1b2220a` | **INCOMPLETE** — 6 endpoints carried, 0 yield |
| B27 v2 migration, archive and shadow evaluation | `1b2220a` | **ACCEPTED as a measurement**, 0 pilot closures |
| `OBSERVED_PUBLIC_SCORE` | **41/81** | unchanged |
| Supported wrong / unscored / downgraded | **0 / 0 / 0** | |
| Terminal mapping | 58/100 | unchanged |
| Hard safety | 23/23 measured, 0 unbound, 0 nonzero | |

### B20 — Lane D was the environment, and now that is provable

The last strict report failed Lane D on one test, and the failure was
unattributable: it reproduced in an unpinned container and passed in exact-head
CI, so neither "the engine is broken" nor "the container is wrong" could be read
off the evidence.  A strict report that cannot say which of those it is, is not
evidence about the engine.

`backend/evaluation/phase56_stage7/locked_environment.py` states the environment
as a contract and `backend/tools/run_phase56_stage7_locked_strict.py` runs the
real gate under it: the lock installed into a dedicated interpreter and verified
back, a detached worktree pinned to an exact commit, and credentials removed
from the child environment rather than assumed absent.

Under the lock, at `c37166d`: the isolated test **passes**, Lane D **passes
24/24**, and strict public-100 is **29 PASS / 10 FAIL** where it was 28 / 11.
**Lane C, D and E all PASS.**  Every remaining FAIL is a Stage-7-incomplete gate.
Nothing about the score moved.

Locked environment: Python 3.11.15, fastapi 0.128.2, starlette 0.50.0,
pydantic 2.13.4, pydantic-core 2.46.4, pytest 9.0.2, sympy 1.14.0,
numpy 2.3.5, scipy 1.17.0, httpx 0.28.1, pint 0.25.3.

### B21 — the census now executes, and it corrects the document

The previous census lived in a table: seventeen cohorts, every one blocked on a
premise the corpus does not type, eleven of the seventeen reducing to a missing
reference frame.  `authority_census.py` computes it instead.

| Figure | Document | Measured |
|---|---:|---:|
| supported unsolved | 40 | **40** |
| supported-unsolved cohorts | 17 | **17** |
| authority-blocked | 40 | **33** |
| capability-blocked (engine declares out of scope) | — | **8** |
| closure candidates | 0 | **1** |
| reference-frame dependent | 11 of 17 cohorts | **13 contexts / 6 cohorts** |

The first two reproduce.  The rest did not, and the measurement stands.

The census also publishes its own negative control and its own precision.  Per
carrier, how often its absence coincides with a solve as well as with a
non-solve: `contact_side` 0 and 6, `constraint_authority` 0 and 3,
`interaction_target` 0 and 1, `angle_reference_datum` 3 and 10,
`endpoint_condition` 9 and 9, `reference_frame` 13 and 13.  The last two are
coin flips and are reported as such rather than tuned until they read zero — a
rule adjusted until its negative control vanished would have been fitted to the
outcome it is supposed to explain.

Four rules were wrong in the first run and each correction is a test.  Chief
among them: an endpoint carrier counted as *available* whenever any event-bound
condition existed, so a stated "starts from rest" satisfied a requirement about
what holds at the finish.

### v1 closure-safe yield is **0**, and that is now measured

Every one of the forty supported-unsolved contexts is traced to a carrier the v1
source contract cannot state, or to a model the engine itself declares out of
scope.  The single remaining automated candidate is the free-flight cohort whose
interval ends on `reaches_condition` — an event kind that says a condition was
reached without saying which — and B22 shows the contract has no field to state
it.  No v1 closure package was opened, because opening one would have meant
inventing the premise.

### B22 — the projection drops nearly nothing, and the contract states nothing

"The projection drops nothing" was measured by counting records.  Equal counts
are not preservation: every revoked meaning survived that count and lost the
thing that mattered.  `semantic_preservation.py` traces meaning instead, over
32 source field categories and 97 projected contexts.

- **Seven engine carriers have no source field at all** — reference frame (34
  contexts need one), angle datum (13), frame axis direction, motion sense,
  contact side, query objective, quantity frame binding.
- Projection loss: **1 field category, 3 contexts, 3 occurrences**.
- Normalization loss: **0**.
- Law-consumption gaps: **1** (`occurrence_index`, stated 276 times and read by
  nothing).

Three false alarms in the audit's own first run were found and fixed, and each
is a test: reading a `DirectionBinding.name` field the contract does not have
reported all 105 stated directions as dropped; comparing an event's segment
against `occurs_in_interval_ids` reported 104 of 132 bindings as dropped when
the interval's own boundary fields carry every one; and tracing refused
projections reported a hundred fields of three contexts as lost when the engine
had simply declined to model them.

Every revoked meaning is pinned as a regression — B10, B12, B15, B16, B17, B18 —
each asserting the source still cannot supply it.

### B23–B27 — the v2 candidate carries the physics; the compiler does not yet read it

Full record in `docs/PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md`.

`dynatutor-ko-corpus-v2.0-candidate` adds the seven missing carriers, additively
and separately: v1 loader, schema and strict scoring untouched, no automatic
upgrade, migration driven by an explicit manifest that a structural scan forbids
from naming any answer-bearing field.  The original v1 record is carried
byte-identical, rollback is deterministic, and two independent rebuilds against
the public archive produced byte-identical archives and reports.

The shadow evaluation exercised **5 carrier categories over 22 augmented
contexts** and produced **0 new solves, 0 wrong, and 3 regressions**.  Supplying
a stated reference frame moves three contexts that currently verify a correct
answer to `compiler_unsupported :: requires_specialized_model` — the compiler
reads a stated frame as evidence that a specialized model is needed, which is
the opposite of what the v2 hypothesis predicted.

So the corpus-side work is done and the engine-side work is not.  The next Stage
7 package is a compiler package: a stated reference frame must be authority to
proceed, not a reason to refuse.  That is recorded, not fabricated, and it was
not opened this session.

## Phase H, B19, and the authority census (2026-07-31, later session) — read this first

This session is **superseded by nothing**; the section below it records the
earlier same-day session and stays as written.

Forward-only from `d01b4db`. No reset, rebase, amend, squash, force-push, or
history rewrite; B19 was withdrawn by a **revert commit**, not by deleting
history.

| Item | Commit | Disposition |
|---|---|---|
| B15 `TABLE_PULLEY_TWO_BODY` future-positive path | `dc8795d` | **hardened**, still INCOMPLETE, public delta **0** |
| B16 `PARTICLE_ON_INCLINE_KINETIC_FRICTION` future-positive path | `b2add89` | **hardened**, still INCOMPLETE, public delta **0** |
| B19 `UNSUPPORTED_OTHER_TYPED_TERMINALS` | `dd42ebe` landed, `a4ced6a` **reverted** | **INCOMPLETE**, public delta **0** |
| Documentation | `0355845` | authority census of the remaining 40 |
| **Final code head** | **`a4ced6a`** | backend byte-identical to `b2add89` |
| **Documentation head** | **`0355845`** | |
| `OBSERVED_PUBLIC_SCORE` | **41/81** | unchanged |
| `AUTHORITY_ACCEPTED_SCORE` | **41/81** | observed = accepted |
| Supported wrong / solved-but-unscored / downgraded | **0 / 0 / 0** | |
| Deferred | 12/12; needs_figure 2/2; needs_confirmation 2/2; insufficient 1/1 | |
| unsupported_other | 0/2 (unchanged known gap) | |
| Terminal mapping | 58/100 (unchanged) | |
| Hard safety | 23/23 measured, 0 unbound, 0 nonzero | |

**Nothing moved, and each reason is measured.**

*Phase H closed the future-positive halves of two already-revoked packages.*
Revoking the public path last session left the closures still able to
manufacture the authority they were revoked for: B15 minted a
tangent/world-x binding out of a bare zero angle and then read that binding back
as evidence the orientation had been stated, and B16 converted a **world**
`downward` into a **slope-tangent** sign and promoted an `initial_velocity`
instant to the whole interval. Both now consume a source-authored reference
frame or refuse. Strict public-100 is identical before and after — a hardening
package that moved the score would have been the wrong shape.

*B19 was built, measured, landed, and reverted.* Its discriminator was clean:
over all 100 public cases, "every mechanism container empty" and "graph cannot
determine the query" selected exactly the two `unsupported_other` targets and
none of the 93 expected-`complete` cases, and would have delivered 2/2 and
mapping 60. Exact-head CI then failed eleven tests, ten of which hold the
opposite and more conservative contract: naming something without relating it
is not evidence of a specialized model, because `underdetermined` leaves the
door open to solving the problem later and `requires_specialized_model` shuts
it. Passing them would have meant weakening the assertions that exist to
prevent exactly that claim, so the package was withdrawn instead.

*The remaining gap is now measured exhaustively.* All 40 expected-supported
cases that do not solve were partitioned into 17 typed cohorts, and each
cohort's missing physical premise identified with the typed carrier that would
supply it. **Every one is blocked on a premise the corpus does not type**, and
eleven of the seventeen reduce to the same missing record — a reference frame
(`contexts_without_reference_frame = 97/97`). Separately measured: the
projection drops nothing, so the gap is in what the corpus states, not in what
the evaluator reads. The table is in
`docs/PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md`.

**Next exact task.** Not another closure package. Terminal mapping counts only
matches and all 40 expect `accepted`, so the next point costs a solve that no
currently-typed authority supports. The next Stage 7 packages are
**corpus-contract packages** — a case must be able to state a reference frame,
a contact side, a slope-relative direction, or an endpoint condition before any
of the 40 can be closed honestly.

Stage 8 must not start.

## B15/B16 authority repair and B18 residual session (2026-07-31) — read this first

An independent authority audit found that **B15 and B16 both produced
public-correct answers from authority the source never states**, and this
session repaired both forward.  No reset, rebase, amend, squash, force-push, or
history rewrite; every pre-session commit is preserved byte-identical, and the
earlier acceptance records below are kept as history rather than edited away.

| Item | Commit | Disposition |
|---|---|---|
| B15 `TABLE_PULLEY_TWO_BODY` | `f67550a` | **INCOMPLETE / revoked**, −3 public solves |
| B16 `PARTICLE_ON_INCLINE_KINETIC_FRICTION` | `0ea3148` | **INCOMPLETE / revoked**, −3 public solves |
| B18 `DIRECTION_SAFE_RESTITUTION_RESIDUALS` | `a544e4b` | **ACCEPTED**, +1 public solve |
| Slide-authority naming | `b825013` | identifiers only, no behaviour change |
| Final code head | `b82501333183c7cec2dbc8d9efacfc438a52e0ae` |  |
| `OBSERVED_PUBLIC_SCORE` | **41/81** | measured at the final code head |
| `AUTHORITY_ACCEPTED_SCORE` | **41/81** | observed = accepted |
| Supported wrong / solved-but-unscored / downgraded | **0 / 0 / 0** |  |
| Deferred | 12/12; needs_figure 2/2; needs_confirmation 2/2; insufficient 1/1 |  |
| unsupported_other | 0/2 (unchanged known gap) |  |
| Terminal mapping | 58/100 (was 63/100) |  |
| Hard safety | 23/23 measured, 0 unbound, 0 nonzero |  |
| Lanes C/D/E, compositional 12, synthetic 38, metamorphic, physics-changing, redaction | all PASS |  |
| External model calls / private access / measured cost | 0 / 0 / $0 |  |
| Strict report | `stage7_strict_public100_b825013.json`, SHA-256 `4132cf05ca9d52dc1bd726e887aa5e80f0c870f414a14ad86099d16ab64077f4` (out-of-repo) |  |
| Corpus archive SHA-256 | `cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef` |  |

**The score went down on purpose.** A solve without typed authority is a defect
even when its number is right; removing it is the repair, not a regression.

### B15 — the generic surface was never horizontal (`f67550a`)

`EntityPrimitive.surface` is a *generic* support.  The corpus contract uses the
same primitive for a banked road, a vertical circular track, and a level floor,
so it can never stand for "horizontal" — and the accepted profile read exactly
that: a `surface`, no `incline` primitive, and no `angle` quantity were taken
together as a stated zero slope.  The transaction then wrote world axes (table
acceleration +x, normal +y, weight −y, hanging acceleration −y) that nothing in
the source licensed.  Information the source never states is not evidence of a
zero.

The orientation now has to be stated.  The one authority admitted is the
source's own support angle — owned by the support entity, evidenced, and
exactly zero, a value that reads the same in every angular unit so the check
needs no unit policy and cannot be widened by one.  Four independent places
require it: the profile signature, the closure transaction, the compiler's
fixed-pulley horizontal-contact contract, and the horizontal-contact law
profile.  The closure records what it means as typed structure: a support frame
whose tangent is bound to world +x and whose normal to world +y, plus an angle
relation carrying the source quantity itself.

Nothing else substitutes: not the primitive, not a missing incline, not a
missing angle, not a label reading "horizontal table", not a sentence in the
problem text, not a nearly-zero number.  The public table-pulley cases state no
support angle, so they fail closed with no numeric output.  **57 focused
tests**, including stated-zero positives, unit invariance of zero, label and
problem-text negative controls, duplicate and second-surface refusals, and
Draft-level mutations of the support frame.  The legacy table-hanging parity
fixture states the same zero angle explicitly, so the long-standing horizontal
contract keeps its coverage under the stricter rule.

### B16 — `sliding_on_incline` never said which way (`0ea3148`)

The accepted profile inferred the slide direction from absence: one body, one
incline, one slide segment, gravity and nothing else was read as "gravity is
the whole driving system, therefore the block is going down".  That confuses
"gravity could start this motion" with "this motion is happening", and no
stated velocity is silence rather than proof.

Direction decides the physics.  On the down-slope-positive tangent a down-slope
slide obeys `a = g(sin θ − μ cos θ)` and an up-slope slide `a = g(sin θ + μ cos
θ)`, because kinetic friction opposes the motion that exists.  The projection
now carries the sense only when the source states it: one velocity fact about
the sliding body, inside the sliding segment, with typed direction `downward`
or `upward`.  A body constrained to the slope moves along the slope tangent, so
those two are the slope senses; `left`, `right`, `along_motion`,
`opposite_motion`, and `unspecified` resolve no sense without a slope facing
the source never gives.  The sense stays on the physics record — the source
velocity, rebound to the slope tangent with its own sign, carried by the typed
motion state — and the law reads the friction sign from that quantity.

The `a ≥ 0` companion inequality is **removed**.  It encoded the same confusion
and refused correct answers whenever `μ > tan θ`: a block already sliding down
a shallow rough slope decelerates, and a negative tangential acceleration is
the right answer.  The remaining inequality states what the model really
requires of a source value — a friction coefficient is never negative.

The public kinetic-incline cases state no velocity at all, so they fail closed.
**47 focused tests**, including up-slope and down-slope closed forms, the
high-friction decelerating slide the old premise refused, direction negative
controls for every non-slope-sense direction, contradictory and duplicated
statements, wrong subject/segment/event scope, non-positive speeds, a roped
second body, and a B15/B16 non-interference control.  The adversarial
ambiguous-friction case still reaches `needs_confirmation`.

### B18 — one directed-scalar contract, +1 public solve (`a544e4b`)

Two of the four applicable restitution impacts never reached a verified solve,
and both were the same scalar encoded two ways.

* **Zero-valued directionless velocity — solved.**  A velocity that is exactly
  zero and states no direction is not missing a direction: `+0` and `−0` are
  the same number on either side of the line of impact, so a body whose speed
  is exactly zero has one velocity vector there.  It is admitted only inside
  the exact one-dimensional impact topology — two bodies, one line of impact,
  the collision-start boundary, the same axis the restitution and momentum laws
  use — and only for an exact finite zero.  Anything merely small, and every
  nonzero directionless magnitude, stays refused.
* **Negative value beside a stated direction — INCOMPLETE, fail-closed.**  A
  scalar that names a direction has stated a magnitude; a magnitude is never
  negative; and which encoding wins when they disagree depends on an axis
  orientation the source never states.  The two readings are mirror-image
  physics, so this refuses at the binding instead of answering.  It previously
  reached the solver and was rejected there — the same outcome, now stated at
  the right layer.

The helper reads a sign and a number — never a role, subject, family, case, or
answer — and is exercised directly so the rule cannot become a per-value patch.
**60 focused tests** (35 existing plus 25 new).

### Regression, strict, and CI at the final code head

- Full Stage 7 focused suite: **1,318 passed**.  Full `phase56_mechanics`
  parity suite: **1,886 passed**.  Backend collection: **4,095 tests, 0
  errors**.
- Strict public-100 (`--require-public-corpus --require-full-stage7`): exit
  **2** (expected while Stage 7 is incomplete), **29 strict gates PASS / 10
  FAIL**.  Every FAIL is a Stage-7-incomplete condition: supported < 81,
  `unsupported_other` 0/2, terminal mapping < 100%, unscored > 0, and the five
  100%-metric gates that follow from them.
- Exact-head CI at `b825013`, all with verified exact checkout: push runs
  `30621958241` (parser), `30621958220` (Stage 6: frontend, focused, regression
  shards 0–7, partition audit, gate — 12 jobs), `30621958236` (Stage 7:
  offline-evaluation incl. full backend regression and collection, frontend, B7
  polar slow, Stage 7 gate — 4 jobs), `30621958223` (release: fast shards 0–3,
  slow shards 0–15, both partition audits, quality, performance, frontend,
  release gate — 26 jobs); PR runs `30621960616`, `30621960798`, `30621960777`,
  `30621960759`.  **8/8 SUCCESS.**
- A **SAME_MODEL_READ_ONLY_CHECKER** (the same Opus model as the author; *not*
  represented as an independent Checker) audited `4898465..b825013`:
  **PASS — blocking 0**.  Scope: B15 horizontal authority and generic-surface
  misuse, B16 motion-direction authority, kinetic/static separation,
  high-friction negative acceleration, B18 zero normalization and sign
  double-application, B10/B12 revoke preservation, raw-text/label/family/case
  routing, generated values, event/interval scope, wrong confident solves,
  threshold/tolerance/budget relaxation, test deletion, gold isolation, and
  strict attribution.  Four non-blocking notes are recorded in
  `PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md` §B18.  A fresh independent Checker
  remains a prerequisite for any Stage 7 acceptance claim.

---

## B15/B16 acceptance session (2026-07-30, later) — **SUPERSEDED**

> **Superseded by the 2026-07-31 authority repair above.**  The B15 and B16
> acceptances recorded here did not hold: both closed on authority the source
> never states, and both were revoked forward.  The section is preserved
> unchanged as the record of what was claimed and when.  Its
> `OBSERVED_PUBLIC_SCORE` / `AUTHORITY_ACCEPTED_SCORE` of 46/81, and its
> B15/B16 `ACCEPTED` dispositions, are **not** current.


This session continued Stage 7 from the measured 40/81 baseline
(documentation head `52b237d`) and closed two structure packages forward-only;
no reset, rebase, amend, squash, force-push, or history rewrite; every
pre-session commit is preserved byte-identical.

| Item | Value |
|---|---|
| B15 `TABLE_PULLEY_TWO_BODY` | **ACCEPTED** — code `9084091`, +3 public solves |
| B16 `PARTICLE_ON_INCLINE_KINETIC_FRICTION` | **ACCEPTED** — code `3baa29d`, +3 public solves |
| Projection owner fix | `a97e794` — body-stated constitutive parameters keep their source owner |
| B17 `SPRING_ENERGY_ENDPOINT_SPEED` | **INCOMPLETE** — no code; see below |
| Final code head | `a97e794b6f2b0a4b4521c280a03d62d03b9a361b` |
| `OBSERVED_PUBLIC_SCORE` | **46/81** (measured at the final code head) |
| `AUTHORITY_ACCEPTED_SCORE` | **46/81** (observed = accepted; no unmeasured claims) |
| Supported wrong / solved-but-unscored / downgraded | **0 / 0 / 0** |
| Deferred | 12/12; needs_figure 2/2; needs_confirmation 2/2; insufficient 1/1 |
| Terminal mapping | 63/100 (was 57/100) |
| Hard safety | 23/23 measured, 0 unbound, 0 nonzero |
| Lanes C/D/E, compositional 12, synthetic 38, metamorphic, physics-changing, redaction | all PASS |
| External model calls / private access / measured cost | 0 / 0 / $0 |
| Strict report SHA-256 | `ff2d4b108f613e0eb3466f3232e443009cdedcdcac9ef4d60bb112e6900c75df` |
| Corpus archive SHA-256 | `cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef` |

`PUBLIC_EVALUATION_INFORMED_FIX: YES` — the packages were selected and
verified by running the authorised public corpus and reading privacy-safe
aggregates.  No private-corpus generalization is claimed.  Stage 7 remains
`IN_PROGRESS / NOT_ACCEPTED`; Stage 8 is `NOT_STARTED`.

### B15 — table-pulley two-body (`9084091`)

A body on a frictionless horizontal table tied over a fixed ideal pulley to a
hanging body; aggregate acceleration-magnitude query.  The projection's
fixed-pulley closure admits the typed `surface` support variant alongside the
incline variant; the new `table_pulley_two_body` profile is disjoint from
`incline_hanging_pulley` by the source's own support primitive (never an
invented zero angle).  The transaction derives only the world frame,
weight/contact/rope interactions, contact and rope states, and value-free
unknown components; the pre-built horizontal-contact law recognizer and
compiler contract were widened to the free-body primitives the corpus
projection actually produces, an optional system entity, and the authorized
server-default gravity policy record.  All solving stays with the existing
`particle_weight`, `particle_newton_second`, `rope_massless_tension`,
`rope_fixed_pulley_motion`, `fixed_contact_no_penetration`, and
`contact_normal_bound` laws.  The vertical two-body (Atwood) transaction now
refuses a support primitive with no typed support relation instead of
treating it as an inert bystander (the B10 lesson applied forward).
31 focused tests.

### B16 — kinetic incline slide (`3baa29d`)

One body in a source-declared kinetic slide down one incline with a
source-valued angle and friction coefficient; tangential-acceleration query,
down-slope positive.  The corpus states no mass, so the existing force-based
incline laws cannot close the shape; instead the projection derives a
`gravity_driven_downslope_sliding` authority by closed policy only when
gravity is the entire typed driving system (one body, one incline support, a
`sliding_on_incline` segment, no stated velocity, force, rope, rest boundary,
extra body, or extra proposal) — the same model-completeness footing as the
B14 impact-isolation policy.  A friction coefficient stated on the support
surface takes the sliding body as its typed owner under the existing
interaction-owned constitutive convention.  The new registered
`incline_sliding_kinetic_acceleration` law — the sliding twin of the existing
sticking law — emits the per-mass slope closure plus the authority's own
nonnegative-drive inequality, so a declared slide gravity cannot drive
refuses instead of answering.  The rolling-energy candidate no longer claims
a declared sliding regime, and the active-incline-friction compiler gate
accepts exactly the mass-free downslope-authorised shape while every
force-bearing mixture keeps failing closed.  The adversarial
ambiguous-friction case remains `needs_confirmation`.  25 focused tests.

### B17 — spring energy endpoint speed — INCOMPLETE, stated honestly

The corpus's typed event structure does not preserve the natural-length
endpoint: the end event's kind is the generic `finish`, and the
natural-length wording exists only in raw-text evidence quotes, which the
engine must never read as authority.  Without a typed carrier for "final
spring deformation is zero", the final-speed query of an attached-spring
release is genuinely underdetermined (the deformation at `finish` is
unstated), and any server default for it would be exactly the silent-solve
hazard the B12 revocation removed.  B17 is recorded INCOMPLETE with no code;
the three affected public cases remain ordinary non-solves (wrong 0, blocked
numeric 0).

### Regression, environment, and audit notes

- Full Stage 7 focused suite at the final code head: **1,245 passed**;
  backend collection 4,095 tests, 0 errors.
- One projection defect found by the suite (a body-stated coefficient was
  rejected as owner-ambiguous) was repaired forward at `a97e794`.
- The first strict run of this session was executed against unpinned
  dependencies and mis-measured Lane D (FastAPI 0.141 route registration);
  the official report was produced under `requirements-lock.txt` versions,
  where Lane D passes.  No code changed between the two runs.
- Exact-head CI at `a97e794` (all with verified exact checkout): push runs
  `30560360254` (parser), `30560359932` (Stage 6: frontend, focused,
  regression shards 0–7, partition audit, gate), `30560360115` (Stage 7:
  B7 slow, offline evaluation incl. full backend regression and collection,
  frontend, Stage 7 gate), `30560360250` (release: fast shards 0–3, slow
  shards 0–15, both partition audits, quality, performance, frontend,
  release gate); PR runs `30560366152`, `30560365767`, `30560365734`,
  `30560365696`.  **8/8 SUCCESS.**
- A **SAME_MODEL_READ_ONLY_CHECKER** (same Fable model as the author; not
  represented as an independent Checker) audited `52b237d..a97e794` across
  twelve scope areas (table/incline separation, kinetic/static separation,
  B10/B12 revoke preservation, routing, generated values, event/interval
  scope, near-miss coverage, compiler gate widenings, thresholds, gold
  isolation, strict attribution): **PASS — blocking 0**, with eight
  non-blocking notes recorded in the session evidence (among them: the
  downslope compiler predicate could also check the approved-id set like its
  sibling; the `a97e794` owner fix deserves its own pinned control; B15
  inherits B8's tolerance of stray unused source quantities rather than
  B16's exact-count style; and the B16 authority's physical premise — no
  up-slope slide without stated prior motion — should stay documented
  wherever the profile is).  A fresh independent Checker remains a
  prerequisite for any Stage 7 acceptance claim.

## B10/B12 authority repair session (2026-07-30)

An independent review found that two sealed packages produced public-correct
answers **without sufficient typed authority**, and this session repaired both
forward (no history rewrite) and landed one new package:

| Item | Commit | Disposition |
|---|---|---|
| B10 common-centre repair | `3411e8eb2e5f920512fcfacc51af11a90d16ea9d` | **B10 INCOMPLETE / revoked** — the profile now requires the source's own typed rotation centre (one `rotates_about` → `coincident` record binding the body to a third, otherwise-inert centre point).  The pre-repair public shape (general plane motion, floating centre entity, no typed relation) is pinned refusing, whatever the ratio computes. |
| B12 limiting-contact repair | `58ae586cbeb8783632d6b09eb2f4a14703858f26` | **B12 INCOMPLETE / revoked** — `minimum_speed` now projects a typed `QueryObjective` the planner enforces globally (no exact-value profile may read an objective-bearing draft), and the `v² = g·r` boundary needs the full typed limiting authority: an `inward` `ContactSide` on the contact, a `contact`/`touching` state over the interval, and a `boundary`/`active` state at the top instant.  The corpus schema cannot state the orientation or the boundary states, so the public vertical-circle cases now fail closed. |
| Frame-reference audit follow-up | `a837719e86be0117126b003eb00e01a3dcc7e1d0` | Classifies the two additive enum fields in the observer-frame audit registry (they are enums, never references); repairs the CI failure at `58ae586`. |
| **B14 1D restitution impact** | `53a169d1ed46fd200e453e5a47784550e2215a13` | **Implemented and tested** (35 focused tests, full stage-7 suite 1,189 passed locally).  New closed-policy projection derivation `external_impulse_negligible` per body from typed model completeness; exact-shape profile + transaction; the pre-existing collision static-boundary recognizer gains the Lane B closure shape as a second exact form, and its own [0, 1] coefficient domain fail-closes unphysical restitution.  **Public yield unmeasured — see the blocker below.** |

**Accounting — measured and reconciled (strict gate re-run after the archive
was supplied mid-session).** `OBSERVED_PUBLIC_SCORE` = `AUTHORITY_ACCEPTED_SCORE`
= **40/81, wrong 0** at `exact_head_sha d719def` (code `53a169d`): the six
revoked B10/B12 solves are gone exactly as designed (both profiles measure
97/100 `not_applicable`, 0 complete — no wrong solve, no downgrade, no blocked
numeric answer, no silent solve), and **B14 adds +2** (collision_restitution:
4 applicable, 2 `verified_solve_reachable`, 1 `profile_plan_not_formable`,
1 `solver_rejected` with no numeric output).  Deferred 12/12; needs_figure
2/2; needs_confirmation 2/2; insufficient_information 1/1; unsupported_other
0/2; terminal mapping 57/100; hard safety 23/23 measured, 0 unbound,
0 nonzero, PASS; lanes C/D/E, compositional 12, synthetic 38, metamorphic,
physics-changing controls, redaction all PASS; exit 2 on Lane B yield gates
only.  Strict report: `/root/stage7_external/stage7_strict_report_d719def.json`,
SHA-256 `fc562bb7dc091894dd6e363a367a1a8305e648df6bc1e26e8646182be3f5fe01`,
corpus SHA-256 verified `cc8d8b27…`, evaluator `phase56-stage7-evaluator-v3`,
contract v1, schema `dynatutor.phase56_stage7.offline_gate` 1.0.  **B14 is
therefore ACCEPTED** (additional supported correct +2, wrong 0, exact-head CI
8/8 SUCCESS at `53a169d`).  The next two restitution contexts (one
plan-not-formable, one solver-rejected, both numberless) are the family's
remaining shape candidates.

The earlier revision of this section, preserved below for the session record,
was written while the archive was absent:

**Corpus-unavailable blocker (this session).** The authorised public archive
(SHA-256 `cc8d8b27…`) is supplied out-of-tree per session and was not present
in this session's container.  No strict public-corpus gate could run; every
public-100 number in this report below this line is the previous session's
measurement at its own head.  The next session with the archive must first
re-run the strict gate at `53a169d` (or later) and reconcile observed =
authority-accepted before any new package.

**Next exact implementation task (measured diagnosis, this session).** The
strongest next family is the **table-pulley two-body** closure (~3 contexts by
the in-tree matrix; the same contexts appear as `fixed_pulley`'s
`authority_fixed_pulley: missing` and `incline_hanging_pulley`'s
`quantity_angle: missing` rows).  A projected table shape reaches validation
`needs_confirmation` because no closure consumes its value-bearing frictionless
approvals; the `_derive_fixed_pulley_assumptions` chain refuses it twice over
(the `lies_on` support must be an *incline* primitive, and two `frictionless`
approvals — pulley and table — break the one-match-per-kind rule); and the
incline profile demands the angle a horizontal table never has.  The package is
a B8-scale table-variant closure (profile + transaction + a horizontal-support
branch of the law profile).  The translating-frame family must **not** be
attempted as yield: its three clean contexts are expected-deferred (the
measured `supported_downgraded_to_unsupported = 0` proves it), so solving them
would create deferred silent solves.

## Supersession note

Earlier revisions of this report described the corpus-preflight checkpoint
(`LANE_B_NOT_STARTED`) and, before that, a corpus-unavailable blocker. Both
states are superseded: the authorised public archive has since been supplied,
its integrity re-verified, and the public 100 **executed end-to-end through the
engine**. The evidence below replaces the preflight-only claims. Historical
package heads remain listed for provenance; their CI evidence still belongs to
them and must not be re-attributed.

## Exact heads

| Role | SHA |
|---|---|
| Main baseline (unchanged) | `00b3a60de6e13756d089655879a02e4094122047` |
| Session base (remote head at session start) | `bc5e0be81ba66c2551f0ef47fa05511167949624` |
| Evaluator v3 package | `1954d14a58bf1b3135d3d42057354958de8a24e4` |
| **CODE_CANDIDATE_HEAD (this session)** | `803b40c37389315a96d2819b4350cad2c00f892b` |
| **STRICT_GATE_TESTED_HEAD** | `803b40c37389315a96d2819b4350cad2c00f892b` |
| **FULL_REGRESSION_TESTED_HEAD** | `1954d14a58bf1b3135d3d42057354958de8a24e4` |
| DOCUMENTATION_HEAD | this commit |

`FULL_REGRESSION_TESTED_HEAD` is deliberately named separately and is **not**
re-attributed to the code candidate. The 4,478-test local regression ran at
`1954d14`; the only later change, `803b40c`, removes tests and adds none (86 → 15
in one file, by collapsing parametrisation into loops). The whole backend is
re-run independently at `803b40c` by CI — `backend fast`, `backend slow`,
`backend quality`, `backend performance` and the release gate all SUCCESS.

The candidate was reflected onto `codex/phase56-generic-mechanics-engine` by a
verified-ancestor **fast-forward push only**
(`7963de0 → 9918d47 → 47b99d2 → 9a6e4b9 → bc5e0be → 1954d14 → 803b40c`). No reset,
rebase, amend, squash, force-push, or history rewrite occurred anywhere in the
session. Every pre-session commit is preserved byte-identical; every change landed as a
new atomic commit on top of them.

## Session packages (`d33c70b..b88a9ea`, 10 atomic commits)

| Package | Commit | Content |
|---|---|---|
| A — event source authority | `a677547` (+`15255a5`) | An event kind licenses a numeric boundary equation only when its gold-declared `evidence_quote` binds to an exact, unique span of the problem text and flows through `source_evidence` into `Event.evidence_refs`. Missing, unfound, or ambiguous quotes fail closed as typed `event_authority_gaps`; unproven events are preserved but never license emission. No raw-text keyword or regex routing. Shared eligibility contract in `engine/mechanics/laws/event_boundary.py`, consumed identically by the law layer and the Stage 7 derivation. |
| B — typed occurrence scope | `a3b9b43` (+`fc4ec64`) | `Event.occurs_in_interval_ids` types segment-interior occupancy separately from boundary authority; `MotionInterval.start/end_event_id` stays the sole boundary authority. Forged interiority (an occupied event that is actually an endpoint) and foreign-subject occupancy are rejected at validation; the compiler enforces inverse reciprocity and applies occurrence reach at every scope site. |
| C — elapsed-duration query binding | `0083fd9` | A time query rebinds to a typed segment duration only when the segment's both boundaries are set, distinct, and the query's event role is terminal — proven from typed fields, with no epoch invention and no role smuggling. Unprovable time queries decline rather than misbind. |
| D — structural angle refusal | `c616151` | The magnitude-with-angle launch refusal is pinned to what an equation structurally touches (consumed angle quantities, folded trig literals, signed launch components, sign machinery) instead of `law_id` substrings, so it is rename-proof. Frozen refusal behaviour unchanged. |
| E — profile-isolated feasibility | `223c070` | `profile_feasibility.py` rewritten: each (profile, context) pair is measured by an independent selected-profile run; 14-status taxonomy; unimplemented profiles report `profile_not_implemented` = **not measured**, never a definitional zero; `precise_unsupported` only via exact typed compiler codes; declaration-order invariance proven by permutation. |
| Solver waiver | `84d1cb6` | Exact static-graph recognizer admits the evidenced-extremum boundary family ({event_vertical_extremum_velocity, particle_constant_acceleration_velocity, uniform_gravity_acceleration}); gravity emission now cites its `constant_gravity` authorization; the verifier's `source_evidence` check accepts assumption citations as provenance while still failing when both evidence and citations are empty. First end-to-end applied-profile verified solve achieved (synthetic apex time `t = v0/g`, all checks passed). |
| Gate aggregation | `1770ea1` | The offline gate now measures every Stage 7 lane honestly: Lane C/D suites in fresh interpreters, compositional 12, synthetic 38, metamorphic, physics-changing controls, gold-scored answer scoring (pint, SI), counts-only hard-safety aggregate, redaction stamp, `--require-full-stage7` strict keys. |
| Gate CI parity | `b88a9ea` | Lane E runs exactly the workflow's steps (pinned eslint toolchain, tests/lint/typecheck/build); hard-safety aggregate no longer inherits the Lane B yield gate — safety and yield are independent verdicts. |

## Measured Lane B public-100 result (executed at `803b40c`)

The full public corpus (SHA-256 `cc8d8b27…` verified, 84 dev / 16 adversarial)
was executed through the complete pipeline: projection → authority →
closure → validation → normalization → authorization → compiler → solver →
independent verification → frozen snapshot → gold scoring.

| Terminal | Count |
|---|---:|
| `solved` | **6** |
| `verified_unsupported` (deferred) | 6 |
| `needs_figure` | 2 |
| `needs_confirmation` | 2 |
| `insufficient_information` | 1 |
| `compiler_failure` (underdetermined) | 67 |
| `compiler_unsupported` (typed precise codes) | 16 |
| Total | 100 |

- **Case-level scoring against the frozen distribution** (evaluator v3, scored
  strictly after the runtime snapshot is frozen): supported **6/81 correct, 0
  wrong, 75 unscored**; deferred **6/12**; unsupported-other **0/2**;
  needs_figure **2/2**; needs_confirmation **2/2**;
  insufficient_information **1/1**. Terminal mapping **0.17**; the six metrics
  all **0.074** (6 / 81).

  The denominator is the 81 supported cases the contract declares, not the six
  that happened to solve, so partial progress reads as partial. An earlier
  revision of this report said "6 scored, 6 correct, 0 unscored", which counted
  only what the engine produced and made a 7 %-complete lane read as complete.
- **Wrong solves: 0** — the hard requirement holds. Every solved value was
  converted to SI with `pint` and matched its gold reference inside the corpus's
  own declared tolerance.
- All 6 solved candidates passed all six verification checks
  (`equation_residual`, `nonnegative_time`, `query_binding`,
  `source_evidence`, `unit_consistency`, `constraint`), and each carries every
  kind its own graph and candidate obliged — now required by the scorer rather
  than assumed.
- The lane distribution is **byte-identical to the session base** `bc5e0be`.
  Evaluator v3 changed how the run is *judged*, not what the engine does, and the
  three scorer changes were each measured before and after to confirm no count
  moved. That is the intended result of contract-hardening work.

**Frozen target comparison.** The frozen Lane B target is
`81 solved / 12 verified deferred / 2 / 2 / 2 / 1, wrong 0`. The measured
result is `6 solved` — the target is **not met**, and this is the single
honest gap that keeps Stage 7 `NOT_ACCEPTED`. The target was not lowered,
reinterpreted, or re-scoped.

### Typed remaining walls (why 6, not 81)

Every non-solved executed case terminates with a typed compiler code, not a
silent failure:

| Typed code | Path | Count |
|---|---|---:|
| `underdetermined` | `equations` | 67 |
| `requires_specialized_model` | `geometry.*` | 12 |
| `requires_specialized_model` | `interactions.*` | 4 |
| `nonlinear_verification_deferred` | `equations` | 6 |
| `free_linear_vibration_readout_deferred` | `queries.*.target.role` | 3 |
| `translating_frame_relative_acceleration_deferred` | `queries.*.target.frame_id` | 3 |

The dominant wall (`underdetermined`, 67) is a real modelling gap: the
projected drafts do not yet carry enough typed structure for the compiler to
close the equation systems the corpus questions need. The profile-by-profile
route to closing it is recorded in
`docs/PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md` §6a, measured by the corrected
profile-isolated instrument (below).

## Profile-isolated feasibility (corrected instrument)

The superseded first-wins census overstated `rigid_fixed_axis`; the rewritten
instrument measures each implemented profile in an **independent
selected-profile run** per applicable context:

- `free_flight_gravity` — 8 applicable: 2 `compiler_no_equation`,
  6 `profile_plan_not_formable`. After the solver waiver this profile has a
  proven end-to-end verified-solve path (synthetic apex-time control), making
  it the **first qualifying profile** under the measured-yield rule.
- `impulse_momentum` — 4 applicable: 4 `profile_plan_not_formable`.
- `relative_translating_frame` — 9 applicable: 3 verified-deferred,
  6 `profile_plan_not_formable`.
- 10 unimplemented profiles — reported `profile_not_implemented` =
  **not measured**. No definitional zeros.

## Full strict gate result at the code candidate `803b40c`

```
cd backend
STAGE7_PUBLIC_CORPUS_PATH=/abs/external/dynatutor_beer12_ko_corpus_v1_public.zip \
OPENAI_API_KEY="" ANTHROPIC_API_KEY="" OPENAI_BASE_URL="" ANTHROPIC_BASE_URL="" \
MECHANICS_MODELER_BASE_URL="" MECHANICS_FIGURE_BASE_URL="" \
python tools/run_phase56_stage7_offline_gate.py \
  --require-public-corpus --require-full-stage7 --output /abs/external/report.json
```

`STAGE7_RUN_SCOPE=STRICT_PUBLIC_CORPUS_GATE`, **exit 2** — expected: Lane B has
not met the frozen distribution. `exact_head_sha` in the report is
`803b40c37389315a96d2819b4350cad2c00f892b`, the code candidate itself, so no
documentation head is stamped with the candidate's evidence.

- Report SHA-256: `be45b67ea163f0b376b94e880059b98fc612aaf5c705d644738bd82395742d46`
- Evaluator `phase56-stage7-evaluator-v3`; contract `phase56-stage7-evaluation-contract-v1`
- Archive SHA-256 matched; `public_dev` 84 / `public_adversarial` 16 / total 100
- External model calls **0**; private held-out accesses **0**; measured cost **$0**

39 strict gates, **11 failing** — every one of them Lane B yield, and nothing else:

| Strict gate | Result |
|---|---|
| corpus supplied / SHA / 84 / 16 / 100 | PASS |
| `strict_lane_b_executed` / `_100_executed` / `_scored` | PASS |
| **`strict_supported_81_solved`** | **FAIL — 6 correct of 81** |
| **`strict_deferred_12_verified_unsupported`** | **FAIL — 6 of 12** |
| **`strict_unsupported_other_2`** | **FAIL — 0 of 2** |
| `strict_needs_figure_2` | PASS |
| `strict_needs_confirmation_2` | PASS |
| `strict_insufficient_information_1` | PASS |
| **`strict_terminal_mapping_100_percent`** | **FAIL — 0.17** |
| **six metric gates** (answer, unit/dimension, query binding, direction/sign, candidate coverage, residual verification) | **FAIL — 0.074 each (6/81)** |
| **`strict_unscored_zero`** | **FAIL — 75** |
| `strict_wrong_solve_zero` | **PASS — 0** |
| `strict_solved_but_unscored_zero` | PASS — 0 |
| `strict_deferred_silent_solve_zero` | PASS — 0 |
| `strict_blocked_silent_solve_zero` | PASS — 0 |
| `strict_blocked_numeric_answer_zero` | PASS — 0 |
| `strict_lane_c_pass` / `strict_lane_d_pass` / `strict_lane_e_pass` | PASS |
| `strict_compositional_12_pass` / `strict_synthetic_38_pass` | PASS |
| `strict_metamorphic_pass` / `strict_physics_changing_controls_pass` | PASS |
| `strict_redaction_pass` | PASS |
| `strict_hard_safety_pass` | PASS |
| **`strict_hard_safety_all_signals_measured`** | **PASS — 23 of 23** |
| **`strict_hard_safety_unbound_zero`** | **PASS — 0** |
| **`strict_hard_safety_nonzero_zero`** | **PASS — 0** |

The last three gates are new in evaluator v3 and are the reason the hard-safety
section now means something: `per_signal_instrument_registry: IMPLEMENTED`,
`signal_count` 23, `measured_signal_count` 23, `unbound_signal_count` 0,
`nonzero_signal_count` 0. Previously the catalog reported `all_zero` while 17 of
its 23 signals had no instrument at all.

Lane C remains contract/integration evidence over the deterministic recorded
modeler only; **actual model quality is `NOT_RUN / N/A`** — no external model
call was made and measured cost is $0.

## Regression evidence

| Suite | Head | Result |
|---|---|---|
| Full backend regression (local) | `1954d14` | **4478 passed, 1 skipped, 0 failed** (43:05) |
| Stage 7 offline gate runner | `803b40c` | 50 passed |
| Hard-safety instrument attacks | `803b40c` | 15 passed |
| Gold isolation + Lane B runner | `803b40c` | 49 passed |
| Preflight + corpus integrity contracts | `803b40c` | 128 passed |

The full local regression is attributed to `1954d14` and **not** re-attributed to
the code candidate. `803b40c` changes exactly one test file, removing 71 tests by
collapsing parametrisation into loops and adding none; the entire backend is
re-executed at `803b40c` by CI below.

No test was deleted, no assertion weakened, no threshold relaxed, no shard budget
widened, no legacy fallback or case-specific patch introduced.

## Exact-head CI evidence for the code candidate `803b40c`

All six workflows executed at the exact candidate head on
`codex/phase56-generic-mechanics-engine`:

| Workflow | Event | Run | Result |
|---|---|---:|---|
| Phase 56 Stage 7 offline evaluation | push | `30271934503` | **SUCCESS** |
| Phase 56 Stage 7 offline evaluation | pull_request | `30271937974` | **SUCCESS** |
| Phase 56 Stage 6 multimodal | push | `30271936141` | **SUCCESS** |
| Phase 56 Stage 6 multimodal | pull_request | `30271937930` | **SUCCESS** |
| DynaTutor release tests | pull_request | `30271938042` | **SUCCESS** |
| Phase 55 textbook parser | pull_request | `30271937988` | **SUCCESS** (`live-openai-smoke` skipped — no Live call approved) |

Within `DynaTutor release tests`: `backend fast`, `backend slow`,
`backend quality`, `backend performance`, `frontend` and `release gate` all
SUCCESS.

This evidence belongs to `803b40c` and must not be re-attributed to the
documentation-only head that follows it.

### A shard-budget failure at the preceding candidate, and why it was not a test failure

The first evaluator-v3 candidate, `1954d14`, failed `backend fast` — with **zero
failing tests**. `scripts/check_backend_fast.sh` splits the suite into four
contiguous shards **by test count** and gives each a 420 s wall clock; the 89
tests the hard-safety attacks added moved every shard boundary, so shard 2
inherited more of the same-fixture parity suites than before and was terminated
at 78 % by `[run_with_timeout] timed out after 420s`.

The repair was to make the new tests cheap, never to widen the budget. Sixteen
parametrised correction attacks each built their own FastAPI application and
seeded their own revision to exercise one recursive guard; they are now two loops
inside two tests. Three denylist sweeps contributed 52 more cases to assert a
pure function over a frozenset; they are now loops. The four attacks that must
drive a real application through the real endpoint are marked `slow` — what the
marker exists for, and what parity suites of the same shape already do — so they
run under `backend slow`, while the strict gate still runs them by exact node ID
with `-o addopts=`, which clears the marker filter. All 37 registry-bound node
IDs still resolve, and the file went from 86 tests / 85 s to 15 tests / 20 s.

No threshold was raised, no budget widened, no assertion weakened and no attack
removed: every key, denylist entry and guard attacked before is still attacked.

## Read-only audit (same-model, not an independent Checker)

A same-model read-only audit covered all 10 commits of `d33c70b..b88a9ea`:
**blocking findings 0**. Spot-runs re-executed 50 + 188 + 237 + 23 tests with
no failure. Identity-routing grep over every added line found zero forbidden
tokens; the evidence-quote binding was confirmed to be exact literal span
matching, not regex routing; the verifier's both-empty provenance refusal was
confirmed by negative control.

Non-blocking observations recorded for a future session (deliberately **not**
patched here, to keep the CI-attributed code head exact):

1. The gate module docstring still says the gate "never contacts an external
   endpoint"; the opt-in strict Lane E step runs `npm install` for the pinned
   lint toolchain, so the wording needs a qualifier.
2. The answer-scoring tolerance floor `1e-6·max(1,|expected|)` can override a
   tighter corpus-declared tolerance; a `1e-9` floor would be safer for the
   wrong-solve signal.
3. `hard_safety.all_zero` does not consider the `unscored` bucket (currently
   0); gate it explicitly.
4. `_score_solved_outputs` is invoked outside the runtime `try/except`; a
   scorer crash aborts the gate instead of degrading to a typed FAIL.
5. The verifier accepts any non-empty assumption citation; it could be
   tightened to accept citations only for equations binding assumption-sourced
   quantities (trust is currently compiler-side, symmetric with the evidence
   path).
6. ~400 gate-runner lines (suite subprocess plumbing, Lane E steps) have no
   direct unit tests; `__import__("re")` style in the summary parser.

## Hard-safety and privacy status

| Signal | Status |
|---|---|
| Catalog signals | 23 |
| **Individually measured this run** | **23** |
| **Unbound (NOT_MEASURED)** | **0** |
| **Nonzero** | **0** |
| Per-signal instrument registry | `IMPLEMENTED` (`phase56-stage7-hard-safety-registry-v1`) |
| External model calls | 0 |
| Measured cost | $0 |
| Private held-out access | 0 |
| Textbook PDF access | 0 |
| Raw corpus committed | no (path-supplied archive only) |
| Gold leakage in runtime material | 0 (enforced by import guard **and** a syntax-aware source guard, both tested in each direction) |
| Case-ID / family / filename / raw-text routing | 0 (enforced and tested) |
| Wrong solves (gold-scored) | **0** |
| Actual model quality | `NOT_RUN / N/A` |

Six signals rest on scorer/runtime counters; the other seventeen on 37 exact
attack node IDs the gate runs each strict run. A signal whose instrument does not
run reports `NOT_MEASURED` and fails strict mode — it never inherits a zero.

## Next exact task — B1, an implementation package

The next session's first action is the **B1 cohesive implementation package**
(slot-pin `radial_transverse` frame), not another audit, census or diagnostic.
The measurement phase is complete: six independent read-only audits and the
evaluator v3 package are done, and the ranked plan is recorded in
`docs/PHASE56_CLAUDE_CODE_HANDOFF.md` with its evidence in
`docs/PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md` §6b-4 … §6b-7.

B1 creates exactly one `IRReferenceFrame` with `frame_type = radial_transverse`
and rebinds the query quantity's `frame_id` to it, inside a transaction following
the working `_DEFERRAL_ONLY_PROFILES` pattern. Every other conjunct of
`_slot_pin_relative_motion_issue` already holds 3/3; the frame is the only missing
one, and its identity is read from the corpus's own `moves_in_slot` relation.
Expected measured outcome: deferred **6/12 → 9/12**, supported unchanged, wrong
solves 0, `supported_downgraded_to_unsupported` 0.

Stated honestly: B1 raises the *deferred* class, not the supported count. The
first package that can raise **supported** is the co-required bundle B5+B6+B7,
because a frame alone unlocks zero laws (`frame_alone_unlocks = 0`, §6b-4).

Stage 8 must not start.

---

# Pause-checkpoint closure at `1b7dfe4`

This section closes the evidence the pause checkpoint left open. It reports
measurements taken at exactly `1b7dfe45608552a087bba4eb1e84085330431bdc`, on a
clean working tree, in a venv rebuilt for this session from
`backend/requirements-lock.txt` (`/home/user/.venv-stage7/bin/python`,
Python 3.11.15).

## Exact-head CI — 8 runs, 8 success, 0 non-success

Both the `push` and the `pull_request` event were checked for all four
workflows. Every run is attempt 1; there is no re-run and no empty commit.

| Workflow | Event | Run ID | Attempt | Head SHA | Status | Conclusion | Duration |
|---|---|---|---|---|---|---|---|
| Phase 55 textbook parser | push | `30746069488` | 1 | `1b7dfe4` | completed | success | 0m31s |
| Phase 56 Stage 6 multimodal | push | `30746069466` | 1 | `1b7dfe4` | completed | success | 9m31s |
| DynaTutor release tests | push | `30746069461` | 1 | `1b7dfe4` | completed | success | 10m59s |
| Phase 56 Stage 7 offline evaluation | push | `30746069493` | 1 | `1b7dfe4` | completed | success | 26m13s |
| Phase 55 textbook parser | pull_request | `30746070902` | 1 | `1b7dfe4` | completed | success | 2m12s |
| Phase 56 Stage 6 multimodal | pull_request | `30746070909` | 1 | `1b7dfe4` | completed | success | 10m22s |
| DynaTutor release tests | pull_request | `30746070894` | 1 | `1b7dfe4` | completed | success | 15m20s |
| Phase 56 Stage 7 offline evaluation | pull_request | `30746070911` | 1 | `1b7dfe4` | completed | success | 25m34s |

## The uploaded Stage 7 artifact, audited from outside the run

```
STAGE7_ARTIFACT_RUN_ID=30746069493
STAGE7_ARTIFACT_RUN_ATTEMPT=1
STAGE7_ARTIFACT_RUN_HEAD_SHA=1b7dfe45608552a087bba4eb1e84085330431bdc
STAGE7_ARTIFACT_CHECKOUT_SHA=1b7dfe45608552a087bba4eb1e84085330431bdc
STAGE7_ARTIFACT_REPORT_SHA=1b7dfe45608552a087bba4eb1e84085330431bdc
STAGE7_ARTIFACT_REPORT_RAW_SHA256=c4d783205f1e1becf9fad0a84544e25d1c473ddd1607c2cba6904f6d3d002791
STAGE7_ARTIFACT_ID=8833183975
STAGE7_ARTIFACT_ZIP_SHA256=160c0d85eff2bb22698acdd7fed155fb603ad16d52aa7ac8f4539522fb6fd3c8
STAGE7_ARTIFACT_IDENTITY_MATCH=true
```

Run head, checkout head and the report's own `exact_head_sha` are the same
commit, and the raw-byte seal agrees across three independent sources:

1. the run's own pre-upload checker (`STAGE7_CI_ARTIFACT_IDENTITY=PASS`), with
   the upload conditioned on it;
2. the report bytes republished in the run log, which decode to JSON carrying
   `"exact_head_sha": "1b7dfe45…"`, `public_corpus` and `lane_b` `NOT_RUN`,
   `external_model_calls` 0 and `private_heldout_accesses` 0;
3. **an independent regeneration at this head, outside CI, which came out
   byte-identical** — same SHA-256 `c4d78320…`, 9241 bytes. Re-running
   `check_stage7_ci_artifact_identity.py` over the regenerated file returns
   `STAGE7_ARTIFACT_IDENTITY_MATCH=true`.

The uploader's own digest `160c0d85…` equals the digest the Artifacts API
reports for artifact `8833183975`, binding the stored blob to those bytes.

**Stated exactly:** the artifact ZIP was *not* re-downloaded. This
environment's egress policy denies `productionresultssa10.blob.core.windows.net`
at CONNECT with 403, recorded by the proxy as a policy denial; per the proxy
contract a policy denial is reported, not routed around. Confirmation (3) is
what replaces the download, and it is the stronger evidence: a download proves
what was stored, a reproduction proves what the source produces.

## Clean-tree read-only checker

`run_phase56_stage7_b28a_readonly_checker.py` on a clean tree at `1b7dfe4`:
**24 checks, 0 blocking findings, 0 non-blocking findings, `ACCEPTANCE=PASS`.**
The non-blocking note recorded against the previous dirty-tree run does not
reappear on a clean tree.

## B29 and B32 at this head

Both engine implementations are confirmed present and green, and neither is
declared accepted.

| | B29 horizontal contact | B32 spring natural length |
|---|---|---|
| Typed source reader | `horizontal_driven_contact.py` | `spring_natural_length.py` |
| `ProfileId` member | `horizontal_contact` | `spring_energy_natural_length` |
| Registered transaction | `_horizontal_driven_contact_transaction` | `_spring_natural_length_energy_transaction` |
| Value-free | no numeric force, acceleration, speed or natural length is invented | same |
| Focused + walls + application regression | **122 passed** (joint run at this head) | same run |
| Disposition | `ENGINE_IMPLEMENTATION_CONFIRMED`, `GOLD_SCORED_ACCEPTANCE_BLOCKED_ON_EXACT_MANIFEST` | same |

Measured, not assumed: at this head **the B29 and B32 corpus cohorts are still
not solved on the raw v1 public archive** — the three `horizontal_friction_force`
and three `spring_energy` contexts that remain unsolved all reach
`compiler_failure / underdetermined`. Their closure evidence is an augmented
campaign, and the augmented half of that campaign is a function of the
unavailable exact manifest.

## Official v1 strict, re-measured at this head

Re-run against the approved public archive
(SHA-256 `cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef`),
runtime first and gold afterwards, through the canonical scorer:

| Metric | Measured at `1b7dfe4` | Frozen v1 |
|---|---:|---:|
| supported correct | **41 / 81** | 41 / 81 |
| supported wrong | **0** | 0 |
| solved-but-unscored | **0** | 0 |
| supported downgraded | **0** | 0 |
| deferred | **12 / 12** | 12 / 12 |
| terminal mapping | **58 / 100** | 58 / 100 |
| blocked numeric answers | **0** | 0 |
| blocked silent solves | **0** | 0 |
| deferred silent solves | **0** | 0 |
| query binding | **41** | 41 |

Terminal distribution: 41 `solved`, 34 `compiler_failure`, 12
`verified_unsupported`, 8 `compiler_unsupported`, 2 `needs_figure`, 2
`needs_confirmation`, 1 `insufficient_information` — the last three being the
three the frozen record groups as `projection_refused`.

```
OFFICIAL_V1_SUPPORTED_CORRECT = 41/81
```

This is the only official score. The historical experimental
`+9` was measured at `e511b63` against an augmented archive and is **not**
re-measured here and never added to it.

## Historical exact manifest — recovery audit

| Field | Value |
|---|---|
| canonical digest | `c72229789cd417c70eb2533212508b259a9f8df903415f1f6aac710464929328` |
| raw file SHA-256 | `95aca08407e9508364468fe7be3a373ad0fe6d3e028bb5d0aa79052717542579` |

Searched: this session's attachments, every mounted filesystem
(`/root`, `/home`, `/tmp`, `/var/tmp`, `/opt`, `/srv`, `/mnt`, `/media`,
`/data`), `/root/stage7_external/`, `work/`, the whole git history for any path
that ever carried such a manifest, this PR's comment history, and the Actions
artifacts of the checkpoint runs. **37 228 files were hashed and compared
against the raw file SHA-256 by content, not by name.**

```
HISTORICAL_EXACT_MANIFEST_AVAILABLE = false
EXACT_HISTORICAL_MANIFEST_UNAVAILABLE
```

`/root/stage7_external/` and `work/` do not exist in this container; the only
supplied artifact is the approved public corpus archive itself, whose SHA-256
is `cc8d8b27…` and whose internal `manifest.json`
(SHA-256 `9d1555dc07dbcb8f4ab22d2563031a9f8c20ca862e02c509f5c52f2b3abd4241`) is
**not** the exact augmentation manifest and was not used as one. No manifest
was reconstructed, guessed, approximated or synthesised, and no threshold,
tolerance, population or seal was relaxed to work around its absence.
