# Phase 52 cross-engine observability

## Goal and boundary

Phase 52 makes parser-to-offline-engine decisions observable and gives release CI deterministic, machine-checkable accuracy, reproducibility, and performance evidence. It does not change the normal `/solve` response schema or make SciPy/PyChrono part of the user-response critical path.

Supported in this phase:

- one-pass product pipeline traces for Phase 42 golden requests;
- analytic/SciPy normalization from the accepted Phase 50 runner;
- analytic/product/PyChrono normalization from the accepted Phase 51 runner;
- deterministic JSON and Markdown cross-engine reports;
- a separate stage-performance artifact;
- PR fast, PR extended, and strict nightly quality tiers;
- an exact eight-metric release dashboard and explicit gate reasons.

Not supported in this phase:

- production telemetry, arbitrary user traffic, or storing raw problem/student text;
- changing physics, solver selection, tolerances, app routes, or API schemas;
- duplicating the parent-vs-head pooled performance measurement owned by Release CI;
- frontend visualization or any Phase 53/54 contract or implementation.

## Trace contract

Wave 1 defines the immutable trace in `engine.observability.contracts` and `engine.observability.trace`. A case-derived `request_id` connects:

1. input hash and length;
2. normalization rule IDs;
3. parse candidates and canonical fingerprint;
4. clarification and route decisions;
5. legacy and typed model fingerprints;
6. equation IDs and solution candidates;
7. validation decision and numeric checks;
8. hashed student-answer presence metadata and final answer projection.

The product is called exactly once for each collector instance. Collection never invokes an extra parser, router, solver, or validator solely to populate a trace. The four exclusive stage boundaries are `parse`, `route`, `solve`, and `verify`.

Raw problem text, normalized text, matched extraction text, student solution, free-form exception messages, and other human text are not report fields. Only hash, length, bounded IDs, finite numeric evidence, and allowlisted settings are persisted. Normal `/solve` behavior is fail-open when optional trace instrumentation fails, and its response remains unchanged.

Before a trace enters the core, Phase 52 recursively validates the complete Wave 1 schema: the root and every nested version/input/candidate/model/equation/validation/answer/stage/error object must contain exactly its allowlisted keys. Unknown containers such as `detail` are rejected even when their key itself is not on the sensitive-name denylist. This prevents raw or student text from being hidden below an otherwise unknown extension field.

## Deterministic core and performance artifact

The core and performance evidence are physically separate files.

The immutable core contains:

- schema/report/source versions and the exact 40-character source commit;
- privacy-safe trace snapshots;
- normalized cross-engine cases;
- numeric dashboard source aggregates;
- the code-owned expected-skip manifest.

It contains no timing, timestamp, random value, platform string, artifact digest, or generated filename. Stable JSON uses sorted keys, compact separators, UTF-8, LF, and `allow_nan=False`. Two independent collections at the same commit/settings compare the canonical core bytes.

The volatile performance artifact contains:

- schema and performance versions;
- source commit and tier;
- stable case IDs and fixed repeat count;
- raw finite millisecond samples for each of `parse`, `route`, `solve`, and `verify`;
- per-stage and end-to-end nearest-rank P50/P95/worst;
- overall mean/P95/worst;
- the historical and absolute budget values.

The final report references the performance artifact by basename, schema version, and SHA-256 of the exact LF-normalized canonical file. Rendering the same immutable core and performance file twice is byte-identical for both JSON and Markdown. Changing or reformatting the performance file invalidates its digest contract.

Validation does not trust summary fields. It recomputes sample cardinality, fixed repeats, ordered unique case IDs, every per-case stage and end-to-end P50/P95/worst, all overall stage statistics, and overall mean/P50/P95/worst from raw finite samples. It also requires the accepted baseline and ceilings exactly. Lowering a summary while leaving slow raw samples therefore cannot bypass the performance gate.

## CrossEngineReport schema

Schema/version: `1` / `phase52-cross-engine-report-v1`.

Every normalized case has exactly these required fields:

| Field | Meaning |
|---|---|
| `case_id` | Stable accepted Phase 50/51 case ID |
| `reference_path` | Independent reference, normally `analytic` |
| `candidate_paths` | Ordered candidate engines, such as `scipy` or `product, pychrono` |
| `values_and_units` | Bounded reference/candidate numeric values and units |
| `absolute_relative_errors` | Absolute/relative observations and tolerances |
| `invariant_checks` | Stable check IDs and boolean outcomes |
| `assumptions` | Bounded modeling assumptions, not raw problem text |
| `engine_settings` | Integration/contact/solver settings needed to reproduce the case |
| `runtime` | Engine identifier and actual engine version evidence |
| `status` | One of the seven values below |

The exact status values and meanings are:

- `passed`: numeric and invariant evidence agrees;
- `passed_with_warning`: agreement holds with a bounded warning;
- `disagreement`: numeric tolerance or invariant agreement fails;
- `inconclusive`: required evidence is insufficient;
- `skipped`: and only when a declared dependency/capability is absent;
- `unsupported`: the installed engine does not implement the case or physics;
- `error`: an installed runtime throws, fails initialization/version checks, or otherwise cannot execute.

Only `ModuleNotFoundError` naming the declared module/capability is classified as dependency absence by the generic classifier. An unrelated import error, an installed-engine exception, a version/init failure, or a free-form `missing_dependency`, `unavailable`, or `skipped` payload claim is `error`, never `skipped`.

The dedicated Phase 51 normalizer may accept serialized absence only when all code-owned provenance agrees: report schema `1`, report version `phase51-pychrono-report-v1`, `chrono_version=unavailable`, and a `not_initialized` solver. It preserves the accepted result's `modeling_assumptions`, top-level `time_step`/`solver`/`contact_method`, and the allowlisted initial `time_step_s`, `solver_max_iterations`, `collision_envelope_m`, and `collision_safe_margin_m`. Product problem/display strings, warning/exception messages, platform timing, and other source-report free text are discarded.

Phase 50 invariant results come from the accepted policy checks, not a raw analytic boolean: invariant drift maps to `energy_policy_passed`, constraint violation to `constraint_policy_passed`, and analytic agreement to `analytic_contract_passed`. Thus the accepted large-angle expected-difference case is not mislabeled as a residual failure.

## Version evidence

Every core records:

- canonical schema version;
- legacy and typed physical-model schema versions;
- solver pipeline version;
- verification tolerance and numeric policy versions;
- benchmark, trace, report, and performance versions;
- actual SymPy, SciPy, and PyChrono versions (null only when unavailable in that tier);
- exact git commit;
- an LLM identifier only when explicitly supplied by the caller.

Platform and transient environment descriptions are intentionally excluded from deterministic core comparison.

## Expected skips and strict nightly

Expected skips are a static code-owned manifest keyed by tier, engine, and case. A runtime result cannot add to or widen it.

- Fast does not require offline cross-engine execution.
- Extended may report declared PyChrono absence as expected because the pinned PyChrono environment is separate.
- Nightly has no expected SciPy or PyChrono skips. It requires each unique `(engine, case_id)` exactly once and requires every one of those 13 pairs to have status `passed` or `passed_with_warning`. The SciPy set is `pendulum_small_angle_accuracy`, `pendulum_large_angle_expected_difference`, `pendulum_equilibrium_hold`, `spring_undamped_accuracy`, `spring_underdamped_accuracy`, `spring_critical_accuracy`, and `spring_overdamped_accuracy`. The PyChrono set is `rolling_sphere`, `rolling_disk`, `incline_friction_slip`, `incline_friction_stick`, `collision_restitution`, and `massive_pulley`. Missing, additional, duplicate, `inconclusive`, `skipped`, `unsupported`, `error`, `disagreement`, or any other non-success status fails strict nightly with a pair-specific reason.

## Performance budgets and gate ownership

The accepted Phase 42 GitHub Actions reference is mean `9.458354 ms` and P95 `32.092011 ms`. Phase 52 retains the existing absolute ceilings:

- mean at most `60 ms`;
- P95 at most `120 ms`.

Stage parse/route/solve/verify P50, P95, and worst values are recorded for diagnosis. Phase 52 invents no independent stage thresholds.

The maximum `15%` parent-vs-head pooled regression check remains external evidence owned by the existing Release exact-HEAD workflow. Phase 52 never duplicates or fabricates that measurement. A final strict report must receive `--pooled-performance-gate passed`; without it the external gate is explicitly `inconclusive` and Phase completion cannot be claimed.

## Release dashboard

The JSON and Markdown reports contain exactly eight metrics:

1. `golden_answer_pass_rate`: passed / total traced Phase 42 golden requests;
2. `false_solve_rate`: false solves / evaluated negative cases;
3. `clarification_precision_recall`: precision is `crafted_rule_ok / (crafted_rule_ok + fp)` and recall is `crafted_fired / crafted_total`, with every numerator and denominator recorded;
4. `routing_accuracy`: correct / total from the accepted routing report;
5. `residual_invariant_failure_count`: failed normalized residual/invariant checks;
6. `cross_engine_disagreement_count`: cases with `disagreement` status;
7. `p95_fast_path_latency_ms`: current performance artifact P95 and sample count;
8. `flaky_test_count`: current run only, with no historical-flakiness claim.

Only numeric aggregates are read from `backend/reports/routing_confusion/report.json` and accepted Phase 44/49/50/51 outputs. Raw problems are never copied into a Phase 52 report.

## Runner interface

Run from `backend` with `PYTHONPATH=.`:

```bash
python tools/run_phase52_observability.py collect \
  --source-commit "$GITHUB_SHA" \
  --tier extended \
  --repeats 2 \
  --core-out "$RUNNER_TEMP/phase52-core.json" \
  --performance-out "$RUNNER_TEMP/phase52-performance.json"

python tools/run_phase52_observability.py render \
  --core "$RUNNER_TEMP/phase52-core.json" \
  --performance "$RUNNER_TEMP/phase52-performance.json" \
  --json-out "$RUNNER_TEMP/phase52-report.json" \
  --markdown-out "$RUNNER_TEMP/phase52-report.md" \
  --pooled-performance-gate inconclusive

python tools/run_phase52_observability.py validate \
  --core "$RUNNER_TEMP/phase52-core.json" \
  --performance "$RUNNER_TEMP/phase52-performance.json" \
  --json-report "$RUNNER_TEMP/phase52-report.json" \
  --pooled-performance-gate inconclusive
```

`collect` requires `--source-commit` and a tier, and writes only atomic LF-normalized files. `--seed 5200` is a fixed compatibility input; collection performs no random sampling. `render` verifies schema, source/tier equality, canonical performance bytes, and the artifact digest before writing. `validate` reconstructs the expected report from the immutable inputs and rejects field/status/schema/finite/digest/tier/gate violations. `--strict` additionally requires a passing gate; strict nightly therefore requires real engines and `--pooled-performance-gate passed`.

## CI tiers

`.github/workflows/phase52-quality.yml` runs only targeted Phase 52 evidence and does not repeat the existing complete Release/frontend/wrapper/pooled suite.

- PR and work-branch pushes run fast and extended in parallel when Phase 52 paths change.
- `workflow_dispatch` accepts `fast`, `extended`, or `nightly`.
- The schedule and explicit nightly dispatch use the pinned Phase 51 micromamba environment and real PyChrono.
- Every job verifies that checkout `HEAD` exactly equals the event/dispatch source SHA.
- Fast covers Phase 52 focused tests plus targeted parser/route/solver/validator/golden/API contracts.
- Extended covers curated NLP, metamorphic, analytic consistency, short SciPy, and the Phase 52 runner with the declared PyChrono absence policy.
- Nightly covers all SciPy cases and the real six Phase 51 scenes, collects twice and compares core bytes, renders the same selected evidence twice in separate processes and compares JSON/Markdown, validates strictly, and uploads core/performance/JSON/Markdown for 30 days.

PR jobs may upload targeted artifacts. They pass `inconclusive` for the external pooled gate and must not claim final Phase acceptance. Only Release CI supplies the independent parent-vs-head pooled evidence. Nightly accepts that evidence only from a successful `pull_request` Release workflow run at the exact Phase 52 SHA and only after the Release `test` job's `Compare pooled PR10 hotfix performance` step is independently confirmed successful. A successful push or `workflow_dispatch` Release run is never accepted as pooled parent-vs-head evidence; absence of the exact PR step fails closed.

## Artifacts and rollback

Generated reports live under a temporary or `backend/reports/generated` path and are not committed by the workflow. CI uploads them as immutable Actions artifacts with a 30-day retention window.

Rollback is deletion/reversion of these six Phase 52 Wave 2 files. Wave 1 trace contracts and the normal solve/API/frontend paths remain independently usable and unchanged. No generated report, cache, database, external deployment, or user answer is modified by rollback.
