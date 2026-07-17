// Phase 54: closed-form evaluation of VisualizationScene motion programs.
// Pure and deterministic: state at time t is a function of the scene only,
// which is what makes reset/step playback exactly reproducible.

function segmentsForBody(scene, bodyId) {
  const segs = (scene.motion || []).filter((s) => s.body_id === bodyId);
  segs.sort((a, b) => a.t_start - b.t_start);
  return segs;
}

function evalSegmentAt(seg, t) {
  const dt = Math.max(0, Math.min(t, seg.t_end) - seg.t_start);
  let x; let y; let vx = 0; let vy = 0; let ax = 0; let ay = 0;
  if (seg.kind === 'rest') {
    x = seg.position0.x;
    y = seg.position0.y;
  } else if (seg.kind === 'uniform_acceleration') {
    x = seg.position0.x + seg.velocity0.x * dt + 0.5 * seg.acceleration.x * dt * dt;
    y = seg.position0.y + seg.velocity0.y * dt + 0.5 * seg.acceleration.y * dt * dt;
    vx = seg.velocity0.x + seg.acceleration.x * dt;
    vy = seg.velocity0.y + seg.acceleration.y * dt;
    ax = seg.acceleration.x;
    ay = seg.acceleration.y;
  } else if (seg.kind === 'oscillation') {
    const phase = (seg.phase || 0) + seg.omega * dt;
    const s = seg.amplitude * Math.cos(phase);
    const sv = -seg.amplitude * seg.omega * Math.sin(phase);
    const sa = -seg.amplitude * seg.omega * seg.omega * Math.cos(phase);
    x = seg.origin.x + seg.axis.x * s;
    y = seg.origin.y + seg.axis.y * s;
    vx = seg.axis.x * sv;
    vy = seg.axis.y * sv;
    ax = seg.axis.x * sa;
    ay = seg.axis.y * sa;
  } else {
    throw new Error(`unknown motion kind: ${seg.kind}`);
  }
  let angle = 0;
  let angularVelocity = 0;
  if (seg.angle0 != null || seg.angular_velocity0 != null || seg.angular_acceleration != null) {
    const a0 = seg.angle0 || 0;
    const w0 = seg.angular_velocity0 || 0;
    const al = seg.angular_acceleration || 0;
    angle = a0 + w0 * dt + 0.5 * al * dt * dt;
    angularVelocity = w0 + al * dt;
  }
  return { x, y, vx, vy, ax, ay, angle, angularVelocity, segmentId: seg.id };
}

// Body state at time t. Before the first segment: its start pose. After the
// last segment (or in gaps): the previous segment's end pose, at rest.
function evaluateBody(scene, body, t) {
  if (body.body_type !== 'kinematic') {
    return {
      x: body.initial_position.x,
      y: body.initial_position.y,
      vx: 0, vy: 0, ax: 0, ay: 0,
      angle: body.initial_angle || 0,
      angularVelocity: 0,
      segmentId: null,
    };
  }
  const segs = segmentsForBody(scene, body.id);
  if (!segs.length) {
    return {
      x: body.initial_position.x,
      y: body.initial_position.y,
      vx: 0, vy: 0, ax: 0, ay: 0,
      angle: body.initial_angle || 0,
      angularVelocity: 0,
      segmentId: null,
    };
  }
  let carriedAngle = 0;
  let lastEnd = null;
  for (const seg of segs) {
    if (t < seg.t_start) {
      if (lastEnd) return { ...lastEnd, vx: 0, vy: 0, ax: 0, ay: 0, angularVelocity: 0 };
      const first = evalSegmentAt(seg, seg.t_start);
      if (seg.angle0 == null && seg.angular_velocity0 == null && seg.angular_acceleration == null) {
        first.angle = body.initial_angle || 0;
      }
      return { ...first, vx: 0, vy: 0, ax: 0, ay: 0, angularVelocity: 0 };
    }
    if (t < seg.t_end) {
      const state = evalSegmentAt(seg, t);
      if (seg.angle0 == null && seg.angular_velocity0 == null && seg.angular_acceleration == null) {
        state.angle = carriedAngle || body.initial_angle || 0;
      }
      return state;
    }
    lastEnd = evalSegmentAt(seg, seg.t_end);
    if (seg.angle0 != null || seg.angular_velocity0 != null || seg.angular_acceleration != null) {
      carriedAngle = lastEnd.angle;
    } else {
      lastEnd.angle = carriedAngle || body.initial_angle || 0;
    }
  }
  return { ...lastEnd, vx: 0, vy: 0, ax: 0, ay: 0, angularVelocity: 0 };
}

function evaluateAll(scene, t) {
  const out = {};
  for (const body of scene.bodies || []) {
    out[body.id] = evaluateBody(scene, body, t);
  }
  return out;
}

// Student-facing readouts must identify every moving body.  Returning one row
// per kinematic body avoids the old collision bug where the first cart's speed
// was shown without a label while the second cart was silently omitted.
function motionReadouts(scene, t) {
  const states = evaluateAll(scene, t);
  const out = [];
  for (const body of scene.bodies || []) {
    if (body.body_type !== 'kinematic') continue;
    const state = states[body.id];
    if (!state) continue;
    out.push({
      bodyId: body.id,
      label: body.label || body.id,
      speed: Math.hypot(state.vx, state.vy),
      acceleration: Math.hypot(state.ax, state.ay),
    });
  }
  return out;
}

function totalDuration(scene) {
  return scene.timestep.duration;
}

function totalSteps(scene) {
  return Math.max(1, Math.round(scene.timestep.duration / scene.timestep.fixed_dt));
}

function timeAtStep(scene, stepIndex) {
  const n = Math.max(0, Math.min(stepIndex, totalSteps(scene)));
  return n * scene.timestep.fixed_dt;
}

function forceVisibleAt(force, t) {
  if (force.visible_t_start != null && t < force.visible_t_start) return false;
  if (force.visible_t_end != null && t > force.visible_t_end) return false;
  return true;
}

// Restoring (spring) arrows point from the body toward the segment origin.
function restoringDirection(scene, force, t) {
  const body = (scene.bodies || []).find((b) => b.id === force.body_id);
  if (!body) return null;
  const seg = segmentsForBody(scene, force.body_id).find((s) => s.kind === 'oscillation');
  if (!seg) return null;
  const state = evaluateBody(scene, body, t);
  const dx = seg.origin.x - state.x;
  const dy = seg.origin.y - state.y;
  const len = Math.hypot(dx, dy);
  if (len < 1e-9) return { x: 0, y: 0 };
  return { x: dx / len, y: dy / len };
}

// Reduced-motion staged states: start, each event, a midpoint when there are
// no events, and the final state.
function snapshotTimes(scene) {
  const duration = totalDuration(scene);
  const times = [0];
  const events = (scene.events || []).map((e) => e.t).filter((t) => t > 0 && t < duration);
  events.sort((a, b) => a - b);
  if (events.length) {
    for (const t of events) {
      if (t - 0.001 > times[times.length - 1]) times.push(Math.max(0, t - 0.001));
      times.push(Math.min(duration, t + 0.001));
    }
  } else {
    times.push(duration / 2);
  }
  times.push(duration);
  return times;
}

function snapshotLabel(scene, index, times) {
  const t = times[index];
  const duration = totalDuration(scene);
  if (index === 0) return '시작 상태 (t = 0 s)';
  if (index === times.length - 1) return `최종 상태 (t = ${duration.toFixed(2)} s)`;
  const near = (scene.events || []).find((e) => Math.abs(e.t - t) <= 0.002);
  if (near) return `${near.label} ${t < near.t ? '직전' : '직후'} (t = ${t.toFixed(2)} s)`;
  return `중간 상태 (t = ${t.toFixed(2)} s)`;
}

module.exports = {
  evaluateBody,
  evaluateAll,
  motionReadouts,
  totalDuration,
  totalSteps,
  timeAtStep,
  forceVisibleAt,
  restoringDirection,
  snapshotTimes,
  snapshotLabel,
};
