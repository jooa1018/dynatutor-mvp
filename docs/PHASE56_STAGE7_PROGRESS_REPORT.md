# Phase 56 Stage 7 progress report

Disposition: **`STAGE_7_IN_PROGRESS / BLOCKED_ON_PUBLIC_CORPUS_AVAILABILITY`**

Stage 7 is **not** accepted. Stage 8 has **not** been started. PR #16 and PR #17
remain open, Draft, and unmerged, and `main` is unchanged at
`00b3a60de6e13756d089655879a02e4094122047`.

## Exact heads

| Role | SHA |
|---|---|
| Main baseline | `00b3a60de6e13756d089655879a02e4094122047` |
| Phase 55 base | `4762727e8f9191604e2531b9982a5ae72ed73db9` |
| Stage 6 code candidate | `58589ad49982871e7d617489b525e9b67428548a` |
| Stage 6 documentation head | `1f05e6cdfab8dd68dd3b76294618477e2761ddd3` |
| Stage 7 preflight checkpoint | `2512c6631acd691b2ad5033f86d8b9cc2c1088dd` |
| Corpus integrity package | `612634bc25b120c25903580d4f26b82f1de94250` |
| Gold-isolation package | `e1c79af201747168b609eb6283305abf1cc2e296` |
| Permanent offline workflow | `a4995799c097e0b36d5c60d671c40b1765b1993d` |

Each package was committed atomically and fast-forward pushed to
`codex/phase56-generic-mechanics-engine`. No reset, rebase, force-push, or
history rewrite occurred.

## Entry gates reconfirmed against the remote

- PR #17 open, Draft, unmerged, base `codex/phase55-gpt-first-textbook-parser`.
- PR #16 open, Draft, unmerged, base `main`.
- Stage 6 code candidate `58589ad…`: release `30045176722`, Phase 55
  `30045176496`, Stage 6 multimodal `30045176628` — all **SUCCESS**.
- Stage 7 preflight head `2512c66…`: release `30049919989`, Phase 55
  `30049920103`, Stage 6 multimodal `30049919985` — all **SUCCESS**, with
  `live-openai-smoke` **skipped**, which is the positive evidence that no Live
  call occurred at that head.

## Blocking limitation — the authorised public archive is unavailable

`dynatutor_beer12_ko_corpus_v1_public.zip` is **not present in this execution
environment**, and neither are the two instruction documents. The whole
filesystem was searched. Consequently:

- **`public_dev` 84, `public_adversarial` 16, and the public total of 100 were
  NOT EXECUTED.** No supported/deferred/blocked accuracy figure is claimed.
- Lane B, Lane C, Lane D, and Lane E end-to-end corpus runs are **NOT_RUN**.
- The compositional 12, synthetic 38, and metamorphic suites over corpus
  material are **NOT_RUN**.

The corpus-independent contract, security, isolation, and integrity work is
complete and verified; it is reported separately below and must never be read
as public-corpus evidence.

The archive is deliberately not committed to the repository and not stored in a
GitHub secret. The permanent workflow accepts it only through
`STAGE7_PUBLIC_CORPUS_PATH`, and reports `NOT_RUN` when it is absent rather
than claiming an unexecuted pass.

## Completed and verified — Lane A corpus integrity

`backend/evaluation/phase56_stage7/corpus_integrity.py`,
`corpus_records.py`, `corpus_semantics.py`, `corpus_preflight.py`.

Archive layer: expected SHA-256, ZIP magic, archive byte limit, entry-count
limit, per-entry and total uncompressed limits, compression-ratio limit, path
traversal, absolute path, `..` component, drive/UNC, directory, symlink,
device, forged-link-payload, duplicate name, case-insensitive duplicate name,
member allowlist, forbidden private names, encrypted entry, unsupported
compression method, forged declared size, nested archive, and UTF-8 validation.

Members are read in memory only. `extract` and `extractall` are never called,
and a structural audit fails the build if they ever are, so no archive member
can materialise a link, a device node, or a traversed path on disk.

Record layer: corpus keys bind through an alias contract that must resolve
unambiguously per record, consistently across records, and only to fields the
archive's own `schema.json` declares. Ambiguity, drift, and undeclared keys
fail closed rather than binding the wrong column. JSON, JSONL framing, record
shape, non-finite numbers, and private-marker keys are rejected.

Semantic layer: unique case IDs, unique problem texts, valid problem hashes,
disjoint splits, Korean problem text, evidence quotes present in the problem
text, fact values present in the evidence quotes, finite reference answers,
required gold fields, blocked cases carrying no answer, private-manifest
keys-only absence audit, and manifest / validation-report cross-checks.

Scope-adjusted distribution is **derived**, never hardcoded: the only scope
input is the frozen four deferred families, and the derived counts must equal
the frozen `81 / 12 / 2 / 2 / 2 / 1` contract totalling 100. No case ID, split,
chapter, or filename participates. Current course scope overrides an older
corpus-declared terminal, which is covered by a dedicated regression.

Every integrity failure terminates as `HARNESS_CONTRACT_FAILURE` with runtime,
compiler, solver, and provider calls all `0` and cost `$0`, carrying only a
closed sanitized reason with no corpus content.

## Completed and verified — gold/runtime isolation

`backend/evaluation/phase56_stage7/evaluator_adapter.py` is the single
authorised crossing. It projects a gold case down to user-like problem text
only; case ID, split, family, chapter, declared terminal, gold facts, evidence
quotes, and the reference answer never cross.

Execution tokens derive from a run nonce and a monotonic counter, never from
case identity, and stay excluded from cache identity. Rebinding a result to its
gold case re-verifies both the token and the cache digest, so a scorer cannot
substitute an execution, mutate a frozen snapshot, or re-run runtime with
expected data.

Attack coverage: direct forbidden field, nested forbidden field at depth,
snake/camel/kebab/spaced aliases, case-ID routing, family/split/chapter/
declared-terminal routing, expected-answer lookup, filename and path routing,
cache-key contamination, prompt-material contamination, environment
contamination, substituted execution, unbound token, and blocked-terminal
answer carriage. Structural audits prove production modules cannot import the
evaluator, gold-domain modules cannot import an executing or network subsystem,
and `runtime_domain` never references gold or corpus modules.

## Completed and verified — permanent offline workflow

`.github/workflows/phase56-stage7-offline-evaluation.yml` plus
`backend/tools/run_phase56_stage7_offline_gate.py`.

The workflow holds `contents: read` only and never pushes, commits, dispatches
a finalizer, modifies itself, reads a secret, deploys, or names private or
full-corpus material. It forces empty `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
and all provider base URLs. Dependencies install before the guard; corpus
integrity, gold isolation, and the contract preflight then run behind a
fail-fast socket guard, before any regression executes. A before/after worktree
diff proves the gate mutated no source. Only the redacted aggregate artifact is
uploaded, and it passes the Stage 7 redaction contract before it is written, so
a redaction failure blocks report generation instead of leaking.

## Test evidence

| Suite | Result |
|---|---|
| `test_phase56_stage7_preflight_contracts.py` | 38 passed |
| `test_phase56_stage7_corpus_integrity.py` | 80 passed |
| `test_phase56_stage7_gold_isolation.py` | 44 passed |
| `test_phase56_stage7_offline_workflow.py` | 19 passed |
| Stage 7 focused total | **181 passed** |
| Full backend collection | 3571 tests collected, no errors |

No test was deleted, no assertion was weakened, and no threshold was relaxed.
The Pydantic `schema` shadowing warnings are pre-existing and are not failures;
the frozen contract was not redesigned to silence them.

## Exact-head CI evidence for `a4995799…`

| Workflow | Run | Result |
|---|---:|---|
| Phase 56 Stage 7 offline evaluation (pull_request) | `30148547712` | **SUCCESS** |
| Phase 56 Stage 7 offline evaluation (push) | `30148546200` | **SUCCESS** |

Within the Stage 7 run: backend compile, the Stage 7 offline gate, Stage 7
focused contracts, Stage 6 multimodal regression, full backend collection, full
backend regression, the no-source-mutation assertion, and the redacted-artifact
upload all succeeded, as did the frontend tests, lint, typecheck, and
production build. `live-openai-smoke` remained **skipped** at this head, which
is positive evidence that no Live call occurred.

### Local reproduction note

A local full-regression pass on this container initially reported two failures.
Both were traced to this sandbox, not to the code:

- `test_phase56_stage6_api_runtime_integration.py::test_openapi_registers_stage6_routes_exactly_once_and_unconfigured_is_typed_503`
  failed only under unpinned FastAPI 0.140.0 / Starlette 1.3.1; it passes under
  the locked `fastapi==0.128.2`.
- `test_phase41_followup.py::test_backend_benchmark_wrapper_returns_after_real_pytest_summary`
  failed only because a uv-managed `/root/.local/bin/pytest` without the project
  dependencies shadowed the project interpreter on `PATH`; it passes once the
  project `pytest` resolves first.

CI installs `backend/requirements-lock.txt` and passed both tests at this exact
head. No test or threshold was modified in response.

After pinning `fastapi==0.128.2` and restoring the project interpreter on
`PATH`, the local full backend regression reported **3203 passed, 1 skipped,
430 deselected, 0 failed**. That run executed at documentation head
`fdc884bf…`, whose `backend/` and `.github/` trees are byte-identical to the
code candidate `a4995799…`.

### Head accounting

- Code candidate / tested head: `a4995799c097e0b36d5c60d671c40b1765b1993d`
- Documentation head: `fdc884bf0ff9c4ac21de642014fb15623a4f9134` and later
- No accepted head exists: Stage 7 is not accepted.

CI evidence above belongs to `a4995799…` and must not be re-attributed to a
later documentation-only head.

## Read-only audit (same-model, not an independent Checker)

Scope and result — blocking findings **0**:

| Audited property | Result |
|---|---|
| Diff since `2512c66…` is additive | 11 files added; only `PHASE56_CLAUDE_CODE_HANDOFF.md` modified |
| Frozen contract/runtime/gold/preflight/redaction modules and the 38-test preflight suite | untouched |
| Case-ID / family / split / filename routing in new code | none; the sole `case_id` use is a gold-domain uniqueness cardinality check |
| Expected-answer use | only inside the leak *detector* that proves its absence from runtime material |
| Adapter payload to runtime | exactly token, input kind, problem text, options |
| Network or provider imports in the evaluator package | only `socket` inside `network_guard`, which is the guard itself |
| Threshold relaxation | no removed threshold or assertion lines |
| Test deletion | none |
| Raw corpus, private material, ZIP, or PDF committed | none |
| Workflow push / commit / secret / self-mutation | none; `contents: read` only |
| Report privacy in practice | exactly one 830-byte redacted artifact uploaded |
| main / PR protection | main `00b3a60…` unchanged; PR #16 and #17 open, Draft, unmerged |

## Hard-safety and privacy status

| Signal | Status |
|---|---|
| External model calls | 0 |
| Measured cost | $0 |
| Private held-out access | 0 |
| Textbook PDF access | 0 |
| Raw corpus committed | no |
| Gold leakage in runtime material | 0 (enforced and tested) |
| Case-ID / family / filename routing | 0 (enforced and tested) |
| Actual model quality | `NOT_RUN / N/A` |

These counts describe the corpus-independent lanes that actually ran. They are
not a public-100 result.

## Next exact task

Supply the authorised archive to a runner as
`STAGE7_PUBLIC_CORPUS_PATH=/path/to/dynatutor_beer12_ko_corpus_v1_public.zip`
and run:

```bash
python backend/tools/run_phase56_stage7_offline_gate.py \
  --output "$RUNNER_TEMP/stage7_offline_gate_report.json"
```

A passing corpus gate confirms the archive SHA-256, the 84/16/100 splits, and
the derived `81/12/2/2/2/1` scope distribution. Only then may Lane B execution,
the compositional 12, the synthetic 38, metamorphic controls, the API/runtime
lane, and the frontend lane proceed.

Stage 8 must not start.
