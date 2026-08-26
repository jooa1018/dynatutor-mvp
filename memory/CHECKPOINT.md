# Checkpoint — Phase 57 reproducible public evaluation — 2026-08-26 21:04 Asia/Seoul

## Active state

- User-confirmed direction: preserve the irrecoverable Phase 56 historical result and continue through a distinct reproducible evaluation lineage; see D-003.
- Source baseline: Phase 56 terminal head `63a6e35614f9aa4dc3dbf8238e70f3b0a748fd17`, tree `8192e523197a193a3244e6aba93de89dd2d24ebf`.
- Target branch: `codex/phase57-reproducible-public-evaluation`, based directly on that head.
- Archived Phase 56 terminal checkpoint raw SHA-256: `372a28cadec12dea83e9d4c1c3420f17098bf54db68c0d5120d6ae94ed5bba71`.
- Phase 57 status: **`REPRODUCIBLE_PUBLIC_BASELINE_IN_PROGRESS`**.
- Phase 56 Stage 7 remains **`STAGE_7_IN_PROGRESS / NOT_ACCEPTED`**.
- Phase 56 Stage 8 remains **`STAGE_8_NOT_STARTED`**.
- `main` remains outside this line and must not be changed.

## What is implemented locally

- Minimum repository-contained public fixture set: 84 public development + 16 public adversarial cases, schema, and sanitized hash/count manifest; private/full/quarantined corpus members are absent.
- Deterministic archive reconstruction SHA-256: `e523fc39a3f44fd50542e622924c3154f76fa25362aaf5180884954892b3f958`.
- Source-only nine-entry continuation manifest canonical/raw identities: `32aa3ce51e3006e533913b2f822251d22dccba2a379a35008f19e7a7e1aef7cd` / `946cd6364669c123341d54999a87a468bc22f7260ea2b8500ddee267878bcd3a`.
- Distinct seal: `phase57-reproducible-public-continuation-v1`.
- Regression floor: 100 accounted, 97 runtime-completed, 3 projection-refused, at least 50 correct, at least 6 newly correct, and every wrong/unscored/forbidden/regressed/query-mismatch count zero.
- Separate public quality target: 81/81 supported correct. Regression green does not imply quality completion.
- Exact-head runner, aggregate report/status models, pre-upload artifact checker, and hosted workflow are implemented.
- Focused Phase 57 tests: 17 passed. Compilation, workflow YAML parsing, and `git diff --check` passed.

## Evidence not yet earned

- The complete exact-head hosted Python 3.11 / locked-dependency M -> V -> R -> G baseline has not yet passed or uploaded an aggregate.
- A local full replay is not acceptance evidence: the available Python 3.13 environment lacks locked Pint and Phase R refused an unaugmented rung movement. No gate was weakened.
- Phase 57 quality remains unmeasured at the new exact head until hosted replay succeeds.
- No hidden generalization, universal dynamics coverage, production deployment, release, merge, or Stage 8 work is claimed.

## Exact next action

1. Review `git diff` and `git status` for the Phase 57-only file set.
2. Create one atomic commit from parent `63a6e35614f9aa4dc3dbf8238e70f3b0a748fd17` and base tree `8192e523197a193a3244e6aba93de89dd2d24ebf` on `codex/phase57-reproducible-public-evaluation`.
3. Open a Draft PR against `codex/phase56-generic-mechanics-engine`; do not merge it.
4. Run the exact-head Phase 57 workflow and existing release checks.
5. If the M/V/R/G workflow fails, inspect the exact failing invariant and repair the general deterministic path without changing the fixture population, seal, scorer, zero-defect thresholds, or historical statuses.
6. If it passes, download and independently verify the aggregate bytes, then update this checkpoint and the PR with exact run/artifact identities before beginning the 50 -> 81 quality progression.

## Prohibited shortcuts

Do not reconstruct or substitute the Phase 56 historical manifest. Do not claim historical Stage 7 acceptance or start Stage 8. Do not route or solve by case ID, family label, array order, expected answer, gold, or scoring handle. Do not upload per-case runtime/gold artifacts from the Phase 57 workflow. Do not weaken the 50-correct floor or any zero-defect gate to make CI green. Do not merge `main`, deploy production, or publish a release.

## Recovery sources

Read in this order: `memory/00-INDEX.md`, `memory/DECISIONS.md`, this checkpoint, `memory/PRODUCT-TRUTH.md`, `docs/PHASE57_REPRODUCIBLE_PUBLIC_EVALUATION.md`, `memory/goal/phase57-reproducible-public-evaluation.md`, `memory/knowledge/phase57-reproducible-public-evaluation.md`, and the current Phase 57 Draft PR. For historical Phase 56 state, read the archived checkpoint and `memory/knowledge/phase56-terminal-blocker.md`.
