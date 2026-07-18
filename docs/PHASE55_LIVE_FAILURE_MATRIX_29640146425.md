# Phase 55 live baseline failure matrix

This document is the privacy-safe autopsy of live run `29640146425`, job
`88069890289`, evaluated at exact head
`b1f86ea35de3eba11186857cf9b3865f9e07f723`.

It intentionally contains no problem text, prompt text, raw model response,
answer, stack trace, or secret. `Unavailable` means the baseline runner did not
record the field; it must not be interpreted as an empty model value or zero
usage.

Root-cause categories are the categories A-O defined by the Phase 55 one-shot
stabilization brief. A slash lists the nearest primary cause followed by an
important contributing cause.

| case | expected terminal / system | actual terminal / system | initial / repair | attempts / retries | sanitized diagnostics | candidate and binding | tokens (input, cached, output, reasoning) | closest root cause |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `newton_001` | `solver_gap` / `single_particle_newton` | `needs_confirmation` / `newtonian_particle_dynamics` | Pydantic failure / schema success, validator veto | 2 / 1 | attempt 1: `pydantic_validation_error`, `value_error`, path `[]`; vetoes `capability_missing`, `quantity_span_mismatch`; response status and incomplete reason unavailable | candidate present; selected false; completeness 1.0; ID counts unavailable; solver none | 3343, 2816, 664, 72; first-attempt usage unavailable | C / E |
| `solver_gap_001` | `solver_gap` / `nonlinear_turbulent_flow` | `solver_gap` / none | success / not requested | 1 / 0 | no exception; unsupported structure represented without a routable candidate; response status unavailable | candidate absent; binding unavailable; solver none | 3318, 2816, 516, 57 | D / M |
| `rigid_001` | `solver_gap` / `fixed_axis_rotation` | `parser_error` / none | Pydantic failure / Pydantic failure | 2 / 1 | both attempts: `pydantic_validation_error`, `value_error`, path `[]`; response status and incomplete reason unavailable | payload unavailable after schema failure; candidate and ID counts unavailable | usage unavailable for both attempts | G / B |
| `rolling_001` | `solver_gap` / `pure_rolling_energy` | `solver_gap` / `rolling_without_slipping` | success / not requested | 1 / 0 | veto `capability_missing`; free-form `speed` used instead of `velocity` | candidate present; selected false; completeness 0.75; solver none | 3326, 2816, 691, 128 | C / D |
| `figure_001` | `needs_figure` / none | `parser_error` / none | Pydantic failure / Pydantic failure | 2 / 1 | both attempts: `pydantic_validation_error`, `value_error`, path `[]`; response status and incomplete reason unavailable | payload unavailable after schema failure; candidate and ID counts unavailable | usage unavailable for both attempts | M / B |
| `pulley_001` | `solver_gap` / `pulley_atwood` | `parser_error` / none | Pydantic failure / Pydantic failure | 2 / 1 | both attempts: `pydantic_validation_error`, `value_error`, path `[]`; response status and incomplete reason unavailable | payload unavailable after schema failure; candidate and ID counts unavailable | usage unavailable for both attempts | G / B |
| `work_energy_001` | `solver_gap` / `constant_force_work` | `needs_confirmation` / `work_interval` | success / not requested | 1 / 0 | vetoes `capability_missing`, `quantity_span_mismatch` | candidate present; selected false; completeness 1.0; solver none | 3320, 2816, 829, 239 | C / E |
| `insufficient_001` | `insufficient_information` / none | `insufficient_information` / `kinematics` | success / not requested | 1 / 0 | terminal correct; non-canonical free-form candidate type produced `capability_missing` | candidate present; selected false; completeness 1.0; solver none | 3300, 2816, 535, 164 | C / N |
| `kinematics_001` | accepted deterministic solve / `constant_acceleration_1d` | `solver_gap` / `kinematics` | success / not requested | 1 / 0 | veto `capability_missing`; accepted `starts_from_rest` proposal was not closed into candidate inputs | candidate present; selected false; completeness 1.0; missing-symbol detail unavailable in baseline; solver none | 3317, 2816, 662, 73 | C / I / J |
| `vibration_001` | `solver_gap` / `spring_mass_vibration` | `solver_gap` / `periodic_motion` | success / not requested | 1 / 0 | veto `capability_missing`; free-form `time_period` used instead of `period` | candidate present; selected false; completeness 0.666667; solver none | 3313, 2816, 501, 88 | C / D |
| `collision_001` | `solver_gap` / `impulse_momentum` | `needs_confirmation` / `impulse_interval` | success / not requested | 1 / 0 | vetoes `capability_missing`, `temporal_binding_ambiguous`; pre-impact state at target start was not representable by V1 boundary policy | candidate present; selected false; completeness 0.8; solver none | 3326, 2816, 824, 125 | H / C |
| `projectile_001` | `solver_gap` / `projectile_motion` | `solver_gap` / `projectile_motion` | success / not requested | 1 / 0 | veto `capability_missing`; free-form semantic synonyms `launch_angle` and `signboard_height` | candidate present; selected false; completeness 0.8; solver none | 3336, 2816, 1015, 185 | D / N |
| `newton_002` | `solver_gap` / `single_particle_newton` | `solver_gap` / `particle_under_net_force` | success / not requested | 1 / 0 | veto `capability_missing` | candidate present; selected false; completeness 1.0; solver none | 3322, 2816, 719, 128 | C |
| `solver_gap_002` | `solver_gap` / `nonlinear_turbulent_flow` | `solver_gap` / none | success / not requested | 1 / 0 | no exception; unsupported structure represented without a routable candidate; free-form `drag_force` | candidate absent; binding unavailable; solver none | 3318, 2816, 484, 123 | D / M |
| `rigid_002` | `solver_gap` / `fixed_axis_rotation` | `parser_error` / none | Pydantic failure / Pydantic failure | 2 / 1 | both attempts: `pydantic_validation_error`, `value_error`, path `[]`; response status and incomplete reason unavailable | payload unavailable after schema failure; candidate and ID counts unavailable | usage unavailable for both attempts | G / B |
| `rolling_002` | `solver_gap` / `pure_rolling_energy` | `needs_confirmation` / `rolling_without_slipping` | success / not requested | 1 / 0 | vetoes `capability_missing`, `quantity_span_mismatch`; free-form `speed` | candidate present; selected false; completeness 0.75; solver none | 3326, 2816, 672, 95 | C / D / E |
| `figure_002` | `needs_figure` / none | `parser_error` / none | Pydantic failure / Pydantic failure | 2 / 1 | both attempts: `pydantic_validation_error`, `value_error`, path `[]`; response status and incomplete reason unavailable | payload unavailable after schema failure; candidate and ID counts unavailable | usage unavailable for both attempts | M / B |
| `pulley_002` | `solver_gap` / `pulley_atwood` | `parser_error` / none | Pydantic failure / Pydantic failure | 2 / 1 | both attempts: `pydantic_validation_error`, `value_error`, path `[]`; response status and incomplete reason unavailable | payload unavailable after schema failure; candidate and ID counts unavailable | usage unavailable for both attempts | G / B |
| `work_energy_002` | `solver_gap` / `constant_force_work` | `parser_error` / none | Pydantic failure / Pydantic failure | 2 / 1 | both attempts: `pydantic_validation_error`, `value_error`, path `[]`; response status and incomplete reason unavailable | payload unavailable after schema failure; candidate and ID counts unavailable | usage unavailable for both attempts | F / B |
| `insufficient_002` | `insufficient_information` / none | `insufficient_information` / `kinematics_time` | success / not requested | 1 / 0 | terminal correct; non-canonical free-form candidate type produced `capability_missing` | candidate present; selected false; completeness 1.0; solver none | 3300, 2816, 421, 50 | C / N |

## Common causes

All seven `repair_failed` cases shared the same observable failure shape:

1. Structured JSON reached Pydantic, but the monolithic after-model graph validator
   raised a root-level `value_error` with field path `[]`.
2. The repair request received only the code `schema_error`, without a field path,
   referenced ID, reason code, enum vocabulary, or closure metadata.
3. The second complete parse therefore repeated the same root-level failure.
4. The rigid and pulley pairs strongly localize the structural problem to point and
   aggregate query closure; the figure pair localizes it to the terminal minimal
   graph contract. `work_energy_002` cannot be localized further from the retained
   telemetry and remains category F/B rather than a fabricated field diagnosis.

The `kinematics_001` solver gap had two independent blockers: the model emitted the
free-form system synonym `kinematics` rather than `constant_acceleration_1d`, and a
server-accepted `starts_from_rest` proposal was not deterministically attached to
the candidate that required `v0`.

## Output budget conclusion

The job retained no `incomplete_details.reason=max_output_tokens`, length-finish
exception, near-ceiling output count, or truncated-object signal. The zero token
totals on the seven schema failures mean usage was unavailable, not that no tokens
were consumed. There is therefore no evidence-based authorization to increase the
1,800-token output limit at this stage.
