// Phase 54 follow-up: imported scenes must carry a valid motion readout policy.
const test = require('node:test');
const assert = require('node:assert/strict');

const { validateScene, SCENE_SCHEMA, SCENE_VERSION } = require('../lib/visualizationScene');

function springScene(mode) {
  return {
    schema: SCENE_SCHEMA,
    version: SCENE_VERSION,
    status: 'ready',
    scene_type: 'mass_spring',
    source_solver: 'spring_mass_vibration',
    simulation_mode: 'kinematic_playback',
    motion_readout_mode: mode,
    bodies: [
      {
        id: 'mass', label: '질량', role: 'block', body_type: 'kinematic',
        shape: { kind: 'rect', half_width: 0.3, half_height: 0.3 },
        initial_position: { x: 0.9, y: 0.3 }, initial_angle: 0,
      },
    ],
    motion: [
      {
        id: 'oscillate', body_id: 'mass', kind: 'oscillation',
        t_start: 0, t_end: 2, origin: { x: 0, y: 0.3 }, axis: { x: 1, y: 0 },
        amplitude: 0.9, omega: 10, phase: 0,
      },
    ],
    forces: [], constraints: [], axes: [], events: [],
    camera: { min_x: -2, min_y: -1, max_x: 2, max_y: 1 },
    timestep: { fixed_dt: 1 / 120, duration: 2, loop: false },
    answer_overlay: [
      { label: '주기', display: 'T = 0.628 s', numeric: 0.628, unit: 's', output_key: 'period', source: 'backend' },
    ],
    authority: {
      answer_authority: 'backend', visualization_authority: 'approximate',
      grading: false, answer_selection: false, student_answer_overwrite: false,
    },
  };
}

test('accepts numeric and direction-only readout modes', () => {
  assert.equal(validateScene(springScene('numeric')).ok, true);
  assert.equal(validateScene(springScene('direction_only')).ok, true);
});

test('rejects an unknown motion readout mode', () => {
  const result = validateScene(springScene('invented_numeric_scale'));
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((message) => message.includes('motion_readout_mode')));
});
