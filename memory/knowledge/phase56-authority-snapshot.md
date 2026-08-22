# Phase 56 authority snapshots

## Authoritative branch, upstream, and PR converged after bootstrap — verified 2026-08-23

- Label: `confirmed (self-gated)`.
- Claim: after fetching `origin` and fast-forward pushing the isolated ballast bootstrap, local `HEAD`, `origin/codex/phase56-generic-mechanics-engine`, and PR #17 head all identify `fee7003a078e59de280018a2cd4f8e9bda66e848`. The commit is a one-parent child of starting head `bcdd8df63d3e1c2e1493ea0c1e38fcdb2b107b70` and changes only `.claude/ballast.rules.json`, `AGENTS.md`, and `memory/`. PR #17 is OPEN and Draft; its base remains `codex/phase55-gpt-first-textbook-parser` at `4762727e8f9191604e2531b9982a5ae72ed73db9`. `origin/main` remains `00b3a60de6e13756d089655879a02e4094122047` and is the merge-base, 0 commits ahead of and 419 commits behind the current head after bootstrap.
- Refutation attempted: fetched with prune; checked local/upstream left-right divergence; compared the GitHub PR API head/base; compared `origin/main`, merge-base, and ancestry; inspected the bootstrap commit's exact path set; checked for remaining worktree changes.
- Primary sources: `git fetch --prune origin`; `git rev-parse HEAD '@{u}' origin/main`; `git rev-list --left-right --count`; `git merge-base`; `git show --stat fee7003`; GitHub PR #17 API response on 2026-08-23.
- Sample: 3 state surfaces (local ref, fetched upstream ref, GitHub PR head) plus commit-tree and ancestry checks.
- Limits: this is a mutable remote-state snapshot, not a permanent fact. PR merge state was `UNSTABLE` immediately after the new-head push while checks settled; no CI or Stage 7 acceptance is inferred from branch convergence.

## Historical manifest status is a current contract constraint — verified 2026-08-23

- Label: `confirmed as current disposition (self-gated)`.
- Claim: the authoritative Stage 7 disposition declares the exact historical augmentation manifest unavailable. It must not be reconstructed or replaced; the documented supplemental campaign is a separate identity and cannot retroactively satisfy the historical seal.
- Refutation attempted: searched the current progress report and candidate contract for supersession language; checked the current PR #17 disposition and project rule catalog for any later recovery or substitution declaration. None was found.
- Primary sources: `docs/PHASE56_STAGE7_PROGRESS_REPORT.md`; `docs/PHASE56_STAGE7_CORPUS_V2_CANDIDATE.md`; PR #17 current body; `.claude/ballast.rules.json`.
- Sample: 4 current authority surfaces.
- Limits: this verifies the current repository/PR contract, not a fresh exhaustive filesystem search for the missing historical artifact. The earlier 37,228-file recovery audit remains historical evidence and was not rerun in this bootstrap phase.

## Exact-head Stage 7 baseline before product changes — verified 2026-08-23

- Label: `verified executable evidence`.
- Claim: at exact head `166d40c3a2368a4a514e93d7766196efdb6a9d8d`, the corpus-independent offline gate passed; its sealed report SHA-256 is `61213ce896022877962b614ef4b777e7d48814c3444f172c01aff7589d545eae`. The artifact identity checker matched configured, checkout, report, and raw artifact identity. B28A's read-only checker returned 24 clean checks and no findings. Focused B29/B32 and catalogue-wall tests passed 122 tests; banked/flat/instant-centre parity tests passed 30 tests.
- Refutation attempted: ran each command in an isolated Python 3.11 virtual environment installed from `backend/requirements-lock.txt`; kept provider credentials/base URLs empty; wrote reports outside the repository; checked the worktree afterwards.
- Primary sources: exact commands from `docs/PHASE56_STAGE7_TEST_MATRIX.md`; `backend/tools/run_phase56_stage7_offline_gate.py`; `backend/tools/check_phase56_stage7_ci_artifact_identity.py`; `backend/tools/run_phase56_stage7_b28a_readonly_checker.py`; pytest output and sealed external artifacts under the current session's temporary report directory.
- Sample: one corpus-independent aggregate run, one artifact identity run, one 24-control B28A run, 152 focused/adversarial tests.
- Limits: none of these results is public-corpus acceptance. The official-v1 probe measured the frozen distribution at 41/81 and hard-safety 23/23 with zero nonzero signals, but used an unsupported one-flag CLI combination whose stdout scope was false; it is diagnostic only until the supported two-flag strict command is repeated.
