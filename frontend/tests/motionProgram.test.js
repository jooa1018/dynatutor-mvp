// Phase 54: closed-form motion program evaluation tests.
const test = require('node:test');
const assert = require('node:assert/strict');

const motion = require('../lib/motionProgram');

const DT = 1 / 120;

function inclineScene() {
  return {
    bodies: [
      { id: 'block', body_type: 'kinematic', initial_position: { x: 0, y: 3 }, initial_angle: -0.3 },
      { id: 'incline', body_type: 'fixed', initial_position: { x: 0, y: 0 }, initial_angle: 0 },
    ],
    motion: [
      {
        id: 'slide', body_id: 'block', kind: 'uniform_acceleration', t_start: 0, t_end: 2,
        position0: { x: 0, y: 3 }, velocity0: { x: 0, y: 0 }, acceleration: { x: 3, y: -1.5 },
      },
      { id: 'settle', body_id: 'block', kind: 'rest', t_start: 2, t_end: 2.5, position0: { x: 6, y: 0 } },
    ],
    events: [],
    timestep: { fixed_dt: DT, duration: 2.5, loop: false },
  };
}

function springScene() {
  return {
    bodies: [{ id: 'mass', body_type: 'kinematic', initial_position: { x: 0.9, y: 0.35 }, initial_angle: 0 }],
    motion: [{
      id: 'osc', body_id: 'mass', kind: 'oscillation', t_start: 0, t_end: 4,
      origin: { x: 0, y: 0.35 }, axis: { x: 1, y: 0 }, amplitude: 0.9, omega: 10, phase: 0,
    }],
    events: [],
    timestep: { fixed_dt: DT, duration: 4, loop: true },
  };
}

function collisionScene(v1After, v2After) {
  const tC = 2;
  return {
    bodies: [
      { id: 'b1', body_type: 'kinematic', initial_position: { x: -8.35, y: 0.35 }, initial_angle: 0 },
      { id: 'b2', body_type: 'kinematic', initial_position: { x: 0.35, y: 0.35 }, initial_angle: 0 },
    ],
    motion: [
      { id: 'b1-before', body_id: 'b1', kind: 'uniform_acceleration', t_start: 0, t_end: tC, position0: { x: -8.35, y: 0.35 }, velocity0: { x: 4, y: 0 }, acceleration: { x: 0, y: 0 } },
      { id: 'b1-after', body_id: 'b1', kind: 'uniform_acceleration', t_start: tC, t_end: 4.2, position0: { x: -0.35, y: 0.35 }, velocity0: { x: v1After, y: 0 }, acceleration: { x: 0, y: 0 } },
      { id: 'b2-before', body_id: 'b2', kind: 'uniform_acceleration', t_start: 0, t_end: tC, position0: { x: 0.35, y: 0.35 }, velocity0: { x: 0, y: 0 }, acceleration: { x: 0, y: 0 } },
      { id: 'b2-after', body_id: 'b2', kind: 'uniform_acceleration', t_start: tC, t_end: 4.2, position0: { x: 0.35, y: 0.35 }, velocity0: { x: v2After, y: 0 }, acceleration: { x: 0, y: 0 } },
    ],
    events: [{ t: tC, kind: 'collision', label: '충돌' }],
    timestep: { fixed_dt: DT, duration: 4.2, loop: false },
  };
}

test('uniform acceleration follows p0 + v0 t + a t²/2 exactly', () => {
  const scene = inclineScene();
  const body = scene.bodies[0];
  const s = motion.evaluateBody(scene, body, 1.5);
  assert.ok(Math.abs(s.x - (0.5 * 3 * 1.5 * 1.5)) < 1e-12);
  assert.ok(Math.abs(s.y - (3 + 0.5 * -1.5 * 1.5 * 1.5)) < 1e-12);
  assert.ok(Math.abs(s.vx - 3 * 1.5) < 1e-12);
  assert.ok(Math.abs(s.ax - 3) < 1e-12);
});

test('rest segment holds position with zero velocity', () => {
  const scene = inclineScene();
  const body = scene.bodies[0];
  const s = motion.evaluateBody(scene, body, 2.3);
  assert.equal(s.x, 6);
  assert.equal(s.vx, 0);
  assert.equal(s.ay, 0);
});

test('oscillation matches A cos(ωt) and its derivatives', () => {
  const scene = springScene();
  const body = scene.bodies[0];
  const t = 0.7;
  const s = motion.evaluateBody(scene, body, t);
  assert.ok(Math.abs(s.x - 0.9 * Math.cos(10 * t)) < 1e-12);
  assert.ok(Math.abs(s.vx - (-0.9 * 10 * Math.sin(10 * t))) < 1e-12);
  assert.ok(Math.abs(s.ax - (-0.9 * 100 * Math.cos(10 * t))) < 1e-12);
});

test('fixed timestep evaluation is deterministic and reset-reproducible', () => {
  const scene = inclineScene();
  const body = scene.bodies[0];
  const stepA = motion.evaluateBody(scene, body, motion.timeAtStep(scene, 97));
  const stepB = motion.evaluateBody(scene, body, motion.timeAtStep(scene, 97));
  assert.deepEqual(stepA, stepB);
  // Reset: state at step 0 equals the initial pose regardless of history.
  const s0 = motion.evaluateBody(scene, body, motion.timeAtStep(scene, 0));
  assert.equal(s0.x, 0);
  assert.equal(s0.y, 3);
  assert.equal(s0.vx, 0);
});

test('collision timeline switches to backend post velocities at the event', () => {
  const v1After = -0.8;
  const v2After = 3.2;
  const scene = collisionScene(v1After, v2After);
  const b1 = scene.bodies[0];
  const b2 = scene.bodies[1];
  const before = motion.evaluateBody(scene, b1, 1.99);
  const after = motion.evaluateBody(scene, b1, 2.01);
  assert.ok(Math.abs(before.vx - 4) < 1e-9);
  assert.ok(Math.abs(after.vx - v1After) < 1e-9);
  const after2 = motion.evaluateBody(scene, b2, 2.01);
  assert.ok(Math.abs(after2.vx - v2After) < 1e-9);
  // The playback uses DTO velocities verbatim — no recomputation drift.
  assert.equal(after.vx, v1After);
  assert.equal(after2.vx, v2After);
});

test('angular playback integrates spin for rolling display', () => {
  const scene = inclineScene();
  scene.motion[0].angle0 = 0;
  scene.motion[0].angular_velocity0 = 0;
  scene.motion[0].angular_acceleration = -2;
  const body = scene.bodies[0];
  const s = motion.evaluateBody(scene, body, 1);
  assert.ok(Math.abs(s.angle - (0.5 * -2)) < 1e-12);
  assert.ok(Math.abs(s.angularVelocity - -2) < 1e-12);
});

test('fixed bodies never move', () => {
  const scene = inclineScene();
  const incline = scene.bodies[1];
  const s = motion.evaluateBody(scene, incline, 1.2);
  assert.equal(s.x, 0);
  assert.equal(s.vx, 0);
});

test('snapshot times cover start, events, and end for reduced motion', () => {
  const scene = collisionScene(-0.8, 3.2);
  const times = motion.snapshotTimes(scene);
  assert.equal(times[0], 0);
  assert.equal(times[times.length - 1], 4.2);
  assert.ok(times.some((t) => Math.abs(t - 2) <= 0.002));
  const labels = times.map((_, i) => motion.snapshotLabel(scene, i, times));
  assert.ok(labels[0].includes('시작'));
  assert.ok(labels[labels.length - 1].includes('최종'));
  assert.ok(labels.some((l) => l.includes('충돌')));

  const noEvents = inclineScene();
  const times2 = motion.snapshotTimes(noEvents);
  assert.equal(times2.length, 3); // start, midpoint, end
});

test('force visibility windows clip impulse arrows', () => {
  const force = { visible_t_start: 1.9, visible_t_end: 2.1 };
  assert.equal(motion.forceVisibleAt(force, 1.0), false);
  assert.equal(motion.forceVisibleAt(force, 2.0), true);
  assert.equal(motion.forceVisibleAt(force, 2.2), false);
  assert.equal(motion.forceVisibleAt({}, 99), true);
});

test('restoring direction points toward equilibrium', () => {
  const scene = springScene();
  const force = { body_id: 'mass', behavior: 'restoring', kind: 'spring_restoring' };
  const dirAtMax = motion.restoringDirection(scene, force, 0); // x = +A
  assert.ok(dirAtMax.x < 0);
  const half = Math.PI / 10; // ωt = π → x = -A
  const dirAtMin = motion.restoringDirection(scene, force, half);
  assert.ok(dirAtMin.x > 0);
});
