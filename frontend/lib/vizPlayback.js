// Phase 54: deterministic playback state machine.
// Simulation time is always stepIndex * fixed_dt with an integer stepIndex,
// so pausing, stepping, changing speed, and resetting are exactly
// reproducible and never accumulate floating-point drift.

const { totalSteps, timeAtStep } = require('./motionProgram');

const SPEEDS = [0.25, 0.5, 1];

function createPlayback(scene) {
  return {
    stepIndex: 0,
    playing: false,
    speed: 1,
    accumulatorMs: 0,
    finished: false,
  };
}

function currentTime(scene, state) {
  return timeAtStep(scene, state.stepIndex);
}

function _clampToEnd(scene, state) {
  const steps = totalSteps(scene);
  if (state.stepIndex >= steps) {
    if (scene.timestep.loop) {
      state.stepIndex = state.stepIndex % steps;
    } else {
      state.stepIndex = steps;
      state.playing = false;
      state.finished = true;
      state.accumulatorMs = 0;
    }
  }
  return state;
}

// Advance from a wall-clock frame delta. Only whole fixed steps are taken;
// the remainder stays in the accumulator. Long deltas (background tab
// wake-ups) are capped so the scene does not teleport.
function tick(scene, state, elapsedMs) {
  if (!state.playing || state.finished) return state;
  const dtMs = scene.timestep.fixed_dt * 1000;
  const capped = Math.min(Math.max(elapsedMs, 0), 250);
  state.accumulatorMs += capped * state.speed;
  while (state.accumulatorMs >= dtMs) {
    state.accumulatorMs -= dtMs;
    state.stepIndex += 1;
    _clampToEnd(scene, state);
    if (state.finished) break;
  }
  return state;
}

function play(scene, state) {
  if (state.finished) reset(scene, state);
  state.playing = true;
  return state;
}

function pause(scene, state) {
  state.playing = false;
  state.accumulatorMs = 0;
  return state;
}

function stepOnce(scene, state) {
  state.playing = false;
  state.accumulatorMs = 0;
  if (state.finished) return state;
  state.stepIndex += 1;
  _clampToEnd(scene, state);
  return state;
}

function reset(scene, state) {
  state.stepIndex = 0;
  state.playing = false;
  state.accumulatorMs = 0;
  state.finished = false;
  return state;
}

function setSpeed(scene, state, speed) {
  if (SPEEDS.includes(speed)) {
    state.speed = speed;
    state.accumulatorMs = 0;
  }
  return state;
}

module.exports = {
  SPEEDS,
  createPlayback,
  currentTime,
  tick,
  play,
  pause,
  stepOnce,
  reset,
  setSpeed,
};
