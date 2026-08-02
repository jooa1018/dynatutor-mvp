# Phase 56 Stage 7 — public corpus v2 candidate contract

Disposition: **`V2_CANDIDATE_GOLD_SCORED_AND_INDEPENDENTLY_RE_SCORABLE — three cohorts closed, two walls measured, the measurement itself fail-closed; the preparation is now attested and independently replayed, and the campaign population is sealed`**

This document records a *candidate* contract and an *experimental* measurement.
The frozen v1 public corpus is unchanged, the v1 acceptance target is unchanged,
`STAGE_7_IN_PROGRESS / NOT_ACCEPTED` stands, and Stage 8 has not been started.

---

## -3. The attested-preparation checkpoint (2026-08-01, latest) — supersedes §-2 below where they differ

Independent verification of the §-2 checkpoint found one further structural
fail-open path in the B28 acceptance seal. It is in the *measurement*, not in
the physics; no cohort was added, none was removed, and no threshold moved.

### -3.1 A context could be excused instead of omitted

§-2 closed *silent omission*. Every context in the corpus now gets exactly one
ledger row, so a context that failed can no longer leave the run by vanishing
from the snapshot, the handle set, the gold index and every count at once.

What it did not close is that all of those rules read the runtime input, and the
runtime input is an ordinary JSON document nobody had signed. So the attack
moves from *removing* a context to *relabelling* one:

```json
{"scoring_handle": "<the real handle>", "context_index": 42,
 "prepared_state": "projection_refused",
 "refusal_code": "projection_refused_no_draft",
 "draft_payload": null}
```

Nothing is missing. The handle is expected, present and unique; the row is a
refusal the contract *anticipates* rather than a blocking one; the record set
and the completed-row set still agree. Applied to all 97 measurable contexts,
the run reports:

| accounting | value |
|---|---:|
| ledger total | 100 |
| runtime_completed | 0 |
| projection_refused | 100 |
| runtime records | 0 |
| missing handles | 0 |
| unknown handles | 0 |
| duplicate handles | 0 |
| blocking refusals | 0 |
| wrong / unscored / regressed | 0 / 0 / 0 |
| acceptance | **PASS** |

`snapshot.expected_handles` was derived from the snapshot's own ledger rather
than from an independent statement of what was prepared, and Phase G scores
`snapshot.records` — so an empty measurement passed. The defect's shape changed
from **silent omission** to **allowed-refusal laundering**; its consequence did
not.

### -3.2 Four structures, and what each one is for

Each closes a different reach of the attack, and none of them is sufficient
alone.

**Cross-field validation** (`RuntimeContextInputV2`). `prepared_state`,
`refusal_code` and `draft_payload` now have to describe one context. A
completed context without a draft, a refusal with one, a refusal under the
wrong code, and a refusal still carrying the projection's own outputs —
`problem_text`, `projection_terminal`, the symbol and authority sets — are all
unrepresentable, each under its own named conflict. `migration_refused` is
refused as unreachable rather than merely unused: `build_candidate_archive`
either resolves an entry, leaves the record unresolved with an empty
augmentation (still a preparable context), or raises and aborts the whole
preparation, so no path turns a migration refusal into a runtime input row.
`runtime_failed` and `snapshot_rejected` are decided by phases that have not
run when the file is written.

**The prepare attestation** (`PrepareAttestationV1`). Phase M now states what it
produced and hashes the statement: context order, handle sequence, prepared
state per context, which contexts were refused and under which code, both count
vectors, and the corpus, manifest, candidate and runtime-input hashes — each
carried twice, as a canonical digest over content *and* as a SHA-256 over the
file's bytes, under names that say which is which. `refusal_handle_set_digest`
covers sorted `(context_index, scoring_handle, refusal_code)` triples rather
than a count, because a swap that refuses a solvable context and admits an
unsolvable one preserves every count. Every digest goes through one shared
canonical JSON spelling; the scorecard previously hashed a `repr`, which
encodes insertion order and the interpreter rather than the content.

**Phase V, the independent prepare replay verifier.** Every check above is a
comparison between two documents Phase M wrote, and a forger who edits the
runtime input and re-derives the attestation from it produces a pair that agrees
with itself perfectly — Phase R has nothing to object to. That is not a defect
in Phase R; it is the boundary of what any artifact-to-artifact check can do.
Phase V goes back to the two inputs that cannot be quietly forged — the public
corpus archive, whose SHA-256 is frozen and published, and the augmentation
manifest, whose digest is published — reruns the deterministic preparation, and
compares its own result against the bytes on disk. It runs *between* Phase M
and Phase R, so a preparation that fails verification reaches the pipeline zero
times. It executes no solver, runs no pipeline, scores nothing, compares no
answer, and writes nothing but its own report.

**The frozen campaign population seal.** Generic completeness asks whether the
run is internally consistent; the seal asks whether it is *this campaign*. It
pins the exact 97/3 split, the identity of the three refusals, the context
order, the handle sequence, the corpus SHA-256 and both manifest hashes, as a
separate versioned acceptance contract rather than counts hard-coded into the
ledger's enums.

### -3.3 The pipeline is now four processes

```
Phase M prepare  →  Phase V verify prepare  →  Phase R runtime  →  Phase G score
```

Phase R gains `--prepare-attestation` and re-scans the **raw** bundle for gold
members at the trust boundary, before any model validates it — `draft_payload`
is an open mapping, so a nested expectation satisfies its type. The scan also
runs before the write in Phase M, so a bundle naming a gold member never exists
on disk as a complete file; previously it was written first and scanned after.
Both scans match normalized keys, so `expectedAnswer` is the same forbidden name
as `expected_answer`.

The full restricted snapshot carries a required `prepare_binding` — required
rather than optional, because an omitted binding would be a fail-open path — and
it is inside the snapshot's digest material. The publishable redacted view
carries the whole-document digests and the aggregate counts but **not** the
handle-set digests: a scoring handle is `sha256(archive_sha256 ‖ context_index)`,
the archive SHA-256 is published and the corpus has a hundred contexts, so a
digest over the refused handles is brute-forceable back to which corpus
positions were refused.

### -3.4 Negative controls

The eight §-2 controls are preserved. Each control below asserts the *name* of
the gate it hits, not merely that something failed; a state-map attack that only
surfaced as "the file hash changed" would be no evidence that the state map is
checked at all.

| # | Attack | Gate | Exit | Pipeline entered |
|---|---|---|---:|---|
| A1 | one runtime-completed context relabelled `projection_refused` | `prepare_prepared_state_map_mismatch` | 2 | no |
| A2 | all 97 relabelled | `prepare_prepared_state_map_mismatch`, `…state_counts_mismatch`, `…refusal_handle_set_mismatch` | 2 | no |
| A3 | one byte of the runtime input edited | `prepare_runtime_input_file_sha_mismatch`, `…digest_mismatch` (and *not* the state map) | 2 | no |
| A4 | gold key nested deep inside `draft_payload` | raw no-gold scan | 2 | no |
| A5 | `runtime_completed` with `draft_payload=null` | `runtime_completed_without_draft` | 2 | no |
| A6 | `projection_refused` carrying a draft | `projection_refused_with_draft` | 2 | no |
| A7 | refusal count held at 3, refused handles swapped | `prepare_refusal_handle_set_mismatch` (and *not* a count gate) | 2 | no |
| A8 | attestation edited | attestation integrity | 2 | no |
| A9 | runtime input **and** attestation forged together | `replay_prepared_state_map_mismatch` at Phase V | 2 | no |
| A10 | snapshot `prepare_attestation_digest` altered | snapshot digest / Phase G binding | 2 | no |
| A11 | different exact code head | `prepare_exact_code_head_mismatch` | 2 | no |
| A12 | frame-less angle=0 admission restored | B30 `stated_support_orientation` | 2 | n/a |

A9 is the one that decides whether any of the rest holds, and it is run twice:
once at the function level, which shows the forged pair satisfies Phase R's
binding check completely, and once end to end over a rebuild of an
independently authored corpus, where Phase V refuses it.

Every runtime-side control asserts three separate things, because two of them
have been true while the third was not: process exit 2, the named gate, and the
pipeline never entered — the last checked both by the absence of any artifact
and by the absence of the unexpected-exception marker the synthetic drafts would
have produced had the run loop been reached. A control group runs an untampered
pair and asserts that marker *is* present, so a broken harness cannot make the
negatives pass silently.

### -3.5 What was measured, and what could not be

The population half of the seal was regenerated from the approved public corpus
`cc8d8b27…` by two independent rebuilds that agreed, and it is *manifest-
independent* by construction: a context's prepared state is decided by
`project_case_to_draft`, which reads the v1 record and nothing else. That was
confirmed empirically by rebuilding against two manifests with different digests
and getting the same four population digests.

| sealed value | source |
|---|---|
| corpus SHA-256 `cc8d8b27…` | the approved archive, hashed here |
| expected context count `100` | rebuilt twice |
| `context_index_set_digest` `9dd50adb…` | rebuilt twice |
| `expected_handle_set_digest` `571e7c40…` | rebuilt twice |
| `prepared_state_map_digest` `d66a27bc…` | rebuilt twice |
| `refusal_handle_set_digest` `84efd880…` | rebuilt twice |
| 97 runtime-completed / 3 projection-refused | rebuilt twice |
| manifest canonical digest `c7222978…` | **the §-2 checkpoint's own record, not a rebuild** |
| manifest file SHA-256 `95aca084…` | **the §-2 checkpoint's own record, not a rebuild** |

**The exact augmentation manifest is not available in this environment.** It is
a restricted out-of-tree artifact and was never committed, by design. Running
Phase M against the approved corpus with the seal enforced therefore fails, and
it fails on exactly two gates and no others:

```
STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:campaign_seal_manifest_digest_mismatch,
                                  campaign_seal_manifest_file_sha_mismatch
```

That result is itself the strongest available evidence about the other nine
sealed values: the corpus hash, the context count, the context order, the handle
sequence, the prepared-state map, the refusal handle set and both count vectors
all matched the seal against the real archive. What could not be re-measured is
the augmented half of the campaign — 15 augmented records, 9 newly solved, the
three closed cohorts — because every one of those numbers is a function of the
manifest.

So this checkpoint is recorded as **`B28A_… INCOMPLETE`** under the blocker
`EXACT_MANIFEST_UNAVAILABLE`, and no augmented v2 number is restated as
re-measured here. The §-2 figures stand as previously recorded; they are not
re-derived, and they are not withdrawn.

### -3.6 Verification at this exact head

Everything below was produced at the final code head, on a quiet host, with the
solver's isolation workers running serially.

| check | command | result |
|---|---|---|
| focused suite | `pytest -q tests/test_phase56_stage7_corpus_v2_prepare_attestation_seal.py` | 93 passed, 0 failed |
| fast Stage 7 | `pytest -q -k stage7 -m "not slow"` | 1380 passed, 0 failed, 183 s |
| slow-inclusive Stage 7 | `pytest -q -k stage7 -m "slow or not slow"` | 1848 passed, 0 failed, 1017 s |
| backend collection | `pytest --collect-only -q` | 4536 collected, **0 errors** |
| read-only checker | `run_phase56_stage7_b28a_readonly_checker.py` | 24 checks, **0 blocking findings** |

`OFFICIAL_V1` strict, under the dependency lock at this head, is unchanged:

| metric | value |
|---|---:|
| supported correct | 41 |
| supported wrong | 0 |
| solved-but-unscored | 0 |
| deferred matched | 12 / 12 |
| blocked numeric answers | 0 |
| blocked silent solves | 0 |
| deferred silent solves | 0 |
| hard-safety signals non-zero | 0 of 23 |
| lanes C / D / E | PASS / PASS / PASS |

The strict process exits 2, as it has throughout Stage 7: the failing gates are
`strict_supported_81_solved`, `strict_unsupported_other_2`,
`strict_terminal_mapping_100_percent`, `strict_unscored_zero` and the six
100 %-metric gates — every one of them a Stage-7-incomplete gate, not a
regression introduced here. **Strict exit 2 ≠ this package failed.**

The v1 terminal map did not move. Run over all 100 public contexts with no
augmentation, at the §-2 checkpoint `3afed91` and at this head, the two maps are
**byte-identical**, with the distribution unchanged:

| Terminal | Count |
|---|---:|
| solved | 41 |
| compiler_failure | 34 |
| verified_unsupported | 12 |
| compiler_unsupported | 8 |
| projection_refused | 3 |
| needs_confirmation | 2 |

The generator that produced the §-2 map's recorded SHA-256
`28965972…` was an out-of-tree script that was not preserved, so that exact
number could not be reproduced from a different serializer. What is recorded
here is the comparison that could be made: the same probe run at both commits,
byte-identical, with the distribution matching §-2's exactly.

### -3.7 Deterministic rebuild, and the artifact digests

The whole `M → V → R → G` pipeline was run twice, independently, at the same
code head, corpus and manifest. All eight artifacts are **byte-identical**:

| artifact | bytes | file SHA-256 |
|---|---:|---|
| candidate archive | 73 982 | `56213da9a3550fa1fe9a93ad73c3d7e220bb6f3b56c3afc0bdaa67790ed3d9c0` |
| runtime input | 1 351 792 | `8251bb3aabfae27d36c141acd290edf36a36aecf5b91e56ef5c560d5fe69deda` |
| prepare attestation | 2 054 | `f3d6f528380707a9c95a50798778d9e4bc2aee2557f72b83783f265a721cc458` |
| prepare verification report | 2 386 | `07a51b845d94126a19e939e91282067b61e658ead99452cd0484614ee5d4b157` |
| full runtime snapshot | 109 728 | `bc91d938cfaa2e62f7395264ecd1d4bf278b0f98af4cc0d7c5aab20c65d5b18e` |
| redacted runtime view | 70 850 | `e2bece9146ce9d65f64d0b1219d27848dc6946f1f7123e8b612a2831c0bac13a` |
| scored shadow report | 2 631 | `2c4176b7be3ab7e97aae11fa3fd48a9507383a706aef73f1cc38441e72b62e12` |
| scorecard | 1 606 | `69ca9ae6ab131a09acc82cda2271fbc33557bd92d648fd845fbf2bdc64858dd8` |

Canonical digests are separate numbers about content, and are never quoted as
file hashes:

| canonical digest | value |
|---|---|
| candidate archive | `9404249bc2be4e4840abc906c5ec6c04c2976d2bdb1507d6bab981b2c93ad110` |
| runtime input | `70c50ed2ad64a00837246ba8eb1cc001c5a6030ed69dcf631e8106add80b3bf8` |
| prepare attestation | `a26dea29a9ce399afe24f828521712be44ca771d019eb1745ebfa91f7de06d3e` |
| `context_index_set_digest` | `9dd50adbd73bc58bb391efca85d1436fcc4c19cb0bc2495ec0eeb4c1e42f6952` |
| `expected_handle_set_digest` | `571e7c40a8999bc04b820ac8d26f5278a76039a06f254da1cef72398711205fd` |
| `prepared_state_map_digest` | `d66a27bc98baed7d8c1f8c3210e9b3319b6d00fdd06143b8d515649d93df5c84` |
| `refusal_handle_set_digest` | `84efd8804e234c4f280b8e8dda665e70011732b53af6c5443d95f2a1d4966cc5` |
| runtime snapshot | `f32a20b8da4fa300f5820e75984b8e82086152add247245003aaafab5873cce4` |
| scorecard | `e1fffdef27f37aca80927679ff33d76b73b912c077602bda55062174a11dcb38` |

Two things about this run, stated plainly so it is not misread. It is the
**unaugmented baseline**: the manifest is empty, so `augmented = 0`,
`newly_solved = 0`, `cohort_yield = 0`, and the 41 all-shadow-correct is the v1
result, not a v2 yield. And the four population digests above are exactly the
values the campaign seal pins — the same numbers the seal check matched against
the real archive — which is why the manifest is the only thing missing.

No artifact carries a wall-clock timestamp or a path; that is what makes the two
runs byte-identical rather than merely equivalent.

### -3.8 Phase M publishes only after the seal passes

A follow-up read of §-3.3 found the command's own docstring overstating what it
guaranteed. Phase M claimed that "everything is derived and scanned before
anything is written, so a preparation that fails leaves no partial evidence
behind", and the forbidden-key scan really does run before any write — but the
*campaign seal* did not. The order was: write the candidate archive to its final
path, write the runtime input to its final path, build the attestation over
their file hashes, then judge the seal. A preparation refused for being some
other campaign therefore exited 2 with two of its three artifacts sitting
exactly where Phase V, and a hand-run Phase R, look for them.

This was never an acceptance bypass: Phase V re-reads all three artifacts and
refuses a set with no attestation, and both later phases require one. What it
was is a code/comment disagreement on a fail-closed path, which is the kind of
thing that becomes a bypass the next time somebody trusts the comment.

The ordering constraint is real and cannot be removed — the seal is judged over
the attestation, the attestation carries each artifact's file SHA-256, and a
file hash needs bytes on a filesystem. So the write is kept and the *publication*
is moved: each artifact is staged beside its destination as `<name>.partial`,
its hash is recomputed from the bytes that came back off the filesystem, the
attestation and the seal are judged, and only then are all three renamed into
place. A refused preparation unlinks its own staged files and leaves the final
paths holding whatever they held before it ran.

| guarantee | before | now |
|---|---|---|
| forbidden-key scan before any write | yes | yes |
| candidate archive on seal failure | left at final path | absent |
| runtime input on seal failure | left at final path | absent |
| prepare attestation on seal failure | absent | absent |
| an earlier honest artifact | overwritten before the seal ran | untouched |
| file hash source | the body the command meant to write | the bytes read back off disk |

Three controls pin it, and the two negative ones were confirmed to **fire**
against the previous ordering rather than merely to pass against the new one:

| control | asserts |
|---|---|
| `test_a_failed_campaign_seal_publishes_no_prepare_artifact` | exit 2; none of the three final paths exists; no `.partial` left behind; the failure names `campaign_seal_manifest_digest_mismatch` and `campaign_seal_manifest_file_sha_mismatch` and *not* the population gates |
| `test_a_failed_campaign_seal_leaves_an_earlier_preparation_intact` | a pre-existing artifact at each final path is byte-unchanged after the refusal |
| `test_a_sealed_preparation_publishes_all_three_artifacts` | all three published; each file SHA-256 and canonical digest recomputed from the published bytes matches the attestation; `runtime_input_binding_failures` empty |

The seal both controls are judged against is built from the synthetic campaign's
own honest attestation, so the negative pair differs from the positive one by
the two manifest hashes alone — which is the shape of this package's live
blocker, not an incidental choice. A fourth control reads the orchestrator's AST
and pins that the statement after Phase M returns its status, so an exit 2 means
Phase V, Phase R and Phase G are unreachable.

`PHASE_M_ATOMIC_PUBLICATION_CONFIRMED`. This changes no threshold, no tolerance
and no population, and it does not move B28A's disposition.

### -3.9 Exact-head CI, closed

The §-3 checkpoint's two heads both reached terminal status; every triggered run
succeeded. (§-3.8's cleanup adds a further code head,
`8471126b5c3a12346657f210a443a10754e34e58`, and this documentation-only
descendant of it; their exact-head runs are recorded in PR #17, since a commit
cannot carry its own SHA.)

| head | event | workflow | run ID | conclusion |
|---|---|---|---|---|
| `3e0f75f` code | push | Phase 55 textbook parser | `30708207308` | success |
| `3e0f75f` code | push | Phase 56 Stage 6 multimodal | `30708207346` | success |
| `3e0f75f` code | push | Phase 56 Stage 7 offline evaluation | `30708207320` | success |
| `3e0f75f` code | push | DynaTutor release tests | `30708207333` | success |
| `3e0f75f` code | pull_request | Phase 55 textbook parser | `30708208675` | success |
| `3e0f75f` code | pull_request | Phase 56 Stage 6 multimodal | `30708208657` | success |
| `3e0f75f` code | pull_request | Phase 56 Stage 7 offline evaluation | `30708208644` | success |
| `3e0f75f` code | pull_request | DynaTutor release tests | `30708208664` | success |
| `0263dd0` docs | push | Phase 55 textbook parser | `30708379850` | success |
| `0263dd0` docs | push | Phase 56 Stage 6 multimodal | `30708379847` | success |
| `0263dd0` docs | push | Phase 56 Stage 7 offline evaluation | `30708379886` | success |
| `0263dd0` docs | pull_request | Phase 55 textbook parser | `30708381487` | success |
| `0263dd0` docs | pull_request | Phase 56 Stage 6 multimodal | `30708381530` | success |
| `0263dd0` docs | pull_request | Phase 56 Stage 7 offline evaluation | `30708381503` | success |
| `0263dd0` docs | pull_request | DynaTutor release tests | `30708381513` | success |

15 runs, 15 success, **0 non-success**. Nothing was re-run and no empty commit
was made to provoke a run.

**The push `DynaTutor release tests` at `0263dd0` does not exist, and its absence
is the path filter working.** `backend-tests.yml` filters its push trigger to
`backend/**`, `frontend/**`, `scripts/**` and its own file; `0263dd0` touches
only `docs/`, so no run was created — the same as at the `3afed91` documentation
head before it. An earlier report described this run as still in flight. It was
never queued, so it had no terminal state to reach; the run that was actually
still going at that moment was the push `Phase 56 Stage 7 offline evaluation`
`30708379886`, which completed **success** at 17:00:44Z after 27m44s. The
Release suite is attested at this documentation head by the pull_request run
`30708381513` (success, 15m25s), and at the code head by both events.

### -3.10 What this checkpoint still is not

`STAGE_7_ACCEPTED`, `STAGE_8_READY_TO_START`, `PUBLIC_CORPUS_V2_OFFICIAL` and
`V1_TARGET_REPLACED` are **not** declared. B29 and B32 remain `INCOMPLETE`, and
this package did not touch either. The official v1 public score is **41/81**
and is unchanged; the experimental v2 shadow's 9 newly-solved-correct is a
separate number about a candidate archive, and the two are never added.

B28A itself is recorded as **`INCOMPLETE`** under the blocker
`EXACT_MANIFEST_UNAVAILABLE`. Every structural gate it adds is implemented,
tested and verified; the augmented half of the public campaign could not be
re-measured, and nothing about it is restated here as though it had been. The
`9 / 9` and the three closed cohorts recorded in §-2.6 are the **§-2 checkpoint's
measurement**, retained as history — they are not a re-measurement at this head,
and this session did not produce one.

The exact manifest the seal pins remains unavailable in this environment:

| field | value |
|---|---|
| `augmentation_manifest_digest` | `c72229789cd417c70eb2533212508b259a9f8df903415f1f6aac710464929328` |
| `augmentation_manifest_file_sha256` | `95aca08407e9508364468fe7be3a373ad0fe6d3e028bb5d0aa79052717542579` |

Regenerating a manifest that merely *hashes* to those values is not possible and
guessing one that plausibly resembles it is not permitted, so the seal check
fails on exactly those two fields against any substitute. That is the correct
outcome, and it must not be softened into a pass.

---

## -2. The independently re-scorable checkpoint (2026-08-01, earlier) — supersedes §-1 below where they differ

Independent verification of the §-1 checkpoint found two defects in the
*measurement*, not in the physics, and one in the B30 admission policy. All
three are corrected forward-only; no cohort was added and none was removed.

### -2.1 A context could leave the measurement silently

The shadow runner walked the corpus with two `continue` statements — one for a
refused projection, one for a bare `except Exception` — and each removed the
context from the run entirely. It left no runtime record, so it was absent from
the snapshot; absent from the snapshot, absent from the scored handle set;
absent from the handle set, absent from the gold index built off that set. A
context that failed was therefore indistinguishable from one that never existed,
and the surviving contexts could carry an acceptance PASS on their own. The
report's zeroes were zeroes about a subset nobody had chosen.

Every context now gets exactly one **ledger** row in a closed vocabulary
(`runtime_completed`, `projection_refused`, `migration_refused`,
`runtime_failed`, `snapshot_rejected`), and the snapshot cannot be frozen unless
those rows account for every expected handle, match the records exactly, and
carry no blocking refusal. The reason catalogue is an enum rather than
`type(exc).__name__`, so an unanticipated exception is a blocking failure by
construction instead of a new key in a counter that acceptance never read. The
gold index is built over the whole corpus rather than over the positions the
snapshot happens to carry — which is what lets the two sets disagree and be
caught disagreeing.

### -2.2 A failed acceptance still exited zero

The runner printed `ACCEPTANCE=FAIL:...` and then `return 0`. Every shell and
CI step reading the exit status was told the measurement had succeeded. Both
phase commands now return 2 on any acceptance failure, from the same
`acceptance_failures` value the scorecard carries — one source of truth for the
printed disposition and the process status.

### -2.3 The stored snapshot could not be re-scored by anyone

What reached disk was the *redacted view*, with the pairing handles stripped,
while the scorer read the in-memory object. The stored artifact could not be
re-loaded as a snapshot, could not recompute its own digest, and was not the
thing that had been measured.

Two artifacts now, with separate models and separate versions. The **full
restricted runtime snapshot** carries handles and answers, re-reads and
re-validates from its own bytes, and is the only input the scorer accepts. The
**public redacted view** carries no handle *in its type*, states
`is_scoring_input: false`, and references the full snapshot's digest rather than
presenting one of its own under that name.

### -2.4 Gold isolation is now process-level

One process held `PublicCorpusCaseV1` objects — which contain `gold` — across
the whole pipeline, so no test could show the runtime phase *could not* have
read an expectation. The run is three commands invoked as separate processes:

```
run_phase56_stage7_v2_shadow_prepare.py   # corpus + manifest -> candidate archive, gold-free bundle
run_phase56_stage7_v2_shadow_runtime.py   # bundle only       -> full snapshot + redacted view
run_phase56_stage7_v2_shadow_score.py     # snapshot from disk + corpus -> scored report, scorecard
```

Phase R's input is a `ShadowRuntimeInputV2`, a type with no field an expected
answer, expected terminal, expected failure code, family, case id or split could
be written into; it never opens the corpus archive. Phase G imports no compiler,
solver or projection, so it cannot re-run the pipeline having seen the gold.

### -2.5 B30: one orientation policy, not two

The planner admitted a horizontal support on two readings — a source-authored
typed frame, *or* a support-owned angle of exactly zero — while the closure, the
compiler contract and the law recognizer read only the frame. An angle-only
Draft planned complete and then reached a closure that refused it. The bare zero
is also exactly what the B15 revocation established is not an orientation: it
names no reference line, so admitting it in the plan re-opened the hole one
stage earlier.

`draft_states_horizontal_support` is now the one reading for every stage, and it
reaches `stated_support_orientation` — the same object the closure binds. A
numeric zero beside a frame is still read as a consistency datum; it can no
longer *be* the orientation, and a frame-less v1 table-pulley record stays
revoked.

### -2.6 The measured result at this exact head

| Figure | Value |
|---|---:|
| Corpus archive SHA-256 | `cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef` |
| Augmentation manifest digest | `c72229789cd417c70eb2533212508b259a9f8df903415f1f6aac710464929328` |
| Candidate archive digest | `c8c33d22c99df9802868ebd36c324f4e77151fd6c2ac01957dee9b695f1500ce` |
| Runtime input digest | `306a4a23933b40e46b61a631040a19d1dca003284e5e83d0b5bf8a3ce7655d7b` |
| Full runtime snapshot digest | `9ad2b05719b3a8ccae4004a3000709e7b40100c3ab571e43aea6f1cebbf2a0dd` |
| Full snapshot file SHA-256 | `076eecdcc1036535b435447e1f6926c779ea43180a03a41ef0e07aeb2fb4fac8` |
| Redacted view file SHA-256 | `5b1ee75104c2efd42b9b37f9eafe68c9b13a3e8844648a110c1edebf04555c5c` |
| Scored report file SHA-256 | `b7b7916f1267e22a3a06e7729e834525c4252560dfbd7fbaea54dc8e7f04d7c1` |
| Scorecard file SHA-256 | `a783fab18d88302ab10c59d6b088e8740b88949ef137cba0b5e2515f14f9a20b` |
| Scorecard digest | `ba12ccf47f7174db5201874e06d0acfb33a3bfc6885a459416a47e2f64c434ca` |
| Public ledger total / scoreable / refused / failed | 100 / 97 / 3 / **0** |
| Missing / unknown / duplicate handles | 0 / 0 / 0 |
| Augmented contexts | 15 |
| Newly solved / correct / wrong / unscored | 9 / **9** / 0 / 0 |
| All shadow correct / wrong / unscored | 50 / 0 / 0 |
| Forbidden-class solves / regressions / query mismatch | 0 / 0 / 0 |
| Cohort yield | 3 |
| Deterministic rebuild | byte-identical across all six artifacts |
| Official status | **not an official score** |

Per cohort, over the 15 augmented contexts:

| Cohort | population | augmented | newly solved | correct | wrong | unscored |
|---|---:|---:|---:|---:|---:|---:|
| Pilot vertical-circle limiting contact | 3 | 3 | 3 | 3 | 0 | 0 |
| B30 table pulley typed frame | 3 | 3 | 3 | 3 | 0 | 0 |
| B31 incline kinetic motion sense | 3 | 3 | 3 | 3 | 0 | 0 |
| B29 horizontal contact free body | 3 | 3 | 0 | 0 | 0 | 0 |
| B32 spring natural-length endpoint | 3 | 3 | 0 | 0 | 0 | 0 |

The B31 correction from §-1.5 is preserved and re-scored: the corrected
3.0790 m/s² is among the nine correct answers, and the 5.2128 m/s² the
up-slope-positive reading produced is not.

### -2.7 The v1 terminal map did not move

The B30 admission got *stricter*, so the question a reader should ask is whether
it took a v1 solve away. It did not, and that is measured rather than argued:
the unaugmented v1 Draft for all 100 public contexts was run at the baseline
commit `70c743b` and at this head, and the two terminal maps are **byte-identical**
(SHA-256 `2896597233738b084ebc2933cdc7c3fc87773ada236d75e328448d206d775f73`).

| Terminal | Count |
|---|---:|
| solved | 41 |
| compiler_failure | 34 |
| verified_unsupported | 12 |
| compiler_unsupported | 8 |
| projection_refused | 3 |
| needs_confirmation | 2 |

The frame-less v1 table-pulley records are among the 34 `compiler_failure`
contexts before and after — still revoked, exactly as the B15 revocation
requires.

### -2.8 Negative controls

Eight deliberate defects, each of which must fail acceptance **and exit 2**:
a wrong answer injected; a newly solved context with no comparable number; a
runtime record deleted; an unknown handle added; the snapshot digest corrupted;
a runtime exception induced in Phase R; a blocked class solved anyway; and a
frame-less support stated only by a zero angle. All eight exited 2. The B30
control is run with the removed angle-only branch restored, so it is shown to
*fire* rather than merely to pass.

### -2.9 What this checkpoint still is not

`STAGE_7_ACCEPTED`, `STAGE_8_READY_TO_START`, `PUBLIC_CORPUS_V2_OFFICIAL` and
`V1_TARGET_REPLACED` are **not** declared. B29 and B32 remain `INCOMPLETE` —
both are capability gaps in the closure catalogue, measured rather than assumed,
and neither is a corpus gap. The official v1 score is unchanged and is never
added to the shadow result:

```
OFFICIAL_V1_SUPPORTED_CORRECT = 41/81
EXPERIMENTAL_V2_SHADOW_NEWLY_SOLVED_CORRECT = 9
```

These are two numbers about two different archives. `50/81` is not a figure this
project has ever measured.

---

## -1. The gold-scored checkpoint (2026-08-01, earlier) — supersedes §0 below where they differ

### -1.1 The shadow measures answers now

Until this session the shadow runner measured whether an augmented context
reached `solved_and_verified` and never compared the number it produced.
`run_shadow_context` took an optional `compare_answer` callback; the public
runner passed none; every solve came back neither correct nor wrong; the
aggregate published `wrong: 0`. That zero meant "nothing was compared" and read
as "nothing was wrong".

Two phases now, and the order is the contract.

*Phase R* projects, compiles, solves and verifies. It reaches no expected
answer, expected terminal, expected failure code, family or case id, and it ends
by sealing every context into a frozen `ShadowRuntimeSnapshotV2` and hashing it.
The record type has no field an expectation could be written into.

*Phase G* opens the gold for the first time, pairs each case to a frozen record
by an opaque handle derived from the archive digest and the context position,
and compares. It holds a snapshot rather than a Draft, so it cannot re-run the
pipeline; a snapshot whose contents no longer match its digest is refused rather
than scored; and the handles are stripped before any artifact is written.

The comparison is `compare_answer_to_gold`, factored out of the official strict
scorer and shared by both callers. There is no v2 comparator, no v2 tolerance
and no v2 unit policy to soften — the shadow scorer carries no float literal, no
`abs`, no `isclose` and no numeric comparison at all, and a test reads that off
its AST.

`ShadowScorecardV2` reports `correct`, `wrong` and `unscored` as three separate
counts, plus `forbidden_class_solve` for a blocked class that solved anyway. A
newly solved context nobody could score fails acceptance; it is not a pass.

### -1.2 Two bypasses closed

**The empty evidence universe.** The unknown-reference check was guarded on the
universe being non-empty, so a context with no source evidence and an
augmentation authoring no quote had an empty universe and every `evidence_refs`
entry passed unexamined. A carrier cites evidence or it is an assertion, and an
unknown reference is unknown whether or not anything else is known.

**`AxisSense` as physics authority.** It is descriptive vocabulary; the typed
`axis(frame, name, sign)` binding is the projection authority. Changing only a
sense leaves the projection identical, a sense never completes a missing
binding, and its one power is refusing a cross-frame binding whose two axes
carry directly opposed senses and a sign that agrees with neither reading.
Senses from different oppositions — world up against a surface normal — are not
compared at all: deciding between them would need geometry this contract does
not carry.

### -1.3 What the contract gained

| Carrier | Change |
|---|---|
| `MotionSenseV2` with no `quantity_id` | projects a **value-free directed motion state**: `raw_value: None`, provenance `unknown`, carrying axis, sign, subject, interval and evidence, and asserting no magnitude |
| slope-tangent motion sense | must use `along_axis_positive`/`along_axis_negative`; `up_slope`/`down_slope` on a self-referentially bound tangent is refused as `slope_sense_requires_axis_relative_statement` |
| axis binding | refused as `axis_sense_contradicts_binding` when two comparable senses disagree with the sign |
| derived authority | a slope-bound tangent sense derives `typed_incline_slide_motion`; **no manifest field can name it**, and the authority bundle still checks the Draft's approved set against what the caller declared |

### -1.4 The measured result

| Figure | Value |
|---|---:|
| Corpus archive SHA-256 | `cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef` |
| Augmentation manifest digest | `4c82ccf1dbfc60679865df952649e7cd1dacaa1a25df49ca1bc6eec73a71725f` |
| Candidate archive SHA-256 | `6cf656a8b2504233802fc4af32a5dffeb7a46afbeb04e76b8d244ec795e32b10` |
| Runtime snapshot digest | `d3b93e9636d55dc6c1f2e08da94d531f096f840e6ef43fbf834238ff8dbbefdd` |
| Scored report file SHA-256 | `604f4c67d5ed8ecbb7cd7405bd59f49344fe8a4b742dcf8314e30464e0e3872b` |
| Scorecard digest | `cf0b2022bc8a06512b2102bc752f49a265f770b9e954dd779d2786c0c72b2087` |
| Augmented contexts | 15 of 97 |
| Newly solved / correct / wrong / unscored | 9 / **9** / 0 / 0 |
| All shadow correct / wrong / unscored | 50 / 0 / 0 |
| Forbidden-class solves / regressions | 0 / 0 |
| Cohort yield | 3 |
| Deterministic rebuild | byte-identical |
| Official status | **not an official score** |

### -1.5 The defect the scorer caught

On B31's first run the shadow reported **three solved, verified, wrong**
answers. `SENSE_SIGN` maps `down_slope` to −1, assuming an up-slope-positive
tangent, while the engine's kinetic-slide law resolves the same axis
down-slope-positive. The slide reached the up-slope formula: 5.2128 m/s² where
the physics gives 3.0790. The pre-B28 runner would have reported "newly solved
3, wrong 0".

The resolution refuses the ambiguity rather than picking a convention, and the
disagreement itself is pinned as a test so it cannot rot silently.

### -1.6 The two walls

`B29_V2_HORIZONTAL_CONTACT_FREE_BODY_INCOMPLETE` and
`B32_V2_SPRING_NATURAL_LENGTH_ENDPOINT_INCOMPLETE`. Both cohorts' carriers were
authored, projected and measured — augmented +6, newly solved +0, regressed 0 —
so neither is a corpus gap.

B29 stops at `_horizontal_surface_contact_profile`, which admits `sticking` (at
rest, applied force, a = 0) and `sliding` (moving, no applied force, no
tangential-acceleration unknown). The B29 shape is moving *with* an applied
force *and* an unknown acceleration, and no law emits `Σ F_t = m a_t` for a
horizontal contact.

B32 stops at the closure catalogue: `ProfileId` has no spring-energy member, and
`_TRANSACTIONS` no spring transaction, though `spring_potential` and
`kinetic_energy` both exist.

Both are capability gaps, not authority gaps.

---

## 0. The corrected checkpoint (2026-08-01, earlier) — supersedes §2, §6 and §7 below


An independent audit found three blocking defects in the first candidate, and
this session corrected them forward-only.  The sections below are kept as
written; where this section contradicts them, this section is the record.

### 0.1 The three defects, corrected

**C1 — the audit misclassified the query objective** (`fix(stage7): trace
source-stated query objectives correctly`).  §2's table says seven engine
carriers have no source field and lists `query_objective` among them.  That was
wrong: the B12 repair already maps the controlled v1 output key
`minimum_speed` onto the Draft's typed `Query.objective = minimum`, and the
official projection has consumed that mapping all along.  The mapping now
lives in one canonical table (`query_objective_sources.py`) consumed by both
the projection and the audit; lookup is exact membership in the closed
vocabulary — no substring reading, no problem-text search, and no `maximum`
member because the v1 vocabulary has no admissible-set-maximum key
(`max_height` is an exact apex readout).  The machine-measured source-contract
omission count is **6**, not the hand-written seven, and the B12 revocation's
remaining blockers — the contact side and the boundary states — are recorded
separately from the objective.

**C2 — augmentation could overwrite v1 meaning** (`fix(stage7): make v2
augmentation fill-only and conflict-safe`).  The first projection wrote a v2
objective, frame binding, direction, or contact side over whatever the v1
Draft already held.  One canonical merge contract (`corpus_v2/merge.py`) now
governs migration and projection alike, decided against the original payload
before anything merges: an empty field may be filled; a semantically identical
restatement is a deterministic no-op that keeps the original record; a
differing restatement fails closed with a closed reason code
(`objective/contact_side/frame_binding/direction/motion_scope/endpoint/
constraint/scalar_encoding _conflicts_with_source`,
`augmentation_would_overwrite_source`); and a narrower or wider scope is a
conflict, never a merge — an event-scoped fact cannot widen to an interval and
an interval fact cannot silently narrow.  A conflicting manifest entry now
fails the migration itself (`augmentation_conflicts_with_source`) before any
candidate archive exists.

**C3 — the frame projection produced shapes the engine never licensed**
(`fix(stage7): project v2 frames as typed axis bindings`).  The first
projection anchored every frame — the world frame included — on a pseudo
entity, emitted `kind=semantic` axis directions, and collapsed opposite senses
onto one value with the sign lost.  Corrected to the engine's own contract: a
stated world frame projects `origin.kind = world` (the v2 record gains an
additive `origin_kind` vocabulary with validation — world origins carry no
point, only the world frame may claim the world anchor, and a world frame may
not have a parent); every v2 axis carries a typed `axis(frame, name, sign)`
binding projected as the engine's `AxisDirection`, with `AxisSense` demoted to
descriptive vocabulary — an incomplete binding is refused
(`axis_binding_missing`), never inferred from spelling; and parity tests pin
the projection to the fully-authored B15 horizontal-support, B16 slope, world
Cartesian and tangential-normal fixtures — equal canonical semantics, with
only generated identifier spelling free to differ.

### 0.2 The compiler hypothesis was measured false — no C4 package

§7 below predicted "a compiler that reads a stated reference frame as
authority to proceed" as the missing piece, from the observation that stated
frames moved three solved contexts to `compiler_unsupported ::
requires_specialized_model`.  Measured against the *corrected* projection,
the compiler needs no change: a correctly projected static world/support frame
pair flows through it without ever raising `requires_specialized_model`
(pinned by `test_phase56_stage7_corpus_v2_static_frame_admission.py`).  The
three regressions were the malformed projection, not a compiler gate.  The
frame-needing horizontal-contact cohort's exact blocker is `compiler_failure
:: underdetermined` — its free-body system lacks normal and friction force
records, which no v2 carrier may state without inventing physics — so what
that family needs is a complete-profile engine package of its own, not a frame
admission change.

### 0.3 Source-quote evidence, and the first closed cohort

The v1 projection materialises evidence records only for quotes the corpus
attached to facts, events and assumptions, so a carrier whose statement lives
elsewhere in the problem text had nothing honest to cite.  The v2 contract
gains `SourceQuoteEvidenceV2`: an authored verbatim quote of the source's own
problem text, aligned at its exact stated occurrence by the projection (or
refused, `evidence_quote_not_in_source`) and re-verified by the engine's own
draft validation.  This is the opposite of the B15 defect — the evidence is
the source text itself, never a minted record.

With it, the **vertical-circle limiting-contact cohort closed** (`engine
(stage7): close the vertical-circle limiting-contact cohort in v2 shadow`).
The source states every authority the B12 revocation found missing: "moves
along the **inside** of the track" (typed contact side, track-relative, no
invented frame), "the least speed that **just maintains contact**" (a
`contact_maintained` interval constraint plus the new
`EndpointCondition.contact_limit` — the boundary/active statement at the
highest-point instant, distinct from `contact_loss`), and the highest point
itself.  The C1-corrected objective arrives from v1.  The existing
`vertical_circle_top_speed` profile and `vertical_circle_top_minimum_speed`
law close it — no new physics, no relaxation, and every ablation (any
authority removed, an outside track, a tampered quote) stays fail-closed.

### 0.4 The corrected shadow checkpoint, measured

All prior out-of-tree artifacts were regenerated at the exact code head; no
prior hash is reused.  Manifest digest
`0e5a8d1162adff6f5b73cd5edc568ff6e4b3afd481134de0be5fc4668fd18534` (3 entries,
authored from source words only) · candidate archive SHA-256
`06bf23a220d3be67cd96027cd9e79e9553dd2195217a0c21cda515c20bbc355e` · shadow
report file SHA-256
`c314b189af73e40bbeeba9106bf1eccd1a1b43e09fd54369120f1b5e297858d7` · scorecard
digest `9618779ccb60071ce446c00ab71765ee19853e604f294d9919d00fcf634ffd1b`.

| Figure | First candidate (§6) | Corrected checkpoint |
|---|---:|---:|
| Contexts evaluated | 97 | 97 |
| Augmented contexts | 22 | 3 |
| Newly solved | 0 | **3** |
| Shadow wrong | 0 | **0** |
| Regressed | 3 | **0** |
| Cohort yield | 0 | **1** |

The regression guard ran in its fail-closed default — no
`--record-regressions` — and two independent rebuilds produced byte-identical
archives and reports.  An empty augmentation still projects to a byte-equal
Draft, unaugmented contexts moved nowhere, and the official v1 score is
unchanged at 41/81 with wrong 0.

The shadow scorecard's `newly_solved` is deliberately answer-blind: the
migration and shadow pipeline never open the gold block, so the three new
solves are verified engine closures whose scalar equals the boundary equality
`sqrt(g r)` on the synthetic pilot fixture, not gold-compared numbers.
`shadow_wrong` is 0 because nothing solved wrongly, and nothing was scored
against an answer at all.

---

## 1. The two scores are different objects

| | Official v1 | Experimental v2 shadow |
|---|---|---|
| Class | `OFFICIAL_V1` | `EXPERIMENTAL_V2_SHADOW` |
| Archive | frozen public corpus, SHA-256 `cc8d8b27…1a1bef` | candidate archive, SHA-256 `2e8ca69f…991c1ff6` |
| Score | supported **41/81**, wrong **0** | newly solved **0**, wrong **0** |
| Status | the project's score | **not** the project's score |

The separation is structural, not editorial. `ShadowScorecardV1` has no field
named like an official metric — no `supported`, no `observed_public_score`, no
`terminal_mapping` — so a shadow number has no official field to be added to.
Every shadow report carries `score_class` and `is_official_score: false`, and
`assert_scores_are_separated` refuses a payload that mixes the two before either
artifact is written.

## 2. Why a v2 contract exists

The executable semantic-preservation audit (B22) measured, over 97 projected
contexts, that **seven engine carriers have no source field anywhere in the v1
corpus contract**:

| Carrier | Contexts that need it | Source fields that could state it |
|---|---:|---|
| `reference_frame` | 34 | none |
| `angle_reference_datum` | 13 | none |
| `frame_axis_direction` | — | none |
| `motion_sense` | — | none |
| `contact_side` | — | none |
| `query_objective` | — | none |
| `quantity_frame_binding` | — | none |

The engine's own `MechanicsProblemDraftV1` has held frames, axis directions,
contact sides and query objectives all along. The gap is in what a case is
allowed to *say*.

The same audit found projection loss of **1 field category across 3 contexts**
and normalization loss of **0**, so the earlier "the projection drops nothing"
is very nearly true and not exactly true — and the residual is three occurrences
of a fact-to-segment binding, not a carrier.

## 3. What the contract adds

Version `dynatutor-ko-corpus-v2.0-candidate`, additive and separate. The v1
loader, schema and strict scoring are untouched; there is no automatic upgrade,
and a v1 record becomes a v2 record only through an explicit migration driven by
a human-authored manifest.

Carriers: reference frames with per-axis direction, angle datums, motion senses,
contact sides, endpoint conditions, constraint authorities, interaction targets,
query objectives, and signed-scalar encodings.

Three rules, each from a revoked closure:

- **Evidence.** `evidence_refs` is non-empty and must point into the source's own
  evidence. B15 minted a binding and then read it back as evidence.
- **Scope.** Every carrier names a subject and either an interval or an event,
  never both. B16 promoted an instant to a whole interval.
- **No defaults.** No default orientation, contact side, endpoint or motion
  sense. A missing carrier is refused.

## 4. What the validator refuses

Twenty-eight typed, privacy-safe rejection reasons. The load-bearing ones:

| Attack | Reason |
|---|---|
| duplicate frame identifier | `duplicate_frame_id` |
| dangling frame parent | `dangling_frame_parent` |
| angle measured from an axis its frame lacks | `angle_datum_axis_unknown` |
| two datums for one angle | `ambiguous_angle_datum` |
| sense with no frame / no such axis | `motion_sense_frame_unknown` / `_axis_unknown` |
| instant sense also stated interval-wide | `event_scoped_sense_used_interval_wide` |
| contact with no normal frame or axis | `contact_side_frame_unknown` / `_axis_unknown` |
| two sides for one contact | `conflicting_contact_sides` |
| endpoint on no event; two endpoints on one boundary | `endpoint_without_event`, `duplicate_endpoint` |
| constraint naming a participant the source lacks | `constraint_without_participants` |
| system-force query with no interaction | `interaction_target_without_interaction` |
| two objectives for one query | `duplicate_query_objective` |
| contradictory double sign | `contradictory_scalar_encoding` |
| carrier scoped to both an instant and a span | `scope_is_both_interval_and_event` |
| authored identifier shadowing a source one | `generated_id_collides_with_authored_id` |

## 5. Migration invariants, measured

- The original v1 record is carried byte-identical and fingerprinted separately
  from its additions.
- Rollback to v1 is total and deterministic.
- A manifest naming any answer-bearing field — expected answer, terminal,
  failure code, reference expression, tolerance, sign convention, solver output —
  is refused by a structural scan at any depth and under any spelling.
- A record with no manifest entry is **not** upgraded; it stays unresolved.
- **Rebuild determinism verified against the public archive**: two independent
  runs produced byte-identical candidate archives and byte-identical shadow
  reports.

## 6. Shadow evaluation result

Manifest SHA-256 `ffdb6312…c05dc893` · candidate archive SHA-256
`2e8ca69f…991c1ff6` · shadow report digest `2e4f9131…257fe4448`.

| Figure | Value |
|---|---:|
| Contexts evaluated | 97 |
| Augmented contexts | 22 |
| Unresolved augmentations | 78 |
| Carrier categories exercised | **5** |
| — `reference_frame` | 16 |
| — `angle_datum` | 13 |
| — `contact_side` | 6 |
| — `endpoint_condition` | 6 |
| — `constraint_authority` | 6 |
| Newly solved | **0** |
| Shadow wrong | **0** |
| Cohort yield | **0** |
| Regressed | **3** |

**No pilot closed, and one carrier is actively unsafe.** Supplying a stated
reference frame — or the angle datum alone — moves three contexts that currently
reach a verified answer to `compiler_unsupported :: requires_specialized_model`.
The compiler treats the presence of a stated frame as a signal that a
specialized model is required, which is the opposite of what the v2 hypothesis
predicted. The regression guard is fail-closed by default; the measurement run
used `--record-regressions` so the evidence exists rather than the run aborting.

`contact_side` and `endpoint_condition` project cleanly, regress nothing, and
unlock nothing on their own.

## 7. What this means

The v2 contract can *state* the seven missing carriers, and the validator refuses
every way of stating them wrongly. That much is done and tested.

What is **not** done is the engine side. A stated frame currently makes the
compiler refuse rather than proceed, so before any of these carriers can yield a
closure the compiler's frame handling has to be the subject of its own package.
That is a Stage 7 engine question, not a corpus question, and this session did
not open it.

Recorded exactly, and not fabricated: the missing piece is a compiler that reads
a stated reference frame as authority to proceed rather than as evidence that a
specialized model is needed.

## 8. What must not be concluded

- The official v1 public score is **41/81** and did not change.
- No v2 number is an official number.
- `PUBLIC_CORPUS_V2_OFFICIAL` is **not** declared; the frozen v1 corpus SHA
  remains the official one and the candidate SHA is experimental.
- `V1_TARGET_REPLACED` is **not** declared.
- `STAGE_7_ACCEPTED` and `STAGE_8_READY_TO_START` are **not** declared.

## 9. Reproducing

```
# official v1, under the dependency lock
backend/tools/run_phase56_stage7_locked_strict.py \
  --commit <exact head> --corpus-archive <archive.zip> --reports <out-of-tree dir>

# the executable census and the semantic audit
backend/tools/run_phase56_stage7_authority_census.py --corpus-archive … --output …
backend/tools/run_phase56_stage7_semantic_preservation.py --corpus-archive … --output …

# the v2 candidate archive and its shadow evaluation, end to end
backend/tools/run_phase56_stage7_v2_shadow.py \
  --corpus-archive … --manifest … --candidate-archive … --runtime-input … \
  --prepare-attestation … --verification-report … \
  --runtime-snapshot … --redacted-view … --shadow-report … --scorecard … \
  --exact-code-head <exact head> \
  --campaign-seal phase56-stage7-v2-public-campaign-v1

# or as the four separate processes it invokes, which is what makes the
# gold-isolation claim checkable rather than merely stated.  The order is
# load-bearing: a preparation that fails Phase V never reaches the pipeline.
backend/tools/run_phase56_stage7_v2_shadow_prepare.py \
  --corpus-archive … --manifest … --candidate-archive … --runtime-input … \
  --prepare-attestation … --exact-code-head <exact head> \
  --campaign-seal phase56-stage7-v2-public-campaign-v1
backend/tools/run_phase56_stage7_v2_shadow_verify_prepare.py \
  --corpus-archive … --manifest … --candidate-archive … --runtime-input … \
  --prepare-attestation … --verification-report … --exact-code-head <exact head> \
  --campaign-seal phase56-stage7-v2-public-campaign-v1
backend/tools/run_phase56_stage7_v2_shadow_runtime.py \
  --runtime-input … --prepare-attestation … \
  --runtime-snapshot … --redacted-view … --exact-code-head <exact head>
backend/tools/run_phase56_stage7_v2_shadow_score.py \
  --corpus-archive … --runtime-snapshot … --prepare-attestation … \
  --shadow-report … --scorecard … --expected-code-head <exact head> \
  --campaign-seal phase56-stage7-v2-public-campaign-v1

# the read-only adversary, which executes the attacks rather than reading the
# code and being satisfied
backend/tools/run_phase56_stage7_b28a_readonly_checker.py --report …
```

`--campaign-seal` is not optional in practice: an attestation that names no
campaign fails the seal under `campaign_seal_absent_from_attestation`, so
declining to name one is itself a refusal rather than a way around it.

Every command exits 0 only when its own acceptance passes, and 2 otherwise.

All artifacts stay out of the repository. The corpus, the manifest, the candidate
archive, the runtime input bundle, the full restricted snapshot, the redacted
view, both reports and the scorecard are never committed.
