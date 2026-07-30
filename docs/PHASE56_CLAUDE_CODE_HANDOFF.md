# Phase 56 Claude Code Continuation Handoff

## 2026-07-30 session prefix — B10/B12 revoked, B14 landed, corpus absent

Read `docs/PHASE56_STAGE7_PROGRESS_REPORT.md` §"B10/B12 authority repair
session" first; it supersedes the head pointers below.  In brief:

- Code head after this session: `53a169d1ed46fd200e453e5a47784550e2215a13`
  (fast-forward `25c36e6 → 3411e8e → 58ae586 → a837719 → 53a169d`).
- **B10 and B12 are revoked to INCOMPLETE**: their profiles now demand the
  typed authority the public structured data cannot state (B10: one
  `rotates_about`-projected common centre; B12: minimum objective + inward
  contact side + touching/boundary states).  `AUTHORITY_ACCEPTED_SCORE` is
  **38/81**; the old 44/81 is observed-only and stale.
- **B14 (1D restitution impact)** is implemented and fully tested but its
  public yield is UNMEASURED: this session's container had **no public
  corpus archive**.  First step next session: supply the archive, re-run the
  strict gate at the code head, reconcile observed = authority-accepted.
- Next package (measured diagnosis in the progress report): the table-pulley
  two-body closure.  Do NOT attempt the translating-frame family as yield —
  its clean contexts are expected-deferred.

## Current authoritative state

- Disposition: `STAGE_7_IN_PROGRESS / NOT_ACCEPTED`
- **CODE_CANDIDATE_HEAD**: `803b40c37389315a96d2819b4350cad2c00f892b`
- **STRICT_GATE_TESTED_HEAD**: `803b40c37389315a96d2819b4350cad2c00f892b`
  (report SHA-256 `be45b67ea163f0b376b94e880059b98fc612aaf5c705d644738bd82395742d46`,
  exit 2 on Lane B yield only)
- **FULL_REGRESSION_TESTED_HEAD**: `1954d14a58bf1b3135d3d42057354958de8a24e4`
  (4478 passed, 1 skipped, 0 failed) — not re-attributed to the candidate; the
  candidate only removes tests, and CI re-runs the whole backend at it
- Branch: `codex/phase56-generic-mechanics-engine` (fast-forward only:
  `bc5e0be → 1954d14 → 803b40c`, every pre-session commit preserved
  byte-identical)
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

### Measured Lane B public-100 state

Runtime terminals: `solved 6 / verified_unsupported 6 / needs_confirmation 2 /
not_projected 3 / compiler_failure 67 / compiler_unsupported 16`. Compiler codes:
`underdetermined 67`, `requires_specialized_model 16`,
`nonlinear_verification_deferred 6`, `translating_frame_relative_acceleration_deferred 3`,
`free_linear_vibration_readout_deferred 3`.

Case-level scoring against the frozen distribution: supported **6/81 correct, 0
wrong, 75 unscored**; deferred **6/12**; unsupported-other **0/2**; needs_figure
**2/2**; needs_confirmation **2/2**; insufficient_information **1/1**; terminal
mapping **0.17**; the six metrics all **0.074** (6/81).

The engine emits **2 distinct laws** and **12 equations** across all 100 cases;
67 cases compile to a graph with zero equations. Hard safety: **23/23 signals
measured, 0 unbound, 0 nonzero**. Lanes C/D/E, compositional 12, synthetic 38,
metamorphic, physics-changing and redaction all PASS.

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

## Next exact task — B1, an implementation package, not an analysis

**The next session's first action is the B1 cohesive implementation package**
(slot-pin `radial_transverse` frame), not another audit, census, diagnostic, or
report. The measurement phase is finished: six independent read-only audits and
the evaluator v3 package are complete, and the ranked plan below is the product
of that work. Re-deriving it would spend a session and move the public-100
supported count by zero.

**B1 in one paragraph.** Create exactly one `IRReferenceFrame` with
`frame_type = radial_transverse` and rebind the query quantity's `frame_id` to
it, inside a transactional profile that follows the existing
`_DEFERRAL_ONLY_PROFILES` pattern (`relative_translating_frame` is the working
precedent and converts 3 undifferentiated `underdetermined` graphs into 3 exact
typed deferrals today). Every other conjunct of
`_slot_pin_relative_motion_issue` (`compiler.py:1232-1400`) already holds 3/3 —
role/component/scalar/symbol/dimension, `len(pin_ids) == 1` with a `joint`
subject, a `slot`-primitive entity in `relevant`, and exactly one qualifying
`lies_on` relation. The frame is the only missing conjunct. The frame's identity
is read from the corpus's own `moves_in_slot` relation; nothing is invented.
Create **no** point, force, or interaction — the detector does not require one
and creating it drags in B3's cost.

**Expected measured outcome:** deferred **6/12 → 9/12**, supported unchanged at
6/81, `wrong_solve` 0, `supported_downgraded_to_unsupported` 0. If the profile
fires on any of the 81 supported cases, revert.

Note honestly that B1 raises the *deferred* class, not the supported count. The
first package that can raise **supported** is the co-required bundle B5+B6+B7,
and the measured reason is in §6b-4: a frame alone unlocks zero laws. B1 is
first because it is the highest measured yield-to-effort item and it exercises
the transaction machinery every later package needs — not because it is the
largest.

Reproduce the strict gate first, then continue Lane B from the **measured**
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

Expected today: exit `2` with **eleven** failing strict gates — the three class
gates (`strict_supported_81_solved` 6/81, `strict_deferred_12_verified_unsupported`
6/12, `strict_unsupported_other_2` 0/2), `strict_terminal_mapping_100_percent`
(0.17), the six metric gates (all 6/81 = 0.074), and `strict_unscored_zero` (75).
Everything else PASSes, including hard safety with **23/23 signals measured, 0
unbound, 0 nonzero**. `strict_lane_b_all_solved` no longer exists; it was an
unsatisfiable gate removed in evaluator v2.

Then, in order of **measured full-pipeline yield** (see below):

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

## Evaluator work that must land before the structural packages

Four items, all measured, none able to fire on the public 100 today. They are
listed before the structural plan because three of them are gates that currently
measure nothing, and the fourth guards the file every structural package edits.

| # | Item | Why it must precede structural work |
|---|---|---|
| E1 | `unit_dimension_accuracy` compares the evaluator's `_QUERY_ROLES` table to gold — both frozen data. Carry the engine's `render_canonical_si_unit(...)` on `LaneBResult` and compare that. | `strict_unit_dimension_accuracy_100_percent` is vacuous until fixed; it is one of the six metrics acceptance requires at 100 %. |
| E2 | `direction_sign_accuracy` collapses onto `answer_accuracy`. Require the sign to be resolved from typed structure and add the sign-inversion mutation control. | `_SEMANTIC_AXIS_BINDING` fixes `up = +y` as a server convention the corpus never states. Inert today; the first signed solve makes it the likeliest source of a confident wrong answer. **Land before B6.** |
| E3 | Bind the tampering-invariance sweeps (the 16 case/gold mutations over `lane_b_draft_projection.py`) into `bound_node_ids()` and the gate's suite lists. | Every structural package edits that file, and no gate currently watches it for case-specific routing. **Land before B1.** |
| E4 | Split `verification_check_kind_missing` into "engine skipped a graph-required kind" vs "the scorer's floor demanded a kind the graph never required", and assert `_REQUIRED_CHECK_KINDS ⊆ graph_required_check_kinds` on every solve. | The `source_evidence` floor is unconditional while the engine requires it conditionally. Latent today (6/6 satisfy it); packages producing new provenance shapes could trip it, and the failure would read as an unscored case rather than as the floor. |

## Ranked structural plan (measured, six independent read-only audits)

The ranking rule is fixed and non-negotiable: **measured additional verified
full-pipeline yield**, never plan-complete count, never application count, never
compiler terminal alone. §6b-1 of `PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md` records
why each of those three misleads.

Two measured facts govern everything below:

- **A frame alone unlocks zero laws** (`frame_alone_unlocks = 0`). The blocking
  structure is a co-required bundle — frame *and* point *and* signed axis binding
  *and* a force-bearing interaction that owns its quantities. Scope packages to a
  bundle, not to a record kind, or every increment measures zero.
- **The information is in the source.** For all ten missing structure kinds,
  `present + derivable ≥ 24/100`, and for six of them `≥ 64/100`. The largest
  single discard is `motion_segments.motion_model`: 9 of 13 declared values are
  dropped, 53/100 records name a regime the projection emits nothing for, and 43
  of the 67 `underdetermined` cases carry one.

| # | Package | Measured yield | Note |
|---|---|---|---|
| B1 | Slot-pin `radial_transverse` frame | deferred 6/12 → **9/12** | Highest yield-to-effort. Every conjunct of `_slot_pin_relative_motion_issue` already holds 3/3 except the frame itself. Uses the working `_DEFERRAL_ONLY_PROFILES` mechanism. Create **one** `IRReferenceFrame`; create no point, force, or interaction. |
| B2 | `unsupported_other` detector | 0/2 → **2/2** | **Do not** populate `unsupported_features` from `expected_failure_codes` / `parse_status` / `expected_system_type` — all three are on `FORBIDDEN_MEMBERS` and reading them is expected-terminal routing in disguise. Derive from a total function over the Draft type vocabulary instead. See §6b-6. |
| B3 | Coriolis `rotating` frame + typed points | deferred 9/12 → **12/12** | Same certainty as B1, four structures instead of one. |
| B4 | `ProfileExecutionTraceV1` | 0 direct | Mandatory before B5+: plan / application / full-lane measured separately per profile, from a pristine Draft, order-invariant. |
| B5 | Assumption-vocabulary widening | 8 contexts | Resurrects an existing transaction. |
| B6 | Source-stated signed components | 63 quantities / 43 records | Pure source-carrying; `right`/`left`/`upward`/`downward`/`along_motion` currently lose their component. |
| B7 | Relation → force-bearing interaction | 52 contact + 12 rope records | |
| B8 | `fixed_pulley` + `incline_hanging_pulley` transactions | 3 + 3 plan-complete | Plan-complete today with **no builder**. Measure the full lane before trusting the count — §6b-1. |
| B9 | `rigid_fixed_axis` capability package | 13 applicable | Largest population, largest effort. |

Every package must carry, before it lands: a positive synthetic control,
near-miss negative controls, an authority attack, a physics-changing control, ID
rename invariance, evidence-order invariance, and the tamper-invariance sweep
(the 16 case/gold mutations) proving the structure is not identified by any
forbidden member.

One claim in the synthesis is **refuted and must not be re-adopted**: that
accepting `compiler_unsupported` for `unsupported_other` would downgrade the 16
supported-expected cases that reach that terminal. It does not —
`_REQUIRED_TERMINALS` is consulted only for a case's own expected class. Measured
identical before and after, `supported_downgraded_to_unsupported == 0` both times.
