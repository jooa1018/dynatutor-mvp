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
| `pure_rolling_energy` | shape-derived `I=βmR²`, rolling energy speed; `solvers/rolling/rolling_energy.py:PureRollingEnergySolver.solve` | I; D/I | rigid body, gravity height change, shape/inertia, rolling constraint | kinetic/gravity/rigid kinetic terms, `rolling_no_slip`, energy conservation constraint | Gate/partial: require IR shape-to-inertia authority before native graph compilation | pure numeric β/energy residual from graph quantities only | rollback | each β shape, h=0, no-slip residual; invariance |
| `rolling_energy_general` | `v=sqrt(2mgh/(m+I/R²))`; `solvers/rolling/rolling_general_I.py:RollingEnergyGeneralSolver.solve` | I; D/I | rigid body, explicit I/R, height change, rolling | rigid/translation energy, `rolling_no_slip`, energy conservation | Gate/partial: explicit inertia is sufficient, but conservation/event bindings still require verified graph coverage | pure algebraic residual only | rollback | arbitrary I, I=βmR² agreement, h=0; invariance |
| `vertical_circle` | top/bottom tension and `v_min=sqrt(gR)`; `solvers/vertical_circle.py:VerticalCircleSolver.solve` | I; D/D | particle, circular geometry, radial frame, contact/string state | `particle_normal_acceleration`, Newton radial balance, top/bottom state constraint | Gate/partial: require typed radial-state/contact-loss query relation before promotion | normal-force/minimum-speed residual only | rollback | top/bottom signs, N=0 minimum-speed, non-top min request terminal; invariance |
| `collision_1d` | perfectly inelastic momentum or elastic momentum+restitution; `solvers/collision.py:Collision1DSolver.solve` | I; D/I | two particles, line frame, collision start/end event | `system_momentum_conservation`, `direct_restitution` | Native now for paired collision IR (compiler validates collision structure) | none | rollback | e=0/e=1, equal masses, momentum/restitution residual; invariance |
| `constant_acceleration_1d` | four constant-acceleration equations; `solvers/kinematics.py:ConstantAcceleration1DSolver.solve` | D (unstructured query/initial-state helpers); D/N | particle, 1-D frame, interval, initial/final states | `particle_constant_acceleration_velocity`, `particle_constant_acceleration_position` | Native now with explicit interval/initial conditions | none; discard text query inference | rollback | each unknown, zero a, redundant-equation residual; invariance |
| `projectile_motion` | horizontal/vertical/angled time, range, height; `solvers/projectile.py:ProjectileMotionSolver.solve` | D; D/I | particle, 2-D frame, launch state, gravity, event/query | constant-acceleration x/y equations plus landing/max-height event constraint | Gate/partial: compiler needs verified event-root/query selection for range/landing variants | graph-derived event root residual only; no text classifier | rollback | horizontal, vertical, angled, nonzero launch height, root selection; invariance |
| `constant_force_work` | `W=Fs cosθ`; `solvers/work_rotation_impulse.py:ConstantForceWorkSolver.solve` | D (angle parser); D/N | force/displacement vectors or explicit angle | `force_work` | Native now when vector dot product/angle is IR evidence | none; discard direction parser | rollback | 0/90/180 degrees and vector-dot equivalence; invariance |
| `fixed_axis_rotation` | `τ=Iα`, `ω=ω0+αt`, `v=ωr`; `solvers/work_rotation_impulse.py:FixedAxisRotationSolver.solve` | D (output words); D/N | rigid body, axis, torque/inertia, angular state/interval, radius | `rigid_newton_euler`, `angular_velocity_derivative`, `fixed_axis_speed` | Native now; IR query replaces text output choice | none | rollback | each query branch, zero torque, angular-rest state; invariance |
| `horizontal_friction_force` | static bound or `f_k=μ_kmg`; `solvers/energy_vibration.py:HorizontalFrictionForceSolver.solve` | D (static/kinetic/motion phrasing); D/I | particle, horizontal contact, gravity, friction regime | contact normal/friction laws | Gate/partial: promote only with IR friction regime/direction; otherwise terminal ambiguity | static/kinetic residual only | rollback | static bound, kinetic μ, μ=0, missing-regime terminal; invariance |
| `impulse_momentum` | `J=F_parallel Δt=m(vf-vi)`; `solvers/work_rotation_impulse.py:ImpulseMomentumSolver.solve` | I; D/I | particle, line/vector frame, force-time interval, states | `linear_impulse`, `linear_impulse_momentum` | Native now | none | rollback | solve J/vf, signed force, zero duration, residual; invariance |
| `work_energy_speed` | `vf=sqrt(vi²+2W/m)`; `solvers/energy_vibration.py:WorkEnergySpeedSolver.solve` | D (rest phrase); D/N | particle, mass, work, initial/final velocity states | `particle_work_energy` and kinetic-energy relation | Native now with explicit rest/state condition | none; discard phrase default | rollback | vi=0, positive/negative work domain, energy residual; invariance |
| `spring_mass_vibration` | free SHM `T,f,ωn`; `solvers/energy_vibration.py:SpringMassVibrationSolver.solve` | I; D/I | mass, spring, displacement, time, free/undamped assumption | `spring_force`, `linear_vibration`, `vibration_natural_frequency` | Gate/partial: native ODE exists; add verified period/frequency output relation before promotion | frequency/ODE residual only | rollback | T/f/ω identities, m/k scaling, initial-condition residual; invariance |
| `spring_energy_speed` | `E=½kx²`, `\|v\|=\|x\|sqrt(k/m)`; `solvers/energy_vibration.py:SpringEnergySpeedSolver.solve` | D (energy phrase fallback); D/I | mass, spring, displacement/state, energy query | `spring_potential`, kinetic energy, energy conservation constraint | Native now from typed energy/state constraint; IR query replaces phrase fallback | none; discard text fallback | rollback | energy and speed queries, x=0, dimension/residual; invariance |
| `flat_curve_friction` | `vmax=sqrt(μgR)`; `solvers/curves.py:FlatCurveFrictionSolver.solve` | I; D/I | particle, circular path/radial frame, horizontal contact | `particle_normal_acceleration`, contact friction, radial Newton balance | Gate/partial: require limiting static-friction regime and radial frame in IR | centripetal/friction residual only | rollback | μ=0, threshold equality, centripetal/friction residual; invariance |
| `banked_curve_no_friction` | `v=sqrt(gR tanθ)`; `solvers/curves.py:BankedCurveNoFrictionSolver.solve` | I; D/I | particle, bank geometry, circular path, normal contact | normal/radial Newton balances plus geometry projection | Gate/partial: bank-angle force-projection relation must be explicit graph geometry | algebraic balance residual only | rollback | θ→0 terminal/domain, force-balance residual, sign/frame; invariance |
| `relative_acceleration_translation` | `aB=aA+aB/A`; `solvers/rigid_body_2d/relative_motion.py:RelativeAccelerationTranslationSolver.solve` | D (component wording); D/I | two points, vector acceleration components, translating frame | translating-frame relative-acceleration law | Unsupported typed-law gap: no dedicated translating-frame emission in `CORE_LAW_CATALOG` | no reuse until law exists | rollback only | typed scalar/vector cases after law; current terminal unsupported; invariance |
| `coriolis_relative_motion` | `aC=2ωvrel`, polar relative acceleration; `solvers/advanced_dynamics.py:CoriolisRelativeMotionSolver.solve` | D; D/I | rotating frame, relative coordinate/speed, angular state | precise Coriolis/rotating-frame law | Unsupported law gap: compiler explicitly reports rotating-frame relative motion as specialized (`compiler.py:_structural_reference_issue`) | no reuse until a graph law exists | rollback only | typed rotating-frame cases after law exists; current expected terminal unsupported; invariance |
| `plane_rigid_body_acceleration` | `aB=aA+α×r+ω×(ω×r)` and components; `solvers/rigid_body_2d/acceleration.py:PlaneRigidBodyAccelerationSolver.solve` | D (fixed/point text); D/I | rigid body, A/B points, rBA vector, angular state | `rigid_point_tangential_acceleration`, `rigid_point_normal_acceleration` | Gate/partial: complete verified vector composition/point binding before promotion | graph-derived vector residual only | rollback | fixed A, nonzero aA, tangential/normal vector residual; invariance |
| `polar_kinematics` | polar `v` and `a` components; `solvers/advanced_motion.py:PolarKinematicsSolver.solve` | D (`_constant_radius_is_explicit` and `_constant_angular_speed_is_explicit` read `c.raw_text`); D/I | polar frame, r/θ derivatives and query | polar-coordinate kinematics law | Unsupported law gap: core catalog has no polar-coordinate emission | no reuse until law exists | rollback only | typed v/a component cases after law; current terminal unsupported; invariance |
| `instant_center_velocity` | `ω=v/r` or `v=ωr`; `solvers/advanced_motion.py:InstantCenterVelocitySolver.solve` | I; D/I | rigid body, instantaneous center/point radius, speed/ω | `fixed_axis_speed` or `rigid_point_velocity` | Native now if instantaneous-center relation is typed geometry | none | rollback | solve either variable, zero-radius domain, residual; invariance |
| `slot_pin_relative_motion` | radial/tangential slot-pin speed/acceleration components; `solvers/advanced_motion.py:SlotPinRelativeMotionSolver.solve` | I; D/I | slot/pin geometry, polar coordinate derivatives | polar relative-motion law | Unsupported law gap: no slot/pin or polar-coordinate emission | no reuse until law exists | rollback only | radial-only/tangential-only/general cases after law; current terminal unsupported; invariance |
| `plane_rigid_body_velocity` | `vB=vA+ω×rBA`, fixed-point `ωr`; `solvers/rigid_body_2d/velocity.py:PlaneRigidBodyVelocitySolver.solve` | D (fixed-point/component text); D/I | rigid body, A/B points, rBA vector, angular velocity | `rigid_point_velocity` | Native now for IR-backed points/vectors | none; discard phrase parser | rollback | fixed A and moving A, vector magnitude/direction residual; invariance |

## Waves, parity policy, and release gates

**Wave 0 — prove the boundary before migration.**  Add only offline,
IR-built fixtures for every matrix parity case; compile, fingerprint, plan,
solve, and independently compare graph residuals to an off-mode legacy oracle.
No label or raw-text selection enters this harness.

**Wave 1 — native laws already catalogued.**  Migrate `single_particle_newton`,
both incline solvers, all three ideal/inertial pulley variants, `collision_1d`,
`constant_acceleration_1d`, `constant_force_work`, `fixed_axis_rotation`,
`impulse_momentum`, `work_energy_speed`, `spring_energy_speed`,
`instant_center_velocity`, and `plane_rigid_body_velocity`.  Keep their
legacy solvers off-mode until their individual parity evidence is independently
accepted.

**Wave 2 — coverage gates and graph-pattern kernels, not legacy routing.**
Close the typed shape-inertia, radial-state, event-root, friction-regime,
vibration-output, force-projection, and full-vector gates for
`pure_rolling_energy`, `rolling_energy_general`, `vertical_circle`,
`projectile_motion`, `horizontal_friction_force`, `spring_mass_vibration`,
both curve solvers, and `plane_rigid_body_acceleration`; then run the listed
graph-pattern numerical residuals as differential oracles.  Promote only
after the generic result itself passes verification.

**Wave 3 — named law gaps.**  Implement and validate typed laws for
`relative_acceleration_translation`, `coriolis_relative_motion`,
`polar_kinematics`, and `slot_pin_relative_motion`; until then their generic
disposition is a precise, verified unsupported terminal, with legacy rollback
off-mode only.

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

1. `single_particle_newton` — **ACCEPTED (1/29)** at exact checkpoint
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

2. `incline_no_friction` — **ACCEPTED (2/29)** at exact product/CI checkpoint
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

The remaining `27/29` entries have no accepted same-fixture parity claim. The
next canonical registry entry is 3, `incline_with_friction`; its matrix gate is
the typed static-hold/sliding regime with hold/slip boundary, `mu=0` reduction,
direction-contradiction rejection, residual parity, and invariance evidence.

## Risks retained

* The registry itself presently contains label/raw-text routing and capability
  checks (`backend/engine/solvers/registry.py:SolverRegistry._variant_specs`,
  `_has_symbol`, and `route`); these are diagnostics to remove from the
  generic authority path, not a migration target for the matrix.
* Conservation/event roots and polar/rotating-frame kinematics are the stated
  coverage risks.  They need typed IR, graph laws, and verification hooks;
  closed-form legacy output is not a substitute.
* This document is an inventory, plan, and limited accepted-evidence ledger.
  Only the two named entries above (`2/29`) have parity passes. No corpus/PDF
  inputs were opened or used for that evidence.
