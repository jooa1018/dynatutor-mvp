# Mechanics legacy solver migration matrix

## Scope and authority

This is a planning and audit artifact for the registered legacy analytic
solvers only.  It does not report execution or parity results, and it makes no
corpus- or PDF-exact-match claim.

The target path is:

`MechanicsProblemIRV1` -> `ValidatedIRAuthorization` -> `MechanicsCompiler`
-> `EquationGraph` -> `solve_verified_equation_graph`.

`EquationGraph` is the only calculation and routing authority on that path.
In particular, a legacy result is never a runtime answer authority when
generic compilation succeeds.  `system_type`, `subtype`, and raw text are
legacy diagnostics only: an adapter may be selected only from a verified IR /
equation pattern, never from a label or text string.

The authority boundary is implemented by
`backend/engine/mechanics/compiler/compiler.py:authorize_validated_mechanics_ir`
and `MechanicsCompiler.compile`, and by
`backend/engine/mechanics/pipeline.py:solve_verified_equation_graph` (whose
docstring rejects raw text, model labels, expected answers, and caller backend
selection).  The normalized calculation-only fingerprint is
`backend/engine/mechanics/normalization.py:calculation_fingerprint`.

`native` below means emit the stated core law(s) from typed IR and solve the
resulting graph.  `adapter` means a graph/IR-pattern-selected numerical kernel
may be used only as an independent differential candidate/residual oracle;
its answer is not delivered.  `rollback` means the legacy solver remains
off-mode and is usable only for controlled rollback after a generic-path
failure.  `discard` means legacy label matching, raw-text interpretation,
answer formatting, and routing are not migrated.

### Dependency notation and citations

* `raw`: **D** = the registered implementation directly reads `c.raw_text`;
  **I** = only the reachable legacy registry/required-input path reads it;
  **N** = neither does.  `type/subtype` uses the same notation.  In practice,
  `registry.py:SolverRegistry._variant_specs`, `_has_symbol`, and `route`
  make raw/type/subtype at least indirect legacy dependencies for every
  registered candidate; class-level direct reads are identified in the rows.
* Every registered solver directly uses `system_type` in `match`; that common
  routing dependency is visible in the registered classes cited in the matrix,
  and the registry invokes those matches in
  `backend/engine/solvers/registry.py:SolverRegistry.route`.  It must be
  discarded, not reproduced.
* Law names refer to `backend/engine/mechanics/laws/core.py:CORE_LAW_CATALOG`
  and emission implementation `apply_core_laws`.  The source contains, among
  others, `particle_newton_second`, `particle_normal_acceleration`,
  `contact_*`, `particle_work_energy`, `system_momentum_conservation`,
  `direct_restitution`, `rope_*`, `pulley_newton_euler`, `rolling_no_slip`,
  `rigid_*`, and `linear_vibration`.

## Exact registered set

Canonical order is the construction order in
`backend/engine/solvers/registry.py:SolverRegistry.__init__` (not alphabetical).
The 29 IDs are:

1. `single_particle_newton`
2. `incline_no_friction`
3. `incline_with_friction`
4. `pulley_atwood`
5. `pulley_table_hanging`
6. `pulley_incline_hanging`
7. `massive_pulley_atwood`
8. `pure_rolling_energy`
9. `rolling_energy_general`
10. `vertical_circle`
11. `collision_1d`
12. `constant_acceleration_1d`
13. `projectile_motion`
14. `constant_force_work`
15. `fixed_axis_rotation`
16. `horizontal_friction_force`
17. `impulse_momentum`
18. `work_energy_speed`
19. `spring_mass_vibration`
20. `spring_energy_speed`
21. `flat_curve_friction`
22. `banked_curve_no_friction`
23. `relative_acceleration_translation`
24. `coriolis_relative_motion`
25. `plane_rigid_body_acceleration`
26. `polar_kinematics`
27. `instant_center_velocity`
28. `slot_pin_relative_motion`
29. `plane_rigid_body_velocity`

Read-only extraction/check (PowerShell; no project file is changed):

```powershell
$registry = Get-Content backend/engine/solvers/registry.py -Raw
$imports = @{}
[regex]::Matches($registry, '(?m)^from engine\.solvers\.([\w\.]+) import ([^\r\n]+)\r?$') | % {
  $p = 'backend/engine/solvers/' + ($_.Groups[1].Value -replace '\.','/') + '.py'
  $_.Groups[2].Value.Split(',') | % { $imports[$_.Trim()] = $p }
}
$classes = [regex]::Matches($registry, '(?m)^\s{12}([A-Za-z][A-Za-z0-9_]*Solver)\(\),\r?$') | % { $_.Groups[1].Value }
$actual = foreach ($class in $classes) {
  $p=$imports[$class]; $root=if(Test-Path $p){$p}else{$p-replace'\.py$',''}
  $s=Get-Content @(& rg -l ('^class\s+'+$class+'\b') $root)[0] -Raw
  ([regex]::Match($s,'class\s+'+[regex]::Escape($class)+'\b[\s\S]*?^    name\s*=\s*"([^"]+)"',[Text.RegularExpressions.RegexOptions]::Multiline)).Groups[1].Value
}
$matrix = [regex]::Matches((Get-Content docs/MECHANICS_LEGACY_MIGRATION.md -Raw),'(?m)^\d+\. `([^`]+)`\r?$') | % { $_.Groups[1].Value }
"registered names=$($actual.Count); matrix IDs=$($matrix.Count); sequence equality=$(($actual -join ';') -ceq ($matrix -join ';'))"
```

Raw result from this audit: `registered names=29; matrix IDs=29; sequence
equality=True`.
The constructor count is additionally guarded at runtime by
`registry.py:SolverRegistry._validate_capability_data`, which builds the
expected `.name` sequence and rejects duplicate, missing, extra, or reordered
capability IDs.  The command resolves each constructor class through its
registry import source and reads its `.name`, so the successful sequence check
is against names rather than class spellings.

### Authoritative typed scope classification

The exact registered inventory is `29/29` classified.  Scope and accepted
same-fixture evidence are separate axes:

* **in scope: `25/29`**;
* **deferred: `4/29`**, exactly registry entries 19
  (`spring_mass_vibration`), 23 (`relative_acceleration_translation`), 24
  (`coriolis_relative_motion`), and 28 (`slot_pin_relative_motion`);
* **accepted in-scope evidence: `10/25`**; **pending in-scope evidence:
  `15/25`**.

Entry 26, `polar_kinematics`, is explicitly **in scope**.  Entries 1-10 are the
ten accepted in-scope entries; deferred entries are not parity passes and are
not generic migrations.  Deferred counts cannot be added to accepted evidence,
and `29/29 generic migrated` is not a valid roll-up.  This classification
supersedes the older Wave 1/2/3 prose
that grouped `polar_kinematics` with the deferred law gaps or kept
`spring_mass_vibration` active.

## Migration matrix

Each **source** citation identifies the registered class/symbol that supports
the stated capability and dependency.  `Reuse / discard` calls out the only
kernel worth preserving; all other legacy logic is explicitly non-reusable.
All listed fallback entries remain **off-mode rollback**, never generic-path
answer authority; the ledger below records which independent parity gates pass.

| solver_id | current math capability; source | legacy dependencies (raw; type/subtype) | required IR primitive | required law / constraint | native generic compiler migration | kernel adapter | legacy fallback | parity test |
|---|---|---|---|---|---|---|---|---|
| `single_particle_newton` | `F=ma`, solve `a/F/m`; `solvers/newton/single_particle.py:SingleParticleNewtonSolver.solve` | D (force/query word heuristics); D/I | particle, force vector, acceleration query | `particle_newton_second`; force directions/balance | Native now; typed force vectors replace text net-force choice | none; formula is trivial | rollback | `m,F -> a`; multi-force signed balance; reject ambiguous directions; invariance |
| `incline_no_friction` | `a=g sin(theta)`; `solvers/incline.py:InclineNoFrictionSolver.solve` | I; D/D | particle, incline geometry/frame, gravity/contact | `incline_gravity_tangent_projection`, `incline_gravity_normal_projection`, `fixed_contact_no_penetration`, `contact_normal_bound`, `particle_newton_second` | Native now; typed angle-based gravity projection, evidenced frictionless touching contact/no penetration, and the inclusive `0 <= theta <= pi/2` domain are accepted | none; existing generated Newton result is not reused | rollback | 0/90-degree limits, interior and signed slope force, out-of-domain/contact rejection, invariance |
| `incline_with_friction` | static hold or `a=g(sinθ-μcosθ)`; `solvers/incline.py:InclineWithFrictionSolver.solve` | I; D/D | particle, incline, contact, friction regime, motion state | `contact_normal_bound`, `contact_friction_bound` or `contact_sliding_friction`, Newton | Native now; model static inequality as graph constraint | static-friction inequality residual only; discard direction prose | rollback | hold/slip boundary, μ=0 reduction, direction contradiction; invariance |
| `pulley_atwood` | two masses, tension and acceleration; `solvers/pulley/atwood.py:AtwoodPulleySolver.solve` | I; D/I | two particles, rope, fixed ideal pulley, gravity | particle Newton, `rope_massless_tension`, `rope_fixed_pulley_motion` | Native now with evidenced rope topology | none | rollback | m1=m2, tension residual, mass swap sign; invariance |
| `pulley_table_hanging` | table/hanging pair, static/kinetic/no-friction branches; `solvers/pulley/table_hanging.py:TableHangingPulleySolver.solve` | I; D/D | two particles, horizontal contact, rope/pulley, friction regime | Newton, rope laws, contact friction laws | Native now for fully typed topology/regime | none; discard subtype/flag branch | rollback | static threshold, μ=0, rope/tension residual; invariance |
| `pulley_incline_hanging` | incline/hanging coupled equations and friction-direction cases; `solvers/pulley/incline_hanging.py:InclineHangingPulleySolver.solve` | D (`_motion_direction`); D/I | two particles, incline, rope/pulley, friction and motion direction | Newton, rope laws, contact friction; directional inequality | Native now when IR encodes direction/regime; otherwise terminal ambiguity | no runtime reuse; candidate residual may compare the closed-form branch | rollback | both directions, static boundary, inconsistent direction terminal; invariance |
| `massive_pulley_atwood` | unequal tensions, `a=(m2-m1)g/(m1+m2+I/R²)`; `solvers/pulley/massive_pulley.py:MassivePulleyAtwoodSolver.solve` | I; D/I | two particles, inertial pulley, rope, radius/inertia | Newton, `pulley_newton_euler`, rope motion | Native now with inertial-pulley IR topology | none; legacy Newton generator/routing discarded | rollback | I→0 reduction, m1=m2, torque/tension residual; invariance |
| `pure_rolling_energy` | shape-derived `I=βmR²`, rolling energy speed; `solvers/rolling/rolling_energy.py:PureRollingEnergySolver.solve` | I; D/I | rigid body, gravity height change, shape/inertia, rolling constraint | kinetic/gravity/rigid kinetic terms, `rolling_no_slip`, energy conservation constraint | Native now; an exact approved/evidenced six-shape assumption derives `I=beta*m*R^2`, while typed initial/final rolling states, height, no-slip, and no-energy-loss authority determine final center-of-mass speed; source inertia and internal queries fail closed | none; direct legacy output is diagnostics only | rollback | all six shapes, nonzero initial speed, h=0, mixed units, mass/radius/gh invariance, residuals, authority/query negatives |
| `rolling_energy_general` | `vf=sqrt(v0²+2mgh/(m+I/R²))`; `solvers/rolling/rolling_general_I.py:RollingEnergyGeneralSolver.solve` | I; D/I | rigid body, explicit positive finite center-of-mass I/R, height change, rolling states | rigid/translation energy, `rolling_no_slip`, energy conservation | Native now; typed initial/final rolling states, source inertia, height, no-slip, and no-energy-loss authority determine final center-of-mass speed; shape authority, internal queries, malformed topology, and invalid domains fail closed | none; direct legacy output is diagnostics only | rollback | arbitrary I, nonzero v0, I=βmR² agreement, h=0, mixed units, scaling/invariance, near-zero positive I, monotonicity, residuals, authority/query negatives |
| `vertical_circle` | top/bottom rope tension or contact normal `C=m(v^2/R∓g)` and top `v_min=sqrt(gR)`; `solvers/vertical_circle.py:VerticalCircleSolver.solve` | I; D/D | particle, exact circular geometry/radial frame, top/bottom state, rope or touching contact | `particle_normal_acceleration`, Newton radial balance, exact top/bottom state constraint | Native now for the narrow exact typed topology; query-independent recognition, contact-loss rejection, relative-epsilon exact-zero boundary handling, and derived numeric fences fail closed | none; direct legacy output is diagnostics only, with contact parity numeric-only | rollback | top/bottom rope/contact signs, exact contact-loss boundary, top minimum speed, derived overflow/underflow/subnormal fences, malformed/query negatives, invariance |
| `collision_1d` | perfectly inelastic momentum or elastic momentum+restitution; `solvers/collision.py:Collision1DSolver.solve` | I; D/I | two particles, line frame, collision start/end event | `system_momentum_conservation`, `direct_restitution` | Native now for paired collision IR (compiler validates collision structure) | none | rollback | e=0/e=1, equal masses, momentum/restitution residual; invariance |
| `constant_acceleration_1d` | four constant-acceleration equations; `solvers/kinematics.py:ConstantAcceleration1DSolver.solve` | D (unstructured query/initial-state helpers); D/N | particle, 1-D frame, interval, initial/final states | `particle_constant_acceleration_velocity`, `particle_constant_acceleration_position` | Native now with explicit interval/initial conditions | none; discard text query inference | rollback | each unknown, zero a, redundant-equation residual; invariance |
| `projectile_motion` | horizontal/vertical/angled time, range, height; `solvers/projectile.py:ProjectileMotionSolver.solve` | D; D/I | particle, 2-D frame, launch state, gravity, event/query | constant-acceleration x/y equations plus landing/max-height event constraint | Gate/partial: compiler needs verified event-root/query selection for range/landing variants | graph-derived event root residual only; no text classifier | rollback | horizontal, vertical, angled, nonzero launch height, root selection; invariance |
| `constant_force_work` | `W=Fs cosθ`; `solvers/work_rotation_impulse.py:ConstantForceWorkSolver.solve` | D (angle parser); D/N | force/displacement vectors or explicit angle | `force_work` | Native now when vector dot product/angle is IR evidence | none; discard direction parser | rollback | 0/90/180 degrees and vector-dot equivalence; invariance |
| `fixed_axis_rotation` | `τ=Iα`, `ω=ω0+αt`, `v=ωr`; `solvers/work_rotation_impulse.py:FixedAxisRotationSolver.solve` | D (output words); D/N | rigid body, axis, torque/inertia, angular state/interval, radius | `rigid_newton_euler`, `angular_velocity_derivative`, `fixed_axis_speed` | Native now; IR query replaces text output choice | none | rollback | each query branch, zero torque, angular-rest state; invariance |
| `horizontal_friction_force` | static bound or `f_k=μ_kmg`; `solvers/energy_vibration.py:HorizontalFrictionForceSolver.solve` | D (static/kinetic/motion phrasing); D/I | particle, horizontal contact, gravity, friction regime | contact normal/friction laws | Gate/partial: promote only with IR friction regime/direction; otherwise terminal ambiguity | static/kinetic residual only | rollback | static bound, kinetic μ, μ=0, missing-regime terminal; invariance |
| `impulse_momentum` | `J=F_parallel Δt=m(vf-vi)`; `solvers/work_rotation_impulse.py:ImpulseMomentumSolver.solve` | I; D/I | particle, line/vector frame, force-time interval, states | `linear_impulse`, `linear_impulse_momentum` | Native now | none | rollback | solve J/vf, signed force, zero duration, residual; invariance |
| `work_energy_speed` | `vf=sqrt(vi²+2W/m)`; `solvers/energy_vibration.py:WorkEnergySpeedSolver.solve` | D (rest phrase); D/N | particle, mass, work, initial/final velocity states | `particle_work_energy` and kinetic-energy relation | Native now with explicit rest/state condition | none; discard phrase default | rollback | vi=0, positive/negative work domain, energy residual; invariance |
| `spring_mass_vibration` | free SHM `T,f,ωn`; `solvers/energy_vibration.py:SpringMassVibrationSolver.solve` | I; D/I | mass, spring, displacement, time, free/undamped assumption | `spring_force`, `linear_vibration`, `vibration_natural_frequency` | **Deferred by the authoritative scope classification**; preserve the native ODE and future verified period/frequency extension, but do not claim migration | none with answer authority | off-mode rollback only | current generic behavior is precise structured unsupported; no generic answer and no silent legacy fallback |
| `spring_energy_speed` | `E=½kx²`, `\|v\|=\|x\|sqrt(k/m)`; `solvers/energy_vibration.py:SpringEnergySpeedSolver.solve` | D (energy phrase fallback); D/I | mass, spring, displacement/state, energy query | `spring_potential`, kinetic energy, energy conservation constraint | Native now from typed energy/state constraint; IR query replaces phrase fallback | none; discard text fallback | rollback | energy and speed queries, x=0, dimension/residual; invariance |
| `flat_curve_friction` | `vmax=sqrt(μgR)`; `solvers/curves.py:FlatCurveFrictionSolver.solve` | I; D/I | particle, circular path/radial frame, horizontal contact | `particle_normal_acceleration`, contact friction, radial Newton balance | Gate/partial: require limiting static-friction regime and radial frame in IR | centripetal/friction residual only | rollback | μ=0, threshold equality, centripetal/friction residual; invariance |
| `banked_curve_no_friction` | `v=sqrt(gR tanθ)`; `solvers/curves.py:BankedCurveNoFrictionSolver.solve` | I; D/I | particle, bank geometry, circular path, normal contact | normal/radial Newton balances plus geometry projection | Gate/partial: bank-angle force-projection relation must be explicit graph geometry | algebraic balance residual only | rollback | θ→0 terminal/domain, force-balance residual, sign/frame; invariance |
| `relative_acceleration_translation` | `aB=aA+aB/A`; `solvers/rigid_body_2d/relative_motion.py:RelativeAccelerationTranslationSolver.solve` | D (component wording); D/I | two points, vector acceleration components, translating frame | translating-frame relative-acceleration law | **Deferred by the authoritative scope classification**; future typed-law extension remains permitted | no reuse until law exists | off-mode rollback only | precise structured unsupported; no generic answer and no silent fallback |
| `coriolis_relative_motion` | `aC=2ωvrel`, polar relative acceleration; `solvers/advanced_dynamics.py:CoriolisRelativeMotionSolver.solve` | D; D/I | rotating frame, relative coordinate/speed, angular state | precise Coriolis/rotating-frame law | **Deferred by the authoritative scope classification**; future typed-law extension remains permitted | no reuse until a graph law exists | off-mode rollback only | precise structured unsupported; no generic answer and no silent fallback |
| `plane_rigid_body_acceleration` | `aB=aA+α×r+ω×(ω×r)` and components; `solvers/rigid_body_2d/acceleration.py:PlaneRigidBodyAccelerationSolver.solve` | D (fixed/point text); D/I | rigid body, A/B points, rBA vector, angular state | `rigid_point_tangential_acceleration`, `rigid_point_normal_acceleration` | Gate/partial: complete verified vector composition/point binding before promotion | graph-derived vector residual only | rollback | fixed A, nonzero aA, tangential/normal vector residual; invariance |
| `polar_kinematics` | polar `v` and `a` components; `solvers/advanced_motion.py:PolarKinematicsSolver.solve` | D (`_constant_radius_is_explicit` and `_constant_angular_speed_is_explicit` read `c.raw_text`); D/I | polar frame, r/θ derivatives and query | polar-coordinate kinematics law | **In scope, Wave F**; implement typed polar-coordinate emission without importing raw-text defaults | no reuse until the typed graph law exists | rollback during the pending in-scope migration only | typed v/a component cases, structured unsupported before implementation, then invariance and residual evidence |
| `instant_center_velocity` | `ω=v/r` or `v=ωr`; `solvers/advanced_motion.py:InstantCenterVelocitySolver.solve` | I; D/I | rigid body, instantaneous center/point radius, speed/ω | `fixed_axis_speed` or `rigid_point_velocity` | Native now if instantaneous-center relation is typed geometry | none | rollback | solve either variable, zero-radius domain, residual; invariance |
| `slot_pin_relative_motion` | radial/tangential slot-pin speed/acceleration components; `solvers/advanced_motion.py:SlotPinRelativeMotionSolver.solve` | I; D/I | slot/pin geometry, polar coordinate derivatives | polar relative-motion law | **Deferred by the authoritative scope classification**; future typed-law extension remains permitted | no reuse until law exists | off-mode rollback only | precise structured unsupported; no generic answer and no silent fallback |
| `plane_rigid_body_velocity` | `vB=vA+ω×rBA`, fixed-point `ωr`; `solvers/rigid_body_2d/velocity.py:PlaneRigidBodyVelocitySolver.solve` | D (fixed-point/component text); D/I | rigid body, A/B points, rBA vector, angular velocity | `rigid_point_velocity` | Native now for IR-backed points/vectors | none; discard phrase parser | rollback | fixed A and moving A, vector magnitude/direction residual; invariance |

## Waves, parity policy, and release gates

**Wave 0 — prove the boundary before migration.**  Add only offline,
IR-built fixtures for every matrix parity case; compile, fingerprint, plan,
solve, and independently compare graph residuals to an off-mode legacy oracle.
No label or raw-text selection enters this harness.

The obsolete Wave 1/2/3 execution plan is superseded by these exact in-scope
families.  Entries 1-4 are already accepted prerequisites and are not rerun as
a wave:

* **Wave A — entries 5-7:** `pulley_table_hanging`,
  `pulley_incline_hanging`, `massive_pulley_atwood`.
* **Wave B — entries 8-10:** `pure_rolling_energy`,
  `rolling_energy_general`, `vertical_circle`.
* **Wave C — entries 11-13:** `collision_1d`,
  `constant_acceleration_1d`, `projectile_motion`.
* **Wave D — entries 14-18:** `constant_force_work`, `fixed_axis_rotation`,
  `horizontal_friction_force`, `impulse_momentum`, `work_energy_speed`.
* **Wave E — entries 20-22:** `spring_energy_speed`, `flat_curve_friction`,
  `banked_curve_no_friction`; deferred entry 19 is deliberately skipped.
* **Wave F — entries 25, 26, 27, and 29:**
  `plane_rigid_body_acceleration`, `polar_kinematics`,
  `instant_center_velocity`, `plane_rigid_body_velocity`; deferred entries 23,
  24, and 28 are deliberately skipped.

Each entry requires its focused parity evidence and connected targeted tests.
The independent read-only Checker and release CI run once at the end of each
complete wave, not after every entry.  Wave A is accepted at exact release
checkpoint `8f18c710fc6d5d730fcceccfb30e3175c2613902`, GitHub Actions run
`29865756663` (run #433, `SUCCESS`).  Wave B Entries 8-10 are locally accepted
and the wave is locally complete, but its independent wave Checker and release CI
have not run.  The next exact task is the fresh Wave-B Checker followed by
exact-head release CI; Entry 11 does not start before that gate.

For all four deferred entries, current generic behavior is a precise structured
unsupported result.  Generic answer authority is **none**; legacy answer
authority is **off-mode rollback only**.  There is no silent fallback.  The
classification preserves a future typed-law/typed-output extension without
claiming that extension exists now.

For every solver and each case named in the matrix, the parity harness must
also prove this metamorphic invariant: **the same `MechanicsProblemIRV1` with
paraphrased raw text and changed or removed `system_type` has the same graph
fingerprint, solve plan/backend, candidate set, and terminal/result.**  The
IR must carry the physics needed to preserve that result; a changed label must
not repair missing IR.

No legacy solver is deleted, demoted, or made unreachable until independent
per-solver parity evidence exists.  Runtime authority remains the generic
graph path; the retained legacy implementations have two distinct,
non-authoritative roles: an offline differential oracle and an off-mode
rollback after generic-path failure.

## Accepted same-fixture parity ledger

1. `single_particle_newton` — **ACCEPTED (registry entry 1; in-scope 1/25)** at exact checkpoint
   `8b7c5c4a6f1f972d479323f5a7179b4f177d3800`, GitHub Actions release run
   `29818526780` (run #422, `SUCCESS`). The accepted Draft -> normalization ->
   IR fixture package proves baseline `m,F -> a`, signed multi-force balance,
   ambiguous-direction fail-closed behavior, and diagnostic-label/source-digest
   invariance. Both solved cases compare value, canonical unit, terminal,
   exhaustive candidate set, and an independently calculated Newton residual.
   Generic execution finishes before the direct legacy-solver call; no registry,
   `match()`, raw text, family/case metadata, expected answer, or legacy output
   has generic calculation or selection authority. Fresh independent Checker:
   `PASS`, blocking findings `0`.

2. `incline_no_friction` — **ACCEPTED (registry entry 2; in-scope 2/25)** at exact product/CI checkpoint
   `5e49f2f267c4c8d75aec6e99e3714fc36f700257` (tree
   `9ffbd6cc9bd60e1153891c2b2b7053e2d801a35c`, parent documentation handoff
   `8711b8a328b7334b0545d62f8a2bba6c8317f0b6`, commit
   `feat(mechanics): migrate frictionless incline solver`), GitHub Actions
   release run `29823679522` (run #424, `SUCCESS`). The generic path derives
   tangent/normal gravity components from the evidenced typed incline angle,
   enforces evidenced frictionless touching contact and fixed-surface
   no-penetration behavior, and accepts only the inclusive physical angle domain
   `0 <= theta <= pi/2`. Its same-fixture package proves 0/90-degree limits,
   interior down-/up-slope signs, full value/unit/terminal/candidate parity with
   the direct diagnostics-only legacy observation, independent projection,
   Newton/contact residuals, angle-domain and gravity-authority negatives,
   manual typed-payload negatives, and diagnostic metadata invariance. Focused
   evidence: `15 passed`; connected
   compiler plus entry-1 regression: `60 passed`; additional Sol-connected
   entry-1/migration/legacy runs: `3`, `23`, and `30 passed`. Local Windows full
   runs used only the 20-second worker-startup shim; the unchanged default
   5-second symbolic and verification budgets are not claimed green locally. Fresh independent
   Checker: `PASS`, blocking findings `0`, nonblocking findings `0`.

3. `incline_with_friction` — **ACCEPTED (registry entry 3; in-scope 3/25)** at exact product/CI checkpoint
   `c134664cd863d33b50c7e5ae794af2ad61ed6524` (tree
   `987cb4ec8b7cbcc321d713313c179e8ca4bcd553`, CI-remediation child of product
   code commit `d58e2c9bcd8c04c8fa380699e19df6a6c43e7296`, product tree
   `72301ea20e43e5310a269dac943fc7d56f01f689`, parent documentation handoff
   `6c53e0fdbbf70854bfec3078d73fb48371fc9a12`, product commit
   `feat(mechanics): migrate friction incline solver`; remediation commit
   `ci: split slow mechanics parity checks`), GitHub Actions release run
   `29832358480` (run #427, `SUCCESS`). The exact typed contract admits only
   evidenced sticking or sliding regimes on a two-axis incline frame. Both emit
   `incline_gravity_tangent_projection`, `incline_gravity_normal_projection`,
   `fixed_contact_no_penetration`, `contact_normal_bound`, and two
   `particle_newton_second` equations. Sticking additionally emits two-sided
   `contact_friction_bound` constraints and
   `incline_sticking_static_acceleration`; it requires an evidenced at-rest body,
   sets tangential acceleration to zero, and includes the exact hold/slip
   boundary. Sliding instead emits `contact_sliding_friction`, requires evidenced
   positive tangential motion, and fixes friction opposite that carrier while
   preserving independent query-direction projection. The physical domain is
   exact: `m,g > 0`, `mu,N >= 0`, and `0 <= theta <= pi/2`. The package proves static
   hold and exact boundary behavior, below-boundary rejection, sliding signs,
   `mu=0` frictionless reduction, value/unit/terminal/candidate parity,
   independent Newton/contact/regime residuals, and metadata invariance. Missing
   or contradictory motion/contact/regime authority, duplicate incline axes,
   empty body/incline/interval evidence, negative coefficients, and unresolved
   blocking ambiguity fail closed before any legacy call. Focused evidence:
   `21 passed`; entry-2 regression: `15 passed`; connected compiler plus entry-1
   regression: `60 passed`. Fresh independent entry-3 Checker: `PASS`, blocking
   findings `0`, nonblocking findings `0`; independent CI-remediation Checker:
   `PASS`, blocking findings `0`, nonblocking findings `0`. The preceding run
   `29829411846` (run #426) failed only when the unchanged 420-second fast
   watchdog reached 82% progress, with no assertion failure; the bounded
   240-second disjoint slow lane fixed the CI classification without changing
   test semantics or the fast watchdog.

4. `pulley_atwood` — **ACCEPTED (registry entry 4; in-scope 4/25)** at exact product/CI checkpoint
   `dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9` (tree
   `dc0e90d954b16a342c16073f2c3021f65da875bf`, parent documentation handoff
   `bd5afe32958ba1ca4efdc5ecc4c22a0ba22fefdd`, commit
   `feat(mechanics): migrate Atwood pulley solver`), GitHub Actions release run
   `29841110152` (run #429, `SUCCESS`). The typed contract requires exactly two
   particles, one rope, one fixed ideal pulley, one gravity environment, two
   evidenced gravity interactions, one evidenced wrap, two rope/body
   attachments, taut/fixed state, and approved evidenced massless,
   inextensible, fixed-pulley, and ideal-pulley assumptions. Its exact equation
   multiset is two `particle_weight`, two `particle_newton_second`, one
   `rope_massless_tension`, and one `rope_fixed_pulley_motion` equation. The
   same-fixture package proves baseline acceleration and tension, equal-mass
   zero acceleration, mass-swap sign reversal with unchanged tension, an
   independently signed B-up query, direct tension-query parity, exhaustive
   symbolic-candidate coverage, independent Newton/rope residuals, and
   diagnostic metadata invariance. Generic results are frozen before the
   direct diagnostics-only legacy call. Structural, scope, evidence,
   assumption, ambiguity, and positive mass/gravity domain violations fail
   closed without a legacy call; missing ideal authority also suppresses the
   fixed-pulley law at the core-law layer. Invariance authority collections and
   mappings are bounded and snapshotted once before variant execution, with the
   same snapshotted comparison inputs reused for every variant; oversized or
   unstable authority is rejected first. Connected regressions preserve the
   massive-pulley graph (`pulley_newton_euler` and unequal tensions, without
   false Atwood rejection) and the pre-existing rigid-body fixed-pulley rope
   laws. Exact release evidence: fast `2293 passed, 1 skipped, 279 deselected`
   in `401.95s`; slow `12 passed, 2561 deselected` in `89.92s`; complete
   collection `2573`; fresh independent Checker `PASS`, blocking findings `0`.

5. `pulley_table_hanging` — **ACCEPTED (registry entry 5; in-scope 5/25)** at
   product checkpoint `7fff1b83f42ed5f1ddf6046f456b2c9f924cb54e`.
   The accepted package binds the typed table/hanging pair, horizontal contact,
   rope and fixed-pulley topology, and explicit no-friction, sliding, or sticking
   regime.  It covers the static threshold, `mu=0` reduction, signed acceleration
   and tension queries, independent Newton/contact/rope residuals, diagnostic
   metadata invariance, and fail-closed structural/evidence/authority negatives.
   Targeted fast evidence is `45 passed, 9 deselected`; targeted slow evidence
   is `9 passed, 45 deselected`; compiler regression is `57 passed`; the fresh
   independent Entry-5 Checker reported `PASS` with blocking findings `0`.  This
   was not a new exact-head release-CI claim: at that checkpoint the Wave A
   family Checker/release CI remained pending entries 6 and 7.  At that Entry-5
   checkpoint, the latest exact release evidence was Entry 4 at `dedb4c7...`,
   run `29841110152` (run #429, `SUCCESS`).

6. `pulley_incline_hanging` — **ACCEPTED (registry entry 6; in-scope 6/25)** at
   product checkpoint `f3e747b4480f98223c113170181698c8b4822e84` (tree
   `f1854d5753249427c00ce51bac3d1b636e297556`, parent typed-scope checkpoint
   `a63647163c291c60eb3ccf9e39d8b6db633766e0`, commit
   `feat(mechanics): migrate incline-hanging pulley solver`).  The exact typed
   contract binds a parent Cartesian world frame to an incline-local
   tangential/normal frame, with one unframed rope-tension magnitude and one
   unframed rope-acceleration coordinate transferred through two evidenced
   attachments.  It derives the incline gravity projections, hanging weight,
   three particle balances, fixed-contact normal behavior, and exact rope
   tension/acceleration transfer equations without raw text, metadata, registry,
   fixture IDs, or legacy results as calculation authority.  Frictionless,
   sticking, and sliding regimes cover signed body-acceleration and tension
   queries, zero angle, `mu=0`, static interior and exact-boundary cases, both
   zero-drive friction axes, and reversed motion/query signs.  Sliding friction
   follows only the explicit velocity carrier; acceleration-direction
   consistency is emitted only from the separately evidenced, externally
   approved `acceleration_not_opposite_motion` assumption.  Missing or
   unapproved authority, invalid domains, internal-coordinate/query bypasses,
   infeasible static or direction candidates, and partial topology fail closed
   without a legacy call.  A Checker-discovered combined deletion of the rope
   interaction and wrap initially exposed a gravity-only fall-through; the
   accepted checkpoint activates the specialized gate from the distinctive
   primitive signature and proves that deletion returns
   `requires_specialized_model` with no graph.  Source quote/span/media content
   is calculation-identity neutral while exact provenance IDs and graph
   topology remain retained and validated.  Final focused evidence is fast
   `39 passed, 16 deselected`; the complete Entry-6 slow matrix is `16 passed`;
   compiler regression is `57 passed`; connected Entry-2-through-5 regression
   is `111 passed, 21 deselected`.  The fresh independent Checker reported
   final blocking findings `0`.  This was a local product checkpoint, not a new
   release-CI claim; at that checkpoint Wave A family Checker/release CI remained
   pending Entry 7.

7. `massive_pulley_atwood` — **ACCEPTED (registry entry 7; in-scope 7/25)** at
   product checkpoint `26434fc5edc25d617724c8352d1643a40b555f13` (tree
   `852c085d5fb93ec03484a9465ab3c72c01a9a245`, parent Entry-6 documentation
   checkpoint `02845bd77ae2dc1048512b482cc8a8ba8dd3007f`, commit
   `feat(mechanics): migrate massive pulley atwood solver`).  The exact typed
   contract closes the global inventory around two particles, one massless
   inextensible rope, one fixed-center inertial pulley with a frictionless axle,
   one gravity environment, and two pulley-owned rim contact points.  Signed
   radius and tangent relations bind the left and right rope segments without
   relying on identifiers or list order.  The exact equation multiset is two
   `particle_weight`, two `particle_newton_second`, two
   `rope_attachment_side_tension_transfer`, two
   `rope_attachment_acceleration_transfer`, one
   `pulley_no_slip_acceleration`, and one `pulley_newton_euler` equation.
   Generic ideal-pulley equal-tension and fixed-pulley motion equations are
   suppressed for this profile; in particular, `TL=TR` is never assumed.  The
   same-fixture package proves the baseline `a=3.5316`, `alpha=11.772`,
   `TL=26.6832`, and `TR=31.392`, plus mass-swap sign reversal, both local
   acceleration/tension queries, equal-mass zero motion, and the positive
   `I -> 0` reduction to Entry 4.  It also proves canonical provenance for the
   fixed-center, no-slip, attachment, wrap, radius/tangent, and frictionless-axle
   authority.  Complementary topology deletion, disconnected extra records,
   internal query targets, nonpositive domains, unequal radii, missing authority,
   and opposite-direction queries all fail closed.  Final focused evidence is
   fast `68 passed, 9 deselected`; the complete Entry-7 slow matrix is `9 passed`;
   compiler regression is `57 passed`; connected Entry-4-through-6 regression is
   `120 passed, 31 deselected`.  The independent Entry-7 Checker reported final
   blocking findings `0` and nonblocking findings `0`.  The independent Wave A
   Checker initially found one documentation-consistency blocker; after the
   ledger/handoff remediation its final verdict was `PASS`, blocking findings
   `0`, with one nonblocking local slow-sampling coverage note.  At this local
   Entry-7 product checkpoint the exact-head Wave A release CI was still pending;
   it later passed at `8f18c710...`, run `29865756663` (run #433).

8. `pure_rolling_energy` — **ACCEPTED (registry entry 8; in-scope 8/25)** at
   product checkpoint `af4b83ff6bde1d577b76ece3191e5b0e5b60d8af` (tree
   `c60ab8ab918dc1078e3faed2ca5d44212e5b85bb`, parent Wave-A release head
   `8f18c710fc6d5d730fcceccfb30e3175c2613902`, commit
   `feat(mechanics): migrate pure rolling energy solver`).  The exact typed
   contract accepts one rigid body on one fixed incline in a Cartesian world
   frame, with center-of-mass/contact geometry, gravity/contact interactions,
   initial/final rolling states, no slip, no energy loss, and exactly one
   approved/evidenced shape assumption.  The six admitted shapes derive
   `beta` as `2/5`, `2/3`, `1/2`, or `1` and emit graph equations for
   `I=beta*m*R^2`, `v=R*omega`, and rolling-energy conservation.  Only final
   center-of-mass scalar speed is a valid query; source inertia, unsupported
   internal queries, malformed topology, missing authority, and invalid domains
   fail closed.  Raw text, `system_type`, metadata, and legacy output have no
   generic calculation or selection authority.  Generic execution is frozen
   before the direct same-fixture legacy observation, whose output is diagnostics
   only.  The final 52-test file
   reports fast `40 passed, 12 deselected` and slow `12 passed, 40 deselected`
   in `148.68s`.  The independent integrated Entry-8 Checker reported `PASS`,
   blocking findings `0`, nonblocking findings `0`; compiler/solver/planner/
   verification regressions report `144 passed`, and connected Entries 4-7 fast
   regressions report `188 passed, 40 deselected`.  This is a local product
   checkpoint, not a release-CI checkpoint; the latest release-validated head
   remains the Wave-A checkpoint `8f18c710...`, run #433.

9. `rolling_energy_general` — **ACCEPTED (registry entry 9; in-scope 9/25)** at
   product checkpoint `2a870ec4808b6301e39bb99f446b457abc5458a5` (tree
   `9430a179e8e79322b1d49d2b53ed3b68a57f4a64`, parent Entry-8 documentation
   checkpoint `dbad228948c82809e854b0f9cf0f97bef9b998ea`, commit
   `feat(mechanics): migrate general rolling energy solver`).  The exact typed
   contract accepts one rigid body on one fixed incline in a Cartesian world
   frame, with center-of-mass/contact geometry, gravity/contact interactions,
   initial/final rolling states, no slip, no energy loss, and an explicit
   positive finite center-of-mass inertia.  Its graph equations bind initial and
   final no-slip motion and the principal energy result
   `vf=sqrt(v0^2+2*m*g*h/(m+I/R^2))`; an evidenced rest state supplies the exact
   zero initial speed.  Only final nonnegative center-of-mass scalar speed is a
   valid query.  Shape authority, source-inertia/shape conflicts, unsupported
   internal queries, malformed topology, missing authority, and invalid domains
   fail closed.  In particular, corrupting the rigid-body primitive fails closed
   independently for final-speed, mass, and source-inertia queries rather than
   escaping to a broad compiler path.  Raw text, `system_type`, metadata, and
   legacy output have no generic calculation or selection authority; the direct
   same-fixture legacy observation is diagnostics only.  Final core fast
   regressions report `294 passed, 22 deselected`; the complete Entry-9 slow
   matrix reports `10 passed, 60 deselected` in `84.11s`.  Two independent
   Checkers reported `PASS`, each with blocking findings `0` and nonblocking
   findings `0`; `py_compile` and `git diff --check` passed, and the Entry-8
   fingerprint remained unchanged.  This is a local product checkpoint, not a
   release-CI checkpoint; the latest release-validated head remains the Wave-A
   checkpoint `8f18c710...`, run #433.

10. `vertical_circle` — **ACCEPTED (registry entry 10; in-scope 10/25)** at
   product checkpoint `dba0016ec9878d40e1ed6edf60106491848b3956` (tree
   `7d02c784030e32e9d4fc08b22f76ecd8e93fbc1f`, parent Entry-9 documentation
   checkpoint `97545c02b53eea82e2951a8f1c81ebe2f3518cf8`, commit
   `feat(mechanics): migrate vertical circle solver`).  The narrow typed contract
   admits an exact query-independent particle/circular-path/radial-frame topology
   with an evidenced top or bottom state and either a rope or touching contact.
   It emits top/bottom rope tension or contact normal as
   `C=m(v^2/R∓g)` (minus at the top, plus at the bottom), and admits the top
   minimum-speed result `v_min=sqrt(gR)`.  Contact loss fails closed; the exact
   zero boundary is decided with a relative epsilon, and derived overflow,
   underflow, and subnormal results are fenced.  There is no hidden gravity
   default and no clamp.  Raw text, `system_type`, metadata, and legacy output
   have no generic calculation or selection authority.  The direct legacy call
   is diagnostics only, and contact parity is numeric-only.  The focused file
   collects `79` tests: `67` fast and `12` slow.  Root's final connected fast
   selection reports `361 passed, 34 deselected`; the final slow matrix reports
   `12 passed` in `105.20s`.  Two independent Entry-10 Checkers reported `PASS`,
   each with blocking findings `0` and nonblocking findings `0`; `py_compile`,
   `git diff --check`, and whitespace checks passed.  This is a local product
   checkpoint, not a release-CI checkpoint; the latest release-validated head
   remains the Wave-A checkpoint `8f18c710...`, run #433.

Current authoritative roll-up: the registry inventory is `29/29` classified;
the in-scope set is `25`, with `10/25` accepted and `15/25` pending; the deferred
set is exactly `4/4` classified.  Deferred classification is not accepted parity,
so accepted and deferred counts must not be added together, and this is not a
`29/29 generic migrated` claim.  Wave B Entries 8-10 are locally accepted and
locally complete, but the Wave-B independent Checker and release CI have not run.
The next exact task is that fresh wave Checker followed by exact-head release CI,
not Entry 11.

The separate typed scope/runtime amendment passed its final independent
read-only Checker with blocking findings `0` and new nonblocking findings `0`.
The Checker ran the focused compiler, scope, deferred-runtime, runtime-contract,
and runtime-static set (`236 passed`) plus the migration harness (`26 passed`),
and confirmed unchanged existing contract fields/version constants, clean
`py_compile`, and clean `git diff --check`.  This is focused amendment evidence,
not Wave A release CI; at that earlier amendment checkpoint the latest
release-validated migration head was Entry 4 at `dedb4c7...`.  The ordinary
runtime suite separately reported `87 passed,
2 failed`; both failures were the documented Windows default five-second
worker-startup timeout rather than a scope/contract assertion.

## Risks retained

* The registry itself presently contains label/raw-text routing and capability
  checks (`backend/engine/solvers/registry.py:SolverRegistry._variant_specs`,
  `_has_symbol`, and `route`); these are diagnostics to remove from the
  generic authority path, not a migration target for the matrix.
* Conservation/event roots and the in-scope `polar_kinematics` migration remain
  coverage risks.  They need typed IR, graph laws, and verification hooks;
  closed-form legacy output is not a substitute.  Deferred translating-frame,
  Coriolis, and slot-pin entries remain structured unsupported without generic
  answer authority.
* This document is an inventory, plan, and limited accepted-evidence ledger.
  Exactly ten in-scope entries (`10/25`) have accepted parity evidence; `15/25`
  in-scope entries remain.  The four deferred entries are not parity passes. No
  corpus/PDF inputs were opened or used for that evidence, and the public corpus
  remains sealed.
