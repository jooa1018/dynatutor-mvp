// Phase 54: playback state machine tests (fixed timestep, controls, reset).
const test = require('node:test');
const assert = require('node:assert/strict');

const playback = require('../lib/vizPlayback');

const DT = 1 / 120;

function scene(loop = false, duration = 1) {
  return { timestep: { fixed_dt: DT, duration, loop }, bodies: [], motion: [], events: [] };
}

test('initial state is paused at t = 0', () => {
  const s = scene();
  const st = playback.createPlayback(s);
  assert.equal(st.playing, false);
  assert.equal(playback.currentTime(s, st), 0);
  assert.equal(st.speed, 1);
});

test('tick advances only whole fixed steps while playing', () => {
  const s = scene();
  const st = playback.createPlayback(s);
  playback.tick(s, st, 1000); // paused: no advance
  assert.equal(st.stepIndex, 0);

  playback.play(s, st);
  playback.tick(s, st, DT * 1000 * 3 + 1); // ~3 steps
  assert.equal(st.stepIndex, 3);
  // Simulation time is exactly stepIndex * dt (no drift).
  assert.equal(playback.currentTime(s, st), 3 * DT);
});

test('speed multipliers scale wall-clock consumption, not the timestep', () => {
  const s = scene();
  const st = playback.createPlayback(s);
  playback.play(s, st);
  playback.setSpeed(s, st, 0.25);
  playback.tick(s, st, DT * 1000 * 4); // 4 frames of wall clock at 0.25× = 1 step
  assert.equal(st.stepIndex, 1);
  playback.setSpeed(s, st, 0.5);
  playback.tick(s, st, DT * 1000 * 4);
  assert.equal(st.stepIndex, 3);
  // Unknown speeds are rejected.
  playback.setSpeed(s, st, 3);
  assert.equal(st.speed, 0.5);
});

test('stepOnce advances exactly one step and pauses', () => {
  const s = scene();
  const st = playback.createPlayback(s);
  playback.play(s, st);
  playback.stepOnce(s, st);
  assert.equal(st.playing, false);
  assert.equal(st.stepIndex, 1);
  playback.stepOnce(s, st);
  assert.equal(st.stepIndex, 2);
});

test('reset returns to step 0 and is reproducible after any history', () => {
  const s = scene();
  const st = playback.createPlayback(s);
  playback.play(s, st);
  playback.tick(s, st, 500);
  playback.stepOnce(s, st);
  playback.reset(s, st);
  assert.deepEqual(
    { stepIndex: st.stepIndex, playing: st.playing, finished: st.finished, accumulatorMs: st.accumulatorMs },
    { stepIndex: 0, playing: false, finished: false, accumulatorMs: 0 },
  );
  assert.equal(playback.currentTime(s, st), 0);
});

test('non-looping playback clamps at the end and finishes', () => {
  const s = scene(false, 0.1); // 12 steps
  const st = playback.createPlayback(s);
  playback.play(s, st);
  playback.tick(s, st, 10000);
  assert.equal(st.finished, true);
  assert.equal(st.playing, false);
  assert.equal(playback.currentTime(s, st), s.timestep.duration);
  // Play after finish restarts from zero.
  playback.play(s, st);
  assert.equal(st.stepIndex, 0);
  assert.equal(st.finished, false);
});

test('looping playback wraps around', () => {
  const s = scene(true, 0.1);
  const st = playback.createPlayback(s);
  playback.play(s, st);
  playback.tick(s, st, DT * 1000 * 15); // 15 steps in a 12-step loop
  assert.equal(st.finished, false);
  assert.equal(st.stepIndex, 3);
});

test('long background deltas are capped so the scene does not teleport', () => {
  const s = scene(false, 60);
  const st = playback.createPlayback(s);
  playback.play(s, st);
  playback.tick(s, st, 60000); // fake 60s background gap
  assert.ok(st.stepIndex <= Math.ceil(250 / (DT * 1000)) + 1);
});
