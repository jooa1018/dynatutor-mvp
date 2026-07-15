# Phase 49 Solver Consistency Report

- Status: PASSED
- Oracle version: phase49-oracle-v1
- Benchmark version: phase49-benchmark-v1
- Metamorphic version: phase49-metamorphic-v1
- Report schema: 2
- Report version: phase49-solver-consistency-report-v2
- Tolerance policy: phase48-tolerance-policy-v1
- Semantic selection evidence: p47_output_validation
- Oracle fixture SHA-256: 9d9d26ecf70340cd7345b06c5e92ceb39d8fde429494368054e57883e6822484
- Metamorphic fixture SHA-256: f141686129eb888207fdb8d947e1388fa07293333f63f9cf82221f49e55f6591
- Offline only; student answers are never overwritten.

## Coverage

| Evidence | Executed | Passed / Total |
|---|---:|---:|
| Phase 48 product verification | 60 | 60 / 60 |
| Oracle-product legs | 60 | 60 / 60 |
| Oracle-secondary legs | 60 | 60 / 60 |
| Product-secondary direct legs | 60 | 60 / 60 |
| Strict three-way aggregates | 60 | 60 / 60 |
| Distinct metamorphic relations | 21 | 21 / 21 |
| Mutation controls killed | 4 | 4 / 4 |
| Scalar fixed expectations | n/a | 70 |

## Family coverage

| Family | Cases |
|---|---:|
| collision | 10 |
| fixed_axis_rotation | 10 |
| incline | 10 |
| pulley | 10 |
| rolling | 10 |
| work_energy | 10 |

## Path roles

- collision: student=['collision_1d']; secondary=phase49.secondary.collision; numeric=None; external=None; fallback=None
- fixed_axis_rotation: student=['fixed_axis_rotation']; secondary=phase49.secondary.fixed_axis_rotation; numeric=None; external=None; fallback=None
- incline: student=['incline_no_friction', 'incline_with_friction']; secondary=phase49.secondary.incline; numeric=None; external=None; fallback=None
- pulley: student=['pulley_atwood', 'pulley_table_hanging', 'pulley_incline_hanging', 'massive_pulley_atwood']; secondary=phase49.secondary.pulley; numeric=None; external=None; fallback=None
- rolling: student=['pure_rolling_energy', 'rolling_energy_general']; secondary=phase49.secondary.rolling; numeric=None; external=None; fallback=None
- work_energy: student=['work_energy_speed']; secondary=phase49.secondary.work_energy; numeric=None; external=None; fallback=None

## Disagreements

- None.
