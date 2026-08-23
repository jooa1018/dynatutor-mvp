# Checkpoint - Phase 56 completion - 2026-08-23 07:05 Asia/Seoul

## The story so far

The distinct supplemental campaign is frozen under manifest digest `32aa3ce51e3006e533913b2f822251d22dccba2a379a35008f19e7a7e1aef7cd` and seal `phase56-stage7-v2-supplemental-yield-campaign-v1`. Its portable exact-byte pre-change baseline at `51a9c68` was 41 all-correct, zero wrong/unscored/regressed, and cohort yield zero.

Commit `69d7b08` added generic typed banked/flat curve invariants and event-scoped instantaneous-centre support. Exact supplemental measurement at that head passed M -> V -> R -> G with four of six augmented cases newly solved and correct. The two remaining instantaneous-centre cases exposed a corpus-independent compiler defect: constraint scope depended on content-hash equation ordering. Commit `7794168734321be78b6fa54373bf20a6938d4bd4` fixes this by anchoring an exact instantaneous-centre constraint to its typed body-scope equation, with order-variant regressions. Focused B10/instantaneous-centre verification passed 56 tests including slow tests, and adjacent compiler/solver verification passed 175 tests.

At exact clean head `7794168`, the unchanged sealed supplemental M -> V -> R -> G transaction passed: 100 expected/accounted, 97 runtime-completed, 3 projection-refused, 6 carrier-augmented, 6 newly solved and all 6 correct, 50 all-shadow correct, zero wrong/unscored/regressed, and cohort yield 2. Relative to the locked pre-change baseline, the same frozen population improved from 41 to 50 correct (`+9`) with no regression. Publication ID is `e67098ab596907c965ae1e312be1bc73c17a1e0ae83df64b3a4367fccc759746`; runtime, redacted, shadow, and scorecard file SHA-256 values are respectively `14c217f089d0c7aa5c9780854bf876b1bceada88469b087379636f5aa9bf8c31`, `ca85b703b0a4f37c7621a71513f4c16a70a13cce3915bb1eedf429ad169d9c5f`, `00ecaee13e89fd4a3ada64d8b46352f194b07a9260b20b7c083c1757f9c81adc`, and `da4ee952113fd4bee57b7110bb9c95d104773608a1f11cadea21c1fefdf57242`.

The locked official-v1 run at `5bd1b3a` remains the latest official measurement: 44/81 supported correct, 0 wrong, 0 solved-but-unscored, 12/12 deferred, terminal mapping 61/100, all 23 hard-safety signals measured and zero, and Lane C/D/E PASS. Its strict inner exit is 2 because 37 supported and 2 unsupported-other cases remain unresolved. B28A passed 24 read-only checks. The supplemental campaign is separate evidence and does not replace the unavailable historical augmentation manifest. Stage 7 therefore remains `IN_PROGRESS / NOT_ACCEPTED`; Stage 8 remains `NOT_STARTED`.

## Decided

- D-001 - use the Ballast durable memory structure.
- D-002 - execute Phase 56 autonomously to evidence-backed COMPLETE or genuine external BLOCKED while preserving all authority and safety gates.
- The historical exact augmentation manifest remains unavailable and is not reconstructed or replaced. Supplemental evidence is labeled separately and cannot create historical acceptance.

## Waiting on the user

None. Routine reversible choices are delegated by D-002; one-way external actions remain outside authority.

## Next first action

Commit and push this exact-head evidence checkpoint, then re-read the current Stage 7 package/disposition criteria against the now-complete supplemental `+9` result. Continue only with general typed capabilities or terminal classifications justified by source/runtime evidence; do not inspect or start Stage 8 while Stage 7 remains not accepted.

## Tried

- The first instantaneous-centre implementation solved one of three selected cases. Gold-free runtime diagnostics showed the difference was hash-order-dependent constraint scoping, not physical data or a corpus-specific exception.
- Exact-head remeasurement after the order-independence fix used the unchanged manifest, seal, population, canonical scorer, thresholds, and gold boundary. It achieved all nine pre-change-to-final gains required by the supplemental target with zero regression.
- Official strict exit 2 remains an honest acceptance failure, not an execution failure. Safety/regression lanes pass; supported/unsupported terminal coverage and the derived 100% metrics remain incomplete.
