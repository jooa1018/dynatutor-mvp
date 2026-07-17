// Phase 54: runtime schema validation tests for VisualizationScene v1.0.
const test = require('node:test');
const assert = require('node:assert/strict');

const { validateScene, SCENE_SCHEMA, SCENE_VERSION } = require('../lib/visualizationScene');

function readyScene() {
  return {
    schema: SCENE_SCHEMA,
    version: SCENE_VERSION,
    status: 'ready',
    scene_type: 'incline_block',
    scene_label: '경사면 블록',
    source_solver: 'incline_no_friction',
    simulation_mode: 'kinematic_playback',
    coordinate_frame: { axes: ['x'], positive_directions: ['경사면 아래쪽'], source: 'physical_model' },
    bodies: [
      {
        id: 'incline', label: '경사면', role: 'incline_surface',
        shape: { kind: 'wedge', angle_deg: 30, base_length: 6 },
        body_type: 'fixed', initial_position: { x: 0, y: 0 }, initial_angle: 0, schematic_size: true,
      },
      {
        id: 'block', label: '블록', role: 'block',
        shape: { kind: 'rect', half_width: 0.4, half_height: 0.25 },
        body_type: 'kinematic', initial_position: { x: 1, y: 2 }, initial_angle: -0.5, schematic_size: true,
      },
    ],
    motion: [
      {
        id: 'slide', body_id: 'block', kind: 'uniform_acceleration',
        t_start: 0, t_end: 2,
        position0: { x: 1, y: 2 }, velocity0: { x: 0, y: 0 }, acceleration: { x: 4.2, y: -2.4 },
      },
      { id: 'settle', body_id: 'block', kind: 'rest', t_start: 2, t_end: 2.8, position0: { x: 8, y: -2 } },
    ],
    forces: [
      { id: 'w', body_id: 'block', kind: 'weight', label: '중력', symbol: 'mg', direction: { x: 0, y: -1 }, behavior: 'fixed', schematic_length: true },
    ],
    constraints: [{ kind: 'contact', description: '경사면 위' }],
    axes: [{ kind: 'positive_x', origin: { x: 0, y: 0 }, direction: { x: 0.87, y: -0.5 }, label: '+x' }],
    events: [],
    camera: { min_x: -1, min_y: -1, max_x: 8, max_y: 5 },
    timestep: { fixed_dt: 1 / 120, duration: 2.8, loop: false },
    answer_overlay: [
      { label: '가속도', display: 'a = 4.905 m/s²', numeric: 4.905, unit: 'm/s²', output_key: 'acceleration', source: 'backend' },
    ],
    scene_description: '경사면 블록 장면',
    assumptions: [], warnings: [], schematic_notes: [],
    fallback_reason: null,
    authority: {
      answer_authority: 'backend',
      visualization_authority: 'approximate',
      grading: false,
      answer_selection: false,
      student_answer_overwrite: false,
    },
  };
}

test('valid ready scene passes', () => {
  const result = validateScene(readyScene());
  assert.deepEqual(result.errors, []);
  assert.equal(result.ok, true);
});

test('unavailable scene needs fallback_reason', () => {
  const scene = readyScene();
  scene.status = 'unavailable';
  scene.bodies = [];
  scene.motion = [];
  scene.fallback_reason = null;
  assert.equal(validateScene(scene).ok, false);
  scene.fallback_reason = '아직 지원하지 않습니다.';
  assert.equal(validateScene(scene).ok, true);
});

test('rejects NaN and Infinity numbers', () => {
  const withNan = readyScene();
  withNan.motion[0].acceleration.x = NaN;
  assert.equal(validateScene(withNan).ok, false);

  const withInf = readyScene();
  withInf.camera.max_x = Infinity;
  assert.equal(validateScene(withInf).ok, false);
});

test('rejects unknown body references', () => {
  const badMotion = readyScene();
  badMotion.motion[0].body_id = 'ghost';
  assert.equal(validateScene(badMotion).ok, false);

  const badForce = readyScene();
  badForce.forces[0].body_id = 'ghost';
  assert.equal(validateScene(badForce).ok, false);
});

test('rejects wrong schema, version, and simulation mode', () => {
  const wrongSchema = readyScene();
  wrongSchema.schema = 'other.schema';
  assert.equal(validateScene(wrongSchema).ok, false);

  const wrongVersion = readyScene();
  wrongVersion.version = '2.0';
  assert.equal(validateScene(wrongVersion).ok, false);

  const wrongMode = readyScene();
  wrongMode.simulation_mode = 'dynamic';
  assert.equal(validateScene(wrongMode).ok, false);
});

test('rejects tampered authority metadata', () => {
  for (const patch of [
    { answer_authority: 'frontend' },
    { visualization_authority: 'exact' },
    { grading: true },
    { answer_selection: true },
    { student_answer_overwrite: true },
  ]) {
    const scene = readyScene();
    Object.assign(scene.authority, patch);
    assert.equal(validateScene(scene).ok, false, JSON.stringify(patch));
  }
});

test('rejects overlapping motion segments and non-backend overlay', () => {
  const overlapping = readyScene();
  overlapping.motion[1] = {
    id: 'dup', body_id: 'block', kind: 'rest', t_start: 1, t_end: 3, position0: { x: 0, y: 0 },
  };
  assert.equal(validateScene(overlapping).ok, false);

  const foreignOverlay = readyScene();
  foreignOverlay.answer_overlay[0].source = 'rapier';
  assert.equal(validateScene(foreignOverlay).ok, false);
});

test('rejects ready scene without playback material', () => {
  const noMotion = readyScene();
  noMotion.motion = [];
  assert.equal(validateScene(noMotion).ok, false);

  const noOverlay = readyScene();
  noOverlay.answer_overlay = [];
  assert.equal(validateScene(noOverlay).ok, false);

  const noCamera = readyScene();
  noCamera.camera = null;
  assert.equal(validateScene(noCamera).ok, false);
});

test('rejects non-object payloads', () => {
  assert.equal(validateScene(null).ok, false);
  assert.equal(validateScene([]).ok, false);
  assert.equal(validateScene('scene').ok, false);
});
