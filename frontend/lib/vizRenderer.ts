// Phase 54: Canvas2D renderer for VisualizationScene playback.
// Pure drawing — every number it renders comes from the scene DTO or the
// closed-form motion state; nothing here feeds back into any answer.
// Vector classes are distinguished by line style + arrowhead + text label,
// never by color alone.

import type { BodyState } from './motionProgram';
import * as motion from './motionProgram';

export interface RenderOptions {
  showVelocity: boolean;
  showAcceleration: boolean;
  showForces: boolean;
}

interface Camera {
  scale: number;
  offsetX: number;
  offsetY: number;
  heightPx: number;
}

function makeCamera(scene: any, widthPx: number, heightPx: number): Camera {
  const cam = scene.camera;
  const worldW = cam.max_x - cam.min_x;
  const worldH = cam.max_y - cam.min_y;
  const scale = Math.min(widthPx / worldW, heightPx / worldH);
  const offsetX = (widthPx - worldW * scale) / 2 - cam.min_x * scale;
  const offsetY = (heightPx - worldH * scale) / 2 + cam.max_y * scale;
  return { scale, offsetX, offsetY, heightPx };
}

function toPx(camera: Camera, x: number, y: number): [number, number] {
  return [camera.offsetX + x * camera.scale, camera.offsetY - y * camera.scale];
}

const INK = '#1C1C22';
const MUTED = '#8A8A94';
const SURFACE_LINE = '#5B5E6B';
const ACCENT = '#4C4FE0';
const VELOCITY_COLOR = '#0B7A4B';
const ACCEL_COLOR = '#B4530A';
const FORCE_COLOR = '#7A3FA8';
const IMPULSE_COLOR = '#C22F3D';

function drawArrow(
  ctx: CanvasRenderingContext2D,
  x0: number, y0: number, x1: number, y1: number,
  opts: { color: string; dash?: number[]; open?: boolean; width?: number; label?: string },
) {
  const dx = x1 - x0;
  const dy = y1 - y0;
  const len = Math.hypot(dx, dy);
  if (len < 2) return;
  const ux = dx / len;
  const uy = dy / len;
  ctx.save();
  ctx.strokeStyle = opts.color;
  ctx.fillStyle = opts.color;
  ctx.lineWidth = opts.width ?? 2;
  ctx.setLineDash(opts.dash ?? []);
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1 - ux * 8, y1 - uy * 8);
  ctx.stroke();
  ctx.setLineDash([]);
  const head = 8;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x1 - ux * head - uy * head * 0.55, y1 - uy * head + ux * head * 0.55);
  ctx.lineTo(x1 - ux * head + uy * head * 0.55, y1 - uy * head - ux * head * 0.55);
  ctx.closePath();
  if (opts.open) {
    ctx.stroke();
  } else {
    ctx.fill();
  }
  if (opts.label) {
    ctx.font = '12px ui-monospace, monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    const lx = x1 + ux * 6 + 4;
    const ly = y1 + uy * 6;
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 3;
    ctx.strokeText(opts.label, lx, ly);
    ctx.fillText(opts.label, lx, ly);
  }
  ctx.restore();
}

function drawWedge(ctx: CanvasRenderingContext2D, camera: Camera, body: any) {
  const { angle_deg, base_length } = body.shape;
  const px = body.initial_position.x;
  const py = body.initial_position.y;
  const h = base_length * Math.tan((angle_deg * Math.PI) / 180);
  const p0 = toPx(camera, px, py);
  const p1 = toPx(camera, px + base_length, py);
  const p2 = toPx(camera, px, py + h);
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(p0[0], p0[1]);
  ctx.lineTo(p1[0], p1[1]);
  ctx.lineTo(p2[0], p2[1]);
  ctx.closePath();
  ctx.fillStyle = 'rgba(91,94,107,0.12)';
  ctx.fill();
  ctx.strokeStyle = SURFACE_LINE;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.restore();
}

function drawRect(ctx: CanvasRenderingContext2D, camera: Camera, state: BodyState, body: any, fill: string) {
  const [cx, cy] = toPx(camera, state.x, state.y);
  const w = body.shape.half_width * camera.scale;
  const h = body.shape.half_height * camera.scale;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(-state.angle);
  ctx.beginPath();
  ctx.rect(-w, -h, 2 * w, 2 * h);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = INK;
  ctx.lineWidth = 1.6;
  ctx.stroke();
  ctx.restore();
}

function drawWheel(ctx: CanvasRenderingContext2D, camera: Camera, state: BodyState, body: any) {
  const [cx, cy] = toPx(camera, state.x, state.y);
  const r = body.shape.radius * camera.scale;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(76,79,224,0.10)';
  ctx.fill();
  ctx.strokeStyle = INK;
  ctx.lineWidth = 1.8;
  ctx.stroke();
  // Spoke shows rotation; center and lowest (contact-side) point are marked.
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + r * Math.cos(-state.angle), cy + r * Math.sin(-state.angle));
  ctx.strokeStyle = ACCENT;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(cx, cy, 2.6, 0, Math.PI * 2);
  ctx.fillStyle = INK;
  ctx.fill();
  ctx.restore();
}

function drawWall(ctx: CanvasRenderingContext2D, camera: Camera, body: any, emphasized: boolean) {
  const [cx, cy] = toPx(camera, body.initial_position.x, body.initial_position.y);
  const w = Math.max(2, body.shape.half_width * camera.scale);
  const h = body.shape.half_height * camera.scale;
  ctx.save();
  if (emphasized) {
    ctx.fillStyle = 'rgba(91,94,107,0.25)';
    ctx.fillRect(cx - w, cy - h, 2 * w, 2 * h);
    ctx.strokeStyle = SURFACE_LINE;
    ctx.strokeRect(cx - w, cy - h, 2 * w, 2 * h);
  } else {
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = MUTED;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(cx, cy - h);
    ctx.lineTo(cx, cy + h);
    ctx.stroke();
  }
  ctx.restore();
}

function drawGround(ctx: CanvasRenderingContext2D, camera: Camera, body: any) {
  const [cx, cy] = toPx(camera, body.initial_position.x, body.initial_position.y);
  const w = body.shape.half_width * camera.scale;
  ctx.save();
  ctx.strokeStyle = SURFACE_LINE;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(cx - w, cy);
  ctx.lineTo(cx + w, cy);
  ctx.stroke();
  ctx.restore();
}

function drawSpring(ctx: CanvasRenderingContext2D, camera: Camera, body: any, massState: BodyState | null) {
  if (!massState) return;
  const [x0, y0] = toPx(camera, body.initial_position.x, body.initial_position.y);
  const [x1, y1] = toPx(camera, massState.x, massState.y);
  const coils = 9;
  const amp = Math.max(4, (body.shape.half_height ?? 0.15) * camera.scale);
  ctx.save();
  ctx.strokeStyle = INK;
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  const dx = x1 - x0;
  const dy = y1 - y0;
  for (let i = 1; i < coils * 2; i += 1) {
    const f = i / (coils * 2);
    const perp = i % 2 === 0 ? 0 : (i % 4 === 1 ? amp : -amp);
    ctx.lineTo(x0 + dx * f - (dy === 0 ? 0 : perp), y0 + dy * f + perp * (dy === 0 ? 1 : 0));
  }
  ctx.lineTo(x1, y1);
  ctx.stroke();
  ctx.restore();
}

export function renderScene(
  canvas: HTMLCanvasElement,
  scene: any,
  t: number,
  options: RenderOptions,
  states?: Record<string, BodyState>,
): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const dpr = Math.min(typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1, 2);
  const widthPx = canvas.width / dpr;
  const heightPx = canvas.height / dpr;
  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, widthPx, heightPx);
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, widthPx, heightPx);

  const camera = makeCamera(scene, widthPx, heightPx);
  const allStates = states ?? motion.evaluateAll(scene, t);

  const kinematicIds = (scene.bodies as any[]).filter((b) => b.body_type === 'kinematic').map((b) => b.id);
  const firstKinematic = kinematicIds.length ? allStates[kinematicIds[0]] : null;

  for (const body of scene.bodies as any[]) {
    const state = allStates[body.id];
    switch (body.shape.kind) {
      case 'wedge': drawWedge(ctx, camera, body); break;
      case 'ground_line': drawGround(ctx, camera, body); break;
      case 'wall': drawWall(ctx, camera, body, body.role === 'wall'); break;
      case 'spring_coil': drawSpring(ctx, camera, body, firstKinematic); break;
      case 'circle': drawWheel(ctx, camera, state, body); break;
      case 'rect':
      default:
        drawRect(ctx, camera, state, body, body.role === 'cart' ? 'rgba(76,79,224,0.10)' : 'rgba(76,79,224,0.14)');
        break;
    }
  }

  // Positive-direction axes.
  for (const axis of (scene.axes || []) as any[]) {
    const [x0, y0] = toPx(camera, axis.origin.x, axis.origin.y);
    const [x1, y1] = toPx(
      camera,
      axis.origin.x + axis.direction.x * 1.4,
      axis.origin.y + axis.direction.y * 1.4,
    );
    drawArrow(ctx, x0, y0, x1, y1, { color: MUTED, width: 1.6, label: '+x' });
  }

  // Force arrows: dashed + label. Restoring arrows follow the current state.
  if (options.showForces) {
    for (const force of (scene.forces || []) as any[]) {
      if (!motion.forceVisibleAt(force, t)) continue;
      const state = allStates[force.body_id];
      if (!state) continue;
      let dir = force.direction as { x: number; y: number } | null;
      if (force.behavior === 'restoring') {
        dir = motion.restoringDirection(scene, force, t);
      }
      if (!dir || (dir.x === 0 && dir.y === 0)) continue;
      const arrowLen = 1.1;
      const [x0, y0] = toPx(camera, state.x, state.y);
      const [x1, y1] = toPx(camera, state.x + dir.x * arrowLen, state.y + dir.y * arrowLen);
      const color = force.kind === 'impulse' ? IMPULSE_COLOR : FORCE_COLOR;
      drawArrow(ctx, x0, y0, x1, y1, {
        color,
        dash: [6, 4],
        label: force.symbol || force.kind,
        width: force.kind === 'impulse' ? 2.6 : 2,
      });
    }
  }

  // Velocity (solid, filled head) and acceleration (solid, open head) arrows.
  for (const id of kinematicIds) {
    const state = allStates[id];
    if (!state) continue;
    const [x0, y0] = toPx(camera, state.x, state.y);
    if (options.showVelocity) {
      const vLen = Math.hypot(state.vx, state.vy);
      if (vLen > 1e-6) {
        const s = Math.min(0.28 * vLen, 1.8);
        const [x1, y1] = toPx(camera, state.x + (state.vx / vLen) * s, state.y + (state.vy / vLen) * s);
        drawArrow(ctx, x0, y0, x1, y1, { color: VELOCITY_COLOR, label: 'v', width: 2.4 });
      }
    }
    if (options.showAcceleration) {
      const aLen = Math.hypot(state.ax, state.ay);
      if (aLen > 1e-6) {
        const s = Math.min(0.22 * aLen, 1.5);
        const [x1, y1] = toPx(camera, state.x + (state.ax / aLen) * s, state.y + (state.ay / aLen) * s);
        drawArrow(ctx, x0, y0, x1, y1, { color: ACCEL_COLOR, label: 'a', open: true, width: 2.2 });
      }
    }
  }

  // Event flash marker near the collision instant.
  for (const event of (scene.events || []) as any[]) {
    if (Math.abs(t - event.t) <= 0.12 && firstKinematic) {
      ctx.save();
      ctx.font = 'bold 13px system-ui, sans-serif';
      ctx.fillStyle = IMPULSE_COLOR;
      ctx.textAlign = 'center';
      const [ex, ey] = toPx(camera, 0, 1.4);
      ctx.fillText(`⚡ ${event.label}`, ex, ey);
      ctx.restore();
    }
  }

  ctx.restore();
}
