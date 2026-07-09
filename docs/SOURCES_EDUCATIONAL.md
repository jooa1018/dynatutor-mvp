# Educational source families

DynaTutor uses educational source families only as human-auditable references
for derived tests and solver design. It does not send copyrighted problem banks
to an LLM for answer generation.

- OpenStax University Physics / College Physics: derived benchmark families only.
- MIT OCW Dynamics: derived benchmark design for rotating frames and rigid-body dynamics.
- FOSSEE Engineering Mechanics Dynamics: calculation-flow reference for derived tests.


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
