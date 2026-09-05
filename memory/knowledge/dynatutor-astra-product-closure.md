# DynaTutor product closure checkpoint

Date: 2026-09-05. Status: **INCOMPLETE**; not a personal-use or release claim.
Branch: `codex/dynatutor-astra-product-closure`, integration target:
`codex/phase57-reproducible-public-evaluation`. PR #49 stays Draft/unmerged.
Parent/checkpoint: `054d3641568b5b3425009b5c46c07cc3633a841e`.

## Observed defect and bounded fix

The original `frontend/components/HomeClient.tsx` blob
`27120b98ec85c6709b3c5379ac6e98f0003194ae` was copied and its Git blob hash
verified locally before modification. A late solve response restored its old
problem text; editing a completed problem left its old result/save action visible;
old finally/error/feedback/AI callbacks could mutate a newer run. Notebook save
used editable fields rather than a snapshot bound to the displayed result.

The patch adds frontend-only request ownership refs, synchronous duplicate-click
suppression, input-change invalidation and result-bound save snapshots. It does
not create a solver authority or change backend statuses, receipts, tolerances,
public populations, model/provider settings, attempt DAGs or Phase 56 contracts.

## Executed local evidence

`node --test tests/homeClientRunIdentity.test.js`, from `frontend/`:
original source: 12 tests, 2 passed / 10 failed;
patched source: 12 tests, 12 passed / 0 failed, none skipped.
These execute the real transpiled HomeClient handlers with controlled hook/API/
timer doubles. They are **not** React DOM, browser, mathematical, fresh public,
provider or MVRG evidence. Local Node was 22.16.0, not the repository's Node 20;
full lockfile install, typecheck/lint/build and regression checks require CI.
No independent reviewer or subagent was used; performance was not measured.

## Current boundary and next execution

The isolated closure workflow uses Node 20 and the existing npm commands, plus
the existing Python 3.11 locked Phase 57 exact-head campaign and identity verifier.
No acceptance criteria or fixed public population are changed. It uploads only
public aggregate evaluation JSON. Its separate runtime artifact contains built
frontend assets and public backend app/engine source, no private/gold case data or
provider credentials, for actual local browser verification. An uploaded build
artifact is not a deployed Preview or an E2E pass. CI results must be read for the
actual final SHA; no result is predeclared here.

Observed: raw Git tree/commit reads and some normalized PR/log responses in this
session disagreed about the same SHA (frontend/backend versus root TypeScript,
August versus July metadata). Do not promote the supplied historical 50/31 or
63/18 counts to a fresh result. Use immutable Git objects and downloaded,
identity-verified exact-head artifacts to settle evaluation identity.

NOT_RUN here: formal real-study MVRG, actual provider call, full product browser
flow and nonproduction Preview E2E. Render workspace selection awaits the user's
confirmation requested in this session; it has not been silently selected. The
connected Vercel team lists HarmonyMaker, not DynaTutor. Existing Render YAML is
production-configured; it has not been changed or deployed. No usable Preview URL
or readiness claim is established.

Next: inspect exact-head closure/release CI; obtain the verified runtime artifact,
execute the real local product flow and inspect fresh public aggregates; resolve
Preview permissions/configuration separately. Keep remaining supported failures
and unmet MVRG requirements visible. Rollback is an additive revert of this
isolated change; no force-push, reset, merge or production action is authorized.
