# Stage 7 B6 — direct constant-force work checkpoint

- Code candidate: `84bb1d945a0ab9aa48987c47dc738a0ba2613d15`
- Parent: `25d02d1dc50810a7c5a53bfd18d151aa6b5f4662`
- Package: derive one value-free, source-scoped `constant_force` authorization from an exact one-body bounded energy interval, then bind the existing force, path increment, work unknown, applied-force interaction, and one-dimensional motion axis to the existing `force_work` law and deterministic solver.
- The derivation requires exactly one source force scoped over the whole interval, one path length, exact start/finish boundaries, an along-motion direction, one work-magnitude query, and no competing relation, assumption proposal, body, force, or event scope. It reads no expected answer, expected terminal, case identity, family identity, or corpus order.
- Guarded atomic finalizer patch digest, exact-parent and changed-path guards, Python 3.11 dedicated/authority-isolation tests, and existing constant-force/work-energy parity suites: PASS.
- Public-100 exact-code scoring: supported correct `20/81`, wrong `0`, deferred matched `12/12`, terminal mapping `37/100`, blocked numeric answers `0`, deferred silent solves `0`, supported downgrades `0`.
- The B5→B6 runtime snapshot differential changes exactly three direct constant-force work structures; no other public runtime snapshot changes.
- Public corpus, raw cases, expected answers, case identifiers, and private material are not stored here.
- Stage 7 remains `IN_PROGRESS / NOT_ACCEPTED`; Stage 8 remains `NOT_STARTED`.

This documentation-only commit triggers corpus-independent CI. Its CI evidence must be attributed separately from the strict public-corpus score above.
