# License notices and modification notes

Phase 13 adds physics-core modules, solver refactors, and derived benchmark
scaffolds. No license-less GitHub code was copied.

## Dependencies

DynaTutor relies on package-manager-installed dependencies such as FastAPI,
SymPy, Pint, NumPy, SciPy, PyDy, Next.js, and React. Their source code is not
vendored into this repository.

## Adapted/derived educational content

- No original FOSSEE/OpenStax/MIT OCW problem text is copied into the app UI.
- Benchmark cases are written as DynaTutor-derived Korean test problems with
  changed wording/numbers and source-family notes.
- If future contributors port an example more directly, they must add:
  source URL, license, original title, modified files, and modification summary.

## LLM policy

LLM output is explanatory only. Solver equations, numeric results, and units are
locked facts and must not be modified by LLM output.


## Phase 19 adapter note

No PyDy example code was copied. The SymPy Mechanics/PyDy adapter code in
`backend/engine/adapters/` is original DynaTutor wrapper code that uses installed
library APIs. PyDy remains optional at runtime.


## Phase 20 benchmark note

Phase 20 adds derived-style benchmark cases labeled with OpenStax/FOSSEE/MIT OCW
source families. These cases are not copied source problems. They use original
DynaTutor-generated Korean wording, changed numerical parameters, and internal
expected-answer or solver-oracle checks for regression testing.


## Phase 21 Chrono validation note

Phase 21 adds a DynaTutor-created offline validation harness for Project
Chrono/PyChrono. PyChrono is not vendored and is not a normal runtime
dependency. The current build environment did not have PyChrono installed, so
automated tests validate analytic references and safe PyChrono skip/manual
hooks rather than claiming a Chrono numerical simulation was executed.


## Phase 22 LLM guardrail note

Phase 22 does not add external LLM-generated solution content. The LLM layer is
restricted to explaining DynaTutor's locked solver facts. Solver outputs,
equations, numeric answers, unsupported decisions, and not-applicable equations
remain deterministic DynaTutor data.
