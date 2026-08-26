# Phase 57 — Reproducible Public Evaluation Lineage

Status: **implementation in progress; local contract tests pass; exact-head hosted M/V/R/G replay pending**

Started: 2026-08-26

Source baseline: `63a6e35614f9aa4dc3dbf8238e70f3b0a748fd17`

## 1. Why Phase 57 exists

Phase 56 Stage 7 is historically `STAGE_7_IN_PROGRESS / NOT_ACCEPTED`. Its
original augmentation manifest is unavailable, and the frozen Phase 56 contract
forbids reconstructing or substituting that artifact. That historical result is
preserved rather than rewritten.

Phase 57 is a **new evaluation lineage**. It asks a different, reproducible
question: can the current deterministic engine retain and improve its behavior
on an explicitly public, repository-contained 100-context population without
wrong answers, unscored solves, forbidden solves, regressions, query-binding
mismatches, hidden runtime authority, private held-out access, or external model
calls?

A Phase 57 PASS does not:

- accept or supersede historical Phase 56 Stage 7;
- authorize or start Phase 56 Stage 8;
- prove hidden-set or real-world Korean generalization;
- prove universal dynamics coverage;
- deploy production or publish a release.

## 2. Public input and provenance boundary

The repository contains only the three explicitly public corpus members needed
for the new campaign, plus a README and a count/hash-only manifest:

```text
backend/tests/fixtures/phase56_stage7_public/
  public_dev.jsonl             84 public cases
  public_adversarial.jsonl     16 public cases
  schema.json
  sanitized_manifest.json
  README.md
```

The source ZIP, `public_all.jsonl`, the private held-out manifest, and all private
held-out cases are excluded. The public JSONL files intentionally contain public
problem text, public case identifiers, and public gold. The inherited isolated
pipeline prevents gold from reaching preparation or runtime: Phase M prepares a
runtime input without gold, Phase V independently rebuilds and verifies it,
Phase R executes and freezes runtime records, and only Phase G opens public gold
after the runtime snapshot is closed and hashed.

Production packaging remains separate: the backend Dockerfile does not copy the
evaluation package, tests, or fixture directory.

## 3. Frozen input identities

| Identity | SHA-256 / value |
|---|---|
| source approved public archive | `cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef` |
| sanitized fixture-set digest | `f3d143fb692711da840ec8aa0b35934d115ef40f2418053eda252892aa4cbeb0` |
| deterministically reconstructed public ZIP | `e523fc39a3f44fd50542e622924c3154f76fa25362aaf5180884954892b3f958` |
| continuation manifest canonical digest | `32aa3ce51e3006e533913b2f822251d22dccba2a379a35008f19e7a7e1aef7cd` |
| continuation manifest raw-file SHA-256 | `946cd6364669c123341d54999a87a468bc22f7260ea2b8500ddee267878bcd3a` |
| source-only selection digest | `dcabc7f3a64ad448093d4d854e501da12d515c2876923bb8a456fccc192c4231` |
| campaign seal | `phase57-reproducible-public-continuation-v1` |

The ZIP uses three lexically ordered `ZIP_STORED` members, fixed 1980 timestamps,
fixed Unix regular-file metadata, no comments, and no extra fields. Any byte,
count, member-set, symlink, directory, schema, manifest spelling, or digest
change is refused before runtime.

The continuation manifest is built from source-visible structural evidence only.
It contains nine entries and no answer-derived selection authority.

## 4. Two independent dispositions

Phase 57 deliberately separates a **regression gate** from a **quality target**.

### 4.1 CI-blocking reproducibility and regression gate

The exact 100-context population must produce:

- 100 expected and accounted contexts;
- 97 runtime-completed and 3 projection-refused contexts;
- at least 50 all-shadow correct;
- at least 6 newly solved correct;
- zero all-shadow wrong;
- zero all-shadow unscored;
- zero newly solved wrong or unscored;
- zero forbidden-class solves;
- zero regressions;
- zero query-binding mismatches;
- an internally accepted inherited scorecard under the distinct Phase 57 seal.

This floor protects the separately measured 50-correct, zero-defect baseline. It
may be raised after new exact-head evidence, but may not be weakened merely to
make CI green.

### 4.2 Non-CI-blocking public quality target

The public population contains exactly 81 contexts whose frozen scope-adjusted
terminal is supported. Phase 57 quality remains `IN_PROGRESS` until all 81 are
correct while every zero-defect constraint remains satisfied. Reaching 81/81 is
public benchmark completion only; it is not hidden-generalization evidence.

A green workflow at 50/81 therefore means:

```text
regression_acceptance = PASS
quality_status        = IN_PROGRESS
```

It does not mean Phase 57 quality is complete.

## 5. Implementation

### New Phase 57 code

- `backend/evaluation/phase57_reproducible/contracts.py` — immutable identities,
  historical boundaries, regression floor, and 81/81 quality target.
- `backend/evaluation/phase57_reproducible/fixtures.py` — exact fixture
  validation, deterministic ZIP construction, source-only manifest generation,
  and out-of-tree materialization.
- `backend/evaluation/phase57_reproducible/gate.py` — strict aggregate model,
  duplicate-state refusal, independently computed regression/quality
  dispositions, and privacy-minimal serialization.
- `backend/tools/run_phase57_reproducible_public_gate.py` — exact-head wrapper
  around separate-process M/V/R/G execution, credential blanking, timeout
  process-group cleanup, and aggregate publication.
- `backend/tools/check_phase57_ci_artifact_identity.py` — exact raw-byte and
  content-digest verification, duplicate JSON-key rejection, recursive forbidden
  key scan, exact-head binding, independent floor recomputation, and
  runner/report coherence checks.
- `.github/workflows/phase57-reproducible-public-evaluation.yml` — locked Python
  3.11 environment, exact checkout, focused inherited regressions, complete
  M/V/R/G execution, source-mutation proof, pre-upload identity verification,
  and aggregate-only artifact upload.

### Narrow inherited extensions

The existing Phase 56 M/V/G entrypoints now accept an optional exact public
archive SHA-256. Omitting it preserves the historical Phase 56 call shape and
frozen public archive identity. The separate Phase 57 wrapper is the only caller
that supplies the new archive identity and campaign seal.

## 6. Artifact boundary

CI uploads only:

```text
phase57-gate-report.json
phase57-runner-status.json
```

The artifact checker rejects per-case/gold/private fields, including problem
text, case IDs, answers, gold values, and scoring handles. Inputs, preparation
artifacts, full runtime snapshots, redacted per-case views, shadow reports, and
scorecards remain runner-temporary and are not uploaded by this workflow.

The aggregate explicitly records:

- the exact code head;
- source report raw SHA and content digest;
- fixture/archive/manifest identities;
- aggregate counts and two dispositions;
- zero external model calls and zero private held-out text accesses;
- unchanged Phase 56 Stage 7 and Stage 8 statuses;
- false historical-substitution, hidden-generalization, production-release, and
  historical-acceptance claims.

## 7. Verification status at initial implementation

Locally verified on 2026-08-26:

- Phase 57 focused contract suite: **17 passed**;
- exact fixture member set, byte counts, hashes, 100-case population, and
  deterministic archive identity;
- exactly 81 supported contexts under the frozen scope-adjusted terminal;
- source-only nine-entry continuation manifest identity;
- existing prepare builder with the alternate exact archive identity;
- distinct campaign seal and 97/3 prepared-state split;
- regression PASS at 50 correct while quality remains `IN_PROGRESS`;
- quality acceptance only at 81 correct;
- tamper, extra member, directory, symlink, noncanonical manifest, duplicate
  ledger state, wrong answer, and artifact-byte attacks fail closed;
- aggregate privacy boundary and production-image exclusion;
- Python compilation, workflow YAML parsing, and `git diff --check`.

The complete local M/V/R/G replay was **not accepted as evidence**. The available
local interpreter was Python 3.13 without the locked Pint dependency, and the
runtime phase refused an unaugmented rung movement. The hosted workflow installs
the repository's locked Python 3.11 dependencies and is the required exact-head
baseline evidence. No gate was weakened to accommodate the local environment.

## 8. Rollback

The implementation is isolated on
`codex/phase57-reproducible-public-evaluation`, based on the immutable Phase 56
terminal head. Rollback is a normal revert of the Phase 57 commit or deletion of
the unmerged feature branch/PR. Phase 56 evidence, PR #17, and `main` are not
rewritten.

## 9. Next work after baseline verification

Once the exact-head hosted M/V/R/G aggregate passes and its bytes are recorded,
improvements proceed against the same sealed public population. Each change must
be general typed mechanics/modeling work, must pass the zero-defect regression
floor, and must not route by public case identity, family label, array order,
expected answer, gold, or scoring handle.
