// Phase 54: runtime schema validation for VisualizationScene v1.0.
// The frontend never trusts a scene blindly — malformed or foreign payloads
// (including imported JSON) must fail here and fall back to the text answer.

const SCENE_SCHEMA = 'dynatutor.visualization_scene';
const SCENE_VERSION = '1.0';

const SCENE_TYPES = ['incline_block', 'mass_spring', 'pure_rolling', 'collision_1d', 'pendulum'];
const BODY_ROLES = ['block', 'wheel', 'cart', 'incline_surface', 'wall', 'ground', 'spring', 'equilibrium_marker'];
const SHAPE_KINDS = ['rect', 'circle', 'wedge', 'wall', 'spring_coil', 'ground_line'];
const MOTION_KINDS = ['rest', 'uniform_acceleration', 'oscillation'];
const FORCE_KINDS = ['weight', 'normal', 'friction', 'spring_restoring', 'impulse'];
const MOTION_READOUT_MODES = ['numeric', 'direction_only'];

function isFiniteNumber(v) {
  return typeof v === 'number' && Number.isFinite(v);
}

function isVec(v) {
  return v != null && typeof v === 'object' && isFiniteNumber(v.x) && isFiniteNumber(v.y);
}

function pushIf(errors, cond, message) {
  if (cond) errors.push(message);
}

function validateSegment(seg, bodyIds, errors) {
  const id = seg && seg.id ? seg.id : '(motion)';
  if (!seg || typeof seg !== 'object') { errors.push('motion segment가 객체가 아닙니다.'); return; }
  pushIf(errors, !bodyIds.has(seg.body_id), `${id}: 존재하지 않는 body를 참조합니다.`);
  pushIf(errors, !MOTION_KINDS.includes(seg.kind), `${id}: 알 수 없는 motion kind입니다.`);
  pushIf(errors, !isFiniteNumber(seg.t_start) || seg.t_start < 0, `${id}: t_start가 유효하지 않습니다.`);
  pushIf(errors, !isFiniteNumber(seg.t_end) || seg.t_end <= (seg.t_start ?? 0), `${id}: t_end가 유효하지 않습니다.`);
  if (seg.kind === 'rest' || seg.kind === 'uniform_acceleration') {
    pushIf(errors, !isVec(seg.position0), `${id}: position0이 필요합니다.`);
  }
  if (seg.kind === 'uniform_acceleration') {
    pushIf(errors, !isVec(seg.velocity0) || !isVec(seg.acceleration), `${id}: velocity0/acceleration이 필요합니다.`);
  }
  if (seg.kind === 'oscillation') {
    pushIf(errors, !isVec(seg.origin) || !isVec(seg.axis), `${id}: origin/axis가 필요합니다.`);
    pushIf(errors, !isFiniteNumber(seg.amplitude) || seg.amplitude <= 0, `${id}: amplitude가 유효하지 않습니다.`);
    pushIf(errors, !isFiniteNumber(seg.omega) || seg.omega <= 0, `${id}: omega가 유효하지 않습니다.`);
  }
  for (const key of ['angle0', 'angular_velocity0', 'angular_acceleration', 'phase']) {
    pushIf(errors, seg[key] != null && !isFiniteNumber(seg[key]), `${id}: ${key}가 유한한 수가 아닙니다.`);
  }
}

function validateScene(raw) {
  const errors = [];
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) {
    return { ok: false, errors: ['장면 데이터가 객체가 아닙니다.'] };
  }
  pushIf(errors, raw.schema !== SCENE_SCHEMA, `schema가 ${SCENE_SCHEMA}가 아닙니다.`);
  pushIf(errors, raw.version !== SCENE_VERSION, `지원하지 않는 장면 버전입니다: ${raw.version}`);
  pushIf(errors, raw.status !== 'ready' && raw.status !== 'unavailable', '알 수 없는 status입니다.');
  pushIf(errors, raw.simulation_mode != null && raw.simulation_mode !== 'kinematic_playback',
    '지원하지 않는 simulation_mode입니다.');
  pushIf(
    errors,
    raw.motion_readout_mode != null && !MOTION_READOUT_MODES.includes(raw.motion_readout_mode),
    '지원하지 않는 motion_readout_mode입니다.',
  );

  const authority = raw.authority;
  const authorityOk = authority && typeof authority === 'object'
    && authority.answer_authority === 'backend'
    && authority.visualization_authority === 'approximate'
    && authority.grading === false
    && authority.answer_selection === false
    && authority.student_answer_overwrite === false;
  pushIf(errors, !authorityOk, 'authority 메타데이터가 backend 정답 권위 계약과 다릅니다.');

  if (raw.status === 'unavailable') {
    pushIf(errors, !raw.fallback_reason, 'unavailable 장면에는 fallback_reason이 필요합니다.');
    return { ok: errors.length === 0, errors };
  }

  pushIf(errors, !SCENE_TYPES.includes(raw.scene_type), `알 수 없는 scene_type입니다: ${raw.scene_type}`);

  const bodies = Array.isArray(raw.bodies) ? raw.bodies : [];
  pushIf(errors, bodies.length === 0, 'ready 장면에는 body가 필요합니다.');
  const bodyIds = new Set();
  for (const body of bodies) {
    if (!body || typeof body !== 'object') { errors.push('body가 객체가 아닙니다.'); continue; }
    pushIf(errors, typeof body.id !== 'string' || !body.id, 'body id가 없습니다.');
    pushIf(errors, bodyIds.has(body.id), `body id가 중복됩니다: ${body.id}`);
    bodyIds.add(body.id);
    pushIf(errors, !BODY_ROLES.includes(body.role), `${body.id}: 알 수 없는 role입니다.`);
    pushIf(errors, body.body_type !== 'kinematic' && body.body_type !== 'fixed', `${body.id}: body_type이 유효하지 않습니다.`);
    pushIf(errors, !isVec(body.initial_position), `${body.id}: initial_position이 유효하지 않습니다.`);
    pushIf(errors, body.initial_angle != null && !isFiniteNumber(body.initial_angle), `${body.id}: initial_angle이 유한한 수가 아닙니다.`);
    const shape = body.shape;
    if (!shape || !SHAPE_KINDS.includes(shape.kind)) {
      errors.push(`${body.id}: shape가 유효하지 않습니다.`);
    } else {
      pushIf(errors, shape.angle_deg != null && !isFiniteNumber(shape.angle_deg), `${body.id}: shape.angle_deg가 유한한 수가 아닙니다.`);
      for (const key of ['half_width', 'half_height', 'radius', 'base_length']) {
        pushIf(
          errors,
          shape[key] != null && (!isFiniteNumber(shape[key]) || shape[key] <= 0),
          `${body.id}: shape.${key}는 양의 유한한 수여야 합니다.`,
        );
      }
      pushIf(errors, shape.kind === 'rect' && (!isFiniteNumber(shape.half_width) || !isFiniteNumber(shape.half_height)), `${body.id}: rect 크기가 없습니다.`);
      pushIf(errors, shape.kind === 'circle' && !isFiniteNumber(shape.radius), `${body.id}: circle 반지름이 없습니다.`);
      pushIf(errors, shape.kind === 'wedge' && (!isFiniteNumber(shape.angle_deg) || !isFiniteNumber(shape.base_length)), `${body.id}: wedge 파라미터가 없습니다.`);
    }
  }

  const motion = Array.isArray(raw.motion) ? raw.motion : [];
  pushIf(errors, motion.length === 0, 'ready 장면에는 motion segment가 필요합니다.');
  for (const seg of motion) validateSegment(seg, bodyIds, errors);
  const spansByBody = {};
  for (const seg of motion) {
    if (!seg || !isFiniteNumber(seg.t_start) || !isFiniteNumber(seg.t_end)) continue;
    const spans = spansByBody[seg.body_id] || (spansByBody[seg.body_id] = []);
    for (const [t0, t1] of spans) {
      pushIf(errors, seg.t_start < t1 && t0 < seg.t_end, `${seg.body_id}: motion segment 구간이 겹칩니다.`);
    }
    spans.push([seg.t_start, seg.t_end]);
  }

  for (const force of Array.isArray(raw.forces) ? raw.forces : []) {
    if (!force || typeof force !== 'object') { errors.push('force가 객체가 아닙니다.'); continue; }
    pushIf(errors, !bodyIds.has(force.body_id), `force ${force.id}: 존재하지 않는 body를 참조합니다.`);
    pushIf(errors, !FORCE_KINDS.includes(force.kind), `force ${force.id}: 알 수 없는 kind입니다.`);
    const restoring = force.behavior === 'restoring';
    pushIf(errors, !restoring && !isVec(force.direction), `force ${force.id}: direction이 필요합니다.`);
    for (const key of ['visible_t_start', 'visible_t_end']) {
      pushIf(errors, force[key] != null && !isFiniteNumber(force[key]), `force ${force.id}: ${key}가 유한한 수가 아닙니다.`);
    }
  }

  const camera = raw.camera;
  if (!camera || !isFiniteNumber(camera.min_x) || !isFiniteNumber(camera.min_y)
    || !isFiniteNumber(camera.max_x) || !isFiniteNumber(camera.max_y)
    || camera.max_x <= camera.min_x || camera.max_y <= camera.min_y) {
    errors.push('camera bounds가 유효하지 않습니다.');
  }

  const timestep = raw.timestep;
  if (!timestep || !isFiniteNumber(timestep.fixed_dt) || timestep.fixed_dt <= 0 || timestep.fixed_dt > 0.1
    || !isFiniteNumber(timestep.duration) || timestep.duration <= 0) {
    errors.push('timestep이 유효하지 않습니다.');
  }

  const overlay = Array.isArray(raw.answer_overlay) ? raw.answer_overlay : [];
  pushIf(errors, overlay.length === 0, 'ready 장면에는 backend answer overlay가 필요합니다.');
  for (const item of overlay) {
    pushIf(errors, !item || item.source !== 'backend', 'answer overlay 항목의 source가 backend가 아닙니다.');
    pushIf(errors, item && item.numeric != null && !isFiniteNumber(item.numeric), 'answer overlay numeric이 유한한 수가 아닙니다.');
  }

  for (const event of Array.isArray(raw.events) ? raw.events : []) {
    pushIf(errors, !event || !isFiniteNumber(event.t) || event.t < 0, 'event 시각이 유효하지 않습니다.');
  }

  return { ok: errors.length === 0, errors };
}

module.exports = {
  SCENE_SCHEMA,
  SCENE_VERSION,
  validateScene,
};
