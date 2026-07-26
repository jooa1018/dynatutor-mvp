# Phase 56 Stage 7 progress report

Disposition: **`STAGE_7_IN_PROGRESS / NOT_ACCEPTED`**

Stage 7 is **not** accepted. Stage 8 has **not** been started. PR #16 and PR #17
remain open, Draft, and unmerged, and `main` is unchanged at
`00b3a60de6e13756d089655879a02e4094122047`.

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
| Prior authoritative head (session base) | `10f4829366c2e959429cd6405541803b6847b370` |
| Session base candidate (exact 4-commit fast-forward of the above) | `d33c70bf16341ae06eb80bbf515333b52d92b59a` |
| **Code candidate / tested head (this session)** | `b88a9eac06c8be16f53a909e63d0c15a044afdf9` |
| Documentation head | this commit and later |

The candidate was reflected onto `codex/phase56-generic-mechanics-engine` by a
verified-ancestor **fast-forward push only** (`10f4829 → b88a9ea`). No reset,
rebase, amend, squash, force-push, or history rewrite occurred anywhere in the
session. The four pre-existing candidate commits (`c1d2dd1`, `42fcc01`,
`bfab131`, `d33c70b`) are preserved byte-identical; every change landed as a
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

## Measured Lane B public-100 result (executed at `b88a9ea`)

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

- **Answer scoring: 6 scored, 6 correct, 0 wrong, 0 unscored.** Every solved
  value was converted to SI with `pint` and matched the gold reference within
  tolerance. **Wrong solves: 0** — the hard requirement holds.
- All 6 solved candidates passed all six verification checks
  (`equation_residual`, `nonnegative_time`, `query_binding`,
  `source_evidence`, `unit_consistency`, `constraint`).
- The lane distribution was **byte-identical at every package head** of the
  session — packages A–E and both gate commits changed no public-100 outcome,
  which is the intended result of contract-hardening work.

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

## Full strict gate result at `b88a9ea`

`run_phase56_stage7_offline_gate.py --require-full-stage7` (authorised archive
supplied out-of-tree via `STAGE7_PUBLIC_CORPUS_PATH`; exit code 2, as expected
with exactly one failing requirement):

| Strict gate | Result |
|---|---|
| `strict_corpus_supplied` / `sha_match` / `84` / `16` / `100` | PASS |
| `strict_lane_b_executed` / `strict_lane_b_100_executed` | PASS |
| **`strict_lane_b_all_solved`** | **FAIL — `unsolved_cases_remain` (6/81)** |
| `strict_lane_c_pass` (modeler 59 + contracts 19 + reconciliation 4 = 82) | PASS |
| `strict_lane_d_pass` (API/runtime + security + image + idempotency + observability = 24) | PASS |
| `strict_lane_e_pass` (toolchain, tests, lint, typecheck, build) | PASS |
| `strict_compositional_12_pass` (12/12 structures) | PASS |
| `strict_synthetic_38_pass` (manifest = 38) | PASS |
| `strict_metamorphic_pass` | PASS |
| `strict_physics_changing_controls_pass` | PASS |
| `strict_hard_safety_pass` (23 signals all zero; wrong solves measured 0) | PASS |
| `strict_redaction_pass` | PASS |

Lane C remains contract/integration evidence over the deterministic recorded
modeler only; **actual model quality is `NOT_RUN / N/A`** — no external model
call was made and measured cost is $0.

## Regression evidence

| Suite | Result |
|---|---|
| Full backend regression (waiver head `84d1cb6`) | **3912 passed, 0 failed** (1 skipped, 430 deselected) |
| Full backend regression (package E head `223c070`) | 3899 passed, 0 failed |
| Stage 7 focused suite at `b88a9ea` | **794 passed** |
| Solver + parity suites at waiver head | 203 passed |
| Extremum-boundary solve controls (incl. 9 near-miss graph mutations + provenance-void control) | 13 passed |

No test was deleted, no assertion weakened, no threshold relaxed, no legacy
fallback or case-specific patch introduced. Negative controls for package A
were written first and confirmed red before the implementation landed.

## Exact-head CI evidence for `b88a9ea`

All four workflows executed at the exact candidate head on
`codex/phase56-generic-mechanics-engine`:

| Workflow | Run | Result |
|---|---:|---|
| Phase 56 Stage 7 offline evaluation (push) | `30213405608` | **SUCCESS** |
| Phase 56 Stage 7 offline evaluation (pull_request) | `30213406987` | **SUCCESS** |
| Phase 56 Stage 6 multimodal (push) | `30213405564` | **SUCCESS** |
| Phase 56 Stage 6 multimodal (pull_request) | `30213407012` | **SUCCESS** |
| DynaTutor release tests (pull_request) | `30213406981` | **FAILURE** — `backend slow` shard timeout, analysed below |
| Phase 55 textbook parser (pull_request) | `30213407014` | **SUCCESS** (`live-openai-smoke` skipped — no Live call) |

This evidence belongs to `b88a9ea` and must not be re-attributed to the later
documentation-only head.

### Release-tests failure analysis (run `30213406981`)

The `backend slow` job's `incline_hanging_same_fixture_parity` file shard was
killed at the wrapper's 240 s per-shard budget, and the `release gate` job then
failed as a consequence. The run's other five jobs — fast, quality (including
the warm-solve latency and cold-import/RSS budgets), frontend, performance —
all passed.

Measured evidence classifies this as the **documented recurring duration flake
of a structurally marginal shard budget**, not a code regression:

1. At the green base head `10f4829` the same shard passed CI at **215.82 s of
   the 240 s budget** — 90 % consumed before any commit of this session.
2. In the failed run, every slow shard was uniformly 6–12 % slower than in the
   green run, including suites untouched by any commit in the window
   (incline_friction 66.2 s vs 59.2 s, massive_pulley 52.0 vs 46.6,
   rolling_general 49.3 vs 45.2, atwood 32.8 vs 30.5, vertical_circle 46.6 vs
   44.1). That is runner-level slowness: 215.8 × ~1.10 ≈ 237 s, plus
   two-worker contention, crossed 240 s.
3. Same-hardware serial timing of the identical shard command on the session
   container: base `10f4829` = **286.94 s**, head `b88a9ea` = **286.46 s** —
   a 0.2 % delta, code-parity within noise. (This container is ~33 % slower
   than CI runners, so both sides exceed 240 s locally; per-test durations are
   statistically identical between the heads.)
4. The identical shard timed out once before, at intermediate head `1c86986`,
   and was classified a duration flake with parent-green and head-green CI
   evidence (recorded in PR #17's body at the time).
5. The `incline_hanging` fixtures carry zero events, so the session window's
   event-scoped engine changes do not execute in this suite.

No threshold was changed and no test was altered in response. The structural
fact — this shard's cost sits at ~90 % of its per-shard budget on a nominal
runner — is recorded here as a typed infrastructure blocker for the maintainer
to resolve deliberately (budget, shard split, or fixture cost), outside this
session's scope.

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
| External model calls | 0 |
| Measured cost | $0 |
| Private held-out access | 0 |
| Textbook PDF access | 0 |
| Raw corpus committed | no (path-supplied archive only) |
| Gold leakage in runtime material | 0 (enforced and tested) |
| Case-ID / family / filename / raw-text routing | 0 (enforced and tested) |
| Wrong solves (gold-scored) | **0** |
| Actual model quality | `NOT_RUN / N/A` |

## Next exact task

Continue Lane B from the measured matrix, not the census: extend the
`free_flight_gravity` plan former so its 6 `profile_plan_not_formable`
contexts become formable (the verified-solve path past the solver waiver is
already proven), then re-measure; take `impulse_momentum` and
`relative_translating_frame` next by the same rule. Each increment must keep
wrong solves at 0 and the distribution honest. Then fold in the six
non-blocking audit observations as small atomic commits, re-run the strict
gate, and re-attribute CI at the new exact head.

Stage 8 must not start.
