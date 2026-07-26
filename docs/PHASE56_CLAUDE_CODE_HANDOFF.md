# Phase 56 Claude Code Continuation Handoff

## Current authoritative state

- Disposition: `STAGE_7_IN_PROGRESS / NOT_ACCEPTED`
- Stage 7 code candidate / tested head: `b88a9eac06c8be16f53a909e63d0c15a044afdf9`
- Branch: `codex/phase56-generic-mechanics-engine` (fast-forward only; the four
  pre-session candidate commits `c1d2dd1`, `42fcc01`, `bfab131`, `d33c70b` are
  preserved byte-identical)
- PR #17: open, Draft, unmerged; stacked on Draft PR #16
- Main: `00b3a60de6e13756d089655879a02e4094122047` (unchanged)
- Stage 7: **IN PROGRESS** — see `docs/PHASE56_STAGE7_PROGRESS_REPORT.md` and
  `docs/PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md`
- Stage 8: **NOT STARTED**
- Public corpus: supplied out-of-tree, integrity-verified, and **EXECUTED**
  end-to-end through the engine (public 100)
- Live/external model calls: **0**; measured cost $0; actual model quality
  `NOT_RUN / N/A`
- Textbook PDF and private corpus: **UNTOUCHED**

### Measured Lane B public-100 state (at `b88a9ea`)

`solved 6 / verified_unsupported 6 / needs_figure 2 / needs_confirmation 2 /
insufficient_information 1 / compiler_failure 67 / compiler_unsupported 16`,
answer scoring 6 correct / **0 wrong**, all six verification checks passed on
every solved candidate. The frozen target (`81/12/2/2/2/1`, wrong 0) is **not
met**; the single failing strict gate is `strict_lane_b_all_solved`. Every
other strict Stage 7 gate passes (Lanes C/D/E, compositional 12, synthetic 38,
metamorphic, physics-changing, hard-safety all-zero, redaction).

### Stage 7 session packages completed and pushed (`d33c70b..b88a9ea`)

| Package | SHA |
|---|---|
| A — event source authority (+routing-token fix) | `a677547`, `15255a5` |
| B — typed occurrence scope (+field-registry fix) | `a3b9b43`, `fc4ec64` |
| C — elapsed-duration query binding | `0083fd9` |
| D — structural angle refusal | `c616151` |
| E — profile-isolated feasibility | `223c070` |
| Solver extremum waiver + provenance rule | `84d1cb6` |
| Offline-gate lane aggregation | `1770ea1` |
| Gate CI parity (Lane E mirror, safety/yield unbind) | `b88a9ea` |

Full backend regression at the waiver head: **3912 passed, 0 failed**. Stage 7
focused suite at `b88a9ea`: **794 passed**. Same-model read-only audit over
the whole range: **blocking findings 0** (six non-blocking observations are
listed in the progress report and are intentionally unpatched at this head).

Exact-head CI at `b88a9ea`: Stage 7 offline evaluation (push + PR), Stage 6
multimodal (push + PR), and Phase 55 parser all **SUCCESS**; DynaTutor release
tests **FAILURE** — the `backend slow` `incline_hanging` file shard hit the
240 s per-shard wrapper budget. Measured classification (recurring duration
flake of a structurally marginal shard budget; same-hardware base-vs-head shard
timing 286.94 s vs 286.46 s = code parity) is in the progress report's
release-tests failure analysis. Do not "fix" this by relaxing the budget
silently; it is a recorded infrastructure blocker.

## Non-negotiable boundaries for the next session

- Stage 7 is authorised and in progress; Stage 8 is not, and must not be started.
- The public corpus is authorised for the evaluator only. Read it from a path
  outside the repository; never commit the archive or a raw split, and never
  store it in a GitHub secret. The full/private corpus and the textbook PDF
  remain out of bounds.
- Do not use corpus family, case ID, expected answer, filename, raw text
  regex/keyword, system type, or model confidence as answer authority.
- Do not add a second AI call, legacy answer fallback, direct graph/answer
  patch, threshold relaxation, or production deployment.
- The frozen Lane B target `81/12/2/2/2/1` (wrong 0) may not be lowered or
  reinterpreted.
- Fast-forward pushes only on `codex/phase56-generic-mechanics-engine`; never
  reset, rebase, amend, squash, or force-push existing history.
- Preserve PR #16/#17 as Draft and unmerged; preserve main.

## Next exact task

Reproduce the strict gate, then continue Lane B from the **measured**
profile-isolated matrix (never the first-wins census):

```bash
cd backend
STAGE7_PUBLIC_CORPUS_PATH=/abs/path/dynatutor_beer12_ko_corpus_v1_public.zip \
OPENAI_API_KEY="" ANTHROPIC_API_KEY="" \
OPENAI_BASE_URL="" ANTHROPIC_BASE_URL="" \
MECHANICS_MODELER_BASE_URL="" MECHANICS_FIGURE_BASE_URL="" \
python tools/run_phase56_stage7_offline_gate.py \
  --require-full-stage7 \
  --output "$TMPDIR/stage7_offline_gate_report.json"
```

Expected today: exit `2` with exactly one failing strict gate
(`strict_lane_b_all_solved`, 6/81) and everything else PASS.

Then, in order of measured yield:

1. `free_flight_gravity` — make its 6 `profile_plan_not_formable` contexts
   formable; the post-waiver verified-solve path is already proven by the
   synthetic apex-time control (`t = v0/g`, all checks pass).
2. `impulse_momentum` (4 contexts), `relative_translating_frame` (9 contexts).
3. Re-measure after each increment; wrong solves must stay 0; the lane
   distribution must only improve by real verified solves.
4. Fold in the six non-blocking audit observations as small atomic commits.

Container notes: run solve experiments as script files with an
`if __name__ == "__main__"` guard (stdin-fed `__main__` breaks the solver's
spawn-isolated subprocess); install `fastapi==0.128.2` and put
`/usr/local/bin` ahead of a uv-managed pytest on `PATH` before trusting a full
regression.

Do not commit the archive or any raw split, do not report an unexecuted lane
as passing, keep Live evaluation disabled, keep PR #16/#17 open, Draft, and
unmerged, leave main unchanged, and do not start Stage 8.
