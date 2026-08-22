# Goal — Phase 56 completion

## Goal and definition of done

- Goal: Recover DynaTutor from the authoritative Phase 56 branch and close the contracted product work without weakening physics, evaluation, provenance, privacy, or acceptance rules.
- Done: Every required current Stage 7 gate is reproducibly satisfied, Stage 8 is then completed if authorized by its specification, whole-product contracted gates are verified, and PR/checkpoint/truth evidence supports COMPLETE; otherwise only a genuinely external blocker remains after three legitimate routes and all independent work are exhausted.

## Terrain map — v1 — 2026-08-23

| Question | Label | Current answer / lead |
|---|---|---|
| Which repository state is authoritative? | `confirmed (self-gated)` | `codex/phase56-generic-mechanics-engine` at `166d40c3a2368a4a514e93d7766196efdb6a9d8d`, matching upstream and PR #17 after fetch/push; [authority snapshot](../knowledge/phase56-authority-snapshot.md) |
| Is current Stage 7 accepted? | `confirmed by current contract` | No: `STAGE_7_IN_PROGRESS / NOT_ACCEPTED`; [progress report](../../docs/PHASE56_STAGE7_PROGRESS_REPORT.md) and [PR #17](https://github.com/jooa1018/dynatutor-mvp/pull/17) |
| May Stage 8 start now? | `confirmed by current contract` | No: `STAGE_8_NOT_STARTED` and stage-order rule; its specification search is deferred until Stage 7 acceptance |
| Can the historical exact augmentation manifest be recovered or substituted? | `confirmed constraint` | It is unavailable and must not be reconstructed, guessed, synthesized, or replaced; [progress report](../../docs/PHASE56_STAGE7_PROGRESS_REPORT.md) |
| What legitimate measurement path remains? | `confirmed direction, outcome unknown` | The separately identified supplemental campaign with its own identity, source-only discovery, manifest/seal, baseline, gold isolation, canonical scoring, final measurement, and reproducible evidence; [candidate contract](../../docs/PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md) |
| Does the current environment hold every non-historical input needed to run that path? | `observed` | The approved official-v1 public archive is available and matches the frozen SHA-256; the distinct supplemental manifest/runtime bundle is not yet built |
| Which current-head implementation or contract defects remain after `166d40c`? | `observed` | 40 supported official-v1 cases remain terminal-not-solved; partial strict CLI flags can produce a false run-scope note; supplemental manifest remains unlocked |
| What important thing is not yet mapped? | `unknown` | Stage 8 specification location, production/runtime availability, and exact whole-product operational evidence remain gated terrain |

## Mobilization table

| Branch | What it needs | What is held | Gap → first move |
|---|---|---|---|
| Authority and recovery | Exact refs, PR disposition, contracts, durable state | [index](../00-INDEX.md), [D-002](../DECISIONS.md), [rules](../../.claude/ballast.rules.json), [authority snapshot](../knowledge/phase56-authority-snapshot.md) | Executable Stage 7 state → inspect entrypoints/checkers and run a corpus-independent baseline |
| Stage 7 acceptance | Current acceptance matrix, inputs, engine/evaluator gaps, official-v1 and artifact proof | [progress](../../docs/PHASE56_STAGE7_PROGRESS_REPORT.md), [candidate contract](../../docs/PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md), [release gates](../../RELEASE_GATES.md) | Current-head remeasurement and exact blocker tree → audit tools/tests/config, then execute smallest authoritative baseline |
| Stage 8 | Genuine Stage 7 acceptance plus authoritative Stage 8 specification | stage-order rule and current `NOT_STARTED` disposition | Specification intentionally gated → search/read only after Stage 7 acceptance |
| Whole-product hardening | Architecture-to-runtime trace, frontend/browser/API/deployment/security/performance evidence | [target architecture](../../01_TARGET_ARCHITECTURE.md), phase documents, [release gates](../../RELEASE_GATES.md) | Current operational evidence unknown → defer broad audit until Phase 56 stage gates stabilize |
| Evidence and handoff | Labeled claims, reproducible commands, atomic history, PR truth, product truth, rehearsal | ballast verify/proof/checkpoint/rehearsal skills, [PRODUCT-TRUTH](../PRODUCT-TRUTH.md), PR #17 | CI/artifact/runtime evidence incomplete → record every accepted package and checkpoint at each large boundary |

## Skeleton — cut v1

Every leaf is one question. `filled` means its source is attached; `named-unfilled` is work, not absence.

### 1. Authority and control plane — conclusion: work proceeds from a recoverable, non-divergent, contract-bound head

Source: [authority snapshot](../knowledge/phase56-authority-snapshot.md), [D-002](../DECISIONS.md), [index](../00-INDEX.md).

| Leaf | Status | Source / lead | Sub-foundations exposed |
|---|---|---|---|
| 1.1 Do local HEAD, upstream, and PR head identify the same commit? | filled | [authority snapshot](../knowledge/phase56-authority-snapshot.md) | exact refs and mutable-remote freshness — atomic |
| 1.2 Is the bootstrap isolated from product code and committed? | filled | commit `fee7003`; `git show --stat fee7003` | author identity and bootstrap scope — atomic |
| 1.3 Are autonomous authority and one-way-door limits recorded? | filled | [D-002](../DECISIONS.md) | reversible execution vs external one-way actions — atomic |

### 2. Stage 7 — conclusion: current contract is either accepted on reproducible evidence or retains an exact blocker

Source: [progress report](../../docs/PHASE56_STAGE7_PROGRESS_REPORT.md), [candidate contract](../../docs/PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md), [release gates](../../RELEASE_GATES.md).

| Leaf | Status | Source / lead |
|---|---|---|
| 2.1 What exact current-head commands and artifacts define the Stage 7 baseline? | filled | evaluation contract, test matrix, workflows, tool entrypoints, and [verified baseline](../knowledge/phase56-authority-snapshot.md) |
| 2.2 Does exact-head/artifact provenance remain fail-closed at the current head? | filled for `166d40c`; remeasure after change | artifact identity PASS and B28A 24/24 clean at exact head |
| 2.3 Does corpus-independent evaluation pass without public/gold access? | filled for `166d40c`; remeasure after change | offline gate PASS, public lanes `NOT_RUN`, report SHA in authority snapshot |
| 2.4 Does official v1 remeasure without correctness/safety regression? | filled for `532ef1f`; remeasure at final head | supported strict run: 41/81 correct, 0 wrong, hard-safety 23/23 measured with zero nonzero; report SHA `3490db4…`; acceptance gates correctly fail |
| 2.5 What is B28A/B28's current executable disposition without the historical manifest? | named-unfilled | prepare/seal/gold-isolation tools and current contract |
| 2.6 Are B29/B32 general engine implementations complete and adversarially verified? | named-unfilled | typed profiles, catalogue walls, profile application tests |
| 2.7 Can the distinct supplemental campaign be frozen before change with source-only selection and an immutable seal? | filled at `51a9c68` | nine-entry manifest digest `32aa3ce5…`, named supplemental seal, portable exact-head sealed M→V→R→G baseline; [authority snapshot](../knowledge/phase56-authority-snapshot.md) |
| 2.8 Which general typed capabilities close the selected cohorts without corpus-specific routing? | named-unfilled | current engine laws/profile architecture and measured candidates |
| 2.9 Does final canonical remeasurement satisfy the supplemental target with zero wrong/unscored leakage? | named-unfilled | locked supplemental manifest, baseline/final reports, canonical scorer |
| 2.10 Do full relevant local matrices, exact-head CI, checker review, and PR evidence jointly satisfy Stage 7 acceptance? | named-unfilled | test matrix, GitHub Actions, release gates, current disposition contract |

### 3. Stage 8 — conclusion: Stage 8 starts only from genuinely accepted Stage 7 and closes its own specification

Source: stage-order rule, [current progress](../../docs/PHASE56_STAGE7_PROGRESS_REPORT.md).

| Leaf | Status | Source / lead |
|---|---|---|
| 3.1 Is Stage 7 genuinely accepted under the current contract? | named-unfilled | leaf 2.10 |
| 3.2 What is the authoritative Stage 8 specification and acceptance tree? | named-unfilled | repository search only after 3.1 |
| 3.3 Does Stage 8 implementation and full evidence satisfy that tree? | named-unfilled | no source yet; gated by 3.2 |

### 4. Whole-product hardening — conclusion: the contracted student product is verified across architecture, runtime, and operations

Source: [target architecture](../../01_TARGET_ARCHITECTURE.md), [release gates](../../RELEASE_GATES.md), phase contracts.

| Leaf | Status | Source / lead |
|---|---|---|
| 4.1 Do NLP, provenance, clarification, unsupported, and contradiction paths meet their current contracts? | named-unfilled | phases 43–47 and relevant test matrices |
| 4.2 Do typed physics, candidate validation, invariants, numeric conditioning, and independent oracles meet their contracts? | named-unfilled | phases 45–52 and relevant test matrices |
| 4.3 Do explanation, visualization authority isolation, frontend/browser/mobile, API/connectivity/CORS/auth/failure states meet their contracts? | named-unfilled | phases 53–54, frontend/backend integration evidence |
| 4.4 Do performance, observability, privacy/security, production configuration, and deployment readiness meet release gates? | named-unfilled | release/operations documents, runtime checks, CI/deployment evidence |

### 5. Evidence and terminal handoff — conclusion: the final claim is narrow, current, reproducible, and recoverable

Source: ballast verify-gate, proof-standard, rehearsal, checkpoint; [PRODUCT-TRUTH](../PRODUCT-TRUTH.md).

| Leaf | Status | Source / lead |
|---|---|---|
| 5.1 Are implemented/wired/operational/verified product states separated with current evidence? | named-unfilled | PRODUCT-TRUTH update after execution |
| 5.2 Does a zero-context executor complete the final handoff without a blocking stall? | named-unfilled | rehearsal rounds, maximum three |
| 5.3 Is the branch/PR/checkpoint clean, pushed, and exact at COMPLETE or genuine BLOCKED? | named-unfilled | final git/GitHub/checkpoint verification |

## Single next leaf

Leaf 2.8 — implement only the general typed capabilities needed by the three frozen cohorts, with adjacent/adversarial/authority-isolation regressions. The manifest, seal, population, gold boundary, scorer, and thresholds stay frozen.

## Known gaps

- The approved public corpus is available and frozen-hash verified; no historical augmentation manifest was found or inferred.
- Exact-head CI at `532ef1f` found one temp-path naming violation in the new strict-flag control; `d5ed247` fixes it and its 102 directly affected tests pass, while new-head CI is pending.
- The supplemental manifest and seal are frozen and the portable exact-head pre-change baseline is complete. The selected cohorts still have zero supplemental yield; general typed capability work is next.
- Stage 8 specification remains intentionally unread until Stage 7 acceptance permits work there.
- Production/deployment operational evidence is not yet current.

## Done-check

| Check | Status |
|---|---|
| Stage 7 current contract | pending |
| Stage 8 current contract | gated |
| Whole-product release gates | pending |
| PRODUCT-TRUTH evidence | pending |
| Rehearsal | pending |
| Clean exact branch/PR/checkpoint | pending |

## Superseded cuts

None.
