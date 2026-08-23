# memory/ — dynatutor-mvp brain

Purpose: this folder is the durable memory for dynatutor-mvp. Conversations forget; this folder does not. What is recorded here survives topic changes, session resets, and context compaction.

## File map

| File | What | Write rule |
|---|---|---|
| `DECISIONS.md` | Confirmed decisions | Append-only. Supersede protocol — never edit past entries |
| `OPEN-QUESTIONS.md` | Unresolved items awaiting a decision, and readings in force the user has not confirmed | Two tables. Close each row with a link to the resolving decision, or drop it |
| `SESSION-LOG.md` | What happened, per working session | Append, dated |
| `PRODUCT-TRUTH.md` | What the product actually does (if applicable) | Evidence + date only. Three sections: implemented / not / excluded |
| `CHECKPOINT.md` | Current thirty-second recovery point for the active goal | Replace only after archiving the outgoing checkpoint |
| `checkpoints/` | Immutable prior checkpoints for the active goal | Add the outgoing checkpoint before replacing `CHECKPOINT.md`; never rewrite archived entries |
| `goal/` | Canonical goal terrain, skeleton, gaps, and done-check | Update by versioned diff; retain superseded cuts |
| `knowledge/` | Findings that passed the verify gate | Evidence, sample, limits, label, and verification date required |

## Verified recovery findings

| Finding | Role |
|---|---|
| [`knowledge/phase56-authority-snapshot.md`](knowledge/phase56-authority-snapshot.md) | Mutable branch/PR authority, historical-manifest constraint, and earlier exact-head baselines |
| [`knowledge/phase56-supplemental-yield-proof.md`](knowledge/phase56-supplemental-yield-proof.md) | Final frozen supplemental `+9` proof and current official-v1 strict result at exact mechanics head `7794168` |
| [`knowledge/phase56-pr10-performance-reproduction.md`](knowledge/phase56-pr10-performance-reproduction.md) | Exact `b3b7291` PR10 performance-failure reproduction evidence, local limits, and remote-CI distinction |
| [`knowledge/phase56-frontend-dependency-security.md`](knowledge/phase56-frontend-dependency-security.md) | Exact baseline/post-change npm audit evidence, locked remediation, CI audit enforcement, and bounded reachability finding |
| [`knowledge/phase56-deployment-readiness.md`](knowledge/phase56-deployment-readiness.md) | Current Render Blueprint schema validation and production-mode local health/auth/docs/CORS evidence |

## Existing authoritative project sources

This memory folder is an index and recovery layer only. It does not replace, duplicate, or restate the sources below as a new source of truth; follow the original source and its own supersession rules.

| Source | Role |
|---|---|
| [`../00_GLOBAL_RULES.md`](../00_GLOBAL_RULES.md) | Repository-wide engineering, physics-safety, git, compatibility, and reporting rules |
| [`../01_TARGET_ARCHITECTURE.md`](../01_TARGET_ARCHITECTURE.md) | Target dynamics architecture, layer responsibilities, data flow, result states, and capability matrix contract |
| [`../RELEASE_GATES.md`](../RELEASE_GATES.md) | Authoritative release gates A–H; implementation or green tests alone do not imply release acceptance |
| [`../docs/PHASE56_STAGE7_PROGRESS_REPORT.md`](../docs/PHASE56_STAGE7_PROGRESS_REPORT.md) | Phase 56 Stage 7 progress and current disposition; its top-level authoritative list and latest closure sections supersede historical per-session `ACCEPTED` entries |
| [`../docs/PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md`](../docs/PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md) | Public-corpus v2 candidate and supplemental-yield campaign contract, provenance boundaries, census, and measured campaign status |
| [GitHub PR #17](https://github.com/jooa1018/dynatutor-mvp/pull/17) | Latest open-PR current disposition, authoritative Phase 56 branch/base/head identity, and review/merge state |
| Git refs and history (`HEAD`, upstream, `main`, merge-base) | Current repository-state and ancestry evidence; `main` must not be mistaken for the authoritative Phase 56 worktree |
| [`../.claude/ballast.rules.json`](../.claude/ballast.rules.json) | Standing project guardrails applied during recovery and work; not a product-status source |

## Operating principles

1. **Record in-session.** Decisions and important facts are written the moment they appear, not at the end. Zero loss.
2. **User-confirmed vs AI-proposed are always distinguished.** A proposal the user hasn't confirmed is not a decision — and neither is your reading of a non-answer; that is registered in OPEN-QUESTIONS.md as `assumed`.
3. **Claims carry labels** — confirmed / observed / assumed / hearsay / unknown (see the ballast verify-gate skill).
4. **External product claims require truth-file evidence** (see the ballast proof-standard skill).
5. **Unresolved things get registered**, not remembered. If it's not in OPEN-QUESTIONS.md, it will be lost.
