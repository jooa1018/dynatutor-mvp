# Phase 57 reproducible public evaluation — verified local finding

Verified: 2026-08-26

## Finding

- Label: `verified local contract and fixture implementation; hosted full replay pending`.
- Claim: A distinct Phase 57 public evaluation lineage can be constructed without reconstructing or substituting the unavailable Phase 56 historical manifest. The implementation deterministically derives its inputs from three reviewed public corpus files, preserves M/V/R/G gold isolation, enforces a 50-correct zero-defect regression floor separately from an 81/81 public quality target, and publishes only an exact-head privacy-minimal aggregate pair.
- Historical boundary: Phase 56 Stage 7 remains `STAGE_7_IN_PROGRESS / NOT_ACCEPTED`; Phase 56 Stage 8 remains `STAGE_8_NOT_STARTED`.

## Evidence

- Source baseline: exact Phase 56 terminal head `63a6e35614f9aa4dc3dbf8238e70f3b0a748fd17`, tree `8192e523197a193a3244e6aba93de89dd2d24ebf`.
- The outgoing Phase 56 terminal checkpoint was archived byte-for-byte with raw SHA-256 `372a28cadec12dea83e9d4c1c3420f17098bf54db68c0d5120d6ae94ed5bba71`.
- Public fixture population: 84 development plus 16 adversarial cases; exactly 81 have the frozen scope-adjusted supported terminal.
- Fixture-set digest: `f3d143fb692711da840ec8aa0b35934d115ef40f2418053eda252892aa4cbeb0`.
- Deterministic reconstructed archive SHA-256: `e523fc39a3f44fd50542e622924c3154f76fa25362aaf5180884954892b3f958`.
- Source-only manifest canonical/raw identities: `32aa3ce51e3006e533913b2f822251d22dccba2a379a35008f19e7a7e1aef7cd` / `946cd6364669c123341d54999a87a468bc22f7260ea2b8500ddee267878bcd3a`.
- Distinct campaign seal: `phase57-reproducible-public-continuation-v1`, with 100 expected, 97 runtime-completed, and 3 projection-refused handles pinned by exact population digests.
- Focused local suite: 17/17 passed. It covers exact member/hash/count identity, deterministic archive, source-only manifest, 100/81 population counts, existing builder integration, separate seal, historical status preservation, dual dispositions, wrong-result failure, duplicate-ledger rejection, byte/member/symlink/canonicalization tampering, aggregate privacy, production-image exclusion, and artifact raw-byte tampering.
- Python compilation, workflow YAML parsing, and `git diff --check` passed at the implementation worktree.

## Refutation attempts

1. Reusing or relabeling the missing historical manifest was rejected; Phase 57 uses a new campaign ID, archive identity, handle set, seal, report version, and explicit non-substitution flags.
2. Committing the original public ZIP was rejected in favor of the minimum three public members and deterministic reconstruction; private/full/quarantined corpus members remain absent.
3. Treating CI green as quality completion was rejected; regression PASS and 81/81 quality status are separate model fields with consistency validators and tests.
4. Uploading runtime or scored per-case artifacts was rejected; the workflow allowlists only the aggregate report and runner status, and a pre-upload checker recursively rejects problem/gold/answer/case/handle keys.
5. The available local full replay was attempted. It reached the runtime phase but refused an unaugmented rung movement under Python 3.13 without the locked Pint dependency. That result was not relabeled PASS and no threshold or invariant was weakened. Exact-head hosted Python 3.11 with locked dependencies remains required.

## Sample

- Three public input files, 100 public contexts, one source-only nine-entry continuation manifest, one distinct population seal.
- Seventeen focused contract/tamper tests.
- One complete local M/V/R/G attempt retained only as an environment-limited diagnostic, not acceptance evidence.

## Limits

- The full hosted exact-head campaign and uploaded aggregate have not yet passed at this finding's timestamp.
- The fixtures are public development/regression data and include public gold. Improvement against them is not hidden-set generalization evidence.
- The 50-correct floor protects a previous separate public measurement; it does not declare 50/81 sufficient product quality.
- No production deployment, release, merge, live provider call, private held-out text access, or Phase 56 Stage 8 work is claimed.
