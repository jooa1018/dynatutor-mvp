# Goal — Phase 57 reproducible public evaluation

## Goal and definition of done

- Goal: Continue DynaTutor development without rewriting the irrecoverable Phase 56 historical evidence by establishing a distinct, repository-reproducible public evaluation lineage and then improving genuine typed mechanics coverage on its fixed public population.
- Baseline done: an exact-head hosted M -> V -> R -> G run reproduces the separately sealed 100-context population, passes the 50-correct zero-defect regression floor, uploads only the verified aggregate pair, and leaves Phase 56 Stage 7 `NOT_ACCEPTED` and Stage 8 `NOT_STARTED`.
- Quality done: the same frozen public population reaches 81/81 supported correct with zero wrong, unscored, forbidden, regressed, or query-binding-mismatch outcomes through general source-authorized mechanics work rather than case/gold authority.
- This goal never claims hidden-set generalization, universal dynamics coverage, production deployment, release, or historical Phase 56 acceptance.

## Terrain map — v1 — 2026-08-26

| Question | Label | Current answer / lead |
|---|---|---|
| What is the immutable source baseline? | `confirmed` | Phase 56 terminal head `63a6e35614f9aa4dc3dbf8238e70f3b0a748fd17`; tree `8192e523197a193a3244e6aba93de89dd2d24ebf` |
| What happens to historical Stage 7? | `confirmed by D-003` | It remains `STAGE_7_IN_PROGRESS / NOT_ACCEPTED`; missing-manifest replay remains historical-only Q-003 |
| Does this authorize Stage 8? | `confirmed no` | No. Phase 56 Stage 8 remains `STAGE_8_NOT_STARTED` |
| What input is reproducible? | `locally verified` | Three explicitly public corpus files, 100 contexts total, deterministic ZIP SHA `e523fc39…`, source-only manifest digest `32aa3ce5…`, distinct Phase 57 seal |
| Is gold isolated? | `locally verified by inherited contracts` | M/V/R run without gold; G opens public gold only after the runtime snapshot is frozen; aggregate-only CI artifact |
| What protects current behavior? | `implemented and locally contract-verified` | 50 correct, 6 newly solved correct, 97/3 state split, every measured defect maximum zero |
| What is the improvement target? | `open` | 81/81 supported public contexts correct with all zero-defect invariants maintained; Q-006 |
| What evidence is still missing? | `named-unfilled` | Exact-head hosted Python 3.11/locked-dependency full M/V/R/G PASS and uploaded aggregate identity |

## Work tree

### 1. Historical boundary — conclusion: Phase 56 evidence is preserved, not laundered

| Leaf | Status | Evidence |
|---|---|---|
| 1.1 Archive the Phase 56 terminal checkpoint byte-for-byte | filled | `memory/checkpoints/2026-08-26T2104+0900-phase56-terminal-blocker.md`; raw SHA `372a28cadec12dea83e9d4c1c3420f17098bf54db68c0d5120d6ae94ed5bba71` |
| 1.2 Record the user's separate-lineage decision | filled | D-003 |
| 1.3 Keep Stage 7 unaccepted and Stage 8 not started in every Phase 57 contract/report | filled locally | contract/report/status models and tests |

### 2. Reproducible public input — conclusion: every runtime input byte is derivable from reviewed source

| Leaf | Status | Evidence |
|---|---|---|
| 2.1 Commit only explicitly public members, excluding private/full archive material | filled | public fixture directory and raw-corpus exclusion test |
| 2.2 Bind every member count/hash and canonical sanitized manifest | filled | `fixtures.py`; tamper/member/symlink tests |
| 2.3 Reconstruct a deterministic archive with a frozen SHA | filled | archive builder and exact hash test |
| 2.4 Rebuild the source-only nine-entry continuation manifest | filled | manifest and selection digest tests |

### 3. Evaluation and artifact integrity — conclusion: a green run means reproducibility/regression only

| Leaf | Status | Evidence |
|---|---|---|
| 3.1 Run inherited M/V/R/G as separate processes under the distinct seal | implemented; hosted proof pending | Phase 57 wrapper and workflow |
| 3.2 Separate CI-blocking regression from 81/81 quality | filled locally | gate models and disposition tests |
| 3.3 Prove exact head, raw bytes, content digest, privacy keys, and runner/report coherence before upload | filled locally | artifact checker and tamper test |
| 3.4 Upload only aggregate report/status | implemented; hosted proof pending | workflow path allowlist |

### 4. Quality progression — conclusion: improve public support through general mechanics only

| Leaf | Status | Evidence / next lead |
|---|---|---|
| 4.1 Seal exact hosted baseline at 50/81 or better | named-unfilled | run Phase 57 workflow at feature-branch exact head |
| 4.2 Produce an authority-only blocker census for the remaining supported public contexts | named-unfilled | aggregate-safe local analysis after baseline; no case/gold runtime authority |
| 4.3 Implement highest-leverage general typed capability | named-unfilled | chosen from census, with focused/adversarial tests |
| 4.4 Re-run fixed population and raise floor only after exact evidence | named-unfilled | same seal, unchanged population/scorer/zero-defect gates |
| 4.5 Reach 81/81 public supported correct | named-unfilled | Q-006; still not hidden-generalization evidence |

## Current next leaf

Publish the atomic Phase 57 implementation from base `63a6e35`, open a Draft PR against `codex/phase56-generic-mechanics-engine`, and obtain exact-head hosted M/V/R/G aggregate evidence. If it fails, repair the general determinism/runtime defect without weakening the population, scorer, seal, thresholds, or zero-defect controls.

## Known limits

- Local full replay is not accepted evidence because the available local environment lacks locked Pint and differs from the hosted Python 3.11 environment.
- Public benchmark quality can be improved through development against public cases and therefore cannot prove hidden generalization.
- Q-003 remains open only for a possible future historical replay; it does not block Phase 57 development.
- No production mutation, merge, or release is authorized by this goal.
